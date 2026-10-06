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
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

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
    """Everything a run checks for *policy* and its inforce overrides."""
    return policy_gate(policy, business_mode=business_mode)
