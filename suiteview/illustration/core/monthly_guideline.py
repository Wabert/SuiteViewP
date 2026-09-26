"""7702 guideline premiums (GLP / GSP / 7-pay) by MONTHLY accumulated-value solve.

This is the monthly-basis equivalent of the RERUN ``Guideline_Premiums``
calculator. The workbook compresses the same recursion into one row per policy
year (a geometric sum of the constant within-year monthly factors — fast and
compact in a spreadsheet, but hard to follow and limited to a fixed number of
recalc blocks). The code has no such constraints, so this module runs the
recursion month by month, which is exact, legible, and reusable for unlimited
policy-change recalcs.

The math
========

Project a fund forward under GUARANTEED COI, CURRENT expense charges, and the
statutory 7702 interest rate. With monthly factor ``(1+i)^(1/12)`` and the COI
charged on the discounted net amount at risk, one month is:

    AV' = (AV·(1+T_eff) − fixed_charges)·(1+i_m)

    DBO A: T_eff = T            fixed COI part = T·SA / (1+i_m)^(1/12)... (= T·SA/d)
    DBO B: T_eff = T − T/d      fixed COI part = T·SA/d

where T is the monthly guaranteed COI per $1 of specified amount (substandard-
adjusted, flat extras truncated to cents monthly, capped at 83.333/1000 — the
workbook's cap) and d = (1+i)^(1/12) is the one-month NAR discount at the
STATUTORY rate (Guideline_Premiums AW20). Annual premiums are deposited at the
start of premium years net of the excess load, with the target/excess load
difference charged as dollars against the target premium ((TPP−EPP)·CTP — the
"P ≥ target" treatment; the same one the workbook applies to GSP/GLP).

Because the recursion is LINEAR in the premium P, track the fund as
``AV_m = a_m + b_m·P`` and solve the 7702 endowment condition exactly:

    a_end + b_end·P = SA        →        P = (SA − a_end) / b_end

at the lesser of policy maturity age and age 100. No search needed.

Premium patterns (matching the workbook):
  * GSP    — single premium at the calculation date; rate = max(guar, 4%+2%).
  * GLP    — annual premium at each policy anniversary from the calc date to
             maturity (a partial first year gets NO premium — the first one
             lands on the next anniversary); rate = max(guar, 4%).
  * 7-pay  — annual premium at the 7-pay start date and the next six
             anniversaries; rate = max(guar, 4%). The starting account value
             at the 7-pay date offsets the needed premium (CH24 "Starting AV");
             GSP/GLP ignore the existing fund.

Known intent-over-workbook choice: the workbook's 7-pay block nets the TARGET
load while also charging the (TPP−EPP)·CTP dollar term — inconsistent with its
own GSP/GLP blocks (harmless when TPP == EPP, which is why it survived). This
module applies the consistent treatment everywhere: net of EPP + dollar term.

Multiple base coverages are approximated the way the workbook approximates
them: ONE guaranteed-COI stream (the base segment's) applied to the TOTAL
specified amount, with per-segment EPU charges. This is the main case where
the formula and the engine-search routine can diverge.

Charge basis (the 7702 rule, per Robert 2026-07-17, matching the workbook):
  * COI — GUARANTEED (scale 0), zeroed from the premium-cease age on.
  * Interest — max(statutory floor, guaranteed rate).
  * Expenses — ALWAYS CURRENT: policy fee (zero from the contract maturity
    age on), per-unit EPU, premium loads, waiver/GIO benefit charges, and
    rider COI streams (CTR / spouse term — the same current schedules the
    monthly deduction charges). ADB is not a QAB: its charges never load the
    guideline even though the deduction charges them monthly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import List, Optional

from dateutil.relativedelta import relativedelta

from suiteview.core.benefit_rate_rules import benefit_charge_factor
from suiteview.illustration.core.monthly_deduction import (
    _adjusted_coi_rate, target_waiver_charge,
)
from suiteview.illustration.core.rate_loader import IllustrationRates, _safe_rate
from suiteview.illustration.core.target_premium import truncate_monthly_mtp
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    IllustrationPolicyData,
    benefit_rate_keys,
    rider_active_on,
)


SEVEN_PAY_YEARS = 7

# Benefit types whose CURRENT charge streams load the 7702 guideline premium —
# the workbook's Guideline_Premiums charge columns are exactly PWoC (type 3),
# PWoT/stipulated waiver (type 4) and GIO (type 5) plus the rider columns.
# ADB (type 1) is NOT a qualified additional benefit and has no column there;
# its charges never enter the guideline (verified vs RERUN on U0356726).
# TODO: verify the GIO type code ("5") against a live GIO policy.
_GUIDELINE_BENEFIT_TYPES = {"3", "4", "5"}
COI_MONTHLY_CAP = 83.333          # per $1000 per month — Guideline_Premiums T column
DEEMED_MATURITY_AGE = 100         # upper bound on the guideline endowment age
GLP_RATE_FLOOR = 0.04             # s7702_GLP_Rate (pre-2021 contracts)
GSP_RATE_SPREAD = 0.02            # GSP floor = GLP floor + 2%
_POST_2020_EFFECTIVE_DATE = date(2021, 1, 1)


def statutory_guideline_rates(issue_date: Optional[date]) -> tuple[float, float]:
    """Return the statutory GLP/7-pay and GSP floors for an issue date."""
    if issue_date is not None and issue_date >= _POST_2020_EFFECTIVE_DATE:
        return 0.02, 0.04
    return GLP_RATE_FLOOR, GLP_RATE_FLOOR + GSP_RATE_SPREAD


def guideline_maturity_age(
    policy: IllustrationPolicyData, age_limit: int = DEEMED_MATURITY_AGE,
) -> int:
    """Bound guideline endowment by both contract maturity and the age-100 cap."""
    return min(policy.maturity_age, DEEMED_MATURITY_AGE, age_limit)


def _trunc2(value: float) -> float:
    return float(Decimal(f"{value:.12f}").quantize(Decimal("0.01"), rounding=ROUND_DOWN))


@dataclass
class GuidelineMonth:
    """One month of guideline-basis inputs (constant within a policy year)."""

    attained_age: int = 0
    coi_rate: float = 0.0          # T — monthly guaranteed COI per $1 of SA
    fee: float = 0.0               # monthly policy fee ($)
    epu: float = 0.0               # monthly per-unit expense charges ($, all segments)
    benefit_charges: float = 0.0   # monthly benefit charges ($; PW on the MTP basis)
    rider_charges: float = 0.0     # monthly QAB rider charges ($)
    tpp: float = 0.0               # target premium load rate
    epp: float = 0.0               # excess premium load rate
    is_anniversary: bool = False   # True on policy-anniversary months
    # Per-benefit charge breakdown ($ this month), keyed by a display label.
    # Sums to ``benefit_charges``; carried only for the monthly-PV drill-down
    # (the endowment solve uses the ``benefit_charges`` total and ignores this).
    benefit_charge_detail: dict = field(default_factory=dict)


@dataclass
class GuidelineBasis:
    """Everything the endowment solve needs, built from one policy state."""

    months: List[GuidelineMonth] = field(default_factory=list)
    total_sa: float = 0.0
    db_option: str = "A"
    ctp: float = 0.0               # annual commission target premium (for the $-load)
    guaranteed_rate: float = 0.0
    glp_rate_floor: float = GLP_RATE_FLOOR
    gsp_rate_floor: float = GLP_RATE_FLOOR + GSP_RATE_SPREAD


@dataclass
class GuidelineSolveResult:
    glp: float = 0.0
    gsp: float = 0.0
    seven_pay: float = 0.0


def _guideline_start_date(
    policy: IllustrationPolicyData,
    as_of: Optional[date],
    start_year: int,
    months_into_year: int,
) -> Optional[date]:
    if as_of is not None or policy.issue_date is None:
        return as_of
    return policy.issue_date + relativedelta(
        months=(start_year - 1) * 12 + months_into_year
    )


def _guideline_coi_rate(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    policy_year: int,
    age: int,
    month_date: Optional[date],
) -> float:
    base = policy.base_segment
    if age >= config.premium_cease_age:
        raw_coi = 0.0
    else:
        raw_coi = _safe_rate(
            rates.segment_coi.get(base.coverage_phase, rates.coi), policy_year
        )
    adjusted = _adjusted_coi_rate(raw_coi, base, config, month_date)
    return min(adjusted, COI_MONTHLY_CAP) / 1000.0


def _guideline_fee(
    config: PlancodeConfig, rates: IllustrationRates, policy_year: int, age: int
) -> float:
    if age >= config.maturity_age:
        return 0.0
    if config.mfee == "Table":
        return _safe_rate(rates.mfee, policy_year)
    try:
        return float(config.mfee)
    except (TypeError, ValueError):
        return 0.0


def _guideline_epu(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    policy_year: int,
) -> float:
    epu_total = 0.0
    for seg in policy.segments:
        seg_year = max(1, policy_year - _coverage_start_year_offset(policy, seg))
        if config.epu_code == "Table":
            seg_rate = _safe_rate(
                rates.segment_epu.get(seg.coverage_phase, rates.epu), seg_year
            )
        else:
            try:
                seg_rate = float(config.epu_code)
            except (TypeError, ValueError):
                seg_rate = 0.0
        sa_basis = (
            seg.original_face_amount if config.sa_basis == "OriginalSA"
            else seg.face_amount
        )
        epu_total += seg_rate * sa_basis / 1000.0
    return epu_total


def _guideline_benefit_charges(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    policy_year: int,
    month_date: Optional[date],
    active_as_of: Optional[date],
    monthly_mtp: float,
) -> tuple[float, dict]:
    ben_total = 0.0
    detail = {}
    benefit_schedule_keys = benefit_rate_keys(policy.benefits)
    for ben in policy.benefits:
        ben_type = ben.benefit_type or ""
        if not _benefit_counts_for_guideline(policy, ben, ben_type, policy_year, active_as_of):
            continue
        ben_key = benefit_schedule_keys[id(ben)]
        benefit_year = max(1, policy_year - _coverage_start_year_offset(policy, ben))
        rate = _safe_rate(rates.benefit_coi.get(ben_key, []), benefit_year)
        if rate <= 0.0:
            continue
        factor = ben.rating_factor if ben.rating_factor and ben.rating_factor > 0 else 1.0
        gross = rate * factor
        charge_factor = benefit_charge_factor(
            policy.plancode, ben_type + (ben.benefit_subtype or "")
        )
        if ben_type == "3":
            charge = _trunc2(gross * monthly_mtp * charge_factor)
        elif ben_type == "4" and config.pwot_coi_basis in (2, 3):
            _, charge = target_waiver_charge(policy, config, rate, month_date)
        else:
            charge = (ben.units or 0.0) * gross * charge_factor
        ben_total += charge
        detail[_benefit_label(ben_type, ben.benefit_subtype)] = charge
    return ben_total, detail


def _benefit_counts_for_guideline(
    policy: IllustrationPolicyData,
    ben,
    ben_type: str,
    policy_year: int,
    active_as_of: Optional[date],
) -> bool:
    if not ben.is_active or ben_type.startswith("#"):
        return False
    if ben_type not in _GUIDELINE_BENEFIT_TYPES:
        return False
    if ben.pay_up_date is not None and active_as_of is not None and active_as_of >= ben.pay_up_date:
        return False
    cease_year = _benefit_cease_year(policy, ben)
    return not (cease_year is not None and policy_year > cease_year)


def _guideline_rider_charges(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    policy_year: int,
    active_as_of: Optional[date],
) -> float:
    year_date = _policy_year_start(policy, policy_year)
    rider_total = 0.0
    for rider in policy.riders:
        if not rider.is_active:
            continue
        if active_as_of is not None and not rider_active_on(rider, policy, active_as_of):
            continue
        if year_date is not None and not rider_active_on(rider, policy, year_date):
            continue
        rider_year = max(1, policy_year - _coverage_start_year_offset(policy, rider))
        rate = _safe_rate(rates.rider_rates.get(rider.export_key, []), rider_year)
        if rate <= 0.0 and rider.coi_rate is not None:
            rate = float(rider.coi_rate)
        if rate <= 0.0:
            continue
        rider_table = rider.table_rating or 0
        rider_flat = rider.flat_extra or 0.0
        adjusted_rate = (
            rate * (1.0 + config.table_rating_factor * rider_table)
            + _trunc2(rider_flat / 12.0)
        )
        rider_total += (rider.units or 0.0) * adjusted_rate
    return rider_total


def _set_guideline_premium_loads(
    gm: GuidelineMonth,
    config: PlancodeConfig,
    rates: IllustrationRates,
    policy_year: int,
    age: int,
) -> None:
    if age >= config.premium_cease_age:
        return
    if config.premium_load == "Table":
        gm.tpp = _safe_rate(rates.tpp, policy_year)
        gm.epp = _safe_rate(rates.epp, policy_year)
        return
    try:
        gm.tpp = gm.epp = float(config.premium_load)
    except (TypeError, ValueError):
        gm.tpp = gm.epp = 0.0


def build_guideline_basis(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    *,
    attained_age: int,
    as_of: Optional[date] = None,
    months_into_year: int = 0,
    active_as_of: Optional[date] = None,
) -> GuidelineBasis:
    """Build the monthly guideline-basis inputs from the CURRENT policy state.

    ``rates`` must be loaded with the GUARANTEED COI scale (coi_scale=0);
    loads/fees/EPU in that object are already the current scale.
    ``months_into_year`` positions a mid-year calculation date (0 = on an
    anniversary); the first partial year then has ``12 − months_into_year``
    months before the first anniversary.

    ``active_as_of`` gates which benefits exist in the basis AT ALL — the
    workbook's after-change blocks key every active flag off the CHANGE row
    (FR163: IF(vPW_Active@change, ...)), so a 7-pay re-solve from the original
    period start still EXCLUDES a benefit that has since ceased. Defaults to
    ``as_of`` (the solve start).
    """
    issue_age = policy.issue_age
    total_months = max(0, (guideline_maturity_age(policy) - attained_age) * 12 - months_into_year)
    if active_as_of is None:
        active_as_of = as_of

    # Year offset from ISSUE for duration-indexed schedules (COI/loads/fees).
    start_year = max(1, attained_age - issue_age + 1)

    glp_rate_floor, gsp_rate_floor = statutory_guideline_rates(policy.issue_date)
    basis = GuidelineBasis(
        total_sa=policy.total_face,
        db_option=str(policy.db_option or "A").upper(),
        ctp=float(policy.ctp or 0.0),
        guaranteed_rate=float(policy.guaranteed_interest_rate or 0.0),
        glp_rate_floor=glp_rate_floor,
        gsp_rate_floor=gsp_rate_floor,
    )

    monthly_mtp = truncate_monthly_mtp(float(policy.mtp or 0.0))

    month_in_year = months_into_year
    policy_year = start_year
    start_date = _guideline_start_date(policy, as_of, start_year, months_into_year)
    for m in range(total_months):
        if m > 0 and month_in_year == 0:
            policy_year += 1
        age = issue_age + policy_year - 1
        gm = GuidelineMonth(
            attained_age=age,
            is_anniversary=(month_in_year == 0),
        )

        month_date = start_date + relativedelta(months=m) if start_date is not None else None
        gm.coi_rate = _guideline_coi_rate(policy, config, rates, policy_year, age, month_date)
        gm.fee = _guideline_fee(config, rates, policy_year, age)
        gm.epu = _guideline_epu(policy, config, rates, policy_year)
        gm.benefit_charges, gm.benefit_charge_detail = _guideline_benefit_charges(
            policy, config, rates, policy_year, month_date, active_as_of, monthly_mtp
        )
        gm.rider_charges = _guideline_rider_charges(
            policy, config, rates, policy_year, active_as_of
        )
        _set_guideline_premium_loads(gm, config, rates, policy_year, age)

        basis.months.append(gm)
        month_in_year = (month_in_year + 1) % 12

    return basis


def _policy_year_start(policy: IllustrationPolicyData, policy_year: int) -> Optional[date]:
    """Anniversary date that STARTS the given policy year (Feb-29 → Feb-28)."""
    issue = policy.issue_date
    if issue is None:
        return None
    year = issue.year + policy_year - 1
    try:
        return issue.replace(year=year)
    except ValueError:
        return issue.replace(year=year, day=28)


def _coverage_start_year_offset(policy: IllustrationPolicyData, seg) -> int:
    """Policy years elapsed before the segment's coverage started (0 for cov 1)."""
    if seg.issue_date is None or policy.issue_date is None:
        return 0
    years = seg.issue_date.year - policy.issue_date.year
    if (seg.issue_date.month, seg.issue_date.day) < (
        policy.issue_date.month,
        policy.issue_date.day,
    ):
        years -= 1
    return max(0, years)


