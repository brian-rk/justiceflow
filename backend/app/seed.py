"""Load demo data:  python -m app.seed [--cases 12000] [--no-history]   (from backend/)

Creates the schema, loads calibrated synthetic cases, creates one demo account per
role (password: demo1234), trains the model behind the fairness gate, and by default
replays three past weekly review cycles so escalations and schedules have data. The
current week's cause list is left PROPOSED for the registrar to work through.
"""

import argparse
from datetime import timedelta

from sqlalchemy import insert, select

from justiceflow import synthetic

from . import services, settings
from .db import Base, SessionLocal, engine
from .models import Case, Hearing, Magistrate, User
from .security import hash_password

DEMO_PASSWORD = "demo1234"
LEVEL_ABBR = {"Primary": "PC", "District": "DC", "Resident Magistrate": "RM", "High Court": "HC"}


def seed(n_cases: int = 12000, history: bool = True, seed_value: int = 7, db=None):
    Base.metadata.drop_all(engine if db is None else db.get_bind())
    Base.metadata.create_all(engine if db is None else db.get_bind())
    db = db or SessionLocal()
    as_of = settings.today()
    data = synthetic.generate(n_cases, seed=seed_value, as_of=str(as_of))

    counters: dict = {}
    mags = []
    for m in data.magistrates.to_dict("records"):
        key = (m["court_station"], m["court_level"])
        counters[key] = counters.get(key, 0) + 1
        mags.append({"id": m["magistrate_id"], "court_level": m["court_level"], "region": m["region"],
                     "court_station": m["court_station"], "daily_capacity": int(m["daily_capacity"]),
                     "unavailable_days": m["unavailable_days"] or "",
                     "full_name": f"Hon. Magistrate {m['court_station']} {LEVEL_ABBR[m['court_level']]}-{counters[key]}"})
    db.execute(insert(Magistrate), mags)

    cases = data.cases
    db.execute(insert(Case), [{
        "id": r["case_id"], "case_type": r["case_type"], "court_level": r["court_level"], "region": r["region"],
        "court_station": r["court_station"], "n_parties": int(r["n_parties"]), "represented": bool(r["represented"]),
        "filing_date": r["filing_date"].date(),
        "resolution_date": r["resolution_date"].date() if r["resolution_date"] == r["resolution_date"] else None,
        "status": r["status"], "assigned_magistrate_id": r["assigned_magistrate"], "source": "synthetic",
    } for r in cases.to_dict("records")])

    last_no = data.hearings.groupby("case_id")["hearing_no"].transform("max")
    disposed = set(cases.loc[cases["status"] == "Disposed", "case_id"])
    rows = []
    for r, is_last in zip(data.hearings.to_dict("records"), (data.hearings["hearing_no"] == last_no)):
        outcome = "adjourned" if r["adjourned"] else ("disposed" if is_last and r["case_id"] in disposed else "proceeded")
        rows.append({"case_id": r["case_id"], "hearing_no": int(r["hearing_no"]),
                     "hearing_date": r["hearing_date"].date(), "outcome": outcome, "adjourned": bool(r["adjourned"]),
                     "adjournment_reason": r["adjournment_reason"], "flag_advocate": bool(r["flag_advocate"]),
                     "flag_prosecution": bool(r["flag_prosecution"]), "flag_forensic": bool(r["flag_forensic"]),
                     "notes": ""})
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
    print(f"Loaded {len(cases)} cases, {len(rows)} hearings, {len(mags)} magistrates.")
    print(f"Model #{run.id}: AUC {run.metrics['auc']:.3f}, fairness gate "
          f"{'PASSED' if run.audit_passed else 'FAILED'} (gap {run.audit_max_gap:.3f})")

    if history and run.audit_passed:
        reg = db.scalars(select(User).where(User.username == "registrar")).first()
        this_monday = services.week_monday(as_of)
        for weeks_back in (3, 2, 1):
            cyc = services.create_cycle(db, this_monday - timedelta(weeks=weeks_back), reg)
            listings = sorted(services.cause_list(db, cyc.id), key=lambda r: -r["priority"])
            for r in listings[: len(listings) // 2]:
                services.decide(db, cyc.id, r["case_id"], "approve", reg)
            out = services.finalise(db, cyc.id, reg)
            print(f"  past cycle {cyc.id}: {out['approved_listings']} approved, {out['escalations']} escalations")
        cyc = services.create_cycle(db, this_monday, reg)
        print(f"  current cycle {cyc.id} left PROPOSED for registrar review")

    print(f"\nDemo logins (password '{DEMO_PASSWORD}'): " + ", ".join(u[0] for u in users))
    return db


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=12000)
    ap.add_argument("--no-history", action="store_true")
    args = ap.parse_args()
    seed(args.cases, history=not args.no_history)
