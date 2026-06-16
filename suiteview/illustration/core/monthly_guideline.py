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

at the deemed maturity (attained age 100). No search needed.

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
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import List, Optional

from suiteview.illustration.core.rate_loader import IllustrationRates, _safe_rate
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


SEVEN_PAY_YEARS = 7
COI_MONTHLY_CAP = 83.333          # per $1000 per month — Guideline_Premiums T column
DEEMED_MATURITY_AGE = 100         # s7702_MaturityAge
GLP_RATE_FLOOR = 0.04             # s7702_GLP_Rate (pre-2021 contracts)
GSP_RATE_SPREAD = 0.02            # GSP floor = GLP floor + 2%


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


@dataclass
class GuidelineSolveResult:
    glp: float = 0.0
    gsp: float = 0.0
    seven_pay: float = 0.0


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
    base = policy.base_segment
    issue_age = policy.issue_age
    total_months = max(0, (DEEMED_MATURITY_AGE - attained_age) * 12 - months_into_year)
    if active_as_of is None:
        active_as_of = as_of

    # Year offset from ISSUE for duration-indexed schedules (COI/loads/fees).
    start_year = max(1, attained_age - issue_age + 1)

    basis = GuidelineBasis(
        total_sa=policy.total_face,
        db_option=str(policy.db_option or "A").upper(),
        ctp=float(policy.ctp or 0.0),
        guaranteed_rate=float(policy.guaranteed_interest_rate or 0.0),
    )

    monthly_mtp = _trunc2(float(policy.mtp or 0.0))

    month_in_year = months_into_year
    policy_year = start_year
    for m in range(total_months):
        if m > 0 and month_in_year == 0:
            policy_year += 1
        age = issue_age + policy_year - 1
        gm = GuidelineMonth(
            attained_age=age,
            is_anniversary=(month_in_year == 0),
        )

        # ── Guaranteed COI per $1 SA (T): substandard + flats, capped ──
        raw_coi = _safe_rate(rates.segment_coi.get(base.coverage_phase, rates.coi), policy_year)
        table = base.table_rating if base.table_rating > 0 and _active(base.table_cease_date, as_of, policy_year) else 0
        adjusted = raw_coi * (1.0 + config.table_rating_factor * table)
        if base.flat_extra and base.flat_extra > 0 and _active(base.flat_cease_date, as_of, policy_year):
            adjusted += _trunc2(base.flat_extra / 12.0)
        gm.coi_rate = min(adjusted, COI_MONTHLY_CAP) / 1000.0

        # ── Monthly policy fee ──
        if config.mfee == "Table":
            gm.fee = _safe_rate(rates.mfee, policy_year)
        else:
            try:
                gm.fee = float(config.mfee)
            except (TypeError, ValueError):
                gm.fee = 0.0

        # ── Per-unit (EPU) charges, per segment at its own coverage year ──
        epu_total = 0.0
        for seg in policy.segments:
            seg_year = max(1, policy_year - _coverage_start_year_offset(policy, seg))
            if config.epu_code == "Table":
                seg_rate = _safe_rate(rates.segment_epu.get(seg.coverage_phase, rates.epu), seg_year)
            else:
                try:
                    seg_rate = float(config.epu_code)
                except (TypeError, ValueError):
                    seg_rate = 0.0
            sa_basis = (
                seg.original_face_amount
                if config.epu_sa_basis == "OriginalSA"
                else seg.face_amount
            )
            epu_total += seg_rate * sa_basis / 1000.0
        gm.epu = epu_total

        # ── Benefit charges (PW waives the monthly MTP — a FIXED basis here,
        #     keeping the solve linear; matches Guideline_Premiums AE). Each
        #     benefit stops at its payup/cease anniversary (the workbook gates
        #     on the payup AGE — e.g. PW ceases at the age-60 anniversary). ──
        ben_total = 0.0
        for ben in policy.benefits:
            ben_type = ben.benefit_type or ""
            if not ben.is_active or ben_type.startswith("#"):
                continue
            # A benefit already ceased at the calculation date contributes
            # nothing anywhere in the solve (strict, matching vPW_Active).
            if (
                ben.cease_date is not None
                and active_as_of is not None
                and active_as_of >= ben.cease_date
            ):
                continue
            cease_year = _benefit_cease_year(policy, ben)
            if cease_year is not None and policy_year > cease_year:
                continue
            ben_key = ben_type + (ben.benefit_subtype or "")
            schedule = rates.benefit_coi.get(ben_key, [])
            rate = _safe_rate(schedule, policy_year)
            if rate <= 0.0:
                continue
            factor = ben.rating_factor if ben.rating_factor and ben.rating_factor > 0 else 1.0
            gross = rate * factor
            if ben_type == "3":
                charge = _trunc2(gross * monthly_mtp)
            else:
                charge = (ben.units or 0.0) * gross
            ben_total += charge
            gm.benefit_charge_detail[_benefit_label(ben_type, ben.benefit_subtype)] = charge
        gm.benefit_charges = ben_total

        # QAB rider charge streams would add here; UL rider target/QAB data is
        # not present for the current product family (see QUESTION_LOG §E.4).

        # ── Premium loads (zero past the premium cease age) ──
        if age < config.premium_cease_age:
            if config.premium_load == "Table":
                gm.tpp = _safe_rate(rates.tpp, policy_year)
                gm.epp = _safe_rate(rates.epp, policy_year)
            else:
                try:
                    gm.tpp = gm.epp = float(config.premium_load)
                except (TypeError, ValueError):
                    gm.tpp = gm.epp = 0.0

        basis.months.append(gm)
        month_in_year = (month_in_year + 1) % 12

    return basis


def _active(cease_date: Optional[date], as_of: Optional[date], years_ahead: int) -> bool:
    """Whether a substandard charge is still active ``years_ahead`` from the start."""
    if cease_date is None or as_of is None:
        return True
    # Compare by year horizon — within-year precision is not needed because
    # guideline-basis rates are constant within a policy year anyway.
    return (as_of.year + years_ahead - 1) <= cease_date.year


def _coverage_start_year_offset(policy: IllustrationPolicyData, seg) -> int:
    """Policy years elapsed before the segment's coverage started (0 for cov 1)."""
    if seg.issue_date is None or policy.issue_date is None:
        return 0
    return max(0, seg.issue_date.year - policy.issue_date.year)


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
    cease = getattr(ben, "cease_date", None)
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
    glp_rate_floor: float = GLP_RATE_FLOOR,
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
    glp_rate = max(basis.guaranteed_rate, glp_rate_floor)
    gsp_rate = max(basis.guaranteed_rate, glp_rate_floor + GSP_RATE_SPREAD)

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
