"""llm-paper-radar 多源采集的 CiteMap 适配。"""

from __future__ import annotations

import asyncio
import os
import random
import re
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from typing import Callable

import feedparser
import httpx

ARXIV_USER_AGENT = "CiteMap/0.4 llm-paper-radar-adapter"
ARXIV_API_URL = "http://export.arxiv.org/api/query"
ARXIV_OAI_URL = "https://export.arxiv.org/oai2"
ARXIV_RETRY_WAITS = (5, 10, 20, 40, 80, 160, 300)
TRENDING_LINK_RE = re.compile(r'href="/papers/(\d{4}\.\d{4,5})"')
ARXIV_ID_RE = re.compile(r"abs/([\d.]+)(?:v\d+)?$")

OPENREVIEW_VENUES = (
    "ICLR.cc/{year}/Conference",
    "ICML.cc/{year}/Conference",
    "NeurIPS.cc/{year}/Conference",
    "MLSys.org/{year}/Conference",
    "AAAI.org/{year}/Conference",
    "aclweb.org/ACL/{year}/Conference",
    "EMNLP/{year}/Conference",
)
WATCHED_AUTHORS = (
    ("Dan Alistarh", "IST Austria"),
    ("Song Han", "MIT HAN Lab"),
    ("Markus Nagel", "Qualcomm AI Research"),
    ("Mart van Baalen", "Qualcomm AI Research"),
    ("Yelysei Bondarenko", "Qualcomm AI Research"),
    ("Marios Fournarakis", "Qualcomm AI Research"),
    ("Andrey Kuzmin", "Qualcomm AI Research"),
    ("Arash Behboodi", "Qualcomm AI Research"),
    ("Babak Ehteshami Bejnordi", "Qualcomm AI Research"),
    ("Tijmen Blankevoort", "Qualcomm AI Research (alumni)"),
    ("Christos Louizos", "Qualcomm AI Research (alumni)"),
)


class ArxivEmptyResponse(Exception):
    pass


def _target_datetime(target: date | datetime | None = None) -> datetime:
    if target is None:
        target = datetime.now(UTC)
    if isinstance(target, date) and not isinstance(target, datetime):
        return datetime.combine(target, datetime.min.time(), tzinfo=UTC)
    return target.astimezone(UTC) if target.tzinfo else target.replace(tzinfo=UTC)


