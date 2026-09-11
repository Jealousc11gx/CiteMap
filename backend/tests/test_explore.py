"""独立 Explore 的扫描、Judge、Digest、趋势与 triage 测试。"""

import json
from datetime import date, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from paper_graph.database import get_connection
from paper_graph.explore import (
    analyze_explore_candidate,
    get_explore_digest,
    get_explore_rollup,
    get_explore_trends,
    list_explore_candidates,
    scan_explore,
    transition_explore_triage,
)


def _candidate(arxiv_id: str, title: str):
    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": "A paper about post-training quantization for LLM inference.",
        "authors": ["A. Researcher"],
        "categories": ["cs.LG"],
        "published_date": date.today().isoformat(),
        "updated_date": date.today().isoformat(),
        "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
    }


class FakeLLM:
    def __init__(self, results: list[dict]):
        self.results = iter(results)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **_kwargs):
        content = json.dumps(next(self.results), ensure_ascii=False)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


def _judge_result() -> dict:
    return {
        "hard_gate": False,
        "topic_relevance": 5,
        "practicality": 4,
        "compression_type": "weight-only",
        "topic_bucket": "ptq",
        "model_domain": "language",
        "format_or_method": "W4A16",
        "largest_model_tested": "70B",
        "accuracy_benchmarks": "WikiText-2",
        "accuracy_summary": "small degradation",
        "inference_perf": "1.5x throughput",
        "calibration_cost": "128 samples",
        "peak_memory": "reduced",
        "reason": "直接研究 LLM PTQ，具有可部署性。",
    }


def _summary_result() -> dict:
    return {
        "summary": "论文提出一种可部署的 LLM PTQ 方法。",
        "highlights": ["🎯 面向 LLM PTQ", "⚡ 提升推理吞吐"],
        "related_methods": [{"name": "GPTQ", "relation": "对比基线", "arxiv_id": None}],
        "summary_en": "The paper presents a deployable PTQ method for LLM inference.",
        "highlights_en": ["🎯 LLM PTQ", "⚡ Higher throughput"],
        "related_methods_en": [{"name": "GPTQ", "relation": "baseline", "arxiv_id": None}],
        "relevance_reason_en": "Directly studies deployable LLM PTQ.",
        "calibration_cost_en": "128 samples",
        "inference_perf_en": "1.5x throughput",
    }


def test_scan_analyze_digest_and_triage_are_project_independent(tmp_db):
    conn = get_connection(tmp_db)
    result = scan_explore(
        conn,
        source_fetchers={
            "arxiv": lambda: [
                _candidate("2609.10001", "Quantization for inference"),
                _candidate("2609.10002", "A broad robotics paper")
                | {"abstract": "A paper about robotics."},
            ],
            "hf_daily": lambda: [_candidate("2609.10001v2", "HF preferred title")],
        },
    )
    assert result["stored_count"] == 2
    candidates = list_explore_candidates(conn)
    quantized = next(item for item in candidates if item["arxiv_id"] == "2609.10001")
    assert quantized["title"] == "HF preferred title"
    assert {source["source"] for source in quantized["sources"]} == {"arxiv", "hf_daily"}

    analyzed = analyze_explore_candidate(
        conn,
        "explore_default",
        quantized["id"],
        client=FakeLLM([_judge_result(), _summary_result()]),
        sleep=lambda _seconds: None,
    )
    assert analyzed["relevance_score"] == 9
    assert analyzed["topic_bucket"] == "ptq"
    assert analyzed["summary_status"] == "completed"
    assert analyzed["highlights_zh"] == ["🎯 面向 LLM PTQ", "⚡ 提升推理吞吐"]

    digest = get_explore_digest(conn, digest_date=date.today().isoformat())
    assert digest["spotlight"][0]["id"] == quantized["id"]
    assert digest["topic_counts"] == {"ptq": 1}
    assert digest["scanned_count"] == 2
    assert digest["pending_count"] == 1
    assert digest["judged_count"] == 1
    assert digest["rejected_count"] == 0
    assert digest["highlighted_count"] == 1
    assert digest["watched_count"] == 0
    assert get_explore_trends(conn, days=7)["topics"]["ptq"] == 1
    rollup = get_explore_rollup(
        conn,
        start_date=date.today().isoformat(),
        end_date=date.today().isoformat(),
    )
    assert rollup["paper_count"] == 1
    assert rollup["buckets"][0]["id"] == "ptq"
    updated = transition_explore_triage(conn, "explore_default", quantized["id"], "later")
    assert updated["triage_status"] == "later"
    conn.close()


