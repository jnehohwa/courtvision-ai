from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta
from typing import Any


TEAMS = [
    {"id": "bos", "name": "Boston", "abbreviation": "BOS"},
    {"id": "nyk", "name": "New York", "abbreviation": "NYK"},
    {"id": "den", "name": "Denver", "abbreviation": "DEN"},
    {"id": "phx", "name": "Phoenix", "abbreviation": "PHX"},
    {"id": "min", "name": "Minnesota", "abbreviation": "MIN"},
    {"id": "dal", "name": "Dallas", "abbreviation": "DAL"},
]

PLAYERS = [
    {"id": "p-tatum", "team_id": "bos", "name": "Jayson Tatum"},
    {"id": "p-brunson", "team_id": "nyk", "name": "Jalen Brunson"},
    {"id": "p-jokic", "team_id": "den", "name": "Nikola Jokic"},
    {"id": "p-booker", "team_id": "phx", "name": "Devin Booker"},
]


def fixture_games(game_date: date | None = None) -> list[dict[str, Any]]:
    target_date = game_date or datetime.now(UTC).date()
    start = datetime.combine(target_date, time(18, 30), tzinfo=UTC)
    ingested = datetime.now(UTC) - timedelta(seconds=8)
    return [
        {
            "id": "cv-2026-bos-nyk",
            "source_id": "fixture-bos-nyk",
            "scheduled_at": start,
            "home_team_id": "bos",
            "away_team_id": "nyk",
            "home_score": 102,
            "away_score": 99,
            "period": 4,
            "clock_seconds": 138,
            "status": "replay",
            "source_status": "replay",
            "last_ingested_at": ingested,
        },
        {
            "id": "cv-2026-den-phx",
            "source_id": "fixture-den-phx",
            "scheduled_at": start + timedelta(hours=2),
            "home_team_id": "den",
            "away_team_id": "phx",
            "home_score": 0,
            "away_score": 0,
            "period": 0,
            "clock_seconds": 2880,
            "status": "scheduled",
            "source_status": "replay",
            "last_ingested_at": ingested,
        },
        {
            "id": "cv-2026-min-dal",
            "source_id": "fixture-min-dal",
            "scheduled_at": start + timedelta(hours=3),
            "home_team_id": "min",
            "away_team_id": "dal",
            "home_score": 0,
            "away_score": 0,
            "period": 0,
            "clock_seconds": 2880,
            "status": "scheduled",
            "source_status": "replay",
            "last_ingested_at": ingested,
        },
    ]


