import type {
  CourtVisionWebSocketEnvelope,
  PlayPayload as GeneratedPlayPayload,
  StatusPayload,
} from "@/generated/websocket-envelope";

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

export type PlayPayload = GeneratedPlayPayload;

export type WebSocketEnvelope =
  | (CourtVisionWebSocketEnvelope & {
      type: "play_added" | "play_corrected";
      payload: PlayPayload;
    })
  | (CourtVisionWebSocketEnvelope & {
      type: "source_status" | "heartbeat" | "replay_completed";
      payload: StatusPayload;
    })
  | (CourtVisionWebSocketEnvelope & {
      type: "snapshot" | "prediction_updated";
      payload: Record<string, unknown>;
    });
