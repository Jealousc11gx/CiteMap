"""CiteMap - FastAPI 后端服务。"""

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from paper_graph.database import (
    DEFAULT_PROJECT_ID,
    add_chat_message,
    add_paper_to_project,
    create_chat_session,
    create_project,
    delete_chat_session,
    delete_project,
    get_chat_messages,
    get_chat_session,
    get_connection,
    get_paper,
    hydrate_paper,
    get_project,
    init_db,
    list_chat_sessions,
    list_available_papers,
    list_papers,
    list_projects,
    remove_paper_from_project,
    update_chat_session_title,
    update_project,
)
from paper_graph.radar import (
    get_radar_config,
    list_radar_matches,
    run_radar_collection,
    transition_radar_state,
    upsert_radar_config,
)
from paper_graph.radar_embeddings import get_embedding_provider
from paper_graph.radar_sync import RadarRemoteClient, flush_pending_operations, sync_remote_changes
from paper_graph.ingest import ingest_local_pdf, ingest_arxiv_id, search_arxiv, search_arxiv_only, _download_arxiv_pdf
from paper_graph.annotate import annotate_paper, annotate_all, get_default_model, get_client, AnnotationError
from paper_graph.graph import build_paper_graph, build_team_ego_graph, build_team_graph
from paper_graph.citations import (
    CitationSyncError,
    build_citation_graph,
    build_similarity_graph,
    sync_citation_metrics,
    sync_citations,
)
from paper_graph.notes import list_notes, get_note, save_note as notes_save, create_note_template, delete_note as notes_delete
from paper_graph.chat_agent import run_agent, run_agent_stream
import arxiv
import re

# 加载 .env 文件
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "papers.db"

app = FastAPI(title="CiteMap API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────
# 数据模型
# ──────────────────────────────

class PaperIngestArxivRequest(BaseModel):
    arxiv_id: str
    download_pdf: bool = False
    project_id: Optional[str] = None


class PaperSearchRequest(BaseModel):
    query: str
    max_results: int = 10
    download_pdf: bool = False


class PaperVenueUpdate(BaseModel):
    venue: Optional[str] = None
    venue_year: Optional[int] = None


class EnhanceRequest(BaseModel):
    paper_id: Optional[str] = None
    model: Optional[str] = None
    project_id: Optional[str] = None
    force: bool = False


class ChatRequest(BaseModel):
    message: str
    mode: str = "auto"  # auto | structured | rag
    project_id: Optional[str] = None


class ChatResponse(BaseModel):
    mode: str
    answer: str
    papers: list[dict]
    tool_calls: list[dict] = []


class BatchIngestRequest(BaseModel):
    paper_ids: list[str]
    download_pdf: bool = False
    project_id: Optional[str] = None


class ChatSessionCreate(BaseModel):
    title: str = ""
    project_id: Optional[str] = None


class ChatSessionRename(BaseModel):
    title: str


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    project_id: Optional[str] = None


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str
    description: Optional[str] = None


class RadarConfigRequest(BaseModel):
    enabled: bool = False
    categories: list[str] = []
    include_keywords: list[str] = []
    exclude_keywords: list[str] = []
    profile_override: str = ""
    anchor_paper_ids: list[str] = []
    top_k: int = 10
    min_score: float = 0.0
    include_cross_list: bool = True
    send_empty: bool = False
    fetch_limit: int = 100
    debug: bool = False
    compute_mode: str = "cloud"


class RadarStateRequest(BaseModel):
    state: str
    download_pdf: bool = False


class RadarSyncRequest(BaseModel):
    remote_url: str
    token: str
    publish_profile: bool = True
    force_publish_profile: bool = False


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    papers: Optional[list[dict]] = None
    tool_calls: Optional[list[dict]] = None
    created_at: str


# ──────────────────────────────
# 论文 API
# ──────────────────────────────

def _resolve_project_id(project_id: Optional[str]) -> str:
    return project_id or DEFAULT_PROJECT_ID


def _require_project(project_id: str) -> dict:
    conn = get_connection(DB_PATH)
    try:
        project = get_project(conn, project_id)
    finally:
        conn.close()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def _assign_paper(project_id: Optional[str], paper_id: str) -> None:
    target_id = _resolve_project_id(project_id)
    _require_project(target_id)
    conn = get_connection(DB_PATH)
    try:
        # 入库函数的正常契约会先写入 papers；测试替身可能只返回 ID。
        if not get_paper(conn, paper_id):
            return
        add_paper_to_project(conn, target_id, paper_id)
    finally:
        conn.close()


# ──────────────────────────────
# 项目 API
# ──────────────────────────────

@app.get("/api/projects")
def api_list_projects():
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        return list_projects(conn)
    finally:
        conn.close()


@app.post("/api/projects", status_code=201)
def api_create_project(req: ProjectCreate):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="项目名称不能为空")
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        return create_project(conn, name, req.description)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="项目名称已存在")
    finally:
        conn.close()


