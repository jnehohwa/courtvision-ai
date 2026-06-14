from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelContract:
    model_type: str
    baseline_version: str
    schema_version: str
    features: tuple[str, ...]
    validation_row: dict[str, float | int | bool]


PREGAME_CONTRACT = ModelContract(
    model_type="pregame",
    baseline_version="pregame-logistic-baseline-1.0",
    schema_version="pregame-v1",
    features=(
        "home_offensive_rating",
        "away_offensive_rating",
        "home_defensive_rating",
        "away_defensive_rating",
        "home_pace",
        "away_pace",
        "home_rest_days",
        "away_rest_days",
    ),
    validation_row={
        "home_offensive_rating": 115.0,
        "away_offensive_rating": 114.0,
        "home_defensive_rating": 112.0,
        "away_defensive_rating": 113.0,
        "home_pace": 98.0,
        "away_pace": 99.0,
        "home_rest_days": 2,
        "away_rest_days": 1,
    },
)

SHOT_QUALITY_CONTRACT = ModelContract(
    model_type="shot_quality",
    baseline_version="shot-quality-baseline-1.0",
    schema_version="shot-quality-v1",
    features=(
        "x",
        "y",
        "shot_value",
        "period",
        "game_clock_seconds",
        "score_differential",
    ),
    validation_row={
        "x": 0.0,
        "y": 10.0,
        "shot_value": 2,
        "period": 1,
        "game_clock_seconds": 600,
        "score_differential": 0,
    },
)

LIVE_WIN_CONTRACT = ModelContract(
    model_type="live_win",
    baseline_version="live-win-logistic-baseline-1.0",
    schema_version="live-win-v1",
    features=(
        "score_differential",
        "time_remaining_seconds",
        "possession_is_home",
        "home_fouls",
        "away_fouls",
        "pregame_home_probability",
    ),
    validation_row={
        "score_differential": 0,
        "time_remaining_seconds": 2880,
        "possession_is_home": True,
        "home_fouls": 0,
        "away_fouls": 0,
        "pregame_home_probability": 0.5,
    },
)

MODEL_CONTRACTS = {
    contract.model_type: contract
    for contract in (
        PREGAME_CONTRACT,
        SHOT_QUALITY_CONTRACT,
        LIVE_WIN_CONTRACT,
    )
}
