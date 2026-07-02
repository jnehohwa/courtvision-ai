# CourtVision AI Handoff

Last updated: 2026-07-02

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
- CI deployment-readiness preflight for Vercel/Render handoff drift
- Read-only public deployment-state checker for Vercel/GitHub evidence
- Vercel-ready web project config, but no authenticated Vercel deployment yet

## Verification Baseline

The latest complete local verification passed:

- Backend and ML: 90 tests locally, plus 3 Redis-only tests in CI
- Ruff: clean
- Web: ESLint, TypeScript, Vitest, Next.js production build, and Playwright
  desktop/mobile dashboard interaction through the installed Chrome channel
- Full-stack web acceptance: 8 desktop/mobile Playwright cases using a real
  Alembic-seeded API, REST snapshot, game WebSocket, 20 replay events, replay
  completion, disconnect/resume, missed-event recovery, and REST fallback
- Redis-backed full-stack acceptance: CI also runs the same browser replay
  workflow with a real Redis service and E2E replay worker, proving queued
  replay commands and Redis pub/sub delivery into the FastAPI WebSocket layer
- Swift: simulator build/run with no diagnostics, shared REST DTO and
  WebSocket enum contract validation, and 14 XCTest cases
- Native acceptance: populated fixture dashboard, game room, model/freshness
  metadata, win-probability chart, shot map selection, and timeline; model
  tests cover sequence resume and last-snapshot retention
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
- Artifact storage: managed local and S3-compatible publish/read, bucket and
  prefix scoping, byte limits, URI bounds, tamper detection, and remote-style
  resolver caching
- Deployment readiness: local and CI preflight validates Vercel defaults,
  Render service wiring, manual CORS/internal-key gates, production env flags,
  delayed-live default, and ignored local `.vercel/` linkage
- Production config guardrails: API settings fail fast on development internal
  keys, loopback CORS, SQLite, loopback Redis, or untrusted proxy headers when
  `COURTVISION_ENVIRONMENT=production`
- API rate limiting: public REST routes expose limit, remaining, reset, and
  retry-after headers on allowed and blocked responses, and CORS exposes those
  headers to allowed browser clients
- Redis E2E harness: the Playwright API launcher resets the dedicated E2E
  Redis database, waits for replay-worker readiness before serving `/health`,
  streams worker output into CI logs for queued replay debugging, and uses a
  Redis client configuration that allows idle blocking replay queue reads
- API security headers: all HTTP responses receive baseline browser safety
  headers and `Cache-Control: no-store`, with HSTS limited to production
- Web security headers: all Next.js routes receive baseline browser safety
  headers through `next.config.ts`
- Web replay proxy guardrail: production replay-start requests return a clear
  `503` unless the internal Render URL and a non-default internal key are
  configured; replay-start responses are returned with `Cache-Control: no-store`
- Web API client freshness: games, live snapshots, and replay-start requests
  explicitly use no-store fetches; failed replay starts restore the last valid
  timeline instead of leaving the UI in replaying state

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
26. Added a bounded content-addressed model artifact store with backward-
    compatible verified local paths, an optional managed local root, and a
    private S3-compatible backend.
27. Changed promotion, rollback, and inference to use the same storage
    boundary while preserving SHA-256 verification and off-event-loop I/O.
28. Added S3 bucket/prefix allowlisting, standard AWS credential-chain support,
    maximum artifact size and registry URI limits, atomic local publication,
    and structured integrity-failure logging.
29. Added storage metadata to model promotion records and content-addressed
    optional calibration artifact publication.
30. Verified desktop and mobile Playwright dashboard interaction. The first
    run correctly reported missing managed browsers; the repository's Chrome
    channel override passed both projects without changing application code.
31. Added an `e2e`-only FastAPI launcher that recreates an isolated SQLite
    database through Alembic, seeds fixtures, refuses non-E2E environments,
    and can delete only the documented `/tmp/courtvision-playwright.db` file.
32. Added dual-service Playwright orchestration and assertions proving the
    browser receives the real live snapshot, connects with
    `after_sequence=20`, streams all 20 replay events, and observes completion.
