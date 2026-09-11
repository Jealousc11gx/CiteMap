"""独立 Explore：按 llm-paper-radar 算法采集、判断、摘要、排序。"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta
from typing import Callable, Optional

from .annotate import get_client, get_default_model
from .explore_algorithms import (
    BUCKET_ORDER,
    BUCKET_TITLES,
    MILESTONE_COOLDOWN_DAYS,
    MILESTONE_TRENDING_IDS,
    PREFILTER_BLACKLIST,
    PREFILTER_WHITELIST,
    TOPIC_CAPS,
    composite_relevance,
    group_with_caps,
    heat_score,
    judge_unavailable_result,
    merge_candidates,
    milestone_override,
    normalize_breakdown,
    prefilter_hard_gate_result,
    prefilter_verdict,
    ranking_score,
    sort_candidates,
)
from .explore_llm import call_json, load_prompt
from .explore_sources import (
    fetch_arxiv_daily,
    fetch_hf_daily,
    fetch_openreview,
    fetch_watched_authors,
    run_source,
)
from .radar import _json, _loads
from .settings import explore_target_date, get_explore_runtime_config

EXPLORE_TRIAGE_STATES = {"unreviewed", "read", "later", "ignored", "project"}


class ExploreAnalysisError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def get_explore_profile(conn: sqlite3.Connection, profile_id: str = "explore_default") -> dict:
    row = conn.execute("SELECT * FROM explore_profiles WHERE id = ?", (profile_id,)).fetchone()
    if row is None:
        raise ValueError("探索主题不存在")
    result = dict(row)
    for key in ("categories", "include_keywords", "exclude_keywords"):
        result[key] = _loads(result.get(key), [])
    result["enabled"] = bool(result.get("enabled", 0))
    return result


def list_explore_profiles(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id FROM explore_profiles ORDER BY updated_at DESC, name COLLATE NOCASE"
    ).fetchall()
    return [get_explore_profile(conn, row["id"]) for row in rows]


def update_explore_profile(
    conn: sqlite3.Connection,
    profile_id: str,
    *,
    name: str,
    description: str,
    categories: list[str],
    include_keywords: list[str],
    exclude_keywords: list[str],
    enabled: bool,
) -> dict:
    if not name.strip():
        raise ValueError("探索主题名称不能为空")
    normalized_categories = [item.strip() for item in categories if item.strip()]
    if not normalized_categories:
        raise ValueError("探索主题至少需要一个 arXiv category")
    result = conn.execute(
        """
        UPDATE explore_profiles
        SET name=?, description=?, categories=?, include_keywords=?, exclude_keywords=?,
            enabled=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (
            name.strip(),
            description.strip(),
            _json(normalized_categories),
            _json([item.strip() for item in include_keywords if item.strip()]),
            _json([item.strip() for item in exclude_keywords if item.strip()]),
            int(enabled),
            profile_id,
        ),
    )
    if result.rowcount == 0:
        raise ValueError("探索主题不存在")
    conn.commit()
    return get_explore_profile(conn, profile_id)


def _canonical_id(value: object) -> str:
    raw = str(value or "").strip()
    if raw.startswith("or-"):
        return raw
    raw = raw.removeprefix("arXiv:").removeprefix("arxiv:")
    raw = raw.replace("https://arxiv.org/abs/", "").replace("http://arxiv.org/abs/", "")
    raw = raw.replace("https://arxiv.org/pdf/", "").replace("http://arxiv.org/pdf/", "")
    return re.sub(r"v\d+$", "", raw.removesuffix(".pdf"))


def _candidate_id(canonical_id: str) -> str:
    return "explore_candidate_" + re.sub(r"[^A-Za-z0-9_.-]+", "_", canonical_id)


def _profile_state(candidate: dict, profile: dict) -> tuple[str, str, Optional[float], dict, str]:
    title = str(candidate.get("title") or "")
    abstract = str(candidate.get("abstract") or "")
    if not title.strip() or not abstract.strip():
        return "skipped", "skipped", None, {}, "skipped: missing title/abstract"
    should_gate, _, blacklist_hits = prefilter_verdict(
        title,
        abstract,
        whitelist=(*PREFILTER_WHITELIST, *profile.get("include_keywords", [])),
        blacklist=(*PREFILTER_BLACKLIST, *profile.get("exclude_keywords", [])),
    )
    if not should_gate:
        return "prefilter_passed", "pending", None, {}, "通过 prefilter，等待 LLM Judge"
    result = prefilter_hard_gate_result(blacklist_hits)
    return "rejected", "completed", 0, normalize_breakdown(result), result["reason"]


