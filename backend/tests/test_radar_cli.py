"""GitHub Actions Radar 入口测试。"""

import pytest

import radar_cli


class FakeRemoteClient:
    projects = []
    created_items = []

    def __init__(self, base_url, token):
        self.base_url = base_url
        self.token = token

    def _request(self, method, path, payload=None):
        if path == "/profiles":
            return {"projects": self.projects}
        return {"ok": True}

    def create_items(self, items):
        self.created_items = items
        return {"new_items": []}


def _project():
    return {
        "project_id": "project-test",
        "enabled": True,
        "categories": ["cs.AI"],
        "include_keywords": [],
        "exclude_keywords": [],
        "reference_papers": [{"id": "reference", "title": "Reference", "abstract": "SNN compression"}],
        "top_k": 3,
        "min_score": 0,
    }


def test_radar_test_uses_historical_candidate_and_repeats_email(monkeypatch):
    FakeRemoteClient.projects = [_project()]
    sent = []
    monkeypatch.setenv("RADAR_REMOTE_URL", "https://radar.example")
    monkeypatch.setenv("RADAR_REMOTE_TOKEN", "token")
    monkeypatch.setenv("RADAR_TEST_MODE", "true")
    monkeypatch.setenv("RADAR_TEST_USE_HISTORICAL", "true")
    monkeypatch.setattr(radar_cli, "RadarRemoteClient", FakeRemoteClient)
    monkeypatch.setattr(radar_cli, "fetch_arxiv_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(radar_cli, "get_embedding_provider", lambda: object())
    monkeypatch.setattr(
        radar_cli,
        "rank_candidates",
        lambda candidates, *args, **kwargs: [{**candidates[0], "score": 0.5, "reason": "test"}],
    )
    monkeypatch.setattr(radar_cli, "enrich_with_tldr", lambda items: items)
    monkeypatch.setattr(radar_cli, "send_radar_email", lambda items, subject, **kwargs: sent.append((items, subject)))

    result = radar_cli.run_remote_radar()

    assert result == {"projects": 1, "sent": 1, "test_mode": True}
    assert sent[0][0][0]["arxiv_id"] == "2508.13434"
    assert sent[0][1].startswith("CiteMap 论文雷达测试")


def test_radar_test_fails_when_cloud_has_no_profiles(monkeypatch):
    FakeRemoteClient.projects = []
    monkeypatch.setenv("RADAR_REMOTE_URL", "https://radar.example")
    monkeypatch.setenv("RADAR_REMOTE_TOKEN", "token")
    monkeypatch.setenv("RADAR_TEST_MODE", "true")
    monkeypatch.setattr(radar_cli, "RadarRemoteClient", FakeRemoteClient)

    with pytest.raises(RuntimeError, match="云端没有项目 profile"):
        radar_cli.run_remote_radar()


def test_merge_email_items_keeps_click_url_and_generated_ai_fields():
    payload = [{"arxiv_id": "1", "ai_summary": "中文摘要", "affiliations": ["测试大学"]}]
    stored = [{"arxiv_id": "1", "ai_summary": "", "affiliations": [], "click_url": "https://radar/r/1"}]

    assert radar_cli._merge_email_items(payload, stored) == [{
        "arxiv_id": "1",
        "ai_summary": "中文摘要",
        "affiliations": ["测试大学"],
        "click_url": "https://radar/r/1",
    }]


def test_radar_logs_default_notice_when_project_has_no_candidates(monkeypatch, capsys):
    FakeRemoteClient.projects = [_project()]
    monkeypatch.setenv("RADAR_REMOTE_URL", "https://radar.example")
    monkeypatch.setenv("RADAR_REMOTE_TOKEN", "token")
    monkeypatch.setattr(radar_cli, "RadarRemoteClient", FakeRemoteClient)
    monkeypatch.setattr(radar_cli, "fetch_arxiv_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(radar_cli, "get_embedding_provider", lambda: object())
    monkeypatch.setattr(radar_cli, "rank_candidates", lambda *args, **kwargs: [])

    radar_cli.run_remote_radar()

    output = capsys.readouterr().out
    assert "暂无符合条件的论文" in output
    assert "categories=cs.AI" in output
    assert "include_keywords=无关键词限制" in output
