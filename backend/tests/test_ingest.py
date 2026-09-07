"""Tests for ingest module."""

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import fitz

from paper_graph.ingest import (
    _parse_arxiv_id,
    _download_arxiv_pdf,
    _extract_authors_from_text,
    _fetch_arxiv_result,
    _select_tldr_sections,
    extract_arxiv_id,
    extract_pdf_context,
    extract_pdf_metadata,
    enrich_paper_metadata_from_pdf,
    ingest_arxiv_id,
    ingest_local_pdf,
    search_arxiv,
    search_arxiv_only,
)


def test_select_tldr_sections_covers_method_results_and_conclusion():
    pages = [
        "1 Introduction\nProblem context and motivation.\n\n2 Method\nA structured pruning method.",
        "3 Experiments\nAccuracy improves by 12 percent.\n\n4 Conclusion\nThe method reduces inference cost.",
    ]

    excerpt = _select_tldr_sections(pages)

    assert "structured pruning method" in excerpt
    assert "improves by 12 percent" in excerpt
    assert "reduces inference cost" in excerpt


class TestParseArxivId:
    def test_with_full_url(self):
        assert _parse_arxiv_id("https://arxiv.org/abs/2401.00001") == "2401.00001"

    def test_with_prefix(self):
        assert _parse_arxiv_id("arxiv_2401.00001") == "2401.00001"

    def test_plain_id(self):
        assert _parse_arxiv_id("2401.00001") == "2401.00001"

    def test_id_with_version(self):
        assert _parse_arxiv_id("2401.00001v2") == "2401.00001"

    def test_extracts_id_from_arxiv_pdf_text(self):
        assert extract_arxiv_id("arXiv:2507.23279v3 [cs.CL] 11 Feb 2026") == "2507.23279"


class TestExtractPdfContext:
    def test_extracts_arxiv_id_and_multiple_pages(self, tmp_path):
        pdf_file = tmp_path / "paper.pdf"
        doc = fitz.open()
        first = doc.new_page()
        first.insert_text((72, 72), "arXiv:2507.23279v3 [cs.CL]")
        first.insert_text((72, 100), "Canonical Paper Title")
        second = doc.new_page()
        second.insert_text((72, 72), "1 Introduction")
        second.insert_text((72, 100), "Important method details.")
        doc.save(pdf_file)
        doc.close()

        context = extract_pdf_context(pdf_file)

        assert context["arxiv_id"] == "2507.23279"
        assert context["page_count"] == 2
        assert "Canonical Paper Title" in context["first_page"]
        assert "Important method details" in context["excerpt"]


class TestSearchArxivOnly:
    def test_returns_correct_format(self):
        mock_result = MagicMock()
        mock_result.entry_id = "http://arxiv.org/abs/2401.00001"
        mock_result.title = "Mock Paper Title"
        mock_result.summary = "Mock abstract text here."
        mock_result.published = datetime.datetime(2024, 1, 1)
        mock_result.updated = datetime.datetime(2024, 1, 2)
        mock_result.categories = ["cs.AI", "cs.CL"]
        mock_result.authors = ["Author One", "Author Two"]

        with patch("paper_graph.ingest.arxiv.Client") as MockClient, \
             patch("paper_graph.ingest.arxiv.Search") as MockSearch, \
             patch("paper_graph.ingest.arxiv.SortCriterion") as MockSort:
            MockSort.Relevance = "relevance"
            mock_client_instance = MockClient.return_value
            mock_client_instance.results.return_value = [mock_result]

            results = search_arxiv_only("test query", max_results=5)

        assert len(results) == 1
        r = results[0]
        assert r["id"] == "arxiv_2401.00001"
        assert r["title"] == "Mock Paper Title"
        assert r["abstract"] == "Mock abstract text here."
        assert r["published_date"] == "2024-01-01"
        assert r["categories"] == "cs.AI, cs.CL"
        assert r["arxiv_url"] == "http://arxiv.org/abs/2401.00001"
        assert r["authors"] == ["Author One", "Author Two"]