33. Added a GitHub Actions E2E job that installs Chromium and runs the
    full-stack replay workflow with desktop and mobile emulation.
34. Upgraded checkout, Node, pnpm, and uv setup actions to Node 24-compatible
    releases ahead of the June 16, 2026 runner transition. The uv action is
    pinned to the verified `v8.2.0` commit because upstream does not publish a
    `v8` alias. Its cache is keyed from all workspace `pyproject.toml` files
    while a generated `uv.lock` is not locally obtainable.
35. Made WebSocket retries bounded by consecutive message-free failures,
    exposed honest connecting/connected/polling UI states, and switched REST
    fallback to non-overlapping polling that preserves the last valid snapshot
    when a poll fails.
36. Added desktop/mobile acceptance that disconnects after sequence 5, proves
    reconnect with `after_sequence=5`, recovers sequences 6 through 20, forces
    repeated socket failure into polling, and retains sequence 20 through a
    simulated REST `503`.
37. Changed the full-stack browser harness from the development server to the
    production standalone Next.js bundle, avoiding Turbopack manifest churn
    between Playwright projects.
38. Added injectable native snapshot and game-stream boundaries, a configurable
    reconnect/polling policy, and Sendable API contracts for Swift 6 actor
    isolation.
39. Changed the iOS game room to reset retry state on any valid envelope,
    reconnect from the latest observed sequence, enter persistent REST polling
    after bounded stream failures, and preserve the last valid snapshot when
    polling fails.
40. Added inline native degraded-state messaging plus XCTest coverage proving
    reconnect from sequence 5, recovery through sequence 20, bounded fallback
    after three failed streams, and sequence-20 retention during source outage.
41. Added a public GitHub Actions native gate pinned to the standard
    `macos-26` arm64 image, Xcode 26.5, and the installed iPhone 17 / iOS 26.5
    simulator destination.
42. Replaced destructive replay `BLPOP` with recoverable Redis `BLMOVE`,
    token-owned locks, an atomic Lua acknowledgement, validated commands, and
    malformed-command removal while preserving the one-worker deployment
    boundary.
43. Added a dedicated real-Redis CI job that kills the replay worker after
    sequence 5, restarts it from the processing list, requires a complete
    sequence 1-through-20 replay, and checks stale-lock ownership plus poison
    command cleanup.
44. Strengthened the shared WebSocket JSON Schema with typed play-event
    payloads and added backend contract tests that validate actual presenter
    output for `play_added`, `play_corrected`, `source_status`, `heartbeat`,
    and `replay_completed` frames.
45. Changed the real-Redis worker restart test to enqueue through an actual
    Redis-backed `EventBus` instead of the API `TestClient`, removing ambiguity
    with the API's legitimate in-process fallback path.
46. Added generated web WebSocket types from
    `contracts/websocket-envelope.schema.json`, replaced the hand-written web
    `PlayPayload` copy, and extended CI drift checks to cover the generated
    WebSocket contract.
47. Added typed Swift WebSocket event enums, XCTest coverage for unknown event
    rejection, and a host-side iOS contract checker that validates Swift enum
    raw values against `contracts/websocket-envelope.schema.json` before
    simulator tests run in CI.
48. Hardened the iOS GitHub Actions job to create an iPhone 17 / iOS 26.5
    simulator, then target it by UDID instead of assuming the runner image has
    a pre-created named simulator.
49. Added Vercel-ready web project defaults and deployment notes. The GitHub
    repository currently has no Vercel deployment records or Vercel check-runs;
    actual deployment still requires linking an authenticated Vercel project.
50. Added Swift REST DTO coverage for health, game detail, prediction,
    shot-quality, source health, and replay-start responses; added public
    `APIClient` methods for read/query REST endpoints while keeping the
    private replay-start command out of the native client.
51. Added `tools/check_ios_rest_contract.py` to validate Swift REST DTO fields,
    `SourceStatus` values, public APIClient method coverage, snake_case
    encoder/decoder mapping, and the native private-command boundary against
    `contracts/openapi.json`; wired it into CI before simulator tests.
