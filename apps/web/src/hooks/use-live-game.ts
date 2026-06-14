"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchLiveSnapshot } from "@/lib/api";
import type {
  LiveSnapshot,
  PlayPayload,
  TimelinePoint,
  WebSocketEnvelope,
} from "@/types/api";

const wsBaseUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

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
  const snapshotReady = snapshot !== null;

  useEffect(() => {
    const controller = new AbortController();
    void fetchLiveSnapshot(gameId, controller.signal)
      .then((value) => {
        setSnapshot(value);
        setTimeline(value.timeline);
        setLiveModelVersion(value.live_model_version);
        lastSeenSequence.current = value.latest_sequence;
      })
      .catch(() => {
        // Development remounts intentionally cancel the first request.
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
        reconnectAttempt.current = 0;
        setConnectionState("connected");
      };
      socket.onmessage = (event) => {
        const envelope = JSON.parse(event.data) as WebSocketEnvelope;
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
        const point = toTimelinePoint(envelope.payload as PlayPayload);
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
        if (reconnectAttempt.current > 4) {
          setConnectionState("polling");
          return;
        }
        const delay = Math.min(1000 * 2 ** reconnectAttempt.current, 10_000);
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
    const interval = setInterval(() => {
      void fetchLiveSnapshot(gameId).then((value) => {
        setSnapshot(value);
        setLiveModelVersion(value.live_model_version);
        lastSeenSequence.current = value.latest_sequence;
        if (!isReplaying) setTimeline(value.timeline);
      });
    }, 10_000);
    return () => clearInterval(interval);
  }, [connectionState, gameId, isReplaying]);

  const startReplay = useCallback(async () => {
    setIsReplaying(true);
    const response = await fetch("/api/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gameId }),
    });
    if (!response.ok) {
      setIsReplaying(false);
      setTimeline(snapshot?.timeline ?? []);
    }
  }, [gameId, snapshot]);

  return {
    snapshot,
    timeline,
    connectionState,
    isReplaying,
    liveModelVersion,
    startReplay,
  };
}
