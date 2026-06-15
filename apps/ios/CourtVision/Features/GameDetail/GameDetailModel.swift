import Foundation
import Observation

protocol LiveSnapshotProviding: Sendable {
    func liveSnapshot(gameID: String) async throws -> LiveSnapshot
}

protocol GameEventStreaming: Actor {
    func messages(
        gameID: String,
        after sequence: Int
    ) -> AsyncThrowingStream<WebSocketEnvelope, Error>
    func disconnect()
}

extension APIClient: LiveSnapshotProviding {}

struct GameDetailRecoveryPolicy: Sendable {
    let maxReconnectAttempts: Int
    let reconnectBaseMilliseconds: Int
    let maximumReconnectMilliseconds: Int
    let pollingIntervalMilliseconds: Int

    static let standard = GameDetailRecoveryPolicy(
        maxReconnectAttempts: 4,
        reconnectBaseMilliseconds: 1_000,
        maximumReconnectMilliseconds: 10_000,
        pollingIntervalMilliseconds: 10_000
    )

    func reconnectDelay(for attempt: Int) -> Duration {
        let exponent = min(max(attempt, 1), 10)
        let multiplier = 1 << exponent
        return .milliseconds(
            min(reconnectBaseMilliseconds * multiplier, maximumReconnectMilliseconds)
        )
    }

    var pollingInterval: Duration {
        .milliseconds(pollingIntervalMilliseconds)
    }
}

@MainActor
@Observable
final class GameDetailModel {
    enum ConnectionState: String {
        case connecting
        case connected
        case polling
    }

    private let game: Game
    private let snapshotProvider: any LiveSnapshotProviding
    private let stream: any GameEventStreaming
    private let recoveryPolicy: GameDetailRecoveryPolicy
    private let sleep: @Sendable (Duration) async throws -> Void

    var snapshot: LiveSnapshot?
    var timeline: [TimelinePoint] = []
    var selectedPoint: TimelinePoint?
    var connectionState: ConnectionState = .connecting
    var errorMessage: String?
    var connectionMessage: String?
    var liveModelVersion = "Model unavailable"

    convenience init(game: Game, apiClient: APIClient) {
        self.init(
            game: game,
            snapshotProvider: apiClient,
            stream: GameStream(apiClient: apiClient)
        )
    }

    init(
        game: Game,
        snapshotProvider: any LiveSnapshotProviding,
        stream: any GameEventStreaming,
        recoveryPolicy: GameDetailRecoveryPolicy = .standard,
        sleep: @escaping @Sendable (Duration) async throws -> Void = {
            try await Task.sleep(for: $0)
        }
    ) {
        self.game = game
        self.snapshotProvider = snapshotProvider
        self.stream = stream
        self.recoveryPolicy = recoveryPolicy
        self.sleep = sleep
    }

    func load() async {
        do {
            let snapshot = try await snapshotProvider.liveSnapshot(gameID: game.id)
            apply(snapshot)
            await connect(after: snapshot.latestSequence)
        } catch is CancellationError {
            return
        } catch {
            errorMessage = error.localizedDescription
            await pollSnapshots()
        }
    }

    func connect(after sequence: Int) async {
        var resumeSequence = sequence
        var reconnectAttempt = 0

        while !Task.isCancelled {
            connectionState = .connecting
            do {
                connectionState = .connected
                errorMessage = nil
                for try await envelope in await stream.messages(
                    gameID: game.id,
                    after: resumeSequence
                ) {
                    reconnectAttempt = 0
                    connectionMessage = nil
                    if let modelVersion = envelope.modelVersion {
                        liveModelVersion = modelVersion
                    }
                    guard let point = envelope.payload?.timelinePoint else { continue }
                    timeline.removeAll { $0.sequence == point.sequence }
                    timeline.append(point)
                    timeline.sort { $0.sequence < $1.sequence }
                    selectedPoint = point
                    resumeSequence = max(resumeSequence, point.sequence)
                }
                reconnectAttempt += 1
            } catch is CancellationError {
                return
            } catch {
                reconnectAttempt += 1
            }

            if reconnectAttempt > recoveryPolicy.maxReconnectAttempts {
                await pollSnapshots()
                return
            }

            do {
                try await sleep(recoveryPolicy.reconnectDelay(for: reconnectAttempt))
            } catch is CancellationError {
                return
            } catch {
                errorMessage = error.localizedDescription
                return
            }
        }
    }

    private func pollSnapshots() async {
        connectionState = .polling
        connectionMessage = "Live updates are using snapshot polling."

        while !Task.isCancelled {
            do {
                let latest = try await snapshotProvider.liveSnapshot(gameID: game.id)
                apply(latest)
                errorMessage = nil
                connectionMessage = "Snapshot polling is active."
            } catch is CancellationError {
                return
            } catch {
                if snapshot == nil {
                    errorMessage = error.localizedDescription
                }
                connectionMessage = "The last valid snapshot is displayed while the source is unavailable."
            }

            do {
                try await sleep(recoveryPolicy.pollingInterval)
            } catch {
                return
            }
        }
    }

    private func apply(_ snapshot: LiveSnapshot) {
        self.snapshot = snapshot
        timeline = snapshot.timeline
        selectedPoint = snapshot.timeline.last
        liveModelVersion = snapshot.liveModelVersion
    }

    func select(_ point: TimelinePoint) {
        selectedPoint = point
    }

    func disconnect() async {
        await stream.disconnect()
    }
}
