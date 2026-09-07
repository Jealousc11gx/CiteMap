"""论文雷达 Action 的可选 LLM TLDR 生成。"""

from __future__ import annotations

import os
import json

from openai import OpenAI


def _enabled() -> bool:
    return os.getenv("RADAR_LLM_ENABLED", "true").strip().casefold() in {"1", "true", "yes", "on"}


def _required() -> bool:
    return os.getenv("RADAR_LLM_REQUIRED", "false").strip().casefold() in {"1", "true", "yes", "on"}


def enrich_with_tldr(items: list[dict]) -> list[dict]:
    """批量生成 TLDR。未开启或缺少配置时保留原摘要。"""
    if not items or not _enabled():
        return items
    key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
    if not key or not base_url:
        if _required():
            raise RuntimeError("未配置 LLM_API_KEY / LLM_BASE_URL，无法生成论文 TLDR")
        return items
    client = OpenAI(api_key=key, base_url=base_url)
    for item in items:
        try:
            prompt = (
                "请分析下面论文，严格只返回 JSON，不要 Markdown 代码块。字段："
                "tldr（中文，不超过80字）、ai_summary（中文，150-300字）、"
                "title_zh（中文标题）、abstract_zh（中文摘要）、core_contribution（核心贡献）、"
                "method（方法）、result（结果）、limitations（局限性）。未知字段填空字符串。\n\n"
                f"标题：{item.get('title', '')}\n摘要：{item.get('abstract', '')[:6000]}"
            )
            response = client.chat.completions.create(
                model=model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": "你是科研论文摘要助手。"},
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.choices[0].message.content if response.choices else ""
            raw = str(text or "{}").strip()
            if raw.startswith("```"):
                raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"tldr": str(text or "").strip()}
            if _required() and (not parsed.get("tldr") or not parsed.get("ai_summary")):
                raise RuntimeError("LLM 响应缺少 tldr 或 ai_summary")
            for field in ("tldr", "ai_summary", "title_zh", "abstract_zh", "core_contribution", "method", "result", "limitations"):
                value = str(parsed.get(field) or "").strip()
                if value:
                    item[field] = value
            item["tldr"] = str(item.get("tldr") or item.get("abstract") or "").strip()
        except Exception as exc:
            if _required():
                paper = item.get("arxiv_id") or item.get("title") or "unknown"
                raise RuntimeError(f"论文 {paper} 的 TLDR/AI 摘要生成失败: {exc}") from exc
            item["tldr"] = str(item.get("tldr") or item.get("abstract") or "").strip()
    return items
