#!/usr/bin/env python3
"""离线核对 CiteMap 与 llm-paper-radar 的确定性算法配置。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from paper_graph.explore_algorithms import (  # noqa: E402
    MILESTONE_COOLDOWN_DAYS,
    MILESTONE_STARS_MIN,
    MILESTONE_TRENDING_IDS,
    MILESTONE_TRENDING_RANK_MAX,
    PREFILTER_BLACKLIST,
    PREFILTER_MAX_BLACKLIST_HITS,
    PREFILTER_WHITELIST,
    RELEVANCE_WEIGHT,
    SOURCE_PRIORITY,
    STAR_BONUS_CAP,
    STAR_WEIGHT,
    TOPIC_CAPS,
    TRENDING_BONUS_CAP,
)
from paper_graph.explore_sources import WATCHED_AUTHORS  # noqa: E402
from paper_graph.settings import SETTING_DEFAULTS  # noqa: E402


def literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return ast.literal_eval(node.value)
    raise KeyError(f"{path}: missing assignment {name}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    args = parser.parse_args()
    reference = args.reference.resolve()
    config = yaml.safe_load((reference / "config.yaml").read_text())

    ref_filter = reference / "pipeline" / "filter.py"
    ref_render = reference / "pipeline" / "render.py"
    reference_milestones = {
        str(seed["id"]).split(":")[-1]
        for seed in yaml.safe_load((reference / "seeds.yaml").read_text()).get("seeds", [])
        if seed.get("category") == "trending"
    }
    reference_authors = tuple(
        (item["name"], item.get("affiliation", ""))
        for item in config["sources"]["arxiv_authors"]["authors"]
    )
    reference_venues = tuple(config["sources"]["openreview"]["venues"])
    citemap_venues = tuple(
        item.strip()
        for item in SETTING_DEFAULTS["EXPLORE_OPENREVIEW_VENUES"].split(",")
    )
    reference_caps = config["render"]["topic_caps"]
    prefilter = config["filter"]["prefilter"]

    checks = {
        "relevance prompt SHA-256": digest(reference / "prompts" / "relevance.md") == digest(BACKEND / "paper_graph" / "prompts" / "explore_relevance.md"),
        "summary prompt SHA-256": digest(reference / "prompts" / "summary.md") == digest(BACKEND / "paper_graph" / "prompts" / "explore_summary.md"),
        "venue relevance prompt SHA-256": digest(reference / "prompts" / "inference_relevance.md") == digest(BACKEND / "paper_graph" / "prompts" / "venue_inference_relevance.md"),
        "source priority": tuple(config["dedupe"]["source_priority"]) == SOURCE_PRIORITY,
        "topic caps": reference_caps == TOPIC_CAPS,
        "prefilter whitelist": tuple(item["pattern"] for item in prefilter["whitelist"]) == PREFILTER_WHITELIST,
        "prefilter blacklist": tuple(item["pattern"] for item in prefilter["blacklist"]) == PREFILTER_BLACKLIST,
        "prefilter threshold": prefilter["max_blacklist_hits"] == PREFILTER_MAX_BLACKLIST_HITS,
        "watched authors": reference_authors == WATCHED_AUTHORS,
        "OpenReview venues": reference_venues == citemap_venues,
        "milestone IDs": reference_milestones == MILESTONE_TRENDING_IDS,
        "milestone rank": literal_assignment(ref_filter, "MILESTONE_TRENDING_RANK_MAX") == MILESTONE_TRENDING_RANK_MAX,
        "milestone stars": literal_assignment(ref_filter, "MILESTONE_STARS_MIN") == MILESTONE_STARS_MIN,
        "milestone cooldown": literal_assignment(ref_filter, "MILESTONE_COOLDOWN_DAYS") == MILESTONE_COOLDOWN_DAYS,
        "relevance weight": literal_assignment(ref_render, "RELEVANCE_WEIGHT") == RELEVANCE_WEIGHT,
        "trending rank cap": literal_assignment(ref_render, "TRENDING_BONUS_CAP") == TRENDING_BONUS_CAP,
        "star weight": literal_assignment(ref_render, "STAR_WEIGHT") == STAR_WEIGHT,
        "star bonus cap": literal_assignment(ref_render, "STAR_BONUS_CAP") == STAR_BONUS_CAP,
    }

    print(f"reference={reference}")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    failures = [name for name, passed in checks.items() if not passed]
    print(f"summary={len(checks) - len(failures)}/{len(checks)} passed")
    if failures:
        print("failed=" + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
