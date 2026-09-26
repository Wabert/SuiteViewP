"""UL Illustration projection engine and canonical monthly pipeline.

Public API::

    engine = IllustrationEngine()
    results = engine.project(policy, months=12)  # -> list[MonthlyState]

Canonical projected-month step order:

1. advance counters and carry beginning values;
2. capitalize loan interest and, for CyberLife monthliversary timing only,
   credit interest before withdrawal;
3. process withdrawal;
4. apply dated policy changes and refresh target/guideline details when the
   timing convention permits them;
5. apply guideline force-out, resolve requested premiums and loan cash flows;
6. compute premium allowances, apply accepted premium, deduct monthly charges
   and any GP/monthly-deduction exception premium;
7. apply new loans, credit post-deduction interest for illustration timing,
   accrue loan interest, calculate shadow account values and evaluate lapse;
8. build the ``MonthlyState`` ledger row.

Timing conventions preserve the known source-system differences:

========================  ======================  ==========================
Step                      ILLUSTRATION            CYBERLIFE_MONTHLIVERSARY
========================  ======================  ==========================
Counters                  issue-anchored          calendar monthliversary
Interest timing           post-deduction          pre-withdrawal
Policy changes            yes                     rejected/skipped
Target refresh/recalc      yes                     carry prior details
WAIR/shadow               yes                     skipped
Lapse                     full protection stack   simple AV <= 0 test
7-pay withdrawals          premium minus gross WD  premiums only
========================  ======================  ==========================
"""
from __future__ import annotations

import calendar
import copy
import logging
import math
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from datetime import date
from enum import Enum
from typing import Dict, List, Literal, Optional

from dateutil.relativedelta import relativedelta

from suiteview.illustration.constants import (
    DAYS_PER_YEAR,
    DB_OPTION_INCREASING,
    DB_OPTION_LEVEL,
    DB_OPTION_RETURN_OF_PREMIUM,
    LAPSE_BASIS_ACCOUNT_VALUE,
    LAPSE_BASIS_SURRENDER_VALUE,
    MONEY_EPSILON,
    MONTHS_PER_YEAR,
    PER_THOUSAND,
    SA_BASIS_ORIGINAL,
)
from suiteview.illustration.core.bonus_rates import BonusConfig, load_bonus_config
from suiteview.illustration.core.corridor_rates import get_corridor_factor
from suiteview.illustration.core.input_applier import apply_cash_flow_inputs
from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.illustration.core.interest_calc import credit_interest
from suiteview.illustration.core.iul_crediting import (
    IULCreditingContext,
    TavInput,
    build_iul_context,
    cap_wair,
    monthly_asset_charge,
    project_tav,
    variable_loan_accrual_rate,
    wair_interest,
    weighted_average_rate,
)
from suiteview.illustration.core.lapse import (
    issue_no_lapse_years,
    lapse_value_for_month,
)
from suiteview.illustration.core.loan_handler import (
    LoanState,
    LoanStepInput,
    accrue_loan_interest,
    apply_new_fixed_loan,
    capitalize_loans,
    repay_loan,
)
from suiteview.illustration.core.mec import seven_pay_backtest, seven_pay_limit_exceeded
from suiteview.illustration.core.monthly_deduction import (
    _at_or_after_policy_maturity,
    _coverage_year,
    _rate_from_schedule,
    _round_near,
    calculate_deduction,
)
from suiteview.illustration.core.premium_allowance import (
    PremiumAllowanceInput,
    PremiumAllowances,
    compute_premium_allowances,
)
from suiteview.illustration.core.premium_handler import apply_premium
from suiteview.illustration.core.rate_loader import (
    IllustrationRates,
    _load_benefit_coi_rates,
    get_rate,
    load_coverage_coi_rates,
    load_rates,
)
from suiteview.illustration.core.shadow_calc import ShadowInput, calculate_shadow
from suiteview.illustration.core.target_premium import (
    build_target_detail_snapshots,
    compute_target_premiums,
    floor_monthly_cent,
    target_actives_signature,
    truncate_monthly_mtp,
)
from suiteview.illustration.core.withdrawal_handler import (
    WithdrawalResult,
    compute_withdrawal,
)
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    PolicyChangeEvent,
    PolicyChangeKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
    rider_active_on,
)

logger = logging.getLogger(__name__)


class ProjectionTiming(str, Enum):
    ILLUSTRATION = "illustration"
    CYBERLIFE_MONTHLIVERSARY = "cyberlife_monthliversary"


@dataclass(frozen=True)
class TimingConvention:
    """Controls the few actuarial timing differences between month pipelines."""

    name: str
    counter_timing: Literal["issue_anchored", "monthliversary"]
    interest_timing: Literal["pre_withdrawal", "post_deduction"]
    supports_policy_changes: bool
    refresh_targets: bool
    guideline_recalc: bool
    full_lapse_protection: bool
    shadow_enabled: bool
    wair_enabled: bool
    withdrawal_reduces_7pay: bool


ILLUSTRATION_TIMING = TimingConvention(
    name="illustration",
    counter_timing="issue_anchored",
    interest_timing="post_deduction",
    supports_policy_changes=True,
    refresh_targets=True,
    guideline_recalc=True,
    full_lapse_protection=True,
    shadow_enabled=True,
    wair_enabled=True,
    withdrawal_reduces_7pay=True,
)

CYBERLIFE_MONTHLIVERSARY_TIMING = TimingConvention(
    name="cyberlife_monthliversary",
    counter_timing="monthliversary",
    interest_timing="pre_withdrawal",
    supports_policy_changes=False,
    refresh_targets=False,
    guideline_recalc=False,
    full_lapse_protection=False,
    shadow_enabled=False,
    wair_enabled=False,
    withdrawal_reduces_7pay=False,
)


@dataclass(frozen=True)
class MonthContext:
    """Immutable inputs for one projected month."""

    state: MonthlyState
    policy: IllustrationPolicyData
    config: PlancodeConfig
    rates: IllustrationRates
    bonus: BonusConfig
    month_inputs: object | None
    options: IllustrationOptions
    policy_changes: object | None = None
    iul_ctx: Optional[IULCreditingContext] = None


@dataclass
class MonthWork:
    """Mutable working state passed between named month-pipeline steps."""

    next_year: int = 0
    next_month: int = 0
    duration: int = 0
    attained_age: int = 0
    month_date: Optional[date] = None
    is_anniversary: bool = False
    rate_year: int = 0
    lapse_value: str = LAPSE_BASIS_SURRENDER_VALUE
    premiums_ytd: float = 0.0
    premiums_to_date: float = 0.0
    cost_basis: float = 0.0
    withdrawals_to_date: float = 0.0
    av: float = 0.0
    bo_av: float = 0.0
    adv_reg_factor: float = 1.0
    adv_pref_factor: float = 1.0
    adv_reg_ln_int: float = 0.0
    adv_pref_ln_int: float = 0.0


@dataclass
class InforceWork:
    """Intermediate values for the month-zero inforce ledger row."""

    rate_year: int = 0
    month_date: Optional[date] = None
    monthly_mtp: float = 0.0
    mtp_detail: Dict[str, object] = dataclass_field(default_factory=dict)
    ctp_detail: Dict[str, object] = dataclass_field(default_factory=dict)
    md_check_av_before_deduction: float = 0.0
    ded: object | None = None
    intr: object | None = None
    wair_held: float = 0.0
    wair_rate: float = 0.0
    wair_swam: float = 0.0
    wair_tav: float = 0.0
    loan: LoanState | None = None
    loan_cap_repay: Dict[str, object] = dataclass_field(default_factory=dict)
    shd: object | None = None
    accumulated_mtp: float = 0.0
    accum_mtp_less_prem: float = 0.0
    snet_active: bool = False
    shadow_protection: bool = False
    surrender_charge: float = 0.0
    scr_rate: float = 0.0
    scr_rates_by_coverage: Dict[int, float] = dataclass_field(default_factory=dict)
    surrender_charges_by_coverage: Dict[int, float] = dataclass_field(default_factory=dict)
    surrender_value: float = 0.0
    ending_sv: float = 0.0
    positive_sv: bool = False
    av_less_loans: float = 0.0


def prepare_run_policy(
    policy: IllustrationPolicyData, options: IllustrationOptions
) -> tuple[IllustrationPolicyData, PlancodeConfig, bool]:
    """Copy the policy and resolve plancode/run-level starting flags."""
    if policy.rollback_requires_shadow_value:
        raise ValueError(
            "Historical shadow account value is unavailable. Enter a verified "
            "historical shadow amount before projecting Value Rollback."
        )
    starting_exception_period = (
        options.recognize_inforce_exception_period
        and policy.in_exception_period
        and not options.guaranteed_assumption
    )
    config = load_plancode(policy.plancode)
    charge_overrides = {
        config_field: getattr(policy, policy_field)
        for policy_field, config_field in (
            ("regular_loan_charge_rate", "loan_charge_rate_guar"),
            ("preferred_loan_charge_rate", "pref_loan_charge_rate_guar"),
        )
        if policy_field in policy.starting_record_fields
    }
    if charge_overrides:
        config = replace(config, **charge_overrides)
    policy = copy.deepcopy(policy)
    if policy.run_from_issue:
        policy.issue_no_lapse_years = issue_no_lapse_years(policy, config)
    return policy, config, starting_exception_period


def validate_projection_timing(
    timing: ProjectionTiming, future_inputs: Optional[IllustrationInputSet]
) -> None:
    """Reject unsupported input combinations for a timing convention."""
    if (
        timing == ProjectionTiming.CYBERLIFE_MONTHLIVERSARY
        and future_inputs is not None
        and future_inputs.policy_changes
    ):
        raise ValueError(
            "ProjectionTiming.CYBERLIFE_MONTHLIVERSARY does not support "
            "policy changes; policy changes are not supported on the "
            "CyberLife-monthliversary path."
        )


def initialize_run_from_issue_targets(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    options: IllustrationOptions,
) -> None:
    """Recompute targets/regulatory premiums for issue-mode projections."""
    if not policy.run_from_issue:
        return
    targets = compute_target_premiums(policy, config, as_of=policy.issue_date)
    policy.mtp = targets.mtp_annual / MONTHS_PER_YEAR
    policy.ctp = targets.ctp_annual
    guideline = _solve_guideline_state(
        policy,
        config,
        policy.issue_age,
        policy.issue_date,
        options,
        starting_av=0.0,
        active_as_of=policy.issue_date,
    )
    policy.glp = floor_monthly_cent(guideline.glp)
    policy.gsp = floor_monthly_cent(guideline.gsp)
    policy.tamra_7pay_level = floor_monthly_cent(guideline.seven_pay)


def resolve_bonus_config(
    policy: IllustrationPolicyData, bonus_override: Optional[BonusConfig]
) -> BonusConfig:
    """Load or override the plan interest-bonus configuration."""
    if bonus_override is not None:
        return bonus_override
    val_date = (
        policy.illustration_date
        if policy.run_from_issue and policy.illustration_date
        else policy.valuation_date or policy.issue_date
    )
    return load_bonus_config(policy.plancode, val_date)


def projection_month_count(policy: IllustrationPolicyData, months: Optional[int]) -> int:
    """Number of projected months, capped at the maturity month."""
    remaining_years = policy.maturity_age - policy.attained_age
    remaining_months = max(remaining_years * 12 - policy.policy_month + 1, 0)
    return remaining_months if months is None else min(months, remaining_months)


def compile_policy_changes_by_duration(
    policy: IllustrationPolicyData, future_inputs: Optional[IllustrationInputSet]
) -> Dict[int, list]:
    """Compile policy changes keyed by projection duration."""
    if future_inputs is not None and not future_inputs.is_empty():
        return _compile_policy_changes(policy, future_inputs.policy_changes)
    return {}


def timing_convention(timing: ProjectionTiming) -> TimingConvention:
    """Map public projection timing to the month-pipeline convention."""
    if timing == ProjectionTiming.CYBERLIFE_MONTHLIVERSARY:
        return CYBERLIFE_MONTHLIVERSARY_TIMING
    return ILLUSTRATION_TIMING


