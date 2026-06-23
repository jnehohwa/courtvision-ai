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

Run the full-stack browser acceptance workflow from `apps/web`:

```bash
COURTVISION_E2E_FULL_STACK=1 \
PLAYWRIGHT_CHANNEL=chrome \
./node_modules/.bin/playwright test
```

Playwright owns an isolated API and Next.js process, recreates
`/tmp/courtvision-playwright.db` through Alembic, seeds the deterministic
fixture, leaves Redis unavailable to exercise the in-process replay fallback,
builds the production standalone web bundle, and verifies the REST snapshot
plus WebSocket replay on desktop and mobile. Recovery cases force a mid-replay
disconnect, confirm sequence-based catch-up, exhaust bounded reconnects, enter
REST polling, and preserve the last valid snapshot through a simulated `503`.

CI also runs the same browser replay workflow with a real Redis service and an
E2E replay worker:

```bash
COURTVISION_E2E_FULL_STACK=1 \
COURTVISION_E2E_REDIS_URL=redis://127.0.0.1:6379/1 \
COURTVISION_E2E_RUN_WORKER=1 \
PLAYWRIGHT_BROWSER=chromium \
./node_modules/.bin/playwright test
```

Use that mode locally only when Redis is available. It proves the API queues
replay commands through Redis, the worker publishes replay envelopes over Redis
pub/sub, and the browser receives them through the FastAPI WebSocket.

The Playwright harness shares an E2E-only non-default internal key between the
API and Next.js replay proxy, so production-style web runs exercise the same
private replay-start guardrail used by hosted deployments.

## Deployment

The web app is ready to link as a Vercel project with `apps/web` as the project
root, but it has not been deployed yet. See `docs/deployment.md` for the Vercel
and Render environment variables, CORS coupling, and the current deployment
status.

Before linking or redeploying, run the deployment preflight:

```bash
python tools/check_deployment_readiness.py
```

CI runs the same check to keep Vercel defaults, Render service wiring, manual
secret gates, and replay-first feature flags from drifting.

The API also validates production settings at startup. A production deployment
must provide a non-default internal API key, hosted PostgreSQL and Redis URLs,
HTTPS CORS origins, and trusted proxy headers.

API responses include baseline browser safety headers, including nosniff,
frame denial, no-referrer, a restrictive permissions policy, and
same-origin opener isolation. HSTS is only added when the API runs with
`COURTVISION_ENVIRONMENT=production`.

The web replay proxy also refuses to call the private replay-start endpoint in
production unless `COURTVISION_INTERNAL_API_URL` and a non-default
`COURTVISION_INTERNAL_API_KEY` are configured. Local development keeps the
deterministic fallback key for the seeded replay fixture.

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
baseline, calibration limit, dataset version, training commit, and Python/ML
runtime versions in one database transaction. Replaced models remain
registered as rollback targets.

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
It also records the Python, joblib, NumPy, pandas, and scikit-learn versions
required to deserialize the artifact safely.

At inference time, the API queries the active registry row, validates the exact
feature order and schema version, hashes the artifact bytes before loading,
checks binary class ordering, and caches the verified immutable model by
version and hash. Loading and prediction run outside the async event loop.
Missing, tampered, incompatible, or failing artifacts fall back to the
deterministic benchmark and report that benchmark's model version. Integrity
failures are emitted as structured error logs rather than being hidden as an
ordinary cache miss.

`joblib` artifacts are executable pickle payloads and must come only from the
private training and registration workflow. The public API exposes no model
write endpoints.

By default, registration retains a verified local path for development
compatibility. Set `COURTVISION_MODEL_ARTIFACT_LOCAL_ROOT` to copy candidates
into an immutable, content-addressed directory on a shared private volume. For
separate Render API, replay-worker, and ingestion processes, use private
S3-compatible object storage:

```bash
COURTVISION_MODEL_ARTIFACT_BACKEND=s3
COURTVISION_MODEL_ARTIFACT_S3_BUCKET=courtvision-private-models
COURTVISION_MODEL_ARTIFACT_S3_PREFIX=courtvision/models
COURTVISION_MODEL_ARTIFACT_S3_REGION=us-east-1
COURTVISION_MODEL_ARTIFACT_S3_ENDPOINT_URL=https://s3.example.com
```

The API uses the standard AWS credential chain, so credentials stay in secret
environment variables rather than registry rows. Configure the same artifact
settings on every process that reads predictions. Scope IAM permissions to the
single private bucket and prefix, enable object versioning where available,
and allow only the promotion process to write. The application also enforces
the configured bucket/prefix, a 100 MiB default size limit, URI length bounds,
and SHA-256 verification on publish and each cold load. Loaded models remain
cached by type, version, and hash, so the remote object is not fetched on every
prediction.

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

The production worker atomically moves each command into a processing list
before replay begins. A restarted worker recovers pending work from the
beginning, while clients reconcile deterministic sequence IDs. Successful
completion atomically removes the pending item and releases only the matching
token-owned game lock. This MVP deployment intentionally runs one replay worker;
multi-worker scaling should migrate the queue to Redis Streams consumer groups.

## Repository

```text
apps/api       FastAPI, SQLAlchemy, ingestion, ML inference, replay
apps/web       Next.js App Router dashboard
apps/ios       Native SwiftUI client
contracts      OpenAPI and WebSocket JSON Schema
ml             Reproducible training and evaluation scripts
```
