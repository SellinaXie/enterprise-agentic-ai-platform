"use client";

import { usePathname } from "next/navigation";

import { AppShell } from "./app-shell";
import { AuthProvider } from "./auth-provider";

export function ExperienceShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();

  // The showcase is intentionally static and public. Keeping it outside AuthProvider prevents
  // session discovery, token reads, and authenticated API calls on the public route.
  if (pathname === "/demo" || pathname.startsWith("/demo/")) {
    return <>{children}</>;
  }

  return (
    <AuthProvider>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  );
}
