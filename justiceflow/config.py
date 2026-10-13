"""Central configuration for JusticeFlow TZ.

Numbers tagged SOURCE: come from a published document; the full citation, page and
quote are in data/sources/SOURCES.md. Numbers tagged ASSUMPTION have no public source
yet and are modelling choices. LAW: marks a rule taken from Tanzanian legislation.

Scope: the Judiciary of Tanzania (Tanzania Mainland). Zanzibar has its own judiciary
and is not modelled.
"""

# --- Court structure -------------------------------------------------------

COURT_LEVELS = ["Primary", "District", "Resident Magistrate", "High Court", "Court of Appeal"]

# Backlog thresholds (months a case may stay pending before it counts as backlog).
# SOURCE: NAO (March 2022), "Management of Backlog of Cases by the Justice System",
# Table 1.1 (PDF p.28), citing the Judiciary Functions Strategic Plan 2015/16-2020/21.
DISPOSITION_TARGET_MONTHS = {
    "Primary": 6,
    "District": 12,
    "Resident Magistrate": 12,
    "High Court": 24,
    "Court of Appeal": 24,
}

# "Economic" = corruption and economic crimes (High Court CEC Division).
CASE_TYPES = ["Criminal", "Civil", "Land", "Matrimonial", "Probate", "Labour", "Commercial", "Economic"]
CRIMINAL_TYPES = {"Criminal", "Economic"}

# Which case types each court hears.
# LAW: land disputes go to the District Land and Housing Tribunals (Ministry of Lands,
# outside the Judiciary) and the High Court Land Division, not to Primary, District or
# RM courts (Land Disputes Courts Act, Cap. 216). Labour disputes start at the
# Commission for Mediation and Arbitration and reach the High Court Labour Division.
CASE_TYPES_BY_LEVEL = {
    "Primary": ["Criminal", "Civil", "Matrimonial", "Probate"],
    "District": ["Criminal", "Civil", "Matrimonial", "Probate"],
    "Resident Magistrate": ["Criminal", "Civil", "Commercial", "Matrimonial"],
    "High Court": ["Criminal", "Civil", "Land", "Labour", "Commercial", "Probate", "Economic"],
    "Court of Appeal": ["Criminal", "Civil", "Land", "Labour", "Commercial"],
}

# High Court divisions (SOURCE: Judiciary 2025 Performance Report, s.1.3.2: Commercial,
# Labour, Land, and Corruption and Economic Crimes Divisions). Other High Court work is
# done in the zonal sub-registries.
HIGH_COURT_DIVISIONS = {
    "Land": "Land Division",
    "Labour": "Labour Division",
    "Commercial": "Commercial Division",
    "Economic": "Corruption and Economic Crimes Division",
}


def division(court_level: str, case_type: str) -> str:
    """The forum a case is heard in: a High Court division, or the court level itself."""
    if court_level == "High Court":
        return "High Court " + HIGH_COURT_DIVISIONS.get(case_type, "sub-registry")
    return court_level


# LAW: advocates may not appear in a Primary Court (Magistrates' Courts Act, Cap. 11,
# s.33). Representation is therefore always "no" there.
NO_ADVOCATES_LEVELS = {"Primary"}

# Filings per court level, 2025.
# SOURCE: Judiciary of Tanzania, Comprehensive Performance Report of the Judicial
# Functions 2025, Table 3.1 (PDF p.41); also the Chief Registrar in Daily News, 13 May
# 2026. Juvenile Courts (1,225) are not modelled.
_FILED_2025 = {"Primary": 176_687, "District": 35_144, "Resident Magistrate": 6_033,
               "High Court": 21_518, "Court of Appeal": 3_214}
FILING_SHARE_BY_LEVEL = {k: v / sum(_FILED_2025.values()) for k, v in _FILED_2025.items()}

# Share of filings that are criminal matters, 2025.
# SOURCE: same report, PDF p.40 - 138,368 criminal of 243,848 filed.
CRIMINAL_SHARE = 138_368 / 243_848
# Criminal share by court level, 2025. SOURCE: court-level cards, pp.48-50
# (filed C | Cr): Primary 69,795 | 106,892; District 14,097 | 21,047; RM 3,661 | 2,372;
# High Court 15,303 | 6,215; Court of Appeal 2,017 | 1,224.
CRIMINAL_SHARE_BY_LEVEL = {"Primary": 106_892 / 176_687, "District": 21_047 / 35_144,
                           "Resident Magistrate": 2_372 / 6_033, "High Court": 6_215 / 21_518,
                           "Court of Appeal": 1_224 / 3_241}
# ASSUMPTION: share of High Court criminal filings that go to the CEC Division.
ECONOMIC_SHARE_OF_HC_CRIMINAL = 0.15

# --- 2025 performance figures (what "today" looks like) -----------------------
# SOURCE: Judiciary 2025 Performance Report.

