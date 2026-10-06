"""Business mode: the soft-launch switch that locks Illustration to business scope.

Business mode is on in the packaged EXE for users whose SuiteView role has no
support privileges (ADMIN/SUPPORT). It hides or locks every developer option,
caps the illustrated rate, and limits illustration to the phase-1 plancodes and
premium-pay statuses (see :mod:`suiteview.illustration.core.run_gates`).

Source runs are developer runs and are never in business mode unless a developer
forces it on for testing with ``SUITEVIEW_ILLUSTRATION_BUSINESS_MODE=1``. Only
the exact value ``1`` is honored, and the variable can only turn business mode
on: it never unlocks a business user's packaged EXE.
"""

from __future__ import annotations

import logging
import os

from suiteview.core.access_control import has_support_privileges

logger = logging.getLogger(__name__)

BUSINESS_MODE_ENV = "SUITEVIEW_ILLUSTRATION_BUSINESS_MODE"

# Shown in tooltips/notes on locked controls.
LOCKED_NOTE = "Locked to the standard setting for business users."

# IllustrationOptions values business users always run with: the controls'
# out-of-the-box defaults, which are the settings the phase-1 testing exercised
# (Exact Days off = monthly compounding, as RERUN's unchecked default).
BUSINESS_LOCKED_OPTIONS = {
    "conform_to_tefra": True,
    "conform_to_tamra": True,
    "switch_to_option_a_in_exception": False,
    "exact_days_interest": False,
    "levelizing_premium": True,
    "guideline_by_search": False,
    "loan_repay_principal_first": False,
    "use_policy_ag49_regime": False,
    "iul_segment_crediting": False,
}


def is_business_mode() -> bool:
    """True when the current user gets the locked-down business Illustration."""
    if os.environ.get(BUSINESS_MODE_ENV) == "1":
        return True
    try:
        return not has_support_privileges()
    except Exception:
        # Permissions could not be verified: fail closed to the locked mode.
        logger.exception("Could not verify support privileges; using business mode")
        return True