@app.patch("/api/projects/{project_id}")
def api_update_project(project_id: str, req: ProjectUpdate):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="项目名称不能为空")
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        project = update_project(conn, project_id, name, req.description)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")
        return project
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="项目名称已存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.delete("/api/projects/{project_id}")
def api_delete_project(project_id: str):
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        if not delete_project(conn, project_id):
            raise HTTPException(status_code=404, detail="项目不存在")
        return {"status": "deleted", "fallback_project_id": DEFAULT_PROJECT_ID}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.post("/api/projects/{project_id}/papers/{paper_id}")
def api_add_paper_to_project(project_id: str, paper_id: str):
    _require_project(project_id)
    if project_id == DEFAULT_PROJECT_ID:
        raise HTTPException(status_code=400, detail="不能手动向未分类添加论文")
    conn = get_connection(DB_PATH)
    try:
        if not get_paper(conn, paper_id):
            raise HTTPException(status_code=404, detail="论文不存在")
        add_paper_to_project(conn, project_id, paper_id)
        return {"status": "added"}
    finally:
        conn.close()


@app.get("/api/projects/{project_id}/available-papers")
def api_list_available_papers(project_id: str):
    project = _require_project(project_id)
    if project["is_system"]:
        raise HTTPException(status_code=400, detail="未分类不能从其他项目导入论文")
    conn = get_connection(DB_PATH)
    try:
        return list_available_papers(conn, project_id)
    finally:
        conn.close()


@app.delete("/api/projects/{project_id}/papers/{paper_id}")
def api_remove_paper_from_project(project_id: str, paper_id: str):
    _require_project(project_id)
    if project_id == DEFAULT_PROJECT_ID:
        raise HTTPException(status_code=400, detail="不能从未分类手动移除论文")
    conn = get_connection(DB_PATH)
    try:
        remove_paper_from_project(conn, project_id, paper_id)
        return {"status": "removed", "fallback_project_id": DEFAULT_PROJECT_ID}
    finally:
        conn.close()


# ──────────────────────────────
# 论文雷达 API
# ──────────────────────────────

@app.get("/api/radar/config")
def api_get_radar_config(project_id: str):
    _require_project(project_id)
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        return get_radar_config(conn, project_id)
    finally:
        conn.close()


