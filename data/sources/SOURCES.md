# Data sources

Every number the synthetic generator and the risk model rely on, where it comes from, and what is still an assumption. Checked 26 September 2026. For the statistics used in the pitch (problem statement), see [PITCH_FACTS.md](PITCH_FACTS.md).

**What the demo data is:** synthetic cases (IDs `SYN-…`) whose aggregate shape is fitted to the published figures below. No real case, party, or magistrate appears anywhere in the app. Scope: the Judiciary of Tanzania, **Tanzania Mainland** only. Zanzibar has a separate judiciary and is not modelled.

## Calibration (updated 11 October 2026)

The generator has two calibrations ([justiceflow/synthetic.py](../../justiceflow/synthetic.py)):

* **2025, the default.** Hearing gaps are scaled until the **average days from filing to decision** for cases decided in the last year match the Judiciary's 2025 report (Chart 3.5, p.47; court cards pp.48-50). The **backlog share** the data then shows is not tuned, so it is a check against the same report:

  | Court | Avg days to decision: synthetic / published | Backlog share of pending: synthetic / published |
  |---|---|---|
  | Primary | 32 / 30 | 0.5% / 0.0% |
  | District | 116 / 116 | 1.0% / 0.7% |
  | Resident Magistrate | 150 / 150 | 4.3% / 4.7% |
  | High Court | 186 / 186 | 0.0% / 1.2% |
  | Court of Appeal | 875 / 816 | 44.9% / 30.7% |

  The time to decision matches at every level. Backlog is close at the subordinate courts, too low at the High Court and too high at the Court of Appeal: the synthetic Court of Appeal has a longer tail of slow appeals than the real one.
* **2020, optional** (`python -m app.seed --calibration 2020`). Gaps are scaled until the backlog share of pending cases matches the 2020 figures (AJC 2024 deck, slide 7). This is the pre-reform, high-backlog picture.

**Tested on real cases:** see [../validation/README.md](../validation/README.md). On 56 decided High Court and Court of Appeal cases the 2025-calibrated model ranks no better than the court level alone (AUC 0.65 vs 0.71); the 2020-calibrated model does worse than chance (0.48).

## Sourced figures

