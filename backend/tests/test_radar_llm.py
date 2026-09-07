"""论文雷达 Action LLM TLDR 测试。"""

from types import SimpleNamespace

import pytest

from paper_graph.radar_llm import _extract_paper_header, enrich_with_tldr


def test_tldr_disabled_keeps_items(monkeypatch):
    monkeypatch.setenv("RADAR_LLM_ENABLED", "false")
    items = [{"title": "A", "abstract": "Abstract"}]
    assert enrich_with_tldr(items) is items
    assert "tldr" not in items[0]


def test_tldr_uses_openai_compatible_client(monkeypatch):
    import paper_graph.radar_llm as module

    create = lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"tldr":"简短结论","ai_summary":"中文总结","title_zh":"中文标题","affiliations":["测试大学"],"corresponding_authors":["张老师"]}'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: client)
    monkeypatch.setenv("RADAR_LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "model")
    items = [{"title": "A", "abstract": "Abstract"}]
    result = enrich_with_tldr(items)[0]
    assert result["tldr"] == "简短结论"
    assert result["ai_summary"] == "中文总结"
    assert result["title_zh"] == "中文标题"
    assert result["affiliations"] == ["测试大学"]
    assert result["corresponding_authors"] == ["张老师"]


def test_tldr_optional_failure_does_not_skip_later_items(monkeypatch):
    import paper_graph.radar_llm as module

    responses = iter([
        RuntimeError("temporary failure"),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"tldr":"第二篇结论","ai_summary":"第二篇总结"}'))]),
    ])

    def create(**kwargs):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: client)
    monkeypatch.setenv("RADAR_LLM_ENABLED", "true")
    monkeypatch.setenv("RADAR_LLM_REQUIRED", "false")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    items = [
        {"title": "A", "abstract": "First abstract"},
        {"title": "B", "abstract": "Second abstract"},
    ]

    result = enrich_with_tldr(items)

    assert result[0]["tldr"] == "First abstract"
    assert result[1]["tldr"] == "第二篇结论"
    assert result[1]["ai_summary"] == "第二篇总结"


def test_tldr_required_rejects_incomplete_response(monkeypatch):
    import paper_graph.radar_llm as module

    create = lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"tldr":"只有结论"}'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: client)
    monkeypatch.setenv("RADAR_LLM_ENABLED", "true")
    monkeypatch.setenv("RADAR_LLM_REQUIRED", "true")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")

    with pytest.raises(RuntimeError, match="缺少中文 tldr 或中文 ai_summary"):
        enrich_with_tldr([{"arxiv_id": "2609.00001", "title": "A", "abstract": "Abstract"}])


def test_tldr_required_rejects_english_summary(monkeypatch):
    import paper_graph.radar_llm as module

    create = lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"tldr":"中文结论","ai_summary":"English summary"}'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: client)
    monkeypatch.setenv("RADAR_LLM_ENABLED", "true")
    monkeypatch.setenv("RADAR_LLM_REQUIRED", "true")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")

    with pytest.raises(RuntimeError, match="缺少中文 tldr 或中文 ai_summary"):
        enrich_with_tldr([{"arxiv_id": "2609.00001", "title": "A", "abstract": "Abstract"}])


def test_extract_paper_header_reads_first_pages(monkeypatch):
    import fitz
    import paper_graph.radar_llm as module

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Example University corresponding author")
    content = document.tobytes()
    document.close()
    response = SimpleNamespace(content=content, raise_for_status=lambda: None)
    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: response)

    assert "Example University" in _extract_paper_header({"pdf_url": "https://example.com/paper.pdf"})
