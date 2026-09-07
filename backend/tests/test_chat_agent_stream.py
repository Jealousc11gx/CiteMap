"""Tests for chat_agent stream output."""

import json
from unittest.mock import MagicMock, AsyncMock
import pytest

from paper_graph.chat_agent import _run_agent_stream, _sse_event
from kosong.message import TextPart, ThinkPart
from kimi_cli.wire.types import ToolCall, ToolResult


class FakeAsyncContextManager:
    """Helper to make an object usable as async context manager."""
    def __init__(self, enter_value):
        self.enter_value = enter_value

    async def __aenter__(self):
        return self.enter_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


@pytest.mark.asyncio
async def test_run_agent_stream_yields_multiple_thinking_events(monkeypatch):
    """流式输出应该为每个 ContentPart yield 一个 thinking 事件。"""
    async def mock_prompt(_prompt, merge_wire_messages=False):
        yield TextPart(text="Hello")
        yield TextPart(text=" ")
        yield TextPart(text="World")
        yield ThinkPart(think="思考中...")

    mock_session = MagicMock()
    mock_session.prompt = mock_prompt

    async def mock_session_create(*args, **kwargs):
        return FakeAsyncContextManager(mock_session)

    monkeypatch.setattr("paper_graph.chat_agent.Session.create", mock_session_create)
    monkeypatch.setattr("paper_graph.chat_agent.AGENT_YAML", MagicMock(exists=lambda: True))

    events = []
    async for event in _run_agent_stream("test message"):
        events.append(event)

    thinking_events = [e for e in events if e.get("type") == "thinking"]
    assert len(thinking_events) >= 1
    assert "Hello" in thinking_events[-1]["content"]
    assert "World" in thinking_events[-1]["content"]
    assert all("思考中" not in e.get("content", "") for e in events)
    assert events[-1]["content"] == "Hello World"


@pytest.mark.asyncio
async def test_run_agent_stream_yields_answer_at_end(monkeypatch):
    """流式输出最后应该 yield 一个 answer 事件。"""
    async def mock_prompt(_prompt, merge_wire_messages=False):
        yield TextPart(text="Final answer")

    mock_session = MagicMock()
    mock_session.prompt = mock_prompt

    async def mock_session_create(*args, **kwargs):
        return FakeAsyncContextManager(mock_session)

    monkeypatch.setattr("paper_graph.chat_agent.Session.create", mock_session_create)
    monkeypatch.setattr("paper_graph.chat_agent.AGENT_YAML", MagicMock(exists=lambda: True))

    events = []
    async for event in _run_agent_stream("test message"):
        events.append(event)

    assert events[-1]["type"] == "answer"
    assert events[-1]["content"] == "Final answer"


@pytest.mark.asyncio
async def test_run_agent_stream_handles_tool_call_and_result(monkeypatch):
    """流式输出应该 yield tool_call 和 tool_result 事件。"""
    from kimi_agent_sdk import ToolOk

    async def mock_prompt(_prompt, merge_wire_messages=False):
        yield ToolCall(
            id="call_1",
            function=ToolCall.FunctionBody(name="search_arxiv", arguments='{"query":"test"}'),
        )
        yield ToolResult(
            tool_call_id="call_1",
            return_value=ToolOk(output="result output", message="done"),
        )

    mock_session = MagicMock()
    mock_session.prompt = mock_prompt

    async def mock_session_create(*args, **kwargs):
        return FakeAsyncContextManager(mock_session)

    monkeypatch.setattr("paper_graph.chat_agent.Session.create", mock_session_create)
    monkeypatch.setattr("paper_graph.chat_agent.AGENT_YAML", MagicMock(exists=lambda: True))

    events = []
    async for event in _run_agent_stream("test message"):
        events.append(event)

    tool_call_events = [e for e in events if e.get("type") == "tool_call"]
    tool_result_events = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_call_events) == 1
    assert tool_call_events[0]["tool"] == "search_arxiv"
    assert len(tool_result_events) == 1


def test_sse_event_format():
    """SSE 事件应该格式化为 data: {...}\n\n"""
    result = _sse_event("thinking", {"content": "hello"})
    assert result.startswith("data: ")
    assert result.endswith("\n\n")
    parsed = json.loads(result.replace("data: ", "").strip())
    assert parsed["type"] == "thinking"
    assert parsed["content"] == "hello"
