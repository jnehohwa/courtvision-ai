import Foundation

enum SourceStatus: String, CaseIterable, Codable, Sendable {
    case replay
    case delayed
    case stale
    case unavailable
}

enum WebSocketEventType: String, CaseIterable, Codable, Sendable {
    case snapshot
    case playAdded = "play_added"
    case playCorrected = "play_corrected"
    case predictionUpdated = "prediction_updated"
    case sourceStatus = "source_status"
    case heartbeat
    case replayCompleted = "replay_completed"
}

struct Team: Codable, Hashable, Identifiable, Sendable {
    let id: String
    let name: String
    let abbreviation: String
}

struct Prediction: Codable, Hashable, Sendable {
    let gameId: String
    let kind: String
    let homeProbability: Double
    let awayProbability: Double
    let modelVersion: String
    let predictedAt: Date
    let featureTimestamp: Date
    let confidence: String
}

struct Game: Codable, Hashable, Identifiable, Sendable {
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

struct GamesResponse: Codable, Sendable {
    let date: String
    let games: [Game]
}

struct SourceHealth: Codable, Hashable, Sendable {
    let status: String
    let lastAttemptAt: Date?
    let lastSuccessAt: Date?
    let lastEventAt: Date?
    let lastError: String?
    let consecutiveFailures: Int
    let totalPolls: Int
    let totalEvents: Int
    let currentPollIntervalSeconds: Double?
    let updatedAt: Date
}

struct HealthResponse: Codable, Hashable, Sendable {
    let status: String
    let database: String
    let redis: String
    let latestIngestionAt: Date?
    let dataLagSeconds: Int?
    let delayedLiveEnabled: Bool
    let sources: [String: SourceHealth]
}

struct TimelinePoint: Codable, Hashable, Identifiable, Sendable {
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

struct LiveSnapshot: Codable, Sendable {
    let game: Game
    let timeline: [TimelinePoint]
    let latestSequence: Int
    let sourceLabel: String
    let isStale: Bool
    let freshnessSeconds: Int?
    let liveModelVersion: String
    let snapshotGeneratedAt: Date
}

struct ShotAttemptRequest: Codable, Hashable, Sendable {
    let x: Double
    let y: Double
    let shotValue: Int
    let period: Int
    let gameClockSeconds: Int
    let scoreDifferential: Int
}

struct ShotQualityRequest: Codable, Hashable, Sendable {
    let playerId: String
    let attempts: [ShotAttemptRequest]
}

struct ShotQualityResult: Codable, Hashable, Sendable {
    let x: Double
    let y: Double
    let distanceFeet: Double
    let angleDegrees: Double
    let shotValue: Int
    let makeProbability: Double
    let expectedPoints: Double
    let qualityLabel: String
}

struct ShotQualityResponse: Codable, Hashable, Sendable {
    let playerId: String
    let definition: String
    let modelVersion: String
    let attempts: [ShotQualityResult]
}

struct ReplayStartResponse: Codable, Hashable, Sendable {
    let gameId: String
    let status: String
    let eventCount: Int
}

struct PlayPayload: Codable, Sendable {
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

struct WebSocketEnvelope: Codable, Sendable {
    let type: WebSocketEventType
    let schemaVersion: String
    let gameId: String
    let sequence: Int
    let occurredAt: Date
    let ingestedAt: Date
    let sourceStatus: SourceStatus
    let modelVersion: String?
    let payload: PlayPayload?
}