@app.put("/api/radar/config")
def api_update_radar_config(project_id: str, req: RadarConfigRequest):
    project = _require_project(project_id)
    if project["is_system"] and req.enabled:
        raise HTTPException(status_code=400, detail="未分类项目不能启用论文雷达，请新建研究项目后再配置雷达")
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        return upsert_radar_config(
            conn,
            project_id,
            enabled=req.enabled,
            categories=req.categories,
            include_keywords=req.include_keywords,
            exclude_keywords=req.exclude_keywords,
            profile_override=req.profile_override,
            anchor_paper_ids=req.anchor_paper_ids,
            top_k=req.top_k,
            min_score=req.min_score,
            include_cross_list=req.include_cross_list,
            send_empty=req.send_empty,
            fetch_limit=req.fetch_limit,
            debug=req.debug,
            compute_mode=req.compute_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@app.get("/api/radar/matches")
def api_list_radar_matches(project_id: str, state: Optional[str] = None, limit: int = 100):
    _require_project(project_id)
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="雷达结果数量必须在 1 到 500 之间")
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        return list_radar_matches(conn, project_id, state=state, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@app.post("/api/radar/scan")
def api_scan_radar(project_id: str, max_results: int = 100):
    _require_project(project_id)
    if max_results < 1 or max_results > 500:
        raise HTTPException(status_code=400, detail="扫描候选数量必须在 1 到 500 之间")
    init_db(DB_PATH)
    from datetime import date
    conn = get_connection(DB_PATH)
    try:
        return run_radar_collection(
            conn,
            project_id,
            date.today().isoformat(),
            embedding_provider=get_embedding_provider(),
            max_results=max_results,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"code": "RADAR_SCAN_FAILED", "error": str(exc)})
    finally:
        conn.close()


@app.patch("/api/radar/matches/{match_id}")
def api_update_radar_match(match_id: str, req: RadarStateRequest):
    if req.state not in {"read", "saved", "dismissed"}:
        raise HTTPException(status_code=400, detail="雷达状态更新只支持 read、saved、dismissed")
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        match = conn.execute("SELECT * FROM radar_matches WHERE id = ?", (match_id,)).fetchone()
        if not match:
            raise HTTPException(status_code=404, detail="雷达匹配不存在")
        if req.state == "saved":
            candidate = conn.execute(
                "SELECT arxiv_id FROM radar_candidates WHERE id = ?", (match["candidate_id"],)
            ).fetchone()
            if not candidate:
                raise HTTPException(status_code=404, detail="雷达候选不存在")
            paper_id = ingest_arxiv_id(
                candidate["arxiv_id"],
                DB_PATH,
                download_pdf=req.download_pdf,
                pdf_dir=DATA_DIR / "pdfs",
            )
            add_paper_to_project(conn, match["project_id"], paper_id)
            result = transition_radar_state(conn, match_id, req.state)
            from paper_graph.radar import enqueue_radar_operation
            enqueue_radar_operation(conn, match["project_id"], match_id, "save")
            result["paper_id"] = paper_id
        else:
            from paper_graph.radar import enqueue_radar_operation
            result = transition_radar_state(conn, match_id, req.state)
            enqueue_radar_operation(conn, match["project_id"], match_id, req.state)
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@app.post("/api/radar/sync")
def api_sync_radar(req: RadarSyncRequest, project_id: Optional[str] = None):
    if project_id:
        _require_project(project_id)
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        client = RadarRemoteClient(req.remote_url, req.token)
        flushed = flush_pending_operations(conn, client)
        synced = sync_remote_changes(conn, client)
        published = 0
        if req.publish_profile:
            project_ids = [project_id] if project_id else [
                row["id"] for row in conn.execute("SELECT id FROM projects WHERE is_system=0")
            ]
            for current_project_id in project_ids:
                project = conn.execute("SELECT * FROM projects WHERE id=?", (current_project_id,)).fetchone()
                if not project:
                    continue
                from paper_graph.radar import get_radar_config
                from paper_graph.radar_ranking import load_anchor_ids, load_project_references
                config = get_radar_config(conn, current_project_id)
                profile = {
                    **config,
                    "project_id": current_project_id,
                    "project_name": project["name"],
                    "reference_papers": load_project_references(conn, current_project_id),
                    "anchor_paper_ids": list(load_anchor_ids(conn, current_project_id)),
                }
                serialized = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                fingerprint = hashlib.sha256(
                    f"{client.base_url}\n{serialized}".encode("utf-8")
                ).hexdigest()
                fingerprint_key = f"profile_fingerprint:{current_project_id}"
                previous = conn.execute(
                    "SELECT value FROM radar_sync_state WHERE key=?", (fingerprint_key,)
                ).fetchone()
                if req.force_publish_profile or not previous or previous["value"] != fingerprint:
                    client.publish_profile(current_project_id, profile)
                    conn.execute(
                        """
                        INSERT INTO radar_sync_state (key, value, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
                        """,
                        (fingerprint_key, fingerprint),
                    )
                    conn.commit()
                    published += 1
        return {
            "flushed": flushed,
            "synced": synced,
            "published": published,
            "profile_forced": req.force_publish_profile,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"code": "RADAR_SYNC_FAILED", "error": str(exc)})
    finally:
        conn.close()

