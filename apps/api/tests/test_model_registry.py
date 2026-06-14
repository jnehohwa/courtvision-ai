from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from courtvision.database import SessionFactory
from courtvision.model_registry import (
    CandidateManifest,
    ModelRegistry,
    PromotionRejectedError,
)
from courtvision.models import ModelActivation, ModelVersion


@pytest.fixture(autouse=True)
async def reset_pregame_registry(database):
    async with SessionFactory() as session, session.begin():
        await session.execute(delete(ModelActivation).where(ModelActivation.model_type == "pregame"))
        await session.execute(
            delete(ModelVersion).where(
                ModelVersion.model_type == "pregame",
                ModelVersion.version != "pregame-logistic-baseline-1.0",
            )
        )
        await session.execute(
            update(ModelVersion)
            .where(
                ModelVersion.model_type == "pregame",
                ModelVersion.version == "pregame-logistic-baseline-1.0",
            )
            .values(
                status="active",
                is_active=True,
                deactivated_at=None,
                artifact_uri=None,
                artifact_sha256=None,
            )
        )
    yield


def candidate_manifest(
    *,
    version: str,
    artifact: Path,
    brier_score: float = 0.20,
    log_loss: float = 0.60,
    expected_calibration_error: float = 0.03,
    incumbent_version: str | None = None,
    incumbent_artifact: Path | None = None,
    incumbent_brier_score: float = 0.20,
    incumbent_log_loss: float = 0.60,
) -> CandidateManifest:
    return CandidateManifest.model_validate(
        {
            "model_type": "pregame",
            "model_version": version,
            "winner": "logistic",
            "features": [
                "home_offensive_rating",
                "away_offensive_rating",
            ],
            "metrics": {
                "brier_score": brier_score,
                "log_loss": log_loss,
                "expected_calibration_error": expected_calibration_error,
            },
            "baseline": {
                "name": "training_home_win_prevalence",
                "metrics": {
                    "brier_score": 0.26,
                    "log_loss": 0.70,
                    "expected_calibration_error": 0.04,
                },
            },
            "split": "chronological_last_two_seasons",
            "dataset": {
                "path": "s3://courtvision/pregame.parquet",
                "version": "pregame-2015-2025-v1",
            },
            "artifact": {
                "filename": artifact.name,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            },
            "calibration": {
                "method": "sigmoid",
                "artifact": "embedded",
            },
            "incumbent": (
                {
                    "model_version": incumbent_version,
                    "artifact_sha256": hashlib.sha256(
                        incumbent_artifact.read_bytes()
                    ).hexdigest(),
                    "metrics": {
                        "brier_score": incumbent_brier_score,
                        "log_loss": incumbent_log_loss,
                        "expected_calibration_error": 0.03,
                    },
                }
                if incumbent_version and incumbent_artifact
                else None
            ),
            "feature_schema_version": "pregame-v1",
            "training_commit": "a" * 40,
            "activation_status": "candidate",
        }
    )


async def test_registry_promotes_candidate_and_retains_previous_model(
    database,
    tmp_path: Path,
):
    artifact = tmp_path / "model.joblib"
    artifact.write_bytes(b"candidate-one")
    registry = ModelRegistry()

    async with SessionFactory() as session, session.begin():
        result = await registry.register_and_activate(
            session,
            manifest=candidate_manifest(
                version="pregame-candidate-2.0",
                artifact=artifact,
            ),
            artifact_path=artifact,
        )

    async with SessionFactory() as session:
        active = await session.scalar(
            select(ModelVersion).where(
                ModelVersion.model_type == "pregame",
                ModelVersion.is_active.is_(True),
            )
        )
        previous = await session.scalar(
            select(ModelVersion).where(
                ModelVersion.model_type == "pregame",
                ModelVersion.version == "pregame-logistic-baseline-1.0",
            )
        )
        activation = await session.scalar(
            select(ModelActivation).order_by(ModelActivation.id.desc())
        )

        assert result.previous_active_version == "pregame-logistic-baseline-1.0"
        assert active is not None and active.version == "pregame-candidate-2.0"
        assert active.artifact_sha256 == result.artifact_sha256
        assert previous is not None and previous.status == "retired"
        assert not previous.is_active
        assert activation is not None and activation.action == "promote"


async def test_registry_rejects_candidate_that_does_not_beat_active_model(
    database,
    tmp_path: Path,
):
    artifact = tmp_path / "weaker.joblib"
    artifact.write_bytes(b"weaker-candidate")
    stronger_artifact = tmp_path / "stronger.joblib"
    stronger_artifact.write_bytes(b"stronger-candidate")
    registry = ModelRegistry()

    async with SessionFactory() as session, session.begin():
        await registry.register_and_activate(
            session,
            manifest=candidate_manifest(
                version="pregame-candidate-strong",
                artifact=stronger_artifact,
            ),
            artifact_path=stronger_artifact,
        )

    async with SessionFactory() as session:
        with pytest.raises(PromotionRejectedError, match="incumbent model"):
            async with session.begin():
                await registry.register_and_activate(
                    session,
                    manifest=candidate_manifest(
                        version="pregame-candidate-weak",
                        artifact=artifact,
                        brier_score=0.21,
                        log_loss=0.61,
                        incumbent_version="pregame-candidate-strong",
                        incumbent_artifact=stronger_artifact,
                    ),
                    artifact_path=artifact,
                )

    async with SessionFactory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ModelVersion)
            .where(ModelVersion.version == "pregame-candidate-weak")
        )
        assert count == 0


