"""CiteMap - Markdown 笔记管理模块。"""

import ast
import json
import re
from pathlib import Path
from typing import Optional

from .database import get_connection, get_paper, get_paper_tags, init_db

NOTES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "notes"
NOTES_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────
# Frontmatter 解析（轻量手动解析，避免引入新依赖）
# ──────────────────────────────

def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 Markdown frontmatter，返回 (metadata_dict, body_text)。"""
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    fm_text = content[3:end].strip()
    body = content[end + 3:].lstrip("\n")

    metadata = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if not value:
            continue

        # 尝试解析 Python/YAML 列表/字典字面量
        if value.startswith("[") and value.endswith("]"):
            try:
                value = ast.literal_eval(value)
            except Exception:
                pass

        metadata[key] = value

    return metadata, body


def _serialize_frontmatter(metadata: dict) -> str:
    """将元数据字典序列化为 frontmatter 文本块。"""
    lines = []
    for key, value in metadata.items():
        if isinstance(value, (list, dict)):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _relative_pdf_path(paper_id: str, pdf_path: Optional[str]) -> str:
    """生成相对 PDF 路径（../pdfs/xxx.pdf）。"""
    if not pdf_path:
        return ""
    pdf = Path(pdf_path)
    # 假设 notes 目录在 data/notes，pdfs 在 data/pdfs
    rel = Path("..") / "pdfs" / f"{paper_id}.pdf"
    return str(rel)


def _get_note_updated_at(md_path: Optional[str]) -> str:
    """获取笔记文件的修改时间，返回 ISO 格式字符串。"""
    if not md_path:
        return ""
    path = Path(md_path)
    if not path.exists():
        return ""
    try:
        import datetime
        ts = path.stat().st_mtime
        return datetime.datetime.fromtimestamp(ts).isoformat()
    except Exception:
        return ""


# ──────────────────────────────
# 核心 API
# ──────────────────────────────

def list_notes(
    db_path: Optional[Path] = None,
    project_id: Optional[str] = None,
) -> list[dict]:
    """列出所有笔记（path, paper_id, title）。"""
    init_db(db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()

    project_join = "JOIN project_papers pp ON pp.paper_id = p.id" if project_id else ""
    project_filter = "AND pp.project_id = ?" if project_id else ""
    params = (project_id,) if project_id else ()
    cur.execute(f"""
        SELECT DISTINCT p.id AS paper_id, p.title, p.md_path
        FROM papers p
        {project_join}
        WHERE p.md_path IS NOT NULL AND p.md_path != ''
          AND p.note_edited_at IS NOT NULL
        {project_filter}
        ORDER BY p.created_at DESC
    """, params)
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "paper_id": row["paper_id"],
            "title": row["title"],
            "path": row["md_path"],
            "updated_at": _get_note_updated_at(row["md_path"]),
        }
        for row in rows
    ]


def get_note(db_path: Optional[Path] = None, paper_id: Optional[str] = None) -> Optional[dict]:
    """读取指定论文的 Markdown 笔记内容，返回 {metadata, content}。"""
    init_db(db_path)
    conn = get_connection(db_path)
    paper = get_paper(conn, paper_id)
    conn.close()

    if not paper or not paper.get("md_path"):
        return None

    note_path = Path(paper["md_path"])
    if not note_path.exists():
        return None

    raw = note_path.read_text(encoding="utf-8")
    metadata, body = _parse_frontmatter(raw)

    return {
        "paper_id": paper_id,
        "path": str(note_path.resolve()),
        "note_edited_at": paper.get("note_edited_at"),
        "metadata": metadata,
        "content": raw,
        "body": body,
    }


def save_note(db_path: Optional[Path] = None, paper_id: Optional[str] = None,
              content: str = "", mark_edited: bool = True) -> dict:
    """保存笔记内容到文件 + 更新数据库中的 md_path。"""
    init_db(db_path)
    conn = get_connection(db_path)
    paper = get_paper(conn, paper_id)
    conn.close()

    if not paper:
        raise ValueError(f"论文不存在: {paper_id}")

    note_path = NOTES_DIR / f"{paper_id}.md"
    note_path.write_text(content, encoding="utf-8")

    # 更新数据库
    conn = get_connection(db_path)
    cur = conn.cursor()
    if mark_edited:
        cur.execute(
            "UPDATE papers SET md_path = ?, note_edited_at = CURRENT_TIMESTAMP WHERE id = ?",
            (str(note_path.resolve()), paper_id),
        )
    else:
        cur.execute(
            "UPDATE papers SET md_path = ? WHERE id = ?",
            (str(note_path.resolve()), paper_id),
        )
    conn.commit()
    conn.close()

    return {"paper_id": paper_id, "path": str(note_path.resolve())}


def create_note_template(db_path: Optional[Path] = None, paper_id: Optional[str] = None,
                         paper_data: Optional[dict] = None) -> dict:
    """根据论文数据生成 Markdown 笔记模板并保存。"""
    init_db(db_path)
    conn = get_connection(db_path)

    if not paper_data:
        paper = get_paper(conn, paper_id)
        if not paper:
            conn.close()
            raise ValueError(f"论文不存在: {paper_id}")
        paper_data = paper

    tags = get_paper_tags(conn, paper_id) if paper_id else []
    conn.close()

    # 解析作者列表
    authors_raw = _load_authors(db_path, paper_id)

    # 构造 frontmatter
    arxiv_num = paper_id.replace("arxiv_", "") if paper_id.startswith("arxiv_") else ""
    pdf_rel = _relative_pdf_path(paper_id, paper_data.get("pdf_path"))

    raw_subfields = paper_data.get("subfields") or []
    if isinstance(raw_subfields, str):
        try:
            raw_subfields = json.loads(raw_subfields)
        except json.JSONDecodeError:
            raw_subfields = []

    fm = {
        "title": paper_data.get("title", ""),
        "authors": authors_raw,
        "published": paper_data.get("published_date", ""),
        "categories": [c.strip() for c in paper_data.get("categories", "").split(",") if c.strip()],
        "domain": paper_data.get("primary_domain", ""),
        "subfields": raw_subfields if isinstance(raw_subfields, list) else [],
        "tags": [tag["name"] for tag in tags],
    }
    if arxiv_num:
        fm["arxiv"] = arxiv_num
    if pdf_rel:
        fm["pdf"] = pdf_rel

    # 构造模板内容
    fm_block = _serialize_frontmatter(fm)
    body = f"""# {paper_data.get('title', '未命名笔记')}

