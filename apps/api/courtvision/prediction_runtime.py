from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from courtvision.inference import LoadedModel
from courtvision.ml import ProbabilityEstimate, prediction_service
from courtvision.model_contracts import PREGAME_CONTRACT
from courtvision.models import Prediction
from courtvision.repository import latest_feature_snapshot

logger = structlog.get_logger()


async def resolve_pregame_estimate(
    session: AsyncSession,
    prediction: Prediction,
    runtime: LoadedModel | None,
) -> ProbabilityEstimate:
    snapshot = await latest_feature_snapshot(
        session,
        prediction.game_id,
        "pregame",
        before=prediction.predicted_at,
    )
    if snapshot is None:
        return ProbabilityEstimate(
            probability=prediction.home_probability,
            model_version=prediction.model_version,
            used_artifact=False,
        )
    if runtime is not None and (
        snapshot.schema_version != PREGAME_CONTRACT.schema_version
        or set(snapshot.features) != set(PREGAME_CONTRACT.features)
    ):
        logger.warning(
            "pregame_snapshot_schema_invalid",
            game_id=prediction.game_id,
            snapshot_schema_version=snapshot.schema_version,
            model_version=runtime.version,
        )
        return ProbabilityEstimate(
            probability=prediction.home_probability,
            model_version=prediction.model_version,
            used_artifact=False,
        )
    return await prediction_service.pregame_estimate(
        snapshot.features,
        runtime,
        fallback_probability=prediction.home_probability,
        fallback_version=prediction.model_version,
    )
