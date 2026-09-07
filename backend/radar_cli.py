"""GitHub Actions 论文雷达入口。

该入口不读取本机 SQLite。Action 只通过 Radar Store 获取项目 profile、写入候选、发邮件。
"""

from __future__ import annotations

import os
from datetime import date

from paper_graph.radar import candidate_matches_config, fetch_arxiv_candidates
from paper_graph.radar_embeddings import get_embedding_provider
from paper_graph.radar_mail import send_radar_email
from paper_graph.radar_llm import enrich_with_tldr
from paper_graph.radar_ranking import rank_candidates
from paper_graph.radar_sync import RadarRemoteClient


HISTORICAL_TEST_CANDIDATE = {
    "arxiv_id": "2508.13434",
    "title": "EventTSF: Event-Aware Non-Stationary Time Series Forecasting",
    "abstract": (
        "Time series forecasting is vital in diverse sectors such as energy and transportation, "
        "where non-stationary dynamics are deeply intertwined with external events in other modalities "
        "such as texts. EventTSF integrates historical time series and textual events via step-wise "
        "diffusion and uses an event-aware flow-matching timestep conditioned on event semantics. "
        "Experiments on synthetic and real-world datasets report gains in probabilistic and deterministic forecasting."
    ),
    "authors": ["Yunfeng Ge", "Ming Jin", "Yiji Zhao", "Hongyan Li", "Bo Du", "Chang Xu", "Shirui Pan"],
    "categories": ["cs.LG", "cs.AI"],
    "primary_category": "cs.LG",
    "published_date": "2025-08-19",
    "updated_date": "2026-05-10",
    "arxiv_url": "https://arxiv.org/abs/2508.13434",
    "pdf_url": "https://arxiv.org/pdf/2508.13434",
}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def run_remote_radar() -> dict:
    base_url = os.environ.get("RADAR_REMOTE_URL", "").strip()
    token = os.environ.get("RADAR_REMOTE_TOKEN", "").strip()
    if not base_url or not token:
        raise RuntimeError("未配置 RADAR_REMOTE_URL / RADAR_REMOTE_TOKEN")
    client = RadarRemoteClient(base_url, token)
    projects_payload = client._request("GET", "/profiles")
    sent = 0
    projects = projects_payload.get("projects") or []
    test_mode = _env_bool("RADAR_TEST_MODE")
    use_historical_test = test_mode and _env_bool("RADAR_TEST_USE_HISTORICAL")
    debug = _env_bool("RADAR_DEBUG")
    if debug:
        print(f"[radar] projects={len(projects)} test_mode={test_mode}")
    if test_mode and not projects:
        raise RuntimeError("Radar Test 无法执行：云端没有项目 profile")
    for project in projects:
        if not project.get("enabled", False):
            continue
        project_id = project["project_id"]
        fetch_limit = int(project.get("fetch_limit", 100))
        top_k = int(project.get("top_k", 10))
        if test_mode:
            fetch_limit = min(fetch_limit, int(os.getenv("RADAR_TEST_MAX_RESULTS", "5")))
            top_k = min(top_k, int(os.getenv("RADAR_TEST_TOP_K", "3")))
        candidates = fetch_arxiv_candidates(
            project.get("categories") or [],
            max_results=fetch_limit,
            include_cross_list=bool(project.get("include_cross_list", True)),
        )
        candidates = [candidate for candidate in candidates if candidate_matches_config(candidate, project)]
        if use_historical_test and not candidates:
            candidates = [dict(HISTORICAL_TEST_CANDIDATE)]
            if debug:
                print(f"[radar] project={project_id} using_historical_test=2508.13434")
        if debug:
            print(f"[radar] project={project_id} candidates_after_filter={len(candidates)}")
        references = project.get("reference_papers") or []
        if not references:
            continue
        ranked = rank_candidates(
            candidates,
            references,
            embedding_provider=get_embedding_provider(),
            anchor_ids=set(project.get("anchor_paper_ids") or []),
            anchor_bonus=float(project.get("anchor_bonus", 0.1)),
            top_k=top_k,
            min_score=float(project.get("min_score", 0.0)),
        )
        if debug:
            print(f"[radar] project={project_id} ranked={len(ranked)}")
        if not ranked:
            if project.get("send_empty"):
                send_radar_email([], subject=f"CiteMap 论文雷达 {date.today().isoformat()}")
            continue
        payload = []
        for item in ranked:
            item["project_id"] = project_id
            payload.append(item)
        enrich_with_tldr(payload)
        created = client.create_items(payload)
        new_items = created.get("new_items") or []
        email_items = new_items or (payload if test_mode else [])
        if email_items:
            subject_prefix = "CiteMap 论文雷达测试" if test_mode else "CiteMap 论文雷达"
            send_radar_email(email_items, subject=f"{subject_prefix} {date.today().isoformat()}")
            if new_items:
                client._request("POST", "/items/emailed", {"items": [{"project_id": project_id, "arxiv_id": item["arxiv_id"]} for item in new_items]})
            sent += len(email_items)
    return {"projects": len(projects), "sent": sent, "test_mode": test_mode}


if __name__ == "__main__":
    print(run_remote_radar())
