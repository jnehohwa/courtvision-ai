import { fallbackGames } from "@/lib/fixtures";
import type { Game, LiveSnapshot } from "@/types/api";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchGames(signal?: AbortSignal): Promise<Game[]> {
  try {
    const date = new Date().toISOString().slice(0, 10);
    const response = await fetch(`${apiUrl}/api/v1/games?date=${date}`, {
      cache: "no-store",
      signal,
    });
    if (!response.ok) throw new Error("Games request failed");
    const payload = (await response.json()) as { games: Game[] };
    return payload.games.length ? payload.games : fallbackGames;
  } catch (error) {
    if (signal?.aborted) throw error;
    return fallbackGames;
  }
}

export async function fetchLiveSnapshot(
  gameId: string,
  signal?: AbortSignal,
): Promise<LiveSnapshot> {
  const response = await fetch(`${apiUrl}/api/v1/games/${gameId}/live`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw new Error("Live snapshot request failed");
  return (await response.json()) as LiveSnapshot;
}

export async function startReplay(gameId: string): Promise<boolean> {
  const response = await fetch("/api/replay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ gameId }),
    cache: "no-store",
  });
  if (!response.ok) return false;
  const payload = (await response.json()) as { status?: string };
  return payload.status === "started";
}
