"""Start a UL illustration from a reinstatement of a lapsed policy.

The projection starts on the reinstatement date (its valuation date) and the
first projected month is the next monthliversary (its forecast date). The
starting basis is the lapse values restored on the reinstatement date:

* **Account value** - the account value at lapse is injected *before* the
  reinstatement-date monthly deduction; that deduction is calculated on the
  reinstated basis and removed. The engine treats a valuation-date account value
  as post-deduction (``account_value + system_monthly_deduction`` is the AV the
  deduction was taken on), so the basis records ``account_value = lapse AV - MD``
  and ``system_monthly_deduction = MD``; its monthly-deduction check reconciles.
* **Loans** - reinstated with their accrued interest added to the principal when
  a policy anniversary falls after the lapse values date and on or before the
  reinstatement date; otherwise the accrued interest is reinstated as is.
* **CCV** - every shadow-account (CCV, benefit type ``A``) benefit is terminated
  as of the lapse date and the shadow account value is zero.
* **MAP / safety net** - stays terminated: it ceases no later than the lapse date.

Durations run from the original issue date (continuous coverage). The
reinstatement premium is not part of this basis; the caller applies it as the
forecast-date lump sum. Pure: no database or Qt access.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.calc_engine import _completed_months, cvat_corridor_rate
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.target_premium import floor_monthly_cent, truncate_monthly_mtp
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData

CCV_BENEFIT_TYPE = "A"
# A reinstated policy is premium paying again (PRM_PAY_STA_REA_CD 22).
REINSTATED_PREMIUM_PAY_STATUS = "22"
GLP_ACCUMULATION_STOP_AGE = 100
PREMIUMS_AFTER_VALUATION_NOT_APPLICABLE = (
    "Not applicable to a reinstatement illustration: the reinstatement premium is the "
    "forecast-date lump sum.")


class ReinstatementStartError(ValueError):
    """The lapse values cannot be restored on the requested reinstatement date."""


@dataclass(frozen=True)
class ReinstatementStart:
    """A projectable reinstated basis and the amounts used to build it."""

    policy: IllustrationPolicyData
    lapse_date: date
    lapse_values_date: date | None
    reinstatement_date: date
    forecast_date: date
    account_value_before_deduction: float
    monthly_deduction: float
    anniversaries_crossed: int
    loan_interest_capitalized: float
    ccv_terminated: bool

    @property
    def account_value(self) -> float:
        return self.policy.account_value


def monthliversary_on_or_before(issue_date: date, when: date) -> date:
    """The issue-day-anchored monthliversary on or before ``when``."""
    return issue_date + relativedelta(months=_completed_months(issue_date, when))


def build_reinstated_policy(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    *,
    lapse_date: date,
    reinstatement_date: date,
    cvat=None,
) -> ReinstatementStart:
    """Restore ``policy``'s lapse values on ``reinstatement_date`` (a monthliversary).

    ``policy`` is the lapse basis with its lapse-terminated coverages and benefits
    already restored (``ReinstatementBasis.policy``); it is never mutated.
    ``cvat`` is the engine's CVAT corridor tracker for a CVAT policy.
    """
    issue = policy.issue_date
    values_date = policy.valuation_date
    when = reinstatement_date
    if issue is None:
        raise ReinstatementStartError("The policy issue date is not available.")
    if when < lapse_date:
        raise ReinstatementStartError(
            f"The reinstatement date {when:%m/%d/%Y} is before the lapse date "
            f"{lapse_date:%m/%d/%Y}.")
    if monthliversary_on_or_before(issue, when) != when:
        raise ReinstatementStartError(
            f"The reinstatement date {when:%m/%d/%Y} is not a monthliversary; the "
            "illustration must start on a monthliversary.")
    maturity = issue + relativedelta(years=policy.maturity_age - policy.issue_age)
    if when >= maturity:
        raise ReinstatementStartError(
            f"The reinstatement date {when:%m/%d/%Y} is at or after maturity "
            f"({maturity:%m/%d/%Y}).")

    reinstated = deepcopy(policy)
    completed = _completed_months(issue, when)
    year = completed // 12 + 1
    crossed = max(year - policy.policy_year, 0)
    lapse_av = float(policy.account_value)
    notes = [
        f"REINSTATEMENT: lapsed {lapse_date:%m/%d/%Y}; reinstated {when:%m/%d/%Y}. "
        "Lapse values restored on the reinstatement date with durations from the "
        "original issue date (continuous coverage)."
    ]

    reinstated.valuation_date = when
    reinstated.reinstatement_date = when
    reinstated.policy_year = year
    reinstated.policy_month = completed % 12 + 1
    reinstated.duration = completed + 1
    reinstated.attained_age = policy.attained_age + crossed
    reinstated.premium_pay_status_code = REINSTATED_PREMIUM_PAY_STATUS
    reinstated.rollback_snapshots = []
    reinstated.premiums_after_valuation = []
    reinstated.premiums_after_valuation_error = PREMIUMS_AFTER_VALUATION_NOT_APPLICABLE
    if crossed:
        reinstated.premiums_ytd = 0.0
        reinstated.accumulated_glp = _accumulated_glp(policy, crossed)

    capitalized = _reinstate_loans(reinstated, capitalize=bool(crossed))
    notes.append(
        f"Loans reinstated; ${capitalized:,.2f} of accrued interest added to the principal "
        "(a policy anniversary was crossed)." if crossed else
        "Loans and their accrued interest reinstated as of the lapse.")
    ccv_terminated = _terminate_ccv(reinstated, lapse_date)
    if ccv_terminated:
        notes.append(f"CCV benefit terminated as of the lapse date {lapse_date:%m/%d/%Y}.")
    if reinstated.map_cease_date is None or reinstated.map_cease_date > lapse_date:
        reinstated.map_cease_date = lapse_date
    notes.append(f"MAP (safety net) period remains terminated as of {lapse_date:%m/%d/%Y}.")

    deduction = calculate_deduction(
        lapse_av, reinstated, config, rates, reinstated.policy_year,
        reinstated.attained_age, reinstated.premiums_paid_to_date,
        monthly_mtp=truncate_monthly_mtp(reinstated.mtp), projection_date=when,
        bln_round_charge=True, corridor_rate=cvat_corridor_rate(cvat, when),
    )
    md = round(float(deduction.total_deduction), 2)
    expense = round(float(deduction.epu_charge + deduction.mfee_charge + deduction.av_charge), 2)
    coi = round(float(deduction.coi_charge + deduction.rider_charges), 2)
    reinstated.account_value = round(lapse_av - md, 2)
    reinstated.system_monthly_deduction = md
    reinstated.system_coi_charge = coi
    reinstated.system_expense_charge = expense
    reinstated.system_other_charge = round(md - coi - expense, 2)
    _rescale_funds(reinstated, lapse_av)
    notes.append(
        f"Account value at lapse ${lapse_av:,.2f} injected before the "
        f"{when:%m/%d/%Y} monthly deduction of ${md:,.2f}; starting account value "
        f"${reinstated.account_value:,.2f}.")
    if crossed:
        notes.append(
            f"{crossed} policy anniversar{'y' if crossed == 1 else 'ies'} crossed while "
            "lapsed: premiums YTD reset; accumulated GLP includes each anniversary's GLP.")
    reinstated.starting_basis_assumptions = [*reinstated.starting_basis_assumptions, *notes]
    return ReinstatementStart(
        policy=reinstated,
        lapse_date=lapse_date,
        lapse_values_date=values_date,
        reinstatement_date=when,
        forecast_date=issue + relativedelta(months=completed + 1),
        account_value_before_deduction=lapse_av,
        monthly_deduction=md,
        anniversaries_crossed=crossed,
        loan_interest_capitalized=capitalized,
        ccv_terminated=ccv_terminated,
    )


def _accumulated_glp(policy: IllustrationPolicyData, crossed: int) -> float:
    """AccumGLP plus one floored GLP per anniversary crossed (none from age 100)."""
    total = policy.accumulated_glp
    glp = floor_monthly_cent(policy.glp)
    for offset in range(1, crossed + 1):
        if policy.attained_age + offset < GLP_ACCUMULATION_STOP_AGE:
            total += glp
    return total


def _reinstate_loans(policy: IllustrationPolicyData, *, capitalize: bool) -> float:
    """Capitalize accrued loan interest after an anniversary; returns the amount added."""
    if not capitalize:
        return 0.0
    fixed_before = policy.regular_loan_principal + policy.preferred_loan_principal
    added = 0.0
    for kind in ("regular", "preferred", "variable"):
        accrued = float(getattr(policy, f"{kind}_loan_accrued") or 0.0)
        setattr(policy, f"{kind}_loan_principal",
                round(float(getattr(policy, f"{kind}_loan_principal") or 0.0) + accrued, 2))
        setattr(policy, f"{kind}_loan_accrued", 0.0)
        added += accrued
    fixed_after = policy.regular_loan_principal + policy.preferred_loan_principal
    if policy.impaired_fund_values and fixed_before > 0:
        factor = fixed_after / fixed_before
        policy.impaired_fund_values = {
            fund: round(value * factor, 2) for fund, value in policy.impaired_fund_values.items()}
    return round(added, 2)


def _terminate_ccv(policy: IllustrationPolicyData, lapse_date: date) -> bool:
    """End every CCV benefit at the lapse date; True when the policy had one."""
    found = False
    for index, benefit in enumerate(policy.benefits):
        if (benefit.benefit_type or "").strip() != CCV_BENEFIT_TYPE:
            continue
        found = True
        policy.benefits[index] = replace(
            benefit, is_active=False,
            cease_date=min(benefit.cease_date or lapse_date, lapse_date),
            pay_up_date=min(benefit.pay_up_date or lapse_date, lapse_date))
    if found or policy.ccv_active:
        policy.ccv_active = False
        policy.ccv_ceased = True
        policy.shadow_account_value = 0.0
        return True
    return False


def _rescale_funds(policy: IllustrationPolicyData, lapse_av: float) -> None:
    """Keep the fund split of the lapse account value; open index segments end."""
    policy.fund_segments = []
    if not policy.fund_values:
        return
    total = sum(policy.fund_values.values())
    target = max(policy.account_value, 0.0)
    if total <= 0 or lapse_av <= 0:
        policy.fund_values = {fund: 0.0 for fund in policy.fund_values}
        return
    factor = target / total
    policy.fund_values = {fund: round(value * factor, 2) for fund, value in policy.fund_values.items()}
