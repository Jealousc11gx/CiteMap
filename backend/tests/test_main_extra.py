"""Additional tests for main.py API endpoints not covered in test_main.py."""

import io
from unittest.mock import MagicMock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from paper_graph.database import init_db, get_connection, upsert_paper


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test.db"
    import main as main_module
    import paper_graph.database as db_module

    original_db_path = main_module.DB_PATH
    main_module.DB_PATH = db_file
    db_module.DB_PATH = db_file
    init_db(db_file)

    yield TestClient(app, raise_server_exceptions=False)

    main_module.DB_PATH = original_db_path
    db_module.DB_PATH = original_db_path


def _insert_paper(db_path, paper_id="test_paper"):
    conn = get_connection(db_path)
    upsert_paper(conn, {
        "id": paper_id,
        "title": f"Title {paper_id}",
        "abstract": "Abstract",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": f"https://arxiv.org/abs/{paper_id}",
    })
    conn.commit()
    conn.close()


class TestHealthEndpoints:
    def test_health_api(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_legacy(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "llm_configured" in data
        assert "model" in data


class TestGetPaperDetail:
    def test_get_existing_paper(self, client):
        import main as main_module
        db_file = main_module.DB_PATH
        _insert_paper(db_file, "detail_001")

        resp = client.get("/api/papers/detail_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Title detail_001"

    def test_get_missing_paper(self, client):
        resp = client.get("/api/papers/nonexistent")
        assert resp.status_code == 404
        assert "论文不存在" in resp.json()["detail"]


class TestBatchIngest:
    def test_batch_ingest_success(self, client, monkeypatch):
        monkeypatch.setattr("main.ingest_arxiv_id", lambda arxiv_id, db_path, download_pdf=False, pdf_dir=None: "arxiv_mock_id")
        monkeypatch.setattr("main.create_note_template", lambda db_path, paper_id: None)

        resp = client.post("/api/papers/batch-ingest", json={"paper_ids": ["2401.00001", "2401.00002"]})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        assert all(r["status"] == "success" for r in data["results"])

    def test_batch_ingest_partial_failure(self, client, monkeypatch):
        call_count = [0]

        def mock_ingest(arxiv_id, db_path, download_pdf=False, pdf_dir=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return "arxiv_mock_id"
            raise RuntimeError("ingest failed")

        monkeypatch.setattr("main.ingest_arxiv_id", mock_ingest)
        monkeypatch.setattr("main.create_note_template", lambda db_path, paper_id: None)

        resp = client.post("/api/papers/batch-ingest", json={"paper_ids": ["2401.00001", "2401.00002"]})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        assert data["results"][0]["status"] == "success"
        assert data["results"][1]["status"] == "error"
        assert "ingest failed" in data["results"][1]["error"]


class TestPaperVenueEndpoint:
    def test_manual_venue_override_and_clear(self, client):
        import main as main_module

        conn = get_connection(main_module.DB_PATH)
        upsert_paper(conn, {
            "id": "venue-paper",
            "title": "Venue Paper",
            "abstract": "Abstract",
            "published_date": "2025-01-01",
            "updated_date": "2025-01-01",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "",
        })
        conn.commit()
        conn.close()

        response = client.patch(
            "/api/papers/venue-paper/venue",
            json={"venue": "AAAI", "venue_year": 2026},
        )
        assert response.status_code == 200
        assert response.json()["venue"] == "AAAI"
        assert response.json()["venue_year"] == 2026
        assert response.json()["venue_source"] == "manual"

        response = client.patch(
            "/api/papers/venue-paper/venue",
            json={"venue": None, "venue_year": None},
        )
        assert response.status_code == 200
        assert response.json()["venue"] is None
        assert response.json()["venue_checked_at"] is None
        assert response.json()["venue_source"] is None

    def test_rejects_partial_manual_venue(self, client):
        import main as main_module

        conn = get_connection(main_module.DB_PATH)
        upsert_paper(conn, {
            "id": "venue-partial",
            "title": "Venue Paper",
            "abstract": "Abstract",
            "published_date": "2025-01-01",
            "updated_date": "2025-01-01",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "",
        })
        conn.commit()
        conn.close()
        response = client.patch(
            "/api/papers/venue-partial/venue",
            json={"venue": "AAAI", "venue_year": None},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "venue 与 venue_year 必须同时填写或同时清空"


class TestGraphEndpoints:
    def test_graph_team_empty(self, client):
        resp = client.get("/api/graph/team")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_graph_team_ego_empty(self, client):
        resp = client.get("/api/graph/team-ego")
        assert resp.status_code == 200
        assert resp.json() == {"nodes": [], "edges": []}

    def test_graph_paper_empty(self, client):
        resp = client.get("/api/graph/paper")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data

    def test_graph_team_with_data(self, client):
        import main as main_module
        db_file = main_module.DB_PATH

        conn = get_connection(db_file)
        upsert_paper(conn, {
            "id": "g1",
            "title": "Graph Paper",
            "abstract": "Abstract",
            "published_date": "2024-01-01",
            "updated_date": "2024-01-02",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00001",
        })
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO teams (name) VALUES (?)", ("Team A",))
        team_id = cur.lastrowid
        cur.execute("INSERT OR IGNORE INTO paper_teams (paper_id, team_id) VALUES (?, ?)", ("g1", team_id))
        conn.commit()
        conn.close()

        resp = client.get("/api/graph/team")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == team_id

    def test_graph_paper_with_data(self, client):
        import main as main_module
        db_file = main_module.DB_PATH

        conn = get_connection(db_file)
        upsert_paper(conn, {
            "id": "gp1",
            "title": "Paper 1",
            "abstract": "Abstract 1",
            "published_date": "2024-01-01",
            "updated_date": "2024-01-02",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00001",
        })
        upsert_paper(conn, {
            "id": "gp2",
            "title": "Paper 2",
            "abstract": "Abstract 2",
            "published_date": "2024-01-03",
            "updated_date": "2024-01-04",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00002",
        })
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO authors (name) VALUES (?)", ("Shared Author",))
        author_id = cur.lastrowid
        cur.execute("INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)", ("gp1", author_id, 0))
        cur.execute("INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)", ("gp2", author_id, 0))
        conn.commit()
        conn.close()

        resp = client.get("/api/graph/paper")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1


class TestAnnotateEndpoint:
    def test_annotate_not_found(self, client):
        resp = client.post("/api/papers/nonexistent/annotate", json={})
        assert resp.status_code == 400

    def test_annotate_success(self, client, monkeypatch):
        import main as main_module
        db_file = main_module.DB_PATH
        _insert_paper(db_file, "ann_001")

        mock_result = {
            "core_contribution": "Test contribution",
            "teams": [],
        }
        monkeypatch.setattr(
            "main.annotate_paper",
            lambda paper_id, model=None, db_path=None, force=False: mock_result,
        )

        resp = client.post("/api/papers/ann_001/annotate", json={})
        assert resp.status_code == 200
        assert resp.json()["core_contribution"] == "Test contribution"


class TestIngestArxivEndpoint:
    def test_ingest_arxiv_success(self, client, monkeypatch):
        monkeypatch.setattr("main.ingest_arxiv_id", lambda arxiv_id, db_path, download_pdf=False, pdf_dir=None: "arxiv_mock_id")
        monkeypatch.setattr("main.create_note_template", lambda db_path, paper_id: None)

        resp = client.post("/api/papers/ingest-arxiv", json={"arxiv_id": "2401.00001"})
        assert resp.status_code == 200
        assert resp.json()["paper_id"] == "arxiv_mock_id"

    def test_ingest_arxiv_with_pdf(self, client, monkeypatch):
        captured = {}

        def mock_ingest(arxiv_id, db_path, download_pdf=False, pdf_dir=None):
            captured["download_pdf"] = download_pdf
            return "arxiv_mock_id"

        monkeypatch.setattr("main.ingest_arxiv_id", mock_ingest)
        monkeypatch.setattr("main.create_note_template", lambda db_path, paper_id: None)

        resp = client.post("/api/papers/ingest-arxiv", json={"arxiv_id": "2401.00001", "download_pdf": True})
        assert resp.status_code == 200
        assert captured["download_pdf"] is True


class TestDownloadPdfEndpoint:
    def test_download_pdf_success(self, client, monkeypatch):
        import main as main_module
        db_file = main_module.DB_PATH
        _insert_paper(db_file, "arxiv_2401.00099")

        mock_result = MagicMock()
        mock_result.entry_id = "http://arxiv.org/abs/2401.00099"
        mock_result.pdf_url = "http://arxiv.org/pdf/2401.00099.pdf"
        mock_client = MagicMock()
        mock_client.results.return_value = [mock_result]
        monkeypatch.setattr("main.arxiv.Client", lambda **kwargs: mock_client)

        def mock_download(result, pdf_path, timeout=60):
            pdf_path.write_bytes(b"fake pdf content")

        monkeypatch.setattr("main._download_arxiv_pdf", mock_download)

        resp = client.post("/api/papers/arxiv_2401.00099/download-pdf")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["pdf_path"].endswith("arxiv_2401.00099.pdf")

    def test_download_pdf_not_found(self, client, monkeypatch):
        mock_client = MagicMock()
        mock_client.results.return_value = []
        monkeypatch.setattr("main.arxiv.Client", lambda **kwargs: mock_client)

        resp = client.post("/api/papers/arxiv_2401.00099/download-pdf")
        assert resp.status_code == 400


class TestChatSessionsEndpoints:
    def test_list_sessions_empty(self, client):
        resp = client.get("/api/chat/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_delete_session(self, client):
        resp = client.post("/api/chat/sessions", json={"title": "Extra Test"})
        assert resp.status_code == 200
        session_id = resp.json()["id"]

        resp = client.delete(f"/api/chat/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_get_messages_empty_session(self, client):
        resp = client.post("/api/chat/sessions", json={"title": "Empty"})
        session_id = resp.json()["id"]
        resp = client.get(f"/api/chat/sessions/{session_id}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_messages_missing_session(self, client):
        resp = client.get("/api/chat/sessions/nonexistent/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_delete_missing_session(self, client):
        resp = client.delete("/api/chat/sessions/nonexistent")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"


class TestNotesEndpoints:
    def test_list_notes_empty(self, client):
        resp = client.get("/api/notes")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_missing_note(self, client):
        resp = client.get("/api/notes/nonexistent")
        assert resp.status_code == 404
        assert "笔记不存在" in resp.json()["detail"]

    def test_delete_missing_note(self, client):
        resp = client.delete("/api/notes/nonexistent")
        assert resp.status_code == 500

    def test_save_and_delete_note(self, client, tmp_path, monkeypatch):
        import paper_graph.notes as notes_mod
        notes_dir = tmp_path / "notes"
        notes_dir.mkdir()
        monkeypatch.setattr(notes_mod, "NOTES_DIR", notes_dir)

        import main as main_module
        db_file = main_module.DB_PATH
        _insert_paper(db_file, "note_extra")

        resp = client.post("/api/notes/note_extra/template")
        assert resp.status_code == 200

        resp = client.post("/api/notes/note_extra", json={"content": "# New note\nbody"})
        assert resp.status_code == 200

        resp = client.get("/api/notes/note_extra")
        assert resp.status_code == 200
        assert resp.json()["body"] == "# New note\nbody"

        resp = client.delete("/api/notes/note_extra")
        assert resp.status_code == 200

        resp = client.get("/api/notes/note_extra")
        assert resp.status_code == 404
