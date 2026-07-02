import { act, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useLiveGame } from "@/hooks/use-live-game";
import { fetchLiveSnapshot, startReplay } from "@/lib/api";
import { fallbackSnapshot } from "@/lib/fixtures";
import type { LiveSnapshot } from "@/types/api";

vi.mock("@/lib/api", () => ({
  fetchLiveSnapshot: vi.fn(),
  startReplay: vi.fn(),
}));

class MockWebSocket {
  static urls: string[] = [];
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onopen: (() => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.urls.push(url);
    queueMicrotask(() => this.onopen?.());
  }

  close() {
    this.onclose?.();
  }
}

function snapshotFor(gameId: string, latestSequence: number): LiveSnapshot {
  return {
    ...fallbackSnapshot,
    game: {
      ...fallbackSnapshot.game,
      id: gameId,
    },
    latest_sequence: latestSequence,
    timeline: fallbackSnapshot.timeline.slice(0, latestSequence),
  };
}

function Probe({ gameId }: { gameId: string }) {
  useLiveGame(gameId);
  return null;
}

describe("useLiveGame", () => {
  afterEach(() => {
    MockWebSocket.urls = [];
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("waits for the selected game's snapshot before opening its WebSocket", async () => {
    const pendingSnapshots = new Map<string, (snapshot: LiveSnapshot) => void>();
    vi.mocked(fetchLiveSnapshot).mockImplementation(
      (gameId) =>
        new Promise((resolve) => {
          pendingSnapshots.set(gameId, resolve);
        }),
    );
    vi.mocked(startReplay).mockResolvedValue(false);
    vi.stubGlobal("WebSocket", MockWebSocket);

    const { rerender } = render(<Probe gameId="cv-2026-bos-nyk" />);
    await waitFor(() => {
      expect(pendingSnapshots.has("cv-2026-bos-nyk")).toBe(true);
    });
    await act(async () => {
      pendingSnapshots.get("cv-2026-bos-nyk")?.(
        snapshotFor("cv-2026-bos-nyk", 16),
      );
    });

    await waitFor(() => {
      expect(MockWebSocket.urls).toEqual([
        "ws://localhost:8000/ws/v1/games/cv-2026-bos-nyk?after_sequence=16",
      ]);
    });

    rerender(<Probe gameId="cv-2026-den-phx" />);

    await waitFor(() => {
      expect(fetchLiveSnapshot).toHaveBeenCalledWith(
        "cv-2026-den-phx",
        expect.any(AbortSignal),
      );
    });
    expect(MockWebSocket.urls).toHaveLength(1);

    await act(async () => {
      pendingSnapshots.get("cv-2026-den-phx")?.(
        snapshotFor("cv-2026-den-phx", 3),
      );
    });

    await waitFor(() => {
      expect(MockWebSocket.urls).toEqual([
        "ws://localhost:8000/ws/v1/games/cv-2026-bos-nyk?after_sequence=16",
        "ws://localhost:8000/ws/v1/games/cv-2026-den-phx?after_sequence=3",
      ]);
    });
  });
});
