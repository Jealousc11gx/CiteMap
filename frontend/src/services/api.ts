import type { Paper, NoteItem, ChatMessage, ChatSession, Project, RadarConfig, RadarMatch, RadarState } from "@/types";

const API_BASE = "/api";

export interface LLMModelsResponse {
  models: string[];
  default_model: string;
}

export async function fetchRadarConfig(projectId: string): Promise<RadarConfig> {
  const res = await fetch(`${API_BASE}/radar/config?project_id=${encodeURIComponent(projectId)}`);
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Failed to fetch radar config");
  return res.json();
}

export async function updateRadarConfig(projectId: string, config: Omit<RadarConfig, "project_id" | "updated_at">): Promise<RadarConfig> {
  const res = await fetch(`${API_BASE}/radar/config?project_id=${encodeURIComponent(projectId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Failed to update radar config");
  return res.json();
}

export async function fetchRadarMatches(projectId: string, state?: RadarState): Promise<RadarMatch[]> {
  const params = new URLSearchParams({ project_id: projectId });
  if (state) params.set("state", state);
  const res = await fetch(`${API_BASE}/radar/matches?${params}`);
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Failed to fetch radar matches");
  return res.json();
}

export async function scanRadar(projectId: string): Promise<{ run_id: string; status: string; candidate_count: number; matched_count: number }> {
  const res = await fetch(`${API_BASE}/radar/scan?project_id=${encodeURIComponent(projectId)}`, { method: "POST" });
  if (!res.ok) {
    const detail = (await res.json().catch(() => null))?.detail;
    throw new Error(typeof detail === "object" ? detail.error || "Radar scan failed" : detail || "Radar scan failed");
  }
  return res.json();
}

export async function updateRadarMatch(matchId: string, state: RadarState, downloadPdf = false): Promise<RadarMatch & { paper_id?: string }> {
  const res = await fetch(`${API_BASE}/radar/matches/${encodeURIComponent(matchId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state, download_pdf: downloadPdf }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Failed to update radar match");
  return res.json();
}

export async function syncRadar(projectId: string | undefined, remoteUrl: string, token: string, forcePublishProfile = false): Promise<{ flushed: unknown; synced: unknown; published: number; profile_forced: boolean }> {
  const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  const res = await fetch(`${API_BASE}/radar/sync${params}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ remote_url: remoteUrl, token, publish_profile: true, force_publish_profile: forcePublishProfile }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail?.error || "Failed to sync radar");
  return res.json();
}

export async function listProjects(): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/projects`);
  if (!res.ok) throw new Error("Failed to list projects");
  return res.json();
}

export async function createProject(name: string, description = ""): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Failed to create project");
  return res.json();
}

export async function renameProject(projectId: string, name: string, description?: string): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, ...(description === undefined ? {} : { description }) }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Failed to rename project");
  return res.json();
}

export async function deleteProject(projectId: string): Promise<{ status: string; fallback_project_id: string }> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Failed to delete project");
  return res.json();
}

export async function addPaperToProject(projectId: string, paperId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/papers/${encodeURIComponent(paperId)}`, { method: "POST" });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Failed to add paper to project");
}

export async function removePaperFromProject(projectId: string, paperId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/papers/${encodeURIComponent(paperId)}`, { method: "DELETE" });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Failed to remove paper from project");
}

export async function fetchAvailablePapers(projectId: string): Promise<Paper[]> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectId)}/available-papers`);
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Failed to fetch available papers");
  return res.json();
}

export async function fetchPapers(source?: string, q?: string, projectId?: string): Promise<Paper[]> {
  const params = new URLSearchParams();
  if (source) params.set("source", source);
  if (q) params.set("q", q);
  if (projectId) params.set("project_id", projectId);
  const query = params.toString();
  const res = await fetch(`${API_BASE}/papers${query ? `?${query}` : ""}`);
  if (!res.ok) throw new Error("Failed to fetch papers");
  return res.json();
}

export async function fetchPaper(id: string): Promise<Paper> {
  const res = await fetch(`${API_BASE}/papers/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error("Failed to fetch paper");
  return res.json();
}

