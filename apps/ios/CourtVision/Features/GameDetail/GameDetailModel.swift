import Foundation
import Observation

protocol LiveSnapshotProviding: Sendable {
    func liveSnapshot(gameID: String) async throws -> LiveSnapshot
}

protocol ShotQualityProviding: Sendable {
    func shotQuality(
        playerID: String,
        attempts: [ShotAttemptRequest]
    ) async throws -> ShotQualityResponse
}

protocol GameEventStreaming: Actor {
    func messages(
        gameID: String,
        after sequence: Int
    ) -> AsyncThrowingStream<WebSocketEnvelope, Error>
    func disconnect()
}

extension APIClient: LiveSnapshotProviding {}
extension APIClient: ShotQualityProviding {}

enum ShotQualityLoadState: String, Equatable {
    case unavailable
    case loading
    case loaded
    case failed
}

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
    private let shotQualityProvider: (any ShotQualityProviding)?
    private let stream: any GameEventStreaming
    private let recoveryPolicy: GameDetailRecoveryPolicy
    private let sleep: @Sendable (Duration) async throws -> Void
    @ObservationIgnored private var shotQualityTask: Task<Void, Never>?
    private var shotQualitySequence: Int?

    var snapshot: LiveSnapshot?
    var timeline: [TimelinePoint] = []
    var selectedPoint: TimelinePoint?
    var selectedShotQuality: ShotQualityResult?
    var shotQualityState: ShotQualityLoadState = .unavailable
    var shotQualityMessage: String?
    var shotQualityModelVersion = "Shot quality unavailable"
    var connectionState: ConnectionState = .connecting
    var errorMessage: String?
    var connectionMessage: String?
    var liveModelVersion = "Model unavailable"

    convenience init(game: Game, apiClient: APIClient) {
        self.init(
            game: game,
            snapshotProvider: apiClient,
            shotQualityProvider: apiClient,
            stream: GameStream(apiClient: apiClient)
        )
    }

    init(
        game: Game,
        snapshotProvider: any LiveSnapshotProviding,
        shotQualityProvider: (any ShotQualityProviding)? = nil,
        stream: any GameEventStreaming,
        recoveryPolicy: GameDetailRecoveryPolicy = .standard,
        sleep: @escaping @Sendable (Duration) async throws -> Void = {
            try await Task.sleep(for: $0)
        }
    ) {
        self.game = game
        self.snapshotProvider = snapshotProvider
        self.shotQualityProvider = shotQualityProvider
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
                    select(point)
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
        if let latestPoint = snapshot.timeline.last {
            select(latestPoint)
        } else {
            select(nil)
        }
        liveModelVersion = snapshot.liveModelVersion
    }

    func select(_ point: TimelinePoint) {
        select(Optional(point))
    }

    private func select(_ point: TimelinePoint?) {
        selectedPoint = point
        guard let point else {
            resetShotQuality()
            return
        }
        loadShotQualityIfNeeded(for: point)
    }

    private func loadShotQualityIfNeeded(for point: TimelinePoint) {
        guard let provider = shotQualityProvider else {
            resetShotQuality()
            return
        }
        guard let attempt = shotQualityAttempt(for: point) else {
            resetShotQuality()
            return
        }
        if shotQualitySequence == point.sequence && shotQualityState == .loaded {
            return
        }

        shotQualityTask?.cancel()
        shotQualitySequence = point.sequence
        selectedShotQuality = nil
        shotQualityState = .loading
        shotQualityMessage = "Calculating shooter-neutral shot quality..."
        shotQualityModelVersion = "Loading shot-quality model"

        shotQualityTask = Task { [weak self] in
            do {
                let response = try await provider.shotQuality(
                    playerID: "unattributed-live-shot",
                    attempts: [attempt]
                )
                guard !Task.isCancelled else { return }
                self?.applyShotQuality(response, for: point.sequence)
            } catch is CancellationError {
                return
            } catch {
                guard !Task.isCancelled else { return }
                self?.applyShotQualityFailure(error, for: point.sequence)
            }
        }
    }

    private func shotQualityAttempt(for point: TimelinePoint) -> ShotAttemptRequest? {
        guard let x = point.x,
              let y = point.y,
              let shotValue = point.shotValue
        else {
            return nil
        }
        return ShotAttemptRequest(
            x: x,
            y: y,
            shotValue: shotValue,
            period: point.period,
            gameClockSeconds: point.clockSeconds,
            scoreDifferential: point.homeScore - point.awayScore
        )
    }

    private func resetShotQuality() {
        shotQualityTask?.cancel()
        shotQualityTask = nil
        shotQualitySequence = nil
        selectedShotQuality = nil
        shotQualityState = .unavailable
        shotQualityMessage = "Select a shot with coordinates to calculate shooter-neutral quality."
        shotQualityModelVersion = "Shot quality unavailable"
    }

    private func applyShotQuality(_ response: ShotQualityResponse, for sequence: Int) {
        guard selectedPoint?.sequence == sequence else { return }
        selectedShotQuality = response.attempts.first
        shotQualityState = response.attempts.isEmpty ? .unavailable : .loaded
        shotQualityMessage = response.definition
        shotQualityModelVersion = response.modelVersion
    }

    private func applyShotQualityFailure(_ error: Error, for sequence: Int) {
        guard selectedPoint?.sequence == sequence else { return }
        selectedShotQuality = nil
        shotQualityState = .failed
        shotQualityMessage = "Shot quality is temporarily unavailable: \(error.localizedDescription)"
        shotQualityModelVersion = "Shot quality unavailable"
    }

    func disconnect() async {
        shotQualityTask?.cancel()
        await stream.disconnect()
    }
}
