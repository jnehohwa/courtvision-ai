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
