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
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 20  # seconds per request
_LINKEDIN_SESSION_FILE = Path("linkedin_session.json")
_LINKEDIN_MAX_CARDS = 25

# Keys every job dict must contain.
_JOB_KEYS = (
    "source", "external_id", "title", "company",
    "location", "description", "apply_url", "tags",
    "remote", "posted_at",
)

AVAILABLE_SOURCES: dict[str, str] = {
    "arbeitnow": "Arbeitnow",
    "remotive": "Remotive (remote)",
    "linkedin": "LinkedIn",
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
# LinkedIn  (Playwright-based — requires credentials via /linkedin-config)
# Uses a visible browser (headless=False) to log in and scrape job cards.
# Session cookies are persisted to linkedin_session.json to avoid re-login.
# ---------------------------------------------------------------------------

async def _linkedin_login(page: object, email: str, password: str) -> None:
    """Ensure the Playwright page is logged into LinkedIn.

    Strategy:
    1. Load cookies from :data:`_LINKEDIN_SESSION_FILE` if it exists.
    2. Navigate to the LinkedIn feed to check if the session is still valid.
    3. If the session is expired or missing, perform a full credential login.
    4. Persist the resulting cookies for future fetches.

    The browser window is visible so the user can complete any 2FA challenge.
    """
    context = page.context

    if _LINKEDIN_SESSION_FILE.exists():
        try:
            cookies = json.loads(_LINKEDIN_SESSION_FILE.read_text())
            await context.add_cookies(cookies)
            logger.info("LinkedIn: loaded %d cookies from session file", len(cookies))
        except Exception as exc:
            logger.warning("LinkedIn: could not load session cookies: %s", exc)

    await page.goto(
        "https://www.linkedin.com/feed/",
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    if "/feed" in page.url or "/jobs" in page.url:
        logger.info("LinkedIn: existing session is valid")
        return

    logger.info("LinkedIn: session invalid — performing full login")
    await page.goto(
        "https://www.linkedin.com/login",
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    await page.fill('input[name="session_key"]', email)
    await page.fill('input[name="session_password"]', password)
    await page.click('button[type="submit"]')

    # Wait up to 60 s — the user may need to complete a 2FA challenge manually.
    try:
        await page.wait_for_function(
            "() => window.location.href.includes('/feed') || window.location.href.includes('/jobs')",
            timeout=60_000,
        )
    except Exception:
        pass  # Timeout acceptable if user handled 2FA in time

    if "linkedin.com/login" in page.url or "checkpoint" in page.url:
        raise RuntimeError(
            "LinkedIn login failed. Check your credentials or complete the "
            "2FA challenge in the browser window, then retry."
        )

    try:
        cookies = await context.cookies()
        _LINKEDIN_SESSION_FILE.write_text(json.dumps(cookies, indent=2))
        logger.info("LinkedIn: session cookies saved to %s", _LINKEDIN_SESSION_FILE)
    except Exception as exc:
        logger.warning("LinkedIn: could not save session cookies: %s", exc)


def _linkedin_parse_posted_at(datetime_attr: Optional[str]) -> str:
    """Convert a LinkedIn <time datetime="..."> value to an ISO string."""
    if not datetime_attr:
        return datetime.now(timezone.utc).isoformat()
    try:
        return datetime.fromisoformat(
            datetime_attr.replace("Z", "+00:00")
        ).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


async def _fetch_linkedin(
    keywords: str,
    location: str,
    max_age_hours: int,
) -> list[dict]:
    """Scrape job listings from LinkedIn Jobs using Playwright.

    Requires LinkedIn credentials configured via ``PUT /linkedin-config``.
    Reuses a saved session cookie file to avoid repeated logins.
    Descriptions are not fetched (they require per-card navigation) to keep
    the scrape fast and minimise detection risk.
    """
    # Late imports to avoid making playwright a hard module-level dependency
    # and to prevent circular imports (profile imports nothing from scraper).
    from playwright.async_api import async_playwright
    import profile as prof

    email, password = prof.get_linkedin_credentials()
    if not email or not password:
        raise RuntimeError(
            "LinkedIn credentials not configured. "
            "Set them via PUT /linkedin-config before fetching."
        )

    cutoff = _cutoff_dt(max_age_hours)
    tpr_seconds = max_age_hours * 3600
    kw_enc = keywords.replace(" ", "%20")
    loc_enc = location.replace(" ", "%20")
    search_url = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={kw_enc}&location={loc_enc}"
        f"&f_TPR=r{tpr_seconds}&sortBy=DD"
    )

    jobs: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            await _linkedin_login(page, email, password)

            logger.info("LinkedIn: navigating to job search URL")
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)

            # Wait for at least one job card to appear.
            try:
                await page.wait_for_selector(
                    "ul.jobs-search__results-list li, "
                    "div.jobs-search-results-list div.job-search-card",
                    timeout=15_000,
                )
            except Exception:
                logger.warning("LinkedIn: no job cards found on results page")
                return []

            # Collect card elements — try primary selector first, then fallback.
            cards = await page.query_selector_all(
                "ul.jobs-search__results-list li.jobs-search-results__list-item"
            )
            if not cards:
                cards = await page.query_selector_all(
                    "div.jobs-search-results-list div.job-search-card"
                )
            cards = cards[:_LINKEDIN_MAX_CARDS]
            logger.info("LinkedIn: found %d job cards", len(cards))

            for card in cards:
                try:
                    title_el = await card.query_selector(
                        "h3.base-search-card__title, a.job-card-list__title"
                    )
                    title = (await title_el.inner_text()).strip() if title_el else ""

                    link_el = await card.query_selector(
                        "a.base-card__full-link, a.job-card-list__title"
                    )
                    href = (await link_el.get_attribute("href") or "") if link_el else ""
                    if href and not href.startswith("http"):
                        href = "https://www.linkedin.com" + href
                    apply_url = href.split("?")[0] if href else ""

                    m = re.search(r"/jobs/view/(\d+)", apply_url)
                    external_id = m.group(1) if m else apply_url

                    company_el = await card.query_selector(
                        "h4.base-search-card__subtitle, "
                        "span.job-card-container__primary-description"
                    )
                    company = (await company_el.inner_text()).strip() if company_el else ""

                    loc_el = await card.query_selector(
                        "span.job-search-card__location, "
                        "span.job-card-container__metadata-item"
                    )
                    job_location = (await loc_el.inner_text()).strip() if loc_el else ""

                    time_el = await card.query_selector("time")
                    datetime_attr = (
                        await time_el.get_attribute("datetime") if time_el else None
                    )
                    posted_at = _linkedin_parse_posted_at(datetime_attr)

                    try:
                        if datetime.fromisoformat(posted_at) < cutoff:
                            continue
                    except ValueError:
                        pass

                    remote = "remote" in job_location.lower()

                    jobs.append({
                        "source": "linkedin",
                        "external_id": external_id,
                        "title": title,
                        "company": company,
                        "location": job_location,
                        "description": "",
                        "apply_url": apply_url,
                        "tags": "",
                        "remote": remote,
                        "posted_at": posted_at,
                    })

                except Exception as exc:
                    logger.warning("LinkedIn: error parsing card: %s", exc)
                    continue

        finally:
            await browser.close()

    logger.info(
        "LinkedIn: scraped %d jobs (keywords=%r location=%r)",
        len(jobs), keywords, location,
    )
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

    if "linkedin" in sources:
        try:
            jobs = await _fetch_linkedin(keywords, location, max_age_hours)
            all_jobs.extend(jobs)
        except Exception as exc:
            logger.exception("LinkedIn fetch error: %s", exc)
            errors.append(f"linkedin: {exc}")

    return all_jobs, errors
