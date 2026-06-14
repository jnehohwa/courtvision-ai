import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const { gameId } = (await request.json()) as { gameId?: string };
  if (!gameId) {
    return NextResponse.json({ detail: "gameId is required" }, { status: 400 });
  }

  const baseUrl =
    process.env.COURTVISION_INTERNAL_API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000";
  const key = process.env.COURTVISION_INTERNAL_API_KEY ?? "local-development-key";

  try {
    const response = await fetch(`${baseUrl}/internal/replays/${gameId}/start`, {
      method: "POST",
      headers: { "X-Internal-Key": key },
      cache: "no-store",
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: "Replay service is unavailable" },
      { status: 503 },
    );
  }
}
