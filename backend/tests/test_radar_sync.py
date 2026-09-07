"""论文雷达远端增量同步与离线操作测试。"""

from paper_graph.database import create_project, get_connection
from paper_graph.radar import enqueue_radar_operation, get_radar_sync_cursor, upsert_radar_candidate, upsert_radar_match
from paper_graph.radar_sync import RadarRemoteClient, flush_pending_operations, sync_remote_changes


class FakeRemote:
    def __init__(self, pages):
        self.pages = list(pages)
        self.states = []

    def pull_changes(self, cursor, limit=200):
        return self.pages.pop(0)

    def update_state(self, project_id, arxiv_id, state):
        self.states.append((project_id, arxiv_id, state))
        return {"ok": True}


def test_remote_client_normalizes_endpoint_url_to_worker_root():
    assert RadarRemoteClient("https://radar.example/sync", "token").base_url == "https://radar.example"
    assert RadarRemoteClient("https://radar.example/profiles/", "token").base_url == "https://radar.example"


def test_sync_remote_changes_pulls_history_and_advances_cursor(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Sync")
    remote = FakeRemote([
        {"events": [{"type": "recommended", "project_id": project["id"], "arxiv_id": "2609.1", "title": "A", "abstract": "x", "score": 0.8, "tldr": "短结论", "ai_summary": "中文总结", "affiliations": ["测试大学"], "corresponding_authors": ["张老师"]}], "next_cursor": "1", "has_more": True},
        {"events": [{"type": "read", "project_id": project["id"], "arxiv_id": "2609.1"}], "next_cursor": "2", "has_more": False},
    ])
    result = sync_remote_changes(conn, remote)
    assert result == {"applied": 2, "pages": 2, "cursor": "2"}
    assert get_radar_sync_cursor(conn) == "2"
    state = conn.execute("SELECT state FROM radar_matches").fetchone()["state"]
    assert state == "read"
    candidate = conn.execute("SELECT tldr, ai_summary, affiliations, corresponding_authors FROM radar_candidates").fetchone()
    assert dict(candidate) == {"tldr": "短结论", "ai_summary": "中文总结", "affiliations": '["测试大学"]', "corresponding_authors": '["张老师"]'}
    conn.close()


def test_flush_pending_operations_sends_and_removes_queue(tmp_db):
    conn = get_connection(tmp_db)
    project = create_project(conn, "Flush")
    candidate = upsert_radar_candidate(conn, {"arxiv_id": "2609.2", "title": "B"})
    match = upsert_radar_match(conn, project["id"], candidate["id"])
    enqueue_radar_operation(conn, project["id"], match["id"], "read")
    remote = FakeRemote([])
    assert flush_pending_operations(conn, remote) == {"sent": 1, "failed": 0}
    assert remote.states == [(project["id"], "2609.2", "read")]
    conn.close()
