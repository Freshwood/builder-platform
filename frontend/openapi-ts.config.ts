import { existsSync } from "node:fs";

import { defineConfig } from "@hey-api/openapi-ts";

// The Go backend publishes its schema in backend/openapi.json. Until it exists, fall back to the
// schema of the previous Python API.
const input = existsSync(new URL("../backend/openapi.json", import.meta.url))
  ? "../backend/openapi.json"
  : "../packages/api-client/openapi.json";

export default defineConfig({
  input,
  output: { path: "./src/api/gen" },
  plugins: ["@hey-api/typescript", "@hey-api/sdk", "@hey-api/client-fetch"],
});