def fixture_events() -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    raw = [
        (1, 1, 690, 2, 0, "Tatum driving layup", "shot_made", "bos", -3.0, 4.0, 2),
        (2, 1, 615, 2, 3, "Brunson pull-up 3", "shot_made", "nyk", 8.0, 23.0, 3),
        (3, 1, 484, 8, 5, "Boston transition 3", "shot_made", "nyk", -17.0, 18.0, 3),
        (4, 1, 318, 18, 17, "New York second-chance layup", "shot_made", "bos", 2.0, 3.0, 2),
        (5, 2, 641, 28, 25, "Tatum wing 3", "shot_made", "nyk", -20.0, 16.0, 3),
        (6, 2, 502, 31, 31, "Brunson 24 ft step-back 3", "shot_made", "bos", 11.0, 22.0, 3),
        (7, 2, 271, 42, 38, "Turnover", "turnover", "nyk", None, None, None),
        (8, 2, 84, 49, 47, "Boston corner 3 missed", "shot_missed", "nyk", -22.0, 5.0, 3),
        (9, 3, 628, 56, 52, "Tatum driving layup", "shot_made", "nyk", 1.0, 5.0, 2),
        (10, 3, 443, 61, 60, "New York above-break 3", "shot_made", "bos", 5.0, 25.0, 3),
        (11, 3, 210, 72, 68, "Boston steal and dunk", "shot_made", "nyk", 0.0, 2.0, 2),
        (12, 3, 22, 77, 75, "Brunson floater", "shot_made", "bos", 4.0, 8.0, 2),
        (13, 4, 659, 82, 79, "Tatum pull-up 3", "shot_made", "nyk", -12.0, 22.0, 3),
        (14, 4, 528, 86, 86, "Brunson 24 ft step-back 3", "shot_made", "bos", 9.0, 23.0, 3),
        (15, 4, 401, 91, 88, "Boston driving layup", "shot_made", "nyk", -2.0, 5.0, 2),
        (16, 4, 310, 94, 94, "New York corner 3", "shot_made", "bos", 22.0, 4.0, 3),
        (17, 4, 231, 98, 96, "Tatum driving layup", "shot_made", "nyk", 3.0, 4.0, 2),
        (18, 4, 181, 100, 99, "Brunson 24 ft step-back 3", "shot_made", "bos", 12.0, 21.0, 3),
        (19, 4, 154, 100, 99, "Turnover", "turnover", "bos", None, None, None),
        (20, 4, 138, 102, 99, "Tatum driving layup", "shot_made", "nyk", -2.0, 4.0, 2),
    ]

    events = []
    for sequence, period, clock, home, away, description, kind, possession, x, y, value in raw:
        occurred = now - timedelta(seconds=(len(raw) - sequence) * 24)
        events.append(
            {
                "game_id": "cv-2026-bos-nyk",
                "source_event_id": f"fixture-play-{sequence:03}",
                "sequence": sequence,
                "revision": 1,
                "event_type": kind,
                "description": description,
                "period": period,
                "clock_seconds": clock,
                "home_score": home,
                "away_score": away,
                "possession_team_id": possession,
                "home_fouls": min(period + sequence // 7, 5),
                "away_fouls": min(period + sequence // 6, 5),
                "x": x,
                "y": y,
                "shot_value": value,
                "occurred_at": occurred,
                "ingested_at": occurred + timedelta(seconds=8),
                "raw_payload": {"fixture": True, "sequence": sequence},
            }
        )
    return events


PREGAME_PROBABILITIES = {
    "cv-2026-bos-nyk": 0.58,
    "cv-2026-den-phx": 0.67,
    "cv-2026-min-dal": 0.54,
}

TEAM_METRIC_PRIORS = {
    "bos": (119.2, 111.1, 98.4, 2),
    "nyk": (116.4, 113.2, 96.8, 1),
    "den": (118.6, 113.4, 97.9, 2),
    "phx": (115.9, 115.1, 99.2, 1),
    "min": (114.8, 109.7, 97.1, 2),
    "dal": (117.7, 114.0, 100.1, 1),
}


def fixture_team_game_statistics() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for game in fixture_games():
        for team_id, is_home in (
            (game["home_team_id"], True),
            (game["away_team_id"], False),
        ):
            offense, defense, pace, rest_days = TEAM_METRIC_PRIORS[team_id]
            rows.append(
                {
                    "game_id": game["id"],
                    "team_id": team_id,
                    "is_home": is_home,
                    "offensive_rating": offense,
                    "defensive_rating": defense,
                    "pace": pace,
                    "rest_days": rest_days,
                    "as_of": game["scheduled_at"] - timedelta(hours=2),
                    "source": "synthetic-fixture",
                    "raw_payload": {
                        "prior": "synthetic-rolling-form",
                        "window_games": 10,
                    },
                }
            )
    return rows


def fixture_shots() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in fixture_events():
        if event["shot_value"] is None or event["x"] is None or event["y"] is None:
            continue

        description = event["description"]
        if "Tatum" in description:
            player_id, team_id = "p-tatum", "bos"
        elif "Brunson" in description:
            player_id, team_id = "p-brunson", "nyk"
        elif "Boston" in description:
            player_id, team_id = None, "bos"
        elif "New York" in description:
            player_id, team_id = None, "nyk"
        else:
            player_id, team_id = None, None

        distance = math.hypot(event["x"], event["y"])
        angle = abs(math.degrees(math.atan2(event["x"], max(event["y"], 0.1))))
        rows.append(
            {
                "game_id": event["game_id"],
                "source_shot_id": f"fixture-shot-{event['sequence']:03}",
                "source_event_id": event["source_event_id"],
                "sequence": event["sequence"],
                "revision": event["revision"],
                "player_id": player_id,
                "team_id": team_id,
                "x": event["x"],
                "y": event["y"],
                "distance_feet": round(distance, 3),
                "angle_degrees": round(angle, 3),
                "shot_value": event["shot_value"],
                "made": event["event_type"] == "shot_made",
                "period": event["period"],
                "game_clock_seconds": event["clock_seconds"],
                "score_differential": event["home_score"] - event["away_score"],
                "occurred_at": event["occurred_at"],
                "ingested_at": event["ingested_at"],
                "raw_payload": {
                    "fixture": True,
                    "source_event_id": event["source_event_id"],
                },
            }
        )
    return rows
