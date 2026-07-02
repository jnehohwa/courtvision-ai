import XCTest
@testable import CourtVision

private struct CapturedShotQualityRequest: Sendable {
    let method: String?
    let path: String?
    let contentType: String?
    let playerId: String?
    let attemptCount: Int
    let shotValue: Int?
    let gameClockSeconds: Int?
    let scoreDifferential: Int?
}

private final class RequestCaptureBox: @unchecked Sendable {
    private let lock = NSLock()
    private var value: CapturedShotQualityRequest?

    func set(_ value: CapturedShotQualityRequest) {
        lock.lock()
        defer { lock.unlock() }
        self.value = value
    }

    func get() -> CapturedShotQualityRequest? {
        lock.lock()
        defer { lock.unlock() }
        return value
    }
}

private enum URLProtocolTestError: Error {
    case missingHandler
    case missingBody
    case invalidBody
    case invalidURL
}

private final class ShotQualityURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool {
        true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        guard let handler = Self.requestHandler else {
            client?.urlProtocol(self, didFailWithError: URLProtocolTestError.missingHandler)
            return
        }

        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

@MainActor
final class APIModelsTests: XCTestCase {
    func testEnvelopeDecodesSnakeCasePayload() throws {
        let json = """
        {
          "type": "play_added",
          "schema_version": "1.0",
          "game_id": "game-1",
          "sequence": 2,
          "occurred_at": "2026-06-14T12:00:00Z",
          "ingested_at": "2026-06-14T12:00:08Z",
          "source_status": "replay",
          "model_version": "live-win-logistic-baseline-1.0",
          "payload": {
            "sequence": 2,
            "source_event_id": "event-2",
            "revision": 1,
            "event_type": "shot_made",
            "description": "Driving layup",
            "period": 1,
            "clock_seconds": 610,
            "home_score": 2,
            "away_score": 0,
            "possession_team_id": "away",
            "home_fouls": 0,
            "away_fouls": 0,
            "x": 1.0,
            "y": 3.0,
            "shot_value": 2,
            "home_probability": 0.58
          }
        }
        """

        let envelope = try APIClient.makeDecoder().decode(
            WebSocketEnvelope.self,
            from: Data(json.utf8)
        )

        XCTAssertEqual(envelope.schemaVersion, "1.0")
        XCTAssertEqual(envelope.type, .playAdded)
        XCTAssertEqual(envelope.payload?.timelinePoint.homeScore, 2)
    }

    func testEnvelopeRejectsUnknownEventType() {
        let json = """
        {
          "type": "not_a_contract_event",
          "schema_version": "1.0",
          "game_id": "game-1",
          "sequence": 2,
          "occurred_at": "2026-06-14T12:00:00Z",
          "ingested_at": "2026-06-14T12:00:08Z",
          "source_status": "replay",
          "model_version": null,
          "payload": null
        }
        """

        XCTAssertThrowsError(
            try APIClient.makeDecoder().decode(
                WebSocketEnvelope.self,
                from: Data(json.utf8)
            )
        )
    }

    func testClockFormatting() {
        XCTAssertEqual(ScoreboardView.clock(138), "02:18")
    }

    func testAPIDateUsesUTCDayAtLocalMidnightBoundary() throws {
        let date = try XCTUnwrap(
            ISO8601DateFormatter().date(from: "2026-06-14T23:17:00Z")
        )

        XCTAssertEqual(APIClient.apiDateString(from: date), "2026-06-14")
    }

    func testConfiguredBaseURLUsesEnvironmentBeforeInfoPlist() {
        let url = APIClient.configuredBaseURL(
            environment: ["COURTVISION_API_URL": "https://env-api.courtvision.test"],
            infoDictionary: [
                "CourtVisionAPIBaseURL": "https://plist-api.courtvision.test"
            ]
        )

        XCTAssertEqual(url.absoluteString, "https://env-api.courtvision.test")
    }

    func testConfiguredBaseURLUsesInfoPlistForDeviceBuilds() {
        let url = APIClient.configuredBaseURL(
            environment: [:],
            infoDictionary: [
                "CourtVisionAPIBaseURL": "https://api.courtvision.test"
            ]
        )

        XCTAssertEqual(url.absoluteString, "https://api.courtvision.test")
    }

    func testConfiguredBaseURLIgnoresPlaceholdersAndFallsBackToLocalhost() {
        let url = APIClient.configuredBaseURL(
            environment: ["COURTVISION_API_URL": ""],
            infoDictionary: [
                "CourtVisionAPIBaseURL": "$(COURTVISION_API_URL)"
            ]
        )

        XCTAssertEqual(url.absoluteString, "http://127.0.0.1:8000")
    }

    func testAPIClientLabelsLocalAndHostedBackends() {
        let localClient = APIClient(baseURL: URL(string: "http://127.0.0.1:8000")!)
        let hostedClient = APIClient(baseURL: URL(string: "https://api.courtvision.test")!)

        XCTAssertTrue(localClient.usesLocalBackend)
        XCTAssertEqual(localClient.configurationLabel, "Local fixture API")
        XCTAssertFalse(hostedClient.usesLocalBackend)
        XCTAssertEqual(hostedClient.configurationLabel, "Hosted API")
    }

