"""CiteMap - 图谱构建与可视化模块。"""

from pathlib import Path
from typing import Literal, Optional

import networkx as nx
from pyvis.network import Network

from .database import get_connection, init_db


# ──────────────────────────────
# 图谱构建
# ──────────────────────────────

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
        SELECT DISTINCT t.id, t.name, t.description
        FROM teams t
        JOIN paper_teams pt ON pt.team_id = t.id
        {project_join}
    """, params)
    for row in cur.fetchall():
        G.add_node(row["id"], label=row["name"], title=row["description"] or "", group="team")

    # 加载论文，作为团队之间的边（共享论文即共著）
    cur.execute(f"""
        SELECT pt.paper_id, pt.team_id, p.title, p.published_date, p.core_contribution
        FROM paper_teams pt
        JOIN papers p ON pt.paper_id = p.id
        {project_join}
    """, params)
    rows = cur.fetchall()

    # 找出共享同一论文的团队对
    from collections import defaultdict
    paper_teams = defaultdict(list)
    for row in rows:
        paper_teams[row["paper_id"]].append({
            "team_id": row["team_id"],
            "title": row["title"],
            "date": row["published_date"],
            "contribution": row["core_contribution"],
        })

    for paper_id, teams in paper_teams.items():
        if len(teams) < 2:
            continue
        # 每对团队之间加一条边，边属性包含共享论文
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                t1, t2 = teams[i]["team_id"], teams[j]["team_id"]
                if G.has_edge(t1, t2):
                    G[t1][t2]["papers"].append({
                        "id": paper_id,
                        "title": teams[i]["title"],
                        "date": teams[i]["date"],
                    })
                else:
                    G.add_edge(t1, t2, papers=[{
                        "id": paper_id,
                        "title": teams[i]["title"],
                        "date": teams[i]["date"],
                    }])

    conn.close()
    return G


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

    # 加载论文节点
    cur.execute(f"""
        SELECT p.id, p.title, p.published_date, p.core_contribution, p.categories
        FROM papers p
        {paper_join}
        {paper_where}
    """, params)
    for row in cur.fetchall():
        G.add_node(
            row["id"],
            label=row["title"][:30] + ("..." if len(row["title"]) > 30 else ""),
            title=f"{row['title']}\n\n{row['core_contribution'] or ''}\n\n{row['categories'] or ''}",
            group="paper",
        )

    # 共享作者的论文之间加边
    project_filter = """
        JOIN project_papers pp1 ON pp1.paper_id = pa1.paper_id
        JOIN project_papers pp2 ON pp2.paper_id = pa2.paper_id
        WHERE pp1.project_id = ? AND pp2.project_id = ?
    """ if project_id else ""
    edge_params = (project_id, project_id) if project_id else ()
    cur.execute(f"""
        SELECT pa1.paper_id AS p1, pa2.paper_id AS p2
        FROM paper_authors pa1
        JOIN paper_authors pa2 ON pa1.author_id = pa2.author_id AND pa1.paper_id < pa2.paper_id
        {project_filter}
    """, edge_params)
    for row in cur.fetchall():
        if G.has_edge(row["p1"], row["p2"]):
            G[row["p1"]][row["p2"]]["weight"] += 1
        else:
            G.add_edge(row["p1"], row["p2"], weight=1, title="共享作者")

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
