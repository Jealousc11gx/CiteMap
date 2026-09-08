"""论文雷达本地存储、状态机与离线操作队列。"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import sqlite3

import arxiv
import feedparser
import requests

from .database import get_connection

DEFAULT_RADAR_CATEGORIES = ["cs.AI"]
ARXIV_CATEGORY_PREFIXES = {
    "cs", "econ", "eess", "hep-ex", "hep-lat", "hep-ph", "hep-th", "math",
    "nlin", "nucl-ex", "nucl-th", "physics", "q-bio", "q-fin", "quant-ph", "stat",
    "astro-ph", "cond-mat", "gr-qc", "adap-org", "cmp-lg", "comp-gas", "funct-an",
    "q-alg", "q-hum", "solv-int", "supr-con", "alg-geom", "dg-ga", "patt-sol",
}


def validate_radar_categories(categories: Optional[list[str]]) -> list[str]:
    normalized = [str(value).strip() for value in (categories or []) if str(value).strip()]
    if not normalized:
        return list(DEFAULT_RADAR_CATEGORIES)
    invalid = []
    for category in normalized:
        prefix, separator, suffix = category.partition(".")
        if not separator or prefix.casefold() not in ARXIV_CATEGORY_PREFIXES or not suffix or not suffix.replace("-", "").isalnum():
            invalid.append(category)
    if invalid:
        raise ValueError(f"无效的 arXiv categories: {', '.join(invalid)}。示例：cs.AI、cs.CV、stat.ML")
    return normalized


RADAR_STATES = {"unread", "read", "saved", "dismissed"}
RADAR_OPERATIONS = {"read", "save", "dismiss"}
STATE_PRIORITY = {"unread": 0, "read": 1, "dismissed": 2, "saved": 3}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads(value: Optional[str], default: object) -> object:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def get_radar_config(conn: sqlite3.Connection, project_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM radar_configs WHERE project_id = ?", (project_id,)
    ).fetchone()
    if row is None:
        return {
            "project_id": project_id,
            "enabled": False,
            "categories": list(DEFAULT_RADAR_CATEGORIES),
            "include_keywords": [],
            "exclude_keywords": [],
            "profile_override": "",
            "anchor_paper_ids": [],
            "top_k": 10,
            "min_score": 0.0,
            "include_cross_list": True,
            "send_empty": False,
            "fetch_limit": 100,
            "debug": False,
            "compute_mode": "cloud",
            "updated_at": None,
        }
    result = dict(row)
    for key in ("categories", "include_keywords", "exclude_keywords", "anchor_paper_ids"):
        result[key] = _loads(result[key], [])
    for key in ("enabled", "include_cross_list", "send_empty", "debug"):
        result[key] = bool(result.get(key, 0))
    result["fetch_limit"] = int(result.get("fetch_limit") or 100)
    return result


def upsert_radar_config(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    enabled: bool = False,
    categories: Optional[list[str]] = None,
    include_keywords: Optional[list[str]] = None,
    exclude_keywords: Optional[list[str]] = None,
    profile_override: str = "",
    anchor_paper_ids: Optional[list[str]] = None,
    top_k: int = 10,
    min_score: float = 0.0,
    include_cross_list: bool = True,
    send_empty: bool = False,
    fetch_limit: int = 100,
    debug: bool = False,
    compute_mode: str = "cloud",
) -> dict:
    if top_k < 1:
        raise ValueError("雷达 Top K 必须大于 0")
    if min_score < 0:
        raise ValueError("雷达最低分数不能小于 0")
    if fetch_limit < 1 or fetch_limit > 500:
        raise ValueError("雷达抓取数量必须在 1 到 500 之间")
    if compute_mode not in {"cloud", "local", "hybrid"}:
        raise ValueError("雷达计算模式必须是 cloud、local 或 hybrid")
    categories = validate_radar_categories(categories)
    conn.execute(
        """
        INSERT INTO radar_configs (
            project_id, enabled, categories, include_keywords, exclude_keywords,
            profile_override, anchor_paper_ids, top_k, min_score, include_cross_list,
            send_empty, fetch_limit, debug, compute_mode, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(project_id) DO UPDATE SET
            enabled=excluded.enabled,
            categories=excluded.categories,
            include_keywords=excluded.include_keywords,
            exclude_keywords=excluded.exclude_keywords,
            profile_override=excluded.profile_override,
            anchor_paper_ids=excluded.anchor_paper_ids,
            top_k=excluded.top_k,
            min_score=excluded.min_score,
            include_cross_list=excluded.include_cross_list,
            send_empty=excluded.send_empty,
            fetch_limit=excluded.fetch_limit,
            debug=excluded.debug,
            compute_mode=excluded.compute_mode,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            project_id,
            int(enabled),
            _json(categories),
            _json(include_keywords or []),
            _json(exclude_keywords or []),
            profile_override.strip(),
            _json(anchor_paper_ids or []),
            top_k,
            min_score,
            int(include_cross_list),
            int(send_empty),
            fetch_limit,
            int(debug),
            compute_mode,
        ),
    )
    conn.commit()
    return get_radar_config(conn, project_id)


