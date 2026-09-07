"""Tests for database module direct functions (init_db, upsert_paper, get_paper, list_papers, chat CRUD)."""

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from paper_graph.database import (
    init_db,
    get_connection,
    upsert_paper,
    get_paper,
    list_papers,
    create_chat_session,
    get_chat_session,
    list_chat_sessions,
    delete_chat_session,
    add_chat_message,
    get_chat_messages,
)


def test_init_db_creates_tables(tmp_path):
    db_file = tmp_path / "test.db"
    init_db(db_file)
    conn = get_connection(db_file)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row["name"] for row in cur.fetchall()}
    conn.close()
    expected = {"papers", "authors", "institutions", "paper_authors", "paper_institutions",
                "teams", "team_members", "paper_teams", "chat_sessions", "chat_messages"}
    assert expected.issubset(tables)


def test_init_db_idempotent(tmp_path):
    db_file = tmp_path / "test.db"
    init_db(db_file)
    init_db(db_file)  # second call should not raise
    conn = get_connection(db_file)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row["name"] for row in cur.fetchall()}
    conn.close()
    assert "papers" in tables


def test_upsert_paper_inserts(tmp_path):
    db_file = tmp_path / "test.db"
    init_db(db_file)
    conn = get_connection(db_file)
    paper = {
        "id": "db_001",
        "title": "DB Paper",
        "abstract": "Abstract",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
    }
    upsert_paper(conn, paper)
    conn.commit()
    conn.close()
    conn2 = get_connection(db_file)
    row = conn2.execute("SELECT * FROM papers WHERE id = ?", ("db_001",)).fetchone()
    conn2.close()
    assert row is not None
    assert row["title"] == "DB Paper"


def test_upsert_paper_updates(tmp_path):
    db_file = tmp_path / "test.db"
    init_db(db_file)
    conn = get_connection(db_file)
    paper = {
        "id": "db_002",
        "title": "Original",
        "abstract": "Abstract",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
    }
    upsert_paper(conn, paper)
    conn.commit()
    upsert_paper(conn, {**paper, "title": "Updated", "abstract": "New abstract"})
    conn.commit()
    conn.close()
    conn2 = get_connection(db_file)
    row = conn2.execute("SELECT title, abstract FROM papers WHERE id = ?", ("db_002",)).fetchone()
    conn2.close()
    assert row["title"] == "Updated"
    assert row["abstract"] == "New abstract"


def test_get_paper_existing(tmp_path):
    db_file = tmp_path / "test.db"
    init_db(db_file)
    conn = get_connection(db_file)
    upsert_paper(conn, {
        "id": "gp_001",
        "title": "Get Paper",
        "abstract": "Abstract",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
    })
    conn.commit()
    conn.close()
    conn2 = get_connection(db_file)
    row = get_paper(conn2, "gp_001")
    conn2.close()
    assert row is not None
    assert row["title"] == "Get Paper"


def test_get_paper_missing(tmp_path):
    db_file = tmp_path / "test.db"
    init_db(db_file)
    conn = get_connection(db_file)
    row = get_paper(conn, "nonexistent")
    conn.close()
    assert row is None


def test_list_papers_empty(tmp_path):
    db_file = tmp_path / "test.db"
    init_db(db_file)
    df = list_papers(db_file)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


def test_list_papers_with_data(tmp_path):
    db_file = tmp_path / "test.db"
    init_db(db_file)
    conn = get_connection(db_file)
    upsert_paper(conn, {
        "id": "lp_001",
        "title": "List Paper",
        "abstract": "Abstract",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
    })
    conn.commit()
    conn.close()
    df = list_papers(db_file)
    assert len(df) == 1
    assert df.iloc[0]["title"] == "List Paper"


def test_list_papers_source_filter(tmp_path):
    db_file = tmp_path / "test.db"
    init_db(db_file)
    conn = get_connection(db_file)
    upsert_paper(conn, {
        "id": "lp_001",
        "title": "Arxiv Paper",
        "abstract": "Abstract",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
    })
    upsert_paper(conn, {
        "id": "lp_002",
        "title": "Local Paper",
        "abstract": "Abstract",
        "published_date": "2024-01-03",
        "updated_date": "2024-01-04",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "local",
        "arxiv_url": None,
    })
    conn.commit()
    conn.close()
    df_arxiv = list_papers(db_file, source="arxiv")
    df_local = list_papers(db_file, source="local")
    assert len(df_arxiv) == 1
    assert len(df_local) == 1


