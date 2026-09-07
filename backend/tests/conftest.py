"""Pytest fixtures for backend tests."""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is on sys.path so paper_graph can be imported
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from paper_graph.database import init_db, get_connection, upsert_paper
from paper_graph.annotate import get_client, get_default_model
from main import app


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a temporary SQLite database path and initialize schema."""
    db_file = tmp_path / "test.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def client():
    """Provide a FastAPI TestClient."""
    return TestClient(app)


@pytest.fixture
def sample_paper(tmp_db):
    """Insert a sample paper into the temporary database and return its data."""
    paper = {
        "id": "test_paper_001",
        "title": "Test Paper Title",
        "abstract": "This is a test abstract for unit testing purposes.",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
    }
    conn = get_connection(tmp_db)
    upsert_paper(conn, paper)
    conn.commit()
    conn.close()
    return paper
