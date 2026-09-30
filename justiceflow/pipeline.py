"""End-to-end pipeline (SRS 7.2).

data -> features (protected held out) -> risk model -> fairness gate -> CP-SAT
optimiser -> registrar review -> dashboard tables.

The fairness gate and the review stage cannot be bypassed: `propose_week` refuses to
build a schedule without a passed AuditResult, and it only ever produces a PROPOSED
cycle in the ReviewStore; turning that into a cause list takes a registrar.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import scheduler
from .fairness import AuditResult, fair_fit
from .features import current_snapshots, training_snapshots
from .model import RiskModel
from .review import ReviewStore


class FairnessGateError(RuntimeError):
    """Raised when scoring or scheduling is attempted without a passed audit."""


@dataclass
class TrainedEngine:
    model: RiskModel
    audit: AuditResult
    holdout_metrics: dict
    trained_as_of: pd.Timestamp


def as_of_view(cases: pd.DataFrame, hearings: pd.DataFrame, as_of):
    """What the court record looked like on `as_of` (nothing from the future)."""
    as_of = pd.Timestamp(as_of)
    c = cases[cases["filing_date"] <= as_of].copy()
    later = c["resolution_date"] > as_of
    c.loc[later, "resolution_date"] = pd.NaT
    c["status"] = np.where(c["resolution_date"].isna(), "Pending", "Disposed")
    h = hearings[(hearings["hearing_date"] <= as_of) & hearings["case_id"].isin(c["case_id"])]
    return c, h


def train(cases, hearings, as_of, seed: int = 0) -> TrainedEngine:
    c, h = as_of_view(cases, hearings, as_of)
    snaps = training_snapshots(c, h, as_of=as_of, seed=seed)

    # Split by case so no case appears in both train and holdout.
    rng = np.random.default_rng(seed)
    ids = snaps["case_id"].unique()
    holdout_ids = set(rng.choice(ids, size=len(ids) // 4, replace=False))
    is_hold = snaps["case_id"].isin(holdout_ids)
    train_s, hold_s = snaps[~is_hold].reset_index(drop=True), snaps[is_hold].reset_index(drop=True)

    model, audit = fair_fit(RiskModel, train_s, hold_s)
    return TrainedEngine(model, audit, model.evaluate(hold_s), pd.Timestamp(as_of))


def score(engine: TrainedEngine, cases, hearings, as_of, real_data: bool = False) -> pd.DataFrame:
    if real_data and not engine.audit.passed:
        raise FairnessGateError(engine.audit.summary())
    return engine.model.score(current_snapshots(cases, hearings, as_of))


def propose_week(engine: TrainedEngine, scored: pd.DataFrame, magistrates: pd.DataFrame,
                 week_start, store: ReviewStore, cycle_id: str):
    """Optimise next week's cause list and open it for registrar review."""
    if not engine.audit.passed:
        raise FairnessGateError(engine.audit.summary())
    proposal, info = scheduler.optimise(scored, magistrates, week_start)
    store.open_cycle(cycle_id, week_start, scored, proposal)
    return proposal, info


def export_dashboard(scored: pd.DataFrame, store: ReviewStore, engine: TrainedEngine, folder):
    """Flat tables for Google Sheets / Looker Studio (one CSV per tab)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cols = ["case_id", "case_type", "court_level", "court_station", "region", "days_elapsed",
            "adjournment_count", "risk_probability", "risk_category", "overdue",
            "driving_factors", "delay_status", "court_controllable"]
    scored[cols].to_csv(folder / "risk_scores.csv", index=False)
    engine.audit.table.reset_index().to_csv(folder / "fairness_audit.csv", index=False)
    for name in ["proposals", "decisions", "cycles", "escalations"]:
        store.t[name].to_csv(folder / f"{name}.csv", index=False)
