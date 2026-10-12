"""Case list, case detail (registrar) and clerk data entry (FR-11)."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case as sql_case, func, or_, select
from sqlalchemy.orm import Session

from justiceflow import config as C

from .. import services
from ..db import get_db
from ..models import Case, Decision, Escalation, Hearing, Magistrate, Proposal, ReviewCycle, RiskScore, User
from ..security import require

router = APIRouter(tags=["cases"])

READERS = ("clerk", "registrar", "management", "admin")

effective_cat = sql_case((RiskScore.review_status == "overridden", RiskScore.reviewed_category),
                         else_=RiskScore.category)


def risk_out(rs: RiskScore | None) -> dict | None:
    if rs is None:
        return None
    return {
        "probability": rs.probability, "model_category": rs.category,
        "category": services.effective_category(rs), "overdue": rs.overdue,
        "driving_factors": rs.driving_factors, "delay_status": rs.delay_status,
        "court_controllable": rs.court_controllable, "target_used": rs.target_used,
        "scored_at": rs.scored_at, "review_status": rs.review_status,
        "reviewed_category": rs.reviewed_category, "review_reason": rs.review_reason,
        "reviewed_at": rs.reviewed_at,
    }


def days_overdue(c: Case) -> int | None:
    """Days a pending case is past its disposition target (None while still within it)."""
    age = (services.settings.today() - c.filing_date).days
    over = age - round(C.DISPOSITION_TARGET_MONTHS[c.court_level] * 30.44)
    return over if over > 0 and c.status == "Pending" else None


def case_row(c: Case, rs: RiskScore | None) -> dict:
    age = (services.settings.today() - c.filing_date).days
    return {
        "id": c.id, "case_type": c.case_type, "court_level": c.court_level,
        "court_station": c.court_station, "region": c.region, "n_parties": c.n_parties,
        "represented": c.represented, "filing_date": c.filing_date, "status": c.status,
        "age_days": age,
        "days_overdue": days_overdue(c),
        "division": C.division(c.court_level, c.case_type),
        "offence": c.offence, "in_custody": c.in_custody,
        "remand_days": age if c.in_custody else None,
        "next_date": c.next_date,
        "sessions_case": C.is_sessions_case(c.court_level, c.case_type, c.offence),
        "assigned_magistrate_id": c.assigned_magistrate_id, "source": c.source,
        "risk": risk_out(rs),
    }


@router.get("/cases")
def list_cases(
    db: Session = Depends(get_db), _=Depends(require(*READERS)),
    status: str = "Pending", risk: str | None = None, controllable: bool | None = None,
    case_type: str | None = None, court_level: str | None = None, court_station: str | None = None,
    review_status: str | None = None, q: str | None = None,
    sort: Literal["risk", "age", "id", "filing_date"] = "risk", order: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, le=500), offset: int = 0,
):
    stmt = select(Case, RiskScore).outerjoin(RiskScore, RiskScore.case_id == Case.id)
    conds = []
    if status != "all":
        conds.append(Case.status == status)
    if risk:
        conds.append(effective_cat == risk)
    if controllable is not None:
        conds.append(RiskScore.court_controllable == controllable)
    if case_type:
        conds.append(Case.case_type == case_type)
    if court_level:
        conds.append(Case.court_level == court_level)
    if court_station:
        conds.append(Case.court_station == court_station)
    if review_status:
        conds.append(RiskScore.review_status == review_status)
    if q:
        conds.append(Case.id.ilike(f"%{q}%"))
    if conds:
        stmt = stmt.where(and_(*conds))

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    key = {"risk": RiskScore.probability, "age": Case.filing_date, "id": Case.id,
           "filing_date": Case.filing_date}[sort]
    # "age desc" means oldest first, i.e. filing_date ascending.
    desc = (order == "desc") != (sort == "age")
    stmt = stmt.order_by(key.desc().nulls_last() if desc else key.asc().nulls_last(), Case.id)
    rows = db.execute(stmt.limit(limit).offset(offset)).all()
    return {"total": total, "items": [case_row(c, rs) for c, rs in rows]}


@router.get("/cases/{case_id}")
def case_detail(case_id: str, db: Session = Depends(get_db), _=Depends(require(*READERS))):
    c = db.get(Case, case_id)
    if not c:
        raise HTTPException(404, "Case not found")
    rs = db.get(RiskScore, case_id)
    hearings = c.hearings
    last = hearings[-1] if hearings else None
    names = dict(db.execute(select(User.id, User.full_name)).all())
    listing = db.execute(
        select(Proposal, ReviewCycle.status).join(ReviewCycle, ReviewCycle.id == Proposal.cycle_id)
        .where(Proposal.case_id == case_id).order_by(Proposal.date.desc()).limit(1)).first()
    decisions = db.scalars(select(Decision).where(Decision.case_id == case_id).order_by(Decision.id.desc())).all()
    escalations = db.scalars(select(Escalation).where(Escalation.case_id == case_id)).all()
    return {
        **case_row(c, rs),
        "resolution_date": c.resolution_date,
        "active_flags": {f: bool(getattr(last, f)) if last else False for f in C.EXTERNAL_FLAGS},
        "flag_labels": C.EXTERNAL_FLAGS,
        "responsible": services.responsible_body(rs.delay_status if rs else ""),
        "disposition_target_months": C.DISPOSITION_TARGET_MONTHS[c.court_level],
        "hearings": [{
            "hearing_no": h.hearing_no, "hearing_date": h.hearing_date, "outcome": h.outcome,
            "adjournment_reason": h.adjournment_reason, "flag_advocate": h.flag_advocate,
            "flag_prosecution": h.flag_prosecution, "flag_forensic": h.flag_forensic,
            "flag_witness": h.flag_witness, "flag_record": h.flag_record, "next_date": h.next_date,
            "notes": h.notes, "recorded_by": names.get(h.recorded_by),
        } for h in reversed(hearings)],
        "latest_listing": ({"cycle_id": listing[0].cycle_id, "cycle_status": listing[1],
                            "magistrate_id": listing[0].magistrate_id, "day": listing[0].day,
                            "date": listing[0].date, "position": listing[0].position}
                           if listing else None),
        "decisions": [{"cycle_id": d.cycle_id, "action": d.action, "by": names.get(d.registrar_id),
                       "timestamp": d.timestamp, "reason": d.reason, "risk_category": d.risk_category,
                       "day": d.day, "magistrate_id": d.magistrate_id} for d in decisions],
        "escalations": [{"cycle_id": e.cycle_id, "note": e.note, "acknowledged": e.acknowledged_by is not None}
                        for e in escalations],
    }


@router.get("/reference")
def reference(db: Session = Depends(get_db), _=Depends(require(*READERS, "magistrate"))):
    """Dropdown values for forms and filters."""
    stations = db.execute(select(Magistrate.court_station, Magistrate.region).distinct()).all()
    return {
        "case_types": C.CASE_TYPES, "court_levels": C.COURT_LEVELS,
        "case_types_by_level": C.CASE_TYPES_BY_LEVEL, "working_days": C.WORKING_DAYS,
        "stations": sorted({s for s, _ in stations}),
        "station_region": {s: r for s, r in stations},
        "adjournment_reasons": {"advocate": "Advocate-requested postponement",
                                "prosecution": "State attorney / prosecution delay (incl. investigation)",
                                "forensic": "Pending forensic / expert report",
                                "witness": "Witness did not attend",
                                "record": "Awaiting record of proceedings (appeals)",
                                "court": "Court-side (magistrate unavailable, list overrun)"},
        "flag_labels": C.EXTERNAL_FLAGS,
        "offences": [o for o in C.OFFENCES if o != "Not criminal"],
        "criminal_types": sorted(C.CRIMINAL_TYPES),
        "no_advocates_levels": sorted(C.NO_ADVOCATES_LEVELS),
        "divisions": C.HIGH_COURT_DIVISIONS,
        "scope": "Judiciary of Tanzania (Tanzania Mainland)",
    }


# --- clerk data entry (FR-11) ---------------------------------------------------

Reason = Literal["advocate", "prosecution", "forensic", "witness", "record", "court"]


class HearingIn(BaseModel):
    hearing_date: date
    outcome: Literal["proceeded", "adjourned", "disposed"]
    adjournment_reason: Reason | None = None
    flag_advocate: bool = False
    flag_prosecution: bool = False
    flag_forensic: bool = False
    flag_witness: bool = False
    flag_record: bool = False
    # The date fixed in court for the next appearance (none if the case was disposed).
    next_date: date | None = None
    # Criminal cases: is the accused still in remand after this hearing (e.g. bail granted)?
    in_custody: bool | None = None
    notes: str = ""


class NextDateIn(BaseModel):
    hearing_date: date
    outcome: Literal["proceeded", "adjourned", "disposed"] = "adjourned"
    adjournment_reason: Reason | None = None
    flag_advocate: bool = False
    flag_prosecution: bool = False
    flag_forensic: bool = False
    flag_witness: bool = False
    flag_record: bool = False
    in_custody: bool | None = None


@router.post("/cases/{case_id}/suggest-next-date")
def suggest_next_date(case_id: str, body: NextDateIn, db: Session = Depends(get_db),
                      _=Depends(require("clerk", "registrar", "magistrate"))):
    """A next date to propose in court, with the reasons behind it. The presiding
    officer fixes the actual date; the clerk records it with the hearing."""
    flags = {f: getattr(body, f) for f in C.EXTERNAL_FLAGS}
    return services.suggest_next_date(db, case_id, body.hearing_date, body.outcome,
                                      body.adjournment_reason, flags, body.in_custody)


@router.post("/cases/{case_id}/hearings", status_code=201)
def record_hearing(case_id: str, body: HearingIn, db: Session = Depends(get_db),
                   user: User = Depends(require("clerk"))):
    h = services.record_hearing(db, case_id, body.model_dump(), user)
    rs = db.get(RiskScore, case_id)
    return {"hearing_no": h.hearing_no, "outcome": h.outcome, "rescored_risk": risk_out(rs)}


class CaseIn(BaseModel):
    case_type: str
    court_level: str
    court_station: str
    n_parties: int = Field(ge=2, le=50)
    represented: bool
    filing_date: date
    offence: str | None = None  # criminal matters only
    in_custody: bool = False
    next_date: date | None = None  # first date fixed by the registry


@router.post("/cases", status_code=201)
def register_case(body: CaseIn, db: Session = Depends(get_db), user: User = Depends(require("clerk"))):
    if body.court_level not in C.COURT_LEVELS or body.case_type not in C.CASE_TYPES:
        raise HTTPException(400, "Unknown court level or case type")
    if body.case_type not in C.CASE_TYPES_BY_LEVEL[body.court_level]:
        hint = (" Land disputes go to the District Land and Housing Tribunal or the High Court Land Division."
                if body.case_type == "Land" else "")
        raise HTTPException(400, f"A {body.court_level} court does not hear {body.case_type} cases.{hint}")
    if body.represented and body.court_level in C.NO_ADVOCATES_LEVELS:
        raise HTTPException(400, "Advocates may not appear in a Primary Court (Magistrates' Courts Act, s.33)")
    criminal = body.case_type in C.CRIMINAL_TYPES
    if criminal and body.case_type == "Criminal" and body.offence not in C.OFFENCES[:-1]:
        raise HTTPException(400, "Choose the offence category for a criminal case")
    if body.next_date and body.next_date < body.filing_date:
        raise HTTPException(400, "The first date cannot be before the filing date")
    if body.filing_date > services.settings.today():
        raise HTTPException(400, "Filing date is in the future")
    mags = db.scalars(select(Magistrate).where(Magistrate.court_station == body.court_station,
                                               Magistrate.court_level == body.court_level,
                                               Magistrate.active)).all()
    if not mags:
        raise HTTPException(400, f"No {body.court_level} magistrate sits at {body.court_station}")
    # Assign to the magistrate with the fewest pending cases.
    load = dict(db.execute(select(Case.assigned_magistrate_id, func.count())
                           .where(Case.status == "Pending").group_by(Case.assigned_magistrate_id)).all())
    mag = min(mags, key=lambda m: load.get(m.id, 0))
    data = body.model_dump()
    data["offence"] = ("Corruption / economic" if body.case_type == "Economic"
                       else body.offence if criminal else "Not criminal")
    # Remand is for accused awaiting trial; Court of Appeal appellants are already convicted.
    data["in_custody"] = bool(body.in_custody and criminal and body.court_level != "Court of Appeal")
    c = Case(id=services.next_case_id(db, body.court_station), region=mags[0].region,
             assigned_magistrate_id=mag.id, source="clerk", status="Pending", **data)
    db.add(c)
    db.commit()
    try:
        services.score_cases(db, [c.id])  # FR-1: score at filing
    except HTTPException:
        pass  # gate not passed: the case is stored but stays unscored
    return case_row(c, db.get(RiskScore, c.id))
