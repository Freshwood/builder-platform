import { defineConfig, devices } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";

// Browser tests of the web app: hand-written end-to-end specs (`e2e`) and the functional Gherkin
// scenarios (`bdd`). Both run against the real Next.js app and the FastAPI backend, started with
// the deterministic offline model (LLM_MODE=test) and a throwaway SQLite database. The backend has
// its own scenarios in apps/api/tests/bdd.
const API_PORT = Number(process.env.E2E_API_PORT ?? 8010);
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 3010);
const API_URL = `http://localhost:${API_PORT}`;
const WEB_URL = `http://localhost:${WEB_PORT}`;

// Set E2E_SERVER_LOGS=1 to see server output.
const logs = process.env.E2E_SERVER_LOGS ? "pipe" : "ignore";

const bddDir = defineBddConfig({
  features: "tests/bdd/features/**/*.feature",
  steps: ["tests/bdd/fixtures.ts", "tests/bdd/steps.ts"],
  outputDir: "tests/bdd/.features-gen",
  tags: "not @wip",
});

export default defineConfig({
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: { baseURL: WEB_URL, trace: "retain-on-failure", locale: "de-DE" },
  projects: [
    { name: "e2e", testDir: "./tests/e2e", use: { ...devices["Desktop Chrome"] } },
    { name: "bdd", testDir: bddDir, use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: `uv run uvicorn homeworking.main:app --port ${API_PORT}`,
      cwd: "../..",
      url: `${API_URL}/api/health`,
      timeout: 300_000,
      reuseExistingServer: !process.env.CI,
      stdout: "ignore",
      stderr: logs,
      env: {
        ENVIRONMENT: "test",
        LLM_MODE: "test",
        DATABASE_URL: "sqlite+aiosqlite:///./var/e2e.db",
        AUTO_CREATE_SCHEMA: "true",
      },
    },
    {
      command: `next dev --port ${WEB_PORT}`,
      url: WEB_URL,
      timeout: 300_000,
      reuseExistingServer: !process.env.CI,
      stdout: "ignore",
      stderr: logs,
      env: { API_ORIGIN: API_URL },
    },
  ],
});
