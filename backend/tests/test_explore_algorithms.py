import math

from paper_graph.explore_algorithms import (
    STAR_BONUS_CAP,
    composite_relevance,
    group_with_caps,
    heat_score,
    merge_candidates,
    milestone_override,
    prefilter_verdict,
    ranking_score,
)


def test_prefilter_uses_word_boundaries():
    _, hits, _ = prefilter_verdict(
        "Equipping language models",
        "A paper about equipping models.",
        whitelist=["QuIP"],
        blacklist=[],
    )
    assert hits == []
    _, hits, _ = prefilter_verdict(
        "QuIP for LLMs",
        "A quantization paper.",
        whitelist=["QuIP"],
        blacklist=[],
    )
    assert hits == ["QuIP"]


def test_prefilter_requires_two_blacklist_hits_without_whitelist():
    gated, whitelist, blacklist = prefilter_verdict(
        "Image classification",
        "Evaluation on CIFAR.",
        whitelist=["PTQ"],
        blacklist=["image classification", "CIFAR"],
        max_blacklist_hits=2,
    )
    assert gated is True
    assert whitelist == []
    assert blacklist == ["image classification", "CIFAR"]


def test_prefilter_whitelist_defers_to_judge():
    gated, whitelist, blacklist = prefilter_verdict(
        "PTQ for image classification",
        "Evaluation on CIFAR.",
        whitelist=["PTQ"],
        blacklist=["image classification", "CIFAR"],
        max_blacklist_hits=2,
    )
    assert gated is False
    assert whitelist == ["PTQ"]
    assert len(blacklist) == 2


def test_heat_and_ranking_match_reference_formula():
    sources = [
        {
            "source": "hf_daily",
            "metadata": {"trending_rank": 2, "upvotes": 10},
        }
    ]
    expected_heat = 50 + 10 + min(math.log(1001) * 3, STAR_BONUS_CAP)
    assert abs(heat_score(sources, {"stars": 1000}) - expected_heat) < 0.01
    assert ranking_score(9, 2) == 272
    assert heat_score(
        [{"source": "hf_daily", "metadata": {"trending_rank": 31}}],
        None,
    ) == 0


def test_merge_uses_reference_source_priority():
    merged = merge_candidates(
        [
            {
                "arxiv_id": "X",
                "source": "arxiv",
                "title": "arxiv title",
                "abstract": "arxiv abstract",
                "authors": ["A"],
                "categories": ["cs.LG"],
            },
            {
                "arxiv_id": "X",
                "source": "hf_daily",
                "title": "hf title",
                "abstract": "hf abstract",
                "authors": [],
                "categories": [],
                "source_metadata": {"upvotes": 42},
            },
        ]
    )
    assert len(merged) == 1
    assert merged[0]["title"] == "hf title"
    assert merged[0]["abstract"] == "hf abstract"
    assert merged[0]["authors"] == ["A"]
    assert {item["source"] for item in merged[0]["sources"]} == {"arxiv", "hf_daily"}


def test_composite_bucket_caps_and_milestone_override():
    assert composite_relevance(
        {"hard_gate": False, "topic_relevance": 5, "practicality": 4}
    ) == 9
    assert composite_relevance(
        {"hard_gate": True, "topic_relevance": 5, "practicality": 5}
    ) == 0
    papers = [{"id": str(index), "topic_bucket": "ptq"} for index in range(10)]
    assert len(group_with_caps(papers, {"ptq": 3, "_default": 2})["ptq"]) == 3
    override = milestone_override(
        "2309.06180",
        [{"source": "hf_daily", "metadata": {"trending_rank": 10}}],
        None,
    )
    assert override is not None
    assert override["topic_bucket"] == "trending"
    assert override["hard_gate"] is False
    assert milestone_override(
        "2309.06180",
        [{"source": "hf_daily", "metadata": {"trending_rank": 10}}],
        None,
        frozenset({"2309.06180"}),
    ) is None