52. Wired the Swift shot-quality REST boundary into the selected-shot court
    analytics panel. The model now requests shooter-neutral xPTS only for
    events with coordinates and shot value, derives score differential from
    the live timeline state, cancels stale requests on selection changes, and
    displays make probability, expected points, quality label, model version,
    and explicit no-defender-tracking copy.
53. Added a runtime Swift `APIClient` integration test using a custom
    `URLProtocol` to prove `shotQuality` sends `POST /api/v1/shot-quality` as
    snake_case JSON through the production `URLSession` boundary and decodes
    the backend response shape.
54. Completed the iOS visual acceptance pass against the local fixture API.
    The selected-shot quality panel was promoted above the court canvas and
    the game room gained bottom scroll padding so the panel is visible above
    the tab bar. XcodeBuildMCP semantic snapshot `seq=16` confirmed rendered
    text for `xPTS`, `MAKE`, `QUALITY`, `1,41`, `71%`, `High`, the
    shooter-neutral definition, `shot-quality-baseline-1.0`, and
    `no defender tracking`; a simulator screenshot was captured and visually
    inspected for the same card.
55. Added `docs/ios-visual-acceptance.md` as a durable manual release gate for
    the selected-shot quality panel, including fixture API startup, expected
    health evidence, XcodeBuildMCP launch steps, semantic snapshot assertions,
    screenshot criteria, cleanup, and troubleshooting notes.
56. Re-verified deployment state on 2026-06-22 at commit
    `fe2f4b98065729a6537e01acce2f2a0aaec03d42`: GitHub Deployments API returned
    `[]`, check-runs were GitHub Actions only with no Vercel app entries,
    `apps/web/vercel.json` exists, no `.vercel/project.json` link exists, and
    the local Vercel CLI is absent. The web app remains Vercel-ready but not
    deployed.
57. Added `tools/check_deployment_readiness.py` and wired it into CI. The gate
    validates Vercel monorepo defaults, standalone Next output, required web
    env docs, ignored `.vercel/` linkage, Render Postgres/Redis/API/worker/cron
    wiring, dashboard-managed `COURTVISION_INTERNAL_API_KEY` and
    `COURTVISION_CORS_ORIGINS`, production env flags, and delayed-live default.
    The Render blueprint now keeps the API key and CORS origins as
    `sync: false`, sets production env flags for background processes, gives
    ingestion Redis, and keeps delayed polling explicitly disabled until the
    source-lag/rate-limit gate is passed.
58. Added a Redis-backed full-stack Playwright CI lane. `courtvision.e2e_server`
    can now launch the replay worker with `COURTVISION_E2E_RUN_WORKER=1`, the
    web harness accepts `COURTVISION_E2E_REDIS_URL`, and the new `e2e-redis`
    job runs the existing desktop/mobile replay acceptance suite against a real
    Redis service. The default local E2E path still leaves Redis unavailable to
    verify the in-process fallback.
59. Added production settings guardrails. `Settings` now rejects production
    startup with the development internal API key, short internal keys, empty
    or non-HTTPS CORS origins, loopback CORS hosts, non-PostgreSQL database
    URLs, loopback Redis URLs, or disabled trusted proxy headers. Added config
    tests for each rejection path plus the accepted hosted production shape.
60. Hardened the Next.js replay proxy. The server route now requires explicit
    `COURTVISION_INTERNAL_API_URL` and a non-default
    `COURTVISION_INTERNAL_API_KEY` in production before it will call the
    private replay-start endpoint, while preserving local replay defaults for
    development. Added route tests for missing game IDs, production
    misconfiguration, development-key rejection, URL normalization, and
    successful production forwarding. The deployment preflight now checks that
    the replay proxy keeps this production guardrail in place. The Playwright
    full-stack harness now shares an E2E-only non-default internal key between
    the API and Next.js so production-style replay tests keep exercising the
    private replay-start boundary.
61. Added FastAPI security headers. HTTP responses now include
    `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
    `Permissions-Policy`, and `Cross-Origin-Opener-Policy`; HSTS is added only
    when `COURTVISION_ENVIRONMENT=production`. Tests cover normal health/API
    responses, rate-limited `429` responses, and the production-only HSTS
    helper. The deployment preflight now checks the source guardrail for these
    headers.
62. Added Next.js security headers. `next.config.ts` now applies
    `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
    `Permissions-Policy`, and `Cross-Origin-Opener-Policy` to every route.
    Added a config test and deployment-preflight coverage so the hosted
    dashboard does not drift away from the same baseline browser protections as
    the API.
