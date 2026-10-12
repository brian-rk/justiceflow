"""Relational schema (SRS 8.3: case / hearing / magistrate data with referential integrity).

JusticeFlow's own store. Nothing here is ever written back to JoT-eCMS or JSDS2.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ROLES = ("clerk", "registrar", "magistrate", "management", "admin")


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str] = mapped_column(String(128))
    court_station: Mapped[str | None] = mapped_column(String(64))
    magistrate_id: Mapped[str | None] = mapped_column(ForeignKey("magistrates.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Magistrate(Base):
    __tablename__ = "magistrates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    court_level: Mapped[str] = mapped_column(String(32))
    region: Mapped[str] = mapped_column(String(64))
    court_station: Mapped[str] = mapped_column(String(64))
    daily_capacity: Mapped[int] = mapped_column(Integer, default=3)
    unavailable_days: Mapped[str] = mapped_column(String(32), default="")  # e.g. "Mon,Fri"
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_type: Mapped[str] = mapped_column(String(32))
    court_level: Mapped[str] = mapped_column(String(32), index=True)
    # Protected: audit-only, never a scoring feature.
    region: Mapped[str] = mapped_column(String(64))
    court_station: Mapped[str] = mapped_column(String(64), index=True)
    n_parties: Mapped[int] = mapped_column(Integer)
    represented: Mapped[bool] = mapped_column(Boolean)
    filing_date: Mapped[date] = mapped_column(Date)
    resolution_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="Pending", index=True)
    assigned_magistrate_id: Mapped[str | None] = mapped_column(ForeignKey("magistrates.id"))
    source: Mapped[str] = mapped_column(String(16), default="clerk")  # synthetic | tanzlii | clerk | import
    # Criminal matters: offence category, and whether the accused is held in remand.
    offence: Mapped[str] = mapped_column(String(32), default="Not criminal")
    in_custody: Mapped[bool] = mapped_column(Boolean, default=False)
    # The date the case is next due in court, as fixed by the presiding officer.
    next_date: Mapped[date | None] = mapped_column(Date, index=True)

    hearings: Mapped[list[Hearing]] = relationship(back_populates="case", order_by="Hearing.hearing_no")


class Hearing(Base):
    __tablename__ = "hearings"
    __table_args__ = (UniqueConstraint("case_id", "hearing_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    hearing_no: Mapped[int] = mapped_column(Integer)
    hearing_date: Mapped[date] = mapped_column(Date)
    outcome: Mapped[str] = mapped_column(String(16))  # proceeded | adjourned | disposed
    adjourned: Mapped[bool] = mapped_column(Boolean)
    adjournment_reason: Mapped[str | None] = mapped_column(String(16))  # advocate|prosecution|forensic|witness|record|court
    flag_advocate: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_prosecution: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_forensic: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_witness: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_record: Mapped[bool] = mapped_column(Boolean, default=False)
    next_date: Mapped[date | None] = mapped_column(Date)  # date fixed at this hearing
    notes: Mapped[str] = mapped_column(Text, default="")
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="hearings")


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    trained_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    as_of: Mapped[date] = mapped_column(Date)
    metrics: Mapped[dict] = mapped_column(JSON)
    audit_passed: Mapped[bool] = mapped_column(Boolean)
    audit_max_gap: Mapped[float] = mapped_column(Float)
    audit_threshold: Mapped[float] = mapped_column(Float)
    audit_rounds: Mapped[list] = mapped_column(JSON)
    audit_table: Mapped[list] = mapped_column(JSON)
    disposition_targets: Mapped[dict] = mapped_column(JSON)
    artifact_path: Mapped[str] = mapped_column(String(256))


class RiskScore(Base):
    """Latest score per case, plus the registrar's review of it (FR-6)."""
    __tablename__ = "risk_scores"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id"))
    scored_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    probability: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(8), index=True)
    overdue: Mapped[bool] = mapped_column(Boolean)
    driving_factors: Mapped[str] = mapped_column(Text)
    delay_status: Mapped[str] = mapped_column(String(160))
    court_controllable: Mapped[bool] = mapped_column(Boolean, index=True)
    target_used: Mapped[float] = mapped_column(Float)
    hearings_held: Mapped[int] = mapped_column(Integer, default=0)
    adjournment_count: Mapped[int] = mapped_column(Integer, default=0)
    # Registrar review
    review_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|approved|overridden
    reviewed_category: Mapped[str | None] = mapped_column(String(8))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_reason: Mapped[str] = mapped_column(Text, default="")


class ReviewCycle(Base):
    __tablename__ = "review_cycles"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. W2026-09-28
    week_start: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="PROPOSED")  # PROPOSED | APPROVED
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    solver_info: Mapped[dict] = mapped_column(JSON, default=dict)
    finalised_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    finalised_at: Mapped[datetime | None] = mapped_column(DateTime)


class Proposal(Base):
    __tablename__ = "proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("review_cycles.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    magistrate_id: Mapped[str] = mapped_column(ForeignKey("magistrates.id"))
    day: Mapped[str] = mapped_column(String(3))
    date: Mapped[date] = mapped_column(Date)
    position: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer)
    risk_category: Mapped[str] = mapped_column(String(8))
    risk_probability: Mapped[float] = mapped_column(Float)
    delay_status: Mapped[str] = mapped_column(String(160))
    driving_factors: Mapped[str] = mapped_column(Text)
    # fixed = date set in court; new = no date yet; brought_forward = moved earlier
    # from a later date fixed in court (fixed_date).
    kind: Mapped[str] = mapped_column(String(16), default="new")
    fixed_date: Mapped[date | None] = mapped_column(Date)


class CycleRisk(Base):
    """Snapshot of each pending case's risk at cycle creation (feeds FR-7)."""
    __tablename__ = "cycle_risk"
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("review_cycles.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    risk_category: Mapped[str] = mapped_column(String(8))
    delay_status: Mapped[str] = mapped_column(String(160))


class Decision(Base):
    """Append-only registrar decision log."""
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("review_cycles.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    registrar_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    magistrate_id: Mapped[str | None] = mapped_column(String(32))
    day: Mapped[str | None] = mapped_column(String(3))
    risk_category: Mapped[str | None] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(Text, default="")


class Escalation(Base):
    __tablename__ = "escalations"
    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("review_cycles.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    consecutive_high_cycles: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text)
    # Who can unblock it (police / NPS, Government Chemist, advocates, the court).
    responsible: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    response: Mapped[str] = mapped_column(Text, default="")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | int | float | str] = mapped_column(JSON)


class SessionPlan(Base):
    """A High Court criminal session: a judge sits for some weeks at a registry and
    tries a batch of committal (murder) cases. Planned separately from weekly lists."""
    __tablename__ = "session_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    court_station: Mapped[str] = mapped_column(String(64))
    magistrate_id: Mapped[str] = mapped_column(ForeignKey("magistrates.id"))
    start_date: Mapped[date] = mapped_column(Date)
    weeks: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="PROPOSED")  # PROPOSED | APPROVED
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)

    cases: Mapped[list[SessionCase]] = relationship(back_populates="plan", order_by="SessionCase.position",
                                                    cascade="all, delete-orphan")


class SessionCase(Base):
    __tablename__ = "session_cases"
    __table_args__ = (UniqueConstraint("plan_id", "case_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("session_plans.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    position: Mapped[int] = mapped_column(Integer)
    planned_date: Mapped[date] = mapped_column(Date)
    priority: Mapped[int] = mapped_column(Integer)

    plan: Mapped[SessionPlan] = relationship(back_populates="cases")
