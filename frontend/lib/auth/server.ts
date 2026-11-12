import { createNeonAuth } from "@neon/auth/next/server";

let instance: ReturnType<typeof createNeonAuth> | undefined;

export function getManagedAuth() {
  if (!instance) {
    const baseUrl = process.env.NEON_AUTH_BASE_URL;
    const secret = process.env.NEON_AUTH_COOKIE_SECRET;
    if (!baseUrl || !secret) throw new Error("Workspace sign-in is not configured.");
    instance = createNeonAuth({ baseUrl, cookies: { secret }, logLevel: "silent" });
  }
  return instance;
}
