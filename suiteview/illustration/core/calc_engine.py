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
   accrue loan interest, roll the CVAT deemed cash value (when the NPT can
   bind), calculate shadow account values and evaluate lapse;
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
from datetime import date, timedelta
from enum import Enum
from typing import Dict, List, Literal, Optional

from dateutil.relativedelta import relativedelta

from suiteview.core.joint_survivor_coi import (
    active_table_code,
    anniversary_year,
    load_joint_basis,
    policy_year_on,
    ratings_with_table,
    ymd,
)
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
from suiteview.illustration.core.corridor_rates import corridor_factor
from suiteview.illustration.core.cvat_nsp import CvatCorridor, IswlNspBasis, UlNspBasis
from suiteview.illustration.core.deemed_cash_value import NptTracker, glp_rate_for
from suiteview.illustration.core.input_applier import apply_cash_flow_inputs
from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.illustration.core.interest_calc import credit_interest, interest_days
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
    _coi_rate_year,
    _coverage_year,
    _rate_from_schedule,
    _round_near,
    calculate_deduction,
    in_force_face,
    premiums_and_charges_ceased,
)
from suiteview.illustration.core.premium_allowance import (
    PremiumAllowanceInput,
    PremiumAllowances,
    compute_premium_allowances,
)
from suiteview.illustration.core.premium_handler import apply_premium, premium_load_rates
from suiteview.illustration.core.rate_loader import (
    IllustrationRates,
    _load_benefit_coi_rates,
    benefit_rate_is_level,
    epu_band,
    get_rate,
    load_coverage_coi_rates,
    load_rates,
    load_segment_coi,
    load_segment_scr,
    mfee_schedule,
    premium_load_schedules,
)
from suiteview.illustration.core.shadow_calc import ShadowInput, calculate_shadow
from suiteview.illustration.core.target_premium import (
    build_target_detail_snapshots,
    compute_target_premiums,
    ffl_pwot_units,
    floor_monthly_cent,
    target_actives_signature,
    coi_table_target_signature,
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
    InterimOpening,
    PolicyChangeEvent,
    PolicyChangeKind,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
    JointLives,
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
    # CVAT deemed-cash-value / NSP state (deemed_cash_value.NptTracker); None
    # when the run never reaches a month where the NPT can limit a premium.
    npt: Optional[NptTracker] = None
    # CVAT corridor (cvat_nsp.CvatCorridor): the minimum death benefit ratio
    # 1/NSP by month; None for GPT policies, which use the plan's CORR.
    cvat: Optional[CvatCorridor] = None


def cvat_corridor_rate(cvat: Optional[CvatCorridor], month_date: Optional[date]) -> Optional[float]:
    """The month's CVAT minimum death benefit ratio, or None (GPT ``CORR`` applies)."""
    if cvat is None or month_date is None:
        return None
    return cvat.corridor_rate(month_date)


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
    # NPT (LG..LI) and DCV roll (YW..AAK) columns for this month, CVAT only.
    npt_detail: Dict[str, object] = dataclass_field(default_factory=dict)


@dataclass
class InforceWork:
    """Intermediate values for the month-zero inforce ledger row."""

    rate_year: int = 0
    month_date: Optional[date] = None
    monthly_mtp: float = 0.0
    mtp_detail: Dict[str, object] = dataclass_field(default_factory=dict)
    ctp_detail: Dict[str, object] = dataclass_field(default_factory=dict)
    md_check_av_before_deduction: float = 0.0
    month_days: float = 0.0
    ded: object | None = None
    intr: object | None = None
    wair_held: float = 0.0
    wair_rate: float = 0.0
    wair_swam: float = 0.0
    wair_tav: float = 0.0
    loan: LoanState | None = None
    loan_cap_repay: Dict[str, object] = dataclass_field(default_factory=dict)
    shd: object | None = None
    shadow_premiums_ytd: float | None = None
    shadow_premiums_to_date: float | None = None
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
    guaranteed_cash_value: float = 0.0
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


def bonus_as_of(policy: IllustrationPolicyData) -> date:
    """Date that selects the plan interest-bonus row for a run."""
    return (
        policy.illustration_date
        if policy.run_from_issue and policy.illustration_date
        else policy.valuation_date or policy.issue_date
    )


def resolve_bonus_config(
    policy: IllustrationPolicyData, bonus_override: Optional[BonusConfig]
) -> BonusConfig:
    """Load or override the plan interest-bonus configuration."""
    if bonus_override is not None:
        return bonus_override
    return load_bonus_config(policy.plancode, bonus_as_of(policy)).capped_for(policy)


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
        if policy.issue_date is not None:
            # Anchor on the prior row's date, not ``state.duration``: a loaded
            # duration that disagrees with a clamped month-end monthliversary
            # must not repeat the valuation month (E14).
            prior_date = state.date or policy.valuation_date
            completed = (
                _completed_months(policy.issue_date, prior_date)
                if prior_date is not None else state.duration - 1
            )
            work.month_date = policy.issue_date + relativedelta(months=completed + 1)
        else:
            prior_date = state.date or policy.valuation_date
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
    prior_month_date = ctx.state.date or (
        ctx.policy.issue_date + relativedelta(months=work.duration - 2)
        if ctx.policy.issue_date is not None and work.duration > 1 else None
    )
    exact_days_override = (
        interest_days(prior_month_date, work.month_date)
        if prior_month_date is not None else None
    )
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
        exact_days_override=exact_days_override,
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
        corridor_rate=cvat_corridor_rate(ctx.cvat, work.month_date),
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
    joint_before = _joint_lives_by_phase(policy)
    if not convention.supports_policy_changes:
        _attach_joint_coi_recalc(ctx, work, joint_before)
        _capture_coverage_after_change(ctx, work)
        return

    guideline_changes, recalc_change, before, before_pv = _apply_policy_change_loop(
        ctx, work
    )
    _recalc_policy_change_guidelines(
        ctx, work, guideline_changes, recalc_change, before, before_pv
    )
    _attach_joint_coi_recalc(ctx, work, joint_before)
    if work.tamra_reset:
        policy.tamra_7pay_start_date = work.month_date
    _capture_coverage_after_change(ctx, work)


def _joint_lives_by_phase(policy) -> Dict[int, JointLives]:
    """Copies of each joint phase's lives, before this month's changes."""
    return {
        seg.coverage_phase: replace(seg.joint_lives, ratings=list(seg.joint_lives.ratings))
        for seg in policy.segments if seg.joint_lives is not None
    }


def _attach_joint_coi_recalc(ctx: MonthContext, work: MonthWork, joint_before) -> None:
    """Add the Joint COI sheet data to a joint policy's guideline recalc."""
    if not (work.guideline_recalc and ctx.policy.is_joint_survivor):
        return
    kinds = [_CHANGE_KIND_LABELS.get(change.kind, str(change.kind))
             for change in ctx.policy_changes or []]
    if work.wd.face_decrease > MONEY_EPSILON:
        kinds.insert(0, "Withdrawal Face Decrease")
    work.guideline_recalc["joint_coi"] = joint_coi_recalc_detail(
        ctx.policy, joint_before, work.month_date, kinds)


def joint_coi_recalc_detail(policy, joint_before, change_date, change_kinds) -> Dict[str, object]:
    """Before/after blended joint COI of every joint phase a change re-rated.

    A phase is recalculated when an insured's rate class or extra ratings
    changed, or it is a new face-increase phase. Rows run from the coverage
    year containing the change to the joint horizon: each life's guaranteed
    rated q (the 7702 mortality basis) and the guaranteed and current joint COI.
    """
    from suiteview.illustration.core.ul_rates import ULRates

    rates_db = ULRates(policy.company_code)
    company = rates_db.joint_survivor_company(policy.plancode)
    changes: List[str] = []
    rows: List[Dict[str, object]] = []
    for index, seg in enumerate(policy.segments, start=1):
        after = seg.joint_lives
        before = joint_before.get(seg.coverage_phase)
        if after is None or before == after:
            continue
        label = f"Cov {index}"
        first_year = policy_year_on(seg.issue_date, change_date)
        rated_from = _joint_table_from_year(seg, change_date) + 1
        changes.extend(_joint_life_changes(label, before, after, rated_from))
        after_basis = load_joint_basis(
            rates_db, company, policy.plancode, after.primary, after.joint, after.ratings)
        before_basis = None if before is None else load_joint_basis(
            rates_db, company, policy.plancode, before.primary, before.joint, before.ratings)
        rows.extend(_joint_recalc_rows(
            label, after.primary.issue_age, first_year, before_basis, after_basis))
    kinds = ", ".join(dict.fromkeys(change_kinds)) or "this change"
    reason = "" if rows else (
        f"No joint COI recalculation: {kinds} leaves both insureds' rate classes, extra "
        "ratings and issue ages as they were, so the blended joint COI is unchanged. "
        "Joint survivor plans are unbanded, so a band change does not move it either.")
    return {"recalculated": bool(rows), "changes": changes, "rows": rows, "reason": reason}


def _joint_life_changes(label: str, before, after, rated_from: int) -> List[str]:
    """What changed for each insured; ``rated_from`` is the first coverage year
    a table change applies to."""
    if before is None:
        return [f"{label}: new joint phase (face increase), insureds issued at ages "
                f"{after.primary.issue_age} / {after.joint.issue_age}"]
    out = []
    for person, name in JOINT_PERSONS.items():
        old, new = _joint_life(before, person), _joint_life(after, person)
        if old.rate_class != new.rate_class:
            out.append(f"{label}: {name} rate class {old.rate_class} → {new.rate_class}")
        old_table = active_table_code(before.ratings, person, rated_from)
        new_table = active_table_code(after.ratings, person, rated_from)
        if old_table != new_table:
            out.append(
                f"{label}: {name} table {_table_text(old_table)} → {_table_text(new_table)}"
                f" from coverage year {rated_from}")
    return out


def _table_text(code: str) -> str:
    return {"0": "Standard", "": "percent rating"}.get(code, code)


def _joint_recalc_rows(label: str, primary_issue_age: int, first_year: int,
                       before_basis, after_basis) -> List[Dict[str, object]]:
    rows = []
    for year in range(max(1, first_year), after_basis.horizon + 1):
        after_g = after_basis.schedule.guaranteed_years[year - 1]
        before_g = (before_basis.schedule.guaranteed_years[year - 1]
                    if before_basis is not None and year <= before_basis.horizon else None)

        def prior(series):
            if before_basis is None or year > before_basis.horizon:
                return None
            return series[year - 1]

        rows.append({
            "Coverage": label,
            "Year": year,
            "Primary Age": primary_issue_age + year - 1,
            "Primary q Before": before_g.qx if before_g is not None else None,
            "Primary q After": after_g.qx,
            "Joint q Before": before_g.qy if before_g is not None else None,
            "Joint q After": after_g.qy,
            "Guar COI Before": prior(before_basis.schedule.guaranteed) if before_basis else None,
            "Guar COI After": after_basis.schedule.guaranteed[year - 1],
            "Curr COI Before": prior(before_basis.schedule.current) if before_basis else None,
            "Curr COI After": after_basis.schedule.current[year - 1],
        })
    return rows


def _apply_policy_change_loop(ctx: MonthContext, work: MonthWork) -> tuple:
    policy = ctx.policy
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
    for change in sorted(
        ctx.policy_changes or [],
        key=lambda item: _POLICY_CHANGE_ORDER.get(item.kind, 99),
    ):
        outcome = _apply_policy_change(
            policy, ctx.config, change, work.attained_age, work.month_date,
            ctx.rates, work.rate_year, work.av, options=ctx.options,
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
            recalc_change = recalc_change or change
        if guideline_before is None and outcome.guideline_before is not None:
            guideline_before = outcome.guideline_before
            guideline_before_pv_detail = outcome.guideline_before_pv_detail
    return guideline_changes, recalc_change, guideline_before, guideline_before_pv_detail


def _recalc_policy_change_guidelines(
    ctx: MonthContext, work: MonthWork, guideline_changes: int,
    recalc_change, guideline_before, guideline_before_pv_detail,
) -> None:
    if not ctx.policy_changes:
        return
    if not (guideline_changes and recalc_change is not None):
        return
    if guideline_changes > 1:
        recalc_change = PolicyChangeEvent(
            kind=recalc_change.kind,
            effective_date=work.month_date,
            value=recalc_change.value,
            metadata={"change_label": "Combined Policy Changes"},
        )
    work.guideline_recalc = _recalc_guideline_on_change(
        ctx.policy, ctx.config, recalc_change, work.attained_age,
        change_date=work.month_date, before=guideline_before, av=work.av,
        material_change=work.tamra_reset, options=ctx.options,
        before_pv_detail=guideline_before_pv_detail,
    )


def _capture_coverage_after_change(ctx: MonthContext, work: MonthWork) -> None:
    work.cov_after_change = _coverage_after_change_snapshot(
        ctx.policy,
        ctx.config,
        work.month_date,
        work.policy_change_av_reduction,
        ctx.state.coverage_after_change,
    )


def refresh_targets(ctx: MonthContext, convention: TimingConvention, work: MonthWork) -> None:
    """Refresh target-premium details and carry safety-net timing flags.

    The MTP stops being recalculated once the MAP period has ended (CyberLife
    freezes MT at the MAP end), so a refresh after ``map_cease_date`` keeps the
    prior MTP unless a policy change forces it. A table extra priced from the COI
    makes the CTP follow the COI, so it is recomputed when a coverage year turns.
    """
    state = ctx.state
    policy = ctx.policy
    policy_changed = bool(ctx.policy_changes) or work.wd.face_decrease > MONEY_EPSILON
    coi_year_turned = (
        convention.refresh_targets
        and bool(state.mtp_detail)
        and coi_table_target_signature(policy, work.month_date)
        != coi_table_target_signature(policy, state.date)
    )
    if (
        convention.refresh_targets
        and (
            not state.mtp_detail
            or policy_changed
            or coi_year_turned
            or target_actives_signature(policy, work.month_date)
            != target_actives_signature(policy, state.date)
        )
    ):
        targets = compute_target_premiums(policy, ctx.config, as_of=work.month_date)
        work.mtp_detail, work.ctp_detail = build_target_detail_snapshots(policy, targets)
        map_ended = (
            policy.map_cease_date is not None and work.month_date > policy.map_cease_date
        )
        if state.mtp_detail and map_ended and not policy_changed:
            work.mtp_detail = state.mtp_detail
        if coi_year_turned:
            policy.ctp = targets.ctp_annual
            if not (map_ended and not policy_changed):
                policy.mtp = targets.mtp_annual / MONTHS_PER_YEAR
    else:
        work.mtp_detail = state.mtp_detail
        work.ctp_detail = state.ctp_detail

    work.monthly_mtp = truncate_monthly_mtp(policy.mtp)
    work.pw_monthly_mtp = _round_near(policy.mtp, 2)
    work.accumulated_mtp = state.accumulated_mtp + work.monthly_mtp
    if policy.map_cease_date is not None:
        work.within_snet = work.month_date <= policy.map_cease_date
    else:
        work.within_snet = work.next_year <= ctx.config.safety_net_years(ctx.policy.issue_age)
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
        policy_month=work.next_month,
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
        repay_principal_first=ctx.options.loan_repay_principal_first,
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
    npt_premium = _npt_premium_for_month(ctx, work)
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
        npt_premium=npt_premium,
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
        dollar_for_dollar_in_transition_year=(
            ctx.options.dollar_for_dollar_in_transition_year
        ),
        loan_repay_from_lumpsum=work.cash_flows.loan_repay_from_lumpsum,
        loan_repay_from_scheduled=work.cash_flows.loan_repay_from_scheduled,
        ln_repay_left_over=work.cash_flows.ln_repay_left_over,
        prior_guideline_limit_reached=state.guideline_limit_reached,
        prior_transition_year_active=state.transition_year_active,
    ))


