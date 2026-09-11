from datetime import UTC, datetime

from paper_graph.settings import explore_target_date, get_app_settings, update_app_settings


def test_settings_never_return_secret_plaintext(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "initial")
    updated = update_app_settings(
        env_path,
        {"LLM_MODEL": "test-model"},
        {"LLM_API_KEY": "super-secret"},
    )

    assert updated["values"]["LLM_MODEL"] == "test-model"
    assert updated["secrets"]["LLM_API_KEY"] is True
    assert "super-secret" not in str(updated)
    assert "super-secret" not in str(get_app_settings(env_path))
    assert "ANTHROPIC_API_KEY" not in updated["secrets"]


def test_secret_can_be_cleared(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setenv("OPENREVIEW_PASSWORD", "")
    update_app_settings(env_path, {}, {"OPENREVIEW_PASSWORD": "password"})
    cleared = update_app_settings(env_path, {}, clear_secrets=["OPENREVIEW_PASSWORD"])

    assert cleared["secrets"]["OPENREVIEW_PASSWORD"] is False


def test_explore_target_defaults_to_previous_complete_utc_day(monkeypatch):
    monkeypatch.delenv("EXPLORE_TARGET_DATE", raising=False)
    monkeypatch.delenv("EXPLORE_DAY_OFFSET", raising=False)
    now = datetime(2026, 9, 11, 2, 30, tzinfo=UTC)

    assert explore_target_date(now).isoformat() == "2026-09-10"
