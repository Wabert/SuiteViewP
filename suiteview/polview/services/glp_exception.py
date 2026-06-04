from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.calc_engine import IllustrationEngine, ProjectionTiming
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.core.rate_loader import load_rates
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.illustration.models.policy_data import IllustrationPolicyData


@dataclass
class GlpForecastAvailability:
    available: bool
    message: str
    policy: IllustrationPolicyData | None = None


@dataclass
class PremiumAdjustmentSinceValuation:
    gross_premium: float = 0.0
    net_premium: float = 0.0


@dataclass
class GlpForecastRow:
    forecast_date: date | None
    policy_year: int
    policy_month: int
    premium: float
    monthly_deduction: float
    interest_credited: float
    account_value: float


@dataclass
class GlpExceptionResult:
    current_valuation_date: date | None
    account_value: float
    premiums_paid_to_date: float
    premiums_since_valuation_date: float
    adjusted_account_value: float
    adjusted_premiums_paid_to_date: float
    accumulated_withdrawals: float
    glp: float
    gsp: float
    accumulated_glp: float
    months_to_target_date: int
    total_monthly_deductions_to_target_date: float
    total_required_premium_before_load: float
    premium_load_percent: float
    flat_fee: float
    total_required_premium_after_load: float
    accumulated_glp_prior_to_target: float
    premium_td_on_target_date: float
    adjustment_to_accum_glp_pre_calc: float
    new_glp: float | None
    adjustment_to_accum_glp: float
    new_accum_glp: float
    glp_adjustment_message: str
    force_out_required: bool
    force_out_amount: float
    forecast_rows: list[GlpForecastRow]


def is_glp_exception_eligible(policy) -> bool:
    if not policy or not getattr(policy, "exists", False):
        return False
    product_type = str(getattr(policy, "product_type", "") or "").upper()
    if product_type not in {"UL", "IUL", "ISWL", "SGUL", "VUL"}:
        return False
    doli_code = str(getattr(policy, "def_of_life_ins_code", "") or "").strip()
    doli_desc = str(getattr(policy, "def_of_life_ins_description", "") or "").upper()
    return doli_code in {"1", "2", "4"} or "GUIDELINE" in doli_desc or doli_desc.startswith("GP")


def check_forecast_availability(policy) -> GlpForecastAvailability:
    if not is_glp_exception_eligible(policy):
        return GlpForecastAvailability(False, "GLP Exception is available only for UL policies using Guideline Premium.")

    try:
        ill_policy = build_illustration_data(
            policy.policy_number,
            region=getattr(policy, "region", "CKPR") or "CKPR",
            company_code=getattr(policy, "company_code", "") or None,
        )
        config = load_plancode(ill_policy.plancode)
        rates = load_rates(ill_policy, config)
    except Exception as exc:
        return GlpForecastAvailability(False, f"Forecast data could not be loaded: {exc}")

    missing = []
    for segment in ill_policy.segments:
        if not segment.is_base:
            continue
        if not rates.segment_coi.get(segment.coverage_phase):
            missing.append(f"Rates not found for cov {segment.coverage_phase} - {ill_policy.plancode}")
        if config.epu_code == "Table" and not rates.segment_epu.get(segment.coverage_phase):
            missing.append(f"EPU rates not found for cov {segment.coverage_phase} - {ill_policy.plancode}")

    for rider in ill_policy.riders:
        if rider.is_active and rider.plancode and not rates.rider_rates.get(rider.export_key):
            missing.append(f"Rates not found for cov {rider.coverage_phase} - {rider.plancode}")

    for benefit in ill_policy.benefits:
        if not benefit.is_active or (benefit.benefit_type or "").startswith("#"):
            continue
        benefit_key = f"{benefit.benefit_type or ''}{benefit.benefit_subtype or ''}"
        if benefit_key and not rates.benefit_coi.get(benefit_key):
            missing.append(f"Rates not found for benefit {benefit_key}")

    if config.mfee == "Table" and not rates.mfee:
        missing.append(f"Monthly fee rates not found for {ill_policy.plancode}")
    if config.premium_load == "Table" and (not rates.tpp or not rates.epp):
        missing.append(f"Premium load rates not found for {ill_policy.plancode}")

    if missing:
        return GlpForecastAvailability(False, "; ".join(missing), ill_policy)
    return GlpForecastAvailability(True, "Data for forecasting is available", ill_policy)