@app.get("/api/papers/search")
def api_search_arxiv(q: str, max_results: int = 10, download: bool = False, project_id: Optional[str] = None):
    try:
        paper_ids = search_arxiv(q, max_results=max_results, db_path=DB_PATH, download_pdf=download, pdf_dir=DATA_DIR / "pdfs")
        for paper_id in paper_ids:
            _assign_paper(project_id, paper_id)
        return {"paper_ids": paper_ids}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/papers/search-arxiv")
def api_search_arxiv_only(q: str, max_results: int = 10):
    try:
        results = search_arxiv_only(q, max_results=max_results)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/papers")
def api_list_papers(source: Optional[str] = None, q: Optional[str] = None, project_id: Optional[str] = None):
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        if project_id:
            _require_project(project_id)
        df = list_papers(DB_PATH, source=source, project_id=project_id)
        records = [hydrate_paper(conn, record) for record in df.to_dict(orient="records")]
        if q:
            needle = q.casefold()
            records = [
                record for record in records
                if needle in " ".join([
                    str(record.get("title") or ""),
                    str(record.get("abstract") or ""),
                    str(record.get("tldr") or ""),
                    str(record.get("core_contribution") or ""),
                    str(record.get("primary_domain") or ""),
                    " ".join(record.get("subfields") or []),
                    " ".join(tag["name"] for tag in record.get("tags") or []),
                ]).casefold()
            ]
        # json.dumps 无法直接序列化 NaN，需要手动清洗
        for record in records:
            for key, value in list(record.items()):
                if isinstance(value, float) and value != value:
                    record[key] = None
        return records
    finally:
        conn.close()


@app.get("/api/papers/{paper_id}")
def api_get_paper(paper_id: str):
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        paper = get_paper(conn, paper_id)
        if not paper:
            raise HTTPException(status_code=404, detail="论文不存在")
        return hydrate_paper(conn, paper)
    finally:
        conn.close()


@app.patch("/api/papers/{paper_id}/venue")
def api_update_paper_venue(paper_id: str, payload: PaperVenueUpdate):
    """人工修正 venue；人工值优先于后续自动标注。"""
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        paper = get_paper(conn, paper_id)
        if not paper:
            raise HTTPException(status_code=404, detail="论文不存在")

        venue = (payload.venue or "").strip()
        year = payload.venue_year
        if bool(venue) != (year is not None):
            raise HTTPException(status_code=422, detail="venue 与 venue_year 必须同时填写或同时清空")
        if len(venue) > 80:
            raise HTTPException(status_code=422, detail="venue 最多 80 个字符")
        if year is not None and not 1900 <= year <= 2100:
            raise HTTPException(status_code=422, detail="venue_year 必须在 1900 到 2100 之间")

        if venue:
            conn.execute(
                """
                UPDATE papers
                SET venue = ?, venue_year = ?, venue_evidence = NULL,
                    venue_checked_at = ?, venue_source = 'manual'
                WHERE id = ?
                """,
                (venue, year, datetime.now().isoformat(), paper_id),
            )
        else:
            conn.execute(
                """
                UPDATE papers
                SET venue = NULL, venue_year = NULL, venue_evidence = NULL,
                    venue_checked_at = NULL, venue_source = NULL
                WHERE id = ?
                """,
                (paper_id,),
            )
        conn.commit()
        return hydrate_paper(conn, get_paper(conn, paper_id))
    finally:
        conn.close()


