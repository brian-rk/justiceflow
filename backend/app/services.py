"""Service layer: database <-> justiceflow ML core.

The ML core (risk model, fairness gate, CP-SAT scheduler, escalation rule) is the
unchanged `justiceflow` package (SRS 8.3). This module loads what it needs from the
database as DataFrames, calls it, and stores the results.
"""

from __future__ import annotations

from datetime import date, timedelta

import joblib
import pandas as pd
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from justiceflow import config as C
from justiceflow import pipeline, scheduler
from justiceflow.features import current_snapshots
from justiceflow.review import find_escalations

from . import settings
from .models import (Case, CycleRisk, Decision, Escalation, Hearing, Magistrate, ModelRun,
                     Proposal, ReviewCycle, RiskScore, SessionCase, SessionPlan, Setting, User, utcnow)

# --- settings (Admin > Settings) -------------------------------------------

DEFAULT_SETTINGS = {
    "disposition_targets": dict(C.DISPOSITION_TARGET_MONTHS),
    "escalation_cycles": C.ESCALATION_CYCLES,
    "fpr_gap_threshold": C.FPR_GAP_THRESHOLD,
    "external_block_penalty": C.EXTERNAL_BLOCK_PENALTY,
    "nao_benchmark_months": 12,
}


def get_settings(db: Session) -> dict:
    stored = {s.key: s.value for s in db.scalars(select(Setting))}
    return {**DEFAULT_SETTINGS, **stored}


def apply_settings(db: Session) -> dict:
    """Push stored settings into the ML core's config before any ML call."""
    s = get_settings(db)
    C.DISPOSITION_TARGET_MONTHS.update(s["disposition_targets"])
    C.ESCALATION_CYCLES = int(s["escalation_cycles"])
    C.FPR_GAP_THRESHOLD = float(s["fpr_gap_threshold"])
    C.EXTERNAL_BLOCK_PENALTY = float(s["external_block_penalty"])
    return s


def update_settings(db: Session, changes: dict) -> dict:
    unknown = set(changes) - set(DEFAULT_SETTINGS)
    if unknown:
        raise HTTPException(400, f"Unknown settings: {sorted(unknown)}")
    if "disposition_targets" in changes:
        bad = set(changes["disposition_targets"]) - set(C.COURT_LEVELS)
        if bad:
            raise HTTPException(400, f"Unknown court levels: {sorted(bad)}")
    for k, v in changes.items():
        row = db.get(Setting, k) or Setting(key=k)
        row.value = v
        db.merge(row)
    db.commit()
    return apply_settings(db)


# --- DataFrame loaders -------------------------------------------------------

def cases_frame(db: Session, case_ids=None) -> pd.DataFrame:
    q = select(Case)
    if case_ids is not None:
        q = q.where(Case.id.in_(case_ids))
    rows = [{
        "case_id": c.id, "case_type": c.case_type, "court_level": c.court_level, "region": c.region,
        "court_station": c.court_station, "n_parties": c.n_parties, "represented": c.represented,
        "filing_date": c.filing_date, "resolution_date": c.resolution_date, "status": c.status,
        "assigned_magistrate": c.assigned_magistrate_id, "source": c.source,
        "offence": c.offence, "in_custody": c.in_custody, "next_date": c.next_date,
    } for c in db.scalars(q)]
    df = pd.DataFrame(rows, columns=["case_id", "case_type", "court_level", "region", "court_station",
                                     "n_parties", "represented", "filing_date", "resolution_date",
                                     "status", "assigned_magistrate", "source", "offence", "in_custody",
                                     "next_date"])
    for col in ["filing_date", "resolution_date", "next_date"]:
        df[col] = pd.to_datetime(df[col])
    return df


def hearings_frame(db: Session, case_ids=None) -> pd.DataFrame:
    q = select(Hearing.case_id, Hearing.hearing_no, Hearing.hearing_date, Hearing.adjourned,
               Hearing.adjournment_reason, Hearing.flag_advocate, Hearing.flag_prosecution,
               Hearing.flag_forensic, Hearing.flag_witness, Hearing.flag_record)
    if case_ids is not None:
        q = q.where(Hearing.case_id.in_(case_ids))
    df = pd.DataFrame(db.execute(q).all(), columns=["case_id", "hearing_no", "hearing_date", "adjourned",
                                                    "adjournment_reason", "flag_advocate",
                                                    "flag_prosecution", "flag_forensic", "flag_witness",
                                                    "flag_record"])
    df["hearing_date"] = pd.to_datetime(df["hearing_date"])
    return df


def magistrates_frame(db: Session) -> pd.DataFrame:
    rows = [{"magistrate_id": m.id, "court_level": m.court_level, "region": m.region,
             "court_station": m.court_station, "daily_capacity": m.daily_capacity,
             "unavailable_days": m.unavailable_days or ""}
            for m in db.scalars(select(Magistrate).where(Magistrate.active))]
    return pd.DataFrame(rows, columns=["magistrate_id", "court_level", "region", "court_station",
                                       "daily_capacity", "unavailable_days"])


# --- model training & scoring (FR-1, FR-2, FR-4) -----------------------------