def _npt_premium_for_month(ctx: MonthContext, work: MonthWork) -> Optional[float]:
    """LG..LI — vNPT_Premium from the deemed cash value; None while unknown.

    A 7702 change this month (material change or guideline recalc) starts a new
    NSP schedule anchored here, on the post-change coverage and this month's
    lowest 7-pay death benefit (RERUN NSP schedule 2).
    """
    tracker = ctx.npt
    if tracker is None or not tracker.dcv_known or not ctx.policy.is_cvat:
        return None
    policy = ctx.policy
    if work.tamra_reset or work.guideline_recalc:
        tracker.policy_changed(
            policy, ctx.config,
            duration=work.duration,
            attained_age=work.attained_age,
            months_into_year=work.next_month - 1,
            as_of=work.month_date,
            lowest_death_benefit=_tamra_premium_display(
                ctx.state, policy, work.month_date, work.next_month, ctx.month_inputs,
            )["lowest_7yr_face"],
        )
    tpp, epp = premium_load_rates(ctx.rates, work.rate_year)
    premium, detail = tracker.npt_for_month(
        policy,
        duration=work.duration,
        gross_withdrawal=work.wd.gross_withdrawal,
        av_after_changes=work.av + work.guideline_forceout,
        tpp=tpp,
        epp=epp,
        days=float(getattr(getattr(work, "intr", None), "days_in_month", 0.0) or 0.0),
    )
    work.npt_detail.update(detail)
    return premium


