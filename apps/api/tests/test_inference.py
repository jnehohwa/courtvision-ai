from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pytest
from sqlalchemy import delete, select, update

from courtvision.database import SessionFactory
from courtvision.inference import ActiveModelResolver, active_model_resolver
from courtvision.model_contracts import (
    LIVE_WIN_CONTRACT,
    MODEL_CONTRACTS,
    PREGAME_CONTRACT,
    SHOT_QUALITY_CONTRACT,
    ModelContract,
)
from courtvision.model_runtime import current_model_runtime
from courtvision.models import FeatureSnapshot, ModelVersion


class ConstantBinaryClassifier:
    classes_ = [0, 1]

    def __init__(self, features: tuple[str, ...], probability: float) -> None:
        self.feature_names_in_ = list(features)
        self.probability = probability

    def predict_proba(self, frame):
        return [
            [1 - self.probability, self.probability]
            for _ in range(len(frame))
        ]


class InvalidClassOrderClassifier(ConstantBinaryClassifier):
    classes_ = [1, 0]


class RequestFailureClassifier(ConstantBinaryClassifier):
    def predict_proba(self, frame):
        if (frame["x"] < 0).any():
            raise ValueError("negative x is unsupported")
        return super().predict_proba(frame)


class InMemoryArtifactStore:
    def __init__(self, artifact_bytes: bytes) -> None:
        self.artifact_bytes = artifact_bytes
        self.read_count = 0

    def read_verified_sync(
        self,
        artifact_uri: str,
        expected_sha256: str,
    ) -> bytes:
        self.read_count += 1
        assert artifact_uri
        assert hashlib.sha256(self.artifact_bytes).hexdigest() == expected_sha256
        return self.artifact_bytes


