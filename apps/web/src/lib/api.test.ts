import { afterEach, describe, expect, it, vi } from "vitest";

import { fallbackGames, fallbackSnapshot } from "@/lib/fixtures";
import { fetchGames, fetchLiveSnapshot, startReplay } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("fetchGames", () => {
  it("requests fresh games and falls back when the API returns no games", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ games: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchGames(controller.signal)).resolves.toEqual(fallbackGames);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/games\?date=\d{4}-\d{2}-\d{2}$/),
      { cache: "no-store", signal: controller.signal },
    );
  });
});

describe("fetchLiveSnapshot", () => {
  it("requests authoritative live snapshots without browser caching", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(fallbackSnapshot), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchLiveSnapshot("cv-2026-bos-nyk", controller.signal),
    ).resolves.toEqual(fallbackSnapshot);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/games/cv-2026-bos-nyk/live",
      { cache: "no-store", signal: controller.signal },
    );
  });
});

describe("startReplay", () => {
  it("starts replay through the local proxy without browser caching", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "started" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(startReplay("cv-2026-bos-nyk")).resolves.toBe(true);

    expect(fetchMock).toHaveBeenCalledWith("/api/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gameId: "cv-2026-bos-nyk" }),
      cache: "no-store",
    });
  });

  it("returns false when replay start is rejected", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(startReplay("cv-2026-bos-nyk")).resolves.toBe(false);
  });

  it("returns false when the replay worker reports an existing run", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "already_running" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(startReplay("cv-2026-bos-nyk")).resolves.toBe(false);
  });
});
