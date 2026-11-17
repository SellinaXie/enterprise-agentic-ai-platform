"use client";

import { createAuthClient } from "@neon/auth/next";

export const managedAuth = createAuthClient();
export const managedAuthEnabled = process.env.NEXT_PUBLIC_AUTH_MODE === "neon";

export async function getManagedAccessToken(): Promise<string | null> {
  const { data, error } = await managedAuth.token();
  if (error) return null;
  return data?.token ?? null;
}
