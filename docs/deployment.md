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

## API on Render

The API must allow the Vercel web origin:

```bash
COURTVISION_CORS_ORIGINS=https://<vercel-production-domain>
```

Add preview deployment origins only when you intentionally want preview builds
to call the hosted API. Keep ingestion and retraining commands private; the
public deployment should expose only read-only REST routes plus replay/WebSocket
behavior for synthetic or licensed fixtures.

## Current Status

As of the latest checkpoint, GitHub has no deployment records for this
repository and no Vercel check-runs. The repo is ready to link, but production
Vercel deployment still requires an authenticated Vercel project.
