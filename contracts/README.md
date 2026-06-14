# Contracts

`websocket-envelope.schema.json` is the source of truth for live messages.
REST clients are generated from FastAPI's `/openapi.json` endpoint after the
API is running.

```bash
pnpm generate:contracts
```
