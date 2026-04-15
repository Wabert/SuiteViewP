"""UL Illustration Engine — suiteview.illustration

API-first calculation package for Universal Life illustration projections.
Migrated from RERUN v19.1 Excel workbook.

Quick start:
    from suiteview.illustration import build_illustration_data, IllustrationEngine

    policy = build_illustration_data("UE000576")
    engine = IllustrationEngine()
    results = engine.project(policy, months=12)

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

__all__ = [
    # Meta
    "__version__",
    # Data Models
    "CoverageSegment",
    "BenefitInfo",
    "IllustrationPolicyData",
    "MonthlyState",
    "PlancodeConfig",
    "load_plancode",
    # Engine
    "IllustrationEngine",
    "IllustrationRates",
    "load_rates",
    # Service
    "build_illustration_data",
]