@app.post("/api/papers/ingest-pdf")
async def api_ingest_pdf(file: UploadFile = File(...), project_id: Optional[str] = Form(None)):
    init_db(DB_PATH)
    safe_name = os.path.basename(file.filename or "upload.pdf")
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件上传")
    temp_file = tempfile.NamedTemporaryFile(
        prefix="paper-upload-",
        suffix=".pdf",
        dir=DATA_DIR,
        delete=False,
    )
    temp_path = Path(temp_file.name)
    temp_file.close()
    try:
        content = await file.read()
        temp_path.write_bytes(content)
        paper_id = ingest_local_pdf(
            temp_path,
            DB_PATH,
            pdf_dir=DATA_DIR / "pdfs",
            source_name=safe_name,
        )
        _assign_paper(project_id, paper_id)
        return {"paper_id": paper_id, "title": file.filename}
    finally:
        if temp_path.exists():
            temp_path.unlink()


@app.post("/api/papers/ingest-arxiv")
def api_ingest_arxiv(req: PaperIngestArxivRequest):
    init_db(DB_PATH)
    try:
        paper_id = ingest_arxiv_id(req.arxiv_id, DB_PATH, download_pdf=req.download_pdf, pdf_dir=DATA_DIR / "pdfs")
        _assign_paper(req.project_id, paper_id)
        return {"paper_id": paper_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/papers/{paper_id}/annotate")
def api_annotate_paper(paper_id: str, req: EnhanceRequest):
    try:
        if req.project_id:
            scoped = list_papers(DB_PATH, project_id=req.project_id)
            if paper_id not in set(scoped["id"].tolist()):
                raise HTTPException(status_code=404, detail="论文不在当前项目")
        result = annotate_paper(
            paper_id,
            model=req.model,
            db_path=DB_PATH,
            force=req.force,
        )
        if req.project_id:
            # metadata 刷新不得改变论文的项目归属。
            _assign_paper(req.project_id, paper_id)
        return result
    except HTTPException:
        raise
    except AnnotationError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": e.code, "error": str(e), "suggestion": "请修正输入或检查模型配置后重试。"},
        )
    except Exception as e:
        error_msg = str(e)
        if "Connection error" in error_msg or "ConnectError" in error_msg or "WinError 10061" in error_msg:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "LLM 服务不可用",
                    "suggestion": "请检查 backend/.env 中的 LLM_API_KEY / LLM_BASE_URL 配置，确认模型服务已启动。",
                    "hint": f"当前 LLM_BASE_URL={os.getenv('LLM_BASE_URL', '<未配置>')}，LLM_MODEL={os.getenv('LLM_MODEL', '<未配置>')}。",
                },
            )
        raise HTTPException(
            status_code=400,
            detail={"code": "ANNOTATE_FAILED", "error": error_msg, "suggestion": "请检查模型、API 地址和服务日志后重试。"},
        )


@app.get("/api/llm/models")
def api_llm_models():
    """通过已配置的 OpenAI-compatible API 获取可用模型。"""
    try:
        models = get_client().models.list()
        model_ids = sorted({item.id for item in models.data if getattr(item, "id", None)})
        return {"models": model_ids, "default_model": get_default_model()}
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "LLM_MODELS_UNAVAILABLE", "error": str(e), "suggestion": "无法读取模型列表，可手动检查 LLM_BASE_URL 和 API Key。"},
        )


@app.post("/api/papers/annotate-all")
def api_annotate_all(req: EnhanceRequest):
    if req.project_id:
        _require_project(req.project_id)
    kwargs = {"model": req.model, "db_path": DB_PATH}
    if req.project_id:
        kwargs["project_id"] = req.project_id
    count = annotate_all(**kwargs)
    return {"annotated_count": count}


@app.post("/api/papers/batch-annotate")
def api_batch_annotate(req: EnhanceRequest):
    """批量标注所有未标注论文。"""
    kwargs = {"model": req.model, "db_path": DB_PATH}
    if req.project_id:
        kwargs["project_id"] = req.project_id
    count = annotate_all(**kwargs)
    return {"annotated_count": count}


