# JusticeFlow TZ

Case-delay early warning and cause-list support for the Judiciary of Tanzania (**Tanzania Mainland**; Zanzibar has its own judiciary and is not covered). A read-only decision-support overlay built for the eGA-RIDC AI & Data Science Hackathon. It never writes to JoT-eCMS or JSDS2, and no schedule is final until a registrar approves it. The interface is in **English and Kiswahili**.

**The problem in 2026.** Backlog has fallen sharply: in 2025 only 5% of pending cases were backlog, and 84.5% of that backlog sat at the Court of Appeal ([PITCH_FACTS.md](data/sources/PITCH_FACTS.md), row 10). So JusticeFlow is not pitched as "cutting backlog in the lower courts". Its job is to **keep courts on target**: flag the few cases sliding towards an overrun early, make delays the court cannot fix (police and prosecution, the Government Chemist, witnesses, records) visible to the bodies that can fix them, and keep remand cases moving. It models all five levels, including the Court of Appeal.

**How it fits court practice.** In Tanzania the next date is fixed by the judge or magistrate in open court, and a case stays with its assigned officer. JusticeFlow follows that:
- **Next-date suggestion** at the end of each hearing, with its reasons (risk, a forensic report pending, accused in remand, room on the bench). The clerk records the date actually fixed.
- **Weekly cause list** starts from the dates fixed in court. The optimiser only fills free slots: cases with no date yet, and high-risk cases it suggests bringing forward. Cases never move to another magistrate.
- **Needs-attention list** for the registrar: dates passed with no hearing recorded, cases with no date, high-risk cases fixed far out, the same external delay three times in a row, and accused in remand over six months.
- **High Court criminal sessions** (murder and other committal trials) are planned as sessions, ranked by time in remand, not on the weekly list.
- **Escalations** name who can unblock each case and print as an agenda for the case-flow committee.

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

**Demo data and "today":** the seed replays three past weeks the way a registry works them (dates fixed in court, hearings held, next dates fixed), so escalations, schedules and the needs-attention list already have data. It leaves next week's cause list and one criminal session awaiting approval. To keep the demo stable, set `JF_AS_OF=2026-09-26` (PowerShell: `$env:JF_AS_OF='2026-09-26'`) before both seeding and starting the server.

**Calibration:** `python -m app.seed` fits the synthetic data to the Judiciary's **2025** figures (the default). `python -m app.seed --calibration 2020` gives the pre-reform, high-backlog baseline instead, which is useful to show the system under heavy load. Both are labelled in [data/sources/SOURCES.md](data/sources/SOURCES.md).

**Language:** the EN / SW switch is in the top bar and on the login page. `cd frontend && npm run i18n:check` lists any interface text without a Kiswahili translation. The Kiswahili was written for this prototype and should be reviewed by a court officer before use.

**Database:** SQLite by default (`backend/justiceflow.db`). For PostgreSQL (Supabase / Neon), set `DATABASE_URL=postgresql+psycopg://user:pass@host/db`. No code changes are needed.

## Tests

```
python -m pytest tests            # ML core (repo root)
cd backend && python -m pytest tests   # API: roles, gates, clerk -> registrar flow
cd frontend && npm run typecheck && npm run i18n:check
python -m justiceflow.check_tanzlii data/validation/tanzlii_search_sample.csv   # real-case test
```

## Where each requirement lives

| SRS | Where | What it does |
|---|---|---|
| FR-1, FR-2 | [justiceflow/model.py](justiceflow/model.py), [backend/app/services.py](backend/app/services.py) `score_cases` | Scored at filing; re-scored every time a clerk records a hearing |
| FR-3 | clerk hearing form → `delay_status` | Advocate, prosecution / investigation, forensic, witness and appeal-record flags → "Court-controllable" or "Externally blocked: …", plus who can unblock it |
| FR-4 | [justiceflow/fairness.py](justiceflow/fairness.py), Fairness audit page | Stratified false-positive "High" rate by region; failed gate returns 409 on scheduling and real-data scoring |
| FR-5 | [justiceflow/scheduler.py](justiceflow/scheduler.py), Cause list page | OR-Tools CP-SAT fills the free capacity left after the dates fixed in court; cases stay with their assigned officer; remand cases get priority. Next-date suggestions: `suggest_next_date` in [services.py](backend/app/services.py). Criminal sessions: Criminal sessions page |
| FR-6 | Cause list + Review queue + Case detail | Approve / edit / remove listings; approve / override risk scores; reasons required and logged; undecided listings are never scheduled |
| FR-7 | `find_escalations`, Escalations page, Committee agenda | High for N consecutive weeks with no registrar action → routed to the body that can unblock it (Police and NPS, Government Chemist, advocates, the court) for the case-flow committee, which must record a response |
| FR-8 | Case detail | Driving factors with effect sizes, delay status, full hearing history |
| FR-9 | the web app | Dashboards per role |
| FR-10 | [justiceflow/ingest.py](justiceflow/ingest.py) | Read-only loaders; nothing writes to source systems |
| FR-11 | Case data entry page, `POST /api/cases/{id}/hearings` | Clerk-only; registrars cannot record hearings and clerks cannot approve |
| 5.1 Reports | Reports page | Backlog trend vs the NAO 12-month benchmark; by court level next to the Judiciary's published 2025 figures; by High Court division and station |
| 5.1 Settings | Settings page | Disposition targets, thresholds, magistrate roster and daily capacity, user accounts |

