import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PublicLanding } from "./public-landing";

describe("public landing page", () => {
  it("renders the portfolio overview with links to the demo, architecture, and workspace", () => {
    render(<PublicLanding />);

    expect(screen.getByText("Public · no login required")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Explore the guided demo/ })).toHaveAttribute("href", "/demo");
    expect(screen.getByRole("link", { name: "Read the architecture overview" })).toHaveAttribute("href", "/architecture");
    expect(screen.getByRole("heading", { name: "Authenticated workspace" })).toBeInTheDocument();
  });
});
