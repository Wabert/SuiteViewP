"""Hover-tip text explaining how the Account Values tab's calculated values are built.

Pure functions: each takes the numbers the tab displays and returns plain text
(one step per line) that ends in the displayed result, so a hover — or the
"Copy Tip Contents" right-click action — shows the working behind the value.
"""

from __future__ import annotations

from typing import Iterable

from ..formatting import format_currency, format_date


def _trim(value: float, decimals: int = 6) -> str:
    """``value`` with up to ``decimals`` places and no trailing zeros."""
    text = f"{value:,.{decimals}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _as_of(value) -> str:
    return f" as of {format_date(value)}" if value else ""


def surrender_charge_tip(surrender) -> str:
    basis = "original" if surrender.original_units_basis else "current"
    lines = [
        f"Surrender Charge{_as_of(surrender.as_of)}",
        "Illustration engine: SCR rate x units, summed over coverages",
        f"(units = {basis} specified amount / 1,000; rate from the plancode's",
        " surrender charge schedule for the coverage year)",
    ]
    lines.extend(
        f"Cov {cov.coverage_phase}: {_trim(cov.rate)} x {_trim(cov.units, 3)} units"
        f" = {format_currency(cov.charge)}"
        for cov in surrender.coverages
    )
    lines.append(f"= {format_currency(surrender.surrender_charge)}")
    return "\n".join(lines)


def surrender_value_tip(surrender) -> str:
    return "\n".join([
        f"Surrender Value{_as_of(surrender.as_of)}",
        f"  Account Value: {format_currency(surrender.account_value)}",
        f"- Surrender Charge: {format_currency(surrender.surrender_charge)}",
        f"- Policy Debt: {format_currency(surrender.policy_debt)}",
        f"= {format_currency(surrender.surrender_value)}",
    ])


def interim_av_tip(interim) -> str:
    lines = [
        f"Interim AV Quote ({interim.quote_date:%m/%d/%Y})",
        "Monthliversary AV rolled forward to the quote date: each later premium's",
        "net amount is added on its effective date, and interest is credited at",
        "the declared rate over exact days (no interest on a negative AV).",
        f"MV AV {interim.valuation_date:%m/%d/%Y}: {format_currency(interim.valuation_account_value)}",
    ]
    lines.extend(
        f"+ Premium {premium.received:%m/%d/%Y}: {format_currency(premium.net)} net"
        f" ({format_currency(premium.gross)} gross)"
        for premium in interim.premiums
    )
    lines.append(f"+ Interest: {format_currency(interim.interest)}")
    lines.append(f"= {format_currency(interim.account_value)}")
    lines.append(f"Valid until the {interim.next_monthliversary:%m/%d/%Y} monthliversary.")
    return "\n".join(lines)


def sum_tip(title: str, source: str, parts: Iterable[tuple[str, float]], total: float,
            empty: str = "No current rows") -> str:
    """``title``/``source`` header, one ``label: amount`` line per part, then the total."""
    lines = [title, source] if source else [title]
    parts = list(parts)
    lines.extend(f"{label}: {format_currency(amount)}" for label, amount in parts)
    if not parts:
        lines.append(empty)
    lines.append(f"= {format_currency(total)}")
    return "\n".join(lines)


def fund_guaranteed_rate_tip(rates) -> str:
    """Per fixed fund/coverage guaranteed crediting rates behind Guar Int Rate."""
    lines = [
        "Guar Int Rate = guaranteed crediting rate of the fixed fund(s)",
        "(LH_COV_FXD_FND_CTL.GUA_FND_ITS_RT; zero-rate funds are not shown",
        " when any fund has a non-zero rate)",
    ]
    lines.extend(
        f"Fund {rate.fund_id or '?'}, Cov {_or_unknown(rate.coverage_phase)}: "
        + (f"{rate.rate:.3f}%" if rate.rate is not None else "blank")
        for rate in rates
    )
    return "\n".join(lines)


def _or_unknown(value) -> str:
    return "?" if value is None else str(value)


def db_discount_rate_tip(rate) -> str:
    return (
        "DB Discount Rate = policy guaranteed interest rate used to discount\n"
        "the death benefit in the NAR calculation\n"
        f"(LH_NON_TRD_POL.POL_GUA_ITS_RT) = {rate:.3f}%"
    )


def sp_prem_cease_age_tip(duration: int, issue_age: int, cease_age: int) -> str:
    return (
        "SP Prem Cease Age = Short Pay Dur + base coverage issue age\n"
        f"{duration} + {issue_age} = {cease_age}"
    )


def guaranteed_cash_value_tip(gcv) -> str:
    """Working behind a ``rates.guaranteed_cash_value()`` payload, per coverage."""
    lines = ["Interpolated from the stored 02-segment CV rates (NSP rates when on "
             "nonforfeiture):",
             "units x (BOY rate x months remaining + EOY rate x months elapsed) / 12"]
    as_of = gcv.get("as_of")
    if as_of:
        lines.append(f"As of {format_date(as_of)}")
    for d in gcv.get("details", []):
        basis = d["basis"] + (f" ({d['nonforfeiture']})" if d["nonforfeiture"] else "")
        lines.append(
            f"Cov {d.get('cov_pha_nbr') or d['cov_index']} {basis}: "
            f"dur {d['duration']} {d['boy_rate']:,.2f} -> "
            f"dur {d['duration'] + 1} {d['eoy_rate']:,.2f}, {d['months']} mo, "
            f"{d['units']:,} units = {d['value']:,.2f}"
        )
    if any(d["basis"] == "NSP" for d in gcv.get("details", [])):
        lines.append("NSP-basis value is not reconciled to a CyberLife nonforfeiture quote.")
    if gcv.get("reason"):
        lines.append(gcv["reason"])
    return "\n".join(lines)


def monthly_deduction_tip(coi, other, expenses, total) -> str:
    return (
        "MD = COI + Other + Expenses\n"
        f"{format_currency(coi) or '0.00'} + {format_currency(other) or '0.00'}"
        f" + {format_currency(expenses) or '0.00'} = {format_currency(total)}"
    )


def policy_month_tip(issue_month: int, mv_month: int, policy_month: int) -> str:
    return (
        "Policy month = months from the issue month to the MV month, + 1\n"
        f"Issue month {issue_month}, MV month {mv_month} -> month {policy_month}"
    )