_model_cache: dict[int, object] = {}


def latest_run(db: Session) -> ModelRun | None:
    return db.scalars(select(ModelRun).order_by(ModelRun.id.desc()).limit(1)).first()


def _load_model(run: ModelRun):
    if run.id not in _model_cache:
        _model_cache[run.id] = joblib.load(run.artifact_path)
    return _model_cache[run.id]


def train_model(db: Session, user: User | None) -> ModelRun:
    s = apply_settings(db)
    as_of = settings.today()
    cases, hearings = cases_frame(db), hearings_frame(db)
    if len(cases) < 200:
        raise HTTPException(400, "Not enough case data to train (need at least 200 cases)")
    engine = pipeline.train(cases, hearings, as_of)

    settings.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    run = ModelRun(
        trained_by=user.id if user else None, as_of=as_of, metrics=engine.holdout_metrics,
        audit_passed=engine.audit.passed, audit_max_gap=engine.audit.max_gap,
        audit_threshold=engine.audit.threshold, audit_rounds=engine.audit.rounds,
        audit_table=engine.audit.table.reset_index().to_dict("records"),
        disposition_targets=s["disposition_targets"], artifact_path="",
    )
    db.add(run)
    db.flush()
    path = settings.MODEL_DIR / f"model_{run.id}.joblib"
    joblib.dump(engine.model, path)
    run.artifact_path = str(path)
    _model_cache[run.id] = engine.model
    db.commit()
    score_cases(db)
    return run


def require_cleared_model(db: Session) -> ModelRun:
    run = latest_run(db)
    if run is None:
        raise HTTPException(409, "No trained model yet. Court management must train one first.")
    if not run.audit_passed:
        raise HTTPException(409, f"Fairness gate FAILED (gap {run.audit_max_gap:.3f} > "
                                 f"{run.audit_threshold:.2f}). Scoring and scheduling are blocked.")
    return run


def score_cases(db: Session, case_ids: list[str] | None = None) -> int:
    """(Re)score pending cases. Keeps a registrar's review if the category is unchanged."""
    run = latest_run(db)
    if run is None:
        return 0
    real = cases_frame(db, case_ids)
    if (real["source"] != "synthetic").any() and not run.audit_passed:
        raise HTTPException(409, "Fairness gate has not passed; real case data cannot be scored.")
    apply_settings(db)
    as_of = pd.Timestamp(settings.today())
    ids = real.loc[real["status"] == "Pending", "case_id"].tolist()
    if not ids:
        return 0
    snaps = current_snapshots(real[real["case_id"].isin(ids)], hearings_frame(db, ids), as_of)
    scored = _load_model(run).score(snaps)

    existing = {r.case_id: r for r in db.scalars(select(RiskScore).where(RiskScore.case_id.in_(ids)))}
    now = utcnow()
    for r in scored.to_dict("records"):
        row = existing.get(r["case_id"]) or RiskScore(case_id=r["case_id"])
        changed = row.reviewed_category is not None and row.reviewed_category != r["risk_category"]
        row.model_run_id, row.scored_at = run.id, now
        row.probability, row.category = float(r["risk_probability"]), r["risk_category"]
        row.overdue, row.driving_factors = bool(r["overdue"]), r["driving_factors"]
        row.delay_status, row.court_controllable = r["delay_status"], bool(r["court_controllable"])
        row.target_used = float(r["target_used"])
        row.hearings_held, row.adjournment_count = int(r["hearings_held"]), int(r["adjournment_count"])
        if row.review_status is None or changed:
            row.review_status = "pending"
        db.add(row)
    db.commit()
    return len(scored)


def effective_category(rs: RiskScore) -> str:
    return rs.reviewed_category if rs.review_status == "overridden" else rs.category


# --- review cycles (FR-5, FR-6, FR-7) -----------------------------------------

LISTING_ACTIONS = {"approve", "edit", "remove"}
OVERRIDE_PROBABILITY = {"Low": 0.2, "Medium": 0.5, "High": 0.85}
# A case heard in the two weeks before a cause list has already been given its next
# date, so it is not proposed again that week (even if that date was not recorded).
RELIST_GAP_DAYS = 14


def open_cycle(db: Session) -> ReviewCycle | None:
    return db.scalars(select(ReviewCycle).where(ReviewCycle.status == "PROPOSED")).first()


def _scored_frame(db: Session) -> pd.DataFrame:
    q = (select(RiskScore, Case).join(Case, Case.id == RiskScore.case_id).where(Case.status == "Pending"))
    rows = []
    for rs, c in db.execute(q).all():
        overridden = rs.review_status == "overridden"
        rows.append({
            "case_id": c.id, "case_type": c.case_type, "court_level": c.court_level,
            "court_station": c.court_station, "assigned_magistrate": c.assigned_magistrate_id,
            "risk_probability": OVERRIDE_PROBABILITY[rs.reviewed_category] if overridden else rs.probability,
            "risk_category": effective_category(rs), "overdue": rs.overdue,
            "court_controllable": rs.court_controllable, "delay_status": rs.delay_status,
            "driving_factors": rs.driving_factors, "hearings_held": rs.hearings_held,
            "adjournment_count": rs.adjournment_count, "offence": c.offence,
            "in_custody": c.in_custody, "next_date": c.next_date,
        })
    return pd.DataFrame(rows)


