from __future__ import annotations

from datetime import UTC, datetime

import pytest
from starlette.websockets import WebSocketDisconnect


def test_lists_seeded_games(client):
    response = client.get(
        "/api/v1/games",
        params={"date": datetime.now(UTC).date().isoformat()},
    )
    assert response.status_code == 200
    games = response.json()["games"]
    assert len(games) == 3
    assert games[0]["prediction"]["home_probability"] == 0.58
    assert games[0]["scheduled_at"].endswith("Z")
    assert games[0]["last_ingested_at"].endswith("Z")


def test_live_snapshot_has_monotonic_timeline(client):
    response = client.get("/api/v1/games/cv-2026-bos-nyk/live")
    assert response.status_code == 200
    payload = response.json()
    sequences = [point["sequence"] for point in payload["timeline"]]
    assert sequences == sorted(set(sequences))
    assert payload["source_label"] == "Historical replay"
    assert payload["latest_sequence"] == 20
    assert payload["live_model_version"] == "live-win-logistic-baseline-1.0"
    assert payload["snapshot_generated_at"]


def test_game_detail_has_typed_response(client):
    response = client.get("/api/v1/games/cv-2026-bos-nyk")
    assert response.status_code == 200
    assert response.json()["home_team"]["abbreviation"] == "BOS"


def test_shot_quality_is_shooter_neutral(client):
    request = {
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
    }
    response = client.post("/api/v1/shot-quality", json=request)
    assert response.status_code == 200
    payload = response.json()
    assert "Shooter-neutral" in payload["definition"]
    assert payload["attempts"][0]["expected_points"] > 0
    assert payload["model_version"] == "shot-quality-baseline-1.0"


def test_feature_timestamp_precedes_prediction(client):
    response = client.get("/api/v1/games/cv-2026-bos-nyk/prediction")
    payload = response.json()
    assert payload["feature_timestamp"] < payload["predicted_at"]


def test_replay_requires_internal_key(client):
    response = client.post("/internal/replays/cv-2026-bos-nyk/start")
    assert response.status_code == 403


def test_health_reports_persistent_source_metrics(client):
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"]["replay"]["status"] == "healthy"
    assert payload["sources"]["replay"]["total_events"] == 20


def test_websocket_resumes_after_sequence(client):
    with client.websocket_connect(
        "/ws/v1/games/cv-2026-bos-nyk?after_sequence=18"
    ) as websocket:
        first = websocket.receive_json()
        second = websocket.receive_json()
        assert first["sequence"] == 19
        assert second["sequence"] == 20
        assert first["schema_version"] == "1.0"


def test_websocket_missing_game_closes_with_not_found_code(client):
    with client.websocket_connect("/ws/v1/games/missing") as websocket:
        with pytest.raises(WebSocketDisconnect) as error:
            websocket.receive_json()
    assert error.value.code == 4404


def test_replay_falls_back_to_in_process_delivery(client):
    with client.websocket_connect(
        "/ws/v1/games/cv-2026-bos-nyk?after_sequence=20"
    ) as websocket:
        response = client.post(
            "/internal/replays/cv-2026-bos-nyk/start",
            headers={"X-Internal-Key": "local-development-key"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "started"
        assert websocket.receive_json()["type"] == "source_status"
