"""论文雷达排序核心。默认算法复用 daily arxiv 的时间衰减 + cosine similarity。"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Callable, Sequence

import numpy as np

from .radar import _loads, get_radar_config


EmbeddingProvider = Callable[[list[str]], Sequence[Sequence[float]]]


def time_decay_weights(count: int) -> np.ndarray:
    """新加入项目的论文权重更高，公式与参考项目保持一致。"""
    if count <= 0:
        return np.array([], dtype=float)
    ranks = np.arange(count, dtype=float)
    weights = 1.0 / (1.0 + np.log10(ranks + 1.0))
    return weights / weights.sum()


def cosine_similarity_matrix(
    candidates: Sequence[Sequence[float]], references: Sequence[Sequence[float]]
) -> np.ndarray:
    left = np.asarray(candidates, dtype=float)
    right = np.asarray(references, dtype=float)
    if left.ndim != 2 or right.ndim != 2:
        raise ValueError("embedding 必须是二维数组")
    if left.shape[1] != right.shape[1]:
        raise ValueError("candidate 与 reference embedding 维度不一致")
    left_norm = np.linalg.norm(left, axis=1, keepdims=True)
    right_norm = np.linalg.norm(right, axis=1, keepdims=True)
    if np.any(left_norm == 0) or np.any(right_norm == 0):
        raise ValueError("embedding 不能包含零向量")
    return (left / left_norm) @ (right / right_norm).T


def rank_candidates(
    candidates: list[dict],
    references: list[dict],
    *,
    embedding_provider: EmbeddingProvider,
    anchor_ids: set[str] | None = None,
    anchor_bonus: float = 0.0,
    top_k: int = 10,
    min_score: float = 0.0,
) -> list[dict]:
    """为候选写入 score、reason，并返回过滤后的 Top K。"""
    if top_k < 1:
        raise ValueError("雷达 Top K 必须大于 0")
    if not candidates or not references:
        return []
    anchor_ids = anchor_ids or set()
    candidate_texts = [f"{item.get('title', '')}\n{item.get('abstract', '')}".strip() for item in candidates]
    reference_texts = [f"{item.get('title', '')}\n{item.get('abstract', '')}".strip() for item in references]
    vectors = embedding_provider(candidate_texts + reference_texts)
    matrix = cosine_similarity_matrix(vectors[: len(candidates)], vectors[len(candidates) :])
    weights = time_decay_weights(len(references))
    ranked: list[dict] = []
    for index, candidate in enumerate(candidates):
        base_score = float(matrix[index] @ weights)
        anchor_scores = [
            float(matrix[index, ref_index])
            for ref_index, reference in enumerate(references)
            if reference.get("id") in anchor_ids or reference.get("paper_id") in anchor_ids
        ]
        score = base_score
        if anchor_scores and anchor_bonus:
            score += anchor_bonus * max(anchor_scores)
        item = dict(candidate)
        item["score"] = score
        item["reason"] = "项目论文语义相似度"
        if anchor_scores and anchor_bonus:
            item["reason"] += " + anchor paper 加权"
        if score >= min_score:
            ranked.append(item)
    ranked.sort(key=lambda item: (-float(item["score"]), str(item.get("arxiv_id", ""))))
    return ranked[:top_k]


def load_project_references(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    """读取项目论文，按加入时间从新到旧排列。"""
    rows = conn.execute(
        """
        SELECT p.id, p.title, p.abstract, pp.added_at
        FROM project_papers pp
        JOIN papers p ON p.id = pp.paper_id
        WHERE pp.project_id = ?
        ORDER BY pp.added_at DESC, p.id ASC
        """,
        (project_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_anchor_ids(conn: sqlite3.Connection, project_id: str) -> set[str]:
    row = conn.execute(
        "SELECT anchor_paper_ids FROM radar_configs WHERE project_id = ?", (project_id,)
    ).fetchone()
    return set(_loads(row["anchor_paper_ids"], []) if row else [])


def rank_project_radar_matches(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    embedding_provider: EmbeddingProvider,
    run_id: str | None = None,
    anchor_bonus: float = 0.0,
) -> list[dict]:
    """对项目候选执行算法 A，并将结果写回 radar_matches。"""
    config = get_radar_config(conn, project_id)
    references = load_project_references(conn, project_id)
    if not references:
        return []
    if run_id:
        rows = conn.execute(
            """
            SELECT rc.*
            FROM radar_matches rm
            JOIN radar_candidates rc ON rc.id = rm.candidate_id
            WHERE rm.project_id = ? AND rm.run_id = ?
            """,
            (project_id, run_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT rc.*
            FROM radar_matches rm
            JOIN radar_candidates rc ON rc.id = rm.candidate_id
            WHERE rm.project_id = ?
            """,
            (project_id,),
        ).fetchall()
    candidates = [dict(row) for row in rows]
    for candidate in candidates:
        candidate["authors"] = _loads(candidate.get("authors"), [])
        candidate["categories"] = _loads(candidate.get("categories"), [])
    ranked = rank_candidates(
        candidates,
        references,
        embedding_provider=embedding_provider,
        anchor_ids=load_anchor_ids(conn, project_id),
        anchor_bonus=anchor_bonus,
        top_k=config["top_k"],
        min_score=config["min_score"],
    )
    for item in ranked:
        conn.execute(
            """
            UPDATE radar_matches
            SET score=?, reason=?, updated_at=CURRENT_TIMESTAMP
            WHERE project_id=? AND candidate_id=?
            """,
            (item["score"], item["reason"], project_id, item["id"]),
        )
    conn.commit()
    return ranked