63. Added no-store cache headers for dynamic API and replay surfaces. The
    FastAPI middleware now applies `Cache-Control: no-store` alongside the
    baseline security headers, and the Next.js replay proxy returns no-store
    responses for validation errors, service-unconfigured responses, upstream
    replay-start results, and upstream failures. Tests cover both API headers
    and replay proxy responses, and the deployment preflight now guards the
    no-store policy.
64. Hardened the web API client freshness path. Games, live snapshots, and
    replay-start requests are now all covered by unit tests proving
    `cache: "no-store"`, and replay starts route through the shared API module.
    The live-game hook now restores the last valid timeline if the replay-start
    request is rejected or the local replay bridge is unavailable, avoiding a
    stuck replaying state. The deployment preflight now guards the web client
    no-store fetch policy.
65. Added an API rate-limit reset header. Rate-limit decisions now carry the
    fixed-window reset epoch, and public REST responses include
    `X-RateLimit-Reset` alongside limit, remaining, and retry-after headers on
    allowed and blocked responses. Tests cover deterministic reset values and
    the HTTP header, and the deployment preflight guards that reset-header
    behavior remains present.
66. Exposed API rate-limit headers through CORS. The FastAPI CORS middleware
    now makes `X-RateLimit-Limit`, `X-RateLimit-Remaining`,
    `X-RateLimit-Reset`, and `Retry-After` readable to allowed browser origins.
    Tests cover the `Access-Control-Expose-Headers` response, and the
    deployment preflight guards the exposed-header wiring.
67. Hardened the Redis-backed E2E replay harness. The isolated Playwright API
    launcher now flushes the dedicated E2E Redis database before worker tests,
    starts the replay worker with captured output, waits for the
    `replay_worker_ready` marker before exposing the API as healthy, and fails
    fast if the worker exits or never becomes ready. Tests cover the readiness
    wrapper and protect the Redis reset from non-E2E environments.
68. Fixed the Redis replay worker idle timeout. The shared EventBus Redis
    client no longer sets a one-second command socket timeout, which could kill
    the replay worker while it blocked on the queue during browser/server
    startup. Health checks still use their own short Redis timeout. A focused
    regression test now verifies the EventBus client keeps blocking commands
    free of `socket_timeout`.
69. Added `tools/check_public_deployment_state.py`, a read-only deployment
    evidence checker that reports GitHub deployments, Vercel check-runs on the
    current commit, local `.vercel/project.json` linkage, and Vercel CLI
    availability. The current verified state remains not deployed to Vercel:
    zero GitHub deployments, no Vercel check-runs, no local Vercel link, and no
    Vercel CLI on `PATH`.
70. Hardened the deployment-state checker so failed GitHub API queries, invalid
    JSON, or missing commit state report `unknown` evidence and
    `Verdict: unable to confirm deployment state` instead of incorrectly
    treating unavailable evidence as zero deployments.
71. Made WebSocket resume metadata more accurate by tracking the highest
    sequence successfully delivered per connected socket. Heartbeat frames now
    use that tracked sequence after replay events stream over the connection,
    and lower-sequence status frames cannot rewind the resume point.
72. Made WebSocket connection cleanup unconditional when a game socket handler
    exits. Expected `WebSocketDisconnect` exceptions are swallowed, unexpected
    exceptions still propagate, and the connection manager unregisters the
    socket in a `finally` block so heartbeat/send edge cases do not leave stale
    local subscribers behind.
73. Hardened the web live-game hook when switching games. The WebSocket now
    opens only after the authoritative snapshot belongs to the selected game,
    and the hook derives visible snapshot/timeline/model/replay state from the
    currently selected game so a new game cannot subscribe with the previous
    game's resume sequence. Added a focused hook regression test with a mocked
    WebSocket and controlled snapshot resolution.