## TLDR
{paper_data.get('tldr', '待标注...') or '待标注...'}

## 核心贡献
{paper_data.get('core_contribution', '待标注...') or '待标注...'}

## 摘要
{paper_data.get('abstract', '')}

## 个人笔记
- 

## 相关团队
- 
"""

    content = f"---\n{fm_block}\n---\n{body}"

    # 模板只是编辑草稿，只有用户保存后才计为正式笔记。
    result = save_note(db_path, paper_id, content, mark_edited=False)
    result["content"] = content
    return result


def delete_note(db_path: Optional[Path] = None, paper_id: Optional[str] = None) -> dict:
    """删除笔记文件和数据库记录。"""
    init_db(db_path)
    conn = get_connection(db_path)
    paper = get_paper(conn, paper_id)
    conn.close()

    if not paper:
        raise ValueError(f"论文不存在: {paper_id}")

    note_path = Path(paper["md_path"]) if paper.get("md_path") else NOTES_DIR / f"{paper_id}.md"

    if note_path.exists():
        note_path.unlink()

    # 清空数据库中的笔记状态
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "UPDATE papers SET md_path = ?, note_edited_at = ? WHERE id = ?",
        (None, None, paper_id),
    )
    conn.commit()
    conn.close()

    return {"paper_id": paper_id, "deleted": True}


# ──────────────────────────────
# 内部辅助
# ──────────────────────────────

def _load_authors(db_path: Optional[Path], paper_id: Optional[str]) -> list[list[str]]:
    """从数据库加载作者及其机构，返回 [["作者名", "机构名"], ...]。"""
    init_db(db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT a.name, a.affiliation
        FROM paper_authors pa
        JOIN authors a ON pa.author_id = a.id
        WHERE pa.paper_id = ?
        ORDER BY pa.author_order
    """, (paper_id,))

    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        if row["affiliation"]:
            result.append([row["name"], row["affiliation"]])
        else:
            result.append([row["name"]])
    return result
