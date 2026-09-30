"""Fairness parity gate (FR-4, SRS 6: Fairness).

The audit asks: among cases that did NOT end up in backlog, is any region more
likely to have been wrongly flagged "High" than another, for otherwise similar cases?

"Otherwise similar" is handled by stratifying on case type x court level: each
region's false-positive rate is compared with its stratum's rate, and those
deviations are averaged (weighted by negatives) into a region-level adjusted FPR.

If the widest gap between regions exceeds FPR_GAP_THRESHOLD, the gate fails and the
model is retrained with higher weight on the over-flagged regions' negatives. The
gate passes only when the gap closes; otherwise real-data deployment stays blocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C

try:
    from fairlearn.metrics import MetricFrame, false_positive_rate
except ImportError:  # the gate still works without fairlearn
    MetricFrame = None


@dataclass
class AuditResult:
    passed: bool
    group_col: str
    max_gap: float
    threshold: float
    table: pd.DataFrame
    rounds: list = field(default_factory=list)

    def summary(self) -> str:
        state = "PASSED" if self.passed else "FAILED - real-data deployment blocked"
        return (f"Fairness gate {state}: max adjusted FPR gap across {self.group_col} = "
                f"{self.max_gap:.3f} (threshold {self.threshold:.2f}, {len(self.rounds)} round(s))")


def _is_high(p):
    return p >= dict((n, lo) for lo, n in C.RISK_BANDS)["High"]


def audit(snaps: pd.DataFrame, proba: np.ndarray, group_col: str = "region",
          threshold: float | None = None) -> AuditResult:
    threshold = C.FPR_GAP_THRESHOLD if threshold is None else threshold
    df = snaps[[group_col, "case_type", "court_level", "label"]].copy()
    df["high"] = _is_high(proba).astype(int)
    neg = df[df["label"] == 0].copy()

    neg["stratum"] = neg["case_type"] + " | " + neg["court_level"]
    neg["stratum_fpr"] = neg.groupby("stratum")["high"].transform("mean")
    neg["deviation"] = neg["high"] - neg["stratum_fpr"]
    overall_fpr = neg["high"].mean()

    table = neg.groupby(group_col).agg(
        negatives=("high", "size"),
        raw_fpr=("high", "mean"),
        mean_deviation=("deviation", "mean"),
    )
    table["adjusted_fpr"] = (overall_fpr + table["mean_deviation"]).clip(0, 1)

    if MetricFrame is not None:
        mf = MetricFrame(metrics=false_positive_rate, y_true=df["label"], y_pred=df["high"],
                         sensitive_features=df[group_col])
        table["fairlearn_fpr"] = mf.by_group

    table["gated"] = table["negatives"] >= C.MIN_GROUP_NEGATIVES
    gated = table[table["gated"]]["adjusted_fpr"]
    gap = float(gated.max() - gated.min()) if len(gated) > 1 else 0.0
    return AuditResult(gap <= threshold, group_col, gap, threshold, table.round(3))


def reweight(snaps: pd.DataFrame, table: pd.DataFrame, weights: np.ndarray,
             group_col: str = "region", strength: float = 1.5) -> np.ndarray:
    """Upweight true negatives in regions whose adjusted FPR is above average,
    so the model learns not to over-flag them."""
    target = table.loc[table["gated"], "adjusted_fpr"].mean()
    excess = (table["adjusted_fpr"] - target).clip(lower=0)
    factor = 1 + strength * excess / max(target, 1e-3)
    w = weights.copy()
    is_neg = snaps["label"].to_numpy() == 0
    w[is_neg] *= snaps.loc[is_neg, group_col].map(factor).fillna(1.0).to_numpy()
    return w


def fair_fit(model_factory, train: pd.DataFrame, holdout: pd.DataFrame,
             group_col: str = "region", max_rounds: int = 5):
    """Train, audit, and reweight until the gate passes or rounds run out.

    Returns (model, AuditResult). The caller must check `result.passed`.
    """
    weights = np.ones(len(train))
    rounds = []
    for _ in range(max_rounds):
        model = model_factory().fit(train, sample_weight=weights)
        result = audit(holdout, model.predict_proba(holdout), group_col)
        rounds.append(round(result.max_gap, 4))
        if result.passed:
            break
        # Reweight using the training set's own audit so the holdout stays unseen.
        train_audit = audit(train, model.predict_proba(train), group_col)
        weights = reweight(train, train_audit.table, weights, group_col)
    result.rounds = rounds
    return model, result