def _store_candidate(
    conn: sqlite3.Connection,
    profile_id: str,
    candidate: dict,
    *,
    discovered_on: date,
) -> dict:
    canonical_id = _canonical_id(candidate.get("arxiv_id"))
    if not canonical_id:
        raise ValueError("探索候选缺少 canonical ID")
    candidate_id = _candidate_id(canonical_id)
    code_meta = candidate.get("code_meta") or {}
    conn.execute(
        """
        INSERT INTO explore_candidates (
            id, arxiv_id, title, abstract, authors, categories, published_date,
            updated_date, arxiv_url, pdf_url, code_url, code_meta, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(arxiv_id) DO UPDATE SET
            title=excluded.title,
            abstract=excluded.abstract,
            authors=excluded.authors,
            categories=excluded.categories,
            published_date=excluded.published_date,
            updated_date=excluded.updated_date,
            arxiv_url=excluded.arxiv_url,
            pdf_url=excluded.pdf_url,
            code_url=excluded.code_url,
            code_meta=excluded.code_meta,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            candidate_id,
            canonical_id,
            candidate.get("title", ""),
            candidate.get("abstract", ""),
            _json(candidate.get("authors") or []),
            _json(candidate.get("categories") or []),
            candidate.get("published_date"),
            candidate.get("updated_date"),
            candidate.get("arxiv_url") or f"https://arxiv.org/abs/{canonical_id}",
            candidate.get("pdf_url"),
            candidate.get("code_url"),
            _json(code_meta),
        ),
    )
    actual_id = conn.execute(
        "SELECT id FROM explore_candidates WHERE arxiv_id = ?", (canonical_id,)
    ).fetchone()["id"]
    for source in candidate.get("sources") or []:
        conn.execute(
            """
            INSERT INTO explore_candidate_sources (candidate_id, source, source_rank, metadata)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(candidate_id, source) DO UPDATE SET
                source_rank=excluded.source_rank,
                metadata=excluded.metadata
            """,
            (
                actual_id,
                source.get("source"),
                source.get("source_rank"),
                _json(source.get("metadata") or {}),
            ),
        )
    sources = [
        {"source": row["source"], "metadata": _loads(row["metadata"], {})}
        for row in conn.execute(
            "SELECT source, metadata FROM explore_candidate_sources WHERE candidate_id = ?",
            (actual_id,),
        ).fetchall()
    ]
    conn.execute(
        "UPDATE explore_candidates SET heat_score = ? WHERE id = ?",
        (heat_score(sources, code_meta), actual_id),
    )
    profile = get_explore_profile(conn, profile_id)
    gate_status, judge_status, score, breakdown, reason = _profile_state(candidate, profile)
    summary_status = "skipped" if gate_status in {"rejected", "skipped"} else "pending"
    conn.execute(
        """
        INSERT INTO explore_profile_candidates (
            profile_id, candidate_id, gate_status, judge_status, summary_status,
            judge_score, topic_relevance_score, practicality_score, topic_bucket,
            relevance_breakdown, judge_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(profile_id, candidate_id) DO UPDATE SET
            gate_status=CASE
                WHEN explore_profile_candidates.judge_status='pending' THEN excluded.gate_status
                ELSE explore_profile_candidates.gate_status
            END,
            judge_status=CASE
                WHEN explore_profile_candidates.judge_status='pending' THEN excluded.judge_status
                ELSE explore_profile_candidates.judge_status
            END,
            summary_status=CASE
                WHEN explore_profile_candidates.judge_status='pending' THEN excluded.summary_status
                ELSE explore_profile_candidates.summary_status
            END,
            judge_score=CASE
                WHEN explore_profile_candidates.judge_status='pending' THEN excluded.judge_score
                ELSE explore_profile_candidates.judge_score
            END,
            relevance_breakdown=CASE
                WHEN explore_profile_candidates.judge_status='pending' THEN excluded.relevance_breakdown
                ELSE explore_profile_candidates.relevance_breakdown
            END,
            judge_reason=CASE
                WHEN explore_profile_candidates.judge_status='pending' THEN excluded.judge_reason
                ELSE explore_profile_candidates.judge_reason
            END,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            profile_id,
            actual_id,
            gate_status,
            judge_status,
            summary_status,
            score,
            0 if score == 0 else None,
            0 if score == 0 else None,
            "unknown" if score == 0 else None,
            _json(breakdown),
            reason,
        ),
    )
    for source in candidate.get("sources") or []:
        source_name = str(source.get("source") or "").strip()
        if source_name:
            conn.execute(
                """
                INSERT OR IGNORE INTO explore_discoveries
                    (profile_id, candidate_id, source, discovered_on)
                VALUES (?, ?, ?, ?)
                """,
                (profile_id, actual_id, source_name, discovered_on.isoformat()),
            )
    return get_explore_candidate(conn, profile_id, actual_id)


