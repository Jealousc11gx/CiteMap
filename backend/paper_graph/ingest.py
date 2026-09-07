"""CiteMap - PDF 和 arXiv 入库模块。"""

import re
import hashlib
import shutil
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Optional

import fitz  # PyMuPDF
import arxiv
import requests

from .database import init_db, get_connection, upsert_paper


ARXIV_LABELED_ID_RE = re.compile(
    r"(?:arxiv\s*:\s*|arxiv\.org/(?:abs|pdf)/)"
    r"(?P<id>\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})"
    r"(?:v\d+)?",
    re.IGNORECASE,
)
ARXIV_BARE_ID_RE = re.compile(
    r"(?:arxiv[_\s:]*)?"
    r"(?P<id>\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})"
    r"(?:v\d+)?(?:\.pdf)?",
    re.IGNORECASE,
)
PDF_CONTEXT_MAX_PAGES = 4
PDF_CONTEXT_MAX_CHARS = 12_000
PDF_TLDR_MAX_PAGES = 40
PDF_TLDR_MAX_CHARS = 16_000

SECTION_HEADING_RE = re.compile(
    r"(?im)^\s*(?:\d+(?:\.\d+)*\.?\s+)?"
    r"(?P<title>abstract|introduction|background|related work|"
    r"methodology|methods?|approach|model|framework|"
    r"experiments?|evaluation|results?|analysis|discussion|"
    r"limitations?|conclusions?|future work)\s*[:.]?\s*$"
)


