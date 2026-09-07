"""Tests for graph module."""

from pathlib import Path

import networkx as nx
import pytest

from paper_graph.graph import build_paper_graph, build_team_graph, export_html, visualize
from paper_graph.database import get_connection, upsert_paper


def test_build_team_graph_empty(tmp_db):
    graph = build_team_graph(tmp_db)
    assert isinstance(graph, nx.Graph)
    assert graph.number_of_nodes() == 0
    assert graph.number_of_edges() == 0


def test_build_paper_graph_empty(tmp_db):
    graph = build_paper_graph(tmp_db)
    assert isinstance(graph, nx.Graph)
    assert graph.number_of_nodes() == 0
    assert graph.number_of_edges() == 0


def test_build_paper_graph_with_data(tmp_db):
    """With papers and shared authors, build_paper_graph should produce nodes and edges."""
    papers = [
        {
            "id": "p1",
            "title": "Paper 1",
            "abstract": "Abstract 1",
            "published_date": "2024-01-01",
            "updated_date": "2024-01-02",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00001",
        },
        {
            "id": "p2",
            "title": "Paper 2",
            "abstract": "Abstract 2",
            "published_date": "2024-01-03",
            "updated_date": "2024-01-04",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00002",
        },
        {
            "id": "p3",
            "title": "Paper 3",
            "abstract": "Abstract 3",
            "published_date": "2024-01-05",
            "updated_date": "2024-01-06",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "https://arxiv.org/abs/2401.00003",
        },
    ]

    conn = get_connection(tmp_db)
    for p in papers:
        upsert_paper(conn, p)

    # Insert authors: p1 and p2 share author "Author A", p2 and p3 share author "Author B"
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO authors (name) VALUES (?)", ("Author A",))
    cur.execute("INSERT OR IGNORE INTO authors (name) VALUES (?)", ("Author B",))
    cur.execute("SELECT id FROM authors WHERE name = ?", ("Author A",))
    author_a_id = cur.fetchone()[0]
    cur.execute("SELECT id FROM authors WHERE name = ?", ("Author B",))
    author_b_id = cur.fetchone()[0]

    cur.execute(
        "INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)",
        ("p1", author_a_id, 0),
    )
    cur.execute(
        "INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)",
        ("p2", author_a_id, 0),
    )
    cur.execute(
        "INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)",
        ("p2", author_b_id, 0),
    )
    cur.execute(
        "INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)",
        ("p3", author_b_id, 0),
    )

    conn.commit()
    conn.close()

    graph = build_paper_graph(tmp_db)
    assert graph.number_of_nodes() == 3
    # p1-p2 share Author A, p2-p3 share Author B
    assert graph.number_of_edges() == 2


def test_build_team_graph_with_data(tmp_db):
    """With teams linked to the same paper, build_team_graph should have nodes and edges."""
    paper = {
        "id": "p1",
        "title": "Paper 1",
        "abstract": "Abstract 1",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-02",
        "categories": "cs.AI",
        "pdf_path": None,
        "source": "arxiv",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
    }

    conn = get_connection(tmp_db)
    upsert_paper(conn, paper)

    # Insert two teams and link them to the same paper
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO teams (name) VALUES (?)", ("Team 1",))
    cur.execute("INSERT OR IGNORE INTO teams (name) VALUES (?)", ("Team 2",))
    cur.execute("SELECT id FROM teams WHERE name = ?", ("Team 1",))
    team1_id = cur.fetchone()[0]
    cur.execute("SELECT id FROM teams WHERE name = ?", ("Team 2",))
    team2_id = cur.fetchone()[0]

    cur.execute(
        "INSERT OR IGNORE INTO paper_teams (paper_id, team_id) VALUES (?, ?)",
        ("p1", team1_id),
    )
    cur.execute(
        "INSERT OR IGNORE INTO paper_teams (paper_id, team_id) VALUES (?, ?)",
        ("p1", team2_id),
    )

    conn.commit()
    conn.close()

    graph = build_team_graph(tmp_db)
    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 1


def test_export_html_creates_file(tmp_path):
    graph = nx.Graph()
    graph.add_node("n1", label="Node 1")
    graph.add_node("n2", label="Node 2")
    graph.add_edge("n1", "n2", weight=1)

    output = tmp_path / "graph.html"
    result = export_html(graph, output, title="Test Graph")

    assert result == output
    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "vis-network" in text
    assert "n1" in text or "Node 1" in text


def test_visualize_team_and_paper_views(tmp_db, tmp_path):
    paper = {
        "id": "viz_p1",
        "title": "Viz Paper",
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

    team_output = visualize(view="team", output_dir=tmp_path, db_path=tmp_db)
    assert team_output.exists()
    assert team_output.name == "graph_team.html"

    paper_output = visualize(view="paper", output_dir=tmp_path, db_path=tmp_db)
    assert paper_output.exists()
    assert paper_output.name == "graph_paper.html"