def in_session_plans(db: Session) -> set[str]:
    """Cases already planned into a criminal session (proposed or approved)."""
    return set(db.scalars(select(SessionCase.case_id)))


def create_cycle(db: Session, week_start: date, user: User) -> ReviewCycle:
    run = require_cleared_model(db)  # fairness gate cannot be skipped
    if open_cycle(db):
        raise HTTPException(409, "A cause list is already awaiting approval. Finalise it first.")
    if week_start.weekday() != 0:
        raise HTTPException(400, "week_start must be a Monday")
    cycle_id = f"W{week_start.isoformat()}"
    if db.get(ReviewCycle, cycle_id):
        raise HTTPException(409, f"Cycle {cycle_id} already exists")

    apply_settings(db)
    scored = _scored_frame(db)
    if scored.empty:
        raise HTTPException(409, "No scored pending cases to schedule")
    listable, fixed = weekly_candidates(db, scored, week_start)
    if listable.empty:
        raise HTTPException(409, "No cases are due or available to list that week")
    plan, info = scheduler.optimise(listable, magistrates_frame(db), week_start, fixed=fixed)

    cycle = ReviewCycle(id=cycle_id, week_start=week_start, model_run_id=run.id,
                        created_by=user.id, solver_info=info)
    db.add(cycle)
    db.flush()
    for r in plan.to_dict("records"):
        db.add(Proposal(cycle_id=cycle_id, case_id=r["case_id"], magistrate_id=r["magistrate_id"],
                        day=r["day"], date=r["date"], position=int(r["position"]), priority=int(r["priority"]),
                        risk_category=r["risk_category"], risk_probability=float(r["risk_probability"]),
                        delay_status=r["delay_status"], driving_factors=r["driving_factors"],
                        kind=r["kind"], fixed_date=_as_date(r["fixed_date"])))
    for r in scored[["case_id", "risk_category", "delay_status"]].to_dict("records"):
        db.add(CycleRisk(cycle_id=cycle_id, **r))
    db.commit()
    return cycle


def _as_date(v):
    return None if v is None or pd.isna(v) else pd.Timestamp(v).date()


def weekly_candidates(db: Session, scored: pd.DataFrame, week_start: date):
    """What can go on a week's cause list.

    * Dates already fixed in court for that week are listed as they are (`fixed`).
    * Cases with no date (or whose date passed without a hearing) may be given one.
    * High-risk, court-controllable cases fixed far in the future may be brought forward.
    * Criminal-sessions cases are planned in sessions, not here.
    """
    week_end = week_start + timedelta(days=len(C.WORKING_DAYS) - 1)
    recently_heard = set(db.scalars(select(Hearing.case_id).where(
        Hearing.hearing_date >= week_start - timedelta(days=RELIST_GAP_DAYS),
        Hearing.hearing_date < week_start)))
    sessions = in_session_plans(db)
    df = scored.copy()
    df["next_date"] = pd.to_datetime(df["next_date"])
    df = df[~df.apply(lambda r: C.is_sessions_case(r["court_level"], r["case_type"], r["offence"]), axis=1)
            & ~df["case_id"].isin(sessions)]
    start, end = pd.Timestamp(week_start), pd.Timestamp(week_end)

    due = df["next_date"].between(start, end) & df["assigned_magistrate"].notna()
    no_date = (df["next_date"].isna() | (df["next_date"] < start)) & ~df["case_id"].isin(recently_heard)
    far = df["next_date"] > end + pd.Timedelta(days=C.BRING_FORWARD_MIN_DAYS)
    forward = far & (df["risk_category"] == "High") & df["court_controllable"]

    df["kind"] = None
    df.loc[due, "kind"] = "fixed"
    df.loc[no_date, "kind"] = "new"
    df.loc[forward, "kind"] = "brought_forward"
    listable = df[df["kind"].notna()].reset_index(drop=True)
    fixed = {r.case_id: (r.assigned_magistrate, r.next_date) for r in listable[listable["kind"] == "fixed"].itertuples()}
    return listable, fixed


def _get_open(db: Session, cycle_id: str) -> ReviewCycle:
    cycle = db.get(ReviewCycle, cycle_id)
    if not cycle:
        raise HTTPException(404, f"Unknown cycle {cycle_id}")
    if cycle.status != "PROPOSED":
        raise HTTPException(409, f"Cycle {cycle_id} is already finalised")
    return cycle


