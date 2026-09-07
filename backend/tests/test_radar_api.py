"""论文雷达本地 API 测试。"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from paper_graph.database import get_connection
from paper_graph.radar import upsert_radar_candidate, upsert_radar_match


@pytest.fixture
def project_client(tmp_path, monkeypatch):
    import main
    import paper_graph.database as database

    db_path = tmp_path / "radar-api.db"
    monkeypatch.setattr(main, "DB_PATH", db_path)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.init_db(db_path)
    return TestClient(main.app)


def test_radar_config_api_and_system_project_guard(project_client):
    created = project_client.post("/api/projects", json={"name": "Radar API"})
    project_id = created.json()["id"]
    response = project_client.put(
        "/api/radar/config",
        params={"project_id": project_id},
        json={
            "enabled": True,
            "categories": ["cs.AI"],
            "include_keywords": ["retrieval"],
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["categories"] == ["cs.AI"]

    blocked = project_client.put(
        "/api/radar/config",
        params={"project_id": "project_default"},
        json={"enabled": True, "categories": ["cs.AI"]},
    )
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == "未分类项目不能启用论文雷达"


def test_radar_matches_api_state_and_save(project_client, monkeypatch):
    created = project_client.post("/api/projects", json={"name": "Radar Match API"})
    project_id = created.json()["id"]
    import main

    conn = get_connection(main.DB_PATH)
    candidate = upsert_radar_candidate(conn, {"arxiv_id": "2609.01001", "title": "API paper"})
    match = upsert_radar_match(conn, project_id, candidate["id"], score=0.5)
    conn.close()
    listing = project_client.get("/api/radar/matches", params={"project_id": project_id})
    assert listing.status_code == 200
    assert listing.json()[0]["state"] == "unread"

    read = project_client.patch(
        f"/api/radar/matches/{match['id']}",
        json={"state": "read"},
    )
    assert read.status_code == 200
    assert read.json()["state"] == "read"

    monkeypatch.setattr(main, "ingest_arxiv_id", lambda *args, **kwargs: "arxiv_2609.01001")
    conn = get_connection(main.DB_PATH)
    conn.execute(
        "INSERT INTO papers (id, title, abstract, source) VALUES (?, ?, ?, ?)",
        ("arxiv_2609.01001", "API paper", "abstract", "arxiv"),
    )
    conn.commit()
    conn.close()
    saved = project_client.patch(
        f"/api/radar/matches/{match['id']}",
        json={"state": "saved"},
    )
    assert saved.status_code == 200
    assert saved.json()["state"] == "saved"
    assert saved.json()["paper_id"] == "arxiv_2609.01001"


def test_radar_scan_api_returns_structured_error(project_client, monkeypatch):
    created = project_client.post("/api/projects", json={"name": "Radar Scan API"})
    project_id = created.json()["id"]
    project_client.put(
        "/api/radar/config",
        params={"project_id": project_id},
        json={"enabled": True, "categories": ["cs.AI"]},
    )
    import paper_graph.radar as radar
    monkeypatch.setattr(radar, "fetch_arxiv_candidates", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("feed down")))
    response = project_client.post("/api/radar/scan", params={"project_id": project_id})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "RADAR_SCAN_FAILED"


def test_radar_sync_api_returns_structured_error(project_client):
    created = project_client.post("/api/projects", json={"name": "Radar Sync API"})
    response = project_client.post(
        "/api/radar/sync",
        json={"remote_url": "http://127.0.0.1:1", "token": "test"},
        params={"project_id": created.json()["id"]},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "RADAR_SYNC_FAILED"
