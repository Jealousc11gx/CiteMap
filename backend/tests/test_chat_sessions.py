"""Tests for chat session management and streaming APIs."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from paper_graph.database import init_db, get_connection, upsert_paper


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test.db"
    import main as main_module
    import paper_graph.database as db_module

    original_db_path = main_module.DB_PATH
    main_module.DB_PATH = db_file
    db_module.DB_PATH = db_file
    init_db(db_file)

    yield TestClient(app)

    main_module.DB_PATH = original_db_path
    db_module.DB_PATH = original_db_path


class TestChatSessions:
    def test_current_message_is_not_duplicated_in_agent_history(self, client, monkeypatch):
        captured = {}

        def fake_chat_generate(message, history=None):
            from main import ChatResponse

            captured["message"] = message
            captured["history"] = history
            return ChatResponse(mode="agent", answer="ok", papers=[], tool_calls=[])

        monkeypatch.setattr("main._chat_generate", fake_chat_generate)

        resp = client.post(
            "/api/chat/sessions/history-check/messages",
            json={"message": "只出现一次", "mode": "auto"},
        )

        assert resp.status_code == 200
        assert captured["message"] == "只出现一次"
        assert all(item["content"] != "只出现一次" for item in captured["history"])

    def test_list_sessions_empty(self, client):
        resp = client.get("/api/chat/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_session(self, client):
        resp = client.post("/api/chat/sessions", json={"title": "测试会话"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "测试会话"
        assert "id" in data
        assert "created_at" in data

    def test_create_session_default_title(self, client):
        resp = client.post("/api/chat/sessions", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == ""

    def test_delete_session(self, client):
        resp = client.post("/api/chat/sessions", json={"title": "待删除"})
        assert resp.status_code == 200
        session_id = resp.json()["id"]

        resp = client.delete(f"/api/chat/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        resp = client.get("/api/chat/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_session_lifecycle(self, client):
        # 创建会话
        resp = client.post("/api/chat/sessions", json={"title": "生命周期测试"})
        assert resp.status_code == 200
        session_id = resp.json()["id"]

        # 发送消息
        resp = client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"message": "列出论文", "mode": "auto"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "mode" in data

        # 获取消息历史
        resp = client.get(f"/api/chat/sessions/{session_id}/messages")
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2  # user + assistant
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "列出论文"
        assert messages[1]["role"] == "assistant"

        # 删除会话
        resp = client.delete(f"/api/chat/sessions/{session_id}")
        assert resp.status_code == 200

        resp = client.get(f"/api/chat/sessions/{session_id}/messages")
        assert resp.status_code == 200
        assert resp.json() == []


class TestChatStreaming:
    def test_stream_chat_message(self, client):
        # 创建会话
        resp = client.post("/api/chat/sessions", json={"title": "流式测试"})
        assert resp.status_code == 200
        session_id = resp.json()["id"]

        # 流式发送消息
        resp = client.post(
            f"/api/chat/sessions/{session_id}/messages/stream",
            json={"message": "hello", "mode": "auto"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        # 读取流式响应
        text = resp.text
        assert len(text) > 0
        assert "hello" not in text  # 流式响应不包含用户消息，只包含 assistant 回复

        # 消息应已持久化
        resp = client.get(f"/api/chat/sessions/{session_id}/messages")
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hello"
        assert messages[1]["role"] == "assistant"
        assert len(messages[1]["content"]) > 0


class TestChatCompatibility:
    def test_legacy_chat_endpoint(self, client):
        resp = client.post("/api/chat", json={"message": "hello", "mode": "auto"})
        assert resp.status_code == 200
        data = resp.json()
        assert "mode" in data
        assert "answer" in data
        assert "papers" in data

        # 应该写入 default 会话
        resp = client.get("/api/chat/sessions/default/messages")
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2
        assert messages[0]["content"] == "hello"