| Figure | Value used | Source | Where in the source |
|---|---|---|---|
| Backlog thresholds (disposition targets) | Primary 6 mo · District 12 · Resident Magistrate 12 · High Court 24 · Court of Appeal 24 | National Audit Office of Tanzania, *Management of Backlog of Cases by the Justice System*, performance audit report, March 2022. [PDF](https://www.nao.go.tz/uploads/reports/MANAGEMENT_OF_BACKLOG_OF_CASES_BY_THE_JUSTICE_SYSTEM.pdf), saved here as `NAO_backlog_of_cases.pdf` | Table 1.1, PDF page 28. The NAO cites the *Judiciary Functions Strategic Plan 2015/16–2020/21* |
| Backlog as a share of pending cases, by level | High Court 14% · subordinate courts (Primary, District, RM) 23% · overall 15% | Judiciary of Tanzania, *Case Backlog Reduction Strategies and their Implementation: The Tanzanian Judiciary Experience*, presented at the Africa Judicial Conference 2024. [PDF](https://judiciary.go.ug/files/downloads/Case%20Backlog%20Reduction%20Strategies%20and%20their%20Implementation%20The%20Tanzanian%20Judiciary%20Experience_AJC%202024.pdf), saved here as `JoT_backlog_strategies_AJC_2024.pdf` | Slide 7, "Backlog Status in 2020" (Court of Appeal 23% is shown too but not modelled) |
| Overall backlog trend | 10% (Dec 2021) → 9% (Jun 2022) → 6% (Dec 2022) → 3% (Jun 2023) | Same deck | Slide 18, "Percentage of case backlog" |
| Filings by court level, 2025 | Primary 176,687 · District 35,144 · RM 6,033 · High Court 21,518 (also CoA 3,214, Juvenile 1,225; total 243,848) | Judiciary of Tanzania, *Comprehensive Performance Report of the Judicial Functions 2025* (saved: `Comprehensive Performance Report of the Judicial Functions2025.pdf`). Also announced by the Chief Registrar, *Daily News*, 13 May 2026 | Table 3.1, PDF p.41 (filed by court level); p.40 (civil/criminal split) |
| Criminal share of filings, 2025 | 138,368 of 243,848 = 56.7% | Same report | PDF p.40 ("C: 105,480 \| Cr: 138,368") |
| Forensic report turnaround | 47 days on average; some samples up to a year | NAO report (March 2022) | Table 5.1 (PDF page 78), Table 5.2 (page 79) |
| Average days from filing to decision, 2025 | Primary 30 · District 116 · RM 150 · High Court 186 · Court of Appeal 816 | Judiciary 2025 Performance Report | Chart 3.5 (p.47) and the court cards (pp.48-50) |
| Pending and backlog cases, end 2025 | Pending: Primary 7,240 · District 8,214 · RM 2,303 · High Court 10,381 · CoA 5,039. Backlog: 1 · 54 · 108 · 121 · 1,547 | Same report | Tables 3.3 and 3.4 (pp.41-42) |
| Criminal share of filings by court, 2025 | Primary 60.5% · District 59.9% · RM 39.3% · High Court 28.9% · CoA 37.8% | Same report | Court cards (filed C / Cr), pp.48-50 |
| Workload per judge / magistrate / panel, 2025 | Primary 227 · District 167 · RM 125 · High Court 310 · CoA 787 | Same report | Table 3.10 (p.46). Used to size each synthetic bench |
| High Court divisions | Commercial, Labour, Land, Corruption and Economic Crimes (plus the Mediation Centre) | Same report | s.1.3.2 |

### How they are used
- **Thresholds** → `DISPOSITION_TARGET_MONTHS` in [justiceflow/config.py](../../justiceflow/config.py). They define the label the model predicts.
- **Filing shares and criminal share** → how many synthetic cases are drawn at each level and of each type.
- **Backlog shares** → the generator calibrates hearing gaps until the share of *pending* cases older than their target matches the Judiciary's figure at each level ([justiceflow/synthetic.py](../../justiceflow/synthetic.py)). Result with 12,000 cases: Primary 23.1%, District 23.2%, RM 23.6%, High Court 13.4%.
- **Forensic turnaround** → how long a case stays adjourned waiting for a Government Chemist report.

### Known mismatches (say so in the pitch)
- **Fixed (October 2026): the demo now uses 2025 levels by default.** The note below describes the 2020 calibration, still available with `--calibration 2020`.
- **The demo used 2020 backlog levels; today's are far lower.** The 2025 report (Tables 3.3 and 3.4, p.42) gives backlog as a share of pending cases: High Court 121 / 10,381 = **1.2%**, RM 108 / 2,303 = **4.7%**, District 54 / 8,214 = **0.7%**, Primary 1 / 7,240 = **~0%**, Court of Appeal 1,547 / 5,039 = **30.7%**; overall 1,831 / 33,379 = **5.5%**. The demo calibrates to 2020 (High Court 14%, subordinate courts 23%), so it shows a **pre-reform baseline**, not today's courts. Label it as such, or recalibrate to 2025.
- **In 2025 the backlog is concentrated at the Court of Appeal** (1,547 of 1,831 backlog cases, 84.5%). JusticeFlow TZ now models the Court of Appeal.
- **Subordinate courts share one figure.** The 2020 slide gives 23% for Primary, District and RM together.
- **Overall synthetic backlog is about 21%, against 15% published**, because the synthetic pending caseload has a larger share of Primary cases than the real one (synthetic pending: Primary 553, HC 313, District 311, RM 55; real 2025 pending: HC 10,381, District 8,214, Primary 7,240, RM 2,303).
- **Filings are confirmed** against the Judiciary's own 2025 report (Table 3.1, p.41): every figure matches the *Daily News* report exactly.

## Legal rules used (check with the Judiciary before relying on them)

| Rule | Where it is used | Source |
|---|---|---|
| Land disputes are heard by the District Land and Housing Tribunals (Ministry of Lands) and the High Court Land Division, not by Primary, District or RM courts | `CASE_TYPES_BY_LEVEL`; case registration refuses land cases below the High Court | Land Disputes Courts Act, Cap. 216 |
| Advocates may not appear in a Primary Court | Representation is always "no" at Primary level; registration refuses it | Magistrates' Courts Act, Cap. 11, s.33 |
| Murder, treason, armed robbery and some drug and economic offences are not bailable | Remand shares by offence; murder accused are always in remand | Criminal Procedure Act, Cap. 20, s.148(5) |
| An accused in remand is brought back at short intervals | Next-date suggestions cap the gap at 14 days for remand cases | Criminal Procedure Act, s.225 (the exact limit is to be confirmed) |
| Murder and other committal trials are heard in High Court criminal sessions | They are planned on the Criminal sessions page, not on the weekly list | Court practice |

## Still assumptions (no public source found yet)

| Assumption | Current value | Where to get the real figure |
|---|---|---|
| Adjournment probability per hearing (advocate, prosecution, court-side) | 3–18% by type | Field sample of case files (see the data-request letter), or JSDS2 extract |
| Share of criminal cases needing a forensic report | 25% | NPS / Police, or a case-file sample |
| Hearings needed to dispose, by case type | 2–6 | Case-file sample |
| Mean days between hearings (before calibration) | 21–55 by level | Published cause lists, tracked over several weeks |
| Rural effects (less representation, more court-side adjournments) | +25% gaps, +8 points court-side adjournment | Case-file sample across urban and rural stations |
| Which stations have which court levels | Representative subset; the High Court sits at each regional seat, the Court of Appeal at Dar es Salaam, Arusha, Mwanza and Dodoma | Judiciary court map (jmap.judiciary.go.tz) |
| Offence mix of criminal filings, by court | `OFFENCE_MIX` in config.py | Case-file sample, NPS statistics |
| Share needing a forensic report, by offence | Homicide 70%, sexual offences 60%, drugs 90%, others 5-20% | Government Chemist (GCLA) workload data |
| Share of accused in remand, by offence | Homicide 100% (not bailable), robbery 70%, drugs 60%, others 10-50% | Prisons Service remand statistics |
| Matters a bench can take in a day | Primary 8, District 6, RM 6, High Court 4, CoA panel 6 | Published cause lists |
| Next-date gaps | High risk 7-14 days, Medium 14-28, Low 28-42; forensic 47+ (NAO); prosecution check 14; witness 14-28; appeal record 60 | Registry practice; JSDS2 extract |
| Court of Appeal: waiting for the record of proceedings | 60% of appeals, 180 days on average | Court of Appeal registry |
| Criminal sessions: trials per judge per week | 3 | High Court registry |
| Adjournment for a witness who did not attend | 8% of hearings (criminal), 4% (others) | Case-file sample |

## Useful but not used (context only)
- **Adjournment reasons in criminal cases** (NAO, Figure 4.1, PDF page 68): of adjourned cases in NPS files, 60% were due to incomplete investigation, 25% to the State Attorney appearing without the case's status, and 15% to the State Attorney appearing without the file. All three are prosecution-side. The sample came from NPS files, so it can't tell us the share of advocate or court-side adjournments. It does support treating "prosecution delay" as the dominant external delay in criminal cases.
- **How often cases are adjourned** (NAO, Table 4.3, PDF page 67): the most-adjourned case in each sampled court averaged 31 adjournments (High Court), 68 (RM) and 48 (District), with a minimum of 2 everywhere. These are extremes, not averages, so they aren't used for calibration.
- **Performance targets** (NAO, section 3.3): judges are expected to dispose 220 cases a year and magistrates 250.
