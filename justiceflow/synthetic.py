"""Statistically-grounded synthetic case generator (SRS 4.2, 4.3).

Each case is simulated hearing by hearing, so the data carries the adjournment
history and external-delay flags that FR-2 and FR-3 need. After generation, a
calibration loop rescales hearing gaps per court level until the share of *pending*
cases that are backlog (older than their disposition target) matches the share the
Judiciary publishes. Sources for every number: data/sources/SOURCES.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C

# Backlog as a share of pending cases, by court level (the Judiciary's own measure).
# SOURCE: Judiciary of Tanzania, "Case Backlog Reduction Strategies and their
# Implementation: The Tanzanian Judiciary Experience", AJC 2024, slide 7
# ("Backlog Status in 2020"): High Court 14%, subordinate courts 23%, 15% overall.
# The slide gives one figure for all subordinate courts, so Primary, District and RM
# share it. 2020 is the most recent year with a per-level split; the same deck
# (slide 18) reports the overall share falling to 3% by June 2023.
TARGET_PENDING_BACKLOG_SHARE = {
    "Primary": 0.23,
    "District": 0.23,
    "Resident Magistrate": 0.23,
    "High Court": 0.14,
}

# Average days to get results back from the Government Chemist Laboratory.
# SOURCE: NAO (March 2022), Table 5.1 (PDF p.78): 47 days on average, with cases of up
# to a year (Table 5.2).
FORENSIC_WAIT_DAYS = 47

# ASSUMPTION: mean days between hearings before calibration rescales them.
BASE_GAP_DAYS = {"Primary": 21, "District": 30, "Resident Magistrate": 30, "High Court": 55}

# ASSUMPTION: substantive (non-adjourned) hearings needed to dispose, by case type.
SUBSTANTIVE_HEARINGS = {
    "Criminal": 5, "Civil": 4, "Land": 6, "Matrimonial": 3,
    "Probate": 2, "Labour": 4, "Commercial": 5,
}


@dataclass
class SyntheticData:
    cases: pd.DataFrame
    hearings: pd.DataFrame
    magistrates: pd.DataFrame
    as_of: pd.Timestamp
    gap_multiplier: dict = field(default_factory=dict)


def _simulate_case(rng, case, gap_mult, as_of):
    level, ctype = case["court_level"], case["case_type"]
    rural = C.REGIONS[case["region"]]["is_rural"]

    needed = 1 + rng.poisson(SUBSTANTIVE_HEARINGS[ctype] * (1 + 0.15 * (case["n_parties"] - 2)))
    p_court = 0.10 + (0.08 if rural else 0.0)
    p_advocate = 0.14 if case["represented"] else 0.03
    p_prosecution = 0.16 if ctype == "Criminal" else 0.0

    # ASSUMPTION: a quarter of criminal cases need a forensic/expert report, requested
    # at one of the first hearings. Hearings are adjourned until it comes back.
    forensic_start, forensic_ready = -1, None
    if ctype == "Criminal" and rng.random() < 0.25:
        forensic_start = rng.integers(0, 3)

    rows, date, done, k = [], case["filing_date"], 0, 0
    while done < needed and k < 60:
        if k == forensic_start:
            forensic_ready = date + pd.Timedelta(days=int(rng.exponential(FORENSIC_WAIT_DAYS)))
        forensic = forensic_ready is not None and date < forensic_ready
        gap = rng.exponential(BASE_GAP_DAYS[level] * gap_mult * (1.25 if rural else 1.0))
        date = date + pd.Timedelta(days=max(3, int(gap)))

        reason = None
        if forensic:
            reason = "forensic"
        else:
            u = rng.random()
            if u < p_prosecution:
                reason = "prosecution"
            elif u < p_prosecution + p_advocate:
                reason = "advocate"
            elif u < p_prosecution + p_advocate + p_court:
                reason = "court"

        if reason is None:
            done += 1
        rows.append({
            "case_id": case["case_id"],
            "hearing_no": k + 1,
            "hearing_date": date,
            "adjourned": reason is not None,
            "adjournment_reason": reason,
            "flag_advocate": reason == "advocate",
            "flag_prosecution": reason == "prosecution",
            "flag_forensic": bool(forensic),
        })
        k += 1

    return rows, date


def _draw_case_type(rng, level):
    """Criminal with the published national share; other types evenly."""
    types = C.CASE_TYPES_BY_LEVEL[level]
    if "Criminal" in types and rng.random() < C.CRIMINAL_SHARE:
        return "Criminal"
    return rng.choice([t for t in types if t != "Criminal"])


def _draw_cases(rng, n, as_of):
    levels = list(C.FILING_SHARE_BY_LEVEL)
    level = rng.choice(levels, size=n, p=list(C.FILING_SHARE_BY_LEVEL.values()))
    regions = list(C.REGIONS)
    # Dar es Salaam carries a larger share of filings.
    region_p = np.array([3.0] + [1.0] * (len(regions) - 1))
    region = rng.choice(regions, size=n, p=region_p / region_p.sum())

    records = []
    for i in range(n):
        lv, rg = level[i], region[i]
        rural = C.REGIONS[rg]["is_rural"]
        base_repr = {"Primary": 0.15, "District": 0.40, "Resident Magistrate": 0.55, "High Court": 0.80}[lv]
        records.append({
            "case_id": f"SYN-{i + 1:05d}",
            "case_type": _draw_case_type(rng, lv),
            "court_level": lv,
            "region": rg,
            "court_station": rng.choice(C.REGIONS[rg]["stations"]),
            "n_parties": int(2 + rng.poisson(0.6)),
            "represented": bool(rng.random() < base_repr * (0.6 if rural else 1.0)),
            "filing_date": as_of - pd.Timedelta(days=int(rng.uniform(30, 5 * 365))),
        })
    return pd.DataFrame(records)


def _simulate_all(cases, gap_mult, as_of, seed):
    hearing_rows, resolution = [], []
    for i, case in enumerate(cases.to_dict("records")):
        # Each case gets its own stream, so changing one level's gaps during
        # calibration does not reshuffle the randomness of every other case.
        rng = np.random.default_rng([seed, i])
        rows, end = _simulate_case(rng, case, gap_mult[case["court_level"]], as_of)
        hearing_rows.extend(rows)
        resolution.append(end)
    return pd.DataFrame(hearing_rows), pd.Series(resolution, index=cases.index)


def _pending_backlog_share(cases, resolution, as_of):
    """Among cases still pending on as_of, the share older than their target."""
    pending = resolution > as_of
    target_days = cases["court_level"].map(C.DISPOSITION_TARGET_MONTHS) * 30.44
    backlog = (as_of - cases["filing_date"]).dt.days > target_days
    return backlog[pending].groupby(cases.loc[pending, "court_level"]).mean()


def _magistrates(cases, rng, pending_per_magistrate=18):
    """Bench sized so a week's slots cover only part of the pending list,
    which is what makes prioritisation matter."""
    rows = []
    pending = cases[cases["status"] == "Pending"]
    for (region, station, level), grp in cases.groupby(["region", "court_station", "court_level"]):
        n_pending = (pending["court_station"].eq(station) & pending["court_level"].eq(level)).sum()
        n = max(1, round(n_pending / pending_per_magistrate))
        for j in range(n):
            off = rng.choice(C.WORKING_DAYS) if rng.random() < 0.3 else ""
            rows.append({
                "magistrate_id": f"MAG-{station[:4].upper()}-{level[:2].upper()}-{j + 1}",
                "court_level": level,
                "region": region,
                "court_station": station,
                "daily_capacity": 2 if level == "High Court" else 3,
                "unavailable_days": off,
            })
    return pd.DataFrame(rows)


def generate(n_cases: int = 4000, seed: int = 7, as_of: str = "2026-09-26",
             calibrate: bool = True, calibration_rounds: int = 10) -> SyntheticData:
    """Generate cases, hearings and magistrates as they stood on `as_of`."""
    as_of = pd.Timestamp(as_of)
    rng = np.random.default_rng(seed)
    cases = _draw_cases(rng, n_cases, as_of)

    gap_mult = {lv: 1.0 for lv in C.COURT_LEVELS}
    for _ in range(calibration_rounds if calibrate else 0):
        _, resolution = _simulate_all(cases, gap_mult, as_of, seed + 1)
        share = _pending_backlog_share(cases, resolution, as_of)
        for lv in C.COURT_LEVELS:
            observed = min(max(share.get(lv, 0.0), 0.01), 0.99)
            # Longer gaps -> more backlog; nudge the multiplier toward the target.
            gap_mult[lv] = float(gap_mult[lv] * (TARGET_PENDING_BACKLOG_SHARE[lv] / observed) ** 0.5)

    hearings, resolution = _simulate_all(cases, gap_mult, as_of, seed + 1)

    # Cut everything at as_of: later hearings have not happened yet.
    hearings = hearings[hearings["hearing_date"] <= as_of].reset_index(drop=True)
    resolved = resolution <= as_of
    cases["resolution_date"] = resolution.where(resolved)
    cases["status"] = np.where(resolved, "Disposed", "Pending")
    cases["source"] = "synthetic"

    mags = _magistrates(cases, rng)
    cases["assigned_magistrate"] = None
    for key, grp in cases.groupby(["court_station", "court_level"]).groups.items():
        pool = mags[(mags.court_station == key[0]) & (mags.court_level == key[1])]["magistrate_id"].tolist()
        cases.loc[grp, "assigned_magistrate"] = [pool[i % len(pool)] for i in range(len(grp))]

    return SyntheticData(cases, hearings, mags, as_of, gap_mult)
