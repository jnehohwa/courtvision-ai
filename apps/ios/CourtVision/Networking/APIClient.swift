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
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)
            if let date = Self.parseISO8601(value) {
                return date
            }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Invalid ISO-8601 timestamp: \(value)"
            )
        }
        return decoder
    }

    static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }

    private static func parseISO8601(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) {
            return date
        }

        let wholeSecond = ISO8601DateFormatter()
        wholeSecond.formatOptions = [.withInternetDateTime]
        return wholeSecond.date(from: value)
    }

    func games(on date: Date = .now) async throws -> [Game] {
        let day = Self.apiDateString(from: date)
        let response: GamesResponse = try await get("/api/v1/games?date=\(day)")
        return response.games
    }

    static func apiDateString(from date: Date) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    func health() async throws -> HealthResponse {
        try await get("/health")
    }

    func game(gameID: String) async throws -> Game {
        try await get("/api/v1/games/\(gameID)")
    }

    func liveSnapshot(gameID: String) async throws -> LiveSnapshot {
        try await get("/api/v1/games/\(gameID)/live")
    }

    func prediction(gameID: String) async throws -> Prediction {
        try await get("/api/v1/games/\(gameID)/prediction")
    }

    func shotQuality(
        playerID: String,
        attempts: [ShotAttemptRequest]
    ) async throws -> ShotQualityResponse {
        try await post(
            "/api/v1/shot-quality",
            body: ShotQualityRequest(playerId: playerID, attempts: attempts)
        )
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
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        return try await send(request)
    }

    private func post<Request: Encodable, Response: Decodable>(
        _ path: String,
        body: Request
    ) async throws -> Response {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIError.invalidResponse
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try APIClient.makeEncoder().encode(body)
        return try await send(request)
    }

    private func send<Response: Decodable>(_ request: URLRequest) async throws -> Response {
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard 200..<300 ~= httpResponse.statusCode else {
            throw APIError.server(httpResponse.statusCode)
        }
        return try APIClient.makeDecoder().decode(Response.self, from: data)
    }
}