def decide(db: Session, cycle_id: str, case_id: str, action: str, user: User,
           magistrate_id: str | None = None, day: str | None = None, reason: str = "") -> Decision:
    _get_open(db, cycle_id)
    if action not in LISTING_ACTIONS:
        raise HTTPException(400, f"action must be one of {sorted(LISTING_ACTIONS)}")
    if action in {"edit", "remove"} and not reason.strip():
        raise HTTPException(400, f"'{action}' needs a reason for the audit log")
    prop = db.scalars(select(Proposal).where(Proposal.cycle_id == cycle_id, Proposal.case_id == case_id)).first()
    if not prop:
        raise HTTPException(404, f"{case_id} is not on cause list {cycle_id}")
    if action == "edit":
        if day and day not in C.WORKING_DAYS:
            raise HTTPException(400, f"day must be one of {C.WORKING_DAYS}")
        if magistrate_id:
            mag, case = db.get(Magistrate, magistrate_id), db.get(Case, case_id)
            if not mag or (mag.court_station, mag.court_level) != (case.court_station, case.court_level):
                raise HTTPException(400, "Magistrate must sit at the case's station and court level")
    d = Decision(cycle_id=cycle_id, case_id=case_id, action=action, registrar_id=user.id,
                 magistrate_id=magistrate_id, day=day, reason=reason)
    db.add(d)
    db.commit()
    return d


def approve_all(db: Session, cycle_id: str, user: User, case_ids: list[str] | None = None) -> int:
    """Approve every undecided listing, or only the undecided ones among `case_ids`."""
    _get_open(db, cycle_id)
    decided = set(db.scalars(select(Decision.case_id).where(Decision.cycle_id == cycle_id,
                                                             Decision.action.in_(LISTING_ACTIONS))))
    listed = [p.case_id for p in db.scalars(select(Proposal).where(Proposal.cycle_id == cycle_id))]
    if case_ids is not None:
        unknown = set(case_ids) - set(listed)
        if unknown:
            raise HTTPException(404, f"Not on cause list {cycle_id}: {', '.join(sorted(unknown)[:5])}")
        listed = [cid for cid in listed if cid in set(case_ids)]
    pending = [cid for cid in listed if cid not in decided]
    for cid in pending:
        db.add(Decision(cycle_id=cycle_id, case_id=cid, action="approve", registrar_id=user.id,
                        reason="bulk approval"))
    db.commit()
    return len(pending)


def cause_list(db: Session, cycle_id: str) -> list[dict]:
    """Every proposed listing with its latest registrar decision (if any)."""
    props = db.scalars(select(Proposal).where(Proposal.cycle_id == cycle_id)
                       .order_by(Proposal.date, Proposal.magistrate_id, Proposal.position)).all()
    latest = {}
    for d in db.scalars(select(Decision).where(Decision.cycle_id == cycle_id,
                                               Decision.action.in_(LISTING_ACTIONS)).order_by(Decision.id)):
        latest[d.case_id] = d
    out = []
    for p in props:
        d = latest.get(p.case_id)
        row = {c: getattr(p, c) for c in ["case_id", "magistrate_id", "day", "date", "position", "priority",
                                          "risk_category", "risk_probability", "delay_status", "driving_factors",
                                          "kind", "fixed_date"]}
        row["decision"] = d.action if d else None
        row["decision_reason"] = d.reason if d else None
        if d and d.action == "edit":
            row["magistrate_id"] = d.magistrate_id or row["magistrate_id"]
            if d.day and d.day != row["day"]:
                row["date"] = row["date"] + timedelta(days=C.WORKING_DAYS.index(d.day) - C.WORKING_DAYS.index(row["day"]))
                row["day"] = d.day
        out.append(row)
    return out


def final_cause_list(db: Session, cycle_id: str) -> list[dict]:
    return [r for r in cause_list(db, cycle_id) if r["decision"] in {"approve", "edit"}]


def finalise(db: Session, cycle_id: str, user: User) -> dict:
    cycle = _get_open(db, cycle_id)
    final = final_cause_list(db, cycle_id)
    cycle.status, cycle.finalised_by, cycle.finalised_at = "APPROVED", user.id, utcnow()
    # The approved list becomes each case's next date (parties are then notified).
    cases = {c.id: c for c in db.scalars(select(Case).where(Case.id.in_([r["case_id"] for r in final])))}
    for r in final:
        if r["case_id"] in cases:
            cases[r["case_id"]].next_date = r["date"]
    db.flush()
    n_esc = run_escalation(db, cycle_id)
    db.commit()
    return {"cycle_id": cycle_id, "approved_listings": len(final), "escalations": n_esc}


def run_escalation(db: Session, cycle_id: str) -> int:
    s = apply_settings(db)
    order = [c.id for c in db.scalars(select(ReviewCycle).order_by(ReviewCycle.week_start))]
    hist = pd.DataFrame(db.execute(select(CycleRisk.cycle_id, CycleRisk.case_id, CycleRisk.risk_category,
                                          CycleRisk.delay_status)).all(),
                        columns=["cycle_id", "case_id", "risk_category", "delay_status"])
    places = dict(db.execute(select(Case.id, Case.court_station)).all())
    levels = dict(db.execute(select(Case.id, Case.court_level)).all())
    hist["court_station"] = hist["case_id"].map(places)
    hist["court_level"] = hist["case_id"].map(levels)
    dec = pd.DataFrame(db.execute(select(Decision.cycle_id, Decision.case_id)).all(),
                       columns=["cycle_id", "case_id"])
    rows = find_escalations(order, cycle_id, hist, dec, int(s["escalation_cycles"]))
    already_open = set(db.scalars(select(Escalation.case_id).where(Escalation.acknowledged_by.is_(None),
                                                                 Escalation.cycle_id != cycle_id)))
    rows = [r for r in rows if r["case_id"] not in already_open]
    latest = hist[hist["cycle_id"] == cycle_id].drop_duplicates("case_id").set_index("case_id")["delay_status"]
    db.execute(delete(Escalation).where(Escalation.cycle_id == cycle_id))
    for r in rows:
        db.add(Escalation(cycle_id=cycle_id, case_id=r["case_id"],
                          consecutive_high_cycles=r["consecutive_high_cycles"], note=r["note"],
                          responsible=responsible_body(latest.get(r["case_id"], ""))))
    return len(rows)


