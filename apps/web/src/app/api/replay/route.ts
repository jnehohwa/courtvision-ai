import { NextRequest, NextResponse } from "next/server";

const DEVELOPMENT_INTERNAL_API_KEY = "local-development-key";
const LOCAL_INTERNAL_API_URL = "http://localhost:8000";
const MINIMUM_PRODUCTION_KEY_LENGTH = 32;

type ReplayProxyConfig =
  | {
      ok: true;
      baseUrl: string;
      key: string;
    }
  | {
      ok: false;
      detail: string;
    };

function replayJson(body: unknown, init: ResponseInit) {
  const response = NextResponse.json(body, init);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export function resolveReplayProxyConfig(
  env: NodeJS.ProcessEnv = process.env,
): ReplayProxyConfig {
  const isProduction = env.NODE_ENV === "production";
  const explicitBaseUrl = env.COURTVISION_INTERNAL_API_URL;
  const explicitKey = env.COURTVISION_INTERNAL_API_KEY;

  if (isProduction) {
    if (!explicitBaseUrl || !explicitKey) {
      return { ok: false, detail: "Replay service is not configured" };
    }

    if (
      explicitKey === DEVELOPMENT_INTERNAL_API_KEY ||
      explicitKey.length < MINIMUM_PRODUCTION_KEY_LENGTH
    ) {
      return { ok: false, detail: "Replay service is not configured" };
    }
  }

  const baseUrl =
    explicitBaseUrl ?? env.NEXT_PUBLIC_API_URL ?? LOCAL_INTERNAL_API_URL;
  const key = explicitKey ?? DEVELOPMENT_INTERNAL_API_KEY;

  return {
    ok: true,
    baseUrl: baseUrl.replace(/\/+$/, ""),
    key,
  };
}

export async function POST(request: NextRequest) {
  const { gameId } = (await request.json()) as { gameId?: string };
  if (!gameId) {
    return replayJson({ detail: "gameId is required" }, { status: 400 });
  }

  const config = resolveReplayProxyConfig();
  if (!config.ok) {
    return replayJson({ detail: config.detail }, { status: 503 });
  }

  try {
    const response = await fetch(
      `${config.baseUrl}/internal/replays/${gameId}/start`,
      {
        method: "POST",
        headers: { "X-Internal-Key": config.key },
        cache: "no-store",
      },
    );
    return replayJson(await response.json(), { status: response.status });
  } catch {
    return replayJson(
      { detail: "Replay service is unavailable" },
      { status: 503 },
    );
  }
}
