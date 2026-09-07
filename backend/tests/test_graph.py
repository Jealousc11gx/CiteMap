"""Tests for graph module."""

from pathlib import Path

import networkx as nx
import pytest

from paper_graph.graph import (
    build_paper_graph,
    build_team_ego_graph,
    build_team_graph,
    export_html,
    visualize,
)
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
    assert graph["p1"]["p2"]["relation_types"] == ["author"]
    assert graph["p1"]["p2"]["shared_authors"] == ["Author A"]
    assert graph.nodes["p2"]["degree"] == 2
    assert graph.nodes["p2"]["weighted_degree"] == 2


def test_build_paper_graph_combines_author_and_institution_evidence(tmp_db):
    papers = [
        {
            "id": paper_id,
            "title": title,
            "abstract": "Abstract",
            "published_date": "2025-01-01",
            "updated_date": "2025-01-02",
            "categories": "cs.LG",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": f"https://arxiv.org/abs/{paper_id}",
        }
        for paper_id, title in (("p1", "First Paper"), ("p2", "Second Paper"))
    ]
    conn = get_connection(tmp_db)
    for paper in papers:
        upsert_paper(conn, paper)
    conn.execute("INSERT INTO authors (name) VALUES (?)", ("Shared Author",))
    author_id = conn.execute("SELECT id FROM authors WHERE name = ?", ("Shared Author",)).fetchone()[0]
    conn.execute("INSERT INTO institutions (name) VALUES (?)", ("Shared Lab",))
    institution_id = conn.execute("SELECT id FROM institutions WHERE name = ?", ("Shared Lab",)).fetchone()[0]
    for paper_id in ("p1", "p2"):
        conn.execute(
            "INSERT INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, 0)",
            (paper_id, author_id),
        )
        conn.execute(
            "INSERT INTO paper_institutions (paper_id, institution_id) VALUES (?, ?)",
            (paper_id, institution_id),
        )
    conn.commit()
    conn.close()

    graph = build_paper_graph(tmp_db)

    assert graph["p1"]["p2"]["weight"] == 2
    assert graph["p1"]["p2"]["relation_types"] == ["author", "institution"]
    assert graph["p1"]["p2"]["shared_authors"] == ["Shared Author"]
    assert graph["p1"]["p2"]["shared_institutions"] == ["Shared Lab"]
    assert graph.nodes["p1"]["authors"] == ["Shared Author"]
    assert graph.nodes["p1"]["institutions"] == ["Shared Lab"]


def test_build_paper_graph_does_not_merge_authors_with_same_name(tmp_db):
    conn = get_connection(tmp_db)
    for paper_id in ("p1", "p2"):
        upsert_paper(conn, {
            "id": paper_id,
            "title": paper_id,
            "abstract": "",
            "published_date": "2025-01-01",
            "updated_date": "2025-01-01",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "",
        })
    conn.execute("INSERT INTO authors (name, affiliation) VALUES (?, ?)", ("Alex Lee", "Lab A"))
    conn.execute("INSERT INTO authors (name, affiliation) VALUES (?, ?)", ("Alex Lee", "Lab B"))
    author_ids = [row[0] for row in conn.execute("SELECT id FROM authors WHERE name = ? ORDER BY id", ("Alex Lee",)).fetchall()]
    conn.execute("INSERT INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, 0)", ("p1", author_ids[0]))
    conn.execute("INSERT INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, 0)", ("p2", author_ids[1]))
    conn.commit()
    conn.close()

    graph = build_paper_graph(tmp_db)

    assert graph.number_of_edges() == 0


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
    assert graph[team1_id][team2_id]["weight"] == 1
    assert graph[team1_id][team2_id]["papers"][0]["id"] == "p1"
    assert graph.nodes[team1_id]["paper_count"] == 1


def test_build_team_ego_graph_infers_communities_and_paper_nodes(tmp_db):
    conn = get_connection(tmp_db)
    for paper_id, title in (("p1", "Graph Paper"), ("p2", "Vision Paper")):
        upsert_paper(conn, {
            "id": paper_id,
            "title": title,
            "abstract": "",
            "published_date": "2025-01-01",
            "updated_date": "2025-01-01",
            "categories": "cs.AI",
            "pdf_path": None,
            "source": "arxiv",
            "arxiv_url": "",
        })
    for name in ("Alice", "Bob", "Carol", "Dan"):
        conn.execute("INSERT INTO authors (name) VALUES (?)", (name,))
    author_ids = {
        row["name"]: row["id"]
        for row in conn.execute("SELECT id, name FROM authors").fetchall()
    }
    for paper_id, names in (("p1", ("Alice", "Bob")), ("p2", ("Carol", "Dan"))):
        for order, name in enumerate(names):
            conn.execute(
                "INSERT INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)",
                (paper_id, author_ids[name], order),
            )
    conn.commit()
    conn.close()

    graph = build_team_ego_graph(tmp_db)

    team_nodes = [data for _, data in graph.nodes(data=True) if data["group"] == "team"]
    paper_nodes = [node_id for node_id, data in graph.nodes(data=True) if data["group"] == "paper"]
    assert len(team_nodes) == 2
    assert set(paper_nodes) == {"paper:p1", "paper:p2"}
    assert all(team["team_type"] == "inferred" for team in team_nodes)
    assert all(len(team["members"]) == 2 for team in team_nodes)
    assert all(team["paper_count"] == 1 for team in team_nodes)
    assert all(
        edge["relation_types"] == ["produced"]
        for _, _, edge in graph.edges(data=True)
    )


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
