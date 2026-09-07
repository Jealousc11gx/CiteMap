"""CiteMap - 智能标注模块。"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import OpenAI

from .database import get_connection, get_paper, list_papers
from .ingest import enrich_paper_metadata_from_pdf


class AnnotationError(RuntimeError):
    """可返回给 API 的标注业务错误。"""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


# ──────────────────────────────
# LLM 客户端
# ──────────────────────────────

def get_client(api_key: Optional[str] = None, base_url: Optional[str] = None) -> OpenAI:
    """获取 OpenAI 兼容客户端。优先使用传入参数，否则读取环境变量。"""
    api_key = api_key or os.getenv("LLM_API_KEY", "dummy")
    base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.stepfun.com/step_plan/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def get_default_model() -> str:
    """获取默认模型名称。"""
    return os.getenv("LLM_MODEL", "step-3.7-flash")


TAG_TYPES = {"task", "method", "model", "dataset", "modality", "application"}
TLDR_MIN_CHARS = 60


ANNOTATE_PROMPT = """你是一名严谨的学术论文分析助手。只能依据提供的论文内容生成结果，不得补充材料中没有出现的信息。

请完成以下任务：

1. 生成 TLDR：
   - 使用中文，80～160 字，2～3 句。
   - 覆盖论文解决的问题、核心方法、主要实验结果或结论、研究价值。
   - 优先保留具体模型、数据集、指标、提升幅度。
   - 材料未提供实验数值时不得编造。
2. 提炼核心贡献：
   - 使用中文，30～80 字。
   - 说明相对已有工作的主要创新，不要重复标题。
3. 识别主要研究领域、子领域、结构化标签。
4. 从作者和机构信息中识别研究团队。无法可靠识别时返回空数组，不得猜测团队名称。
5. 识别正式发表会议或期刊：
   - 会议年份是会议届次年份，不是 arXiv 上传年份。
   - 仅当 arXiv 备注、journal reference 或正文中明确出现时返回。
   - evidence 必须逐字来自提供的材料；投稿中、准备投稿、只有模板名称均返回 null。

论文标题：{title}
arXiv 分类：{categories}
摘要：{abstract}
作者：{authors}
机构：{institutions}
arXiv 备注：{arxiv_comment}
journal reference：{journal_ref}
正文关键章节节选：
{paper_excerpt}

