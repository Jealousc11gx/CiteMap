import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchRadarConnection, syncRadar, updateRadarConnection } from "./radarConnection";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

describe("radar connection service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads the masked persistent connection", async () => {
    const connection = {
      remote_url: "https://radar.example",
      token_configured: true,
      updated_at: "2026-09-10 10:00:00",
    };
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve(connection) });

    await expect(fetchRadarConnection()).resolves.toEqual(connection);
    expect(mockFetch).toHaveBeenCalledWith("/api/radar/connection");
  });

  it("can update the URL without resending a stored token", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ remote_url: "https://new.example", token_configured: true }),
    });

    await updateRadarConnection("https://new.example");
    expect(mockFetch).toHaveBeenCalledWith("/api/radar/connection", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ remote_url: "https://new.example", token: null }),
    });
  });

  it("syncs with credentials held by the backend", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ flushed: {}, synced: { applied: 0 }, published: 0 }),
    });

    await syncRadar("project/1", true, false);
    expect(mockFetch).toHaveBeenCalledWith("/api/radar/sync?project_id=project%2F1", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ publish_profile: false, force_publish_profile: true }),
    });
  });
});
