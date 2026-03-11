"""
SuiteView - PolView Package
============================

Policy Information Viewer — a self-contained feature app for viewing
life insurance policy data stored in DB2 databases.

Quick start (from SuiteView):
    Launched from Tools menu or the green "P" button in the header bar.

Quick start (standalone):
    python scripts/run_polview.py [policy_number] [--region CKPR]

Quick start (as a library):
    from suiteview.polview import PolicyInformation, load_policy

    # Headless data access — no UI required
    pol = load_policy("U0532652", region="CKPR")
    print(pol.status_description, pol.base_plancode)

Shared infrastructure:
    - DB2 connections:  suiteview.core.db2_connection
    - Insurance rates:  suiteview.core.rates
    - DB2 constants:    suiteview.core.db2_constants
"""

__version__ = "2.2.0"

# ── Core data access (no UI dependencies) ───────────────────────────────
from .models.policy_information import PolicyInformation, load_policy, close_all_connections
from .models.cl_polrec.policy_data_classes import (
    CoverageInfo,
    BenefitInfo,
    AgentInfo,
    LoanInfo,
    PolicyNotFoundError,
)
from suiteview.core.db2_connection import DB2Connection, DB2ConnectionError, db_connection
from suiteview.core.db2_constants import REGION_DSN_MAP, REGIONS, DEFAULT_REGION

# ── UI launcher (lazy — avoids importing PyQt6 until called) ────────────

def launch_viewer(policy_number: str = None, region: str = DEFAULT_REGION):
    """
    Launch the PolView GUI.

    If a QApplication already exists (e.g. host app), uses that.
    Otherwise creates a new one. Does NOT call sys.exit() so control
    returns to the caller after the window closes.

    Args:
        policy_number: Optional policy to load on startup.
        region: DB2 region code.
    """
    from .main import create_viewer  # deferred import avoids PyQt6 at package-load time
    return create_viewer(policy_number, region)


__all__ = [
    # Core
    "PolicyInformation",
    "load_policy",
    "close_all_connections",
    # Data classes
    "CoverageInfo",
    "BenefitInfo",
    "AgentInfo",
    "LoanInfo",
    "PolicyNotFoundError",
    # Database (from shared core)
    "DB2Connection",
    "DB2ConnectionError",
    "db_connection",
    # Config (from shared core)
    "REGION_DSN_MAP",
    "REGIONS",
    "DEFAULT_REGION",
    # UI
    "launch_viewer",
    # Meta
    "__version__",
]
