# iOS Visual Acceptance Gate

CourtVision AI uses deterministic replay fixtures, so the native game room can
be visually accepted without a licensed live feed. This gate verifies the
selected-shot quality panel renders honest shooter-neutral output from the
FastAPI fixture API.

Run this gate before TestFlight-style native handoff work or after changes to
`GameDetailView`, `ShotCourtView`, `GameDetailModel`, `APIClient`, or the
shot-quality response contract.

## Prerequisites

- The repo is clean and synced with `origin/main`.
- The iOS simulator defaults point to the `CourtVision` project, `CourtVision`
  scheme, and iPhone 17 / iOS 26.5 simulator.
- The Python virtualenv exists at `.venv`.
- The app still defaults to `http://127.0.0.1:8000`, or
  `COURTVISION_API_URL` is set to the same fixture host before launch.

## Start The Fixture API

From the repository root:

```bash
PYTHONPATH=apps/api \
COURTVISION_ENVIRONMENT=e2e \
COURTVISION_DATABASE_URL=sqlite+aiosqlite:////tmp/courtvision-playwright.db \
COURTVISION_REDIS_URL=redis://127.0.0.1:6399/0 \
.venv/bin/python -m courtvision.e2e_server
```

This recreates `/tmp/courtvision-playwright.db`, runs Alembic through `head`,
seeds deterministic games, and serves the API on `127.0.0.1:8000`. Redis is
intentionally unavailable in this gate; the API should report `redis:
degraded` while replay fixtures remain available.

Confirm health in another terminal:

```bash
curl -fsS http://127.0.0.1:8000/health
```

Expected health evidence:

- `status` is `ok`
- `database` is `ok`
- `sources.replay.status` is `healthy`
- `sources.replay.total_events` is `20`

## Launch The Native App

Use XcodeBuildMCP:

```text
session_show_defaults
```

If defaults are missing, set:

```text
projectPath: apps/ios/CourtVision.xcodeproj
scheme: CourtVision
simulatorName: iPhone 17
simulatorPlatform: iOS Simulator
useLatestOS: true
bundleId: ai.courtvision.app
```

Then run:

```text
build_run_sim(extraArgs: ["CODE_SIGNING_ALLOWED=NO"])
```

The build should finish with no diagnostics. If `snapshot_ui` fails right after
launch, take a screenshot and retry once the games list is visible.

## Acceptance Path

1. Capture `snapshot_ui`.
2. Tap the Boston/New York replay game card.
3. Wait for the game room to settle.
4. Capture `snapshot_ui`.
5. Capture a simulator screenshot for visual inspection.

The semantic snapshot must include all of the following text:

- `Connected`
- `Historical replay`
- `Replay fixture`
- `Shot Map`
- a selected shot description such as `Tatum driving layup`
- `xPTS`
- `MAKE`
- `QUALITY`
- a numeric expected-points value, for example `1,41` or `1.41`
- a make probability, for example `71%`
- a quality label, for example `High`
- the shooter-neutral definition text
- `shot-quality-baseline-1.0`
- `no defender tracking`

The screenshot should show the same selected-shot quality card above the court
canvas, not hidden behind the tab bar.

## Cleanup

Stop the simulator app:

```text
stop_app_sim
```

Stop the fixture API with `Ctrl+C`.

## Troubleshooting

- If the fixture API cannot bind to `127.0.0.1:8000` under the managed sandbox,
  rerun it with command escalation.
- If the tab bar covers the shot-quality card, verify that `ShotCourtView`
  renders `selectedShotSummary` above the court canvas and that `GameDetailView`
  applies bottom scroll padding.
- If shot-quality values are missing, check `/api/v1/shot-quality` through the
  Swift `APIClient` runtime test and confirm the selected timeline point has
  `x`, `y`, and `shot_value`.
- If the values use commas instead of periods, that is locale formatting from
  SwiftUI and is acceptable as long as the metric labels and model boundary copy
  are present.
