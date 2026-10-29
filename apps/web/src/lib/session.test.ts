import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The module remembers the pending request, so every test starts with a fresh copy.
async function freshSession() {
  vi.resetModules();
  return (await import("./session")).sessionReady;
}

describe("sessionReady", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("asks the API for the session cookie once, however many requests wait for it", async () => {
    fetchMock.mockResolvedValue(new Response("{}"));
    const sessionReady = await freshSession();
    await Promise.all([sessionReady(), sessionReady(), sessionReady()]);
    await sessionReady();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/me", { credentials: "include" });
  });

  it("does not block forever when the API is unreachable: the next request tries again", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const sessionReady = await freshSession();
    await expect(sessionReady()).resolves.toBeUndefined();

    fetchMock.mockResolvedValue(new Response("{}"));
    await sessionReady();
    await sessionReady();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
