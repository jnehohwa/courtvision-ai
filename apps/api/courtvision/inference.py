from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import joblib
import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from courtvision.artifact_store import (
    ArtifactIntegrityError,
    ModelArtifactStore,
    model_artifact_store,
)
from courtvision.model_contracts import MODEL_CONTRACTS, ModelContract
from courtvision.model_runtime import current_model_runtime
from courtvision.models import ModelVersion

logger = structlog.get_logger()


class ModelArtifactError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadedModel:
    model_type: str
    version: str
    artifact_sha256: str
    features: tuple[str, ...]
    model: Any

    async def predict_probabilities(
        self,
        rows: list[dict[str, float | int | bool]],
    ) -> list[float]:
        return await asyncio.to_thread(self._predict_probabilities, rows)

    def _predict_probabilities(
        self,
        rows: list[dict[str, float | int | bool]],
    ) -> list[float]:
        if not rows:
            return []
        if any(
            isinstance(value, str)
            for row in rows
            for value in row.values()
        ):
            raise ModelArtifactError("Inference features must be numeric or boolean")

        frame = pd.DataFrame(rows, columns=list(self.features))
        if frame.isnull().any().any():
            raise ModelArtifactError("Inference features contain missing values")
        frame = frame.apply(pd.to_numeric, errors="raise")

        raw_probabilities = self.model.predict_proba(frame)
        if len(raw_probabilities) != len(rows):
            raise ModelArtifactError("Model returned an unexpected number of predictions")

        probabilities: list[float] = []
        for raw_row in raw_probabilities:
            if len(raw_row) != 2:
                raise ModelArtifactError(
                    "Binary classifier predict_proba must return two columns"
                )
            probability = float(raw_row[1])
            if not 0 <= probability <= 1:
                raise ModelArtifactError("Model returned a probability outside [0, 1]")
            probabilities.append(probability)
        return probabilities


class ActiveModelResolver:
    def __init__(
        self,
        artifact_store: ModelArtifactStore = model_artifact_store,
    ) -> None:
        self._artifact_store = artifact_store
        self._cache: dict[tuple[str, str, str], LoadedModel] = {}
        self._load_lock = asyncio.Lock()

    async def resolve(
        self,
        session: AsyncSession,
        model_type: str,
    ) -> LoadedModel | None:
        contract = MODEL_CONTRACTS[model_type]
        registered = await session.scalar(
            select(ModelVersion).where(
                ModelVersion.model_type == model_type,
                ModelVersion.is_active.is_(True),
            )
        )
        if (
            registered is None
            or not registered.artifact_uri
            or not registered.artifact_sha256
        ):
            return None

        try:
            self._validate_registry_contract(registered, contract)
            cache_key = (
                registered.model_type,
                registered.version,
                registered.artifact_sha256,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

            async with self._load_lock:
                cached = self._cache.get(cache_key)
                if cached is not None:
                    return cached
                loaded = await asyncio.to_thread(
                    self._load_artifact,
                    registered,
                    contract,
                )
                self._cache = {
                    key: value
                    for key, value in self._cache.items()
                    if key[0] != model_type
                }
                self._cache[cache_key] = loaded
                return loaded
        except ArtifactIntegrityError as exc:
            logger.error(
                "active_model_integrity_failure",
                model_type=model_type,
                model_version=registered.version,
                reason=str(exc),
            )
            return None
        except Exception as exc:
            logger.warning(
                "active_model_unavailable",
                model_type=model_type,
                model_version=registered.version,
                reason=str(exc),
            )
            return None

    def clear(self) -> None:
        self._cache.clear()

    @staticmethod
    def _validate_registry_contract(
        registered: ModelVersion,
        contract: ModelContract,
    ) -> None:
        registered_features = registered.feature_schema.get("features")
        registered_schema = registered.feature_schema.get("schema_version")
        if registered_features != list(contract.features):
            raise ModelArtifactError("Registered feature order does not match the API contract")
        if registered_schema != contract.schema_version:
            raise ModelArtifactError("Registered feature schema version is not supported")
        registered_runtime = registered.promotion_metadata.get("runtime")
        if registered_runtime != current_model_runtime():
            raise ModelArtifactError(
                "Artifact runtime versions do not match the API environment"
            )

    def _load_artifact(
        self,
        registered: ModelVersion,
        contract: ModelContract,
    ) -> LoadedModel:
        assert registered.artifact_uri is not None
        assert registered.artifact_sha256 is not None

        artifact_bytes = self._artifact_store.read_verified_sync(
            registered.artifact_uri,
            registered.artifact_sha256,
        )

        model = joblib.load(BytesIO(artifact_bytes))
        if not callable(getattr(model, "predict_proba", None)):
            raise ModelArtifactError("Artifact does not implement predict_proba")

        model_features = getattr(model, "feature_names_in_", None)
        if model_features is not None and list(model_features) != list(contract.features):
            raise ModelArtifactError("Artifact feature names do not match the registry")
        model_classes = getattr(model, "classes_", None)
        if model_classes is None or list(model_classes) != [0, 1]:
            raise ModelArtifactError("Binary classifier classes must be ordered as [0, 1]")

        loaded = LoadedModel(
            model_type=registered.model_type,
            version=registered.version,
            artifact_sha256=registered.artifact_sha256,
            features=contract.features,
            model=model,
        )
        loaded._predict_probabilities([contract.validation_row])
        return loaded


active_model_resolver = ActiveModelResolver()
