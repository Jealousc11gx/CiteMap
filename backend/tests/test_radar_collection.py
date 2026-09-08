"""论文雷达候选抓取与规则过滤测试。"""

from datetime import datetime
from types import SimpleNamespace

from paper_graph.database import create_project, get_connection
from paper_graph import radar
from paper_graph.radar import (
    candidate_matches_config,
    fetch_arxiv_candidates,
    get_radar_config,
    list_radar_matches,
    run_enabled_radar_collections,
    run_radar_collection,
    upsert_radar_config,
)


ATOM_FEED = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom' xmlns:arxiv='http://arxiv.org/schemas/atom' xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <title>cs.AI updates on arXiv.org</title>
  <entry><id>oai:arXiv.org:2609.00001v1</id><title> New paper </title><summary>arXiv:2609.00001v1 Announce Type: new
Abstract: A useful abstract.</summary><link href='https://arxiv.org/abs/2609.00001' rel='alternate'/><category term='cs.AI'/><published>2026-09-07T00:00:00-04:00</published><updated>2026-09-07T04:00:00Z</updated><arxiv:announce_type>new</arxiv:announce_type><dc:creator>Alice, Bob</dc:creator></entry>
  <entry><id>oai:arXiv.org:2609.00002v2</id><title>Cross paper</title><summary>Abstract: Cross abstract.</summary><link href='https://arxiv.org/abs/2609.00002' rel='alternate'/><category term='cs.LG'/><category term='cs.AI'/><published>2026-09-07T00:00:00-04:00</published><arxiv:announce_type>cross</arxiv:announce_type><dc:creator>Carol</dc:creator></entry>
</feed>"""


def test_fetch_arxiv_candidates_uses_atom_metadata(monkeypatch):
    response = SimpleNamespace(content=ATOM_FEED, raise_for_status=lambda: None)
    requested = {}

    def fake_get(url, **kwargs):
        requested.update(url=url, **kwargs)
        return response

    monkeypatch.setattr(radar.requests, "get", fake_get)
    candidates = fetch_arxiv_candidates(["cs.AI", "cs.LG"], max_results=5)
    assert requested["url"] == "https://rss.arxiv.org/atom/cs.AI+cs.LG"
    assert candidates[0] == {
        "arxiv_id": "2609.00001",
        "title": "New paper",
        "abstract": "A useful abstract.",
        "authors": ["Alice", "Bob"],
        "categories": ["cs.AI"],
        "primary_category": "cs.AI",
        "published_date": "2026-09-07",
        "updated_date": "2026-09-07",
        "arxiv_url": "https://arxiv.org/abs/2609.00001",
        "pdf_url": "https://arxiv.org/pdf/2609.00001",
    }
    assert [item["arxiv_id"] for item in candidates] == ["2609.00001", "2609.00002"]


def test_fetch_arxiv_candidates_can_exclude_cross_list(monkeypatch):
    response = SimpleNamespace(content=ATOM_FEED, raise_for_status=lambda: None)
    monkeypatch.setattr(radar.requests, "get", lambda *args, **kwargs: response)
    candidates = fetch_arxiv_candidates(["cs.AI"], include_cross_list=False)
    assert [item["arxiv_id"] for item in candidates] == ["2609.00001"]


def test_fetch_arxiv_candidates_falls_back_to_export_api_when_atom_is_empty(monkeypatch):
    empty = SimpleNamespace(content=b"<feed xmlns='http://www.w3.org/2005/Atom'><title>empty</title></feed>", raise_for_status=lambda: None)
    api = SimpleNamespace(content=ATOM_FEED, raise_for_status=lambda: None)
    requested = []

    def fake_get(url, **kwargs):
        requested.append(url)
        return empty if url.startswith("https://rss.arxiv.org") else api

    monkeypatch.setattr(radar.requests, "get", fake_get)
    candidates = fetch_arxiv_candidates(["cs.AI"], max_results=5)
    assert requested == ["https://rss.arxiv.org/atom/cs.AI", "https://export.arxiv.org/api/query"]
    assert candidates[0]["arxiv_id"] == "2609.00001"


def candidate(arxiv_id: str, title: str, categories=None, abstract=""):
    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "authors": ["Author"],
        "categories": categories or ["cs.AI"],
        "published_date": "2026-09-06",
        "updated_date": "2026-09-06",
        "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
    }


def test_candidate_filter_categories_keywords_and_excludes():
    config = {
        "categories": ["cs.AI"],
        "include_keywords": ["retrieval"],
        "exclude_keywords": ["medical"],
    }
    assert candidate_matches_config(candidate("1", "Retrieval model", abstract="dense"), config)
    assert not candidate_matches_config(candidate("2", "Retrieval model", ["cs.CV"]), config)
    assert not candidate_matches_config(candidate("3", "Medical retrieval", abstract="x"), config)
    assert not candidate_matches_config(candidate("4", "Language model"), config)


def test_run_collection_filters_deduplicates_and_records_run(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Collection")
    upsert_radar_config(
        conn,
        project["id"],
        enabled=True,
        categories=["cs.AI"],
        include_keywords=["retrieval"],
    )
    data = [
        candidate("2609.00001", "Retrieval A"),
        candidate("2609.00001", "Retrieval A duplicate"),
        candidate("2609.00002", "Unrelated", abstract="classification"),
    ]
    result = run_radar_collection(
        conn,
        project["id"],
        "2026-09-06",
        fetcher=lambda categories, max_results: data,
    )
    assert result["status"] == "success"
    assert result["candidate_count"] == 3
    assert result["matched_count"] == 1
    assert len(list_radar_matches(conn, project["id"])) == 1
    run = conn.execute("SELECT * FROM radar_runs WHERE id=?", (result["run_id"],)).fetchone()
    assert run["matched_count"] == 1
    conn.close()


def test_disabled_project_skips_without_fetching(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Disabled")
    called = []
    result = run_radar_collection(
        conn,
        project["id"],
        "2026-09-06",
        fetcher=lambda *args, **kwargs: called.append(True),
    )
    assert result["status"] == "skipped"
    assert called == []
    conn.close()


def test_failed_collection_records_error(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Failed")
    upsert_radar_config(conn, project["id"], enabled=True, categories=["cs.AI"])
    try:
        run_radar_collection(
            conn,
            project["id"],
            "2026-09-06",
            fetcher=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("feed down")),
        )
    except RuntimeError as exc:
        assert str(exc) == "feed down"
    row = conn.execute(
        "SELECT status, error FROM radar_runs WHERE project_id=? AND run_date=?",
        (project["id"], "2026-09-06"),
    ).fetchone()
    assert row["status"] == "failed"
    assert row["error"] == "feed down"
    conn.close()


def test_run_enabled_projects_isolates_projects(tmp_db):
    conn = get_connection(tmp_db)
    first = create_project(conn, "Enabled")
    second = create_project(conn, "Disabled")
    upsert_radar_config(conn, first["id"], enabled=True, categories=["cs.AI"])
    upsert_radar_config(conn, second["id"], enabled=False, categories=["cs.AI"])
    conn.close()

    results = run_enabled_radar_collections(
        tmp_db,
        "2026-09-06",
        fetcher=lambda categories, max_results: [candidate("2609.00009", "Retrieval")],
    )
    assert len(results) == 1
    assert results[0]["status"] == "success"
