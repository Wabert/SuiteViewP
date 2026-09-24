"""CyberLife fixed-premium modal premiums from ``RATE_MODEFACT`` factors.

Modal premium = round(annual premium x mode factor, 2)
              + round(annual policy fee x fee factor, 2)

verified against system-calculated in-force premiums for mode premium table
00-048 (plancode 81335200) on direct (bill form 0) and PAC (bill form G) bills
in every mode. Only that verified rule combination is calculated; any other
bill form, rule code or collection fee fails with an explanation rather than
producing a plausible but unverified number.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Mapping, Optional

CENT = Decimal("0.01")

# CKUDT323 billing-form entry D (direct notice) supplies DIR*, O (PAC) PAC*.
BILL_FORM_FACTOR_FAMILY = {"0": "DIR", "G": "PAC"}
BILL_FORM_LABELS = {"DIR": "Direct notice", "PAC": "PAC"}

MODE_BY_FREQUENCY = {12: "A", 6: "S", 3: "Q", 1: "M"}
MODE_LABELS = {"A": "Annual", "S": "Semi-Annual", "Q": "Quarterly", "M": "Monthly"}

# CyberDoc D20 POLICY-FEE-ADD: modes the policy fee is added to.
POLICY_FEE_ADD_MODES = {
    "0": frozenset(), "9": frozenset(), "1": frozenset("M"), "2": frozenset("MQ"),
    "3": frozenset("SQM"), "4": frozenset("ASQM"),
}
POLICY_FEE_ADD_LABELS = {
    "0": "Not added", "9": "Not added", "1": "Monthly only", "2": "Monthly and quarterly",
    "3": "All modes but annual", "4": "All modes",
}

# The rule codes whose results were reproduced from in-force premiums.
VERIFIED_RULES = {
    "POLICY_FEE_RULE": "3", "MULTIPLY_ORDER": "1", "RATING_ORDER": "1", "ROUNDING_RULE": "1",
}


class ModalPremiumError(ValueError):
    """A modal premium cannot be calculated from verified rules."""


@dataclass(frozen=True)
class ModalPremium:
    family: str
    mode: str
    annual_premium: Decimal
    factor: Decimal
    premium: Decimal
    policy_fee: Decimal
    fee_factor: Decimal
    fee: Decimal

    @property
    def total(self) -> Decimal:
        return self.premium + self.fee


def billing_mode(frequency: int, non_standard_mode: str = "") -> str:
    """A/S/Q/M from PMT_FQY_PER. Non-standard modes (bi-weekly etc.) bill a
    monthly premium through the premium depositor fund, so they are monthly."""
    if str(non_standard_mode or "").strip():
        return "M"
    try:
        return MODE_BY_FREQUENCY[int(frequency)]
    except (KeyError, TypeError, ValueError):
        raise ModalPremiumError(f"Payment frequency {frequency!r} has no mode factor.") from None


def factor_family(bill_form: str) -> str:
    form = str(bill_form or "").strip().upper()
    try:
        return BILL_FORM_FACTOR_FAMILY[form]
    except KeyError:
        raise ModalPremiumError(
            f"Bill form {form or '(blank)'} has no verified mode factor mapping (only 0=DIR, G=PAC)."
        ) from None


def unverified_rules(factors: Mapping) -> list[str]:
    problems = [
        f"{key}={factors.get(key)!r}" for key, value in VERIFIED_RULES.items()
        if str(factors.get(key) or "").strip() != value
    ]
    if Decimal(str(factors.get("COLLECTION_FEE") or 0)) != 0:
        problems.append(f"COLLECTION_FEE={factors.get('COLLECTION_FEE')}")
    if str(factors.get("POLICY_FEE_ADD") or "").strip() not in POLICY_FEE_ADD_MODES:
        problems.append(f"POLICY_FEE_ADD={factors.get('POLICY_FEE_ADD')!r}")
    return problems


def calculate_modal_premium(
    annual_premium: Decimal, factors: Mapping, bill_form: str, mode: str,
) -> ModalPremium:
    """Modal premium for a RATE_MODEFACT row, bill form and A/S/Q/M mode."""
    problems = unverified_rules(factors)
    if problems:
        raise ModalPremiumError("Unverified mode premium rules: " + ", ".join(problems))
    family = factor_family(bill_form)
    if mode not in MODE_LABELS:
        raise ModalPremiumError(f"Unknown mode {mode!r}.")
    if mode == "A":
        factor = fee_factor = Decimal("1")
    else:
        factor = Decimal(str(factors[f"{family}{mode}"]))
        fee_factor = Decimal(str(factors[f"{family}{mode}_FEE"]))
    annual_premium = Decimal(str(annual_premium))
    policy_fee = Decimal(str(factors["POLICY_FEE"]))
    if mode not in POLICY_FEE_ADD_MODES[str(factors["POLICY_FEE_ADD"]).strip()]:
        policy_fee = Decimal("0")
    return ModalPremium(
        family=family, mode=mode, annual_premium=annual_premium, factor=factor,
        premium=(annual_premium * factor).quantize(CENT, rounding=ROUND_HALF_UP),
        policy_fee=policy_fee, fee_factor=fee_factor,
        fee=(policy_fee * fee_factor).quantize(CENT, rounding=ROUND_HALF_UP),
    )


def describe_bill_form(bill_form: str) -> str:
    form = str(bill_form or "").strip().upper()
    family = BILL_FORM_FACTOR_FAMILY.get(form)
    return f"{form} ({family} - {BILL_FORM_LABELS[family]})" if family else f"{form or '(blank)'} (no verified factors)"


def fee_label(code: Optional[str]) -> str:
    code = str(code or "").strip()
    return f"{code} ({POLICY_FEE_ADD_LABELS.get(code, 'Unknown')})"
