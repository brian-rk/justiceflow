"""Check a hand-collected TanzLII sample, then test the model on it.

    python -m justiceflow.check_tanzlii data/tanzlii_sample.csv

Reports problem rows (missing dates, unknown case types, decision before filing),
the spread across court levels and case types, and - once the sample has both
backlog and non-backlog cases - how well the at-filing risk model ranks them.
"""

import sys

import pandas as pd

from . import config as C
from .ingest import TANZLII_COLUMNS, read_tanzlii_sample


def check(path: str) -> int:
    raw = pd.read_csv(path, dtype=str)
    missing_cols = [c for c in TANZLII_COLUMNS if c not in raw.columns]
    if missing_cols:
        print(f"Missing columns: {missing_cols}. Start from data/tanzlii_sample_template.csv.")
        return 1

    problems = []
    for i, r in raw.iterrows():
        row = i + 2  # spreadsheet row number (header is row 1)
        if r["case_type"] not in C.CASE_TYPES:
            problems.append((row, f"case_type '{r['case_type']}' not one of {C.CASE_TYPES}"))
        if r["court_level"] not in C.COURT_LEVELS:
            problems.append((row, f"court_level '{r['court_level']}' not one of {C.COURT_LEVELS}"))
        f, d = pd.to_datetime(r["filing_date"], errors="coerce"), pd.to_datetime(r["decision_date"], errors="coerce")
        if pd.isna(f) or pd.isna(d):
            problems.append((row, "filing_date / decision_date missing or not YYYY-MM-DD"))
        elif d < f:
            problems.append((row, "decision_date is before filing_date"))
        if str(r.get("represented", "")).strip().lower() not in {"yes", "no", "true", "false", "1", "0", "y", "n"}:
            problems.append((row, "represented should be yes or no"))

    print(f"{len(raw)} rows in {path}")
    if problems:
        print(f"\n{len(problems)} problem(s) - fix these rows:")
        for row, msg in problems:
            print(f"  row {row}: {msg}")
        return 1
    print("No problems found.\n")

    df = read_tanzlii_sample(path)
    print("Cases by court level:", df["court_level"].value_counts().to_dict())
    print("Cases by type:       ", df["case_type"].value_counts().to_dict())
    print(f"Past disposition target: {df['label'].sum()} of {len(df)} ({df['label'].mean():.0%})\n")

    if df["label"].nunique() < 2:
        print("Need both backlog and non-backlog cases before the model can be scored.")
        return 0
    if len(df) < 30:
        print(f"Only {len(df)} cases: the score below is very rough.")

    from . import pipeline, synthetic
    data = synthetic.generate(12000)
    engine = pipeline.train(data.cases, data.hearings, data.as_of)
    m = engine.model.evaluate(df)
    print(f"Model on real cases: AUC {m['auc']:.2f} (0.5 = chance, 1.0 = perfect ranking), Brier {m['brier']:.3f}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(check(sys.argv[1]))
