"""CiteMap - 聊天 Agent 可用工具集合。

所有工具函数都接收并返回 JSON-serializable 的字典，便于 OpenAI function calling 使用。
"""

from __future__ import annotations

import json
import os
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any, Optional

from .database import (
    add_paper_to_project,
    get_connection,
    get_paper,
    get_paper_tags,
    list_chat_sessions as db_list_chat_sessions,
    list_papers,
)
from .ingest import ingest_arxiv_id, search_arxiv_only, _download_arxiv_pdf
from .annotate import annotate_paper
from .notes import get_note

# 复用 main.py 里的数据目录约定
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_PATH = DATA_DIR / "papers.db"
ACTIVE_PROJECT_ID: ContextVar[Optional[str]] = ContextVar("active_project_id", default=None)


def set_active_project(project_id: Optional[str]) -> Token:
    return ACTIVE_PROJECT_ID.set(project_id)


def reset_active_project(token: Token) -> None:
    ACTIVE_PROJECT_ID.reset(token)


def _paper_in_scope(paper_id: str) -> bool:
    project_id = ACTIVE_PROJECT_ID.get()
    if not project_id:
        return True
    conn = get_connection(DB_PATH)
    try:
        row = conn.execute(
            "SELECT 1 FROM project_papers WHERE project_id = ? AND paper_id = ?",
            (project_id, paper_id),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _paper_to_dict(row: Any) -> dict:
    """把 DataFrame row / sqlite row 转成干净字典。"""
    if hasattr(row, "to_dict"):
        d = row.to_dict()
    else:
        d = dict(row)
    for k, v in list(d.items()):
        if isinstance(v, float) and v != v:  # NaN
            d[k] = None
    return d


# ──────────────────────────────
# 工具 schema 定义（供 LLM 使用）
# ──────────────────────────────

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_arxiv",
            "description": "在 arXiv 上搜索与给定主题相关的论文，返回论文标题、摘要、ID 等元数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或主题，例如 'transformer protein folding'",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最多返回多少条结果，默认 5 条",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ingest_arxiv_paper",
            "description": "根据 arXiv ID 将论文入库到本地知识库。入库后可继续查询、标注或下载 PDF。",
            "parameters": {
                "type": "object",
                "properties": {
                    "arxiv_id": {
                        "type": "string",
                        "description": "arXiv ID，例如 '2402.09199'。不要包含 'arxiv_' 前缀。",
                    },
                    "download_pdf": {
                        "type": "boolean",
                        "description": "是否同时下载 PDF 原文，默认 False",
                        "default": False,
                    },
                },
                "required": ["arxiv_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_local_papers",
            "description": "列出本地论文库中已入库的论文，支持按来源筛选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "来源筛选，例如 'arxiv' 或 'pdf'。不填则返回全部。",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回多少条，默认 20",
                        "default": 20,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_local_papers",
            "description": "在本地论文库的标题和摘要中搜索关键词。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "string",
                        "description": "搜索关键词，例如 'large language model reasoning'",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回多少条，默认 5",
                        "default": 5,
                    },
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_paper_details",
            "description": "获取本地知识库中某篇论文的完整详情，包括标题、摘要、作者、核心贡献、PDF/笔记路径等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "string",
                        "description": "本地论文 ID，例如 'arxiv_2402.09199' 或 'pdf_xxx'。",
                    },
                },
                "required": ["paper_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "annotate_paper_tool",
            "description": "对本地论文生成 TLDR、核心贡献、领域、结构化标签，补充研究团队关系。结果写回数据库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "string",
                        "description": "本地论文 ID",
                    },
                },
                "required": ["paper_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "download_paper_pdf",
            "description": "为本地已入库的 arXiv 论文下载 PDF 原文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "string",
                        "description": "本地论文 ID，例如 'arxiv_2402.09199'",
                    },
                },
                "required": ["paper_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_paper_notes",
            "description": "获取某篇论文关联的 Markdown 笔记内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "string",
                        "description": "本地论文 ID",
                    },
                },
                "required": ["paper_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_graph_summary",
            "description": "获取本地论文库的知识图谱统计摘要：团队数量、论文数量、主要合作关系等。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


# ──────────────────────────────
# 工具执行函数
# ──────────────────────────────

def search_arxiv(query: str, max_results: int = 5) -> dict[str, Any]:
    try:
        results = search_arxiv_only(query, max_results=max_results)
        papers = [
            {
                "id": r["id"],
                "title": r["title"],
                "abstract": r.get("abstract", "")[:400],
                "published_date": r.get("published_date", ""),
                "categories": r.get("categories", ""),
                "arxiv_url": r.get("arxiv_url", ""),
            }
            for r in results
        ]
        return {
            "success": True,
            "title": f"找到 {len(papers)} 篇论文",
            "summary": f"关键词: {query}",
            "count": len(papers),
            "papers": papers,
        }
    except Exception as e:
        return {"success": False, "title": "搜索失败", "summary": str(e), "error": str(e)}


def ingest_arxiv_paper(arxiv_id: str, download_pdf: bool = False) -> dict[str, Any]:
    try:
        paper_id = ingest_arxiv_id(
            arxiv_id.strip(),
            DB_PATH,
            download_pdf=download_pdf,
            pdf_dir=DATA_DIR / "pdfs",
        )
        project_id = ACTIVE_PROJECT_ID.get()
        if project_id:
            conn = get_connection(DB_PATH)
            try:
                add_paper_to_project(conn, project_id, paper_id)
            finally:
                conn.close()
        return {
            "success": True,
            "title": "论文已入库",
            "summary": paper_id,
            "paper_id": paper_id,
            "downloaded_pdf": download_pdf,
        }
    except Exception as e:
        return {"success": False, "title": "入库失败", "summary": str(e), "error": str(e)}


def list_local_papers(source: Optional[str] = None, limit: int = 20) -> dict[str, Any]:
    try:
        df = list_papers(DB_PATH, source=source, project_id=ACTIVE_PROJECT_ID.get())
        papers = [_paper_to_dict(row) for _, row in df.head(limit).iterrows()]
        source_desc = f"来源={source}" if source else "全部来源"
        return {
            "success": True,
            "title": f"本地论文库有 {len(papers)} 篇",
            "summary": source_desc,
            "count": len(papers),
            "papers": papers,
        }
    except Exception as e:
        return {"success": False, "title": "查询失败", "summary": str(e), "error": str(e)}


def search_local_papers(keywords: str, limit: int = 5) -> dict[str, Any]:
    try:
        df = list_papers(DB_PATH, project_id=ACTIVE_PROJECT_ID.get())
        matched = df[
            df["title"].str.contains(keywords, case=False, na=False, regex=False)
            | df["abstract"].str.contains(keywords, case=False, na=False, regex=False)
        ]
        papers = [_paper_to_dict(row) for _, row in matched.head(limit).iterrows()]
        return {
            "success": True,
            "title": f"找到 {len(papers)} 篇匹配",
            "summary": f"关键词: {keywords}",
            "count": len(papers),
            "papers": papers,
        }
    except Exception as e:
        return {"success": False, "title": "搜索失败", "summary": str(e), "error": str(e)}


def get_paper_details(paper_id: str) -> dict[str, Any]:
    try:
        if not _paper_in_scope(paper_id):
            return {"success": False, "title": "论文不在当前项目", "summary": f"ID: {paper_id}", "error": f"论文不在当前项目: {paper_id}"}
        conn = get_connection(DB_PATH)
        paper = get_paper(conn, paper_id)
        tags = get_paper_tags(conn, paper_id) if paper else []
        conn.close()
        if not paper:
            return {"success": False, "title": "论文不存在", "summary": f"ID: {paper_id}", "error": f"论文不存在: {paper_id}"}

        # 补充作者信息
        conn = get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT a.name, a.affiliation
            FROM paper_authors pa
            JOIN authors a ON pa.author_id = a.id
            WHERE pa.paper_id = ?
            ORDER BY pa.author_order
            """,
            (paper_id,),
        )
        authors = [{"name": r["name"], "affiliation": r["affiliation"]} for r in cur.fetchall()]
        conn.close()

        result = _paper_to_dict(paper)
        result["authors"] = authors
        try:
            result["subfields"] = json.loads(result.get("subfields") or "[]")
        except (TypeError, json.JSONDecodeError):
            result["subfields"] = []
        result["tags"] = tags
        author_names = ", ".join(a["name"] for a in authors[:3])
        author_suffix = "..." if len(authors) > 3 else ""
        return {
            "success": True,
            "title": result.get("title", paper_id),
            "summary": f"作者: {author_names}{author_suffix}",
            "paper": result,
        }
    except Exception as e:
        return {"success": False, "title": "查询失败", "summary": str(e), "error": str(e)}


def annotate_paper_tool(paper_id: str) -> dict[str, Any]:
    try:
        if not _paper_in_scope(paper_id):
            return {"success": False, "title": "标注失败", "summary": "论文不在当前项目", "error": f"论文不在当前项目: {paper_id}"}
        result = annotate_paper(paper_id, db_path=DB_PATH)
        summary = result.get("tldr", "") or result.get("core_contribution", "") or "无标注结果"
        if len(summary) > 80:
            summary = summary[:77] + "..."
        return {
            "success": True,
            "title": "标注完成",
            "summary": summary,
            "result": result,
        }
    except Exception as e:
        return {"success": False, "title": "标注失败", "summary": str(e), "error": str(e)}


def download_paper_pdf(paper_id: str) -> dict[str, Any]:
    try:
        if not _paper_in_scope(paper_id):
            return {"success": False, "title": "下载失败", "summary": "论文不在当前项目", "error": f"论文不在当前项目: {paper_id}"}
        if not paper_id.startswith("arxiv_"):
            return {"success": False, "title": "下载失败", "summary": "仅支持 arXiv 论文下载 PDF", "error": "仅支持 arXiv 论文下载 PDF"}
        arxiv_id = paper_id.replace("arxiv_", "")

        import arxiv as arxiv_lib

        client = arxiv_lib.Client(page_size=1, delay_seconds=1)
        search = arxiv_lib.Search(id_list=[arxiv_id])
        results = list(client.results(search))
        if not results:
            return {"success": False, "title": "下载失败", "summary": "论文不存在", "error": "论文不存在"}

        pdf_dir = DATA_DIR / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_file = pdf_dir / f"{paper_id}.pdf"
        if not pdf_file.exists():
            _download_arxiv_pdf(results[0], pdf_file)

        # 更新数据库
        conn = get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "UPDATE papers SET pdf_path = ? WHERE id = ?",
            (str(pdf_file.resolve()), paper_id),
        )
        conn.commit()
        conn.close()

        return {
            "success": True,
            "title": "PDF 已下载",
            "summary": str(pdf_file.resolve()),
            "pdf_path": str(pdf_file.resolve()),
        }
    except Exception as e:
        return {"success": False, "title": "下载失败", "summary": str(e), "error": str(e)}


def get_paper_notes(paper_id: str) -> dict[str, Any]:
    try:
        if not _paper_in_scope(paper_id):
            return {"success": False, "title": "读取失败", "summary": "论文不在当前项目", "error": f"论文不在当前项目: {paper_id}"}
        note = get_note(DB_PATH, paper_id)
        if not note:
            return {"success": False, "title": "没有笔记", "summary": f"论文 {paper_id} 没有笔记", "error": f"论文 {paper_id} 没有笔记"}
        content_preview = (note.get("content", "") or "")[:80]
        if len(note.get("content", "") or "") > 80:
            content_preview += "..."
        return {
            "success": True,
            "title": "笔记内容",
            "summary": content_preview or "空笔记",
            "note": note,
        }
    except Exception as e:
        return {"success": False, "title": "查询失败", "summary": str(e), "error": str(e)}


def get_graph_summary() -> dict[str, Any]:
    try:
        from .graph import build_team_graph, build_paper_graph

        project_id = ACTIVE_PROJECT_ID.get()
        team_graph = build_team_graph(DB_PATH, project_id=project_id)
        paper_graph = build_paper_graph(DB_PATH, project_id=project_id)

        # 团队图中节点是团队，边是共著关系
        top_teams = sorted(
            [(n, team_graph.nodes[n].get("paper_count", 0)) for n in team_graph.nodes()],
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        return {
            "success": True,
            "title": "图谱统计",
            "summary": f"{len(team_graph.nodes())} 个团队, {len(paper_graph.edges())} 条论文连接",
            "team_count": len(team_graph.nodes()),
            "team_collaboration_count": len(team_graph.edges()),
            "paper_connection_count": len(paper_graph.edges()),
            "top_teams": [{"name": name, "paper_count": count} for name, count in top_teams],
        }
    except Exception as e:
        return {"success": False, "title": "查询失败", "summary": str(e), "error": str(e)}


# 工具名 -> 执行函数 的映射表
TOOL_DISPATCH: dict[str, Any] = {
    "search_arxiv": search_arxiv,
    "ingest_arxiv_paper": ingest_arxiv_paper,
    "list_local_papers": list_local_papers,
    "search_local_papers": search_local_papers,
    "get_paper_details": get_paper_details,
    "annotate_paper_tool": annotate_paper_tool,
    "download_paper_pdf": download_paper_pdf,
    "get_paper_notes": get_paper_notes,
    "get_graph_summary": get_graph_summary,
}
