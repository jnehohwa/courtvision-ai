import type { Game, LiveSnapshot, TimelinePoint } from "@/types/api";

const now = new Date();
const timestamp = now.toISOString();

function scheduledAt(hour: number, minute: number) {
  const value = new Date();
  value.setHours(hour, minute, 0, 0);
  return value.toISOString();
}

const timeline: TimelinePoint[] = [
  [1, 1, 690, 0.53, "Tatum driving layup", "shot_made", 2, 0, -3, 4, 2],
  [2, 1, 615, 0.47, "Brunson pull-up 3", "shot_made", 2, 3, 8, 23, 3],
  [3, 1, 484, 0.61, "Boston transition 3", "shot_made", 8, 5, -17, 18, 3],
  [4, 2, 641, 0.65, "Tatum wing 3", "shot_made", 28, 25, -20, 16, 3],
  [5, 2, 502, 0.52, "Brunson 24 ft step-back 3", "shot_made", 31, 31, 11, 22, 3],
  [6, 2, 271, 0.59, "Turnover", "turnover", 42, 38, null, null, null],
  [7, 3, 628, 0.68, "Tatum driving layup", "shot_made", 56, 52, 1, 5, 2],
  [8, 3, 443, 0.55, "New York above-break 3", "shot_made", 61, 60, 5, 25, 3],
  [9, 3, 210, 0.75, "Boston steal and dunk", "shot_made", 72, 68, 0, 2, 2],
  [10, 4, 528, 0.5, "Brunson 24 ft step-back 3", "shot_made", 86, 86, 9, 23, 3],
  [11, 4, 401, 0.67, "Boston driving layup", "shot_made", 91, 88, -2, 5, 2],
  [12, 4, 310, 0.46, "New York corner 3", "shot_made", 94, 94, 22, 4, 3],
  [13, 4, 231, 0.64, "Tatum driving layup", "shot_made", 98, 96, 3, 4, 2],
  [14, 4, 181, 0.45, "Brunson 24 ft step-back 3", "shot_made", 100, 99, 12, 21, 3],
  [15, 4, 154, 0.52, "Turnover", "turnover", 100, 99, null, null, null],
  [16, 4, 138, 0.64, "Tatum driving layup", "shot_made", 102, 99, -2, 4, 2],
].map(
  ([
    sequence,
    period,
    clock_seconds,
    home_probability,
    description,
    event_type,
    home_score,
    away_score,
    x,
    y,
    shot_value,
  ]) => ({
    sequence: sequence as number,
    period: period as number,
    clock_seconds: clock_seconds as number,
    home_probability: home_probability as number,
    description: description as string,
    event_type: event_type as string,
    home_score: home_score as number,
    away_score: away_score as number,
    x: x as number | null,
    y: y as number | null,
    shot_value: shot_value as number | null,
  }),
);

const game = (
  id: string,
  home: string,
  away: string,
  probability: number,
  scheduledHour: number,
  status = "scheduled",
): Game => ({
  id,
  scheduled_at: scheduledAt(scheduledHour, 30),
  home_team: { id: home.toLowerCase(), name: home, abbreviation: home.slice(0, 3) },
  away_team: { id: away.toLowerCase(), name: away, abbreviation: away.slice(0, 3) },
  home_score: id.includes("bos") ? 102 : 0,
  away_score: id.includes("bos") ? 99 : 0,
  period: id.includes("bos") ? 4 : 0,
  clock_seconds: id.includes("bos") ? 138 : 2880,
  status,
  source_status: "replay",
  last_ingested_at: timestamp,
  prediction: {
    game_id: id,
    kind: "pregame",
    home_probability: probability,
    away_probability: 1 - probability,
    model_version: "pregame-logistic-baseline-1.0",
    predicted_at: timestamp,
    feature_timestamp: timestamp,
    confidence: "calibrated baseline",
  },
});

export const fallbackGames = [
  game("cv-2026-bos-nyk", "Boston", "New York", 0.58, 18, "replay"),
  game("cv-2026-den-phx", "Denver", "Phoenix", 0.67, 20),
  game("cv-2026-min-dal", "Minnesota", "Dallas", 0.54, 21),
];

export const fallbackSnapshot: LiveSnapshot = {
  game: fallbackGames[0],
  timeline,
  latest_sequence: timeline.at(-1)?.sequence ?? 0,
  source_label: "Historical replay",
  is_stale: false,
  freshness_seconds: 8,
  live_model_version: "live-win-logistic-baseline-1.0",
  snapshot_generated_at: timestamp,
};