def calculate_glp_exception(policy, target_date: date) -> GlpExceptionResult:
    availability = check_forecast_availability(policy)
    if not availability.available or availability.policy is None:
        raise ValueError(availability.message)

    ill_policy = availability.policy
    valuation_date = ill_policy.valuation_date
    if valuation_date is None:
        raise ValueError("Current valuation date was not found")
    if target_date <= valuation_date:
        raise ValueError("Target inforce date must be after the current valuation date")

    original_account_value = ill_policy.account_value
    original_premiums_paid_to_date = ill_policy.premiums_paid_to_date
    premium_adjustment = _premium_adjustment_since_valuation(policy, valuation_date)
    ill_policy = _policy_with_post_valuation_premiums(ill_policy, premium_adjustment)
    months_to_target = _months_between_exclusive(valuation_date, target_date)
    if months_to_target <= 0:
        raise ValueError("Target date must leave at least one monthly deduction before the target")

    engine = IllustrationEngine()
    no_premium_policy = _policy_with_modal_premium(ill_policy, 0.0)
    baseline = _project_full_horizon(engine, no_premium_policy, months_to_target)
    total_md = sum(state.total_deduction for state in baseline[1:])
    target_state = baseline[-1] if baseline else None
    target_av_before_md = target_state.av_end_of_month if target_state else ill_policy.account_value

    if len(baseline) == months_to_target + 1 and target_state and not target_state.lapsed and target_av_before_md > 0.0:
        return _build_result(
            ill_policy, target_date, months_to_target, total_md,
            0.0, 0.0, 0.0, 0.0, _forecast_rows_from_projection(ill_policy, baseline), premium_adjustment,
            original_account_value, original_premiums_paid_to_date,
        )

    level_premium = _solve_level_premium(ill_policy, months_to_target, engine)
    solved_inputs = _level_premium_inputs(ill_policy, months_to_target, level_premium)
    solved = _project_full_horizon(
        engine,
        _policy_with_modal_premium(ill_policy, 0.0),
        months_to_target,
        future_inputs=solved_inputs,
    )
    projected = solved[1:]
    before_load = sum(state.net_premium for state in projected)
    premium_load = sum(state.target_load + state.excess_load for state in projected)
    flat_fee = sum(state.flat_load for state in projected)
    after_load = sum(state.gross_premium for state in projected)
    premium_load_percent = (premium_load / after_load) if after_load > 0 else 0.0
    forecast_rows = _forecast_rows_from_projection(ill_policy, solved)

    return _build_result(
        ill_policy, target_date, months_to_target, total_md,
        before_load, premium_load_percent, flat_fee, after_load, forecast_rows, premium_adjustment,
        original_account_value, original_premiums_paid_to_date,
    )