@app.post("/api/papers/batch-ingest")
def api_batch_ingest(req: BatchIngestRequest):
    """批量入库论文 ID 列表。"""
    results = []
    for paper_id in req.paper_ids:
        try:
            # 解析 arxiv ID
            arxiv_id = paper_id.replace("arxiv_", "")
            paper_id_new = ingest_arxiv_id(arxiv_id, DB_PATH, download_pdf=req.download_pdf, pdf_dir=DATA_DIR / "pdfs")
            _assign_paper(req.project_id, paper_id_new)
            results.append({"id": paper_id, "status": "success", "paper_id": paper_id_new})
        except Exception as e:
            results.append({"id": paper_id, "status": "error", "error": str(e)})
    return {"results": results}


@app.post("/api/papers/{paper_id}/download-pdf")
def api_download_pdf(paper_id: str):
    """下载论文 PDF。"""
    try:
        arxiv_id = paper_id.replace("arxiv_", "")
        client = arxiv.Client(page_size=1, delay_seconds=1)
        search = arxiv.Search(id_list=[arxiv_id])
        results = list(client.results(search))
        if not results:
            raise HTTPException(status_code=404, detail="论文不存在")

        paper = results[0]
        pdf_dir = DATA_DIR / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_file = pdf_dir / f"{paper_id}.pdf"
        if not pdf_file.exists():
            _download_arxiv_pdf(paper, pdf_file)

        # 更新数据库中的 pdf_path
        conn = get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE papers SET pdf_path = ? WHERE id = ?", (str(pdf_file.resolve()), paper_id))
        conn.commit()
        conn.close()

        return {"status": "success", "pdf_path": str(pdf_file.resolve())}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────
# 图谱 API
# ──────────────────────────────

@app.get("/api/graph/team")
def api_graph_team(project_id: Optional[str] = None):
    init_db(DB_PATH)
    if project_id:
        _require_project(project_id)
    graph = build_team_graph(DB_PATH, project_id=project_id)
    return {
        "nodes": [{"id": n, **graph.nodes[n]} for n in graph.nodes()],
        "edges": [{"source": u, "target": v, **graph.edges[u, v]} for u, v in graph.edges()],
    }


@app.get("/api/graph/team-ego")
def api_graph_team_ego(project_id: Optional[str] = None):
    """返回 Louvain 推断团队与关联论文组成的异构图。"""
    init_db(DB_PATH)
    if project_id:
        _require_project(project_id)
    graph = build_team_ego_graph(DB_PATH, project_id=project_id)
    return {
        "nodes": [{"id": n, **graph.nodes[n]} for n in graph.nodes()],
        "edges": [{"source": u, "target": v, **graph.edges[u, v]} for u, v in graph.edges()],
    }


@app.get("/api/graph/paper")
def api_graph_paper(project_id: Optional[str] = None):
    init_db(DB_PATH)
    if project_id:
        _require_project(project_id)
    graph = build_paper_graph(DB_PATH, project_id=project_id)
    return {
        "nodes": [{"id": n, **graph.nodes[n]} for n in graph.nodes()],
        "edges": [{"source": u, "target": v, **graph.edges[u, v]} for u, v in graph.edges()],
    }


@app.post("/api/papers/{paper_id}/sync-citations")
def api_sync_citations(paper_id: str):
    """从 Semantic Scholar 同步引用数及一阶引用邻域。"""
    try:
        return sync_citations(paper_id, DB_PATH)
    except CitationSyncError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/papers/sync-citation-metrics")
def api_sync_citation_metrics(project_id: Optional[str] = None):
    try:
        return sync_citation_metrics(DB_PATH, project_id)
    except CitationSyncError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/graph/citation")
def api_graph_citation(paper_id: str, limit_per_direction: int = 12):
    graph = build_citation_graph(
        paper_id,
        DB_PATH,
        limit_per_direction=max(0, min(limit_per_direction, 30)),
    )
    return {
        "nodes": [{"id": n, **graph.nodes[n]} for n in graph.nodes()],
        "edges": [{"source": u, "target": v, **graph.edges[u, v]} for u, v in graph.edges()],
    }


