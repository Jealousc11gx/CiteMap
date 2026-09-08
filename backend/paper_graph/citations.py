"""Semantic Scholar 引用同步与本地论文关系图。"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import networkx as nx

from .database import get_connection, init_db


API_BASE = "https://api.semanticscholar.org/graph/v1"
PAPER_FIELDS = "title,year,venue,citationCount,referenceCount,externalIds"


class CitationSyncError(RuntimeError):
    """引用数据源返回不可恢复的同步错误。"""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _arxiv_id(paper: dict[str, Any]) -> str | None:
    if str(paper.get("id", "")).startswith("arxiv_"):
        return str(paper["id"])[6:].split("v", 1)[0]
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", str(paper.get("arxiv_url") or ""), re.I)
    return match.group(1).removesuffix(".pdf").split("v", 1)[0] if match else None


def _request_json(path: str, *, params: dict[str, Any] | None = None, payload: dict | None = None) -> Any:
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urlencode(params)
    headers = {"Accept": "application/json", "User-Agent": "CiteMap/0.4"}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    try:
        with urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            raise CitationSyncError("Semantic Scholar 未找到这篇论文", 404) from exc
        if exc.code == 429:
            raise CitationSyncError(
                "Semantic Scholar 请求频率受限；请稍后重试，或在 backend/.env 配置 SEMANTIC_SCHOLAR_API_KEY",
                429,
            ) from exc
        raise CitationSyncError(f"Semantic Scholar 请求失败（HTTP {exc.code}）") from exc
    except (URLError, TimeoutError) as exc:
        raise CitationSyncError("无法连接 Semantic Scholar，请检查网络后重试") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CitationSyncError("Semantic Scholar 返回了无法解析的数据") from exc


def _paper_payload(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw or not raw.get("paperId"):
        return None
    return {
        "scholar_id": str(raw["paperId"]),
        "title": str(raw.get("title") or "未命名论文"),
        "year": raw.get("year"),
        "venue": raw.get("venue") or None,
        "citation_count": raw.get("citationCount"),
        "reference_count": raw.get("referenceCount"),
        "external_ids": raw.get("externalIds") or {},
    }


def _upsert_scholar_paper(conn, paper: dict[str, Any], local_paper_id: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO citation_papers (
            scholar_id, local_paper_id, title, year, venue, citation_count,
            reference_count, external_ids, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(scholar_id) DO UPDATE SET
            local_paper_id=COALESCE(excluded.local_paper_id, citation_papers.local_paper_id),
            title=CASE WHEN excluded.title != '' THEN excluded.title ELSE citation_papers.title END,
            year=COALESCE(excluded.year, citation_papers.year),
            venue=COALESCE(excluded.venue, citation_papers.venue),
            citation_count=COALESCE(excluded.citation_count, citation_papers.citation_count),
            reference_count=COALESCE(excluded.reference_count, citation_papers.reference_count),
            external_ids=CASE WHEN excluded.external_ids != '{}' THEN excluded.external_ids ELSE citation_papers.external_ids END,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            paper["scholar_id"], local_paper_id, paper.get("title") or "", paper.get("year"),
            paper.get("venue"), paper.get("citation_count"), paper.get("reference_count"),
            json.dumps(paper.get("external_ids") or {}, ensure_ascii=False),
        ),
    )


def _local_id_for_external(conn, external_ids: dict[str, Any]) -> str | None:
    arxiv_id = str(external_ids.get("ArXiv") or "").strip()
    if not arxiv_id:
        return None
    row = conn.execute(
        "SELECT id FROM papers WHERE id = ? OR arxiv_url LIKE ? LIMIT 1",
        (f"arxiv_{arxiv_id}", f"%/{arxiv_id}%"),
    ).fetchone()
    return str(row["id"]) if row else None


def sync_citations(paper_id: str, db_path: Optional[Path] = None, neighbor_limit: int = 30) -> dict[str, Any]:
    """同步一篇论文及其一阶引用邻域，并缓存候选论文的参考文献。"""
    init_db(db_path)
    conn = get_connection(db_path)
    paper_row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    conn.close()
    if not paper_row:
        raise CitationSyncError("论文不存在", 404)
    paper = dict(paper_row)
    arxiv_id = _arxiv_id(paper)
    if not arxiv_id:
        raise CitationSyncError("该论文没有可用于匹配的 arXiv ID", 422)

    identifier = quote(f"ARXIV:{arxiv_id}", safe=":")
    seed_raw = _request_json(f"/paper/{identifier}", params={"fields": PAPER_FIELDS})
    refs_raw = _request_json(
        f"/paper/{identifier}/references",
        params={"limit": neighbor_limit, "fields": PAPER_FIELDS},
    )
    cites_raw = _request_json(
        f"/paper/{identifier}/citations",
        params={"limit": neighbor_limit, "fields": PAPER_FIELDS},
    )
    seed = _paper_payload(seed_raw)
    if not seed:
        raise CitationSyncError("Semantic Scholar 未返回有效论文数据")

    references = [
        parsed for item in refs_raw.get("data", [])
        if (parsed := _paper_payload(item.get("citedPaper")))
    ]
    citations = [
        parsed for item in cites_raw.get("data", [])
        if (parsed := _paper_payload(item.get("citingPaper")))
    ]
    candidates = {item["scholar_id"]: item for item in [seed, *references, *citations]}

    # 批量获取参考文献集合，供 bibliographic coupling 计算使用。
    batch = _request_json(
        "/paper/batch",
        params={"fields": f"{PAPER_FIELDS},references.paperId"},
        payload={"ids": list(candidates)},
    )

    conn = get_connection(db_path)
    try:
        for item in candidates.values():
            local_id = paper_id if item["scholar_id"] == seed["scholar_id"] else _local_id_for_external(conn, item["external_ids"])
            _upsert_scholar_paper(conn, item, local_id)

        refreshed_ids: set[str] = set()
        for raw in batch or []:
            parsed = _paper_payload(raw)
            if not parsed:
                continue
            local_id = paper_id if parsed["scholar_id"] == seed["scholar_id"] else _local_id_for_external(conn, parsed["external_ids"])
            _upsert_scholar_paper(conn, parsed, local_id)
            refreshed_ids.add(parsed["scholar_id"])
            for reference in raw.get("references") or []:
                reference_id = reference.get("paperId") if reference else None
                if reference_id:
                    _upsert_scholar_paper(conn, {
                        "scholar_id": str(reference_id), "title": "", "external_ids": {},
                    })

        for scholar_id in refreshed_ids:
            conn.execute("DELETE FROM citation_edges WHERE citing_id = ?", (scholar_id,))
        for raw in batch or []:
            citing_id = raw.get("paperId") if raw else None
            if not citing_id:
                continue
            for reference in raw.get("references") or []:
                cited_id = reference.get("paperId") if reference else None
                if cited_id:
                    conn.execute(
                        "INSERT OR REPLACE INTO citation_edges (citing_id, cited_id, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                        (str(citing_id), str(cited_id)),
                    )

        # 分页端点是种子论文直接边的权威结果，确保截断批量字段时仍有一阶关系。
        for item in references:
            conn.execute(
                "INSERT OR REPLACE INTO citation_edges (citing_id, cited_id, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (seed["scholar_id"], item["scholar_id"]),
            )
        for item in citations:
            conn.execute(
                "INSERT OR REPLACE INTO citation_edges (citing_id, cited_id, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (item["scholar_id"], seed["scholar_id"]),
            )

        conn.execute(
            """
            UPDATE papers SET semantic_scholar_id = ?, citation_count = ?, reference_count = ?,
                              citation_synced_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (seed["scholar_id"], seed.get("citation_count"), seed.get("reference_count"), paper_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "paper_id": paper_id,
        "semantic_scholar_id": seed["scholar_id"],
        "citation_count": seed.get("citation_count"),
        "reference_count": seed.get("reference_count"),
        "loaded_references": len(references),
        "loaded_citations": len(citations),
    }


