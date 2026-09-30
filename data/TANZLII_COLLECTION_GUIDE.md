# Collecting the TanzLII validation sample

**Goal:** 60–100 real, decided cases with a filing date and a decision date. They are used only to check the at-filing risk prediction (FR-1) on real cases.

**What TanzLII allows** ([terms of use](https://tanzlii.org/en/terms-of-use/), checked 28 Sep 2026):
- Browsing the site and copying details by hand: allowed.
- "Scraping and bulk downloading from this website is strictly prohibited" (Section 4). Don't use scripts, browser extensions or AI tools to pull pages in bulk. The site also runs a bot check that blocks automated requests.
- Bulk data: email info@tanzlii.org. A ready-to-send request is in [requests/TanzLII_bulk_access_request.md](requests/TanzLII_bulk_access_request.md). Send it now; it may arrive after the hackathon, but it shows reviewers a real path to scale.
- Reuse: CC BY-NC 4.0 (Section 9). Credit TanzLII, non-commercial use only.

**Recommended plan:** four people collect by hand (below) *and* send the bulk-access email. Hand collection is the part you can count on for the hackathon.

## How to split the work
Aim for a spread across court levels and case types, e.g. four people × 20 cases:

| Person | Court level to target | Where on TanzLII |
|---|---|---|
| 1 | High Court, civil / land / commercial | High Court judgments by year, including the Land and Commercial Divisions |
| 2 | High Court, criminal | High Court judgments, criminal sessions and appeals |
| 3 | Resident Magistrate / District (trial history) | High Court appeals from subordinate courts: the judgment recounts the trial court's history |
| 4 | Primary / District (trial history) | High Court appeals originating from Primary Courts |

Pick cases from several years and registries rather than the first page of results.

## What to record (one row per case)
Fill [tanzlii_sample_template.csv](tanzlii_sample_template.csv) and save it as `tanzlii_sample.csv`:

| Column | What to enter | Where to find it |
|---|---|---|
| `case_id` | Your own ID, e.g. `TZL-001` | — |
| `citation` | Neutral citation, e.g. `[2023] TZHC 1234` | Top of the judgment page |
| `case_type` | One of: Criminal, Civil, Land, Matrimonial, Probate, Labour, Commercial | Case title / division |
| `court_level` | The court whose **filing and decision dates** you record: Primary, District, Resident Magistrate, or High Court | See "Trial or appeal?" below |
| `region`, `court_station` | Registry or court location | Judgment header. Used only for the fairness check, never for scoring |
| `n_parties` | Number of parties (count all appellants and respondents; minimum 2) | Case title |
| `represented` | `yes` if any party had an advocate, else `no` | "Mr/Ms … learned advocate for …" near the start or end |
| `filing_date` | Date the case was filed or instituted (YYYY-MM-DD) | Often in the opening paragraph: "instituted on", "filed on", "charged on" |
| `decision_date` | Date of that court's judgment (YYYY-MM-DD) | "Date of judgment" / signature date |
| `source_url` | Link to the judgment on TanzLII | Browser address bar |

**Trial or appeal?** Record the dates for **one** court only.
- A High Court judgment in a case that **started** at the High Court: use `High Court` with its filing and judgment dates.
- A High Court **appeal**: the judgment usually says when the case was filed in the lower court and when that court decided it. Record the **lower court's** level and dates. That is how we get Primary, District and RM cases.

**If a date is not stated, skip the case.** Don't estimate: a guessed date undermines the whole check. Only if the judgment states just the month, use the 1st of that month and write "month only" in a note.

## Checking the sample
Run this from the project folder whenever you like, even after only 10 rows:

```
python -m justiceflow.check_tanzlii data/tanzlii_sample.csv
```

It lists problem rows by spreadsheet row number (unknown case types, missing or back-to-front dates, a bad `represented` value), shows the spread across court levels and case types, and once both backlog and non-backlog cases are present, reports how well the at-filing model ranks them (AUC). A sample of 60–100 gives a rough answer, not a precise one. Present it that way.
