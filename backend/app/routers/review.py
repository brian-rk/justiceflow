"""Registrar workflow: cause list (FR-5, FR-6), risk review, review queue; magistrate schedule."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case as sql_case, func, select
from sqlalchemy.orm import Session

from justiceflow import config as C

from .. import services
from ..db import get_db
from ..models import Case, Decision, Magistrate, Proposal, ReviewCycle, RiskScore, SessionPlan, User
from ..security import current_user, require
from .cases import case_row, days_overdue

router = APIRouter(tags=["review"])

registrar = require("registrar")


def cycle_out(db: Session, c: ReviewCycle) -> dict:
    names = dict(db.execute(select(User.id, User.full_name)).all())
    rows = services.cause_list(db, c.id)
    return {
        "id": c.id, "week_start": c.week_start, "status": c.status, "solver_info": c.solver_info,
        "created_by": names.get(c.created_by), "created_at": c.created_at,
        "finalised_by": names.get(c.finalised_by), "finalised_at": c.finalised_at,
        "listings": len(rows), "decided": sum(r["decision"] is not None for r in rows),
        "approved": sum(r["decision"] in {"approve", "edit"} for r in rows),
    }


@router.get("/cycles")
def list_cycles(db: Session = Depends(get_db), _=Depends(require("registrar", "management", "admin"))):
    cycles = db.scalars(select(ReviewCycle).order_by(ReviewCycle.week_start.desc())).all()
    return [cycle_out(db, c) for c in cycles]


class CycleIn(BaseModel):
    week_start: date | None = None


@router.post("/cycles", status_code=201)
def create_cycle(body: CycleIn, db: Session = Depends(get_db), user: User = Depends(registrar)):
    week = body.week_start or services.week_monday(services.settings.today())
    return cycle_out(db, services.create_cycle(db, week, user))


@router.get("/cycles/{cycle_id}")
def get_cycle(cycle_id: str, db: Session = Depends(get_db),
              _=Depends(require("registrar", "management", "admin"))):
    c = db.get(ReviewCycle, cycle_id)
    if not c:
        raise HTTPException(404, "Cycle not found")
    mags = {m.id: m for m in db.scalars(select(Magistrate))}
    items = services.cause_list(db, cycle_id)
    cases = {c.id: c for c in db.scalars(select(Case).where(Case.id.in_([r["case_id"] for r in items])))}
    for r in items:
        m, case = mags.get(r["magistrate_id"]), cases.get(r["case_id"])
        r["magistrate_name"] = m.full_name if m else r["magistrate_id"]
        r["court_station"] = case.court_station if case else None
        r["days_overdue"] = days_overdue(case) if case else None
        r["in_custody"] = bool(case and case.in_custody)
    # Magistrates each listing could be moved to (same station & level) for the edit control.
    options = {}
    for m in mags.values():
        if m.active:
            options.setdefault(f"{m.court_station}|{m.court_level}", []).append(
                {"id": m.id, "name": m.full_name, "unavailable_days": m.unavailable_days})
    return {**cycle_out(db, c), "items": items, "magistrate_options": options}


class DecisionIn(BaseModel):
    case_id: str
    action: Literal["approve", "edit", "remove"]
    magistrate_id: str | None = None
    day: str | None = None
    reason: str = ""


@router.post("/cycles/{cycle_id}/decisions", status_code=201)
def decide(cycle_id: str, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(registrar)):
    d = services.decide(db, cycle_id, body.case_id, body.action, user, body.magistrate_id, body.day, body.reason)
    return {"id": d.id, "action": d.action, "case_id": d.case_id}


@router.post("/cycles/{cycle_id}/approve-all")
def approve_all(cycle_id: str, db: Session = Depends(get_db), user: User = Depends(registrar)):
    return {"approved": services.approve_all(db, cycle_id, user)}


@router.post("/cycles/{cycle_id}/approve-selected")
def approve_selected(cycle_id: str, case_ids: list[str], db: Session = Depends(get_db),
                     user: User = Depends(registrar)):
    """Approve the undecided listings among `case_ids` (row selection on the cause list)."""
    return {"approved": services.approve_all(db, cycle_id, user, case_ids)}


@router.post("/cycles/{cycle_id}/finalise")
def finalise(cycle_id: str, db: Session = Depends(get_db), user: User = Depends(registrar)):
    return services.finalise(db, cycle_id, user)


# --- risk-score review ------------------------------------------------------------

class RiskReviewIn(BaseModel):
    action: Literal["approve", "override"]
    category: Literal["Low", "Medium", "High"] | None = None
    reason: str = ""


@router.post("/cases/{case_id}/risk-review")
def review_risk(case_id: str, body: RiskReviewIn, db: Session = Depends(get_db), user: User = Depends(registrar)):
    rs = services.review_risk(db, case_id, body.action, user, body.category, body.reason)
    return {"case_id": case_id, "review_status": rs.review_status, "category": services.effective_category(rs)}


@router.post("/risk-review/approve-bulk")
def approve_risk_bulk(case_ids: list[str], db: Session = Depends(get_db), user: User = Depends(registrar)):
    for cid in case_ids:
        services.review_risk(db, cid, "approve", user, reason="bulk approval")
    return {"approved": len(case_ids)}


# --- review queue -------------------------------------------------------------------

@router.get("/review-queue")
def review_queue(db: Session = Depends(get_db), _=Depends(registrar),
                 risk: str | None = "High", limit: int = Query(50, le=500), offset: int = 0):
    """Everything awaiting a registrar: undecided listings in the open cause list, and
    risk scores not yet reviewed (new or changed category)."""
    cyc = services.open_cycle(db)
    listings = []
    if cyc:
        listings = [r for r in services.cause_list(db, cyc.id) if r["decision"] is None]
    stmt = (select(Case, RiskScore).join(RiskScore, RiskScore.case_id == Case.id)
            .where(Case.status == "Pending", RiskScore.review_status == "pending"))
    if risk:
        stmt = stmt.where(RiskScore.category == risk)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    # Same ordering as the scheduler's priority: overdue and court-controllable first,
    # then the oldest filing, so the queue reads as "what to look at first".
    services.apply_settings(db)
    mult = sql_case((RiskScore.court_controllable, 1.0), else_=C.EXTERNAL_BLOCK_PENALTY)
    priority = ((RiskScore.probability * 100 + sql_case((RiskScore.overdue, 20), else_=0)) * mult
                + sql_case((Case.in_custody, C.CUSTODY_PRIORITY), else_=0))
    stmt = stmt.order_by(priority.desc(), Case.filing_date, Case.id)
    rows = db.execute(stmt.limit(limit).offset(offset)).all()
    return {
        "open_cycle": cyc.id if cyc else None,
        "open_cycle_week": cyc.week_start if cyc else None,
        "undecided_listings": len(listings),
        "listings": listings[:limit],
        "risk_pending_total": total,
        "risk_pending": [case_row(c, rs) for c, rs in rows],
    }


# --- magistrate: my schedule ---------------------------------------------------------

@router.get("/my-schedule")
def my_schedule(db: Session = Depends(get_db), user: User = Depends(current_user),
                magistrate_id: str | None = None):
    """Approved listings only: nothing is on a magistrate's schedule until a registrar approves it."""
    if user.role == "magistrate":
        magistrate_id = user.magistrate_id
    elif user.role not in {"registrar", "management", "admin"}:
        raise HTTPException(403, "Not permitted")
    if not magistrate_id:
        raise HTTPException(400, "magistrate_id is required")
    mag = db.get(Magistrate, magistrate_id)
    if not mag:
        raise HTTPException(404, "Magistrate not found")
    cycles = db.scalars(select(ReviewCycle).where(ReviewCycle.status == "APPROVED")
                        .order_by(ReviewCycle.week_start.desc()).limit(4)).all()
    weeks = []
    for c in cycles:
        rows = [r for r in services.final_cause_list(db, c.id) if r["magistrate_id"] == magistrate_id]
        rows.sort(key=lambda r: (r["date"], r["position"]))
        cases = {x.id: x for x in db.scalars(select(Case).where(Case.id.in_([r["case_id"] for r in rows])))}
        for r in rows:
            r["days_overdue"] = days_overdue(cases[r["case_id"]]) if r["case_id"] in cases else None
            r["in_custody"] = bool(r["case_id"] in cases and cases[r["case_id"]].in_custody)
        weeks.append({"cycle_id": c.id, "week_start": c.week_start, "listings": rows})
    plans = db.scalars(select(SessionPlan).where(SessionPlan.magistrate_id == magistrate_id,
                                                 SessionPlan.status == "APPROVED")
                       .order_by(SessionPlan.start_date.desc())).all()
    return {
        "magistrate": {"id": mag.id, "name": mag.full_name, "court_station": mag.court_station,
                       "court_level": mag.court_level, "unavailable_days": mag.unavailable_days,
                       "daily_capacity": mag.daily_capacity},
        "weeks": weeks,
        "sessions": [session_out(db, p) for p in plans],
    }