def advance_counters(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> None:
    """Advance date, policy counters and attained age for the next month."""
    state = ctx.state
    policy = ctx.policy
    if convention.counter_timing == "monthliversary" and not policy.run_from_issue:
        prior_date = state.date or policy.valuation_date or policy.issue_date
        work.month_date = prior_date + relativedelta(months=1)
        work.next_year, work.next_month, work.duration = _policy_counters_for_date(
            policy, work.month_date
        )
    else:
        work.next_year, work.next_month = _advance_month(
            state.policy_year, state.policy_month
        )
        work.duration = state.duration + 1
        work.month_date = policy.issue_date + relativedelta(months=work.duration - 1)
    work.lapse_value = lapse_value_for_month(policy, ctx.config, work.duration)
    work.attained_age = policy.issue_age + (work.duration - 1) // 12
    work.is_anniversary = work.next_month == 1
    work.rate_year = work.next_year


def carry_begin_values(ctx: MonthContext, work: MonthWork) -> None:
    """Carry beginning-of-month premium, basis and account-value values."""
    state = ctx.state
    work.premiums_ytd = (
        0.0 if work.is_anniversary else state.premiums_ytd_after_exception
    )
    work.premiums_to_date = state.premiums_to_date_after_exception
    work.cost_basis = state.cost_basis_after_exception
    work.withdrawals_to_date = state.withdrawals_to_date
    work.av = state.av_end_of_month


def capitalize_loans_step(ctx: MonthContext, work: MonthWork) -> None:
    """Capitalize loan interest at anniversaries and carry loan display factors."""
    state = ctx.state
    days_to_next_anniv = _days_to_next_anniversary(
        ctx.policy.issue_date, work.month_date
    )
    work.adv_reg_factor, work.adv_pref_factor = _advance_loan_factors(
        ctx.config, days_to_next_anniv
    )
    work.cap_loan = capitalize_loans(
        state.end_rg_loan_princ,
        state.end_rg_loan_accrued,
        state.end_pf_loan_princ,
        state.end_pf_loan_accrued,
        state.end_vbl_loan_princ,
        state.end_vbl_loan_accrued,
        work.is_anniversary,
        config=ctx.config,
        adv_reg_factor=work.adv_reg_factor,
        adv_pref_factor=work.adv_pref_factor,
    )
    work.adv_reg_ln_int = work.cap_loan.adv_reg_int
    work.adv_pref_ln_int = work.cap_loan.adv_pref_int


def credit_interest_pre_withdrawal(ctx: MonthContext, work: MonthWork) -> None:
    """Credit interest before withdrawal for CyberLife monthliversary timing."""
    work.intr = credit_interest(
        ctx.state.av_end_of_month,
        ctx.policy,
        ctx.config,
        ctx.rates,
        ctx.bonus,
        work.rate_year,
        work.attained_age,
        work.month_date,
        reg_loan_balance=work.cap_loan.rg_loan_princ,
        pref_loan_balance=work.cap_loan.pf_loan_princ,
        exact_days_interest=ctx.options.exact_days_interest,
    )
    work.av = work.intr.av_end_of_month


def process_withdrawal_step(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> None:
    """Apply requested withdrawal and update AV, cost basis and withdrawal totals."""
    work.wd = _process_withdrawal(WithdrawalInput(
        state=ctx.state,
        policy=ctx.policy,
        config=ctx.config,
        rates=ctx.rates,
        rate_year=work.rate_year,
        attained_age=work.attained_age,
        month_date=work.month_date,
        av=work.av,
        cost_basis=work.cost_basis,
        month_inputs=ctx.month_inputs,
        cap_loan=work.cap_loan,
        is_anniversary=work.is_anniversary,
        options=ctx.options,
        defer_guideline_recalc=(
            convention.guideline_recalc and bool(ctx.policy_changes)
        ),
    ))
    work.av = work.wd.av_post_withdrawal
    work.bo_av = work.av
    work.cost_basis = work.wd.cost_basis_after_wd
    work.withdrawals_to_date = work.wd.withdrawals_to_date


def apply_policy_changes(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> None:
    """Apply dated policy changes and capture coverage/guideline recalc detail."""
    state = ctx.state
    policy = ctx.policy
    work.tamra_reset = False
    work.policy_change_av_reduction = work.wd.gross_withdrawal
    work.dbo_change_detail = {}
    work.face_change_detail = {}
    work.guideline_recalc = dict(work.wd.guideline_recalc)
    if not convention.supports_policy_changes:
        work.cov_after_change = _coverage_after_change_snapshot(
            policy,
            ctx.config,
            work.month_date,
            work.wd.gross_withdrawal,
            state.coverage_after_change,
        )
        return

    guideline_before = work.wd.guideline_before
    guideline_before_pv_detail = work.wd.guideline_before_pv_detail
    guideline_changes = 1 if work.wd.face_decrease > MONEY_EPSILON else 0
    recalc_change = (
        PolicyChangeEvent(
            kind=PolicyChangeKind.FACE_AMOUNT,
            effective_date=work.month_date,
            value=policy.total_face,
        )
        if guideline_changes
        else None
    )
    if ctx.policy_changes:
        for change in sorted(
            ctx.policy_changes,
            key=lambda item: _POLICY_CHANGE_ORDER.get(item.kind, 99),
        ):
            outcome = _apply_policy_change(
                policy,
                ctx.config,
                change,
                work.attained_age,
                work.month_date,
                ctx.rates,
                work.rate_year,
                work.av,
                options=ctx.options,
                defer_guideline_recalc=True,
                capture_guideline_before=guideline_before is None,
            )
            work.av += outcome.av_adjustment
            work.policy_change_av_reduction += max(0.0, -outcome.av_adjustment)
            work.tamra_reset = work.tamra_reset or outcome.material_change
            work.dbo_change_detail.update(outcome.dbo_detail)
            work.face_change_detail.update(outcome.face_detail)
            if outcome.coverage_changed:
                guideline_changes += 1
                if recalc_change is None:
                    recalc_change = change
            if guideline_before is None and outcome.guideline_before is not None:
                guideline_before = outcome.guideline_before
                guideline_before_pv_detail = outcome.guideline_before_pv_detail

        if guideline_changes and recalc_change is not None:
            if guideline_changes > 1:
                recalc_change = PolicyChangeEvent(
                    kind=recalc_change.kind,
                    effective_date=work.month_date,
                    value=recalc_change.value,
                    metadata={"change_label": "Combined Policy Changes"},
                )
            work.guideline_recalc = _recalc_guideline_on_change(
                policy,
                ctx.config,
                recalc_change,
                work.attained_age,
                change_date=work.month_date,
                before=guideline_before,
                av=work.av,
                material_change=work.tamra_reset,
                options=ctx.options,
                before_pv_detail=guideline_before_pv_detail,
            )

    if work.tamra_reset:
        policy.tamra_7pay_start_date = work.month_date

    work.cov_after_change = _coverage_after_change_snapshot(
        policy,
        ctx.config,
        work.month_date,
        work.policy_change_av_reduction,
        state.coverage_after_change,
    )


def refresh_targets(ctx: MonthContext, convention: TimingConvention, work: MonthWork) -> None:
    """Refresh target-premium details and carry safety-net timing flags."""
    state = ctx.state
    policy = ctx.policy
    if (
        convention.refresh_targets
        and (
            not state.mtp_detail
            or ctx.policy_changes
            or work.wd.face_decrease > MONEY_EPSILON
            or target_actives_signature(policy, work.month_date)
            != target_actives_signature(policy, state.date)
        )
    ):
        work.mtp_detail, work.ctp_detail = build_target_detail_snapshots(
            policy, compute_target_premiums(policy, ctx.config, as_of=work.month_date)
        )
    else:
        work.mtp_detail = state.mtp_detail
        work.ctp_detail = state.ctp_detail

    work.monthly_mtp = truncate_monthly_mtp(policy.mtp)
    work.pw_monthly_mtp = _round_near(policy.mtp, 2)
    work.accumulated_mtp = state.accumulated_mtp + work.monthly_mtp
    if policy.map_cease_date is not None:
        work.within_snet = work.month_date <= policy.map_cease_date
    else:
        work.within_snet = work.next_year <= ctx.config.snet_period
    work.past_snet = not work.within_snet
    work.prior_exception_mode = state.gp_exception_mode


def apply_guideline_forceout(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> None:
    """Accumulate guideline premium and apply any required force-out."""
    state = ctx.state
    policy = ctx.policy
    work.accum_glp_prior_amount = state.accumulated_glp
    work.gsp_floored = floor_monthly_cent(policy.gsp)
    work.accumulated_glp = _accumulate_guideline_premium(
        state, policy, work.is_anniversary, work.attained_age
    )
    if convention.guideline_recalc and work.attained_age < 100:
        work.accumulated_glp += float(
            work.guideline_recalc.get("accum_glp_adjustment", 0.0) or 0.0
        )
    if convention.guideline_recalc and work.guideline_recalc:
        _record_accum_glp_recalc_detail(
            work.guideline_recalc,
            prior_amount=work.accum_glp_prior_amount,
            new_amount=work.accumulated_glp,
            policy_month=work.next_month,
        )
    work.guideline_limit = max(work.gsp_floored, work.accumulated_glp)
    work.withdrawals_before_forceout = work.withdrawals_to_date
    (
        work.guideline_forceout,
        work.withdrawals_to_date,
        work.av,
    ) = _apply_guideline_forceout(
        work.gsp_floored,
        work.accumulated_glp,
        work.premiums_to_date,
        work.withdrawals_to_date,
        work.av,
        enabled=ctx.options.force_out_enabled,
        has_guideline_limit=policy.is_gpt,
        prior_exception_mode=work.prior_exception_mode,
    )


def resolve_requested_premium(ctx: MonthContext, work: MonthWork) -> None:
    """Resolve scheduled and lump-sum premiums before loan repayment."""
    state = ctx.state
    work.requested_scheduled, work.requested_lumpsum = _split_requested_premium(
        ctx.policy,
        ctx.config,
        ctx.month_inputs,
        work.attained_age,
        exception_period=state.inforce_exception_period,
    )
    work.b2md_active = _billable_to_md_active(ctx.options, work.next_year)
    if work.b2md_active and state.billable_md_switched:
        work.requested_scheduled = 0.0
        if ctx.month_inputs is not None:
            work.requested_lumpsum = max(
                0.0,
                work.requested_lumpsum - ctx.month_inputs.billable_to_md_premium,
            )
    work.has_loan_balance = _loan_balance_for_levelizing(work.cap_loan)
    work.boy_loan = work.cap_loan


def apply_cashflows(ctx: MonthContext, work: MonthWork) -> None:
    """Apply loan repayments, loan-to-premium remainders and premium diversion."""
    work.cash_flows = apply_cash_flow_inputs(
        work.av,
        work.cap_loan,
        ctx.month_inputs,
        config=ctx.config,
        adv_reg_factor=work.adv_reg_factor,
        adv_pref_factor=work.adv_pref_factor,
        apply_prem_to_loan=ctx.options.apply_prem_to_loan,
        excess_repayment_to_premium=(
            ctx.options.apply_excess_repayment_as_premium
            and not ctx.state.inforce_exception_period
        ),
        requested_lumpsum=work.requested_lumpsum,
        requested_scheduled=work.requested_scheduled,
    )
    work.av = work.cash_flows.av
    work.cap_loan = work.cash_flows.loan_state
    work.loan_cap_repay_detail = work.cash_flows.loan_cap_repay


def compute_allowances(ctx: MonthContext, work: MonthWork) -> None:
    """Compute TEFRA/TAMRA premium allowances for this month."""
    state = ctx.state
    policy = ctx.policy
    work.accumulated_7pay_base = (
        0.0 if getattr(work, "tamra_reset", False) else state.accumulated_7pay
    )
    work.tamra_year = _tamra_year(policy, work.month_date)
    work.tamra_moy = _tamra_month_of_year(policy, work.month_date)
    work.pc_policy, work.pc_tamra, work.payment_mode = _payment_counts(
        state, policy, work.month_date, work.next_month, ctx.month_inputs
    )
    work.beginning_of_year = (
        work.is_anniversary or state.payment_count_policy_year == 0
    )
    work.allowances = compute_premium_allowances(PremiumAllowanceInput(
        is_cvat=policy.is_cvat,
        is_gpt=policy.is_gpt,
        tefra_force=ctx.options.guideline_cap_enabled,
        tamra_force=_tamra_force(ctx.options, policy),
        mec_bypass=policy.is_mec,
        guideline_limit=work.guideline_limit,
        prem_less_wd=work.premiums_to_date - work.withdrawals_before_forceout,
        force_out=work.guideline_forceout,
        loan_repay_from_forceout=0.0,
        seven_pay_level=policy.tamra_7pay_level,
        amount_in_7pay=work.accumulated_7pay_base,
        tamra_year=work.tamra_year,
        tamra_month_of_year=work.tamra_moy,
        policy_month=work.next_month,
        npt_premium=0.0,
        tamra_reset=getattr(work, "tamra_reset", False),
        requested_scheduled=work.requested_scheduled,
        requested_lumpsum=work.requested_lumpsum,
        payment_count_policy_year=work.pc_policy,
        payment_count_tamra_year=work.pc_tamra,
        has_loan_balance=work.has_loan_balance,
        levelizing_premium=ctx.options.levelizing_premium,
        beginning_of_year=work.beginning_of_year,
        policy_anniversary=work.is_anniversary,
        prior_scheduled_prem_cap=state.scheduled_prem_cap,
        prior_scheduled_cap_by_guideline=state.scheduled_cap_by_guideline,
        prior_scheduled_cap_by_tamra=state.scheduled_cap_by_tamra,
        loan_repay_from_lumpsum=work.cash_flows.loan_repay_from_lumpsum,
        loan_repay_from_scheduled=work.cash_flows.loan_repay_from_scheduled,
        ln_repay_left_over=work.cash_flows.ln_repay_left_over,
        prior_guideline_limit_reached=state.guideline_limit_reached,
        prior_transition_year_active=state.transition_year_active,
    ))


def apply_premium_step(ctx: MonthContext, work: MonthWork) -> None:
    """Apply the accepted premium and expose pre-deduction AV."""
    work.prem = apply_premium(
        work.av,
        ctx.policy,
        ctx.config,
        ctx.rates,
        work.rate_year,
        work.premiums_ytd,
        work.premiums_to_date,
        work.cost_basis,
        gross_premium_override=work.allowances.applied_total_premium,
        premium_cap=None,
    )
    work.av = work.prem.av_after_premium
    work.av_before_deduction = work.av


def deduct_monthly_charges(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> None:
    """Deduct monthly charges and IUL asset charge."""
    monthly_mtp = (
        work.pw_monthly_mtp
        if convention == ILLUSTRATION_TIMING
        else work.monthly_mtp
    )
    work.ded = calculate_deduction(
        work.av_before_deduction,
        ctx.policy,
        ctx.config,
        ctx.rates,
        work.rate_year,
        work.attained_age,
        work.prem.premiums_to_date,
        monthly_mtp=monthly_mtp,
        projection_date=work.month_date,
    )
    work.asset_charge = monthly_asset_charge(
        ctx.iul_ctx,
        work.av_before_deduction,
        work.cap_loan.rg_loan_princ,
        work.cap_loan.rg_loan_accrued,
    )
    work.av_after_charge = work.ded.av_after_deduction - work.asset_charge


def _exception_input(
    ctx: MonthContext, work: MonthWork, md_premium_active: bool
) -> ExceptionPremiumInput:
    return ExceptionPremiumInput(
        options=ctx.options,
        policy=ctx.policy,
        config=ctx.config,
        rates=ctx.rates,
        rate_year=work.rate_year,
        av_after_charge=work.av_after_charge,
        coi_rate=work.ded.coi_rate,
        guideline_limit_reached=work.guideline_limit_reached,
        past_snet=work.past_snet,
        prior_exception_mode=work.prior_exception_mode,
        prior_lapsed=ctx.state.lapsed,
        attained_age=work.attained_age,
        md_premium_active=md_premium_active,
        total_deduction=work.ded.total_deduction,
        guideline_limit=work.guideline_limit,
        premiums_to_date=work.prem.premiums_to_date,
        withdrawals_to_date=work.withdrawals_to_date,
        guideline_cap_enabled=ctx.options.guideline_cap_enabled and ctx.policy.is_gpt,
    )


def _update_billable_to_md(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> None:
    work.b2md_switched = ctx.state.billable_md_switched
    if not (
        work.b2md_active
        and not work.b2md_switched
        and not ctx.state.lapsed
        and _b2md_latch_allowed(ctx.options, work.month_date)
    ):
        return
    if convention.full_lapse_protection:
        _, sc_probe, _, _ = _calculate_surrender_charge(
            ctx.policy, ctx.rates, work.rate_year, work.month_date, ctx.config
        )
        probe_debt = work.cap_loan.policy_debt
        snet_probe = (
            (work.prem.premiums_to_date - work.withdrawals_to_date - probe_debt)
            - work.accumulated_mtp >= 0 and work.within_snet
        )
        shadow_probe = (
            ctx.policy.has_shadow_account
            and work.past_snet
            and ctx.state.shadow_eav_less_debt > 0
        )
        sv_probe = (
            work.lapse_value == LAPSE_BASIS_SURRENDER_VALUE
            and work.av_after_charge - sc_probe - probe_debt > 0
        )
        av_probe = (
            work.lapse_value == LAPSE_BASIS_ACCOUNT_VALUE
            and work.av_after_charge - probe_debt > 0
        )
        work.b2md_switched = not (
            snet_probe or shadow_probe or sv_probe or av_probe
        )
    else:
        work.b2md_switched = work.av_after_charge <= 0.0


def apply_exception_premium(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> None:
    """Compute monthly-deduction and GP exception premiums."""
    work.guideline_limit_reached = _guideline_limit_reached(
        ctx.config,
        work.allowances,
        attained_age=work.attained_age,
        beginning_of_year=work.beginning_of_year,
        prior_limit_reached=ctx.state.guideline_limit_reached,
    )
    _update_billable_to_md(ctx, convention, work)
    md_premium_active = (
        _monthly_deduction_premium_active(ctx.options, work.next_year)
        or (work.b2md_active and work.b2md_switched)
    ) and not ctx.state.inforce_exception_period
    work.exception = _compute_exception_premium(
        _exception_input(ctx, work, md_premium_active)
    )
    if work.exception.requires_option_a:
        ctx.policy.db_option = DB_OPTION_LEVEL
        deduct_monthly_charges(ctx, convention, work)
        work.exception = _compute_exception_premium(
            _exception_input(ctx, work, md_premium_active)
        )
    work.av = work.exception.av_after_exception


def apply_new_loans(ctx: MonthContext, work: MonthWork) -> None:
    """Apply new fixed loans after deduction/exception premium processing."""
    loan_cap = None
    if ctx.options.restrict_loans_to_sv:
        _, full_sc_for_loan, _, _ = _calculate_surrender_charge(
            ctx.policy, ctx.rates, work.rate_year, work.month_date, ctx.config
        )
        loan_cap = (
            work.av
            - full_sc_for_loan
            - work.cap_loan.policy_debt
            - ctx.config.md_holdback * work.ded.total_deduction
        )
    work.fixed_loan_state = apply_new_fixed_loan(LoanStepInput(
        loan=work.cap_loan,
        requested_amount=(
            ctx.month_inputs.regular_loan if ctx.month_inputs is not None else 0.0
        ),
        account_value=work.av,
        premiums_to_date=work.prem.premiums_to_date,
        withdrawals_to_date=work.withdrawals_to_date,
        max_loan=loan_cap,
    ))
    work.applied_regular_loan = max(
        0.0, work.fixed_loan_state.rg_loan_princ - work.cap_loan.rg_loan_princ
    )
    work.applied_preferred_loan = max(
        0.0, work.fixed_loan_state.pf_loan_princ - work.cap_loan.pf_loan_princ
    )


def credit_interest_post_deduction(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> None:
    """Credit post-deduction interest and optional WAIR interest."""
    if convention.interest_timing != "post_deduction":
        return
    work.intr = credit_interest(
        work.av,
        ctx.policy,
        ctx.config,
        ctx.rates,
        ctx.bonus,
        work.rate_year,
        work.attained_age,
        work.month_date,
        reg_loan_balance=work.fixed_loan_state.rg_loan_princ,
        pref_loan_balance=work.fixed_loan_state.pf_loan_princ,
        exact_days_interest=ctx.options.exact_days_interest,
    )
    work.wair_tav = work.wair_swam = work.wair_held = work.wair_rate = 0.0
    if ctx.iul_ctx is not None and ctx.iul_ctx.wair_enabled:
        _apply_wair_interest(ctx, work)
    work.av = work.intr.av_end_of_month


def _apply_wair_interest(ctx: MonthContext, work: MonthWork) -> None:
    iul_ctx = ctx.iul_ctx
    uk = iul_ctx.declared_rate + work.intr.bonus_interest_rate
    up = work.intr.effective_annual_rate
    if work.beginning_of_year:
        tavp = project_tav(TavInput(
            begin_av=work.bo_av,
            planned_premium=work.requested_scheduled,
            payments_per_year=work.pc_policy,
            lumpsum=work.requested_lumpsum,
            policy_month=work.next_month,
            fixed_ln_principal=(
                work.boy_loan.rg_loan_princ + work.boy_loan.pf_loan_princ
            ),
            fixed_ln_accrued=(
                work.boy_loan.rg_loan_accrued + work.boy_loan.pf_loan_accrued
            ),
            vbl_ln_principal=work.boy_loan.vbl_loan_princ,
            vbl_ln_accrued=work.boy_loan.vbl_loan_accrued,
            reg_loan_charge_rate=ctx.config.loan_charge_rate_guar,
            vbl_loan_rate=variable_loan_accrual_rate(
                iul_ctx,
                ctx.policy.variable_loan_charge_rate,
                ctx.policy.current_interest_rate,
            ),
            apply_prem_to_loan=ctx.options.apply_prem_to_loan,
            is_cvat=ctx.policy.is_cvat,
            annual_cap=work.allowances.annual_cap_1,
            premium_load=work.prem.tpp_rate,
        ))
        work.wair_tav = tavp.tav_display
        work.wair_swam = work.ded.total_deduction * MONTHS_PER_YEAR
        work.wair_held = weighted_average_rate(
            av=tavp.tav,
            swam=work.wair_swam,
            reg_ln_principal=work.fixed_loan_state.rg_loan_princ,
            reg_ln_accrued=work.fixed_loan_state.rg_loan_accrued,
            pref_ln_principal=work.fixed_loan_state.pf_loan_princ,
            pref_ln_accrued=work.fixed_loan_state.pf_loan_accrued,
            reg_loan_credit_rate=work.intr.reg_loan_credit_rate,
            pref_loan_credit_rate=work.intr.pref_loan_credit_rate,
            declared_plus_bonus=uk,
            blend_plus_bonus=up,
        )
    else:
        work.wair_tav = ctx.state.wair_tav
        work.wair_swam = ctx.state.wair_swam
        work.wair_held = ctx.state.wair_held
    work.wair_rate = cap_wair(iul_ctx, work.wair_held, uk)
    vl = wair_interest(work.av, work.wair_rate, work.intr.days_in_month)
    work.intr = replace(
        work.intr,
        effective_annual_rate=work.wair_rate,
        monthly_interest_rate=(
            (1.0 + work.wair_rate) ** (work.intr.days_in_month / DAYS_PER_YEAR)
            - 1.0
        ),
        reg_impaired_int=0.0,
        pref_impaired_int=0.0,
        unimpaired_int=vl,
        interest_credited=vl,
        av_end_of_month=work.av + vl,
    )


def accrue_loans(ctx: MonthContext, work: MonthWork) -> None:
    """Accrue loan interest after new loans and interest crediting."""
    work.accrual_loan = accrue_loan_interest(
        work.fixed_loan_state,
        ctx.config,
        work.intr.days_in_month,
        variable_loan_accrual_rate(
            ctx.iul_ctx,
            ctx.policy.variable_loan_charge_rate,
            ctx.policy.current_interest_rate,
        ),
    )


def calculate_shadow_step(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> None:
    """Run shadow account processing when the timing convention supports it."""
    if not convention.shadow_enabled:
        work.shd = None
        return
    work.shd = calculate_shadow(ShadowInput(
        prev_shadow_eav=ctx.state.shadow_eav,
        gross_premium=work.prem.gross_premium,
        premiums_ytd=work.prem.premiums_ytd,
        policy=ctx.policy,
        config=ctx.config,
        rates=ctx.rates,
        rate_year=work.rate_year,
        attained_age=work.attained_age,
        days_in_month=work.intr.actual_days_in_month,
        policy_debt=work.accrual_loan.policy_debt,
        shadow_rider_charges=_shadow_rider_charges_from_deduction(
            ctx.policy, work.ded
        ),
        projection_date=work.month_date,
        display_days_in_month=work.intr.days_in_month,
    ))


def evaluate_lapse(ctx: MonthContext, convention: TimingConvention, work: MonthWork) -> None:
    """Evaluate lapse, protection flags, surrender value and terminal rollups."""
    if convention.full_lapse_protection:
        _evaluate_illustration_lapse(ctx, work)
    else:
        _evaluate_cyberlife_lapse(ctx, work)


def _evaluate_illustration_lapse(ctx: MonthContext, work: MonthWork) -> None:
    policy = ctx.policy
    work.accum_mtp_less_prem = (
        work.prem.premiums_to_date - work.withdrawals_to_date
        - work.accrual_loan.policy_debt
    ) - work.accumulated_mtp
    work.snet_active = work.accum_mtp_less_prem >= 0 and work.within_snet
    work.shadow_protection = (
        policy.has_shadow_account
        and work.past_snet
        and work.shd.shadow_eav_less_debt > 0
    )
    (
        work.scr_rate,
        work.surrender_charge,
        work.scr_rates_by_coverage,
        work.surrender_charges_by_coverage,
    ) = _calculate_surrender_charge(
        policy, ctx.rates, work.rate_year, work.month_date, ctx.config
    )
    lapse_check_av = work.exception.av_after_exception
    lapse_check_debt = work.cap_loan.policy_debt
    work.surrender_value = lapse_check_av - work.surrender_charge - lapse_check_debt
    work.ending_db = _ending_death_benefit(ctx, work)
    work.ending_sv = work.av - work.surrender_charge - work.accrual_loan.policy_debt
    work.positive_sv = (
        work.lapse_value == LAPSE_BASIS_SURRENDER_VALUE
        and work.surrender_value > 0
    )
    work.av_less_loans = lapse_check_av - lapse_check_debt
    av_loans_test = (
        work.lapse_value == LAPSE_BASIS_ACCOUNT_VALUE and work.av_less_loans > 0
    )
    work.exception_protection = (
        work.exception.mode and work.surrender_value > -0.0001
    )
    protected = _illustration_lapse_protected(work, av_loans_test)
    work.lapsed = ctx.state.lapsed or not protected
    if ctx.options is not None and ctx.options.no_lapse:
        work.lapsed = False
    work.accumulated_7pay = work.accumulated_7pay_base + (
        work.prem.gross_premium - work.wd.gross_withdrawal
        if work.tamra_year <= 7
        else 0.0
    )


def _ending_death_benefit(ctx: MonthContext, work: MonthWork) -> float:
    policy = ctx.policy
    edb_wo_corr = policy.total_face
    if policy.db_option == DB_OPTION_INCREASING:
        edb_wo_corr += max(0.0, work.av)
    elif policy.db_option == DB_OPTION_RETURN_OF_PREMIUM:
        edb_wo_corr += max(
            0.0, work.prem.premiums_to_date - work.withdrawals_to_date
        )
    edb_corr = (
        max(0.0, math.floor(work.av * work.ded.corridor_rate + 1e-6) - edb_wo_corr)
        if work.ded.corridor_rate > 0
        else 0.0
    )
    return (
        edb_wo_corr + edb_corr - work.accrual_loan.policy_debt
        + _primary_insured_rider_face(policy, work.month_date)
    )


def _illustration_lapse_protected(work: MonthWork, av_loans_test: bool) -> bool:
    return (
        work.snet_active or work.shadow_protection or work.positive_sv
        or av_loans_test or work.exception_protection
    )


def _evaluate_cyberlife_lapse(ctx: MonthContext, work: MonthWork) -> None:
    work.monthly_mtp = truncate_monthly_mtp(ctx.policy.mtp)
    work.accumulated_mtp = ctx.state.accumulated_mtp + work.monthly_mtp
    work.accum_mtp_less_prem = (
        work.prem.premiums_to_date - work.withdrawals_to_date
        - work.accrual_loan.policy_debt
    ) - work.accumulated_mtp
    work.av_less_loans = work.av - work.accrual_loan.policy_debt
    work.accumulated_7pay = ctx.state.accumulated_7pay + (
        work.prem.gross_premium if work.tamra_year <= 7 else 0.0
    )
    work.exception_protection = work.exception.mode and work.av_less_loans > -0.0001
    work.lapsed = ctx.state.lapsed or (work.av <= 0.0 and not work.exception.mode)
    if ctx.options is not None and ctx.options.no_lapse:
        work.lapsed = False


def run_month(ctx: MonthContext, convention: TimingConvention) -> MonthlyState:
    """Run one projected month using the canonical step sequence."""
    if ctx.options is None:
        ctx = replace(ctx, options=IllustrationOptions())
    work = MonthWork()
    advance_counters(ctx, convention, work)
    carry_begin_values(ctx, work)
    capitalize_loans_step(ctx, work)
    if convention.interest_timing == "pre_withdrawal":
        credit_interest_pre_withdrawal(ctx, work)
    process_withdrawal_step(ctx, convention, work)
    apply_policy_changes(ctx, convention, work)
    refresh_targets(ctx, convention, work)
    apply_guideline_forceout(ctx, convention, work)
    resolve_requested_premium(ctx, work)
    apply_cashflows(ctx, work)
    compute_allowances(ctx, work)
    apply_premium_step(ctx, work)
    deduct_monthly_charges(ctx, convention, work)
    apply_exception_premium(ctx, convention, work)
    apply_new_loans(ctx, work)
    if convention.interest_timing == "post_deduction":
        credit_interest_post_deduction(ctx, convention, work)
    accrue_loans(ctx, work)
    calculate_shadow_step(ctx, convention, work)
    evaluate_lapse(ctx, convention, work)
    return build_month_state(ctx, convention, work)


def build_month_state(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> MonthlyState:
    """Create the ledger row from completed month work."""
    fields = {}
    for part in (
        _month_counter_fields,
        _change_and_target_fields,
        _loan_begin_fields,
        _premium_fields,
        _deduction_fields,
        _interest_and_loan_end_fields,
        _tracking_fields,
        _lapse_fields,
    ):
        fields.update(part(ctx, convention, work))
    if convention.shadow_enabled:
        fields.update(_shadow_fields(work))
    return MonthlyState(**fields)


def _month_counter_fields(
    ctx: MonthContext, _convention: TimingConvention, work: MonthWork
) -> dict:
    return {
        "date": work.month_date,
        "policy_year": work.next_year,
        "policy_month": work.next_month,
        "duration": work.duration,
        "attained_age": work.attained_age,
        "matured": work.attained_age >= ctx.config.maturity_age,
        "is_anniversary": work.is_anniversary,
        "db_option": str(ctx.policy.db_option or "").upper(),
        "coverage_after_change": work.cov_after_change,
        **_withdrawal_state_fields(work.wd),
    }


def _change_and_target_fields(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> dict:
    fields = {
        "mtp_detail": work.mtp_detail,
        "ctp_detail": work.ctp_detail,
        "mtp_annual": ctx.policy.mtp * MONTHS_PER_YEAR,
    }
    if convention.supports_policy_changes:
        fields.update({
            "guideline_recalc": work.guideline_recalc,
            "dbo_change_detail": work.dbo_change_detail,
            "face_change_detail": work.face_change_detail,
        })
    return fields


def _loan_begin_fields(
    _ctx: MonthContext, _convention: TimingConvention, work: MonthWork
) -> dict:
    return {
        "rg_loan_princ": work.cap_loan.rg_loan_princ,
        "rg_loan_accrued": work.cap_loan.rg_loan_accrued,
        "pf_loan_princ": work.cap_loan.pf_loan_princ,
        "pf_loan_accrued": work.cap_loan.pf_loan_accrued,
        "vbl_loan_princ": work.cap_loan.vbl_loan_princ,
        "vbl_loan_accrued": work.cap_loan.vbl_loan_accrued,
        "applied_loan_repayment": work.cash_flows.applied_loan_repayment,
        "loan_repay_from_prem": (
            work.cash_flows.loan_repay_from_lumpsum
            + work.cash_flows.loan_repay_from_scheduled
        ),
        "applied_regular_loan": work.applied_regular_loan,
        "applied_preferred_loan": work.applied_preferred_loan,
        "applied_variable_loan": work.cash_flows.applied_variable_loan,
        "loan_cap_repay": work.loan_cap_repay_detail,
    }


def _premium_fields(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> dict:
    requested = work.requested_scheduled + work.requested_lumpsum
    fields = {
        "gross_premium": work.prem.gross_premium,
        "prem_under_target": work.prem.prem_under_target,
        "prem_over_target": work.prem.prem_over_target,
        "tpp_rate": work.prem.tpp_rate,
        "epp_rate": work.prem.epp_rate,
        "target_load": work.prem.target_load + work.exception.percentage_load,
        "excess_load": work.prem.excess_load,
        "flat_load": work.prem.flat_load + work.exception.flat_load,
        "total_premium_load": (
            work.prem.total_premium_load
            + work.exception.percentage_load + work.exception.flat_load
        ),
        "net_premium": work.prem.net_premium,
        "av_after_premium": work.prem.av_after_premium,
        **_premium_state_fields(work.allowances, requested),
        **_tamra_premium_display(
            ctx.state, ctx.policy, work.month_date, work.next_month,
            ctx.month_inputs,
        ),
        "glp": floor_monthly_cent(ctx.policy.glp),
        "gsp": work.gsp_floored,
        "accumulated_glp": work.accumulated_glp,
        "guideline_limit": work.guideline_limit,
        "guideline_forceout": work.guideline_forceout,
        "guideline_av_before_monthly_deduction": work.av_before_deduction,
        "accumulated_7pay": work.accumulated_7pay,
        "amount_in_7pay": work.accumulated_7pay_base,
        "tamra_year": work.tamra_year,
        "tamra_7pay_level": ctx.policy.tamra_7pay_level,
    }
    if convention.supports_policy_changes:
        fields.update({"is_mec": ctx.policy.is_mec, "mec_year": ctx.state.mec_year})
    return fields


def _deduction_fields(
    ctx: MonthContext, _convention: TimingConvention, work: MonthWork
) -> dict:
    ded = work.ded
    return {
        "guideline_limit_reached": work.guideline_limit_reached,
        "md_premium_mode": work.exception.md_premium_mode,
        "billable_md_switched": work.b2md_switched,
        "md_premium": work.exception.md_prem,
        "md_premium_gross": work.exception.md_prem_gross,
        "md_premium_capped": work.exception.md_prem_capped,
        "md_premium_discount": work.exception.md_discount,
        "exception_prem_mode": work.exception.mode,
        "gp_exception_mode": work.exception.is_gp_exception,
        "inforce_exception_period": ctx.state.inforce_exception_period,
        "gp_exception_prem_gross": work.exception.gross,
        "gp_exception_prem": work.exception.prem,
        "gp_exception_prem_discount": work.exception.discount,
        "gp_exception_percentage_load": work.exception.gp_percentage_load,
        "gp_exception_flat_load": work.exception.gp_flat_load,
        "exception_protection": work.exception_protection,
        "nar_av": ded.nar_av,
        "standard_db": ded.standard_db,
        "corridor_rate": ded.corridor_rate,
        "gross_db": ded.gross_db,
        "corr_amount": ded.corr_amount,
        "db_by_coverage": ded.db_by_coverage,
        "discounted_db_by_coverage": ded.discounted_db_by_coverage,
        "discounted_db_cov1": ded.discounted_db_cov1,
        "discounted_db_corr": ded.discounted_db_corr,
        "discounted_db": ded.discounted_db,
        "total_db": ded.total_db,
        "total_discounted_db": ded.total_discounted_db,
        "nar_by_coverage": ded.nar_by_coverage,
        "nar_cov1": ded.nar_cov1,
        "nar_corr": ded.nar_corr,
        "nar": ded.nar,
        "total_nar": ded.total_nar,
        **_coi_deduction_fields(ded),
        **_expense_deduction_fields(ctx, ded, work),
    }


def _coi_deduction_fields(ded) -> dict:
    return {
        "coi_rates_by_coverage": ded.coi_rates_by_coverage,
        "coi_charges_by_coverage": ded.coi_charges_by_coverage,
        "coi_rate": ded.coi_rate,
        "coi_rate_corr": ded.coi_rate_corr,
        "coi_charge_cov1": ded.coi_charge_cov1,
        "coi_charge_corr": ded.coi_charge_corr,
        "coi_charge": ded.coi_charge,
        "total_coi_charge": ded.total_coi_charge,
        "ratchet_active": ded.ratchet_active,
        "band_break": ded.band_break,
        "coi_band1_nar_by_coverage": ded.coi_band1_nar_by_coverage,
        "coi_band2_nar_by_coverage": ded.coi_band2_nar_by_coverage,
        "coi_band1_rates_by_coverage": ded.coi_band1_rates_by_coverage,
        "coi_band2_rates_by_coverage": ded.coi_band2_rates_by_coverage,
    }


def _expense_deduction_fields(ctx: MonthContext, ded, work: MonthWork) -> dict:
    return {
        "epu_rate": ded.epu_rate,
        "epu_charge": ded.epu_charge,
        "epu_rates_by_coverage": ded.epu_rates_by_coverage,
        "epu_charges_by_coverage": ded.epu_charges_by_coverage,
        "mfee_charge": ded.mfee_charge,
        "av_charge": ded.av_charge,
        "pw_charge": ded.pw_charge,
        "benefit_charges": ded.benefit_charges,
        "benefit_amounts": ded.benefit_amounts,
        "benefit_rates": ded.benefit_rates,
        "benefit_charge_detail": ded.benefit_charge_detail,
        "rider_charges": ded.rider_charges,
        "rider_amounts": ded.rider_amounts,
        "rider_rates": ded.rider_rates,
        "rider_charge_detail": ded.rider_charge_detail,
        "total_deduction": ded.total_deduction,
        "av_after_deduction": ded.av_after_deduction - work.asset_charge,
        "av_after_exception": work.exception.av_after_exception,
        "asset_charge_rate": ctx.iul_ctx.asset_charge_rate if ctx.iul_ctx else 0.0,
        "asset_charge": work.asset_charge,
    }


def _interest_and_loan_end_fields(
    _ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> dict:
    fields = {}
    if convention.wair_enabled:
        fields.update({
            "wair_tav": work.wair_tav,
            "wair_swam": work.wair_swam,
            "wair_held": work.wair_held,
            "wair_rate": work.wair_rate,
        })
    fields.update({
        "days_in_month": work.intr.days_in_month,
        "annual_interest_rate": work.intr.annual_interest_rate,
        "bonus_interest_rate": work.intr.bonus_interest_rate,
        "effective_annual_rate": work.intr.effective_annual_rate,
        "monthly_interest_rate": work.intr.monthly_interest_rate,
        "reg_loan_credit_rate": work.intr.reg_loan_credit_rate,
        "pref_loan_credit_rate": work.intr.pref_loan_credit_rate,
        "reg_impaired_int": work.intr.reg_impaired_int,
        "pref_impaired_int": work.intr.pref_impaired_int,
        "unimpaired_int": work.intr.unimpaired_int,
        "interest_credited": work.intr.interest_credited,
        "av_end_of_month": work.av,
        **_loan_end_fields(work),
    })
    return fields


def _loan_end_fields(work: MonthWork) -> dict:
    return {
        "reg_loan_charge": work.accrual_loan.reg_loan_charge,
        "pref_loan_charge": work.accrual_loan.pref_loan_charge,
        "vbl_loan_charge": work.accrual_loan.vbl_loan_charge,
        "adv_reg_ln_int": work.adv_reg_ln_int,
        "adv_pref_ln_int": work.adv_pref_ln_int,
        "end_rg_loan_princ": work.accrual_loan.rg_loan_princ,
        "end_rg_loan_accrued": work.accrual_loan.rg_loan_accrued,
        "end_pf_loan_princ": work.accrual_loan.pf_loan_princ,
        "end_pf_loan_accrued": work.accrual_loan.pf_loan_accrued,
        "end_vbl_loan_princ": work.accrual_loan.vbl_loan_princ,
        "end_vbl_loan_accrued": work.accrual_loan.vbl_loan_accrued,
        "policy_debt": work.accrual_loan.policy_debt,
    }


def _tracking_fields(
    ctx: MonthContext, _convention: TimingConvention, work: MonthWork
) -> dict:
    return {
        "premiums_ytd": work.prem.premiums_ytd,
        "premiums_to_date": work.prem.premiums_to_date,
        "withdrawals_to_date": work.withdrawals_to_date,
        "cost_basis": work.prem.cost_basis,
        "premiums_ytd_after_exception": (
            work.prem.premiums_ytd + work.exception.total_prem
        ),
        "premiums_to_date_after_exception": (
            work.prem.premiums_to_date + work.exception.total_prem
        ),
        "cost_basis_after_exception": work.prem.cost_basis + work.exception.total_prem,
        "cumulative_interest": (
            ctx.state.cumulative_interest + work.intr.interest_credited
        ),
        "cumulative_charges": (
            ctx.state.cumulative_charges + work.ded.total_deduction
        ),
        "monthly_mtp": work.monthly_mtp,
        "ctp": ctx.policy.ctp,
        "accumulated_mtp": work.accumulated_mtp,
        "accum_mtp_less_prem": work.accum_mtp_less_prem,
        "av_less_loans": work.av_less_loans,
        "lapsed": work.lapsed,
    }


def _lapse_fields(
    _ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> dict:
    if not convention.full_lapse_protection:
        return {}
    return {
        "scr_rate": work.scr_rate,
        "scr_rates_by_coverage": work.scr_rates_by_coverage,
        "surrender_charge": work.surrender_charge,
        "surrender_charges_by_coverage": work.surrender_charges_by_coverage,
        "surrender_value": work.surrender_value,
        "ending_sv": work.ending_sv,
        "ending_db": work.ending_db,
        "snet_active": work.snet_active,
        "shadow_protection": work.shadow_protection,
        "positive_sv": work.positive_sv,
    }


def _shadow_fields(work: MonthWork) -> dict:
    shd = work.shd
    return {
        "shadow_bav": shd.shadow_bav,
        "shadow_wd_charges": shd.shadow_wd_charges,
        "shadow_sa": shd.shadow_sa,
        "shadow_target_prem": shd.shadow_target_prem,
        "shadow_prem_under_target": shd.shadow_prem_under_target,
        "shadow_prem_over_target": shd.shadow_prem_over_target,
        "shadow_target_load": shd.shadow_target_load,
        "shadow_excess_load": shd.shadow_excess_load,
        "shadow_prem_load": shd.shadow_prem_load,
        "shadow_net_prem": shd.shadow_net_prem,
        "shadow_nar_av": shd.shadow_nar_av,
        "shadow_db": shd.shadow_db,
        "shadow_coi_rate": shd.shadow_coi_rate,
        "shadow_coi": shd.shadow_coi,
        "shadow_dbd_rate": shd.shadow_dbd_rate,
        "shadow_nar": shd.shadow_nar,
        "shadow_epu_rate": shd.shadow_epu_rate,
        "shadow_epu": shd.shadow_epu,
        "shadow_mfee": shd.shadow_mfee,
        "shadow_rider_charges": shd.shadow_rider_charges,
        "shadow_md": shd.shadow_md,
        "shadow_av": shd.shadow_av,
        "shadow_days": shd.shadow_days,
        "shadow_int_rate": shd.shadow_int_rate,
        "shadow_eff_rate": shd.shadow_eff_rate,
        "shadow_interest": shd.shadow_interest,
        "shadow_eav": shd.shadow_eav,
        "shadow_eav_less_debt": shd.shadow_eav_less_debt,
    }




def build_inforce_state(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    bonus: BonusConfig,
    options: IllustrationOptions,
    iul_ctx: Optional[IULCreditingContext],
    timing: ProjectionTiming,
    starting_exception_period: bool,
) -> MonthlyState:
    """Build the month-zero inforce state that seeds a projection."""
    work = _initialize_inforce_work(policy, config, rates, bonus, options, iul_ctx)
    _add_inforce_loan_shadow_lapse(policy, config, rates, iul_ctx, work)
    inforce = _build_inforce_row(
        policy, config, iul_ctx, starting_exception_period, work
    )
    return _adjust_inforce_for_timing(policy, timing, inforce, work)


def _initialize_inforce_work(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    bonus: BonusConfig,
    options: IllustrationOptions,
    iul_ctx: Optional[IULCreditingContext],
) -> InforceWork:
    work = InforceWork()
    work.rate_year = policy.policy_year
    work.month_date = policy.valuation_date or (
        policy.issue_date + relativedelta(months=policy.duration)
    )
    work.monthly_mtp = truncate_monthly_mtp(policy.mtp)
    work.mtp_detail, work.ctp_detail = build_target_detail_snapshots(
        policy, compute_target_premiums(policy, config, as_of=work.month_date)
    )
    work.md_check_av_before_deduction = (
        policy.account_value + policy.system_monthly_deduction
    )
    work.ded = calculate_deduction(
        work.md_check_av_before_deduction,
        policy,
        config,
        rates,
        work.rate_year,
        policy.attained_age,
        policy.premiums_paid_to_date,
        monthly_mtp=work.monthly_mtp,
        projection_date=work.month_date,
        bln_round_charge=True,
    )
    work.intr = credit_interest(
        policy.account_value, policy, config, rates, bonus,
        work.rate_year, policy.attained_age, work.month_date,
        reg_loan_balance=policy.regular_loan_principal,
        pref_loan_balance=policy.preferred_loan_principal,
        exact_days_interest=options.exact_days_interest,
    )
    _apply_inforce_wair(policy, iul_ctx, work)
    return work


def _apply_inforce_wair(
    policy: IllustrationPolicyData,
    iul_ctx: Optional[IULCreditingContext],
    work: InforceWork,
) -> None:
    if iul_ctx is None or not iul_ctx.wair_enabled:
        return
    uk0 = iul_ctx.declared_rate + work.intr.bonus_interest_rate
    work.wair_swam = float(policy.sweep_account_min or 0.0)
    work.wair_held = weighted_average_rate(
        av=policy.account_value,
        swam=work.wair_swam,
        reg_ln_principal=policy.regular_loan_principal,
        reg_ln_accrued=policy.regular_loan_accrued,
        pref_ln_principal=policy.preferred_loan_principal,
        pref_ln_accrued=policy.preferred_loan_accrued,
        reg_loan_credit_rate=work.intr.reg_loan_credit_rate,
        pref_loan_credit_rate=work.intr.pref_loan_credit_rate,
        declared_plus_bonus=uk0,
        blend_plus_bonus=work.intr.effective_annual_rate,
    )
    work.wair_rate = cap_wair(iul_ctx, work.wair_held, uk0)
    vl0 = wair_interest(policy.account_value, work.wair_rate, work.intr.days_in_month)
    work.intr = replace(
        work.intr,
        effective_annual_rate=work.wair_rate,
        monthly_interest_rate=(
            (1.0 + work.wair_rate) ** (work.intr.days_in_month / DAYS_PER_YEAR)
            - 1.0
        ),
        reg_impaired_int=0.0,
        pref_impaired_int=0.0,
        unimpaired_int=vl0,
        interest_credited=vl0,
        av_end_of_month=policy.account_value + vl0,
    )


def _add_inforce_loan_shadow_lapse(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    iul_ctx: Optional[IULCreditingContext],
    work: InforceWork,
) -> None:
    work.loan = _inforce_accrued_loan(policy, config, iul_ctx, work)
    work.loan_cap_repay = _inforce_loan_cap_repay(policy, config, work)
    work.shd = calculate_shadow(ShadowInput(
        prev_shadow_eav=policy.shadow_account_value,
        gross_premium=0.0,
        premiums_ytd=policy.premiums_ytd,
        policy=policy,
        config=config,
        rates=rates,
        rate_year=work.rate_year,
        attained_age=policy.attained_age,
        days_in_month=work.intr.actual_days_in_month,
        policy_debt=work.loan.policy_debt,
        is_inforce=True,
        shadow_rider_charges=_shadow_rider_charges_from_deduction(policy, work.ded),
        projection_date=work.month_date,
        display_days_in_month=work.intr.days_in_month,
    ))
    _set_inforce_lapse_fields(policy, config, rates, work)


def _inforce_accrued_loan(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    iul_ctx: Optional[IULCreditingContext],
    work: InforceWork,
) -> LoanState:
    loan = LoanState(
        rg_loan_princ=policy.regular_loan_principal,
        rg_loan_accrued=policy.regular_loan_accrued,
        pf_loan_princ=policy.preferred_loan_principal,
        pf_loan_accrued=policy.preferred_loan_accrued,
        vbl_loan_princ=policy.variable_loan_principal,
        vbl_loan_accrued=policy.variable_loan_accrued,
    )
    return accrue_loan_interest(
        loan,
        config,
        work.intr.days_in_month,
        variable_loan_accrual_rate(
            iul_ctx, policy.variable_loan_charge_rate, policy.current_interest_rate
        ),
    )


def _inforce_loan_cap_repay(
    policy: IllustrationPolicyData, config: PlancodeConfig, work: InforceWork
) -> Dict[str, object]:
    days_to_next = _days_to_next_anniversary(policy.issue_date, work.month_date)
    adv_reg_factor, adv_pref_factor = _advance_loan_factors(config, days_to_next)
    return repay_loan(LoanStepInput(
        loan=LoanState(
            rg_loan_princ=policy.regular_loan_principal,
            rg_loan_accrued=policy.regular_loan_accrued,
            pf_loan_princ=policy.preferred_loan_principal,
            pf_loan_accrued=policy.preferred_loan_accrued,
            vbl_loan_princ=policy.variable_loan_principal,
            vbl_loan_accrued=policy.variable_loan_accrued,
        ),
        config=config,
        adv_reg_factor=adv_reg_factor,
        adv_pref_factor=adv_pref_factor,
    )).detail


def _set_inforce_lapse_fields(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    work: InforceWork,
) -> None:
    work.accumulated_mtp = policy.accumulated_mtp
    work.accum_mtp_less_prem = (
        policy.premiums_paid_to_date - policy.withdrawals_to_date
        - work.loan.policy_debt
    ) - work.accumulated_mtp
    within_snet = (
        work.month_date <= policy.map_cease_date
        if policy.map_cease_date is not None
        else policy.policy_year <= config.snet_period
    )
    work.snet_active = work.accum_mtp_less_prem >= 0 and within_snet
    work.shadow_protection = (
        policy.has_shadow_account and not within_snet and work.shd.shadow_eav_less_debt > 0
    )
    (
        work.scr_rate,
        work.surrender_charge,
        work.scr_rates_by_coverage,
        work.surrender_charges_by_coverage,
    ) = _calculate_surrender_charge(policy, rates, work.rate_year, work.month_date, config)
    work.surrender_value = policy.account_value - work.surrender_charge - work.loan.policy_debt
    work.ending_sv = work.intr.av_end_of_month - work.surrender_charge - work.loan.policy_debt
    work.positive_sv = (
        config.lapse_value == LAPSE_BASIS_SURRENDER_VALUE and work.surrender_value > 0
    )
    work.av_less_loans = policy.account_value - work.loan.policy_debt


def _build_inforce_row(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    iul_ctx: Optional[IULCreditingContext],
    starting_exception_period: bool,
    work: InforceWork,
) -> MonthlyState:
    return MonthlyState(
        date=policy.valuation_date,
        policy_year=policy.policy_year,
        policy_month=policy.policy_month,
        duration=policy.duration,
        attained_age=policy.attained_age,
        db_option=str(policy.db_option or "").upper(),
        coverage_after_change=_coverage_after_change_snapshot(
            policy, config, policy.valuation_date or policy.issue_date, 0.0, None,
        ),
        mtp_detail=work.mtp_detail,
        ctp_detail=work.ctp_detail,
        mtp_annual=policy.mtp * MONTHS_PER_YEAR,
        av_after_premium=work.md_check_av_before_deduction,
        glp=floor_monthly_cent(policy.glp),
        gsp=floor_monthly_cent(policy.gsp),
        accumulated_glp=policy.accumulated_glp,
        guideline_limit=max(floor_monthly_cent(policy.gsp), policy.accumulated_glp),
        guideline_forceout=0.0,
        gp_exception_mode=starting_exception_period,
        inforce_exception_period=starting_exception_period,
        exception_prem_mode=starting_exception_period,
        guideline_av_before_monthly_deduction=work.md_check_av_before_deduction,
        accumulated_7pay=sum(policy.tamra_7year_contributions or []),
        amount_in_7pay=sum(policy.tamra_7year_contributions or []),
        tamra_7pay_level=policy.tamra_7pay_level,
        tamra_7pay_start_date=policy.tamra_7pay_start_date,
        is_mec=policy.is_mec,
        tamra_year=_tamra_year(policy, work.month_date),
        tamra_month_of_year=_tamra_month_of_year(policy, work.month_date),
        lowest_7yr_face=_tamra_starting_lowest_face(policy),
        planned_premium_mode=_billing_mode(policy),
        # Deduction check
        nar_av=work.ded.nar_av,
        standard_db=work.ded.standard_db,
        corridor_rate=work.ded.corridor_rate,
        gross_db=work.ded.gross_db,
        corr_amount=work.ded.corr_amount,
        db_by_coverage=work.ded.db_by_coverage,
        discounted_db_by_coverage=work.ded.discounted_db_by_coverage,
        discounted_db_cov1=work.ded.discounted_db_cov1,
        discounted_db_corr=work.ded.discounted_db_corr,
        discounted_db=work.ded.discounted_db,
        total_db=work.ded.total_db,
        total_discounted_db=work.ded.total_discounted_db,
        nar_by_coverage=work.ded.nar_by_coverage,
        nar_cov1=work.ded.nar_cov1,
        nar_corr=work.ded.nar_corr,
        nar=work.ded.nar,
        total_nar=work.ded.total_nar,
        coi_rates_by_coverage=work.ded.coi_rates_by_coverage,
        coi_charges_by_coverage=work.ded.coi_charges_by_coverage,
        coi_rate=work.ded.coi_rate,
        coi_rate_corr=work.ded.coi_rate_corr,
        coi_charge_cov1=work.ded.coi_charge_cov1,
        coi_charge_corr=work.ded.coi_charge_corr,
        coi_charge=work.ded.coi_charge,
        total_coi_charge=work.ded.total_coi_charge,
        ratchet_active=work.ded.ratchet_active,
        band_break=work.ded.band_break,
        coi_band1_nar_by_coverage=work.ded.coi_band1_nar_by_coverage,
        coi_band2_nar_by_coverage=work.ded.coi_band2_nar_by_coverage,
        coi_band1_rates_by_coverage=work.ded.coi_band1_rates_by_coverage,
        coi_band2_rates_by_coverage=work.ded.coi_band2_rates_by_coverage,
        epu_rate=work.ded.epu_rate,
        epu_charge=work.ded.epu_charge,
        epu_rates_by_coverage=work.ded.epu_rates_by_coverage,
        epu_charges_by_coverage=work.ded.epu_charges_by_coverage,
        mfee_charge=work.ded.mfee_charge,
        av_charge=work.ded.av_charge,
        pw_charge=work.ded.pw_charge,
        benefit_charges=work.ded.benefit_charges,
        benefit_amounts=work.ded.benefit_amounts,
        benefit_rates=work.ded.benefit_rates,
        benefit_charge_detail=work.ded.benefit_charge_detail,
        rider_charges=work.ded.rider_charges,
        rider_amounts=work.ded.rider_amounts,
        rider_rates=work.ded.rider_rates,
        rider_charge_detail=work.ded.rider_charge_detail,
        total_deduction=work.ded.total_deduction,
        av_after_deduction=policy.account_value,
        av_after_exception=policy.account_value,
        system_coi_charge=policy.system_coi_charge,
        system_expense_charge=policy.system_expense_charge,
        system_other_charge=policy.system_other_charge,
        system_monthly_deduction=policy.system_monthly_deduction,
        md_check_av_before_deduction=work.md_check_av_before_deduction,
        md_check_calculated_deduction=work.ded.total_deduction,
        md_check_deduction_variance=work.ded.total_deduction - policy.system_monthly_deduction,
        md_check_calculated_av_after_deduction=work.ded.av_after_deduction,
        md_check_av_variance=work.ded.av_after_deduction - policy.account_value,
        # Set 1: Loan cap/repay (beginning of month — from policy inputs)
        rg_loan_princ=policy.regular_loan_principal,
        rg_loan_accrued=policy.regular_loan_accrued,
        pf_loan_princ=policy.preferred_loan_principal,
        pf_loan_accrued=policy.preferred_loan_accrued,
        vbl_loan_princ=policy.variable_loan_principal,
        vbl_loan_accrued=policy.variable_loan_accrued,
        loan_cap_repay=work.loan_cap_repay,
        # IUL crediting — no asset charge on the valuation row (RERUN SX
        # takes sInput_CurrentAV verbatim); WAIR seeds from VI.
        asset_charge_rate=iul_ctx.asset_charge_rate if iul_ctx else 0.0,
        asset_charge=0.0,
        wair_tav=work.wair_tav,
        wair_swam=work.wair_swam,
        wair_held=work.wair_held,
        wair_rate=work.wair_rate,
        # Interest
        days_in_month=work.intr.days_in_month,
        annual_interest_rate=work.intr.annual_interest_rate,
        bonus_interest_rate=work.intr.bonus_interest_rate,
        effective_annual_rate=work.intr.effective_annual_rate,
        monthly_interest_rate=work.intr.monthly_interest_rate,
        reg_loan_credit_rate=work.intr.reg_loan_credit_rate,
        pref_loan_credit_rate=work.intr.pref_loan_credit_rate,
        reg_impaired_int=work.intr.reg_impaired_int,
        pref_impaired_int=work.intr.pref_impaired_int,
        unimpaired_int=work.intr.unimpaired_int,
        interest_credited=work.intr.interest_credited,
        av_end_of_month=work.intr.av_end_of_month,
        # Set 2: Loan accrual (end of month — after accrual)
        reg_loan_charge=work.loan.reg_loan_charge,
        pref_loan_charge=work.loan.pref_loan_charge,
        vbl_loan_charge=work.loan.vbl_loan_charge,
        end_rg_loan_princ=work.loan.rg_loan_princ,
        end_rg_loan_accrued=work.loan.rg_loan_accrued,
        end_pf_loan_princ=work.loan.pf_loan_princ,
        end_pf_loan_accrued=work.loan.pf_loan_accrued,
        end_vbl_loan_princ=work.loan.vbl_loan_princ,
        end_vbl_loan_accrued=work.loan.vbl_loan_accrued,
        policy_debt=work.loan.policy_debt,
        # Tracking
        premiums_ytd=policy.premiums_ytd,
        premiums_to_date=policy.premiums_paid_to_date,
        withdrawals_to_date=policy.withdrawals_to_date,
        cost_basis=policy.cost_basis,
        # Seed the after-exception set from the same inforce values — no
        # exception premium has been applied yet, so month 1 carries these
        # forward unchanged.
        premiums_ytd_after_exception=policy.premiums_ytd,
        premiums_to_date_after_exception=policy.premiums_paid_to_date,
        cost_basis_after_exception=policy.cost_basis,
        cumulative_interest=work.intr.interest_credited,
        # Shadow
        shadow_bav=work.shd.shadow_bav,
        shadow_wd_charges=work.shd.shadow_wd_charges,
        shadow_sa=work.shd.shadow_sa,
        shadow_target_prem=work.shd.shadow_target_prem,
        shadow_prem_under_target=work.shd.shadow_prem_under_target,
        shadow_prem_over_target=work.shd.shadow_prem_over_target,
        shadow_target_load=work.shd.shadow_target_load,
        shadow_excess_load=work.shd.shadow_excess_load,
        shadow_prem_load=work.shd.shadow_prem_load,
        shadow_net_prem=work.shd.shadow_net_prem,
        shadow_nar_av=work.shd.shadow_nar_av,
        shadow_db=work.shd.shadow_db,
        shadow_coi_rate=work.shd.shadow_coi_rate,
        shadow_coi=work.shd.shadow_coi,
        shadow_dbd_rate=work.shd.shadow_dbd_rate,
        shadow_nar=work.shd.shadow_nar,
        shadow_epu_rate=work.shd.shadow_epu_rate,
        shadow_epu=work.shd.shadow_epu,
        shadow_mfee=work.shd.shadow_mfee,
        shadow_rider_charges=work.shd.shadow_rider_charges,
        shadow_md=work.shd.shadow_md,
        shadow_av=work.shd.shadow_av,
        shadow_days=work.shd.shadow_days,
        shadow_int_rate=work.shd.shadow_int_rate,
        shadow_eff_rate=work.shd.shadow_eff_rate,
        shadow_interest=work.shd.shadow_interest,
        shadow_eav=work.shd.shadow_eav,
        shadow_eav_less_debt=work.shd.shadow_eav_less_debt,
        # Safety Net / Lapse Protection
        monthly_mtp=work.monthly_mtp,
        ctp=policy.ctp,
        accumulated_mtp=work.accumulated_mtp,
        accum_mtp_less_prem=work.accum_mtp_less_prem,
        snet_active=work.snet_active,
        shadow_protection=work.shadow_protection,
        positive_sv=work.positive_sv,
        av_less_loans=work.av_less_loans,
        # End-of-month values
        scr_rate=work.scr_rate,
        scr_rates_by_coverage=work.scr_rates_by_coverage,
        surrender_charge=work.surrender_charge,
        surrender_charges_by_coverage=work.surrender_charges_by_coverage,
        surrender_value=work.surrender_value,
        ending_sv=work.ending_sv,
    )

def _adjust_inforce_for_timing(
    policy: IllustrationPolicyData,
    timing: ProjectionTiming,
    inforce: MonthlyState,
    work: InforceWork,
) -> MonthlyState:
    if policy.run_from_issue:
        inforce = replace(
            inforce,
            date=policy.issue_date - relativedelta(months=1),
            policy_year=0,
            policy_month=12,
            duration=0,
            attained_age=policy.issue_age,
            is_anniversary=False,
        )
    if timing == ProjectionTiming.CYBERLIFE_MONTHLIVERSARY:
        inforce = replace(
            inforce,
            av_after_deduction=policy.account_value,
            av_end_of_month=policy.account_value,
            ending_sv=work.surrender_value,
            unimpaired_int=0.0,
            interest_credited=0.0,
            cumulative_interest=0.0,
        )
    return inforce

class IllustrationEngine:
    """UL illustration projection engine.

    Stateless — all inputs come through IllustrationPolicyData.
    Can be reused across multiple projections.
    """

    def __init__(self) -> None:
        self._rates_cache: Dict[str, IllustrationRates] = {}

    def project(
        self,
        policy: IllustrationPolicyData,
        months: Optional[int] = None,
        future_inputs: Optional[IllustrationInputSet] = None,
        timing: ProjectionTiming = ProjectionTiming.ILLUSTRATION,
        stop_on_lapse: bool = True,
        options: Optional[IllustrationOptions] = None,
        bonus_override: Optional[BonusConfig] = None,
        rates_override: Optional[IllustrationRates] = None,
    ) -> List[MonthlyState]:
        """Run monthly projection from current policy state.

        Args:
            policy: Populated IllustrationPolicyData.
            months: Number of months to project. If None, projects to maturity age.
            options: Per-run guideline toggles (TEFRA/TAMRA conformance, exception
                premium). Defaults to a normal as-is illustration.
            bonus_override: Replaces the JSON-loaded bonus config. Pass a zeroed
                BonusConfig for guideline-premium projections that must exclude
                interest bonuses.

        Returns:
            List of MonthlyState, one per projected month.
        """
        if options is None:
            options = IllustrationOptions()
        validate_projection_timing(timing, future_inputs)
        policy, config, starting_exception_period = prepare_run_policy(policy, options)
        rates = rates_override if rates_override is not None else self._load_rates(policy, config)
        iul_ctx = build_iul_context(policy, options)
        initialize_run_from_issue_targets(policy, config, options)
        bonus = resolve_bonus_config(policy, bonus_override)
        total_months = projection_month_count(policy, months)
        changes_by_duration = compile_policy_changes_by_duration(policy, future_inputs)

        inforce = build_inforce_state(
            policy, config, rates, bonus, options, iul_ctx, timing,
            starting_exception_period,
        )

        compiled_inputs = compile_month_inputs(policy, future_inputs, total_months)

        results: List[MonthlyState] = [inforce]
        state = inforce
        convention = timing_convention(timing)
        for _ in range(total_months):
            month_inputs = compiled_inputs.get(state.duration + 1)
            policy_changes = None
            if convention.supports_policy_changes:
                policy_changes = changes_by_duration.get(state.duration + 1)
            state = run_month(MonthContext(
                state=state, policy=policy, config=config, rates=rates,
                bonus=bonus, month_inputs=month_inputs, options=options,
                policy_changes=policy_changes, iul_ctx=iul_ctx,
            ), convention)
            state = _apply_mec_status(policy, results, state)
            results.append(state)
            if stop_on_lapse and state.lapsed:
                break

        return results



    def _load_rates(
        self,
        policy: IllustrationPolicyData,
        config: PlancodeConfig,
    ) -> IllustrationRates:
        """Load rates for the current policy.

        IllustrationRates includes policy-specific rider and benefit schedules,
        so it cannot be safely reused across policies with the same base rate
        attributes.
        """
        seg = policy.base_segment
        if seg is None:
            return IllustrationRates()
        return load_rates(policy, config)


def _apply_mec_status(policy, prior_states, state: MonthlyState) -> MonthlyState:
    """Latch monthly excess or a recalc back-test failure independently of capping."""
    if policy.is_mec:
        return replace(state, is_mec=True, mec_year=prior_states[-1].mec_year)

    backtest_failed = False
    detail = state.guideline_recalc
    if detail.get("tamra_case") == "within_period":
        history = list(prior_states) + [state]
        backtest = seven_pay_backtest(policy, history, len(history) - 1, detail)
        if backtest is not None:
            detail = dict(detail)
            detail["seven_pay_backtest"] = backtest
            state = replace(state, guideline_recalc=detail)
            backtest_failed = backtest["is_mec"]
    if backtest_failed or seven_pay_limit_exceeded(state):
        policy.is_mec = True
        state = replace(state, is_mec=True, mec_year=state.policy_year)
    return state


def _change_duration(policy: IllustrationPolicyData, effective_date) -> int:
    """Projection duration (1-indexed month) at which a dated change takes effect."""
    issue = policy.issue_date
    if issue is None or effective_date is None:
        return 0
    months = (effective_date.year - issue.year) * 12 + (effective_date.month - issue.month)
    before_anniversary = (
        effective_date < issue + relativedelta(months=months)
        if policy.run_from_issue else effective_date.day < issue.day
    )
    if before_anniversary:
        months -= 1
    return max(1, months + 1)


_POLICY_CHANGE_ORDER = {
    PolicyChangeKind.DB_OPTION: 0,
    PolicyChangeKind.FACE_AMOUNT: 1,
    PolicyChangeKind.RATE_CLASS: 2,
    PolicyChangeKind.SUBSTANDARD: 3,
    PolicyChangeKind.RIDER_DROP: 4,
}


def _compile_policy_changes(policy: IllustrationPolicyData, changes) -> Dict[int, list]:
    """Bucket and order dated changes by their position in the monthly pipeline."""
    by_duration: Dict[int, list] = {}
    for change in changes:
        by_duration.setdefault(_change_duration(policy, change.effective_date), []).append(change)
    for month_changes in by_duration.values():
        month_changes.sort(
            key=lambda change: _POLICY_CHANGE_ORDER.get(change.kind, 99))
    return by_duration


def _reband_segment(rates, segment, plancode: str, *, band: int) -> None:
    """Reload COI/EPU at the current combined specified-amount band.

    CyberLife/RERUN band the COI by the CURRENT specified amount, so a face change
    that crosses a band breakpoint moves the per-unit rate. SCR is band-independent
    (varies only by rateclass), so it is not reloaded here.

    The caller resolves the policy issue-date boundary once for all segments.
    """
    from suiteview.core.rates import Rates

    rates_db = Rates()
    if band == segment.band:
        return
    segment.band = band
    rates.segment_coi[segment.coverage_phase] = load_coverage_coi_rates(
        rates_db,
        plancode=plancode,
        issue_age=segment.issue_age,
        sex=segment.rate_sex,
        rateclass=segment.rate_class,
        scale=rates.coi_scale,
        band=segment.band,
    )
    rates.segment_epu[segment.coverage_phase] = rates_db.get_rates(
        "EPU", plancode, segment.issue_age, segment.rate_sex,
        segment.rate_class, scale=rates.expense_scale, band=segment.band,
    ) or []


def _load_segment_rates(rates, segment, plancode: str, config=None) -> None:
    """Load COI/EPU/SCR schedules for a NEW segment at its issue age + band.

    The face-increase segment carries its OWN surrender charge schedule from
    its issue age (RERUN TI — vFullSC sums every coverage's charge).

    On a ratchet-banded plancode the segment ALSO needs explicit band-1 and
    band-2 COI schedules (RERUN PP-QX charges every segment's NAR split at
    those rates — PolicyRates keys cov 2/3 by the coverage's own issue age,
    same as cov 1). rate_loader only loads them for segments present at load
    time; without this a face-increase segment silently contributes 0 COI.
    """
    from suiteview.core.rates import Rates

    rates_db = Rates()
    rates.segment_coi[segment.coverage_phase] = load_coverage_coi_rates(
        rates_db,
        plancode=plancode,
        issue_age=segment.issue_age,
        sex=segment.rate_sex,
        rateclass=segment.rate_class,
        scale=rates.coi_scale,
        band=segment.band,
    )
    for attr, kind, scale in (
        ("segment_epu", "EPU", rates.expense_scale),
        ("segment_scr", "SCR", 1),
    ):
        schedule = rates_db.get_rates(
            kind, plancode, segment.issue_age, segment.rate_sex,
            segment.rate_class, scale=scale, band=segment.band,
        ) or []
        getattr(rates, attr)[segment.coverage_phase] = schedule
    if config is not None and getattr(config, "rachet_banding", False):
        for band, attr in ((1, "segment_coi_band1"), (2, "segment_coi_band2")):
            getattr(rates, attr)[segment.coverage_phase] = load_coverage_coi_rates(
                rates_db,
                plancode=plancode,
                issue_age=segment.issue_age,
                sex=segment.rate_sex,
                rateclass=segment.rate_class,
                scale=rates.coi_scale,
                band=band,
            )


def _reband_benefits(rates, policy) -> None:
    """Reload benefit COI rates at the base segment's (possibly re-banded) band."""
    from suiteview.core.rates import Rates

    seg = policy.base_segment
    if seg is None:
        return
    rates_db = Rates()
    for ben in policy.benefits:
        if not ben.is_active or (ben.benefit_type or "").startswith("#"):
            continue
        ben_key = (ben.benefit_type or "") + (ben.benefit_subtype or "")
        if not ben_key:
            continue
        rates.benefit_coi[ben_key] = _load_benefit_coi_rates(
            rates_db, policy, ben, seg
        )


def _reload_policy_band_rates(rates, policy, config) -> None:
    """Re-band COI/EPU and policy schedules at the CURRENT total-SA band.

    RERUN keys TPP/EPP (premium loads), MFEE, and PoAV on the month's
    CurrentBand (PolicyRates EC/ED/FE/FF all VLOOKUP on CalcEngine FD), so a
    face change that crosses a band breakpoint moves these schedules too —
    e.g. this plancode's band-3 target load steps 8%->4% at year 11 while
    bands 1-2 stay 8%.
    """
    from suiteview.core.rates import Rates

    seg = policy.base_segment
    if seg is None:
        return
    rates_db = Rates()
    band = rates_db.get_band(
        policy.plancode, policy.band_specified_amount, issue_date=policy.issue_date)
    band = int(band) if band is not None else seg.band
    policy.band = band
    for segment in policy.segments:
        if segment.face_amount > 0:
            _reband_segment(rates, segment, policy.plancode, band=band)
    _reband_benefits(rates, policy)
    for attr, kind in (("tpp", "TPP"), ("epp", "EPP"), ("mfee", "MFEE")):
        setattr(rates, attr, rates_db.get_rates(
            kind, policy.plancode, issue_age=seg.issue_age, sex=seg.rate_sex,
            rateclass=seg.rate_class, scale=rates.expense_scale, band=band,
        ) or [])
    if config.poav_table != "0":
        from suiteview.illustration.core.poav_rates import load_poav_schedule

        rates.poav = load_poav_schedule(
            config.poav_table,
            band,
            scale=rates.expense_scale,
        )


@dataclass
class _PolicyChangeOutcome:
    """What one applied policy change did to the projection month."""

    av_adjustment: float = 0.0       # AV movement this month (negative = charge)
    coverage_changed: bool = False   # Coverage/rider/benefit basis changed -> recompute fired
    material_change: bool = False    # face increase / B->A -> new 7-pay period (KZ)
    # Display detail keyed by RERUN column names (BW..CU / CW..DO).
    dbo_detail: Dict[str, object] = dataclass_field(default_factory=dict)
    face_detail: Dict[str, object] = dataclass_field(default_factory=dict)
    # Before/after GLP & GSP solves when this change re-solved the guideline
    # premiums (see _recalc_guideline_on_change); empty otherwise.
    guideline_recalc: Dict[str, object] = dataclass_field(default_factory=dict)
    guideline_before: Optional[object] = None
    guideline_before_pv_detail: Dict[str, object] = dataclass_field(default_factory=dict)


@dataclass
class _FaceCutResult:
    """Per-coverage detail of a face reduction (decrease / A->B / withdrawal)."""

    av_adjustment: float = 0.0
    cuts_by_phase: Dict[int, float] = dataclass_field(default_factory=dict)
    psc_by_phase: Dict[int, float] = dataclass_field(default_factory=dict)


def _reduce_base_face(policy, amount, rates, change_date, rate_year, charge_scr, config) -> _FaceCutResult:
    """Reduce base coverage newest-first; the caller then reloads policy bands.

    The AV adjustment is the decreased units' surrender charge when
    ``charge_scr`` — RERUN charges it on an elective face decrease and the
    A->B level-DB adjustment, but NOT on a withdrawal's face reduction (the
    partial surrender charge is already inside the gross withdrawal).
    """
    result = _FaceCutResult()
    remaining = amount
    for seg in reversed(policy.segments):
        if remaining <= 0:
            break
        cut = min(seg.face_amount, remaining)
        cut_units = cut / (seg.vpu or PER_THOUSAND)
        if charge_scr:
            scr_rate = _segment_surrender_rate(
                policy, seg, rates, rate_year, change_date, config)
            result.psc_by_phase[seg.coverage_phase] = scr_rate * cut_units
            result.av_adjustment -= scr_rate * cut_units
        result.cuts_by_phase[seg.coverage_phase] = cut
        seg.units -= cut_units
        seg.face_amount -= cut
        remaining -= cut
    policy.face_amount = sum(s.face_amount for s in policy.segments)
    return result


def _coverage_after_change_snapshot(policy, config, month_date, av_reduction, prior) -> Dict[str, object]:
    """Per-segment coverage snapshot after policy changes (CalcEngine DQ..FQ).

    Keyed by the RERUN display column names so the values tab can read them
    directly. The engine's base coverage segments map onto RERUN's three
    coverage slots (Cov 1 = base, later segments = face increases) plus APB.
    APB is not modeled as a coverage in this engine, so its slots stay
    inactive / 0.
    """
    from suiteview.core.rates import Rates

    snap: Dict[str, object] = {}
    segments = sorted(
        (s for s in policy.segments if getattr(s, "is_base", True)),
        key=lambda s: s.coverage_phase,
    )
    issue_date = policy.issue_date

    def months_between(d0, d1):
        if d0 is None or d1 is None:
            return 0
        rd = relativedelta(d1, d0)
        return rd.years * 12 + rd.months

    last_active = 0
    for index in (1, 2, 3):
        seg = segments[index - 1] if index - 1 < len(segments) else None
        # A base segment with positive face is active unless terminated. The
        # status carries the raw CyberLife code ("0" = active), so test for the
        # terminated marker rather than a literal "A".
        active = bool(
            seg and seg.face_amount > 0 and str(seg.status or "").strip().upper() != "T"
        )
        seg_issue = seg.issue_date if seg else None
        cov_months = (months_between(seg_issue, month_date) + 1) if active else 0
        terminated = int(getattr(seg, "months_since_terminated", 0) or 0) if seg else 0
        cov_months_sb = max(0, cov_months - terminated)
        # Policy-anniversary alignment: offset the coverage's own duration so the
        # year rolls on the policy anniversary, not the coverage anniversary.
        pol_offset = months_between(issue_date, seg_issue) % 12 if (active and seg_issue) else 0
        year_cov_ann = (cov_months - 1) // 12 + 1 if cov_months > 0 else 0
        year_pol_ann = (cov_months - 1 + pol_offset) // 12 + 1 if cov_months > 0 else 0
        year_cov_ann_sb = max(1, (cov_months_sb - 1) // 12 + 1) if active else 0
        year_pol_ann_sb = max(1, (cov_months_sb - 1 + pol_offset) // 12 + 1) if active else 0
        if active:
            last_active = index
        snap[f"Cov {index} Active"] = active
        snap[f"Cov {index} Issue Date"] = seg_issue if active else None
        snap[f"Cov {index} Months from Issue"] = cov_months
        snap[f"Cov {index} Months from Issue w setback"] = cov_months_sb
        snap[f"Year by Pol Ann Cov {index}"] = year_pol_ann
        snap[f"Year by Pol Ann w setback Cov {index}"] = year_pol_ann_sb
        snap[f"Year by Cov Ann Cov {index}"] = year_cov_ann
        snap[f"Year by Cov Ann w setback Cov {index}"] = year_cov_ann_sb
        snap[f"Original SA Cov {index}"] = float(seg.original_face_amount) if seg else 0.0
        snap[f"Current SA Cov {index}"] = float(seg.face_amount) if seg else 0.0
        snap[f"Band Lock Cov {index}"] = int(seg.original_band) if seg else 0
        snap[f"Issue Age Cov {index}"] = int(seg.issue_age) if seg else 0
        snap[f"Rateclass Cov {index}"] = (seg.rate_class or "") if seg else ""
        snap[f"Table Rating Cov {index}"] = int(seg.table_rating) if seg else 0

    # APB is not modeled as a coverage segment in this engine.
    snap["APB Active"] = False
    snap["Original SA APB"] = 0.0
    snap["Current SA APB"] = 0.0
    snap["Band APB"] = 0
    snap["LastActiveSegment"] = last_active

    current_sa = float(policy.total_face)
    snap["CurrentSA"] = current_sa
    base = policy.base_segment
    # Band is looked up on the specified amount PLUS any rider that bands as base
    # coverage (see core.band_rules); equals current_sa when there is none.
    band = Rates().get_band(
        policy.plancode, policy.band_specified_amount, issue_date=policy.issue_date)
    snap["CurrentBand"] = (
        int(band) if band is not None else (int(base.original_band) if base else 0)
    )

    # Base flat extras (FN/FO). This engine carries a single flat on the base
    # segment; map it to Base Flat1 and leave Base Flat2 at 0.
    base_flat = 0.0
    if base and base.flat_extra and base.flat_extra > 0:
        # Strict: flat extra ceases AT the cease-date anniversary (matches
        # _charge_active in monthly_deduction) — not charged on/after that date.
        if base.flat_cease_date is None or month_date < base.flat_cease_date:
            base_flat = float(base.flat_extra)
    snap["Base Flat1"] = base_flat
    snap["Base Flat2"] = 0.0

    # Coverage_Change (FP): any monitored coverage attribute moved this month.
    change_keys = (
        ["CurrentSA"]
        + [f"Rateclass Cov {i}" for i in (1, 2, 3)]
        + [f"Table Rating Cov {i}" for i in (1, 2, 3)]
        + ["Base Flat1", "Base Flat2"]
    )
    coverage_change = bool(prior) and any(
        snap.get(key) != prior.get(key) for key in change_keys
    )
    snap["Coverage_Change"] = coverage_change
    snap["PolicyChangeAVReduction"] = float(av_reduction)
    return snap


def _age_on_date(birth_date, as_of, age_basis, fallback) -> int:
    """Insured's true age on ``as_of`` under the plancode's age basis.

    ALB (Age Last Birthday): completed years since birth.
    ANB (Age Nearest Birthday): ALB plus one when the insured is nearer the next
        birthday — i.e. 183+ days have elapsed since the last birthday (182 days
        or fewer keeps the current age).

    Returns ``fallback`` (the policy attained age) when the DOB is missing.
    """
    if birth_date is None or as_of is None:
        return fallback
    age = as_of.year - birth_date.year - (
        (as_of.month, as_of.day) < (birth_date.month, birth_date.day)
    )
    if str(age_basis).upper() == "ANB":
        last_birthday = birth_date + relativedelta(years=age)
        if (as_of - last_birthday).days >= 183:
            age += 1
    return age


def _append_face_increase_segment(policy, rates, delta, attained_age, change_date, config=None) -> None:
    """Append the face-increase segment, issued at the insured's true age.

    CyberLife/RERUN band the increase's COI by the new TOTAL specified amount,
    not the increment's own size.

    The increase segment's issue age is the insured's actual age on the increase
    date — computed from the insured DOB under the plancode's age basis (ANB or
    ALB), not the policy's anniversary-based attained age. Falls back to
    ``attained_age`` when the DOB is unavailable.
    """
    from suiteview.core.rates import Rates

    base = policy.base_segment
    age_basis = getattr(config, "age_calc", "") if config is not None else ""
    increase_age = _age_on_date(
        getattr(policy, "insured_birth_date", None), change_date, age_basis, attained_age)
    # Band the increase on the new TOTAL specified amount, including any rider
    # that bands as base coverage (see core.band_rules).
    new_band = Rates().get_band(
        policy.plancode, policy.band_specified_amount + delta,
        issue_date=policy.issue_date)
    new_band = int(new_band) if new_band is not None else base.band
    new_phase = max((s.coverage_phase for s in policy.segments), default=1) + 1
    # The increase matures at the policy maturity age measured from THIS segment's
    # issue age. An off-anniversary increase (with a bumped issue age) therefore
    # matures on its own date — earlier than the base — and stops charges there
    # rather than riding the last COI rate to the base's maturity.
    maturity_age = int(getattr(policy, "maturity_age", 0) or 0)
    seg_maturity_date = (
        change_date + relativedelta(years=maturity_age - increase_age)
        if maturity_age > increase_age
        else None
    )
    new_seg = CoverageSegment(
        coverage_phase=new_phase,
        is_base=True,
        issue_date=change_date,
        issue_age=increase_age,
        rate_sex=base.rate_sex,
        rate_class=base.rate_class,
        face_amount=delta,
        original_face_amount=delta,
        units=delta / (base.vpu or PER_THOUSAND),
        vpu=base.vpu,
        band=new_band,
        original_band=new_band,
        table_rating=base.table_rating,
        flat_extra=base.flat_extra,
        status="A",
        maturity_date=seg_maturity_date,
    )
    policy.segments.append(new_seg)
    _load_segment_rates(rates, new_seg, policy.plancode, config)
    policy.face_amount = sum(s.face_amount for s in policy.segments)


def _primary_insured_rider_face(policy, month_date) -> float:
    """Face of riders on the primary insured that are active at ``month_date``.

    RERUN's vIllustratedDB = base policy DB + the face of all riders covering the
    primary insured (e.g. Signature Term Riders).  A term rider drops off at its
    maturity, so it stops contributing on/after its maturity date.
    """
    total = 0.0
    for rider in getattr(policy, "riders", None) or []:
        if not getattr(rider, "on_primary_insured", False):
            continue
        if not rider_active_on(rider, policy, month_date):
            continue
        total += float(rider.face_amount or 0.0)
    return total


@dataclass(frozen=True)
class WithdrawalInput:
    """Inputs for the pre-policy-change withdrawal step.

    ``av`` and ``cost_basis`` are beginning-of-step dollars after any
    pre-withdrawal interest for CyberLife timing.  ``cap_loan`` is the
    post-capitalization beginning loan state used for debt limits.
    """

    state: MonthlyState
    policy: IllustrationPolicyData
    config: PlancodeConfig
    rates: IllustrationRates
    rate_year: int
    attained_age: int
    month_date: date
    av: float
    cost_basis: float
    month_inputs: object | None
    cap_loan: LoanState
    is_anniversary: bool
    options: IllustrationOptions
    defer_guideline_recalc: bool = False


def _process_withdrawal(inputs: WithdrawalInput) -> WithdrawalResult:
    """Compute and APPLY one month's withdrawal (CalcEngine AX..BU).

    Runs BEFORE the dated policy changes (the workbook pipeline order). A
    withdrawal that reduces the specified amount is processed like a face
    decrease — newest coverage first, no extra SCR charge (the partial
    surrender charge is already inside the gross) — and fires the same
    target/guideline/7-pay recompute as any coverage change.
    """
    state = inputs.state
    policy = inputs.policy
    config = inputs.config
    rates = inputs.rates
    rate_year = inputs.rate_year
    attained_age = inputs.attained_age
    month_date = inputs.month_date
    av = inputs.av
    cost_basis = inputs.cost_basis
    month_inputs = inputs.month_inputs
    cap_loan = inputs.cap_loan
    is_anniversary = inputs.is_anniversary
    options = inputs.options
    defer_guideline_recalc = inputs.defer_guideline_recalc

    request = month_inputs.withdrawal if month_inputs is not None else 0.0
    gross_request = month_inputs.withdrawal_gross if month_inputs is not None else 0.0
    scr_rates = {
        seg.coverage_phase: _segment_surrender_rate(
            policy, seg, rates, rate_year, month_date, config,
        )
        for seg in policy.segments
    }
    debt = (
        cap_loan.rg_loan_princ + cap_loan.rg_loan_accrued
        + cap_loan.pf_loan_princ + cap_loan.pf_loan_accrued
        + cap_loan.vbl_loan_princ + cap_loan.vbl_loan_accrued
    )
    wd = compute_withdrawal(
        av, policy, config, scr_rates, request,
        gross_request=gross_request,
        corridor_rate=get_corridor_factor(
            policy.plancode, attained_age, config.corridor_code),
        prior_total_md=state.total_deduction,
        policy_debt=debt,
        cost_basis=cost_basis,
        withdrawals_to_date=state.withdrawals_to_date,
        withdrawals_ytd=state.withdrawals_ytd,
        is_anniversary=is_anniversary,
    )
    if wd.face_decrease > MONEY_EPSILON:
        before = _solve_guideline_state(
            policy, config, attained_age, month_date, options)
        seven_pay_before = None
        if not defer_guideline_recalc:
            seven_pay_start = policy.tamra_7pay_start_date or month_date
            seven_pay_before = _solve_guideline_state(
                policy, config, _attained_age_at(policy, seven_pay_start),
                seven_pay_start, options,
                starting_av=policy.tamra_7pay_start_av,
                active_as_of=month_date,
            ).seven_pay
        before_pv_detail = _safe_guideline_pv_recalc_detail(
            policy, config, attained_age, month_date)
        wd.guideline_before = before
        wd.guideline_before_pv_detail = before_pv_detail
        _reduce_base_face(
            policy, wd.face_decrease, rates, month_date, rate_year,
            charge_scr=False, config=config)
        _reload_policy_band_rates(rates, policy, config)
        targets = compute_target_premiums(policy, config, as_of=month_date)
        policy.mtp = targets.mtp_annual / MONTHS_PER_YEAR
        policy.ctp = targets.ctp_annual
        if not defer_guideline_recalc:
            wd.guideline_recalc = _recalc_guideline_on_change(
                policy, config,
                PolicyChangeEvent(
                    kind=PolicyChangeKind.FACE_AMOUNT,
                    effective_date=month_date,
                    value=policy.total_face),
                attained_age,
                change_date=month_date,
                before=before,
                av=wd.av_post_withdrawal,
                material_change=False,
                options=options,
                before_pv_detail=before_pv_detail,
                seven_pay_before=seven_pay_before,
            )
    return wd


def _withdrawal_state_fields(wd: WithdrawalResult) -> Dict[str, object]:
    """MonthlyState kwargs for the withdrawal block (shared by both pipelines)."""
    return dict(
        input_withdrawal=wd.input_withdrawal,
        max_net_withdrawal=wd.max_net_withdrawal,
        cost_basis_before_wd=wd.cost_basis_before_wd,
        applied_net_withdrawal=wd.applied_net_withdrawal,
        remaining_distribution=wd.remaining_distribution,
        cost_basis_after_wd=wd.cost_basis_after_wd,
        withdrawals_ytd=wd.withdrawals_ytd,
        wd_corridor_amount=wd.corridor_amount,
        wd_reduces_sa=wd.reduces_sa,
        wd_partial_sc=wd.partial_sc,
        gross_withdrawal=wd.gross_withdrawal,
        av_post_withdrawal=wd.av_post_withdrawal,
        wd_face_decrease=wd.face_decrease,
        wd_sa_change_by_cov=dict(wd.sa_change_by_cov),
    )


def _apply_policy_change(
    policy, config, change, attained_age, change_date, rates, rate_year, av,
    options=None, defer_guideline_recalc=False, capture_guideline_before=True,
) -> _PolicyChangeOutcome:
    """Mutate the (private) policy state for one change at its effective month.

    - DB_OPTION: RERUN keeps the death benefit LEVEL at the change — A->B reduces
      the specified amount by the current account value (so DB = (face-AV)+AV) and
      B->A adds it back. B->A is a TAMRA material change (CalcEngine KZ "BA").
    - FACE_AMOUNT decrease: reduce existing segment(s) newest-first and DEDUCT the
      decreased coverage's surrender charge from AV.
    - FACE_AMOUNT increase: append a new segment at the current attained age with
      its own COI/EPU/SCR rates; TAMRA material change.

    After any specified-amount movement (vPolicyChangeIndicator) the targets
    (vMTP/vCTP) are recomputed from rates and the guideline premiums (GLP/GSP)
    are recalculated by the attained-age delta method; a material change also
    restarts the 7-pay period. The before-change guideline solve runs BEFORE the
    mutation so it sees the pre-change coverage basis.
    """
    outcome = _PolicyChangeOutcome()
    face_before = sum(s.face_amount for s in policy.segments) or policy.face_amount

    md = change.metadata or {}
    fully_injected = {"new_glp", "new_gsp", "new_7pay"} <= md.keys()
    before = None
    seven_pay_before = None
    before_pv_detail: Dict[str, object] = {}
    if (
        capture_guideline_before
        and (
            _will_alter_coverage(policy, change, face_before, av)
            or _will_alter_guideline_charge_basis(policy, change)
        )
        and not fully_injected
    ):
        before = _solve_guideline_state(
            policy, config, attained_age, change_date, options)
        if not defer_guideline_recalc:
            seven_pay_start = policy.tamra_7pay_start_date or change_date
            seven_pay_before = _solve_guideline_state(
                policy, config, _attained_age_at(policy, seven_pay_start),
                seven_pay_start, options,
                starting_av=policy.tamra_7pay_start_av,
                active_as_of=change_date,
            ).seven_pay
        before_pv_detail = _safe_guideline_pv_recalc_detail(
            policy, config, attained_age, change_date)
        outcome.guideline_before = before
        outcome.guideline_before_pv_detail = before_pv_detail

    if change.kind == PolicyChangeKind.DB_OPTION:
        old = str(policy.db_option or "").upper()
        new = str(change.value or "").upper()
        if new and new != old:
            # The SA adjustment uses the whole-dollar AV entering the month —
            # RERUN truncates (100,000 face − AV 7,312.75 → SA 92,688).
            av_whole = float(math.floor(max(av, 0.0)))
            detail: Dict[str, object] = {
                "Prev DBO": old,                 # BW
                "Input DBO": new,                # BY
                "DBO Changed": True,             # BZ
                "Change Type": old + new,        # CA — "AB" / "BA"
                "DBO Change Allowed": True,      # CC
            }
            if old == DB_OPTION_LEVEL and new == DB_OPTION_INCREASING:
                # Level-DB mechanic: shift AV out of the specified amount.
                # The reduction is processed like a face decrease INCLUDING the
                # decreased units' surrender charge (RERUN deducts it from AV).
                cuts = _reduce_base_face(
                    policy, av_whole, rates, change_date, rate_year,
                    charge_scr=config.partial_surrender_charge,
                    config=config,
                )
                outcome.av_adjustment += cuts.av_adjustment
                outcome.coverage_changed = True
                detail["DBO Face Decrease"] = av_whole          # CD
                detail["DBO Face Increase"] = 0.0               # CO
                detail["Total PSC DBO"] = -cuts.av_adjustment   # CM
                for i, (phase, cut) in enumerate(sorted(cuts.cuts_by_phase.items()), 1):
                    detail[f"DBO Decrease Cov {i}"] = cut        # CE..CG
                    detail[f"DBO PSC Cov {i}"] = cuts.psc_by_phase.get(phase, 0.0)  # CI..CK
            elif old == DB_OPTION_INCREASING and new == DB_OPTION_LEVEL:
                # Inverse: fold the AV back into the specified amount (in place,
                # no new segment — this is not an elective face increase).
                base = policy.base_segment
                if base is not None and av_whole > 0.0:
                    base.face_amount += av_whole
                    base.units += av_whole / (base.vpu or PER_THOUSAND)
                    policy.face_amount = sum(s.face_amount for s in policy.segments)
                    outcome.coverage_changed = True
                outcome.material_change = True  # KZ fires on "BA"
                detail["DBO Face Decrease"] = 0.0
                detail["DBO Face Increase"] = av_whole           # CO
                detail["DBO Increase Cov 1"] = av_whole          # CP
                detail["Total PSC DBO"] = 0.0
            policy.db_option = new
            detail["DBO"] = new                                  # CT
            detail["Total SA"] = policy.total_face               # CU
            outcome.dbo_detail = detail
    elif change.kind == PolicyChangeKind.FACE_AMOUNT:
        new_total = float(change.value)
        delta = new_total - face_before
        detail = {
            "Input Face": new_total,             # CW
            "Change in Input Face": delta,       # CX
            "Specified Face Decrease": 0.0,      # CY
            "Specified Face Increase": 0.0,      # DJ
            "Total PSC Spec Dec": 0.0,           # DH
        }
        if delta < -1e-6:
            cuts = _reduce_base_face(
                policy,
                -delta,
                rates,
                change_date,
                rate_year,
                charge_scr=(
                    config.partial_surrender_charge
                    and policy.decrease_charge_allowed is not False
                    and bool(md.get("charge_surrender", True))
                ),
                config=config,
            )
            outcome.av_adjustment += cuts.av_adjustment
            outcome.coverage_changed = True
            detail["Specified Face Decrease"] = -delta
            detail["Total PSC Spec Dec"] = -cuts.av_adjustment
            for i, (phase, cut) in enumerate(sorted(cuts.cuts_by_phase.items()), 1):
                detail[f"Spec Decrease Cov {i}"] = cut           # CZ..DB
                detail[f"Spec PSC Cov {i}"] = cuts.psc_by_phase.get(phase, 0.0)  # DD..DF
        elif delta > 1e-6:
            _append_face_increase_segment(policy, rates, delta, attained_age, change_date, config)
            outcome.coverage_changed = True
            outcome.material_change = True
            detail["Specified Face Increase"] = delta
            detail[f"Spec Increase Cov {len(policy.segments)}"] = delta  # DK..DM
        detail["Total SA"] = policy.total_face                   # DO
        outcome.face_detail = detail
    elif change.kind == PolicyChangeKind.RATE_CLASS:
        # Rate-class change applies to the entire base coverage: the issue
        # segment AND every increase segment (including an increase added the
        # same day, since FACE_AMOUNT is ordered ahead of RATE_CLASS). Reload
        # each segment's class-keyed schedules; targets/guideline recompute via
        # coverage_changed.
        # TODO: validate vs RERUN (sINPUT_Rateclass_Change) on the laptop.
        new_class = str(change.value or "").strip().upper()
        base = policy.base_segment
        if new_class and base is not None and any(
            new_class != (seg.rate_class or "").upper() for seg in policy.segments
        ):
            for seg in policy.segments:
                if new_class != (seg.rate_class or "").upper():
                    seg.rate_class = new_class
                    _load_segment_rates(rates, seg, policy.plancode, config)
            policy.rate_class = new_class
            _reband_benefits(rates, policy)
            outcome.coverage_changed = True
    elif change.kind == PolicyChangeKind.SUBSTANDARD:
        # Waivers store a multiplier, not a table number. Change their private
        # basis before targets, deductions and guideline after-solves consume it.
        new_table = int(change.value or 0)
        base = policy.base_segment
        if base is not None and new_table != base.table_rating:
            base.table_rating = new_table
            if new_table == 0:
                base.table_cease_date = change_date
            else:
                base.table_cease_date = None
            for benefit in policy.benefits:
                if benefit.benefit_type in ("3", "4"):
                    benefit.rating_factor = 1.0 + config.table_rating_factor * new_table
            outcome.coverage_changed = True
    elif change.kind == PolicyChangeKind.RIDER_DROP:
        # Drop/changed rider or benefit: value is the new amount (0 = drop).
        # metadata["target"]: "cov:<phase>" or "ben:<key>:<phase>".
        # TODO: validate vs RERUN rider-change inputs on the laptop.
        target = str((change.metadata or {}).get("target", ""))
        new_amount = float(change.value or 0.0)
        if target.startswith("cov:"):
            phase = int(target.split(":", 1)[1])
            for rider in policy.riders:
                if rider.coverage_phase == phase:
                    if new_amount <= 0.0:
                        rider.is_active = False
                    else:
                        rider.face_amount = new_amount
                        rider.units = new_amount / (rider.vpu or PER_THOUSAND)
                    outcome.coverage_changed = True
        elif target.startswith("ben:"):
            parts = target.split(":")
            ben_key, phase = parts[1], int(parts[2]) if len(parts) > 2 else 0
            for ben in policy.benefits:
                key = (ben.benefit_type or "") + (ben.benefit_subtype or "")
                if key == ben_key and (phase == 0 or ben.coverage_phase == phase):
                    if new_amount <= 0.0:
                        ben.is_active = False
                    else:
                        ben.benefit_amount = new_amount
                    outcome.coverage_changed = True
    else:
        logger.warning("Policy change kind %s is not implemented; ignored", change.kind)

    if outcome.coverage_changed:
        if policy.is_mec:
            outcome.material_change = False
        _reload_policy_band_rates(rates, policy, config)
        targets = compute_target_premiums(policy, config, as_of=change_date)
        policy.mtp = targets.mtp_annual / MONTHS_PER_YEAR
        policy.ctp = targets.ctp_annual
        if not defer_guideline_recalc:
            outcome.guideline_recalc = _recalc_guideline_on_change(
                policy, config, change, attained_age,
                change_date=change_date,
                before=before,
                av=av,
                material_change=outcome.material_change,
                options=options,
                before_pv_detail=before_pv_detail,
                seven_pay_before=seven_pay_before,
            )
    return outcome


def _will_alter_coverage(policy, change, face_before: float, av: float) -> bool:
    """Predict whether the change will move the specified amount (and so needs
    a before-change guideline solve captured ahead of the mutation)."""
    if change.kind == PolicyChangeKind.FACE_AMOUNT:
        return abs(float(change.value) - face_before) > 1e-6
    if change.kind == PolicyChangeKind.DB_OPTION:
        old = str(policy.db_option or "").upper()
        new = str(change.value or "").upper()
        return bool(new) and new != old
    return False


def _will_alter_guideline_charge_basis(policy, change) -> bool:
    if not policy.is_gpt:
        return False
    if change.kind == PolicyChangeKind.RATE_CLASS:
        base = policy.base_segment
        new_class = str(change.value or "").strip().upper()
        return (
            base is not None
            and bool(new_class)
            and new_class != (base.rate_class or "").upper()
        )
    if change.kind == PolicyChangeKind.SUBSTANDARD:
        base = policy.base_segment
        return base is not None and int(change.value or 0) != base.table_rating
    if change.kind != PolicyChangeKind.RIDER_DROP:
        return False
    target = str((change.metadata or {}).get("target", ""))
    new_amount = float(change.value or 0.0)
    if target.startswith("cov:"):
        phase = int(target.split(":", 1)[1])
        for rider in policy.riders:
            if rider.coverage_phase == phase and rider.is_active:
                return new_amount <= 0.0 or abs(float(rider.face_amount) - new_amount) > 1e-6
    if target.startswith("ben:"):
        parts = target.split(":")
        ben_key = parts[1] if len(parts) > 1 else ""
        phase = int(parts[2]) if len(parts) > 2 else 0
        for ben in policy.benefits:
            key = (ben.benefit_type or "") + (ben.benefit_subtype or "")
            if key == ben_key and (phase == 0 or ben.coverage_phase == phase) and ben.is_active:
                return new_amount <= 0.0 or abs(float(ben.benefit_amount) - new_amount) > 1e-6
    return False


def _months_into_policy_year(policy, as_of) -> int:
    """Months elapsed since the last policy anniversary (0 = on an anniversary)."""
    issue = policy.issue_date
    if issue is None or as_of is None:
        return 0
    months = (as_of.year - issue.year) * 12 + (as_of.month - issue.month)
    if as_of.day < issue.day:
        months -= 1
    return max(0, months) % 12


def _solve_guideline_state(
    policy, config, attained_age, change_date, options, starting_av: float = 0.0,
    active_as_of=None,
):
    """Solve GLP/GSP/7-pay for the policy's CURRENT coverage state.

    Default: the monthly accumulated-value solve (``monthly_guideline``) — the
    exact monthly equivalent of the workbook's compressed commutation. With
    ``IllustrationOptions.guideline_by_search`` on: a premium search on the
    real calc engine (guaranteed COIs, statutory interest, current expenses).

    ``active_as_of`` gates benefit existence for a re-solve dated in the past
    (the 7-pay period start): the workbook keys active flags off the CHANGE
    row, so a since-ceased benefit is excluded from the whole solve.
    """
    guar = load_rates(policy, config, coi_scale=0)
    if options is not None and getattr(options, "guideline_by_search", False):
        from suiteview.illustration.core.guideline_calc import search_guideline_premiums

        # TODO: the search path does not yet gate since-ceased benefits by the
        # change date (active_as_of) — it projects from the solve start.
        return search_guideline_premiums(
            policy, config, guar,
            attained_age=attained_age, as_of=change_date, starting_av=starting_av,
        )

    from suiteview.illustration.core.monthly_guideline import (
        build_guideline_basis,
        solve_guideline_premiums,
    )

    basis = build_guideline_basis(
        policy, config, guar,
        attained_age=attained_age, as_of=change_date,
        months_into_year=_months_into_policy_year(policy, change_date),
        active_as_of=active_as_of,
    )
    return solve_guideline_premiums(basis, starting_av=starting_av)


def _safe_guideline_pv_recalc_detail(
    policy, config, attained_age: int, change_date, active_as_of=None,
) -> Dict[str, object]:
    """Month-by-month present-value GLP/GSP breakdowns for recalc drill-downs.

    Built on the SAME guaranteed-COI basis as ``_solve_guideline_state`` so the
    roll-ups equal the recalc summary. Supplementary display only — returns an
    empty dict rather than failing the projection.
    """
    try:
        from suiteview.illustration.core.guideline_pv import (
            guideline_glp_detail,
            guideline_gsp_detail,
        )
        from suiteview.illustration.core.monthly_guideline import build_guideline_basis

        guar = load_rates(policy, config, coi_scale=0)
        basis = build_guideline_basis(
            policy, config, guar,
            attained_age=attained_age, as_of=change_date,
            months_into_year=_months_into_policy_year(policy, change_date),
            active_as_of=active_as_of,
        )
        return {
            "glp": guideline_glp_detail(basis),
            "gsp": guideline_gsp_detail(basis),
        }
    except Exception:
        logger.debug("Guideline monthly-PV recalc detail unavailable", exc_info=True)
        return {}


def _safe_guideline_pv_detail(
    policy, config, attained_age: int, change_date, active_as_of=None,
) -> Dict[str, object]:
    """After-change GLP detail for the standalone Values-tab PV page."""
    return (_safe_guideline_pv_recalc_detail(
        policy, config, attained_age, change_date, active_as_of) or {}).get("glp", {})


def _safe_seven_pay_pv_detail(policy, config, change_date) -> Dict[str, object]:
    """Month-by-month present-value 7-pay breakdown for the TAMRA recalc sheet.

    Solved at the CURRENT 7-pay period start (the change date after a material
    change) with that period's starting account value and benefit-active flags
    from the change row — the same basis as the level re-solve. Supplementary
    display only — returns an empty dict rather than failing the projection.
    """
    try:
        from suiteview.illustration.core.guideline_pv import guideline_7pay_detail
        from suiteview.illustration.core.monthly_guideline import build_guideline_basis

        start = policy.tamra_7pay_start_date or change_date
        guar = load_rates(policy, config, coi_scale=0)
        basis = build_guideline_basis(
            policy, config, guar,
            attained_age=_attained_age_at(policy, start), as_of=start,
            months_into_year=_months_into_policy_year(policy, start),
            active_as_of=change_date,
        )
        detail = guideline_7pay_detail(basis, starting_av=policy.tamra_7pay_start_av)
        detail["solve_date"] = start
        return detail
    except Exception:
        logger.debug("7-pay monthly-PV recalc detail unavailable", exc_info=True)
        return {}


# Friendly recalc labels for the Values-tab "Guideline Recalc" group.
_CHANGE_KIND_LABELS = {
    PolicyChangeKind.FACE_AMOUNT: "Specified Amount Change",
    PolicyChangeKind.DB_OPTION: "Death Benefit Option Change",
    PolicyChangeKind.RATE_CLASS: "Rate Class Change",
    PolicyChangeKind.SUBSTANDARD: "Substandard Rating Change",
    PolicyChangeKind.RIDER_DROP: "Rider / Benefit Change",
}


def _recalc_guideline_on_change(
    policy,
    config,
    change,
    attained_age: int,
    *,
    change_date,
    before,
    av: float,
    material_change: bool,
    options=None,
    before_pv_detail: Optional[Dict[str, object]] = None,
    seven_pay_before: Optional[float] = None,
) -> Dict[str, object]:
    """Recalculate GLP/GSP/7-pay at a policy change.

    RERUN (Guideline_Premiums rows 5..10): the new guideline premiums are the
    attained-age delta — new = prior + (after − before) — floored to a
    monthly-divisible cent (TRUNC(x/12,2)·12). The 7-pay level is fully
    recomputed at the after-change state (offset by the account value at the
    change); a MATERIAL change also restarts the 7-pay period. Unlike the
    workbook, recalcs are unlimited.

    ``change.metadata`` may inject reference values (``new_glp`` / ``new_gsp``
    / ``new_7pay``) so AV/segment/target mechanics can be validated
    independently of the guideline calculator.
    """
    md = change.metadata or {}
    new_glp = md.get("new_glp")
    new_gsp = md.get("new_gsp")
    new_7pay = md.get("new_7pay")

    # TAMRA context BEFORE any reset: the change's position in the current
    # 7-pay window decides which TAMRA sheet the Values tab shows —
    # no recalc needed (outside the window, no new period), a recalc inside
    # the window (back-tested for MEC), or a brand-new 7-pay period.
    tamra_year_at_change = _tamra_year(policy, change_date)
    seven_pay_prior = policy.tamra_7pay_level
    seven_pay_prior_start = policy.tamra_7pay_start_date

    # A MATERIAL change restarts the 7-pay period at the change date with the
    # current account value as the period's starting AV (CH24 "Starting AV").
    if material_change and not policy.is_mec:
        policy.tamra_7pay_start_date = change_date
        policy.tamra_7pay_start_av = max(av, 0.0)

    after = None
    if (new_glp is None or new_gsp is None) and before is not None:
        after = _solve_guideline_state(
            policy, config, attained_age, change_date, options)

    # Prior (pre-recalc) values feed both the delta formula and the recalc detail.
    glp_prior = floor_monthly_cent(policy.glp)
    gsp_prior = floor_monthly_cent(policy.gsp)

    if new_glp is not None:
        policy.glp = floor_monthly_cent(float(new_glp))
    elif after is not None:
        policy.glp = floor_monthly_cent(glp_prior + after.glp - before.glp)
    if new_gsp is not None:
        policy.gsp = floor_monthly_cent(float(new_gsp))
    elif after is not None:
        policy.gsp = floor_monthly_cent(gsp_prior + after.gsp - before.gsp)

    # Mid-year recalc: the anniversary already banked a FULL year of the prior
    # GLP into AccumGLP, so true it up pro-rata for the months remaining in the
    # policy year — change at BOM m keeps (m-1)/12 of the old GLP and accrues
    # (13-m)/12 at the new one. An anniversary-month change (m=1) needs no
    # adjustment: the accumulation later this month reads the already-updated
    # policy.glp (same net effect as RERUN's KT->KU ordering). RERUN's annual
    # input vectors cannot express a mid-year change, so this rule is spec'd by
    # Robert (2026-07-17), not the workbook.
    accum_glp_adjustment = 0.0
    accum_glp_months_remaining = 0
    if policy.issue_date is not None:
        month_in_year = ((change_date.year - policy.issue_date.year) * 12
                         + (change_date.month - policy.issue_date.month)) % 12 + 1
        if month_in_year > 1 and abs(policy.glp - glp_prior) > MONEY_EPSILON:
            accum_glp_months_remaining = 13 - month_in_year
            accum_glp_adjustment = round(
                accum_glp_months_remaining / MONTHS_PER_YEAR * (policy.glp - glp_prior), 2)

    # Expose the before/after solve so the Values tab can explain the recalc.
    # Only the genuine attained-age delta path (a before AND after solve) has
    # calc detail to show; a fully-injected recalc has no before/after solve.
    recalc_detail: Dict[str, object] = {}
    if before is not None and after is not None:
        after_pv_detail = _safe_guideline_pv_recalc_detail(
            policy, config, attained_age, change_date)
        recalc_detail = {
            "change_kind": md.get("change_label") or _CHANGE_KIND_LABELS.get(
                change.kind, change.kind.name.replace("_", " ").title()),
            "change_date": change_date,
            "glp_before": before.glp,
            "glp_after": after.glp,
            "gsp_before": before.gsp,
            "gsp_after": after.gsp,
            "glp_prior": glp_prior,
            "glp_new": policy.glp,
            "gsp_prior": gsp_prior,
            "gsp_new": policy.gsp,
            "monthly_pv_recalc": {
                "before": before_pv_detail or {},
                "after": after_pv_detail,
            },
            "monthly_pv": (after_pv_detail or {}).get("glp", {}),
        }

    # The 7-pay LEVEL recalculates on ANY coverage change (KY fires on the
    # policy-change indicator), solved from the CURRENT 7-pay period start —
    # the change date after a material change, otherwise the original start
    # date — with that period's starting account value.
    seven_pay_after = None
    if new_7pay is not None:
        policy.tamra_7pay_level = floor_monthly_cent(float(new_7pay))
        seven_pay_after = float(new_7pay)
    elif before is not None:
        start = policy.tamra_7pay_start_date or change_date
        start_age = _attained_age_at(policy, start)
        seven_solve = _solve_guideline_state(
            policy, config, start_age, start, options,
            starting_av=policy.tamra_7pay_start_av,
            # Benefit active flags come from the CHANGE row even when the
            # solve is dated at the original period start (FR159..FR165 all
            # INDEX at FM158) — a since-ceased PW is excluded entirely.
            active_as_of=change_date,
        )
        policy.tamra_7pay_level = floor_monthly_cent(seven_solve.seven_pay)
        seven_pay_after = seven_solve.seven_pay

    # TAMRA sheet detail: classify the change against the 7-pay window and
    # (when the recalc matters) attach the 7-pay PV breakdown. Only recalcs
    # with a genuine before/after solve carry drill-down detail.
    if recalc_detail:
        if policy.is_mec:
            tamra_case = "no_recalc"
        elif material_change:
            tamra_case = "new_period"
        elif tamra_year_at_change <= 7:
            tamra_case = "within_period"
        else:
            tamra_case = "no_recalc"
        recalc_detail.update({
            "tamra_case": tamra_case,
            "tamra_year_at_change": tamra_year_at_change,
            "seven_pay_prior": seven_pay_prior,
            "seven_pay_before": seven_pay_before,
            "seven_pay_after": seven_pay_after,
            "seven_pay_new": policy.tamra_7pay_level,
            "seven_pay_prior_start": seven_pay_prior_start,
            "seven_pay_window_start": policy.tamra_7pay_start_date or change_date,
            "seven_pay_start_av": policy.tamra_7pay_start_av,
        })
        if tamra_case != "no_recalc":
            recalc_detail["seven_pay_pv"] = _safe_seven_pay_pv_detail(
                policy, config, change_date)

    # Carried even on the injected-values path (empty recalc_detail): the
    # accumulation step in process_month reads it via .get(); the Values-tab
    # recalc summary shows the amount with its months-remaining factor.
    if accum_glp_adjustment:
        recalc_detail["accum_glp_adjustment"] = accum_glp_adjustment
        recalc_detail["accum_glp_months_remaining"] = accum_glp_months_remaining

    return recalc_detail


def _attained_age_at(policy, as_of) -> int:
    """Attained age (anniversary-aligned) at a date."""
    issue = policy.issue_date
    if issue is None or as_of is None:
        return policy.attained_age
    years = as_of.year - issue.year
    if (as_of.month, as_of.day) < (issue.month, issue.day):
        years -= 1
    return policy.issue_age + max(0, years)


def _days_to_next_anniversary(issue_date: date, month_date: date) -> int:
    """RERUN vDaysToNextAnnivesary (CalcEngine col Q = P − C).

    Calendar days from the current monthliversary to the next policy
    anniversary. ``P`` (col P) = the issue month/day in this calendar year if the
    current month is before the issue month, otherwise next year — so at an
    anniversary month the gap is a full year (365/366)."""
    add_year = 0 if month_date.month < issue_date.month else 1
    year = month_date.year + add_year
    day = min(issue_date.day, calendar.monthrange(year, issue_date.month)[1])
    next_anniversary = date(year, issue_date.month, day)
    return (next_anniversary - month_date).days


def _advance_loan_factors(config: PlancodeConfig, days_to_next_anniversary: int) -> tuple[float, float]:
    """RERUN vAdvRegIntFactor (X) / vAdvPrefIntFactor (Y): the unearned-interest
    fraction for the remaining days of the policy year (cols X/Y)."""
    fraction = days_to_next_anniversary / DAYS_PER_YEAR
    return (
        config.loan_charge_rate_guar * fraction,
        config.pref_loan_charge_rate_guar * fraction,
    )


def _advance_month(policy_year: int, policy_month: int) -> tuple[int, int]:
    """Advance policy year/month by one month."""
    if policy_month == 12:
        return policy_year + 1, 1
    return policy_year, policy_month + 1


def _policy_counters_for_date(policy: IllustrationPolicyData, month_date) -> tuple[int, int, int]:
    if policy.issue_date is None:
        next_year, next_month = _advance_month(policy.policy_year, policy.policy_month)
        return next_year, next_month, policy.duration + 1
    completed_months = _completed_months(policy.issue_date, month_date)
    duration = completed_months + 1
    policy_year = (completed_months // 12) + 1
    policy_month = (completed_months % 12) + 1
    return policy_year, policy_month, duration


def _shadow_rider_charges_from_deduction(policy: IllustrationPolicyData, deduction) -> float:
    ccv_charge = 0.0
    for benefit in policy.benefits:
        if benefit.benefit_type != "A":
            continue
        benefit_key = (benefit.benefit_type or "") + (benefit.benefit_subtype or "")
        ccv_charge += deduction.benefit_charge_detail.get(benefit_key, 0.0)
    return max(0.0, deduction.rider_charges + deduction.benefit_charges - ccv_charge)


def _completed_months(start, end) -> int:
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def _accumulate_guideline_premium(
    state: MonthlyState,
    policy: IllustrationPolicyData,
    is_anniversary: bool,
    attained_age: int,
) -> float:
    """Accumulate GLP at each anniversary (CalcEngine KU).

    AccumGLP stops growing once attained age reaches 100. The GLP added is the
    floored vGLP (KT — INT(x/12*100)*12/100).
    """
    if attained_age >= 100:
        return state.accumulated_glp
    return state.accumulated_glp + (
        floor_monthly_cent(policy.glp) if is_anniversary else 0.0
    )


def _record_accum_glp_recalc_detail(
    detail: Dict[str, object],
    *,
    prior_amount: float,
    new_amount: float,
    policy_month: int,
) -> None:
    """Record the actual AccumGLP transition around a guideline recalc."""
    months_prior = max(0, min(12, int(policy_month) - 1))
    detail.update({
        "accum_glp_prior_amount": prior_amount,
        "accum_glp_months_prior": months_prior,
        "accum_glp_months_after": 12 - months_prior,
        "accum_glp_prorata_delta": round(new_amount - prior_amount, 2),
        "accum_glp_new_amount": new_amount,
    })


def _apply_guideline_forceout(
    gsp: float,
    accumulated_glp: float,
    premiums_to_date: float,
    withdrawals_to_date: float,
    account_value_before_premium: float,
    *,
    enabled: bool,
    has_guideline_limit: bool,
    prior_exception_mode: bool,
) -> tuple[float, float, float]:
    """Guideline force-out (CalcEngine KX).

    The limit is the GREATER of GSP and accumulated GLP. The force-out is the
    cumulative premium-net-of-withdrawals above that limit, capped by available
    account value. It is disabled when TEFRA conformance is off, when the policy
    has no guideline-premium limit, or once exception mode is on (so the
    exception premium is not immediately clawed back).
    """
    if (not enabled) or (not has_guideline_limit) or prior_exception_mode:
        return 0.0, withdrawals_to_date, account_value_before_premium

    guideline_limit = max(gsp, accumulated_glp)
    excess = max(0.0, (premiums_to_date - withdrawals_to_date) - guideline_limit)
    forceout = min(max(0.0, account_value_before_premium), excess)
    return forceout, withdrawals_to_date + forceout, account_value_before_premium - forceout


def _tamra_starting_lowest_face(policy: IllustrationPolicyData) -> float:
    amount = float(policy.tamra_7year_lowest_db)
    if "tamra_7year_lowest_db" in policy.starting_record_fields:
        return amount
    return amount or float(policy.total_face)


def _tamra_year(policy: IllustrationPolicyData, month_date) -> int:
    """Policy year within the active 7-pay window (CalcEngine LD).

    Returns 999 when there is no active 7-pay start date (no TAMRA cap).
    """
    start = policy.tamra_7pay_start_date
    if start is None or month_date is None:
        return 999
    if month_date < start:
        return 999
    months = (month_date.year - start.year) * 12 + (month_date.month - start.month)
    if month_date.day < start.day:
        months -= 1
    return (max(months, 0) // 12) + 1


_MODE_INTERVALS = {"M": 1, "Q": 3, "S": 6, "A": 12}


def _billing_mode(policy: IllustrationPolicyData) -> str:
    """Map the policy's billing frequency (months between payments) to a mode."""
    return {1: "M", 3: "Q", 6: "S", 12: "A"}.get(
        int(getattr(policy, "billing_frequency", 12) or 12), "A")


def _tamra_month_of_year(policy: IllustrationPolicyData, month_date) -> int:
    """Month (1-12) within the current TAMRA year (CalcEngine LC); 0 if none."""
    start = policy.tamra_7pay_start_date
    if start is None or month_date is None:
        return 0
    if month_date < start:
        return 0
    months = (month_date.year - start.year) * 12 + (month_date.month - start.month)
    if month_date.day < start.day:
        months -= 1
    return max(months, 0) % 12 + 1


def _payment_counts(prior_state, policy, month_date, next_month, month_inputs) -> tuple[int, int, str]:
    """Modal payment counts for the policy / TAMRA year (CalcEngine LT / LU).

    Counts are recomputed at policy-year and TAMRA-year boundaries. TAMRA years
    may be off-anniversary, so their remaining payments follow policy-anchored
    modal due months rather than the TAMRA month number. The TAMRA count only
    applies inside an active 7-pay window (years 1..7).
    Returns ``(payment_count_policy_year, payment_count_tamra_year, mode)``.
    """
    mode = (
        month_inputs.premium_mode
        if (month_inputs is not None and month_inputs.premium_mode)
        else _billing_mode(policy)
    )
    interval = _MODE_INTERVALS.get(mode, 12)
    tamra_moy = _tamra_month_of_year(policy, month_date)
    in_period = 1 <= _tamra_year(policy, month_date) <= 7

    def count_due_months(start_policy_month: int, month_count: int) -> int:
        return sum(
            1
            for offset in range(month_count)
            if ((start_policy_month - 1 + offset) % 12) % interval == 0
        )

    if (
        next_month == 1
        or tamra_moy == 1
        or prior_state.payment_count_policy_year == 0
    ):
        pc_policy = count_due_months(next_month, 13 - next_month)
    else:
        pc_policy = prior_state.payment_count_policy_year

    if not in_period:
        pc_tamra = 0
    elif (
        next_month == 1
        or tamra_moy == 1
        or prior_state.payment_count_tamra_year == 0
    ):
        pc_tamra = count_due_months(next_month, 13 - tamra_moy)
    else:
        pc_tamra = prior_state.payment_count_tamra_year

    return pc_policy, pc_tamra, mode


def _tamra_premium_display(prior_state, policy, month_date, next_month, month_inputs) -> dict:
    """Display-only TEFRA/TAMRA and Requested-Premium fields for one month."""
    unscheduled = float(month_inputs.unscheduled_premium) if month_inputs is not None else 0.0
    pc_policy, pc_tamra, mode = _payment_counts(
        prior_state, policy, month_date, next_month, month_inputs
    )
    tamra_year = _tamra_year(policy, month_date)
    tamra_moy = _tamra_month_of_year(policy, month_date)
    in_period = tamra_year <= 7

    current_face = float(policy.total_face)
    if not in_period:
        lowest = _tamra_starting_lowest_face(policy)
    elif tamra_year == 1 and tamra_moy == 1:
        lowest = current_face
    else:
        prior_lowest = prior_state.lowest_7yr_face
        if not prior_lowest and "tamra_7year_lowest_db" not in policy.starting_record_fields:
            prior_lowest = current_face
        lowest = min(prior_lowest, current_face)

    return {
        "unscheduled_premium": unscheduled,
        "planned_premium_mode": mode,
        "payment_count_policy_year": pc_policy,
        "payment_count_tamra_year": pc_tamra,
        "tamra_month_of_year": tamra_moy,
        "tamra_7pay_start_date": policy.tamra_7pay_start_date,
        "lowest_7yr_face": lowest,
    }


def _split_requested_premium(
    policy, config, month_inputs, attained_age, *, exception_period=False,
) -> tuple[float, float]:
    """Requested scheduled (LS) and unscheduled/lumpsum (vLumpsum) premium.

    With no premium schedule at all the modal premium bills every month (the
    workbook's vPlannedPremium fallback); a schedule supplies the per-month
    scheduled amount and dated deposits the lumpsum. No premium is collected on
    or after the maturity date — the policy endows.
    """
    if exception_period or _at_or_after_policy_maturity(policy, config, attained_age):
        return 0.0, 0.0
    total_override = month_inputs.total_premium if month_inputs is not None else None
    if total_override is None:
        return float(policy.modal_premium or 0.0), 0.0
    requested_scheduled = float(month_inputs.scheduled_premium or 0.0)
    requested_lumpsum = float(month_inputs.unscheduled_premium or 0.0)
    return requested_scheduled, requested_lumpsum


def _loan_balance_for_levelizing(loan_state) -> bool:
    """True when the policy carries any loan (levelizing is off with a loan).

    RERUN gates on SUM(LX:LY, MB:MC) (fixed + variable principal and accrued);
    we include every loan bucket so any outstanding debt disables levelizing.
    """
    total = (
        loan_state.rg_loan_princ + loan_state.rg_loan_accrued
        + loan_state.pf_loan_princ + loan_state.pf_loan_accrued
        + loan_state.vbl_loan_princ + loan_state.vbl_loan_accrued
    )
    return total > MONEY_EPSILON


def _tamra_force(options: IllustrationOptions, policy: IllustrationPolicyData) -> bool:
    """Whether the 7-pay limit participates in this month's allowance chain."""
    return (
        options.tamra_cap_enabled
        and policy.has_defined_life_insurance
        and policy.tamra_7pay_level > 0
    )


def _premium_state_fields(allowances: PremiumAllowances, requested_total: float) -> dict:
    """MonthlyState fields for the premium-cap block, from an allowance chain."""
    applied = allowances.applied_total_premium
    return {
        "requested_premium": requested_total,
        "premium_cap": allowances.annual_cap_2,
        "premium_capped": applied < requested_total - MONEY_EPSILON,
        "premium_capped_by_guideline": allowances.capped_by_guideline,
        "premium_capped_by_tamra": allowances.capped_by_tamra,
        "prem_less_wd": allowances.prem_less_wd,
        "applied_lumpsum": allowances.applied_lumpsum,
        "applied_scheduled_premium": allowances.applied_scheduled_premium,
        "scheduled_prem_cap": allowances.scheduled_prem_cap,
        "scheduled_cap_by_guideline": allowances.scheduled_cap_by_guideline,
        "scheduled_cap_by_tamra": allowances.scheduled_cap_by_tamra,
        "transition_year_active": allowances.in_transition_year,
        "levelized_max_premium": allowances.levelized_max_premium,
        "apply_levelized": allowances.apply_levelized,
        "premium_allowance_detail": allowances.to_detail(),
    }


def _guideline_limit_reached(
    config: PlancodeConfig,
    allowances: PremiumAllowances,
    *,
    attained_age: int,
    beginning_of_year: bool,
    prior_limit_reached: bool,
) -> bool:
    """Guideline Limit Reached — CalcEngine SX.

        =IF(vYear>=sMaturityYear, FALSE,
            IF(vBeginningOfYearCalc, NW=NU, SX_prior))

    Latched at the start of each policy year to whether the GP level cap is the
    binding constraint on the scheduled premium. NV is floored to whole cents,
    so comparing NW to the unrounded NU loses the flag for fractional-cent
    allowances. Use the recorded cap source and compare NW to the payable NV
    instead. It is carried forward untouched the rest of the year and forced
    off from the maturity year on. With levelizing, this means the year's
    scheduled premiums bind the guideline cap, not that all annual room has
    already been collected. GEP may therefore fund a midyear shortfall while
    room remains for the later levelized payments.
    """
    if attained_age >= config.maturity_age:
        return False
    if beginning_of_year:
        return (
            allowances.scheduled_cap_by_guideline
            and allowances.levelized_max_premium == allowances.scheduled_prem_cap
        )
    return prior_limit_reached


@dataclass
class _ExceptionPremium:
    # ── Monthly Deduction premium (Phase 1 — capped at the guideline room) ──
    md_premium_mode: bool = False
    md_prem: float = 0.0           # grossed-up MD premium actually paid (capped)
    md_prem_gross: float = 0.0     # account-value restoration the MD premium funded
    md_prem_capped: bool = False   # the guideline room limited the MD premium
    md_discount: float = 0.0       # COI saving from lifting the AV pre-deduction
    # ── GP exception premium (Phase 2 — uncapped, on the residual) ──
    mode: bool = False             # GP exception mode (latches; drives protection/lapse)
    # == mode; kept for the MonthlyState.gp_exception_mode wiring (force-out
    # bypass + latch apply to GP exceptions only, never the MD premium).
    is_gp_exception: bool = False
    gross: float = 0.0             # GP exception gross shortfall covered
    prem: float = 0.0              # grossed-up GP exception premium
    discount: float = 0.0          # COI saving (CalcEngine TA) when the exception fires
    percentage_load: float = 0.0   # TPP load charged on MD + GP exception premiums
    flat_load: float = 0.0         # flat dollar load charged per generated premium
    gp_percentage_load: float = 0.0
    gp_flat_load: float = 0.0
    av_after_exception: float = 0.0
    requires_option_a: bool = False

    @property
    def total_prem(self) -> float:
        """Combined premium added this month (MD + GP exception)."""
        return self.md_prem + self.prem


def _monthly_deduction_premium_active(options: IllustrationOptions, policy_year: int) -> bool:
    """Whether the Monthly Deduction premium applies in this policy year.

    With no bounding windows (``monthly_deduction_windows`` is None) the premium
    runs the whole projection — active from the forecast date to maturity. When
    the Input tab supplies windows, the premium is active ONLY within a window
    (``start_year`` through ``end_year`` inclusive; ``end_year`` None runs to
    maturity), so a Monthly Deduction row bounds itself and later premium rows
    take over once its window ends.
    """
    if not options.pay_monthly_deduction:
        return False
    windows = options.monthly_deduction_windows
    if not windows:
        return True
    return any(
        policy_year >= start and (end is None or policy_year <= end)
        for start, end in windows
    )


def _billable_to_md_active(options: IllustrationOptions, policy_year: int) -> bool:
    """Whether a "Billable to MD" premium window covers this policy year.

    Within the window the row's scheduled billable premium pays normally until
    the first month it can no longer keep the policy in force; the engine then
    latches ``MonthlyState.billable_md_switched``, stops the billable premium,
    and pays the Monthly Deduction premium instead (GP exception backstop once
    the guideline room runs out).
    """
    windows = options.billable_to_md_windows
    if not windows:
        return False
    return any(
        policy_year >= start and (end is None or policy_year <= end)
        for start, end in windows
    )


def _b2md_latch_allowed(options: IllustrationOptions, month_date: date) -> bool:
    """Whether the Billable-to-MD hand-off may latch this month.

    A "Lumpsum to Next Premium" bridge only funds the policy to its next modal
    premium, leaving the account value near breakeven in the meantime. Latching
    the switch during that window would hand off to Monthly Deduction premiums
    before the regularly billable premium is ever paid — defeating the purpose
    of the run, which is to reach that premium and measure how long it sustains
    the policy. ``billable_to_md_no_latch_before`` suppresses the latch for
    every month strictly before the next premium date; None means no floor.
    """
    floor = options.billable_to_md_no_latch_before
    return floor is None or month_date >= floor


@dataclass(frozen=True)
class ExceptionPremiumInput:
    """Inputs for the MD/GP exception-premium gross-up.

    ``av_after_charge`` is after deduction and asset charge, before any MD or GP
    exception premium. ``coi_rate`` is the monthly COI rate per $1,000 used for
    the COI-saving feedback.
    """

    options: IllustrationOptions
    policy: IllustrationPolicyData
    config: PlancodeConfig
    rates: IllustrationRates
    rate_year: int
    av_after_charge: float
    coi_rate: float
    guideline_limit_reached: bool
    past_snet: bool
    prior_exception_mode: bool
    prior_lapsed: bool
    attained_age: int
    md_premium_active: bool = False
    total_deduction: float = 0.0
    guideline_limit: float = 0.0
    premiums_to_date: float = 0.0
    withdrawals_to_date: float = 0.0
    guideline_cap_enabled: bool = False


@dataclass(frozen=True)
class ExceptionGrossUpBasis:
    """Premium-load and COI-saving factors for MD/GP gross-up."""

    tpp: float
    denom: float
    flat: float
    phi: float
    coi_factor: float


def _exception_grossup_basis(inputs: ExceptionPremiumInput) -> ExceptionGrossUpBasis:
    """Resolve premium-load denominator and COI feedback factors."""
    tpp = get_rate(inputs.rates, "tpp", inputs.rate_year)
    denom = 1.0 - tpp
    if abs(denom) < MONEY_EPSILON:
        denom = 1.0
    db_factor = 1.0
    if str(inputs.policy.db_option or "").upper() in (
        DB_OPTION_INCREASING,
        DB_OPTION_RETURN_OF_PREMIUM,
    ):
        discount = round((1.0 + inputs.config.dbd) ** (1.0 / MONTHS_PER_YEAR), 7)
        db_factor = 1.0 - 1.0 / discount if discount else 1.0
    phi = (inputs.coi_rate / PER_THOUSAND) * db_factor
    coi_factor = 1.0 - phi
    if abs(coi_factor) < MONEY_EPSILON:
        coi_factor = 1.0
    return ExceptionGrossUpBasis(
        tpp=tpp, denom=denom, flat=inputs.config.prem_flat_load,
        phi=phi, coi_factor=coi_factor,
    )


def _apply_md_exception_premium(
    result: _ExceptionPremium,
    av: float,
    inputs: ExceptionPremiumInput,
    basis: ExceptionGrossUpBasis,
) -> float:
    """Apply the guideline-capped Monthly Deduction premium phase."""
    if not inputs.md_premium_active or inputs.prior_lapsed:
        return av
    result.md_premium_mode = True
    gross_target = max(0.0, inputs.total_deduction)
    if gross_target <= 0.0:
        return av
    discount = gross_target * basis.phi
    wanted = (gross_target - discount + basis.flat) / basis.denom
    room = _exception_guideline_room(inputs)
    md_prem = min(wanted, room)
    result.md_prem_capped = md_prem < wanted - MONEY_EPSILON
    net = md_prem * basis.denom - basis.flat
    if net <= 0.0:
        return av
    av_bump = net / basis.coi_factor
    result.md_prem = md_prem
    result.md_prem_gross = av_bump
    result.percentage_load += md_prem * basis.tpp
    result.flat_load += basis.flat
    result.md_discount = av_bump - net
    return av + av_bump


def _exception_guideline_room(inputs: ExceptionPremiumInput) -> float:
    """Remaining gross-premium room for the MD premium."""
    if not inputs.guideline_cap_enabled:
        return math.inf
    used_room = inputs.premiums_to_date - inputs.withdrawals_to_date
    return max(0.0, inputs.guideline_limit - used_room)


def _apply_gp_exception_premium(
    result: _ExceptionPremium,
    av: float,
    inputs: ExceptionPremiumInput,
    basis: ExceptionGrossUpBasis,
) -> float:
    """Apply the uncapped GP exception phase on the remaining negative AV."""
    gp_mode = inputs.prior_exception_mode or _exception_triggers(result, av, inputs)
    result.requires_option_a = (
        inputs.options.switch_to_option_a_in_exception
        and gp_mode
        and str(inputs.policy.db_option or "").upper() == DB_OPTION_INCREASING
    )
    result.mode = gp_mode
    result.is_gp_exception = gp_mode
    if not (
        gp_mode and inputs.past_snet and not inputs.policy.has_shadow_account
        and not inputs.prior_lapsed and av < 0.0
    ):
        return av
    gross = -av
    discount = gross * basis.phi
    gp_prem = (gross - discount + basis.flat) / basis.denom
    result.gross = gross
    result.prem = gp_prem
    result.discount = discount
    result.gp_percentage_load = gp_prem * basis.tpp
    result.gp_flat_load = basis.flat
    result.percentage_load += result.gp_percentage_load
    result.flat_load += result.gp_flat_load
    new_av = av + gp_prem * basis.denom - basis.flat + discount
    return 0.0 if abs(new_av) < MONEY_EPSILON else new_av


def _exception_triggers(result: _ExceptionPremium, av: float, inputs: ExceptionPremiumInput) -> bool:
    """Whether this month newly enters GP exception mode."""
    room_exhausted = (
        inputs.guideline_cap_enabled and inputs.policy.is_gpt
        and inputs.guideline_limit - (
            inputs.premiums_to_date - inputs.withdrawals_to_date
        ) <= MONEY_EPSILON
    )
    at_guideline = inputs.guideline_limit_reached or result.md_prem_capped or room_exhausted
    return inputs.options.allow_exception_prems and at_guideline and av < 0.0


def _compute_exception_premium(inputs: ExceptionPremiumInput) -> _ExceptionPremium:
    """Monthly Deduction premium then GP exception premium, in sequence.

    Two phases run on the same residual account value:

    * **Phase 1 — Monthly Deduction premium** (``md_premium_active``): grosses the
      after-charge account value back up toward its pre-deduction value, but the
      gross premium is **capped at the remaining guideline room** so it is
      subject to the guideline limit. When the room runs out the AV is only
      partially restored (or not at all) and the policy starts to run down. This
      is NOT exception mode.
    * **Phase 2 — GP exception premium**: if exceptions are allowed and the
      account value is still negative once the policy is at the guideline limit
      (including the case where the MD premium was just capped out), the
      exception premium covers the residual *past* the guideline (it is NOT
      capped) and brings the account value back to zero. It latches once on
      (``mode``/``is_gp_exception``) and bypasses the force-out from then on.

    The two are independent and can both be non-zero in the single hand-off
    month. The COI feedback (a premium that lifts the AV before the deduction
    lowers the COI) is modelled as a realized bump of ``net / (1 - phi)`` where
    ``phi`` is the COI saving per dollar of AV: the full ``coi_rate/1000`` for a
    level death benefit (Option A), but only ``r·(1 - 1/(1+dbd)^(1/12))`` for an
    increasing death benefit (Option B/C), where the rising DB nearly offsets the
    NAR drop. When an Option B policy would first enter GP exception mode, this
    calculation requests an Option A rerun so the entire exception month uses the
    level-benefit deduction and premium assumptions. Exact for the uncapped MD
    premium and the GP exception, and correct for a partially-funded (capped) MD
    premium.
    """
    result = _ExceptionPremium(av_after_exception=inputs.av_after_charge)
    if inputs.attained_age >= inputs.config.maturity_age:
        return result
    basis = _exception_grossup_basis(inputs)
    av = _apply_md_exception_premium(
        result, inputs.av_after_charge, inputs, basis)
    av = _apply_gp_exception_premium(result, av, inputs, basis)
    result.av_after_exception = av
    return result


def _segment_surrender_rate(
    policy: IllustrationPolicyData,
    segment: CoverageSegment,
    rates: IllustrationRates,
    rate_year: int,
    projection_date,
    config: Optional[PlancodeConfig],
) -> float:
    if segment.is_cola and policy.company_code.strip() == "26":
        plan = config if config is not None else load_plancode(policy.plancode)
        if plan.is_ffl:
            return 0.0
    schedule = rates.segment_scr.get(segment.coverage_phase, rates.scr)
    return _rate_from_schedule(
        schedule, _coverage_year(segment, projection_date, rate_year))


def _calculate_surrender_charge(
    policy: IllustrationPolicyData,
    rates: IllustrationRates,
    rate_year: int,
    projection_date,
    config: PlancodeConfig = None,
):
    # SA_Basis drives the SCR units basis: OriginalSA plans charge the
    # surrender charge on the coverage's ORIGINAL units; every other plan uses
    # the current units. (Units are the specified amount per $1,000.)
    original_basis = bool(config is not None and config.sa_basis == SA_BASIS_ORIGINAL)

    segments = policy.segments or [policy.base_segment]
    segments = [segment for segment in segments if segment is not None]
    if not segments:
        scr_rate = get_rate(rates, "scr", rate_year)
        surrender_charge = scr_rate * policy.units
        return scr_rate, surrender_charge, {}, {}

    scr_rates_by_coverage = {}
    surrender_charges_by_coverage = {}
    for index, segment in enumerate(segments, start=1):
        segment_scr_rate = _segment_surrender_rate(
            policy, segment, rates, rate_year, projection_date, config)
        segment_units = (
            segment.original_face_amount / PER_THOUSAND if original_basis else segment.units
        )
        segment_surrender_charge = segment_scr_rate * segment_units
        key = f"cov{index}"
        scr_rates_by_coverage[key] = segment_scr_rate
        surrender_charges_by_coverage[key] = segment_surrender_charge

    return (
        scr_rates_by_coverage.get("cov1", 0.0),
        sum(surrender_charges_by_coverage.values()),
        scr_rates_by_coverage,
        surrender_charges_by_coverage,
    )
