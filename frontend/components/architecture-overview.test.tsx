import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ArchitectureOverview } from "./architecture-overview";

describe("public architecture overview", () => {
  it("renders the design rationale and end-to-end flow without calling the backend", () => {
    render(<ArchitectureOverview />);

    expect(screen.getByText("Read-only · no backend call")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How one decision moves through the system" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Why the major components exist" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Current limitations" })).toBeInTheDocument();
  });
});