# --- registrar: what needs attention this week ------------------------------------------

@router.get("/needs-attention")
def needs_attention(db: Session = Depends(get_db), _=Depends(require("registrar", "management", "admin"))):
    return services.needs_attention(db)


# --- High Court criminal sessions ------------------------------------------------------

def session_out(db: Session, p: SessionPlan) -> dict:
    names = dict(db.execute(select(User.id, User.full_name)).all())
    mag = db.get(Magistrate, p.magistrate_id)
    cases = {c.id: c for c in db.scalars(select(Case).where(Case.id.in_([sc.case_id for sc in p.cases])))}
    risks = {r.case_id: r for r in db.scalars(select(RiskScore).where(RiskScore.case_id.in_(list(cases))))}
    today = services.settings.today()
    return {
        "id": p.id, "court_station": p.court_station, "magistrate_id": p.magistrate_id,
        "magistrate_name": mag.full_name if mag else p.magistrate_id, "start_date": p.start_date,
        "weeks": p.weeks, "status": p.status, "created_by": names.get(p.created_by),
        "approved_by": names.get(p.approved_by), "approved_at": p.approved_at,
        "cases": [{
            "case_id": sc.case_id, "position": sc.position, "planned_date": sc.planned_date,
            "priority": sc.priority, "in_custody": bool(cases.get(sc.case_id) and cases[sc.case_id].in_custody),
            "days_pending": (today - cases[sc.case_id].filing_date).days if sc.case_id in cases else None,
            "risk_category": services.effective_category(risks[sc.case_id]) if sc.case_id in risks else None,
            "delay_status": risks[sc.case_id].delay_status if sc.case_id in risks else None,
        } for sc in p.cases],
    }


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), _=Depends(require("registrar", "management", "admin"))):
    plans = db.scalars(select(SessionPlan).order_by(SessionPlan.start_date.desc())).all()
    return [session_out(db, p) for p in plans]