# Average days from filing to determination, cases decided in 2025 (Chart 3.5, p.47;
# court-level cards pp.48-50).
AVG_DAYS_TO_DECISION_2025 = {"Primary": 30, "District": 116, "Resident Magistrate": 150,
                             "High Court": 186, "Court of Appeal": 816}
# Pending cases and backlog at the end of 2025 (Tables 3.3 and 3.4, pp.41-42).
PENDING_2025 = {"Primary": 7_240, "District": 8_214, "Resident Magistrate": 2_303,
                "High Court": 10_381, "Court of Appeal": 5_039}
BACKLOG_2025 = {"Primary": 1, "District": 54, "Resident Magistrate": 108,
                "High Court": 121, "Court of Appeal": 1_547}
BACKLOG_SHARE_2025 = {k: BACKLOG_2025[k] / PENDING_2025[k] for k in PENDING_2025}
# Average workload per judge / magistrate / Court of Appeal panel (Table 3.10, p.46).
WORKLOAD_2025 = {"Primary": 227, "District": 167, "Resident Magistrate": 125,
                 "High Court": 310, "Court of Appeal": 787}

# --- Regions & courts (PROTECTED: audit-only, never scoring features) --------
# Seven Mainland regions. Every court is a real one from the court register in
# justiceflow/courts.csv, built by `python -m justiceflow.build_courts` from the
# Judiciary's public court map (jmap.judiciary.go.tz), with the few courts the map
# omits added from the instruments that establish them (each row names its source):
# Court of Appeal registries (GN 579 of 2020), Lindi served by the Mtwara High Court
# (GN 853A of 2023), Dodoma Resident Magistrate's Court (Magistrates' Courts Act).
# is_rural drives infrastructure effects in the synthetic generator only.
REGIONS = {
    "Dar es Salaam": {"is_rural": False},
    "Arusha": {"is_rural": False},
    "Mwanza": {"is_rural": False},
    "Dodoma": {"is_rural": False},
    "Kigoma": {"is_rural": True},
    "Rukwa": {"is_rural": True},
    "Lindi": {"is_rural": True},
}


def _load_courts():
    import csv
    from pathlib import Path
    with (Path(__file__).with_name("courts.csv")).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# Each: code, region (whose cases it hears), district, court_level, court_name, division, source.
COURTS = _load_courts()
COURT_BY_NAME = {c["court_name"]: c for c in COURTS}


def court_stations(region: str, court_level: str, case_type: str | None = None) -> list[str]:
    """Courts of this level that hear cases from this region. At the High Court a case
    goes to the matching division where the region has one (e.g. Dar es Salaam High
    Court Land Division), otherwise to the general registry."""
    rows = [c for c in COURTS if c["region"] == region and c["court_level"] == court_level]
    if court_level == "High Court":
        division = [c for c in rows if c["division"] and c["division"] == case_type]
        rows = division or [c for c in rows if not c["division"]]
    return [c["court_name"] for c in rows]


def court_code(name: str) -> str:
    """Short code of a court, e.g. PC-KARIAKOO; a made-up one for unknown names."""
    c = COURT_BY_NAME.get(name)
    if c:
        return c["code"]
    import re
    return re.sub(r"[^A-Z]", "", name.upper())[:10] or "COURT"


# --- Criminal matters --------------------------------------------------------

OFFENCES = ["Homicide", "Sexual offence", "Robbery / violence", "Property / theft", "Drugs",
            "Corruption / economic", "Other", "Not criminal"]

# ASSUMPTION: offence mix of criminal filings at each level.
OFFENCE_MIX = {
    "Primary": {"Property / theft": 0.45, "Robbery / violence": 0.30, "Other": 0.25},
    "District": {"Property / theft": 0.35, "Robbery / violence": 0.20, "Sexual offence": 0.15,
                 "Drugs": 0.10, "Other": 0.20},
    "Resident Magistrate": {"Property / theft": 0.30, "Robbery / violence": 0.20, "Sexual offence": 0.15,
                            "Drugs": 0.15, "Corruption / economic": 0.10, "Other": 0.10},
    "High Court": {"Homicide": 0.80, "Drugs": 0.20},
    "Court of Appeal": {"Homicide": 0.35, "Sexual offence": 0.30, "Robbery / violence": 0.20,
                        "Drugs": 0.10, "Other": 0.05},
}

# ASSUMPTION: share of cases needing a Government Chemist / forensic report, by offence.
FORENSIC_SHARE = {"Homicide": 0.70, "Sexual offence": 0.60, "Drugs": 0.90, "Robbery / violence": 0.20,
                  "Property / theft": 0.05, "Corruption / economic": 0.10, "Other": 0.10}

# ASSUMPTION: share of accused held in remand while awaiting trial (not used at the
# Court of Appeal, whose criminal appellants are already convicted).
# LAW: murder, treason, armed robbery and some drug and economic offences are
# not bailable (Criminal Procedure Act, Cap. 20, s.148(5)), so those shares are high.
REMAND_SHARE = {"Homicide": 1.0, "Robbery / violence": 0.7, "Drugs": 0.6, "Sexual offence": 0.5,
                "Corruption / economic": 0.4, "Property / theft": 0.2, "Other": 0.1}


