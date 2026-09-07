"""Tests for annotate module."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from paper_graph.annotate import AnnotationError, annotate_all, annotate_paper, get_client, get_default_model
from paper_graph.database import get_connection, get_paper, init_db, upsert_paper


def annotation_payload(core_contribution="测试核心贡献", teams=None, **overrides):
    payload = {
        "tldr": "本文研究测试问题，提出一种可验证的方法处理关键挑战，并在多个公开数据集的实验中获得稳定结果。结果表明该方法能够改善核心指标，同时降低使用成本，为相关研究提供了可复用的技术路径。",
        "core_contribution": core_contribution,
        "primary_domain": "Artificial Intelligence",
        "subfields": ["Machine Learning"],
        "tags": [{"name": "Test Method", "type": "method"}],
        "teams": teams or [],
    }
    payload.update(overrides)
    return payload


def test_init_db_migrates_annotation_schema(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE papers (
            id TEXT PRIMARY KEY, title TEXT, abstract TEXT, core_contribution TEXT,
            published_date TEXT, updated_date TEXT, categories TEXT, pdf_path TEXT,
            source TEXT, arxiv_url TEXT, created_at TEXT, enhanced_at TEXT
        )
    """)
    conn.commit()
    conn.close()

    init_db(db_path)

    conn = get_connection(db_path)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(papers)").fetchall()}
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    conn.close()
    assert {
        "tldr", "primary_domain", "subfields", "venue", "venue_year",
        "venue_evidence", "venue_checked_at", "venue_source", "arxiv_comment", "journal_ref",
    } <= columns
    assert {"tags", "paper_tags"} <= tables


class TestGetDefaultModel:
    def test_default_value(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL", raising=False)
        assert get_default_model() == "step-3.7-flash"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "custom-model")
        assert get_default_model() == "custom-model"


class TestGetClient:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        client = get_client()
        assert client.api_key == "dummy"
        assert str(client.base_url).rstrip("/") == "https://api.stepfun.com/step_plan/v1"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999/v1")
        client = get_client()
        assert client.api_key == "test-key"
        assert str(client.base_url).rstrip("/") == "http://localhost:9999/v1"

    def test_override_params(self):
        client = get_client(api_key="override-key", base_url="http://example.com/v1")
        assert client.api_key == "override-key"
        assert str(client.base_url).rstrip("/") == "http://example.com/v1"


