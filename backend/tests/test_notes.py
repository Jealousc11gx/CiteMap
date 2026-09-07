"""Tests for the Markdown notes module."""

import pytest

from paper_graph.notes import (
    _parse_frontmatter,
    _serialize_frontmatter,
    _relative_pdf_path,
    create_note_template,
    delete_note,
    get_note,
    list_notes,
    save_note,
)
from paper_graph.database import get_connection, upsert_paper


@pytest.fixture
def tmp_notes_dir(tmp_path, monkeypatch):
    """Redirect NOTES_DIR to a temp directory for the duration of a test."""
    d = tmp_path / "notes"
    d.mkdir()
    import paper_graph.notes as notes_mod

    monkeypatch.setattr(notes_mod, "NOTES_DIR", d)
    return d


def test_parse_frontmatter_normal():
    content = '---\ntitle: Hello World\nauthors: ["Alice", "Bob"]\ncategories: ["cs.AI", "cs.CL"]\n---\nBody line 1\nBody line 2'
    meta, body = _parse_frontmatter(content)

    assert meta["title"] == "Hello World"
    assert meta["authors"] == ["Alice", "Bob"]
    assert meta["categories"] == ["cs.AI", "cs.CL"]
    assert body == "Body line 1\nBody line 2"


def test_parse_frontmatter_no_frontmatter():
    content = "Just a plain markdown body.\n"
    meta, body = _parse_frontmatter(content)
    assert meta == {}
    assert body == content


def test_parse_frontmatter_malformed_list_literal():
    # Missing closing bracket - literal_eval should fail and leave value as string.
    content = "---\ntags: [one, two\n---\nbody"
    meta, body = _parse_frontmatter(content)
    assert meta["tags"] == "[one, two"
    assert body == "body"


def test_serialize_frontmatter():
    meta = {
        "title": "Paper Title",
        "authors": [["Alice", "MIT"], ["Bob"]],
        "categories": ["cs.AI"],
    }
    text = _serialize_frontmatter(meta)
    assert "title: Paper Title" in text
    assert "authors: " in text
    assert "categories: " in text


def test_relative_pdf_path():
    import os

    expected = f"..{os.sep}pdfs{os.sep}p1.pdf"
    assert _relative_pdf_path("p1", "/data/pdfs/p1.pdf") == expected
    assert _relative_pdf_path("p1", None) == ""
    assert _relative_pdf_path("p1", "") == ""


def test_save_note_and_get_note_and_list_notes(tmp_db, tmp_notes_dir):
    paper = {
        "id": "note_paper_1",
        "title": "Note Paper",
        "abstract": "Abstract",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
    }
    conn = get_connection(tmp_db)
    upsert_paper(conn, paper)
    conn.commit()
    conn.close()

    result = save_note(tmp_db, "note_paper_1", "# Note\ncontent")
    assert result["paper_id"] == "note_paper_1"

    note_file = tmp_notes_dir / "note_paper_1.md"
    assert note_file.exists()
    assert note_file.read_text(encoding="utf-8") == "# Note\ncontent"

    fetched = get_note(tmp_db, "note_paper_1")
    assert fetched is not None
    assert fetched["paper_id"] == "note_paper_1"
    assert fetched["body"] == "# Note\ncontent"
    assert fetched["note_edited_at"] is not None

    listed = list_notes(tmp_db)
    assert len(listed) == 1
    assert listed[0]["paper_id"] == "note_paper_1"


def test_create_note_template(tmp_db, tmp_notes_dir):
    paper = {
        "id": "tpl_paper_1",
        "title": "Template Paper",
        "abstract": "Abstract text.",
        "published_date": "2024-02-01",
        "updated_date": "2024-02-02",
        "categories": "cs.CL, cs.AI",
        "pdf_path": "/data/pdfs/tpl_paper_1.pdf",
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2402.00001",
        "core_contribution": "A core contribution.",
    }
    conn = get_connection(tmp_db)
    upsert_paper(conn, paper)
    # upsert_paper does not include core_contribution, so update it directly
    conn.execute(
        "UPDATE papers SET core_contribution = ? WHERE id = ?",
        (paper["core_contribution"], paper["id"]),
    )
    conn.commit()
    conn.close()

    result = create_note_template(tmp_db, paper_id="tpl_paper_1")
    assert result["paper_id"] == "tpl_paper_1"

    note_file = tmp_notes_dir / "tpl_paper_1.md"
    assert note_file.exists()
    content = note_file.read_text(encoding="utf-8")
    assert "Template Paper" in content
    assert "A core contribution." in content
    assert "Abstract text." in content
    assert "---" in content
    assert result["content"] == content

    conn = get_connection(tmp_db)
    paper_after_template = conn.execute(
        "SELECT note_edited_at FROM papers WHERE id = ?",
        ("tpl_paper_1",),
    ).fetchone()
    conn.close()
    assert paper_after_template["note_edited_at"] is None
    assert list_notes(tmp_db) == []
    draft = get_note(tmp_db, "tpl_paper_1")
    assert draft is not None
    assert draft["note_edited_at"] is None

    save_note(tmp_db, "tpl_paper_1", content + "\n用户修改")
    assert [note["paper_id"] for note in list_notes(tmp_db)] == ["tpl_paper_1"]


def test_delete_note(tmp_db, tmp_notes_dir):
    paper = {
        "id": "del_paper_1",
        "title": "Delete Paper",
        "abstract": "Abstract",
        "published_date": "2024-03-01",
        "updated_date": "2024-03-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2403.00001",
    }
    conn = get_connection(tmp_db)
    upsert_paper(conn, paper)
    conn.commit()
    conn.close()

    save_note(tmp_db, "del_paper_1", "deletable content")
    assert (tmp_notes_dir / "del_paper_1.md").exists()

    result = delete_note(tmp_db, "del_paper_1")
    assert result == {"paper_id": "del_paper_1", "deleted": True}
    assert not (tmp_notes_dir / "del_paper_1.md").exists()

    conn = get_connection(tmp_db)
    row = conn.execute("SELECT md_path FROM papers WHERE id = ?", ("del_paper_1",)).fetchone()
    conn.close()
    assert row["md_path"] is None


def test_save_note_raises_for_missing_paper(tmp_db, tmp_notes_dir):
    with pytest.raises(ValueError, match="论文不存在"):
        save_note(tmp_db, "missing_id", "content")


def test_delete_note_raises_for_missing_paper(tmp_db):
    with pytest.raises(ValueError, match="论文不存在"):
        delete_note(tmp_db, "missing_id")


def test_create_note_template_raises_for_missing_paper(tmp_db):
    with pytest.raises(ValueError, match="论文不存在"):
        create_note_template(tmp_db, paper_id="missing_id")