@app.get("/api/graph/similarity")
def api_graph_similarity(paper_id: str):
    graph = build_similarity_graph(paper_id, DB_PATH)
    return {
        "nodes": [{"id": n, **graph.nodes[n]} for n in graph.nodes()],
        "edges": [{"source": u, "target": v, **graph.edges[u, v]} for u, v in graph.edges()],
    }


# ──────────────────────────────
# 聊天 API（混合模式 + 会话管理 + 流式）
# ──────────────────────────────


def _derive_session_title(message: str) -> str:
    """根据用户第一条消息生成会话标题（前 10 个字，不足取全部）。"""
    text = message.strip().replace("\n", " ").replace("\r", "")
    if not text:
        return "未命名会话"
    return text[:10]


def _chat_generate(message: str, history: Optional[list[dict]] = None, project_id: Optional[str] = None) -> ChatResponse:
    result = run_agent(message, history=history, project_id=project_id)
    return ChatResponse(
        mode=result.get("mode", "agent"),
        answer=result.get("answer", ""),
        papers=result.get("papers", []),
        tool_calls=result.get("tool_calls", []),
    )


@app.get("/api/chat/sessions")
def api_list_chat_sessions(project_id: Optional[str] = None):
    init_db(DB_PATH)
    if project_id:
        _require_project(project_id)
    conn = get_connection(DB_PATH)
    try:
        sessions = list_chat_sessions(conn, project_id=project_id)
        return sessions
    finally:
        conn.close()


@app.post("/api/chat/sessions", response_model=ChatSessionResponse)
def api_create_chat_session(req: ChatSessionCreate):
    init_db(DB_PATH)
    session_id = f"session_{int(__import__('time').time() * 1000)}"
    conn = get_connection(DB_PATH)
    try:
        project_id = _resolve_project_id(req.project_id)
        _require_project(project_id)
        create_chat_session(conn, session_id, req.title, project_id=project_id)
        session = get_chat_session(conn, session_id)
        return session
    finally:
        conn.close()


@app.delete("/api/chat/sessions/{session_id}")
def api_delete_chat_session(session_id: str):
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        delete_chat_session(conn, session_id)
        return {"status": "deleted"}
    finally:
        conn.close()