74. Added an iOS device-build API URL configuration path. `APIClient` now
    resolves the backend URL from `COURTVISION_API_URL` launch environment
    first, then the `CourtVisionAPIBaseURL` Info.plist value populated by the
    `COURTVISION_API_URL` Xcode build setting, then localhost. Empty values and
    unresolved `$(...)` placeholders are ignored so simulator defaults remain
    safe until a hosted API URL is supplied for an installed/TestFlight build.

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
   PYTHONPATH=apps/api:ml .venv/bin/pytest -q
   PYTHONPATH=apps/api .venv/bin/ruff check apps/api ml tools
   .venv/bin/python tools/check_deployment_readiness.py
   ```

4. Run web checks from `apps/web`:

   ```bash
   ./node_modules/.bin/eslint .
   ./node_modules/.bin/tsc --noEmit
   ./node_modules/.bin/vitest run
   ./node_modules/.bin/next build
   COURTVISION_E2E_FULL_STACK=1 PLAYWRIGHT_CHANNEL=chrome ./node_modules/.bin/playwright test
   ```

   If Redis is available locally, also run:

   ```bash
   COURTVISION_E2E_FULL_STACK=1 \
   COURTVISION_E2E_REDIS_URL=redis://127.0.0.1:6379/1 \
   COURTVISION_E2E_RUN_WORKER=1 \
   PLAYWRIGHT_CHANNEL=chrome \
   ./node_modules/.bin/playwright test
   ```

5. Run the native checks with:

   ```bash
   python3 tools/check_ios_rest_contract.py
   python3 tools/check_ios_websocket_contract.py
   ```

   Then use XcodeBuildMCP with the saved `CourtVision` project,
   `CourtVision` scheme, and iPhone 17 / iOS 26.5 simulator defaults.
   If XcodeBuildMCP times out in `test-without-building`, kill the stale
   child `xcodebuild` process and run a fresh `xcodebuild test` or
   `xcodebuild clean test` with the same simulator destination.

6. The next valuable increment is to choose the deployment path deliberately:
   either link the web app to an authenticated Vercel project after the backend
   has stable hosted REST/WebSocket URLs and the deployment preflight passes, or
   continue local/replay-first product hardening while keeping the Vercel-ready
   versus deployed distinction honest.

   To re-check the public deployment evidence, run:

   ```bash
   export GH_CONFIG_DIR="$HOME/Library/Application Support/gh"
   .venv/bin/python tools/check_public_deployment_state.py
   ```

7. If deploying next, link Vercel with `apps/web` as the project root and set
   the environment variables in `docs/deployment.md`. Do not mark the web app
   deployed until Vercel returns a production URL and GitHub/Vercel deployment
   status confirms it.

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
- Private S3-compatible storage is implemented and unit-tested with an injected
  client, but no real provider credentials were available for an external
  upload/download smoke test. Configure identical storage settings on API,
  replay worker, and ingestion processes, with IAM restricted to the declared
  bucket and prefix.
- Full-stack E2E still leaves Redis unavailable by default to verify the local
  in-process fallback. The `e2e-redis` CI job covers the production-style Redis
  queue/pub-sub replay path; local Redis-backed Playwright was not run on this
  machine because `redis-server` is not installed.
- On 2026-06-23, the replay-proxy hardening increment passed:
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q` (`87 passed, 3 skipped`),
  `.venv/bin/python tools/check_deployment_readiness.py`,
  `./node_modules/.bin/eslint .`, `./node_modules/.bin/tsc --noEmit`,
  `./node_modules/.bin/vitest run` (`8 passed`),
  `./node_modules/.bin/next build`, and
  `COURTVISION_E2E_FULL_STACK=1 PLAYWRIGHT_CHANNEL=chrome ./node_modules/.bin/playwright test`
  (`8 passed`). The first Playwright attempt was intentionally rerun after it
  exposed the harness still using `local-development-key` under a production
  Next runtime; the harness now supplies a non-default E2E key to both services.