def responsible_body(delay_status: str) -> str:
    """Who can unblock a case, from its delay status ("Externally blocked: ...")."""
    bodies = [body for flag, body in C.RESPONSIBLE_BODY.items() if C.EXTERNAL_FLAGS[flag] in (delay_status or "")]
    return "; ".join(dict.fromkeys(bodies)) or C.COURT_BODY


# --- risk-score review (FR-6: "every proposed risk score") ----------------------

def review_risk(db: Session, case_id: str, action: str, user: User,
                category: str | None = None, reason: str = "") -> RiskScore:
    rs = db.get(RiskScore, case_id)
    if not rs:
        raise HTTPException(404, f"No risk score for {case_id}")
    if action == "approve":
        rs.review_status, rs.reviewed_category = "approved", rs.category
    elif action == "override":
        if category not in OVERRIDE_PROBABILITY:
            raise HTTPException(400, "category must be Low, Medium or High")
        if not reason.strip():
            raise HTTPException(400, "An override needs a reason for the audit log")
        rs.review_status, rs.reviewed_category = "overridden", category
    else:
        raise HTTPException(400, "action must be approve or override")
    rs.reviewed_by, rs.reviewed_at, rs.review_reason = user.id, utcnow(), reason
    cyc = open_cycle(db)
    db.add(Decision(cycle_id=cyc.id if cyc else None, case_id=case_id,
                    action="approve_risk" if action == "approve" else "override_risk",
                    registrar_id=user.id, risk_category=rs.reviewed_category, reason=reason))
    db.commit()
    return rs


# --- clerk data entry (FR-11) --------------------------------------------------

def record_hearing(db: Session, case_id: str, data: dict, user: User) -> Hearing:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, f"Unknown case {case_id}")
    if case.status != "Pending":
        raise HTTPException(409, f"{case_id} is already disposed")
    hdate: date = data["hearing_date"]
    if hdate < case.filing_date:
        raise HTTPException(400, "Hearing date is before the filing date")
    if hdate > settings.today():
        raise HTTPException(400, "Hearing date is in the future")
    last = db.scalars(select(Hearing).where(Hearing.case_id == case_id)
                      .order_by(Hearing.hearing_no.desc()).limit(1)).first()
    if last and hdate < last.hearing_date:
        raise HTTPException(400, f"Hearing date is before the previous hearing ({last.hearing_date})")

    outcome, reason = data["outcome"], data.get("adjournment_reason")
    if outcome == "adjourned" and reason not in ADJOURNMENT_REASONS:
        raise HTTPException(400, f"An adjournment needs a reason: {', '.join(ADJOURNMENT_REASONS)}")
    if outcome != "adjourned":
        reason = None
    next_date = data.get("next_date") if outcome != "disposed" else None
    if next_date and next_date <= hdate:
        raise HTTPException(400, "The next date must be after the hearing date")
    flags = {f: bool(data.get(f)) or C.REASON_FLAG.get(reason) == f for f in C.EXTERNAL_FLAGS}
    h = Hearing(
        case_id=case_id, hearing_no=(last.hearing_no + 1) if last else 1, hearing_date=hdate,
        outcome=outcome, adjourned=outcome == "adjourned", adjournment_reason=reason, **flags,
        next_date=next_date, notes=data.get("notes", ""), recorded_by=user.id,
    )
    db.add(h)
    case.next_date = next_date
    if data.get("in_custody") is not None and case.case_type in C.CRIMINAL_TYPES and case.court_level != "Court of Appeal":
        case.in_custody = bool(data["in_custody"])  # e.g. bail granted at this hearing
    if outcome == "disposed":
        case.status, case.resolution_date = "Disposed", hdate
        case.in_custody = False
        db.execute(delete(RiskScore).where(RiskScore.case_id == case_id))
    db.commit()
    if outcome != "disposed":
        score_cases(db, [case_id])  # FR-2: re-score at each hearing
    return h


ADJOURNMENT_REASONS = ["advocate", "prosecution", "forensic", "witness", "record", "court"]


def bench_load(db: Session, magistrate_id: str, day: date) -> int:
    """Cases already due before a magistrate on a day."""
    return db.scalar(select(func.count()).select_from(Case).where(
        Case.assigned_magistrate_id == magistrate_id, Case.next_date == day, Case.status == "Pending")) or 0


