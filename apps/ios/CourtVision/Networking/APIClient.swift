import Foundation

enum APIError: LocalizedError {
    case invalidResponse
    case server(Int)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            "The server returned an invalid response."
        case .server(let statusCode):
            "The server returned status \(statusCode)."
        }
    }
}

struct APIClient: Sendable {
    let baseURL: URL
    let session: URLSession

    init(
        baseURL: URL = APIClient.defaultBaseURL,
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.session = session
    }

    static var defaultBaseURL: URL {
        let configured = ProcessInfo.processInfo.environment["COURTVISION_API_URL"]
        return URL(string: configured ?? "http://127.0.0.1:8000")!
    }

    static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }

    func games(on date: Date = .now) async throws -> [Game] {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        let day = formatter.string(from: date)
        let response: GamesResponse = try await get("/api/v1/games?date=\(day)")
        return response.games
    }

    func liveSnapshot(gameID: String) async throws -> LiveSnapshot {
        try await get("/api/v1/games/\(gameID)/live")
    }

    func webSocketURL(gameID: String, after sequence: Int) -> URL {
        var components = URLComponents(
            url: baseURL.appending(path: "/ws/v1/games/\(gameID)"),
            resolvingAgainstBaseURL: false
        )!
        components.scheme = baseURL.scheme == "https" ? "wss" : "ws"
        components.queryItems = [URLQueryItem(name: "after_sequence", value: String(sequence))]
        return components.url!
    }

    private func get<Response: Decodable>(_ path: String) async throws -> Response {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIError.invalidResponse
        }
        let (data, response) = try await session.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard 200..<300 ~= httpResponse.statusCode else {
            throw APIError.server(httpResponse.statusCode)
        }
        return try APIClient.makeDecoder().decode(Response.self, from: data)
    }
}
