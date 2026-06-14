import { defineConfig, devices } from "@playwright/test";

const browserChannel = process.env.PLAYWRIGHT_CHANNEL;
const browserName = process.env.PLAYWRIGHT_BROWSER;
const channelOverride = browserChannel
  ? { browserName: "chromium" as const, channel: browserChannel }
  : browserName === "chromium"
    ? { browserName: "chromium" as const }
  : {};
const fullStack = process.env.COURTVISION_E2E_FULL_STACK === "1";
const apiCommand =
  process.env.COURTVISION_E2E_API_COMMAND ??
  "../../.venv/bin/python -m courtvision.e2e_server";
const nextCommand = "./node_modules/.bin/next dev --hostname 127.0.0.1";

export default defineConfig({
  testDir: "./e2e",
  workers: fullStack ? 1 : undefined,
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  webServer: fullStack
    ? [
        {
          command: apiCommand,
          cwd: "../api",
          url: "http://127.0.0.1:8000/health",
          reuseExistingServer: false,
          env: {
            ...process.env,
            COURTVISION_ENVIRONMENT: "e2e",
            COURTVISION_DATABASE_URL:
              "sqlite+aiosqlite:////tmp/courtvision-playwright.db",
            COURTVISION_REDIS_URL: "redis://127.0.0.1:6399/0",
            COURTVISION_REPLAY_TICK_SECONDS: "0.03",
          },
        },
        {
          command: nextCommand,
          url: "http://127.0.0.1:3000",
          reuseExistingServer: false,
          env: {
            ...process.env,
            NEXT_PUBLIC_API_URL: "http://127.0.0.1:8000",
            NEXT_PUBLIC_WS_URL: "ws://127.0.0.1:8000",
            COURTVISION_INTERNAL_API_URL: "http://127.0.0.1:8000",
            COURTVISION_INTERNAL_API_KEY: "local-development-key",
          },
        },
      ]
    : {
        command: nextCommand,
        url: "http://127.0.0.1:3000",
        reuseExistingServer: true,
      },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], ...channelOverride },
    },
    {
      name: "mobile",
      use: { ...devices["iPhone 15"], ...channelOverride },
    },
  ],
});
