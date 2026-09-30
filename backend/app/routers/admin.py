"""Admin settings: magistrate roster, courtroom capacity, disposition targets (SRS 5.1)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from justiceflow import config as C

from .. import services
from ..db import get_db
from ..models import Case, Magistrate
from ..security import require

router = APIRouter(tags=["admin"])
admin = require("admin")


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _=Depends(require("admin", "management"))):
    return services.get_settings(db)


@router.put("/settings")
def put_settings(changes: dict, db: Session = Depends(get_db), _=Depends(admin)):
    s = services.update_settings(db, changes)
    if "disposition_targets" in changes:
        s["note"] = "Disposition targets changed: retrain the model so risk scores use the new targets."
    return s


def mag_out(m: Magistrate, load: dict) -> dict:
    return {"id": m.id, "full_name": m.full_name, "court_level": m.court_level, "region": m.region,
            "court_station": m.court_station, "daily_capacity": m.daily_capacity,
            "unavailable_days": m.unavailable_days, "active": m.active, "pending_cases": load.get(m.id, 0)}


@router.get("/magistrates")
def list_magistrates(db: Session = Depends(get_db), _=Depends(require("admin", "registrar", "management"))):
    load = dict(db.execute(select(Case.assigned_magistrate_id, func.count())
                           .where(Case.status == "Pending").group_by(Case.assigned_magistrate_id)).all())
    mags = db.scalars(select(Magistrate).order_by(Magistrate.court_station, Magistrate.court_level)).all()
    return [mag_out(m, load) for m in mags]


class MagistrateIn(BaseModel):
    id: str
    full_name: str
    court_level: str
    region: str
    court_station: str
    daily_capacity: int = Field(3, ge=1, le=40)
    unavailable_days: str = ""


class MagistratePatch(BaseModel):
    full_name: str | None = None
    daily_capacity: int | None = Field(None, ge=1, le=40)
    unavailable_days: str | None = None
    active: bool | None = None


def _check_days(days: str):
    bad = {d.strip() for d in days.split(",") if d.strip()} - set(C.WORKING_DAYS)
    if bad:
        raise HTTPException(400, f"unavailable_days must use {C.WORKING_DAYS}")


@router.post("/magistrates", status_code=201)
def create_magistrate(body: MagistrateIn, db: Session = Depends(get_db), _=Depends(admin)):
    if body.court_level not in C.COURT_LEVELS:
        raise HTTPException(400, "Unknown court level")
    _check_days(body.unavailable_days)
    if db.get(Magistrate, body.id):
        raise HTTPException(409, "Magistrate id already exists")
    m = Magistrate(**body.model_dump())
    db.add(m)
    db.commit()
    return mag_out(m, {})


@router.patch("/magistrates/{mag_id}")
def update_magistrate(mag_id: str, body: MagistratePatch, db: Session = Depends(get_db), _=Depends(admin)):
    m = db.get(Magistrate, mag_id)
    if not m:
        raise HTTPException(404, "Magistrate not found")
    changes = body.model_dump(exclude_unset=True)
    if "unavailable_days" in changes:
        _check_days(changes["unavailable_days"])
    for k, v in changes.items():
        setattr(m, k, v)
    db.commit()
    return mag_out(m, {})