def _backoff_wait(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    base = ARXIV_RETRY_WAITS[min(attempt, len(ARXIV_RETRY_WAITS) - 1)]
    return base * random.uniform(0.8, 1.2)


async def arxiv_get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    context: str = "arxiv",
    validate: Callable[[httpx.Response], None] | None = None,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(len(ARXIV_RETRY_WAITS)):
        try:
            response = await client.get(url, params=params)
            if response.status_code not in (429, 503):
                response.raise_for_status()
                if validate:
                    validate(response)
                return response
            wait = _backoff_wait(attempt, response.headers.get("Retry-After"))
            last_error = httpx.HTTPStatusError(
                str(response.status_code),
                request=response.request,
                response=response,
            )
        except (httpx.TimeoutException, httpx.TransportError, ArxivEmptyResponse) as exc:
            last_error = exc
            wait = _backoff_wait(attempt, None)
        print(f"{context}: {type(last_error).__name__}，{wait:.0f}s 后重试")
        await asyncio.sleep(wait)
    assert last_error is not None
    raise last_error


def _entry_id(entry: dict) -> str | None:
    match = ARXIV_ID_RE.search(entry.get("id", ""))
    return match.group(1) if match else None


def _entry_date(entry: dict) -> datetime:
    raw = entry.get("published") or entry.get("updated")
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _entry_candidate(entry: dict, source: str, metadata: dict | None = None) -> dict | None:
    arxiv_id = _entry_id(entry)
    if not arxiv_id:
        return None
    categories = [tag["term"] for tag in entry.get("tags", [])]
    pdf_url = next(
        (link["href"] for link in entry.get("links", []) if link.get("type") == "application/pdf"),
        None,
    )
    published = _entry_date(entry)
    return {
        "arxiv_id": arxiv_id,
        "title": entry.get("title", "").strip().replace("\n ", " "),
        "abstract": entry.get("summary", "").strip(),
        "authors": [author.get("name", "") for author in entry.get("authors", [])],
        "categories": categories,
        "published_date": published.date().isoformat(),
        "updated_date": published.date().isoformat(),
        "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": pdf_url or f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "source": source,
        "source_metadata": metadata or {},
    }


async def fetch_arxiv_by_ids(
    ids: list[str],
    *,
    source: str,
    metadata_by_id: dict[str, dict] | None = None,
) -> list[dict]:
    if not ids:
        return []
    async with httpx.AsyncClient(
        timeout=60,
        follow_redirects=True,
        headers={"User-Agent": ARXIV_USER_AGENT},
    ) as client:
        response = await arxiv_get_with_retry(
            client,
            ARXIV_API_URL,
            params={"id_list": ",".join(ids), "max_results": len(ids)},
            context=f"arxiv lookup ({len(ids)})",
        )
    result = []
    for entry in feedparser.parse(response.text).entries:
        arxiv_id = _entry_id(entry)
        candidate = _entry_candidate(
            entry,
            source,
            (metadata_by_id or {}).get(arxiv_id or "", {}),
        )
        if candidate:
            result.append(candidate)
    return result


async def _fetch_arxiv_oai(target: datetime, categories: list[str], max_pages: int = 20) -> list[dict]:
    namespace = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "ar": "http://arxiv.org/OAI/arXiv/",
    }
    target_day = target.date()
    params: dict = {
        "verb": "ListRecords",
        "metadataPrefix": "arXiv",
        "set": "cs",
        "from": target_day.isoformat(),
        "until": (target_day + timedelta(days=3)).isoformat(),
    }
    results = []
    async with httpx.AsyncClient(
        timeout=90,
        follow_redirects=True,
        headers={"User-Agent": ARXIV_USER_AGENT},
    ) as client:
        for page in range(max_pages):
            response = await arxiv_get_with_retry(
                client,
                ARXIV_OAI_URL,
                params=params,
                context=f"arxiv OAI ({page})",
            )
            root = ET.fromstring(response.text)
            for record in root.findall(".//oai:record", namespace):
                header = record.find("oai:header", namespace)
                if header is not None and header.get("status") == "deleted":
                    continue
                metadata = record.find(".//ar:arXiv", namespace)
                if metadata is None:
                    continue
                created = (metadata.findtext("ar:created", "", namespace) or "").strip()
                found_categories = (metadata.findtext("ar:categories", "", namespace) or "").split()
                if created != target_day.isoformat() or not set(categories).intersection(found_categories):
                    continue
                arxiv_id = (metadata.findtext("ar:id", "", namespace) or "").strip()
                if not arxiv_id:
                    continue
                authors = []
                authors_node = metadata.find("ar:authors", namespace)
                if authors_node is not None:
                    for author in authors_node.findall("ar:author", namespace):
                        last = (author.findtext("ar:keyname", "", namespace) or "").strip()
                        first = (author.findtext("ar:forenames", "", namespace) or "").strip()
                        if f"{first} {last}".strip():
                            authors.append(f"{first} {last}".strip())
                results.append(
                    {
                        "arxiv_id": arxiv_id,
                        "title": " ".join((metadata.findtext("ar:title", "", namespace) or "").split()),
                        "abstract": (metadata.findtext("ar:abstract", "", namespace) or "").strip(),
                        "authors": authors,
                        "categories": found_categories,
                        "published_date": created,
                        "updated_date": created,
                        "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
                        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                        "source": "arxiv",
                        "source_metadata": {},
                    }
                )
            token_node = root.find(".//oai:resumptionToken", namespace)
            token = (token_node.text or "").strip() if token_node is not None else ""
            if not token:
                break
            params = {"verb": "ListRecords", "resumptionToken": token}
            await asyncio.sleep(2)
    return results