class _ArxivMetaParser(HTMLParser):
    """读取 arXiv 摘要页中的 citation_* meta，不解析页面展示结构。"""

    def __init__(self):
        super().__init__()
        self.values: dict[str, list[str]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag != "meta":
            return
        attributes = dict(attrs)
        name = attributes.get("name")
        content = attributes.get("content")
        if name and name.startswith("citation_") and content:
            self.values.setdefault(name, []).append(content)


def _download_arxiv_pdf(result: arxiv.Result, pdf_path: Path, timeout: int = 60) -> None:
    """兼容 arxiv 4.x：使用 pdf_url 手动下载 PDF。"""
    pdf_url = getattr(result, "pdf_url", None)
    if not pdf_url:
        # 4.0 中 pdf_url 可能是 links 中的第一个 link
        for link in getattr(result, "links", []):
            href = getattr(link, "href", "")
            if href.endswith(".pdf"):
                pdf_url = href
                break
    if not pdf_url:
        raise RuntimeError(f"无法获取 PDF URL: {result.entry_id}")

    response = requests.get(pdf_url, timeout=timeout)
    response.raise_for_status()
    pdf_path.write_bytes(response.content)


def extract_arxiv_id(text: str) -> Optional[str]:
    """从 PDF 文本、文件名或 arXiv URL 中提取不带版本号的 ID。"""
    value = text or ""
    match = ARXIV_LABELED_ID_RE.search(value)
    if not match and len(value.strip()) <= 255:
        match = ARXIV_BARE_ID_RE.search(value.strip())
    return match.group("id") if match else None


def extract_pdf_context(
    pdf_path: str | Path,
    max_pages: int = PDF_CONTEXT_MAX_PAGES,
    max_chars: int = PDF_CONTEXT_MAX_CHARS,
) -> dict:
    """使用项目现有 PyMuPDF 提取 arXiv ID、首页信息与摘要上下文。"""
    path = Path(pdf_path)
    doc = fitz.open(path)
    try:
        all_page_texts = []
        for page_index in range(min(len(doc), PDF_TLDR_MAX_PAGES)):
            text = doc[page_index].get_text("text", sort=True)
            text = _normalize_pdf_text(text)
            if text:
                all_page_texts.append(text)

        page_texts = all_page_texts[:max_pages]
        first_page = page_texts[0] if page_texts else ""
        combined = "\n\n".join(page_texts)[:max_chars]
        arxiv_id = extract_arxiv_id(first_page) or extract_arxiv_id(path.name)
        return {
            "arxiv_id": arxiv_id,
            "first_page": first_page,
            "excerpt": combined,
            "tldr_excerpt": _select_tldr_sections(all_page_texts),
            "page_count": len(doc),
        }
    finally:
        doc.close()


def _normalize_pdf_text(text: str) -> str:
    """清理 PDF 抽取中的软连字符、断词与过量空白。"""
    text = (text or "").replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\n(?=[a-z])", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _select_tldr_sections(page_texts: list[str], max_chars: int = PDF_TLDR_MAX_CHARS) -> str:
    """优先选取 TLDR 所需章节，避免只把论文开头交给模型。"""
    text = "\n\n".join(page_texts)
    matches = list(SECTION_HEADING_RE.finditer(text))
    if not matches:
        return text[:max_chars]

    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((match.group("title").lower(), text[match.start():end].strip()))

    groups = (
        ({"introduction", "background", "related work"}, 2800),
        ({"method", "methods", "methodology", "approach", "model", "framework"}, 4200),
        ({"experiment", "experiments", "evaluation", "result", "results", "analysis"}, 4800),
        ({"discussion", "limitation", "limitations", "conclusion", "conclusions", "future work"}, 4200),
    )
    selected = []
    for names, budget in groups:
        section = next((body for title, body in sections if title in names), "")
        if section:
            selected.append(section[:budget])
    return "\n\n".join(selected)[:max_chars] or text[:max_chars]


def _fetch_arxiv_result(arxiv_id: str) -> Any:
    """优先使用 arXiv API；遇到限流时回退到摘要页 citation metadata。"""
    client = arxiv.Client(page_size=1, delay_seconds=3, num_retries=1)
    search = arxiv.Search(id_list=[_parse_arxiv_id(arxiv_id)])
    api_error: Optional[Exception] = None
    try:
        results = list(client.results(search))
        if results:
            return results[0]
        api_error = ValueError(f"未找到 arXiv 论文: {arxiv_id}")
    except Exception as exc:
        api_error = exc

    try:
        return _fetch_arxiv_abs_metadata(arxiv_id)
    except Exception as fallback_error:
        raise RuntimeError(
            f"arXiv 元数据获取失败: API={api_error}; ABS={fallback_error}"
        ) from fallback_error


def _fetch_arxiv_abs_metadata(arxiv_id: str, timeout: int = 20) -> SimpleNamespace:
    normalized_id = _parse_arxiv_id(arxiv_id)
    url = f"https://arxiv.org/abs/{normalized_id}"
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "CiteMap/0.1 personal research tool"},
    )
    response.raise_for_status()

    parser = _ArxivMetaParser()
    parser.feed(response.text)
    values = parser.values

    title = (values.get("citation_title") or [""])[0].strip()
    abstract = (values.get("citation_abstract") or [""])[0].strip()
    if not title or not abstract:
        raise ValueError(f"arXiv 摘要页缺少标题或摘要: {normalized_id}")

    authors = []
    for raw_name in values.get("citation_author", []):
        parts = [part.strip() for part in raw_name.split(",", 1)]
        authors.append(f"{parts[1]} {parts[0]}" if len(parts) == 2 else raw_name.strip())

    published = _parse_arxiv_meta_date((values.get("citation_date") or [""])[0])
    updated = _parse_arxiv_meta_date((values.get("citation_online_date") or [""])[0]) or published
    subjects_match = re.search(
        r'<td class="tablecell subjects">(.*?)</td>',
        response.text,
        flags=re.DOTALL,
    )
    categories = []
    if subjects_match:
        subjects_html = subjects_match.group(1)
        categories = list(dict.fromkeys(
            re.findall(r'href="/list/([^/\"]+)/recent"', subjects_html)
            + re.findall(r"\(([a-z-]+\.[A-Z]+)\)", subjects_html)
        ))

    return SimpleNamespace(
        entry_id=url,
        title=title,
        summary=abstract,
        published=published,
        updated=updated,
        categories=categories,
        authors=authors,
        affiliation=[],
        pdf_url=(values.get("citation_pdf_url") or [None])[0],
    )


def _parse_arxiv_meta_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    for date_format in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:10], date_format)
        except ValueError:
            continue
    return None


def _paper_data_from_arxiv(
    result: Any,
    paper_id: str,
    pdf_path: Optional[str] = None,
) -> dict:
    return {
        "id": paper_id,
        "title": result.title.replace("\n", " ").strip(),
        "abstract": result.summary.replace("\n", " ").strip(),
        "published_date": result.published.date().isoformat() if result.published else datetime.now().isoformat()[:10],
        "updated_date": result.updated.date().isoformat() if result.updated else datetime.now().isoformat(),
        "categories": ", ".join(result.categories),
        "pdf_path": pdf_path,
        "source": "arxiv",
        "arxiv_url": result.entry_id,
    }


