"""Feature engineering (SRS 7.2, stage 2).

A case is turned into one or more point-in-time *snapshots*: one at filing, and one
after each hearing. That single representation lets the same model score a case at
filing (FR-1) and re-score it hearing by hearing (FR-2).

Protected fields (region, court_station) are carried alongside for the fairness
audit but are never part of the feature matrix returned by `feature_matrix`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

DAYS_PER_MONTH = 30.44


def target_days(court_level: pd.Series) -> pd.Series:
    return court_level.map(C.DISPOSITION_TARGET_MONTHS) * DAYS_PER_MONTH


def _snapshot(case: dict, hist: pd.DataFrame, at: pd.Timestamp) -> dict:
    last = hist.iloc[-1] if len(hist) else None
    elapsed = int((at - case["filing_date"]).days)
    target = C.DISPOSITION_TARGET_MONTHS[case["court_level"]] * DAYS_PER_MONTH
    return {
        "case_id": case["case_id"],
        "snapshot_date": at,
        "days_elapsed": elapsed,
        "target_used": round(elapsed / target, 3),
        "hearings_held": len(hist),
        "adjournment_count": int(hist["adjourned"].sum()) if len(hist) else 0,
        "court_side_adjournments": int((hist["adjournment_reason"] == "court").sum()) if len(hist) else 0,
        # Flags reflect the *current* state, i.e. the most recent hearing.
        **{f: bool(last.get(f, False)) if last is not None else False for f in C.EXTERNAL_FLAGS},
    }


def _attach_case_fields(snaps: pd.DataFrame, cases: pd.DataFrame) -> pd.DataFrame:
    keep = ["case_id", *C.FILING_FEATURES, *C.PROTECTED_FEATURES, "filing_date", "source",
            "assigned_magistrate", "in_custody", "next_date"]
    keep = [c for c in keep if c in cases.columns]
    return snaps.merge(cases[keep], on="case_id", how="left")


def training_snapshots(cases: pd.DataFrame, hearings: pd.DataFrame, as_of=None,
                       max_per_case: int = 4, seed: int = 0) -> pd.DataFrame:
    """Labelled snapshots for training.

    Label = case ended up (or already is) past its disposition target. Only cases
    whose outcome is known are used: disposed cases, and pending cases already past
    target. Snapshots taken after the target date are dropped, since the answer is
    no longer a prediction by then.
    """
    rng = np.random.default_rng(seed)
    cases = cases.copy()
    cases["target_days"] = target_days(cases["court_level"])
    as_of = pd.Timestamp(as_of) if as_of is not None else hearings["hearing_date"].max()
    end = cases["resolution_date"].fillna(as_of)
    cases["duration_days"] = (end - cases["filing_date"]).dt.days
    cases["label"] = (cases["duration_days"] > cases["target_days"]).astype(int)
    known = cases[(cases["status"] == "Disposed") | (cases["label"] == 1)]

    by_case = {cid: g.sort_values("hearing_no") for cid, g in hearings.groupby("case_id")}
    rows = []
    for case in known.to_dict("records"):
        hist = by_case.get(case["case_id"], hearings.iloc[0:0])
        cutoff = case["filing_date"] + pd.Timedelta(days=case["target_days"])
        hist = hist[hist["hearing_date"] < min(cutoff, case["resolution_date"] if pd.notna(case["resolution_date"]) else cutoff)]
        points = [0] + list(range(1, len(hist) + 1))
        if len(points) > max_per_case:
            points = [0] + sorted(rng.choice(points[1:], size=max_per_case - 1, replace=False).tolist())
        for k in points:
            h = hist.iloc[:k]
            at = h["hearing_date"].iloc[-1] if k else case["filing_date"]
            snap = _snapshot(case, h, at)
            snap["label"] = case["label"]
            rows.append(snap)

    return _attach_case_fields(pd.DataFrame(rows), cases)


def current_snapshots(cases: pd.DataFrame, hearings: pd.DataFrame, as_of) -> pd.DataFrame:
    """One snapshot per pending case, as of `as_of` (used for live scoring)."""
    as_of = pd.Timestamp(as_of)
    pending = cases[(cases["filing_date"] <= as_of)
                    & (cases["resolution_date"].isna() | (cases["resolution_date"] > as_of))]
    by_case = {cid: g.sort_values("hearing_no") for cid, g in hearings.groupby("case_id")}
    rows = []
    for case in pending.to_dict("records"):
        hist = by_case.get(case["case_id"], hearings.iloc[0:0])
        hist = hist[hist["hearing_date"] <= as_of]
        rows.append(_snapshot(case, hist, as_of))
    snaps = _attach_case_fields(pd.DataFrame(rows), cases)
    snaps["target_days"] = target_days(snaps["court_level"])
    return snaps


def feature_matrix(snaps: pd.DataFrame) -> pd.DataFrame:
    """Model inputs only. Protected features are excluded by construction."""
    snaps = with_defaults(snaps)
    X = snaps[C.MODEL_FEATURES].copy()
    assert not set(C.PROTECTED_FEATURES) & set(X.columns), "protected feature leaked into model"
    for col in C.CATEGORICAL_FEATURES:
        X[col] = pd.Categorical(X[col], categories=_categories(col))
    for col in ["represented", *C.EXTERNAL_FLAGS]:
        X[col] = X[col].astype(int)
    return X


def _categories(col):
    return {"case_type": C.CASE_TYPES, "court_level": C.COURT_LEVELS, "offence": C.OFFENCES}[col]


def with_defaults(df: pd.DataFrame) -> pd.DataFrame:
    """Fill fields that older data sources do not carry (offence, newer delay flags)."""
    df = df.copy()
    if "offence" not in df:
        df["offence"] = None
    criminal = df["case_type"].isin(C.CRIMINAL_TYPES) if "case_type" in df else False
    df["offence"] = df["offence"].where(df["offence"].notna(), np.where(criminal, "Other", "Not criminal"))
    for f in C.EXTERNAL_FLAGS:
        if f not in df:
            df[f] = False
    return df