def write_artifact(
    path: Path,
    contract: ModelContract,
    probability: float,
    *,
    model_class=ConstantBinaryClassifier,
) -> str:
    joblib.dump(model_class(contract.features, probability), path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def activate_artifact(
    contract: ModelContract,
    *,
    version: str,
    artifact: Path,
    artifact_sha256: str,
    features: list[str] | None = None,
    schema_version: str | None = None,
    runtime: dict[str, str] | None = None,
) -> None:
    async with SessionFactory() as session, session.begin():
        active = await session.scalar(
            select(ModelVersion).where(
                ModelVersion.model_type == contract.model_type,
                ModelVersion.is_active.is_(True),
            )
        )
        if active is not None:
            active.status = "retired"
            active.is_active = False
            active.deactivated_at = datetime.now(UTC)
            await session.flush()
        await session.execute(
            delete(ModelVersion).where(
                ModelVersion.model_type == contract.model_type,
                ModelVersion.version == version,
            )
        )
        session.add(
            ModelVersion(
                model_type=contract.model_type,
                version=version,
                artifact_uri=str(artifact),
                artifact_sha256=artifact_sha256,
                feature_schema={
                    "features": features or list(contract.features),
                    "schema_version": schema_version or contract.schema_version,
                },
                metrics={
                    "brier_score": 0.2,
                    "log_loss": 0.6,
                    "expected_calibration_error": 0.03,
                },
                dataset_version="inference-test-v1",
                training_commit="a" * 40,
                promotion_metadata={
                    "runtime": runtime or current_model_runtime(),
                },
                status="active",
                is_active=True,
                activated_at=datetime.now(UTC),
            )
        )


async def restore_baselines() -> None:
    async with SessionFactory() as session, session.begin():
        for contract in MODEL_CONTRACTS.values():
            active = await session.scalar(
                select(ModelVersion).where(
                    ModelVersion.model_type == contract.model_type,
                    ModelVersion.is_active.is_(True),
                )
            )
            if active is not None and active.version != contract.baseline_version:
                active.status = "retired"
                active.is_active = False
                active.deactivated_at = datetime.now(UTC)
                await session.flush()
            await session.execute(
                delete(ModelVersion).where(
                    ModelVersion.model_type == contract.model_type,
                    ModelVersion.version.like("test-%"),
                )
            )
            await session.execute(
                update(ModelVersion)
                .where(
                    ModelVersion.model_type == contract.model_type,
                    ModelVersion.version == contract.baseline_version,
                )
                .values(
                    status="active",
                    is_active=True,
                    deactivated_at=None,
                )
            )


async def set_pregame_snapshot_schema(schema_version: str) -> None:
    async with SessionFactory() as session, session.begin():
        await session.execute(
            update(FeatureSnapshot)
            .where(
                FeatureSnapshot.game_id == "cv-2026-bos-nyk",
                FeatureSnapshot.model_type == "pregame",
            )
            .values(schema_version=schema_version)
        )


@pytest.fixture(autouse=True)
async def reset_inference_registry(database):
    active_model_resolver.clear()
    yield
    active_model_resolver.clear()
    await restore_baselines()


def test_shot_quality_uses_active_artifact(client, tmp_path: Path):
    artifact = tmp_path / "shot.joblib"
    artifact_hash = write_artifact(artifact, SHOT_QUALITY_CONTRACT, 0.8)
    asyncio.run(
        activate_artifact(
            SHOT_QUALITY_CONTRACT,
            version="test-shot-2.0",
            artifact=artifact,
            artifact_sha256=artifact_hash,
        )
    )

    response = client.post(
        "/api/v1/shot-quality",
        json={
            "player_id": "p-brunson",
            "attempts": [
                {
                    "x": 12,
                    "y": 21,
                    "shot_value": 3,
                    "period": 4,
                    "game_clock_seconds": 181,
                    "score_differential": -2,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["model_version"] == "test-shot-2.0"
    assert response.json()["attempts"][0]["make_probability"] == 0.8
    assert response.json()["attempts"][0]["expected_points"] == 2.4


def test_pregame_response_uses_active_artifact(client, tmp_path: Path):
    artifact = tmp_path / "pregame.joblib"
    artifact_hash = write_artifact(artifact, PREGAME_CONTRACT, 0.73)
    asyncio.run(
        activate_artifact(
            PREGAME_CONTRACT,
            version="test-pregame-2.0",
            artifact=artifact,
            artifact_sha256=artifact_hash,
        )
    )

    response = client.get("/api/v1/games/cv-2026-bos-nyk/prediction")

    assert response.status_code == 200
    assert response.json()["model_version"] == "test-pregame-2.0"
    assert response.json()["home_probability"] == 0.73
    assert response.json()["confidence"] == "active calibrated artifact"


def test_pregame_snapshot_schema_mismatch_falls_back(client, tmp_path: Path):
    artifact = tmp_path / "pregame-schema.joblib"
    artifact_hash = write_artifact(artifact, PREGAME_CONTRACT, 0.73)
    asyncio.run(
        activate_artifact(
            PREGAME_CONTRACT,
            version="test-pregame-schema",
            artifact=artifact,
            artifact_sha256=artifact_hash,
        )
    )
    asyncio.run(set_pregame_snapshot_schema("legacy-v0"))
    try:
        response = client.get("/api/v1/games/cv-2026-bos-nyk/prediction")
    finally:
        asyncio.run(
            set_pregame_snapshot_schema(PREGAME_CONTRACT.schema_version)
        )

    assert response.status_code == 200
    assert response.json()["model_version"] == PREGAME_CONTRACT.baseline_version
    assert response.json()["home_probability"] == 0.58


def test_live_snapshot_uses_one_pinned_active_version(client, tmp_path: Path):
    artifact = tmp_path / "live.joblib"
    artifact_hash = write_artifact(artifact, LIVE_WIN_CONTRACT, 0.64)
    asyncio.run(
        activate_artifact(
            LIVE_WIN_CONTRACT,
            version="test-live-2.0",
            artifact=artifact,
            artifact_sha256=artifact_hash,
        )
    )

    response = client.get("/api/v1/games/cv-2026-bos-nyk/live")

    assert response.status_code == 200
    assert response.json()["live_model_version"] == "test-live-2.0"
    assert {
        point["home_probability"]
        for point in response.json()["timeline"]
    } == {0.64}


@pytest.mark.parametrize(
    "failure_mode",
    ["missing", "tampered", "schema", "runtime"],
)
def test_invalid_shot_artifact_falls_back_to_baseline(
    client,
    tmp_path: Path,
    failure_mode: str,
):
    artifact = tmp_path / "invalid-shot.joblib"
    artifact_hash = write_artifact(artifact, SHOT_QUALITY_CONTRACT, 0.8)
    features = list(SHOT_QUALITY_CONTRACT.features)
    if failure_mode == "missing":
        artifact.unlink()
    elif failure_mode == "tampered":
        artifact.write_bytes(b"tampered")
    else:
        if failure_mode == "schema":
            features.reverse()
    runtime = current_model_runtime()
    if failure_mode == "runtime":
        runtime["scikit_learn"] = "0.0"

    asyncio.run(
        activate_artifact(
            SHOT_QUALITY_CONTRACT,
            version=f"test-shot-{failure_mode}",
            artifact=artifact,
            artifact_sha256=artifact_hash,
            features=features,
            runtime=runtime,
        )
    )

    response = client.post(
        "/api/v1/shot-quality",
        json={
            "player_id": "p-brunson",
            "attempts": [
                {
                    "x": 12,
                    "y": 21,
                    "shot_value": 3,
                    "period": 4,
                    "game_clock_seconds": 181,
                    "score_differential": -2,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["model_version"] == SHOT_QUALITY_CONTRACT.baseline_version


def test_invalid_class_order_falls_back_before_inference(client, tmp_path: Path):
    artifact = tmp_path / "invalid-classes.joblib"
    artifact_hash = write_artifact(
        artifact,
        SHOT_QUALITY_CONTRACT,
        0.8,
        model_class=InvalidClassOrderClassifier,
    )
    asyncio.run(
        activate_artifact(
            SHOT_QUALITY_CONTRACT,
            version="test-shot-invalid-classes",
            artifact=artifact,
            artifact_sha256=artifact_hash,
        )
    )

    response = client.post(
        "/api/v1/shot-quality",
        json={
            "player_id": "p-brunson",
            "attempts": [
                {
                    "x": 12,
                    "y": 21,
                    "shot_value": 3,
                    "period": 4,
                    "game_clock_seconds": 181,
                    "score_differential": -2,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["model_version"] == SHOT_QUALITY_CONTRACT.baseline_version


def test_request_specific_model_failure_falls_back(client, tmp_path: Path):
    artifact = tmp_path / "runtime-failure.joblib"
    artifact_hash = write_artifact(
        artifact,
        SHOT_QUALITY_CONTRACT,
        0.8,
        model_class=RequestFailureClassifier,
    )
    asyncio.run(
        activate_artifact(
            SHOT_QUALITY_CONTRACT,
            version="test-shot-runtime-failure",
            artifact=artifact,
            artifact_sha256=artifact_hash,
        )
    )

    response = client.post(
        "/api/v1/shot-quality",
        json={
            "player_id": "p-brunson",
            "attempts": [
                {
                    "x": -1,
                    "y": 3,
                    "shot_value": 2,
                    "period": 1,
                    "game_clock_seconds": 500,
                    "score_differential": 0,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["model_version"] == SHOT_QUALITY_CONTRACT.baseline_version


async def test_concurrent_cold_cache_loads_artifact_once(
    database,
    tmp_path: Path,
    monkeypatch,
):
    artifact = tmp_path / "concurrent.joblib"
    artifact_hash = write_artifact(artifact, PREGAME_CONTRACT, 0.7)
    await activate_artifact(
        PREGAME_CONTRACT,
        version="test-pregame-concurrent",
        artifact=artifact,
        artifact_sha256=artifact_hash,
    )
    resolver = ActiveModelResolver()
    original_loader = resolver._load_artifact
    load_count = 0

    def counted_loader(registered, contract):
        nonlocal load_count
        load_count += 1
        time.sleep(0.05)
        return original_loader(registered, contract)

    monkeypatch.setattr(resolver, "_load_artifact", counted_loader)

    async with SessionFactory() as first_session, SessionFactory() as second_session:
        first, second = await asyncio.gather(
            resolver.resolve(first_session, "pregame"),
            resolver.resolve(second_session, "pregame"),
        )

    assert first is second
    assert load_count == 1


async def test_resolver_reads_injected_remote_store_only_once(
    database,
    tmp_path: Path,
):
    artifact = tmp_path / "remote.joblib"
    artifact_hash = write_artifact(artifact, PREGAME_CONTRACT, 0.77)
    artifact_bytes = artifact.read_bytes()
    await activate_artifact(
        PREGAME_CONTRACT,
        version="test-pregame-remote",
        artifact=artifact,
        artifact_sha256=artifact_hash,
    )
    artifact.unlink()
    store = InMemoryArtifactStore(artifact_bytes)
    resolver = ActiveModelResolver(artifact_store=store)

    async with SessionFactory() as session:
        first = await resolver.resolve(session, "pregame")
        second = await resolver.resolve(session, "pregame")

    assert first is not None and first.version == "test-pregame-remote"
    assert second is first
    assert store.read_count == 1


async def test_resolver_loads_new_artifact_after_promotion(
    database,
    tmp_path: Path,
):
    first_artifact = tmp_path / "first.joblib"
    first_hash = write_artifact(first_artifact, PREGAME_CONTRACT, 0.6)
    await activate_artifact(
        PREGAME_CONTRACT,
        version="test-pregame-first",
        artifact=first_artifact,
        artifact_sha256=first_hash,
    )
    resolver = ActiveModelResolver()
    async with SessionFactory() as session:
        first = await resolver.resolve(session, "pregame")

    second_artifact = tmp_path / "second.joblib"
    second_hash = write_artifact(second_artifact, PREGAME_CONTRACT, 0.7)
    await activate_artifact(
        PREGAME_CONTRACT,
        version="test-pregame-second",
        artifact=second_artifact,
        artifact_sha256=second_hash,
    )
    async with SessionFactory() as session:
        second = await resolver.resolve(session, "pregame")

    assert first is not None and first.version == "test-pregame-first"
    assert second is not None and second.version == "test-pregame-second"
    assert first is not second
