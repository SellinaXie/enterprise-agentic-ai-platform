import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "./auth-provider";
import { AppShell } from "./app-shell";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

function auth(role: "analyst" | "reviewer" | "admin"): AuthContextValue {
  return {
    principal: { subject: `${role}-1`, email: `${role}@example.test`, display_name: "Synthetic User", roles: [role], issuer: "test" },
    status: "authenticated",
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
    refresh: vi.fn(),
    hasRole: (...roles) => roles.includes(role),
  };
}

describe("role-aware application shell", () => {
  it("does not offer the review queue to an analyst", () => {
    render(<AuthContext.Provider value={auth("analyst")}><AppShell><p>Content</p></AppShell></AuthContext.Provider>);
    expect(screen.queryByRole("link", { name: "Reviews" })).not.toBeInTheDocument();
    expect(screen.getByText("analyst", { exact: true })).toBeInTheDocument();
  });

  it.each(["reviewer", "admin"] as const)("offers the review queue to %s", (role) => {
    render(<AuthContext.Provider value={auth(role)}><AppShell><p>Content</p></AppShell></AuthContext.Provider>);
    expect(screen.getByRole("link", { name: "Reviews" })).toBeInTheDocument();
  });
});