def test_watched_authors_are_a_separate_subscription_lane(tmp_db):
    conn = get_connection(tmp_db)
    watched = _candidate("2609.10009", "Watched author update")
    scan_explore(
        conn,
        source_fetchers={"arxiv_authors": lambda: [watched]},
        target_date=date.today(),
    )

    digest = get_explore_digest(conn, digest_date=date.today().isoformat())

    assert digest["pending_count"] == 1
    assert digest["highlighted_count"] == 0
    assert digest["watched_count"] == 1
    assert digest["watched"][0]["arxiv_id"] == "2609.10009"
    assert digest["spotlight"][0]["watched_author"] is True
    conn.close()


def test_digest_does_not_treat_legacy_discovery_timestamp_as_publication(tmp_db):
    conn = get_connection(tmp_db)
    old_paper = _candidate("2301.00001", "Old trending paper") | {
        "published_date": (date.today() - timedelta(days=365)).isoformat(),
    }
    scan_explore(
        conn,
        source_fetchers={"hf_daily": lambda: [old_paper]},
        target_date=date.today(),
    )
    conn.execute("DELETE FROM explore_discoveries")
    conn.commit()

    digest = get_explore_digest(conn, digest_date=date.today().isoformat())

    assert digest["scanned_count"] == 0
    assert digest["spotlight"] == []
    conn.close()


def test_digest_filters_old_hf_discovery_records(tmp_db, monkeypatch):
    monkeypatch.setenv("EXPLORE_HF_TRENDING_MAX_AGE_DAYS", "30")
    monkeypatch.setenv("EXPLORE_INCLUDE_HISTORICAL_MILESTONES", "false")
    conn = get_connection(tmp_db)
    old_paper = _candidate("2301.00002", "Old HF trending paper") | {
        "published_date": (date.today() - timedelta(days=365)).isoformat(),
    }
    scan_explore(
        conn,
        source_fetchers={"hf_daily": lambda: [old_paper]},
        target_date=date.today(),
    )

    digest = get_explore_digest(conn, digest_date=date.today().isoformat())

    assert digest["scanned_count"] == 0
    assert digest["spotlight"] == []
    conn.close()


@pytest.fixture
def explore_client(tmp_path, monkeypatch):
    import main
    import paper_graph.database as database
    import paper_graph.explore as explore

    db_path = tmp_path / "explore-api.db"
    monkeypatch.setattr(main, "DB_PATH", db_path)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.init_db(db_path)
    real_scan = explore.scan_explore

    def fake_scan(conn, profile_id, max_results):
        return real_scan(
            conn,
            profile_id,
            max_results=max_results,
            source_fetchers={
                "arxiv": lambda: [_candidate("2609.10003", "Serving quantization")],
                "hf_daily": lambda: [],
            },
        )

    monkeypatch.setattr(main, "scan_explore", fake_scan)
    return TestClient(main.app)


def test_explore_api_scan_and_candidate_triage(explore_client):
    assert explore_client.post("/api/explore/scan", json={"max_results": 10}).status_code == 200
    listing = explore_client.get("/api/explore/candidates", params={"triage_status": "unreviewed"})
    candidate_id = listing.json()[0]["id"]
    moved = explore_client.patch(
        f"/api/explore/candidates/{candidate_id}",
        json={"status": "later"},
    )
    assert moved.status_code == 200
    assert moved.json()["triage_status"] == "later"
    blocked = explore_client.patch(
        f"/api/explore/candidates/{candidate_id}",
        json={"status": "project"},
    )
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == "加入项目时必须提供 project_id"
