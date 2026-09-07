"""CiteMap - Kimi Agent SDK 工具集合（CallableTool2）。

所有工具继承 CallableTool2，参数用 Pydantic BaseModel 描述，便于 Agent 理解。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue

from . import chat_tools


def _ok(obj) -> ToolReturnValue:
    return ToolOk(output=json.dumps(obj, ensure_ascii=False, default=str))


def _err(exc: Exception, brief: str = "工具执行失败") -> ToolReturnValue:
    return ToolError(output="", message=str(exc), brief=brief)


# ── search_arxiv ─────────────────────────────────────────────────────────────
class SearchArxivParams(BaseModel):
    query: str = Field(description="搜索关键词或主题，例如 'transformer protein folding'")
    max_results: int = Field(default=5, ge=1, le=20, description="最多返回多少条结果")


class SearchArxiv(CallableTool2):
    name: str = "search_arxiv"
    description: str = "在 arXiv 上搜索与给定主题相关的论文，返回论文标题、摘要、ID 等元数据。"
    params: type[BaseModel] = SearchArxivParams

    async def __call__(self, params: SearchArxivParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(
                chat_tools.search_arxiv, params.query, params.max_results
            )
            return _ok(result)
        except Exception as e:
            return _err(e, "search_arxiv failed")


# ── ingest_arxiv_paper ───────────────────────────────────────────────────────
class IngestArxivPaperParams(BaseModel):
    arxiv_id: str = Field(description="arXiv ID，例如 '2402.09199'")
    download_pdf: bool = Field(default=False, description="是否同时下载 PDF 原文")


class IngestArxivPaper(CallableTool2):
    name: str = "ingest_arxiv_paper"
    description: str = "根据 arXiv ID 将论文入库到本地知识库。入库后可继续查询、标注或下载 PDF。"
    params: type[BaseModel] = IngestArxivPaperParams

    async def __call__(self, params: IngestArxivPaperParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(
                chat_tools.ingest_arxiv_paper, params.arxiv_id, params.download_pdf
            )
            return _ok(result)
        except Exception as e:
            return _err(e, "ingest_arxiv_paper failed")


# ── list_local_papers ─────────────────────────────────────────────────────────
class ListLocalPapersParams(BaseModel):
    source: Optional[str] = Field(default=None, description="来源筛选，例如 'arxiv' 或 'pdf'")
    limit: int = Field(default=20, ge=1, le=100, description="最多返回多少条")


class ListLocalPapers(CallableTool2):
    name: str = "list_local_papers"
    description: str = "列出本地论文库中已入库的论文，支持按来源筛选。"
    params: type[BaseModel] = ListLocalPapersParams

    async def __call__(self, params: ListLocalPapersParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(
                chat_tools.list_local_papers, params.source, params.limit
            )
            return _ok(result)
        except Exception as e:
            return _err(e, "list_local_papers failed")


# ── search_local_papers ───────────────────────────────────────────────────────
class SearchLocalPapersParams(BaseModel):
    keywords: str = Field(description="搜索关键词，例如 'large language model reasoning'")
    limit: int = Field(default=5, ge=1, le=20, description="最多返回多少条")


class SearchLocalPapers(CallableTool2):
    name: str = "search_local_papers"
    description: str = "在本地论文库的标题和摘要中搜索关键词。"
    params: type[BaseModel] = SearchLocalPapersParams

    async def __call__(self, params: SearchLocalPapersParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(
                chat_tools.search_local_papers, params.keywords, params.limit
            )
            return _ok(result)
        except Exception as e:
            return _err(e, "search_local_papers failed")


# ── get_paper_details ─────────────────────────────────────────────────────────
class GetPaperDetailsParams(BaseModel):
    paper_id: str = Field(description="本地论文 ID，例如 'arxiv_2402.09199'")


class GetPaperDetails(CallableTool2):
    name: str = "get_paper_details"
    description: str = "获取本地知识库中某篇论文的完整详情，包括标题、摘要、作者、核心贡献、PDF/笔记路径等。"
    params: type[BaseModel] = GetPaperDetailsParams

    async def __call__(self, params: GetPaperDetailsParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(chat_tools.get_paper_details, params.paper_id)
            return _ok(result)
        except Exception as e:
            return _err(e, "get_paper_details failed")


# ── annotate_paper_tool ───────────────────────────────────────────────────────
class AnnotatePaperParams(BaseModel):
    paper_id: str = Field(description="本地论文 ID")


class AnnotatePaperTool(CallableTool2):
    name: str = "annotate_paper_tool"
    description: str = "对本地论文生成 TLDR、核心贡献、领域、结构化标签，补充研究团队关系。结果写回数据库。"
    params: type[BaseModel] = AnnotatePaperParams

    async def __call__(self, params: AnnotatePaperParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(chat_tools.annotate_paper_tool, params.paper_id)
            return _ok(result)
        except Exception as e:
            return _err(e, "annotate_paper_tool failed")


# ── download_paper_pdf ────────────────────────────────────────────────────────
class DownloadPaperPdfParams(BaseModel):
    paper_id: str = Field(description="本地论文 ID，例如 'arxiv_2402.09199'")


class DownloadPaperPdf(CallableTool2):
    name: str = "download_paper_pdf"
    description: str = "为本地已入库的 arXiv 论文下载 PDF 原文。"
    params: type[BaseModel] = DownloadPaperPdfParams

    async def __call__(self, params: DownloadPaperPdfParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(chat_tools.download_paper_pdf, params.paper_id)
            return _ok(result)
        except Exception as e:
            return _err(e, "download_paper_pdf failed")


# ── get_paper_notes ───────────────────────────────────────────────────────────
class GetPaperNotesParams(BaseModel):
    paper_id: str = Field(description="本地论文 ID")


class GetPaperNotes(CallableTool2):
    name: str = "get_paper_notes"
    description: str = "获取某篇论文关联的 Markdown 笔记内容。"
    params: type[BaseModel] = GetPaperNotesParams

    async def __call__(self, params: GetPaperNotesParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(chat_tools.get_paper_notes, params.paper_id)
            return _ok(result)
        except Exception as e:
            return _err(e, "get_paper_notes failed")


# ── get_graph_summary ─────────────────────────────────────────────────────────
class GetGraphSummaryParams(BaseModel):
    pass


class GetGraphSummary(CallableTool2):
    name: str = "get_graph_summary"
    description: str = "获取本地论文库的知识图谱统计摘要：团队数量、论文数量、主要合作关系等。"
    params: type[BaseModel] = GetGraphSummaryParams

    async def __call__(self, params: GetGraphSummaryParams) -> ToolReturnValue:
        try:
            result = await asyncio.to_thread(chat_tools.get_graph_summary)
            return _ok(result)
        except Exception as e:
            return _err(e, "get_graph_summary failed")
