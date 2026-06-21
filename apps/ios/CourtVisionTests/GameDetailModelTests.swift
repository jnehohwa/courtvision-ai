import Foundation
import XCTest
@testable import CourtVision

private enum RecoveryTestError: Error {
    case disconnected
    case sourceUnavailable
}

private struct ShotQualityCapture: Sendable {
    let playerID: String
    let attempts: [ShotAttemptRequest]
}

private actor ScriptedSnapshotProvider: LiveSnapshotProviding {
    private let initialSnapshot: LiveSnapshot
    private let failAfterInitial: Bool
    private var callCount = 0

    init(initialSnapshot: LiveSnapshot, failAfterInitial: Bool = false) {
        self.initialSnapshot = initialSnapshot
        self.failAfterInitial = failAfterInitial
    }

    func liveSnapshot(gameID: String) async throws -> LiveSnapshot {
        callCount += 1
        if failAfterInitial, callCount > 1 {
            throw RecoveryTestError.sourceUnavailable
        }
        return initialSnapshot
    }

    func calls() -> Int {
        callCount
    }
}

private actor ScriptedShotQualityProvider: ShotQualityProviding {
    private let response: ShotQualityResponse
    private var captures: [ShotQualityCapture] = []

    init(response: ShotQualityResponse) {
        self.response = response
    }

    func shotQuality(
        playerID: String,
        attempts: [ShotAttemptRequest]
    ) async throws -> ShotQualityResponse {
        captures.append(ShotQualityCapture(playerID: playerID, attempts: attempts))
        return response
    }

    func requests() -> [ShotQualityCapture] {
        captures
    }
}

private actor ScriptedGameStream: GameEventStreaming {
    struct Script: Sendable {
        let envelopes: [WebSocketEnvelope]
        let failure: Error?
        let holdOpen: Bool
    }

    private var scripts: [Script]
    private let defaultScript: Script
    private var requestedSequences: [Int] = []

    init(scripts: [Script], defaultScript: Script) {
        self.scripts = scripts
        self.defaultScript = defaultScript
    }

    func messages(
        gameID: String,
        after sequence: Int
    ) -> AsyncThrowingStream<WebSocketEnvelope, Error> {
        requestedSequences.append(sequence)
        let script = scripts.isEmpty ? defaultScript : scripts.removeFirst()

        return AsyncThrowingStream { continuation in
            let producer = Task {
                for envelope in script.envelopes {
                    continuation.yield(envelope)
                }
                if let failure = script.failure {
                    continuation.finish(throwing: failure)
                } else if script.holdOpen {
                    do {
                        try await Task.sleep(for: .seconds(60))
                    } catch {
                        continuation.finish()
                    }
                } else {
                    continuation.finish()
                }
            }
            continuation.onTermination = { _ in
                producer.cancel()
            }
        }
    }

    func disconnect() {}

    func sequences() -> [Int] {
        requestedSequences
    }
}

@MainActor
final class GameDetailModelTests: XCTestCase {
    func testReconnectsFromLastSequenceAndRecoversMissedEvents() async throws {
        let snapshot = makeSnapshot(latestSequence: 4, timeline: [makePoint(sequence: 4)])
        let provider = ScriptedSnapshotProvider(initialSnapshot: snapshot)
        let stream = ScriptedGameStream(
            scripts: [
                .init(
                    envelopes: [makeEnvelope(sequence: 5)],
                    failure: RecoveryTestError.disconnected,
                    holdOpen: false
                ),
                .init(
                    envelopes: [makeEnvelope(sequence: 6), makeEnvelope(sequence: 20)],
                    failure: nil,
                    holdOpen: true
                ),
            ],
            defaultScript: .init(
                envelopes: [],
                failure: RecoveryTestError.disconnected,
                holdOpen: false
            )
        )
        let model = GameDetailModel(
            game: snapshot.game,
            snapshotProvider: provider,
            stream: stream,
            recoveryPolicy: testPolicy,
            sleep: { _ in await Task.yield() }
        )

        let loadTask = Task { await model.load() }
        try await waitUntil { model.timeline.last?.sequence == 20 }
        let requestedSequences = await stream.sequences()

        XCTAssertEqual(requestedSequences, [4, 5])
        XCTAssertEqual(model.timeline.map(\.sequence), [4, 5, 6, 20])
        XCTAssertEqual(model.connectionState, .connected)

        loadTask.cancel()
        await model.disconnect()
        await loadTask.value
    }