def test_annotate_paper_core_logic(tmp_db, sample_paper, monkeypatch):
    """annotate_paper should call OpenAI, parse JSON, and update DB."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(annotation_payload(
        teams=[
            {
                "name": "测试团队",
                "institution": "测试机构",
                "members": ["作者A", "作者B"],
            }
        ],
    ))

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    # Patch get_client in the annotate module
    monkeypatch.setattr("paper_graph.annotate.get_client", lambda *args, **kwargs: mock_client)

    # Patch get_connection to always use tmp_db
    import paper_graph.annotate as annotate_mod
    import paper_graph.database as db_mod

    def _get_connection(db_path=None):
        return db_mod.get_connection(tmp_db)

    monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

    result = annotate_paper(sample_paper["id"], model="test-model")

    assert result["core_contribution"] == "测试核心贡献"
    assert result["tldr"].startswith("本文研究测试问题")
    assert result["primary_domain"] == "Artificial Intelligence"
    assert result["tags"] == [{"name": "Test Method", "type": "method"}]
    assert len(result["teams"]) == 1
    assert result["teams"][0]["name"] == "测试团队"

    # Verify DB updated
    conn = db_mod.get_connection(tmp_db)
    paper = db_mod.get_paper(conn, sample_paper["id"])
    conn.close()
    assert paper["core_contribution"] == "测试核心贡献"
    assert paper["tldr"] == result["tldr"]
    conn = db_mod.get_connection(tmp_db)
    tags = conn.execute(
        """
        SELECT t.name, t.type FROM paper_tags pt
        JOIN tags t ON t.id = pt.tag_id WHERE pt.paper_id = ?
        """,
        (sample_paper["id"],),
    ).fetchall()
    conn.close()
    assert [dict(tag) for tag in tags] == [{"name": "Test Method", "type": "method"}]


def test_annotate_paper_uses_explicit_db_path(tmp_db, sample_paper, monkeypatch):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(annotation_payload("显式数据库"))
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("paper_graph.annotate.get_client", lambda *args, **kwargs: mock_client)

    result = annotate_paper(sample_paper["id"], model="test-model", db_path=tmp_db)

    assert result["core_contribution"] == "显式数据库"
    conn = get_connection(tmp_db)
    paper = get_paper(conn, sample_paper["id"])
    conn.close()
    assert paper["core_contribution"] == "显式数据库"


def test_annotate_paper_includes_pdf_excerpt(tmp_db, sample_paper, monkeypatch):
    conn = get_connection(tmp_db)
    conn.execute("UPDATE papers SET pdf_path = ? WHERE id = ?", ("/tmp/paper.pdf", sample_paper["id"]))
    conn.commit()
    conn.close()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(annotation_payload("利用正文信息标注"))
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("paper_graph.annotate.get_client", lambda *args, **kwargs: mock_client)
    monkeypatch.setattr(
        "paper_graph.annotate.enrich_paper_metadata_from_pdf",
        lambda paper_id, db_path=None: (
            {**sample_paper, "pdf_path": "/tmp/paper.pdf"},
            {"excerpt": "Affiliation block. 1 Introduction. Important PDF evidence."},
        ),
    )

    annotate_paper(sample_paper["id"], model="test-model", db_path=tmp_db)

    prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "Important PDF evidence" in prompt
    assert "Affiliation block" in prompt


def test_annotate_paper_rejects_missing_abstract(tmp_db, sample_paper):
    conn = get_connection(tmp_db)
    conn.execute("UPDATE papers SET abstract = NULL WHERE id = ?", (sample_paper["id"],))
    conn.commit()
    conn.close()

    with pytest.raises(AnnotationError) as exc_info:
        annotate_paper(sample_paper["id"], model="test-model", db_path=tmp_db)

    assert exc_info.value.code == "ANNOTATE_ABSTRACT_MISSING"


def test_annotate_paper_rejects_already_annotated(tmp_db, sample_paper):
    conn = get_connection(tmp_db)
    conn.execute(
        "UPDATE papers SET tldr = ?, core_contribution = ?, venue_checked_at = ? WHERE id = ?",
        ("已有 TLDR", "已有贡献", "2026-01-01T00:00:00", sample_paper["id"]),
    )
    conn.commit()
    conn.close()

    with pytest.raises(AnnotationError) as exc_info:
        annotate_paper(sample_paper["id"], model="test-model", db_path=tmp_db)

    assert exc_info.value.code == "ANNOTATE_ALREADY_DONE"


def test_annotate_paper_force_replaces_existing_annotation(tmp_db, sample_paper, monkeypatch):
    conn = get_connection(tmp_db)
    conn.execute("UPDATE papers SET core_contribution = ? WHERE id = ?", ("旧贡献", sample_paper["id"]))
    conn.commit()
    conn.close()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(annotation_payload("新贡献"))
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("paper_graph.annotate.get_client", lambda *args, **kwargs: mock_client)

    result = annotate_paper(
        sample_paper["id"],
        model="test-model",
        db_path=tmp_db,
        force=True,
    )

    assert result["core_contribution"] == "新贡献"


def test_annotate_persists_institution_and_links_team_without_members(tmp_db, sample_paper, monkeypatch):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(annotation_payload(
        "机构写入测试",
        teams=[{
            "name": "测试实验室",
            "institution": "测试大学",
            "members": [],
        }],
    ))
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("paper_graph.annotate.get_client", lambda *args, **kwargs: mock_client)

    annotate_paper(sample_paper["id"], model="test-model", db_path=tmp_db)

    conn = get_connection(tmp_db)
    team = conn.execute(
        """
        SELECT t.name, i.name AS institution
        FROM paper_teams pt
        JOIN teams t ON t.id = pt.team_id
        LEFT JOIN institutions i ON i.id = t.lead_institution_id
        WHERE pt.paper_id = ?
        """,
        (sample_paper["id"],),
    ).fetchone()
    paper_institution = conn.execute(
        """
        SELECT i.name
        FROM paper_institutions pi
        JOIN institutions i ON i.id = pi.institution_id
        WHERE pi.paper_id = ?
        """,
        (sample_paper["id"],),
    ).fetchone()
    conn.close()

    assert dict(team) == {"name": "测试实验室", "institution": "测试大学"}
    assert paper_institution["name"] == "测试大学"


def test_annotate_persists_venue_with_verifiable_evidence(tmp_db, sample_paper, monkeypatch):
    evidence = "Accepted at AAAI 2026"
    conn = get_connection(tmp_db)
    conn.execute(
        "UPDATE papers SET arxiv_comment = ? WHERE id = ?",
        (evidence, sample_paper["id"]),
    )
    conn.commit()
    conn.close()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(annotation_payload(
        venue={"name": "AAAI", "year": 2026, "evidence": evidence},
    ))
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("paper_graph.annotate.get_client", lambda *args, **kwargs: mock_client)

    result = annotate_paper(sample_paper["id"], model="test-model", db_path=tmp_db)

    conn = get_connection(tmp_db)
    paper = get_paper(conn, sample_paper["id"])
    conn.close()
    assert result["venue"] == {"name": "AAAI", "year": 2026, "evidence": evidence}
    assert paper["venue"] == "AAAI"
    assert paper["venue_year"] == 2026
    assert paper["venue_evidence"] == evidence
    assert paper["venue_checked_at"]


def test_annotate_rejects_venue_without_source_evidence(tmp_db, sample_paper, monkeypatch):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(annotation_payload(
        venue={"name": "ICLR", "year": 2026, "evidence": "Accepted at ICLR 2026"},
    ))
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("paper_graph.annotate.get_client", lambda *args, **kwargs: mock_client)

    result = annotate_paper(sample_paper["id"], model="test-model", db_path=tmp_db)

    conn = get_connection(tmp_db)
    paper = get_paper(conn, sample_paper["id"])
    conn.close()
    assert result["venue"] is None
    assert paper["venue"] is None
    assert paper["venue_checked_at"]


def test_annotate_does_not_overwrite_manual_venue(tmp_db, sample_paper, monkeypatch):
    conn = get_connection(tmp_db)
    conn.execute(
        """
        UPDATE papers
        SET venue = 'ICLR', venue_year = 2025, venue_source = 'manual',
            venue_checked_at = '2026-01-01T00:00:00', arxiv_comment = 'Accepted at AAAI 2026'
        WHERE id = ?
        """,
        (sample_paper["id"],),
    )
    conn.commit()
    conn.close()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(annotation_payload(
        venue={"name": "AAAI", "year": 2026, "evidence": "Accepted at AAAI 2026"},
    ))
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    monkeypatch.setattr("paper_graph.annotate.get_client", lambda *args, **kwargs: mock_client)

    result = annotate_paper(sample_paper["id"], model="test-model", db_path=tmp_db, force=True)

    conn = get_connection(tmp_db)
    paper = get_paper(conn, sample_paper["id"])
    conn.close()
    assert paper["venue"] == "ICLR"
    assert paper["venue_year"] == 2025
    assert paper["venue_source"] == "manual"
    assert result["venue"]["name"] == "ICLR"


def test_force_annotation_replaces_team_links_without_duplicate_authors(tmp_db, sample_paper, monkeypatch):
    responses = [
        annotation_payload(
            "第一次",
            teams=[{"name": "旧团队", "institution": "旧机构", "members": ["New Author"]}],
        ),
        annotation_payload(
            "第二次",
            teams=[{"name": "新团队", "institution": "新机构", "members": ["New Author"]}],
        ),
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps(payload)))])
        for payload in responses
    ]
    monkeypatch.setattr("paper_graph.annotate.get_client", lambda *args, **kwargs: mock_client)

    annotate_paper(sample_paper["id"], model="test-model", db_path=tmp_db)
    annotate_paper(sample_paper["id"], model="test-model", db_path=tmp_db, force=True)

    conn = get_connection(tmp_db)
    team_names = [
        row["name"]
        for row in conn.execute(
            """
            SELECT t.name
            FROM paper_teams pt
            JOIN teams t ON t.id = pt.team_id
            WHERE pt.paper_id = ?
            """,
            (sample_paper["id"],),
        ).fetchall()
    ]
    author_count = conn.execute(
        "SELECT COUNT(*) FROM authors WHERE name = ?",
        ("New Author",),
    ).fetchone()[0]
    institution_names = [
        row["name"]
        for row in conn.execute(
            """
            SELECT i.name
            FROM paper_institutions pi
            JOIN institutions i ON i.id = pi.institution_id
            WHERE pi.paper_id = ?
            """,
            (sample_paper["id"],),
        ).fetchall()
    ]
    conn.close()

    assert team_names == ["新团队"]
    assert author_count == 1
    assert institution_names == ["新机构"]


def test_annotate_all_skips_done(tmp_db, monkeypatch):
    """annotate_all should skip papers that already have TLDR and core contribution."""
    papers = [
        {
            "id": "done_paper",
            "title": "Already Done",
            "abstract": "Abstract",
            "published_date": "2024-01-01",
            "updated_date": "2024-01-02",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00001",
            "core_contribution": "已有贡献",
        },
        {
            "id": "pending_paper",
            "title": "Pending Paper",
            "abstract": "Abstract",
            "published_date": "2024-01-03",
            "updated_date": "2024-01-04",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00002",
            "core_contribution": "",
        },
    ]

    conn = get_connection(tmp_db)
    for p in papers:
        upsert_paper(conn, p)
    # upsert_paper does not update core_contribution, set it explicitly
    conn.execute(
        "UPDATE papers SET tldr = ?, core_contribution = ?, venue_checked_at = ? WHERE id = ?",
        ("已有 TLDR", "已有贡献", "2026-01-01T00:00:00", "done_paper"),
    )
    conn.commit()
    conn.close()

    # Patch get_client and get_connection in annotate module
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(annotation_payload("新贡献"))
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    import paper_graph.annotate as annotate_mod
    import paper_graph.database as db_mod

    monkeypatch.setattr(annotate_mod, "get_client", lambda *args, **kwargs: mock_client)

    def _get_connection(db_path=None):
        return db_mod.get_connection(tmp_db)

    monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

    count = annotate_all(model="test-model", db_path=tmp_db)

    # Only the pending paper should be annotated
    assert count == 1

class TestAnnotateDegradation:
    """Test annotate_paper resilience against malformed LLM responses."""

    def test_non_json_response(self, tmp_db, sample_paper, monkeypatch):
        """LLM returns plain text instead of JSON; should raise JSONDecodeError."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "This is not JSON at all."

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        import paper_graph.annotate as annotate_mod
        import paper_graph.database as db_mod

        monkeypatch.setattr(annotate_mod, "get_client", lambda *a, **kw: mock_client)

        def _get_connection(db_path=None):
            return db_mod.get_connection(tmp_db)

        monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

        with pytest.raises(Exception):
            annotate_paper(sample_paper["id"], model="test-model")

    def test_empty_content(self, tmp_db, sample_paper, monkeypatch):
        """LLM returns empty string; should raise JSONDecodeError."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = ""

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        import paper_graph.annotate as annotate_mod
        import paper_graph.database as db_mod

        monkeypatch.setattr(annotate_mod, "get_client", lambda *a, **kw: mock_client)

        def _get_connection(db_path=None):
            return db_mod.get_connection(tmp_db)

        monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

        with pytest.raises(Exception):
            annotate_paper(sample_paper["id"], model="test-model")

    def test_missing_teams_field(self, tmp_db, sample_paper, monkeypatch):
        """LLM returns JSON without 'teams'; should not crash."""
        mock_response = MagicMock()
        payload = annotation_payload("Only contribution")
        payload.pop("teams")
        mock_response.choices[0].message.content = json.dumps(payload)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        import paper_graph.annotate as annotate_mod
        import paper_graph.database as db_mod

        monkeypatch.setattr(annotate_mod, "get_client", lambda *a, **kw: mock_client)

        def _get_connection(db_path=None):
            return db_mod.get_connection(tmp_db)

        monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

        result = annotate_paper(sample_paper["id"], model="test-model")
        assert result["core_contribution"] == "Only contribution"
        assert result.get("teams", []) == []

    def test_missing_core_contribution_field(self, tmp_db, sample_paper, monkeypatch):
        """LLM response without required summary fields should be rejected."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "teams": [{"name": "Team", "members": []}],
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        import paper_graph.annotate as annotate_mod
        import paper_graph.database as db_mod

        monkeypatch.setattr(annotate_mod, "get_client", lambda *a, **kw: mock_client)

        def _get_connection(db_path=None):
            return db_mod.get_connection(tmp_db)

        monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

        with pytest.raises(AnnotationError) as exc_info:
            annotate_paper(sample_paper["id"], model="test-model")
        assert exc_info.value.code == "LLM_RESPONSE_INVALID"

    def test_short_tldr_is_rejected(self, tmp_db, sample_paper, monkeypatch):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(annotation_payload(
            "有效核心贡献",
            tldr="过短的 TLDR",
        ))
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        monkeypatch.setattr("paper_graph.annotate.get_client", lambda *args, **kwargs: mock_client)

        with pytest.raises(AnnotationError) as exc_info:
            annotate_paper(sample_paper["id"], model="test-model", db_path=tmp_db)

        assert exc_info.value.code == "LLM_RESPONSE_INVALID"
        assert "TLDR 过短" in str(exc_info.value)

    def test_markdown_code_block_wrapped_json(self, tmp_db, sample_paper, monkeypatch):
        """LLM wraps JSON in ```json ... ```; should be parsed correctly."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = (
            "```json\n"
            + json.dumps(annotation_payload(
                "Wrapped contribution",
                teams=[{"name": "Team", "members": ["A"]}],
            ))
            + "\n```"
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        import paper_graph.annotate as annotate_mod
        import paper_graph.database as db_mod

        monkeypatch.setattr(annotate_mod, "get_client", lambda *a, **kw: mock_client)

        def _get_connection(db_path=None):
            return db_mod.get_connection(tmp_db)

        monkeypatch.setattr(annotate_mod, "get_connection", _get_connection)

        result = annotate_paper(sample_paper["id"], model="test-model")
        assert result["core_contribution"] == "Wrapped contribution"
