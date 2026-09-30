"""Registrar workflow: cause list (FR-5, FR-6), risk review, review queue; magistrate schedule."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import services
from ..db import get_db
from ..models import Case, Decision, Magistrate, Proposal, ReviewCycle, RiskScore, User
from ..security import current_user, require
from .cases import case_row

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
    places = dict(db.execute(select(Case.id, Case.court_station)).all())
    for r in items:
        m = mags.get(r["magistrate_id"])
        r["magistrate_name"] = m.full_name if m else r["magistrate_id"]
        r["court_station"] = places.get(r["case_id"])
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
    rows = db.execute(stmt.order_by(RiskScore.probability.desc(), Case.id).limit(limit).offset(offset)).all()
    return {
        "open_cycle": cyc.id if cyc else None,
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
        weeks.append({"cycle_id": c.id, "week_start": c.week_start, "listings": rows})
    return {
        "magistrate": {"id": mag.id, "name": mag.full_name, "court_station": mag.court_station,
                       "court_level": mag.court_level, "unavailable_days": mag.unavailable_days,
                       "daily_capacity": mag.daily_capacity},
        "weeks": weeks,
    }