def sync_citation_metrics(
    db_path: Optional[Path] = None,
    project_id: str | None = None,
) -> dict[str, int]:
    """批量更新本地论文的引用数与参考文献数，不下载引用邻域。"""
    init_db(db_path)
    conn = get_connection(db_path)
    project_join = "JOIN project_papers pp ON pp.paper_id = p.id" if project_id else ""
    project_where = "WHERE pp.project_id = ?" if project_id else ""
    rows = [dict(row) for row in conn.execute(
        f"SELECT p.id, p.arxiv_url FROM papers p {project_join} {project_where}",
        (project_id,) if project_id else (),
    ).fetchall()]
    conn.close()

    candidates = [
        (paper["id"], arxiv_id)
        for paper in rows
        if (arxiv_id := _arxiv_id(paper))
    ]
    updated = 0
    unmatched = 0
    conn = get_connection(db_path)
    try:
        for offset in range(0, len(candidates), 400):
            chunk = candidates[offset:offset + 400]
            response = _request_json(
                "/paper/batch",
                params={"fields": PAPER_FIELDS},
                payload={"ids": [f"ARXIV:{arxiv_id}" for _, arxiv_id in chunk]},
            )
            for (local_id, _), raw in zip(chunk, response or []):
                parsed = _paper_payload(raw)
                if not parsed:
                    unmatched += 1
                    continue
                conn.execute(
                    """
                    UPDATE papers
                    SET semantic_scholar_id = ?, citation_count = ?, reference_count = ?,
                        venue = COALESCE(venue, ?), venue_year = COALESCE(venue_year, ?)
                    WHERE id = ?
                    """,
                    (
                        parsed["scholar_id"], parsed.get("citation_count"),
                        parsed.get("reference_count"), parsed.get("venue"),
                        parsed.get("year"), local_id,
                    ),
                )
                updated += 1
            unmatched += max(0, len(chunk) - len(response or []))
        conn.commit()
    finally:
        conn.close()

    return {
        "total": len(rows),
        "eligible": len(candidates),
        "updated": updated,
        "unmatched": unmatched,
        "skipped": len(rows) - len(candidates),
    }


