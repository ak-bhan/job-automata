# JobAutomata

## What this project is

JobAutomata is an open-source, local-first web application that automates filling job application forms. The user pastes a job application URL, a visible browser opens, detects and fills form fields using the user's saved profile data, and the user reviews and submits manually. Human-in-the-loop by design — the bot fills, the human decides.

**This is not a spray-and-pray bot.** It does not submit applications automatically. It does not scrape job boards. It fills forms intelligently and gives the user full control.

## Architecture

- **Backend:** Python 3.11+ with FastAPI
- **Browser automation:** Playwright (opens a visible Chromium window, not headless)
- **Database:** SQLite via Python's built-in sqlite3 module (single file: `db.sqlite`)
- **Frontend:** React (added after backend is proven — not part of MVP v0.1)
- **LLM integration:** Not in v0.1. Architecture supports plugging in Ollama or any OpenAI-compatible API later for smart field matching and screening question answers

## MVP scope (v0.1)

The user can:
1. Run the app locally with `python main.py`
2. Save their profile once (personal details, work preferences, education, links)
3. Upload a resume PDF
4. Paste a job application URL via API endpoint
5. Watch a real Chrome window open, navigate to that URL, and fill the form fields
6. Review the filled fields, make edits, and submit the form themselves

What v0.1 does NOT include:
- React frontend (use API endpoints directly or the minimal HTML test page)
- LLM-based field matching (rule-based only)
- Job board scraping or search
- Application tracking or analytics
- Multi-user support

## File structure

```
job-automata/
├── main.py                 # FastAPI app — all endpoints
├── profile.py              # SQLite-backed profile CRUD + fill logging
├── field_matcher.py         # Rule-based form field detection and matching
├── filler.py               # Playwright: open browser, scan fields, fill, attach resume
├── requirements.txt         # Python dependencies
├── db.sqlite               # Auto-created on first run (gitignored)
├── resumes/                # Uploaded resume PDFs (gitignored)
├── test_page.html          # Simple HTML form for testing the filler locally
├── .env.example            # Environment variable template
├── .gitignore
├── LICENSE                 # MIT
├── README.md               # Setup instructions, vision, contributing, roadmap
├── CONTRIBUTING.md         # Guidelines for contributors
├── Dockerfile
├── docker-compose.yml
└── CLAUDE.md               # This file
```

## API endpoints (v0.1)

```
GET    /profile              — Get current profile
PUT    /profile              — Save/update profile
POST   /upload-resume        — Upload resume PDF (multipart form)
POST   /fill                 — Fill a form: { "url": "https://..." }
GET    /logs                 — Get fill history
GET    /health               — Health check
```

## How the filler works

1. Receives a URL from the `/fill` endpoint
2. Launches Playwright with `headless=False` (visible browser window)
3. Navigates to the URL, waits for the page to load
4. Scans the page for all form elements: `<input>`, `<select>`, `<textarea>`, file upload fields
5. For each field, collects signals: `name`, `id`, `label` text, `placeholder`, `autocomplete` attribute, `aria-label`, surrounding text
6. Passes these signals to `field_matcher.py` which maps each field to a profile key
7. Fills matched fields directly in the visible browser
8. For file upload fields (resume/CV), attaches the user's uploaded resume PDF
9. Leaves the browser open — the user reviews and clicks submit
10. Logs the fill attempt (URL, fields detected, fields filled, fields skipped)

## Field matching strategy

### Layer 1: Rule-based (v0.1)
Match form fields to profile data using pattern matching on multiple signals:
- `autocomplete` attribute (most reliable): `given-name`, `family-name`, `email`, `tel`, `street-address`, etc.
- `name` and `id` attributes: pattern match against known variations (e.g., `firstName`, `first_name`, `fname`, `vorname`)
- `<label>` text associated with the field
- `placeholder` text
- `aria-label` attribute

Each profile key has a list of known patterns. The matcher scores candidates and picks the best match above a confidence threshold. Unknown fields are skipped (not guessed).

### Layer 2: LLM fallback (future)
For fields that Layer 1 can't match confidently, send the field context to a local LLM (Ollama) or API. The LLM determines which profile field maps to it, or generates answers for screening questions. This is NOT part of v0.1 but the code should be structured so adding it is trivial — `field_matcher.py` should have a clean interface that a future `llm_matcher.py` can extend.

## Profile data structure

```json
{
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
  "workAuth": "",
  "university": "",
  "degree": "",
  "gradYear": "",
  "customFields": {}
}
```

## Coding conventions

- Python 3.11+ with type hints on all function signatures
- Use `async` for FastAPI endpoints and Playwright operations
- Docstrings on every module, class, and public function
- No classes where a function will do — keep it simple
- Error handling: catch specific exceptions, never bare `except:`
- Logging: use Python's `logging` module, not print statements
- No hardcoded values — use constants at module top or `.env`

## Git conventions

- Commit messages follow Conventional Commits: `type: description`
  - `feat:` new feature
  - `fix:` bug fix
  - `docs:` documentation
  - `chore:` maintenance (deps, config, CI)
  - `test:` tests
  - `refactor:` code restructuring
- One logical change per commit — atomic commits
- Always commit working code — no broken intermediate states

## Setup instructions (for README)

```bash
git clone https://github.com/USERNAME/job-automata.git
cd job-automata
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
python main.py
# Server runs at http://localhost:8000
# API docs at http://localhost:8000/docs
```

## Roadmap (for README)

- [x] Profile storage and management
- [x] Rule-based form field detection and filling
- [x] Resume PDF upload and attachment
- [x] Visible browser with Playwright
- [x] Fill logging and history
- [ ] React dashboard frontend
- [ ] LLM-powered smart field matching (Ollama integration)
- [ ] Screening question answering
- [ ] Multi-platform job listing aggregation
- [ ] Application pipeline tracker (Kanban board)
- [ ] Analytics and conversion funnel
- [ ] Follow-up email drafting and scheduling
- [ ] Docker one-command setup
- [ ] Mobile-responsive review queue

## License

MIT — free to use, modify, and distribute.

## Important notes for Claude Code

- Always run tests after creating modules: `python -c "from module import *; print('OK')"`
- When creating Playwright code, always use `headless=False` — the user must SEE the browser
- SQLite database and resumes/ directory should be in .gitignore
- Keep dependencies minimal — don't add packages unless absolutely necessary
- The field_matcher.py is the core intelligence — spend extra care on comprehensive pattern matching
- Structure field_matcher.py with a clean `match_field(signals: dict) -> Optional[str]` interface so LLM integration later is a drop-in replacement
- Commit after every atomic change — one logical change per commit, do not batch unrelated changes together