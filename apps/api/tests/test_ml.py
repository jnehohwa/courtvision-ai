from __future__ import annotations

from courtvision.ml import LiveGameState, prediction_service
from courtvision.schemas import ShotAttemptRequest


def test_late_lead_is_more_decisive_than_early_lead():
    early = prediction_service.live_probability(
        LiveGameState(5, 2600, True, 1, 1, 0.55)
    )
    late = prediction_service.live_probability(
        LiveGameState(5, 60, True, 4, 4, 0.55)
    )
    assert late > early


def test_closer_shot_has_higher_make_probability():
    close = prediction_service.shot_quality(
        ShotAttemptRequest(
            x=1,
            y=3,
            shot_value=2,
            period=1,
            game_clock_seconds=500,
            score_differential=0,
        )
    )
    far = prediction_service.shot_quality(
        ShotAttemptRequest(
            x=10,
            y=24,
            shot_value=3,
            period=1,
            game_clock_seconds=500,
            score_differential=0,
        )
    )
    assert close.make_probability > far.make_probability