async def fetch_arxiv_daily(
    categories: list[str],
    *,
    max_results: int = 100,
    target_date: date | datetime | None = None,
) -> list[dict]:
    target = _target_datetime(target_date)
    category_query = "+OR+".join(f"cat:{category}" for category in categories)
    end = target + timedelta(hours=24)
    date_query = (
        f"submittedDate:[{target.strftime('%Y%m%d%H%M')}+TO+"
        f"{end.strftime('%Y%m%d%H%M')}]"
    )
    query = f"({category_query})+AND+{date_query}"
    try:
        entries: list[dict] = []
        async with httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            headers={"User-Agent": ARXIV_USER_AGENT},
        ) as client:
            def validate(response: httpx.Response) -> None:
                feed = feedparser.parse(response.text)
                if feed.entries:
                    return
                total = feed.feed.get("opensearch_totalresults")
                if total is not None and str(total).strip() == "0":
                    return
                raise ArxivEmptyResponse("arxiv 返回空 feed，且没有 totalResults=0")

            page_size = min(200, max_results)
            for page_index in range(5):
                start = page_index * page_size
                if start >= max_results:
                    break
                size = min(page_size, max_results - start)
                url = (
                    f"{ARXIV_API_URL}?search_query={query}&start={start}"
                    f"&max_results={size}&sortBy=submittedDate&sortOrder=descending"
                )
                response = await arxiv_get_with_retry(
                    client,
                    url,
                    context=f"arxiv(page {start})",
                    validate=validate if page_index == 0 else None,
                )
                page = feedparser.parse(response.text).entries
                if not page:
                    break
                entries.extend(page)
                if len(page) < size:
                    break
                await asyncio.sleep(3)
        output = []
        for entry in entries:
            if target <= _entry_date(entry) <= end:
                candidate = _entry_candidate(entry, "arxiv")
                if candidate:
                    output.append(candidate)
        return output
    except (ArxivEmptyResponse, httpx.HTTPError):
        return (await _fetch_arxiv_oai(target, categories))[:max_results]


def parse_trending_ranks(html: str) -> dict[str, int]:
    seen: dict[str, int] = {}
    for match in TRENDING_LINK_RE.finditer(html):
        arxiv_id = match.group(1)
        if arxiv_id not in seen:
            seen[arxiv_id] = len(seen) + 1
    return seen


def hf_candidate_in_window(
    published: date,
    target: date,
    max_age_days: int,
    arxiv_id: str,
    historical_milestone_ids: frozenset[str] = frozenset(),
) -> bool:
    """限制 HF 候选发表日；curated milestone 只能突破下界，不能来自未来。"""
    if published > target:
        return False
    cutoff = target - timedelta(days=max(0, max_age_days))
    return published >= cutoff or arxiv_id in historical_milestone_ids


async def fetch_hf_daily(
    *,
    max_results: int = 100,
    target_date: date | datetime | None = None,
    include_trending: bool = True,
    trending_max_age_days: int = 30,
    historical_milestone_ids: frozenset[str] = frozenset(),
) -> list[dict]:
    target = _target_datetime(target_date)
    async with httpx.AsyncClient(
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 CiteMap llm-paper-radar"},
    ) as client:
        daily_response = await client.get(
            "https://huggingface.co/api/daily_papers",
            params={"date": target.strftime("%Y-%m-%d")},
        )
        daily_response.raise_for_status()
        daily_items = daily_response.json()
        trending_ranks: dict[str, int] = {}
        if include_trending:
            try:
                trending_response = await client.get("https://huggingface.co/papers/trending")
                if trending_response.status_code == 200:
                    trending_ranks = parse_trending_ranks(trending_response.text)
            except httpx.HTTPError:
                pass

    papers: dict[str, dict] = {}
    now = datetime.now(UTC).isoformat()
    for item in daily_items[:max_results]:
        paper = item.get("paper") or {}
        arxiv_id = str(paper.get("id") or item.get("id") or "").strip()
        if not arxiv_id:
            continue
        published_raw = paper.get("publishedAt") or item.get("publishedAt")
        try:
            published = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            published = target
        if not hf_candidate_in_window(
            published.date(),
            target.date(),
            trending_max_age_days,
            arxiv_id,
            historical_milestone_ids,
        ):
            continue
        github_repo = paper.get("githubRepo")
        github_stars = paper.get("githubStars")
        code_url = github_repo if isinstance(github_repo, str) and "github.com" in github_repo else None
        code_meta = (
            {"stars": github_stars, "source": "hf_daily", "fetched_at": now}
            if code_url and isinstance(github_stars, int)
            else None
        )
        metadata = {
            "upvotes": paper.get("upvotes", item.get("upvotes", 0)),
            "num_comments": paper.get("numComments", item.get("numComments", 0)),
        }
        if arxiv_id in trending_ranks:
            metadata["trending_rank"] = trending_ranks[arxiv_id]
        papers[arxiv_id] = {
            "arxiv_id": arxiv_id,
            "title": str(paper.get("title") or item.get("title") or "").strip(),
            "abstract": str(paper.get("summary") or item.get("summary") or "").strip(),
            "authors": [a.get("name", "") for a in paper.get("authors", [])],
            "categories": [],
            "published_date": published.date().isoformat(),
            "updated_date": published.date().isoformat(),
            "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            "code_url": code_url,
            "code_meta": code_meta,
            "source": "hf_daily",
            "source_metadata": metadata,
        }
    missing = [arxiv_id for arxiv_id in trending_ranks if arxiv_id not in papers]
    metadata_by_id = {arxiv_id: {"trending_rank": trending_ranks[arxiv_id]} for arxiv_id in missing}
    try:
        enriched = await fetch_arxiv_by_ids(
            missing,
            source="hf_daily",
            metadata_by_id=metadata_by_id,
        )
    except httpx.HTTPError:
        enriched = []
    for candidate in enriched:
        try:
            published = date.fromisoformat(str(candidate.get("published_date") or ""))
        except ValueError:
            continue
        arxiv_id = candidate["arxiv_id"]
        if not hf_candidate_in_window(
            published,
            target.date(),
            trending_max_age_days,
            arxiv_id,
            historical_milestone_ids,
        ):
            continue
        papers[arxiv_id] = candidate
    return list(papers.values())


