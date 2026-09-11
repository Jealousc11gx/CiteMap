"""论文雷达 Worker 连接配置的本地持久化。"""

from __future__ import annotations

import sqlite3
from typing import Optional
from urllib.parse import urlsplit, urlunsplit


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS radar_connection (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            remote_url TEXT NOT NULL,
            token TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _normalize_remote_url(remote_url: str) -> str:
    parsed = urlsplit(remote_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Worker URL 必须是有效的 http(s) 地址")
    path = parsed.path.rstrip("/")
    if path in {"/sync", "/profiles", "/items"}:
        path = ""
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def get_radar_connection(conn: sqlite3.Connection) -> dict:
    """返回可展示的连接状态，不暴露 token 明文。"""
    _ensure_table(conn)
    row = conn.execute(
        "SELECT remote_url, token, updated_at FROM radar_connection WHERE id = 1"
    ).fetchone()
    if not row:
        return {"remote_url": "", "token_configured": False, "updated_at": None}
    return {
        "remote_url": row["remote_url"],
        "token_configured": bool(row["token"]),
        "updated_at": row["updated_at"],
    }


def save_radar_connection(
    conn: sqlite3.Connection,
    remote_url: str,
    token: Optional[str] = None,
    *,
    clear_token: bool = False,
) -> dict:
    """保存全局 Worker 连接；token 留空时保留原值，可显式清除 token。"""
    _ensure_table(conn)
    normalized_url = _normalize_remote_url(remote_url)
    existing = conn.execute(
        "SELECT token FROM radar_connection WHERE id = 1"
    ).fetchone()
    next_token = "" if clear_token else (token.strip() if token and token.strip() else (existing["token"] if existing else ""))
    if not next_token and not clear_token:
        raise ValueError("首次连接 Worker 时必须填写 RADAR_TOKEN")
    conn.execute(
        """
        INSERT INTO radar_connection (id, remote_url, token, updated_at)
        VALUES (1, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            remote_url=excluded.remote_url,
            token=excluded.token,
            updated_at=CURRENT_TIMESTAMP
        """,
        (normalized_url, next_token),
    )
    conn.commit()
    return get_radar_connection(conn)


def load_radar_credentials(conn: sqlite3.Connection) -> tuple[str, str]:
    """读取后端同步使用的完整凭据。"""
    _ensure_table(conn)
    row = conn.execute(
        "SELECT remote_url, token FROM radar_connection WHERE id = 1"
    ).fetchone()
    if not row or not row["remote_url"] or not row["token"]:
        raise ValueError("尚未保存 Worker URL 和 RADAR_TOKEN")
    return row["remote_url"], row["token"]
