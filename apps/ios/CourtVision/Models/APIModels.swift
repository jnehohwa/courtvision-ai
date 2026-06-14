import Foundation

enum SourceStatus: String, Codable {
    case replay
    case delayed
    case stale
    case unavailable
}

struct Team: Codable, Hashable, Identifiable {
    let id: String
    let name: String
    let abbreviation: String
}

struct Prediction: Codable, Hashable {
    let gameId: String
    let kind: String
    let homeProbability: Double
    let awayProbability: Double
    let modelVersion: String
    let predictedAt: Date
    let featureTimestamp: Date
    let confidence: String
}

struct Game: Codable, Hashable, Identifiable {
    let id: String
    let scheduledAt: Date
    let homeTeam: Team
    let awayTeam: Team
    let homeScore: Int
    let awayScore: Int
    let period: Int
    let clockSeconds: Int
    let status: String
    let sourceStatus: SourceStatus
    let lastIngestedAt: Date?
    let prediction: Prediction?
}

struct GamesResponse: Codable {
    let date: String
    let games: [Game]
}

struct TimelinePoint: Codable, Hashable, Identifiable {
    var id: Int { sequence }

    let sequence: Int
    let period: Int
    let clockSeconds: Int
    let homeProbability: Double
    let description: String
    let eventType: String
    let homeScore: Int
    let awayScore: Int
    let x: Double?
    let y: Double?
    let shotValue: Int?
}

struct LiveSnapshot: Codable {
    let game: Game
    let timeline: [TimelinePoint]
    let latestSequence: Int
    let sourceLabel: String
    let isStale: Bool
    let freshnessSeconds: Int?
    let liveModelVersion: String
    let snapshotGeneratedAt: Date
}

struct PlayPayload: Codable {
    let sequence: Int
    let sourceEventId: String
    let revision: Int
    let eventType: String
    let description: String
    let period: Int
    let clockSeconds: Int
    let homeScore: Int
    let awayScore: Int
    let possessionTeamId: String?
    let homeFouls: Int
    let awayFouls: Int
    let x: Double?
    let y: Double?
    let shotValue: Int?
    let homeProbability: Double

    var timelinePoint: TimelinePoint {
        TimelinePoint(
            sequence: sequence,
            period: period,
            clockSeconds: clockSeconds,
            homeProbability: homeProbability,
            description: description,
            eventType: eventType,
            homeScore: homeScore,
            awayScore: awayScore,
            x: x,
            y: y,
            shotValue: shotValue
        )
    }
}

struct WebSocketEnvelope: Codable {
    let type: String
    let schemaVersion: String
    let gameId: String
    let sequence: Int
    let occurredAt: Date
    let ingestedAt: Date
    let sourceStatus: SourceStatus
    let modelVersion: String?
    let payload: PlayPayload?
}
