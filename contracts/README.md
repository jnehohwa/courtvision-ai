# Contracts

`websocket-envelope.schema.json` is the source of truth for live messages. It
defines the common envelope plus typed `play_added` and `play_corrected`
payloads consumed by the web and iOS clients. Backend contract tests validate
actual presenter output against this schema and reject incomplete play payloads.

REST clients are generated from FastAPI's `/openapi.json` endpoint after the
API is running.

```bash
pnpm generate:contracts
```
