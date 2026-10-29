import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// Unit tests for the pure logic in src/lib (no DOM, no React). The browser behaviour is covered
// by the Playwright projects in playwright.config.ts.
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
