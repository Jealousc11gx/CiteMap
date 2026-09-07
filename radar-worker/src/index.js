const STATES = new Set(["unread", "read", "saved", "dismissed"]);
const PRIORITY = { unread: 0, read: 1, dismissed: 2, saved: 3 };

function json(data, status = 200, origin = "*") {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": origin },
  });
}

function authorized(request, env) {
  const expected = env.RADAR_TOKEN;
  if (!expected) return true;
  return request.headers.get("authorization") === `Bearer ${expected}`;
}

function eventPayload(item) {
  return {
    project_id: item.project_id,
    arxiv_id: item.arxiv_id,
    title: item.title,
    abstract: item.abstract,
    authors: JSON.parse(item.authors || "[]"),
    categories: JSON.parse(item.categories || "[]"),
    published_date: item.published_date,
    arxiv_url: item.arxiv_url,
    pdf_url: item.pdf_url,
    score: item.score,
    reason: item.reason,
    tldr: item.tldr || "",
    ai_summary: item.ai_summary || "",
    title_zh: item.title_zh || "",
    abstract_zh: item.abstract_zh || "",
    core_contribution: item.core_contribution || "",
    method: item.method || "",
    result: item.result || "",
    limitations: item.limitations || "",
  };
}

async function addEvent(env, projectId, arxivId, type, state, payload = {}) {
  await env.DB.prepare(
    "INSERT INTO events (project_id, arxiv_id, type, state, payload) VALUES (?, ?, ?, ?, ?)",
  ).bind(projectId, arxivId, type, state || null, JSON.stringify(payload)).run();
}

async function createItems(request, env) {
  const body = await request.json();
  const items = body.items || [];
  const newItems = [];
  for (const item of items) {
    const existing = await env.DB.prepare("SELECT * FROM items WHERE project_id=? AND arxiv_id=?")
      .bind(item.project_id, item.arxiv_id).first();
    if (existing) {
      await env.DB.prepare(`
        UPDATE items SET tldr=?, ai_summary=?, title_zh=?, abstract_zh=?, core_contribution=?, method=?, result=?, limitations=?, score=?, reason=?, updated_at=?
        WHERE id=?
      `).bind(
        item.tldr || existing.tldr || "", item.ai_summary || existing.ai_summary || "",
        item.title_zh || existing.title_zh || "", item.abstract_zh || existing.abstract_zh || "",
        item.core_contribution || existing.core_contribution || "", item.method || existing.method || "",
        item.result || existing.result || "", item.limitations || existing.limitations || "",
        Number(item.score ?? existing.score ?? 0), item.reason || existing.reason || "",
        new Date().toISOString(), existing.id,
      ).run();
      const updated = await env.DB.prepare("SELECT * FROM items WHERE id=?").bind(existing.id).first();
      await addEvent(env, item.project_id, item.arxiv_id, "recommended", updated.user_state, eventPayload(updated));
      continue;
    }
    const token = crypto.randomUUID();
    await env.DB.prepare(`
      INSERT INTO items (project_id, arxiv_id, title, abstract, authors, categories, published_date, arxiv_url, pdf_url, score, reason, tldr, ai_summary, title_zh, abstract_zh, core_contribution, method, result, limitations, click_token)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      item.project_id, item.arxiv_id, item.title || "", item.abstract || "",
      JSON.stringify(item.authors || []), JSON.stringify(item.categories || []),
      item.published_date || null, item.arxiv_url || `https://arxiv.org/abs/${item.arxiv_id}`,
      item.pdf_url || null, Number(item.score || 0), item.reason || "", item.tldr || "",
      item.ai_summary || "", item.title_zh || "", item.abstract_zh || "", item.core_contribution || "",
      item.method || "", item.result || "", item.limitations || "", token,
    ).run();
    const created = await env.DB.prepare("SELECT * FROM items WHERE click_token=?").bind(token).first();
    await addEvent(env, item.project_id, item.arxiv_id, "recommended", "unread", eventPayload(created));
    newItems.push({ ...eventPayload(created), click_url: `${new URL(request.url).origin}/r/${token}` });
  }
  return json({ new_items: newItems });
}

