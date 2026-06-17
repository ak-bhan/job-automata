# JobAutomata

**Local-first job application form filler. You paste a URL, a real browser opens, fields get filled — you review and submit.**

This is not a spray-and-pray bot. It does not auto-submit. It does not scrape job boards. It fills forms intelligently and leaves the final decision to you.

---

## How it works

1. Save your profile once (name, email, phone, address, education, work preferences, links)
2. Upload your resume PDF
3. POST a job application URL to `/fill`
4. Watch a visible Chrome window open and fill the form fields automatically
5. Review what was filled, make any edits, and click Submit yourself

---

## Quickstart

```bash
git clone https://github.com/USERNAME/job-automata.git
cd job-automata
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
python main.py
```

The server starts at `http://localhost:8000`. Interactive API docs at `http://localhost:8000/docs`.

---

## API

| Method | Endpoint        | Description                              |
|--------|-----------------|------------------------------------------|
| GET    | /health         | Health check                             |
| GET    | /profile        | Get saved profile                        |
| PUT    | /profile        | Save or update profile                   |
| POST   | /upload-resume  | Upload resume PDF (multipart/form-data)  |
| POST   | /fill           | Open browser and fill form at a URL      |
| GET    | /logs           | View fill history                        |

### Example: save profile

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

### Example: fill a form

```bash
curl -X POST http://localhost:8000/fill \
  -H "Content-Type: application/json" \
  -d '{"url": "https://jobs.example.com/apply/12345"}'
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
| workAuth       | Work authorization status            |
| university     | University / college                 |
| degree         | Degree name                          |
| gradYear       | Graduation year                      |
| customFields   | Any extra key-value pairs            |

---

## Architecture

- **Backend:** Python 3.11+ · FastAPI · Uvicorn
- **Browser:** Playwright (visible Chromium — never headless)
- **Database:** SQLite (single `db.sqlite` file, no server needed)
- **Field matching:** Rule-based pattern matching across `autocomplete`, `name`, `id`, `label`, `placeholder`, `aria-label` signals
- **LLM:** Not in v0.1 — architecture is ready for Ollama or any OpenAI-compatible API as a drop-in layer

---

## Roadmap

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

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and PRs are welcome.

---

## License

[MIT](LICENSE)
