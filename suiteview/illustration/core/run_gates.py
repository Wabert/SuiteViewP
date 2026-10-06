"""Soft-launch run gates: which policies business users may illustrate, and how.

One place for the phase-1 scope rules, applied at policy load (Run disabled with
the reason) and again on every run (``run_service.execute_run`` and Compare), so
saved, imported and Compare cases are gated the same way:

* **Plancode (M5)** — business users may illustrate only the phase-1 plancodes
  in ``plancodes/phase1_allowlist.json``. Developers keep the plancode table's
  ``CanIllustrate`` behavior (enforced by the window in packaged builds).
* **Policy status (M3)** — business users may illustrate only the premium-pay
  statuses in :data:`PHASE1_ALLOWED_PREMIUM_PAY_STATUSES`; a death-claim-pending
  suspense code is refused too. Suspended policies (suspense code 2) remain
  allowed and get a banner. Developers get a warning instead of a block.
* **Illustrated rate (M2)** — on declared-rate UL, the Illustrated Rate may not
  exceed the policy's current declared rate and may not be blank. Developers
  get a warning instead of a block.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from suiteview.illustration.core.input_context import default_illustrated_rate
from suiteview.illustration.core.rate_loader import load_rates
from suiteview.illustration.core.rate_validation import missing_required_rate_warnings
from suiteview.illustration.models.index_strategies import is_iul_plan
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.polview.models.cl_polrec.policy_translations import (
    PREMIUM_PAY_STATUS_CODES,
    SUSPENSE_CODES,
)
from suiteview.polview.models.policy_sections.lookup import policy_attr

# Phase-1 in-force illustration covers these premium-pay statuses
# (PRM_PAY_STA_REA_CD): 22 premium paying, 32/33/34 waiver of premium/charges/
# COI — the statuses the phase-1 testing covered. Every other status (44 ETI,
# 45 RPU, lapsed, matured, surrendered, terminated, ...) is refused for business
# users. Edit this set to widen or narrow the scope.
PHASE1_ALLOWED_PREMIUM_PAY_STATUSES = frozenset({"22", "32", "33", "34"})

# Suspense codes (LH_BAS_POL.SUS_CD) refused regardless of premium-pay status.
# "2" (Suspended) is allowed with a banner.
REFUSED_SUSPENSE_CODES = frozenset({"3"})

_STATUS_LABELS = {
    **PREMIUM_PAY_STATUS_CODES,
    "44": "Extended Term",
    "45": "Reduced Paid-Up",
}

_ALLOWLIST_PATH = (
    Path(__file__).resolve().parent.parent / "plancodes" / "phase1_allowlist.json")

# Half a displayed digit (the field shows 3 decimals of a percent): a rate the
# field rounds to the declared rate is not "above" it.
_RATE_TOLERANCE = 0.000005

GATE_TITLE = "Not Available for Illustration"


@dataclass(frozen=True)
class GateResult:
    """Refusals (business users can't proceed) and warnings (they can)."""

    blocks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def blocked(self) -> bool:
        return bool(self.blocks)

    def __add__(self, other: "GateResult") -> "GateResult":
        return GateResult(self.blocks + other.blocks, self.warnings + other.warnings)


@lru_cache(maxsize=1)
def phase1_plancodes() -> frozenset[str]:
    """The shipped phase-1 plancode allow-list."""
    data = json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return frozenset(str(code).strip().upper() for code in data["plancodes"])


def _plancode(policy) -> str:
    return str(policy_attr(policy, "base_plancode", "")
               or getattr(policy, "plancode", "") or "").strip().upper()


def plancode_refusal(plancode: str) -> str | None:
    """Why a business user can't illustrate *plancode*, or None when allowed."""
    plancode = (plancode or "").strip().upper()
    if plancode in phase1_plancodes():
        return None
    return (f"Plancode {plancode or '(blank)'} is not supported for in-force "
            "illustration in this release.")


def status_refusal(policy) -> str | None:
    """Why the policy's status is out of phase-1 scope, or None when allowed."""
    suspense = str(policy_attr(policy, "suspense_code", "") or "").strip()
    if suspense in REFUSED_SUSPENSE_CODES:
        return (f"Policy suspense status {suspense} "
                f"({SUSPENSE_CODES.get(suspense, 'Unknown')}) is not supported for "
                "in-force illustration in this release.")
    status = str(policy_attr(policy, "premium_pay_status_code", "") or "").strip()
    if status in PHASE1_ALLOWED_PREMIUM_PAY_STATUSES:
        return None
    label = _STATUS_LABELS.get(status, "Unknown") if status else "Not Recorded"
    return (f"Policy status {status or '(blank)'} ({label}) is not supported for "
            "in-force illustration in this release.")


def illustrated_rate_cap(policy) -> float | None:
    """The highest Illustrated Rate allowed (decimal), or None when not capped.

    Declared-rate UL only: the current declared rate the policy loaded with
    (``default_illustrated_rate`` — the declared rate, or the plan GINT when no
    declared rate is loaded). IUL rates are a read-only blend and ISWL is
    outside the phase-1 scope.
    """
    plancode = _plancode(policy)
    if not plancode or is_iul_plan(plancode):
        return None
    try:
        if load_plancode(plancode).is_iswl:
            return None
        return default_illustrated_rate(policy)
    except Exception:
        return None


def _pct(rate: float) -> str:
    return f"{rate * 100.0:.3f}%"


def rate_gate(policy, inforce_overrides, *, business_mode: bool) -> GateResult:
    """Cap the Illustrated Rate at the current declared rate; refuse blank (M2)."""
    if inforce_overrides is None:
        return GateResult()
    cap = illustrated_rate_cap(policy)
    if cap is None:
        return GateResult()
    rate = inforce_overrides.current_interest_rate
    if rate is None:
        if business_mode:
            return GateResult(blocks=(
                "Enter an Illustrated Rate — it can't be blank. The current "
                f"declared rate is {_pct(cap)}.",))
        return GateResult()
    if rate <= cap + _RATE_TOLERANCE:
        return GateResult()
    message = (f"The Illustrated Rate {_pct(rate)} is above the current declared "
               f"rate {_pct(cap)}. Illustrated rates can't exceed the current rate.")
    if business_mode:
        return GateResult(blocks=(message,))
    return GateResult(warnings=(message + " (Developer run: allowed.)",))


def policy_gate(policy, *, business_mode: bool) -> GateResult:
    """Plancode allow-list (M5) and policy status (M3) for a loaded policy."""
    if business_mode:
        blocks = tuple(
            reason for reason in (plancode_refusal(_plancode(policy)), status_refusal(policy))
            if reason)
        return GateResult(blocks=blocks)
    status = status_refusal(policy)
    if status:
        return GateResult(warnings=(
            status + " Business users are blocked; developer run allowed.",))
    return GateResult()


def run_gate(policy, inforce_overrides, *, business_mode: bool) -> GateResult:
    """Everything a run checks: policy scope plus the Illustrated Rate."""
    return (policy_gate(policy, business_mode=business_mode)
            + rate_gate(policy, inforce_overrides, business_mode=business_mode))


# Monthly-deduction check (should-do 4): SuiteView's recalculated valuation-month
# deduction vs CyberLife's. A difference above this shows a prominent warning
# banner (Inputs tab and the run notice); it never blocks a run.
MD_MISMATCH_TOLERANCE = 0.01


def monthly_deduction_mismatch_notice(md_check) -> str:
    """Banner text when |calculated - CyberLife| > $0.01, else ""."""
    cyberlife = float(getattr(md_check, "system_monthly_deduction", 0.0) or 0.0)
    calculated = float(getattr(md_check, "md_check_calculated_deduction", 0.0) or 0.0)
    difference = calculated - cyberlife
    if abs(difference) <= MD_MISMATCH_TOLERANCE + 1e-9:
        return ""
    return (
        "MONTHLY DEDUCTION CHECK: SuiteView calculates the current monthly deduction "
        f"as ${calculated:,.2f}; CyberLife shows ${cyberlife:,.2f} (difference "
        f"${difference:,.2f}). Review the illustration with care — its values may "
        "not match the policy's administration.")


# Missing illustration rates (should-do 4): business users can't run a policy
# whose active riders/benefits have no rates (e.g. riders 06582004/06582016,
# which have none by design) — the engine would silently omit those charges.
# Checked on every run path (Run, Compare, saved/imported cases), not only at load.

def missing_rate_findings(policy) -> tuple[str, ...]:
    """Load the policy's illustration rates and report what is missing.

    An exception while loading rates is itself a finding (the run can't be trusted)."""
    try:
        rates = load_rates(policy, load_plancode(_plancode(policy)))
    except Exception as exc:
        return (f"Unable to load illustration data/rates: {exc}",)
    return tuple(missing_required_rate_warnings(policy, rates))


def missing_rates_block(findings) -> str:
    """The one refusal text every path shows for missing rates."""
    return ("This policy can't be illustrated in this release: illustration rates "
            f"are missing. {' '.join(findings)}")


def rate_presence_gate(policy, *, business_mode: bool, findings_for=None) -> GateResult:
    """Business users: refuse a run when illustration rates are missing.

    Developers get the load-time warning only (no extra rate load per run)."""
    if not business_mode:
        return GateResult()
    findings = (findings_for or missing_rate_findings)(policy)
    return GateResult(blocks=(missing_rates_block(findings),)) if findings else GateResult()