- On 2026-06-23, the API security-header increment passed:
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q` (`90 passed, 3 skipped`),
  `.venv/bin/python tools/check_deployment_readiness.py`, and
  `git diff --check`.
- On 2026-06-23, the Next.js security-header increment passed:
  `./node_modules/.bin/eslint .`, `./node_modules/.bin/tsc --noEmit`,
  `./node_modules/.bin/vitest run` (`9 passed`),
  `./node_modules/.bin/next build`,
  `.venv/bin/python tools/check_deployment_readiness.py`, and
  `git diff --check`.
- On 2026-06-23, the no-store cache-header increment passed:
  `PYTHONPATH=apps/api:ml .venv/bin/pytest apps/api/tests/test_security_headers.py apps/api/tests/test_rate_limit.py -q`
  (`6 passed`),
  `./node_modules/.bin/vitest run src/app/api/replay/route.test.ts`
  (`7 passed`),
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `.venv/bin/python tools/check_deployment_readiness.py`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q`
  (`90 passed, 3 skipped`), `./node_modules/.bin/eslint .`,
  `./node_modules/.bin/tsc --noEmit`, `./node_modules/.bin/vitest run`
  (`9 passed`), `./node_modules/.bin/next build`,
  `COURTVISION_E2E_FULL_STACK=1 PLAYWRIGHT_CHANNEL=chrome ./node_modules/.bin/playwright test`
  (`8 passed`), and `git diff --check`.
- On 2026-06-23, the web API-client freshness increment passed:
  `./node_modules/.bin/vitest run src/lib/api.test.ts` (`4 passed`),
  `./node_modules/.bin/eslint src/lib/api.ts src/lib/api.test.ts src/hooks/use-live-game.ts`,
  `./node_modules/.bin/tsc --noEmit`, `./node_modules/.bin/eslint .`,
  `./node_modules/.bin/vitest run` (`13 passed`),
  `.venv/bin/python tools/check_deployment_readiness.py`,
  `./node_modules/.bin/next build`,
  `COURTVISION_E2E_FULL_STACK=1 PLAYWRIGHT_CHANNEL=chrome ./node_modules/.bin/playwright test`
  (`8 passed`), and `git diff --check`.
- On 2026-06-23, the API rate-limit reset-header increment passed:
  `PYTHONPATH=apps/api:ml .venv/bin/pytest apps/api/tests/test_rate_limit.py apps/api/tests/test_security_headers.py -q`
  (`6 passed`),
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `.venv/bin/python tools/check_deployment_readiness.py`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q`
  (`90 passed, 3 skipped`), and `git diff --check`.
- On 2026-07-01, the CORS-exposed rate-limit headers increment passed:
  `PYTHONPATH=apps/api:ml .venv/bin/pytest apps/api/tests/test_rate_limit.py apps/api/tests/test_security_headers.py -q`
  (`7 passed`),
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `.venv/bin/python tools/check_deployment_readiness.py`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q`
  (`91 passed, 3 skipped`), and `git diff --check`.
- On 2026-07-01, the Redis E2E harness hardening increment passed:
  `PYTHONPATH=apps/api:ml .venv/bin/pytest apps/api/tests/test_e2e_server.py apps/api/tests/test_worker_redis_integration.py -q`
  (`4 passed, 3 skipped`),
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`, and
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q`
  (`92 passed, 3 skipped`). Local Redis-backed Playwright could not be run:
  `redis-server` is not installed, Docker exists but the daemon is not running,
  and the non-Redis Playwright rerun was stopped before app startup because
  pnpm had to recreate `node_modules` and registry downloads repeatedly timed
  out or retried.