class TestIngestArxivId:
    def test_writes_to_db(self, tmp_db):
        mock_result = MagicMock()
        mock_result.entry_id = "http://arxiv.org/abs/2401.00001"
        mock_result.title = "Mock Paper Title"
        mock_result.summary = "Mock abstract text here."
        mock_result.published = datetime.datetime(2024, 1, 1)
        mock_result.updated = datetime.datetime(2024, 1, 2)
        mock_result.categories = ["cs.AI"]
        mock_result.authors = ["Author One"]
        mock_result.affiliation = ["Inst A"]

        with patch("paper_graph.ingest.arxiv.Client") as MockClient, \
             patch("paper_graph.ingest.arxiv.Search") as MockSearch:
            MockClient.return_value.results.return_value = [mock_result]
            MockSearch.return_value

            paper_id = ingest_arxiv_id("2401.00001", db_path=tmp_db)

        assert paper_id == "arxiv_2401.00001"

        import paper_graph.database as db_mod
        conn = db_mod.get_connection(tmp_db)
        paper = db_mod.get_paper(conn, paper_id)
        conn.close()

        assert paper is not None
        assert paper["title"] == "Mock Paper Title"
        assert paper["source"] == "arxiv"
        assert paper["arxiv_url"] == "http://arxiv.org/abs/2401.00001"

    def test_metadata_falls_back_to_abs_page_on_api_error(self):
        html = """
        <html><head>
        <meta name="citation_title" content="Fallback Title" />
        <meta name="citation_author" content="Doe, Jane" />
        <meta name="citation_date" content="2025/07/31" />
        <meta name="citation_online_date" content="2026/02/11" />
        <meta name="citation_pdf_url" content="https://arxiv.org/pdf/2507.23279" />
        <meta name="citation_abstract" content="Fallback abstract." />
        </head><body>
        <td class="tablecell subjects"><a href="/list/cs.LG/recent">cs.LG</a></td>
        </body></html>
        """
        response = MagicMock()
        response.text = html
        response.raise_for_status.return_value = None

        with patch("paper_graph.ingest.arxiv.Client") as MockClient, \
             patch("paper_graph.ingest.requests.get", return_value=response):
            MockClient.return_value.results.side_effect = RuntimeError("HTTP 429")
            result = _fetch_arxiv_result("2507.23279")

        assert result.title == "Fallback Title"
        assert result.summary == "Fallback abstract."
        assert result.authors == ["Jane Doe"]
        assert result.categories == ["cs.LG"]


class TestExtractPdfMetadata:
    def test_extracts_title_and_date(self, tmp_path):
        pdf_file = tmp_path / "dummy.pdf"
        pdf_file.write_text("not a real pdf")

        mock_doc = MagicMock()
        mock_doc.metadata = {"title": "", "creationDate": "D:20230101000000"}
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value.get_text.return_value = (
            "PDF Real Title\nAlice Smith\nBob Jones\nAbstract\nSome abstract text."
        )
        mock_doc.close.return_value = None

        with patch("paper_graph.ingest.fitz.open", return_value=mock_doc):
            meta = extract_pdf_metadata(pdf_file)

        assert meta["title"] == "PDF Real Title"
        assert meta["published_date"] == "2023-01-01"
        assert meta["source"] == "local"
        assert meta["pdf_path"] == str(pdf_file.resolve())
        assert meta["abstract"] == "Some abstract text."
        mock_doc.close.assert_called()

    def test_layout_fallback_skips_header_and_extracts_abstract_authors(self, tmp_path):
        pdf_file = tmp_path / "local-paper.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 45), "Published as a workshop paper", fontsize=9)
        page.insert_text((72, 90), "A Reliable Local PDF", fontsize=18)
        page.insert_text((72, 112), "Metadata Extraction Method", fontsize=18)
        page.insert_text((72, 145), "Alice Smith, Bob Jones", fontsize=10)
        page.insert_text((72, 190), "Abstract", fontsize=12)
        page.insert_text((72, 215), "This is the actual abstract content.", fontsize=10)
        page.insert_text((72, 255), "1 Introduction", fontsize=12)
        page.insert_text((72, 280), "Introduction content must not enter the abstract.", fontsize=10)
        doc.save(pdf_file)
        doc.close()

        meta = extract_pdf_metadata(pdf_file)

        assert meta["title"] == "A Reliable Local PDF Metadata Extraction Method"
        assert meta["abstract"] == "This is the actual abstract content."
        assert meta["authors"] == ["Alice Smith", "Bob Jones"]


