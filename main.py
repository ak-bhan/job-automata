"""FastAPI application entry point for JobAutomata.

Exposes the REST API that drives profile management, resume upload, and
form-fill automation. Run directly with ``python main.py`` or via uvicorn:

    uvicorn main:app --reload

Endpoints
---------
    GET  /health           — liveness check
    GET  /profile          — fetch saved profile
    PUT  /profile          — save / update profile
    POST /upload-resume    — upload resume PDF
    POST /fill             — open browser and fill a job application form
    GET  /logs             — retrieve fill history
"""

import asyncio
import csv
import io
import logging
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, HttpUrl

import profile as prof
import filler

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
RESUME_DIR = Path(os.getenv("RESUME_DIR", "resumes"))

# ---------------------------------------------------------------------------
# Lifespan — runs once on startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the database and resume storage directory on startup."""
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    prof.init_db()
    logger.info("JobAutomata started — http://%s:%d", HOST, PORT)
    yield
    logger.info("JobAutomata shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="JobAutomata",
    description="Local-first job application form filler.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ProfileBody(BaseModel):
    """Accepts any profile field — unknown keys land in customFields."""

    model_config = {"extra": "allow"}

    salutation: str = ""
    firstName: str = ""
    lastName: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    city: str = ""
    zip: str = ""
    country: str = ""
    nationality: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    currentTitle: str = ""
    currentCompany: str = ""
    yearsExp: str = ""
    languageSkills: str = ""
    salaryExpect: str = ""
    noticePeriod: str = ""
    startDate: str = ""
    dateOfBirth: str = ""
    workAuth: str = ""
    phoneCountryCode: str = ""
    university: str = ""
    degree: str = ""
    gradYear: str = ""
    customFields: dict[str, Any] = {}


class MarkAppliedRequest(BaseModel):
    """Body for POST /applications."""

    url: str
    company: str = ""
    role: str = ""


class FillRequest(BaseModel):
    """Body for POST /fill."""

    url: HttpUrl


class FillResponse(BaseModel):
    """Summary returned after a fill attempt."""

    url: str
    fields_detected: int
    fields_filled: int
    fields_skipped: int
    page_title: str
    log_id: int
    detail: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    """Redirect to the React frontend if built, otherwise serve the test page."""
    if Path("frontend/dist").exists():
        return RedirectResponse(url="/app")
    return FileResponse("test_page.html")


@app.get("/docs-api", include_in_schema=False)
async def api_docs() -> RedirectResponse:
    """Redirect to the auto-generated OpenAPI docs."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Return a simple liveness signal."""
    return {"status": "ok"}


@app.get("/profile", tags=["profile"])
async def get_profile() -> dict[str, Any]:
    """Return the currently saved profile.

    If no profile has been saved yet, returns an empty profile structure
    with all standard fields set to empty strings.
    """
    return prof.get_profile()


@app.put("/profile", tags=["profile"])
async def save_profile(body: ProfileBody) -> dict[str, Any]:
    """Save or update the user profile.

    Performs a full replacement of the stored profile data. Fields not
    included in the request body are reset to empty strings.
    """
    data = body.model_dump()
    saved = prof.save_profile(data)
    logger.info("Profile updated")
    return saved


@app.post("/upload-resume", tags=["profile"])
async def upload_resume(file: UploadFile = File(...)) -> dict[str, str]:
    """Accept a resume PDF and store it in the resumes/ directory.

    Any previously saved resume path is replaced. The uploaded file is
    saved with a UUID-prefixed filename to avoid collisions.

    Args:
        file: Multipart file upload. Should be a PDF.

    Raises:
        422: if no file is provided.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No filename provided.",
        )

    suffix = Path(file.filename).suffix or ".pdf"
    dest_name = f"{uuid.uuid4().hex}{suffix}"
    dest_path = RESUME_DIR / dest_name

    with dest_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    prof.set_resume_path(str(dest_path.resolve()), original_name=file.filename)
    logger.info("Resume saved to %s", dest_path)

    return {"resume_path": str(dest_path), "resume_name": file.filename}


@app.post("/upload-cover-letter", tags=["profile"])
async def upload_cover_letter(file: UploadFile = File(...)) -> dict[str, str]:
    """Accept a cover letter PDF and store it in the resumes/ directory.

    Args:
        file: Multipart file upload. Should be a PDF.

    Raises:
        422: if no file is provided.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No filename provided.",
        )

    suffix = Path(file.filename).suffix or ".pdf"
    dest_name = f"{uuid.uuid4().hex}{suffix}"
    dest_path = RESUME_DIR / dest_name

    with dest_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    prof.set_cover_letter_path(str(dest_path.resolve()), original_name=file.filename)
    logger.info("Cover letter saved to %s", dest_path)

    return {"cover_letter_path": str(dest_path), "cover_letter_name": file.filename}


