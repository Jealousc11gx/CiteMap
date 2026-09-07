"""Tests for chat_tools module (Agent tool execution functions)."""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from paper_graph.chat_tools import (
    search_arxiv,
    ingest_arxiv_paper,
    list_local_papers,
    search_local_papers,
    get_paper_details,
    annotate_paper_tool,
    download_paper_pdf,
    get_paper_notes,
    get_graph_summary,
)
from paper_graph.database import get_connection, upsert_paper, init_db


@pytest.fixture
def tmp_db(tmp_path):
    db_file = tmp_path / "test.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def populated_db(tmp_db):
    conn = get_connection(tmp_db)
    upsert_paper(conn, {
        "id": "arxiv_2401.00001",
        "title": "Test Paper 1",
        "abstract": "Abstract about transformers.",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
    })
    upsert_paper(conn, {
        "id": "arxiv_2401.00002",
        "title": "Test Paper 2",
        "abstract": "Abstract about RAG.",
        "published_date": "2024-01-03",
        "updated_date": "2024-01-04",
        "categories": "cs.CL",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2401.00002",
    })
    conn.commit()
    conn.close()
    return tmp_db


class TestSearchArxiv:
    def test_success(self, monkeypatch):
        mock_results = [
            {
                "id": "arxiv_2401.00001",
                "title": "Mock Paper",
                "abstract": "Mock abstract.",
                "published_date": "2024-01-01",
                "categories": "cs.AI",
                "arxiv_url": "https://arxiv.org/abs/2401.00001",
            }
        ]
        monkeypatch.setattr("paper_graph.chat_tools.search_arxiv_only", lambda q, max_results=5: mock_results)
        result = search_arxiv("test query")
        assert result["success"] is True
        assert result["count"] == 1
        assert result["papers"][0]["title"] == "Mock Paper"
        assert result["title"] == "找到 1 篇论文"
        assert "test query" in result["summary"]

    def test_exception(self, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.search_arxiv_only", lambda q, max_results=5: (_ for _ in ()).throw(RuntimeError("search failed")))
        result = search_arxiv("test query")
        assert result["success"] is False
        assert "search failed" in result["error"]
        assert result["title"] == "搜索失败"


class TestIngestArxivPaper:
    def test_success(self, tmp_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.ingest_arxiv_id", lambda arxiv_id, db_path, download_pdf=False, pdf_dir=None: "arxiv_mock_id")
        result = ingest_arxiv_paper("2401.00001")
        assert result["success"] is True
        assert result["paper_id"] == "arxiv_mock_id"
        assert result["title"] == "论文已入库"
        assert result["summary"] == "arxiv_mock_id"

    def test_failure(self, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.ingest_arxiv_id", lambda arxiv_id, db_path, download_pdf=False, pdf_dir=None: (_ for _ in ()).throw(RuntimeError("ingest failed")))
        result = ingest_arxiv_paper("2401.00001")
        assert result["success"] is False
        assert "ingest failed" in result["error"]
        assert result["title"] == "入库失败"


class TestListLocalPapers:
    def test_empty(self, tmp_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", tmp_db)
        result = list_local_papers()
        assert result["success"] is True
        assert result["count"] == 0
        assert result["papers"] == []
        assert result["title"] == "本地论文库有 0 篇"

    def test_with_data(self, populated_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = list_local_papers()
        assert result["success"] is True
        assert result["count"] == 2
        assert result["title"] == "本地论文库有 2 篇"

    def test_source_filter(self, populated_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = list_local_papers(source="arxiv")
        assert result["success"] is True
        assert result["count"] == 2
        assert "来源=arxiv" in result["summary"]

    def test_limit(self, populated_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = list_local_papers(limit=1)
        assert result["success"] is True
        assert len(result["papers"]) == 1


class TestSearchLocalPapers:
    def test_match(self, populated_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = search_local_papers("transformers")
        assert result["success"] is True
        assert result["count"] == 1
        assert result["papers"][0]["id"] == "arxiv_2401.00001"
        assert result["title"] == "找到 1 篇匹配"
        assert "transformers" in result["summary"]

    def test_no_match(self, populated_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = search_local_papers("nonexistent xyz")
        assert result["success"] is True
        assert result["count"] == 0
        assert result["title"] == "找到 0 篇匹配"

    def test_empty_db(self, tmp_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", tmp_db)
        result = search_local_papers("anything")
        assert result["success"] is True
        assert result["count"] == 0


class TestGetPaperDetails:
    def test_existing_paper(self, populated_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = get_paper_details("arxiv_2401.00001")
        assert result["success"] is True
        assert result["paper"]["id"] == "arxiv_2401.00001"
        assert result["paper"]["title"] == "Test Paper 1"
        assert result["title"] == "Test Paper 1"
        assert "Author" not in result["summary"]  # no authors in fixture

    def test_missing_paper(self, populated_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = get_paper_details("nonexistent_id")
        assert result["success"] is False
        assert "error" in result
        assert result["title"] == "论文不存在"

    def test_with_authors(self, populated_db, monkeypatch):
        conn = get_connection(populated_db)
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO authors (name) VALUES (?)", ("Author A",))
        author_id = cur.lastrowid
        cur.execute("INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)", ("arxiv_2401.00001", author_id, 0))
        conn.commit()
        conn.close()
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = get_paper_details("arxiv_2401.00001")
        assert result["success"] is True
        assert len(result["paper"]["authors"]) == 1
        assert result["paper"]["authors"][0]["name"] == "Author A"
        assert result["title"] == "Test Paper 1"
        assert "Author A" in result["summary"]


class TestAnnotatePaperTool:
    def test_success(self, tmp_db, monkeypatch):
        mock_result = {
            "core_contribution": "Test contribution",
            "teams": [],
        }
        monkeypatch.setattr(
            "paper_graph.chat_tools.annotate_paper",
            lambda paper_id, model=None, db_path=None: mock_result,
        )
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", tmp_db)
        # Insert a paper first
        conn = get_connection(tmp_db)
        upsert_paper(conn, {
            "id": "annotate_001",
            "title": "Annotate Me",
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
        result = annotate_paper_tool("annotate_001")
        assert result["success"] is True
        assert result["result"]["core_contribution"] == "Test contribution"
        assert result["title"] == "标注完成"
        assert "Test contribution" in result["summary"]

    def test_failure(self, monkeypatch):
        monkeypatch.setattr(
            "paper_graph.chat_tools.annotate_paper",
            lambda paper_id, model=None, db_path=None: (_ for _ in ()).throw(RuntimeError("annotate failed")),
        )
        result = annotate_paper_tool("any_id")
        assert result["success"] is False
        assert "annotate failed" in result["error"]
        assert result["title"] == "标注失败"


class TestDownloadPaperPdf:
    def test_success(self, populated_db, monkeypatch, tmp_path):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        mock_result = MagicMock()
        mock_result.pdf_url = "http://arxiv.org/pdf/2401.00001.pdf"
        mock_client = MagicMock()
        mock_client.results.return_value = [mock_result]
        import arxiv as arxiv_lib
        monkeypatch.setattr(arxiv_lib, "Client", lambda **kw: mock_client)

        pdf_path = tmp_path / "arxiv_2401.00001.pdf"
        pdf_path.write_bytes(b"fake pdf")
        monkeypatch.setattr("paper_graph.chat_tools._download_arxiv_pdf", lambda result, path: path.write_bytes(b"fake pdf"))

        result = download_paper_pdf("arxiv_2401.00001")
        assert result["success"] is True
        assert "pdf_path" in result
        assert result["title"] == "PDF 已下载"

    def test_non_arxiv_rejected(self, populated_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = download_paper_pdf("local_mock_id")
        assert result["success"] is False
        assert "仅支持 arXiv" in result["error"]
        assert result["title"] == "下载失败"

    def test_paper_not_found(self, populated_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        mock_client = MagicMock()
        mock_client.results.return_value = []
        import arxiv as arxiv_lib
        monkeypatch.setattr(arxiv_lib, "Client", lambda **kw: mock_client)
        result = download_paper_pdf("arxiv_2401.00099")
        assert result["success"] is False
        assert "论文不存在" in result["error"]
        assert result["title"] == "下载失败"


class TestGetPaperNotes:
    def test_with_notes(self, populated_db, monkeypatch, tmp_path):
        import paper_graph.notes as notes_mod
        monkeypatch.setattr(notes_mod, "NOTES_DIR", tmp_path)
        notes_mod.save_note(populated_db, "arxiv_2401.00001", "# My Note\ncontent")
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = get_paper_notes("arxiv_2401.00001")
        assert result["success"] is True
        assert result["note"]["paper_id"] == "arxiv_2401.00001"
        assert result["title"] == "笔记内容"
        assert "My Note" in result["summary"]

    def test_no_notes(self, populated_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = get_paper_notes("arxiv_2401.00001")
        assert result["success"] is False
        assert "没有笔记" in result["error"]
        assert result["title"] == "没有笔记"


class TestGetGraphSummary:
    def test_empty(self, tmp_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", tmp_db)
        result = get_graph_summary()
        assert result["success"] is True
        assert result["team_count"] == 0
        assert result["team_collaboration_count"] == 0
        assert result["title"] == "图谱统计"
        assert "0 个团队" in result["summary"]

    def test_with_data(self, populated_db, monkeypatch):
        monkeypatch.setattr("paper_graph.chat_tools.DB_PATH", populated_db)
        result = get_graph_summary()
        assert result["success"] is True
        assert "team_count" in result
        assert "paper_connection_count" in result
        assert result["title"] == "图谱统计"
