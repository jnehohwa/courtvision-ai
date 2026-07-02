"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchLiveSnapshot, startReplay as startReplayRequest } from "@/lib/api";
import { fallbackSnapshot } from "@/lib/fixtures";
import type {
  LiveSnapshot,
  PlayPayload,
  TimelinePoint,
  WebSocketEnvelope,
} from "@/types/api";

const wsBaseUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

function positiveInteger(value: string | undefined, fallback: number) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

const reconnectBaseDelayMs = positiveInteger(
  process.env.NEXT_PUBLIC_WS_RECONNECT_BASE_MS,
  1000,
);
const maxReconnectAttempts = positiveInteger(
  process.env.NEXT_PUBLIC_WS_MAX_RECONNECT_ATTEMPTS,
  4,
);
const pollIntervalMs = positiveInteger(
  process.env.NEXT_PUBLIC_LIVE_POLL_INTERVAL_MS,
  10_000,
);

function toTimelinePoint(payload: PlayPayload): TimelinePoint {
  return {
    sequence: payload.sequence,
    period: payload.period,
    clock_seconds: payload.clock_seconds,
    home_probability: payload.home_probability,
    description: payload.description,
    event_type: payload.event_type,
    home_score: payload.home_score,
    away_score: payload.away_score,
    x: payload.x,
    y: payload.y,
    shot_value: payload.shot_value,
  };
}

export function useLiveGame(gameId: string) {
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [connectionState, setConnectionState] = useState<
    "connecting" | "connected" | "polling"
  >("connecting");
  const [isReplaying, setIsReplaying] = useState(false);
  const [liveModelVersion, setLiveModelVersion] = useState<string>();
  const reconnectAttempt = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);
  const lastSeenSequence = useRef(-1);
  const snapshotReady = snapshot?.game.id === gameId;
  const visibleSnapshot = snapshotReady ? snapshot : null;
  const visibleTimeline = snapshotReady ? timeline : [];
  const visibleIsReplaying = snapshotReady && isReplaying;
  const visibleLiveModelVersion = snapshotReady ? liveModelVersion : undefined;

  useEffect(() => {
    const controller = new AbortController();
    lastSeenSequence.current = -1;
    void fetchLiveSnapshot(gameId, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setSnapshot(value);
        setTimeline(value.timeline);
        setLiveModelVersion(value.live_model_version);
        lastSeenSequence.current = value.latest_sequence;
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        const fallback = {
          ...fallbackSnapshot,
          game: { ...fallbackSnapshot.game, id: gameId },
        };
        setSnapshot(fallback);
        setTimeline(fallback.timeline);
        setLiveModelVersion(fallback.live_model_version);
        lastSeenSequence.current = fallback.latest_sequence;
      });
    return () => controller.abort();
  }, [gameId]);

  useEffect(() => {
    if (!snapshotReady) return;

    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const socket = new WebSocket(
        `${wsBaseUrl}/ws/v1/games/${gameId}?after_sequence=${lastSeenSequence.current}`,
      );
      socketRef.current = socket;
      setConnectionState("connecting");

      socket.onopen = () => {
        setConnectionState("connected");
      };
      socket.onmessage = (event) => {
        const envelope = JSON.parse(event.data) as WebSocketEnvelope;
        reconnectAttempt.current = 0;
        if (envelope.model_version) {
          setLiveModelVersion(envelope.model_version);
        }
        if (
          envelope.type === "source_status" &&
          "status" in envelope.payload &&
          envelope.payload.status === "replay_started"
        ) {
          lastSeenSequence.current = 0;
          setTimeline([]);
          setIsReplaying(true);
          return;
        }
        if (envelope.type === "replay_completed") {
          setIsReplaying(false);
          return;
        }
        if (envelope.type !== "play_added" && envelope.type !== "play_corrected") {
          return;
        }
        const point = toTimelinePoint(envelope.payload);
        lastSeenSequence.current = Math.max(lastSeenSequence.current, point.sequence);
        setTimeline((current) => {
          const withoutRevision = current.filter(
            (candidate) => candidate.sequence !== point.sequence,
          );
          return [...withoutRevision, point].sort(
            (left, right) => left.sequence - right.sequence,
          );
        });
      };
      socket.onclose = () => {
        if (disposed) return;
        reconnectAttempt.current += 1;
        if (reconnectAttempt.current > maxReconnectAttempts) {
          setConnectionState("polling");
          return;
        }
        setConnectionState("connecting");
        const delay = Math.min(
          reconnectBaseDelayMs * 2 ** reconnectAttempt.current,
          10_000,
        );
        reconnectTimer = setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socketRef.current?.close();
    };
  }, [gameId, snapshotReady]);

  useEffect(() => {
    if (connectionState !== "polling") return;
    let disposed = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const value = await fetchLiveSnapshot(gameId);
        if (disposed) return;
        setSnapshot(value);
        setLiveModelVersion(value.live_model_version);
        lastSeenSequence.current = value.latest_sequence;
        if (!isReplaying) setTimeline(value.timeline);
      } catch {
        // Preserve the last valid snapshot and retry on the next polling tick.
      } finally {
        if (!disposed) {
          pollTimer = setTimeout(poll, pollIntervalMs);
        }
      }
    };

    void poll();
    return () => {
      disposed = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [connectionState, gameId, isReplaying]);

  const startReplay = useCallback(async () => {
    if (!visibleSnapshot) return;
    setIsReplaying(true);
    try {
      const replayStarted = await startReplayRequest(gameId);
      if (replayStarted) return;
    } catch {
      // Restore the last valid timeline if the local replay bridge is unavailable.
    }
    setIsReplaying(false);
    setTimeline(visibleSnapshot.timeline);
  }, [gameId, visibleSnapshot]);

  return {
    snapshot: visibleSnapshot,
    timeline: visibleTimeline,
    connectionState,
    isReplaying: visibleIsReplaying,
    liveModelVersion: visibleLiveModelVersion,
    startReplay,
  };
}