def get_explore_candidate(conn: sqlite3.Connection, profile_id: str, candidate_id: str) -> dict:
    row = conn.execute(
        """
        SELECT ec.*, epc.gate_status, epc.judge_status, epc.summary_status,
               epc.judge_score, epc.topic_relevance_score, epc.practicality_score,
               epc.topic_bucket, epc.relevance_breakdown,
               epc.judge_reason AS profile_judge_reason, epc.judge_reason_en,
               epc.triage_status, epc.analysis_updated_at, epc.discovered_at,
               epc.updated_at AS profile_updated_at
        FROM explore_candidates ec
        JOIN explore_profile_candidates epc ON epc.candidate_id = ec.id
        WHERE epc.profile_id = ? AND ec.id = ?
        """,
        (profile_id, candidate_id),
    ).fetchone()
    if row is None:
        raise ValueError("探索候选不存在")
    result = dict(row)
    for key, default in (
        ("authors", []),
        ("categories", []),
        ("code_meta", {}),
        ("highlights_zh", []),
        ("highlights_en", []),
        ("related_methods_zh", []),
        ("related_methods_en", []),
        ("relevance_breakdown", {}),
    ):
        result[key] = _loads(result.get(key), default)
    result["judge_reason"] = result.pop("profile_judge_reason") or result.get("judge_reason") or ""
    result["relevance_score"] = result.get("judge_score")
    result["topic"] = result.get("topic_bucket") or result.get("topic")
    sources = []
    for source in conn.execute(
        """
        SELECT source, source_rank, first_seen_at, metadata
        FROM explore_candidate_sources
        WHERE candidate_id = ?
        ORDER BY source
        """,
        (candidate_id,),
    ).fetchall():
        item = dict(source)
        item["metadata"] = _loads(item.get("metadata"), {})
        sources.append(item)
    result["sources"] = sources
    result["watched_author"] = any(source["source"] == "arxiv_authors" for source in sources)
    result["ranking_score"] = ranking_score(result.get("relevance_score"), result.get("heat_score") or 0)
    return result


def list_explore_candidates(
    conn: sqlite3.Connection,
    profile_id: str = "explore_default",
    *,
    source: Optional[str] = None,
    topic: Optional[str] = None,
    triage_status: Optional[str] = None,
    query: Optional[str] = None,
    include_rejected: bool = True,
    limit: int = 100,
) -> list[dict]:
    get_explore_profile(conn, profile_id)
    if triage_status and triage_status not in EXPLORE_TRIAGE_STATES:
        raise ValueError("无效的探索 triage 状态")
    sql = """
        SELECT ec.id
        FROM explore_candidates ec
        JOIN explore_profile_candidates epc ON epc.candidate_id = ec.id
        WHERE epc.profile_id = ?
    """
    params: list[object] = [profile_id]
    if source:
        sql += """
            AND EXISTS (
                SELECT 1 FROM explore_candidate_sources ecs
                WHERE ecs.candidate_id=ec.id AND ecs.source=?
            )
        """
        params.append(source)
    if topic:
        sql += " AND epc.topic_bucket = ?"
        params.append(topic)
    if triage_status:
        sql += " AND epc.triage_status = ?"
        params.append(triage_status)
    if query:
        sql += " AND (ec.title LIKE ? OR ec.abstract LIKE ?)"
        term = f"%{query}%"
        params.extend([term, term])
    if not include_rejected:
        sql += " AND epc.judge_score IS NOT NULL AND epc.gate_status != 'rejected'"
    sql += """
        ORDER BY
            COALESCE(epc.judge_score, 0) * 30 + ec.heat_score DESC,
            ec.heat_score DESC,
            ec.title COLLATE NOCASE
        LIMIT ?
    """
    params.append(limit)
    ids = [row["id"] for row in conn.execute(sql, params).fetchall()]
    return [get_explore_candidate(conn, profile_id, candidate_id) for candidate_id in ids]


