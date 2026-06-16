import XCTest
@testable import CourtVision

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
}