请严格按以下 JSON 格式返回（不要有其他文字）：
{{
  "tldr": "80～160 字的 TLDR",
  "core_contribution": "30～80 字的核心贡献",
  "primary_domain": "主要研究领域",
  "subfields": ["子领域"],
  "tags": [
    {{
      "name": "标签名称",
      "type": "task|method|model|dataset|modality|application"
    }}
  ],
  "venue": {{
    "name": "会议或期刊规范简称，如 ICLR、AAAI、NeurIPS",
    "year": 2026,
    "evidence": "材料中明确说明发表信息的原文"
  }},
  "teams": [
    {{
      "name": "团队名称（如：中科院计算所曹娟团队）",
      "institution": "主要所属机构",
      "members": ["作者名1", "作者名2"]
    }}
  ]
}}"""


# ──────────────────────────────
# 单篇标注
# ──────────────────────────────

def annotate_paper(paper_id: str, model: Optional[str] = None,
                   api_key: Optional[str] = None, base_url: Optional[str] = None,
                   db_path: Optional[Path] = None, force: bool = False) -> dict:
    """生成 TLDR、核心贡献、领域、标签，补充团队关系。"""
    model = model or get_default_model()
    conn = get_connection(db_path)
    try:
        paper = get_paper(conn, paper_id)
        if not paper:
            raise AnnotationError("PAPER_NOT_FOUND", f"论文不存在: {paper_id}")
        if (
            (paper.get("tldr") or "").strip()
            and (paper.get("core_contribution") or "").strip()
            and paper.get("venue_checked_at")
            and not force
        ):
            raise AnnotationError("ANNOTATE_ALREADY_DONE", "论文已完成智能标注，无需重复标注")
    finally:
        conn.close()

    pdf_excerpt = ""
    if paper.get("pdf_path"):
        try:
            paper, pdf_context = enrich_paper_metadata_from_pdf(paper_id, db_path=db_path)
            pdf_excerpt = (
                pdf_context.get("tldr_excerpt")
                or pdf_context.get("excerpt")
                or ""
            )[:16000]
        except Exception:
            # PDF 损坏或 arXiv 暂不可用时，仍可使用数据库摘要降级标注。
            pdf_excerpt = ""

    if not (paper.get("abstract") or "").strip() and not pdf_excerpt:
        raise AnnotationError("ANNOTATE_ABSTRACT_MISSING", "论文摘要和 PDF 正文均为空，无法进行智能标注")

    # 收集作者和机构信息
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT a.name, a.affiliation
        FROM paper_authors pa
        JOIN authors a ON pa.author_id = a.id
        WHERE pa.paper_id = ?
        ORDER BY pa.author_order
    """, (paper_id,))
    author_rows = cur.fetchall()
    authors = [r["name"] for r in author_rows]
    institutions = [r["affiliation"] for r in author_rows if r["affiliation"]]
    conn.close()

    authors_str = ", ".join(authors) if authors else "未知"
    institutions_str = ", ".join(dict.fromkeys(institutions)) if institutions else "未知"

    prompt = ANNOTATE_PROMPT.format(
        title=paper["title"],
        categories=paper.get("categories") or "未知",
        abstract=(paper.get("abstract") or "")[:3000],
        authors=authors_str,
        institutions=institutions_str,
        arxiv_comment=paper.get("arxiv_comment") or "未知",
        journal_ref=paper.get("journal_ref") or "未知",
        paper_excerpt=pdf_excerpt or "未下载 PDF，使用摘要进行标注。",
    )

    client = get_client(api_key, base_url)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise AnnotationError("LLM_REQUEST_FAILED", str(exc)) from exc

    content = response.choices[0].message.content or ""
    content = content.strip()

    # 清理可能的 markdown 代码块标记
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        result = json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AnnotationError("LLM_RESPONSE_INVALID", f"模型返回内容不是有效 JSON: {content[:300]}") from exc

    if not isinstance(result, dict):
        raise AnnotationError("LLM_RESPONSE_INVALID", "模型返回 JSON 必须是对象")
    tldr = str(result.get("tldr", "") or "").strip()
    core_contribution = str(result.get("core_contribution", "") or "").strip()
    primary_domain = str(result.get("primary_domain", "") or "").strip()
    subfields = _normalize_string_list(result.get("subfields", []), max_items=8)
    tags = _normalize_tags(result.get("tags", []))
    venue = _normalize_venue(
        result.get("venue"),
        "\n".join(filter(None, (
            paper.get("arxiv_comment"),
            paper.get("journal_ref"),
            pdf_excerpt,
        ))),
    )
    teams = result.get("teams", [])
    if not isinstance(teams, list):
        teams = []
    if not tldr or not core_contribution:
        raise AnnotationError("LLM_RESPONSE_INVALID", "模型返回缺少 tldr 或 core_contribution")
    if not primary_domain or not tags:
        raise AnnotationError("LLM_RESPONSE_INVALID", "模型返回缺少 primary_domain 或有效 tags")
    if len(tldr) < TLDR_MIN_CHARS:
        raise AnnotationError(
            "LLM_RESPONSE_INVALID",
            f"模型返回的 TLDR 过短（{len(tldr)} 字，至少 {TLDR_MIN_CHARS} 字）",
        )
    result["tldr"] = tldr
    result["core_contribution"] = core_contribution
    result["primary_domain"] = primary_domain
    result["subfields"] = subfields
    result["tags"] = tags
    result["venue"] = venue
    result["teams"] = teams

    # 写回数据库
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE papers
        SET tldr = ?, core_contribution = ?, primary_domain = ?, subfields = ?,
            venue = ?, venue_year = ?, venue_evidence = ?, venue_checked_at = ?,
            enhanced_at = ?
        WHERE id = ?
        """,
        (
            tldr,
            core_contribution,
            primary_domain,
            json.dumps(subfields, ensure_ascii=False),
            venue["name"] if venue else None,
            venue["year"] if venue else None,
            venue["evidence"] if venue else None,
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            paper_id,
        ),
    )
    # 重新标注采用替换语义，避免旧 team 关联残留。
    cur.execute("DELETE FROM paper_teams WHERE paper_id = ?", (paper_id,))
    cur.execute("DELETE FROM paper_tags WHERE paper_id = ?", (paper_id,))
    if force:
        cur.execute("DELETE FROM paper_institutions WHERE paper_id = ?", (paper_id,))

    for tag in tags:
        cur.execute(
            "INSERT OR IGNORE INTO tags (name, type) VALUES (?, ?)",
            (tag["name"], tag["type"]),
        )
        tag_row = cur.execute(
            "SELECT id FROM tags WHERE name = ? COLLATE NOCASE AND type = ?",
            (tag["name"], tag["type"]),
        ).fetchone()
        cur.execute(
            "INSERT OR IGNORE INTO paper_tags (paper_id, tag_id) VALUES (?, ?)",
            (paper_id, tag_row[0]),
        )

    # 写入团队
    for team in teams:
        if not isinstance(team, dict):
            continue
        team_name = str(team.get("name", "")).strip()
        if not team_name:
            continue

        institution_name = str(team.get("institution", "")).strip()
        institution_id = None
        if institution_name:
            cur.execute("INSERT OR IGNORE INTO institutions (name) VALUES (?)", (institution_name,))
            cur.execute("SELECT id FROM institutions WHERE name = ?", (institution_name,))
            institution_id = cur.fetchone()[0]
            cur.execute(
                "INSERT OR IGNORE INTO paper_institutions (paper_id, institution_id) VALUES (?, ?)",
                (paper_id, institution_id),
            )

        cur.execute(
            "INSERT OR IGNORE INTO teams (name, lead_institution_id) VALUES (?, ?)",
            (team_name, institution_id),
        )
        if institution_id is not None:
            cur.execute(
                "UPDATE teams SET lead_institution_id = ? WHERE name = ?",
                (institution_id, team_name),
            )
        cur.execute("SELECT id FROM teams WHERE name = ?", (team_name,))
        team_id = cur.fetchone()[0]
        cur.execute(
            "INSERT OR IGNORE INTO paper_teams (paper_id, team_id) VALUES (?, ?)",
            (paper_id, team_id),
        )

        members = team.get("members", [])
        if not isinstance(members, list):
            continue
        for raw_member_name in members:
            member_name = str(raw_member_name).strip()
            if not member_name:
                continue
            cur.execute("SELECT id FROM authors WHERE name = ?", (member_name,))
            author_row = cur.fetchone()
            if author_row:
                author_id = author_row[0]
            else:
                cur.execute("INSERT INTO authors (name) VALUES (?)", (member_name,))
                author_id = cur.lastrowid
            cur.execute(
                "INSERT OR IGNORE INTO team_members (team_id, author_id) VALUES (?, ?)",
                (team_id, author_id),
            )

    conn.commit()
    conn.close()
    return result


def _normalize_string_list(value: object, max_items: int) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        text = str(item or "").strip()
        if text and text.casefold() not in {entry.casefold() for entry in normalized}:
            normalized.append(text)
        if len(normalized) >= max_items:
            break
    return normalized


def _normalize_tags(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        tag_type = str(item.get("type", "") or "").strip().lower()
        key = (name.casefold(), tag_type)
        if not name or tag_type not in TAG_TYPES or key in seen:
            continue
        seen.add(key)
        normalized.append({"name": name, "type": tag_type})
        if len(normalized) >= 16:
            break
    return normalized


def _normalize_venue(value: object, evidence_source: str) -> Optional[dict]:
    """只接受能在输入材料中回查的 venue，阻止无证据推断。"""
    if not isinstance(value, dict):
        return None
    name = str(value.get("name", "") or "").strip()
    evidence = str(value.get("evidence", "") or "").strip()
    try:
        year = int(value.get("year"))
    except (TypeError, ValueError):
        return None
    if not name or len(name) > 80 or not evidence or not 1900 <= year <= 2100:
        return None

    normalize = lambda text: re.sub(r"\s+", " ", text or "").strip().casefold()
    if normalize(evidence) not in normalize(evidence_source):
        return None
    return {"name": name, "year": year, "evidence": evidence}


def annotate_all(model: str = "step-3.7-flash", api_key: Optional[str] = None,
                 base_url: Optional[str] = None, db_path: Optional[Path] = None,
                 project_id: Optional[str] = None) -> int:
    """批量标注所有未标注的论文。"""
    conn = get_connection(db_path)
    df = list_papers(db_path, project_id=project_id)
    # 旧标注缺少 TLDR 时也应升级。
    pending = df[
        df["tldr"].isna()
        | (df["tldr"] == "")
        | df["core_contribution"].isna()
        | (df["core_contribution"] == "")
        | df["venue_checked_at"].isna()
        | (df["venue_checked_at"] == "")
    ]
    count = 0

    for _, row in pending.iterrows():
        try:
            annotate_paper(
                row["id"], model=model, api_key=api_key,
                base_url=base_url, db_path=db_path,
            )
            count += 1
        except Exception as e:
            print(f"标注失败 {row['id']}: {e}")

    conn.close()
    return count