@app.patch("/api/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def api_rename_chat_session(session_id: str, req: ChatSessionRename):
    """重命名会话。"""
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        update_chat_session_title(conn, session_id, req.title.strip())
        session = get_chat_session(conn, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        return session
    finally:
        conn.close()


@app.get("/api/chat/sessions/{session_id}/messages")
def api_get_chat_messages(session_id: str):
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        messages = get_chat_messages(conn, session_id)
        return messages
    finally:
        conn.close()


@app.post("/api/chat/sessions/{session_id}/messages", response_model=ChatResponse)
def api_chat_session_message(session_id: str, req: ChatRequest):
    """会话内发送消息（非流式）。"""
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        project_id = _resolve_project_id(req.project_id)
        _require_project(project_id)
        create_chat_session(conn, session_id, project_id=project_id)
        session = get_chat_session(conn, session_id)
        if req.project_id and session.get("project_id") != req.project_id:
            raise HTTPException(status_code=404, detail="会话不属于当前项目")
        project_id = session.get("project_id") or project_id
        if not session.get("title"):
            update_chat_session_title(conn, session_id, _derive_session_title(req.message))
        history = [
            {"role": message["role"], "content": message["content"]}
            for message in get_chat_messages(conn, session_id)
        ]
        add_chat_message(conn, f"msg_{int(__import__('time').time() * 1000)}_{req.message[:8]}", session_id, "user", req.message)
    finally:
        conn.close()

    if req.project_id:
        response = _chat_generate(req.message, history=history, project_id=project_id)
    else:
        response = _chat_generate(req.message, history=history)

    conn = get_connection(DB_PATH)
    try:
        add_chat_message(
            conn,
            f"msg_{int(__import__('time').time() * 1000)}_assistant",
            session_id,
            "assistant",
            response.answer,
            json.dumps(response.papers, ensure_ascii=False, default=str),
            json.dumps(response.tool_calls, ensure_ascii=False, default=str),
        )
    finally:
        conn.close()

    return response


@app.post("/api/chat", response_model=ChatResponse)
def api_chat_legacy(req: ChatRequest):
    """兼容旧客户端，消息统一写入 default 会话。"""
    return api_chat_session_message("default", req)


@app.post("/api/chat/sessions/{session_id}/messages/stream")
async def api_chat_session_stream(session_id: str, req: ChatRequest):
    """会话内发送消息（流式输出）。"""
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        project_id = _resolve_project_id(req.project_id)
        _require_project(project_id)
        create_chat_session(conn, session_id, project_id=project_id)
        session = get_chat_session(conn, session_id)
        if req.project_id and session.get("project_id") != req.project_id:
            raise HTTPException(status_code=404, detail="会话不属于当前项目")
        project_id = session.get("project_id") or project_id
        if not session.get("title"):
            update_chat_session_title(conn, session_id, _derive_session_title(req.message))
        history = [
            {"role": message["role"], "content": message["content"]}
            for message in get_chat_messages(conn, session_id)
        ]
        add_chat_message(conn, f"msg_{int(__import__('time').time() * 1000)}_{req.message[:8]}", session_id, "user", req.message)
    finally:
        conn.close()

    async def generate():
        answer = ""
        papers: list[dict] = []
        tool_calls: list[dict] = []

        async for event in run_agent_stream(req.message, history=history, project_id=project_id):
            yield event
            # 解析最终答案以便落库
            data = json.loads(event.replace("data: ", ""))
            if data.get("type") == "answer":
                answer = data.get("content", "")
                papers = data.get("papers", [])
                tool_calls = data.get("tool_calls", [])

        conn = get_connection(DB_PATH)
        try:
            add_chat_message(
                conn,
                f"msg_{int(__import__('time').time() * 1000)}_assistant",
                session_id,
                "assistant",
                answer,
                json.dumps(papers, ensure_ascii=False, default=str),
                json.dumps(tool_calls, ensure_ascii=False, default=str),
            )
        finally:
            conn.close()

    from fastapi.responses import StreamingResponse
    return StreamingResponse(generate(), media_type="text/event-stream; charset=utf-8")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/health")
def health_legacy():
    llm_configured = bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_BASE_URL"))
    return {
        "status": "ok",
        "llm_configured": llm_configured,
        "model": os.getenv("LLM_MODEL", "step-3.7-flash"),
    }


def _cleanup_logs(max_mb: int = 5) -> None:
    """启动时清理过大的 server.log，避免无限增长。"""
    log_path = BASE_DIR / "server.log"
    if not log_path.exists():
        return
    size_mb = log_path.stat().st_size / (1024 * 1024)
    if size_mb > max_mb:
        log_path.write_text("", encoding="utf-8")


_cleanup_logs()


# ──────────────────────────────
# 笔记 API
# ──────────────────────────────

@app.get("/api/notes")
def api_list_notes(project_id: Optional[str] = None):
    init_db(DB_PATH)
    if project_id:
        _require_project(project_id)
    result = list_notes(DB_PATH, project_id=project_id)
    return result


@app.get("/api/notes/{paper_id}")
def api_get_note(paper_id: str):
    init_db(DB_PATH)
    result = get_note(DB_PATH, paper_id)
    if not result:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return result


@app.post("/api/notes/{paper_id}")
def api_save_note(paper_id: str, req: dict):
    init_db(DB_PATH)
    content = req.get("content", "")
    result = notes_save(DB_PATH, paper_id, content)
    return result


@app.post("/api/notes/{paper_id}/template")
def api_create_note_template(paper_id: str):
    init_db(DB_PATH)
    result = create_note_template(DB_PATH, paper_id)
    return result


@app.delete("/api/notes/{paper_id}")
def api_delete_note(paper_id: str):
    init_db(DB_PATH)
    result = notes_delete(DB_PATH, paper_id)
    return result
    if req.project_id:
        _require_project(req.project_id)