def test_ingest_pdf_uses_arxiv_metadata_when_id_is_detected(tmp_path, monkeypatch):
    pdf_file = tmp_path / "uploaded.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Published as a conference paper")
    page.insert_text((72, 100), "arXiv:2507.23279v3 [cs.CL]")
    doc.save(pdf_file)
    doc.close()

    mock_result = MagicMock()
    mock_result.entry_id = "https://arxiv.org/abs/2507.23279v3"
    mock_result.title = "Canonical arXiv Title"
    mock_result.summary = "Canonical arXiv abstract."
    mock_result.published = datetime.datetime(2025, 7, 31)
    mock_result.updated = datetime.datetime(2026, 2, 11)
    mock_result.categories = ["cs.CL", "cs.LG"]
    mock_result.authors = ["Author One", "Author Two"]
    mock_result.affiliation = []
    monkeypatch.setattr("paper_graph.ingest._fetch_arxiv_result", lambda _: mock_result)

    db_path = tmp_path / "papers.db"
    paper_id = ingest_local_pdf(pdf_file, db_path=db_path, pdf_dir=tmp_path / "pdfs")

    from paper_graph.database import get_connection, get_paper

    conn = get_connection(db_path)
    paper = get_paper(conn, paper_id)
    conn.close()
    assert paper_id == "arxiv_2507.23279"
    assert paper["title"] == "Canonical arXiv Title"
    assert paper["abstract"] == "Canonical arXiv abstract."
    assert paper["source"] == "arxiv"
    assert paper["pdf_path"].endswith("arxiv_2507.23279.pdf")


def test_enrich_existing_local_paper_uses_layout_metadata(tmp_path):
    pdf_file = tmp_path / "existing-local.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), "Correct Local Paper Title", fontsize=18)
    page.insert_text((72, 130), "Alice Smith, Bob Jones", fontsize=10)
    page.insert_text((72, 180), "Abstract", fontsize=12)
    page.insert_text((72, 205), "Correct local abstract.", fontsize=10)
    page.insert_text((72, 245), "1 Introduction", fontsize=12)
    doc.save(pdf_file)
    doc.close()

    from paper_graph.database import add_paper_to_project, create_project, get_connection, init_db, upsert_paper

    db_path = tmp_path / "papers.db"
    init_db(db_path)
    conn = get_connection(db_path)
    upsert_paper(conn, {
        "id": "local_existing",
        "title": "Wrong Header",
        "abstract": "Wrong abstract",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-01",
        "categories": "",
        "pdf_path": str(pdf_file),
        "source": "local",
        "arxiv_url": None,
    })
    project = create_project(conn, "Metadata Project")
    add_paper_to_project(conn, project["id"], "local_existing")
    conn.commit()
    conn.close()

    paper, _ = enrich_paper_metadata_from_pdf("local_existing", db_path)

    assert paper["title"] == "Correct Local Paper Title"
    assert paper["abstract"] == "Correct local abstract."
    conn = get_connection(db_path)
    authors = [
        row["name"]
        for row in conn.execute(
            """
            SELECT a.name
            FROM paper_authors pa
            JOIN authors a ON a.id = pa.author_id
            WHERE pa.paper_id = ?
            ORDER BY pa.author_order
            """,
            ("local_existing",),
        ).fetchall()
    ]
    project_link = conn.execute(
        "SELECT 1 FROM project_papers WHERE project_id = ? AND paper_id = ?",
        (project["id"], "local_existing"),
    ).fetchone()
    conn.close()
    assert authors == ["Alice Smith", "Bob Jones"]
    assert project_link is not None


class TestExtractAuthorsFromText:
    def test_newline_separated_english_names(self):
        text = "PDF Title\nAlice Smith\nBob Jones\nAbstract\nText"
        assert _extract_authors_from_text(text) == ["Alice Smith", "Bob Jones"]

    def test_newline_separated_chinese_names(self):
        text = "Title\n张三\n李四\nAbstract\n正文"
        assert _extract_authors_from_text(text) == ["张三", "李四"]

    def test_names_with_initials(self):
        text = "Title\nAlice B. Chan\nDavid E. Lee\nIntroduction"
        assert _extract_authors_from_text(text) == ["Alice B. Chan", "David E. Lee"]

    def test_stops_at_abstract_keyword(self):
        text = "Title\nAlice Smith\nAbstract\nBob Jones"
        assert _extract_authors_from_text(text) == ["Alice Smith"]

    def test_no_authors_found(self):
        assert _extract_authors_from_text("Abstract\nJust text") == []