async function markEmailed(request, env) {
  const body = await request.json();
  const now = new Date().toISOString();
  for (const item of body.items || []) {
    await env.DB.prepare("UPDATE items SET emailed_at=?, updated_at=? WHERE project_id=? AND arxiv_id=? AND emailed_at IS NULL")
      .bind(now, now, item.project_id, item.arxiv_id).run();
    await addEvent(env, item.project_id, item.arxiv_id, "emailed", null, { emailed_at: now });
  }
  return json({ ok: true });
}

async function updateState(request, env) {
  const body = await request.json();
  if (!STATES.has(body.state) || !body.project_id || !body.arxiv_id) return json({ error: "invalid state" }, 400);
  const item = await env.DB.prepare("SELECT * FROM items WHERE project_id=? AND arxiv_id=?")
    .bind(body.project_id, body.arxiv_id).first();
  if (!item) return json({ error: "item not found" }, 404);
  const next = PRIORITY[body.state] >= PRIORITY[item.user_state] ? body.state : item.user_state;
  await env.DB.prepare("UPDATE items SET user_state=?, updated_at=? WHERE id=?")
    .bind(next, new Date().toISOString(), item.id).run();
  await addEvent(env, item.project_id, item.arxiv_id, "state", next, {});
  return json({ ok: true, state: next });
}

async function sync(request, env) {
  const url = new URL(request.url);
  const after = Number(url.searchParams.get("after") || 0);
  const limit = Math.min(Number(url.searchParams.get("limit") || 200), 500);
  const rows = await env.DB.prepare("SELECT * FROM events WHERE event_id>? ORDER BY event_id LIMIT ?")
    .bind(after, limit).all();
  const events = rows.results.map((row) => ({
    event_id: row.event_id,
    project_id: row.project_id,
    arxiv_id: row.arxiv_id,
    type: row.type,
    state: row.state,
    ...JSON.parse(row.payload || "{}"),
  }));
  const next = events.length ? String(events[events.length - 1].event_id) : String(after);
  return json({ events, next_cursor: next, has_more: events.length === limit });
}

async function redirectRead(request, env, token) {
  const item = await env.DB.prepare("SELECT * FROM items WHERE click_token=?").bind(token).first();
  if (!item) return new Response("Not found", { status: 404 });
  const next = PRIORITY.read >= PRIORITY[item.user_state] ? "read" : item.user_state;
  await env.DB.prepare("UPDATE items SET user_state=?, updated_at=? WHERE id=?")
    .bind(next, new Date().toISOString(), item.id).run();
  await addEvent(env, item.project_id, item.arxiv_id, "state", next, {});
  return Response.redirect(item.arxiv_url, 302);
}

export default {
  async fetch(request, env) {
    const origin = env.ALLOWED_ORIGIN || "*";
    if (request.method === "OPTIONS") return new Response(null, { headers: { "access-control-allow-origin": origin, "access-control-allow-methods": "GET,POST,OPTIONS", "access-control-allow-headers": "Authorization,Content-Type" } });
    const url = new URL(request.url);
    if (url.pathname.startsWith("/r/")) return redirectRead(request, env, url.pathname.slice(3));
    if (!authorized(request, env)) return json({ error: "unauthorized" }, 401, origin);
    try {
      if (request.method === "POST" && url.pathname === "/profiles") {
        const body = await request.json();
        await env.DB.prepare("INSERT INTO profiles(project_id,payload,updated_at) VALUES(?,?,?) ON CONFLICT(project_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at")
          .bind(body.project_id, JSON.stringify(body), new Date().toISOString()).run();
        return json({ ok: true }, 200, origin);
      }
      if (request.method === "GET" && url.pathname === "/profiles") {
        const rows = await env.DB.prepare("SELECT payload FROM profiles").all();
        return json({ projects: rows.results.map((row) => JSON.parse(row.payload)) }, 200, origin);
      }
      if (request.method === "POST" && url.pathname === "/items") return createItems(request, env);
      if (request.method === "POST" && url.pathname === "/items/emailed") return markEmailed(request, env);
      if (request.method === "POST" && url.pathname === "/items/state") return updateState(request, env);
      if (request.method === "GET" && url.pathname === "/sync") return sync(request, env);
      return json({ error: "not found" }, 404, origin);
    } catch (error) {
      return json({ error: String(error) }, 500, origin);
    }
  },
};
