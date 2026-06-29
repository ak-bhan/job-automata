"""SQLite-backed profile storage and fill logging for JobAutomata.

Single-user, local-first design: the profiles table always holds exactly one
row (id=1). Fill attempts are appended to the fill_logs table.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("db.sqlite")

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_PROFILE_TABLE = """
CREATE TABLE IF NOT EXISTS profile (
    id                      INTEGER PRIMARY KEY CHECK (id = 1),
    data                    TEXT    NOT NULL DEFAULT '{}',
    resume_path             TEXT,
    resume_name             TEXT,
    cover_letter_path       TEXT,
    cover_letter_name       TEXT,
    reference_letter_path   TEXT,
    reference_letter_name   TEXT,
    updated_at              TEXT    NOT NULL
);
"""

_MIGRATE_STATEMENTS = [
    "ALTER TABLE profile ADD COLUMN cover_letter_path TEXT",
    "ALTER TABLE profile ADD COLUMN reference_letter_path TEXT",
    "ALTER TABLE profile ADD COLUMN resume_name TEXT",
    "ALTER TABLE profile ADD COLUMN cover_letter_name TEXT",
    "ALTER TABLE profile ADD COLUMN reference_letter_name TEXT",
    # pronouns stored inside the JSON data blob — no column migration needed
]

_CREATE_FILL_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS fill_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT    NOT NULL,
    fields_detected INTEGER NOT NULL DEFAULT 0,
    fields_filled   INTEGER NOT NULL DEFAULT 0,
    fields_skipped  INTEGER NOT NULL DEFAULT 0,
    detail          TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL
);
"""

_CREATE_QA_TABLE = """
CREATE TABLE IF NOT EXISTS qa_pairs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    question   TEXT    NOT NULL,
    answer     TEXT    NOT NULL DEFAULT '',
    tags       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);
"""

_CREATE_APPLICATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS applications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT    NOT NULL,
    company    TEXT    NOT NULL DEFAULT '',
    role       TEXT    NOT NULL DEFAULT '',
    status     TEXT    NOT NULL DEFAULT 'applied',
    applied_at TEXT    NOT NULL
);
"""

_CREATE_SEARCH_CONFIG_TABLE = """
CREATE TABLE IF NOT EXISTS search_config (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    keywords      TEXT    NOT NULL DEFAULT '',
    location      TEXT    NOT NULL DEFAULT '',
    max_age_hours INTEGER NOT NULL DEFAULT 24,
    sources       TEXT    NOT NULL DEFAULT 'arbeitnow,remotive',
    updated_at    TEXT    NOT NULL
);
"""

_CREATE_JOB_LISTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS job_listings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    external_id TEXT    NOT NULL,
    title       TEXT    NOT NULL DEFAULT '',
    company     TEXT    NOT NULL DEFAULT '',
    location    TEXT    NOT NULL DEFAULT '',
    description TEXT    NOT NULL DEFAULT '',
    apply_url   TEXT    NOT NULL DEFAULT '',
    tags        TEXT    NOT NULL DEFAULT '',
    remote      INTEGER NOT NULL DEFAULT 0,
    posted_at   TEXT,
    fetched_at  TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'new',
    UNIQUE(source, external_id)
);
"""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """Open a connection to the SQLite database with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create database tables if they do not already exist.

    Safe to call every time the application starts — uses CREATE TABLE IF NOT
    EXISTS so it is idempotent.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(_CREATE_PROFILE_TABLE)
        conn.execute(_CREATE_FILL_LOGS_TABLE)
        conn.execute(_CREATE_QA_TABLE)
        conn.execute(_CREATE_APPLICATIONS_TABLE)
        conn.execute(_CREATE_SEARCH_CONFIG_TABLE)
        conn.execute(_CREATE_JOB_LISTINGS_TABLE)
        # Apply any additive migrations for existing databases.
        for stmt in _MIGRATE_STATEMENTS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # Column already exists — safe to ignore.
        conn.commit()
    logger.info("Database initialised at %s", DB_PATH)


def get_profile() -> dict[str, Any]:
    """Return the stored profile as a plain dict.

    Returns an empty profile structure if no profile has been saved yet.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT data, resume_path, resume_name, cover_letter_path, cover_letter_name, "
            "reference_letter_path, reference_letter_name FROM profile WHERE id = 1"
        ).fetchone()

    if row is None:
        return _empty_profile()

    profile = json.loads(row["data"])
    profile["resumePath"] = row["resume_path"]
    profile["resumeName"] = row["resume_name"]
    profile["coverLetterPath"] = row["cover_letter_path"]
    profile["coverLetterName"] = row["cover_letter_name"]
    profile["referenceLetterPath"] = row["reference_letter_path"]
    profile["referenceLetterName"] = row["reference_letter_name"]
    return profile


