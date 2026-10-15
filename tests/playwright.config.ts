import { defineConfig, devices, type PlaywrightTestConfig } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";

// Functional BDD scenarios. They only talk HTTP (backend) or drive the browser (frontend), so the
// same scenarios run against any implementation of the stack. Servers are started per run with the
// deterministic offline model (LLM_MODE=test) and a throwaway SQLite database.
const API_PORT = Number(process.env.BDD_API_PORT ?? 8010);
const WEB_PORT = Number(process.env.BDD_WEB_PORT ?? 3010);
export const API_URL = `http://localhost:${API_PORT}`;
const WEB_URL = `http://localhost:${WEB_PORT}`;

// Set BDD_SERVER_LOGS=1 to see server output.
// Which servers to start: "backend" needs only the API, "frontend" and "all" need both.
const SCOPE = process.env.BDD_SCOPE ?? "all";

const BACKEND_CMD =
  process.env.BDD_BACKEND_CMD ??
  `go run ./backend/cmd/homeworking`;
const FRONTEND_CMD =
  process.env.BDD_FRONTEND_CMD ??
  `corepack pnpm --filter @homeworking/frontend exec vite --port ${WEB_PORT} --strictPort`;

const steps = ["steps/**/*.ts", "support/**/*.ts"];

const backend = defineBddConfig({
  features: "features/backend/**/*.feature",
  steps,
  outputDir: ".features-gen/backend",
  tags: "not @wip",
});
const frontend = defineBddConfig({
  features: "features/frontend/**/*.feature",
  steps,
  outputDir: ".features-gen/frontend",
  tags: "not @wip",
});

type WebServer = NonNullable<PlaywrightTestConfig["webServer"]> extends infer T
  ? T extends Array<infer S>
    ? S
    : T
  : never;

const servers: WebServer[] = [
  {
    command: BACKEND_CMD,
    cwd: "..",
    url: `${API_URL}/api/health`,
    timeout: 300_000,
    reuseExistingServer: !process.env.CI,
    stdout: "ignore",
    stderr: process.env.BDD_SERVER_LOGS ? "pipe" : "ignore",
    env: {
      ENVIRONMENT: "test",
      LLM_MODE: "test",
      API_PORT: String(API_PORT),
      DATABASE_URL: process.env.BDD_DATABASE_URL ?? "sqlite:///./var/bdd.db",
      AUTO_CREATE_SCHEMA: "true",
    },
  },
];
if (SCOPE !== "backend") {
  servers.push({
    command: FRONTEND_CMD,
    cwd: "..",
    url: WEB_URL,
    timeout: 300_000,
    reuseExistingServer: !process.env.CI,
    stdout: "ignore",
    stderr: process.env.BDD_SERVER_LOGS ? "pipe" : "ignore",
    env: { API_ORIGIN: API_URL },
  });
}

export default defineConfig({
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: { trace: "retain-on-failure", locale: "de-DE" },
  projects: [
    { name: "backend", testDir: backend, use: { baseURL: API_URL } },
    {
      name: "frontend",
      testDir: frontend,
      use: { ...devices["Desktop Chrome"], baseURL: WEB_URL, locale: "de-DE" },
    },
  ],
  webServer: servers,
});
