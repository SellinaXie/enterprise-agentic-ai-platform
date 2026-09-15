import { describe, expect, it } from "vitest";

import { GET } from "./route";

describe("frontend health endpoint", () => {
  it("returns liveness without contacting the backend", async () => {
    const response = GET();

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    await expect(response.json()).resolves.toEqual({ status: "ok", version: "0.8.0" });
  });
});