def _build_result(
    policy: IllustrationPolicyData,
    target_date: date,
    months_to_target: int,
    total_md: float,
    before_load: float,
    premium_load_percent: float,
    flat_fee: float,
    after_load: float,
    forecast_rows: list[GlpForecastRow],
    premium_adjustment: PremiumAdjustmentSinceValuation,
    original_account_value: float,
    original_premiums_paid_to_date: float,
) -> GlpExceptionResult:
    current_accumulated_glp = policy.accumulated_glp or 0.0
    accumulated_glp_prior_to_target = _accumulated_glp_to_target(policy, target_date)
    premium_td_on_target_date = policy.premiums_paid_to_date + after_load
    pre_calc_adjustment = max(0.0, premium_td_on_target_date - accumulated_glp_prior_to_target)

    new_glp = None
    adjustment = 0.0
    force_out_required = False
    force_out_amount = 0.0
    adjustment_message = ""

    if accumulated_glp_prior_to_target >= premium_td_on_target_date:
        adjustment_message = "NO ADJUSTMENT NEEDED"
    elif after_load <= 0.0:
        force_out_required = True
        force_out_amount = premium_td_on_target_date - accumulated_glp_prior_to_target
    else:
        adjustment_basis = current_accumulated_glp if policy.glp < 0.0 else accumulated_glp_prior_to_target
        new_glp = 0.0 if policy.glp < 0.0 else policy.glp
        adjustment = max(0.0, premium_td_on_target_date - adjustment_basis)

    new_accum_glp = current_accumulated_glp + adjustment
    return GlpExceptionResult(
        current_valuation_date=policy.valuation_date,
        account_value=original_account_value,
        premiums_paid_to_date=original_premiums_paid_to_date,
        premiums_since_valuation_date=premium_adjustment.gross_premium,
        adjusted_account_value=policy.account_value,
        adjusted_premiums_paid_to_date=policy.premiums_paid_to_date,
        accumulated_withdrawals=policy.withdrawals_to_date,
        glp=policy.glp,
        gsp=policy.gsp,
        accumulated_glp=current_accumulated_glp,
        months_to_target_date=months_to_target,
        total_monthly_deductions_to_target_date=total_md,
        total_required_premium_before_load=before_load,
        premium_load_percent=premium_load_percent,
        flat_fee=flat_fee,
        total_required_premium_after_load=after_load,
        accumulated_glp_prior_to_target=accumulated_glp_prior_to_target,
        premium_td_on_target_date=premium_td_on_target_date,
        adjustment_to_accum_glp_pre_calc=pre_calc_adjustment,
        new_glp=new_glp,
        adjustment_to_accum_glp=adjustment,
        new_accum_glp=new_accum_glp,
        glp_adjustment_message=adjustment_message,
        force_out_required=force_out_required,
        force_out_amount=force_out_amount,
        forecast_rows=forecast_rows,
    )

def _forecast_rows_from_projection(
    policy: IllustrationPolicyData,
    projection,
) -> list[GlpForecastRow]:
    if not projection:
        return []
    first_state = projection[0]
    rows = [
        GlpForecastRow(
            forecast_date=first_state.date,
            policy_year=first_state.policy_year,
            policy_month=first_state.policy_month,
            premium=0.0,
            monthly_deduction=0.0,
            interest_credited=0.0,
            account_value=policy.account_value,
        ),
    ]
    rows.extend(
        GlpForecastRow(
            forecast_date=state.date,
            policy_year=state.policy_year,
            policy_month=state.policy_month,
            premium=state.gross_premium,
            monthly_deduction=state.total_deduction,
            interest_credited=state.interest_credited,
            account_value=state.av_end_of_month,
        )
        for state in projection[1:]
    )
    return rows


def _solve_level_premium(policy: IllustrationPolicyData, months: int, engine: IllustrationEngine) -> float:
    if policy.account_value < 1.0 and months <= 1:
        return 0.0

    low = 0.0
    high = max(policy.system_monthly_deduction, policy.glp / 12.0, 100.0)

    def ending_av(level: float) -> float:
        projected = _project_full_horizon(
            engine,
            _policy_with_modal_premium(policy, 0.0),
            months=months,
            future_inputs=_level_premium_inputs(policy, months, level),
        )
        if len(projected) <= months:
            return -1.0
        return projected[-1].av_end_of_month

    while ending_av(high) < 1.0:
        high *= 2.0
        if high > 10_000_000.0:
            raise ValueError("Could not solve required premium below $10,000,000 monthly")

    for _ in range(40):
        mid = (low + high) / 2.0
        if ending_av(mid) >= 1.0:
            high = mid
        else:
            low = mid
    return high


def _project_full_horizon(
    engine: IllustrationEngine,
    policy: IllustrationPolicyData,
    months: int,
    future_inputs: IllustrationInputSet | None = None,
):
    return engine.project(
        policy,
        months=months,
        future_inputs=future_inputs,
        timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
        stop_on_lapse=False,
    )


