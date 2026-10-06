import type { NextConfig } from "next";

const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  transpilePackages: ["@homeworking/api-client"],
  experimental: {
    // The /api proxy cuts requests after 30 s by default and then answers with a plain-text
    // 500. Agent turns with free designs and cold PDF renders can take longer.
    proxyTimeout: 300_000,
  },
  // Same-origin proxy so the session cookie stays first-party (no third-party cookies).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