def suggest_next_date(db: Session, case_id: str, hearing_date: date, outcome: str = "adjourned",
                      reason: str | None = None, flags: dict | None = None,
                      in_custody: bool | None = None) -> dict:
    """Suggest the next date to fix at the end of a hearing.

    The judge or magistrate fixes the date in open court; this only proposes one that
    suits the case (its risk, what it is waiting for, remand) and has room on the
    assigned bench. Every rule behind the suggestion is returned as a reason.
    """
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, f"Unknown case {case_id}")
    if outcome == "disposed":
        return {"date": None, "reasons": ["The case is concluded: no next date."]}
    flags = {f: bool((flags or {}).get(f)) or C.REASON_FLAG.get(reason) == f for f in C.EXTERNAL_FLAGS}
    rs = db.get(RiskScore, case_id)
    category = effective_category(rs) if rs else "Medium"
    lo, hi = C.NEXT_DATE_GAP_DAYS[category]
    reasons = [f"{category} risk: relist within {lo} to {hi} days"]
    if flags["flag_forensic"]:
        lo, hi = C.FORENSIC_WAIT_DAYS, C.FORENSIC_WAIT_DAYS + 14
        reasons = [f"Waiting for a forensic report: Government Chemist results take {C.FORENSIC_WAIT_DAYS} days on average (NAO 2022)"]
    elif flags["flag_record"]:
        lo, hi = C.RECORD_WAIT_DAYS, C.RECORD_WAIT_DAYS + 14
        reasons = [f"Waiting for the record of proceedings: allow about {C.RECORD_WAIT_DAYS} days"]
    elif flags["flag_prosecution"]:
        lo, hi = C.PROSECUTION_GAP_DAYS, C.PROSECUTION_GAP_DAYS + 7
        reasons = [f"Investigation or prosecution delay: a short date ({lo} days) to check progress"]
    elif flags["flag_witness"]:
        lo, hi = 14, 28
        reasons = ["Witness did not attend: time to serve a summons (14 to 28 days)"]
    custody = case.in_custody if in_custody is None else bool(in_custody)
    if custody and case.case_type in C.CRIMINAL_TYPES and case.court_level != "Court of Appeal":
        hi = min(hi, C.REMAND_MAX_GAP_DAYS)
        lo = min(lo, hi)
        reasons.append(f"Accused in remand: bring back within {C.REMAND_MAX_GAP_DAYS} days")

    mag = db.get(Magistrate, case.assigned_magistrate_id) if case.assigned_magistrate_id else None
    off = {d.strip() for d in (mag.unavailable_days or "").split(",") if d.strip()} if mag else set()
    best, full_days = None, 0
    for offset in range(lo, hi + 31):
        day = hearing_date + timedelta(days=offset)
        if day.weekday() >= 5 or C.WORKING_DAYS[day.weekday()] in off:
            continue
        load = bench_load(db, mag.id, day) if mag else 0
        if not mag or load < mag.daily_capacity:
            best = (day, load)
            break
        full_days += 1
    if best is None:  # every day in the window is full: take the earliest working day
        day = hearing_date + timedelta(days=lo)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        best = (day, bench_load(db, mag.id, day) if mag else 0)
        reasons.append("Every day in the window is fully booked; this is the earliest working day")
    elif full_days:
        reasons.append("The bench is full earlier in the window, so this is the first day with room")
    if mag:
        reasons.append(f"{mag.full_name} has {best[1]} of {mag.daily_capacity} slots booked that day")
    return {"date": best[0], "earliest": hearing_date + timedelta(days=lo), "latest": hearing_date + timedelta(days=hi),
            "magistrate_id": mag.id if mag else None, "load": best[1],
            "capacity": mag.daily_capacity if mag else None, "reasons": reasons}


LEVEL_CODE = {"Primary": "PC", "District": "DC", "Resident Magistrate": "RM", "High Court": "HC",
              "Court of Appeal": "CA"}


def next_case_id(db: Session, station: str, court_level: str) -> str:
    """e.g. PC-KARIAKOO-2026-0001: the court, the year, a running number (like
    "Civil Case No. 1 of 2026" at Kariakoo Primary Court)."""
    code = C.court_code(station)
    if not code.startswith(LEVEL_CODE[court_level] + "-"):
        code = f"{LEVEL_CODE[court_level]}-{code}"
    prefix = f"{code}-{settings.today().year}-"
    n = len(db.scalars(select(Case.id).where(Case.id.like(prefix + "%"))).all())
    return f"{prefix}{n + 1:04d}"


# --- reports (Court management > Reports) --------------------------------------

