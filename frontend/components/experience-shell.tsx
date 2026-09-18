"use client";

import { usePathname } from "next/navigation";

import { AppShell } from "./app-shell";
import { AuthProvider } from "./auth-provider";

const PUBLIC_SHOWCASE_ROUTES = ["/", "/demo", "/architecture"];

function isPublicShowcaseRoute(pathname: string): boolean {
  return PUBLIC_SHOWCASE_ROUTES.some((route) => (route === "/" ? pathname === "/" : pathname === route || pathname.startsWith(`${route}/`)));
}

export function ExperienceShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();

  // The public portfolio showcase (`/`, `/demo`, `/architecture`) is intentionally static and
  // public. Keeping it outside AuthProvider prevents session discovery, token reads, and
  // authenticated API calls on these routes — they must render without the Render backend or an
  // application login. The authenticated product now lives under `/dashboard` and the other
  // application routes, unaffected by this boundary.
  if (isPublicShowcaseRoute(pathname)) {
    return <>{children}</>;
  }

  return (
    <AuthProvider>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  );
}
