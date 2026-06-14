from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from courtvision.artifact_store import ModelArtifactStore, model_artifact_store
from courtvision.database import SessionFactory
from courtvision.model_runtime import current_model_runtime
from courtvision.models import ModelActivation, ModelVersion


class EvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    brier_score: float = Field(ge=0, le=1)
    log_loss: float = Field(ge=0)
    expected_calibration_error: float = Field(ge=0, le=1)


class BaselineManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    metrics: EvaluationMetrics


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    version: str = Field(min_length=1, max_length=100)


class ArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CalibrationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str = Field(min_length=1)
    artifact: str = Field(min_length=1)


class IncumbentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_version: str = Field(min_length=1, max_length=40)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics: EvaluationMetrics


class RuntimeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    python: str = Field(min_length=3)
    joblib: str = Field(min_length=1)
    numpy: str = Field(min_length=1)
    pandas: str = Field(min_length=1)
    scikit_learn: str = Field(min_length=1)


class CandidateManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_type: str = Field(min_length=1, max_length=40)
    model_version: str = Field(min_length=1, max_length=40)
    winner: str = Field(min_length=1)
    features: list[str] = Field(min_length=1)
    metrics: EvaluationMetrics
    baseline: BaselineManifest
    split: str = Field(min_length=1)
    dataset: DatasetManifest
    artifact: ArtifactManifest
    calibration: CalibrationManifest
    runtime: RuntimeManifest
    incumbent: IncumbentManifest | None = None
    feature_schema_version: str = Field(min_length=1, max_length=20)
    training_commit: str = Field(min_length=1, max_length=64)
    activation_status: Literal["candidate"]


@dataclass(frozen=True)
class RegistryResult:
    model_type: str
    version: str
    status: str
    previous_active_version: str | None
    artifact_sha256: str


class PromotionRejectedError(RuntimeError):
    pass


