import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  send: vi.fn(), verify: vi.fn(), session: vi.fn(), refresh: vi.fn(), push: vi.fn(), routerRefresh: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push, refresh: mocks.routerRefresh }) }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ refresh: mocks.refresh }) }));
vi.mock("@/lib/api/client", () => ({ api: { session: mocks.session } }));
vi.mock("@/lib/auth/client", () => ({
  managedAuthEnabled: true,
  managedAuth: { emailOtp: { sendVerificationOtp: mocks.send }, signIn: { emailOtp: mocks.verify } },
}));

import LoginPage from "./page";

beforeEach(() => {
  vi.clearAllMocks();
  mocks.send.mockResolvedValue({ error: null });
  mocks.verify.mockResolvedValue({ error: null });
  mocks.session.mockResolvedValue({ data: { subject: "invited-user" } });
});

async function enterCode() {
  render(<LoginPage />);
  await userEvent.type(screen.getByLabelText("Email address"), "invited@example.test");
  await userEvent.click(screen.getByRole("button", { name: "Send sign-in code" }));
  await userEvent.type(await screen.findByLabelText("Verification code"), "123456");
  await userEvent.click(screen.getByRole("button", { name: "Enter workspace" }));
}

describe("managed workspace sign-in", () => {
  it("validates both the email code and workspace authorization before navigation", async () => {
    await enterCode();
    expect(mocks.send).toHaveBeenCalledWith({ email: "invited@example.test", type: "sign-in" });
    expect(mocks.verify).toHaveBeenCalledWith({ email: "invited@example.test", otp: "123456" });
    expect(mocks.session).toHaveBeenCalledOnce();
    expect(mocks.push).toHaveBeenCalledWith("/dashboard");
  });

  it("keeps an expired-code error on the sign-in page", async () => {
    mocks.verify.mockResolvedValue({ error: { message: "expired" } });
    await enterCode();
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or expired");
    expect(mocks.session).not.toHaveBeenCalled();
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("does not admit a valid identity without a workspace role", async () => {
    mocks.session.mockRejectedValue(new Error("unauthorized"));
    await enterCode();
    expect(await screen.findByRole("alert")).toHaveTextContent("has not been granted workspace access");
    expect(mocks.push).not.toHaveBeenCalled();
  });
});