def enrich_paper_metadata_from_pdf(
    paper_id: str,
    db_path: Optional[Path] = None,
) -> tuple[dict, dict]:
    """从 PDF 刷新论文信息；arXiv 优先，否则使用本地布局提取。"""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"论文不存在: {paper_id}")

    paper = dict(row)
    pdf_path = paper.get("pdf_path")
    if not pdf_path or not Path(pdf_path).is_file():
        conn.close()
        return paper, {
            "arxiv_id": None,
            "first_page": "",
            "excerpt": "",
            "tldr_excerpt": "",
            "page_count": 0,
        }

    context = extract_pdf_context(pdf_path)
    detected_arxiv_id = context.get("arxiv_id")
    if not detected_arxiv_id and paper.get("source") == "local":
        try:
            local_data = extract_pdf_metadata(Path(pdf_path))
            local_authors = local_data.pop("authors", [])
            local_data.update({"id": paper_id, "pdf_path": str(Path(pdf_path).resolve())})
            upsert_paper(conn, local_data)
            conn.execute("DELETE FROM paper_authors WHERE paper_id = ?", (paper_id,))
            _save_authors(conn, paper_id, local_authors)
            conn.commit()
            updated = dict(conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone())
            conn.close()
            return updated, context
        except Exception:
            conn.close()
            return paper, context

    needs_refresh = bool(detected_arxiv_id) and (
        paper.get("source") != "arxiv" or not paper.get("arxiv_url")
    )
    if not needs_refresh:
        conn.close()
        return paper, context

    try:
        result = _fetch_arxiv_result(detected_arxiv_id)
    except Exception:
        conn.close()
        return paper, context

    paper_data = _paper_data_from_arxiv(result, paper_id, str(Path(pdf_path).resolve()))
    upsert_paper(conn, paper_data)
    conn.execute("DELETE FROM paper_authors WHERE paper_id = ?", (paper_id,))
    _save_authors_from_arxiv(
        conn,
        paper_id,
        result.authors,
        getattr(result, "affiliation", None),
    )
    conn.commit()
    updated = dict(conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone())
    conn.close()
    return updated, context


# 保留旧名称，避免已有调用方中断。
enrich_arxiv_metadata_from_pdf = enrich_paper_metadata_from_pdf


# ──────────────────────────────
# 本地 PDF 入库
# ──────────────────────────────

def _local_paper_id(pdf_path: Path) -> str:
    """根据文件内容生成稳定的本地论文 ID。"""
    digest = hashlib.sha256()
    with pdf_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"local_{digest.hexdigest()[:12]}"


def _join_line_spans(spans: list[dict]) -> str:
    """依据 span 间的视觉间距恢复空格，兼容 small caps 分段字体。"""
    parts = []
    previous_right = None
    previous_had_space = False
    for span in spans:
        raw_text = str(span.get("text", ""))
        text = raw_text.strip()
        if not text:
            previous_had_space = previous_had_space or bool(raw_text)
            continue
        bbox = span.get("bbox", (0.0, 0.0, 0.0, 0.0))
        left = float(bbox[0])
        right = float(bbox[2])
        size = float(span.get("size", 10.0))
        gap = left - previous_right if previous_right is not None else 0.0
        if parts and (previous_had_space or raw_text.startswith(" ") or gap > max(0.8, size * 0.08)):
            parts.append(" ")
        parts.append(text)
        previous_right = right
        previous_had_space = raw_text.endswith(" ")
    return "".join(parts).strip()


