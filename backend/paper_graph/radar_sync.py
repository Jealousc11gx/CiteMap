"""论文雷达远端同步协议与本地合并。"""

from __future__ import annotations

import json
from typing import Any, Optional

import requests

from .radar import (
    enqueue_radar_operation,
    get_radar_sync_cursor,
    list_pending_radar_operations,
    mark_radar_operation_result,
    set_radar_sync_cursor,
    transition_radar_state,
    upsert_radar_candidate,
    upsert_radar_match,
)


class RadarRemoteError(RuntimeError):
    """远端雷达服务错误。"""


class RadarRemoteClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: Optional[dict] = None, params: Optional[dict] = None) -> dict:
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json=payload,
            params=params,
            timeout=self.timeout,
        )
        if not response.ok:
            raise RadarRemoteError(f"远端雷达服务返回 HTTP {response.status_code}: {response.text[:500]}")
        try:
            return response.json()
        except ValueError as exc:
            raise RadarRemoteError("远端雷达服务返回了无效 JSON") from exc

    def publish_profile(self, project_id: str, profile: dict) -> dict:
        payload = dict(profile)
        payload.setdefault("project_id", project_id)
        return self._request("POST", "/profiles", payload)

    def create_items(self, items: list[dict]) -> dict:
        return self._request("POST", "/items", {"items": items})

    def pull_changes(self, cursor: Optional[str], limit: int = 200) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["after"] = cursor
        return self._request("GET", "/sync", params=params)

    def update_state(self, project_id: str, arxiv_id: str, state: str) -> dict:
        return self._request(
            "POST",
            "/items/state",
            {"project_id": project_id, "arxiv_id": arxiv_id, "state": state},
        )


def apply_remote_event(conn, event: dict) -> Optional[dict]:
    """将一条远端事件幂等合并到本地。"""
    event_type = event.get("type") or event.get("event_type")
    project_id = event.get("project_id")
    arxiv_id = event.get("arxiv_id")
    if not project_id or not arxiv_id:
        return None
    if event_type in {"recommended", "created", "item"}:
        candidate = upsert_radar_candidate(conn, event)
        return upsert_radar_match(
            conn,
            project_id,
            candidate["id"],
            score=float(event.get("score") or 0.0),
            reason=str(event.get("reason") or "远端雷达推荐"),
        )
    if event_type in {"read", "saved", "dismissed", "state"}:
        row = conn.execute(
            """
            SELECT rm.id
            FROM radar_matches rm
            JOIN radar_candidates rc ON rc.id = rm.candidate_id
            WHERE rm.project_id=? AND rc.arxiv_id=?
            """,
            (project_id, arxiv_id),
        ).fetchone()
        if row:
            return transition_radar_state(conn, row["id"], str(event.get("state") or event_type))
        candidate = upsert_radar_candidate(conn, event)
        match = upsert_radar_match(conn, project_id, candidate["id"], score=float(event.get("score") or 0.0))
        return transition_radar_state(conn, match["id"], str(event.get("state") or event_type))
    return None


def sync_remote_changes(conn, client: RadarRemoteClient, *, limit: int = 200) -> dict:
    """拉取远端历史，合并成功后推进 cursor；支持分页。"""
    cursor = get_radar_sync_cursor(conn)
    applied = 0
    pages = 0
    while True:
        payload = client.pull_changes(cursor, limit=limit)
        pages += 1
        events = payload.get("events") or []
        for event in events:
            apply_remote_event(conn, event)
            applied += 1
        next_cursor = payload.get("next_cursor") or cursor
        if next_cursor is not None:
            set_radar_sync_cursor(conn, str(next_cursor))
        if not payload.get("has_more"):
            break
        if str(next_cursor) == str(cursor):
            raise RadarRemoteError("远端分页未推进 cursor")
        cursor = str(next_cursor)
    return {"applied": applied, "pages": pages, "cursor": get_radar_sync_cursor(conn)}


def flush_pending_operations(conn, client: RadarRemoteClient, *, limit: int = 100) -> dict:
    """上传本地离线操作；失败保留队列，等待下次重试。"""
    sent = 0
    failed = 0
    for operation in list_pending_radar_operations(conn, limit=limit):
        row = conn.execute(
            """
            SELECT rm.project_id, rc.arxiv_id
            FROM radar_matches rm
            JOIN radar_candidates rc ON rc.id=rm.candidate_id
            WHERE rm.id=?
            """,
            (operation["match_id"],),
        ).fetchone()
        if not row:
            mark_radar_operation_result(conn, operation["id"], success=True)
            continue
        try:
            state = "read" if operation["operation"] == "read" else "saved" if operation["operation"] == "save" else "dismissed"
            client.update_state(row["project_id"], row["arxiv_id"], state)
            mark_radar_operation_result(conn, operation["id"], success=True)
            sent += 1
        except Exception as exc:
            mark_radar_operation_result(conn, operation["id"], success=False, error=str(exc))
            failed += 1
    return {"sent": sent, "failed": failed}