def is_sessions_case(court_level: str, case_type: str, offence: str | None) -> bool:
    """High Court criminal trials (murder and other committal cases) are heard in
    criminal sessions, planned in batches, not on the weekly cause list."""
    return court_level == "High Court" and case_type == "Criminal" and offence == "Homicide"


# --- Feature contract (SRS 4.1, 6: Fairness) -------------------------------

# Features available at filing (FR-1).
FILING_FEATURES = ["case_type", "court_level", "n_parties", "represented", "offence"]

# Extra features known at each hearing (FR-2, FR-3).
HEARING_FEATURES = [
    "target_used",  # share of the disposition target already elapsed
    "hearings_held",
    "adjournment_count",
    "court_side_adjournments",
    "flag_advocate",
    "flag_prosecution",
    "flag_forensic",
    "flag_witness",
    "flag_record",
]

MODEL_FEATURES = FILING_FEATURES + HEARING_FEATURES
CATEGORICAL_FEATURES = ["case_type", "court_level", "offence"]

# Held out of the model; used only by the fairness audit.
PROTECTED_FEATURES = ["region", "court_station"]

# Delays the court cannot fix by itself, and who can.
EXTERNAL_FLAGS = {
    "flag_advocate": "Advocate-requested postponement",
    "flag_prosecution": "State attorney / prosecution delay",
    "flag_forensic": "Pending forensic / expert report",
    "flag_witness": "Witness did not attend",
    "flag_record": "Awaiting record of proceedings",
}
# Adjournment reason recorded at a hearing -> the flag it sets.
REASON_FLAG = {"advocate": "flag_advocate", "prosecution": "flag_prosecution",
               "forensic": "flag_forensic", "witness": "flag_witness", "record": "flag_record"}

# Who can unblock each external delay. Escalations go to the case-flow committee with
# these agencies named, since the court cannot clear them alone.
RESPONSIBLE_BODY = {
    "flag_prosecution": "Police (investigation) and National Prosecutions Service",
    "flag_forensic": "Government Chemist Laboratory Authority",
    "flag_witness": "Police (summons) and the parties",
    "flag_advocate": "Advocates (Tanganyika Law Society)",
    "flag_record": "Court registry (record of proceedings)",
}
COURT_BODY = "Court (in-charge judge or magistrate)"

# --- Risk categories -------------------------------------------------------

# Probability of exceeding the disposition target -> category.
RISK_BANDS = [(0.0, "Low"), (0.35, "Medium"), (0.65, "High")]

# --- Fairness gate (FR-4) --------------------------------------------------

# Max tolerated gap in false-positive "High"-risk rate between any two regions,
# after conditioning on case type and court level.
FPR_GAP_THRESHOLD = 0.10
# Groups with fewer true negatives than this are reported but not gated on.
MIN_GROUP_NEGATIVES = 30

# --- Scheduling (FR-5) -----------------------------------------------------

WORKING_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
# Weight applied to externally-blocked cases (deprioritised, not dropped).
EXTERNAL_BLOCK_PENALTY = 0.2
# Priority added when the accused is in remand (prison congestion is a national concern).
CUSTODY_PRIORITY = 15
# Relative importance of balancing workload vs. clearing priority cases.
BALANCE_WEIGHT = 2
SOLVER_TIME_LIMIT_S = 20.0

# ASSUMPTION: matters a judge / magistrate / panel can take in a day, by level.
DAILY_CAPACITY = {"Primary": 8, "District": 6, "Resident Magistrate": 6, "High Court": 4,
                  "Court of Appeal": 6}

# Next-date suggestions (at the end of a hearing). ASSUMPTION unless tagged.
NEXT_DATE_GAP_DAYS = {"High": (7, 14), "Medium": (14, 28), "Low": (28, 42)}
# SOURCE: NAO (March 2022), Table 5.1 - Government Chemist results take 47 days on average.
FORENSIC_WAIT_DAYS = 47
RECORD_WAIT_DAYS = 60  # ASSUMPTION: preparing a record of proceedings
PROSECUTION_GAP_DAYS = 14  # ASSUMPTION: a short date to check on the investigation
# ASSUMPTION: an accused in remand is brought back at least this often. Confirm the
# statutory limit (Criminal Procedure Act, s.225) with the Judiciary.
REMAND_MAX_GAP_DAYS = 14

# A case "brought forward" by the optimiser must currently be fixed this far out.
BRING_FORWARD_MIN_DAYS = 21

# Criminal sessions: ASSUMPTION - trials a High Court judge completes per sessions week.
SESSION_CASES_PER_WEEK = 3

# --- Human-in-the-loop (FR-6, FR-7) ----------------------------------------

# Consecutive review cycles a case may stay High with no registrar action
# before an escalation note is raised to the case-flow committee.
ESCALATION_CYCLES = 3
