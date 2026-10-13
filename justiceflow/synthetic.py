"""Statistically-grounded synthetic case generator (SRS 4.2, 4.3).

Each case is simulated hearing by hearing, so the data carries the adjournment
history, the next date fixed at each hearing, and the external-delay flags that FR-2
and FR-3 need. A calibration loop then rescales hearing gaps per court level until
the data matches the Judiciary's published figures:

  * "2025" (default): average days from filing to determination for cases decided in
    the last year (Judiciary 2025 Performance Report) - what the courts look like now;
  * "2020": backlog as a share of pending cases (AJC 2024 deck, slide 7) - the
    pre-reform baseline, useful to show the system under heavy backlog.

Sources for every number: data/sources/SOURCES.md. The data is about 1:100 of real
volume (12,000 cases over five years, against roughly 244,000 filings a year).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C

CALIBRATIONS = ("2025", "2020")

# 2020 baseline: backlog as a share of pending cases, by court level.
# SOURCE: Judiciary of Tanzania, "Case Backlog Reduction Strategies and their
# Implementation: The Tanzanian Judiciary Experience", AJC 2024, slide 7
# ("Backlog Status in 2020"): Court of Appeal 23%, High Court 14%, subordinate courts
# 23% (one figure for Primary, District and RM).
TARGET_PENDING_BACKLOG_SHARE_2020 = {
    "Primary": 0.23,
    "District": 0.23,
    "Resident Magistrate": 0.23,
    "High Court": 0.14,
    "Court of Appeal": 0.23,
}

# ASSUMPTION: mean days between hearings before calibration rescales them. The Court
# of Appeal sits in sessions, so its gaps are long.
BASE_GAP_DAYS = {"Primary": 21, "District": 30, "Resident Magistrate": 30, "High Court": 55,
                 "Court of Appeal": 150}

# ASSUMPTION: substantive (non-adjourned) hearings needed to dispose, by case type.
SUBSTANTIVE_HEARINGS = {
    "Criminal": 5, "Civil": 4, "Land": 6, "Matrimonial": 3,
    "Probate": 2, "Labour": 4, "Commercial": 5, "Economic": 6,
}
# ASSUMPTION: an appeal at the Court of Appeal needs one or two substantive hearings.
APPEAL_HEARINGS = 1

# ASSUMPTION: base representation rate by level (halved-ish in rural regions).
# LAW: none at Primary Courts (Magistrates' Courts Act, s.33).
BASE_REPRESENTED = {"Primary": 0.0, "District": 0.40, "Resident Magistrate": 0.55,
                    "High Court": 0.80, "Court of Appeal": 0.90}

# ASSUMPTION: share of Court of Appeal matters that wait for the record of proceedings,
# and how long that takes on average.
P_AWAITING_RECORD, RECORD_PREP_DAYS = 0.6, 180
# ASSUMPTION: share of pending cases with no next date recorded (data-entry gaps).
P_NO_NEXT_DATE = 0.03
# ASSUMPTION: shortest adjournment while a report or record is awaited.
WAITING_GAP_DAYS = 14


@dataclass
class SyntheticData:
    cases: pd.DataFrame
    hearings: pd.DataFrame
    magistrates: pd.DataFrame
    as_of: pd.Timestamp
    gap_multiplier: dict = field(default_factory=dict)
    calibration: str = "2025"


def _weekday(date: pd.Timestamp) -> pd.Timestamp:
    """Courts sit Monday to Friday."""
    while date.weekday() >= 5:
        date = date + pd.Timedelta(days=1)
    return date


def _simulate_case(rng, case, gap_mult):
    level, ctype = case["court_level"], case["case_type"]
    rural = C.REGIONS[case["region"]]["is_rural"]
    criminal = ctype in C.CRIMINAL_TYPES

    base = APPEAL_HEARINGS if level == "Court of Appeal" else SUBSTANTIVE_HEARINGS[ctype]
    needed = 1 + rng.poisson(base * (1 + 0.15 * (case["n_parties"] - 2)))
    p_court = 0.10 + (0.08 if rural else 0.0)
    p_advocate = 0.14 if case["represented"] else (0.0 if level in C.NO_ADVOCATES_LEVELS else 0.03)
    p_prosecution = 0.16 if criminal else 0.0
    p_witness = 0.08 if criminal else 0.04

    # A forensic / Government Chemist report, requested at one of the first hearings.
    forensic_start, forensic_ready = -1, None
    if criminal and level != "Court of Appeal" and rng.random() < C.FORENSIC_SHARE.get(case["offence"], 0.1):
        forensic_start = rng.integers(0, 3)
    # Appeals often wait for the record of proceedings before they can be argued.
    record_ready = None
    if level == "Court of Appeal" and rng.random() < P_AWAITING_RECORD:
        record_ready = case["filing_date"] + pd.Timedelta(days=int(rng.exponential(RECORD_PREP_DAYS)))

    rows, date, done, k = [], case["filing_date"], 0, 0
    while done < needed and k < 60:
        if k == forensic_start:
            forensic_ready = date + pd.Timedelta(days=int(rng.exponential(C.FORENSIC_WAIT_DAYS)))
        forensic = forensic_ready is not None and date < forensic_ready
        record = record_ready is not None and date < record_ready
        gap = rng.exponential(BASE_GAP_DAYS[level] * gap_mult * (1.25 if rural else 1.0))
        if forensic or record:
            gap = max(gap, WAITING_GAP_DAYS)  # no point relisting every few days while waiting
        date = _weekday(date + pd.Timedelta(days=max(3, int(gap))))

        reason = None
        if record:
            reason = "record"
        elif forensic:
            reason = "forensic"
        else:
            u, cum = rng.random(), 0.0
            for name, p in (("prosecution", p_prosecution), ("advocate", p_advocate),
                            ("witness", p_witness), ("court", p_court)):
                cum += p
                if u < cum:
                    reason = name
                    break

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
            "flag_witness": reason == "witness",
            "flag_record": bool(record),
        })
        k += 1

    # The date fixed at each hearing is when the next one took place.
    for a, b in zip(rows, rows[1:]):
        a["next_date"] = b["hearing_date"]
    if rows:
        rows[-1]["next_date"] = pd.NaT
    return rows, date


def _draw_case_type(rng, level):
    """Criminal share by level (2025 report); other types evenly."""
    types = C.CASE_TYPES_BY_LEVEL[level]
    if rng.random() < C.CRIMINAL_SHARE_BY_LEVEL[level]:
        if level == "High Court" and rng.random() < C.ECONOMIC_SHARE_OF_HC_CRIMINAL:
            return "Economic"
        return "Criminal"
    return rng.choice([t for t in types if t not in C.CRIMINAL_TYPES])


def _draw_offence(rng, level, ctype):
    if ctype == "Economic":
        return "Corruption / economic"
    if ctype != "Criminal":
        return "Not criminal"
    mix = C.OFFENCE_MIX[level]
    return rng.choice(list(mix), p=np.array(list(mix.values())) / sum(mix.values()))


def _draw_cases(rng, n, as_of):
    levels = list(C.FILING_SHARE_BY_LEVEL)
    level = rng.choice(levels, size=n, p=list(C.FILING_SHARE_BY_LEVEL.values()))
    regions = list(C.REGIONS)
    # Dar es Salaam carries a larger share of filings.
    region_p = np.array([3.0] + [1.0] * (len(regions) - 1))

    records = []
    for i in range(n):
        lv = level[i]
        rg = rng.choice(regions, p=region_p / region_p.sum())
        rural = C.REGIONS[rg]["is_rural"]
        ctype = _draw_case_type(rng, lv)
        offence = _draw_offence(rng, lv, ctype)
        # A real court of that level serving the region (a High Court division for
        # land, labour, commercial and economic cases where the region has one).
        station = rng.choice(C.court_stations(rg, lv, ctype))
        records.append({
            "case_id": f"SYN-{i + 1:05d}",
            "case_type": ctype,
            "court_level": lv,
            "region": rg,
            "court_station": station,
            "n_parties": int(2 + rng.poisson(0.6)),
            "represented": bool(rng.random() < BASE_REPRESENTED[lv] * (0.6 if rural else 1.0)),
            "offence": offence,
            # Remand is for accused awaiting trial. Criminal appellants at the Court of
            # Appeal are already convicted, so they are not counted as remand.
            "in_custody": bool(offence != "Not criminal" and lv != "Court of Appeal"
                               and rng.random() < C.REMAND_SHARE.get(offence, 0.0)),
            "filing_date": as_of - pd.Timedelta(days=int(rng.uniform(0, 5 * 365))),
        })
    return pd.DataFrame(records)


def _simulate_all(cases, gap_mult, seed):
    hearing_rows, resolution = [], []
    for i, case in enumerate(cases.to_dict("records")):
        # Each case gets its own stream, so changing one level's gaps during
        # calibration does not reshuffle the randomness of every other case.
        rng = np.random.default_rng([seed, i])
        rows, end = _simulate_case(rng, case, gap_mult[case["court_level"]])
        hearing_rows.extend(rows)
        resolution.append(end)
    return pd.DataFrame(hearing_rows), pd.Series(resolution, index=cases.index)


def pending_backlog_share(cases, resolution, as_of):
    """Among cases still pending on as_of, the share older than their target."""
    pending = resolution > as_of
    target_days = cases["court_level"].map(C.DISPOSITION_TARGET_MONTHS) * 30.44
    backlog = (as_of - cases["filing_date"]).dt.days > target_days
    return backlog[pending].groupby(cases.loc[pending, "court_level"]).mean()


def avg_days_to_decision(cases, resolution, as_of):
    """Mean days from filing to decision, for cases decided in the year before as_of
    (the Judiciary's 'time taken from filing to determination')."""
    decided = (resolution <= as_of) & (resolution > as_of - pd.Timedelta(days=365))
    days = (resolution - cases["filing_date"]).dt.days
    return days[decided].groupby(cases.loc[decided, "court_level"]).mean()


def _magistrates(cases, as_of, rng):
    """A bench at every court in the register (so any court can take new cases), sized
    from the Judiciary's published workload per judge / magistrate (filed in the last
    year plus pending, divided by workload)."""
    rows = []
    pending = cases[cases["status"] == "Pending"]
    recent = cases[cases["filing_date"] > as_of - pd.Timedelta(days=365)]
    counts = (pd.concat([recent, pending]).groupby(["court_station", "court_level"]).size().to_dict())
    for court in C.COURTS:
        region, station, level = court["region"], court["court_name"], court["court_level"]
        n = max(1, round(counts.get((station, level), 0) / C.WORKLOAD_2025[level]))
        for j in range(n):
            off = rng.choice(C.WORKING_DAYS) if rng.random() < 0.3 else ""
            rows.append({
                "magistrate_id": f"MAG-{court['code']}-{j + 1}",
                "court_level": level,
                "region": region,
                "court_station": station,
                "daily_capacity": C.DAILY_CAPACITY[level],
                "unavailable_days": off,
            })
    return pd.DataFrame(rows)


def generate(n_cases: int = 4000, seed: int = 7, as_of: str = "2026-09-26",
             calibrate: bool = True, calibration_rounds: int = 12,
             calibration: str = "2025") -> SyntheticData:
    """Generate cases, hearings and magistrates as they stood on `as_of`."""
    if calibration not in CALIBRATIONS:
        raise ValueError(f"calibration must be one of {CALIBRATIONS}")
    as_of = pd.Timestamp(as_of)
    rng = np.random.default_rng(seed)
    cases = _draw_cases(rng, n_cases, as_of)

    gap_mult = {lv: 1.0 for lv in C.COURT_LEVELS}
    for _ in range(calibration_rounds if calibrate else 0):
        _, resolution = _simulate_all(cases, gap_mult, seed + 1)
        if calibration == "2025":
            observed = avg_days_to_decision(cases, resolution, as_of)
            for lv in C.COURT_LEVELS:
                ratio = C.AVG_DAYS_TO_DECISION_2025[lv] / max(observed.get(lv, np.nan), 1.0)
                if np.isfinite(ratio):
                    gap_mult[lv] = float(gap_mult[lv] * ratio ** 0.8)
        else:
            share = pending_backlog_share(cases, resolution, as_of)
            for lv in C.COURT_LEVELS:
                observed = min(max(share.get(lv, 0.0), 0.01), 0.99)
                # Longer gaps -> more backlog; nudge the multiplier toward the target.
                gap_mult[lv] = float(gap_mult[lv] * (TARGET_PENDING_BACKLOG_SHARE_2020[lv] / observed) ** 0.5)

    hearings, resolution = _simulate_all(cases, gap_mult, seed + 1)
    resolved = resolution <= as_of
    cases["resolution_date"] = resolution.where(resolved)
    cases["status"] = np.where(resolved, "Disposed", "Pending")
    cases["source"] = "synthetic"

    # The date each pending case is next due in court: its first simulated hearing
    # after as_of. A few have none recorded, as in any real registry.
    upcoming = hearings[hearings["hearing_date"] > as_of].groupby("case_id")["hearing_date"].min()
    cases["next_date"] = cases["case_id"].map(upcoming).where(cases["status"] == "Pending")
    no_date = (cases["status"] == "Pending") & (rng.random(len(cases)) < P_NO_NEXT_DATE)
    cases.loc[no_date, "next_date"] = pd.NaT

    # Cut everything at as_of: later hearings have not happened yet.
    hearings = hearings[hearings["hearing_date"] <= as_of].reset_index(drop=True)

    mags = _magistrates(cases, as_of, rng)
    cases["assigned_magistrate"] = None
    for key, grp in cases.groupby(["court_station", "court_level"]).groups.items():
        pool = mags[(mags.court_station == key[0]) & (mags.court_level == key[1])]["magistrate_id"].tolist()
        cases.loc[grp, "assigned_magistrate"] = [pool[i % len(pool)] for i in range(len(grp))]

    return SyntheticData(cases, hearings, mags, as_of, gap_mult, calibration)
