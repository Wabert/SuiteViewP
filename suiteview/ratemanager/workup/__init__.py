"""
Rate Workup — single-pass, multi-file rate loading for one plancode.

Combines the IAF (base COI + targets + benefit riders), MPF (supplemental
benefits), CKULTB04 (surrender charges) and CKULTB01 (expense-per-unit) into
one UL_Rates-ready output folder:

  POINT_PVSRB, RATE_COI, RATE_TRGPREM, RATE_SCR, RATE_EPU,
  POINT_BENEFIT, RATE_BENCOI, RATE_BENTRG  (+ WORKUP_SUMMARY)

Every rate family varies by the same (State, Sex, Rateclass, Band) space as
the base COI rates. See ``builder.py`` for the projection rules.
"""

from suiteview.ratemanager.workup.spec import BenefitSelection, WorkupSpec
from suiteview.ratemanager.workup.builder import (
    WorkupAnalysis,
    WorkupResult,
    analyze,
    build,
)

__all__ = [
    "BenefitSelection",
    "WorkupSpec",
    "WorkupAnalysis",
    "WorkupResult",
    "analyze",
    "build",
]
