"""
ABR Quote — static constants, lookup tables, and configuration.

Values here are *display-only* labels, VBT mappings, and mortality
parameters.  All editable rate/fee data now lives exclusively in
the UL_Rates SQL Server database (see abr_odbc_database.py).
"""

from typing import Dict, Tuple

# =============================================================================
# PLAN CODE DISPLAY INFORMATION  (not editable — cosmetic only)
# =============================================================================

# Plan code → (level_period, product_description)
PLAN_CODE_INFO: Dict[str, Tuple[str, str]] = {
    "B15TD100": ("10", "Signature Term 2012"),
    "B15TD200": ("15", "Signature Term 2012"),
    "B15TD300": ("20", "Signature Term 2012"),
    "B15TD400": ("30", "Signature Term 2012"),
    "B15TD500": ("1",  "Signature Term 2012"),
    "B75TL100": ("10", "Signature Term 2018"),
    "B75TL200": ("15", "Signature Term 2018"),
    "B75TL300": ("20", "Signature Term 2018"),
    "B75TL400": ("30", "Signature Term 2018"),
    "B75TL500": ("1",  "Signature Term 2018"),
}

# =============================================================================
# MODAL / BILLING LABELS  (display only — factors are in the DB)
# =============================================================================

# Billing mode → human-readable label
MODAL_LABELS: Dict[int, str] = {
    1: "Annual",
    2: "Semi-Annual",
    3: "Quarterly",
    4: "Monthly",
    5: "PAC Monthly",
    6: "Bi-Weekly",
}

# NSD_MD_CD → billing_mode_code
# Non-standard modes force PMT_FQY_PER=01 (monthly) and the actual billing
# cadence is indicated by NSD_MD_CD.  The premium in CyberLife is still a
# monthly premium — collected via a Premium Depositor Fund (PDF).
NON_STANDARD_MODE_MAP: Dict[str, int] = {
    "1": 6,   # Weekly  → treat as PAC monthly for factor purposes
    "2": 6,   # Bi-Weekly → treat as PAC monthly for factor purposes
    "4": 5,   # 13thly  → PAC monthly
    "9": 5,   # 9thly   → PAC monthly
    "A": 5,   # 10thly  → PAC monthly
    "S": 5,   # Semi-Monthly → PAC monthly
}

NON_STANDARD_MODE_LABELS: Dict[str, str] = {
    "1": "Weekly",
    "2": "Bi-Weekly",
    "4": "13thly",
    "9": "9thly",
    "A": "10thly",
    "S": "Semi-Monthly",
}

# =============================================================================
# TABLE RATING MAPPING  (letter → numeric multiplier)
# =============================================================================

TABLE_RATING_MAP: Dict[str, int] = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7,
}


def get_table_rating_numeric(table_letter: str) -> int:
    """Convert table rating letter (A-G) to numeric (1-7). Returns 0 for standard."""
    if not table_letter or table_letter.strip() == "":
        return 0
    return TABLE_RATING_MAP.get(table_letter.upper(), 0)


# =============================================================================
# RATE CLASS → VBT BLOCK MAPPING
# =============================================================================

# Sex + rate_class → VBT block key
# N = Non-smoker (preferred), S = Smoker
# P = Preferred Non-smoker, Q = Preferred Smoker (mapped like N/S for VBT)
# R = Preferred Plus Non-smoker, T = Tobacco user
VBT_BLOCK_MAP: Dict[Tuple[str, str], str] = {
    # Male
    ("M", "N"): "MN", ("M", "P"): "MN", ("M", "R"): "MN",
    ("M", "S"): "MS", ("M", "Q"): "MS", ("M", "T"): "MS",
    # Female
    ("F", "N"): "FN", ("F", "P"): "FN", ("F", "R"): "FN",
    ("F", "S"): "FS", ("F", "Q"): "FS", ("F", "T"): "FS",
    # Unisex — default to male non-smoker
    ("U", "N"): "MN", ("U", "P"): "MN", ("U", "R"): "MN",
    ("U", "S"): "MS", ("U", "Q"): "MS", ("U", "T"): "MS",
}


def get_vbt_block(sex: str, rate_class: str) -> str:
    """Return VBT block key ('MN', 'FN', 'MS', 'FS') for given sex and rate class."""
    return VBT_BLOCK_MAP.get((sex.upper(), rate_class.upper()), "MN")


# =============================================================================
# MORTALITY IMPROVEMENT DEFAULTS
# =============================================================================

MORTALITY_IMPROVEMENT_RATE: float = 0.01    # 1% annual improvement
MORTALITY_IMPROVEMENT_CAP: int = 105        # Cap age for improvement (MI cease age)
MORTALITY_MULTIPLIER: float = 0.75          # 75% for Chronic/Critical riders
MORTALITY_MULTIPLIER_TERMINAL: float = 1.0  # 100% for Terminal rider

# =============================================================================
# MATURITY / DURATION LIMITS
# =============================================================================

MATURITY_AGE: int = 95
MAX_DURATION_YEARS: int = 121       # VBT max duration (years)
MAX_DURATION_MONTHS: int = 1460     # ~121 years × 12 months
