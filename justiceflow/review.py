"""Registrar review and escalation (FR-6, FR-7, SRS 6: Human oversight).

Nothing the system proposes is final until a named registrar acts on it:
  * a proposed cause list starts as PROPOSED;
  * each listing is approved, edited, or removed by a registrar (bulk approval is
    allowed but is still an explicit, logged registrar action);
  * only listings with a registrar decision appear in the finalised cause list.

Every action is written to an append-only decision log. Across review cycles, a case
that stays "High" with no registrar action for ESCALATION_CYCLES consecutive cycles
produces an escalation note for court management.

State is kept as CSV tables in a folder, so the same files can be uploaded to
Google Sheets (one tab each) for the Looker Studio dashboard.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config as C

ACTIONS = {"approve", "edit", "remove", "override_risk", "acknowledge"}


class ReviewStore:
    TABLES = {
        "proposals": ["cycle_id", "case_id", "magistrate_id", "day", "date", "position",
                      "court_station", "court_level", "case_type", "priority",
                      "risk_category", "risk_probability", "delay_status", "driving_factors"],
        "risk_history": ["cycle_id", "case_id", "risk_category", "risk_probability",
                         "delay_status", "court_station", "court_level"],
        "decisions": ["cycle_id", "case_id", "action", "registrar", "timestamp",
                      "magistrate_id", "day", "risk_category", "reason"],
        "cycles": ["cycle_id", "week_start", "status", "created", "finalised_by", "finalised_at"],
        "escalations": ["cycle_id", "case_id", "consecutive_high_cycles", "court_station",
                        "court_level", "note"],
    }

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.t = {name: self._load(name, cols) for name, cols in self.TABLES.items()}

    def _load(self, name, cols):
        path = self.folder / f"{name}.csv"
        return pd.read_csv(path) if path.exists() else pd.DataFrame(columns=cols)

    def save(self):
        for name, df in self.t.items():
            df.to_csv(self.folder / f"{name}.csv", index=False)

    def _append(self, name, rows):
        new = pd.DataFrame(rows, columns=self.TABLES[name])
        self.t[name] = new if self.t[name].empty else pd.concat([self.t[name], new], ignore_index=True)

    # --- cycle lifecycle --------------------------------------------------

    def open_cycle(self, cycle_id: str, week_start, scored: pd.DataFrame, proposal: pd.DataFrame):
        if cycle_id in set(self.t["cycles"]["cycle_id"]):
            raise ValueError(f"cycle {cycle_id} already exists")
        self._append("cycles", [{"cycle_id": cycle_id, "week_start": str(pd.Timestamp(week_start).date()),
                                 "status": "PROPOSED", "created": _now()}])
        prop = proposal.assign(cycle_id=cycle_id)
        self._append("proposals", prop.reindex(columns=self.TABLES["proposals"]).to_dict("records"))
        hist = scored.assign(cycle_id=cycle_id)
        self._append("risk_history", hist.reindex(columns=self.TABLES["risk_history"]).to_dict("records"))
        self.save()

    def _cycle_status(self, cycle_id):
        row = self.t["cycles"][self.t["cycles"]["cycle_id"] == cycle_id]
        if row.empty:
            raise KeyError(f"unknown cycle {cycle_id}")
        return row["status"].iloc[0]

    def decide(self, cycle_id: str, case_id: str, action: str, registrar: str, *,
               magistrate_id=None, day=None, risk_category=None, reason: str = ""):
        if action not in ACTIONS:
            raise ValueError(f"action must be one of {sorted(ACTIONS)}")
        if not registrar:
            raise ValueError("a registrar id is required for every decision")
        if self._cycle_status(cycle_id) != "PROPOSED":
            raise PermissionError(f"cycle {cycle_id} is already finalised")
        if action in {"edit", "override_risk", "remove"} and not reason:
            raise ValueError(f"'{action}' needs a reason for the audit log")
        self._append("decisions", [{
            "cycle_id": cycle_id, "case_id": case_id, "action": action, "registrar": registrar,
            "timestamp": _now(), "magistrate_id": magistrate_id, "day": day,
            "risk_category": risk_category, "reason": reason,
        }])

    def approve_all(self, cycle_id: str, registrar: str):
        """Explicit bulk approval of every listing not yet decided."""
        decided = set(self._decisions(cycle_id)["case_id"])
        for cid in self._proposal(cycle_id)["case_id"]:
            if cid not in decided:
                self.decide(cycle_id, cid, "approve", registrar, reason="bulk approval")

    def finalise(self, cycle_id: str, registrar: str) -> pd.DataFrame:
        """Build the final cause list from registrar decisions only."""
        if not registrar:
            raise ValueError("a registrar id is required to finalise")
        final = self.final_cause_list(cycle_id)
        cyc = self.t["cycles"] = self.t["cycles"].astype(object)
        idx = cyc.index[cyc["cycle_id"] == cycle_id]
        cyc.loc[idx, ["status", "finalised_by", "finalised_at"]] = ["APPROVED", registrar, _now()]
        self.run_escalation(cycle_id)
        self.save()
        return final

    def final_cause_list(self, cycle_id: str) -> pd.DataFrame:
        prop = self._proposal(cycle_id).set_index("case_id")
        dec = self._decisions(cycle_id)
        listing = dec[dec["action"].isin(["approve", "edit", "remove"])].groupby("case_id").last()
        rows = []
        for cid, d in listing.iterrows():
            if d["action"] == "remove" or cid not in prop.index:
                continue
            row = prop.loc[cid].to_dict() | {"case_id": cid, "approved_by": d["registrar"]}
            if d["action"] == "edit":
                row["magistrate_id"] = d["magistrate_id"] if pd.notna(d["magistrate_id"]) else row["magistrate_id"]
                row["day"] = d["day"] if pd.notna(d["day"]) else row["day"]
                row["edited"] = True
            rows.append(row)
        return pd.DataFrame(rows)

    # --- escalation (FR-7) ------------------------------------------------

    def run_escalation(self, cycle_id: str, n: int = C.ESCALATION_CYCLES) -> pd.DataFrame:
        rows = find_escalations(self.t["cycles"]["cycle_id"].tolist(), cycle_id,
                                self.t["risk_history"], self.t["decisions"], n)
        self.t["escalations"] = self.t["escalations"][self.t["escalations"]["cycle_id"] != cycle_id]
        self._append("escalations", rows)
        return pd.DataFrame(rows, columns=self.TABLES["escalations"])

    # --- helpers ----------------------------------------------------------

    def _proposal(self, cycle_id):
        return self.t["proposals"][self.t["proposals"]["cycle_id"] == cycle_id]

    def _decisions(self, cycle_id):
        return self.t["decisions"][self.t["decisions"]["cycle_id"] == cycle_id]


def find_escalations(cycle_order: list, cycle_id, risk_history: pd.DataFrame,
                     decisions: pd.DataFrame, n: int = C.ESCALATION_CYCLES) -> list[dict]:
    """Cases rated High in each of the last `n` cycles (ending at `cycle_id`) with no
    registrar decision on them in any of those cycles.

    risk_history needs cycle_id, case_id, risk_category, delay_status, court_station,
    court_level; decisions needs cycle_id, case_id.
    """
    upto = cycle_order[: cycle_order.index(cycle_id) + 1][-n:]
    if len(upto) < n:
        return []

    hist = risk_history[risk_history["cycle_id"].isin(upto)]
    high = hist[hist["risk_category"] == "High"].groupby("case_id")["cycle_id"].nunique()
    always_high = set(high[high == n].index)
    acted = set(decisions[decisions["cycle_id"].isin(upto)]["case_id"])
    latest = hist[hist["cycle_id"] == cycle_id].drop_duplicates("case_id").set_index("case_id")
    labels = ", ".join(str(c) for c in upto)
    return [{
        "cycle_id": cycle_id, "case_id": cid, "consecutive_high_cycles": n,
        "court_station": latest.loc[cid, "court_station"], "court_level": latest.loc[cid, "court_level"],
        "note": (f"Case {cid} has been rated High risk for {n} consecutive review cycles "
                 f"({labels}) with no registrar action. Status: {latest.loc[cid, 'delay_status']}."),
    } for cid in sorted(always_high - acted) if cid in latest.index]


def _now():
    return datetime.now().isoformat(timespec="seconds")
