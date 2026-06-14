export type SourceStatus = "replay" | "delayed" | "stale" | "unavailable";

export interface Team {
  id: string;
  name: string;
  abbreviation: string;
}

export interface Prediction {
  game_id: string;
  kind: string;
  home_probability: number;
  away_probability: number;
  model_version: string;
  predicted_at: string;
  feature_timestamp: string;
  confidence: string;
}

export interface Game {
  id: string;
  scheduled_at: string;
  home_team: Team;
  away_team: Team;
  home_score: number;
  away_score: number;
  period: number;
  clock_seconds: number;
  status: string;
  source_status: SourceStatus;
  last_ingested_at: string | null;
  prediction: Prediction | null;
}

export interface TimelinePoint {
  sequence: number;
  period: number;
  clock_seconds: number;
  home_probability: number;
  description: string;
  event_type: string;
  home_score: number;
  away_score: number;
  x: number | null;
  y: number | null;
  shot_value: number | null;
}

export interface LiveSnapshot {
  game: Game;
  timeline: TimelinePoint[];
  latest_sequence: number;
  source_label: string;
  is_stale: boolean;
  freshness_seconds: number | null;
  live_model_version: string;
  snapshot_generated_at: string;
}

export interface PlayPayload {
  sequence: number;
  source_event_id: string;
  revision: number;
  event_type: string;
  description: string;
  period: number;
  clock_seconds: number;
  home_score: number;
  away_score: number;
  possession_team_id: string | null;
  home_fouls: number;
  away_fouls: number;
  x: number | null;
  y: number | null;
  shot_value: number | null;
  home_probability: number;
}

export interface WebSocketEnvelope {
  type:
    | "snapshot"
    | "play_added"
    | "play_corrected"
    | "prediction_updated"
    | "source_status"
    | "heartbeat"
    | "replay_completed";
  schema_version: "1.0";
  game_id: string;
  sequence: number;
  occurred_at: string;
  ingested_at: string;
  source_status: SourceStatus;
  model_version: string | null;
  payload: PlayPayload | Record<string, unknown>;
}
