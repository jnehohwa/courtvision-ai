import { expect, test } from "@playwright/test";

const fullStack = process.env.COURTVISION_E2E_FULL_STACK === "1";

test("shows the dashboard and selects a shot", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Tonight's Games" })).toBeVisible();
  await expect(page.getByText("Boston vs New York")).toBeVisible();
  await page
    .getByRole("button", {
      name: "02:18 Q4 Tatum driving layup 102 – 99",
      exact: true,
    })
    .click();
  await expect(page.getByRole("status")).toContainText("Tatum driving layup");
});

test("streams a complete replay from FastAPI over WebSockets", async ({ page }) => {
  test.skip(!fullStack, "Full-stack services are not enabled");

  const liveResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/games/cv-2026-bos-nyk/live") &&
      response.status() === 200,
  );
  const websocketPromise = page.waitForEvent(
    "websocket",
    (websocket) => websocket.url().includes("/ws/v1/games/"),
  );

  await page.goto("/");

  const liveResponse = await liveResponsePromise;
  const liveSnapshot = (await liveResponse.json()) as {
    latest_sequence: number;
    live_model_version: string;
    source_label: string;
  };
  expect(liveSnapshot.latest_sequence).toBe(20);
  expect(liveSnapshot.source_label).toBe("Historical replay");
  expect(liveSnapshot.live_model_version).toBe(
    "live-win-logistic-baseline-1.0",
  );

  const websocket = await websocketPromise;
  expect(websocket.url()).toContain(
    "/ws/v1/games/cv-2026-bos-nyk?after_sequence=20",
  );
  const envelopeTypes: string[] = [];
  websocket.on("framereceived", ({ payload }) => {
    const envelope = JSON.parse(String(payload)) as { type?: string };
    if (envelope.type) envelopeTypes.push(envelope.type);
  });

  await expect(page.getByText("WebSocket connected")).toBeVisible();
  await page.getByRole("button", { name: "Start replay" }).click();

  await expect
    .poll(
      () => envelopeTypes.filter((eventType) => eventType === "play_added").length,
      { timeout: 10_000 },
    )
    .toBe(20);
  await expect
    .poll(() => envelopeTypes.includes("replay_completed"), {
      timeout: 10_000,
    })
    .toBe(true);
  await expect(page.locator('[data-sequence="20"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "Start replay" })).toBeEnabled();
});