- On 2026-07-01, the Redis replay worker idle-timeout fix passed:
  `PYTHONPATH=apps/api:ml .venv/bin/pytest apps/api/tests/test_broadcast.py apps/api/tests/test_e2e_server.py apps/api/tests/test_worker_redis_integration.py -q`
  (`5 passed, 3 skipped`),
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q`
  (`93 passed, 3 skipped`), and `git diff --check`. The immediately preceding
  CI run `28541657308` still failed only in `e2e-redis`, while backend, web,
  Redis integration, non-Redis e2e, and iOS all passed; this fix targets that
  isolated Redis browser lane.
- On 2026-07-01, the Redis replay observability increment added event-bus
  lifecycle logs, replay queue/receive logs, connected-client counts, worker
  command logging, and plain E2E launcher markers for Redis reset, worker
  start, worker ready, and worker exit. Focused verification passed:
  `PYTHONPATH=apps/api:ml .venv/bin/pytest apps/api/tests/test_broadcast.py apps/api/tests/test_e2e_server.py apps/api/tests/test_worker_redis_integration.py -q`
  (`5 passed, 3 skipped`),
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q`
  (`93 passed, 3 skipped`), and `git diff --check`. The latest CI run
  inspected before this increment was `28542591307`: backend, web, Redis
  integration, non-Redis e2e, and iOS passed, but `e2e-redis` still failed
  with zero `play_added` frames and no visible worker/event-bus lifecycle lines
  in the Actions log.
- On 2026-07-02, the public deployment-state checker increment passed:
  `PYTHONPATH=apps/api:ml .venv/bin/pytest apps/api/tests/test_public_deployment_state.py -q`
  (`5 passed` after the unavailable-evidence guard was added),
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q`
  (`98 passed, 3 skipped`),
  `.venv/bin/python tools/check_deployment_readiness.py`, and
  `export GH_CONFIG_DIR="$HOME/Library/Application Support/gh"; .venv/bin/python tools/check_public_deployment_state.py`.
  The read-only deployment check reported zero GitHub deployments, no Vercel
  check-runs on the current commit, no local `.vercel/project.json`, no Vercel
  CLI on `PATH`, and `Verdict: not deployed to Vercel yet`.
  Remote GitHub Actions run `28573557494` passed for commit
  `0ce75f3ceccd3e604fb8235b67ca808468782bbc`: backend, web,
  `redis-integration`, `e2e`, `e2e-redis`, and iOS were all green.
- On 2026-07-02, the WebSocket heartbeat sequence tracking increment passed:
  `PYTHONPATH=apps/api:ml .venv/bin/pytest apps/api/tests/test_broadcast.py apps/api/tests/test_api.py -q`
  (`12 passed`),
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q`
  (`99 passed, 3 skipped`),
  `.venv/bin/python tools/check_deployment_readiness.py`, and
  `export GH_CONFIG_DIR="$HOME/Library/Application Support/gh"; .venv/bin/python tools/check_public_deployment_state.py`.
  The deployment-state check still reported zero GitHub deployments, no Vercel
  check-runs, no local Vercel link, no Vercel CLI, and `Verdict: not deployed
  to Vercel yet`.
  Remote GitHub Actions run `28585855894` passed for commit
  `78a4ba89a1bcc6e0e0065861abe7dcc38da350ca`: backend, web,
  `redis-integration`, `e2e`, `e2e-redis`, and iOS were all green.
