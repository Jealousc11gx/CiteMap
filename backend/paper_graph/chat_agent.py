"""CiteMap - 基于 Kimi Agent SDK 的聊天 Agent。

每次用户发一条消息，后端创建一个 Kimi Session，让 LLM 在一个 turn 内自主调用工具、
看结果，最后给出面向用户的自然语言回答。所有工具调用过程都会保留，便于前端展示。
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from kimi_agent_sdk import Session, ApprovalRequest
from kimi_agent_sdk._aggregator import MessageAggregator
from kimi_cli.wire.types import ContentPart, ToolCall, ToolResult
from kosong.message import TextPart, ThinkPart


def ensure_kimi_config() -> None:
    """根据 backend/.env 里的 LLM_* 变量生成 ~/.kimi/config.toml。

    这是 Kimi Agent SDK 实际读取配置的地方。若已有可用配置则保留。
    """
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "").strip()
    model = os.environ.get("LLM_MODEL", "").strip()

    share_dir = Path.home() / ".kimi"
    cfg_path = share_dir / "config.toml"

    def _has_usable_config(path: Path) -> bool:
        if not path.exists():
            return False
        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib  # type: ignore
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            return False
        providers = data.get("providers", {})
        models = data.get("models", {})
        has_provider = any(
            isinstance(v, dict) and v.get("base_url") and v.get("api_key")
            for v in providers.values()
        )
        has_model = any(
            isinstance(v, dict) and v.get("provider") for v in models.values()
        )
        return has_provider and has_model

    # 如果环境变量没配，但 config.toml 已有可用配置，直接复用
    if not api_key and _has_usable_config(cfg_path):
        return

    # 既没有 env 也没有现成配置，无法运行
    if not api_key or not base_url or not model:
        return

    provider_type = os.environ.get("LLM_PROVIDER_TYPE", "openai_legacy").strip() or "openai_legacy"
    caps_raw = os.environ.get("LLM_CAPABILITIES", "")
    caps_list = [c.strip() for c in caps_raw.split(",") if c.strip()]

    try:
        max_ctx = int(os.environ.get("LLM_MAX_CONTEXT_SIZE", "128000"))
    except ValueError:
        max_ctx = 128000

    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    provider_label = "primary"
    content = (
        f'default_model = "{_esc(model)}"\n'
        f'default_yolo = true\n\n'
        f'[providers.{provider_label}]\n'
        f'type = "{_esc(provider_type)}"\n'
        f'base_url = "{_esc(base_url)}"\n'
        f'api_key = "{_esc(api_key)}"\n\n'
        f'[models."{_esc(model)}"]\n'
        f'provider = "{provider_label}"\n'
        f'model = "{_esc(model)}"\n'
        f'max_context_size = {max_ctx}\n'
    )
    if caps_list:
        content += f'capabilities = ["' + '", "'.join(_esc(c) for c in caps_list) + '"]\n'

    share_dir.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(content, encoding="utf-8")


AGENT_YAML = Path(__file__).resolve().parent.parent / "agent.yaml"
AGENTS_MD = Path(__file__).resolve().parent.parent / "AGENTS.md"

MAX_STEPS_PER_TURN = 8


def _serialize_tool_result(return_value: Any) -> dict[str, Any]:
    """把 Kimi 的 ToolOk/ToolError 转成可 JSON 序列化的字典。"""
    try:
        from kimi_agent_sdk import ToolOk, ToolError

        if isinstance(return_value, ToolOk):
            return {
                "success": True,
                "output": return_value.output,
                "message": return_value.message,
            }
        if isinstance(return_value, ToolError):
            return {
                "success": False,
                "message": return_value.message,
                "brief": return_value.brief,
            }
    except Exception:
        pass
    if hasattr(return_value, "model_dump"):
        return return_value.model_dump()
    return {"raw": str(return_value)}


async def _run_agent_stream(
    user_message: str,
    history: Optional[list[dict[str, Any]]] = None,
    project_id: Optional[str] = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """统一的 Agent 流式执行逻辑，供同步/流式入口复用。"""
    ensure_kimi_config()

    if not AGENT_YAML.exists():
        yield {
            "type": "answer",
            "content": f"agent.yaml 不存在：{AGENT_YAML}",
            "papers": [],
            "tool_calls": [],
        }
        return

    def _auto_approve(req: ApprovalRequest) -> None:
        if not req.resolved:
            req.resolve("approve")

    prompt_lines: list[str] = []
    if history:
        for h in history[-20:]:
            role = h.get("role", "user")
            content = h.get("content", "")
            prompt_lines.append(f"{role}: {content}")
    prompt_lines.append(f"user: {user_message}")
    prompt = "\n".join(prompt_lines)

    collected_text = ""
    collected_tool_calls: list[dict] = []

    from . import chat_tools
    project_token = chat_tools.set_active_project(project_id)
    try:
        async with await Session.create(
            agent_file=AGENT_YAML,
            thinking=True,
            yolo=True,
            max_steps_per_turn=MAX_STEPS_PER_TURN,
        ) as session:
            async for wire in session.prompt(prompt, merge_wire_messages=True):
                if isinstance(wire, ApprovalRequest):
                    _auto_approve(wire)
                    continue
                if isinstance(wire, ToolCall):
                    func = wire.function
                    tc = {
                        "tool": getattr(func, "name", "unknown"),
                        "arguments": json.loads(getattr(func, "arguments", "{}")),
                        "status": "running",
                    }
                    collected_tool_calls.append(tc)
                    yield {"type": "tool_call", **tc}
                    continue
                if isinstance(wire, ToolResult):
                    for tc in reversed(collected_tool_calls):
                        if tc.get("status") == "running":
                            tc["status"] = "done"
                            tc["result"] = _serialize_tool_result(wire.return_value)
                            yield {"type": "tool_result", "tool": tc["tool"], "result": tc["result"]}
                            break
                    continue
                if isinstance(wire, ContentPart):
                    if isinstance(wire, TextPart):
                        text = wire.text or ""
                        collected_text += text
                        yield {"type": "thinking", "content": collected_text}
                    elif isinstance(wire, ThinkPart):
                        # SDK 推理内容不属于最终回答，不展示、不持久化。
                        continue
                    continue
    except Exception as e:
        yield {
            "type": "answer",
            "content": f"Agent 运行出错：{str(e)}",
            "papers": [],
            "tool_calls": collected_tool_calls,
        }
        return
    finally:
        chat_tools.reset_active_project(project_token)

    collected_papers = await _collect_papers_from_tool_calls(collected_tool_calls, project_id=project_id)

    yield {
        "type": "answer",
        "content": collected_text or "（无回复）",
        "papers": collected_papers,
        "tool_calls": collected_tool_calls,
    }


async def _run_agent_async(
    user_message: str,
    history: Optional[list[dict[str, Any]]] = None,
    project_id: Optional[str] = None,
) -> dict[str, Any]:
    """异步内部实现：运行一次 Kimi Session turn，返回最终回答。"""
    final_answer = ""
    final_tool_calls: list[dict] = []
    final_papers: list[dict] = []

    async for event in _run_agent_stream(user_message, history, project_id=project_id):
        if event["type"] == "thinking":
            final_answer = event.get("content", "")
        elif event["type"] == "tool_call":
            final_tool_calls.append(event)
        elif event["type"] == "tool_result":
            for tc in reversed(final_tool_calls):
                if tc.get("status") == "running":
                    tc["status"] = "done"
                    tc["result"] = event.get("result")
                    break
        elif event["type"] == "answer":
            final_answer = event.get("content", final_answer)
            final_tool_calls = event.get("tool_calls", final_tool_calls)
            final_papers = event.get("papers", [])

    return {
        "answer": final_answer,
        "tool_calls": final_tool_calls,
        "mode": "agent",
        "papers": final_papers,
    }


async def _collect_papers_from_tool_calls(
    tool_calls: list[dict[str, Any]],
    project_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """遍历工具调用结果，提取论文 ID 并查询详情。

    支持的字段：
    - result.output / result.paper_id
    - result.output / result.papers[].id / paper_id
    """
    collected_ids: list[str] = []

    def _extract_ids_from_obj(obj: Any) -> None:
        if isinstance(obj, dict):
            if "paper_id" in obj and isinstance(obj["paper_id"], str):
                collected_ids.append(obj["paper_id"])
            if "papers" in obj and isinstance(obj["papers"], list):
                for p in obj["papers"]:
                    if isinstance(p, dict):
                        for key in ("id", "paper_id"):
                            if key in p and isinstance(p[key], str):
                                collected_ids.append(p[key])
                                break
        elif isinstance(obj, list):
            for item in obj:
                _extract_ids_from_obj(item)

    for tc in tool_calls:
        result = tc.get("result")
        if isinstance(result, dict):
            # ToolOk 序列化后会把 output 放在 result.output 里
            output = result.get("output")
            if output is not None:
                try:
                    parsed = json.loads(output) if isinstance(output, str) else output
                    _extract_ids_from_obj(parsed)
                except Exception:
                    pass
            _extract_ids_from_obj(result)

    # 去重并保持顺序
    seen: set[str] = set()
    unique_ids: list[str] = []
    for pid in collected_ids:
        if pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)

    from . import chat_tools
    project_token = chat_tools.set_active_project(project_id)
    collected_papers: list[dict] = []
    try:
        for pid in unique_ids:
            try:
                detail = await asyncio.to_thread(chat_tools.get_paper_details, pid)
                if detail.get("success") and detail.get("paper"):
                    collected_papers.append(detail["paper"])
            except Exception:
                pass
    finally:
        chat_tools.reset_active_project(project_token)

    return collected_papers


def run_agent(
    user_message: str,
    history: Optional[list[dict[str, Any]]] = None,
    model: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict[str, Any]:
    """同步入口：运行 Agent 并返回最终回答。"""
    return asyncio.run(_run_agent_async(user_message, history, project_id=project_id))


async def run_agent_stream(
    user_message: str,
    history: Optional[list[dict[str, Any]]] = None,
    model: Optional[str] = None,
    project_id: Optional[str] = None,
):
    """流式入口：产生 SSE 事件（thinking / tool_call / tool_result / answer）。"""
    async for event in _run_agent_stream(user_message, history, project_id=project_id):
        event_type = event.get("type", "answer")
        data = {k: v for k, v in event.items() if k != "type"}
        yield _sse_event(event_type, data)


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    """把事件封装成 SSE 格式的字符串。"""
    return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False, default=str)}\n\n"