class TestSearchArxiv:
    def test_upserts_papers_into_db(self, tmp_db):
        mock_result = MagicMock()
        mock_result.entry_id = "http://arxiv.org/abs/2401.00002"
        mock_result.title = "Search Result Title"
        mock_result.summary = "Search abstract."
        mock_result.published = datetime.datetime(2024, 1, 15)
        mock_result.updated = datetime.datetime(2024, 1, 16)
        mock_result.categories = ["cs.LG"]
        mock_result.authors = ["Searcher One"]
        mock_result.affiliation = None

        with patch("paper_graph.ingest.arxiv.Client") as MockClient, \
             patch("paper_graph.ingest.arxiv.Search") as MockSearch, \
             patch("paper_graph.ingest.arxiv.SortCriterion") as MockSort:
            MockSort.Relevance = "relevance"
            MockClient.return_value.results.return_value = [mock_result]
            MockSearch.return_value

            paper_ids = search_arxiv("transformers", max_results=1, db_path=tmp_db)

        assert paper_ids == ["arxiv_2401.00002"]

        import paper_graph.database as db_mod
        conn = db_mod.get_connection(tmp_db)
        paper = db_mod.get_paper(conn, "arxiv_2401.00002")
        conn.close()
        assert paper is not None
        assert paper["title"] == "Search Result Title"
        assert paper["source"] == "arxiv"


class TestDownloadArxivPdf:
    def test_writes_pdf_file(self, tmp_path):
        result = MagicMock()
        result.pdf_url = "http://arxiv.org/pdf/2401.00003.pdf"

        mock_response = MagicMock()
        mock_response.content = b"PDF binary data"
        mock_response.raise_for_status.return_value = None

        pdf_path = tmp_path / "paper.pdf"

        with patch("paper_graph.ingest.requests.get", return_value=mock_response):
            _download_arxiv_pdf(result, pdf_path)

        assert pdf_path.exists()
        assert pdf_path.read_bytes() == b"PDF binary data"
        mock_response.raise_for_status.assert_called_once()


class TestIngestLocalPdf:
    def test_persists_pdf_in_managed_directory(self, tmp_path):
        source_file = tmp_path / "upload.pdf"
        source_file.write_bytes(b"%PDF-1.4 managed content")
        pdf_dir = tmp_path / "pdfs"
        db_path = tmp_path / "papers.db"

        mock_doc = MagicMock()
        mock_doc.metadata = {"title": "Managed PDF"}
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value.get_text.return_value = "Managed PDF\nAbstract\nText"
        mock_doc.close.return_value = None

        with patch("paper_graph.ingest.fitz.open", return_value=mock_doc):
            paper_id = ingest_local_pdf(source_file, db_path=db_path, pdf_dir=pdf_dir)

        import paper_graph.database as db_mod
        conn = db_mod.get_connection(db_path)
        paper = db_mod.get_paper(conn, paper_id)
        conn.close()

        stored_path = Path(paper["pdf_path"])
        assert stored_path.parent == pdf_dir.resolve()
        assert stored_path.exists()
        assert stored_path.read_bytes() == source_file.read_bytes()

    def test_ingests_local_pdf(self, tmp_path, monkeypatch):
        pdf_file = tmp_path / "local.pdf"
        pdf_file.write_text("not real pdf")

        mock_doc = MagicMock()
        mock_doc.metadata = {"title": ""}
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value.get_text.return_value = (
            "Local PDF Title\nAlice Smith\nBob Jones\nAbstract\nAbstract text here."
        )
        mock_doc.close.return_value = None

        with patch("paper_graph.ingest.fitz.open", return_value=mock_doc):
            paper_id = ingest_local_pdf(pdf_file, db_path=tmp_path / "papers.db")

        assert paper_id.startswith("local_")

        import paper_graph.database as db_mod
        conn = db_mod.get_connection(tmp_path / "papers.db")
        paper = db_mod.get_paper(conn, paper_id)
        conn.close()
        assert paper is not None
        assert paper["title"] == "Local PDF Title"
        assert paper["abstract"] == "Abstract text here."
        assert paper["source"] == "local"

    def test_ingest_local_pdf_rejects_image_only_pdf(self, tmp_path, monkeypatch):
        pdf_file = tmp_path / "empty.pdf"
        pdf_file.write_text("not real pdf")

        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_doc.__len__.return_value = 0
        mock_doc.close.return_value = None

        with patch("paper_graph.ingest.fitz.open", return_value=mock_doc):
            with pytest.raises(ValueError, match="PDF 未包含可提取文本，暂不支持扫描版 PDF"):
                ingest_local_pdf(pdf_file, db_path=tmp_path / "papers.db")
