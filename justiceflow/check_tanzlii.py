"""Test the at-filing risk model on real, decided Tanzanian cases.

    python -m justiceflow.check_tanzlii data/validation/tanzlii_search_sample.csv
        [--model backend/model_store/model_1.joblib] [--report data/validation/RESULTS.md]

Each row is one decided case: its court level, case type, number of parties,
representation, filing date (or just the filing year, from the case number) and
decision date. The label is whether it took longer than its disposition target.
With only a filing year the label is kept only when it is certain whatever the filing
day; the rest are reported as ambiguous and left out.

The model is scored on what it knows at filing (FR-1). Its result is set against a
"court level only" baseline - the share of synthetic cases at that level that overran
- because in Tanzania the court level alone explains a lot: if the model cannot beat
that baseline, its other inputs add nothing on real cases.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from . import config as C
from .ingest import TANZLII_COLUMNS, interval_labels, read_tanzlii_sample

HIGH = dict((n, lo) for lo, n in C.RISK_BANDS)["High"]


def _problems(raw: pd.DataFrame) -> list[tuple[int, str]]:
    problems = []
    has_year = "filing_year" in raw.columns
    for i, r in raw.iterrows():
        row = i + 2  # spreadsheet row number (header is row 1)
        if r["case_type"] not in C.CASE_TYPES:
            problems.append((row, f"case_type '{r['case_type']}' not one of {C.CASE_TYPES}"))
        elif r["court_level"] in C.CASE_TYPES_BY_LEVEL and r["case_type"] not in C.CASE_TYPES_BY_LEVEL[r["court_level"]]:
            problems.append((row, f"a {r['court_level']} court does not hear {r['case_type']} cases"))
        if r["court_level"] not in C.COURT_LEVELS:
            problems.append((row, f"court_level '{r['court_level']}' not one of {C.COURT_LEVELS}"))
        f = pd.to_datetime(r["filing_date"], errors="coerce")
        y = pd.to_numeric(r["filing_year"], errors="coerce") if has_year else np.nan
        d = pd.to_datetime(r["decision_date"], errors="coerce")
        if pd.isna(d) or (pd.isna(f) and pd.isna(y)):
            problems.append((row, "needs decision_date and either filing_date or filing_year (YYYY-MM-DD / YYYY)"))
        elif pd.notna(f) and d < f:
            problems.append((row, "decision_date is before filing_date"))
        elif pd.notna(y) and d.year < y:
            problems.append((row, "decision is before the filing year"))
        if str(r.get("represented", "")).strip().lower() not in {"yes", "no", "true", "false", "1", "0", "y", "n"}:
            problems.append((row, "represented should be yes or no"))
    return problems


def _auc_ci(y, p, n_boot=2000, seed=0):
    rng = np.random.default_rng(seed)
    y, p = np.asarray(y), np.asarray(p)
    aucs = []
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        if len(set(y[i])) == 2:
            aucs.append(roc_auc_score(y[i], p[i]))
    return float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))


def _summary(name, y, p):
    auc = roc_auc_score(y, p) if len(set(y)) == 2 else float("nan")
    lo, hi = _auc_ci(y, p) if len(set(y)) == 2 else (float("nan"), float("nan"))
    high = p >= HIGH
    return {"name": name, "auc": auc, "auc_lo": lo, "auc_hi": hi, "brier": brier_score_loss(y, p),
            "caught": int((high & (y == 1)).sum()), "positives": int((y == 1).sum()),
            "false_alarms": int((high & (y == 0)).sum()), "negatives": int((y == 0).sum())}


def _fmt(s):
    return (f"AUC {s['auc']:.2f} (95% range {s['auc_lo']:.2f}-{s['auc_hi']:.2f}), Brier {s['brier']:.3f}; "
            f"rated High: {s['caught']} of {s['positives']} overruns, {s['false_alarms']} of {s['negatives']} on-time cases")


def check(path: str, model_path: str | None = None, report: str | None = None) -> int:
    raw = pd.read_csv(path, dtype=str)
    missing_cols = [c for c in TANZLII_COLUMNS if c not in raw.columns]
    if missing_cols:
        print(f"Missing columns: {missing_cols}. Start from data/tanzlii_sample_template.csv.")
        return 1
    problems = _problems(raw)
    print(f"{len(raw)} rows in {path}")
    if problems:
        print(f"\n{len(problems)} problem(s) - fix these rows:")
        for row, msg in problems:
            print(f"  row {row}: {msg}")
        return 1

    labelled = interval_labels(raw)
    ambiguous = labelled[labelled["label"].isna()]
    df = read_tanzlii_sample(path).reset_index(drop=True)
    print(f"{len(df)} cases with a certain outcome; {len(ambiguous)} left out as ambiguous (filing year only).")
    print("Cases by court level:", df["court_level"].value_counts().to_dict())
    print("Cases by type:       ", df["case_type"].value_counts().to_dict())
    print(f"Past disposition target: {df['label'].sum()} of {len(df)} ({df['label'].mean():.0%})\n")
    if df["label"].nunique() < 2:
        print("Need both overrun and on-time cases before the model can be scored.")
        return 0

    # The synthetic data the model learns from (also gives the court-level baseline).
    from . import pipeline, synthetic
    from .features import training_snapshots
    data = synthetic.generate(12000)
    if model_path:
        import joblib
        model = joblib.load(model_path)
        source = f"model loaded from {model_path}"
    else:
        model = pipeline.train(data.cases, data.hearings, data.as_of).model
        source = "model trained on 12,000 synthetic cases (2025 calibration)"
    snaps = training_snapshots(data.cases, data.hearings, data.as_of)
    at_filing = snaps[snaps["hearings_held"] == 0]
    level_rate = at_filing.groupby("court_level")["label"].mean()
    level_type_rate = at_filing.groupby(["court_level", "case_type"])["label"].mean()

    y = df["label"].to_numpy()
    p_model = model.predict_proba(df)
    p_level = df["court_level"].map(level_rate).fillna(level_rate.mean()).to_numpy()
    p_lt = np.array([level_type_rate.get((lv, t), level_rate.get(lv, 0.0)) for lv, t in zip(df["court_level"], df["case_type"])])
    alt = df.copy()
    alt["represented"] = False
    p_unrep = model.predict_proba(alt)

    rows = [_summary("JusticeFlow model", y, p_model),
            _summary("Baseline: court level only", y, p_level),
            _summary("Baseline: court level + case type", y, p_lt),
            _summary("Model, everyone assumed unrepresented", y, p_unrep)]
    print(f"({source})")
    for s in rows:
        print(f"  {s['name']:<40} {_fmt(s)}")

    by_level = []
    for lv, g in df.groupby("court_level"):
        idx = g.index.to_numpy()
        yl = y[idx]
        auc = roc_auc_score(yl, p_model[idx]) if len(set(yl)) == 2 else float("nan")
        by_level.append({"court_level": lv, "n": len(idx), "overran": int(yl.sum()),
                         "mean_risk_overran": float(p_model[idx][yl == 1].mean()) if yl.sum() else float("nan"),
                         "mean_risk_on_time": float(p_model[idx][yl == 0].mean()) if (yl == 0).any() else float("nan"),
                         "auc_within_level": auc})
    print("\nWithin each court level:")
    for r in by_level:
        print(f"  {r['court_level']:<16} n={r['n']:<3} overran={r['overran']:<3} mean risk: overran {r['mean_risk_overran']:.0%}, "
              f"on time {r['mean_risk_on_time']:.0%}, AUC within level {r['auc_within_level']:.2f}")

    if report:
        _write_report(report, path, source, df, ambiguous, y, p_model, rows, by_level)
        print(f"\nReport written to {report}")
    return 0


def _write_report(report, path, source, df, ambiguous, y, p, rows, by_level):
    pct = lambda x: "-" if pd.isna(x) else f"{x:.0%}"  # noqa: E731
    lines = [
        "# Real-case test of the at-filing risk model",
        "",
        f"Sample: `{path}`. {source}.",
        "",
        f"* **{len(df)} decided cases** with a certain outcome ({int(y.sum())} overran their disposition target, "
        f"{int((y == 0).sum())} finished within it); **{len(ambiguous)} left out** because their filing year alone "
        "cannot tell which side of the target they fall.",
        "* Courts: " + ", ".join(f"{k} {v}" for k, v in df["court_level"].value_counts().items()) + ".",
        "",
        "| Predictor | AUC (95% range) | Brier | Overruns rated High | On-time cases rated High |",
        "|---|---|---|---|---|",
    ]
    for s in rows:
        lines.append(f"| {s['name']} | {s['auc']:.2f} ({s['auc_lo']:.2f}-{s['auc_hi']:.2f}) | {s['brier']:.3f} | "
                     f"{s['caught']} of {s['positives']} | {s['false_alarms']} of {s['negatives']} |")
    lines += ["", "**Within each court level** (does the model tell slow cases from fast ones at the same court?):", "",
              "| Court | Cases | Overran | Mean risk, overran | Mean risk, on time | AUC within level |", "|---|---|---|---|---|---|"]
    for r in by_level:
        auc = "-" if pd.isna(r["auc_within_level"]) else f"{r['auc_within_level']:.2f}"
        lines.append(f"| {r['court_level']} | {r['n']} | {r['overran']} | {pct(r['mean_risk_overran'])} | "
                     f"{pct(r['mean_risk_on_time'])} | {auc} |")
    lines += ["", "**Every case:**", "", "| Case | Court | Type | Outcome | Model risk |", "|---|---|---|---|---|"]
    for (_, r), pi, yi in sorted(zip(df.iterrows(), p, y), key=lambda t: -t[1]):
        lines.append(f"| [{r['citation']}]({r['source_url']}) | {r['court_level']} | {r['case_type']} | "
                     f"{'overran' if yi else 'on time'} | {pi:.0%} |")
    with open(report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--model", help="a trained model (.joblib) instead of training a fresh one")
    ap.add_argument("--report", help="write a markdown report here")
    a = ap.parse_args()
    sys.exit(check(a.path, a.model, a.report))