def save_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Persist profile data, creating or replacing the single profile row.

    Args:
        data: Mapping of profile field names to values. Unknown keys are stored
              in ``customFields``. The ``resumePath`` key is ignored here — use
              :func:`set_resume_path` to update it.

    Returns:
        The saved profile as returned by :func:`get_profile`.
    """
    # Strip file paths so they do not bleed into the JSON blob.
    _path_keys = {"resumePath", "coverLetterPath", "referenceLetterPath"}
    payload = {k: v for k, v in data.items() if k not in _path_keys}
    serialised = json.dumps(payload, ensure_ascii=False)

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profile (id, data, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                data       = excluded.data,
                updated_at = excluded.updated_at
            """,
            (serialised, _now_iso()),
        )
        conn.commit()

    logger.info("Profile saved")
    return get_profile()


def set_resume_path(path: str, original_name: str = "") -> None:
    """Store the filesystem path and original filename of the uploaded resume PDF.

    Args:
        path:          Absolute or relative path to the resume PDF on disk.
        original_name: The original filename as provided by the user.
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profile (id, data, resume_path, resume_name, updated_at)
            VALUES (1, '{}', ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                resume_path = excluded.resume_path,
                resume_name = excluded.resume_name,
                updated_at  = excluded.updated_at
            """,
            (path, original_name, _now_iso()),
        )
        conn.commit()

    logger.info("Resume path set to %s", path)


def set_cover_letter_path(path: str, original_name: str = "") -> None:
    """Store the filesystem path and original filename of the uploaded cover letter PDF.

    Args:
        path:          Absolute or relative path to the cover letter PDF on disk.
        original_name: The original filename as provided by the user.
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profile (id, data, cover_letter_path, cover_letter_name, updated_at)
            VALUES (1, '{}', ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                cover_letter_path = excluded.cover_letter_path,
                cover_letter_name = excluded.cover_letter_name,
                updated_at        = excluded.updated_at
            """,
            (path, original_name, _now_iso()),
        )
        conn.commit()
    logger.info("Cover letter path set to %s", path)


def set_reference_letter_path(path: str, original_name: str = "") -> None:
    """Store the filesystem path and original filename of the uploaded reference letter PDF.

    Args:
        path:          Absolute or relative path to the reference letter PDF on disk.
        original_name: The original filename as provided by the user.
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profile (id, data, reference_letter_path, reference_letter_name, updated_at)
            VALUES (1, '{}', ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                reference_letter_path = excluded.reference_letter_path,
                reference_letter_name = excluded.reference_letter_name,
                updated_at            = excluded.updated_at
            """,
            (path, original_name, _now_iso()),
        )
        conn.commit()
    logger.info("Reference letter path set to %s", path)


def log_fill(
    url: str,
    fields_detected: int,
    fields_filled: int,
    fields_skipped: int,
    detail: Optional[dict[str, Any]] = None,
) -> int:
    """Append a record of a form-fill attempt to the fill_logs table.

    Args:
        url:             The job application URL that was filled.
        fields_detected: Total number of form fields found on the page.
        fields_filled:   Number of fields that were successfully filled.
        fields_skipped:  Number of fields that could not be matched and were
                         left empty.
        detail:          Optional mapping with per-field information, e.g.
                         ``{"email": "filled", "salary": "skipped"}``.

    Returns:
        The auto-incremented ``id`` of the newly created log row.
    """
    detail_json = json.dumps(detail or {}, ensure_ascii=False)

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO fill_logs
                (url, fields_detected, fields_filled, fields_skipped, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (url, fields_detected, fields_filled, fields_skipped, detail_json, _now_iso()),
        )
        conn.commit()
        row_id: int = cursor.lastrowid  # type: ignore[assignment]

    logger.info(
        "Fill logged — url=%s detected=%d filled=%d skipped=%d",
        url,
        fields_detected,
        fields_filled,
        fields_skipped,
    )
    return row_id


