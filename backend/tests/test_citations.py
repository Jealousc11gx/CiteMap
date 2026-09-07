from pathlib import Path

import pytest

from paper_graph.citations import (
    CitationSyncError,
    build_citation_graph,
    build_similarity_graph,
    sync_citation_metrics,
    sync_citations,
)
from paper_graph.database import get_connection, upsert_paper


def _insert_seed(db_path: Path, paper_id: str = "arxiv_2401.00001") -> None:
    conn = get_connection(db_path)
    upsert_paper(conn, {
        "id": paper_id,
        "title": "Seed Paper",
        "abstract": "",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-01",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
    })
    conn.commit()
    conn.close()


def test_sync_and_build_citation_and_similarity_graphs(tmp_db, monkeypatch):
    _insert_seed(tmp_db)
    responses = iter([
        {
            "paperId": "S", "title": "Seed Paper", "year": 2024, "venue": "ICLR",
            "citationCount": 12, "referenceCount": 2, "externalIds": {"ArXiv": "2401.00001"},
        },
        {"data": [
            {"citedPaper": {"paperId": "R1", "title": "Reference One", "year": 2020, "citationCount": 30, "referenceCount": 2}},
            {"citedPaper": {"paperId": "R2", "title": "Reference Two", "year": 2021, "citationCount": 20, "referenceCount": 2}},
        ]},
        {"data": [
            {"citingPaper": {"paperId": "C", "title": "Citing Paper", "year": 2025, "citationCount": 3, "referenceCount": 2}},
        ]},
        [
            {"paperId": "S", "title": "Seed Paper", "year": 2024, "citationCount": 12, "referenceCount": 2, "externalIds": {"ArXiv": "2401.00001"}, "references": [{"paperId": "R1"}, {"paperId": "R2"}]},
            {"paperId": "R1", "title": "Reference One", "year": 2020, "citationCount": 30, "referenceCount": 2, "references": [{"paperId": "X"}, {"paperId": "Y"}]},
            {"paperId": "R2", "title": "Reference Two", "year": 2021, "citationCount": 20, "referenceCount": 2, "references": [{"paperId": "X"}, {"paperId": "Z"}]},
            {"paperId": "C", "title": "Citing Paper", "year": 2025, "citationCount": 3, "referenceCount": 2, "references": [{"paperId": "R1"}, {"paperId": "R2"}]},
        ],
    ])
    monkeypatch.setattr("paper_graph.citations._request_json", lambda *args, **kwargs: next(responses))

    result = sync_citations("arxiv_2401.00001", tmp_db)

    assert result["citation_count"] == 12
    assert result["loaded_references"] == 2
    assert result["loaded_citations"] == 1
    conn = get_connection(tmp_db)
    stored = conn.execute("SELECT citation_count, reference_count, semantic_scholar_id FROM papers WHERE id = ?", ("arxiv_2401.00001",)).fetchone()
    assert dict(stored) == {"citation_count": 12, "reference_count": 2, "semantic_scholar_id": "S"}
    assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1
    conn.close()

    citation_graph = build_citation_graph("arxiv_2401.00001", tmp_db)
    assert citation_graph.has_edge("arxiv_2401.00001", "s2:R1")
    assert citation_graph.has_edge("s2:C", "arxiv_2401.00001")
    assert citation_graph["s2:C"]["arxiv_2401.00001"]["directed"] is True

    similarity_graph = build_similarity_graph("arxiv_2401.00001", tmp_db)
    assert similarity_graph.has_edge("arxiv_2401.00001", "s2:C")
    edge = similarity_graph["arxiv_2401.00001"]["s2:C"]
    assert edge["similarity"] == 0.8165
    assert edge["shared_references"] == 2
    assert similarity_graph.nodes["s2:C"]["similarity_score"] == 0.8165


def test_sync_rejects_paper_without_arxiv_identifier(tmp_db):
    _insert_seed(tmp_db, "local_without_arxiv")
    conn = get_connection(tmp_db)
    conn.execute("UPDATE papers SET arxiv_url = NULL WHERE id = ?", ("local_without_arxiv",))
    conn.commit()
    conn.close()

    with pytest.raises(CitationSyncError, match="没有可用于匹配的 arXiv ID") as exc_info:
        sync_citations("local_without_arxiv", tmp_db)
    assert exc_info.value.status_code == 422


def test_sync_citation_metrics_updates_counts_without_full_graph(tmp_db, monkeypatch):
    _insert_seed(tmp_db)
    monkeypatch.setattr("paper_graph.citations._request_json", lambda *args, **kwargs: [{
        "paperId": "S", "title": "Seed Paper", "year": 2024, "venue": "ICLR",
        "citationCount": 81, "referenceCount": 36, "externalIds": {"ArXiv": "2401.00001"},
    }])

    result = sync_citation_metrics(tmp_db)

    assert result == {"total": 1, "eligible": 1, "updated": 1, "unmatched": 0, "skipped": 0}
    conn = get_connection(tmp_db)
    row = conn.execute(
        "SELECT citation_count, reference_count, citation_synced_at, venue, venue_year FROM papers WHERE id = ?",
        ("arxiv_2401.00001",),
    ).fetchone()
    assert dict(row) == {
        "citation_count": 81, "reference_count": 36, "citation_synced_at": None,
        "venue": "ICLR", "venue_year": 2024,
    }
    conn.close()


def test_unsynced_graphs_are_empty(tmp_db):
    _insert_seed(tmp_db)
    assert build_citation_graph("arxiv_2401.00001", tmp_db).number_of_nodes() == 0
    assert build_similarity_graph("arxiv_2401.00001", tmp_db).number_of_nodes() == 0
