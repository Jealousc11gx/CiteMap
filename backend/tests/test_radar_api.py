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
    assert blocked.json()["detail"] == "未分类项目不能启用论文雷达，请新建研究项目后再配置雷达"


def test_radar_connection_token_can_be_replaced_and_cleared(project_client):
    saved = project_client.put(
        "/api/radar/connection",
        json={"remote_url": "https://radar.example.com", "token": "first-token"},
    )
    assert saved.status_code == 200
    assert saved.json()["token_configured"] is True
    assert "first-token" not in str(saved.json())

    replaced = project_client.put(
        "/api/radar/connection",
        json={"remote_url": "https://radar.example.com", "token": "next-token"},
    )
    assert replaced.status_code == 200
    assert replaced.json()["token_configured"] is True

    cleared = project_client.put(
        "/api/radar/connection",
        json={"remote_url": "https://radar.example.com", "clear_token": True},
    )
    assert cleared.status_code == 200
    assert cleared.json()["token_configured"] is False


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


def test_radar_connection_api_persists_and_masks_token(project_client):
    saved = project_client.put(
        "/api/radar/connection",
        json={"remote_url": "https://radar.example.workers.dev/sync", "token": "secret"},
    )
    assert saved.status_code == 200
    assert saved.json()["remote_url"] == "https://radar.example.workers.dev"
    assert saved.json()["token_configured"] is True
    assert "token" not in saved.json()

    loaded = project_client.get("/api/radar/connection")
    assert loaded.status_code == 200
    assert loaded.json()["remote_url"] == "https://radar.example.workers.dev"
    assert "secret" not in loaded.text


def test_radar_sync_uses_persisted_connection(project_client, monkeypatch):
    import main

    created = project_client.post("/api/projects", json={"name": "Persisted sync"})
    project_id = created.json()["id"]
    project_client.put(
        "/api/radar/connection",
        json={"remote_url": "https://radar.example", "token": "stored-secret"},
    )
    credentials = []

    class FakeClient:
        def __init__(self, base_url, token):
            self.base_url = base_url
            credentials.append((base_url, token))

        def publish_profile(self, current_project_id, profile):
            return {"ok": True}

    monkeypatch.setattr(main, "RadarRemoteClient", FakeClient)
    monkeypatch.setattr(main, "flush_pending_operations", lambda conn, client: {"sent": 0, "failed": 0})
    monkeypatch.setattr(main, "sync_remote_changes", lambda conn, client: {"applied": 0, "pages": 1, "cursor": "0"})

    response = project_client.post(
        "/api/radar/sync",
        params={"project_id": project_id},
        json={"publish_profile": False},
    )
    assert response.status_code == 200
    assert credentials == [("https://radar.example", "stored-secret")]


def test_radar_sync_only_publishes_changed_profile_unless_forced(project_client, monkeypatch):
    import main

    created = project_client.post("/api/projects", json={"name": "Profile fingerprint"})
    project_id = created.json()["id"]
    published = []

    class FakeClient:
        def __init__(self, base_url, token):
            self.base_url = base_url.rstrip("/")

        def publish_profile(self, current_project_id, profile):
            published.append((current_project_id, profile))
            return {"ok": True}

    monkeypatch.setattr(main, "RadarRemoteClient", FakeClient)
    monkeypatch.setattr(main, "flush_pending_operations", lambda conn, client: {"sent": 0, "failed": 0})
    monkeypatch.setattr(main, "sync_remote_changes", lambda conn, client: {"applied": 0, "pages": 1, "cursor": "0"})
    payload = {"remote_url": "https://radar.example", "token": "secret"}

    first = project_client.post("/api/radar/sync", params={"project_id": project_id}, json=payload)
    second = project_client.post("/api/radar/sync", params={"project_id": project_id}, json=payload)
    forced = project_client.post(
        "/api/radar/sync",
        params={"project_id": project_id},
        json={**payload, "force_publish_profile": True},
    )

    assert first.status_code == 200
    assert first.json()["published"] == 1
    assert second.json()["published"] == 0
    assert forced.json()["published"] == 1
    assert forced.json()["profile_forced"] is True
    assert len(published) == 2
