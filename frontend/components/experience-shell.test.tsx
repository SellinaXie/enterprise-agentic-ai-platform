import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ExperienceShell } from "./experience-shell";

const pathname = vi.hoisted(() => ({ value: "/" }));

vi.mock("next/navigation", () => ({ usePathname: () => pathname.value }));
vi.mock("./auth-provider", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => <div data-testid="auth-provider">{children}</div>,
}));
vi.mock("./app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div data-testid="app-shell">{children}</div>,
}));

describe("experience boundary", () => {
  beforeEach(() => { pathname.value = "/"; });

  it("keeps application routes inside authentication", () => {
    render(<ExperienceShell><p>Application</p></ExperienceShell>);
    expect(screen.getByTestId("auth-provider")).toBeInTheDocument();
    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
  });

  it("renders the public demo without mounting authentication", () => {
    pathname.value = "/demo";
    render(<ExperienceShell><p>Public demo</p></ExperienceShell>);
    expect(screen.getByText("Public demo")).toBeInTheDocument();
    expect(screen.queryByTestId("auth-provider")).not.toBeInTheDocument();
    expect(screen.queryByTestId("app-shell")).not.toBeInTheDocument();
  });
});
