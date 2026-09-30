"""Hover-tip text explaining the Targets & Accumulators tab's calculated values.

Pure functions returning plain text (one step per line) that ends in the
displayed result, so a hover — or "Copy Tip Contents" — shows the working.
"""

from __future__ import annotations

from ..formatting import format_currency


def _money(value) -> str:
    return format_currency(value) or "0.00"


def prem_pay_years_tip(inputs: dict) -> str:
    return (
        "Premium paying years left = maturity age (capped at 100) - attained age - 1\n"
        f"{inputs['maturity_age']} - {inputs['attained_age']} - 1"
        f" = {inputs['prem_pay_years']} (not below 0)"
    )


def max_annual_level_qual_prem_tip(inputs: dict, value) -> str:
    years = inputs["prem_pay_years"]
    lines = [
        "Max annual level premium that stays within the guideline:",
        "(Accum GLP at maturity - (Premiums TD - Withdrawals)) / years left",
        f"Accum GLP at maturity = GLP {_money(inputs['glp'])} x {years} yrs"
        f" + Accum GLP {_money(inputs['accum_glp'])} = {_money(inputs['accum_glp_at_maturity'])}",
        f"Premiums TD {_money(inputs['premium_td'])} - Withdrawals {_money(inputs['withdrawals'])}",
    ]
    if years > 0:
        lines.append(f"= {_money(value)}")
    else:
        lines.append("No premium paying years left, so 0.00")
    return "\n".join(lines)


def min_qualifying_glp_tip(inputs: dict, value) -> str:
    years = inputs["prem_pay_years"]
    lines = [
        "Min qualifying GLP = -(Accum GLP - (Premiums TD - Withdrawals)) / years left",
        f"-({_money(inputs['accum_glp'])} - ({_money(inputs['premium_td'])}"
        f" - {_money(inputs['withdrawals'])})) / {years}",
        "Shown only when negative (premiums paid exceed the accumulated GLP).",
    ]
    if value is not None:
        lines.append(f"= {_money(value)}")
    return "\n".join(lines)


def premiums_paid_tip(reg_prem, additional_prem, total) -> str:
    return (
        "Premiums Paid = Reg Prem + Additional Prem\n"
        f"{_money(reg_prem)} + {_money(additional_prem)} = {_money(total)}"
    )


def prem_allowed_gpt_tip(inputs: dict, value) -> str:
    limit = max(inputs["gsp"], inputs["accum_glp"])
    return "\n".join([
        "Premium still allowed by the guideline premium test:",
        "max(GSP, Accum GLP) - Premiums TD + Withdrawals, not below 0",
        f"max({_money(inputs['gsp'])}, {_money(inputs['accum_glp'])}) = {_money(limit)}",
        f"{_money(limit)} - {_money(inputs['premium_td'])} + {_money(inputs['withdrawals'])}"
        f" = {_money(value)}",
    ])


def annual_min_tip(monthly, annual) -> str:
    return f"Annual Min = Monthly Min x 12\n{_money(monthly)} x 12 = {_money(annual)}"


def monthly_min_tip(amounts) -> str:
    amounts = list(amounts)
    lines = ["Monthly Min = sum of MT targets (LH_POL_TARGET.TAR_PRM_AMT, TAR_TYP_CD 'MT')"]
    lines.extend(f"+ {_money(amount)}" for amount in amounts)
    lines.append(f"= {_money(sum(amounts))}")
    return "\n".join(lines)


def _number(value: float) -> str:
    text = f"{value:,.4f}"
    return text.rstrip("0").rstrip(".")


def face_tip(units: float, vpu: float, face: float) -> str:
    return f"Face = units x value per unit\n{_number(units)} x {_number(vpu)} = {_money(face)}"


def rate_target_tip(face: float, rate, target: float, label: str) -> str:
    return (
        f"{label} = Face / 1,000 x (rate / 1,000)\n"
        f"{_money(face)} / 1,000 x {float(rate) / 1000:.3f} = {_money(target)}"
    )


def commission_target_tip(amounts, total) -> str:
    amounts = list(amounts)
    lines = ["Commission Target = sum of CT targets (LH_COM_TARGET.TAR_PRM_AMT, TAR_TYP_CD 'CT')"]
    lines.extend(f"+ {_money(amount)}" for amount in amounts)
    lines.append(f"= {_money(total)}")
    return "\n".join(lines)