def get_fill_logs(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent fill attempts, newest first.

    Args:
        limit: Maximum number of rows to return (default 50).

    Returns:
        List of dicts, each containing ``id``, ``url``, ``fields_detected``,
        ``fields_filled``, ``fields_skipped``, ``detail``, and ``created_at``.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, url, fields_detected, fields_filled, fields_skipped,
                   detail, created_at
            FROM fill_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "url": row["url"],
            "fields_detected": row["fields_detected"],
            "fields_filled": row["fields_filled"],
            "fields_skipped": row["fields_skipped"],
            "detail": json.loads(row["detail"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_qa_pairs() -> list[dict[str, Any]]:
    """Return all Q&A pairs, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, question, answer, tags, created_at, updated_at FROM qa_pairs ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def add_qa_pair(question: str, answer: str, tags: str = "") -> dict[str, Any]:
    """Insert a new Q&A pair and return it."""
    now = _now_iso()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO qa_pairs (question, answer, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (question.strip(), answer.strip(), tags.strip(), now, now),
        )
        conn.commit()
        row_id: int = cursor.lastrowid  # type: ignore[assignment]
    return {"id": row_id, "question": question, "answer": answer, "tags": tags,
            "created_at": now, "updated_at": now}


def update_qa_pair(pair_id: int, question: str, answer: str, tags: str = "") -> bool:
    """Update an existing Q&A pair. Returns True if a row was updated."""
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE qa_pairs SET question=?, answer=?, tags=?, updated_at=? WHERE id=?",
            (question.strip(), answer.strip(), tags.strip(), _now_iso(), pair_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def delete_qa_pair(pair_id: int) -> bool:
    """Delete a Q&A pair by id. Returns True if a row was deleted."""
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM qa_pairs WHERE id=?", (pair_id,))
        conn.commit()
    return cursor.rowcount > 0


def delete_application(application_id: int) -> bool:
    """Delete a saved application by id.

    Returns:
        True if a row was deleted, False if no row with that id existed.
    """
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM applications WHERE id = ?", (application_id,)
        )
        conn.commit()
    deleted = cursor.rowcount > 0
    if deleted:
        logger.info("Application %d deleted", application_id)
    return deleted


def log_application(url: str, company: str = "", role: str = "") -> int:
    """Record a job application as submitted.

    Args:
        url:     The job application URL that was submitted.
        company: Optional company name.
        role:    Optional job title / role name.

    Returns:
        The auto-incremented ``id`` of the newly created row.
    """
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO applications (url, company, role, status, applied_at)
            VALUES (?, ?, ?, 'applied', ?)
            """,
            (url, company, role, _now_iso()),
        )
        conn.commit()
        row_id: int = cursor.lastrowid  # type: ignore[assignment]

    logger.info("Application logged — url=%s", url)
    return row_id


def get_applications(
    limit: int = 200,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return saved applications, newest first.

    Args:
        limit:     Maximum number of rows to return.
        from_date: Optional ISO date string (YYYY-MM-DD). Only return rows
                   where applied_at >= from_date (inclusive, start of day).
        to_date:   Optional ISO date string (YYYY-MM-DD). Only return rows
                   where applied_at <= to_date (inclusive, end of day).

    Returns:
        List of dicts with ``id``, ``url``, ``company``, ``role``,
        ``status``, and ``applied_at``.
    """
    conditions = []
    params: list = []

    if from_date:
        conditions.append("applied_at >= ?")
        params.append(f"{from_date}T00:00:00")
    if to_date:
        conditions.append("applied_at <= ?")
        params.append(f"{to_date}T23:59:59")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, url, company, role, status, applied_at
            FROM applications
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return [
        {
            "id": row["id"],
            "url": row["url"],
            "company": row["company"],
            "role": row["role"],
            "status": row["status"],
            "applied_at": row["applied_at"],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Search config
# ---------------------------------------------------------------------------

def get_search_config() -> dict[str, Any]:
    """Return the saved search configuration (single row, id=1)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT keywords, location, max_age_hours, sources FROM search_config WHERE id = 1"
        ).fetchone()
    if row is None:
        return {
            "keywords": "",
            "location": "",
            "max_age_hours": 24,
            "sources": ["arbeitnow", "remotive"],
        }
    return {
        "keywords": row["keywords"],
        "location": row["location"],
        "max_age_hours": row["max_age_hours"],
        "sources": [s.strip() for s in row["sources"].split(",") if s.strip()],
    }


def save_search_config(
    keywords: str,
    location: str,
    max_age_hours: int,
    sources: list[str],
) -> dict[str, Any]:
    """Persist the search configuration."""
    sources_str = ",".join(sources)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO search_config (id, keywords, location, max_age_hours, sources, updated_at)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                keywords      = excluded.keywords,
                location      = excluded.location,
                max_age_hours = excluded.max_age_hours,
                sources       = excluded.sources,
                updated_at    = excluded.updated_at
            """,
            (keywords, location, max_age_hours, sources_str, _now_iso()),
        )
        conn.commit()
    logger.info("Search config saved")
    return get_search_config()


# ---------------------------------------------------------------------------
# Job listings
# ---------------------------------------------------------------------------

def save_jobs(jobs: list[dict[str, Any]]) -> tuple[int, int]:
    """Insert new job listings, skipping duplicates (same source + external_id).

    Returns:
        Tuple of (inserted, skipped) counts.
    """
    fetched_at = _now_iso()
    inserted = 0
    skipped = 0
    with _connect() as conn:
        for job in jobs:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO job_listings
                    (source, external_id, title, company, location, description,
                     apply_url, tags, remote, posted_at, fetched_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                """,
                (
                    job.get("source", ""),
                    job.get("external_id", ""),
                    job.get("title", ""),
                    job.get("company", ""),
                    job.get("location", ""),
                    job.get("description", ""),
                    job.get("apply_url", ""),
                    job.get("tags", ""),
                    1 if job.get("remote") else 0,
                    job.get("posted_at"),
                    fetched_at,
                ),
            )
            if cursor.rowcount:
                inserted += 1
            else:
                skipped += 1
        conn.commit()
    logger.info("save_jobs: inserted=%d skipped=%d", inserted, skipped)
    return inserted, skipped


def get_jobs(
    status: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return job listings with optional filtering.

    Args:
        status: Filter by status: ``"new"``, ``"saved"``, ``"hidden"``.
                Pass ``None`` or ``"all"`` to return all non-hidden jobs.
        source: Filter by source id (e.g. ``"arbeitnow"``).
        q:      Case-insensitive text search on title + company.
        limit:  Max rows to return.
        offset: Row offset for pagination.
    """
    conditions: list[str] = []
    params: list = []

    if status and status != "all":
        conditions.append("status = ?")
        params.append(status)
    elif not status or status == "all":
        # Exclude hidden from the default "all" view
        conditions.append("status != 'hidden'")

    if source:
        conditions.append("source = ?")
        params.append(source)

    if q:
        conditions.append("(title LIKE ? OR company LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, source, external_id, title, company, location,
                   description, apply_url, tags, remote, posted_at, fetched_at, status
            FROM job_listings
            {where}
            ORDER BY posted_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()

    return [
        {
            "id": row["id"],
            "source": row["source"],
            "title": row["title"],
            "company": row["company"],
            "location": row["location"],
            "description": row["description"],
            "apply_url": row["apply_url"],
            "tags": [t.strip() for t in row["tags"].split(",") if t.strip()],
            "remote": bool(row["remote"]),
            "posted_at": row["posted_at"],
            "fetched_at": row["fetched_at"],
            "status": row["status"],
        }
        for row in rows
    ]


def update_job_status(job_id: int, status: str) -> bool:
    """Update a job listing's status. Returns True if the row existed."""
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE job_listings SET status = ? WHERE id = ?",
            (status, job_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def delete_job(job_id: int) -> bool:
    """Delete a job listing by id. Returns True if a row was deleted."""
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM job_listings WHERE id = ?", (job_id,))
        conn.commit()
    return cursor.rowcount > 0


def get_job_counts() -> dict[str, int]:
    """Return counts of jobs grouped by status."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM job_listings GROUP BY status"
        ).fetchall()
    counts = {"new": 0, "saved": 0, "hidden": 0}
    for row in rows:
        counts[row["status"]] = row["cnt"]
    return counts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_profile() -> dict[str, Any]:
    """Return a profile dict with every standard field set to an empty string."""
    return {
        "salutation": "",
        "pronouns": "",
        "gender": "",
        "ethnicity": "",
        "firstName": "",
        "lastName": "",
        "email": "",
        "phone": "",
        "address": "",
        "city": "",
        "zip": "",
        "country": "",
        "nationality": "",
        "linkedin": "",
        "github": "",
        "portfolio": "",
        "currentTitle": "",
        "currentCompany": "",
        "yearsExp": "",
        "englishLevel": "",
        "germanLevel": "",
        "frenchLevel": "",
        "spanishLevel": "",
        "italianLevel": "",
        "salaryExpect": "",
        "noticePeriod": "",
        "startDate": "",
        "dateOfBirth": "",
        "workAuth": "",
        "phoneCountryCode": "",
        "university": "",
        "degree": "",
        "gradYear": "",
        "customFields": {},
        "resumePath": None,
        "resumeName": None,
        "coverLetterPath": None,
        "coverLetterName": None,
        "referenceLetterPath": None,
        "referenceLetterName": None,
    }
