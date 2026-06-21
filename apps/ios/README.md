# CourtVision iOS

Generate the Xcode project:

```bash
brew install xcodegen
cd apps/ios
xcodegen generate
open CourtVision.xcodeproj
```

The simulator client defaults to `http://127.0.0.1:8000`. Set the
`COURTVISION_API_URL` launch environment variable to use another backend.

The game room fetches an authoritative snapshot before opening its WebSocket,
reconnects from the last observed sequence with bounded exponential backoff,
and switches to periodic REST snapshots after repeated stream failures. Failed
polls retain the last valid timeline and surface the degraded state inline.
Selecting a shot on the court requests shooter-neutral shot quality from the
REST API and displays xPTS, make probability, model version, and an explicit
no-defender-tracking label.

From the repository root, run the shared REST and WebSocket contract checks
before simulator tests:

```bash
python3 tools/check_ios_rest_contract.py
python3 tools/check_ios_websocket_contract.py
```