    func testDecoderAcceptsFractionalUTCDate() throws {
        let json = """
        {
          "date": "2026-06-14",
          "games": [{
            "id": "game-1",
            "scheduled_at": "2026-06-14T18:30:00Z",
            "home_team": {"id": "bos", "name": "Boston", "abbreviation": "BOS"},
            "away_team": {"id": "nyk", "name": "New York", "abbreviation": "NYK"},
            "home_score": 0,
            "away_score": 0,
            "period": 0,
            "clock_seconds": 2880,
            "status": "scheduled",
            "source_status": "replay",
            "last_ingested_at": "2026-06-14T18:29:52.123456Z",
            "prediction": null
          }]
        }
        """

        let response = try APIClient.makeDecoder().decode(
            GamesResponse.self,
            from: Data(json.utf8)
        )

        XCTAssertNotNil(response.games.first?.lastIngestedAt)
    }

    func testLiveSnapshotDecodesModelAndFreshnessMetadata() throws {
        let json = """
        {
          "game": {
            "id": "game-1",
            "scheduled_at": "2026-06-14T18:30:00Z",
            "home_team": {"id": "bos", "name": "Boston", "abbreviation": "BOS"},
            "away_team": {"id": "nyk", "name": "New York", "abbreviation": "NYK"},
            "home_score": 102,
            "away_score": 99,
            "period": 4,
            "clock_seconds": 138,
            "status": "replay",
            "source_status": "replay",
            "last_ingested_at": "2026-06-14T18:29:52Z",
            "prediction": null
          },
          "timeline": [],
          "latest_sequence": 20,
          "source_label": "Historical replay",
          "is_stale": false,
          "freshness_seconds": 8,
          "live_model_version": "live-win-logistic-baseline-1.0",
          "snapshot_generated_at": "2026-06-14T18:30:00Z"
        }
        """

        let snapshot = try APIClient.makeDecoder().decode(
            LiveSnapshot.self,
            from: Data(json.utf8)
        )

        XCTAssertEqual(snapshot.liveModelVersion, "live-win-logistic-baseline-1.0")
        XCTAssertEqual(snapshot.freshnessSeconds, 8)
    }

    func testHealthResponseDecodesSourceHealth() throws {
        let json = """
        {
          "status": "ok",
          "database": "ok",
          "redis": "degraded",
          "latest_ingestion_at": "2026-06-14T18:29:52Z",
          "data_lag_seconds": 12,
          "delayed_live_enabled": false,
          "sources": {
            "replay": {
              "status": "ok",
              "last_attempt_at": "2026-06-14T18:29:40Z",
              "last_success_at": "2026-06-14T18:29:41Z",
              "last_event_at": null,
              "last_error": null,
              "consecutive_failures": 0,
              "total_polls": 7,
              "total_events": 20,
              "current_poll_interval_seconds": 2.5,
              "updated_at": "2026-06-14T18:29:52Z"
            }
          }
        }
        """

        let health = try APIClient.makeDecoder().decode(
            HealthResponse.self,
            from: Data(json.utf8)
        )

        XCTAssertEqual(health.sources["replay"]?.totalEvents, 20)
        XCTAssertEqual(health.sources["replay"]?.currentPollIntervalSeconds, 2.5)
    }

    func testShotQualityRequestEncodesSnakeCase() throws {
        let request = ShotQualityRequest(
            playerId: "player-1",
            attempts: [
                ShotAttemptRequest(
                    x: 4.5,
                    y: 22.0,
                    shotValue: 3,
                    period: 2,
                    gameClockSeconds: 312,
                    scoreDifferential: -4
                )
            ]
        )

        let data = try APIClient.makeEncoder().encode(request)
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        let attempts = try XCTUnwrap(object["attempts"] as? [[String: Any]])
        let attempt = try XCTUnwrap(attempts.first)

        XCTAssertEqual(object["player_id"] as? String, "player-1")
        XCTAssertEqual(attempt["shot_value"] as? Int, 3)
        XCTAssertEqual(attempt["game_clock_seconds"] as? Int, 312)
        XCTAssertEqual(attempt["score_differential"] as? Int, -4)
    }

    func testShotQualityResponseDecodesResult() throws {
        let json = """
        {
          "player_id": "player-1",
          "definition": "Shooter-neutral expected field-goal probability.",
          "model_version": "shot-quality-baseline-1.0",
          "attempts": [{
            "x": 4.5,
            "y": 22.0,
            "distance_feet": 24.2,
            "angle_degrees": 12.4,
            "shot_value": 3,
            "make_probability": 0.37,
            "expected_points": 1.11,
            "quality_label": "Average"
          }]
        }
        """

        let response = try APIClient.makeDecoder().decode(
            ShotQualityResponse.self,
            from: Data(json.utf8)
        )

        XCTAssertEqual(response.playerId, "player-1")
        XCTAssertEqual(response.attempts.first?.expectedPoints, 1.11)
    }

