"""User-supplied settings for a Rate Workup run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class BenefitSelection:
    """One benefit rate table to include in the workup.

    ``mpf_code`` links the benefit to an MPF premium code when its charges
    live in the Misc Premium File instead of the IAF (the telltale: 0 COI
    rates in the IAF but target rates present). Linked benefits take their
    BENCOI from the MPF and their BENTRG from the IAF.
    """
    code: str                 # IAF plan_option (benefit) code
    renewable: bool = False   # rate varies by attained age vs level at issue
    mpf_code: str = ""        # MPF premium code ('' = charges come from IAF)
    # First Index(BENCOI)/Index(BENTRG). 0 = derive from the convention:
    # (base_index + 2-digit type code) × 100, letters via SUBTYPE_LETTER_MAP.
    start_index: int = 0


@dataclass
class WorkupSpec:
    """Everything needed to build one plancode's full rate workup."""
    plancode: str = ""
    output_dir: str = ""
    fmt: str = "db"                # "db" (CSV folder) | "excel" (one workbook)
    maturity_age: int = 121        # SCR/EPU schedules fill out to this age

    # Source files — IAF is required, the rest are optional.
    iaf_path: str = ""
    mpf_path: str = ""
    scr_path: str = ""             # CKULTB04 report
    epu_path: str = ""             # CKULTB01 report

    # The plancode's base index. Every rate family allocates from this same
    # number (each physical table is its own index space, so COI/TRGPREM/SCR/
    # EPU all start at base; benefits pack sequentially from base within the
    # BENCOI/BENTRG space). Dedup: identical rate tables share one index.
    base_index: int = 13400

    # CKULTB internal (2-char) plan selections.
    scr_plan: str = ""
    epu_plan: str = ""
    epu_freq: str = "M"
    epu_rule: str = ""

    # CKULTB04 state-code mapping confirmed by the user (raw code → 2-letter
    # abbreviation). '**' always maps to 'AA'; codes not listed here fall
    # back to the CyberLife numeric state table.
    state_map: Dict[str, str] = field(default_factory=dict)

    benefits: List[BenefitSelection] = field(default_factory=list)
