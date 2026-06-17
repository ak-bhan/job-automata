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
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    data        TEXT    NOT NULL DEFAULT '{}',
    resume_path TEXT,
    updated_at  TEXT    NOT NULL
);
"""

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
        conn.commit()
    logger.info("Database initialised at %s", DB_PATH)


def get_profile() -> dict[str, Any]:
    """Return the stored profile as a plain dict.

    Returns an empty profile structure if no profile has been saved yet.
    """
    with _connect() as conn:
        row = conn.execute("SELECT data, resume_path FROM profile WHERE id = 1").fetchone()

    if row is None:
        return _empty_profile()

    profile = json.loads(row["data"])
    profile["resumePath"] = row["resume_path"]
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
    # Strip resumePath so it does not bleed into the JSON blob.
    payload = {k: v for k, v in data.items() if k != "resumePath"}
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


def set_resume_path(path: str) -> None:
    """Store the filesystem path of the uploaded resume PDF.

    Creates a blank profile row first if one does not exist yet, so that a
    user can upload their resume before filling out the rest of their profile.

    Args:
        path: Absolute or relative path to the resume PDF on disk.
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profile (id, data, resume_path, updated_at)
            VALUES (1, '{}', ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                resume_path = excluded.resume_path,
                updated_at  = excluded.updated_at
            """,
            (path, _now_iso()),
        )
        conn.commit()

    logger.info("Resume path set to %s", path)


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_profile() -> dict[str, Any]:
    """Return a profile dict with every standard field set to an empty string."""
    return {
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
        "salaryExpect": "",
        "noticePeriod": "",
        "startDate": "",
        "dateOfBirth": "",
        "workAuth": "",
        "university": "",
        "degree": "",
        "gradYear": "",
        "customFields": {},
        "resumePath": None,
    }