def create_radar_run(conn: sqlite3.Connection, project_id: str, run_date: str) -> str:
    run_id = f"radar_run_{uuid.uuid4().hex}"
    conn.execute(
        """
        INSERT INTO radar_runs (id, project_id, run_date, status)
        VALUES (?, ?, ?, 'running')
        ON CONFLICT(project_id, run_date) DO UPDATE SET
            status='running', error=NULL, started_at=CURRENT_TIMESTAMP, finished_at=NULL
        """,
        (run_id, project_id, run_date),
    )
    row = conn.execute(
        "SELECT id FROM radar_runs WHERE project_id = ? AND run_date = ?",
        (project_id, run_date),
    ).fetchone()
    conn.commit()
    return str(row["id"])


def finish_radar_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    status: str,
    candidate_count: int = 0,
    matched_count: int = 0,
    error: Optional[str] = None,
) -> None:
    if status not in {"success", "failed", "skipped"}:
        raise ValueError("无效的雷达运行状态")
    conn.execute(
        """
        UPDATE radar_runs
        SET status=?, candidate_count=?, matched_count=?, error=?, finished_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (status, candidate_count, matched_count, error, run_id),
    )
    conn.commit()


def upsert_radar_candidate(conn: sqlite3.Connection, candidate: dict) -> dict:
    arxiv_id = str(candidate["arxiv_id"]).strip()
    candidate_id = str(candidate.get("id") or f"radar_candidate_{arxiv_id.replace('/', '_')}")
    conn.execute(
        """
        INSERT INTO radar_candidates (
            id, arxiv_id, title, abstract, authors, categories, affiliations, corresponding_authors, published_date,
            updated_date, arxiv_url, pdf_url, tldr, ai_summary, title_zh,
            abstract_zh, core_contribution, method, result, limitations
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(arxiv_id) DO UPDATE SET
            title=excluded.title,
            abstract=excluded.abstract,
            authors=excluded.authors,
            categories=excluded.categories,
            affiliations=excluded.affiliations,
            corresponding_authors=excluded.corresponding_authors,
            published_date=excluded.published_date,
            updated_date=excluded.updated_date,
            arxiv_url=excluded.arxiv_url,
            pdf_url=excluded.pdf_url,
            tldr=COALESCE(excluded.tldr, radar_candidates.tldr),
            ai_summary=COALESCE(excluded.ai_summary, radar_candidates.ai_summary),
            title_zh=COALESCE(excluded.title_zh, radar_candidates.title_zh),
            abstract_zh=COALESCE(excluded.abstract_zh, radar_candidates.abstract_zh),
            core_contribution=COALESCE(excluded.core_contribution, radar_candidates.core_contribution),
            method=COALESCE(excluded.method, radar_candidates.method),
            result=COALESCE(excluded.result, radar_candidates.result),
            limitations=COALESCE(excluded.limitations, radar_candidates.limitations)
        """,
        (
            candidate_id,
            arxiv_id,
            candidate.get("title", ""),
            candidate.get("abstract", ""),
            _json(candidate.get("authors") or []),
            _json(candidate.get("categories") or []),
            _json(candidate.get("affiliations") or []),
            _json(candidate.get("corresponding_authors") or []),
            candidate.get("published_date"),
            candidate.get("updated_date"),
            candidate.get("arxiv_url") or f"https://arxiv.org/abs/{arxiv_id}",
            candidate.get("pdf_url"),
            candidate.get("tldr"), candidate.get("ai_summary"), candidate.get("title_zh"),
            candidate.get("abstract_zh"), candidate.get("core_contribution"), candidate.get("method"),
            candidate.get("result"), candidate.get("limitations"),
        ),
    )
    row = conn.execute("SELECT * FROM radar_candidates WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
    return dict(row)


def upsert_radar_match(
    conn: sqlite3.Connection,
    project_id: str,
    candidate_id: str,
    *,
    score: float = 0.0,
    reason: str = "",
    run_id: Optional[str] = None,
) -> dict:
    match_id = f"radar_match_{uuid.uuid4().hex}"
    conn.execute(
        """
        INSERT INTO radar_matches (id, project_id, candidate_id, run_id, score, reason)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, candidate_id) DO UPDATE SET
            run_id=excluded.run_id,
            score=excluded.score,
            reason=excluded.reason,
            updated_at=CURRENT_TIMESTAMP
        """,
        (match_id, project_id, candidate_id, run_id, score, reason),
    )
    row = conn.execute(
        """
        SELECT rm.*, rc.arxiv_id, rc.title, rc.abstract, rc.authors, rc.categories,
               rc.affiliations, rc.corresponding_authors,
               rc.published_date, rc.updated_date, rc.arxiv_url, rc.pdf_url,
               rc.tldr, rc.ai_summary, rc.title_zh, rc.abstract_zh, rc.core_contribution,
               rc.method, rc.result, rc.limitations
        FROM radar_matches rm
        JOIN radar_candidates rc ON rc.id = rm.candidate_id
        WHERE rm.project_id = ? AND rm.candidate_id = ?
        """,
        (project_id, candidate_id),
    ).fetchone()
    conn.commit()
    return dict(row)


def list_radar_matches(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    state: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    if state is not None and state not in RADAR_STATES:
        raise ValueError("无效的雷达状态")
    sql = """
        SELECT rm.*, rc.arxiv_id, rc.title, rc.abstract, rc.authors, rc.categories,
               rc.affiliations, rc.corresponding_authors,
               rc.published_date, rc.updated_date, rc.arxiv_url, rc.pdf_url,
               rc.tldr, rc.ai_summary, rc.title_zh, rc.abstract_zh, rc.core_contribution,
               rc.method, rc.result, rc.limitations
        FROM radar_matches rm
        JOIN radar_candidates rc ON rc.id = rm.candidate_id
        WHERE rm.project_id = ?
    """
    params: list[object] = [project_id]
    if state:
        sql += " AND rm.state = ?"
        params.append(state)
    sql += " ORDER BY rm.created_at DESC, rm.score DESC LIMIT ?"
    params.append(limit)
    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    for row in rows:
        for field in ("authors", "categories", "affiliations", "corresponding_authors"):
            row[field] = _loads(row.get(field), [])
    return rows


def transition_radar_state(conn: sqlite3.Connection, match_id: str, state: str) -> dict:
    if state not in RADAR_STATES:
        raise ValueError("无效的雷达状态")
    row = conn.execute("SELECT state FROM radar_matches WHERE id = ?", (match_id,)).fetchone()
    if row is None:
        raise ValueError("雷达匹配不存在")
    current = row["state"]
    if STATE_PRIORITY[state] < STATE_PRIORITY[current]:
        state = current
    conn.execute(
        "UPDATE radar_matches SET state=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (state, match_id),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM radar_matches WHERE id = ?", (match_id,)).fetchone())


def get_radar_sync_cursor(conn: sqlite3.Connection, key: str = "default") -> Optional[str]:
    row = conn.execute("SELECT value FROM radar_sync_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_radar_sync_cursor(conn: sqlite3.Connection, value: str, key: str = "default") -> None:
    conn.execute(
        """
        INSERT INTO radar_sync_state (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
        """,
        (key, value),
    )
    conn.commit()


def enqueue_radar_operation(
    conn: sqlite3.Connection,
    project_id: str,
    match_id: str,
    operation: str,
) -> dict:
    if operation not in RADAR_OPERATIONS:
        raise ValueError("无效的雷达离线操作")
    operation_id = f"radar_op_{uuid.uuid4().hex}"
    conn.execute(
        """
        INSERT INTO radar_pending_operations (id, project_id, match_id, operation)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(match_id, operation) DO NOTHING
        """,
        (operation_id, project_id, match_id, operation),
    )
    row = conn.execute(
        "SELECT * FROM radar_pending_operations WHERE match_id=? AND operation=?",
        (match_id, operation),
    ).fetchone()
    conn.commit()
    return dict(row)


def list_pending_radar_operations(
    conn: sqlite3.Connection, project_id: Optional[str] = None, limit: int = 100
) -> list[dict]:
    if project_id:
        rows = conn.execute(
            "SELECT * FROM radar_pending_operations WHERE project_id=? ORDER BY created_at LIMIT ?",
            (project_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM radar_pending_operations ORDER BY created_at LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def mark_radar_operation_result(
    conn: sqlite3.Connection,
    operation_id: str,
    *,
    success: bool,
    error: Optional[str] = None,
) -> None:
    if success:
        conn.execute("DELETE FROM radar_pending_operations WHERE id = ?", (operation_id,))
    else:
        conn.execute(
            """
            UPDATE radar_pending_operations
            SET retry_count=retry_count + 1, last_error=?
            WHERE id=?
            """,
            (error, operation_id),
        )
    conn.commit()


def _normalize_keywords(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value).strip().casefold() for value in values if str(value).strip()]


def candidate_matches_config(candidate: dict, config: dict) -> bool:
    """按项目 categories、include/exclude keywords 过滤候选。"""
    categories = {str(value).strip().casefold() for value in candidate.get("categories", [])}
    configured_categories = {
        str(value).strip().casefold()
        for value in config.get("categories", [])
        if str(value).strip()
    }
    if configured_categories and not categories.intersection(configured_categories):
        return False

    haystack = " ".join(
        [str(candidate.get("title") or ""), str(candidate.get("abstract") or "")]
    ).casefold()
    include_keywords = _normalize_keywords(config.get("include_keywords"))
    exclude_keywords = _normalize_keywords(config.get("exclude_keywords"))
    if include_keywords and not any(keyword in haystack for keyword in include_keywords):
        return False
    if any(keyword in haystack for keyword in exclude_keywords):
        return False
    return True


def _arxiv_result_to_candidate(result: object) -> dict:
    entry_id = str(getattr(result, "entry_id", ""))
    arxiv_id = entry_id.rstrip("/").rsplit("/", 1)[-1]
    arxiv_id = arxiv_id.removesuffix(".pdf")
    arxiv_id = arxiv_id.split("v", 1)[0]
    published = getattr(result, "published", None)
    updated = getattr(result, "updated", None)
    return {
        "arxiv_id": arxiv_id,
        "title": " ".join(str(getattr(result, "title", "") or "").split()),
        "abstract": " ".join(str(getattr(result, "summary", "") or "").split()),
        "authors": [str(getattr(author, "name", author)) for author in (getattr(result, "authors", None) or [])],
        "categories": list(getattr(result, "categories", None) or []),
        "primary_category": getattr(result, "primary_category", None),
        "published_date": published.date().isoformat() if published else None,
        "updated_date": updated.date().isoformat() if updated else None,
        "arxiv_url": entry_id,
        "pdf_url": getattr(result, "pdf_url", None),
    }


def _atom_entry_to_candidate(entry: object) -> dict:
    """将 arXiv 每日 Atom 条目转换为雷达候选，不再二次请求 export API。"""
    entry_id = str(entry.get("id") or "").removeprefix("oai:arXiv.org:")
    arxiv_id = re.sub(r"v\d+$", "", entry_id)
    abstract = str(entry.get("summary") or "")
    abstract = re.sub(
        r"^arXiv:.*?Announce Type:\s*\w+\s*Abstract:\s*",
        "",
        abstract,
        flags=re.DOTALL | re.IGNORECASE,
    )
    abstract = re.sub(r"^Abstract:\s*", "", abstract, flags=re.IGNORECASE)
    categories = [
        str(tag.get("term") or "").strip()
        for tag in (entry.get("tags") or [])
        if str(tag.get("term") or "").strip()
    ]
    creator = str(entry.get("author") or entry.get("dc_creator") or "")
    authors = [author.strip() for author in creator.split(",") if author.strip()]
    arxiv_url = str(entry.get("link") or f"https://arxiv.org/abs/{arxiv_id}")
    return {
        "arxiv_id": arxiv_id,
        "title": " ".join(str(entry.get("title") or "").split()),
        "abstract": " ".join(abstract.split()),
        "authors": authors,
        "categories": categories,
        "primary_category": categories[0] if categories else None,
        "published_date": str(entry.get("published") or "")[:10] or None,
        "updated_date": str(entry.get("updated") or "")[:10] or None,
        "arxiv_url": arxiv_url,
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
    }


def fetch_arxiv_candidates(categories: list[str], max_results: int = 100, include_cross_list: bool = True) -> list[dict]:
    """从 arXiv 每日 Atom feed 获取新候选，不访问易限流的分类查询 API。"""
    normalized = validate_radar_categories(categories)
    query = quote("+".join(normalized), safe="+.")
    response = requests.get(
        f"https://rss.arxiv.org/atom/{query}",
        headers={"User-Agent": "CiteMap/0.4 (+https://github.com/Jealousc11gx/CiteMap)"},
        timeout=30,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    if getattr(feed, "bozo", False) and not feed.entries:
        raise RuntimeError(f"arXiv Atom feed 解析失败: {feed.bozo_exception}")
    if "Feed error for query" in str(feed.feed.get("title") or ""):
        raise ValueError(f"无效的 arXiv categories: {', '.join(normalized)}")

    allowed_types = {"new", "cross"} if include_cross_list else {"new"}
    candidates = []
    seen = set()
    for entry in feed.entries:
        announce_type = str(entry.get("arxiv_announce_type") or "new").casefold()
        candidate = _atom_entry_to_candidate(entry)
        if announce_type not in allowed_types or not candidate["arxiv_id"] or candidate["arxiv_id"] in seen:
            continue
        seen.add(candidate["arxiv_id"])
        candidates.append(candidate)
        if len(candidates) >= max_results:
            break
    return candidates


def run_radar_collection(
    conn: sqlite3.Connection,
    project_id: str,
    run_date: str,
    *,
    fetcher=None,
    embedding_provider=None,
    max_results: int = 100,
) -> dict:
    """抓取、过滤、保存一个项目的候选；排序由 Node 3 负责。"""
    config = get_radar_config(conn, project_id)
    run_id = create_radar_run(conn, project_id, run_date)
    if not config["enabled"]:
        finish_radar_run(conn, run_id, status="skipped")
        return {"run_id": run_id, "status": "skipped", "candidate_count": 0, "matched_count": 0}

    fetch = fetcher or fetch_arxiv_candidates
    try:
        if fetcher is None:
            candidates = fetch(
                config["categories"],
                max_results=max_results,
                include_cross_list=config.get("include_cross_list", True),
            )
        else:
            candidates = fetch(config["categories"], max_results=max_results)
        seen: set[str] = set()
        matched = 0
        for candidate in candidates:
            arxiv_id = str(candidate.get("arxiv_id") or "").strip()
            if not arxiv_id or arxiv_id in seen or not candidate_matches_config(candidate, config):
                continue
            seen.add(arxiv_id)
            stored = upsert_radar_candidate(conn, candidate)
            upsert_radar_match(
                conn,
                project_id,
                stored["id"],
                run_id=run_id,
                reason="候选已通过 category / keyword 过滤，等待语义排序",
            )
            matched += 1
        finish_radar_run(
            conn,
            run_id,
            status="success",
            candidate_count=len(candidates),
            matched_count=matched,
        )
        ranked_count = matched
        if embedding_provider is not None:
            from .radar_ranking import rank_project_radar_matches

            ranked = rank_project_radar_matches(
                conn,
                project_id,
                embedding_provider=embedding_provider,
                run_id=run_id,
            )
            if ranked and config.get("compute_mode") in {"local", "hybrid"}:
                from .radar_llm import enrich_with_tldr

                enrich_with_tldr(ranked)
                for item in ranked:
                    upsert_radar_candidate(conn, item)
            ranked_count = len(ranked)
            finish_radar_run(
                conn,
                run_id,
                status="success",
                candidate_count=len(candidates),
                matched_count=ranked_count,
            )
        return {
            "run_id": run_id,
            "status": "success",
            "candidate_count": len(candidates),
            "matched_count": ranked_count,
        }
    except Exception as exc:
        finish_radar_run(conn, run_id, status="failed", error=str(exc))
        raise


def run_enabled_radar_collections(
    db_path, run_date: str, *, fetcher=None, embedding_provider=None, max_results: int = 100
) -> list[dict]:
    """对所有启用雷达的项目执行候选抓取。"""
    conn = get_connection(db_path)
    try:
        project_ids = [
            row["project_id"]
            for row in conn.execute("SELECT project_id FROM radar_configs WHERE enabled = 1")
        ]
        results = []
        for project_id in project_ids:
            results.append(
                run_radar_collection(
                    conn,
                    project_id,
                    run_date,
                    fetcher=fetcher,
                    embedding_provider=embedding_provider,
                    max_results=max_results,
                )
            )
        return results
    finally:
        conn.close()