def roll_deemed_cash_value_step(ctx: MonthContext, work: MonthWork) -> None:
    """Close the month's CVAT deemed-cash-value roll (YW..AAK) once interest
    days are known."""
    tracker = ctx.npt
    if tracker is None or not tracker.dcv_known or not ctx.policy.is_cvat:
        return
    work.npt_detail.update(tracker.roll_month(
        ctx.policy, ctx.config, ctx.rates, work.ded,
        month_date=work.month_date,
        rate_year=work.rate_year,
        gross_withdrawal=work.wd.gross_withdrawal,
        net_premium=work.prem.net_premium,
        premiums_less_withdrawals=(
            work.prem.premiums_to_date - ctx.policy.net_withdrawals(work.withdrawals_to_date)),
        days=float(work.intr.days_in_month),
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
        projection_date=work.month_date,
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
        corridor_rate=cvat_corridor_rate(ctx.cvat, work.month_date),
    )
    work.asset_charge = monthly_asset_charge(
        ctx.iul_ctx,
        work.av_before_deduction,
        work.cap_loan.rg_loan_princ,
        work.cap_loan.rg_loan_accrued,
    )
    work.av_after_charge = work.ded.av_after_deduction - work.asset_charge
    if ctx.config.is_iswl and work.av_after_charge < 0.0:
        # The fixed premium carries an ISWL whose account value is exhausted: the COI
        # does not take it below zero (CyberDoc B10 sample: guaranteed AV 0, in force).
        work.av_after_charge = 0.0


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
            ctx.policy, ctx.rates, work.rate_year, work.month_date, ctx.config,
            account_value=work.av_after_charge,
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
            ctx.policy, ctx.rates, work.rate_year, work.month_date, ctx.config,
            account_value=work.av,
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


def apply_dated_receipt_interest(
    ctx: MonthContext, convention: TimingConvention, work: MonthWork
) -> None:
    """Credit receipt-to-monthliversary interest for historical dated inputs."""
    if (
        convention.interest_timing != "pre_withdrawal"
        or ctx.month_inputs is None
        or not getattr(ctx.month_inputs, "dated_cash_flows", None)
        or not (ctx.policy.run_from_issue or ctx.policy.rollback_date is not None)
    ):
        return
    adjustment = _dated_cash_flow_interest_adjustment(ctx, work)
    if abs(adjustment) <= MONEY_EPSILON:
        return
    work.av += adjustment
    work.intr.interest_credited += adjustment
    work.intr.unimpaired_int += adjustment
    work.intr.av_end_of_month += adjustment


def _dated_cash_flow_interest_adjustment(ctx: MonthContext, work: MonthWork) -> float:
    flows = ctx.month_inputs.dated_cash_flows
    premium_bases = _accepted_cash_flow_bases(
        flows, TransactionKind.PREMIUM, work.prem.net_premium)
    withdrawal_bases = _accepted_cash_flow_bases(
        flows, TransactionKind.WITHDRAWAL, work.wd.gross_withdrawal)
    loan_bases = _accepted_cash_flow_bases(
        flows,
        TransactionKind.LOAN,
        work.applied_regular_loan
        + work.applied_preferred_loan
        + work.cash_flows.applied_variable_loan,
    )
    repayment_bases = _accepted_cash_flow_bases(
        flows, TransactionKind.LOAN_REPAYMENT, work.cash_flows.applied_loan_repayment)
    annual = work.intr.effective_annual_rate
    loan_credit = work.intr.reg_loan_credit_rate or annual
    adjustment = 0.0
    for flow, amount in premium_bases:
        adjustment += amount * _cash_flow_stub_rate(annual, flow)
    for flow, amount in withdrawal_bases:
        adjustment -= amount * _cash_flow_stub_rate(annual, flow)
    for flow, amount in loan_bases:
        days = _cash_flow_stub_days(flow)
        adjustment += amount * (
            _period_factor(loan_credit, days) - _period_factor(annual, days)
        )
    for flow, amount in repayment_bases:
        days = _cash_flow_stub_days(flow)
        adjustment += amount * (
            _period_factor(annual, days) - _period_factor(loan_credit, days)
        )
    return adjustment


def _accepted_cash_flow_bases(flows, kind: TransactionKind, accepted: float):
    matching = [flow for flow in flows if flow.kind == kind and flow.amount > 0.0]
    if not matching or accepted <= 0.0:
        return []
    requested = sum(flow.amount for flow in matching)
    if requested <= 0.0:
        return []
    ratio = min(1.0, accepted / requested)
    return [(flow, flow.amount * ratio) for flow in matching]


def _cash_flow_stub_rate(annual_rate: float, flow) -> float:
    return _period_factor(annual_rate, _cash_flow_stub_days(flow))


def _cash_flow_stub_days(flow) -> int:
    return interest_days(flow.effective_date - timedelta(days=1), flow.bucket_date)


def _period_factor(annual_rate: float, days: int) -> float:
    if days <= 0:
        return 0.0
    return (1.0 + annual_rate) ** (days / DAYS_PER_YEAR) - 1.0


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
        work.intr.loan_accrual_days,
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
    gross_premium, post_deduction_premium = _shadow_premium_timing(ctx, work)
    premiums_ytd, premiums_to_date = _shadow_premium_totals(
        ctx, work, gross_premium + post_deduction_premium)
    work.shadow_premiums_ytd, work.shadow_premiums_to_date = (
        (premiums_ytd, premiums_to_date)
        if ctx.config.shadow_late_payment_forgiveness else (None, None))
    work.shd = calculate_shadow(ShadowInput(
        prev_shadow_eav=ctx.state.shadow_eav,
        gross_premium=gross_premium,
        post_deduction_gross_premium=post_deduction_premium,
        premiums_ytd=premiums_ytd,
        premiums_to_date=premiums_to_date,
        policy=ctx.policy,
        config=ctx.config,
        rates=ctx.rates,
        rate_year=work.rate_year,
        policy_month=work.next_month,
        attained_age=work.attained_age,
        days_in_month=work.intr.actual_days_in_month,
        policy_debt=work.accrual_loan.policy_debt,
        gross_premium_interest_days=(
            getattr(ctx.month_inputs, "shadow_premium_days_to_bucket", 0.0)
            if ctx.month_inputs is not None else 0.0
        ),
        # The accepted (net) withdrawal: CyberLife's shadow does not deduct the
        # withdrawal fee / partial surrender charge (U0591866 vs XP: net +2.22,
        # the AV's gross -37.80).
        gross_withdrawal=work.wd.applied_net_withdrawal,
        gross_withdrawal_interest_days=(
            getattr(ctx.month_inputs, "shadow_withdrawal_days_to_bucket", 0.0)
            if ctx.month_inputs is not None else 0.0
        ),
        shadow_rider_charges=_shadow_rider_charges_from_deduction(
            ctx.policy, work.ded
        ),
        projection_date=work.month_date,
        display_days_in_month=work.intr.days_in_month,
    ))


def _shadow_premium_timing(ctx: MonthContext, work: MonthWork) -> tuple[float, float]:
    if not ctx.config.shadow_late_payment_forgiveness or ctx.month_inputs is None:
        return work.prem.gross_premium, 0.0
    bucketed = getattr(ctx.month_inputs, "shadow_bucketed_prior_period_premium", 0.0)
    prior = getattr(ctx.month_inputs, "shadow_prior_period_premium", 0.0)
    return max(0.0, work.prem.gross_premium - bucketed), prior


def _shadow_premium_totals(
    ctx: MonthContext, work: MonthWork, shadow_gross: float,
) -> tuple[float, float]:
    """Shadow premiums YTD / to date after this month's shadow-credited gross.

    With late-payment forgiveness the shadow credits a premium in the month it
    was received, so its own running totals are carried on the state (the AV
    totals follow the bucket month). Without it they equal the AV totals.
    """
    av_ytd_before = work.prem.premiums_ytd - work.prem.gross_premium
    av_td_before = work.prem.premiums_to_date - work.prem.gross_premium
    state = ctx.state
    if not ctx.config.shadow_late_payment_forgiveness or state.shadow_premiums_to_date is None:
        return av_ytd_before + shadow_gross, av_td_before + shadow_gross
    ytd_before = 0.0 if work.next_month == 1 else float(state.shadow_premiums_ytd or 0.0)
    return ytd_before + shadow_gross, state.shadow_premiums_to_date + shadow_gross


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
    lapse_check_av = work.exception.av_after_exception
    lapse_check_debt = work.cap_loan.policy_debt
    # The reported charge pairs with the ending surrender value; a percentage-of-AV
    # (rule-5 ISWL) charge differs on the lapse-check AV, so that test takes its own.
    (
        work.scr_rate,
        work.surrender_charge,
        work.scr_rates_by_coverage,
        work.surrender_charges_by_coverage,
    ) = _calculate_surrender_charge(
        policy, ctx.rates, work.rate_year, work.month_date, ctx.config, account_value=work.av,
    )
    _, lapse_check_charge, _, _ = _calculate_surrender_charge(
        policy, ctx.rates, work.rate_year, work.month_date, ctx.config,
        account_value=lapse_check_av,
    )
    work.guaranteed_cash_value = _iswl_guaranteed_cash_value(ctx.rates, work.month_date)
    work.surrender_value = (
        _iswl_cash_value_floor(ctx.rates, work.month_date, lapse_check_av - lapse_check_charge)
        - lapse_check_debt
    )
    work.ending_db = _ending_death_benefit(ctx, work)
    work.ending_sv = (
        _iswl_cash_value_floor(ctx.rates, work.month_date, work.av - work.surrender_charge)
        - work.accrual_loan.policy_debt
    )
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


def _iswl_guaranteed_cash_value(rates, month_date) -> float:
    """ISWL tabular guaranteed cash value on ``month_date``; 0 for UL-family plans."""
    basis = getattr(rates, "iswl", None)
    return basis.guaranteed_cash_value(month_date) if basis is not None else 0.0


def _iswl_cash_value_floor(rates, month_date, value: float) -> float:
    """An ISWL surrender value is never below the guaranteed cash value; UL unchanged."""
    if getattr(rates, "iswl", None) is None:
        return value
    return max(value, _iswl_guaranteed_cash_value(rates, month_date))


def _ending_death_benefit(ctx: MonthContext, work: MonthWork) -> float:
    policy = ctx.policy
    edb_wo_corr = in_force_face(policy, work.month_date)
    if policy.db_option == DB_OPTION_INCREASING:
        edb_wo_corr += max(0.0, work.av)
    elif policy.db_option == DB_OPTION_RETURN_OF_PREMIUM:
        edb_wo_corr += max(
            0.0, work.prem.premiums_to_date - policy.net_withdrawals(work.withdrawals_to_date)
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
    exhausted = work.av <= 0.0 and _iswl_guaranteed_cash_value(ctx.rates, work.month_date) <= 0.0
    work.lapsed = ctx.state.lapsed or (exhausted and not work.exception.mode)
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
    apply_dated_receipt_interest(ctx, convention, work)
    if convention.interest_timing == "post_deduction":
        credit_interest_post_deduction(ctx, convention, work)
    accrue_loans(ctx, work)
    roll_deemed_cash_value_step(ctx, work)
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
        "premium_policy_fee": work.prem.policy_fee,
        "premium_benefit_charge": work.prem.benefit_premium,
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
    if work.npt_detail:
        fields["premium_allowance_detail"] = {
            **fields["premium_allowance_detail"], **work.npt_detail,
        }
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
        "joint_coi_detail": joint_coi_month_detail(
            ctx.policy, ctx.rates, work.month_date, work.rate_year),
    }


def joint_coi_month_detail(policy, rates, month_date, rate_year: int) -> Dict[str, Dict[str, float]]:
    """Each joint phase's JSURVCOI year behind this month's COI, keyed like
    ``coi_rates_by_coverage`` ("cov1" ...). Empty for single-life policies.

    The values are the run's scale (current, or guaranteed on a guaranteed run):
    both lives' JS_Q, rated q, the survival steps and the capped monthly COI.
    A coverage year past the joint horizon has no entry.
    """
    detail: Dict[str, Dict[str, float]] = {}
    scale = "C" if rates.coi_scale == 1 else "G"
    for index, segment in enumerate(policy.segments, start=1):
        basis = rates.segment_joint.get(segment.coverage_phase)
        if basis is None:
            continue
        year = _coi_rate_year(segment, policy, month_date, rate_year)
        if not 1 <= year <= basis.horizon:
            continue
        joint_year = (basis.schedule.current_years if scale == "C"
                      else basis.schedule.guaranteed_years)[year - 1]
        primary_q, joint_q = basis.js_q[scale]
        detail[f"cov{index}"] = {
            "year": year,
            "js_q_primary": primary_q[year - 1],
            "js_q_joint": joint_q[year - 1],
            "q_primary": joint_year.qx,
            "q_joint": joint_year.qy,
            "tpx": joint_year.tpx,
            "tpy": joint_year.tpy,
            "tpxy": joint_year.tpxy,
            "tqxy": joint_year.tqxy,
            "monthly_p": joint_year.monthly_p,
            "joint_coi": (basis.schedule.current if scale == "C"
                          else basis.schedule.guaranteed)[year - 1],
        }
    return detail


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
        "av_after_deduction": work.av_after_charge,
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
        "guaranteed_cash_value": work.guaranteed_cash_value,
        "snet_active": work.snet_active,
        "shadow_protection": work.shadow_protection,
        "positive_sv": work.positive_sv,
    }


def _shadow_fields(work: MonthWork) -> dict:
    fields = _shadow_fields_from_result(work.shd)
    fields["shadow_premiums_ytd"] = work.shadow_premiums_ytd
    fields["shadow_premiums_to_date"] = work.shadow_premiums_to_date
    return fields


def _shadow_fields_from_result(shd) -> dict:
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
    cvat: Optional[CvatCorridor] = None,
) -> MonthlyState:
    """Build the month-zero inforce state that seeds a projection."""
    work = _initialize_inforce_work(policy, config, rates, bonus, options, iul_ctx, cvat)
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
    cvat: Optional[CvatCorridor] = None,
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
    opening = options.interim_opening
    # The valuation month's deduction was taken on the monthliversary AV, even
    # when the account value now opens on a later interim date.
    valuation_av = (
        opening.valuation_account_value if opening is not None else policy.account_value)
    work.md_check_av_before_deduction = valuation_av + policy.system_monthly_deduction
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
        corridor_rate=cvat_corridor_rate(cvat, work.month_date),
    )
    work.intr = credit_interest(
        policy.account_value, policy, config, rates, bonus,
        work.rate_year, policy.attained_age, work.month_date,
        reg_loan_balance=policy.regular_loan_principal,
        pref_loan_balance=policy.preferred_loan_principal,
        exact_days_interest=options.exact_days_interest,
    )
    # Loans and the shadow account stay on the valuation date and accrue for
    # the whole month even when the account value opens on an interim date.
    work.month_days = work.intr.days_in_month
    interim_days = _inforce_interim_days(policy, opening, work.month_date)
    if interim_days is not None:
        work.intr = credit_interest(
            policy.account_value, policy, config, rates, bonus,
            work.rate_year, policy.attained_age, work.month_date,
            reg_loan_balance=policy.regular_loan_principal,
            pref_loan_balance=policy.preferred_loan_principal,
            exact_days_interest=options.exact_days_interest,
            period_days=interim_days,
        )
    _apply_inforce_wair(policy, iul_ctx, work)
    return work