async def test_registry_requires_same_split_incumbent_evaluation(
    database,
    tmp_path: Path,
):
    active_artifact = tmp_path / "active.joblib"
    active_artifact.write_bytes(b"active-candidate")
    replacement_artifact = tmp_path / "replacement.joblib"
    replacement_artifact.write_bytes(b"replacement-candidate")
    registry = ModelRegistry()

    async with SessionFactory() as session, session.begin():
        await registry.register_and_activate(
            session,
            manifest=candidate_manifest(
                version="pregame-candidate-active",
                artifact=active_artifact,
            ),
            artifact_path=active_artifact,
        )

    async with SessionFactory() as session:
        with pytest.raises(PromotionRejectedError, match="candidate test split"):
            async with session.begin():
                await registry.register_and_activate(
                    session,
                    manifest=candidate_manifest(
                        version="pregame-candidate-replacement",
                        artifact=replacement_artifact,
                        brier_score=0.18,
                        log_loss=0.55,
                    ),
                    artifact_path=replacement_artifact,
                )


async def test_registry_rejects_artifact_that_changed_after_training(
    database,
    tmp_path: Path,
):
    artifact = tmp_path / "model.joblib"
    artifact.write_bytes(b"evaluated-artifact")
    manifest = candidate_manifest(
        version="pregame-candidate-tampered",
        artifact=artifact,
    )
    artifact.write_bytes(b"tampered-artifact")

    async with SessionFactory() as session:
        with pytest.raises(PromotionRejectedError, match="SHA-256"):
            async with session.begin():
                await ModelRegistry().register_and_activate(
                    session,
                    manifest=manifest,
                    artifact_path=artifact,
                )


async def test_registry_rolls_back_to_retained_model(database, tmp_path: Path):
    candidate_artifact = tmp_path / "candidate.joblib"
    candidate_artifact.write_bytes(b"candidate")
    baseline_artifact = tmp_path / "baseline.joblib"
    baseline_artifact.write_bytes(b"baseline")
    registry = ModelRegistry()

    async with SessionFactory() as session, session.begin():
        await registry.register_and_activate(
            session,
            manifest=candidate_manifest(
                version="pregame-candidate-2.0",
                artifact=candidate_artifact,
            ),
            artifact_path=candidate_artifact,
        )
        baseline = await session.scalar(
            select(ModelVersion).where(
                ModelVersion.model_type == "pregame",
                ModelVersion.version == "pregame-logistic-baseline-1.0",
            )
        )
        assert baseline is not None
        baseline.artifact_uri = str(baseline_artifact)
        baseline.artifact_sha256 = registry._sha256(baseline_artifact)

        result = await registry.rollback(
            session,
            model_type="pregame",
            version=baseline.version,
            reason="test rollback",
        )

    async with SessionFactory() as session:
        active = await session.scalar(
            select(ModelVersion).where(
                ModelVersion.model_type == "pregame",
                ModelVersion.is_active.is_(True),
            )
        )
        activation = await session.scalar(
            select(ModelActivation)
            .where(ModelActivation.action == "rollback")
            .order_by(ModelActivation.id.desc())
        )

        assert result.previous_active_version == "pregame-candidate-2.0"
        assert active is not None
        assert active.version == "pregame-logistic-baseline-1.0"
        assert activation is not None
        assert activation.previous_model_version == "pregame-candidate-2.0"


async def test_seed_does_not_replace_promoted_active_model(database):
    from courtvision.seed import seed_database

    artifact = Path(__file__).parent / "promoted-model.joblib"
    artifact.write_bytes(b"promoted")
    try:
        async with SessionFactory() as session, session.begin():
            await ModelRegistry().register_and_activate(
                session,
                manifest=candidate_manifest(
                    version="pregame-candidate-2.0",
                    artifact=artifact,
                ),
                artifact_path=artifact,
            )

        await seed_database()

        async with SessionFactory() as session:
            active = await session.scalar(
                select(ModelVersion).where(
                    ModelVersion.model_type == "pregame",
                    ModelVersion.is_active.is_(True),
                )
            )
            assert active is not None
            assert active.version == "pregame-candidate-2.0"
    finally:
        artifact.unlink(missing_ok=True)


def registry_row(
    *,
    model_type: str,
    version: str,
    status: str,
    is_active: bool,
) -> ModelVersion:
    return ModelVersion(
        model_type=model_type,
        version=version,
        feature_schema={"features": ["score"], "schema_version": "test-v1"},
        metrics={
            "brier_score": 0.2,
            "log_loss": 0.6,
            "expected_calibration_error": 0.03,
        },
        dataset_version="test-dataset-v1",
        status=status,
        is_active=is_active,
    )


async def test_database_rejects_status_active_mismatch(database):
    async with SessionFactory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add(
                    registry_row(
                        model_type="status-constraint",
                        version="invalid",
                        status="active",
                        is_active=False,
                    )
                )


async def test_database_allows_only_one_active_version_per_type(database):
    async with SessionFactory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add_all(
                    [
                        registry_row(
                            model_type="unique-active",
                            version="one",
                            status="active",
                            is_active=True,
                        ),
                        registry_row(
                            model_type="unique-active",
                            version="two",
                            status="active",
                            is_active=True,
                        ),
                    ]
                )


async def test_activation_history_requires_registered_versions(database):
    async with SessionFactory() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add(
                    ModelActivation(
                        model_type="missing-model",
                        model_version="missing-version",
                        previous_model_version=None,
                        action="promote",
                        reason="invalid test activation",
                        activated_at=datetime.now(UTC),
                        metrics_snapshot={},
                    )
                )