def _node_id(row: dict[str, Any]) -> str:
    return str(row.get("local_paper_id") or f"s2:{row['scholar_id']}")


def _add_node(graph: nx.Graph, row: dict[str, Any], seed_id: str, **extra: Any) -> None:
    scholar_id = str(row["scholar_id"])
    graph.add_node(
        _node_id(row),
        label=row.get("title") or "未命名论文",
        title=row.get("title") or "未命名论文",
        group="paper",
        paper_id=row.get("local_paper_id"),
        scholar_id=scholar_id,
        is_seed=scholar_id == seed_id,
        published_date=str(row.get("year") or ""),
        venue=row.get("venue"),
        venue_year=row.get("year"),
        citation_count=row.get("citation_count"),
        reference_count=row.get("reference_count"),
        external=not bool(row.get("local_paper_id")),
        **extra,
    )


def _seed_row(conn, paper_id: str):
    return conn.execute(
        "SELECT * FROM citation_papers WHERE local_paper_id = ?",
        (paper_id,),
    ).fetchone()


def build_citation_graph(
    paper_id: str,
    db_path: Optional[Path] = None,
    limit_per_direction: int = 12,
) -> nx.DiGraph:
    """返回种子论文的一阶引用关系，默认按方向裁剪为可读子图。"""
    init_db(db_path)
    conn = get_connection(db_path)
    graph = nx.DiGraph()
    seed_row = _seed_row(conn, paper_id)
    if not seed_row:
        conn.close()
        return graph
    seed_id = str(seed_row["scholar_id"])
    direct_edges = [dict(row) for row in conn.execute(
        "SELECT citing_id, cited_id FROM citation_edges WHERE citing_id = ? OR cited_id = ?",
        (seed_id, seed_id),
    ).fetchall()]
    ids = {seed_id}
    for row in direct_edges:
        ids.update((str(row["citing_id"]), str(row["cited_id"])))
    placeholders = ",".join("?" for _ in ids)
    papers = {
        str(row["scholar_id"]): dict(row)
        for row in conn.execute(f"SELECT * FROM citation_papers WHERE scholar_id IN ({placeholders})", tuple(ids)).fetchall()
    }
    # 未返回元数据的占位论文无法提供任何研究线索，不进入可视化。
    valid_ids = {
        scholar_id for scholar_id, row in papers.items()
        if scholar_id == seed_id or (row.get("title") and row.get("title") != "未命名论文")
    }
    references = [
        str(row["cited_id"]) for row in direct_edges
        if str(row["citing_id"]) == seed_id and str(row["cited_id"]) in valid_ids
    ]
    citations = [
        str(row["citing_id"]) for row in direct_edges
        if str(row["cited_id"]) == seed_id and str(row["citing_id"]) in valid_ids
    ]
    rank_key = lambda scholar_id: (
        -(papers[scholar_id].get("citation_count") or 0),
        -(papers[scholar_id].get("year") or 0),
        papers[scholar_id].get("title") or "",
    )
    references = sorted(set(references), key=rank_key)
    citations = sorted(set(citations), key=rank_key)
    if limit_per_direction > 0:
        references = references[:limit_per_direction]
        citations = citations[:limit_per_direction]

    _add_node(graph, papers[seed_id], seed_id, citation_role="seed")
    for scholar_id in references:
        _add_node(graph, papers[scholar_id], seed_id, citation_role="reference")
        graph.add_edge(
            _node_id(papers[seed_id]), _node_id(papers[scholar_id]), weight=1,
            directed=True, relation_types=["citation"], title="种子论文引用了该论文",
        )
    for scholar_id in citations:
        _add_node(graph, papers[scholar_id], seed_id, citation_role="citing")
        graph.add_edge(
            _node_id(papers[scholar_id]), _node_id(papers[seed_id]), weight=1,
            directed=True, relation_types=["citation"], title="该论文引用了种子论文",
        )
    for node_id in graph.nodes:
        graph.nodes[node_id]["degree"] = graph.degree(node_id)
    conn.close()
    return graph


