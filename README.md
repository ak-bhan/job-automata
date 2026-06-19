# JobAutomata

**Local-first job application form filler. You paste a URL, a real browser opens, fields get filled — you review and submit.**

This is not a spray-and-pray bot. It does not auto-submit. It does not scrape job boards. It fills forms intelligently and leaves the final decision to you.

---

## How it works

1. Save your profile once (name, email, phone, address, education, work preferences, links)
2. Upload your resume PDF (and optionally a cover letter and reference letter)
3. Paste a job application URL into the frontend or POST it to `/fill`
4. Watch a visible Chrome window open and fill the form fields automatically
5. Review what was filled, make any edits, and click Submit yourself

---

## Requirements

- **Python 3.11 or higher** — check with `python --version` or `python3 --version`
- **Node.js 18 or higher** (for the React frontend) — check with `node --version`
- A desktop environment (Playwright opens a real visible browser window — headless servers won't work)

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/USERNAME/job-automata.git
cd job-automata
```

### 2. Create a virtual environment

**Mac / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (Command Prompt)**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

> If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and retry.

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install the Chromium browser

```bash
playwright install chromium
```

### 5. Set up environment variables

**Mac / Linux**
```bash
cp .env.example .env
```

**Windows**
```cmd
copy .env.example .env
```

Edit `.env` if you want to change the host or port (defaults are fine for local use).

### 6. Start the backend

```bash
python main.py
```

The API server starts at `http://localhost:8000`. Interactive API docs at `http://localhost:8000/docs`.

### 7. Start the React frontend

Open a second terminal, activate the same virtual environment if needed, then:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`.

---

## Usage

1. Open `http://localhost:5173` in your browser
2. Go to **Profile** and fill in your details
3. Go to **Documents** and upload your resume (and optionally a cover letter and reference letter)
4. Go to **Fill** and paste a job application URL — a browser window will open and fill the form
5. Review the filled fields in the browser, make any corrections, and submit yourself

---

## API

| Method | Endpoint                   | Description                                      |
|--------|----------------------------|--------------------------------------------------|
| GET    | /health                    | Health check                                     |
| GET    | /profile                   | Get saved profile                                |
| PUT    | /profile                   | Save or update profile                           |
| POST   | /upload-resume             | Upload resume PDF (multipart/form-data)          |
| POST   | /upload-cover-letter       | Upload cover letter PDF (multipart/form-data)    |
| POST   | /upload-reference-letter   | Upload reference letter PDF (multipart/form-data)|
| POST   | /fill                      | Open browser and fill form at a URL              |
| GET    | /logs                      | View fill history                                |

### Example: save profile

**Mac / Linux**
```bash
curl -X PUT http://localhost:8000/profile \
  -H "Content-Type: application/json" \
  -d '{
    "firstName": "Ada",
    "lastName": "Lovelace",
    "email": "ada@example.com",
    "phone": "+1-555-0100",
    "linkedin": "https://linkedin.com/in/ada"
  }'
```

**Windows (PowerShell)**
```powershell
Invoke-RestMethod -Method Put -Uri http://localhost:8000/profile `
  -ContentType "application/json" `
  -Body '{"firstName":"Ada","lastName":"Lovelace","email":"ada@example.com"}'
```

### Example: upload resume

**Mac / Linux**
```bash
curl -X POST http://localhost:8000/upload-resume \
  -F "file=@/path/to/resume.pdf"
```

**Windows (PowerShell)**
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/upload-resume `
  -Form @{ file = Get-Item "C:\path\to\resume.pdf" }
```

### Example: fill a form

**Mac / Linux**
```bash
curl -X POST http://localhost:8000/fill \
  -H "Content-Type: application/json" \
  -d '{"url": "https://jobs.example.com/apply/12345"}'
```

**Windows (PowerShell)**
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/fill `
  -ContentType "application/json" `
  -Body '{"url":"https://jobs.example.com/apply/12345"}'
```

---

## Profile fields

| Field          | Description                          |
|----------------|--------------------------------------|
| firstName      | First name                           |
| lastName       | Last name                            |
| email          | Email address                        |
| phone          | Phone number                         |
| address        | Street address                       |
| city           | City                                 |
| zip            | ZIP / postal code                    |
| country        | Country                              |
| nationality    | Nationality                          |
| linkedin       | LinkedIn profile URL                 |
| github         | GitHub profile URL                   |
| portfolio      | Portfolio / personal site URL        |
| currentTitle   | Current job title                    |
| currentCompany | Current employer                     |
| yearsExp       | Years of experience                  |
| salaryExpect   | Salary expectation                   |
| noticePeriod   | Notice period                        |
| startDate      | Earliest start date                  |
| dateOfBirth    | Date of birth                        |
| workAuth       | Work authorization status            |
| university     | University / college                 |
| degree         | Degree name                          |
| gradYear       | Graduation year                      |
| customFields   | Any extra key-value pairs            |

---

## Architecture

- **Backend:** Python 3.11+ · FastAPI · Uvicorn
- **Frontend:** React 18 · Vite · Tailwind CSS
- **Browser:** Playwright (visible Chromium — never headless)
- **Database:** SQLite (single `db.sqlite` file, no server needed)
- **Field matching:** Rule-based pattern matching across `autocomplete`, `name`, `id`, `label`, `placeholder`, `aria-label` signals
- **LLM:** Not in v0.1 — architecture is ready for Ollama or any OpenAI-compatible API as a drop-in layer

---

## Troubleshooting

**`python` not found on Mac/Linux**
Use `python3` instead — or create an alias: `alias python=python3`.

**Playwright browser fails to launch on Linux**
Install system dependencies:
```bash
playwright install-deps chromium
```

**PowerShell says "running scripts is disabled"**
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**`pip install` fails with "externally managed environment" (Linux)**
You must use a virtual environment — see step 2 above. Do not use `--break-system-packages`.

**Port 8000 already in use**
Set a different port in `.env`:
```
PORT=8001
```

**Frontend cannot reach the backend**
Make sure `python main.py` is running before starting `npm run dev`. Both must be running at the same time.

---

## Roadmap

- [x] Profile storage and management
- [x] Rule-based form field detection and filling
- [x] Resume, cover letter, and reference letter upload and attachment
- [x] Visible browser with Playwright
- [x] Fill logging and history
- [x] React dashboard frontend
- [ ] LLM-powered smart field matching (Ollama integration)
- [ ] Screening question answering
- [ ] Multi-platform job listing aggregation
- [ ] Application pipeline tracker (Kanban board)
- [ ] Analytics and conversion funnel
- [ ] Follow-up email drafting and scheduling
- [ ] Docker one-command setup
- [ ] Mobile-responsive review queue

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and PRs are welcome.

---

## License

[MIT](LICENSE)
