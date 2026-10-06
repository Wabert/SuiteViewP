"""Map PolicyInformation/DB2 policy records into IllustrationPolicyData.

Source mapping:

* Core identity/duration: PolicyInformation properties backed by LH_BAS_POL and
  base coverage fields (plan, company, status, issue/valuation dates, billing,
  demographics, death-benefit option and duration).
* Coverage/rider/benefit structure: PolicyInformation ``get_base_coverages()``,
  ``get_riders()``, ``get_benefits()`` plus substandard ratings. Band lookups
  stay at the rate boundary through ``ULRates.get_band`` (UL_Rates schema ``rates``).
* Financial basis: PolicyInformation monthliversary values, premium history,
  policy totals, target/guideline amounts, loans, withdrawals, MEC/TAMRA fields
  and shadow-account seed values.
* IUL basis: current fund buckets, impaired loan-collateral buckets, premium
  allocations and the index assumptions for the requested illustration date:
  crediting parameters from schema ``rates`` (``ULRates``) plus illustrated
  rates, benchmark and market returns from schema ``rates`` FUND rows
  (``IndexAssumptionTables``).

The public loader deliberately performs only source mapping and validation. It
loads neither projection rates nor engine results; use ``suiteview.illustration.api``
for the canonical build-rates-project wiring.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from suiteview.core.band_rules import rider_bands_as_base
from suiteview.core.index_rates import IndexAssumptionTables
from suiteview.polview.services.policy_service import get_policy_info
from suiteview.illustration.core.reinstatement_basis import restore_lapse_coverage
from suiteview.illustration.core.skipped_coverage import (
    OPTION_C_PREMIUM_CODES,
    WITHDRAWAL_CODES,
    build_skipped_coverage_periods,
)
from suiteview.illustration.core.target_premium import floor_monthly_cent
from suiteview.illustration.core.ul_rates import ULRates
from suiteview.illustration.core.value_rollback import build_value_rollback_snapshots
from suiteview.illustration.core.withdrawal_handler import seed_ffl_withdrawal_history
from suiteview.illustration.models.index_strategies import (
    FIXED_FUND_ID,
    SWEEP_FUND_ID,
    is_iul_plan,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import (
    BenefitInfo as IllBenefitInfo,
)
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    FundSegmentValue,
    IllustrationPolicyData,
    JointLives,
    PremiumTransaction,
    RiderInfo,
)
from suiteview.illustration.models.rider_config import load_rider_config
from suiteview.polview.models.policy_sections.lookup import policy_attr

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PolicySourceSnapshot:
    """Loaded DB2/PolicyInformation facts used to build an illustration policy.

    The snapshot names the source boundary: all database reads happen before the
    build_* mapping steps, while rate-band lookups needed to identify the policy
    shape are captured here with their source inputs.
    """

    policy_number: str
    region: str
    pi: object
    rates_db: ULRates
    illustration_date: date
    reinstatement_date: date | None
    plancode: str
    plancode_config: PlancodeConfig
    issue_date: date | None
    issue_age: int
    rate_sex: str
    rate_class: str
    valuation_date: date | None
    as_of_date: date
    face_amount: float
    units: float
    band: int
    form_number: str
    base_coverages: list
    active_base_coverages: list
    substandard_by_phase: dict
    raw_benefits: list
    raw_riders: list
    joint_company: str | None = None   # rates.PLAN_ATTR LIVES=3 plan's company


@dataclass(frozen=True)
class BenefitAssembly:
    """Mapped supplemental benefits plus derived CCV/shadow indicators."""

    benefits: list[IllBenefitInfo]
    ccv_active: bool
    ccv_ceased: bool
    ccv_units: float
    ccv_coi_rate: float | None


def build_illustration_data(
    policy_number: str,
    region: str = "CKPR",
    company_code: str | None = None,
    *,
    illustration_date: date | None = None,
    reinstatement_date: date | None = None,
) -> IllustrationPolicyData:
    """Load PolicyInformation and map it into IllustrationPolicyData.

    The orchestration is intentionally thin: create a source snapshot, build the
    named policy-data sections, then attach value-rollback snapshots. Projection
    rates and engine execution are owned by ``suiteview.illustration.api``.
    ``reinstatement_date`` opts into continuous coverage for a confirmed lapse;
    only coverages explicitly terminated on that effective date are restored.

    Raises:
        ValueError: If policy not found in DB2.
    """
    source = _load_policy_source_snapshot(
        policy_number,
        region,
        company_code,
        illustration_date=illustration_date,
        reinstatement_date=reinstatement_date,
    )
    benefits = build_benefits(source)
    policy = IllustrationPolicyData(
        **build_core_identity(source),
        **build_financial_basis(source),
        **build_iul_basis(source),
        segments=build_coverage_segments(source),
        benefits=benefits.benefits,
        riders=build_riders(source),
        ccv_active=benefits.ccv_active,
        ccv_ceased=benefits.ccv_ceased,
        ccv_units=benefits.ccv_units,
        ccv_coi_rate=benefits.ccv_coi_rate,
    )
    policy.skipped_coverage_periods = build_skipped_coverage_basis(source, policy)
    policy.rollback_snapshots = build_value_rollback_snapshots(source.pi, policy)
    build_ffl_withdrawal_credit(source, policy)
    return policy


def build_ffl_withdrawal_credit(source: PolicySourceSnapshot, policy: IllustrationPolicyData) -> None:
    """Company-26 FFL: seed the surrender-charge credit for partial surrender charges taken
    on in-force withdrawals (FH_FIXED SG/SM/SN events), or fall back to the current-units
    basis when that history cannot be read or is incomplete against TOT_WTD_QTY."""
    config = source.plancode_config
    count = int(source.pi.values.total_withdrawal_count or 0)
    if (not count or str(policy.company_code or "").strip() != "26"
            or not config.ffl_per_unit_surrender_charge):
        return
    try:
        transactions = source.pi.activity.get_live_transactions(WITHDRAWAL_CODES)
        if source.pi.table_error("FH_FIXED"):
            transactions = None
    except RuntimeError as exc:
        logger.warning("FFL withdrawal history unavailable for %s: %s", policy.policy_number, exc)
        transactions = None
    seed_ffl_withdrawal_history(policy, config, transactions, count, config.withdrawal_fee)


def build_skipped_coverage_basis(source: PolicySourceSnapshot, policy: IllustrationPolicyData):
    """Skipped-coverage reinstatements on coverage phase 1 with their option C exclusion.

    A policy without LH_COV_SKIPPED_PER rows (never reinstated, or a continuous
    reinstatement) gets none and keeps its lifetime basis. A failed read is raised, not
    taken as "never reinstated".
    """
    pi = source.pi
    periods = [
        period for period in pi.coverages.get_skipped_periods(cov_pha_nbr=1)
        if period.reinstatement_date is not None
    ]
    error = pi.table_error("LH_COV_SKIPPED_PER")
    if error:
        raise RuntimeError(f"Cannot load skipped-coverage periods (LH_COV_SKIPPED_PER): {error}")
    if not periods:
        return []
    transactions = pi.activity.get_live_transactions(OPTION_C_PREMIUM_CODES | WITHDRAWAL_CODES)
    error = pi.table_error("FH_FIXED")
    if error:
        raise RuntimeError(f"Cannot load reinstatement transactions (FH_FIXED): {error}")
    return build_skipped_coverage_periods(
        periods, transactions,
        premiums_to_date=policy.premiums_paid_to_date,
        withdrawals_to_date=policy.withdrawals_to_date,
        inforce_withdrawal_fees=policy.inforce_withdrawal_fees,
        withdrawal_fee=policy.withdrawal_fee,
    )


def _load_policy_source_snapshot(
    policy_number: str,
    region: str,
    company_code: str | None,
    *,
    illustration_date: date | None,
    reinstatement_date: date | None,
) -> PolicySourceSnapshot:
    """Read PolicyInformation once and cache source facts shared by builders."""
    pi = get_policy_info(policy_number, region, company_code)
    _validate_source_policy(pi, policy_number, region, reinstatement_date)
    rates_db = ULRates(pi.company_code or "")
    illustration_date = illustration_date or date.today()  # noqa: DTZ011
    plancode = pi.coverages.base_plancode or ""
    plancode_config = load_plancode(plancode)
    valuation_date = pi.values.valuation_date
    as_of_date = valuation_date or date.today()  # noqa: DTZ011
    raw_riders, base_coverages = _restored_coverage_sources(pi, reinstatement_date)
    active_base_coverages = _active_base_coverages(base_coverages, as_of_date)
    face_amount, units, band = _source_face_units_band(
        pi, rates_db, plancode, pi.activity.issue_date, active_base_coverages,
        base_coverages, raw_riders, as_of_date, reinstatement_date,
        banded=not plancode_config.is_iswl)
    joint_company = rates_db.joint_survivor_company(plancode)
    if joint_company is not None and joint_company != (pi.company_code or "").strip():
        raise ValueError(
            f"Joint survivor plan {plancode} is defined for company {joint_company}, "
            f"not the policy's company {pi.company_code}.")
    return PolicySourceSnapshot(
        policy_number=policy_number,
        region=region,
        pi=pi,
        rates_db=rates_db,
        illustration_date=illustration_date,
        reinstatement_date=reinstatement_date,
        plancode=plancode,
        plancode_config=plancode_config,
        issue_date=pi.activity.issue_date,
        issue_age=pi.coverages.base_issue_age if pi.coverages.base_issue_age is not None else 0,
        rate_sex=_translate_sex(pi.coverages.base_sex_code),
        rate_class=policy_attr(pi, "base_rate_class", "") or "",
        valuation_date=valuation_date,
        as_of_date=as_of_date,
        face_amount=face_amount,
        units=units,
        band=band,
        form_number=_source_form_number(active_base_coverages, base_coverages),
        base_coverages=base_coverages,
        active_base_coverages=active_base_coverages,
        substandard_by_phase=_substandard_by_phase(pi),
        raw_benefits=pi.benefits.get_benefits(),
        raw_riders=raw_riders,
        joint_company=joint_company,
    )


def _validate_source_policy(pi, policy_number: str, region: str, reinstatement_date) -> None:
    if pi is None or not pi.exists:
        raise ValueError(f"Policy {policy_number} not found in region {region}")
    if reinstatement_date is not None and (
        pi.status.last_entry_code.strip().upper() != "Q" or pi.activity.terminate_date != reinstatement_date
    ):
        raise ValueError("Coverage restoration requires the policy's confirmed lapse effective date.")


def _restored_coverage_sources(pi, reinstatement_date) -> tuple[list, list]:
    raw_riders = [
        restore_lapse_coverage(rider, reinstatement_date)
        for rider in pi.coverages.get_riders()
    ]
    base_coverages = [
        restore_lapse_coverage(cov, reinstatement_date)
        for cov in pi.coverages.get_base_coverages()
    ]
    return raw_riders, base_coverages


def _active_base_coverages(base_coverages: list, as_of_date: date) -> list:
    return [
        cov for cov in base_coverages
        if not _coverage_is_terminated(cov, as_of_date)
    ]


def _source_form_number(active_base_coverages: list, base_coverages: list) -> str:
    form_cov = (active_base_coverages or base_coverages or [None])[0]
    return (getattr(form_cov, "form_number", "") or "").strip()


def _source_face_units_band(
    pi, rates_db: ULRates, plancode: str, issue_date,
    active_base_coverages: list, base_coverages: list, raw_riders: list,
    as_of_date: date, reinstatement_date, *, banded: bool = True,
) -> tuple[float, float, int]:
    """Base face, units and UL rate band. ``banded=False`` (ISWL, whose fixed-premium
    basis bands itself in ``iswl_rates``) keeps band 1."""
    face_amount = float(pi.coverages.base_total_face_amount) if pi.coverages.base_total_face_amount else 0.0
    units = face_amount / 1000.0 if face_amount else 0.0
    band_face = float(pi.coverages.base_band_specified_amount)
    if base_coverages:
        face_amount, units = _base_face_units(active_base_coverages)
        band_face = _base_band_face(
            pi, face_amount, raw_riders, as_of_date, reinstatement_date)
    if not banded:
        return face_amount, units, 1
    raw_band = rates_db.get_band(plancode, band_face, issue_date=issue_date)
    return face_amount, units, raw_band if raw_band is not None else 1


def _base_face_units(active_base_coverages: list) -> tuple[float, float]:
    face_amount = sum(float(cov.face_amount or 0.0) for cov in active_base_coverages)
    units = sum(
        float(cov.units) if cov.units else float(cov.face_amount or 0.0) / 1000.0
        for cov in active_base_coverages
    )
    return face_amount, units


def _base_band_face(pi, face_amount: float, raw_riders: list, as_of_date, reinstatement_date) -> float:
    if reinstatement_date is None:
        return float(pi.coverages.base_band_specified_amount)
    return face_amount + sum(
        float(rider.face_amount)
        for rider in raw_riders
        if not _coverage_is_terminated(rider, as_of_date)
        and rider_bands_as_base(rider.plancode)
    )


def _substandard_by_phase(pi) -> dict:
    result = {}
    for rating in pi.coverages.get_substandard_ratings():
        result.setdefault(rating.coverage_phase, []).append(rating)
    return result


def build_core_identity(source: PolicySourceSnapshot) -> dict:
    """Map LH_BAS_POL/base coverage identity, timing and DBO fields."""
    pi = source.pi
    policy_year = pi.activity.policy_year or 1
    policy_month = pi.activity.policy_month or 1
    if source.issue_date and source.valuation_date:
        months_since_issue = _completed_months(source.issue_date, source.valuation_date)
        policy_month = (months_since_issue % 12) + 1
    duration = (policy_year - 1) * 12 + policy_month
    attained_age = (
        pi.coverages.attained_age
        if pi.coverages.attained_age is not None
        else (source.issue_age + policy_year - 1)
    )
    return {
        "policy_number": source.policy_number.strip(),
        "region": source.region,
        "company_code": pi.company_code or "",
        "reins_partner": str(policy_attr(pi, "reins_partner", "") or "").strip().upper(),
        "insured_name": pi.persons.primary_insured_name or "",
        "premium_pay_status_code": str(policy_attr(pi, "premium_pay_status_code", "") or ""),
        "plancode": source.plancode,
        "product_type": pi.product.product_type or "",
        "form_number": source.form_number,
        "issue_state": pi.product.issue_state or "",
        "company_sub": pi.company_name or "",
        "issue_date": source.issue_date,
        "issue_age": source.issue_age,
        "attained_age": attained_age,
        "insured_birth_date": pi.persons.primary_insured_birth_date,
        "rate_sex": source.rate_sex,
        "rate_class": source.rate_class,
        "face_amount": source.face_amount,
        "units": source.units,
        "db_option": _translate_dbo(pi.product.db_option_code or ""),
        "band": source.band,
        "illustration_date": source.illustration_date,
        "policy_year": policy_year,
        "policy_month": policy_month,
        "duration": duration,
        "valuation_date": source.valuation_date,
        "maturity_age": pi.coverages.age_at_maturity or 121,
    }


def build_iul_basis(source: PolicySourceSnapshot) -> dict:
    """Map IUL fund/allocation tables and UL_Rates index assumptions."""
    pi = source.pi
    reins_partner = str(policy_attr(pi, "reins_partner", "") or "").strip().upper()
    index_illustration_rates = None
    index_strategy_parameters = None
    index_benchmark_minimum = None
    index_benchmark_maximum = None
    index_market_returns = None
    if is_iul_plan(source.plancode):
        index_strategy_parameters = source.rates_db.get_index_strategy_parameters(
            source.plancode,
            source.illustration_date,
            reins_partner,
        )
        tables = IndexAssumptionTables()
        try:
            index_illustration_rates = tables.get_index_illustration_rates(
                pi.company_code or "",
                source.plancode,
                source.illustration_date,
                reins_partner,
            )
            index_market_returns = tables.get_index_market_returns()
            benchmark = tables.get_index_benchmark_minmax(
                source.plancode,
                source.illustration_date,
                reins_partner,
            )
        finally:
            tables.close()
        if benchmark is not None:
            index_benchmark_minimum = benchmark["minimum"]
            index_benchmark_maximum = benchmark["maximum"]

    fund_values = {}
    fund_segments = []
    # Only IUL plans carry index segments; declared-rate UL phases (e.g. a
    # negative GP bucket or the FFL F1 fund) are not segments.
    index_plan = is_iul_plan(source.plancode)
    for bucket in pi.values.get_fund_buckets(current_only=True):
        fund = str(bucket.fund_id or "").strip()
        if fund:
            value = float(bucket.csv_amount) if bucket.csv_amount is not None else 0.0
            fund_values[fund] = fund_values.get(fund, 0.0) + value
            if not index_plan:
                continue
            segment = _open_index_segment(fund, value, getattr(bucket, "raw_data", None))
            if segment is not None:
                fund_segments.append(segment)
    impaired_fund_values = {
        str(fund): float(value)
        for fund, value in pi.values.get_loan_values_dict().items()
    }
    premium_allocations = {
        str(fund): float(pct)
        for fund, pct in pi.values.get_premium_allocation_dict().items()
    }
    if sum(premium_allocations.values()) > 1.5:
        premium_allocations = {fund: pct / 100 for fund, pct in premium_allocations.items()}
    current_rate, current_rate_source = _current_interest_rate(source)
    return {
        "guaranteed_interest_rate": source.plancode_config.gint,
        "current_interest_rate": current_rate,
        "current_interest_rate_source": current_rate_source,
        "prospective_bonus_stage": pi.product.prospective_bonus_code,
        "guaranteed_crediting_rate": _legacy_guaranteed_crediting_rate(source),
        "fund_values": fund_values,
        "fund_segments": fund_segments,
        "impaired_fund_values": impaired_fund_values,
        "premium_allocations": premium_allocations,
        "index_illustration_rates": index_illustration_rates,
        "index_strategy_parameters": index_strategy_parameters,
        "index_benchmark_minimum": index_benchmark_minimum,
        "index_benchmark_maximum": index_benchmark_maximum,
        "index_market_returns": index_market_returns,
    }


def _open_index_segment(fund: str, value: float, row) -> FundSegmentValue | None:
    """An open indexed segment from a current LH_POL_FND_VAL_TOT phase row.

    Each index segment is its own fund value phase opened on ``VAL_STR_DT`` (the
    sweep date); matured phases stay on the table with no value. Sweep, fixed
    and loan-impaired rows are not index segments.
    """
    if fund in (SWEEP_FUND_ID, FIXED_FUND_ID) or abs(value) < 0.005:
        return None
    if str((row or {}).get("IMPAIRED_IND", "0") or "0").strip() == "1":
        return None
    start = (row or {}).get("VAL_STR_DT")
    if isinstance(start, datetime):
        start = start.date()
    elif not isinstance(start, date):
        try:
            start = datetime.strptime(str(start).strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return FundSegmentValue(fund_id=fund, start_date=start, value=value)


def _policy_guaranteed_rate(source: PolicySourceSnapshot) -> float:
    """The policy's operative guaranteed crediting rate (decimal); see
    :func:`declared_rates.policy_guaranteed_rate` (plan GINT without a fund row)."""
    from suiteview.illustration.core.declared_rates import policy_guaranteed_rate

    return policy_guaranteed_rate(source.pi, source.plancode_config.gint)


def _legacy_guaranteed_crediting_rate(source: PolicySourceSnapshot) -> float | None:
    """The guaranteed crediting rate after the initial guarantee period, when it is
    not the plan GINT (declared-rate UL only).

    The ANICO1996 4%-GINT plans (1U135900/D00/H00/K00/Q00) guarantee 4% in policy
    years 1-10 and then the policy's ``GUA_FND_ITS_RT``, 3.00% or 3.25% (product
    specs Section M; SR113413 "C is 4% in years 1-10 and 3% from year 11, except in
    TX where it is 3.25%"). DB2 CKPR 2026-10-04: no other declared-rate UL plan has
    an in-force policy whose fund guarantee differs from its GINT. The plan GINT stays
    the NAR discount and 7702 rate."""
    config = source.plancode_config
    if config.is_iswl or is_iul_plan(source.plancode):
        return None
    rate = _policy_guaranteed_rate(source)
    return rate if abs(rate - float(config.gint or 0.0)) > 1e-9 else None


def _current_interest_rate(source: PolicySourceSnapshot) -> tuple[float, str]:
    """Current declared crediting rate, floored at the policy's guaranteed rate.

    Declared-rate UL plans use the latest current-scale CIRF rate for the plan's
    ``CINT_Key`` fund (RGA policies: its ``R`` reinsurance block when loaded) in
    schema ``rates`` on the illustration date, floored at the fixed fund's
    guaranteed rate; with none loaded they keep that guaranteed rate. IUL keeps
    GINT here (its fixed account uses the IUL declared rate). ISWL uses the
    declared fixed-fund rate in schema ``rates`` on the illustration date; where
    the plan has none loaded, the rate its current fund buckets are credited
    (``VAL_PHA_ITS_RT``).
    """
    config = source.plancode_config
    if not config.is_iswl:
        if is_iul_plan(source.plancode):
            return config.gint, ""
        from suiteview.illustration.core.declared_rates import ul_current_declared_rate

        guaranteed = _policy_guaranteed_rate(source)
        declared = ul_current_declared_rate(
            source.pi.company_code or "", source.plancode, source.illustration_date,
            guaranteed, cint_key=config.cint_key,
            rga_indicator=str(policy_attr(source.pi, "reins_partner", "") or ""))
        if declared is None:
            return guaranteed, ""
        return declared.rate, declared.source
    from suiteview.illustration.core.iswl_rates import (
        FundBucketRate,
        iswl_current_credited_rate,
        iswl_recorded_credited_rate,
    )

    rate = iswl_current_credited_rate(
        source.pi.company_code or "", source.plancode, source.illustration_date, config.gint)
    if rate is not None:
        return rate, "UL_Rates schema rates declared fixed-fund rate (CINT_NEW/CINT_ROLL)"
    current = [
        (str(bucket.raw_data.get("IMPAIRED_IND", "0")).strip() == "1",
         FundBucketRate(float(bucket.csv_amount or 0), bucket.interest_rate, bucket.fund_id))
        for bucket in source.pi.values.get_fund_buckets(current_only=True)
    ]
    # IMPAIRED_IND 1 marks a fund that also holds loan collateral; its LH_POL_FND_VAL_TOT
    # row is still the unloaned value (the collateral is LH_FND_VAL_LOAN), credited at the
    # declared rate (B11SB200 26/000321893: AV 21,077.73 = F1 12,752.46 + loan 8,325.27).
    buckets = [b for impaired, b in current if not impaired] or [b for _impaired, b in current]
    return (
        iswl_recorded_credited_rate(buckets, config.gint),
        "Rate credited to the policy's current fund buckets (LH_POL_FND_VAL_TOT); "
        "schema rates has no declared rate for this plan",
    )


def build_financial_basis(source: PolicySourceSnapshot) -> dict:
    """Map monthliversary values, premiums, targets, loans and TAMRA fields."""
    pi = source.pi
    modal_premium = float(pi.billing.modal_premium) if pi.billing.modal_premium is not None else 0.0
    billing_frequency = pi.billing.billing_frequency or 1
    if billing_frequency <= 0:
        billing_frequency = 1
    av_raw = pi.values.mv_av(0)
    glp_raw = pi.targets.glp
    gsp_raw = pi.targets.gsp
    tamra_level_raw = pi.values.tamra_7pay_level
    tamra_start_av_raw = pi.values.tamra_7pay_av
    return {
        "account_value": float(av_raw) if av_raw is not None else 0.0,
        "cost_basis": float(pi.values.cost_basis) if pi.values.cost_basis is not None else 0.0,
        "system_coi_charge": float(pi.values.mv_coi_charge(0) or 0),
        "system_expense_charge": float(pi.values.mv_expense_charge(0) or 0),
        "system_other_charge": float(pi.values.mv_other_charge(0) or 0),
        "system_monthly_deduction": float(pi.values.mv_monthly_deduction(0) or 0),
        "modal_premium": modal_premium,
        "annual_premium": modal_premium * (12.0 / billing_frequency),
        "billing_frequency": billing_frequency,
        "bill_form_code": str(pi.billing.bill_form_code or "").strip(),
        "premiums_paid_to_date": float(pi.billing.premium_td) if pi.billing.premium_td is not None else 0.0,
        "premiums_ytd": float(pi.billing.premium_ytd) if pi.billing.premium_ytd is not None else 0.0,
        "premium_transactions": _premium_transactions(pi),
        "def_of_life_ins": _translate_doli(str(pi.product.def_of_life_ins_code or "")),
        "glp": floor_monthly_cent(float(glp_raw)) if glp_raw is not None else 0.0,
        "glp_is_known": glp_raw is not None,
        "gsp": floor_monthly_cent(float(gsp_raw)) if gsp_raw is not None else 0.0,
        "accumulated_glp": _float_or_zero(pi.targets.accumulated_glp_target),
        "corridor_percent": _float_or_default(pi.product.corridor_percent, 100.0),
        "mtp": _float_or_zero(pi.targets.mtp),
        "accumulated_mtp": _float_or_zero(pi.targets.accumulated_mtp_target),
        "map_cease_date": policy_attr(pi, "map_date", None),
        "ctp": _float_or_zero(pi.targets.ctp),
        "is_mec": pi.values.is_mec,
        "tamra_7pay_level": _float_or_zero(tamra_level_raw),
        "tamra_7pay_start_date": pi.values.tamra_7pay_start_date,
        "tamra_7pay_start_av": _float_or_zero(tamra_start_av_raw),
        "tamra_7pay_cash_value": _float_or_zero(tamra_start_av_raw),
        "tamra_7year_lowest_db": float(policy_attr(pi, "tamra_7pay_specified_amount", None) or 0.0),
        "tamra_7year_contributions": _tamra_contributions(pi),
        "withdrawals_to_date": float(pi.values.total_withdrawals or 0),
        "terminated_base_face": _terminated_base_face(source),
        "inforce_withdrawal_fees": (
            (pi.values.total_withdrawal_count or 0) * source.plancode_config.withdrawal_fee),
        "withdrawal_fee": source.plancode_config.withdrawal_fee,
        "decrease_charge_allowed": pi.support.decrease_charge_allowed,
        "shadow_account_value": _float_or_zero(pi.targets.shadow_account_value),
        **_loan_basis(pi),
    }


def _float_or_zero(value) -> float:
    return float(value) if value is not None else 0.0


def _terminated_base_face(source: PolicySourceSnapshot) -> float:
    """Face of the base-plan coverage phases that are terminated but still on record."""
    active = {id(cov) for cov in source.active_base_coverages}
    return sum(float(cov.face_amount or 0.0) for cov in source.base_coverages if id(cov) not in active)


def _float_or_default(value, default: float) -> float:
    return float(value) if value is not None else default


def _premium_transactions(pi) -> list[PremiumTransaction]:
    return [
        PremiumTransaction(
            effective_date=transaction.trans_date,
            amount=float(transaction.gross_amount),
            transaction_type=transaction.trans_code,
        )
        for transaction in pi.activity.get_premium_transactions()
    ]


def _tamra_contributions(pi) -> list[float]:
    return [
        float(pi.values.tamra_7pay_premium_paid(tamra_year) or 0.0)
        - float(pi.values.tamra_7pay_withdrawals(tamra_year) or 0.0)
        for tamra_year in range(1, 8)
    ]


def _loan_basis(pi) -> dict:
    var_loan_rate_raw = policy_attr(pi, "variable_loan_charge_rate", None)
    var_loan_charge_rate = (
        float(var_loan_rate_raw) if var_loan_rate_raw is not None else None
    )
    if var_loan_charge_rate is not None and var_loan_charge_rate > 1:
        var_loan_charge_rate /= 100.0
    regular_rate_raw = policy_attr(pi, "fixed_loan_interest_rate", None)
    preferred_rate_raw = policy_attr(pi, "preferred_loan_interest_rate", None)
    return {
        "regular_loan_principal": float(pi.loans.total_regular_loan_principal or 0),
        "regular_loan_accrued": float(pi.loans.total_regular_loan_accrued or 0),
        "preferred_loan_principal": float(pi.loans.total_preferred_loan_principal or 0),
        "preferred_loan_accrued": float(pi.loans.total_preferred_loan_accrued or 0),
        "preferred_loans_available": bool(pi.loans.preferred_loans_available),
        "regular_loan_charge_rate": (
            float(regular_rate_raw) / 100 if regular_rate_raw is not None else None
        ),
        "preferred_loan_charge_rate": (
            float(preferred_rate_raw) / 100 if preferred_rate_raw is not None else None
        ),
        "variable_loan_principal": float(pi.loans.total_variable_loan_principal or 0),
        "variable_loan_accrued": float(pi.loans.total_variable_loan_accrued or 0),
        "variable_loan_charge_rate": var_loan_charge_rate,
    }


def build_coverage_segments(source: PolicySourceSnapshot) -> list[CoverageSegment]:
    """Map active LH_COV_PHA base coverage rows into engine segments."""
    return [_coverage_segment_from_source(source, cov) for cov in source.active_base_coverages]


def _coverage_segment_from_source(source: PolicySourceSnapshot, cov) -> CoverageSegment:
    seg_face = float(cov.face_amount) if cov.face_amount else 0.0
    if source.plancode_config.sa_basis == "OriginalSA" and cov.orig_amount is None:
        raise ValueError(
            f"Coverage {cov.cov_pha_nbr}: original specified amount is required "
            "for SA_Basis=OriginalSA"
        )
    seg_orig_face = float(cov.orig_amount) if cov.orig_amount is not None else seg_face
    try:
        seg_rate_sex = _translate_sex(cov.sex_code)
    except (AttributeError, TypeError, ValueError):
        seg_rate_sex = source.rate_sex
    seg_table, seg_table_cease, seg_flat, seg_flat_cease = _substandard_basis(source, cov)
    joint_lives = None
    surrender_target = None
    if _is_joint_phase(cov, source.joint_company, source.plancode):
        joint_lives, surrender_target = _joint_segment_inputs(source.pi, cov)
        # Both insureds' extras are inside the blended JointCOI.
        seg_table, seg_table_cease, seg_flat, seg_flat_cease = 0, None, 0.0, None
    seg_band = source.band
    original_band = (
        source.pi.rates.cov_mtp_band(cov.cov_pha_nbr)
        if source.plancode_config.sa_basis == "OriginalSA"
        else seg_band
    )
    return CoverageSegment(
        coverage_phase=cov.cov_pha_nbr,
        is_base=True,
        is_cola=str(getattr(cov, "cola_indicator", "")).strip() == "1",
        issue_date=cov.issue_date,
        issue_age=cov.issue_age if cov.issue_age is not None else source.issue_age,
        rate_sex=seg_rate_sex,
        rate_class=cov.rate_class or source.rate_class,
        face_amount=seg_face,
        original_face_amount=seg_orig_face,
        units=float(cov.units) if cov.units else seg_face / 1000.0,
        vpu=float(cov.vpu) if cov.vpu else 1000.0,
        band=seg_band,
        original_band=original_band,
        table_rating=seg_table,
        table_cease_date=seg_table_cease,
        flat_extra=seg_flat,
        flat_cease_date=seg_flat_cease,
        status=cov.cov_status or "A",
        maturity_date=cov.maturity_date,
        coi_renewal_rate=float(cov.coi_rate) if cov.coi_rate else None,
        premium_rate=float(cov.premium_rate) if cov.premium_rate else None,
        joint_lives=joint_lives,
        surrender_target=surrender_target,
        **_iswl_nsp_basis(source, cov),
    )


def _iswl_nsp_basis(source: PolicySourceSnapshot, cov) -> dict:
    """ISWL CVAT NSP inputs: valuation mortality table and NSP interest (CyberDoc D10:
    ISL DEFRA net single premiums use the valuation mortality table)."""
    if not source.plancode_config.is_iswl:
        return {}
    facts = source.pi.coverages.traditional_facts(cov.cov_pha_nbr)
    rate = facts.nsp_interest_rate
    return {
        "nsp_mortality_table": facts.valuation_mortality_table,
        "nsp_interest_rate": float(rate) / 100.0 if rate is not None else None,
    }


def _is_joint_phase(cov, joint_company: str | None, plancode: str) -> bool:
    """A lives-3 phase must be on a plan defined as joint in UL_Rates, and vice versa."""
    lives = str(getattr(cov, "number_of_lives_code", "") or "").strip()
    if joint_company is None:
        if lives == "3":
            raise ValueError(
                f"Coverage phase {cov.cov_pha_nbr} is joint survivor (NBR_OF_LIVES_CD 3), but "
                f"plan {plancode} is not defined as joint in UL_Rates rates.PLAN_ATTR (LIVES=3); "
                "RERUN cannot illustrate it as a single life.")
        return False
    if lives != "3":
        raise ValueError(
            f"Coverage phase {cov.cov_pha_nbr} of joint survivor plan {plancode} has "
            f"NBR_OF_LIVES_CD {lives or 'blank'}, not 3.")
    return True


def _joint_segment_inputs(pi, cov) -> tuple[JointLives, float | None]:
    """Both insureds, their extras and the stored surrender target for a joint phase."""
    index = pi.coverages.cov_index_for_phase(cov.cov_pha_nbr)
    primary, joint = pi.rates.cov_joint_insureds(index)
    target = pi.targets.cov_surrender_target(cov.cov_pha_nbr)
    return (
        JointLives(primary=primary, joint=joint, ratings=list(pi.rates.cov_joint_ratings(index))),
        float(target) if target is not None else None,
    )


def _substandard_basis(source: PolicySourceSnapshot, cov) -> tuple[int, object, float, object]:
    seg_table = cov.table_rating if cov.table_rating is not None else 0
    seg_table_cease = None
    seg_flat = float(cov.flat_extra) if cov.flat_extra else 0.0
    seg_flat_cease = cov.flat_cease_date
    for rating in source.substandard_by_phase.get(cov.cov_pha_nbr, []):
        if rating.type_code == "T" and rating.table_rating_numeric and rating.table_rating_numeric > 0:
            seg_table = rating.table_rating_numeric
            seg_table_cease = rating.flat_cease_date
        elif rating.type_code == "F":
            if rating.flat_amount:
                seg_flat = float(rating.flat_amount)
            seg_flat_cease = rating.flat_cease_date
    return seg_table, seg_table_cease, seg_flat, seg_flat_cease


def build_benefits(source: PolicySourceSnapshot) -> BenefitAssembly:
    """Map LH_SPM_BNF supplemental benefits and derive CCV indicators."""
    benefits = [
        _benefit_info(benefit, source.as_of_date)
        for benefit in source.raw_benefits
        if _benefit_payable(benefit, source.as_of_date)
    ]
    ccv_active, ccv_units, ccv_coi_rate = _active_ccv_basis(benefits)
    ccv_ceased = _ccv_ceased(source.raw_benefits, source.as_of_date, ccv_active)
    return BenefitAssembly(
        benefits=benefits,
        ccv_active=ccv_active,
        ccv_ceased=ccv_ceased,
        ccv_units=ccv_units,
        ccv_coi_rate=ccv_coi_rate,
    )


def _benefit_payable(benefit, as_of_date: date) -> bool:
    payable_until = _payable_until(benefit)
    return not (payable_until and payable_until < as_of_date)


def _payable_until(benefit):
    """The benefit's pay-up date, or its cease date when that was extended past the
    original (BNF_CEA_DT > BNF_OGN_CEA_DT; CEA_DT_INP_IND 1) beyond pay-up: CyberLife
    charges to the extended cease date (V8634366 ADB2 pay-up 2025-10-10 extended to
    2026-10-10; S0505863 PW3 pay-up 2026-01-23 extended to 2027-01-23)."""
    pay_up, cease, original = benefit.pay_up_date, benefit.cease_date, benefit.orig_cease_date
    if pay_up and cease and original and cease > original and cease > pay_up:
        return cease
    return pay_up


def _charge_end_date(benefit):
    """The date a benefit's charge stops (exclusive, like a pay-up date). A cease date
    before pay-up ends the charge on the cease-date monthliversary (S4600372 PW4 cease
    2026-05-20, pay-up 2031: 0.60 through 04-20, nothing from 05-20)."""
    payable_until, cease = _payable_until(benefit), benefit.cease_date
    if payable_until and cease and cease < payable_until:
        return cease
    return payable_until


def _benefit_ceased(benefit, as_of_date: date) -> bool:
    """CyberLife moves BNF_CEA_DT to the termination date when a benefit ends before
    its pay-up date (BNF_OGN_CEA_DT keeps the original); a ceased benefit is not charged."""
    return bool(benefit.cease_date and benefit.cease_date < as_of_date)


def _benefit_info(benefit, as_of_date: date) -> IllBenefitInfo:
    return IllBenefitInfo(
        coverage_phase=benefit.cov_pha_nbr,
        form_number=benefit.form_number or "",
        benefit_type=benefit.benefit_type_cd or "",
        benefit_subtype=benefit.benefit_subtype_cd or "",
        benefit_amount=float(benefit.benefit_amount) if benefit.benefit_amount else 0.0,
        units=float(benefit.units) if benefit.units else 0.0,
        vpu=float(benefit.vpu) if benefit.vpu else 0.0,
        issue_date=benefit.issue_date,
        issue_age=benefit.issue_age if benefit.issue_age is not None else 0,
        pay_up_date=_charge_end_date(benefit),
        cease_date=benefit.cease_date,
        rating_factor=float(benefit.rating_factor) if benefit.rating_factor else 0.0,
        coi_rate=float(benefit.coi_rate) if benefit.coi_rate else None,
        is_active=not _benefit_ceased(benefit, as_of_date),
        renews=str(benefit.renewal_indicator or "").strip() != "0",
    )


def _active_ccv_basis(benefits: list[IllBenefitInfo]) -> tuple[bool, float, float | None]:
    for benefit in benefits:
        if benefit.benefit_type == "A" and benefit.is_active:
            return True, benefit.units, benefit.coi_rate
    return False, 0.0, None


def _ccv_ceased(raw_benefits: list, as_of_date: date, ccv_active: bool) -> bool:
    if ccv_active:
        return False
    return any(
        (benefit.benefit_type_cd or "") == "A" and _benefit_ceased(benefit, as_of_date)
        for benefit in raw_benefits
    )


def build_riders(source: PolicySourceSnapshot) -> list[RiderInfo]:
    """Map non-base LH_COV_PHA rider rows with rider-config metadata."""
    riders = []
    rider_counts = {}
    for rider in source.raw_riders:
        if not _rider_is_projectable(rider, source):
            continue
        rider_plancode = rider.plancode or ""
        rider_counts[rider_plancode] = rider_counts.get(rider_plancode, 0) + 1
        riders.append(_rider_info(source, rider, rider_counts[rider_plancode]))
    return riders


def _rider_is_projectable(rider, source: PolicySourceSnapshot) -> bool:
    rider_plancode = rider.plancode or ""
    return bool(
        rider_plancode
        and rider_plancode != source.plancode
        and not _coverage_is_terminated(rider, source.as_of_date)
    )


def _rider_info(source: PolicySourceSnapshot, rider, occurrence: int) -> RiderInfo:
    rider_plancode = rider.plancode or ""
    rider_config = load_rider_config(rider_plancode)
    rider_face = float(rider.face_amount) if rider.face_amount else 0.0
    rider_units = float(rider.units) if rider.units else rider_face / 1000.0
    return RiderInfo(
        coverage_phase=rider.cov_pha_nbr,
        occurrence=occurrence,
        plancode=rider_plancode,
        issue_date=rider.issue_date,
        issue_age=rider.issue_age if rider.issue_age is not None else 0,
        rate_sex=rider.sex_code or "",
        rate_class=rider.rate_class or "",
        face_amount=rider_face,
        units=rider_units,
        vpu=float(rider.vpu) if rider.vpu else 1000.0,
        band=int(_rider_band(source, rider_plancode, rider_face, rider.issue_date)),
        table_rating=rider.table_rating or 0,
        flat_extra=float(rider.flat_extra) if rider.flat_extra else 0.0,
        maturity_date=rider.maturity_date,
        status=rider.cov_status or "",
        premium_rate=float(rider.premium_rate) if rider.premium_rate else None,
        coi_rate=float(rider.coi_rate) if rider.coi_rate else None,
        is_active=True,
        on_primary_insured=source.pi.coverages._covers_primary_insured(rider),
        cov_type=rider_config.cov_type if rider_config is not None else "",
        cease_age_dur=rider_config.cease_age_dur if rider_config is not None else None,
        cease_use_code=rider_config.cease_use_code if rider_config is not None else "",
        description=rider_config.description if rider_config is not None else "",
    )


def _rider_band(source: PolicySourceSnapshot, rider_plancode: str, rider_face: float,
                rider_issue_date) -> int:
    if source.plancode_config.is_iswl:
        # ISWL riders are premium-funded: no rider COI is charged, so no band lookup.
        return 1
    if rider_bands_as_base(rider_plancode):
        return source.band
    raw_rider_band = source.rates_db.get_band(rider_plancode, rider_face, issue_date=rider_issue_date)
    return raw_rider_band if raw_rider_band is not None else 1


def active_rider_benefit_codes(pi) -> str:
    """Comma-delimited active rider plancodes + supplemental benefit codes.

    The premium-paying riders and benefits in force at the valuation date — the
    same summary shown in the illustration test matrix. Reads PolicyInformation
    directly: riders carry a ``plancode``, supplemental benefits a ``benefit_code``.
    A rider/benefit counts as active when it has no cease/terminate date, or that
    date is on/after the valuation date. ``"#"``-type benefits (the ABR accelerated
    riders) are excluded — they carry no premium and load no rate.
    """
    as_of_date = pi.values.valuation_date or pi.activity.issue_date
    codes: list[str] = []

    riders = pi.coverages.get_riders()
    for rider in riders:
        if as_of_date is not None and not _active_as_of(rider, as_of_date):
            continue
        code = str(getattr(rider, "plancode", "") or "").strip()
        if code:
            codes.append(code)

    benefits = pi.benefits.get_benefits()
    for benefit in benefits:
        if as_of_date is not None and not _active_as_of(benefit, as_of_date):
            continue
        if str(getattr(benefit, "benefit_type_cd", "") or "").strip() == "#":
            continue  # premium-less ABR accelerated rider
        code = str(getattr(benefit, "benefit_code", "") or "").strip()
        if code:
            codes.append(code)

    return ", ".join(codes)


def coverage_segment_data_warnings(pi) -> list[str]:
    """Flag blank CyberLife fields before illustration defaults mask them."""
    as_of_date = pi.values.valuation_date or date.today()  # noqa: DTZ011
    incomplete_segments: list[str] = []

    for coverage in pi.coverages.get_base_coverages():
        if _coverage_is_terminated(coverage, as_of_date):
            continue

        missing_fields: list[str] = []
        if _is_blank(coverage.face_amount):
            missing_fields.append("Current Specified Amount")
        if _is_blank(coverage.rate_class):
            missing_fields.append("Rate Class")
        if _is_blank(coverage.issue_age):
            missing_fields.append("Issue Age")

        if missing_fields:
            phase = coverage.cov_pha_nbr
            incomplete_segments.append(
                f"Segment {phase}: {', '.join(missing_fields)}"
            )

    if not incomplete_segments:
        return []
    return [
        "CyberLife coverage data is incomplete: "
        + "; ".join(incomplete_segments)
        + "."
    ]


def _active_as_of(item, as_of_date) -> bool:
    cease_date = getattr(item, "cease_date", None) or getattr(item, "terminate_date", None)
    return cease_date is None or cease_date >= as_of_date


# ── Private helpers ───────────────────────────────────────────


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _translate_sex(code: str) -> str:
    """Translate sex code from DB2/PI to rate sex."""
    code = (code or "").strip().upper()
    if code in ("M", "1"):
        return "M"
    if code in ("F", "2"):
        return "F"
    if code in ("U", "0"):
        return "U"
    return code


def _completed_months(start: date, end: date) -> int:
    """Whole months from ``start`` to ``end``, with month-end clamped
    monthliversaries counted (issue 7/31 -> 2/29 is 7 months; E14)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end < start + relativedelta(months=months):
        months -= 1
    return max(months, 0)


