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

CASE_COLUMNS = ["case_id", "case_type", "court_level", "region", "court_station",
                "n_parties", "represented", "filing_date", "resolution_date", "status"]
HEARING_COLUMNS = ["case_id", "hearing_no", "hearing_date", "adjourned", "adjournment_reason",
                   "flag_advocate", "flag_prosecution", "flag_forensic"]
MAGISTRATE_COLUMNS = ["magistrate_id", "court_level", "region", "court_station",
                      "daily_capacity", "unavailable_days"]
TANZLII_COLUMNS = ["case_id", "citation", "case_type", "court_level", "region", "court_station",
                   "n_parties", "represented", "filing_date", "decision_date", "source_url"]


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
    df["source"] = df.get("source", "import")
    _validate_values(df, "cases")
    return df


def read_hearings(src) -> pd.DataFrame:
    df = _read(src)
    _require(df, HEARING_COLUMNS, "hearings")
    df["hearing_date"] = pd.to_datetime(df["hearing_date"])
    for col in ["adjourned", *C.EXTERNAL_FLAGS]:
        df[col] = _bool(df[col])
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
    from .features import target_days

    df = _read(src)
    _require(df, TANZLII_COLUMNS, "TanzLII sample")
    df = df.dropna(subset=["filing_date", "decision_date"]).copy()
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    df["decision_date"] = pd.to_datetime(df["decision_date"])
    df["represented"] = _bool(df["represented"])
    _validate_values(df, "TanzLII sample")

    df["label"] = ((df["decision_date"] - df["filing_date"]).dt.days
                   > target_days(df["court_level"])).astype(int)
    for col in ["days_elapsed", "target_used", "hearings_held", "adjournment_count", "court_side_adjournments"]:
        df[col] = 0
    for col in C.EXTERNAL_FLAGS:
        df[col] = False
    df["source"] = "tanzlii"
    return df
