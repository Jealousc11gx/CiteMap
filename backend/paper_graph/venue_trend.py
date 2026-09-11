"""会议级 venue trend 分析。

语义移植自 llm-paper-radar 的 openreview_venue、venue_filter、venue_group
与 venue-trend skill。它是手动触发的一次性分析，不属于每日 Explore scan。
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from .annotate import get_client, get_default_model
from .explore_llm import call_json, load_prompt
from .explore_sources import _openreview_date, _openreview_value

OPENREVIEW_NOTES_URL = "https://api2.openreview.net/notes"
VENUE_PAGE_SIZE = 1000
VENUE_RETRYABLE_STATUS = {403, 429}


class VenueTrendError(RuntimeError):
    pass


def _is_accepted(note: dict, venue: str) -> bool:
    return _openreview_value(note.get("content", {}) or {}, "venueid", "") == venue


def _note_to_paper(note: dict, venue: str) -> dict | None:
    content = note.get("content", {}) or {}
    title = str(_openreview_value(content, "title", "") or "").strip()
    abstract = str(_openreview_value(content, "abstract", "") or "").strip()
    note_id = str(note.get("id", "") or "").strip()
    published = _openreview_date(note)
    if not title or not note_id or published is None:
        return None
    authors = _openreview_value(content, "authors", []) or []
    if isinstance(authors, str):
        authors = [authors]
    return {
        "id": f"or-{note_id}",
        "title": title,
        "abstract": abstract,
        "authors": list(authors),
        "venue": venue,
        "url": f"https://openreview.net/forum?id={note_id}",
        "pdf_url": f"https://openreview.net/pdf?id={note_id}",
        "published_date": published.date().isoformat(),
    }


def _fetch_page(client: httpx.Client, venue: str, offset: int) -> list[dict]:
    invitation = f"{venue}/-/Submission"
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            response = client.get(
                OPENREVIEW_NOTES_URL,
                params={
                    "invitation": invitation,
                    "offset": offset,
                    "limit": VENUE_PAGE_SIZE,
                    "sort": "cdate:desc",
                },
            )
            if response.status_code in VENUE_RETRYABLE_STATUS:
                last_error = VenueTrendError(f"OpenReview HTTP {response.status_code}")
                time.sleep(min(60, 5 * (2**attempt)))
                continue
            response.raise_for_status()
            return response.json().get("notes", [])
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            time.sleep(min(60, 5 * (2**attempt)))
    raise VenueTrendError(f"OpenReview page offset={offset} 获取失败: {last_error}")


def _venue_headers(client: httpx.Client) -> dict[str, str]:
    email = os.environ.get("OPENREVIEW_EMAIL")
    password = os.environ.get("OPENREVIEW_PASSWORD")
    if not email or not password:
        return {}
    response = client.post(
        "https://api2.openreview.net/login",
        json={"id": email, "password": password},
    )
    response.raise_for_status()
    token = response.json().get("token")
    if not token:
        raise VenueTrendError("OpenReview login succeeded but response had no token")
    return {"Authorization": f"Bearer {token}"}


def fetch_venue_accepted(venue: str, *, max_pages: int = 20) -> list[dict]:
    """分页获取完整 accepted set；只接受 venueid 精确等于 venue 的 note。"""
    papers: list[dict] = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        client.headers.update(_venue_headers(client))
        for page in range(max_pages):
            notes = _fetch_page(client, venue, page * VENUE_PAGE_SIZE)
            if not notes:
                break
            for note in notes:
                if _is_accepted(note, venue):
                    paper = _note_to_paper(note, venue)
                    if paper:
                        papers.append(paper)
            if len(notes) < VENUE_PAGE_SIZE:
                break
            time.sleep(1)
    return papers


def _classify_paper(paper: dict, client: Any, model: str) -> dict:
    if not paper["title"].strip() or not paper["abstract"].strip():
        return {"hard_gate": True, "subfield": "unknown", "reason": "skipped: missing title/abstract"}
    try:
        return call_json(
            client,
            model=model,
            system=load_prompt("venue_inference_relevance.md"),
            user=f"Title: {paper['title']}\n\nAbstract: {paper['abstract']}",
            max_tokens=512,
        )
    except Exception as exc:
        return {
            "hard_gate": True,
            "subfield": "unknown",
            "reason": f"judge unavailable: {type(exc).__name__}: {exc}"[:200],
        }


def _group_in_scope(papers: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for paper in papers:
        if paper.get("hard_gate"):
            continue
        subfield = str(paper.get("subfield") or "unknown")
        groups.setdefault(subfield, []).append(paper)
    return dict(sorted(groups.items(), key=lambda item: len(item[1]), reverse=True))


def _generate_report(groups: dict[str, list[dict]], client: Any, model: str) -> dict:
    papers = [paper for group in groups.values() for paper in group]
    context = "\n\n".join(
        f"[{paper['subfield']}] {paper['title']}\n{paper['abstract']}\n{paper['url']}"
        for paper in papers
    )
    if not context:
        return {"takeaway": "没有通过 venue relevance 的论文。", "research_concerns": [], "cross_cutting_threads": [], "caveats": []}
    return call_json(
        client,
        model=model,
        system=load_prompt("venue_trend_report.md"),
        user=f"Venue: {papers[0]['venue']}\n\nAccepted papers classified in scope ({len(papers)}):\n\n{context}",
        max_tokens=6000,
    )


def run_venue_trend(
    conn,
    venue: str,
    *,
    max_pages: int = 20,
    min_accepted: int = 20,
    model: str | None = None,
    fetcher=fetch_venue_accepted,
    llm_client=None,
) -> dict:
    venue = venue.strip()
    if not venue:
        raise ValueError("venue 不能为空")
    accepted = fetcher(venue, max_pages=max_pages)
    if not accepted:
        raise VenueTrendError("OpenReview 没有返回 accepted papers；检查 venue host/year、决策状态、OpenReview 凭据")
    if len(accepted) < min_accepted:
        raise VenueTrendError(
            f"OpenReview accepted papers 仅 {len(accepted)} 篇，低于完整结果下限 {min_accepted}；不要把 partial venue 当成最终报告"
        )
    client = llm_client or get_client()
    effective_model = model or get_default_model()
    scored = []
    for paper in accepted:
        scored_paper = dict(paper)
        scored_paper.update(_classify_paper(paper, client, effective_model))
        scored.append(scored_paper)
    groups = _group_in_scope(scored)
    report = _generate_report(groups, client, effective_model)
    run_id = "venue_trend_" + re.sub(r"[^A-Za-z0-9_.-]+", "_", venue) + "_" + datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    result = {
        "id": run_id,
        "venue": venue,
        "model": effective_model,
        "accepted_count": len(scored),
        "in_scope_count": sum(len(items) for items in groups.values()),
        "groups": groups,
        "report": report,
        "created_at": datetime.now(UTC).isoformat(),
    }
    conn.execute(
        "INSERT INTO explore_venue_trend_runs (id, venue, model, accepted_count, in_scope_count, result) VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, venue, effective_model, len(scored), result["in_scope_count"], json.dumps(result, ensure_ascii=False)),
    )
    conn.commit()
    return result


def list_venue_trend_runs(conn, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT id, venue, model, accepted_count, in_scope_count, created_at FROM explore_venue_trend_runs ORDER BY created_at DESC LIMIT ?",
        (max(1, min(limit, 100)),),
    ).fetchall()
    return [dict(row) for row in rows]


def get_venue_trend_run(conn, run_id: str) -> dict:
    row = conn.execute("SELECT result FROM explore_venue_trend_runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise ValueError("venue trend 运行记录不存在")
    return json.loads(row["result"])