Region and court station are **never** model inputs; `feature_matrix` asserts this and a test enforces it.

**Real courts:** every case sits at a real court from the Judiciary's court map: 300 courts in seven regions, from Kariakoo Primary Court to the Dar es Salaam High Court Land Division ([justiceflow/courts.csv](justiceflow/courts.csv), rebuilt with `python -m justiceflow.build_courts --fetch`). The clerk picks region, then court.

**Court rules built in** ([justiceflow/config.py](justiceflow/config.py)): five levels (Primary, District, Resident Magistrate, High Court with its Land, Labour, Commercial and Corruption & Economic Crimes divisions, Court of Appeal); land cases only at the High Court (they otherwise go to the District Land and Housing Tribunals, outside the Judiciary); no advocates in Primary Courts (Magistrates' Courts Act, s.33); murder not bailable, so those accused are always in remand. Registration refuses cases a court cannot hear.

**Auth** is local JWT with bcrypt (`backend/app/security.py`), so it runs with no external service. Swapping in Supabase Auth / Firebase Auth (SRS 8.3) only replaces `current_user`.

## Data: what is real and where it comes from

All cases in the demo are **synthetic** (IDs `SYN-…`, at about 1:100 of real volume). Their aggregate shape is fitted to published figures:
- **Average days from filing to decision, by court (2025):** Judiciary of Tanzania, *Comprehensive Performance Report of the Judicial Functions 2025*, Chart 3.5. The generator is calibrated to these; the backlog shares it then produces are a check against the same report.
- **Filings, criminal share and workload per officer, by court (2025):** the same report, Table 3.1, court cards, Table 3.10.
- **Disposition targets:** NAO, March 2022, Table 1.1.
- **2020 baseline (optional):** backlog share of pending cases by court level, AJC 2024 presentation, slide 7.
- **Forensic report turnaround:** NAO, Table 5.1.

**Tested on real cases:** [data/validation/](data/validation/README.md) scores the model on 56 decided High Court and Court of Appeal cases from TanzLII listings. It ranks them no better than knowing the court level alone (AUC 0.65 vs 0.71), rates none of the 20 overruns High, and does no better than chance within one court. Real Judiciary data is needed before the risk score means anything for a single case; say so in the pitch.

The full register, with page references, known mismatches and the figures that are still assumptions, is in [data/sources/SOURCES.md](data/sources/SOURCES.md). The source PDFs are saved next to it. In code, each figure is tagged `SOURCE:` or `ASSUMPTION`.

**Getting real data:**
- [data/TANZLII_COLLECTION_GUIDE.md](data/TANZLII_COLLECTION_GUIDE.md): hand-collect 60–100 judgments to validate the at-filing prediction (FR-1).
- [data/requests/Judiciary_data_request.md](data/requests/Judiciary_data_request.md): a draft letter, sent through eGA-RIDC, asking the Judiciary Data Hub for anonymised aggregate statistics.
- [data/requests/TanzLII_bulk_access_request.md](data/requests/TanzLII_bulk_access_request.md): a draft email to info@tanzlii.org asking for API or bulk metadata access, which TanzLII's terms require instead of scraping.
- `python -m justiceflow.check_tanzlii data/tanzlii_sample.csv` checks a hand-collected sample and scores the model on it, against a court-level-only baseline. It accepts exact filing dates or just the filing year from the case number.

**Pitch figures:** every statistic in the problem statement has been checked against its source. Safe wording and page references are in [data/sources/PITCH_FACTS.md](data/sources/PITCH_FACTS.md).

## References
- **JustiFlow: Differentiated Caseflow Management** (India). The closest working precedent: case classification, greedy priority-based scheduling, and predictive analytics. JusticeFlow TZ keeps the dates fixed in court and uses CP-SAT only to fill free capacity, and adds fairness auditing and external-delay awareness. [GitHub](https://github.com/vigneshkriishna/JustiFlow-Differentiated_caseflow_management-) (MIT licence)
- **de Oliveira, R. S., Reis Jr., A. S., & Nascimento, E. G. S. (2022).** Predicting the number of days in court cases using artificial intelligence. *PLOS ONE* 17(5): e0269008. Precedent for predicting case duration with machine learning (a Brazilian labour court, about 334,000 cases, comparing gradient boosting, AdaBoost and neural networks). [doi:10.1371/journal.pone.0269008](https://doi.org/10.1371/journal.pone.0269008)
- **Data sources:** see [data/sources/SOURCES.md](data/sources/SOURCES.md) and [data/sources/PITCH_FACTS.md](data/sources/PITCH_FACTS.md).

## Colab path (SRS 8.1)

The ML core also runs in the browser: zip `justiceflow/`, open [notebooks/JusticeFlow_TZ.ipynb](notebooks/JusticeFlow_TZ.ipynb) in Colab, upload the zip, and run all cells. `python -m justiceflow` runs the same pipeline from a terminal.