class ModelRegistry:
    max_expected_calibration_error = 0.05

    def __init__(
        self,
        artifact_store: ModelArtifactStore = model_artifact_store,
    ) -> None:
        self.artifact_store = artifact_store

    async def register_and_activate(
        self,
        session: AsyncSession,
        *,
        manifest: CandidateManifest,
        artifact_path: Path,
        calibration_path: Path | None = None,
        reason: str = "candidate passed promotion gates",
    ) -> RegistryResult:
        if manifest.training_commit == "uncommitted":
            raise PromotionRejectedError(
                "An uncommitted training artifact cannot be activated"
            )
        if manifest.runtime.model_dump() != current_model_runtime():
            raise PromotionRejectedError(
                "Artifact runtime versions do not match the registry environment"
            )
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Model artifact not found: {artifact_path}")
        if calibration_path is not None and not calibration_path.is_file():
            raise FileNotFoundError(
                f"Calibration artifact not found: {calibration_path}"
            )

        await self._lock_model_type(session, manifest.model_type)
        active = await self._active_model(
            session,
            manifest.model_type,
            for_update=True,
        )
        self._assert_improves(
            manifest.metrics,
            manifest.baseline.metrics,
            baseline_name=manifest.baseline.name,
        )
        if active is not None:
            if active.artifact_sha256:
                if manifest.incumbent is None:
                    raise PromotionRejectedError(
                        "The active artifact must be evaluated on the candidate test split"
                    )
                if (
                    manifest.incumbent.model_version != active.version
                    or manifest.incumbent.artifact_sha256 != active.artifact_sha256
                ):
                    raise PromotionRejectedError(
                        "Incumbent identity does not match the active registry model"
                    )
                self._assert_improves(
                    manifest.metrics,
                    manifest.incumbent.metrics,
                    baseline_name=f"incumbent model {active.version}",
                )
            else:
                self._assert_improves(
                    manifest.metrics,
                    self._stored_metrics(active),
                    baseline_name=f"active baseline {active.version}",
                )

        artifact_sha256 = await asyncio.to_thread(self._sha256, artifact_path)
        if artifact_path.name != manifest.artifact.filename:
            raise PromotionRejectedError(
                "Artifact filename does not match the training manifest"
            )
        if artifact_sha256 != manifest.artifact.sha256:
            raise PromotionRejectedError(
                "Artifact SHA-256 does not match the training manifest"
            )
        existing = await session.scalar(
            select(ModelVersion)
            .where(
                ModelVersion.model_type == manifest.model_type,
                ModelVersion.version == manifest.model_version,
            )
            .with_for_update()
        )
        if existing is not None and existing.artifact_sha256 not in {
            None,
            artifact_sha256,
        }:
            raise PromotionRejectedError(
                "The model version is already registered with a different artifact"
            )

        artifact_uri = await self.artifact_store.publish(
            artifact_path,
            model_type=manifest.model_type,
            version=manifest.model_version,
            artifact_kind="model",
            expected_sha256=artifact_sha256,
        )
        calibration_uri = None
        calibration_sha256 = None
        if calibration_path is not None:
            calibration_sha256 = await asyncio.to_thread(
                self._sha256,
                calibration_path,
            )
            calibration_uri = await self.artifact_store.publish(
                calibration_path,
                model_type=manifest.model_type,
                version=manifest.model_version,
                artifact_kind="calibration",
                expected_sha256=calibration_sha256,
            )

        now = datetime.now(UTC)
        candidate = existing or ModelVersion(
            model_type=manifest.model_type,
            version=manifest.model_version,
            registered_at=now,
            status="candidate",
            is_active=False,
        )
        if existing is None:
            session.add(candidate)

        candidate.artifact_uri = artifact_uri
        candidate.artifact_sha256 = artifact_sha256
        candidate.calibration_uri = calibration_uri
        candidate.feature_schema = {
            "features": manifest.features,
            "schema_version": manifest.feature_schema_version,
        }
        candidate.metrics = manifest.metrics.model_dump()
        candidate.dataset_version = manifest.dataset.version
        candidate.training_commit = manifest.training_commit
        candidate.promotion_metadata = {
            "winner": manifest.winner,
            "split": manifest.split,
            "declared_baseline": manifest.baseline.model_dump(),
            "calibration": manifest.calibration.model_dump(),
            "runtime": manifest.runtime.model_dump(),
            "incumbent": (
                manifest.incumbent.model_dump() if manifest.incumbent else None
            ),
            "previous_active_version": active.version if active else None,
            "reason": reason,
            "artifact_storage": self.artifact_store.config.backend,
            "calibration_sha256": calibration_sha256,
        }

        if active is not None and active.id != candidate.id:
            active.status = "retired"
            active.is_active = False
            active.deactivated_at = now
            await session.flush()

        candidate.status = "active"
        candidate.is_active = True
        candidate.activated_at = now
        candidate.deactivated_at = None
        await session.flush()
        session.add(
            ModelActivation(
                model_type=manifest.model_type,
                model_version=manifest.model_version,
                previous_model_version=active.version if active else None,
                action="promote",
                reason=reason,
                activated_at=now,
                metrics_snapshot=manifest.metrics.model_dump(),
            )
        )
        await session.flush()
        return RegistryResult(
            model_type=manifest.model_type,
            version=manifest.model_version,
            status=candidate.status,
            previous_active_version=active.version if active else None,
            artifact_sha256=artifact_sha256,
        )

    async def rollback(
        self,
        session: AsyncSession,
        *,
        model_type: str,
        version: str,
        reason: str,
    ) -> RegistryResult:
        await self._lock_model_type(session, model_type)
        active = await self._active_model(session, model_type, for_update=True)
        target = await session.scalar(
            select(ModelVersion)
            .where(
                ModelVersion.model_type == model_type,
                ModelVersion.version == version,
            )
            .with_for_update()
        )
        if target is None:
            raise ValueError(f"Model version {model_type}/{version} is not registered")
        if not target.artifact_uri or not target.artifact_sha256:
            raise ValueError("Rollback target does not have a registered artifact")
        if target.promotion_metadata.get("runtime") != current_model_runtime():
            raise ValueError("Rollback artifact runtime is incompatible")
        await self.artifact_store.read_verified(
            target.artifact_uri,
            target.artifact_sha256,
        )
        if active is not None and active.id == target.id:
            return RegistryResult(
                model_type=model_type,
                version=version,
                status=target.status,
                previous_active_version=version,
                artifact_sha256=target.artifact_sha256,
            )

        now = datetime.now(UTC)
        if active is not None:
            active.status = "retired"
            active.is_active = False
            active.deactivated_at = now
            await session.flush()
        target.status = "active"
        target.is_active = True
        target.activated_at = now
        target.deactivated_at = None
        target.promotion_metadata = {
            **target.promotion_metadata,
            "previous_active_version": active.version if active else None,
            "reason": reason,
        }
        session.add(
            ModelActivation(
                model_type=model_type,
                model_version=version,
                previous_model_version=active.version if active else None,
                action="rollback",
                reason=reason,
                activated_at=now,
                metrics_snapshot=target.metrics,
            )
        )
        await session.flush()
        return RegistryResult(
            model_type=model_type,
            version=version,
            status=target.status,
            previous_active_version=active.version if active else None,
            artifact_sha256=target.artifact_sha256,
        )

    async def _lock_model_type(
        self,
        session: AsyncSession,
        model_type: str,
    ) -> None:
        if session.bind and session.bind.dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:model_type))"),
                {"model_type": f"courtvision:model:{model_type}"},
            )

    async def _active_model(
        self,
        session: AsyncSession,
        model_type: str,
        *,
        for_update: bool,
    ) -> ModelVersion | None:
        statement = select(ModelVersion).where(
            ModelVersion.model_type == model_type,
            ModelVersion.is_active.is_(True),
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    def _assert_improves(
        self,
        candidate: EvaluationMetrics,
        baseline: EvaluationMetrics,
        *,
        baseline_name: str,
    ) -> None:
        if (
            candidate.brier_score >= baseline.brier_score
            or candidate.log_loss >= baseline.log_loss
        ):
            raise PromotionRejectedError(
                f"Candidate must improve Brier score and log loss over {baseline_name}"
            )
        if (
            candidate.expected_calibration_error
            > self.max_expected_calibration_error
        ):
            raise PromotionRejectedError(
                "Candidate expected calibration error exceeds 0.05"
            )

    @staticmethod
    def _stored_metrics(model: ModelVersion) -> EvaluationMetrics:
        try:
            return EvaluationMetrics.model_validate(model.metrics)
        except ValueError as exc:
            raise PromotionRejectedError(
                f"Active model {model.version} is missing comparable metrics"
            ) from exc

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as artifact:
            for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


model_registry = ModelRegistry()


def load_manifest(path: Path) -> CandidateManifest:
    return CandidateManifest.model_validate_json(path.read_text(encoding="utf-8"))


def runtime_manifest() -> RuntimeManifest:
    return RuntimeManifest.model_validate(current_model_runtime())


async def register_command(args: argparse.Namespace) -> RegistryResult:
    manifest = load_manifest(args.metadata)
    async with SessionFactory() as session, session.begin():
        return await model_registry.register_and_activate(
            session,
            manifest=manifest,
            artifact_path=args.artifact,
            calibration_path=args.calibration,
            reason=args.reason,
        )


async def rollback_command(args: argparse.Namespace) -> RegistryResult:
    async with SessionFactory() as session, session.begin():
        return await model_registry.rollback(
            session,
            model_type=args.model_type,
            version=args.version,
            reason=args.reason,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage private model activation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser("register")
    register.add_argument("metadata", type=Path)
    register.add_argument("artifact", type=Path)
    register.add_argument("--calibration", type=Path)
    register.add_argument(
        "--reason",
        default="candidate passed declared and active promotion gates",
    )

    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("model_type")
    rollback.add_argument("version")
    rollback.add_argument("--reason", required=True)

    args = parser.parse_args()
    result = asyncio.run(
        register_command(args)
        if args.command == "register"
        else rollback_command(args)
    )
    print(json.dumps(result.__dict__, indent=2))


if __name__ == "__main__":
    main()