export async function ingestPdf(file: File, projectId?: string): Promise<{ paper_id: string; title: string }> {
  const form = new FormData();
  form.append("file", file);
  if (projectId) form.append("project_id", projectId);
  const res = await fetch(`${API_BASE}/papers/ingest-pdf`, { method: "POST", body: form });
  if (!res.ok) throw new Error("Failed to ingest PDF");
  return res.json();
}

export async function ingestArxiv(arxivId: string, downloadPdf = false, projectId?: string) {
  const res = await fetch(`${API_BASE}/papers/ingest-arxiv`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ arxiv_id: arxivId, download_pdf: downloadPdf, ...(projectId ? { project_id: projectId } : {}) }),
  });
  if (!res.ok) throw new Error("Failed to ingest arXiv");
  return res.json();
}

export async function searchArxiv(query: string, maxResults = 10, download = false, projectId?: string) {
  const params = new URLSearchParams({ q: query, max_results: String(maxResults), download: String(download) });
  if (projectId) params.set("project_id", projectId);
  const res = await fetch(`${API_BASE}/papers/search?${params}`);
  if (!res.ok) throw new Error("Failed to search arXiv");
  return res.json();
}

export async function searchArxivResults(query: string, maxResults = 10) {
  const res = await fetch(`${API_BASE}/papers/search-arxiv?${new URLSearchParams({ q: query, max_results: String(maxResults) })}`);
  if (!res.ok) throw new Error("Failed to search arXiv");
  return res.json();
}

export async function annotatePaper(paperId: string, model?: string, projectId?: string, force = false) {
  const body: { paper_id: string; model?: string; force?: boolean } = { paper_id: paperId };
  if (model) body.model = model;
  if (projectId) (body as Record<string, unknown>).project_id = projectId;
  if (force) body.force = true;
  const res = await fetch(`${API_BASE}/papers/${encodeURIComponent(paperId)}/annotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = typeof res.json === "function" ? await res.json().catch(() => null) : null;
    const detail = payload?.detail;
    const message = typeof detail === "string" ? detail : detail?.error;
    const code = typeof detail === "object" ? detail?.code : undefined;
    throw new Error(code ? `[${code}] ${message}` : message || "Failed to annotate paper");
  }
  return res.json();
}

export async function fetchGraphTeam(projectId?: string) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  const res = await fetch(`${API_BASE}/graph/team${query}`);
  if (!res.ok) throw new Error("Failed to fetch team graph");
  return res.json();
}

export async function fetchGraphPaper(projectId?: string) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  const res = await fetch(`${API_BASE}/graph/paper${query}`);
  if (!res.ok) throw new Error("Failed to fetch paper graph");
  return res.json();
}

export async function listChatSessions(projectId?: string): Promise<ChatSession[]> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  const res = await fetch(`${API_BASE}/chat/sessions${query}`);
  if (!res.ok) throw new Error("Failed to list chat sessions");
  return res.json();
}

export async function createChatSession(title = "", projectId?: string): Promise<ChatSession> {
  const res = await fetch(`${API_BASE}/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, ...(projectId ? { project_id: projectId } : {}) }),
  });
  if (!res.ok) throw new Error("Failed to create chat session");
  return res.json();
}

export async function deleteChatSession(sessionId: string) {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete chat session");
  return res.json();
}

export async function renameChatSession(sessionId: string, title: string): Promise<ChatSession> {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("Failed to rename chat session");
  return res.json();
}

