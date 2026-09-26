"""UL Illustration Engine — suiteview.illustration

API-first calculation package for Universal Life illustration projections.
Migrated from RERUN v19.1 Excel workbook.

Quick start:
    from suiteview.illustration import project_policy

    run = project_policy("UE000576", months=12)
    results = run.states

Export debug to Excel:
    from suiteview.illustration.debug.excel_export import export_projection_to_excel
    export_projection_to_excel(results, "debug.xlsx", policy_data=policy)
"""

__version__ = "0.1.0"

# ── Data Models ───────────────────────────────────────────────
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    BenefitInfo,
    IllustrationPolicyData,
    RiderInfo,
)
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode

# ── Core Engine ───────────────────────────────────────────────
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates, load_rates

# ── Service Layer ─────────────────────────────────────────────
from suiteview.illustration.core.illustration_policy_service import (
    build_illustration_data,
)
from suiteview.illustration.api import (
    ProjectionBasis,
    ProjectionRun,
    load_policy_data,
    load_projection_basis,
    project_policy,
)


def launch_illustration():
    """Launch the Illustration app GUI."""
    from suiteview.illustration.main import create_illustration_window
    return create_illustration_window()

__all__ = [
    # Meta
    "__version__",
    # Data Models
    "CoverageSegment",
    "BenefitInfo",
    "IllustrationPolicyData",
    "RiderInfo",
    "MonthlyState",
    "PlancodeConfig",
    "load_plancode",
    # Engine
    "IllustrationEngine",
    "IllustrationRates",
    "load_rates",
    # Service
    "build_illustration_data",
    "ProjectionBasis",
    "ProjectionRun",
    "load_policy_data",
    "load_projection_basis",
    "project_policy",
    # UI
    "launch_illustration",
]