@app.post("/upload-reference-letter", tags=["profile"])
async def upload_reference_letter(file: UploadFile = File(...)) -> dict[str, str]:
    """Accept a reference letter PDF and store it in the resumes/ directory.

    Args:
        file: Multipart file upload. Should be a PDF.

    Raises:
        422: if no file is provided.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No filename provided.",
        )

    suffix = Path(file.filename).suffix or ".pdf"
    dest_name = f"{uuid.uuid4().hex}{suffix}"
    dest_path = RESUME_DIR / dest_name

    with dest_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    prof.set_reference_letter_path(str(dest_path.resolve()), original_name=file.filename)
    logger.info("Reference letter saved to %s", dest_path)

    return {"reference_letter_path": str(dest_path), "reference_letter_name": file.filename}


@app.post("/fill", response_model=FillResponse, tags=["automation"])
async def fill(body: FillRequest) -> FillResponse:
    """Open a visible browser and fill the job application form at *url*.

    Retrieves the saved profile and resume path, launches Playwright, and
    fills all matched fields. The browser is left open for the user to
    review and submit. The fill attempt is logged to the database.

    Args:
        body: JSON object with a ``url`` key pointing to the application form.

    Raises:
        400: if no profile has been saved yet.
        502: if Playwright fails to launch or navigate to the page.
    """
    profile_data = prof.get_profile()
    if not any(v for k, v in profile_data.items() if k not in ("customFields", "resumePath") and v):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No profile saved. Please PUT /profile before filling a form.",
        )

    resume_path: str | None = profile_data.pop("resumePath", None)
    cover_letter_path: str | None = profile_data.pop("coverLetterPath", None)
    reference_letter_path: str | None = profile_data.pop("referenceLetterPath", None)
    url_str = str(body.url)

    try:
        summary = await filler.fill_form(
            url=url_str,
            profile=profile_data,
            resume_path=resume_path,
            cover_letter_path=cover_letter_path,
            reference_letter_path=reference_letter_path,
        )
    except Exception as exc:
        logger.exception("fill_form raised an unexpected error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Browser automation failed: {exc}",
        ) from exc

    log_id = prof.log_fill(
        url=url_str,
        fields_detected=summary["fields_detected"],
        fields_filled=summary["fields_filled"],
        fields_skipped=summary["fields_skipped"],
        detail={
            "entries": [
                {
                    "signals": e.get("signals", {}),
                    "matched_key": e.get("matched_key"),
                    "status": e.get("status"),
                }
                for e in summary["detail"]
            ]
        },
    )

    return FillResponse(
        url=url_str,
        fields_detected=summary["fields_detected"],
        fields_filled=summary["fields_filled"],
        fields_skipped=summary["fields_skipped"],
        page_title=summary.get("page_title", ""),
        log_id=log_id,
        detail=summary["detail"],
    )


@app.post("/applications", tags=["applications"])
async def mark_applied(body: MarkAppliedRequest) -> dict[str, Any]:
    """Record a job as applied.

    Call this after you have reviewed and submitted the form in the browser.

    Args:
        body: JSON with ``url`` (required), ``company`` and ``role`` (optional).

    Returns:
        The saved application record.
    """
    row_id = prof.log_application(
        url=body.url,
        company=body.company,
        role=body.role,
    )
    logger.info("Application marked as applied — url=%s id=%d", body.url, row_id)
    return {"id": row_id, "url": body.url, "company": body.company, "role": body.role, "status": "applied"}


@app.get("/applications", tags=["applications"])
async def get_applications(
    limit: int = 200,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict[str, Any]]:
    """Return saved job applications, newest first.

    Args:
        limit:     Maximum number of records to return (default 200).
        from_date: ISO date string (YYYY-MM-DD) — filter from this date.
        to_date:   ISO date string (YYYY-MM-DD) — filter up to this date.
    """
    return prof.get_applications(limit=min(limit, 1000), from_date=from_date, to_date=to_date)


@app.delete("/applications/{application_id}", tags=["applications"])
async def delete_application(application_id: int) -> dict[str, str]:
    """Delete a saved application by id.

    Raises:
        404: if no application with that id exists.
    """
    deleted = prof.delete_application(application_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found.",
        )
    return {"status": "deleted"}


@app.get("/applications/export", tags=["applications"])
async def export_applications(
    from_date: str | None = None,
    to_date: str | None = None,
) -> StreamingResponse:
    """Download saved job applications as a CSV file.

    Args:
        from_date: ISO date string (YYYY-MM-DD) — include applications on or after this date.
        to_date:   ISO date string (YYYY-MM-DD) — include applications on or before this date.
    """
    applications = prof.get_applications(limit=10_000, from_date=from_date, to_date=to_date)

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["id", "company", "role", "url", "status", "applied_at"],
    )
    writer.writeheader()
    writer.writerows(applications)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"},
    )


@app.get("/logs", tags=["automation"])
async def get_logs(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent fill attempts, newest first.

    Args:
        limit: Maximum number of records to return (default 50, max 200).
    """
    limit = min(limit, 200)
    return prof.get_fill_logs(limit=limit)


# ---------------------------------------------------------------------------
# Serve built React frontend if available
# ---------------------------------------------------------------------------

_FRONTEND_DIST = Path("frontend/dist")
if _FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    @app.get("/app", include_in_schema=False)
    async def frontend():
        return FileResponse(str(_FRONTEND_DIST / "index.html"))

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