def coverage_or_benefit_matured(obj, as_of) -> bool:
    """True when a coverage/benefit has matured or ceased by ``as_of``.

    A presentation helper for the Policy / Inputs tabs to de-emphasize riders and
    benefits no longer in force. Broader than the engine's exclusion: it keys off
    any of cease / maturity / terminate dates, so a matured-but-not-terminated
    rider is still flagged. A date in the FUTURE is in force, so not matured.
    """
    if as_of is None:
        return False
    for attr in ("cease_date", "maturity_date", "terminate_date"):
        when = getattr(obj, attr, None)
        if when is not None and when <= as_of:
            return True
    return False


def _coverage_is_terminated(coverage, as_of_date: date) -> bool:
    status = str(
        getattr(coverage, "nxt_chg_typ_cd", "")
        or getattr(coverage, "cov_status", "")
        or ""
    ).strip()
    cease_date = getattr(coverage, "nxt_chg_dt", None)
    terminate_date = getattr(coverage, "terminate_date", None)

    if terminate_date and terminate_date <= as_of_date:
        return True
    if status == "0":
        return cease_date is None or cease_date <= as_of_date
    return False


def _translate_dbo(code: str) -> str:
    """Translate death benefit option code."""
    code = (code or "").strip()
    mapping = {"1": "A", "2": "B", "3": "C", "A": "A", "B": "B", "C": "C"}
    return mapping.get(code, "A")


def _translate_doli(code: str) -> str:
    """Translate def_of_life_ins_code: 1/2/4 -> GPT, 3/5 -> CVAT."""
    code = (code or "").strip()
    if not code:
        return ""
    if code in ("1", "2", "4"):
        return "GPT"
    if code in ("3", "5"):
        return "CVAT"
    return "GPT"