def scan_explore(
    conn: sqlite3.Connection,
    profile_id: str = "explore_default",
    *,
    fetcher: Optional[Callable[..., list[dict]]] = None,
    source_fetchers: Optional[dict[str, Callable[[], list[dict]]]] = None,
    max_results: int = 100,
    target_date: Optional[date] = None,
) -> dict:
    if max_results < 1 or max_results > 500:
        raise ValueError("探索抓取数量必须在 1 到 500 之间")
    profile = get_explore_profile(conn, profile_id)
    target = target_date or explore_target_date()
    runtime = get_explore_runtime_config()
    if source_fetchers is None:
        if fetcher:
            source_fetchers = {
                "arxiv": lambda: fetcher(profile["categories"], max_results=max_results)
            }
        else:
            source_fetchers = {}
            if runtime["arxiv_enabled"]:
                source_fetchers["arxiv"] = lambda: run_source(
                    fetch_arxiv_daily(
                        profile["categories"],
                        max_results=max_results,
                        target_date=target,
                    )
                )
            if runtime["hf_daily_enabled"]:
                historical_ids = (
                    MILESTONE_TRENDING_IDS
                    if runtime["include_historical_milestones"]
                    else frozenset()
                )
                source_fetchers["hf_daily"] = lambda: run_source(
                    fetch_hf_daily(
                        max_results=max_results,
                        target_date=target,
                        include_trending=runtime["hf_trending_enabled"],
                        trending_max_age_days=runtime["hf_trending_max_age_days"],
                        historical_milestone_ids=historical_ids,
                    )
                )
            if runtime["watched_authors_enabled"]:
                source_fetchers["arxiv_authors"] = lambda: run_source(
                    fetch_watched_authors(
                        categories=profile["categories"],
                        target_date=target,
                        window_days=runtime["watched_authors_window_days"],
                    )
                )
            if runtime["openreview_enabled"]:
                source_fetchers["openreview"] = lambda: run_source(
                    fetch_openreview(
                        target_date=target,
                        venues=tuple(runtime["openreview_venues"]),
                        window_days=runtime["openreview_window_days"],
                        max_pages=runtime["openreview_max_pages"],
                    )
                )
    if not source_fetchers:
        raise ValueError("至少启用一个探索来源")
    raw_candidates: list[dict] = []
    source_counts: dict[str, int] = {}
    source_errors: dict[str, str] = {}
    for source, source_fetcher in source_fetchers.items():
        try:
            candidates = source_fetcher()
        except Exception as exc:
            source_errors[source] = f"{type(exc).__name__}: {exc}"
            continue
        source_counts[source] = len(candidates)
        for position, candidate in enumerate(candidates, start=1):
            item = dict(candidate)
            item["arxiv_id"] = _canonical_id(item.get("arxiv_id"))
            item["source"] = source
            if source == "hf_daily":
                rank = (item.get("source_metadata") or {}).get("trending_rank")
                item["source_rank"] = rank if isinstance(rank, int) else None
            else:
                item["source_rank"] = item.get("source_rank")
            if item["arxiv_id"]:
                raw_candidates.append(item)
    if not source_counts:
        raise RuntimeError("所有探索来源均采集失败")
    merged = merge_candidates(raw_candidates)
    status_counts = {"prefilter_passed": 0, "rejected": 0, "skipped": 0}
    for candidate in merged:
        stored = _store_candidate(conn, profile_id, candidate, discovered_on=target)
        gate_status = stored["gate_status"]
        if gate_status in status_counts:
            status_counts[gate_status] += 1
    conn.commit()
    return {
        "profile_id": profile_id,
        "target_date": target.isoformat(),
        "status": "partial" if source_errors else "success",
        "candidate_count": len(raw_candidates),
        "stored_count": len(merged),
        "source_counts": source_counts,
        "source_errors": source_errors,
        "prefilter": status_counts,
    }


def _recent_milestone_ids(
    conn: sqlite3.Connection,
    profile_id: str,
    target: date,
) -> frozenset[str]:
    cutoff = (target - timedelta(days=MILESTONE_COOLDOWN_DAYS)).isoformat()
    rows = conn.execute(
        """
        SELECT ec.arxiv_id
        FROM explore_milestone_surfaces ems
        JOIN explore_candidates ec ON ec.id=ems.candidate_id
        WHERE ems.profile_id=? AND ems.surfaced_on>=? AND ems.surfaced_on<?
        """,
        (profile_id, cutoff, target.isoformat()),
    ).fetchall()
    return frozenset(row["arxiv_id"] for row in rows)