export async function getChatMessages(sessionId: string): Promise<ChatMessage[]> {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}/messages`);
  if (!res.ok) throw new Error("Failed to get chat messages");
  return res.json();
}

export async function sendChatMessage(sessionId: string, message: string, mode = "auto", projectId?: string): Promise<ChatMessage> {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, mode, ...(projectId ? { project_id: projectId } : {}) }),
  });
  if (!res.ok) throw new Error("Failed to send chat message");
  return res.json();
}

export interface ChatStreamEvent {
  type: "thinking" | "tool_call" | "tool_result" | "answer";
  content?: string;
  tool?: string;
  arguments?: Record<string, unknown>;
  result?: Record<string, unknown>;
  papers?: any[];
  tool_calls?: any[];
}

export async function streamChatMessage(
  sessionId: string,
  message: string,
  onEvent: (event: ChatStreamEvent) => void,
  onComplete: (fullMessage: ChatMessage) => void,
  onError: (err: Error) => void,
  projectId?: string,
) {
  try {
    const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, mode: "auto", ...(projectId ? { project_id: projectId } : {}) }),
    });

    if (!res.ok) throw new Error("Failed to stream chat message");

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";
    let fullText = "";
    let finalPapers: any[] = [];
    let finalToolCalls: any[] = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;

        const dataStr = trimmed.slice(6);
        if (dataStr === "[DONE]") continue;

        try {
          const event = JSON.parse(dataStr) as ChatStreamEvent;
          onEvent(event);

          if (event.type === "answer") {
            fullText = event.content || "";
            finalPapers = event.papers || [];
            finalToolCalls = event.tool_calls || [];
          }
        } catch {
          // ignore parse error
        }
      }
    }

    onComplete({
      role: "assistant",
      content: fullText,
      papers: finalPapers as any,
      tool_calls: finalToolCalls as any,
      created_at: new Date().toISOString(),
    });
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)));
  }
}

export async function batchIngest(paperIds: string[], downloadPdf = false) {
  const res = await fetch(`${API_BASE}/papers/batch-ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paper_ids: paperIds, download_pdf: downloadPdf }),
  });
  if (!res.ok) throw new Error("Failed to batch ingest");
  return res.json();
}

export async function downloadPdf(paperId: string) {
  const res = await fetch(`${API_BASE}/papers/${encodeURIComponent(paperId)}/download-pdf`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to download PDF");
  return res.json();
}

export async function batchAnnotate(model?: string, projectId?: string) {
  const body = { ...(model ? { model } : {}), ...(projectId ? { project_id: projectId } : {}) };
  const res = await fetch(`${API_BASE}/papers/batch-annotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = typeof res.json === "function" ? await res.json().catch(() => null) : null;
    const detail = payload?.detail;
    const message = typeof detail === "string" ? detail : detail?.error;
    const code = typeof detail === "object" ? detail?.code : undefined;
    throw new Error(code ? `[${code}] ${message}` : message || "Failed to batch annotate");
  }
  return res.json();
}

export async function fetchLLMModels(): Promise<LLMModelsResponse> {
  const res = await fetch(`${API_BASE}/llm/models`);
  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = payload?.detail;
    const message = typeof detail === "string" ? detail : detail?.error;
    const code = typeof detail === "object" ? detail?.code : undefined;
    throw new Error(code ? `[${code}] ${message}` : message || "Failed to fetch LLM models");
  }
  return payload;
}

export async function listNotes(projectId?: string): Promise<NoteItem[]> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  const res = await fetch(`${API_BASE}/notes${query}`);
  if (!res.ok) throw new Error("Failed to list notes");
  return res.json();
}

export async function getNote(paperId: string): Promise<NoteItem> {
  const res = await fetch(`${API_BASE}/notes/${encodeURIComponent(paperId)}`);
  if (!res.ok) throw new Error("Failed to get note");
  return res.json();
}

export async function saveNote(paperId: string, content: string): Promise<{ success: boolean }> {
  const res = await fetch(`${API_BASE}/notes/${encodeURIComponent(paperId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error("Failed to save note");
  return res.json();
}

export async function createNoteTemplate(paperId: string): Promise<{
  paper_id: string;
  path: string;
  content: string;
}> {
  const res = await fetch(`${API_BASE}/notes/${encodeURIComponent(paperId)}/template`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to create note template");
  return res.json();
}

export async function deleteNote(paperId: string): Promise<{ success: boolean }> {
  const res = await fetch(`${API_BASE}/notes/${encodeURIComponent(paperId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete note");
  return res.json();
}