def _page_line_records(page: Any) -> list[dict]:
    """按视觉行聚合 PyMuPDF spans，供本地 metadata fallback 使用。"""
    raw = page.get_text("dict", sort=True)
    if not isinstance(raw, dict):
        return []

    records = []
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            direction = line.get("dir", (1.0, 0.0))
            if abs(direction[1]) > 0.2:
                continue
            spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
            if not spans:
                continue
            bbox = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
            records.append({
                "text": _join_line_spans(spans),
                "size": max(float(span.get("size", 0.0)) for span in spans),
                "x": float(bbox[0]),
                "y": float(bbox[1]),
                "bottom": float(bbox[3]),
            })

    grouped: list[dict] = []
    for record in sorted(records, key=lambda item: (item["y"], item["x"])):
        if grouped and abs(grouped[-1]["y"] - record["y"]) <= 2.5:
            grouped[-1]["parts"].append((record["x"], record["text"]))
            grouped[-1]["size"] = max(grouped[-1]["size"], record["size"])
            grouped[-1]["bottom"] = max(grouped[-1]["bottom"], record["bottom"])
        else:
            grouped.append({**record, "parts": [(record["x"], record["text"])]})

    for record in grouped:
        record["text"] = " ".join(text for _, text in sorted(record.pop("parts"))).strip()
    return grouped


def _is_usable_title(value: str, filename: str = "") -> bool:
    title = re.sub(r"\s+", " ", value or "").strip()
    lowered = title.lower()
    if len(title) < 5 or len(title) > 350:
        return False
    if filename and lowered == filename.lower():
        return False
    if re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", title):
        return False
    blocked = (
        "untitled",
        "microsoft word",
        "published as",
        "published in",
        "accepted at",
        "arxiv:",
    )
    return not lowered.endswith(".pdf") and not any(lowered.startswith(item) for item in blocked)


def _extract_layout_title(page: Any, filename: str = "") -> tuple[str, float]:
    records = _page_line_records(page)
    if not records:
        return "", 0.0

    abstract_record = next(
        (record for record in records if record["text"].strip().lower() in {"abstract", "abstract."}),
        None,
    )
    page_height = float(getattr(getattr(page, "rect", None), "height", 800.0))
    upper_limit = abstract_record["y"] if abstract_record else page_height * 0.45
    candidates = [
        record for record in records
        if record["y"] < upper_limit
        and record["size"] >= 11.5
        and (
            _is_usable_title(record["text"], filename)
            or (
                len(record["text"].strip()) >= 2
                and record["text"].replace("-", "").replace(" ", "").isalpha()
                and record["text"].upper() == record["text"]
            )
        )
    ]
    if not candidates:
        return "", 0.0

    max_size = max(record["size"] for record in candidates)
    title_lines = [record for record in candidates if record["size"] >= max_size * 0.78]
    title_lines.sort(key=lambda item: (item["y"], item["x"]))

    clusters: list[list[dict]] = []
    for record in title_lines:
        if clusters and record["y"] - clusters[-1][-1]["bottom"] <= max_size * 0.75:
            clusters[-1].append(record)
        else:
            clusters.append([record])
    cluster = max(
        clusters,
        key=lambda items: (
            max(item["size"] for item in items),
            -items[0]["y"],
        ),
    )
    title = re.sub(r"\s+", " ", " ".join(item["text"] for item in cluster)).strip()
    return title, max(item["bottom"] for item in cluster)


def _extract_abstract(text: str) -> str:
    normalized = _normalize_pdf_text(text)
    start = re.search(r"(?im)^\s*abstract\s*[:.\-]?\s*(.*)$", normalized)
    if not start:
        return ""
    tail = (start.group(1) + "\n" + normalized[start.end():]).strip()
    end = re.search(
        r"(?im)^\s*(?:\d+(?:\.\d+)*\s+)?(?:introduction|keywords?|index terms)\s*[:.\-]?\s*$",
        tail,
    )
    if end:
        tail = tail[:end.start()]
    return re.sub(r"\s+", " ", tail).strip()[:2500]


