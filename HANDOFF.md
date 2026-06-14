# CourtVision AI Handoff

Last updated: 2026-06-15

## Current State

CourtVision AI has a verified replay-first vertical slice:

- Public repository: `https://github.com/jnehohwa/courtvision-ai`
- FastAPI REST and WebSocket API
- SQLAlchemy models and Alembic migrations
- Redis-compatible replay queue and pub/sub with an in-process local fallback
- Deterministic pregame, shot-quality, and live-win fallbacks
- Verified active-artifact inference for all three model surfaces
- Offline calibrated model candidate pipeline
- Responsive Next.js dashboard
- Native SwiftUI client
- Shared OpenAPI and WebSocket contracts
- Docker Compose, Render configuration, and CI

## Verification Baseline

The latest complete local verification passed:

- Backend and ML: 63 tests
- Ruff: clean
- Web: ESLint, TypeScript, Vitest, Next.js production build
- Swift: simulator build/run with no diagnostics and 5 XCTest cases
- Native acceptance: populated fixture dashboard, game room, model/freshness
  metadata, win-probability chart, shot map selection, and timeline
- Database: blank SQLite upgrade through Alembic `0005`, downgrade to `0004`,
  re-upgrade, and fixture seed
- OpenAPI: regenerated contract matches the committed schema
- Registry: private CLI promotion, activation history, reseed preservation,
  artifact hashing, runtime compatibility, same-split incumbent comparison,
  and rollback tests
- Runtime: active pregame, shot-quality, and live-win artifacts plus
  deterministic fallback, replay, WebSocket backlog, and heartbeat behavior
- Artifact lifecycle: a current-runtime pregame candidate was trained,
  registered, loaded, and used for inference in an isolated database

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
17. Added shared versioned model contracts for pregame, shot quality, and live
    win probability.
18. Added verified active-artifact loading with SHA-256, feature-order,
    schema-version, runtime-version, classifier-interface, and class-order
    checks.
19. Moved artifact reads, hashing, deserialization, and prediction off the
    async event loop and cached immutable artifacts by type, version, and hash.
20. Integrated active artifacts into REST snapshots, shot-quality batches,
    WebSocket backlog delivery, delayed ingestion broadcasts, and pinned
    historical replay.
21. Preserved deterministic fallback for missing, tampered, incompatible, or
    request-failing artifacts and report the model version actually used.
22. Added runtime metadata to training manifests, promotion validation, and
    rollback validation.
23. Normalized public API timestamps to UTC and made the Swift decoder accept
    both whole-second and fractional ISO-8601 timestamps.
24. Made the iOS games query use the UTC API day and added simulator-only
    signing settings without changing device signing.
25. Installed and verified the matching iOS 26.5 simulator runtime. The app
    builds, launches, loads the seeded API, and passes all 5 XCTest cases.

## Important Product Boundaries

- Public fixtures are synthetic or curated historical replay.
- Do not describe the product as licensed low-latency or true real-time NBA data.
- Player identity is attribution only for shot quality.
- Defender-aware shot quality requires licensed tracking data.
- The API can use a verified registered artifact and intentionally falls back
  to deterministic benchmarks when the artifact cannot be trusted or loaded.
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

5. Run the native checks with XcodeBuildMCP using the saved `CourtVision`
   project, `CourtVision` scheme, and iPhone 17 / iOS 26.5 simulator defaults.

6. The next valuable increment is deployment-grade model artifact storage and
   replay acceptance automation. Replace local-only artifact paths with a
   private storage adapter suitable for separate Render API/worker processes,
   then run the full web replay workflow in Playwright and add durable native
   UI coverage for reconnect and sequence recovery.

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
- Public GitHub publication is complete. Commit `f4b7993` is the initial
  portfolio MVP and `5050e6d` records the checkpoint workflow.
- PostgreSQL registry execution was not run locally because neither a Docker
  daemon nor `psql` is available. PostgreSQL uses a per-model advisory
  transaction lock; SQLite migration and constraint behavior is verified.
- The current artifact registry stores local filesystem paths. Production API
  and worker processes must share a private mounted volume until the next
  storage-adapter increment is complete.