    func testAPIClientShotQualityPostsSnakeCaseAndDecodesResponse() async throws {
        let captureBox = RequestCaptureBox()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ShotQualityURLProtocol.self]
        let session = URLSession(configuration: configuration)
        defer {
            ShotQualityURLProtocol.requestHandler = nil
            session.invalidateAndCancel()
        }

        ShotQualityURLProtocol.requestHandler = { request in
            let body = try Self.requestBodyData(from: request)
            let object = try XCTUnwrap(
                JSONSerialization.jsonObject(with: body) as? [String: Any]
            )
            let attempts = try XCTUnwrap(object["attempts"] as? [[String: Any]])
            let firstAttempt = try XCTUnwrap(attempts.first)
            captureBox.set(
                CapturedShotQualityRequest(
                    method: request.httpMethod,
                    path: request.url?.path,
                    contentType: request.value(forHTTPHeaderField: "Content-Type"),
                    playerId: object["player_id"] as? String,
                    attemptCount: attempts.count,
                    shotValue: firstAttempt["shot_value"] as? Int,
                    gameClockSeconds: firstAttempt["game_clock_seconds"] as? Int,
                    scoreDifferential: firstAttempt["score_differential"] as? Int
                )
            )
            guard let url = request.url else {
                throw URLProtocolTestError.invalidURL
            }
            let response = try XCTUnwrap(
                HTTPURLResponse(
                    url: url,
                    statusCode: 200,
                    httpVersion: nil,
                    headerFields: ["Content-Type": "application/json"]
                )
            )
            let responseBody = """
            {
              "player_id": "player-9",
              "definition": "Shooter-neutral expected field-goal probability.",
              "model_version": "shot-quality-baseline-1.0",
              "attempts": [{
                "x": 7.5,
                "y": 18.0,
                "distance_feet": 19.5,
                "angle_degrees": 24.0,
                "shot_value": 2,
                "make_probability": 0.51,
                "expected_points": 1.02,
                "quality_label": "Average"
              }]
            }
            """
            return (response, Data(responseBody.utf8))
        }

        let client = APIClient(
            baseURL: URL(string: "https://courtvision.test")!,
            session: session
        )
        let response = try await client.shotQuality(
            playerID: "player-9",
            attempts: [
                ShotAttemptRequest(
                    x: 7.5,
                    y: 18.0,
                    shotValue: 2,
                    period: 3,
                    gameClockSeconds: 221,
                    scoreDifferential: 6
                )
            ]
        )
        let captured = try XCTUnwrap(captureBox.get())

        XCTAssertEqual(captured.method, "POST")
        XCTAssertEqual(captured.path, "/api/v1/shot-quality")
        XCTAssertEqual(captured.contentType, "application/json")
        XCTAssertEqual(captured.playerId, "player-9")
        XCTAssertEqual(captured.attemptCount, 1)
        XCTAssertEqual(captured.shotValue, 2)
        XCTAssertEqual(captured.gameClockSeconds, 221)
        XCTAssertEqual(captured.scoreDifferential, 6)
        XCTAssertEqual(response.modelVersion, "shot-quality-baseline-1.0")
        XCTAssertEqual(response.attempts.first?.expectedPoints, 1.02)
    }

    func testAPIClientSurfacesServerErrorDetail() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ShotQualityURLProtocol.self]
        let session = URLSession(configuration: configuration)
        defer {
            ShotQualityURLProtocol.requestHandler = nil
            session.invalidateAndCancel()
        }

        ShotQualityURLProtocol.requestHandler = { request in
            guard let url = request.url else {
                throw URLProtocolTestError.invalidURL
            }
            let response = try XCTUnwrap(
                HTTPURLResponse(
                    url: url,
                    statusCode: 404,
                    httpVersion: nil,
                    headerFields: ["Content-Type": "application/json"]
                )
            )
            return (response, Data(#"{"detail":"Game not found"}"#.utf8))
        }

        let client = APIClient(
            baseURL: URL(string: "https://courtvision.test")!,
            session: session
        )

        do {
            _ = try await client.game(gameID: "missing-game")
            XCTFail("Expected the API client to throw the server detail.")
        } catch APIError.server(let statusCode, let detail) {
            XCTAssertEqual(statusCode, 404)
            XCTAssertEqual(detail, "Game not found")
        } catch {
            XCTFail("Expected APIError.server, got \(error).")
        }
    }

    private static func requestBodyData(from request: URLRequest) throws -> Data {
        if let body = request.httpBody {
            return body
        }
        guard let stream = request.httpBodyStream else {
            throw URLProtocolTestError.missingBody
        }

        stream.open()
        defer { stream.close() }

        var data = Data()
        let bufferSize = 1_024
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
        defer { buffer.deallocate() }

        while stream.hasBytesAvailable {
            let count = stream.read(buffer, maxLength: bufferSize)
            if count < 0 {
                throw stream.streamError ?? URLProtocolTestError.invalidBody
            }
            if count == 0 {
                break
            }
            data.append(buffer, count: count)
        }
        return data
    }
}
