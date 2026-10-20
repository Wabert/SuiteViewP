"""Partial surrender charge on a face decrease must be covered by the surrender value.

A requested specified-amount decrease, or the face reduction of a DB option A->B
change, assesses a partial surrender charge (PSC) on the decreased units. The
administration system will not process the decrease when the policy's surrender
value at the change date cannot cover that charge. The engine still projects
the change (so the Values tab shows what would happen), but records the
shortfall on the month's face/DBO change detail; the Run Values flow then
refuses to build the illustration report and explains why.

The surrender value tested is the one at the point of the change, before it is
applied: account value after any same-month withdrawal, less the full surrender
charge on the pre-change units, less policy debt. Withdrawal face reductions
keep their own limit (``withdrawal_handler`` max net withdrawal) and are not
tested here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional

# Face / DBO change detail keys set on a month a decrease assesses a PSC.
PSC_EXCEEDS_SV_KEY = "PSC Exceeds SV"
SV_BEFORE_CHANGE_KEY = "SV Before Change"
AV_BEFORE_CHANGE_KEY = "AV Before Change"
SC_BEFORE_CHANGE_KEY = "SC Before Change"
DEBT_BEFORE_CHANGE_KEY = "Debt Before Change"

FACE_PSC_KEY = "Total PSC Spec Dec"
DBO_PSC_KEY = "Total PSC DBO"

BLOCKED_TITLE = "Face Decrease Not Allowed"

_EPS = 0.005


@dataclass(frozen=True)
class UncoveredDecreaseCharge:
    """One face decrease whose partial surrender charge exceeds the surrender value."""

    change_date: Optional[date]
    description: str
    decrease: float
    partial_surrender_charge: float
    surrender_value: float
    account_value: float
    surrender_charge: float
    policy_debt: float


def record_charge_coverage(
    detail: dict, psc_key: str, *, account_value: float,
    surrender_charge: float, policy_debt: float,
) -> None:
    """Record the pre-change surrender value on a detail dict that assessed a PSC.

    Months without a partial surrender charge are left untouched.
    """
    psc = float(detail.get(psc_key) or 0.0)
    if psc <= _EPS:
        return
    surrender_value = account_value - surrender_charge - policy_debt
    detail[AV_BEFORE_CHANGE_KEY] = float(account_value)
    detail[SC_BEFORE_CHANGE_KEY] = float(surrender_charge)
    detail[DEBT_BEFORE_CHANGE_KEY] = float(policy_debt)
    detail[SV_BEFORE_CHANGE_KEY] = float(surrender_value)
    detail[PSC_EXCEEDS_SV_KEY] = psc > surrender_value + _EPS


def uncovered_decrease_charges(states: Iterable) -> List[UncoveredDecreaseCharge]:
    """Every projected face decrease whose PSC the surrender value cannot cover."""
    found: List[UncoveredDecreaseCharge] = []
    for state in states or ():
        for attr, psc_key, decrease_key, description in (
            ("dbo_change_detail", DBO_PSC_KEY, "DBO Face Decrease",
             "death benefit option A to B change"),
            ("face_change_detail", FACE_PSC_KEY, "Specified Face Decrease",
             "specified face decrease"),
        ):
            detail = getattr(state, attr, None) or {}
            if not detail.get(PSC_EXCEEDS_SV_KEY):
                continue
            found.append(UncoveredDecreaseCharge(
                change_date=getattr(state, "date", None),
                description=description,
                decrease=float(detail.get(decrease_key) or 0.0),
                partial_surrender_charge=float(detail.get(psc_key) or 0.0),
                surrender_value=float(detail[SV_BEFORE_CHANGE_KEY]),
                account_value=float(detail[AV_BEFORE_CHANGE_KEY]),
                surrender_charge=float(detail[SC_BEFORE_CHANGE_KEY]),
                policy_debt=float(detail[DEBT_BEFORE_CHANGE_KEY]),
            ))
    return found


def _money(value: float) -> str:
    return f"-${-value:,.2f}" if value < 0 else f"${value:,.2f}"


def uncovered_decrease_charge_message(findings: List[UncoveredDecreaseCharge]) -> str:
    """User-facing explanation of why the illustration report was not generated."""
    paragraphs = ["The illustration report was not generated."]
    for item in findings:
        stamp = item.change_date.strftime("%m/%d/%Y") if item.change_date else "the change date"
        paragraphs.append(
            f"The {item.description} effective {stamp} reduces the specified amount by "
            f"{_money(item.decrease)} and assesses a partial surrender charge of "
            f"{_money(item.partial_surrender_charge)}, but the surrender value at that date is "
            f"only {_money(item.surrender_value)} (account value "
            f"{_money(item.account_value)} less surrender charge "
            f"{_money(item.surrender_charge)} less policy debt {_money(item.policy_debt)}).")
    paragraphs.append(
        "The administration system will not process a face decrease when the surrender "
        "value cannot cover its partial surrender charge, even if a no-lapse guarantee "
        "would keep the policy in force. Reduce the decrease, fund the policy before the "
        "change (or check \"Apply premium needed to cover policy change surrender "
        "charge\"), or move the change to a later date.")
    return "\n\n".join(paragraphs)