def backlog_report(db: Session, months: int = 24) -> dict:
    s = apply_settings(db)
    bench = int(s["nao_benchmark_months"])
    cases = cases_frame(db)
    today = pd.Timestamp(settings.today())
    # Past month-ends, with the current (partial) month ending today.
    ends = [*pd.date_range(end=today, periods=months, freq="ME")[-(months - 1):], today]
    trend = []
    for m in ends:
        filed = cases["filing_date"] <= m
        pending = filed & (cases["resolution_date"].isna() | (cases["resolution_date"] > m))
        over = pending & (cases["filing_date"] < m - pd.DateOffset(months=bench))
        month_start = m.replace(day=1)
        disposed = cases["resolution_date"].between(month_start, m)
        new = cases["filing_date"].between(month_start, m)
        trend.append({
            "month": m.strftime("%Y-%m"), "pending": int(pending.sum()), "over_benchmark": int(over.sum()),
            "over_benchmark_share": round(float(over.sum() / max(pending.sum(), 1)), 3),
            "filed": int(new.sum()), "disposed": int(disposed.sum()),
            "partial": m == today and m != m + pd.offsets.MonthEnd(0),  # current month, still running
        })

    pend = cases[cases["status"] == "Pending"].copy()
    age_m = (today - pend["filing_date"]).dt.days / 30.44
    pend["over_benchmark"] = age_m > bench
    pend["over_target"] = age_m > pend["court_level"].map(C.DISPOSITION_TARGET_MONTHS)
    by_level = (pend.groupby("court_level")
                .agg(pending=("case_id", "size"), over_benchmark=("over_benchmark", "sum"),
                     over_target=("over_target", "sum")).reset_index())
    by_station = (pend.groupby(["court_station", "court_level"])
                  .agg(pending=("case_id", "size"), over_benchmark=("over_benchmark", "sum"))
                  .reset_index().sort_values("pending", ascending=False))
    pend["division"] = [C.division(lv, t) for lv, t in zip(pend["court_level"], pend["case_type"])]
    by_division = (pend[pend["court_level"] == "High Court"].groupby("division")
                   .agg(pending=("case_id", "size"), over_target=("over_target", "sum"))
                   .reset_index().sort_values("pending", ascending=False))
    # Average days from filing to decision for cases decided in the last year, next to
    # the Judiciary's published 2025 figures.
    decided = cases[cases["resolution_date"].between(today - pd.Timedelta(days=365), today)]
    avg_days = ((decided["resolution_date"] - decided["filing_date"]).dt.days
                .groupby(decided["court_level"]).mean().round().to_dict())
    levels = by_level.astype({"over_benchmark": int, "over_target": int}).to_dict("records")
    for r in levels:
        lv = r["court_level"]
        r["avg_days_to_decision"] = avg_days.get(lv)
        r["published_avg_days_2025"] = C.AVG_DAYS_TO_DECISION_2025.get(lv)
        r["published_backlog_share_2025"] = round(C.BACKLOG_SHARE_2025.get(lv, 0), 4)
    order = {lv: i for i, lv in enumerate(C.COURT_LEVELS)}
    levels.sort(key=lambda r: order.get(r["court_level"], 99))
    return {
        "benchmark_months": bench,
        "trend": trend,
        "by_level": levels,
        "by_division": by_division.astype({"over_target": int}).to_dict("records"),
        "by_station": by_station.astype({"over_benchmark": int}).to_dict("records"),
    }


def week_monday(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7 or 7) if d.weekday() else d


# --- weekly "needs attention" list for the registrar ------------------------------

LONG_REMAND_DAYS = 180  # ASSUMPTION: remand long enough to raise with the committee
FAR_DATE_DAYS = 28


def needs_attention(db: Session, limit: int = 50) -> dict:
    """Cases a registrar should look at this week, grouped by what is wrong."""
    today = settings.today()
    sessions = in_session_plans(db)
    q = (select(Case, RiskScore).outerjoin(RiskScore, RiskScore.case_id == Case.id)
         .where(Case.status == "Pending"))
    rows = db.execute(q).all()
    pending_ids = select(Case.id).where(Case.status == "Pending")
    last_hearing = dict(db.execute(select(Hearing.case_id, func.max(Hearing.hearing_date))
                                   .where(Hearing.case_id.in_(pending_ids)).group_by(Hearing.case_id)).all())
    groups = {k: [] for k in ["date_passed", "no_date", "far_date_high", "repeated_external", "long_remand"]}

    # Last three hearings per pending case, to spot the same external delay again and again.
    recent = {}
    for h in db.scalars(select(Hearing).where(Hearing.case_id.in_(pending_ids))
                        .order_by(Hearing.case_id, Hearing.hearing_no.desc())):
        lst = recent.setdefault(h.case_id, [])
        if len(lst) < 3:
            lst.append(h)

    for c, rs in rows:
        cat = effective_category(rs) if rs else None
        base = {"case_id": c.id, "case_type": c.case_type, "court_level": c.court_level,
                "court_station": c.court_station, "risk_category": cat, "next_date": c.next_date,
                "delay_status": rs.delay_status if rs else None, "in_custody": c.in_custody}
        sessions_case = C.is_sessions_case(c.court_level, c.case_type, c.offence)
        if c.next_date and c.next_date < today and (last_hearing.get(c.id) or date.min) < c.next_date:
            groups["date_passed"].append({**base, "detail": f"Date {c.next_date} passed with no hearing recorded"})
        elif c.next_date is None and c.id not in sessions and not sessions_case:
            groups["no_date"].append({**base, "detail": "No next date fixed"})
        if (c.next_date and cat == "High" and rs and rs.court_controllable
                and (c.next_date - today).days > FAR_DATE_DAYS):
            groups["far_date_high"].append({**base, "detail": f"High risk but next due in {(c.next_date - today).days} days"})
        hs = recent.get(c.id, [])
        if len(hs) == 3 and all(h.adjourned for h in hs) and len({h.adjournment_reason for h in hs}) == 1 \
                and hs[0].adjournment_reason in C.REASON_FLAG:
            flag = C.REASON_FLAG[hs[0].adjournment_reason]
            groups["repeated_external"].append({**base, "detail": f"Adjourned 3 times in a row: {C.EXTERNAL_FLAGS[flag]}",
                                                "responsible": C.RESPONSIBLE_BODY[flag]})
        days_in = (today - c.filing_date).days
        if c.in_custody and c.court_level != "Court of Appeal" and days_in > LONG_REMAND_DAYS:
            groups["long_remand"].append({**base, "detail": f"Accused in remand for {days_in} days", "remand_days": days_in})

    groups["long_remand"].sort(key=lambda r: -r["remand_days"])
    order = {"High": 0, "Medium": 1, "Low": 2, None: 3}
    for k in ["date_passed", "no_date", "repeated_external"]:
        groups[k].sort(key=lambda r: order.get(r["risk_category"], 3))
    return {k: {"total": len(v), "items": v[:limit]} for k, v in groups.items()}


