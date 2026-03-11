"""
SuiteView - ABR Quote Package
==============================

Accelerated Benefit Rider (ABR) Quote Tool — calculates accelerated
death benefit quotes for term life insurance policies.

Theme: "Crimson Slate" (Crimson & Slate-Blue)
Database: UL_Rates ODBC DSN (shared SQL Server)

Quick start (standalone):
    python scripts/run_abrquote.py

Quick start (embedded from SuiteView):
    from suiteview.abrquote import launch_abrquote
    launch_abrquote()

Quick start (headless — calculation only):
    from suiteview.abrquote.core.apv_engine import APVEngine
    from suiteview.abrquote.core.mortality_engine import MortalityEngine
"""

__version__ = "1.0.0"

# ── Core data access (no UI dependencies) ───────────────────────────────
from .models.abr_constants import (
    PLAN_CODE_INFO, TABLE_RATING_MAP,
)
from .models.abr_data import (
    ABRPolicyData, MedicalAssessment, MortalityParams,
    APVResult, ABRQuoteResult,
)


# ── UI launcher (lazy — avoids importing PyQt6 until called) ────────────

def launch_abrquote():
    """
    Launch the ABR Quote Tool GUI.

    If a QApplication already exists (e.g. host app), uses that.
    Otherwise creates a new one.  Does NOT call sys.exit() so control
    returns to the caller after the window closes.
    """
    from .main import create_abrquote_window  # deferred import
    return create_abrquote_window()


__all__ = [
    # Constants
    "PLAN_CODE_INFO", "TABLE_RATING_MAP",
    # Data classes
    "ABRPolicyData", "MedicalAssessment", "MortalityParams",
    "APVResult", "ABRQuoteResult",
    # UI
    "launch_abrquote",
    # Meta
    "__version__",
]