def _level_premium_inputs(policy: IllustrationPolicyData, months: int, amount: float) -> IllustrationInputSet:
    dated_transactions = []
    if policy.issue_date is not None and months > 0:
        first_level_offset = 1
        if policy.account_value < 1.0:
            first_projection_date = policy.issue_date + relativedelta(months=policy.duration)
            dated_transactions.append(
                DatedTransaction(
                    kind=TransactionKind.PREMIUM,
                    effective_date=first_projection_date,
                    amount=1.0 - policy.account_value,
                    subtype="catch_up_to_one",
                )
            )
            first_level_offset = 2
        for offset in range(first_level_offset, months + 1):
            premium_date = policy.issue_date + relativedelta(months=policy.duration + offset - 1)
            dated_transactions.append(
                DatedTransaction(
                    kind=TransactionKind.PREMIUM,
                    effective_date=premium_date,
                    amount=amount,
                    subtype="level",
                )
            )
    return IllustrationInputSet(dated_transactions=dated_transactions)


def _policy_with_modal_premium(policy: IllustrationPolicyData, modal_premium: float) -> IllustrationPolicyData:
    policy_copy = IllustrationPolicyData(**policy.__dict__)
    policy_copy.modal_premium = modal_premium
    return policy_copy


def _policy_with_post_valuation_premiums(
    policy: IllustrationPolicyData,
    premium_adjustment: PremiumAdjustmentSinceValuation,
) -> IllustrationPolicyData:
    policy_copy = IllustrationPolicyData(**policy.__dict__)
    policy_copy.account_value += premium_adjustment.net_premium
    policy_copy.premiums_paid_to_date += premium_adjustment.gross_premium
    policy_copy.cost_basis += premium_adjustment.gross_premium
    return policy_copy


def _premium_adjustment_since_valuation(policy, valuation_date: date) -> PremiumAdjustmentSinceValuation:
    premium_codes = {"PR", "PA", "PI", "PB", "PN", "PW", "PT", "PF"}
    adjustment = PremiumAdjustmentSinceValuation()
    try:
        rows = policy.fetch_table("FH_FIXED")
    except Exception:
        rows = []

    for row in rows:
        entry_date = _parse_transaction_date(row.get("ENTRY_DT") or row.get("ENT_DT") or row.get("ASOF_DT"))
        if entry_date is None or entry_date <= valuation_date:
            continue
        trans_code = _transaction_code(row)
        if trans_code not in premium_codes:
            continue
        if _is_reversal_or_reversed(row):
            continue

        gross = _amount(row.get("GROSS_AMT") or row.get("TOT_TRS_AMT"))
        net = _amount(row.get("NET_AMT") or row.get("ACC_VAL_GRS_AMT"))
        if gross <= 0 or net <= 0:
            continue
        adjustment.gross_premium += gross
        adjustment.net_premium += net
    return adjustment


def _transaction_code(row: dict) -> str:
    trans = str(row.get("TRANS", "") or "").strip().upper()
    if trans:
        return trans
    trans_type = str(row.get("TRN_TYP_CD", "") or "").strip().upper()
    trans_subtype = str(row.get("TRN_SBY_CD", "") or "").strip().upper()
    return trans_type + trans_subtype


def _is_reversal_or_reversed(row: dict) -> bool:
    rev_ind = str(row.get("FCB0_REV_IND", "") or "").strip()
    rev_appl = str(row.get("FCB2_REV_APPL_IND", "") or "").strip()
    return rev_ind == "1" or rev_appl == "1"


def _amount(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _parse_transaction_date(value) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            continue
    return None


def _months_between_exclusive(start: date, target: date) -> int:
    months = 0
    current = start + relativedelta(months=1)
    while current < target:
        months += 1
        current += relativedelta(months=1)
    return months


def _accumulated_glp_to_target(policy: IllustrationPolicyData, target_date: date) -> float:
    accumulated_glp = policy.accumulated_glp or 0.0
    if policy.issue_date is None or policy.valuation_date is None:
        return accumulated_glp

    anniversary = policy.issue_date + relativedelta(years=policy.policy_year)
    while anniversary <= policy.valuation_date:
        anniversary += relativedelta(years=1)
    while anniversary < target_date:
        accumulated_glp += policy.glp
        anniversary += relativedelta(years=1)
    return accumulated_glp