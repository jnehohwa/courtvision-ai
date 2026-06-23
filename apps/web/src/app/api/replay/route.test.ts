import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { POST, resolveReplayProxyConfig } from "./route";

const PRODUCTION_KEY = "courtvision-production-internal-key-123";

function replayRequest(body: unknown): NextRequest {
  return new Request("http://localhost/api/replay", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  }) as NextRequest;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("resolveReplayProxyConfig", () => {
  it("keeps local replay defaults outside production", () => {
    expect(resolveReplayProxyConfig({ NODE_ENV: "development" })).toEqual({
      ok: true,
      baseUrl: "http://localhost:8000",
      key: "local-development-key",
    });
  });

  it("requires explicit internal replay settings in production", () => {
    expect(resolveReplayProxyConfig({ NODE_ENV: "production" })).toEqual({
      ok: false,
      detail: "Replay service is not configured",
    });
  });

  it("rejects the development key in production", () => {
    expect(
      resolveReplayProxyConfig({
        NODE_ENV: "production",
        COURTVISION_INTERNAL_API_URL: "https://api.example.com",
        COURTVISION_INTERNAL_API_KEY: "local-development-key",
      }),
    ).toEqual({
      ok: false,
      detail: "Replay service is not configured",
    });
  });

  it("normalizes configured production URLs", () => {
    expect(
      resolveReplayProxyConfig({
        NODE_ENV: "production",
        COURTVISION_INTERNAL_API_URL: "https://api.example.com/",
        COURTVISION_INTERNAL_API_KEY: PRODUCTION_KEY,
      }),
    ).toEqual({
      ok: true,
      baseUrl: "https://api.example.com",
      key: PRODUCTION_KEY,
    });
  });
});

describe("POST", () => {
  it("rejects missing game ids before calling the replay service", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(replayRequest({}));

    expect(response.status).toBe(400);
    expect(response.headers.get("cache-control")).toBe("no-store");
    await expect(response.json()).resolves.toEqual({
      detail: "gameId is required",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns a clear 503 when the production replay bridge is unconfigured", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(replayRequest({ gameId: "cv-2026-bos-nyk" }));

    expect(response.status).toBe(503);
    expect(response.headers.get("cache-control")).toBe("no-store");
    await expect(response.json()).resolves.toEqual({
      detail: "Replay service is not configured",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards configured production replay requests with the internal key", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("COURTVISION_INTERNAL_API_URL", "https://api.example.com/");
    vi.stubEnv("COURTVISION_INTERNAL_API_KEY", PRODUCTION_KEY);

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ started: true }), {
        status: 202,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(replayRequest({ gameId: "cv-2026-bos-nyk" }));

    expect(response.status).toBe(202);
    expect(response.headers.get("cache-control")).toBe("no-store");
    await expect(response.json()).resolves.toEqual({ started: true });
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.com/internal/replays/cv-2026-bos-nyk/start",
      {
        method: "POST",
        headers: { "X-Internal-Key": PRODUCTION_KEY },
        cache: "no-store",
      },
    );
  });
});
