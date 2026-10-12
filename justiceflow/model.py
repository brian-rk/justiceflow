"""Risk classification model (FR-1, FR-2, FR-3, FR-8).

Gradient-boosted trees predict the probability that a case exceeds its disposition
target. Every score comes with:
  * driving factors: each feature's contribution, measured by resetting that feature
    to a neutral baseline and seeing how much the probability moves;
  * a delay status: court-controllable vs. externally blocked (and by what).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score

from . import config as C
from .features import feature_matrix

# Neutral values used when measuring a feature's contribution.
NUMERIC_BASELINE = {
    "n_parties": 2, "represented": 0, "target_used": 0, "hearings_held": 0,
    "adjournment_count": 0, "court_side_adjournments": 0,
    "flag_advocate": 0, "flag_prosecution": 0, "flag_forensic": 0, "flag_witness": 0, "flag_record": 0,
}

FEATURE_LABELS = {
    "case_type": lambda v: f"Case type: {v}",
    "court_level": lambda v: f"Court level: {v}",
    "n_parties": lambda v: f"{v} parties",
    "represented": lambda v: "Legally represented" if v else "Unrepresented",
    "target_used": lambda v: f"{v:.0%} of disposition target elapsed",
    "hearings_held": lambda v: f"{v} hearings held",
    "adjournment_count": lambda v: f"{v} adjournments",
    "court_side_adjournments": lambda v: f"{v} court-side adjournments",
    "flag_advocate": lambda v: "Advocate postponement active" if v else "No advocate postponement",
    "flag_prosecution": lambda v: "Prosecution delay active" if v else "No prosecution delay",
    "flag_forensic": lambda v: "Forensic report pending" if v else "No forensic report pending",
    "flag_witness": lambda v: "Witness did not attend" if v else "Witnesses attending",
    "flag_record": lambda v: "Awaiting record of proceedings" if v else "Record of proceedings ready",
    "offence": lambda v: f"Offence: {v}",
}


def risk_category(p: float) -> str:
    label = C.RISK_BANDS[0][1]
    for lower, name in C.RISK_BANDS:
        if p >= lower:
            label = name
    return label


def delay_status(row) -> str:
    active = [label for flag, label in C.EXTERNAL_FLAGS.items() if bool(row[flag])]
    return "Externally blocked: " + "; ".join(active) if active else "Court-controllable"


class RiskModel:
    def __init__(self, **params):
        defaults = dict(max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                        l2_regularization=1.0, categorical_features="from_dtype", random_state=0)
        self.clf = HistGradientBoostingClassifier(**{**defaults, **params})
        self._cat_freq: dict[str, pd.Series] = {}

    def fit(self, snaps: pd.DataFrame, sample_weight=None) -> "RiskModel":
        X = feature_matrix(snaps)
        self.clf.fit(X, snaps["label"], sample_weight=sample_weight)
        self._cat_freq = {c: X[c].value_counts(normalize=True) for c in C.CATEGORICAL_FEATURES}
        return self

    def predict_proba(self, snaps: pd.DataFrame) -> np.ndarray:
        return self.clf.predict_proba(feature_matrix(snaps))[:, 1]

    def evaluate(self, snaps: pd.DataFrame) -> dict:
        p = self.predict_proba(snaps)
        y = snaps["label"].to_numpy()
        return {
            "n": int(len(y)),
            "positive_rate": float(y.mean()),
            "auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else float("nan"),
            "brier": float(brier_score_loss(y, p)),
        }

    # --- explanations -----------------------------------------------------

    def contributions(self, snaps: pd.DataFrame) -> pd.DataFrame:
        """Per-feature effect on probability (positive = pushes risk up)."""
        X = feature_matrix(snaps).reset_index(drop=True)
        base = self.clf.predict_proba(X)[:, 1]
        out = pd.DataFrame(index=X.index)

        for col, neutral in NUMERIC_BASELINE.items():
            Xn = X.copy()
            Xn[col] = neutral
            out[col] = base - self.clf.predict_proba(Xn)[:, 1]

        for col in C.CATEGORICAL_FEATURES:
            expected = np.zeros(len(X))
            for cat, w in self._cat_freq[col].items():
                Xc = X.copy()
                Xc[col] = pd.Categorical([cat] * len(X), categories=X[col].cat.categories)
                expected += w * self.clf.predict_proba(Xc)[:, 1]
            out[col] = base - expected
        return out

    def score(self, snaps: pd.DataFrame, top_k: int = 3) -> pd.DataFrame:
        """Score snapshots and attach explanations and delay status."""
        snaps = snaps.reset_index(drop=True)
        p = self.predict_proba(snaps)
        contrib = self.contributions(snaps)

        overdue = snaps["days_elapsed"] > snaps.get("target_days", np.inf)
        p = np.where(overdue, 1.0, p)

        drivers = []
        for i, row in snaps.iterrows():
            if overdue[i]:
                drivers.append("Already past disposition target")
                continue
            top = contrib.loc[i].sort_values(key=np.abs, ascending=False).head(top_k)
            drivers.append("; ".join(
                f"{FEATURE_LABELS[f](row[f])} ({v:+.2f})" for f, v in top.items() if abs(v) >= 0.01
            ) or "No single dominant factor")

        result = snaps.copy()
        result["risk_probability"] = p.round(3)
        result["risk_category"] = [risk_category(x) for x in p]
        result["overdue"] = overdue.to_numpy()
        result["driving_factors"] = drivers
        result["delay_status"] = [delay_status(r) for _, r in snaps.iterrows()]
        result["court_controllable"] = result["delay_status"] == "Court-controllable"
        return result
