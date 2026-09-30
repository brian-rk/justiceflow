# JusticeFlow TZ

Case-delay risk prediction and cause-list optimisation for Tanzanian courts: a read-only decision-support overlay built for the eGA-RIDC AI & Data Science Hackathon. It never writes to JoT-eCMS or JSDS2, and no schedule is final until a registrar approves it.

```
justiceflow/   ML core: synthetic data, risk model, fairness gate, CP-SAT scheduler, escalation rule
backend/       FastAPI service + database (SRS 8.3), wraps the ML core
frontend/      React + TypeScript + Tailwind (Vite) web app, one set of pages per role (SRS 5.1)
notebooks/     Colab walkthrough of the ML core (SRS 8.1 browser-only path)
tests/         ML core tests;  backend/tests/ = API tests
```

## Run the web app locally

Needs Python 3.11+ and Node 20+. Use two terminals.

**1. Backend.** First time only, inside the `backend` folder:

```
cd backend
pip install -r requirements.txt
python -m app.seed                          # demo data + trained model (~1 min)
```

Then start it, from any folder:

```
python backend/run.py          # or, inside backend/:  python run.py
```

`run.py` tells you if the backend is already running instead of failing with a port error.

**2. Frontend.** In a second terminal:

```
cd frontend
npm install
npm run dev
```

Common backend errors (if you start it with `uvicorn` directly instead of `run.py`):
- `No module named 'app'`: you are not in the `backend` folder. Run `cd backend` first.
- `[Errno 10048] ... only one usage of each socket address`: something is already using port 8000, often a backend you started earlier. Close that terminal, or use `--port 8001` and change the proxy port in `frontend/vite.config.ts` to match.

Open http://localhost:5173 and sign in with any demo account (password `demo1234`). The login page has one-click buttons for each.

| Username | Role | Lands on |
|---|---|---|
| `clerk` | Court Clerk | Case data entry |
| `registrar` | Court Registrar | Dashboard → Review queue → Cause list |
| `magistrate` | Magistrate / Judge | My schedule (read-only) |
| `manager` | Court Management | Dashboard, Escalations, Reports, Fairness audit |
| `admin` | Administrator | Settings (targets, roster, users) |

API docs (Swagger) are at http://localhost:8000/docs.

**Demo data and "today":** the seed replays three past weekly review cycles, so escalations and schedules already have data, and leaves next week's cause list awaiting approval. To keep the demo stable, set `JF_AS_OF=2026-09-26` (PowerShell: `$env:JF_AS_OF='2026-09-26'`) before both seeding and starting the server.

**Database:** SQLite by default (`backend/justiceflow.db`). For PostgreSQL (Supabase / Neon), set `DATABASE_URL=postgresql+psycopg://user:pass@host/db`. No code changes are needed.

## Tests

```
python -m pytest tests            # ML core (repo root)
cd backend && python -m pytest tests   # API: roles, gates, clerk -> registrar flow
cd frontend && npm run typecheck
```

## Where each requirement lives

| SRS | Where | What it does |
|---|---|---|
| FR-1, FR-2 | [justiceflow/model.py](justiceflow/model.py), [backend/app/services.py](backend/app/services.py) `score_cases` | Scored at filing; re-scored every time a clerk records a hearing |
| FR-3 | clerk hearing form → `delay_status` | Advocate / prosecution / forensic flags → "Court-controllable" or "Externally blocked: …" |
| FR-4 | [justiceflow/fairness.py](justiceflow/fairness.py), Fairness audit page | Stratified false-positive "High" rate by region; failed gate returns 409 on scheduling and real-data scoring |
| FR-5 | [justiceflow/scheduler.py](justiceflow/scheduler.py), Cause list page | OR-Tools CP-SAT over the whole week |
| FR-6 | Cause list + Review queue + Case detail | Approve / edit / remove listings; approve / override risk scores; reasons required and logged; undecided listings are never scheduled |
| FR-7 | `find_escalations`, Escalations page | High for N consecutive cycles with no registrar action → note to court management, who must record a response |
| FR-8 | Case detail | Driving factors with effect sizes, delay status, full hearing history |
| FR-9 | the web app | Dashboards per role |
| FR-10 | [justiceflow/ingest.py](justiceflow/ingest.py) | Read-only loaders; nothing writes to source systems |
| FR-11 | Case data entry page, `POST /api/cases/{id}/hearings` | Clerk-only; registrars cannot record hearings and clerks cannot approve |
| 5.1 Reports | Reports page | Backlog trend vs the NAO 12-month benchmark, by level and station |
| 5.1 Settings | Settings page | Disposition targets, thresholds, magistrate roster and daily capacity, user accounts |

