"""Dashboard, escalations (FR-7), reports, fairness audit (FR-4) and model training."""


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import services
from ..db import get_db
from ..models import Case, Escalation, ModelRun, RiskScore, User, utcnow
from ..security import require
from .cases import effective_cat

router = APIRouter(tags=["oversight"])

management = require("management", "admin")


def run_out(r: ModelRun | None) -> dict | None:
    if r is None:
        return None
    return {"id": r.id, "trained_at": r.trained_at, "as_of": r.as_of, "metrics": r.metrics,
            "audit_passed": r.audit_passed, "audit_max_gap": r.audit_max_gap,
            "audit_threshold": r.audit_threshold, "audit_rounds": r.audit_rounds,
            "audit_table": r.audit_table, "disposition_targets": r.disposition_targets}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _=Depends(require("registrar", "management", "admin"))):
    pending = db.scalar(select(func.count()).where(Case.status == "Pending"))
    by_cat = dict(db.execute(select(effective_cat, func.count()).join(Case, Case.id == RiskScore.case_id)
                             .where(Case.status == "Pending").group_by(effective_cat)).all())
    high_ctrl = db.scalar(select(func.count()).select_from(RiskScore).join(Case, Case.id == RiskScore.case_id)
                          .where(Case.status == "Pending", effective_cat == "High", RiskScore.court_controllable))
    overdue = db.scalar(select(func.count()).select_from(RiskScore).join(Case, Case.id == RiskScore.case_id)
                        .where(Case.status == "Pending", RiskScore.overdue))
    risk_pending = db.scalar(select(func.count()).select_from(RiskScore).join(Case, Case.id == RiskScore.case_id)
                             .where(Case.status == "Pending", RiskScore.review_status == "pending",
                                    RiskScore.category == "High"))
    cyc = services.open_cycle(db)
    awaiting = sum(r["decision"] is None for r in services.cause_list(db, cyc.id)) if cyc else 0
    open_esc = db.scalars(select(Escalation).where(Escalation.acknowledged_by.is_(None))
                          .order_by(Escalation.id.desc())).all()
    run = services.latest_run(db)
    statuses = dict(db.execute(select(RiskScore.case_id, RiskScore.delay_status)
                               .where(RiskScore.case_id.in_([e.case_id for e in open_esc[:5]]))).all())
    in_remand = db.scalar(select(func.count()).where(Case.status == "Pending", Case.in_custody))
    return {
        "pending": pending,
        "in_remand": in_remand,
        "risk_counts": {k: by_cat.get(k, 0) for k in ["High", "Medium", "Low"]},
        "high_controllable": high_ctrl,
        "overdue": overdue,
        "high_risk_awaiting_review": risk_pending,
        "open_cycle": {"id": cyc.id, "week_start": cyc.week_start, "awaiting_decision": awaiting} if cyc else None,
        "escalations_open": len(open_esc),
        "escalations_recent": [{"id": e.id, "case_id": e.case_id, "cycle_id": e.cycle_id, "note": e.note,
                                "consecutive_high_cycles": e.consecutive_high_cycles,
                                "delay_status": statuses.get(e.case_id), "responsible": e.responsible}
                               for e in open_esc[:5]],
        "model": {"id": run.id, "trained_at": run.trained_at, "audit_passed": run.audit_passed,
                  "auc": run.metrics.get("auc")} if run else None,
    }


@router.get("/escalations")
def escalations(db: Session = Depends(get_db), _=Depends(require("registrar", "management", "admin")),
                include_acknowledged: bool = False):
    stmt = select(Escalation, Case).join(Case, Case.id == Escalation.case_id).order_by(Escalation.id.desc())
    if not include_acknowledged:
        stmt = stmt.where(Escalation.acknowledged_by.is_(None))
    names = dict(db.execute(select(User.id, User.full_name)).all())
    rows = db.execute(stmt).all()
    statuses = dict(db.execute(select(RiskScore.case_id, RiskScore.delay_status)
                               .where(RiskScore.case_id.in_([e.case_id for e, _ in rows]))).all())
    return [{
        "id": e.id, "cycle_id": e.cycle_id, "case_id": e.case_id, "note": e.note,
        "consecutive_high_cycles": e.consecutive_high_cycles, "created_at": e.created_at,
        "court_station": c.court_station, "court_level": c.court_level, "case_type": c.case_type,
        "case_status": c.status, "acknowledged_by": names.get(e.acknowledged_by),
        "acknowledged_at": e.acknowledged_at, "response": e.response,
        "responsible": e.responsible or services.responsible_body(""),
        "in_custody": c.in_custody, "days_pending": (services.settings.today() - c.filing_date).days,
        "delay_status": statuses.get(e.case_id),
    } for e, c in rows]


@router.get("/escalations/agenda")
def committee_agenda(station: str | None = None, db: Session = Depends(get_db),
                     _=Depends(require("registrar", "management", "admin"))):
    """Open escalations for a case-flow committee meeting, grouped by the body that can
    unblock them (police and prosecution, Government Chemist, advocates, the court)."""
    items = escalations(db, None, include_acknowledged=False)
    if station:
        items = [e for e in items if e["court_station"] == station]
    groups = {}
    for e in items:
        for body in e["responsible"].split("; "):
            groups.setdefault(body, []).append(e)
    return {
        "station": station, "date": services.settings.today(), "total": len(items),
        "stations": sorted({e["court_station"] for e in escalations(db, None, include_acknowledged=False)}),
        "groups": [{"responsible": k, "items": v} for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))],
    }


class AckIn(BaseModel):
    response: str


@router.post("/escalations/{esc_id}/acknowledge")
def acknowledge(esc_id: int, body: AckIn, db: Session = Depends(get_db), user: User = Depends(management)):
    e = db.get(Escalation, esc_id)
    if not e:
        raise HTTPException(404, "Escalation not found")
    if not body.response.strip():
        raise HTTPException(400, "Record what action court management is taking")
    e.acknowledged_by, e.acknowledged_at, e.response = user.id, utcnow(), body.response
    db.commit()
    return {"id": e.id, "acknowledged": True}


@router.get("/reports/backlog")
def backlog(db: Session = Depends(get_db), _=Depends(management), months: int = 24):
    return services.backlog_report(db, months)


@router.get("/fairness")
def fairness(db: Session = Depends(get_db), _=Depends(management)):
    runs = db.scalars(select(ModelRun).order_by(ModelRun.id.desc()).limit(10)).all()
    latest = runs[0] if runs else None
    return {
        "cleared_for_real_data": bool(latest and latest.audit_passed),
        "latest": run_out(latest),
        "history": [{"id": r.id, "trained_at": r.trained_at, "audit_passed": r.audit_passed,
                     "audit_max_gap": r.audit_max_gap, "auc": r.metrics.get("auc")} for r in runs],
    }


@router.post("/model/train")
def train(db: Session = Depends(get_db), user: User = Depends(management)):
    run = services.train_model(db, user)
    return run_out(run)


@router.post("/model/rescore")
def rescore(db: Session = Depends(get_db), _=Depends(management)):
    services.require_cleared_model(db)
    return {"rescored": services.score_cases(db)}