def _persist_judge_result(
    conn: sqlite3.Connection,
    profile_id: str,
    candidate_id: str,
    result: dict,
    *,
    judge_status: str = "completed",
) -> None:
    breakdown = normalize_breakdown(result)
    relevance = composite_relevance(result)
    conn.execute(
        """
        UPDATE explore_profile_candidates
        SET gate_status=?, judge_status=?, summary_status=?,
            judge_score=?, topic_relevance_score=?, practicality_score=?,
            topic_bucket=?, relevance_breakdown=?, judge_reason=?,
            analysis_updated_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
        WHERE profile_id=? AND candidate_id=?
        """,
        (
            "rejected" if result.get("hard_gate") else "passed",
            judge_status,
            "skipped" if result.get("hard_gate") else "pending",
            relevance,
            breakdown.get("topic_relevance"),
            breakdown.get("practicality"),
            breakdown.get("topic_bucket"),
            _json(breakdown),
            str(result.get("reason") or ""),
            profile_id,
            candidate_id,
        ),
    )


def judge_explore_candidate(
    conn: sqlite3.Connection,
    profile_id: str,
    candidate_id: str,
    *,
    model: Optional[str] = None,
    client=None,
    force: bool = False,
    sleep: Callable[[float], None] | None = None,
) -> dict:
    candidate = get_explore_candidate(conn, profile_id, candidate_id)
    if candidate["judge_status"] == "completed" and not force:
        return candidate
    if not candidate["title"].strip() or not candidate["abstract"].strip():
        conn.execute(
            """
            UPDATE explore_profile_candidates
            SET gate_status='skipped', judge_status='skipped', summary_status='skipped',
                judge_score=NULL, judge_reason='skipped: missing title/abstract',
                updated_at=CURRENT_TIMESTAMP
            WHERE profile_id=? AND candidate_id=?
            """,
            (profile_id, candidate_id),
        )
        conn.commit()
        return get_explore_candidate(conn, profile_id, candidate_id)
    profile = get_explore_profile(conn, profile_id)
    should_gate, _, blacklist_hits = prefilter_verdict(
        candidate["title"],
        candidate["abstract"],
        whitelist=(*PREFILTER_WHITELIST, *profile.get("include_keywords", [])),
        blacklist=(*PREFILTER_BLACKLIST, *profile.get("exclude_keywords", [])),
    )
    if should_gate:
        _persist_judge_result(
            conn,
            profile_id,
            candidate_id,
            prefilter_hard_gate_result(blacklist_hits),
        )
        conn.commit()
        return get_explore_candidate(conn, profile_id, candidate_id)
    conn.execute(
        """
        UPDATE explore_profile_candidates
        SET judge_status='running', updated_at=CURRENT_TIMESTAMP
        WHERE profile_id=? AND candidate_id=?
        """,
        (profile_id, candidate_id),
    )
    conn.commit()
    try:
        llm = client or get_client()
        call_kwargs = {
            "client": llm,
            "model": model or get_default_model(),
            "system": load_prompt("explore_relevance.md"),
            "user": f"Title: {candidate['title']}\n\nAbstract: {candidate['abstract']}",
            "max_tokens": 1024,
        }
        if sleep is not None:
            call_kwargs["sleep"] = sleep
        result = call_json(**call_kwargs)
        judge_status = "completed"
    except Exception as exc:
        result = judge_unavailable_result(exc)
        judge_status = "failed"
    override = milestone_override(
        candidate["arxiv_id"],
        candidate["sources"],
        candidate["code_meta"],
        _recent_milestone_ids(conn, profile_id, explore_target_date()),
    )
    if override is not None:
        result = override
        judge_status = "completed"
    _persist_judge_result(
        conn,
        profile_id,
        candidate_id,
        result,
        judge_status=judge_status,
    )
    conn.commit()
    return get_explore_candidate(conn, profile_id, candidate_id)