def _inforce_interim_days(
    policy: IllustrationPolicyData, opening: Optional[InterimOpening], valuation: date,
) -> Optional[int]:
    """Days from an interim opening date to the next monthliversary, if any."""
    if opening is None:
        return None
    start = opening.as_of
    if policy.run_from_issue or policy.issue_date is None:
        raise ValueError("An interim opening value requires an inforce projection.")
    next_monthliversary = policy.issue_date + relativedelta(months=policy.duration)
    if not valuation <= start < next_monthliversary:
        raise ValueError(
            f"Interim opening date {start:%m/%d/%Y} must fall between the valuation "
            f"date {valuation:%m/%d/%Y} and the next monthliversary "
            f"{next_monthliversary:%m/%d/%Y}.")
    return interest_days(start, next_monthliversary)


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
        premiums_to_date=policy.premiums_paid_to_date,
        policy=policy,
        config=config,
        rates=rates,
        rate_year=work.rate_year,
        policy_month=policy.policy_month,
        attained_age=policy.attained_age,
        days_in_month=work.intr.actual_days_in_month,
        policy_debt=work.loan.policy_debt,
        is_inforce=True,
        shadow_rider_charges=_shadow_rider_charges_from_deduction(policy, work.ded),
        projection_date=work.month_date,
        display_days_in_month=work.month_days,
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
        work.month_days,
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
        else policy.policy_year <= config.safety_net_years(policy.issue_age)
    )
    work.snet_active = work.accum_mtp_less_prem >= 0 and within_snet
    work.shadow_protection = (
        policy.has_shadow_account and not within_snet and work.shd.shadow_eav_less_debt > 0
    )
    # The reported charge is on the monthliversary AV (PolView's surrender value);
    # a percentage-of-AV (rule-5 ISWL) charge on the ending AV is computed apart.
    (
        work.scr_rate,
        work.surrender_charge,
        work.scr_rates_by_coverage,
        work.surrender_charges_by_coverage,
    ) = _calculate_surrender_charge(
        policy, rates, work.rate_year, work.month_date, config, account_value=policy.account_value)
    _, ending_charge, _, _ = _calculate_surrender_charge(
        policy, rates, work.rate_year, work.month_date, config,
        account_value=work.intr.av_end_of_month)
    work.guaranteed_cash_value = _iswl_guaranteed_cash_value(rates, work.month_date)
    work.surrender_value = (
        _iswl_cash_value_floor(rates, work.month_date, policy.account_value - work.surrender_charge)
        - work.loan.policy_debt
    )
    work.ending_sv = (
        _iswl_cash_value_floor(rates, work.month_date, work.intr.av_end_of_month - ending_charge)
        - work.loan.policy_debt
    )
    work.positive_sv = (
        config.lapse_value == LAPSE_BASIS_SURRENDER_VALUE and work.surrender_value > 0
    )
    work.av_less_loans = policy.account_value - work.loan.policy_debt


def _inforce_identity_fields(policy, config, work: InforceWork) -> dict:
    return {
        "date": policy.valuation_date,
        "policy_year": policy.policy_year,
        "policy_month": policy.policy_month,
        "duration": policy.duration,
        "attained_age": policy.attained_age,
        "db_option": str(policy.db_option or "").upper(),
        "coverage_after_change": _coverage_after_change_snapshot(
            policy, config, policy.valuation_date or policy.issue_date, 0.0, None,
        ),
        "mtp_detail": work.mtp_detail,
        "ctp_detail": work.ctp_detail,
        "mtp_annual": policy.mtp * MONTHS_PER_YEAR,
        "av_after_premium": work.md_check_av_before_deduction,
    }


def _inforce_guideline_fields(policy, starting_exception_period: bool, work: InforceWork) -> dict:
    tamra_total = sum(policy.tamra_7year_contributions or [])
    return {
        "glp": floor_monthly_cent(policy.glp),
        "gsp": floor_monthly_cent(policy.gsp),
        "accumulated_glp": policy.accumulated_glp,
        "guideline_limit": max(floor_monthly_cent(policy.gsp), policy.accumulated_glp),
        "guideline_forceout": 0.0,
        "gp_exception_mode": starting_exception_period,
        "inforce_exception_period": starting_exception_period,
        "exception_prem_mode": starting_exception_period,
        "guideline_av_before_monthly_deduction": work.md_check_av_before_deduction,
        "accumulated_7pay": tamra_total,
        "amount_in_7pay": tamra_total,
        "tamra_7pay_level": policy.tamra_7pay_level,
        "tamra_7pay_start_date": policy.tamra_7pay_start_date,
        "is_mec": policy.is_mec,
        "tamra_year": _tamra_year(policy, work.month_date),
        "tamra_month_of_year": _tamra_month_of_year(policy, work.month_date),
        "lowest_7yr_face": _tamra_starting_lowest_face(policy),
        "planned_premium_mode": _billing_mode(policy),
    }


def _inforce_deduction_fields(policy, work: InforceWork) -> dict:
    ded = work.ded
    return {
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
        **_inforce_expense_fields(policy, ded, work),
    }


def _inforce_expense_fields(policy, ded, work: InforceWork) -> dict:
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
        "av_after_deduction": policy.account_value,
        "av_after_exception": policy.account_value,
        "system_coi_charge": policy.system_coi_charge,
        "system_expense_charge": policy.system_expense_charge,
        "system_other_charge": policy.system_other_charge,
        "system_monthly_deduction": policy.system_monthly_deduction,
        "md_check_av_before_deduction": work.md_check_av_before_deduction,
        "md_check_calculated_deduction": ded.total_deduction,
        "md_check_deduction_variance": ded.total_deduction - policy.system_monthly_deduction,
        "md_check_calculated_av_after_deduction": ded.av_after_deduction,
        "md_check_av_variance": ded.av_after_deduction - policy.account_value,
    }


def _inforce_loan_interest_fields(policy, iul_ctx, work: InforceWork) -> dict:
    return {
        "rg_loan_princ": policy.regular_loan_principal,
        "rg_loan_accrued": policy.regular_loan_accrued,
        "pf_loan_princ": policy.preferred_loan_principal,
        "pf_loan_accrued": policy.preferred_loan_accrued,
        "vbl_loan_princ": policy.variable_loan_principal,
        "vbl_loan_accrued": policy.variable_loan_accrued,
        "loan_cap_repay": work.loan_cap_repay,
        "asset_charge_rate": iul_ctx.asset_charge_rate if iul_ctx else 0.0,
        "asset_charge": 0.0,
        "wair_tav": work.wair_tav,
        "wair_swam": work.wair_swam,
        "wair_held": work.wair_held,
        "wair_rate": work.wair_rate,
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
        "av_end_of_month": work.intr.av_end_of_month,
        **_inforce_loan_end_fields(work),
    }


def _inforce_loan_end_fields(work: InforceWork) -> dict:
    return {
        "reg_loan_charge": work.loan.reg_loan_charge,
        "pref_loan_charge": work.loan.pref_loan_charge,
        "vbl_loan_charge": work.loan.vbl_loan_charge,
        "end_rg_loan_princ": work.loan.rg_loan_princ,
        "end_rg_loan_accrued": work.loan.rg_loan_accrued,
        "end_pf_loan_princ": work.loan.pf_loan_princ,
        "end_pf_loan_accrued": work.loan.pf_loan_accrued,
        "end_vbl_loan_princ": work.loan.vbl_loan_princ,
        "end_vbl_loan_accrued": work.loan.vbl_loan_accrued,
        "policy_debt": work.loan.policy_debt,
    }


def _inforce_tracking_fields(policy, work: InforceWork) -> dict:
    return {
        "premiums_ytd": policy.premiums_ytd,
        "premiums_to_date": policy.premiums_paid_to_date,
        "withdrawals_to_date": policy.withdrawals_to_date,
        "cost_basis": policy.cost_basis,
        "premiums_ytd_after_exception": policy.premiums_ytd,
        "premiums_to_date_after_exception": policy.premiums_paid_to_date,
        "cost_basis_after_exception": policy.cost_basis,
        "cumulative_interest": work.intr.interest_credited,
        "monthly_mtp": work.monthly_mtp,
        "ctp": policy.ctp,
        "accumulated_mtp": work.accumulated_mtp,
        "accum_mtp_less_prem": work.accum_mtp_less_prem,
        "snet_active": work.snet_active,
        "shadow_protection": work.shadow_protection,
        "positive_sv": work.positive_sv,
        "av_less_loans": work.av_less_loans,
        "scr_rate": work.scr_rate,
        "scr_rates_by_coverage": work.scr_rates_by_coverage,
        "surrender_charge": work.surrender_charge,
        "surrender_charges_by_coverage": work.surrender_charges_by_coverage,
        "surrender_value": work.surrender_value,
        "ending_sv": work.ending_sv,
        "guaranteed_cash_value": work.guaranteed_cash_value,
    }


def _build_inforce_row(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    iul_ctx: Optional[IULCreditingContext],
    starting_exception_period: bool,
    work: InforceWork,
) -> MonthlyState:
    fields = {}
    for part in (
        _inforce_identity_fields(policy, config, work),
        _inforce_guideline_fields(policy, starting_exception_period, work),
        _inforce_deduction_fields(policy, work),
        _inforce_loan_interest_fields(policy, iul_ctx, work),
        _inforce_tracking_fields(policy, work),
        _shadow_fields_from_result(work.shd),
    ):
        fields.update(part)
    return MonthlyState(**fields)

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
        self._guaranteed_rates_cache: Dict[str, IllustrationRates] = {}

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

        cvat = self._start_cvat_corridor(policy, config)
        inforce = build_inforce_state(
            policy, config, rates, bonus, options, iul_ctx, timing,
            starting_exception_period, cvat,
        )
        npt, inforce = self._start_npt_tracker(
            policy, config, rates, options, timing, inforce, total_months)

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
                policy_changes=policy_changes, iul_ctx=iul_ctx, npt=npt, cvat=cvat,
            ), convention)
            state = _apply_mec_status(policy, results, state)
            results.append(state)
            if stop_on_lapse and state.lapsed:
                break

        return results

    def _start_cvat_corridor(
        self, policy: IllustrationPolicyData, config: PlancodeConfig,
    ) -> Optional[CvatCorridor]:
        """The CVAT minimum death benefit ratio tracker; None for GPT policies.

        UL plans use the guaranteed COI (reloaded per coverage state through the
        guaranteed-rates cache); ISWL plans the coverage's valuation mortality table.
        """
        if not policy.is_cvat:
            return None
        if config.is_iswl:
            return CvatCorridor(IswlNspBasis(policy))
        return CvatCorridor(UlNspBasis(
            policy, config, self._guaranteed_rates(policy, config),
            loader=lambda current: self._guaranteed_rates(current, config)))

    def _start_npt_tracker(
        self,
        policy: IllustrationPolicyData,
        config: PlancodeConfig,
        rates: IllustrationRates,
        options: IllustrationOptions,
        timing: ProjectionTiming,
        inforce: MonthlyState,
        total_months: int,
    ) -> tuple[Optional[NptTracker], MonthlyState]:
        """Create the CVAT deemed-cash-value tracker when the NPT can bind.

        The valuation row's DCV roll (RERUN's inforce valuation row) is added
        to the month-zero detail. Runs that never reach TAMRA year 8 under
        Conform to TAMRA skip the DCV entirely — the NPT is unlimited there.
        """
        if not _npt_can_bind(policy, options, inforce, total_months):
            return None, inforce
        tracker = NptTracker(
            load_guaranteed=lambda current: self._guaranteed_rates(current, config),
            glp_rate=glp_rate_for(policy),
            interest_at_start=timing == ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
        )
        detail = tracker.start(
            policy, config, rates, inforce,
            lowest_death_benefit=_tamra_starting_lowest_face(policy),
        )
        if detail:
            inforce = replace(
                inforce,
                premium_allowance_detail={**inforce.premium_allowance_detail, **detail},
            )
        return tracker, inforce

    def _guaranteed_rates(
        self, policy: IllustrationPolicyData, config: PlancodeConfig,
    ) -> IllustrationRates:
        """Guaranteed-COI rates for the policy's current coverage, cached per
        coverage state so repeated solver projections load them once."""
        key = repr((
            policy.plancode, policy.issue_date, policy.band,
            policy.segments, policy.benefits, policy.riders,
        ))
        cached = self._guaranteed_rates_cache.get(key)
        if cached is None:
            cached = load_rates(policy, config, coi_scale=0)
            self._guaranteed_rates_cache[key] = cached
        return cached

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