_BENEFIT_TYPE_LABELS = {
    "3": "PW (Waiver)",       # Premium Waiver — charged on the monthly MTP basis
}


def _benefit_label(ben_type: str, ben_subtype: Optional[str]) -> str:
    """Readable column label for a benefit charge in the monthly-PV drill-down."""
    base = _BENEFIT_TYPE_LABELS.get(ben_type, f"Benefit {ben_type}")
    sub = (ben_subtype or "").strip()
    return f"{base} {sub}".strip() if sub and ben_type not in _BENEFIT_TYPE_LABELS else base


def _benefit_cease_year(policy: IllustrationPolicyData, ben) -> Optional[int]:
    """Last policy year the benefit charges (anniversary-aligned cease date)."""
    cease = getattr(ben, "pay_up_date", None)
    if cease is None or policy.issue_date is None:
        return None
    return max(0, cease.year - policy.issue_date.year)


def solve_endowment_premium(
    basis: GuidelineBasis,
    annual_rate: float,
    premium_months: set[int],
    starting_av: float = 0.0,
    db_option: Optional[str] = None,
) -> float:
    """Premium that endows the fund (AV = SA) at the deemed maturity.

    The fund is linear in the premium P — track AV = a + b·P through the
    monthly recursion and solve a_end + b_end·P = SA exactly.
    ``db_option`` overrides the basis option (the GSP and 7-pay solves are
    always computed on level-DB mechanics).
    """
    if not basis.months:
        return 0.0

    option = (db_option or basis.db_option or "A").upper()
    monthly_factor = (1.0 + annual_rate) ** (1.0 / 12.0)
    i_m = monthly_factor - 1.0
    d_m = monthly_factor          # one-month NAR discount at the statutory rate (AW20)

    a = float(starting_av)
    b = 0.0
    for index, month in enumerate(basis.months):
        if index in premium_months:
            b += 1.0 - month.epp
            a -= (month.tpp - month.epp) * basis.ctp

        t = month.coi_rate
        if option == "B":
            t_eff = t - t / d_m   # DB = SA + AV: the AV part of the NAR shrinks the coefficient
        else:
            t_eff = t
        fixed = (
            t * basis.total_sa / d_m
            + month.fee + month.epu + month.benefit_charges + month.rider_charges
        )
        a = (a * (1.0 + t_eff) - fixed) * (1.0 + i_m)
        b = b * (1.0 + t_eff) * (1.0 + i_m)

    if abs(b) < 1e-12:
        return 0.0
    return (basis.total_sa - a) / b