    func testSelectingShotLoadsShotQualityContext() async throws {
        let snapshot = makeSnapshot(latestSequence: 4, timeline: [makePoint(sequence: 4)])
        let provider = ScriptedSnapshotProvider(initialSnapshot: snapshot)
        let shotQualityProvider = ScriptedShotQualityProvider(
            response: ShotQualityResponse(
                playerId: "unattributed-live-shot",
                definition: "Shooter-neutral expected field-goal probability.",
                modelVersion: "shot-quality-baseline-1.0",
                attempts: [
                    ShotQualityResult(
                        x: 1,
                        y: 3,
                        distanceFeet: 4.2,
                        angleDegrees: 18.0,
                        shotValue: 2,
                        makeProbability: 0.62,
                        expectedPoints: 1.24,
                        qualityLabel: "High"
                    )
                ]
            )
        )
        let stream = ScriptedGameStream(
            scripts: [],
            defaultScript: .init(envelopes: [], failure: nil, holdOpen: true)
        )
        let model = GameDetailModel(
            game: snapshot.game,
            snapshotProvider: provider,
            shotQualityProvider: shotQualityProvider,
            stream: stream,
            recoveryPolicy: testPolicy,
            sleep: { _ in await Task.yield() }
        )

        model.select(makePoint(sequence: 8))
        try await waitUntil { model.selectedShotQuality?.expectedPoints == 1.24 }
        let requests = await shotQualityProvider.requests()
        let attempt = try XCTUnwrap(requests.first?.attempts.first)

        XCTAssertEqual(requests.first?.playerID, "unattributed-live-shot")
        XCTAssertEqual(attempt.x, 1)
        XCTAssertEqual(attempt.y, 3)
        XCTAssertEqual(attempt.shotValue, 2)
        XCTAssertEqual(attempt.period, 4)
        XCTAssertEqual(attempt.gameClockSeconds, 192)
        XCTAssertEqual(attempt.scoreDifferential, 3)
        XCTAssertEqual(model.shotQualityState, .loaded)
        XCTAssertEqual(model.shotQualityModelVersion, "shot-quality-baseline-1.0")

        await model.disconnect()
    }

    func testSelectingNonShotDoesNotLoadShotQuality() async throws {
        let snapshot = makeSnapshot(latestSequence: 4, timeline: [makePoint(sequence: 4)])
        let provider = ScriptedSnapshotProvider(initialSnapshot: snapshot)
        let shotQualityProvider = ScriptedShotQualityProvider(
            response: ShotQualityResponse(
                playerId: "unattributed-live-shot",
                definition: "Shooter-neutral expected field-goal probability.",
                modelVersion: "shot-quality-baseline-1.0",
                attempts: []
            )
        )
        let stream = ScriptedGameStream(
            scripts: [],
            defaultScript: .init(envelopes: [], failure: nil, holdOpen: true)
        )
        let model = GameDetailModel(
            game: snapshot.game,
            snapshotProvider: provider,
            shotQualityProvider: shotQualityProvider,
            stream: stream,
            recoveryPolicy: testPolicy,
            sleep: { _ in await Task.yield() }
        )

        model.select(
            TimelinePoint(
                sequence: 9,
                period: 4,
                clockSeconds: 180,
                homeProbability: 0.64,
                description: "Turnover",
                eventType: "turnover",
                homeScore: 102,
                awayScore: 99,
                x: nil,
                y: nil,
                shotValue: nil
            )
        )
        try await Task.sleep(for: .milliseconds(10))
        let requests = await shotQualityProvider.requests()

        XCTAssertTrue(requests.isEmpty)
        XCTAssertEqual(model.shotQualityState, .unavailable)
        XCTAssertNil(model.selectedShotQuality)

        await model.disconnect()
    }

