"""Tests for the Markdown export module."""

import pandas as pd
import pytest

import paper_graph.export as export_mod
from paper_graph.database import get_connection, upsert_paper


@pytest.fixture(autouse=True)
def patch_export_pandas(monkeypatch):
    """export.py references pandas via a module-global `pd`; inject it here."""
    monkeypatch.setattr(export_mod, "pd", pd, raising=False)


def test_export_markdown_empty(tmp_db, tmp_path):
    output = tmp_path / "export_empty.md"
    result = export_mod.export_markdown(output, db_path=tmp_db, title="Empty Export")

    assert result == output
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "# Empty Export" in text
    assert "论文清单" in text
    assert "**总计**：0 篇" in text


def test_export_markdown_with_data(tmp_db, tmp_path):
    output = tmp_path / "export_data.md"

    paper = {
        "id": "exp_paper_1",
        "title": "Exportable Paper Title",
        "abstract": "Abstract text.",
        "published_date": "2024-05-01",
        "updated_date": "2024-05-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2405.00001",
    }
    conn = get_connection(tmp_db)
    upsert_paper(conn, paper)
    conn.execute(
        "UPDATE papers SET core_contribution = ? WHERE id = ?",
        ("A breakthrough contribution.", paper["id"]),
    )

    # Institution
    conn.execute("INSERT OR IGNORE INTO institutions (name) VALUES (?)", ("Test University",))
    cur = conn.execute("SELECT id FROM institutions WHERE name = ?", ("Test University",))
    institution_id = cur.fetchone()["id"]

    # Team
    conn.execute(
        "INSERT OR IGNORE INTO teams (name, lead_institution_id, description) VALUES (?, ?, ?)",
        ("Dream Team", institution_id, "The best team."),
    )
    cur = conn.execute("SELECT id FROM teams WHERE name = ?", ("Dream Team",))
    team_id = cur.fetchone()["id"]

    conn.execute(
        "INSERT OR IGNORE INTO paper_teams (paper_id, team_id) VALUES (?, ?)",
        (paper["id"], team_id),
    )
    conn.commit()
    conn.close()

    result = export_mod.export_markdown(output, db_path=tmp_db, title="Data Export")
    assert result == output
    assert output.exists()

    text = output.read_text(encoding="utf-8")
    assert "# Data Export" in text
    assert "研究团队" in text
    assert "Dream Team" in text
    assert "Test University" in text
    assert "论文清单" in text
    assert "Exportable Paper Title" in text
    assert "A breakthrough contribution." in text
    assert "**总计**：1 篇" in text
