export type RadarConnection = {
  remote_url: string;
  token_configured: boolean;
  updated_at: string | null;
};

type RadarSyncResult = {
  flushed: unknown;
  synced: { applied?: number };
  published: number;
  profile_forced: boolean;
};

const API_BASE = "/api";

async function readError(response: Response, fallback: string): Promise<string> {
  const payload = await response.json().catch(() => null);
  const detail = payload?.detail;
  if (typeof detail === "string") return detail;
  return detail?.error || fallback;
}

export async function fetchRadarConnection(): Promise<RadarConnection> {
  const response = await fetch(`${API_BASE}/radar/connection`);
  if (!response.ok) throw new Error(await readError(response, "Failed to fetch radar connection"));
  return response.json();
}

export async function updateRadarConnection(remoteUrl: string, token?: string): Promise<RadarConnection> {
  const response = await fetch(`${API_BASE}/radar/connection`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ remote_url: remoteUrl, token: token || null }),
  });
  if (!response.ok) throw new Error(await readError(response, "Failed to update radar connection"));
  return response.json();
}

export async function syncRadar(
  projectId: string | undefined,
  forcePublishProfile = false,
  publishProfile = true,
): Promise<RadarSyncResult> {
  const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  const response = await fetch(`${API_BASE}/radar/sync${params}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      publish_profile: publishProfile,
      force_publish_profile: forcePublishProfile,
    }),
  });
  if (!response.ok) throw new Error(await readError(response, "Failed to sync radar"));
  return response.json();
}
