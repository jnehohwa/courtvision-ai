from __future__ import annotations

import math
from dataclasses import dataclass

from courtvision.schemas import ShotAttemptRequest, ShotQualityResult


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


class PredictionService:
    pregame_model_version = "pregame-logistic-baseline-1.0"
    shot_model_version = "shot-quality-baseline-1.0"
    live_model_version = "live-win-logistic-baseline-1.0"

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


prediction_service = PredictionService()
