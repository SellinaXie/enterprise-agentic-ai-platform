import { afterEach, describe, expect, it, vi } from "vitest";

import { api, setAccessToken } from "./client";

afterEach(() => {
  setAccessToken(null);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("typed API client", () => {
  it("attaches the session token and returns the request ID", async () => {
    setAccessToken("synthetic.jwt.token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ subject: "analyst-1", email: null, display_name: null, roles: ["analyst"], issuer: "test" }), {
        status: 200,
        headers: { "content-type": "application/json", "x-request-id": "request-123" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await api.session();

    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer synthetic.jwt.token");
    expect(headers.get("X-Request-ID")).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    expect(response.requestId).toBe("request-123");
    expect(response.data.roles).toEqual(["analyst"]);
  });

  it("normalizes structured authorization failures without logging the token", async () => {
    setAccessToken("private.jwt.value");
    const consoleSpy = vi.spyOn(console, "log");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "permission_denied", message: "Permission denied." }, request_id: "forbidden-1" }), {
        status: 403,
        headers: { "content-type": "application/json" },
      }),
    ));

    await expect(api.session()).rejects.toEqual(
      expect.objectContaining({
        status: 403,
        code: "permission_denied",
        requestId: "forbidden-1",
      }),
    );
    expect(consoleSpy).not.toHaveBeenCalled();
  });
});
