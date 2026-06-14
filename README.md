# CourtVision AI

CourtVision AI is a replay-first basketball analytics portfolio application. It
combines pregame predictions, shooter-neutral shot quality, and a live win
probability timeline across a FastAPI backend, Next.js dashboard, and SwiftUI
client.

The included data is synthetic. Delayed third-party NBA ingestion is isolated
behind a feature flag and is not required for local development.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Then open:

- Web dashboard: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

Without Docker:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e "apps/api[dev]"
cd apps/api
alembic upgrade head
python -m courtvision.seed
uvicorn courtvision.main:app --reload
```

Install the separate ML workspace only when training models:

```bash
pip install -e ml
```

In another terminal:

```bash
corepack pnpm install
corepack pnpm --filter @courtvision/web dev
```

## Replay

The seeded game `cv-2026-bos-nyk` is deterministic. Open its game room and
press Play, or call:

```bash
curl -X POST http://localhost:8000/internal/replays/cv-2026-bos-nyk/start \
  -H "X-Internal-Key: local-development-key"
```

The public app labels every streamed event as `Historical replay` or
`Delayed data`; it does not claim licensed real-time coverage.

## Model promotion

The API ships deterministic logistic and shot-location benchmarks so replay
fixtures remain reproducible even when model artifacts are unavailable. The
`ml/` workspace trains calibrated candidates and records promotion metrics, but
an artifact is not represented as active until it is packaged for inference
and registered in `model_versions`.

Pregame and live candidates must improve held-out Brier score and log loss
while keeping expected calibration error at or below `0.05`. The shot-quality
benchmark is shooter-neutral and does not claim defender tracking.

The offline pregame trainer declares training-set home-win prevalence as its
minimum benchmark and records those metrics beside the winning candidate.
Replacing an existing active model should additionally compare against that
active artifact before the registry activation flag is changed.

Register and activate a trained candidate through the private command:

```bash
python -m courtvision.model_registry register \
  ml/artifacts/pregame/metadata.json \
  ml/artifacts/pregame/model.joblib
```

The registry verifies the artifact hash, declared baseline, active-model
baseline, calibration limit, dataset version, and training commit in one
database transaction. Replaced models remain registered as rollback targets.

When replacing an artifact-backed active model, train against that incumbent on
the same chronological holdout:

```bash
python -m courtvision_ml.train ml/data/pregame.parquet \
  --output ml/artifacts/pregame-next \
  --model-version pregame-logistic-2.0 \
  --dataset-version pregame-2015-2025-v2 \
  --training-commit "$(git rev-parse HEAD)" \
  --incumbent-artifact ml/artifacts/pregame/model.joblib \
  --incumbent-version pregame-logistic-1.0
```

The resulting manifest binds the incumbent version, hash, and same-split
metrics, preventing invalid comparisons across different evaluation datasets.

Restore a retained artifact with:

```bash
python -m courtvision.model_registry rollback \
  pregame pregame-logistic-baseline-1.0 \
  --reason "rollback after production validation"
```

## Processes

The API owns REST snapshots and WebSocket connections. In production, replay
commands are queued through Redis-compatible storage and consumed by
`courtvision.worker`; emitted envelopes return through Redis pub/sub. If Redis
is unavailable in local development, the API runs deterministic replay in
process and continues serving the last valid snapshots.

## Repository

```text
apps/api       FastAPI, SQLAlchemy, ingestion, ML inference, replay
apps/web       Next.js App Router dashboard
apps/ios       Native SwiftUI client
contracts      OpenAPI and WebSocket JSON Schema
ml             Reproducible training and evaluation scripts
```