def _anniversary_months(basis: GuidelineBasis, limit_years: Optional[int] = None) -> set[int]:
    months = set()
    count = 0
    for index, month in enumerate(basis.months):
        if month.is_anniversary:
            count += 1
            if limit_years is not None and count > limit_years:
                break
            months.add(index)
    return months


def _net_premium_basis(basis: GuidelineBasis) -> GuidelineBasis:
    """The 7702A 7-pay basis: a NET premium — guaranteed COI and benefit/rider
    charges only. No policy fee, no per-unit charges, no premium loads (the
    workbook's 7-pay block leaves those columns empty)."""
    stripped = GuidelineBasis(
        total_sa=basis.total_sa,
        db_option=basis.db_option,
        ctp=basis.ctp,
        guaranteed_rate=basis.guaranteed_rate,
        glp_rate_floor=basis.glp_rate_floor,
        gsp_rate_floor=basis.gsp_rate_floor,
    )
    for month in basis.months:
        stripped.months.append(GuidelineMonth(
            attained_age=month.attained_age,
            coi_rate=month.coi_rate,
            benefit_charges=month.benefit_charges,
            rider_charges=month.rider_charges,
            is_anniversary=month.is_anniversary,
        ))
    return stripped


def solve_guideline_premiums(
    basis: GuidelineBasis,
    *,
    starting_av: float = 0.0,
    glp_rate_floor: Optional[float] = None,
) -> GuidelineSolveResult:
    """GLP, GSP, and 7-pay from one guideline basis.

    * GSP: single premium at month 0, statutory floor +2%, LEVEL-DB mechanics.
    * GLP: premium at every anniversary month (a mid-year start defers the
      first premium to the next anniversary, per the workbook's indicator);
      honors the contract's actual DB option.
    * 7-pay: NET premium (no fees/EPU/loads) at month 0 and the next 6
      anniversaries, offset by the starting account value at the 7-pay date,
      LEVEL-DB mechanics.

    Only the GLP uses the contract's DB option — the workbook pins the GSP and
    7-pay blocks to option A (a true increasing-DB single-premium endowment is
    degenerate: the fund earns no COI offset, producing absurd premiums).
    """
    selected_glp_floor = basis.glp_rate_floor if glp_rate_floor is None else glp_rate_floor
    selected_gsp_floor = (
        basis.gsp_rate_floor
        if glp_rate_floor is None
        else glp_rate_floor + GSP_RATE_SPREAD
    )
    glp_rate = max(basis.guaranteed_rate, selected_glp_floor)
    gsp_rate = max(basis.guaranteed_rate, selected_gsp_floor)

    gsp = solve_endowment_premium(basis, gsp_rate, premium_months={0}, db_option="A")

    glp = solve_endowment_premium(basis, glp_rate, _anniversary_months(basis))

    seven_pay_months = {0} | _anniversary_months(basis, limit_years=SEVEN_PAY_YEARS)
    # Month 0 IS the first anniversary month when the calc starts on one — the
    # set union keeps exactly 7 premium dates either way.
    if len(seven_pay_months) > SEVEN_PAY_YEARS:
        seven_pay_months = set(sorted(seven_pay_months)[:SEVEN_PAY_YEARS])
    seven_pay = solve_endowment_premium(
        _net_premium_basis(basis), glp_rate, seven_pay_months,
        starting_av=starting_av, db_option="A")

    return GuidelineSolveResult(glp=glp, gsp=gsp, seven_pay=seven_pay)
