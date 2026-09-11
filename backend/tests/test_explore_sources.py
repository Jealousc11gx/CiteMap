from datetime import date

from paper_graph.explore_sources import (
    _expand_venues,
    _normalize_author,
    fetch_watched_authors,
    hf_candidate_in_window,
    parse_trending_ranks,
)


def test_trending_rank_keeps_first_unique_occurrence():
    html = (
        '<a href="/papers/2601.00001">one</a>'
        '<a href="/papers/2601.00001">duplicate</a>'
        '<a href="/papers/2601.00002">two</a>'
    )
    assert parse_trending_ranks(html) == {
        "2601.00001": 1,
        "2601.00002": 2,
    }


def test_watched_author_normalization_handles_last_first():
    assert _normalize_author("van Baalen, Mart") == "mart van baalen"
    assert _normalize_author("  Mart   van Baalen ") == "mart van baalen"


async def test_empty_watched_author_list_returns_without_request():
    assert await fetch_watched_authors(authors=[]) == []


def test_openreview_venue_templates_expand_current_and_next_year():
    assert _expand_venues(
        ("ICLR.cc/{year}/Conference", "EMNLP/2026/Conference"),
        2026,
    ) == [
        "ICLR.cc/2026/Conference",
        "ICLR.cc/2027/Conference",
        "EMNLP/2026/Conference",
    ]


def test_hf_window_rejects_old_and_future_papers_by_default():
    target = date(2026, 9, 10)
    assert hf_candidate_in_window(date(2026, 8, 20), target, 30, "2608.00001")
    assert not hf_candidate_in_window(date(2023, 7, 1), target, 30, "2307.00001")
    assert not hf_candidate_in_window(date(2026, 9, 11), target, 30, "2609.00001")


def test_hf_window_allows_explicit_historical_milestone():
    assert hf_candidate_in_window(
        date(2023, 7, 1),
        date(2026, 9, 10),
        30,
        "2307.08691",
        frozenset({"2307.08691"}),
    )
