"""CiteMap - 图谱构建与可视化模块。"""

from collections import Counter, defaultdict
from hashlib import sha1
from itertools import combinations
from pathlib import Path
from typing import Literal, Optional

import networkx as nx
from pyvis.network import Network

from .database import get_connection, init_db


# ──────────────────────────────
# 图谱构建
# ──────────────────────────────

def _short_institution_name(name: str) -> str:
    """为圆形节点生成可读的机构简称，详情中仍保留全名。"""
    cleaned = name.replace(" Inc.", "").replace(" Ltd.", "").strip()
    if len(cleaned) <= 12:
        return cleaned
    words = cleaned.replace("-", " ").split()
    stop_words = {"of", "the", "and", "for"}
    acronym = "".join(
        word[0]
        for word in words
        if word.lower() not in stop_words and word[0].isalnum()
    ).upper()
    if 2 <= len(acronym) <= 6:
        return acronym
    return cleaned[:10]

def build_team_graph(
    db_path: Optional[Path] = None,
    project_id: Optional[str] = None,
) -> nx.Graph:
    """以团队为节点，共著论文为边构建图。"""
    init_db(db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()
    G = nx.Graph()

    project_join = """
        JOIN project_papers pp ON pp.paper_id = pt.paper_id
        WHERE pp.project_id = ?
    """ if project_id else ""
    params = (project_id,) if project_id else ()

    # 只加载当前项目论文关联的团队，避免出现其他项目的孤立节点。
    cur.execute(f"""
        SELECT DISTINCT t.id, t.name, t.description, i.name AS institution
        FROM teams t
        JOIN paper_teams pt ON pt.team_id = t.id
        LEFT JOIN institutions i ON i.id = t.lead_institution_id
        {project_join}
    """, params)
    for row in cur.fetchall():
        G.add_node(
            row["id"],
            label=row["name"],
            title=row["description"] or "",
            group="team",
            institution=row["institution"],
            members=[],
            papers=[],
            paper_count=0,
        )

    team_ids = list(G.nodes)
    if team_ids:
        placeholders = ",".join("?" for _ in team_ids)
        cur.execute(f"""
            SELECT tm.team_id, a.name
            FROM team_members tm
            JOIN authors a ON a.id = tm.author_id
            WHERE tm.team_id IN ({placeholders})
            ORDER BY a.name
        """, team_ids)
        for row in cur.fetchall():
            G.nodes[row["team_id"]]["members"].append(row["name"])

    # 加载论文，作为团队之间的边（共享论文即共著）
    cur.execute(f"""
        SELECT pt.paper_id, pt.team_id, p.title, p.published_date, p.core_contribution
        FROM paper_teams pt
        JOIN papers p ON pt.paper_id = p.id
        {project_join}
    """, params)
    rows = cur.fetchall()

    paper_teams = defaultdict(list)
    for row in rows:
        paper_teams[row["paper_id"]].append({
            "team_id": row["team_id"],
            "title": row["title"],
            "date": row["published_date"],
            "contribution": row["core_contribution"],
        })

    for paper_id, teams in paper_teams.items():
        paper = {
            "id": paper_id,
            "title": teams[0]["title"],
            "date": teams[0]["date"],
        }
        for team in teams:
            if team["team_id"] in G:
                G.nodes[team["team_id"]]["papers"].append(paper)
                G.nodes[team["team_id"]]["paper_count"] += 1
        if len(teams) < 2:
            continue
        # 每对团队之间加一条边，边属性包含共享论文
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                t1, t2 = teams[i]["team_id"], teams[j]["team_id"]
                if G.has_edge(t1, t2):
                    G[t1][t2]["papers"].append(paper)
                    G[t1][t2]["weight"] += 1
                else:
                    G.add_edge(
                        t1,
                        t2,
                        papers=[paper],
                        weight=1,
                        relation_types=["paper"],
                        title="共同参与论文",
                    )

    for node_id in G.nodes:
        G.nodes[node_id]["degree"] = G.degree(node_id)
        G.nodes[node_id]["weighted_degree"] = G.degree(node_id, weight="weight")

    conn.close()
    return G


def build_team_ego_graph(
    db_path: Optional[Path] = None,
    project_id: Optional[str] = None,
) -> nx.Graph:
    """用 Louvain 从共著网络推断团队，并生成团队、论文异构图。"""
    init_db(db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()
    graph = nx.Graph()

    project_join = "JOIN project_papers pp ON pp.paper_id = p.id" if project_id else ""
    project_where = "WHERE pp.project_id = ?" if project_id else ""
    params = (project_id,) if project_id else ()
    cur.execute(f"""
        SELECT p.id, p.title, p.published_date, p.core_contribution,
               p.categories, p.arxiv_url, p.venue, p.venue_year
        FROM papers p
        {project_join}
        {project_where}
        ORDER BY p.published_date DESC, p.id
    """, params)
    papers = {row["id"]: dict(row) for row in cur.fetchall()}
    if not papers:
        conn.close()
        return graph

    author_project_join = "JOIN project_papers pp ON pp.paper_id = pa.paper_id" if project_id else ""
    author_project_where = "WHERE pp.project_id = ?" if project_id else ""
    cur.execute(f"""
        SELECT pa.paper_id, pa.author_id, pa.author_order, a.name, a.affiliation
        FROM paper_authors pa
        JOIN authors a ON a.id = pa.author_id
        {author_project_join}
        {author_project_where}
        ORDER BY pa.paper_id, pa.author_order
    """, params)
    authors_by_paper: dict[str, list[dict]] = defaultdict(list)
    author_names: dict[int, str] = {}
    for row in cur.fetchall():
        if row["paper_id"] not in papers:
            continue
        author = dict(row)
        authors_by_paper[row["paper_id"]].append(author)
        author_names[row["author_id"]] = row["name"]

    institution_project_join = "JOIN project_papers pp ON pp.paper_id = pi.paper_id" if project_id else ""
    institution_project_where = "WHERE pp.project_id = ?" if project_id else ""
    cur.execute(f"""
        SELECT pi.paper_id, i.name
        FROM paper_institutions pi
        JOIN institutions i ON i.id = pi.institution_id
        {institution_project_join}
        {institution_project_where}
    """, params)
    institutions_by_paper: dict[str, list[str]] = defaultdict(list)
    for row in cur.fetchall():
        if row["paper_id"] in papers:
            institutions_by_paper[row["paper_id"]].append(row["name"])

    coauthor_graph = nx.Graph()
    for authors in authors_by_paper.values():
        author_ids = [author["author_id"] for author in authors]
        coauthor_graph.add_nodes_from(author_ids)
        for author_a, author_b in combinations(author_ids, 2):
            if coauthor_graph.has_edge(author_a, author_b):
                coauthor_graph[author_a][author_b]["weight"] += 1
            else:
                coauthor_graph.add_edge(author_a, author_b, weight=1)

    if coauthor_graph.number_of_nodes() == 0:
        conn.close()
        return graph

    communities = nx.community.louvain_communities(
        coauthor_graph,
        weight="weight",
        resolution=1,
        seed=42,
    )
    communities = [community for community in communities if len(community) >= 2]
    author_to_team: dict[int, str] = {}

    for community in communities:
        sorted_author_ids = sorted(community)
        team_id = "inferred_team_" + sha1(
            ",".join(map(str, sorted_author_ids)).encode("utf-8")
        ).hexdigest()[:12]
        for author_id in community:
            author_to_team[author_id] = team_id

        related_paper_ids = [
            paper_id
            for paper_id, authors in authors_by_paper.items()
            if any(author["author_id"] in community for author in authors)
        ]
        institution_counts = Counter(
            institution
            for paper_id in related_paper_ids
            for institution in institutions_by_paper[paper_id]
        )
        institution = institution_counts.most_common(1)[0][0] if institution_counts else None
        representative_id = max(
            community,
            key=lambda author_id: (
                coauthor_graph.degree(author_id, weight="weight"),
                author_names.get(author_id, ""),
            ),
        )
        representative = author_names.get(representative_id, "未知作者")
        team_name = f"{institution} · {representative}" if institution else f"{representative} 协作组"
        representative_short = representative.split()[-1]
        team_label = (
            f"{_short_institution_name(institution)} · {representative_short}"
            if institution
            else f"{representative_short} 协作组"
        )
        team_papers = [
            {
                "id": paper_id,
                "title": papers[paper_id]["title"],
                "date": papers[paper_id]["published_date"],
                "venue": papers[paper_id]["venue"],
                "venue_year": papers[paper_id]["venue_year"],
            }
            for paper_id in related_paper_ids
        ]
        team_papers.sort(key=lambda paper: paper.get("date") or "", reverse=True)
        graph.add_node(
            team_id,
            label=team_label,
            title=team_name,
            group="team",
            team_type="inferred",
            confidence="medium",
            description=f"根据 {len(related_paper_ids)} 篇论文的共著关系自动推断。",
            institution=institution,
            representative_author=representative,
            members=sorted(author_names[author_id] for author_id in community),
            papers=team_papers,
            paper_count=len(team_papers),
            latest_paper_date=team_papers[0].get("date") if team_papers else None,
        )

    paper_team_ids: dict[str, set[str]] = defaultdict(set)
    for paper_id, authors in authors_by_paper.items():
        for author in authors:
            team_id = author_to_team.get(author["author_id"])
            if team_id:
                paper_team_ids[paper_id].add(team_id)

    for paper_id, team_ids in paper_team_ids.items():
        if not team_ids:
            continue
        paper = papers[paper_id]
        paper_node_id = f"paper:{paper_id}"
        graph.add_node(
            paper_node_id,
            paper_id=paper_id,
            label=paper["title"],
            title=paper["title"],
            group="paper",
            published_date=paper["published_date"],
            core_contribution=paper["core_contribution"],
            categories=paper["categories"],
            arxiv_url=paper["arxiv_url"],
            venue=paper["venue"],
            venue_year=paper["venue_year"],
            authors=[author["name"] for author in authors_by_paper[paper_id]],
            institutions=institutions_by_paper[paper_id],
        )
        for team_id in team_ids:
            graph.add_edge(
                team_id,
                paper_node_id,
                weight=1,
                relation_types=["produced"],
                title="发表论文",
            )

        for team_a, team_b in combinations(sorted(team_ids), 2):
            paper_ref = {
                "id": paper_id,
                "title": paper["title"],
                "date": paper["published_date"],
                "venue": paper["venue"],
                "venue_year": paper["venue_year"],
            }
            if graph.has_edge(team_a, team_b):
                graph[team_a][team_b]["weight"] += 1
                graph[team_a][team_b]["papers"].append(paper_ref)
            else:
                graph.add_edge(
                    team_a,
                    team_b,
                    weight=1,
                    papers=[paper_ref],
                    relation_types=["collaboration"],
                    title="跨团队合作",
                )

    for node_id in graph.nodes:
        graph.nodes[node_id]["degree"] = graph.degree(node_id)
        graph.nodes[node_id]["weighted_degree"] = graph.degree(node_id, weight="weight")

    conn.close()
    return graph


def build_paper_graph(
    db_path: Optional[Path] = None,
    project_id: Optional[str] = None,
) -> nx.Graph:
    """以论文为节点，共享作者/机构为边构建图。"""
    init_db(db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()
    G = nx.Graph()

    paper_join = "JOIN project_papers pp ON pp.paper_id = p.id" if project_id else ""
    paper_where = "WHERE pp.project_id = ?" if project_id else ""
    params = (project_id,) if project_id else ()

    # 加载论文节点及其可用于详情展示的元数据。
    cur.execute(f"""
        SELECT p.id, p.title, p.published_date, p.core_contribution,
               p.categories, p.arxiv_url, p.source, p.venue, p.venue_year,
               p.citation_count, p.reference_count, p.citation_synced_at
        FROM papers p
        {paper_join}
        {paper_where}
    """, params)
    for row in cur.fetchall():
        G.add_node(
            row["id"],
            label=row["title"][:30] + ("..." if len(row["title"]) > 30 else ""),
            title=row["title"],
            group="paper",
            published_date=row["published_date"],
            core_contribution=row["core_contribution"],
            categories=row["categories"],
            arxiv_url=row["arxiv_url"],
            source=row["source"],
            venue=row["venue"],
            venue_year=row["venue_year"],
            citation_count=row["citation_count"],
            reference_count=row["reference_count"],
            citation_synced_at=row["citation_synced_at"],
            authors=[],
            institutions=[],
        )

    paper_ids = set(G.nodes)
    authors_by_paper: dict[str, dict[int, str]] = defaultdict(dict)
    institutions_by_paper: dict[str, set[str]] = defaultdict(set)

    if paper_ids:
        author_project_join = "JOIN project_papers pp ON pp.paper_id = pa.paper_id" if project_id else ""
        author_project_where = "WHERE pp.project_id = ?" if project_id else ""
        relation_params = (project_id,) if project_id else ()
        cur.execute(f"""
            SELECT pa.paper_id, a.id, a.name
            FROM paper_authors pa
            JOIN authors a ON a.id = pa.author_id
            {author_project_join}
            {author_project_where}
        """, relation_params)
        for row in cur.fetchall():
            if row["paper_id"] in paper_ids:
                authors_by_paper[row["paper_id"]][row["id"]] = row["name"]

        institution_project_join = "JOIN project_papers pp ON pp.paper_id = pi.paper_id" if project_id else ""
        institution_project_where = "WHERE pp.project_id = ?" if project_id else ""
        cur.execute(f"""
            SELECT pi.paper_id, i.name
            FROM paper_institutions pi
            JOIN institutions i ON i.id = pi.institution_id
            {institution_project_join}
            {institution_project_where}
        """, relation_params)
        for row in cur.fetchall():
            if row["paper_id"] in paper_ids:
                institutions_by_paper[row["paper_id"]].add(row["name"])

    for paper_id in paper_ids:
        G.nodes[paper_id]["authors"] = sorted(authors_by_paper[paper_id].values())
        G.nodes[paper_id]["institutions"] = sorted(institutions_by_paper[paper_id])

    # 倒排关系后组合论文对，避免多次 SQL 自连接，并保留可解释的关系证据。
    papers_by_author: dict[int, set[str]] = defaultdict(set)
    author_names: dict[int, str] = {}
    papers_by_institution: dict[str, set[str]] = defaultdict(set)
    for paper_id, authors in authors_by_paper.items():
        for author_id, author_name in authors.items():
            papers_by_author[author_id].add(paper_id)
            author_names[author_id] = author_name
    for paper_id, institutions in institutions_by_paper.items():
        for institution in institutions:
            papers_by_institution[institution].add(paper_id)

    edge_evidence: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"authors": set(), "institutions": set()}
    )
    for author_id, related_papers in papers_by_author.items():
        for p1, p2 in combinations(sorted(related_papers), 2):
            edge_evidence[(p1, p2)]["authors"].add(author_names[author_id])
    for institution, related_papers in papers_by_institution.items():
        for p1, p2 in combinations(sorted(related_papers), 2):
            edge_evidence[(p1, p2)]["institutions"].add(institution)

    for (p1, p2), evidence in edge_evidence.items():
        shared_authors = sorted(evidence["authors"])
        shared_institutions = sorted(evidence["institutions"])
        relation_types = []
        if shared_authors:
            relation_types.append("author")
        if shared_institutions:
            relation_types.append("institution")
        weight = len(shared_authors) + len(shared_institutions)
        G.add_edge(
            p1,
            p2,
            weight=weight,
            relation_types=relation_types,
            shared_authors=shared_authors,
            shared_institutions=shared_institutions,
            title="、".join(
                part for part in (
                    f"{len(shared_authors)} 位共享作者" if shared_authors else "",
                    f"{len(shared_institutions)} 个共享机构" if shared_institutions else "",
                ) if part
            ),
        )

    for node_id in G.nodes:
        G.nodes[node_id]["degree"] = G.degree(node_id)
        G.nodes[node_id]["weighted_degree"] = G.degree(node_id, weight="weight")

    conn.close()
    return G


# ──────────────────────────────
# 可视化导出
# ──────────────────────────────

def export_html(graph: nx.Graph, output_path: Path, height: str = "800px",
                title: str = "论文图谱") -> Path:
    """导出 PyVis 交互式 HTML。"""
    net = Network(height=height, width="100%", directed=False, notebook=False)
    net.from_nx(graph)

    # 设置物理引擎让布局更稳定
    net.set_options("""
    {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "centralGravity": 0.01,
          "springLength": 200,
          "springConstant": 0.08
        },
        "maxVelocity": 50,
        "solver": "forceAtlas2Based",
        "timestep": 0.35,
        "stabilization": {
          "enabled": true,
          "iterations": 150
        }
      }
    }
    """)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    net.save_graph(str(output_path))
    return output_path


def visualize(view: Literal["team", "paper"] = "team", output_dir: Path = Path("_output"),
              db_path: Optional[Path] = None) -> Path:
    """一键生成指定视图的 HTML 可视化。"""
    if view == "team":
        graph = build_team_graph(db_path)
    else:
        graph = build_paper_graph(db_path)

    output_path = output_dir / f"graph_{view}.html"
    return export_html(graph, output_path, title=f"论文图谱 - {view}视图")
