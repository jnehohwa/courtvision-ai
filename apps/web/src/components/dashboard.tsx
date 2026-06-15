"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, ChevronRight } from "lucide-react";
import { CourtMap } from "@/components/court-map";
import { ProbabilityChart } from "@/components/probability-chart";
import { ReplayControls } from "@/components/replay-controls";
import { useLiveGame } from "@/hooks/use-live-game";
import { fetchGames } from "@/lib/api";
import { fallbackGames } from "@/lib/fixtures";
import type { Game, TimelinePoint } from "@/types/api";

function formatClock(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function formatFreshness(
  sourceLabel: string | undefined,
  isStale: boolean | undefined,
  freshnessSeconds: number | null | undefined,
) {
  if (sourceLabel === "Historical replay") return "Replay fixture";
  if (freshnessSeconds === null || freshnessSeconds === undefined) {
    return isStale ? "Source unavailable" : "Freshness unknown";
  }
  const age =
    freshnessSeconds < 60
      ? `${freshnessSeconds}s`
      : `${Math.floor(freshnessSeconds / 60)}m`;
  return `${isStale ? "Stale" : "Source updated"} · ${age} ago`;
}

function ProbabilityBar({ home }: { home: number }) {
  return (
    <div className="probability-bar" aria-label={`${Math.round(home * 100)} percent home win probability`}>
      <span className="home-fill" style={{ width: `${home * 100}%` }} />
      <i style={{ left: `${home * 100}%` }} />
      <small>{Math.round(home * 100)}%</small>
      <small>{Math.round((1 - home) * 100)}%</small>
    </div>
  );
}

export function Dashboard() {
  const [games, setGames] = useState<Game[]>(fallbackGames);
  const [selectedGameId, setSelectedGameId] = useState(fallbackGames[0].id);
  const [selectedSequence, setSelectedSequence] = useState<number>();
  const {
    snapshot,
    timeline,
    connectionState,
    isReplaying,
    liveModelVersion,
    startReplay,
  } = useLiveGame(selectedGameId);

  useEffect(() => {
    const controller = new AbortController();
    void fetchGames(controller.signal).then(setGames).catch(() => {
      // Development remounts intentionally cancel the first request.
    });
    return () => controller.abort();
  }, []);

  const game = snapshot?.game ?? games.find((item) => item.id === selectedGameId) ?? games[0];
  const selectedPoint =
    timeline.find((point) => point.sequence === selectedSequence) ?? timeline.at(-1);
  const homeProbability =
    selectedPoint?.home_probability ?? game.prediction?.home_probability ?? 0.5;
  const visibleEvents = useMemo(() => timeline.slice(-6).reverse(), [timeline]);
  const progress = timeline.length / Math.max(snapshot?.timeline.length ?? timeline.length, 1);
  const connectionLabel =
    connectionState === "connected"
      ? "WebSocket connected"
      : connectionState === "polling"
        ? "Polling fallback"
        : "WebSocket connecting";

  const selectPoint = (point: TimelinePoint) => setSelectedSequence(point.sequence);

  return (
    <main>
      <header className="app-header">
        <a href="#" className="brand" aria-label="CourtVision AI home">
          CourtVision <span>AI</span>
        </a>
        <nav aria-label="Primary navigation">
          <a className="active" href="#games">Games</a>
          <a href="#models">Models</a>
          <a href="#about">About</a>
        </nav>
        <div className="freshness">
          {formatFreshness(
            snapshot?.source_label,
            snapshot?.is_stale,
            snapshot?.freshness_seconds,
          )}
          <span
            className={
              connectionState === "connected" && !snapshot?.is_stale
                ? "online"
                : "degraded"
            }
          />
        </div>
      </header>

      <div className="shell" id="games">
        <h1>Tonight&apos;s Games</h1>
        <section className="game-grid">
          <article className="score-panel">
            <div className="live-label">
              <span />
              {snapshot?.source_label ?? "Historical replay"}
            </div>
            <h2>{game.home_team.name} vs {game.away_team.name}</h2>
            <div className="scoreboard">
              <div>
                <span className="home-accent">{game.home_team.name}</span>
                <strong>{selectedPoint?.home_score ?? game.home_score}</strong>
              </div>
              <div className="clock">
                <b>Q{selectedPoint?.period ?? game.period} {formatClock(selectedPoint?.clock_seconds ?? game.clock_seconds)}</b>
                <small>QTR</small>
                <span>{selectedPoint?.period ?? game.period}</span>
              </div>
              <div>
                <span className="away-accent">{game.away_team.name}</span>
                <strong>{selectedPoint?.away_score ?? game.away_score}</strong>
              </div>
            </div>
            <div className="probability-summary">
              <div>
                <small>Home Win Probability</small>
                <strong>{Math.round(homeProbability * 100)}%</strong>
              </div>
              <ProbabilityBar home={homeProbability} />
              <dl>
                <div><dt>Data source</dt><dd>{snapshot?.source_label ?? "Historical replay"}</dd></div>
                <div><dt>Model</dt><dd>{liveModelVersion ?? "Model unavailable"}</dd></div>
              </dl>
            </div>
            <div className="chart-heading">
              <h3>Win Probability Over Time</h3>
              <span>{connectionLabel}</span>
            </div>
            <ProbabilityChart points={timeline} activeSequence={selectedPoint?.sequence} />
          </article>

          <article className="court-panel">
            <div className="panel-heading">
              <h3>Shot Map <span>(All Players)</span></h3>
              <div className="legend"><span className="made" /> Made <span className="missed" /> Missed</div>
            </div>
            <CourtMap
              points={timeline}
              selectedSequence={selectedPoint?.sequence}
              onSelect={selectPoint}
            />
            {selectedPoint?.x !== null && selectedPoint?.x !== undefined ? (
              <div className="shot-detail" role="status">
                <strong>{selectedPoint.description}</strong>
                <span>
                  Q{selectedPoint.period} {formatClock(selectedPoint.clock_seconds)} ·{" "}
                  {selectedPoint.shot_value}-point attempt
                </span>
              </div>
            ) : null}
          </article>
        </section>

        <section className="momentum-panel">
          <div className="panel-heading">
            <h3>Momentum <span>({isReplaying ? "Replay" : "Latest"})</span></h3>
          </div>
          <div className="event-rail">
            {visibleEvents.map((point) => (
              <button
                type="button"
                className={point.sequence === selectedPoint?.sequence ? "selected" : ""}
                key={point.sequence}
                data-sequence={point.sequence}
                onClick={() => selectPoint(point)}
              >
                <span>{formatClock(point.clock_seconds)}<small>Q{point.period}</small></span>
                <strong>{point.description}</strong>
                <em>{point.home_score} – {point.away_score}</em>
              </button>
            ))}
          </div>
          <ReplayControls
            isReplaying={isReplaying}
            progress={Math.min(progress, 1)}
            onStart={() => void startReplay()}
          />
        </section>

        <section className="upcoming">
          <h2>Upcoming Games</h2>
          <div className="upcoming-head" aria-hidden="true">
            <span>Tip-off</span><span>Home win probability</span><span>Data source</span><span>Model</span>
          </div>
          {games.slice(1).map((upcomingGame) => {
            const probability = upcomingGame.prediction?.home_probability ?? 0.5;
            return (
              <button
                type="button"
                className="game-row"
                key={upcomingGame.id}
                onClick={() => setSelectedGameId(upcomingGame.id)}
              >
                <time>
                  {new Date(upcomingGame.scheduled_at).toLocaleTimeString([], {
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                </time>
                <strong>{upcomingGame.home_team.name} vs {upcomingGame.away_team.name}</strong>
                <ProbabilityBar home={probability} />
                <span>Historical replay</span>
                <span>{upcomingGame.prediction?.model_version ?? "Unavailable"}</span>
                <ChevronRight size={18} />
              </button>
            );
          })}
        </section>
      </div>

      <footer id="about">
        <span><Activity size={14} /> Predictions are model estimates, not guarantees.</span>
        <span>Portfolio build · Synthetic replay fixtures</span>
      </footer>
    </main>
  );
}
