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
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from justiceflow import config as C
from justiceflow import pipeline, scheduler
from justiceflow.features import current_snapshots
from justiceflow.review import find_escalations

from . import settings
from .models import (Case, CycleRisk, Decision, Escalation, Hearing, Magistrate, ModelRun,
                     Proposal, ReviewCycle, RiskScore, Setting, User, utcnow)

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
    } for c in db.scalars(q)]
    df = pd.DataFrame(rows, columns=["case_id", "case_type", "court_level", "region", "court_station",
                                     "n_parties", "represented", "filing_date", "resolution_date",
                                     "status", "assigned_magistrate", "source"])
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    df["resolution_date"] = pd.to_datetime(df["resolution_date"])
    return df


def hearings_frame(db: Session, case_ids=None) -> pd.DataFrame:
    q = select(Hearing.case_id, Hearing.hearing_no, Hearing.hearing_date, Hearing.adjourned,
               Hearing.adjournment_reason, Hearing.flag_advocate, Hearing.flag_prosecution,
               Hearing.flag_forensic)
    if case_ids is not None:
        q = q.where(Hearing.case_id.in_(case_ids))
    df = pd.DataFrame(db.execute(q).all(), columns=["case_id", "hearing_no", "hearing_date", "adjourned",
                                                    "adjournment_reason", "flag_advocate",
                                                    "flag_prosecution", "flag_forensic"])
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
            "adjournment_count": rs.adjournment_count,
        })
    return pd.DataFrame(rows)


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
    plan, info = scheduler.optimise(scored, magistrates_frame(db), week_start)

    cycle = ReviewCycle(id=cycle_id, week_start=week_start, model_run_id=run.id,
                        created_by=user.id, solver_info=info)
    db.add(cycle)
    db.flush()
    for r in plan.to_dict("records"):
        db.add(Proposal(cycle_id=cycle_id, case_id=r["case_id"], magistrate_id=r["magistrate_id"],
                        day=r["day"], date=r["date"], position=int(r["position"]), priority=int(r["priority"]),
                        risk_category=r["risk_category"], risk_probability=float(r["risk_probability"]),
                        delay_status=r["delay_status"], driving_factors=r["driving_factors"]))
    for r in scored[["case_id", "risk_category", "delay_status"]].to_dict("records"):
        db.add(CycleRisk(cycle_id=cycle_id, **r))
    db.commit()
    return cycle


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


def approve_all(db: Session, cycle_id: str, user: User) -> int:
    _get_open(db, cycle_id)
    decided = set(db.scalars(select(Decision.case_id).where(Decision.cycle_id == cycle_id,
                                                             Decision.action.in_(LISTING_ACTIONS))))
    pending = [p.case_id for p in db.scalars(select(Proposal).where(Proposal.cycle_id == cycle_id))
               if p.case_id not in decided]
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
                                          "risk_category", "risk_probability", "delay_status", "driving_factors"]}
        row["decision"] = d.action if d else None
        row["decision_reason"] = d.reason if d else None
        if d and d.action == "edit":
            row["magistrate_id"] = d.magistrate_id or row["magistrate_id"]
            row["day"] = d.day or row["day"]
        out.append(row)
    return out


def final_cause_list(db: Session, cycle_id: str) -> list[dict]:
    return [r for r in cause_list(db, cycle_id) if r["decision"] in {"approve", "edit"}]


def finalise(db: Session, cycle_id: str, user: User) -> dict:
    cycle = _get_open(db, cycle_id)
    final = final_cause_list(db, cycle_id)
    cycle.status, cycle.finalised_by, cycle.finalised_at = "APPROVED", user.id, utcnow()
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
    db.execute(delete(Escalation).where(Escalation.cycle_id == cycle_id))
    for r in rows:
        db.add(Escalation(cycle_id=cycle_id, case_id=r["case_id"],
                          consecutive_high_cycles=r["consecutive_high_cycles"], note=r["note"]))
    return len(rows)


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
    if outcome == "adjourned" and reason not in {"advocate", "prosecution", "forensic", "court"}:
        raise HTTPException(400, "An adjournment needs a reason: advocate, prosecution, forensic or court")
    if outcome != "adjourned":
        reason = None
    h = Hearing(
        case_id=case_id, hearing_no=(last.hearing_no + 1) if last else 1, hearing_date=hdate,
        outcome=outcome, adjourned=outcome == "adjourned", adjournment_reason=reason,
        flag_advocate=bool(data.get("flag_advocate")) or reason == "advocate",
        flag_prosecution=bool(data.get("flag_prosecution")) or reason == "prosecution",
        flag_forensic=bool(data.get("flag_forensic")) or reason == "forensic",
        notes=data.get("notes", ""), recorded_by=user.id,
    )
    db.add(h)
    if outcome == "disposed":
        case.status, case.resolution_date = "Disposed", hdate
        db.execute(delete(RiskScore).where(RiskScore.case_id == case_id))
    db.commit()
    if outcome != "disposed":
        score_cases(db, [case_id])  # FR-2: re-score at each hearing
    return h


def next_case_id(db: Session, station: str) -> str:
    prefix = f"{station[:3].upper()}-{settings.today().year}-"
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
    return {
        "benchmark_months": bench,
        "trend": trend,
        "by_level": by_level.astype({"over_benchmark": int, "over_target": int}).to_dict("records"),
        "by_station": by_station.astype({"over_benchmark": int}).to_dict("records"),
    }


def week_monday(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7 or 7) if d.weekday() else d
