"""
SuiteView - Audit Tool Package
================================

Cyberlife Policy Audit Tool — a self-contained feature app for building
complex dynamic DB2 queries to find policies matching detailed criteria
across coverage, rider, benefit, financial, and transaction dimensions.

Quick start (from SuiteView):
    Launched from Tools menu or the silver/blue "A" button in the header bar.

Quick start (standalone):
    python scripts/run_audit.py [--region CKPR]

Quick start (as a library):
    from suiteview.audit import launch_audit
    window = launch_audit(region="CKPR")

Shared infrastructure:
    - DB2 connections:  suiteview.core.db2_connection
    - Insurance constants: suiteview.polview.models.policy_constants
    - DB2 constants:    suiteview.core.db2_constants
"""

__version__ = "1.0.0"

# ── Core data access (no UI dependencies) ───────────────────────────────
from suiteview.core.db2_connection import DB2Connection, DB2ConnectionError, db_connection
from suiteview.core.db2_constants import REGION_DSN_MAP, REGIONS, DEFAULT_REGION

# ── UI launcher (lazy — avoids importing PyQt6 until called) ────────────

def launch_audit(region: str = DEFAULT_REGION):
    """
    Launch the Audit Tool GUI.

    If a QApplication already exists (e.g. host app), uses that.
    Otherwise creates a new one. Does NOT call sys.exit() so control
    returns to the caller after the window closes.

    Args:
        region: DB2 region code (default CKPR).
    """
    from .main import create_audit_window
    return create_audit_window(region)


__all__ = [
    # Core
    "DB2Connection",
    "DB2ConnectionError",
    "db_connection",
    "REGION_DSN_MAP",
    "REGIONS",
    "DEFAULT_REGION",
    # UI
    "launch_audit",
]