- On 2026-07-02, the WebSocket unconditional cleanup increment passed:
  `PYTHONPATH=apps/api:ml .venv/bin/pytest apps/api/tests/test_api.py apps/api/tests/test_broadcast.py -q`
  (`12 passed`),
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q`
  (`99 passed, 3 skipped`),
  `.venv/bin/python tools/check_deployment_readiness.py`, and
  `export GH_CONFIG_DIR="$HOME/Library/Application Support/gh"; .venv/bin/python tools/check_public_deployment_state.py`.
  The deployment-state check reported commit
  `78a4ba89a1bcc6e0e0065861abe7dcc38da350ca`, zero GitHub deployments, no
  Vercel check-runs, no local Vercel link, no Vercel CLI, and `Verdict: not
  deployed to Vercel yet`.
  Remote GitHub Actions run `28586267564` passed for commit
  `ed783dcc26d7d408f136b34012c6dec856e96947`: backend, web,
  `redis-integration`, `e2e`, `e2e-redis`, and iOS were all green.
- On 2026-07-02, the web game-switch WebSocket guard passed `git diff --check`.
  The first pushed version failed the GitHub Actions web lint job with
  `react-hooks/set-state-in-effect` because it synchronously cleared React
  state inside the snapshot-fetch effect. The follow-up fix derives the visible
  state from `snapshot.game.id === gameId` and only resets the transient
  sequence ref before fetching. Local web test execution was blocked by the
  machine's incomplete pnpm install:
  `pnpm --filter @courtvision/web exec vitest run src/hooks/use-live-game.test.tsx`,
  focused ESLint, and `tsc --noEmit` all triggered dependency rehydration and
  slow registry metadata/tarball retries; a direct Vitest invocation reached
  startup but failed because the interrupted install was missing Rollup's
  native optional package `@rollup/rollup-darwin-arm64`. The corrective pushed
  commit's GitHub Actions web job should be treated as the authoritative
  verifier for this increment.
- On 2026-07-02, the iOS device-build API URL configuration increment passed:
  `python3 tools/check_ios_rest_contract.py`,
  `python3 tools/check_ios_websocket_contract.py`, plist parsing for
  `CourtVisionAPIBaseURL`, `git diff --check`, and
  `xcodebuild build -project apps/ios/CourtVision.xcodeproj -scheme CourtVision -destination 'generic/platform=iOS Simulator' -derivedDataPath .xcode-derived-data`.
  Local `xcodebuild test` against `platform=iOS Simulator,name=iPhone 17,OS=26.5`
  could not run because this Mac's CoreSimulator service is out of date
  (`1051.54.0` versus Xcode's `1051.55.0`) and no matching iPhone 17 simulator
  destination is available. GitHub Actions remains the native simulator-test
  authority for committed iOS changes.
- On 2026-07-01, the Redis replay diagnostic follow-up moved E2E launcher and
  worker markers to stderr so Playwright web-server logs expose them, made the
  web replay client require a `{status: "started"}` response instead of any
  HTTP 2xx, and made the full-stack replay tests assert that `/api/replay`
  actually starts a replay. Backend verification passed:
  `PYTHONPATH=apps/api:ml .venv/bin/pytest apps/api/tests/test_e2e_server.py -q`
  (`4 passed`),
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q`
  (`93 passed, 3 skipped`), and `git diff --check`. Local web vitest/eslint
  could not complete because pnpm repeatedly retried slow/failed registry
  downloads while recreating `node_modules`; the web and e2e checks are expected
  to be verified by GitHub Actions after push.
- On 2026-07-01, CI run `28543598798` exposed the Redis E2E root cause: the
  replay worker started, reset Redis, became ready, then exited before tests
  began because the blocking `BLMOVE` read hit `redis.exceptions.TimeoutError`.
  That left the replay lock in Redis, so `/api/replay` returned
  `{status: "already_running"}` and no browser saw `play_added` frames. The fix
  explicitly sets `socket_timeout=None` on the event-bus Redis client and keeps
  the focused regression in `apps/api/tests/test_broadcast.py`. Verification
  passed:
  `PYTHONPATH=apps/api:ml .venv/bin/pytest apps/api/tests/test_broadcast.py apps/api/tests/test_e2e_server.py apps/api/tests/test_worker_redis_integration.py -q`
  (`5 passed, 3 skipped`),
  `PYTHONPATH=apps/api:ml .venv/bin/ruff check apps/api ml tools`,
  `PYTHONPATH=apps/api:ml .venv/bin/pytest -q`
  (`93 passed, 3 skipped`), and `git diff --check`.
- On 2026-07-01, GitHub Actions run `28543785381` passed on `main` after the
  Redis read-timeout fix: backend, web, Redis integration, non-Redis e2e,
  Redis-backed e2e, and iOS all completed successfully. This is the safe resume
  point for the next increment.
- The repository still has no committed `uv.lock`; a local `uv` wheel download
  was cancelled after sustained CDN throughput of roughly 34 kB/s. CI cache
  invalidation is explicitly keyed from the workspace dependency manifests in
  the meantime.
- Simulator tests should not read repository files through `#filePath` at
  runtime. A prior attempt to read the shared WebSocket schema directly inside
  XCTest hung under the simulator; host-side contract validation is the stable
  path.
- The `macos-26` GitHub runner can have the iOS 26.5 runtime and iPhone 17
  device type installed without a pre-created `iPhone 17` simulator. Create a
  simulator with `xcrun simctl create` in CI and pass its UDID to `xcodebuild`.
