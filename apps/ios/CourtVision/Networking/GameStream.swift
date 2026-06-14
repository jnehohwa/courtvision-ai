import Foundation

actor GameStream {
    private let apiClient: APIClient
    private var task: URLSessionWebSocketTask?

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func messages(gameID: String, after sequence: Int) -> AsyncThrowingStream<WebSocketEnvelope, Error> {
        AsyncThrowingStream { continuation in
            let socket = apiClient.session.webSocketTask(
                with: apiClient.webSocketURL(gameID: gameID, after: sequence)
            )
            task = socket
            socket.resume()

            let receiveTask = Task {
                do {
                    while !Task.isCancelled {
                        let message = try await socket.receive()
                        let data: Data
                        switch message {
                        case .data(let value):
                            data = value
                        case .string(let value):
                            data = Data(value.utf8)
                        @unknown default:
                            continue
                        }
                        let envelope = try APIClient.makeDecoder().decode(
                            WebSocketEnvelope.self,
                            from: data
                        )
                        continuation.yield(envelope)
                    }
                } catch is CancellationError {
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                receiveTask.cancel()
                socket.cancel(with: .goingAway, reason: nil)
            }
        }
    }

    func disconnect() {
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
    }
}
