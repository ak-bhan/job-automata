"""Job listing fetchers for JobAutomata.

Fetches job listings from configured public APIs and returns normalised
job dicts ready for storage via ``profile.save_jobs()``.

Public interface
----------------
    await fetch_all(keywords, location, max_age_hours, sources) -> (list[dict], list[str])
    AVAILABLE_SOURCES  — {source_id: display_name}

Adding a new source
-------------------
1.  Implement ``async def _fetch_<name>(keywords, location, max_age_hours) -> list[dict]``
    where each returned dict contains the keys in ``_JOB_KEYS``.
2.  Add it to ``AVAILABLE_SOURCES`` and the dispatch block in ``fetch_all``.
"""

import html
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 20  # seconds per request

# Keys every job dict must contain.
_JOB_KEYS = (
    "source", "external_id", "title", "company",
    "location", "description", "apply_url", "tags",
    "remote", "posted_at",
)

AVAILABLE_SOURCES: dict[str, str] = {
    "arbeitnow": "Arbeitnow",
    "remotive": "Remotive (remote)",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from *text*."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _cutoff_dt(max_age_hours: int) -> datetime:
    """Return the earliest datetime that satisfies the age filter."""
    return datetime.now(timezone.utc) - timedelta(hours=max_age_hours)


# ---------------------------------------------------------------------------
# Arbeitnow  (https://www.arbeitnow.com/api/job-board-api)
# No API key required. Covers jobs posted to Personio, Lever, Greenhouse etc.
# Results are ordered newest-first so we stop as soon as we hit the cutoff.
# ---------------------------------------------------------------------------

async def _fetch_arbeitnow(
    keywords: str,
    location: str,
    max_age_hours: int,
    max_pages: int = 5,
) -> list[dict]:
    """Fetch from the Arbeitnow public job board API."""
    cutoff = _cutoff_dt(max_age_hours)
    jobs: list[dict] = []

    params: dict = {}
    if keywords:
        params["search"] = keywords
    if location:
        params["location"] = location

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for page in range(1, max_pages + 1):
            params["page"] = page
            try:
                r = await client.get(
                    "https://www.arbeitnow.com/api/job-board-api", params=params
                )
                r.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Arbeitnow request failed page=%d: %s", page, exc)
                break

            data = r.json()
            items = data.get("data", [])
            stop = False

            for item in items:
                ts = item.get("created_at", 0)
                try:
                    created = datetime.fromtimestamp(ts, tz=timezone.utc)
                except (OSError, OverflowError, ValueError):
                    created = datetime.now(timezone.utc)

                if created < cutoff:
                    stop = True  # results are newest-first; nothing older is useful
                    break

                jobs.append({
                    "source": "arbeitnow",
                    "external_id": str(item.get("slug", "")),
                    "title": item.get("title", ""),
                    "company": item.get("company_name", ""),
                    "location": item.get("location", ""),
                    "description": _strip_html(item.get("description", ""))[:3000],
                    "apply_url": item.get("url", ""),
                    "tags": ",".join(item.get("tags", [])),
                    "remote": bool(item.get("remote", False)),
                    "posted_at": created.isoformat(),
                })

            if stop:
                break

            meta = data.get("meta", {})
            if page >= meta.get("last_page", 1):
                break

    logger.info("Arbeitnow: fetched %d jobs (keywords=%r location=%r)", len(jobs), keywords, location)
    return jobs


# ---------------------------------------------------------------------------
# Remotive  (https://remotive.com/api/remote-jobs)
# No API key required. Remote-only jobs.
# ---------------------------------------------------------------------------

async def _fetch_remotive(
    keywords: str,
    location: str,
    max_age_hours: int,
) -> list[dict]:
    """Fetch from the Remotive public remote-jobs API."""
    cutoff = _cutoff_dt(max_age_hours)
    jobs: list[dict] = []

    params: dict = {"limit": 100}
    if keywords:
        params["search"] = keywords
    # Remotive has no location filter for its API; location is in listing metadata.

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            r = await client.get("https://remotive.com/api/remote-jobs", params=params)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Remotive request failed: %s", exc)
            return []

    location_lower = location.lower() if location else ""

    for item in r.json().get("jobs", []):
        pub_str = item.get("publication_date", "")
        try:
            posted = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            posted = datetime.now(timezone.utc)

        if posted < cutoff:
            continue

        # Optional location filter (post-fetch) when user specified a location.
        candidate_loc = item.get("candidate_required_location", "").lower()
        if location_lower and location_lower not in candidate_loc and "worldwide" not in candidate_loc:
            continue

        jobs.append({
            "source": "remotive",
            "external_id": str(item.get("id", "")),
            "title": item.get("title", ""),
            "company": item.get("company_name", ""),
            "location": item.get("candidate_required_location", "Remote"),
            "description": _strip_html(item.get("description", ""))[:3000],
            "apply_url": item.get("url", ""),
            "tags": item.get("tags", ""),
            "remote": True,
            "posted_at": posted.isoformat(),
        })

    logger.info("Remotive: fetched %d jobs (keywords=%r)", len(jobs), keywords)
    return jobs


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def fetch_all(
    keywords: str = "",
    location: str = "",
    max_age_hours: int = 24,
    sources: Optional[list[str]] = None,
) -> tuple[list[dict], list[str]]:
    """Fetch jobs from all enabled sources.

    Args:
        keywords:      Search terms (e.g. ``"python developer"``).
        location:      Location filter (e.g. ``"Berlin"``).
        max_age_hours: Only return jobs posted within this many hours.
        sources:       Source IDs to query. Defaults to all in
                       :data:`AVAILABLE_SOURCES`.

    Returns:
        Tuple of ``(job_list, errors)`` where *job_list* is a list of
        normalised job dicts and *errors* is a list of human-readable
        error strings (one per failed source).
    """
    if sources is None:
        sources = list(AVAILABLE_SOURCES.keys())

    all_jobs: list[dict] = []
    errors: list[str] = []

    if "arbeitnow" in sources:
        try:
            jobs = await _fetch_arbeitnow(keywords, location, max_age_hours)
            all_jobs.extend(jobs)
        except Exception as exc:
            logger.exception("Arbeitnow fetch error: %s", exc)
            errors.append(f"arbeitnow: {exc}")

    if "remotive" in sources:
        try:
            jobs = await _fetch_remotive(keywords, location, max_age_hours)
            all_jobs.extend(jobs)
        except Exception as exc:
            logger.exception("Remotive fetch error: %s", exc)
            errors.append(f"remotive: {exc}")

    return all_jobs, errors
