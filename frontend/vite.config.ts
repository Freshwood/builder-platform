import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig, type ProxyOptions } from "vite";

const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

// Same headers as the former Next.js config. In production the Go binary serves the build and
// sets them itself.
const securityHeaders = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Frame-Options": "DENY",
};

// Same-origin proxy so the session cookie stays first-party (no third-party cookies). Agent turns
// and cold PDF renders can take minutes, so the timeouts are generous.
const proxy: Record<string, ProxyOptions> = {
  "/api": {
    target: apiOrigin,
    changeOrigin: true,
    timeout: 300_000,
    proxyTimeout: 300_000,
    configure(proxyServer) {
      // Chat answers are an SSE stream: make sure nothing on the way buffers or compresses it.
      proxyServer.on("proxyRes", (res) => {
        if (String(res.headers["content-type"] ?? "").startsWith("text/event-stream")) {
          res.headers["cache-control"] = "no-cache, no-transform";
          res.headers["x-accel-buffering"] = "no";
        }
      });
    },
  },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { proxy, headers: securityHeaders },
  preview: { proxy, headers: securityHeaders },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // three.js (lazy Viewer3D chunk) and the AI SDK are large on their own; both are cached.
    chunkSizeWarningLimit: 700,
  },
});
