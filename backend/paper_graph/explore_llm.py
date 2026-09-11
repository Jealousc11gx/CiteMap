"""Explore LLM JSON 调用适配层。"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from pathlib import Path

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def load_prompt(filename: str) -> str:
    return (Path(__file__).resolve().parent / "prompts" / filename).read_text()


def extract_json(text: object) -> dict:
    raw = str(text or "").strip()
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        raw = match.group(0)
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("模型返回 JSON 必须是对象")
    return result


def _response_text(response: object) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    return str(getattr(choices[0].message, "content", "") or "")


def _attempt_burst(
    client,
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    structured: bool,
    sleep: Callable[[float], None],
) -> dict:
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            if structured:
                kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**kwargs)
            return extract_json(_response_text(response))
        except Exception as exc:
            last_error = exc
            if attempt < 4:
                sleep(min(20, 2**attempt))
    assert last_error is not None
    raise last_error


def call_json(
    client,
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1024,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """执行两轮、每轮最多 5 次调用；第二轮关闭 structured output。"""
    try:
        return _attempt_burst(
            client,
            model=model,
            system=system,
            user=user,
            max_tokens=max_tokens,
            structured=True,
            sleep=sleep,
        )
    except Exception:
        return _attempt_burst(
            client,
            model=model,
            system=system,
            user=user,
            max_tokens=max_tokens,
            structured=False,
            sleep=sleep,
        )
