import Foundation
import Observation

@MainActor
@Observable
final class GameDetailModel {
    enum ConnectionState: String {
        case connecting
        case connected
        case polling
    }

    private let game: Game
    private let apiClient: APIClient
    private let stream: GameStream

    var snapshot: LiveSnapshot?
    var timeline: [TimelinePoint] = []
    var selectedPoint: TimelinePoint?
    var connectionState: ConnectionState = .connecting
    var errorMessage: String?
    var liveModelVersion = "Model unavailable"

    init(game: Game, apiClient: APIClient) {
        self.game = game
        self.apiClient = apiClient
        stream = GameStream(apiClient: apiClient)
    }

    func load() async {
        do {
            let snapshot = try await apiClient.liveSnapshot(gameID: game.id)
            self.snapshot = snapshot
            timeline = snapshot.timeline
            selectedPoint = snapshot.timeline.last
            liveModelVersion = snapshot.liveModelVersion
            await connect(after: snapshot.latestSequence)
        } catch is CancellationError {
            return
        } catch {
            errorMessage = error.localizedDescription
            connectionState = .polling
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
                    if let modelVersion = envelope.modelVersion {
                        liveModelVersion = modelVersion
                    }
                    guard let point = envelope.payload?.timelinePoint else { continue }
                    timeline.removeAll { $0.sequence == point.sequence }
                    timeline.append(point)
                    timeline.sort { $0.sequence < $1.sequence }
                    selectedPoint = point
                    resumeSequence = max(resumeSequence, point.sequence)
                    reconnectAttempt = 0
                }
            } catch is CancellationError {
                return
            } catch {
                reconnectAttempt += 1
            }

            if reconnectAttempt > 4 {
                connectionState = .polling
                errorMessage = "Live updates are polling while the stream reconnects."
                do {
                    let latest = try await apiClient.liveSnapshot(gameID: game.id)
                    snapshot = latest
                    timeline = latest.timeline
                    selectedPoint = latest.timeline.last
                    liveModelVersion = latest.liveModelVersion
                    resumeSequence = latest.latestSequence
                    reconnectAttempt = 0
                } catch is CancellationError {
                    return
                } catch {
                    errorMessage = "The last valid snapshot is still displayed."
                }
            }

            let delaySeconds = min(pow(2.0, Double(max(reconnectAttempt, 1))), 10.0)
            do {
                try await Task.sleep(for: .seconds(delaySeconds))
            } catch {
                return
            }
        }
    }

    func select(_ point: TimelinePoint) {
        selectedPoint = point
    }

    func disconnect() async {
        await stream.disconnect()
    }
}
