import { defineConfig, devices } from "@playwright/test";

const API_PORT = 8010;
const WEB_PORT = 3010;

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    locale: "de-DE",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // Offline deterministic LLM (LLM_MODE=test) and a throwaway SQLite database.
      command: `uv run uvicorn homeworking.main:app --port ${API_PORT}`,
      cwd: "../..",
      url: `http://localhost:${API_PORT}/api/health`,
      timeout: 300_000,
      reuseExistingServer: !process.env.CI,
      env: {
        ENVIRONMENT: "test",
        LLM_MODE: "test",
        DATABASE_URL: "sqlite+aiosqlite:///./var/e2e.db",
        AUTO_CREATE_SCHEMA: "true",
      },
    },
    {
      command: `next dev --port ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}`,
      timeout: 300_000,
      reuseExistingServer: !process.env.CI,
      env: { API_ORIGIN: `http://localhost:${API_PORT}` },
    },
  ],
});
