from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import structlog

from courtvision.inference import LoadedModel
from courtvision.model_contracts import (
    LIVE_WIN_CONTRACT,
    PREGAME_CONTRACT,
    SHOT_QUALITY_CONTRACT,
)
from courtvision.schemas import ShotAttemptRequest, ShotQualityResult

logger = structlog.get_logger()


def clamp_probability(value: float) -> float:
    return max(0.01, min(0.99, value))


def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))


@dataclass(frozen=True)
class LiveGameState:
    score_differential: int
    time_remaining_seconds: int
    possession_is_home: bool
    home_fouls: int
    away_fouls: int
    pregame_home_probability: float


@dataclass(frozen=True)
class ProbabilityEstimate:
    probability: float
    model_version: str
    used_artifact: bool


class PredictionService:
    pregame_model_version = PREGAME_CONTRACT.baseline_version
    shot_model_version = SHOT_QUALITY_CONTRACT.baseline_version
    live_model_version = LIVE_WIN_CONTRACT.baseline_version

    def pregame_probability(
        self,
        *,
        home_offensive_rating: float,
        away_offensive_rating: float,
        home_defensive_rating: float,
        away_defensive_rating: float,
        home_pace: float,
        away_pace: float,
        home_rest_days: int,
        away_rest_days: int,
    ) -> float:
        rating_edge = (
            home_offensive_rating
            - away_defensive_rating
            - away_offensive_rating
            + home_defensive_rating
        )
        pace_edge = (home_pace - away_pace) * 0.02
        rest_edge = (home_rest_days - away_rest_days) * 0.09
        return clamp_probability(sigmoid(0.17 + rating_edge * 0.065 + pace_edge + rest_edge))

    async def pregame_estimate(
        self,
        features: dict[str, Any],
        runtime: LoadedModel | None,
        *,
        fallback_probability: float | None = None,
        fallback_version: str | None = None,
    ) -> ProbabilityEstimate:
        fallback = (
            fallback_probability
            if fallback_probability is not None
            else self.pregame_probability(
                home_offensive_rating=float(features["home_offensive_rating"]),
                away_offensive_rating=float(features["away_offensive_rating"]),
                home_defensive_rating=float(features["home_defensive_rating"]),
                away_defensive_rating=float(features["away_defensive_rating"]),
                home_pace=float(features["home_pace"]),
                away_pace=float(features["away_pace"]),
                home_rest_days=int(features["home_rest_days"]),
                away_rest_days=int(features["away_rest_days"]),
            )
        )
        fallback_model_version = fallback_version or self.pregame_model_version
        if runtime is None:
            return ProbabilityEstimate(
                probability=fallback,
                model_version=fallback_model_version,
                used_artifact=False,
            )
        try:
            row = {
                feature: features[feature]
                for feature in PREGAME_CONTRACT.features
            }
        except KeyError as exc:
            logger.warning(
                "pregame_features_invalid",
                missing_feature=str(exc),
            )
            return ProbabilityEstimate(
                probability=fallback,
                model_version=fallback_model_version,
                used_artifact=False,
            )
        return (
            await self._estimate_probabilities(
                runtime,
                [row],
                [fallback],
                fallback_model_version,
            )
        )[0]

    def shot_quality(self, attempt: ShotAttemptRequest) -> ShotQualityResult:
        distance = math.hypot(attempt.x, attempt.y)
        angle = abs(math.degrees(math.atan2(attempt.x, max(attempt.y, 0.1))))
        is_three = attempt.shot_value == 3

        logit = 1.35 - distance * 0.105
        logit -= max(angle - 42, 0) * 0.009
        logit -= 0.12 if is_three else 0
        logit -= 0.09 if attempt.game_clock_seconds < 5 else 0
        logit -= 0.04 if abs(attempt.score_differential) > 20 else 0
        make_probability = clamp_probability(sigmoid(logit))
        expected_points = make_probability * attempt.shot_value

        if expected_points >= 1.18:
            quality = "High"
        elif expected_points >= 0.9:
            quality = "Average"
        else:
            quality = "Low"

        return ShotQualityResult(
            x=attempt.x,
            y=attempt.y,
            distance_feet=round(distance, 1),
            angle_degrees=round(angle, 1),
            shot_value=attempt.shot_value,
            make_probability=round(make_probability, 4),
            expected_points=round(expected_points, 3),
            quality_label=quality,
        )

    async def shot_quality_batch(
        self,
        attempts: list[ShotAttemptRequest],
        runtime: LoadedModel | None,
    ) -> tuple[str, list[ShotQualityResult]]:
        baselines = [self.shot_quality(attempt) for attempt in attempts]
        rows = [
            {
                "x": attempt.x,
                "y": attempt.y,
                "shot_value": attempt.shot_value,
                "period": attempt.period,
                "game_clock_seconds": attempt.game_clock_seconds,
                "score_differential": attempt.score_differential,
            }
            for attempt in attempts
        ]
        estimates = await self._estimate_probabilities(
            runtime,
            rows,
            [baseline.make_probability for baseline in baselines],
            self.shot_model_version,
        )
        results = [
            self._shot_quality_result(attempt, baseline, estimate.probability)
            for attempt, baseline, estimate in zip(
                attempts,
                baselines,
                estimates,
                strict=True,
            )
        ]
        return estimates[0].model_version, results

    def live_probability(self, state: LiveGameState) -> float:
        elapsed_fraction = 1 - max(state.time_remaining_seconds, 0) / 2880
        score_weight = 0.075 + elapsed_fraction * 0.05
        baseline_logit = math.log(
            state.pregame_home_probability / (1 - state.pregame_home_probability)
        )
        possession_edge = 0.02 if state.possession_is_home else -0.02
        foul_edge = (state.away_fouls - state.home_fouls) * 0.025
        time_pressure = 1 + 0.35 * elapsed_fraction**3
        logit = (
            baseline_logit * (1 - elapsed_fraction * 0.72)
            + state.score_differential * score_weight * time_pressure
            + possession_edge
            + foul_edge
        )
        return clamp_probability(sigmoid(logit))

    async def live_estimates(
        self,
        states: list[LiveGameState],
        runtime: LoadedModel | None,
    ) -> list[ProbabilityEstimate]:
        rows = [
            {
                "score_differential": state.score_differential,
                "time_remaining_seconds": state.time_remaining_seconds,
                "possession_is_home": state.possession_is_home,
                "home_fouls": state.home_fouls,
                "away_fouls": state.away_fouls,
                "pregame_home_probability": state.pregame_home_probability,
            }
            for state in states
        ]
        return await self._estimate_probabilities(
            runtime,
            rows,
            [self.live_probability(state) for state in states],
            self.live_model_version,
        )

    @staticmethod
    def _shot_quality_result(
        attempt: ShotAttemptRequest,
        baseline: ShotQualityResult,
        make_probability: float,
    ) -> ShotQualityResult:
        expected_points = make_probability * attempt.shot_value
        if expected_points >= 1.18:
            quality = "High"
        elif expected_points >= 0.9:
            quality = "Average"
        else:
            quality = "Low"
        return baseline.model_copy(
            update={
                "make_probability": round(make_probability, 4),
                "expected_points": round(expected_points, 3),
                "quality_label": quality,
            }
        )

    @staticmethod
    async def _estimate_probabilities(
        runtime: LoadedModel | None,
        rows: list[dict[str, float | int | bool]],
        fallback_probabilities: list[float],
        fallback_version: str,
    ) -> list[ProbabilityEstimate]:
        if runtime is not None:
            try:
                return [
                    ProbabilityEstimate(
                        probability=probability,
                        model_version=runtime.version,
                        used_artifact=True,
                    )
                    for probability in await runtime.predict_probabilities(rows)
                ]
            except Exception as exc:
                logger.warning(
                    "active_model_inference_failed",
                    model_type=runtime.model_type,
                    model_version=runtime.version,
                    reason=str(exc),
                )

        return [
            ProbabilityEstimate(
                probability=probability,
                model_version=fallback_version,
                used_artifact=False,
            )
            for probability in fallback_probabilities
        ]


prediction_service = PredictionService()
