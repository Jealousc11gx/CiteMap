"""Explore 的确定性算法。

算法语义移植自 llm-paper-radar，CiteMap 仅适配 dict 与 SQLite 数据结构。
参考 commit: dc1e54afcfefb3579aae43ddc4b056fda24e2d0a。
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from functools import lru_cache

SOURCE_PRIORITY = ("hf_daily", "openreview", "arxiv_authors", "arxiv")

BUCKET_ORDER = (
    "ptq",
    "low_bits",
    "qat",
    "kv_cache",
    "pruning_distill",
    "diffusion",
    "trending",
    "survey",
)
BUCKET_TITLES = {
    "ptq": "PTQ（训练后量化）",
    "low_bits": "Low-bit（<= 2-bit）",
    "qat": "QAT（量化感知训练）",
    "kv_cache": "KV cache 压缩",
    "pruning_distill": "Pruning / 蒸馏",
    "diffusion": "Diffusion",
    "trending": "Trending / 高热度但未归桶",
    "survey": "Survey / 方法论与对比",
}
TOPIC_CAPS = {
    "ptq": 8,
    "low_bits": 5,
    "qat": 5,
    "kv_cache": 5,
    "pruning_distill": 3,
    "diffusion": 3,
    "trending": 3,
    "survey": 3,
    "_default": 2,
}

TRENDING_BONUS_CAP = 30
RELEVANCE_WEIGHT = 30
STAR_WEIGHT = 3.0
STAR_BONUS_CAP = 25.0

MILESTONE_TRENDING_RANK_MAX = 20
MILESTONE_STARS_MIN = 5000
MILESTONE_COOLDOWN_DAYS = 14
MILESTONE_TRENDING_IDS = frozenset(
    {
        "2602.06036",
        "2605.12825",
        "2309.06180",
        "2205.14135",
        "2307.08691",
        "2407.08608",
        "2401.15077",
        "2406.16858",
        "2401.10774",
        "2402.02057",
        "2312.07104",
    }
)

PREFILTER_MAX_BLACKLIST_HITS = 2
PREFILTER_WHITELIST = (
    "post-training quantization",
    "PTQ",
    "weight-only quantization",
    "activation quantization",
    "low-bit quantization",
    "1-bit",
    "1.58-bit",
    "2-bit",
    "ternary",
    "binary",
    "W4A16",
    "W4A4",
    "W4A8",
    "W8A8",
    "INT4",
    "FP4",
    "FP8",
    "MXFP4",
    "MXFP6",
    "NVFP4",
    "MXINT",
    "microscaling",
    "block floating point",
    "GPTQ",
    "AWQ",
    "SmoothQuant",
    "OmniQuant",
    "QuaRot",
    "SpinQuant",
    "QuIP",
    "AQLM",
    "VPTQ",
    "BitNet",
    "QServe",
    "KIVI",
    "KVQuant",
    "Wanda",
    "SparseGPT",
    "KV cache quantization",
    "KV-cache quantization",
    "KV compression",
    "calibration",
    "no retraining",
    "training-free",
    "data-free",
)
PREFILTER_BLACKLIST = (
    "image classification",
    "object detection",
    "semantic segmentation",
    "ImageNet",
    "CIFAR",
    "federated learning",
    "speech recognition",
    "graph neural network",
    "agent framework",
    "RAG",
    "retrieval-augmented",
    "BERT-base",
    "BERT-large",
    "machine translation",
    "convergence proof",
    "self-explanation",
    "self-explanations",
    "video diffusion",
    "video generation",
    "world model",
    "any-step",
    "flow map",
)

BREAKDOWN_FIELDS = (
    "hard_gate",
    "topic_relevance",
    "practicality",
    "compression_type",
    "topic_bucket",
    "model_domain",
    "format_or_method",
    "largest_model_tested",
    "accuracy_benchmarks",
    "accuracy_summary",
    "inference_perf",
    "calibration_cost",
    "peak_memory",
)


@lru_cache(maxsize=None)
def _compiled(pattern: str) -> re.Pattern[str]:
    lowered = pattern.lower()
    left = r"(?<![a-z0-9])" if lowered and lowered[0].isalnum() else ""
    right = r"(?![a-z0-9])" if lowered and lowered[-1].isalnum() else ""
    return re.compile(left + re.escape(lowered) + right)


def _matches(pattern: str, text: str) -> bool:
    return _compiled(pattern).search(text) is not None


def prefilter_verdict(
    title: str,
    abstract: str,
    *,
    whitelist: Iterable[str] = PREFILTER_WHITELIST,
    blacklist: Iterable[str] = PREFILTER_BLACKLIST,
    max_blacklist_hits: int = PREFILTER_MAX_BLACKLIST_HITS,
) -> tuple[bool, list[str], list[str]]:
    """返回 `(should_hard_gate, whitelist_hits, blacklist_hits)`。"""
    text = f"{title}\n{abstract}".lower()
    whitelist_hits = [pattern for pattern in whitelist if _matches(pattern, text)]
    blacklist_hits = [pattern for pattern in blacklist if _matches(pattern, text)]
    should_gate = (not whitelist_hits) and len(blacklist_hits) >= max_blacklist_hits
    return should_gate, whitelist_hits, blacklist_hits


def hard_gate_result(reason: str) -> dict:
    return {
        "hard_gate": True,
        "topic_relevance": 0,
        "practicality": 0,
        "compression_type": "unknown",
        "topic_bucket": "unknown",
        "model_domain": "unknown",
        "format_or_method": "unknown",
        "largest_model_tested": "unknown",
        "accuracy_benchmarks": "none",
        "accuracy_summary": "unknown",
        "inference_perf": "unknown",
        "calibration_cost": "unknown",
        "peak_memory": "unknown",
        "reason": reason,
    }


def prefilter_hard_gate_result(blacklist_hits: list[str]) -> dict:
    return hard_gate_result(f"prefilter: 命中黑名单 {', '.join(blacklist_hits[:3])}")


def judge_unavailable_result(error: Exception) -> dict:
    reason = f"judge unavailable: {type(error).__name__}: {error}"[:200]
    return hard_gate_result(reason)


def _clip(value: object, low: int = 0, high: int = 5) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, parsed))


def composite_relevance(result: dict) -> int:
    if result.get("hard_gate"):
        return 0
    return _clip(result.get("topic_relevance")) + _clip(result.get("practicality"))


def normalize_breakdown(result: dict) -> dict:
    return {field: result.get(field) for field in BREAKDOWN_FIELDS}


def merge_candidates(candidates: list[dict], source_priority: Iterable[str] = SOURCE_PRIORITY) -> list[dict]:
    """按 canonical ID 合并来源；共享字段取最高优先级来源。"""
    grouped: dict[str, list[dict]] = {}
    for candidate in candidates:
        grouped.setdefault(str(candidate["arxiv_id"]), []).append(candidate)
    priority = {source: index for index, source in enumerate(source_priority)}
    merged: list[dict] = []
    for group in grouped.values():
        ordered = sorted(group, key=lambda item: priority.get(str(item.get("source")), 999))
        head = dict(ordered[0])
        sources: list[dict] = []
        for item in group:
            sources.append(
                {
                    "source": item.get("source"),
                    "source_rank": item.get("source_rank"),
                    "metadata": dict(item.get("source_metadata") or {}),
                }
            )
        head["sources"] = sources
        for item in ordered[1:]:
            for field in ("title", "abstract", "pdf_url", "code_url", "code_meta"):
                if not head.get(field) and item.get(field):
                    head[field] = item[field]
            if not head.get("authors") and item.get("authors"):
                head["authors"] = item["authors"]
            if not head.get("categories") and item.get("categories"):
                head["categories"] = item["categories"]
        merged.append(head)
    return merged


def star_bonus(code_meta: dict | None) -> float:
    stars = (code_meta or {}).get("stars")
    if not isinstance(stars, int) or stars <= 0:
        return 0.0
    return min(math.log(stars + 1) * STAR_WEIGHT, STAR_BONUS_CAP)


def heat_score(sources: Iterable[dict], code_meta: dict | None = None) -> float:
    """Heat = HF trending bonus + upvotes + GitHub stars bonus。"""
    trending_bonus = 0.0
    hf_upvotes = 0
    for source in sources:
        if source.get("source") != "hf_daily":
            continue
        metadata = source.get("metadata") or {}
        rank = metadata.get("trending_rank")
        if isinstance(rank, int) and rank and rank <= TRENDING_BONUS_CAP:
            trending_bonus = max(trending_bonus, 100.0 / rank)
        upvotes = metadata.get("upvotes", 0) or 0
        if isinstance(upvotes, (int, float)):
            hf_upvotes = max(hf_upvotes, upvotes)
    return trending_bonus + hf_upvotes + star_bonus(code_meta)


def ranking_score(relevance_score: int | float | None, heat: float) -> float:
    return heat + (relevance_score or 0) * RELEVANCE_WEIGHT


def sort_candidates(candidates: Iterable[dict]) -> list[dict]:
    return sorted(
        candidates,
        key=lambda item: (
            ranking_score(item.get("relevance_score"), float(item.get("heat_score") or 0)),
            float(item.get("heat_score") or 0),
        ),
        reverse=True,
    )


def group_with_caps(candidates: Iterable[dict], caps: dict[str, int] | None = None) -> dict[str, list[dict]]:
    effective_caps = caps or TOPIC_CAPS
    grouped = {bucket: [] for bucket in BUCKET_ORDER}
    for candidate in candidates:
        bucket = candidate.get("topic_bucket")
        if bucket in grouped:
            grouped[bucket].append(candidate)
    return {
        bucket: papers[: effective_caps.get(bucket, effective_caps.get("_default", 3))]
        for bucket, papers in grouped.items()
    }


def milestone_override(
    arxiv_id: str,
    sources: Iterable[dict],
    code_meta: dict | None,
    cooldown_ids: frozenset[str] = frozenset(),
) -> dict | None:
    normalized = arxiv_id.split(":")[-1]
    if normalized not in MILESTONE_TRENDING_IDS or normalized in cooldown_ids:
        return None
    hot_trending = any(
        source.get("source") == "hf_daily"
        and isinstance((source.get("metadata") or {}).get("trending_rank"), int)
        and (source.get("metadata") or {})["trending_rank"] <= MILESTONE_TRENDING_RANK_MAX
        for source in sources
    )
    stars = (code_meta or {}).get("stars")
    hot_stars = isinstance(stars, int) and stars >= MILESTONE_STARS_MIN
    if not (hot_trending or hot_stars):
        return None
    return {
        "hard_gate": False,
        "topic_relevance": 4,
        "practicality": 4,
        "compression_type": "trending",
        "topic_bucket": "trending",
        "model_domain": "language",
        "format_or_method": "milestone framework",
        "largest_model_tested": "production-deployed",
        "accuracy_benchmarks": "n/a (infra paper)",
        "accuracy_summary": "milestone framework, no compression accuracy metric",
        "inference_perf": "real-world deployed at scale",
        "calibration_cost": "n/a",
        "peak_memory": "n/a",
        "reason": (
            "milestone-override: seeds.yaml-curated trending milestone "
            "(vLLM/FlashAttention/EAGLE/Medusa/Lookahead/SGLang class) "
            "with HF trending rank <= 20 or code_meta.stars >= 5000"
        ),
    }
