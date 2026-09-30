# Data sources

Every number the synthetic generator and the risk model rely on, where it comes from, and what is still an assumption. Checked 26 September 2026. For the statistics used in the pitch (problem statement), see [PITCH_FACTS.md](PITCH_FACTS.md).

**What the demo data is:** synthetic cases (IDs `SYN-…`) whose aggregate shape is fitted to the published figures below. No real case, party, or magistrate appears anywhere in the app.

## Sourced figures

| Figure | Value used | Source | Where in the source |
|---|---|---|---|
| Backlog thresholds (disposition targets) | Primary 6 mo · District 12 · Resident Magistrate 12 · High Court 24 · Court of Appeal 24 | National Audit Office of Tanzania, *Management of Backlog of Cases by the Justice System*, performance audit report, March 2022. [PDF](https://www.nao.go.tz/uploads/reports/MANAGEMENT_OF_BACKLOG_OF_CASES_BY_THE_JUSTICE_SYSTEM.pdf), saved here as `NAO_backlog_of_cases.pdf` | Table 1.1, PDF page 28. The NAO cites the *Judiciary Functions Strategic Plan 2015/16–2020/21* |
| Backlog as a share of pending cases, by level | High Court 14% · subordinate courts (Primary, District, RM) 23% · overall 15% | Judiciary of Tanzania, *Case Backlog Reduction Strategies and their Implementation: The Tanzanian Judiciary Experience*, presented at the Africa Judicial Conference 2024. [PDF](https://judiciary.go.ug/files/downloads/Case%20Backlog%20Reduction%20Strategies%20and%20their%20Implementation%20The%20Tanzanian%20Judiciary%20Experience_AJC%202024.pdf), saved here as `JoT_backlog_strategies_AJC_2024.pdf` | Slide 7, "Backlog Status in 2020" (Court of Appeal 23% is shown too but not modelled) |
| Overall backlog trend | 10% (Dec 2021) → 9% (Jun 2022) → 6% (Dec 2022) → 3% (Jun 2023) | Same deck | Slide 18, "Percentage of case backlog" |
| Filings by court level, 2025 | Primary 176,687 · District 35,144 · RM 6,033 · High Court 21,518 (also CoA 3,214, Juvenile 1,225; total 243,848) | Statement by the Chief Registrar of the Judiciary, Hon. Eva Nkya, reported in *Daily News*, "Why case backlogs drop sharply amid judicial reforms success", 13 May 2026. [Article](https://dailynews.co.tz/why-case-backlogs-drop-sharply-amid-judicial-reforms-success/) | Filed / decided / pending per level |
| Criminal share of filings, 2025 | 138,368 of 243,848 = 56.7% | Same article | Civil/criminal split |
| Forensic report turnaround | 47 days on average; some samples up to a year | NAO report (March 2022) | Table 5.1 (PDF page 78), Table 5.2 (page 79) |

### How they are used
- **Thresholds** → `DISPOSITION_TARGET_MONTHS` in [justiceflow/config.py](../../justiceflow/config.py). They define the label the model predicts.
- **Filing shares and criminal share** → how many synthetic cases are drawn at each level and of each type.
- **Backlog shares** → the generator calibrates hearing gaps until the share of *pending* cases older than their target matches the Judiciary's figure at each level ([justiceflow/synthetic.py](../../justiceflow/synthetic.py)). Result with 12,000 cases: Primary 23.1%, District 23.2%, RM 23.6%, High Court 13.4%.
- **Forensic turnaround** → how long a case stays adjourned waiting for a Government Chemist report.

### Known mismatches (say so in the pitch)
- **Years are mixed.** Backlog shares are from 2020, the latest per-level split found; filings are from 2025. By 2023 the Judiciary reports overall backlog of only 3%, so the demo shows a heavier backlog than today's courts. That suits a pre-reform "baseline" scenario, but label it as such.
- **Subordinate courts share one figure.** The 2020 slide gives 23% for Primary, District and RM together.
- **Overall synthetic backlog is about 21%, against 15% published**, because the synthetic pending caseload has a larger share of Primary cases than the real one (synthetic pending: Primary 553, HC 313, District 311, RM 55; real 2025 pending: HC 10,381, District 8,214, Primary 7,240, RM 2,303).
- **The filings figures come from a newspaper report of an official statement**, not the Judiciary's report itself. Confirm them against the *Comprehensive Performance Report of the Judicial Functions* (judiciary.go.tz blocks scripted downloads, so download it in a browser).

## Still assumptions (no public source found yet)

| Assumption | Current value | Where to get the real figure |
|---|---|---|
| Adjournment probability per hearing (advocate, prosecution, court-side) | 3–18% by type | Field sample of case files (see the data-request letter), or JSDS2 extract |
| Share of criminal cases needing a forensic report | 25% | NPS / Police, or a case-file sample |
| Hearings needed to dispose, by case type | 2–6 | Case-file sample |
| Mean days between hearings (before calibration) | 21–55 by level | Published cause lists, tracked over several weeks |
| Rural effects (less representation, more court-side adjournments) | +25% gaps, +8 points court-side adjournment | Case-file sample across urban and rural stations |
| Which stations have which court levels | Representative subset | Judiciary court map (jmap.judiciary.go.tz) |

## Useful but not used (context only)
- **Adjournment reasons in criminal cases** (NAO, Figure 4.1, PDF page 68): of adjourned cases in NPS files, 60% were due to incomplete investigation, 25% to the State Attorney appearing without the case's status, and 15% to the State Attorney appearing without the file. All three are prosecution-side. The sample came from NPS files, so it can't tell us the share of advocate or court-side adjournments. It does support treating "prosecution delay" as the dominant external delay in criminal cases.
- **How often cases are adjourned** (NAO, Table 4.3, PDF page 67): the most-adjourned case in each sampled court averaged 31 adjournments (High Court), 68 (RM) and 48 (District), with a minimum of 2 everywhere. These are extremes, not averages, so they aren't used for calibration.
- **Performance targets** (NAO, section 3.3): judges are expected to dispose 220 cases a year and magistrates 250.