# --- High Court criminal sessions ---------------------------------------------------

def session_candidates(db: Session, station: str | None = None) -> list[dict]:
    """Committal (murder) cases awaiting trial in a High Court criminal session, most
    urgent first: longest in remand, then highest risk, then oldest."""
    today = settings.today()
    planned = in_session_plans(db)
    q = (select(Case, RiskScore).outerjoin(RiskScore, RiskScore.case_id == Case.id)
         .where(Case.status == "Pending", Case.court_level == "High Court", Case.case_type == "Criminal",
                Case.offence == "Homicide"))
    if station:
        q = q.where(Case.court_station == station)
    out = []
    for c, rs in db.execute(q).all():
        if c.id in planned:
            continue
        days = (today - c.filing_date).days
        prob = rs.probability if rs else 0.5
        priority = int(round(100 * prob + (C.CUSTODY_PRIORITY + days / 30 if c.in_custody else 0)))
        out.append({"case_id": c.id, "court_station": c.court_station, "filing_date": c.filing_date,
                    "days_pending": days, "in_custody": c.in_custody, "remand_days": days if c.in_custody else None,
                    "risk_category": effective_category(rs) if rs else None, "risk_probability": prob,
                    "delay_status": rs.delay_status if rs else None, "priority": priority})
    out.sort(key=lambda r: (-(r["remand_days"] or 0), -r["risk_probability"], r["filing_date"]))
    return out


def create_session(db: Session, station: str, magistrate_id: str, start_date: date, weeks: int, user: User) -> SessionPlan:
    mag = db.get(Magistrate, magistrate_id)
    if not mag or mag.court_level != "High Court" or mag.court_station != station:
        raise HTTPException(400, "Choose a High Court judge sitting at this station")
    if start_date.weekday() != 0:
        raise HTTPException(400, "A session starts on a Monday")
    if not 1 <= weeks <= 12:
        raise HTTPException(400, "A session runs for 1 to 12 weeks")
    picks = session_candidates(db, station)[: weeks * C.SESSION_CASES_PER_WEEK]
    if not picks:
        raise HTTPException(409, f"No committal cases are waiting for a session at {station}")
    plan = SessionPlan(court_station=station, magistrate_id=magistrate_id, start_date=start_date, weeks=weeks,
                       created_by=user.id)
    db.add(plan)
    db.flush()
    step = max(1, len(C.WORKING_DAYS) // C.SESSION_CASES_PER_WEEK)
    for i, r in enumerate(picks):
        week, slot = divmod(i, C.SESSION_CASES_PER_WEEK)
        day = start_date + timedelta(weeks=week, days=min(slot * step, len(C.WORKING_DAYS) - 1))
        db.add(SessionCase(plan_id=plan.id, case_id=r["case_id"], position=i + 1, planned_date=day,
                           priority=r["priority"]))
    db.commit()
    return plan


def remove_from_session(db: Session, plan_id: int, case_id: str) -> None:
    plan = db.get(SessionPlan, plan_id)
    if not plan or plan.status != "PROPOSED":
        raise HTTPException(409, "Only a proposed session can be changed")
    db.execute(delete(SessionCase).where(SessionCase.plan_id == plan_id, SessionCase.case_id == case_id))
    db.commit()


def approve_session(db: Session, plan_id: int, user: User) -> SessionPlan:
    plan = db.get(SessionPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Session not found")
    if plan.status != "PROPOSED":
        raise HTTPException(409, "This session is already approved")
    plan.status, plan.approved_by, plan.approved_at = "APPROVED", user.id, utcnow()
    for sc in plan.cases:
        case = db.get(Case, sc.case_id)
        if case:
            case.next_date = sc.planned_date
    db.commit()
    return plan
