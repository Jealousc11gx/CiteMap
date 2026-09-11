import json

from paper_graph.database import get_connection
from paper_graph.venue_trend import _group_in_scope, _is_accepted, run_venue_trend


def _note(note_id: str, title: str, venueid: str) -> dict:
    return {
        "id": note_id,
        "cdate": 1_700_000_000_000,
        "content": {
            "venueid": {"value": venueid},
            "title": {"value": title},
            "abstract": {"value": "An inference optimization method."},
            "authors": {"value": ["A"]},
        },
    }


def test_venue_acceptance_requires_exact_venue_id():
    venue = "MLSys.org/2026/Conference"
    assert _is_accepted(_note("a", "accepted", venue), venue)
    assert not _is_accepted(_note("r", "rejected", f"{venue}/Rejected_Submission"), venue)
    assert not _is_accepted(_note("s", "submission", f"{venue}/-/Submission"), venue)


def test_group_excludes_hard_gated_papers():
    groups = _group_in_scope([
        {"id": "1", "hard_gate": False, "subfield": "kv_cache"},
        {"id": "2", "hard_gate": False, "subfield": "quantization"},
        {"id": "3", "hard_gate": True, "subfield": "quantization"},
    ])
    assert groups == {"kv_cache": [{"id": "1", "hard_gate": False, "subfield": "kv_cache"}], "quantization": [{"id": "2", "hard_gate": False, "subfield": "quantization"}]}


def test_run_venue_trend_persists_full_result(tmp_db, monkeypatch):
    venue = "TEST.cc/2026/Conference"
    accepted = [{
        "id": "or-a1",
        "title": "Paged cache",
        "abstract": "A KV cache method.",
        "authors": ["A"],
        "venue": venue,
        "url": "https://openreview.net/forum?id=a1",
        "pdf_url": "https://openreview.net/pdf?id=a1",
        "published_date": "2026-01-01",
    }]

    class FakeClient:
        pass

    monkeypatch.setattr(
        "paper_graph.venue_trend._classify_paper",
        lambda paper, client, model: {"hard_gate": False, "subfield": "kv_cache", "reason": "命中"},
    )
    monkeypatch.setattr(
        "paper_graph.venue_trend._generate_report",
        lambda groups, client, model: {"takeaway": "KV cache", "research_concerns": []},
    )
    conn = get_connection(tmp_db)
    result = run_venue_trend(
        conn,
        venue,
        fetcher=lambda venue, max_pages: accepted,
        min_accepted=1,
        llm_client=FakeClient(),
        model="test-model",
    )
    assert result["accepted_count"] == 1
    assert result["in_scope_count"] == 1
    stored = conn.execute("SELECT result FROM explore_venue_trend_runs WHERE id = ?", (result["id"],)).fetchone()
    assert json.loads(stored["result"])["groups"]["kv_cache"][0]["title"] == "Paged cache"
    conn.close()
