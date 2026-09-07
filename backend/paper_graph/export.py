"""CiteMap - Markdown 导出模块。"""

from pathlib import Path
from typing import Optional

import pandas as pd

from .database import get_connection, init_db, list_papers


def export_markdown(output_path: Path, db_path: Optional[Path] = None,
                    title: str = "论文图谱") -> Path:
    """导出 Markdown 格式的论文图谱，对齐用户现有模板。"""
    init_db(db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()

    lines = [f"# {title}", "", f"> 自动生成于 {(Path(__file__).resolve().parent.parent.parent / 'data' / 'papers.db')}", ""]

    # ── 团队视角 ──
    cur.execute("""
        SELECT t.id, t.name, t.description, i.name AS institution
        FROM teams t
        LEFT JOIN institutions i ON t.lead_institution_id = i.id
        ORDER BY t.name
    """)
    teams = cur.fetchall()

    if teams:
        lines.append("---")
        lines.append("")
        lines.append("## 研究团队")
        lines.append("")

        for team in teams:
            lines.append(f"### {team['name']}")
            lines.append("")
            if team["institution"]:
                lines.append(f"**所属机构**：{team['institution']}")
                lines.append("")
            if team["description"]:
                lines.append(team["description"])
                lines.append("")

            # 该团队的代表论文
            cur.execute("""
                SELECT p.id, p.title, p.published_date, p.categories, p.tldr, p.core_contribution, p.arxiv_url
                FROM papers p
                JOIN paper_teams pt ON p.id = pt.paper_id
                WHERE pt.team_id = ?
                ORDER BY p.published_date DESC
            """, (team["id"],))
            papers = cur.fetchall()

            if papers:
                lines.append("**代表论文**")
                lines.append("")
                lines.append("| 论文 | 来源 | 年份 | TLDR | 核心贡献 |")
                lines.append("|------|------|------|------|---------|")
                for p in papers:
                    title_short = (p["title"][:50] + "...") if len(p["title"]) > 50 else p["title"]
                    year = p["published_date"][:4] if p["published_date"] else "?"
                    contribution = p["core_contribution"] or "—"
                    tldr = (p["tldr"] or "—").replace("|", "\\|")
                    link = f"[{title_short}]({p['arxiv_url']})" if p["arxiv_url"] else title_short
                    lines.append(f"| {link} | {p['categories'] or 'local'} | {year} | {tldr} | {contribution} |")
                lines.append("")

    # ── 论文视角 ──
    df = list_papers(db_path)
    lines.append("---")
    lines.append("")
    lines.append("## 论文清单")
    lines.append("")
    lines.append(f"**总计**：{len(df)} 篇")
    lines.append("")
    lines.append("| # | 标题 | 来源 | 年份 | TLDR | 核心贡献 |")
    lines.append("|---|------|------|------|------|---------|")
    for idx, row in df.iterrows():
        title_short = (row["title"][:50] + "...") if len(row["title"]) > 50 else row["title"]
        year = str(row["published_date"])[:4] if row["published_date"] else "?"
        contribution = str(row["core_contribution"]) if pd.notna(row["core_contribution"]) else "—"
        tldr = str(row["tldr"]).replace("|", "\\|") if pd.notna(row["tldr"]) else "—"
        source = "arXiv" if row["source"] == "arxiv" else "本地"
        link = f"[{title_short}]({row['arxiv_url']})" if row["arxiv_url"] else title_short
        lines.append(f"| {idx + 1} | {link} | {source} | {year} | {tldr} | {contribution} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*本图谱由 CiteMap 自动生成*")
    lines.append("")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    conn.close()
    return output_path