def _extract_layout_abstract(page: Any) -> str:
    """按 Abstract 所在栏提取摘要，避免双栏阅读顺序混入正文。"""
    raw = page.get_text("dict", sort=True)
    if not isinstance(raw, dict):
        return ""

    blocks = []
    abstract_heading = None
    introduction_y = None
    for block in raw.get("blocks", []):
        lines = []
        for line in block.get("lines", []):
            text = _join_line_spans(line.get("spans", []))
            if text:
                lines.append(text)
        text = "\n".join(lines).strip()
        if not text:
            continue
        bbox = tuple(float(value) for value in block.get("bbox", (0.0, 0.0, 0.0, 0.0)))
        item = {"text": text, "bbox": bbox}
        blocks.append(item)
        if re.fullmatch(r"(?i)abstract[.:]?", text):
            abstract_heading = item
        if re.match(r"(?i)^\s*(?:\d+(?:\.\d+)*\s*)?introduction\b", text.replace("\n", " ")):
            introduction_y = bbox[1] if introduction_y is None else min(introduction_y, bbox[1])

    if not abstract_heading:
        return ""

    heading_bbox = abstract_heading["bbox"]
    heading_center_x = (heading_bbox[0] + heading_bbox[2]) / 2
    lower_bound = heading_bbox[3] - 2
    upper_bound = introduction_y if introduction_y is not None else float(getattr(page.rect, "height", 800.0)) * 0.8
    selected = []
    for block in blocks:
        bbox = block["bbox"]
        if block is abstract_heading or bbox[1] < lower_bound or bbox[1] >= upper_bound:
            continue
        if bbox[0] - 8 <= heading_center_x <= bbox[2] + 8:
            selected.append(block)

    selected.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    abstract = "\n".join(item["text"] for item in selected)
    return re.sub(r"\s+", " ", _normalize_pdf_text(abstract)).strip()[:2500]


