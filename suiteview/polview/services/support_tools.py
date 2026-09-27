"""Policy Support tab state derivation."""

from __future__ import annotations

from dataclasses import dataclass

from suiteview.polview.services.glp_exception import is_glp_exception_eligible


@dataclass(frozen=True)
class SupportToolState:
    loaded: bool
    has_annuity_rider: bool
    glp_eligible: bool


def build_support_tool_state(policy) -> SupportToolState:
    """Derive support-tool availability without mutating widgets."""
    loaded = bool(policy and getattr(policy, "exists", False))
    if not loaded:
        return SupportToolState(False, False, False)
    has_annuity = any(
        str(getattr(coverage, "plancode", "")).strip().upper() == "0699830R"
        for coverage in policy.coverages.get_coverages()
    )
    return SupportToolState(loaded, has_annuity, is_glp_exception_eligible(policy))
