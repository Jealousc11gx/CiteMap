"""项目分类、迁移、作用域测试。"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from paper_graph.database import (
    DEFAULT_PROJECT_ID,
    add_paper_to_project,
    create_chat_session,
    create_project,
    delete_project,
    get_connection,
    get_paper,
    init_db,
    list_chat_sessions,
    list_available_papers,
    list_papers,
    remove_paper_from_project,
    upsert_paper,
)
from paper_graph.graph import build_paper_graph


@pytest.fixture
def project_client(tmp_path, monkeypatch):
    import main
    import paper_graph.database as database

    db_path = tmp_path / "api-projects.db"
    monkeypatch.setattr(main, "DB_PATH", db_path)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    init_db(db_path)
    return TestClient(main.app)


def _paper(paper_id: str, title: str) -> dict:
    return {
        "id": paper_id,
        "title": title,
        "abstract": f"{title} abstract",
        "published_date": "2026-01-01",
        "updated_date": "2026-01-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": None,
    }


def test_init_migrates_unassigned_papers_to_default_project(tmp_path):
    db_path = tmp_path / "projects.db"
    init_db(db_path)
    conn = get_connection(db_path)
    upsert_paper(conn, _paper("p1", "Legacy"))
    conn.commit()
    conn.close()

    init_db(db_path)
    assert list_papers(db_path, project_id=DEFAULT_PROJECT_ID)["id"].tolist() == ["p1"]


def test_project_names_are_case_insensitive_unique(tmp_db):
    conn = get_connection(tmp_db)
    create_project(conn, "Alpha")
    with pytest.raises(sqlite3.IntegrityError):
        create_project(conn, "alpha")
    conn.close()


def test_default_project_cannot_be_renamed(tmp_db):
    from paper_graph.database import update_project

    conn = get_connection(tmp_db)
    with pytest.raises(ValueError, match="未分类项目不能重命名"):
        update_project(conn, DEFAULT_PROJECT_ID, "Other")
    conn.close()


def test_add_and_remove_paper_uses_default_as_fallback(tmp_db):
    conn = get_connection(tmp_db)
    upsert_paper(conn, _paper("p1", "Scoped"))
    conn.commit()
    project = create_project(conn, "Project A")
    add_paper_to_project(conn, project["id"], "p1")

    assert list_papers(tmp_db, project_id=project["id"])["id"].tolist() == ["p1"]
    assert list_papers(tmp_db, project_id=DEFAULT_PROJECT_ID).empty

    remove_paper_from_project(conn, project["id"], "p1")
    assert list_papers(tmp_db, project_id=DEFAULT_PROJECT_ID)["id"].tolist() == ["p1"]
    conn.close()


def test_delete_project_preserves_paper_and_moves_orphan_to_default(tmp_db):
    conn = get_connection(tmp_db)
    upsert_paper(conn, _paper("p1", "Keep Me"))
    conn.commit()
    project = create_project(conn, "Temporary")
    add_paper_to_project(conn, project["id"], "p1")
    create_chat_session(conn, "session_project", project_id=project["id"])

    assert delete_project(conn, project["id"]) is True
    assert get_paper(conn, "p1") is not None
    assert list_papers(tmp_db, project_id=DEFAULT_PROJECT_ID)["id"].tolist() == ["p1"]
    assert list_chat_sessions(conn, project_id=project["id"]) == []
    conn.close()


def test_paper_graph_is_project_scoped(tmp_db):
    conn = get_connection(tmp_db)
    project_a = create_project(conn, "Graph A")
    project_b = create_project(conn, "Graph B")
    upsert_paper(conn, _paper("p1", "Paper A"))
    upsert_paper(conn, _paper("p2", "Paper B"))
    conn.commit()
    add_paper_to_project(conn, project_a["id"], "p1")
    add_paper_to_project(conn, project_b["id"], "p2")
    conn.close()

    graph_a = build_paper_graph(tmp_db, project_id=project_a["id"])
    graph_b = build_paper_graph(tmp_db, project_id=project_b["id"])
    assert set(graph_a.nodes) == {"p1"}
    assert set(graph_b.nodes) == {"p2"}


def test_available_papers_include_source_projects(tmp_db):
    conn = get_connection(tmp_db)
    source = create_project(conn, "Source")
    target = create_project(conn, "Target")
    upsert_paper(conn, _paper("p1", "Available"))
    upsert_paper(conn, _paper("p2", "Already imported"))
    conn.commit()
    add_paper_to_project(conn, source["id"], "p1")
    add_paper_to_project(conn, source["id"], "p2")
    add_paper_to_project(conn, target["id"], "p2")

    available = list_available_papers(conn, target["id"])
    assert [paper["id"] for paper in available] == ["p1"]
    assert available[0]["projects"] == [{"id": source["id"], "name": "Source"}]
    conn.close()


def test_project_api_crud_and_paper_scope(project_client):
    created = project_client.post("/api/projects", json={"name": "API Project"})
    assert created.status_code == 201
    project = created.json()

    import main

    conn = get_connection(main.DB_PATH)
    upsert_paper(conn, _paper("api_paper", "API Paper"))
    conn.commit()
    conn.close()

    added = project_client.post(f"/api/projects/{project['id']}/papers/api_paper")
    assert added.status_code == 200
    scoped = project_client.get("/api/papers", params={"project_id": project["id"]})
    assert [paper["id"] for paper in scoped.json()] == ["api_paper"]

    renamed = project_client.patch(f"/api/projects/{project['id']}", json={"name": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"

    deleted = project_client.delete(f"/api/projects/{project['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["fallback_project_id"] == DEFAULT_PROJECT_ID


def test_reannotate_preserves_current_project(project_client, monkeypatch):
    created = project_client.post("/api/projects", json={"name": "Annotation Project"})
    project = created.json()

    import main

    conn = get_connection(main.DB_PATH)
    upsert_paper(conn, _paper("annotated_paper", "Annotated Paper"))
    conn.commit()
    add_paper_to_project(conn, project["id"], "annotated_paper")
    conn.close()

    monkeypatch.setattr(
        main,
        "annotate_paper",
        lambda paper_id, model=None, db_path=None, force=False: {
            "core_contribution": "Updated",
            "teams": [],
        },
    )
    response = project_client.post(
        "/api/papers/annotated_paper/annotate",
        json={"project_id": project["id"], "force": True},
    )

    assert response.status_code == 200
    conn = get_connection(main.DB_PATH)
    project_ids = [
        row["project_id"]
        for row in conn.execute(
            "SELECT project_id FROM project_papers WHERE paper_id = ?",
            ("annotated_paper",),
        ).fetchall()
    ]
    conn.close()
    assert project_ids == [project["id"]]


def test_default_project_cannot_be_deleted(project_client):
    renamed = project_client.patch(
        f"/api/projects/{DEFAULT_PROJECT_ID}",
        json={"name": "Renamed default"},
    )
    assert renamed.status_code == 400
    assert renamed.json()["detail"] == "未分类项目不能重命名"

    available = project_client.get(f"/api/projects/{DEFAULT_PROJECT_ID}/available-papers")
    assert available.status_code == 400
    assert available.json()["detail"] == "未分类不能从其他项目导入论文"

    response = project_client.delete(f"/api/projects/{DEFAULT_PROJECT_ID}")
    assert response.status_code == 400
    assert response.json()["detail"] == "系统项目不能删除"
