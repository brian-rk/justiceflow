"""Run the full JusticeFlow TZ demo:  python -m justiceflow [--cases N] [--out DIR]

1. Generate calibrated synthetic data (saved as CSVs, the same shape a real import uses).
2. Train the risk model behind the fairness gate.
3. Replay three weekly review cycles: score, optimise, registrar review.
   The simulated registrar acts on only part of each list, so the escalation rule fires.
4. Compare the CP-SAT cause list with a greedy baseline.
5. Export dashboard tables for Google Sheets / Looker Studio.
"""

import argparse
import shutil
from pathlib import Path

import pandas as pd

from . import pipeline, scheduler, synthetic
from .review import ReviewStore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--as-of", default="2026-09-26")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    out = Path(args.out)
    if (out / "review").exists():
        shutil.rmtree(out / "review")

    print(f"[1/5] Generating {args.cases} synthetic cases ...")
    data = synthetic.generate(args.cases, seed=args.seed, as_of=args.as_of)
    raw = out / "data"
    raw.mkdir(parents=True, exist_ok=True)
    data.cases.to_csv(raw / "cases.csv", index=False)
    data.hearings.to_csv(raw / "hearings.csv", index=False)
    data.magistrates.to_csv(raw / "magistrates.csv", index=False)
    print(f"      {len(data.hearings)} hearings, {len(data.magistrates)} magistrates, "
          f"{(data.cases.status == 'Pending').sum()} pending cases")
    print("      calibrated gap multipliers:", {k: round(v, 2) for k, v in data.gap_multiplier.items()})

    cycle_dates = [data.as_of - pd.Timedelta(days=14 - 7 * i) for i in range(3)]

    print("[2/5] Training risk model behind the fairness gate ...")
    engine = pipeline.train(data.cases, data.hearings, as_of=cycle_dates[0])
    print("      holdout:", {k: round(v, 3) if isinstance(v, float) else v
                             for k, v in engine.holdout_metrics.items()})
    print("     ", engine.audit.summary(), "| gap by round:", engine.audit.rounds)

    store = ReviewStore(out / "review")
    print("[3/5] Replaying three weekly review cycles ...")
    for i, day in enumerate(cycle_dates):
        cycle_id = f"W{day:%Y-%m-%d}"
        c, h = pipeline.as_of_view(data.cases, data.hearings, day)
        scored = pipeline.score(engine, c, h, day)
        week_start = day + pd.offsets.Week(weekday=0)
        proposal, info = pipeline.propose_week(engine, scored, data.magistrates, week_start, store, cycle_id)

        # Simulated registrar: works through the top of the list only.
        top = proposal.sort_values("priority", ascending=False)
        for cid in top["case_id"].head(len(top) // 2):
            store.decide(cycle_id, cid, "approve", "REG-001")
        if len(top) > 1:
            store.decide(cycle_id, top["case_id"].iloc[-1], "remove", "REG-001",
                         reason="Party reported unwell; relist next week")
        final = store.finalise(cycle_id, "REG-001")
        esc = store.t["escalations"]
        n_esc = int((esc["cycle_id"] == cycle_id).sum())
        print(f"      {cycle_id}: {len(scored)} pending, {(scored.risk_category == 'High').sum()} High, "
              f"{len(proposal)} proposed ({info['solver_status']}, {info['wall_time_s']}s), "
              f"{len(final)} approved, {n_esc} escalations")

    print("[4/5] CP-SAT vs greedy on the final week ...")
    greedy = scheduler.greedy(scored, data.magistrates, week_start)
    print("      CP-SAT:", scheduler.compare(proposal, scored, data.magistrates))
    print("      greedy:", scheduler.compare(greedy, scored, data.magistrates))

    print("[5/5] Exporting dashboard tables ...")
    pipeline.export_dashboard(scored, store, engine, out / "dashboard")
    print(f"      written to {out / 'dashboard'}")

    sample = scored.sort_values("risk_probability", ascending=False).head(5)
    print("\nTop-risk pending cases:")
    for r in sample.itertuples():
        print(f"  {r.case_id} {r.case_type:<11} {r.court_level:<19} p={r.risk_probability:.2f} "
              f"{r.risk_category:<6} | {r.delay_status} | {r.driving_factors}")


if __name__ == "__main__":
    main()