def _reband_segment(rates, segment, plancode: str, *, band: int, policy) -> None:
    """Reload COI/EPU at the current combined specified-amount band.

    CyberLife/RERUN band the COI by the CURRENT specified amount, so a face change
    that crosses a band breakpoint moves the per-unit rate. SCR is band-independent
    (varies only by rateclass), so it is not reloaded here.

    The caller resolves the policy issue-date boundary once for all segments.
    """
    from suiteview.illustration.core.ul_rates import ULRates

    rates_db = ULRates()
    if band == segment.band:
        return
    segment.band = band
    rates.segment_coi[segment.coverage_phase] = load_segment_coi(
        rates_db, plancode, segment, scale=rates.coi_scale, band=segment.band,
        joint_bases=rates.segment_joint,
    )
    rates.segment_epu[segment.coverage_phase] = rates_db.get_rates(
        "EPU", plancode, segment.issue_age, segment.rate_sex,
        segment.rate_class, scale=rates.expense_scale,
        band=epu_band(rates_db, policy, segment.band),
        issue_date=segment.issue_date,
    ) or []


def _load_segment_rates(rates, segment, plancode: str, config=None, *, policy) -> None:
    """Load COI/EPU/SCR schedules for a NEW segment at its issue age + band.

    The face-increase segment carries its OWN surrender charge schedule from
    its issue age (RERUN TI — vFullSC sums every coverage's charge).

    On a ratchet-banded plancode the segment ALSO needs explicit band-1 and
    band-2 COI schedules (RERUN PP-QX charges every segment's NAR split at
    those rates — PolicyRates keys cov 2/3 by the coverage's own issue age,
    same as cov 1). rate_loader only loads them for segments present at load
    time; without this a face-increase segment silently contributes 0 COI.
    """
    from suiteview.illustration.core.ul_rates import ULRates

    rates_db = ULRates()
    rates.segment_coi[segment.coverage_phase] = load_segment_coi(
        rates_db, plancode, segment, scale=rates.coi_scale, band=segment.band,
        joint_bases=rates.segment_joint,
    )
    rates.segment_epu[segment.coverage_phase] = rates_db.get_rates(
        "EPU", plancode, segment.issue_age, segment.rate_sex,
        segment.rate_class, scale=rates.expense_scale,
        band=epu_band(rates_db, policy, segment.band),
        issue_date=segment.issue_date,
    ) or []
    plan = config if config is not None else load_plancode(plancode)
    rates.segment_scr[segment.coverage_phase] = load_segment_scr(
        rates_db, plancode, segment, plan)
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
                issue_date=segment.issue_date,
            )


