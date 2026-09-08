"""论文雷达排序核心测试。"""

import numpy as np
import pytest

from paper_graph.database import create_project, get_connection, upsert_paper
from paper_graph.radar import upsert_radar_config
from paper_graph.radar_ranking import (
    cosine_similarity_matrix,
    load_anchor_ids,
    load_project_references,
    rank_project_radar_matches,
    rank_candidates,
    time_decay_weights,
)


def test_time_decay_weights_match_reference_shape():
    weights = time_decay_weights(3)
    assert len(weights) == 3
    assert np.isclose(weights.sum(), 1.0)
    assert weights[0] > weights[1] > weights[2]
    assert time_decay_weights(0).size == 0


def test_cosine_similarity_matrix():
    matrix = cosine_similarity_matrix([[1, 0], [0, 1]], [[1, 0], [1, 1]])
    assert matrix.shape == (2, 2)
    assert np.isclose(matrix[0, 0], 1.0)
    assert np.isclose(matrix[1, 1], 1 / np.sqrt(2))
    with pytest.raises(ValueError, match="维度不一致"):
        cosine_similarity_matrix([[1, 0]], [[1, 0, 0]])


def test_rank_candidates_matches_daily_arxiv_score_scale_and_abstract_only():
    candidates = [
        {"arxiv_id": "b", "title": "B", "abstract": "B abstract"},
        {"arxiv_id": "a", "title": "A", "abstract": "A abstract"},
    ]
    references = [
        {"id": "recent", "title": "R", "abstract": "R abstract"},
        {"id": "anchor", "title": "Old", "abstract": "Old abstract"},
    ]
    vectors = {
        "B abstract": [1, 0],
        "A abstract": [0, 1],
        "R abstract": [1, 0],
        "Old abstract": [0, 1],
    }
    ranked = rank_candidates(
        candidates,
        references,
        embedding_provider=lambda texts: [vectors[text] for text in texts],
        top_k=1,
    )
    assert len(ranked) == 1
    assert ranked[0]["arxiv_id"] == "b"
    assert np.isclose(ranked[0]["score"], time_decay_weights(2)[0] * 10.0)


def test_rank_candidates_empty_references_returns_empty():
    assert rank_candidates(
        [{"arxiv_id": "a", "title": "A", "abstract": ""}],
        [],
        embedding_provider=lambda texts: [[1, 0] for _ in texts],
    ) == []


def test_load_project_references_and_anchor_ids(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Ranking")
    for paper_id in ("p1", "p2"):
        upsert_paper(
            conn,
            {
                "id": paper_id,
                "title": paper_id,
                "abstract": "abstract",
                "published_date": "2026-01-01",
                "updated_date": "2026-01-01",
                "categories": "cs.AI",
                "pdf_path": None,
                "source": "arxiv",
                "arxiv_url": None,
            },
        )
        conn.execute("INSERT INTO project_papers(project_id, paper_id) VALUES (?, ?)", (project["id"], paper_id))
    conn.commit()
    upsert_radar_config(conn, project["id"], anchor_paper_ids=["p2"])
    assert {row["id"] for row in load_project_references(conn, project["id"])} == {"p1", "p2"}
    assert load_anchor_ids(conn, project["id"]) == {"p2"}
    conn.close()


def test_rank_project_matches_writes_score_and_keeps_top_k(tmp_db):
    from paper_graph.radar import upsert_radar_candidate, upsert_radar_match

    conn = get_connection(tmp_db)
    project = create_project(conn, "Project Ranking")
    upsert_paper(
        conn,
        {
            "id": "ref",
            "title": "Relevant",
            "abstract": "retrieval",
            "published_date": "2026-01-01",
            "updated_date": "2026-01-01",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": None,
        },
    )
    conn.execute("INSERT INTO project_papers(project_id, paper_id) VALUES (?, ?)", (project["id"], "ref"))
    upsert_radar_config(conn, project["id"], enabled=True, top_k=1, min_score=0.0)
    first = upsert_radar_candidate(conn, {"arxiv_id": "r1", "title": "Relevant", "abstract": "abstract"})
    second = upsert_radar_candidate(conn, {"arxiv_id": "r2", "title": "Other", "abstract": "other"})
    upsert_radar_match(conn, project["id"], first["id"])
    upsert_radar_match(conn, project["id"], second["id"])
    conn.commit()
    vectors = {"abstract": [1, 0], "other": [0, 1], "retrieval": [1, 0]}
    ranked = rank_project_radar_matches(
        conn,
        project["id"],
        embedding_provider=lambda texts: [vectors[text] for text in texts],
    )
    assert [item["arxiv_id"] for item in ranked] == ["r1"]
    assert [row["arxiv_id"] for row in conn.execute(
        "SELECT rc.arxiv_id FROM radar_matches rm JOIN radar_candidates rc ON rc.id=rm.candidate_id WHERE rm.project_id=?",
        (project["id"],),
    )] == ["r1", "r2"]
    conn.close()
