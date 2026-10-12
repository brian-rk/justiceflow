"""Load demo data:  python -m app.seed [--cases 12000] [--calibration 2025|2020] [--no-history]

Run from backend/. Creates the schema, loads calibrated synthetic cases, creates one
demo account per role (password: demo1234), and trains the model behind the fairness
gate. By default it then replays three past weeks the way a registry works them:

  * each week's cause list starts from the dates already fixed in court, plus any
    cases the optimiser adds to free capacity;
  * the registrar approves the dates fixed in court and part of the rest;
  * the listed hearings are held, and the next date is fixed at each one (using the
    same suggestion the clerk sees), so the following week starts from a new state.

The current week's cause list is left PROPOSED for the registrar, and one High Court
criminal session is proposed for the busiest High Court station.

--calibration 2025 (default) fits the data to the Judiciary's 2025 figures; 2020 gives
the pre-reform, high-backlog baseline. Scope: Tanzania Mainland.
"""

import argparse
import os
from datetime import timedelta

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, insert, select

from justiceflow import config as C
from justiceflow import synthetic

from . import services, settings
from .db import Base, SessionLocal, engine
from .models import Case, Hearing, Magistrate, RiskScore, User
from .security import hash_password

DEMO_PASSWORD = "demo1234"
LEVEL_ABBR = {"Primary": "PC", "District": "DC", "Resident Magistrate": "RM", "High Court": "HC",
              "Court of Appeal": "CA"}
LEVEL_TITLE = {"High Court": "Hon. Judge", "Court of Appeal": "Hon. Justices (panel)"}
REPLAY_WEEKS = 3

# ASSUMPTION: outcome of a listed hearing in the replayed weeks.
P_DISPOSED, P_ADJOURNED = 0.12, 0.50
ADJOURN_REASONS = {"court": 0.28, "prosecution": 0.25, "advocate": 0.20, "witness": 0.12,
                   "forensic": 0.10, "record": 0.05}
P_BAIL = 0.05  # ASSUMPTION: an accused in remand is granted bail at a hearing


def _hold_listed_hearings(db, cycle_id, week_start, clerk, rng):
    """Hold the hearings on an approved past cause list: record each outcome, fix the
    next date (with the clerk's suggestion), and re-score."""
    listings = services.final_cause_list(db, cycle_id)
    ids = [r["case_id"] for r in listings]
    last_no = dict(db.execute(select(Hearing.case_id, func.max(Hearing.hearing_no))
                              .where(Hearing.case_id.in_(ids)).group_by(Hearing.case_id)).all())
    cases = {c.id: c for c in db.scalars(select(Case).where(Case.id.in_(ids)))}
    disposed = []
    for r in sorted(listings, key=lambda r: r["date"]):
        case = cases[r["case_id"]]
        hdate = r["date"]
        roll, reason = rng.random(), None
        if roll < P_DISPOSED:
            outcome = "disposed"
        elif roll < P_DISPOSED + P_ADJOURNED:
            outcome = "adjourned"
            options = {k: w for k, w in ADJOURN_REASONS.items()
                       if (k not in {"prosecution", "forensic"} or case.case_type in C.CRIMINAL_TYPES)
                       and (k != "record" or case.court_level == "Court of Appeal")
                       and (k != "advocate" or case.court_level not in C.NO_ADVOCATES_LEVELS)}
            reason = rng.choice(list(options), p=np.array(list(options.values())) / sum(options.values()))
        else:
            outcome = "proceeded"
        flags = {f: C.REASON_FLAG.get(reason) == f for f in C.EXTERNAL_FLAGS}
        if case.in_custody and outcome != "disposed" and rng.random() < P_BAIL:
            case.in_custody = False
        next_date = None
        if outcome != "disposed":
            db.flush()
            next_date = services.suggest_next_date(db, case.id, hdate, outcome, reason, flags)["date"]
        db.add(Hearing(case_id=case.id, hearing_no=last_no.get(case.id, 0) + 1, hearing_date=hdate,
                       outcome=outcome, adjourned=outcome == "adjourned", adjournment_reason=reason,
                       **flags, next_date=next_date, notes="", recorded_by=clerk.id))
        last_no[case.id] = last_no.get(case.id, 0) + 1
        case.next_date = next_date
        if outcome == "disposed":
            case.status, case.resolution_date, case.in_custody = "Disposed", hdate, False
            disposed.append(case.id)
    db.execute(delete(RiskScore).where(RiskScore.case_id.in_(disposed)))
    db.commit()
    services.score_cases(db, [cid for cid in ids if cid not in set(disposed)])
    return len(listings), len(disposed)