def _normalize_author(name: str) -> str:
    value = name.strip().lower()
    if "," in value:
        last, first = (part.strip() for part in value.split(",", 1))
        value = f"{first} {last}"
    return " ".join(value.split())


async def fetch_watched_authors(
    *,
    categories: list[str] | None = None,
    authors: list[tuple[str, str]] | tuple[tuple[str, str], ...] | None = None,
    target_date: date | datetime | None = None,
    window_days: int = 7,
    page_size: int = 50,
    max_pages: int = 3,
) -> list[dict]:
    watched_authors = tuple(WATCHED_AUTHORS if authors is None else authors)
    if not watched_authors:
        return []
    target = _target_datetime(target_date)
    window_start = target - timedelta(days=window_days)
    author_query = "+OR+".join(f'au:"{name.replace(" ", "+")}"' for name, _ in watched_authors)
    category_query = "+OR+".join(f"cat:{category}" for category in (categories or ["cs.LG", "cs.CL", "cs.CV", "cs.AR", "stat.ML"]))
    query = f"({author_query})+AND+({category_query})"
    entries: list[dict] = []
    async with httpx.AsyncClient(
        timeout=60,
        follow_redirects=True,
        headers={"User-Agent": ARXIV_USER_AGENT},
    ) as client:
        start = 0
        for _ in range(max_pages):
            url = (
                f"{ARXIV_API_URL}?search_query={query}&start={start}"
                f"&max_results={page_size}&sortBy=submittedDate&sortOrder=descending"
            )
            response = await arxiv_get_with_retry(client, url, context=f"arxiv_authors({start})")
            page = feedparser.parse(response.text).entries
            if not page:
                break
            entries.extend(page)
            if _entry_date(page[-1]) < window_start:
                break
            start += page_size

    output = []
    for entry in entries:
        published = _entry_date(entry)
        if not (window_start <= published <= target + timedelta(hours=1)):
            continue
        candidate = _entry_candidate(entry, "arxiv_authors")
        if not candidate:
            continue
        paper_authors = {_normalize_author(author) for author in candidate["authors"]}
        matched = [(name, affiliation) for name, affiliation in watched_authors if _normalize_author(name) in paper_authors]
        if not matched:
            continue
        candidate["source_metadata"] = {
            "matched_authors": [name for name, _ in matched],
            "affiliations": sorted({affiliation for _, affiliation in matched if affiliation}),
        }
        output.append(candidate)
    return output


def _openreview_value(content: dict, field: str, default=None):
    value = content.get(field)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value if value is not None else default


def _openreview_date(note: dict) -> datetime | None:
    timestamp = note.get("cdate") or note.get("pdate") or note.get("mdate")
    return datetime.fromtimestamp(timestamp / 1000, tz=UTC) if timestamp is not None else None


