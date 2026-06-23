# Deployment Notes

CourtVision AI is deployment-ready, but the public web app has not been
deployed to Vercel yet. Deploy the backend first so the Vercel build can be
configured with stable API and WebSocket URLs.

## Web on Vercel

Create a Vercel project from the GitHub repository and set:

- Root Directory: `apps/web`
- Install Command: `cd ../.. && pnpm install --frozen-lockfile`
- Build Command: `pnpm build`

The same values are committed in `apps/web/vercel.json` for project-level
defaults when the Vercel root directory is `apps/web`.

Required Vercel environment variables:

```bash
NEXT_PUBLIC_API_URL=https://<render-api-host>
NEXT_PUBLIC_WS_URL=wss://<render-api-host>
COURTVISION_INTERNAL_API_URL=https://<render-api-host>
COURTVISION_INTERNAL_API_KEY=<same value configured on the API>
```

`NEXT_PUBLIC_*` values are compiled into the client bundle, so changing them
requires a new Vercel deployment.

The server-side replay proxy rejects production replay-start requests with a
clear `503` unless the internal Render URL and shared internal key are set. It
also rejects the development replay key in production, matching the API startup
guardrail.

Do not commit `.vercel/project.json`; local Vercel linkage belongs in the
ignored `.vercel/` directory. If you later add a Vercel CLI deploy workflow,
keep `VERCEL_TOKEN`, `VERCEL_ORG_ID`, and `VERCEL_PROJECT_ID` in GitHub
Secrets.

## API on Render

The API must allow the Vercel web origin:

```bash
COURTVISION_CORS_ORIGINS=https://<vercel-production-domain>
```

The Render blueprint intentionally leaves the following API values
dashboard-managed via `sync: false`:

```bash
COURTVISION_INTERNAL_API_KEY=<same value configured in Vercel>
COURTVISION_CORS_ORIGINS=https://<vercel-production-domain>
```

The API validates production settings at startup. A production process will fail
fast if it is still using the development internal key, loopback CORS origins,
SQLite, loopback Redis, or untrusted proxy headers.

The API also attaches baseline security headers to HTTP responses. HSTS is
production-only so local HTTP development remains usable while hosted API
responses advertise HTTPS transport once `COURTVISION_ENVIRONMENT=production`.

`COURTVISION_ENABLE_DELAYED_LIVE` is explicitly `false` in the blueprint.
Enable delayed polling only after source-lag and rate-limit testing passes, and
keep the UI labels as delayed or replay data.

Add preview deployment origins only when you intentionally want preview builds
to call the hosted API. Keep ingestion and retraining commands private; the
public deployment should expose only read-only REST routes plus replay/WebSocket
behavior for synthetic or licensed fixtures.

## Readiness Gate

Run this local preflight before linking Vercel or syncing the Render blueprint:

```bash
python tools/check_deployment_readiness.py
```

The check validates:

- Vercel monorepo install/build defaults and standalone Next.js output.
- Required web environment-variable documentation.
- Ignored local Vercel project linkage.
- Render Postgres, Redis-compatible storage, API, replay worker, and ingestion
  service wiring.
- FastAPI baseline security headers and production-only HSTS source guardrail.
- Manual Render gates for CORS and the shared internal API key.
- Production environment flags and the delayed-live feature flag default.

CI runs the same preflight in the backend job.

## Current Status

Verified on 2026-06-22 against commit
`fe2f4b98065729a6537e01acce2f2a0aaec03d42`:

- GitHub Deployments API for `jnehohwa/courtvision-ai` returned `[]`.
- The commit's check-runs are GitHub Actions jobs only: `backend`, `web`,
  `e2e`, `redis-integration`, and `ios`; there are no Vercel check-runs.
- `apps/web/vercel.json` contains Vercel-ready project defaults.
- No `.vercel/project.json` is committed or present locally, so the checkout is
  not linked to an authenticated Vercel project.
- The Vercel CLI is not installed on this machine's `PATH`.

The repo is Vercel-ready, but the public web app has not been deployed to
Vercel yet. Production deployment still requires an authenticated Vercel project
and stable hosted API/WebSocket URLs.
