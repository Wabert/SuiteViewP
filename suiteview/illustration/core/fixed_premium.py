"""Fixed-premium traditional plans: shared schema ``rates`` lookups and mode factors.

Par whole life (``core/parwl``) and indeterminate premium term (``core/term``) both
bill fixed premiums from per-unit annual rates modalized by the plan's ``RATE_MODEFACT``
rows. This module holds what they share: the plan row, the coverage's rate band, a
rate window's values and the mode factors for a bill form (UL_Rates schema ``rates``
only, never the dbo rate tables).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional, Tuple

from suiteview.core.modal_premium import BILL_FORM_FACTOR_FAMILY
from suiteview.core.rates_schema import PlanDef
from suiteview.illustration.core.schema_reader import SchemaReader
from suiteview.polview.models.schema_rates import band_for_amount, resolve_plan

# Bill form -> RATE_MODEFACT billing form. Bill forms H and F bill at the PAC factors and
# fee (H: E0017485, 14750097, 13476873 and 14334488; F: 8L1F1500 13662970, 14.691 x 0.47
# + 3.50 = 10.40, reproduce to the cent); other forms are not mapped and fall back to the
# plan's "*" factors or the billed premium.
BILL_FORM_FAMILY = {**BILL_FORM_FACTOR_FAMILY, "H": "PAC", "F": "PAC"}
MODES_BY_FREQUENCY = {12: "A", 6: "S", 3: "Q", 1: "M"}
# POLICY_FEE_RULE Z adds the annual fee to the annual premium and rounds the modal premium once.
FEE_IN_ANNUAL_PREMIUM = "Z"


def cents(value) -> float:
    """Round half up to cents, as CyberLife does (Decimal of the float's repr)."""
    return float(Decimal(repr(float(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class ModeFactors:
    """Premium and policy-fee factors for the policy's billing form and mode.

    ``multiply_order`` (RATE_MODEFACT MULTIPLY_ORDER, CyberDoc D10 calculation rules):
    ``1`` modalizes the annual premium (``round(units x rate x factor, 2)``, B711E100,
    B111A100); ``2`` modalizes the rate per unit first (``round(units x round(rate x
    factor, 2), 2)``: 8L1F1500 13476873 0.71 x 10, 8O1C1000 12864500 0.76 x 60, B15TG100
    D0194819 100 x round(23.36 x 0.08333, 2) + 7.00 = 202.00).
    ``policy_fee_rule`` (POLICY_FEE_RULE): ``Z`` adds the annual fee to the annual premium
    before one rounding (``parwl.premiums.modal_premium``)."""

    billing_form: str
    mode: str
    prem_factor: float
    fee_factor: float
    policy_fee_annual: float
    fee_add: str
    multiply_order: str = "1"
    policy_fee_rule: str = ""


def resolve_rate_plan(reader: SchemaReader, plancode: str, company: str, error=ValueError) -> Tuple[PlanDef, str]:
    """The plancode's PLAN_DEF row for the policy's company; ``error`` names the missing plan."""
    plan, note = resolve_plan(reader.plan_defs(plancode), company)
    if plan is None:
        detail = f" ({note})" if note else ""
        raise error(f"Plancode {plancode} is not loaded in UL_Rates schema rates{detail}.")
    return plan, note


def coverage_band(reader: SchemaReader, plan: PlanDef, band_code: str, issue_date: date, face_amount: float) -> str:
    """The schema band for a coverage: its stored rate band when the plan maps it, else by face."""
    bands = reader.plan_bands(plan.company, plan.plancode)
    if not bands:
        return "0"
    if band_code:
        rows = [b for b in bands if b.source_band == band_code and b.issue_date_from <= issue_date]
        if rows:
            return max(rows, key=lambda b: b.issue_date_from).band
    spec, _note = band_for_amount(bands, issue_date, face_amount)
    return spec.band if spec is not None else "0"


def window_values(reader: SchemaReader, assignment, scale: str, on: date, issue_age: Optional[int]) -> Tuple[str, dict]:
    """(grain, values) of the ``scale`` window in effect on ``on`` for ``issue_age``."""
    windows = [w for w in reader.schedule_windows(assignment.schedule_id) if w.scale == scale]
    window = next((w for w in windows if w.covers(on)), None)
    if window is None:
        return "", {}
    sets = reader.rate_sets((window.rate_set_id,))
    info = sets.get(window.rate_set_id)
    values = reader.rate_values((window.rate_set_id,), issue_age).get(window.rate_set_id, {})
    return (info.grain if info else ""), values


def plan_mode_factors(reader: SchemaReader, plan: PlanDef, bill_form: str, units: float,
                      notes: List[str]) -> Tuple[ModeFactors, ...]:
    """Mode factors for a bill form. The ``FEE_AMOUNT_FROM/TO`` bands select the policy fee
    by base units (face / 1,000): B711E100 charges 60.00 below 1,000 units and none above
    (reproduces CyberLife's billed premiums, e.g. 14781972, E0050777)."""
    rows = reader.modal_factors(plan.company, plan.plancode)
    if not rows:
        notes.append(f"{plan.plancode} has no RATE_MODEFACT rows; the billed premium is used as is.")
        return ()
    family = BILL_FORM_FAMILY.get(str(bill_form or "").strip().upper(), "")
    forms = {m.billing_form for m in rows}
    form = family if family in forms else ("*" if "*" in forms else "")
    if not form:
        notes.append(f"{plan.plancode} mode factors have no billing form for bill form {bill_form}.")
        return ()
    chosen = []
    for mode in ("A", "S", "Q", "M"):
        candidates = [m for m in rows if m.billing_form == form and m.mode == mode
                      and float(m.fee_amount_from) <= units
                      and (m.fee_amount_to is None or float(m.fee_amount_to) == 0
                           or units <= float(m.fee_amount_to))]
        if candidates:
            m = candidates[0]
            chosen.append(ModeFactors(form, mode, float(m.prem_factor), float(m.fee_factor),
                                      float(m.policy_fee_annual), str(m.policy_fee_add).strip(),
                                      str(m.multiply_order or "1").strip() or "1",
                                      str(m.policy_fee_rule or "").strip().upper()))
    return tuple(chosen)
