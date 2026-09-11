import json
from types import SimpleNamespace

import pytest

from paper_graph.explore_llm import call_json, extract_json


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('result: {"a": 1} trailing', {"a": 1}),
    ],
)
def test_extract_json_matches_reference_tolerance(raw, expected):
    assert extract_json(raw) == expected


def test_call_json_uses_second_five_attempt_burst_without_structured_output():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) <= 5:
            content = "not json"
        else:
            content = json.dumps({"ok": True})
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    result = call_json(
        client,
        model="test",
        system="system",
        user="user",
        sleep=lambda _seconds: None,
    )
    assert result == {"ok": True}
    assert len(calls) == 6
    assert all("response_format" in call for call in calls[:5])
    assert "response_format" not in calls[5]
