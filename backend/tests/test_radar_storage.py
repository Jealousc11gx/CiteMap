"""论文雷达本地存储、状态机、游标、离线队列测试。"""

import pytest

from paper_graph.database import (
    add_paper_to_project,
    create_project,
    delete_project,
    get_connection,
    upsert_paper,
)
from paper_graph.radar import (
    create_radar_run,
    enqueue_radar_operation,
    finish_radar_run,
    get_radar_config,
    get_radar_sync_cursor,
    list_pending_radar_operations,
    list_radar_matches,
    mark_radar_operation_result,
    set_radar_sync_cursor,
    transition_radar_state,
    upsert_radar_candidate,
    upsert_radar_config,
    upsert_radar_match,
)


def test_radar_categories_default_and_validation(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Category defaults")
    config = upsert_radar_config(conn, project["id"], categories=[])
    assert config["categories"] == ["cs.AI"]
    with pytest.raises(ValueError, match=r"无效的 arXiv categories: cd\.AI。示例：cs\.AI、cs\.CV、stat\.ML"):
        upsert_radar_config(conn, project["id"], categories=["cd.AI"])
    conn.close()


def test_radar_config_defaults_and_upsert(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Radar Project")

    assert get_radar_config(conn, project["id"])["enabled"] is False
    config = upsert_radar_config(
        conn,
        project["id"],
        enabled=True,
        categories=["cs.AI"],
        include_keywords=["retrieval"],
        exclude_keywords=["medical"],
        profile_override="multimodal retrieval",
        anchor_paper_ids=["paper-1"],
        top_k=5,
        min_score=0.4,
    )
    assert config["enabled"] is True
    assert config["categories"] == ["cs.AI"]
    assert config["top_k"] == 5
    assert config["min_score"] == 0.4
    conn.close()


def test_radar_run_is_idempotent_by_project_and_date(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Run Project")
    first = create_radar_run(conn, project["id"], "2026-09-06")
    second = create_radar_run(conn, project["id"], "2026-09-06")
    assert first == second
    finish_radar_run(conn, first, status="success", candidate_count=3, matched_count=2)
    row = conn.execute("SELECT * FROM radar_runs WHERE id=?", (first,)).fetchone()
    assert row["status"] == "success"
    assert row["candidate_count"] == 3
    conn.close()


def test_candidate_and_match_are_upserted_without_duplicates(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Match Project")
    candidate = upsert_radar_candidate(
        conn,
        {
            "arxiv_id": "2609.01234",
            "title": "First title",
            "abstract": "First abstract",
            "authors": ["A"],
            "categories": ["cs.AI"],
            "published_date": "2026-09-06",
        },
    )
    match = upsert_radar_match(conn, project["id"], candidate["id"], score=0.8)
    same = upsert_radar_match(conn, project["id"], candidate["id"], score=0.9)
    assert match["id"] == same["id"]
    assert same["score"] == 0.9
    assert len(list_radar_matches(conn, project["id"])) == 1
    conn.close()


def test_state_transition_never_downgrades_saved(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "State Project")
    candidate = upsert_radar_candidate(conn, {"arxiv_id": "2609.00001", "title": "Paper"})
    match = upsert_radar_match(conn, project["id"], candidate["id"])
    transition_radar_state(conn, match["id"], "saved")
    result = transition_radar_state(conn, match["id"], "read")
    assert result["state"] == "saved"
    with pytest.raises(ValueError, match="无效的雷达状态"):
        transition_radar_state(conn, match["id"], "unknown")
    conn.close()


def test_sync_cursor_and_pending_operations_are_idempotent(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Offline Project")
    candidate = upsert_radar_candidate(conn, {"arxiv_id": "2609.00002", "title": "Offline"})
    match = upsert_radar_match(conn, project["id"], candidate["id"])
    assert get_radar_sync_cursor(conn) is None
    set_radar_sync_cursor(conn, "42")
    assert get_radar_sync_cursor(conn) == "42"
    first = enqueue_radar_operation(conn, project["id"], match["id"], "save")
    second = enqueue_radar_operation(conn, project["id"], match["id"], "save")
    assert first["id"] == second["id"]
    assert len(list_pending_radar_operations(conn, project["id"])) == 1
    mark_radar_operation_result(conn, first["id"], success=False, error="offline")
    assert list_pending_radar_operations(conn, project["id"])[0]["retry_count"] == 1
    mark_radar_operation_result(conn, first["id"], success=True)
    assert list_pending_radar_operations(conn, project["id"]) == []
    conn.close()


def test_delete_project_cleans_radar_records(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Delete Radar Project")
    candidate = upsert_radar_candidate(conn, {"arxiv_id": "2609.00003", "title": "Delete"})
    match = upsert_radar_match(conn, project["id"], candidate["id"])
    enqueue_radar_operation(conn, project["id"], match["id"], "read")
    create_radar_run(conn, project["id"], "2026-09-06")
    upsert_radar_config(conn, project["id"], enabled=True)
    assert delete_project(conn, project["id"]) is True
    assert conn.execute("SELECT 1 FROM radar_matches WHERE id=?", (match["id"],)).fetchone() is None
    assert conn.execute("SELECT 1 FROM radar_configs WHERE project_id=?", (project["id"],)).fetchone() is None
    assert conn.execute("SELECT 1 FROM radar_runs WHERE project_id=?", (project["id"],)).fetchone() is None
    conn.close()