def _expand_venues(venues: tuple[str, ...], current_year: int) -> list[str]:
    output: list[str] = []
    for template in venues:
        candidates = (
            [template.format(year=current_year), template.format(year=current_year + 1)]
            if "{year}" in template
            else [template]
        )
        for venue in candidates:
            if venue not in output:
                output.append(venue)
    return output


def _venue_label(venue: str) -> str:
    parts = venue.split("/")
    if parts[0] == "aclweb.org" and len(parts) > 1:
        return parts[1].lower()
    return parts[0].split(".", 1)[0].lower()


_openreview_token: str | None = None


async def _openreview_headers(client: httpx.AsyncClient) -> dict[str, str]:
    global _openreview_token
    if _openreview_token:
        return {"Authorization": f"Bearer {_openreview_token}"}
    email = os.environ.get("OPENREVIEW_EMAIL")
    password = os.environ.get("OPENREVIEW_PASSWORD")
    if not email or not password:
        return {}
    response = await client.post(
        "https://api2.openreview.net/login",
        json={"id": email, "password": password},
    )
    response.raise_for_status()
    _openreview_token = response.json().get("token")
    if not _openreview_token:
        raise RuntimeError("openreview login succeeded but response had no 'token' field")
    return {"Authorization": f"Bearer {_openreview_token}"}


async def fetch_openreview(
    *,
    target_date: date | datetime | None = None,
    venues: tuple[str, ...] = OPENREVIEW_VENUES,
    window_days: int = 7,
    max_pages: int = 5,
) -> list[dict]:
    target = _target_datetime(target_date)
    window_start = target - timedelta(days=window_days)
    window_end = target + timedelta(hours=1)
    output = []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        client.headers.update(await _openreview_headers(client))
        for venue in _expand_venues(venues, target.year):
            invitation = f"{venue}/-/Submission"
            notes: list[dict] = []
            offset = 0
            try:
                for _ in range(max_pages):
                    response = None
                    last_error: Exception | None = None
                    for attempt in range(3):
                        try:
                            response = await client.get(
                                "https://api2.openreview.net/notes",
                                params={
                                    "invitation": invitation,
                                    "offset": offset,
                                    "limit": 1000,
                                    "sort": "cdate:desc",
                                },
                            )
                            if response.status_code != 429:
                                last_error = None
                                break
                            wait = 5 * (2**attempt)
                        except (httpx.TimeoutException, httpx.TransportError) as exc:
                            last_error = exc
                            wait = 5 * (2**attempt)
                        await asyncio.sleep(wait)
                    if last_error:
                        raise last_error
                    assert response is not None
                    response.raise_for_status()
                    page = response.json().get("notes", [])
                    if not page:
                        break
                    notes.extend(page)
                    oldest = _openreview_date(page[-1])
                    if oldest and oldest < window_start:
                        break
                    offset += 1000
                    await asyncio.sleep(1)
            except Exception as exc:
                print(f"openreview: skip {venue}: {type(exc).__name__}: {exc}")
                continue
            for note in notes:
                published = _openreview_date(note)
                if published is None or not (window_start <= published <= window_end):
                    continue
                content = note.get("content") or {}
                title = str(_openreview_value(content, "title", "") or "").strip()
                note_id = str(note.get("id") or "")
                if not title or not note_id:
                    continue
                authors = _openreview_value(content, "authors", []) or []
                if isinstance(authors, str):
                    authors = [authors]
                canonical_id = f"or-{note_id}"
                output.append(
                    {
                        "arxiv_id": canonical_id,
                        "title": title,
                        "abstract": str(_openreview_value(content, "abstract", "") or "").strip(),
                        "authors": list(authors),
                        "categories": [_venue_label(venue)],
                        "published_date": published.date().isoformat(),
                        "updated_date": published.date().isoformat(),
                        "arxiv_url": f"https://openreview.net/forum?id={note_id}",
                        "pdf_url": f"https://openreview.net/pdf?id={note_id}",
                        "source": "openreview",
                        "source_metadata": {"venue": venue},
                    }
                )
            await asyncio.sleep(1)
    return output


def run_source(coroutine) -> list[dict]:
    return asyncio.run(coroutine)
