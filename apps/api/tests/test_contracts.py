from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from courtvision.database import SessionFactory
from courtvision.main import app
from courtvision.presenters import event_envelopes, status_envelope
from courtvision.repository import game_events, get_game


CONTRACTS_ROOT = Path(__file__).resolve().parents[3] / "contracts"


def websocket_validator() -> Draft202012Validator:
    schema = json.loads(
        (CONTRACTS_ROOT / "websocket-envelope.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_committed_openapi_matches_application():
    contract_path = CONTRACTS_ROOT / "openapi.json"
    committed = json.loads(contract_path.read_text(encoding="utf-8"))
    assert committed == app.openapi()


async def test_presented_websocket_envelopes_match_shared_schema(database):
    validator = websocket_validator()
    async with SessionFactory() as session:
        game = await get_game(session, "cv-2026-bos-nyk")
        assert game is not None
        events = await game_events(session, game.id)

    play_added = (
        await event_envelopes(
            [events[0]],
            game,
            baseline=0.58,
            event_types=["play_added"],
        )
    )[0]
    play_corrected = (
        await event_envelopes(
            [events[-1]],
            game,
            baseline=0.58,
            event_types=["play_corrected"],
        )
    )[0]
    status_frames = [
        status_envelope(
            game,
            sequence=0,
            event_type="source_status",
            payload={"status": "replay_started", "event_count": len(events)},
        ),
        status_envelope(
            game,
            sequence=events[-1].sequence,
            event_type="heartbeat",
            payload={"status": "connected"},
        ),
        status_envelope(
            game,
            sequence=events[-1].sequence,
            event_type="replay_completed",
            payload={"status": "completed"},
        ),
    ]

    for envelope in [play_added, play_corrected, *status_frames]:
        validator.validate(envelope.model_dump(mode="json"))


def test_websocket_schema_rejects_incomplete_play_payload():
    invalid_play_frame = {
        "type": "play_added",
        "schema_version": "1.0",
        "game_id": "game-1",
        "sequence": 1,
        "occurred_at": "2026-06-14T12:00:00Z",
        "ingested_at": "2026-06-14T12:00:01Z",
        "source_status": "replay",
        "model_version": "live-win-logistic-baseline-1.0",
        "payload": {"status": "missing play fields"},
    }

    with pytest.raises(ValidationError):
        websocket_validator().validate(invalid_play_frame)
