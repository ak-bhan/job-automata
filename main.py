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
from fastapi.responses import JSONResponse, RedirectResponse
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
    salaryExpect: str = ""
    noticePeriod: str = ""
    startDate: str = ""
    workAuth: str = ""
    university: str = ""
    degree: str = ""
    gradYear: str = ""
    customFields: dict[str, Any] = {}


class FillRequest(BaseModel):
    """Body for POST /fill."""

    url: HttpUrl


class FillResponse(BaseModel):
    """Summary returned after a fill attempt."""

    url: str
    fields_detected: int
    fields_filled: int
    fields_skipped: int
    log_id: int
    detail: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect browser visits to the interactive API docs."""
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

    prof.set_resume_path(str(dest_path.resolve()))
    logger.info("Resume saved to %s", dest_path)

    return {"resume_path": str(dest_path)}


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
    url_str = str(body.url)

    try:
        summary = await filler.fill_form(
            url=url_str,
            profile=profile_data,
            resume_path=resume_path,
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
        log_id=log_id,
        detail=summary["detail"],
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
