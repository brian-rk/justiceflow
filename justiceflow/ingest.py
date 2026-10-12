"""Read-only data ingestion (FR-10, SRS 2.5).

This module only ever *reads*. There is deliberately no function that writes to a
source system; JusticeFlow's own outputs go to its own workspace folder instead.

Supported sources:
  * a folder of CSVs (cases.csv, hearings.csv, magistrates.csv);
  * Google Sheets tabs published as CSV (File > Share > Publish to web > CSV), read
    by URL with no credentials;
  * the hand-collected TanzLII sample (validation only, filing-level fields).
Future: a read-only e-CMS / JSDS2 export would plug in as another `read_*` function.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config as C
from .features import target_days, with_defaults

CASE_COLUMNS = ["case_id", "case_type", "court_level", "region", "court_station",
                "n_parties", "represented", "filing_date", "resolution_date", "status"]
HEARING_COLUMNS = ["case_id", "hearing_no", "hearing_date", "adjourned", "adjournment_reason",
                   "flag_advocate", "flag_prosecution", "flag_forensic"]
# Optional columns: offence, in_custody, next_date (cases); flag_witness, flag_record,
# next_date (hearings). Older exports without them still load.
MAGISTRATE_COLUMNS = ["magistrate_id", "court_level", "region", "court_station",
                      "daily_capacity", "unavailable_days"]
TANZLII_COLUMNS = ["case_id", "citation", "case_type", "court_level", "region", "court_station",
                   "n_parties", "represented", "filing_date", "decision_date", "source_url"]
# A judgment often gives only the case number ("Land Case No. 38 of 2021"), whose year
# is the filing year. Such rows may leave filing_date empty and give filing_year: the
# label is kept only when it is certain for every filing date in that year.


def _read(src: str | Path) -> pd.DataFrame:
    return pd.read_csv(src)  # works for local paths and published-CSV URLs alike


def _require(df, cols, name):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{name} is missing columns: {missing}")


def _bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def _validate_values(cases: pd.DataFrame, name: str):
    bad_level = set(cases["court_level"]) - set(C.COURT_LEVELS)
    bad_type = set(cases["case_type"]) - set(C.CASE_TYPES)
    if bad_level or bad_type:
        raise ValueError(f"{name}: unknown court_level {bad_level or '-'} / case_type {bad_type or '-'}")


def read_cases(src) -> pd.DataFrame:
    df = _read(src)
    _require(df, CASE_COLUMNS, "cases")
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    df["resolution_date"] = pd.to_datetime(df["resolution_date"])
    df["represented"] = _bool(df["represented"])
    df["n_parties"] = df["n_parties"].astype(int)
    if "assigned_magistrate" not in df:
        df["assigned_magistrate"] = None
    df["in_custody"] = _bool(df["in_custody"]) if "in_custody" in df else False
    df["next_date"] = pd.to_datetime(df["next_date"]) if "next_date" in df else pd.NaT
    df["source"] = df.get("source", "import")
    df = with_defaults(df)
    _validate_values(df, "cases")
    return df


def read_hearings(src) -> pd.DataFrame:
    df = _read(src)
    _require(df, HEARING_COLUMNS, "hearings")
    df["hearing_date"] = pd.to_datetime(df["hearing_date"])
    for col in ["adjourned", *C.EXTERNAL_FLAGS]:
        df[col] = _bool(df[col]) if col in df else False
    df["adjournment_reason"] = df["adjournment_reason"].where(df["adjournment_reason"].notna(), None)
    return df


def read_magistrates(src) -> pd.DataFrame:
    df = _read(src)
    _require(df, MAGISTRATE_COLUMNS, "magistrates")
    df["unavailable_days"] = df["unavailable_days"].fillna("")
    return df


def read_folder(folder: str | Path):
    folder = Path(folder)
    return (read_cases(folder / "cases.csv"), read_hearings(folder / "hearings.csv"),
            read_magistrates(folder / "magistrates.csv"))


def read_tanzlii_sample(src) -> pd.DataFrame:
    """Hand-collected TanzLII judgments (CC BY-NC 4.0, attribute tanzlii.org).

    Judgments give filing and decision dates but not hearing histories, so these rows
    validate the at-filing prediction (FR-1) only. Returns filing-time snapshots with
    a `label` column, ready for RiskModel.evaluate().
    """
    df = _read(src)
    _require(df, TANZLII_COLUMNS, "TanzLII sample")
    df = interval_labels(df)
    df = df[df["label"].notna()].copy()
    df["label"] = df["label"].astype(int)
    df["represented"] = _bool(df["represented"])
    df = with_defaults(df)
    _validate_values(df, "TanzLII sample")
    for col in ["days_elapsed", "target_used", "hearings_held", "adjournment_count", "court_side_adjournments"]:
        df[col] = 0
    for col in C.EXTERNAL_FLAGS:
        df[col] = False
    df["source"] = "tanzlii"
    return df


def interval_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Label each decided case 1 (past its disposition target) or 0 (within it).

    With an exact filing_date the label is direct. With only a filing_year, the case
    could have been filed on any day of that year, so the label is set only if it is
    the same for the earliest and latest possible filing date; otherwise it is left
    empty (ambiguous) and the row is not used.
    """
    df = df.copy()
    df["decision_date"] = pd.to_datetime(df["decision_date"], errors="coerce")
    exact = pd.to_datetime(df["filing_date"], errors="coerce") if "filing_date" in df else pd.NaT
    year = pd.to_numeric(df["filing_year"], errors="coerce") if "filing_year" in df else pd.Series(float("nan"), df.index)
    earliest = exact.fillna(pd.to_datetime(year.astype("Int64").astype(str) + "-01-01", errors="coerce"))
    latest = exact.fillna(pd.to_datetime(year.astype("Int64").astype(str) + "-12-31", errors="coerce"))
    target = target_days(df["court_level"])
    longest = (df["decision_date"] - earliest).dt.days
    shortest = (df["decision_date"] - latest).dt.days
    df["label"] = pd.NA
    df.loc[shortest > target, "label"] = 1
    df.loc[longest <= target, "label"] = 0
    df["filing_date"] = exact if isinstance(exact, pd.Series) else pd.NaT
    df["filing_date"] = df["filing_date"].fillna(earliest)
    df["days_min"], df["days_max"] = shortest, longest
    for col in ["days_elapsed", "target_used", "hearings_held", "adjournment_count", "court_side_adjournments"]:
        df[col] = 0
    for col in C.EXTERNAL_FLAGS:
        df[col] = False
    df["source"] = "tanzlii"
    return df