Region and court station are **never** model inputs; `feature_matrix` asserts this and a test enforces it.

**Auth** is local JWT with bcrypt (`backend/app/security.py`), so it runs with no external service. Swapping in Supabase Auth / Firebase Auth (SRS 8.3) only replaces `current_user`.

## Data: what is real and where it comes from

All cases in the demo are **synthetic** (IDs `SYN-…`). Their aggregate shape is fitted to published figures:
- **Disposition targets:** NAO, March 2022, Table 1.1.
- **Backlog share of pending cases by court level (2020):** Judiciary of Tanzania, AJC 2024 presentation, slide 7.
- **Filings by court level and criminal share (2025):** Chief Registrar's statement, reported in *Daily News*, 13 May 2026.
- **Forensic report turnaround:** NAO, Table 5.1.

The full register, with page references, known mismatches and the figures that are still assumptions, is in [data/sources/SOURCES.md](data/sources/SOURCES.md). The source PDFs are saved next to it. In code, each figure is tagged `SOURCE:` or `ASSUMPTION`.

**Getting real data:**
- [data/TANZLII_COLLECTION_GUIDE.md](data/TANZLII_COLLECTION_GUIDE.md): hand-collect 60–100 judgments to validate the at-filing prediction (FR-1).
- [data/requests/Judiciary_data_request.md](data/requests/Judiciary_data_request.md): a draft letter, sent through eGA-RIDC, asking the Judiciary Data Hub for anonymised aggregate statistics.
- [data/requests/TanzLII_bulk_access_request.md](data/requests/TanzLII_bulk_access_request.md): a draft email to info@tanzlii.org asking for API or bulk metadata access, which TanzLII's terms require instead of scraping.
- `python -m justiceflow.check_tanzlii data/tanzlii_sample.csv` checks the hand-collected sample and scores the model on it.

**Pitch figures:** every statistic in the problem statement has been checked against its source. Safe wording and page references are in [data/sources/PITCH_FACTS.md](data/sources/PITCH_FACTS.md).

## References
- **JustiFlow: Differentiated Caseflow Management** (India). The closest working precedent: case classification, greedy priority-based scheduling, and predictive analytics. JusticeFlow TZ replaces the greedy scheduler with whole-week CP-SAT optimisation, and adds fairness auditing and external-delay awareness. [GitHub](https://github.com/vigneshkriishna/JustiFlow-Differentiated_caseflow_management-) (MIT licence)
- **de Oliveira, R. S., Reis Jr., A. S., & Nascimento, E. G. S. (2022).** Predicting the number of days in court cases using artificial intelligence. *PLOS ONE* 17(5): e0269008. Precedent for predicting case duration with machine learning (a Brazilian labour court, about 334,000 cases, comparing gradient boosting, AdaBoost and neural networks). [doi:10.1371/journal.pone.0269008](https://doi.org/10.1371/journal.pone.0269008)
- **Data sources:** see [data/sources/SOURCES.md](data/sources/SOURCES.md) and [data/sources/PITCH_FACTS.md](data/sources/PITCH_FACTS.md).

## Colab path (SRS 8.1)

The ML core also runs in the browser: zip `justiceflow/`, open [notebooks/JusticeFlow_TZ.ipynb](notebooks/JusticeFlow_TZ.ipynb) in Colab, upload the zip, and run all cells. `python -m justiceflow` runs the same pipeline from a terminal.