def _reband_benefits(rates, policy) -> None:
    """Reload benefit COI rates at the base segment's (possibly re-banded) band."""
    from suiteview.illustration.core.ul_rates import ULRates

    seg = policy.base_segment
    if seg is None:
        return
    rates_db = ULRates(policy.company_code)
    for ben in policy.benefits:
        if not ben.is_active or (ben.benefit_type or "").startswith("#"):
            continue
        ben_key = (ben.benefit_type or "") + (ben.benefit_subtype or "")
        if not ben_key:
            continue
        # A CCV charge pinned to the policy record's rate stays pinned, as does a
        # non-renewing benefit's level stored rate and a zero-premium benefit.
        if (ben_key in rates.benefit_rate_overrides or ben_key in rates.zero_premium_benefits
                or benefit_rate_is_level(ben)):
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
    from suiteview.illustration.core.ul_rates import ULRates

    seg = policy.base_segment
    if seg is None:
        return
    rates_db = ULRates(policy.company_code)
    band = rates_db.get_band(
        policy.plancode, policy.band_specified_amount, issue_date=policy.issue_date)
    band = int(band) if band is not None else seg.band
    policy.band = band
    for segment in policy.segments:
        if segment.face_amount > 0:
            _reband_segment(rates, segment, policy.plancode, band=band, policy=policy)
    _reband_benefits(rates, policy)
    rates.tpp, rates.epp = premium_load_schedules(
        rates_db, policy.plancode, seg, scale=rates.expense_scale, band=band)
    rates.mfee = mfee_schedule(
        rates_db, policy.plancode, seg, scale=rates.expense_scale, band=band)
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
class _PolicyChangeBefore:
    before: object | None = None
    seven_pay_before: Optional[float] = None
    pv_detail: Dict[str, object] = dataclass_field(default_factory=dict)


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
    if charge_scr:
        _reject_pct_surrender_charge(rates, policy.segments, change_date, rate_year, "A face decrease")
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
    from suiteview.illustration.core.ul_rates import ULRates

    snap: Dict[str, object] = {}
    segments = sorted(
        (s for s in policy.segments if getattr(s, "is_base", True)),
        key=lambda s: s.coverage_phase,
    )
    last_active = _add_coverage_slot_snapshots(
        snap, segments, policy.issue_date, month_date
    )
    _add_apb_snapshot(snap)
    snap["LastActiveSegment"] = last_active

    current_sa = float(policy.total_face)
    snap["CurrentSA"] = current_sa
    base = policy.base_segment
    # Band is looked up on the specified amount PLUS any rider that bands as base
    # coverage (see core.band_rules); equals current_sa when there is none.
    band = ULRates(policy.company_code).get_band(
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
    snap["Coverage_Change"] = _coverage_snapshot_changed(snap, prior)
    snap["PolicyChangeAVReduction"] = float(av_reduction)
    return snap


def _months_between_dates(d0, d1) -> int:
    if d0 is None or d1 is None:
        return 0
    rd = relativedelta(d1, d0)
    return rd.years * 12 + rd.months


def _add_coverage_slot_snapshots(snap, segments, issue_date, month_date) -> int:
    last_active = 0
    for index in (1, 2, 3):
        seg = segments[index - 1] if index - 1 < len(segments) else None
        active = _coverage_segment_active(seg)
        if active:
            last_active = index
        snap.update(_coverage_slot_snapshot(index, seg, active, issue_date, month_date))
    return last_active


def _coverage_segment_active(seg) -> bool:
    return bool(
        seg and seg.face_amount > 0 and str(seg.status or "").strip().upper() != "T"
    )


def _coverage_slot_snapshot(index: int, seg, active: bool, issue_date, month_date) -> dict:
    seg_issue = seg.issue_date if seg else None
    cov_months = (_months_between_dates(seg_issue, month_date) + 1) if active else 0
    terminated = int(getattr(seg, "months_since_terminated", 0) or 0) if seg else 0
    cov_months_sb = max(0, cov_months - terminated)
    pol_offset = (
        _months_between_dates(issue_date, seg_issue) % 12
        if (active and seg_issue) else 0
    )
    return {
        f"Cov {index} Active": active,
        f"Cov {index} Issue Date": seg_issue if active else None,
        f"Cov {index} Months from Issue": cov_months,
        f"Cov {index} Months from Issue w setback": cov_months_sb,
        f"Year by Pol Ann Cov {index}": _duration_year(cov_months, pol_offset),
        f"Year by Pol Ann w setback Cov {index}": _setback_year(cov_months_sb, pol_offset, active),
        f"Year by Cov Ann Cov {index}": _duration_year(cov_months, 0),
        f"Year by Cov Ann w setback Cov {index}": _setback_year(cov_months_sb, 0, active),
        f"Original SA Cov {index}": float(seg.original_face_amount) if seg else 0.0,
        f"Current SA Cov {index}": float(seg.face_amount) if seg else 0.0,
        f"Band Lock Cov {index}": int(seg.original_band) if seg else 0,
        f"Issue Age Cov {index}": int(seg.issue_age) if seg else 0,
        f"Rateclass Cov {index}": (seg.rate_class or "") if seg else "",
        f"Table Rating Cov {index}": int(seg.table_rating) if seg else 0,
    }


def _duration_year(months: int, offset: int) -> int:
    return (months - 1 + offset) // 12 + 1 if months > 0 else 0


def _setback_year(months: int, offset: int, active: bool) -> int:
    return max(1, (months - 1 + offset) // 12 + 1) if active else 0


def _add_apb_snapshot(snap) -> None:
    snap["APB Active"] = False
    snap["Original SA APB"] = 0.0
    snap["Current SA APB"] = 0.0
    snap["Band APB"] = 0


def _coverage_snapshot_changed(snap, prior) -> bool:
    if not prior:
        return False
    change_keys = (
        ["CurrentSA"]
        + [f"Rateclass Cov {i}" for i in (1, 2, 3)]
        + [f"Table Rating Cov {i}" for i in (1, 2, 3)]
        + ["Base Flat1", "Base Flat2"]
    )
    return any(snap.get(key) != prior.get(key) for key in change_keys)


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


def _increase_joint_lives(base, increase_age: int, change_date):
    """Both insureds of a joint face-increase segment, or None for single life.

    Each life is issued at its age on the increase date (the joint insured ages
    in step with the primary). Ratings still active then carry over, restated
    in the new segment's policy years — the joint analog of a single-life
    increase inheriting the base table rating and flat extra.
    """
    lives = base.joint_lives
    if lives is None:
        return None
    age_step = increase_age - lives.primary.issue_age
    shift = policy_year_on(base.issue_date, change_date) - 1
    ratings = [
        replace(r, effective_year=max(0, r.effective_year - shift),
                cease_year=r.cease_year - shift)
        for r in lives.ratings if r.cease_year - shift >= 1
    ]
    return JointLives(
        primary=replace(lives.primary, issue_age=increase_age),
        joint=replace(lives.joint, issue_age=lives.joint.issue_age + age_step),
        ratings=ratings,
    )


def _append_face_increase_segment(policy, rates, delta, attained_age, change_date, config=None) -> None:
    """Append the face-increase segment, issued at the insured's true age.

    CyberLife/RERUN band the increase's COI by the new TOTAL specified amount,
    not the increment's own size.

    The increase segment's issue age is the insured's actual age on the increase
    date — computed from the insured DOB under the plancode's age basis (ANB or
    ALB), not the policy's anniversary-based attained age. Falls back to
    ``attained_age`` when the DOB is unavailable.
    """
    from suiteview.illustration.core.ul_rates import ULRates

    base = policy.base_segment
    age_basis = getattr(config, "age_calc", "") if config is not None else ""
    increase_age = _age_on_date(
        getattr(policy, "insured_birth_date", None), change_date, age_basis, attained_age)
    # Band the increase on the new TOTAL specified amount, including any rider
    # that bands as base coverage (see core.band_rules).
    new_band = ULRates(policy.company_code).get_band(
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
        joint_lives=_increase_joint_lives(base, increase_age, change_date),
    )
    policy.segments.append(new_seg)
    _load_segment_rates(rates, new_seg, policy.plancode, config, policy=policy)
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
    # CVAT minimum death benefit ratio; None uses the plan's GPT CORR.
    corridor_rate: Optional[float] = None


def _process_withdrawal(inputs: WithdrawalInput) -> WithdrawalResult:
    """Compute and apply one month's withdrawal (CalcEngine AX..BU)."""
    wd = _compute_month_withdrawal(inputs)
    if wd.face_decrease > MONEY_EPSILON:
        _apply_withdrawal_face_decrease(inputs, wd)
    return wd


def _compute_month_withdrawal(inputs: WithdrawalInput) -> WithdrawalResult:
    state = inputs.state
    policy = inputs.policy
    config = inputs.config
    month_inputs = inputs.month_inputs
    request = month_inputs.withdrawal if month_inputs is not None else 0.0
    gross_request = month_inputs.withdrawal_gross if month_inputs is not None else 0.0
    if request > 0.0 or gross_request > 0.0:
        _reject_pct_surrender_charge(
            inputs.rates, policy.segments, inputs.month_date, inputs.rate_year, "A withdrawal")
    scr_rates = {
        seg.coverage_phase: _segment_surrender_rate(
            policy, seg, inputs.rates, inputs.rate_year, inputs.month_date, config,
        )
        for seg in policy.segments
    }
    pct_of_av_charge = sum(
        (_iswl_surrender_charge_pct(inputs.rates, seg, inputs.month_date, inputs.rate_year) or 0.0)
        * max(inputs.av, 0.0)
        for seg in policy.segments
    )
    debt = _loan_state_debt(inputs.cap_loan)
    return compute_withdrawal(
        inputs.av, policy, config, scr_rates, request,
        gross_request=gross_request,
        pct_of_av_surrender_charge=pct_of_av_charge,
        corridor_rate=(
            inputs.corridor_rate if inputs.corridor_rate is not None
            else corridor_factor(config, inputs.attained_age)),
        prior_total_md=state.total_deduction,
        policy_debt=debt,
        cost_basis=inputs.cost_basis,
        withdrawals_to_date=state.withdrawals_to_date,
        withdrawals_ytd=state.withdrawals_ytd,
        is_anniversary=inputs.is_anniversary,
    )


def _loan_state_debt(loan: LoanState) -> float:
    return (
        loan.rg_loan_princ + loan.rg_loan_accrued
        + loan.pf_loan_princ + loan.pf_loan_accrued
        + loan.vbl_loan_princ + loan.vbl_loan_accrued
    )


def _apply_withdrawal_face_decrease(inputs: WithdrawalInput, wd: WithdrawalResult) -> None:
    before = _solve_guideline_state(
        inputs.policy, inputs.config, inputs.attained_age, inputs.month_date,
        inputs.options)
    seven_pay_before = _withdrawal_seven_pay_before(inputs)
    before_pv_detail = _safe_guideline_pv_recalc_detail(
        inputs.policy, inputs.config, inputs.attained_age, inputs.month_date)
    wd.guideline_before = before
    wd.guideline_before_pv_detail = before_pv_detail
    _reduce_base_face(
        inputs.policy, wd.face_decrease, inputs.rates, inputs.month_date,
        inputs.rate_year, charge_scr=False, config=inputs.config)
    _reload_policy_band_rates(inputs.rates, inputs.policy, inputs.config)
    _apply_recomputed_targets(inputs.policy, inputs.config, inputs.month_date)
    if not inputs.defer_guideline_recalc:
        wd.guideline_recalc = _withdrawal_guideline_recalc(
            inputs, wd, before, before_pv_detail, seven_pay_before)


def _withdrawal_seven_pay_before(inputs: WithdrawalInput) -> Optional[float]:
    if inputs.defer_guideline_recalc:
        return None
    seven_pay_start = inputs.policy.tamra_7pay_start_date or inputs.month_date
    return _solve_guideline_state(
        inputs.policy, inputs.config, _attained_age_at(inputs.policy, seven_pay_start),
        seven_pay_start, inputs.options,
        starting_av=inputs.policy.tamra_7pay_start_av,
        active_as_of=inputs.month_date,
    ).seven_pay


def _withdrawal_guideline_recalc(
    inputs: WithdrawalInput, wd: WithdrawalResult, before,
    before_pv_detail: Dict[str, object], seven_pay_before: Optional[float],
) -> Dict[str, object]:
    return _recalc_guideline_on_change(
        inputs.policy, inputs.config,
        PolicyChangeEvent(
            kind=PolicyChangeKind.FACE_AMOUNT,
            effective_date=inputs.month_date,
            value=inputs.policy.total_face),
        inputs.attained_age,
        change_date=inputs.month_date,
        before=before,
        av=wd.av_post_withdrawal,
        material_change=False,
        options=inputs.options,
        before_pv_detail=before_pv_detail,
        seven_pay_before=seven_pay_before,
    )


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


def _capture_policy_change_before(
    policy, config, change, face_before: float, av: float, attained_age: int,
    change_date, options, defer_guideline_recalc: bool,
    capture_guideline_before: bool,
) -> _PolicyChangeBefore:
    md = change.metadata or {}
    fully_injected = {"new_glp", "new_gsp", "new_7pay"} <= md.keys()
    should_capture = (
        capture_guideline_before
        and not fully_injected
        and (
            _will_alter_coverage(policy, change, face_before, av)
            or _will_alter_guideline_charge_basis(policy, change, change_date)
        )
    )
    if not should_capture:
        return _PolicyChangeBefore()
    before = _solve_guideline_state(policy, config, attained_age, change_date, options)
    seven_pay_before = None
    if not defer_guideline_recalc:
        seven_pay_start = policy.tamra_7pay_start_date or change_date
        seven_pay_before = _solve_guideline_state(
            policy, config, _attained_age_at(policy, seven_pay_start),
            seven_pay_start, options,
            starting_av=policy.tamra_7pay_start_av,
            active_as_of=change_date,
        ).seven_pay
    return _PolicyChangeBefore(
        before=before,
        seven_pay_before=seven_pay_before,
        pv_detail=_safe_guideline_pv_recalc_detail(
            policy, config, attained_age, change_date
        ),
    )


def _apply_db_option_change(
    policy, config, change, rates, rate_year: int, av: float,
    outcome: _PolicyChangeOutcome,
) -> None:
    old = str(policy.db_option or "").upper()
    new = str(change.value or "").upper()
    if not new or new == old:
        return
    av_whole = float(math.floor(max(av, 0.0)))
    detail: Dict[str, object] = {
        "Prev DBO": old,
        "Input DBO": new,
        "DBO Changed": True,
        "Change Type": old + new,
        "DBO Change Allowed": True,
    }
    if old == DB_OPTION_LEVEL and new == DB_OPTION_INCREASING:
        _apply_option_a_to_b(
            policy, config, rates, change.effective_date, rate_year,
            av_whole, detail, outcome,
        )
    elif old == DB_OPTION_INCREASING and new == DB_OPTION_LEVEL:
        _apply_option_b_to_a(policy, av_whole, detail, outcome)
    policy.db_option = new
    detail["DBO"] = new
    detail["Total SA"] = policy.total_face
    outcome.dbo_detail = detail


def _apply_option_a_to_b(
    policy, config, rates, change_date, rate_year: int, av_whole: float,
    detail: Dict[str, object], outcome: _PolicyChangeOutcome,
) -> None:
    cuts = _reduce_base_face(
        policy, av_whole, rates, change_date, rate_year,
        charge_scr=config.partial_surrender_charge, config=config,
    )
    outcome.av_adjustment += cuts.av_adjustment
    outcome.coverage_changed = True
    detail["DBO Face Decrease"] = av_whole
    detail["DBO Face Increase"] = 0.0
    detail["Total PSC DBO"] = -cuts.av_adjustment
    for i, (phase, cut) in enumerate(sorted(cuts.cuts_by_phase.items()), 1):
        detail[f"DBO Decrease Cov {i}"] = cut
        detail[f"DBO PSC Cov {i}"] = cuts.psc_by_phase.get(phase, 0.0)


def _apply_option_b_to_a(policy, av_whole: float, detail, outcome) -> None:
    base = policy.base_segment
    if base is not None and av_whole > 0.0:
        base.face_amount += av_whole
        base.units += av_whole / (base.vpu or PER_THOUSAND)
        policy.face_amount = sum(s.face_amount for s in policy.segments)
        outcome.coverage_changed = True
    outcome.material_change = True
    detail["DBO Face Decrease"] = 0.0
    detail["DBO Face Increase"] = av_whole
    detail["DBO Increase Cov 1"] = av_whole
    detail["Total PSC DBO"] = 0.0


def _apply_face_amount_change(
    policy, config, change, attained_age, change_date, rates, rate_year: int,
    face_before: float, md: dict, outcome: _PolicyChangeOutcome,
) -> None:
    new_total = float(change.value)
    delta = new_total - face_before
    detail = _face_change_detail(new_total, delta)
    if delta < -1e-6:
        cuts = _reduce_base_face(
            policy, -delta, rates, change_date, rate_year,
            charge_scr=_charge_face_decrease_surrender(policy, config, md),
            config=config,
        )
        _record_face_decrease(detail, cuts, -delta, outcome)
    elif delta > 1e-6:
        _append_face_increase_segment(policy, rates, delta, attained_age, change_date, config)
        outcome.coverage_changed = True
        outcome.material_change = True
        detail["Specified Face Increase"] = delta
        detail[f"Spec Increase Cov {len(policy.segments)}"] = delta
    detail["Total SA"] = policy.total_face
    outcome.face_detail = detail


def _face_change_detail(new_total: float, delta: float) -> Dict[str, object]:
    return {
        "Input Face": new_total,
        "Change in Input Face": delta,
        "Specified Face Decrease": 0.0,
        "Specified Face Increase": 0.0,
        "Total PSC Spec Dec": 0.0,
    }


def _charge_face_decrease_surrender(policy, config, md: dict) -> bool:
    return (
        config.partial_surrender_charge
        and policy.decrease_charge_allowed is not False
        and bool(md.get("charge_surrender", True))
    )


def _record_face_decrease(detail, cuts, decrease: float, outcome) -> None:
    outcome.av_adjustment += cuts.av_adjustment
    outcome.coverage_changed = True
    detail["Specified Face Decrease"] = decrease
    detail["Total PSC Spec Dec"] = -cuts.av_adjustment
    for i, (phase, cut) in enumerate(sorted(cuts.cuts_by_phase.items()), 1):
        detail[f"Spec Decrease Cov {i}"] = cut
        detail[f"Spec PSC Cov {i}"] = cuts.psc_by_phase.get(phase, 0.0)


def _apply_rate_class_change(policy, config, change, rates, outcome) -> None:
    if policy.is_joint_survivor:
        _apply_joint_rate_class_change(policy, config, change, rates, outcome)
        return
    new_class = str(change.value or "").strip().upper()
    base = policy.base_segment
    if not (new_class and base is not None):
        return
    if not any(new_class != (seg.rate_class or "").upper() for seg in policy.segments):
        return
    for seg in policy.segments:
        if new_class != (seg.rate_class or "").upper():
            seg.rate_class = new_class
            _load_segment_rates(rates, seg, policy.plancode, config, policy=policy)
    policy.rate_class = new_class
    _reband_benefits(rates, policy)
    outcome.coverage_changed = True


def _apply_substandard_change(policy, config, change, change_date, rates, outcome) -> None:
    if policy.is_joint_survivor:
        _apply_joint_table_change(policy, config, change, change_date, rates, outcome)
        return
    new_table = int(change.value or 0)
    base = policy.base_segment
    if base is None or new_table == base.table_rating:
        return
    base.table_rating = new_table
    base.table_cease_date = change_date if new_table == 0 else None
    for benefit in policy.benefits:
        if benefit.benefit_type in ("3", "4"):
            benefit.rating_factor = 1.0 + config.table_rating_factor * new_table
    outcome.coverage_changed = True


# ── Joint survivor rate class / table changes ─────────────────────────────
# A joint phase's COI is the blended JointCOI of both insureds, so a rate class
# or table change names the insured it applies to (metadata "person": "00"
# primary, "01" joint) and rebuilds the schedule. The table value is the plan's
# JS_TABLE_PCT code ("0" = standard). The blended COI is annual by coverage
# year, so a table change applies from the coverage year starting on or after
# the change date (the model's f_anniversary of the rating's effective date).

JOINT_PERSONS = {"00": "Primary insured", "01": "Joint insured"}


def _joint_change_person(change) -> str:
    person = str((change.metadata or {}).get("person") or "").strip()
    if person not in JOINT_PERSONS:
        raise ValueError(
            f"{_CHANGE_KIND_LABELS.get(change.kind, change.kind)} on a joint survivor policy "
            "must name the insured it applies to (person 00 primary or 01 joint).")
    return person


def _joint_life(lives, person: str):
    return lives.primary if person == "00" else lives.joint


def _with_joint_life(lives, person: str, life):
    return replace(lives, primary=life) if person == "00" else replace(lives, joint=life)


def _joint_table_from_year(segment, change_date) -> int:
    return anniversary_year(ymd(change_date), ymd(segment.issue_date))


def _joint_rate_class_segments(policy, change) -> list:
    """Joint segments whose named insured's class differs from the new class."""
    person = _joint_change_person(change)
    new_class = str(change.value or "").strip().upper()
    if not new_class:
        return []
    return [
        seg for seg in policy.segments
        if seg.joint_lives is not None
        and _joint_life(seg.joint_lives, person).rate_class.upper() != new_class
    ]


def _joint_table_segments(policy, change, change_date) -> list:
    """Joint segments whose named insured's table differs after the change date."""
    person = _joint_change_person(change)
    code = str(change.value if change.value is not None else "0").strip().upper() or "0"
    return [
        seg for seg in policy.segments
        if seg.joint_lives is not None
        and active_table_code(
            seg.joint_lives.ratings, person,
            _joint_table_from_year(seg, change_date) + 1) != code
    ]


def _apply_joint_rate_class_change(policy, config, change, rates, outcome) -> None:
    person = _joint_change_person(change)
    new_class = str(change.value or "").strip().upper()
    for seg in _joint_rate_class_segments(policy, change):
        life = replace(_joint_life(seg.joint_lives, person), rate_class=new_class)
        seg.joint_lives = _with_joint_life(seg.joint_lives, person, life)
        if person == "00":
            seg.rate_class = new_class
        _load_segment_rates(rates, seg, policy.plancode, config, policy=policy)
        outcome.coverage_changed = True
    if outcome.coverage_changed and person == "00":
        policy.rate_class = new_class
        _reband_benefits(rates, policy)


def _apply_joint_table_change(policy, config, change, change_date, rates, outcome) -> None:
    person = _joint_change_person(change)
    code = str(change.value if change.value is not None else "0").strip().upper() or "0"
    for seg in _joint_table_segments(policy, change, change_date):
        seg.joint_lives = replace(seg.joint_lives, ratings=ratings_with_table(
            seg.joint_lives.ratings, person, code, _joint_table_from_year(seg, change_date)))
        _load_segment_rates(rates, seg, policy.plancode, config, policy=policy)
        outcome.coverage_changed = True


def _apply_rider_drop_change(policy, change, outcome) -> None:
    target = str((change.metadata or {}).get("target", ""))
    new_amount = float(change.value or 0.0)
    if target.startswith("cov:"):
        _apply_rider_amount_change(policy.riders, target, new_amount, outcome)
    elif target.startswith("ben:"):
        _apply_benefit_amount_change(policy.benefits, target, new_amount, outcome)


def _apply_rider_amount_change(riders, target: str, new_amount: float, outcome) -> None:
    phase = int(target.split(":", 1)[1])
    for rider in riders:
        if rider.coverage_phase == phase:
            if new_amount <= 0.0:
                rider.is_active = False
            else:
                rider.face_amount = new_amount
                rider.units = new_amount / (rider.vpu or PER_THOUSAND)
            outcome.coverage_changed = True


def _apply_benefit_amount_change(benefits, target: str, new_amount: float, outcome) -> None:
    parts = target.split(":")
    ben_key, phase = parts[1], int(parts[2]) if len(parts) > 2 else 0
    for ben in benefits:
        key = (ben.benefit_type or "") + (ben.benefit_subtype or "")
        if key == ben_key and (phase == 0 or ben.coverage_phase == phase):
            if new_amount <= 0.0:
                ben.is_active = False
            else:
                ben.benefit_amount = new_amount
            outcome.coverage_changed = True


def _apply_recomputed_targets(policy, config, as_of) -> None:
    """Recompute MTP/CTP after a coverage change (RERUN vPolicyChangeIndicator).

    FFL stipulated premium waivers (type 4) are then re-derived from the new
    MTP, as CyberLife does on the change, so later charges, displays and the
    guideline after-basis use the waiver amount admin will carry.
    """
    targets = compute_target_premiums(policy, config, as_of=as_of)
    policy.mtp = targets.mtp_annual / MONTHS_PER_YEAR
    policy.ctp = targets.ctp_annual
    if config.is_ffl:
        _refresh_ffl_pwot_units(policy, as_of)


def _refresh_ffl_pwot_units(policy, as_of) -> None:
    for ben in policy.benefits:
        if (ben.benefit_type or "") != "4" or not ben.is_active:
            continue
        if ben.pay_up_date is not None and as_of is not None and as_of >= ben.pay_up_date:
            continue
        if not ben.vpu or ben.vpu <= 0:
            raise ValueError(
                f"FFL stipulated premium waiver {ben.benefit_type}{ben.benefit_subtype or ''} "
                "has no value per unit, so its units cannot be re-derived from the "
                "recomputed Minimum Target Premium."
            )
        ben.units = ffl_pwot_units(policy.mtp, ben.vpu)
        ben.benefit_amount = ben.units * ben.vpu


def _finish_policy_change(
    policy, config, change, attained_age, change_date, rates, av, options,
    defer_guideline_recalc: bool, before_info: _PolicyChangeBefore,
    outcome: _PolicyChangeOutcome,
) -> None:
    if not outcome.coverage_changed:
        return
    if policy.is_mec:
        outcome.material_change = False
    _reload_policy_band_rates(rates, policy, config)
    _apply_recomputed_targets(policy, config, change_date)
    if defer_guideline_recalc:
        return
    outcome.guideline_recalc = _recalc_guideline_on_change(
        policy, config, change, attained_age,
        change_date=change_date,
        before=before_info.before,
        av=av,
        material_change=outcome.material_change,
        options=options,
        before_pv_detail=before_info.pv_detail,
        seven_pay_before=before_info.seven_pay_before,
    )


def _apply_policy_change(
    policy, config, change, attained_age, change_date, rates, rate_year, av,
    options=None, defer_guideline_recalc=False, capture_guideline_before=True,
) -> _PolicyChangeOutcome:
    """Mutate the private policy state for one effective-month change."""
    outcome = _PolicyChangeOutcome()
    face_before = sum(s.face_amount for s in policy.segments) or policy.face_amount
    md = change.metadata or {}
    before_info = _capture_policy_change_before(
        policy, config, change, face_before, av, attained_age, change_date,
        options, defer_guideline_recalc, capture_guideline_before,
    )
    outcome.guideline_before = before_info.before
    outcome.guideline_before_pv_detail = before_info.pv_detail

    if change.kind == PolicyChangeKind.DB_OPTION:
        _apply_db_option_change(policy, config, change, rates, rate_year, av, outcome)
    elif change.kind == PolicyChangeKind.FACE_AMOUNT:
        _apply_face_amount_change(
            policy, config, change, attained_age, change_date, rates, rate_year,
            face_before, md, outcome,
        )
    elif change.kind == PolicyChangeKind.RATE_CLASS:
        _apply_rate_class_change(policy, config, change, rates, outcome)
    elif change.kind == PolicyChangeKind.SUBSTANDARD:
        _apply_substandard_change(policy, config, change, change_date, rates, outcome)
    elif change.kind == PolicyChangeKind.RIDER_DROP:
        _apply_rider_drop_change(policy, change, outcome)
    else:
        logger.warning("Policy change kind %s is not implemented; ignored", change.kind)

    _finish_policy_change(
        policy, config, change, attained_age, change_date, rates, av, options,
        defer_guideline_recalc, before_info, outcome,
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


def _will_alter_guideline_charge_basis(policy, change, change_date) -> bool:
    if not policy.is_gpt:
        return False
    if change.kind == PolicyChangeKind.RATE_CLASS:
        if policy.is_joint_survivor:
            return bool(_joint_rate_class_segments(policy, change))
        return _rate_class_will_change(policy, change.value)
    if change.kind == PolicyChangeKind.SUBSTANDARD:
        if policy.is_joint_survivor:
            return bool(_joint_table_segments(policy, change, change_date))
        return _substandard_will_change(policy, change.value)
    return (
        change.kind == PolicyChangeKind.RIDER_DROP
        and _rider_or_benefit_will_change(policy, change)
    )


def _rate_class_will_change(policy, value) -> bool:
    base = policy.base_segment
    new_class = str(value or "").strip().upper()
    return (
        base is not None
        and bool(new_class)
        and new_class != (base.rate_class or "").upper()
    )


def _substandard_will_change(policy, value) -> bool:
    base = policy.base_segment
    return base is not None and int(value or 0) != base.table_rating


def _rider_or_benefit_will_change(policy, change) -> bool:
    target = str((change.metadata or {}).get("target", ""))
    new_amount = float(change.value or 0.0)
    if target.startswith("cov:"):
        return _rider_will_change(policy.riders, target, new_amount)
    if target.startswith("ben:"):
        return _benefit_will_change(policy.benefits, target, new_amount)
    return False


def _rider_will_change(riders, target: str, new_amount: float) -> bool:
    phase = int(target.split(":", 1)[1])
    for rider in riders:
        if rider.coverage_phase == phase and rider.is_active:
            return new_amount <= 0.0 or abs(float(rider.face_amount) - new_amount) > 1e-6
    return False


def _benefit_will_change(benefits, target: str, new_amount: float) -> bool:
    parts = target.split(":")
    ben_key = parts[1] if len(parts) > 1 else ""
    phase = int(parts[2]) if len(parts) > 2 else 0
    for ben in benefits:
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
    """Recalculate GLP/GSP/7-pay at a policy change."""
    md = change.metadata or {}
    context = _prepare_guideline_change_context(
        policy, change_date, material_change, av
    )
    after = _solve_guideline_after_change(
        policy, config, attained_age, change_date, options, before,
        md.get("new_glp"), md.get("new_gsp"),
    )
    glp_prior, gsp_prior = _apply_guideline_premium_delta(
        policy, before, after, md.get("new_glp"), md.get("new_gsp")
    )
    adjustment, months_remaining = _accum_glp_adjustment(
        policy, change_date, glp_prior
    )
    recalc_detail = _guideline_recalc_detail(
        policy, config, change, attained_age, change_date, before, after,
        before_pv_detail, glp_prior, gsp_prior,
    )
    seven_pay_after = _apply_seven_pay_recalc(
        policy, config, change_date, options, before, md.get("new_7pay")
    )
    _update_tamra_recalc_detail(
        policy, config, change_date, material_change, recalc_detail, context,
        seven_pay_before, seven_pay_after,
    )
    _add_accum_glp_recalc_detail(recalc_detail, adjustment, months_remaining)
    return recalc_detail


def _prepare_guideline_change_context(policy, change_date, material_change: bool, av: float) -> dict:
    context = {
        "tamra_year_at_change": _tamra_year(policy, change_date),
        "seven_pay_prior": policy.tamra_7pay_level,
        "seven_pay_prior_start": policy.tamra_7pay_start_date,
    }
    if material_change and not policy.is_mec:
        policy.tamra_7pay_start_date = change_date
        policy.tamra_7pay_start_av = max(av, 0.0)
    return context


def _solve_guideline_after_change(
    policy, config, attained_age: int, change_date, options, before, new_glp, new_gsp
):
    if (new_glp is None or new_gsp is None) and before is not None:
        return _solve_guideline_state(policy, config, attained_age, change_date, options)
    return None


def _apply_guideline_premium_delta(policy, before, after, new_glp, new_gsp) -> tuple[float, float]:
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
    return glp_prior, gsp_prior


def _accum_glp_adjustment(policy, change_date, glp_prior: float) -> tuple[float, int]:
    if policy.issue_date is None:
        return 0.0, 0
    month_in_year = (
        (change_date.year - policy.issue_date.year) * 12
        + (change_date.month - policy.issue_date.month)
    ) % 12 + 1
    if month_in_year <= 1 or abs(policy.glp - glp_prior) <= MONEY_EPSILON:
        return 0.0, 0
    months_remaining = 13 - month_in_year
    adjustment = round(
        months_remaining / MONTHS_PER_YEAR * (policy.glp - glp_prior), 2
    )
    return adjustment, months_remaining


def _guideline_recalc_detail(
    policy, config, change, attained_age: int, change_date, before, after,
    before_pv_detail, glp_prior: float, gsp_prior: float,
) -> Dict[str, object]:
    if before is None or after is None:
        return {}
    md = change.metadata or {}
    after_pv_detail = _safe_guideline_pv_recalc_detail(
        policy, config, attained_age, change_date
    )
    return {
        "change_kind": md.get("change_label") or _CHANGE_KIND_LABELS.get(
            change.kind, change.kind.name.replace("_", " ").title()
        ),
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


def _apply_seven_pay_recalc(policy, config, change_date, options, before, new_7pay) -> Optional[float]:
    if new_7pay is not None:
        policy.tamra_7pay_level = floor_monthly_cent(float(new_7pay))
        return float(new_7pay)
    if before is None:
        return None
    start = policy.tamra_7pay_start_date or change_date
    seven_solve = _solve_guideline_state(
        policy, config, _attained_age_at(policy, start), start, options,
        starting_av=policy.tamra_7pay_start_av, active_as_of=change_date,
    )
    policy.tamra_7pay_level = floor_monthly_cent(seven_solve.seven_pay)
    return seven_solve.seven_pay


def _update_tamra_recalc_detail(
    policy, config, change_date, material_change: bool, recalc_detail: dict,
    context: dict, seven_pay_before: Optional[float], seven_pay_after: Optional[float],
) -> None:
    if not recalc_detail:
        return
    if policy.is_mec:
        tamra_case = "no_recalc"
    elif material_change:
        tamra_case = "new_period"
    elif context["tamra_year_at_change"] <= 7:
        tamra_case = "within_period"
    else:
        tamra_case = "no_recalc"
    recalc_detail.update({
        "tamra_case": tamra_case,
        "tamra_year_at_change": context["tamra_year_at_change"],
        "seven_pay_prior": context["seven_pay_prior"],
        "seven_pay_before": seven_pay_before,
        "seven_pay_after": seven_pay_after,
        "seven_pay_new": policy.tamra_7pay_level,
        "seven_pay_prior_start": context["seven_pay_prior_start"],
        "seven_pay_window_start": policy.tamra_7pay_start_date or change_date,
        "seven_pay_start_av": policy.tamra_7pay_start_av,
    })
    if tamra_case != "no_recalc":
        recalc_detail["seven_pay_pv"] = _safe_seven_pay_pv_detail(
            policy, config, change_date
        )


def _add_accum_glp_recalc_detail(recalc_detail: dict, adjustment: float, months: int) -> None:
    if adjustment:
        recalc_detail["accum_glp_adjustment"] = adjustment
        recalc_detail["accum_glp_months_remaining"] = months


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
    if end < start + relativedelta(months=months):
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
    policy_month=None,
) -> tuple[float, float]:
    """Requested scheduled (LS) and unscheduled/lumpsum (vLumpsum) premium.

    With no premium schedule at all the modal premium bills every month (the
    workbook's vPlannedPremium fallback); a schedule supplies the per-month
    scheduled amount and dated deposits the lumpsum. No premium is collected on
    or after the maturity date — the policy endows — or from the plan's charge-cease
    age (paid up). A fixed-premium ISWL bills
    its modal premium only in billing months; a single-premium ISWL bills nothing.
    """
    if exception_period or premiums_and_charges_ceased(policy, config, attained_age):
        return 0.0, 0.0
    total_override = month_inputs.total_premium if month_inputs is not None else None
    if total_override is None:
        if config.is_iswl and policy.is_single_premium:
            return 0.0, 0.0
        if config.is_iswl and policy_month is not None and not _is_billing_month(policy, policy_month):
            return 0.0, 0.0
        return float(policy.modal_premium or 0.0), 0.0
    requested_scheduled = float(month_inputs.scheduled_premium or 0.0)
    requested_lumpsum = float(month_inputs.unscheduled_premium or 0.0)
    return requested_scheduled, requested_lumpsum


def _is_billing_month(policy, policy_month: int) -> bool:
    """Whether a policy month is a premium due month at the billing frequency."""
    interval = max(int(getattr(policy, "billing_frequency", 1) or 1), 1)
    return (int(policy_month) - 1) % interval == 0


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


def _npt_can_bind(
    policy: IllustrationPolicyData,
    options: IllustrationOptions,
    inforce: MonthlyState,
    total_months: int,
) -> bool:
    """Whether a projection can reach a month where the CVAT NPT limits premium.

    The NPT allowance (RERUN ND) only exists for CVAT with the 7-pay limit
    enforced, no inforce MEC, after TAMRA year 7. A later material change can
    only restart the 7-pay window, so the last projected month bounds it.
    """
    if not policy.is_cvat or policy.is_mec or total_months <= 0:
        return False
    if not _tamra_force(options, policy) or policy.issue_date is None:
        return False
    last_month = policy.issue_date + relativedelta(
        months=inforce.duration + total_months - 1)
    return _tamra_year(policy, last_month) > 7


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
    if (inputs.attained_age >= inputs.config.maturity_age
            or inputs.config.charges_ceased(inputs.attained_age)):
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


def surrender_charge_units(segment: CoverageSegment, config: Optional[PlancodeConfig]) -> float:
    """Units the surrender charge rate applies to for ``segment``.

    SA_Basis drives the SCR units basis: OriginalSA plans charge the surrender
    charge on the coverage's ORIGINAL units; every other plan uses the current
    units. (Units are the specified amount per $1,000.)
    """
    if config is not None and config.sa_basis == SA_BASIS_ORIGINAL:
        return segment.original_face_amount / PER_THOUSAND
    return segment.units


def _calculate_surrender_charge(
    policy: IllustrationPolicyData,
    rates: IllustrationRates,
    rate_year: int,
    projection_date,
    config: PlancodeConfig = None,
    *,
    account_value: float,
):
    """Full surrender charge on ``account_value``: ``(cov1 rate, total, rates by
    coverage, charges by coverage)``.

    Most plans charge a per-unit rate x units, independent of the account value. A
    rule-5 ISWL base coverage charges a fraction of the account value instead; its
    reported rate is that fraction.
    """
    segments = policy.segments or [policy.base_segment]
    segments = [segment for segment in segments if segment is not None]
    if not segments:
        scr_rate = get_rate(rates, "scr", rate_year)
        surrender_charge = scr_rate * policy.units
        return scr_rate, surrender_charge, {}, {}

    scr_rates_by_coverage = {}
    surrender_charges_by_coverage = {}
    for index, segment in enumerate(segments, start=1):
        pct_of_av = _iswl_surrender_charge_pct(rates, segment, projection_date, rate_year)
        if pct_of_av is not None:
            segment_scr_rate = pct_of_av
            segment_surrender_charge = pct_of_av * max(account_value, 0.0)
        else:
            segment_scr_rate = _segment_surrender_rate(
                policy, segment, rates, rate_year, projection_date, config)
            segment_surrender_charge = segment_scr_rate * surrender_charge_units(segment, config)
        key = f"cov{index}"
        scr_rates_by_coverage[key] = segment_scr_rate
        surrender_charges_by_coverage[key] = segment_surrender_charge

    return (
        scr_rates_by_coverage.get("cov1", 0.0),
        sum(surrender_charges_by_coverage.values()),
        scr_rates_by_coverage,
        surrender_charges_by_coverage,
    )


def _iswl_surrender_charge_pct(rates, segment, projection_date, rate_year: int) -> Optional[float]:
    """Rule-5 ISWL base coverage: the fraction of the account value charged on a full
    surrender in the coverage year. ``None`` when the charge is per unit."""
    basis = getattr(rates, "iswl", None)
    if basis is None or not basis.surrender_charge_is_pct_of_av or not segment.is_base:
        return None
    return basis.surrender_charge_rate(_coverage_year(segment, projection_date, rate_year))


def _reject_pct_surrender_charge(rates, segments, projection_date, rate_year: int, action: str) -> None:
    """A rule-5 percentage-of-AV surrender charge is modelled for full surrenders only;
    an action that would need a partial charge inside the charge period raises."""
    for segment in segments:
        pct = _iswl_surrender_charge_pct(rates, segment, projection_date, rate_year)
        if pct:
            raise ValueError(
                f"{action} in a rule-5 ISWL surrender charge year ({pct:.0%} of the account "
                "value) is not supported: the partial surrender charge is not modelled.")