    func testPollingPreservesLastSnapshotWhenSourceIsUnavailable() async throws {
        let snapshot = makeSnapshot(
            latestSequence: 20,
            timeline: [makePoint(sequence: 20)]
        )
        let provider = ScriptedSnapshotProvider(
            initialSnapshot: snapshot,
            failAfterInitial: true
        )
        let failure = ScriptedGameStream.Script(
            envelopes: [],
            failure: RecoveryTestError.disconnected,
            holdOpen: false
        )
        let stream = ScriptedGameStream(scripts: [], defaultScript: failure)
        let model = GameDetailModel(
            game: snapshot.game,
            snapshotProvider: provider,
            stream: stream,
            recoveryPolicy: testPolicy,
            sleep: { _ in try await Task.sleep(for: .milliseconds(1)) }
        )

        let loadTask = Task { await model.load() }
        try await waitUntil {
            model.connectionState == .polling &&
                model.connectionMessage?.contains("last valid snapshot") == true
        }
        let requestedSequences = await stream.sequences()
        let snapshotCalls = await provider.calls()

        XCTAssertEqual(requestedSequences, [20, 20, 20])
        XCTAssertGreaterThanOrEqual(snapshotCalls, 2)
        XCTAssertEqual(model.timeline.map(\.sequence), [20])
        XCTAssertEqual(model.snapshot?.latestSequence, 20)

        loadTask.cancel()
        await model.disconnect()
        await loadTask.value
    }

    private var testPolicy: GameDetailRecoveryPolicy {
        GameDetailRecoveryPolicy(
            maxReconnectAttempts: 2,
            reconnectBaseMilliseconds: 0,
            maximumReconnectMilliseconds: 0,
            pollingIntervalMilliseconds: 1
        )
    }

    private func waitUntil(
        _ condition: @escaping @MainActor () -> Bool
    ) async throws {
        for _ in 0..<200 {
            if condition() {
                return
            }
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTFail("Timed out waiting for the recovery state")
    }

    private func makeSnapshot(
        latestSequence: Int,
        timeline: [TimelinePoint]
    ) -> LiveSnapshot {
        LiveSnapshot(
            game: makeGame(),
            timeline: timeline,
            latestSequence: latestSequence,
            sourceLabel: "Historical replay",
            isStale: false,
            freshnessSeconds: 8,
            liveModelVersion: "live-win-logistic-baseline-1.0",
            snapshotGeneratedAt: Date(timeIntervalSince1970: 1_750_000_000)
        )
    }

    private func makeGame() -> Game {
        Game(
            id: "game-1",
            scheduledAt: Date(timeIntervalSince1970: 1_750_000_000),
            homeTeam: Team(id: "bos", name: "Boston", abbreviation: "BOS"),
            awayTeam: Team(id: "nyk", name: "New York", abbreviation: "NYK"),
            homeScore: 102,
            awayScore: 99,
            period: 4,
            clockSeconds: 138,
            status: "replay",
            sourceStatus: .replay,
            lastIngestedAt: Date(timeIntervalSince1970: 1_750_000_000),
            prediction: nil
        )
    }

    private func makePoint(sequence: Int) -> TimelinePoint {
        TimelinePoint(
            sequence: sequence,
            period: 4,
            clockSeconds: max(0, 200 - sequence),
            homeProbability: 0.64,
            description: "Event \(sequence)",
            eventType: "shot_made",
            homeScore: 102,
            awayScore: 99,
            x: 1,
            y: 3,
            shotValue: 2
        )
    }

    private func makeEnvelope(sequence: Int) -> WebSocketEnvelope {
        WebSocketEnvelope(
            type: .playAdded,
            schemaVersion: "1.0",
            gameId: "game-1",
            sequence: sequence,
            occurredAt: Date(timeIntervalSince1970: 1_750_000_000),
            ingestedAt: Date(timeIntervalSince1970: 1_750_000_001),
            sourceStatus: .replay,
            modelVersion: "live-win-logistic-baseline-1.0",
            payload: PlayPayload(
                sequence: sequence,
                sourceEventId: "event-\(sequence)",
                revision: 1,
                eventType: "shot_made",
                description: "Event \(sequence)",
                period: 4,
                clockSeconds: max(0, 200 - sequence),
                homeScore: 102,
                awayScore: 99,
                possessionTeamId: "bos",
                homeFouls: 4,
                awayFouls: 5,
                x: 1,
                y: 3,
                shotValue: 2,
                homeProbability: 0.64
            )
        )
    }
}