def _extract_layout_authors(page: Any, title_bottom: float) -> list[str]:
    records = _page_line_records(page)
    abstract_record = next(
        (record for record in records if record["text"].strip().lower() in {"abstract", "abstract."}),
        None,
    )
    if not abstract_record:
        return []

    affiliation_terms = (
        "university", "institute", "department", "laboratory", "school of",
        "college", "research", "inc.", "team", "academy", "@",
    )
    author_lines = []
    for record in records:
        if record["y"] <= title_bottom + 3 or record["y"] >= abstract_record["y"]:
            continue
        lowered = record["text"].lower()
        if any(term in lowered for term in affiliation_terms):
            continue
        author_lines.append(record["text"])

    raw = " ".join(author_lines)
    raw = re.sub(r"[\d*†‡§#]+", "", raw)
    candidates = re.split(r"\s*(?:,|;|\band\b)\s*", raw)
    authors = []
    for candidate in candidates:
        name = re.sub(r"\s+", " ", candidate).strip(" .")
        words = name.split()
        if not 2 <= len(words) <= 5:
            continue
        if not all(re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ'\-.]+", word) for word in words):
            continue
        authors.append(name)
    return list(dict.fromkeys(authors))


def extract_pdf_metadata(pdf_path: Path) -> dict:
    """用 PyMuPDF 的 metadata 与页面布局提取本地论文信息。"""
    doc = fitz.open(pdf_path)
    try:
        metadata = doc.metadata or {}
        page_texts = []
        first_page_text = ""
        layout_title = ""
        title_bottom = 0.0
        authors = []
        if len(doc) > 0:
            first_page = doc[0]
            first_page_text = first_page.get_text("text", sort=True)
            layout_title, title_bottom = _extract_layout_title(first_page, pdf_path.name)
            authors = _extract_layout_authors(first_page, title_bottom)
            for page_index in range(min(len(doc), 2)):
                page_texts.append(doc[page_index].get_text("text", sort=True))

        metadata_title = str(metadata.get("title", "")).strip()
        title = layout_title or (metadata_title if _is_usable_title(metadata_title, pdf_path.name) else "")
        if not title:
            lines = [line.strip() for line in first_page_text.splitlines() if line.strip()]
            title = next((line for line in lines if _is_usable_title(line, pdf_path.name)), "")

        abstract = _extract_layout_abstract(doc[0]) if len(doc) > 0 else ""
        if not abstract:
            abstract = _extract_abstract("\n\n".join(page_texts))
        if not abstract:
            abstract = _normalize_pdf_text(first_page_text).replace("\n", " ")[:3000]

        # 解析 PDF 创建日期（格式可能是 D:20240101000000 或 2024-01-01）
        raw_date = metadata.get("creationDate", datetime.now().isoformat())
        created_date = _parse_pdf_date(raw_date)
    finally:
        doc.close()

    return {
        "id": _local_paper_id(pdf_path),
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "published_date": created_date,
        "updated_date": datetime.now().isoformat(),
        "categories": "",
        "pdf_path": str(pdf_path.resolve()),
        "source": "local",
        "arxiv_url": None,
    }


def _parse_pdf_date(raw: str) -> str:
    """解析 PDF 元数据日期格式。"""
    # 匹配 D:20240101000000 格式
    m = re.search(r"D:(\d{4})(\d{2})(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # 已经是 YYYY-MM-DD 格式
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    return datetime.now().isoformat()[:10]


def ingest_local_pdf(
    pdf_path: str | Path,
    db_path: Optional[Path] = None,
    pdf_dir: Optional[Path] = None,
    source_name: Optional[str] = None,
) -> str:
    """入库 PDF；可识别 arXiv ID 时优先使用 arXiv 权威元数据。"""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 不存在: {pdf_path}")

    init_db(db_path)
    conn = get_connection(db_path)
    local_paper = extract_pdf_metadata(pdf_path)
    local_authors = local_paper.pop("authors", [])
    context = extract_pdf_context(pdf_path)
    detected_arxiv_id = context["arxiv_id"] or extract_arxiv_id(source_name or "")
    if not context["excerpt"] and not detected_arxiv_id:
        conn.close()
        raise ValueError("PDF 未包含可提取文本，暂不支持扫描版 PDF")

    arxiv_result = None
    if detected_arxiv_id:
        try:
            arxiv_result = _fetch_arxiv_result(detected_arxiv_id)
        except Exception:
            # arXiv 暂时不可用时仍允许 PDF 本地入库，后续标注会再次尝试回填。
            arxiv_result = None

    paper_id = (
        f"arxiv_{_parse_arxiv_id(detected_arxiv_id)}"
        if arxiv_result is not None and detected_arxiv_id
        else local_paper["id"]
    )

    stored_pdf_path = pdf_path
    if pdf_dir is not None:
        pdf_dir = Path(pdf_dir)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        stored_pdf_path = pdf_dir / f"{paper_id}.pdf"
        if stored_pdf_path.resolve() != pdf_path.resolve():
            shutil.copy2(pdf_path, stored_pdf_path)

    if arxiv_result is not None:
        paper_data = _paper_data_from_arxiv(
            arxiv_result,
            paper_id,
            str(stored_pdf_path.resolve()),
        )
    else:
        paper_data = {
            **local_paper,
            "id": paper_id,
            "pdf_path": str(stored_pdf_path.resolve()),
        }

    upsert_paper(conn, paper_data)
    if arxiv_result is not None:
        _save_authors_from_arxiv(
            conn,
            paper_id,
            arxiv_result.authors,
            getattr(arxiv_result, "affiliation", None),
        )
    else:
        authors_raw = local_authors or _extract_authors_from_text(context["first_page"])
        _save_authors(conn, paper_id, authors_raw)
    conn.commit()
    conn.close()
    return paper_id


def _extract_authors_from_text(text: str) -> list[str]:
    authors = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:15]:
        if any(kw in line.lower() for kw in ["abstract", "introduction", "keywords", "received", "accepted"]):
            break
        if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,3}$", line):
            authors.append(line)
        elif re.match(r"^[\u4e00-\u9fa5]{2,4}(?:\s+[\u4e00-\u9fa5]{2,4}){0,3}$", line):
            authors.append(line)
    return authors


def _save_authors(conn, paper_id: str, authors: list[str]) -> None:
    cur = conn.cursor()
    for order, name in enumerate(authors):
        cur.execute("SELECT id FROM authors WHERE name = ?", (name,))
        author_row = cur.fetchone()
        if author_row:
            author_id = author_row[0]
        else:
            cur.execute("INSERT INTO authors (name) VALUES (?)", (name,))
            author_id = cur.lastrowid
        cur.execute(
            "INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)",
            (paper_id, author_id, order),
        )


# ──────────────────────────────
# arXiv 入库
# ──────────────────────────────

def _parse_arxiv_id(identifier: str) -> str:
    parsed = extract_arxiv_id(identifier)
    if parsed:
        return parsed
    return identifier.strip()


