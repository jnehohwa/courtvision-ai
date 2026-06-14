# CourtVision AI Handoff

Last updated: 2026-06-14

## Current State

CourtVision AI has a verified replay-first vertical slice:

- Public repository: `https://github.com/jnehohwa/courtvision-ai`
- FastAPI REST and WebSocket API
- SQLAlchemy models and Alembic migrations
- Redis-compatible replay queue and pub/sub with an in-process local fallback
- Deterministic pregame, shot-quality, and live-win benchmarks
- Offline calibrated model candidate pipeline
- Responsive Next.js dashboard
- Native SwiftUI client
- Shared OpenAPI and WebSocket contracts
- Docker Compose, Render configuration, and CI

## Verification Baseline

The latest complete verification in this continuation passed:

- Backend: 39 tests
- Ruff: clean
- Web: ESLint, TypeScript, Vitest, Next.js production build
- Playwright: desktop and mobile before the latest metadata-only UI change
- Swift: app and XCTest source typechecking with the Xcode XCTest overlay
- ML: 10 tests plus artifact-bound trainer and incumbent-gate smoke tests
- Database: blank SQLite and `0004` upgrade paths through Alembic `0005 (head)`
- Registry: private CLI promotion, activation history, reseed preservation,
  artifact hashing, same-split incumbent comparison, and rollback tests
- Runtime: deterministic replay and WebSocket heartbeat
- GitHub Actions: backend and web jobs green for commits `f4b7993` and `5050e6d`

The full Xcode simulator build remains blocked by the local machine having iOS
26.0 and 26.1 runtimes while Xcode 26.5 requires a matching simulator runtime.
`xcodebuild -showdestinations` therefore reports no eligible destination. Swift
application and XCTest source compilation is clean.

## Current Increment

Completed in this continuation:

1. Added normalized `team_game_statistics`, `shots`, and `feature_snapshots`.
2. Added Alembic revisions `0003` and `0004`; blank-database migration is green.
3. Added validated source batches, bounded retry, adaptive polling, and
   persistent source health metrics.
4. Added idempotent play ingestion, correction sequencing, normalized shot
   creation, and correction-ready WebSocket envelopes.
5. Added Redis-backed public rate limiting with an in-memory fallback.
6. Added authoritative live model and freshness metadata to web and iOS.
7. Added benchmark-driven ML promotion: candidates must beat the declared
   prevalence baseline on Brier score and log loss and maintain ECE `<= 0.05`.
8. Added reproducibility metadata for dataset version, feature schema, training
   commit, baseline metrics, winner metrics, and activation state.
9. Made in-process replay starts atomic and covered concurrent starts.
10. Prevented out-of-order source batches from rewinding the authoritative game
    snapshot and changed internal-key validation to constant-time comparison.
11. Completed a read-only Claude/Gemini review and verified each finding before
    editing. Incorrect findings were rejected rather than applied blindly.
12. Published the public repository and established the verify, handoff,
    commit, push, and upstream-sync checkpoint workflow.
13. Added Alembic revision `0005` and a transactional private model registry.
14. Enforced one active model per type, status consistency, artifact SHA-256
    binding, activation-history referential integrity, and retained rollback
    targets.
15. Added incumbent evaluation on the same chronological holdout and required
    version/hash identity with the active registry model.
16. Changed fixture seeding to preserve promoted models and record initial
    baseline activation instead of silently restoring the fixture baseline.

The in-app browser rejected the latest localhost reload under its URL policy
and explicitly prohibited switching browser surfaces for the same action.
Do not claim the latest metadata-only copy was visually reverified until that
policy condition changes. Type checking and production builds are green.

## Important Product Boundaries

- Public fixtures are synthetic or curated historical replay.
- Do not describe the product as licensed low-latency or true real-time NBA data.
- Player identity is attribution only for shot quality.
- Defender-aware shot quality requires licensed tracking data.
- The shipped API uses deterministic benchmarks; `ml/` contains offline
  candidate training and promotion logic.
- The offline prevalence baseline is the minimum promotion threshold. Replacing
  an artifact-backed active model must also beat that exact version on the same
  chronological holdout.

## Resume Instructions

1. Read this file and `README.md`.
2. Run `git status --short --branch` and confirm the current branch is synced
   with GitHub before editing.
   GitHub CLI commands on this machine require:

   ```bash
   export GH_CONFIG_DIR="$HOME/Library/Application Support/gh"
   ```
3. Run backend tests with:

   ```bash
   PYTHONPATH=apps/api .venv/bin/pytest apps/api/tests -q
   PYTHONPATH=apps/api .venv/bin/ruff check apps/api ml
   ```

4. Run web checks from `apps/web`:

   ```bash
   ./node_modules/.bin/eslint .
   ./node_modules/.bin/tsc --noEmit
   ./node_modules/.bin/vitest run
   ./node_modules/.bin/next build
   ```

5. Run ML checks with the available scientific Python environment:

   ```bash
   PYTHONPATH=ml /opt/anaconda3/bin/python -m pytest ml/tests -q
   ```

6. The next valuable increment is inference integration: load the active
   registered artifact after verifying its SHA-256 and feature schema, expose
   its actual version in predictions, and gracefully retain the deterministic
   baseline when the artifact is missing or invalid.

## Checkpoint Workflow

Every substantial session ends in this order:

1. Complete and verify a coherent increment.
2. Update this handoff with exact results and the next resume point.
3. Audit the staged changes for secrets, generated files, and unrelated edits.
4. Commit with a descriptive message and push to GitHub.
5. Confirm the branch is synchronized with its upstream.

Commits should reflect real progress; do not create empty or misleading commits
solely to increase contribution activity.

## Verification Notes

- Backend emits a Starlette deprecation warning about the current TestClient
  `httpx` bridge; it does not fail tests.
- The Anaconda pytest stack warns that `asyncio_mode` is unknown when running
  the synchronous ML-only test directory.
- Public GitHub publication is complete. Commit `f4b7993` is the initial
  portfolio MVP and `5050e6d` records the checkpoint workflow.
- PostgreSQL registry execution was not run locally because neither a Docker
  daemon nor `psql` is available. PostgreSQL uses a per-model advisory
  transaction lock; SQLite migration and constraint behavior is verified.