def test_list_papers_json_safe(tmp_path):
    """NaN values should be replaced with None for JSON serialization."""
    db_file = tmp_path / "test.db"
    init_db(db_file)
    conn = get_connection(db_file)
    conn.execute("INSERT INTO papers (id, title, abstract, published_date, updated_date, categories, pdf_path, source, arxiv_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 ("nan_paper", "NaN Paper", None, None, None, "cs.AI", None, "arxiv", None))
    conn.commit()
    conn.close()
    df = list_papers(db_file)
    row = df.iloc[0]
    assert row["abstract"] is None
    assert row["published_date"] is None


class TestChatCrud:
    def test_create_and_get_session(self, tmp_path):
        db_file = tmp_path / "test.db"
        init_db(db_file)
        conn = get_connection(db_file)
        create_chat_session(conn, "s1", "Session 1")
        conn.commit()
        session = get_chat_session(conn, "s1")
        conn.close()
        assert session is not None
        assert session["title"] == "Session 1"
        assert session["id"] == "s1"

    def test_create_duplicate_session(self, tmp_path):
        db_file = tmp_path / "test.db"
        init_db(db_file)
        conn = get_connection(db_file)
        create_chat_session(conn, "s1", "First")
        create_chat_session(conn, "s1", "Second")  # should not overwrite due to INSERT OR IGNORE
        conn.commit()
        session = get_chat_session(conn, "s1")
        conn.close()
        assert session["title"] == "First"

    def test_list_sessions(self, tmp_path):
        db_file = tmp_path / "test.db"
        init_db(db_file)
        conn = get_connection(db_file)
        create_chat_session(conn, "s1", "Session 1")
        create_chat_session(conn, "s2", "Session 2")
        conn.commit()
        sessions = list_chat_sessions(conn)
        conn.close()
        assert len(sessions) == 2

    def test_delete_session(self, tmp_path):
        db_file = tmp_path / "test.db"
        init_db(db_file)
        conn = get_connection(db_file)
        create_chat_session(conn, "s1", "Session 1")
        conn.commit()
        delete_chat_session(conn, "s1")
        session = get_chat_session(conn, "s1")
        conn.close()
        assert session is None

    def test_delete_session_cascades_messages(self, tmp_path):
        db_file = tmp_path / "test.db"
        init_db(db_file)
        conn = get_connection(db_file)
        create_chat_session(conn, "s1", "Session 1")
        add_chat_message(conn, "m1", "s1", "user", "hello")
        add_chat_message(conn, "m2", "s1", "assistant", "hi")
        conn.commit()
        delete_chat_session(conn, "s1")
        messages = get_chat_messages(conn, "s1")
        conn.close()
        assert messages == []

    def test_add_and_get_messages(self, tmp_path):
        db_file = tmp_path / "test.db"
        init_db(db_file)
        conn = get_connection(db_file)
        create_chat_session(conn, "s1", "Session 1")
        add_chat_message(conn, "m1", "s1", "user", "hello")
        add_chat_message(conn, "m2", "s1", "assistant", "hi", papers='[{"id": "p1"}]')
        conn.commit()
        messages = get_chat_messages(conn, "s1")
        conn.close()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hello"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "hi"
        assert messages[1]["papers"] == '[{"id": "p1"}]'

    def test_messages_ordered_by_created_at(self, tmp_path):
        db_file = tmp_path / "test.db"
        init_db(db_file)
        conn = get_connection(db_file)
        create_chat_session(conn, "s1", "Session 1")
        add_chat_message(conn, "m1", "s1", "user", "first")
        add_chat_message(conn, "m2", "s1", "user", "second")
        conn.commit()
        messages = get_chat_messages(conn, "s1")
        conn.close()
        assert [m["content"] for m in messages] == ["first", "second"]

    def test_get_messages_for_missing_session(self, tmp_path):
        db_file = tmp_path / "test.db"
        init_db(db_file)
        conn = get_connection(db_file)
        messages = get_chat_messages(conn, "nonexistent")
        conn.close()
        assert messages == []
