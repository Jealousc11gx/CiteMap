"""论文雷达 Worker 连接持久化测试。"""

from paper_graph.database import get_connection
from paper_graph.radar_connection import (
    get_radar_connection,
    load_radar_credentials,
    save_radar_connection,
)


def test_connection_persists_without_exposing_token(tmp_db):
    conn = get_connection(tmp_db)
    saved = save_radar_connection(
        conn,
        "https://radar.example.workers.dev/sync/",
        "secret-token",
    )
    assert saved["remote_url"] == "https://radar.example.workers.dev"
    assert saved["token_configured"] is True
    assert "token" not in saved
    conn.close()

    reopened = get_connection(tmp_db)
    assert get_radar_connection(reopened)["token_configured"] is True
    assert load_radar_credentials(reopened) == (
        "https://radar.example.workers.dev",
        "secret-token",
    )
    reopened.close()


def test_blank_token_keeps_existing_secret(tmp_db):
    conn = get_connection(tmp_db)
    save_radar_connection(conn, "https://old.example.workers.dev", "keep-me")
    save_radar_connection(conn, "https://new.example.workers.dev", None)
    assert load_radar_credentials(conn) == (
        "https://new.example.workers.dev",
        "keep-me",
    )
    conn.close()


def test_first_connection_requires_token(tmp_db):
    conn = get_connection(tmp_db)
    try:
        save_radar_connection(conn, "https://radar.example.workers.dev")
    except ValueError as exc:
        assert str(exc) == "首次连接 Worker 时必须填写 RADAR_TOKEN"
    else:
        raise AssertionError("首次连接不应接受空 token")
    conn.close()