def build_similarity_graph(paper_id: str, db_path: Optional[Path] = None, max_nodes: int = 31, top_k: int = 3) -> nx.Graph:
    """以共享参考文献的 Ochiai 系数构建简化版 Connected Papers 图。"""
    init_db(db_path)
    conn = get_connection(db_path)
    graph = nx.Graph()
    seed_row = _seed_row(conn, paper_id)
    if not seed_row:
        conn.close()
        return graph
    seed_id = str(seed_row["scholar_id"])
    candidate_ids = {seed_id}
    for row in conn.execute(
        "SELECT citing_id, cited_id FROM citation_edges WHERE citing_id = ? OR cited_id = ?",
        (seed_id, seed_id),
    ).fetchall():
        candidate_ids.update((str(row["citing_id"]), str(row["cited_id"])))

    references: dict[str, set[str]] = {candidate_id: set() for candidate_id in candidate_ids}
    placeholders = ",".join("?" for _ in candidate_ids)
    for row in conn.execute(
        f"SELECT citing_id, cited_id FROM citation_edges WHERE citing_id IN ({placeholders})",
        tuple(candidate_ids),
    ).fetchall():
        references[str(row["citing_id"])].add(str(row["cited_id"]))

    def score(left: str, right: str) -> tuple[float, int]:
        shared = len(references[left] & references[right])
        denominator = math.sqrt(len(references[left]) * len(references[right]))
        return (shared / denominator if denominator else 0.0, shared)

    seed_scores = {candidate_id: score(seed_id, candidate_id)[0] for candidate_id in candidate_ids}
    paper_rows = {
        str(row["scholar_id"]): dict(row)
        for row in conn.execute(f"SELECT * FROM citation_papers WHERE scholar_id IN ({placeholders})", tuple(candidate_ids)).fetchall()
    }
    selected = sorted(
        candidate_ids,
        key=lambda item: (item != seed_id, -seed_scores[item], -(paper_rows.get(item, {}).get("citation_count") or 0)),
    )[:max_nodes]
    for candidate_id in selected:
        row = paper_rows.get(candidate_id)
        if row:
            _add_node(graph, row, seed_id, similarity_score=round(seed_scores[candidate_id], 4))

    edge_candidates: dict[tuple[str, str], tuple[float, int]] = {}
    for left in selected:
        nearest = sorted(
            ((right, *score(left, right)) for right in selected if right != left),
            key=lambda item: (-item[1], -item[2], item[0]),
        )[:top_k]
        for right, similarity, shared in nearest:
            if similarity <= 0:
                continue
            pair = tuple(sorted((left, right)))
            edge_candidates[pair] = max(edge_candidates.get(pair, (0.0, 0)), (similarity, shared))
    for (left, right), (similarity, shared) in edge_candidates.items():
        if left in paper_rows and right in paper_rows:
            graph.add_edge(
                _node_id(paper_rows[left]), _node_id(paper_rows[right]),
                weight=round(similarity * 10, 3), similarity=round(similarity, 4),
                shared_references=shared, relation_types=["similarity"],
                title=f"共同参考文献 {shared} 篇 · 相似度 {similarity:.0%}",
            )
    # 没有任何正相似边的候选无法参与相似网络，避免渲染成无意义孤立点；Seed 始终保留。
    seed_node_id = _node_id(paper_rows[seed_id]) if seed_id in paper_rows else None
    isolated = [node_id for node_id, degree in graph.degree() if degree == 0 and node_id != seed_node_id]
    graph.remove_nodes_from(isolated)
    for node_id in graph.nodes:
        graph.nodes[node_id]["degree"] = graph.degree(node_id)
        graph.nodes[node_id]["weighted_degree"] = round(graph.degree(node_id, weight="weight"), 3)
    conn.close()
    return graph
