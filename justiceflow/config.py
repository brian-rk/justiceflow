"""Central configuration for JusticeFlow TZ.

Numbers tagged SOURCE: come from a published document; the full citation, page and
quote are in data/sources/SOURCES.md. Numbers tagged ASSUMPTION have no public source
yet and are modelling choices.
"""

# --- Court structure -------------------------------------------------------

COURT_LEVELS = ["Primary", "District", "Resident Magistrate", "High Court"]

# Backlog thresholds (months a case may stay pending before it counts as backlog).
# SOURCE: NAO (March 2022), "Management of Backlog of Cases by the Justice System",
# Table 1.1 (PDF p.28), citing the Judiciary Functions Strategic Plan 2015/16-2020/21.
DISPOSITION_TARGET_MONTHS = {
    "Primary": 6,
    "District": 12,
    "Resident Magistrate": 12,
    "High Court": 24,
}

CASE_TYPES = ["Criminal", "Civil", "Land", "Matrimonial", "Probate", "Labour", "Commercial"]

# Which case types each court level hears in the synthetic data.
CASE_TYPES_BY_LEVEL = {
    "Primary": ["Criminal", "Civil", "Matrimonial", "Probate"],
    "District": ["Criminal", "Civil", "Matrimonial", "Probate", "Land"],
    "Resident Magistrate": ["Criminal", "Civil", "Commercial"],
    "High Court": ["Criminal", "Civil", "Land", "Labour", "Commercial", "Probate"],
}

# Share of filings per court level, 2025, renormalised over the four levels modelled
# (Court of Appeal and Juvenile Courts excluded).
# SOURCE: Chief Registrar Eva Nkya, reported in Daily News (13 May 2026): filed in 2025 -
# Primary 176,687; District 35,144; Resident Magistrate 6,033; High Court 21,518.
_FILED_2025 = {"Primary": 176_687, "District": 35_144, "Resident Magistrate": 6_033, "High Court": 21_518}
FILING_SHARE_BY_LEVEL = {k: v / sum(_FILED_2025.values()) for k, v in _FILED_2025.items()}

# Share of filings that are criminal matters, 2025.
# SOURCE: same statement - 138,368 criminal of 243,848 filed.
CRIMINAL_SHARE = 138_368 / 243_848

# --- Regions & stations (PROTECTED: audit-only, never scoring features) ----
# ASSUMPTION: a representative subset of real region / station names. Which courts
# exist at each station and each level is not verified.

# is_rural drives infrastructure effects in the synthetic generator only.
REGIONS = {
    "Dar es Salaam": {"is_rural": False, "stations": ["Kisutu", "Kinondoni", "Ilala", "Temeke"]},
    "Arusha": {"is_rural": False, "stations": ["Arusha Urban", "Arumeru"]},
    "Mwanza": {"is_rural": False, "stations": ["Mwanza Urban", "Ilemela"]},
    "Dodoma": {"is_rural": False, "stations": ["Dodoma Urban", "Kondoa"]},
    "Kigoma": {"is_rural": True, "stations": ["Kigoma", "Kasulu"]},
    "Rukwa": {"is_rural": True, "stations": ["Sumbawanga", "Nkasi"]},
    "Lindi": {"is_rural": True, "stations": ["Lindi", "Nachingwea"]},
}

# --- Feature contract (SRS 4.1, 6: Fairness) -------------------------------

# Features available at filing (FR-1).
FILING_FEATURES = ["case_type", "court_level", "n_parties", "represented"]

# Extra features known at each hearing (FR-2, FR-3).
HEARING_FEATURES = [
    "target_used",  # share of the disposition target already elapsed
    "hearings_held",
    "adjournment_count",
    "court_side_adjournments",
    "flag_advocate",
    "flag_prosecution",
    "flag_forensic",
]

MODEL_FEATURES = FILING_FEATURES + HEARING_FEATURES
CATEGORICAL_FEATURES = ["case_type", "court_level"]

# Held out of the model; used only by the fairness audit.
PROTECTED_FEATURES = ["region", "court_station"]

EXTERNAL_FLAGS = {
    "flag_advocate": "Advocate-requested postponement",
    "flag_prosecution": "State attorney / prosecution delay",
    "flag_forensic": "Pending forensic / expert report",
}

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
# Relative importance of balancing workload vs. clearing priority cases.
BALANCE_WEIGHT = 2
SOLVER_TIME_LIMIT_S = 20.0

# --- Human-in-the-loop (FR-6, FR-7) ----------------------------------------

# Consecutive review cycles a case may stay High with no registrar action
# before an escalation note is raised to court management.
ESCALATION_CYCLES = 3
