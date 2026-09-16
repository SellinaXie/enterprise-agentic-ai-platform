import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DemoExperience } from "./demo-experience";

describe("public guided demo", () => {
  it("starts with a clear synthetic and non-privileged boundary", () => {
    render(<DemoExperience />);

    expect(screen.getByText("Synthetic data only")).toBeInTheDocument();
    expect(screen.getByText(/makes no backend request/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open authenticated app" })).toHaveAttribute("href", "/");
  });

  it("walks through evidence, risk, governance, HITL, and operations", () => {
    render(<DemoExperience />);

    fireEvent.click(screen.getByRole("button", { name: /next stage/i }));
    expect(screen.getByRole("heading", { name: "Trace claims to controlled evidence" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Evaluation/i }));
    expect(screen.getByText(/not live-provider or production assurance/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /HITL/i }));
    expect(screen.getByText("None — controls are illustrative and non-operational")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Operations/i }));
    expect(screen.getByText(/No prompts, documents, embeddings/i)).toBeInTheDocument();
  });
});
