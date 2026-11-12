import type { NextConfig } from "next";

const configuredApiTarget =
  process.env.API_INTERNAL_URL?.trim() ||
  (process.env.API_INTERNAL_HOSTPORT
    ? `http://${process.env.API_INTERNAL_HOSTPORT}`
    : "http://127.0.0.1:8000");
const apiTarget = configuredApiTarget.replace(/\/+$/, "");

if (!/^https?:\/\//.test(apiTarget)) {
  throw new Error("API_INTERNAL_URL must be an absolute HTTP(S) URL");
}

const nextConfig: NextConfig = {
  agentRules: false,
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
  async rewrites() {
    // In a Vercel Services deployment, the platform routes /backend directly to
    // FastAPI. Keep the external proxy for standalone frontend/Render installs.
    if (process.env.VERCEL && !process.env.API_INTERNAL_URL && !process.env.API_INTERNAL_HOSTPORT) {
      return [];
    }
    return [
      {
        source: "/backend/:path*",
        destination: `${apiTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
