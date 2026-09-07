"""Integration tests for FastAPI routes in main.py."""

import io
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from paper_graph.database import init_db, get_connection, upsert_paper


@pytest.fixture
def client(tmp_path):
    """Provide a FastAPI TestClient with an isolated database."""
    db_file = tmp_path / "test.db"
    # Patch the DB_PATH used by main.py
    import main as main_module
    import paper_graph.database as db_module

    original_db_path = main_module.DB_PATH
    main_module.DB_PATH = db_file
    db_module.DB_PATH = db_file
    init_db(db_file)

    yield TestClient(app)

    main_module.DB_PATH = original_db_path
    db_module.DB_PATH = original_db_path


class TestSearchAndList:
    def test_list_papers_empty(self, client):
        resp = client.get("/api/papers")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_papers_with_data(self, client, tmp_path):
        db_file = tmp_path / "test.db"
        paper = {
            "id": "search_001",
            "title": "Attention Is All You Need",
            "abstract": "We propose a new model.",
            "published_date": "2024-01-01",
            "updated_date": "2024-01-02",
            "categories": "cs.CL",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/1706.03762",
        }
        conn = get_connection(db_file)
        upsert_paper(conn, paper)
        conn.commit()
        conn.close()

        resp = client.get("/api/papers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Attention Is All You Need"

    def test_search_papers_with_regex_safe(self, client, tmp_path):
        db_file = tmp_path / "test.db"
        paper = {
            "id": "search_002",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "abstract": "We introduce BERT.",
            "published_date": "2024-01-01",
            "updated_date": "2024-01-02",
            "categories": "cs.CL",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/1810.04805",
        }
        conn = get_connection(db_file)
        upsert_paper(conn, paper)
        conn.commit()
        conn.close()

        # Should not crash on regex metacharacters
        resp = client.get("/api/papers?q=.*")
        assert resp.status_code == 200

        resp = client.get("/api/papers?q=BERT")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    def test_list_papers_returns_and_searches_structured_annotation(self, client, tmp_path):
        db_file = tmp_path / "test.db"
        paper = {
            "id": "tagged_001",
            "title": "Structured Annotation",
            "abstract": "Paper abstract.",
            "published_date": "2024-01-01",
            "updated_date": "2024-01-02",
            "categories": "cs.LG",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00003",
        }
        conn = get_connection(db_file)
        upsert_paper(conn, paper)
        conn.execute(
            "UPDATE papers SET tldr = ?, primary_domain = ?, subfields = ? WHERE id = ?",
            ("完整 TLDR", "Machine Learning", '["Model Compression"]', paper["id"]),
        )
        conn.execute("INSERT INTO tags (name, type) VALUES (?, ?)", ("Mixture of Experts", "model"))
        tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", ("Mixture of Experts",)).fetchone()[0]
        conn.execute("INSERT INTO paper_tags (paper_id, tag_id) VALUES (?, ?)", (paper["id"], tag_id))
        conn.commit()
        conn.close()

        response = client.get("/api/papers?q=Mixture%20of%20Experts")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["tldr"] == "完整 TLDR"
        assert data[0]["subfields"] == ["Model Compression"]
        assert data[0]["tags"] == [{"name": "Mixture of Experts", "type": "model"}]


class TestIngestPdf:
    def test_ingest_non_pdf_rejected(self, client):
        fake_file = io.BytesIO(b"not a pdf")
        resp = client.post(
            "/api/papers/ingest-pdf",
            files={"file": ("evil.exe", fake_file, "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "PDF" in resp.json()["detail"]

    def test_ingest_pdf_empty_filename(self, client):
        fake_file = io.BytesIO(b"%PDF-1.4 fake")
        resp = client.post(
            "/api/papers/ingest-pdf",
            files={"file": ("", fake_file, "application/pdf")},
        )
        # FastAPI rejects empty filename at framework level (422)
        assert resp.status_code in (400, 422)

    def test_ingest_path_traversal_filename(self, client, tmp_path):
        fake_file = io.BytesIO(b"%PDF-1.4 fake")
        resp = client.post(
            "/api/papers/ingest-pdf",
            files={"file": ("../../etc/passwd", fake_file, "application/pdf")},
        )
        # basename strips directory, but extension is not .pdf, so rejected
        assert resp.status_code == 400
        assert "PDF" in resp.json()["detail"]


class TestNotes:
    def test_list_notes_empty(self, client):
        resp = client.get("/api/notes")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_note_crud(self, client, tmp_path):
        db_file = tmp_path / "test.db"
        paper_id = "note_001"
        paper = {
            "id": paper_id,
            "title": "Note Paper",
            "abstract": "Abstract",
            "published_date": "2024-01-01",
            "updated_date": "2024-01-02",
            "categories": "cs.CL",
            "pdf_path": None,
            "source": "local",
            "arxiv_url": None,
        }
        conn = get_connection(db_file)
        upsert_paper(conn, paper)
        conn.commit()
        conn.close()

        # Create template
        resp = client.post(f"/api/notes/{paper_id}/template")
        assert resp.status_code == 200

        # Get note
        resp = client.get(f"/api/notes/{paper_id}")
        assert resp.status_code == 200
        assert "content" in resp.json()

        # Save note
        new_content = "# Updated\n\nNew content here."
        resp = client.post(f"/api/notes/{paper_id}", json={"content": new_content})
        assert resp.status_code == 200

        # List notes
        resp = client.get("/api/notes")
        assert resp.status_code == 200
        notes = resp.json()
        assert len(notes) == 1
        assert notes[0]["paper_id"] == paper_id
        assert "updated_at" in notes[0]

        # Delete note
        resp = client.delete(f"/api/notes/{paper_id}")
        assert resp.status_code == 200

        resp = client.get(f"/api/notes/{paper_id}")
        assert resp.status_code == 404


class TestDownloadPdf:
    def test_download_pdf_success(self, client, monkeypatch):
        paper = {
            "id": "arxiv_2401.00099",
            "title": "Downloadable Paper",
            "abstract": "Abstract",
            "published_date": "2024-01-01",
            "updated_date": "2024-01-02",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00099",
        }
        conn = get_connection()
        upsert_paper(conn, paper)
        conn.commit()
        conn.close()

        mock_result = MagicMock()
        mock_result.entry_id = "http://arxiv.org/abs/2401.00099"
        mock_result.pdf_url = "http://arxiv.org/pdf/2401.00099.pdf"

        mock_client = MagicMock()
        mock_client.results.return_value = [mock_result]
        monkeypatch.setattr("main.arxiv.Client", lambda **kwargs: mock_client)

        written = []

        def mock_download(result, pdf_path, timeout=60):
            pdf_path.write_bytes(b"fake pdf content")
            written.append(pdf_path)

        monkeypatch.setattr("main._download_arxiv_pdf", mock_download)

        resp = client.post("/api/papers/arxiv_2401.00099/download-pdf")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["pdf_path"].endswith("arxiv_2401.00099.pdf")

        conn = get_connection()
        row = conn.execute("SELECT pdf_path FROM papers WHERE id = ?", ("arxiv_2401.00099",)).fetchone()
        conn.close()
        assert row["pdf_path"] is not None

    def test_download_pdf_not_found(self, client, monkeypatch):
        mock_client = MagicMock()
        mock_client.results.return_value = []
        monkeypatch.setattr("main.arxiv.Client", lambda **kwargs: mock_client)

        resp = client.post("/api/papers/arxiv_2401.00099/download-pdf")
        # Endpoint wraps HTTPException into 400
        assert resp.status_code == 400


class TestIngestPdfEndpoint:
    def test_ingest_pdf_success(self, client, monkeypatch):
        captured = {}

        def mock_ingest(pdf_path, db_path, pdf_dir=None, source_name=None):
            captured["pdf_path"] = str(pdf_path)
            captured["db_path"] = str(db_path)
            captured["pdf_dir"] = str(pdf_dir)
            captured["source_name"] = source_name
            return "local_mock_pdf_id"

        monkeypatch.setattr("main.ingest_local_pdf", mock_ingest)

        resp = client.post(
            "/api/papers/ingest-pdf",
            files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["paper_id"] == "local_mock_pdf_id"
        assert captured["source_name"] == "doc.pdf"


class TestBatchAnnotate:
    def test_batch_annotate_and_annotate_all(self, client, monkeypatch):
        paper = {
            "id": "batch_001",
            "title": "Batch Paper",
            "abstract": "Abstract",
            "published_date": "2024-01-01",
            "updated_date": "2024-01-02",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00001",
            "core_contribution": "",
        }
        conn = get_connection()
        upsert_paper(conn, paper)
        conn.commit()
        conn.close()

        def mock_annotate_all(model=None, api_key=None, base_url=None, db_path=None):
            return 1

        monkeypatch.setattr("main.annotate_all", mock_annotate_all)

        resp = client.post("/api/papers/batch-annotate", json={"model": "test-model"})
        assert resp.status_code == 200
        assert resp.json()["annotated_count"] == 1

        resp = client.post("/api/papers/annotate-all", json={})
        assert resp.status_code == 200
        assert "annotated_count" in resp.json()