@router.get("/sessions/options")
def session_options(db: Session = Depends(get_db), _=Depends(require("registrar", "management", "admin"))):
    """High Court stations, their judges, and how many committal cases are waiting."""
    waiting = {}
    for r in services.session_candidates(db):
        waiting[r["court_station"]] = waiting.get(r["court_station"], 0) + 1
    judges = db.scalars(select(Magistrate).where(Magistrate.court_level == "High Court", Magistrate.active)).all()
    out = {}
    for m in judges:
        out.setdefault(m.court_station, {"court_station": m.court_station, "waiting": waiting.get(m.court_station, 0),
                                         "judges": []})["judges"].append({"id": m.id, "name": m.full_name})
    return {"stations": sorted(out.values(), key=lambda r: -r["waiting"]),
            "cases_per_week": C.SESSION_CASES_PER_WEEK,
            "next_monday": services.week_monday(services.settings.today())}


@router.get("/sessions/candidates")
def session_candidates(station: str, db: Session = Depends(get_db),
                       _=Depends(require("registrar", "management", "admin"))):
    return services.session_candidates(db, station)


class SessionIn(BaseModel):
    court_station: str
    magistrate_id: str
    start_date: date
    weeks: int = 4


@router.post("/sessions", status_code=201)
def create_session(body: SessionIn, db: Session = Depends(get_db), user: User = Depends(registrar)):
    p = services.create_session(db, body.court_station, body.magistrate_id, body.start_date, body.weeks, user)
    return session_out(db, p)


@router.delete("/sessions/{plan_id}/cases/{case_id}")
def remove_session_case(plan_id: int, case_id: str, db: Session = Depends(get_db), _=Depends(registrar)):
    services.remove_from_session(db, plan_id, case_id)
    return session_out(db, db.get(SessionPlan, plan_id))


@router.post("/sessions/{plan_id}/approve")
def approve_session(plan_id: int, db: Session = Depends(get_db), user: User = Depends(registrar)):
    return session_out(db, services.approve_session(db, plan_id, user))
