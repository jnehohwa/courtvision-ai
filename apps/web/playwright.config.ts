import { defineConfig, devices } from "@playwright/test";

const browserChannel = process.env.PLAYWRIGHT_CHANNEL;
const channelOverride = browserChannel
  ? { browserName: "chromium" as const, channel: browserChannel }
  : {};

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  webServer: {
    command: "pnpm dev",
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