def _clean_related(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        output.append(
            {
                "name": str(item.get("name") or "").strip(),
                "relation": str(item.get("relation") or "").strip(),
                "arxiv_id": item.get("arxiv_id") or None,
            }
        )
    return output[:3]


def summarize_explore_candidate(
    conn: sqlite3.Connection,
    profile_id: str,
    candidate_id: str,
    *,
    model: Optional[str] = None,
    client=None,
    force: bool = False,
    sleep: Callable[[float], None] | None = None,
) -> dict:
    candidate = get_explore_candidate(conn, profile_id, candidate_id)
    watched = candidate["watched_author"]
    passed = candidate.get("relevance_score") is not None and not (
        candidate.get("relevance_breakdown") or {}
    ).get("hard_gate", False)
    if not passed and not watched:
        return candidate
    if candidate["summary_status"] == "completed" and not force:
        return candidate
    conn.execute(
        """
        UPDATE explore_profile_candidates
        SET summary_status='running', updated_at=CURRENT_TIMESTAMP
        WHERE profile_id=? AND candidate_id=?
        """,
        (profile_id, candidate_id),
    )
    conn.commit()
    breakdown = candidate.get("relevance_breakdown") or {}
    user = (
        f"Title: {candidate['title']}\n\n"
        f"Abstract: {candidate['abstract']}\n\n"
        "Chinese fields to translate (write English siblings, do not re-evaluate):\n"
        f"- relevance_reason: {candidate.get('judge_reason') or ''}\n"
        f"- calibration_cost: {breakdown.get('calibration_cost') or ''}\n"
        f"- inference_perf: {breakdown.get('inference_perf') or ''}"
    )
    try:
        call_kwargs = {
            "client": client or get_client(),
            "model": model or get_default_model(),
            "system": load_prompt("explore_summary.md"),
            "user": user,
            "max_tokens": 3000,
        }
        if sleep is not None:
            call_kwargs["sleep"] = sleep
        result = call_json(**call_kwargs)
        if "calibration_cost_en" in result:
            breakdown["calibration_cost_en"] = result.get("calibration_cost_en")
        if "inference_perf_en" in result:
            breakdown["inference_perf_en"] = result.get("inference_perf_en")
        conn.execute(
            """
            UPDATE explore_candidates
            SET summary_zh=?, summary_en=?, highlights_zh=?, highlights_en=?,
                related_methods_zh=?, related_methods_en=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                result.get("summary"),
                result.get("summary_en"),
                _json(result.get("highlights") or []),
                _json(result.get("highlights_en") or []),
                _json(_clean_related(result.get("related_methods"))),
                _json(_clean_related(result.get("related_methods_en"))),
                candidate_id,
            ),
        )
        conn.execute(
            """
            UPDATE explore_profile_candidates
            SET summary_status='completed', relevance_breakdown=?,
                judge_reason_en=?, updated_at=CURRENT_TIMESTAMP
            WHERE profile_id=? AND candidate_id=?
            """,
            (
                _json(breakdown),
                result.get("relevance_reason_en"),
                profile_id,
                candidate_id,
            ),
        )
    except Exception as exc:
        conn.execute(
            """
            UPDATE explore_profile_candidates
            SET summary_status='failed', updated_at=CURRENT_TIMESTAMP
            WHERE profile_id=? AND candidate_id=?
            """,
            (profile_id, candidate_id),
        )
        conn.commit()
        return get_explore_candidate(conn, profile_id, candidate_id)
    conn.commit()
    return get_explore_candidate(conn, profile_id, candidate_id)


def analyze_explore_candidate(
    conn: sqlite3.Connection,
    profile_id: str,
    candidate_id: str,
    **kwargs,
) -> dict:
    candidate = judge_explore_candidate(
        conn,
        profile_id,
        candidate_id,
        **kwargs,
    )
    if candidate["gate_status"] == "passed" or candidate["watched_author"]:
        candidate = summarize_explore_candidate(
            conn,
            profile_id,
            candidate_id,
            **kwargs,
        )
    return candidate


def analyze_pending_explore_candidates(
    conn: sqlite3.Connection,
    profile_id: str = "explore_default",
    *,
    limit: int = 20,
    model: Optional[str] = None,
    client=None,
) -> dict:
    if limit < 1 or limit > 100:
        raise ValueError("批量分析数量必须在 1 到 100 之间")
    rows = conn.execute(
        """
        SELECT candidate_id
        FROM explore_profile_candidates
        WHERE profile_id=? AND judge_status IN ('pending', 'failed')
        ORDER BY discovered_at, candidate_id
        LIMIT ?
        """,
        (profile_id, limit),
    ).fetchall()
    completed = 0
    rejected = 0
    failed = 0
    summary_failed = 0
    errors: list[dict] = []
    for row in rows:
        candidate_id = row["candidate_id"]
        try:
            result = analyze_explore_candidate(
                conn,
                profile_id,
                candidate_id,
                model=model,
                client=client,
                force=True,
            )
        except Exception as exc:
            failed += 1
            errors.append(
                {
                    "candidate_id": candidate_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        if result["judge_status"] == "failed":
            failed += 1
        elif result["gate_status"] == "rejected":
            rejected += 1
        else:
            completed += 1
            if result["summary_status"] == "failed":
                summary_failed += 1
    remaining = conn.execute(
        """
        SELECT COUNT(*)
        FROM explore_profile_candidates
        WHERE profile_id=? AND judge_status IN ('pending', 'failed')
        """,
        (profile_id,),
    ).fetchone()[0]
    return {
        "profile_id": profile_id,
        "requested": len(rows),
        "completed": completed,
        "rejected": rejected,
        "failed": failed,
        "summary_failed": summary_failed,
        "remaining": remaining,
        "errors": errors,
    }


def get_explore_digest(
    conn: sqlite3.Connection,
    profile_id: str = "explore_default",
    digest_date: Optional[str] = None,
) -> dict:
    target = date.fromisoformat(digest_date) if digest_date else explore_target_date()
    all_candidates = list_explore_candidates(
        conn,
        profile_id,
        include_rejected=True,
        limit=500,
    )
    discovery_sources: dict[str, set[str]] = {}
    for row in conn.execute(
        """
        SELECT candidate_id, source
        FROM explore_discoveries
        WHERE profile_id=? AND discovered_on=?
        """,
        (profile_id, target.isoformat()),
    ).fetchall():
        discovery_sources.setdefault(row["candidate_id"], set()).add(row["source"])
    discovered_ids = set(discovery_sources)
    runtime = get_explore_runtime_config()
    hf_cutoff = target - timedelta(days=runtime["hf_trending_max_age_days"])

    def belongs_to_digest(item: dict) -> bool:
        published_raw = item.get("published_date") or ""
        try:
            published = date.fromisoformat(published_raw[:10])
        except ValueError:
            published = None
        if item["id"] not in discovered_ids:
            return not discovered_ids and published == target
        sources = discovery_sources[item["id"]]
        if sources != {"hf_daily"}:
            return True
        if published is None or published > target:
            return False
        return (
            published >= hf_cutoff
            or runtime["include_historical_milestones"]
            and item.get("arxiv_id") in MILESTONE_TRENDING_IDS
        )

    daily = [
        item
        for item in all_candidates
        if belongs_to_digest(item)
    ]
    scored = [
        item
        for item in daily
        if item.get("relevance_score") is not None
        and not (item.get("relevance_breakdown") or {}).get("hard_gate", False)
    ]
    surviving = sort_candidates(scored)
    watched = sort_candidates([item for item in daily if item["watched_author"]])
    watched_ids = {item["id"] for item in watched}
    grouped = group_with_caps(
        [item for item in surviving if item["id"] not in watched_ids],
        TOPIC_CAPS,
    )
    spotlight = watched + [
        item
        for bucket in BUCKET_ORDER
        for item in grouped[bucket]
    ]
    topic_counts = {
        bucket: len(items)
        for bucket, items in grouped.items()
        if items
    }
    source_counts: dict[str, int] = {}
    for item in daily:
        for source in {source["source"] for source in item["sources"]}:
            source_counts[source] = source_counts.get(source, 0) + 1
    for item in spotlight:
        breakdown = item.get("relevance_breakdown") or {}
        if (
            str(item.get("judge_reason") or "").startswith("milestone-override:")
            and breakdown.get("topic_bucket") == "trending"
            and breakdown.get("hard_gate") is False
        ):
            conn.execute(
                """
                INSERT OR IGNORE INTO explore_milestone_surfaces
                    (profile_id, candidate_id, surfaced_on)
                VALUES (?, ?, ?)
                """,
                (profile_id, item["id"], target.isoformat()),
            )
    conn.commit()
    return {
        "profile_id": profile_id,
        "digest_date": target.isoformat(),
        "period": "daily",
        "summary": (
            f"今日精选 {len(spotlight)} 篇，来自 {len(source_counts)} 个来源。"
            if spotlight
            else "今日没有已通过 Judge 的精选论文。"
        ),
        "scanned_count": len(daily),
        "surviving_count": len(surviving),
        "highlighted_count": len(spotlight),
        "watched": watched,
        "buckets": [
            {
                "id": bucket,
                "title": BUCKET_TITLES[bucket],
                "cap": TOPIC_CAPS[bucket],
                "papers": grouped[bucket],
            }
            for bucket in BUCKET_ORDER
            if grouped[bucket]
        ],
        "topic_counts": topic_counts,
        "source_counts": source_counts,
        "spotlight": spotlight,
        "generated_at": target.isoformat(),
    }


def get_explore_trends(
    conn: sqlite3.Connection,
    profile_id: str = "explore_default",
    days: int = 30,
) -> dict:
    if days < 7 or days > 180:
        raise ValueError("趋势周期必须在 7 到 180 天之间")
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    candidates = list_explore_candidates(
        conn,
        profile_id,
        include_rejected=False,
        limit=500,
    )
    series: dict[str, dict[str, int]] = {}
    for item in candidates:
        day = str(item.get("published_date") or item.get("discovered_at") or "")[:10]
        if day < cutoff:
            continue
        bucket = item.get("topic_bucket")
        if bucket not in BUCKET_ORDER:
            continue
        values = series.setdefault(day, {})
        values[bucket] = values.get(bucket, 0) + 1
    totals: dict[str, int] = {}
    for values in series.values():
        for bucket, count in values.items():
            totals[bucket] = totals.get(bucket, 0) + count
    return {"profile_id": profile_id, "days": days, "series": series, "topics": totals}


def get_explore_rollup(
    conn: sqlite3.Connection,
    profile_id: str = "explore_default",
    *,
    start_date: str,
    end_date: str,
    require_complete: bool = False,
) -> dict:
    """按参考仓库 weekly/rollup 语义聚合已完成的 Explore 结果。

    SQLite 中每个候选只保留一条 profile 结果，因此天然完成按 paper ID 去重。
    `require_complete` 用于 monthly/long cadence，要求窗口内每天都有发现记录。
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("rollup 起始日期不能晚于结束日期")
    get_explore_profile(conn, profile_id)
    rows = conn.execute(
        """
        SELECT ec.id
        FROM explore_candidates ec
        JOIN explore_profile_candidates epc ON epc.candidate_id = ec.id
        WHERE epc.profile_id=?
          AND epc.judge_score IS NOT NULL
          AND epc.gate_status != 'rejected'
          AND date(COALESCE(ec.published_date, substr(epc.discovered_at, 1, 10))) BETWEEN ? AND ?
        """,
        (profile_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    papers = [get_explore_candidate(conn, profile_id, row["id"]) for row in rows]
    by_bucket = {bucket: [] for bucket in BUCKET_ORDER}
    for paper in papers:
        bucket = paper.get("topic_bucket")
        if bucket in by_bucket:
            by_bucket[bucket].append(paper)
    for bucket in by_bucket:
        by_bucket[bucket] = sorted(
            by_bucket[bucket],
            key=lambda item: (
                -(item.get("relevance_score") or 0),
                -(item.get("heat_score") or 0),
            ),
        )
    missing_days = []
    cursor = start
    while cursor <= end:
        day = cursor.isoformat()
        exists = conn.execute(
            """
            SELECT 1
            FROM explore_candidates ec
            JOIN explore_profile_candidates epc ON epc.candidate_id=ec.id
            WHERE epc.profile_id=? AND substr(epc.discovered_at, 1, 10)=?
            LIMIT 1
            """,
            (profile_id, day),
        ).fetchone()
        if exists is None:
            missing_days.append(day)
        cursor += timedelta(days=1)
    if require_complete and missing_days:
        raise ValueError(f"rollup 缺少每日采集结果: {', '.join(missing_days)}")
    return {
        "profile_id": profile_id,
        "period": "rollup",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "require_complete": require_complete,
        "missing_days": missing_days,
        "papers": papers,
        "buckets": [
            {
                "id": bucket,
                "title": BUCKET_TITLES[bucket],
                "papers": by_bucket[bucket],
            }
            for bucket in BUCKET_ORDER
            if by_bucket[bucket]
        ],
        "paper_count": len(papers),
    }


def transition_explore_triage(
    conn: sqlite3.Connection,
    profile_id: str,
    candidate_id: str,
    status: str,
) -> dict:
    if status not in EXPLORE_TRIAGE_STATES:
        raise ValueError("无效的探索 triage 状态")
    get_explore_candidate(conn, profile_id, candidate_id)
    conn.execute(
        """
        UPDATE explore_profile_candidates
        SET triage_status=?, updated_at=CURRENT_TIMESTAMP
        WHERE profile_id=? AND candidate_id=?
        """,
        (status, profile_id, candidate_id),
    )
    conn.commit()
    return get_explore_candidate(conn, profile_id, candidate_id)
