"""Cause-list optimisation with OR-Tools CP-SAT (FR-5, SRS 7.3).

In Tanzanian courts the next date is fixed by the judge or magistrate in open court,
with the parties present, and a case stays with the officer assigned to it. So the
optimiser does not redraw the week. It takes the dates already fixed in court as
given, and only fills the free capacity left on each bench, choosing from cases with
no date yet and high-risk cases worth bringing forward. Constraints:
  * each case listed at most once in the week;
  * a magistrate's daily capacity (dates fixed in court use it up first) and days off;
  * a case is heard only by its assigned magistrate (or, if it has none yet, by a
    magistrate at its own station and court level).
The objective rewards listing high-risk, court-controllable cases and accused held in
remand (earlier in the week for the highest priority), and penalises uneven workload
across magistrates who share a station.

A greedy baseline (JustiFlow-style, one case at a time in priority order) is
included so the two approaches can be compared on the same inputs.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd
from ortools.sat.python import cp_model

from . import config as C


def priority_weight(row) -> int:
    """Integer priority in roughly 0..135."""
    mult = 1.0 if row["court_controllable"] else C.EXTERNAL_BLOCK_PENALTY
    w = 100 * row["risk_probability"] * mult
    if row.get("overdue", False):
        w += 20 * mult
    if row.get("in_custody", False):
        # Not scaled down: a remand case waiting on others still needs pushing.
        w += C.CUSTODY_PRIORITY
    return max(1, int(round(w)))


def _prepare(scored: pd.DataFrame, magistrates: pd.DataFrame):
    cases = scored.copy().reset_index(drop=True)
    cases["priority"] = cases.apply(priority_weight, axis=1) if len(cases) else []

    mags = magistrates.copy().reset_index(drop=True)
    mags["off"] = mags["unavailable_days"].fillna("").map(
        lambda s: {d.strip() for d in str(s).split(",") if d.strip()})

    pool = defaultdict(list)
    for m in mags.itertuples():
        pool[(m.court_station, m.court_level)].append(m.magistrate_id)

    eligible = {}
    for c in cases.itertuples():
        options = pool.get((c.court_station, c.court_level), [])
        assigned = getattr(c, "assigned_magistrate", None)
        if assigned in options:
            options = [assigned]  # cases stay with their assigned officer
        eligible[c.case_id] = options
    return cases, mags, pool, eligible


def _fixed_slots(fixed, cases, week_start):
    """Dates fixed in court that fall in this week -> {case_id: (magistrate_id, day index)}."""
    if not fixed:
        return {}
    start = pd.Timestamp(week_start).normalize()
    known = set(cases["case_id"])
    out = {}
    for cid, (mid, day) in fixed.items():
        d = (pd.Timestamp(day).normalize() - start).days
        if cid in known and 0 <= d < len(C.WORKING_DAYS):
            out[cid] = (mid, d)
    return out


def _to_frame(assign, cases, week_start, fixed_slots=None):
    days = pd.bdate_range(pd.Timestamp(week_start), periods=len(C.WORKING_DAYS))
    by_id = cases.set_index("case_id")
    fixed_slots = fixed_slots or {}
    rows = []
    for cid, (mid, d) in {**assign, **fixed_slots}.items():
        c = by_id.loc[cid]
        rows.append({
            "case_id": cid, "magistrate_id": mid, "day": C.WORKING_DAYS[d], "date": days[d].date(),
            "court_station": c["court_station"], "court_level": c["court_level"],
            "case_type": c["case_type"], "priority": c["priority"],
            "risk_category": c["risk_category"], "risk_probability": c["risk_probability"],
            "delay_status": c["delay_status"], "driving_factors": c["driving_factors"],
            # fixed = date set in court; new = no date yet; brought_forward = moved earlier.
            "kind": "fixed" if cid in fixed_slots else c.get("kind", "new"),
            "fixed_date": c.get("next_date"),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["date", "magistrate_id", "priority"], ascending=[True, True, False])
    out["position"] = out.groupby(["date", "magistrate_id"]).cumcount() + 1
    return out.reset_index(drop=True)


def optimise(scored: pd.DataFrame, magistrates: pd.DataFrame, week_start,
             time_limit_s: float = C.SOLVER_TIME_LIMIT_S, fixed: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """`fixed` maps case_id -> (magistrate_id, date) for dates already fixed in court.
    Those cases are listed as they are; every other case in `scored` competes for the
    capacity left over."""
    cases, mags, pool, eligible = _prepare(scored, magistrates)
    off = dict(zip(mags["magistrate_id"], mags["off"]))
    cap = dict(zip(mags["magistrate_id"], mags["daily_capacity"]))
    n_days = len(C.WORKING_DAYS)
    prio = dict(zip(cases["case_id"], cases["priority"]))
    fixed_slots = _fixed_slots(fixed, cases, week_start)
    used = defaultdict(int)
    for mid, d in fixed_slots.values():
        used[mid, d] += 1

    m = cp_model.CpModel()
    x = {}
    for cid, options in eligible.items():
        if cid in fixed_slots:
            continue
        for mid in options:
            for d, day in enumerate(C.WORKING_DAYS):
                if day not in off[mid]:
                    x[cid, mid, d] = m.NewBoolVar(f"x_{cid}_{mid}_{d}")

    by_case, by_slot, by_mag = defaultdict(list), defaultdict(list), defaultdict(list)
    for (cid, mid, d), var in x.items():
        by_case[cid].append(var)
        by_slot[mid, d].append(var)
        by_mag[mid].append(var)

    for vars_ in by_case.values():
        m.AddAtMostOne(vars_)
    for (mid, d), vars_ in by_slot.items():
        m.Add(sum(vars_) <= max(0, cap[mid] - used[mid, d]))

    # Workload balance within each station/level pool.
    spreads = []
    for key, mids in pool.items():
        if len(mids) < 2:
            continue
        loads = []
        for mid in mids:
            fixed_load = sum(used[mid, d] for d in range(n_days))
            load = m.NewIntVar(0, cap[mid] * n_days + fixed_load, f"load_{mid}")
            m.Add(load == sum(by_mag[mid]) + fixed_load)
            loads.append(load)
        hi = m.NewIntVar(0, 10_000, f"hi_{key}")
        lo = m.NewIntVar(0, 10_000, f"lo_{key}")
        m.AddMaxEquality(hi, loads)
        m.AddMinEquality(lo, loads)
        spreads.append(hi - lo)

    # Priority, with a small bonus for listing high-priority cases earlier in the week.
    gain = sum(var * (10 * prio[cid] + (n_days - 1 - d) * max(1, prio[cid] // 10))
               for (cid, mid, d), var in x.items())
    m.Maximize(gain - C.BALANCE_WEIGHT * 100 * sum(spreads))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 8
    status = solver.Solve(m)

    assign = {}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for (cid, mid, d), var in x.items():
            if solver.Value(var):
                assign[cid] = (mid, d)

    info = {"solver_status": solver.StatusName(status), "wall_time_s": round(solver.WallTime(), 2),
            "fixed_in_court": len(fixed_slots), "added_by_optimiser": len(assign)}
    return _to_frame(assign, cases, week_start, fixed_slots), info


def greedy(scored: pd.DataFrame, magistrates: pd.DataFrame, week_start, fixed: dict | None = None) -> pd.DataFrame:
    """Baseline: take cases in priority order, give each the first free slot."""
    cases, mags, _, eligible = _prepare(scored, magistrates)
    off = dict(zip(mags["magistrate_id"], mags["off"]))
    free = {(r.magistrate_id, d): r.daily_capacity
            for r in mags.itertuples() for d in range(len(C.WORKING_DAYS))}
    fixed_slots = _fixed_slots(fixed, cases, week_start)
    for slot in fixed_slots.values():
        if slot in free:
            free[slot] -= 1
    assign = {}
    for c in cases.sort_values("priority", ascending=False).itertuples():
        if c.case_id in fixed_slots:
            continue
        for mid in eligible[c.case_id]:
            slot = next((d for d, day in enumerate(C.WORKING_DAYS)
                         if day not in off[mid] and free[mid, d] > 0), None)
            if slot is not None:
                free[mid, slot] -= 1
                assign[c.case_id] = (mid, slot)
                break
    return _to_frame(assign, cases, week_start, fixed_slots)


def compare(schedule: pd.DataFrame, scored: pd.DataFrame, magistrates: pd.DataFrame) -> dict:
    """Metrics for comparing two cause lists built from the same inputs."""
    hi_ctrl = scored[(scored["risk_category"] == "High") & scored["court_controllable"]]
    listed = set(schedule["case_id"]) if len(schedule) else set()
    loads = schedule.groupby("magistrate_id").size().reindex(magistrates["magistrate_id"], fill_value=0)
    pool_spread = loads.groupby(magistrates.set_index("magistrate_id")[["court_station", "court_level"]]
                                .apply(tuple, axis=1)).agg(lambda s: s.max() - s.min())
    return {
        "cases_listed": len(listed),
        "total_priority_listed": int(schedule["priority"].sum()) if len(schedule) else 0,
        "high_risk_controllable_listed": f"{len(listed & set(hi_ctrl['case_id']))}/{len(hi_ctrl)}",
        "max_workload_spread_within_station": int(pool_spread.max()) if len(pool_spread) else 0,
    }