def _magistrate_name(m, n):
    title = LEVEL_TITLE.get(m["court_level"], "Hon. Magistrate")
    return f"{title} {m['court_station']} {LEVEL_ABBR[m['court_level']]}-{n}"


def seed(n_cases: int = 12000, history: bool = True, seed_value: int = 7, db=None,
         calibration: str | None = None):
    calibration = calibration or os.getenv("JF_CALIBRATION", "2025")
    Base.metadata.drop_all(engine if db is None else db.get_bind())
    Base.metadata.create_all(engine if db is None else db.get_bind())
    db = db or SessionLocal()
    as_of = settings.today()
    data = synthetic.generate(n_cases, seed=seed_value, as_of=str(as_of), calibration=calibration)

    counters: dict = {}
    mags = []
    for m in data.magistrates.to_dict("records"):
        key = (m["court_station"], m["court_level"])
        counters[key] = counters.get(key, 0) + 1
        mags.append({"id": m["magistrate_id"], "court_level": m["court_level"], "region": m["region"],
                     "court_station": m["court_station"], "daily_capacity": int(m["daily_capacity"]),
                     "unavailable_days": m["unavailable_days"] or "", "full_name": _magistrate_name(m, counters[key])})
    db.execute(insert(Magistrate), mags)

    cases = data.cases.copy()
    hearings = data.hearings
    # The replayed weeks' hearings are re-created below from the cause lists approved
    # for them, so the generated ones for pending cases stop before the replay, and
    # each such case is due on the first of the hearings removed.
    replay_start = pd.Timestamp(services.week_monday(as_of) - timedelta(weeks=REPLAY_WEEKS))
    if history:
        pending = set(cases.loc[cases["status"] == "Pending", "case_id"])
        cut = hearings["case_id"].isin(pending) & (hearings["hearing_date"] >= replay_start)
        first_cut = hearings[cut].groupby("case_id")["hearing_date"].min()
        hearings = hearings[~cut]
        due = cases["case_id"].map(first_cut)
        cases["next_date"] = due.where(due.notna(), cases["next_date"]).where(cases["next_date"].notna() | due.notna())
    # Committal (murder) cases wait for a criminal session rather than a weekly date.
    sessions = [C.is_sessions_case(lv, t, o) for lv, t, o in zip(cases["court_level"], cases["case_type"], cases["offence"])]
    cases.loc[sessions, "next_date"] = pd.NaT

    def _d(v):
        return None if pd.isna(v) else pd.Timestamp(v).date()

    db.execute(insert(Case), [{
        "id": r["case_id"], "case_type": r["case_type"], "court_level": r["court_level"], "region": r["region"],
        "court_station": r["court_station"], "n_parties": int(r["n_parties"]), "represented": bool(r["represented"]),
        "filing_date": r["filing_date"].date(), "resolution_date": _d(r["resolution_date"]),
        "status": r["status"], "assigned_magistrate_id": r["assigned_magistrate"], "source": "synthetic",
        "offence": r["offence"], "in_custody": bool(r["in_custody"]) and r["status"] == "Pending",
        "next_date": _d(r["next_date"]),
    } for r in cases.to_dict("records")])

    last_no = hearings.groupby("case_id")["hearing_no"].transform("max")
    disposed = set(cases.loc[cases["status"] == "Disposed", "case_id"])
    rows = []
    for r, is_last in zip(hearings.to_dict("records"), (hearings["hearing_no"] == last_no)):
        outcome = "adjourned" if r["adjourned"] else ("disposed" if is_last and r["case_id"] in disposed else "proceeded")
        rows.append({"case_id": r["case_id"], "hearing_no": int(r["hearing_no"]),
                     "hearing_date": r["hearing_date"].date(), "outcome": outcome, "adjourned": bool(r["adjourned"]),
                     "adjournment_reason": r["adjournment_reason"],
                     **{f: bool(r.get(f, False)) for f in C.EXTERNAL_FLAGS},
                     "next_date": _d(r.get("next_date")), "notes": ""})
    for i in range(0, len(rows), 5000):
        db.execute(insert(Hearing), rows[i:i + 5000])

    # One demo account per role. The magistrate account is linked to the busiest bench.
    busiest = cases[cases.status == "Pending"]["assigned_magistrate"].value_counts().index[0]
    users = [
        ("clerk", "Court Clerk (demo)", "clerk", None),
        ("registrar", "Court Registrar (demo)", "registrar", None),
        ("magistrate", "Magistrate (demo)", "magistrate", busiest),
        ("manager", "Court Management (demo)", "management", None),
        ("admin", "System Admin (demo)", "admin", None),
    ]
    pw = hash_password(DEMO_PASSWORD)
    for username, name, role, mag in users:
        db.add(User(username=username, full_name=name, role=role, password_hash=pw, magistrate_id=mag))
    db.commit()

    run = services.train_model(db, None)
    print(f"Calibration {calibration}: loaded {len(cases)} cases, {len(rows)} hearings, {len(mags)} benches.")
    print(f"Model #{run.id}: AUC {run.metrics['auc']:.3f}, fairness gate "
          f"{'PASSED' if run.audit_passed else 'FAILED'} (gap {run.audit_max_gap:.3f})")

    if history and run.audit_passed:
        reg = db.scalars(select(User).where(User.username == "registrar")).first()
        clerk = db.scalars(select(User).where(User.username == "clerk")).first()
        rng = np.random.default_rng(seed_value)
        this_monday = services.week_monday(as_of)
        for weeks_back in range(REPLAY_WEEKS, 0, -1):
            week = this_monday - timedelta(weeks=weeks_back)
            cyc = services.create_cycle(db, week, reg)
            listings = services.cause_list(db, cyc.id)
            fixed = [r for r in listings if r["kind"] == "fixed"]
            added = sorted((r for r in listings if r["kind"] != "fixed"), key=lambda r: -r["priority"])
            # Dates fixed in court are approved; the registrar works through half of the rest.
            services.approve_all(db, cyc.id, reg, [r["case_id"] for r in fixed + added[: len(added) // 2]])
            out = services.finalise(db, cyc.id, reg)
            heard, closed = _hold_listed_hearings(db, cyc.id, week, clerk, rng)
            print(f"  past week {cyc.id}: {len(fixed)} fixed in court + {len(added)} proposed, "
                  f"{out['approved_listings']} approved, {heard} heard ({closed} disposed), "
                  f"{out['escalations']} escalations")
        cyc = services.create_cycle(db, this_monday, reg)
        print(f"  current week {cyc.id} left PROPOSED for registrar review "
              f"({cyc.solver_info.get('fixed_in_court')} fixed in court, "
              f"{cyc.solver_info.get('added_by_optimiser')} proposed by the optimiser)")

        # One proposed criminal session at the High Court station with most committal cases.
        waiting = services.session_candidates(db)
        if waiting:
            station = pd.Series([r["court_station"] for r in waiting]).value_counts().index[0]
            judge = db.scalars(select(Magistrate).where(Magistrate.court_level == "High Court",
                                                        Magistrate.court_station == station)).first()
            if judge:
                plan = services.create_session(db, station, judge.id, this_monday + timedelta(weeks=2), 4, reg)
                print(f"  criminal session proposed at {station}: {len(plan.cases)} committal cases")

    print(f"\nDemo logins (password '{DEMO_PASSWORD}'): " + ", ".join(u[0] for u in users))
    return db


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=12000)
    ap.add_argument("--calibration", choices=synthetic.CALIBRATIONS, default=None,
                    help="2025 (default, or JF_CALIBRATION) or 2020")
    ap.add_argument("--no-history", action="store_true")
    args = ap.parse_args()
    seed(args.cases, history=not args.no_history, calibration=args.calibration)