def ingest_arxiv_id(arxiv_id: str, db_path: Optional[Path] = None, download_pdf: bool = False,
                    pdf_dir: Optional[Path] = None) -> str:
    """通过 arXiv ID 入库论文。"""
    init_db(db_path)
    conn = get_connection(db_path)

    paper = _fetch_arxiv_result(arxiv_id)
    paper_id = f"arxiv_{_parse_arxiv_id(paper.entry_id)}"

    pdf_path = None
    if download_pdf and pdf_dir:
        pdf_dir = Path(pdf_dir)
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_file = pdf_dir / f"{paper_id}.pdf"
        if not pdf_file.exists():
            _download_arxiv_pdf(paper, pdf_file)
        pdf_path = str(pdf_file.resolve())

    paper_data = _paper_data_from_arxiv(paper, paper_id, pdf_path)

    upsert_paper(conn, paper_data)
    _save_authors_from_arxiv(conn, paper_id, paper.authors, getattr(paper, "affiliation", None))
    conn.commit()
    conn.close()
    return paper_id


def _save_authors_from_arxiv(conn, paper_id: str, authors: list, affiliations: Optional[list] = None) -> None:
    cur = conn.cursor()
    for order, author in enumerate(authors):
        name = str(author).strip()
        affiliation = ""
        if affiliations and order < len(affiliations) and affiliations[order]:
            affiliation = str(affiliations[order]).strip()

        cur.execute("SELECT id FROM authors WHERE name = ?", (name,))
        author_row = cur.fetchone()
        if author_row:
            author_id = author_row[0]
            if affiliation:
                cur.execute(
                    "UPDATE authors SET affiliation = ? WHERE id = ? AND (affiliation IS NULL OR affiliation = '')",
                    (affiliation, author_id),
                )
        else:
            cur.execute("INSERT INTO authors (name, affiliation) VALUES (?, ?)", (name, affiliation))
            author_id = cur.lastrowid

        if affiliation:
            cur.execute("INSERT OR IGNORE INTO institutions (name) VALUES (?)", (affiliation,))
            cur.execute("SELECT id FROM institutions WHERE name = ?", (affiliation,))
            inst_id = cur.fetchone()[0]
            cur.execute(
                "INSERT OR IGNORE INTO paper_institutions (paper_id, institution_id) VALUES (?, ?)",
                (paper_id, inst_id),
            )

        cur.execute(
            "INSERT OR IGNORE INTO paper_authors (paper_id, author_id, author_order) VALUES (?, ?, ?)",
            (paper_id, author_id, order),
        )


def search_arxiv(query: str, max_results: int = 10, db_path: Optional[Path] = None,
                 download_pdf: bool = False, pdf_dir: Optional[Path] = None) -> list[str]:
    """搜索 arXiv 并批量入库，返回 paper_id 列表。"""
    init_db(db_path)
    conn = get_connection(db_path)
    paper_ids = []

    client = arxiv.Client(page_size=min(max_results, 50), delay_seconds=1)
    search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)

    for result in client.results(search):
        paper_id = f"arxiv_{_parse_arxiv_id(result.entry_id)}"
        pdf_path = None
        if download_pdf and pdf_dir:
            pdf_dir = Path(pdf_dir)
            pdf_dir.mkdir(parents=True, exist_ok=True)
            pdf_file = pdf_dir / f"{paper_id}.pdf"
            if not pdf_file.exists():
                _download_arxiv_pdf(result, pdf_file)
            pdf_path = str(pdf_file.resolve())

        paper_data = _paper_data_from_arxiv(result, paper_id, pdf_path)
        upsert_paper(conn, paper_data)
        _save_authors_from_arxiv(conn, paper_id, result.authors, getattr(result, "affiliation", None))
        paper_ids.append(paper_id)

    conn.commit()
    conn.close()
    return paper_ids


def search_arxiv_only(query: str, max_results: int = 10) -> list[dict]:
    """只搜索 arXiv，不自动入库，返回论文元数据列表。"""
    client = arxiv.Client(page_size=min(max_results, 50), delay_seconds=1)
    search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)

    results = []
    for result in client.results(search):
        paper_id = f"arxiv_{_parse_arxiv_id(result.entry_id)}"
        results.append({
            "id": paper_id,
            "title": result.title.replace("\n", " ").strip(),
            "abstract": result.summary.replace("\n", " ").strip(),
            "published_date": result.published.date().isoformat() if result.published else "",
            "categories": ", ".join(result.categories),
            "arxiv_url": result.entry_id,
            "authors": [str(a).strip() for a in getattr(result, "authors", [])],
        })

    return results
