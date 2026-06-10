"""UL Illustration projection engine — orchestrates the monthly pipeline.

Public API:
    engine = IllustrationEngine()
    results = engine.project(policy, months=12)  # → List[MonthlyState]
"""
from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, List, Optional

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.bonus_rates import BonusConfig, load_bonus_config
from suiteview.illustration.core.input_applier import apply_cash_flow_inputs
from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.illustration.core.interest_calc import credit_interest
from suiteview.illustration.core.loan_handler import (
    LoanState,
    accrue_loan_interest,
    apply_new_fixed_loan,
    capitalize_loans,
)
from suiteview.illustration.core.monthly_deduction import (
    _coverage_year,
    _rate_from_schedule,
    _round_near,
    calculate_deduction,
)
from suiteview.illustration.core.premium_handler import apply_premium
from suiteview.illustration.core.rate_loader import (
    IllustrationRates,
    get_rate,
    load_rates,
)
from suiteview.illustration.core.shadow_calc import calculate_shadow
from suiteview.illustration.core.target_premium import (
    compute_target_premiums,
    floor_monthly_cent,
)
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    PolicyChangeKind,
)
from suiteview.illustration.models.policy_data import CoverageSegment
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import IllustrationPolicyData


logger = logging.getLogger(__name__)


class ProjectionTiming(str, Enum):
    ILLUSTRATION = "illustration"
    CYBERLIFE_MONTHLIVERSARY = "cyberlife_monthliversary"


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
        config = load_plancode(policy.plancode)
        rates = rates_override if rates_override is not None else self._load_rates(policy, config)

        # Load bonus config from tRates_IntBonus based on valuation date
        if bonus_override is not None:
            bonus = bonus_override
        else:
            val_date = policy.valuation_date or policy.issue_date
            bonus = load_bonus_config(policy.plancode, val_date)

        if months is None:
            remaining_years = policy.maturity_age - policy.attained_age
            remaining_months = remaining_years * 12 - policy.policy_month + 1
            total_months = max(remaining_months, 0)
        else:
            total_months = months

        # Policy changes (face decrease, DBO change) mutate a PRIVATE copy of the
        # policy at their effective month. Base cases (no changes) keep the original
        # object and fast path — byte-for-byte unchanged.
        changes_by_duration: Dict[int, list] = {}
        if future_inputs is not None and future_inputs.policy_changes:
            policy = copy.deepcopy(policy)
            changes_by_duration = _compile_policy_changes(policy, future_inputs.policy_changes)

        # Inforce snapshot (month 0) — AV from CyberLife is after-deduction.
        # We must credit interest to roll AV to end-of-month before projecting.
        rate_year_inforce = policy.policy_year
        month_date_inforce = (
            policy.valuation_date
            if policy.valuation_date
            else policy.issue_date + relativedelta(months=policy.duration)
        )
        monthly_mtp_0 = math.trunc(policy.mtp * 100) / 100
        md_check_av_before_deduction = policy.account_value + policy.system_monthly_deduction
        ded0 = calculate_deduction(
            md_check_av_before_deduction,
            policy,
            config,
            rates,
            rate_year_inforce,
            policy.attained_age,
            policy.premiums_paid_to_date,
            monthly_mtp=monthly_mtp_0,
            projection_date=month_date_inforce,
            bln_round_charge=True,
        )
        intr0 = credit_interest(
            policy.account_value, policy, config, rates, bonus,
            rate_year_inforce, policy.attained_age, month_date_inforce,
            reg_loan_balance=policy.regular_loan_principal,
            pref_loan_balance=policy.preferred_loan_principal,
            exact_days_interest=options.exact_days_interest,
        )

        # Loan interest accrual for inforce month
        loan0 = LoanState(
            rg_loan_princ=policy.regular_loan_principal,
            rg_loan_accrued=policy.regular_loan_accrued,
            pf_loan_princ=policy.preferred_loan_principal,
            pf_loan_accrued=policy.preferred_loan_accrued,
            vbl_loan_princ=policy.variable_loan_principal,
            vbl_loan_accrued=policy.variable_loan_accrued,
        )
        loan0 = accrue_loan_interest(
            loan0,
            config,
            intr0.days_in_month,
            policy.variable_loan_charge_rate,
        )

        # Shadow account for inforce month
        shd0 = calculate_shadow(
            prev_shadow_eav=0.0,
            gross_premium=0.0,
            premiums_ytd=policy.premiums_ytd,
            policy=policy,
            config=config,
            rates=rates,
            rate_year=rate_year_inforce,
            attained_age=policy.attained_age,
            days_in_month=intr0.days_in_month,
            policy_debt=loan0.policy_debt,
            is_inforce=True,
            shadow_rider_charges=_shadow_rider_charges_from_deduction(policy, ded0),
        )

        # Safety Net / Lapse Protection for inforce month
        accumulated_mtp_0 = policy.accumulated_mtp
        accum_mtp_less_prem_0 = (
            policy.premiums_paid_to_date - policy.withdrawals_to_date
            - loan0.policy_debt
        ) - accumulated_mtp_0

        if policy.map_cease_date is not None:
            within_snet_0 = month_date_inforce <= policy.map_cease_date
        else:
            within_snet_0 = policy.policy_year <= config.snet_period
        snet_active_0 = accum_mtp_less_prem_0 >= 0 and within_snet_0

        past_snet_0 = not within_snet_0
        shadow_protection_0 = (
            policy.has_shadow_account
            and past_snet_0
            and shd0.shadow_eav_less_debt > 0
        )

        scr_rate_0, surrender_charge_0, scr_rates_by_coverage_0, surrender_charges_by_coverage_0 = _calculate_surrender_charge(
            policy, rates, rate_year_inforce, month_date_inforce
        )
        surrender_value_0 = max(
            intr0.av_end_of_month - surrender_charge_0 - loan0.policy_debt, 0.0
        )
        positive_sv_0 = config.lapse_value == "SV" and surrender_value_0 > 0
        av_less_loans_0 = intr0.av_end_of_month - loan0.policy_debt

        inforce = MonthlyState(
            date=policy.valuation_date,
            policy_year=policy.policy_year,
            policy_month=policy.policy_month,
            duration=policy.duration,
            attained_age=policy.attained_age,
            av_after_premium=md_check_av_before_deduction,
            glp=floor_monthly_cent(policy.glp),
            gsp=floor_monthly_cent(policy.gsp),
            accumulated_glp=policy.accumulated_glp,
            guideline_limit=max(floor_monthly_cent(policy.gsp), policy.accumulated_glp),
            guideline_forceout=0.0,
            guideline_av_before_monthly_deduction=md_check_av_before_deduction,
            accumulated_7pay=sum(policy.tamra_7year_contributions or []),
            amount_in_7pay=sum(policy.tamra_7year_contributions or []),
            tamra_7pay_level=policy.tamra_7pay_level,
            # Deduction check
            nar_av=ded0.nar_av,
            standard_db=ded0.standard_db,
            corridor_rate=ded0.corridor_rate,
            gross_db=ded0.gross_db,
            corr_amount=ded0.corr_amount,
            db_by_coverage=ded0.db_by_coverage,
            discounted_db_by_coverage=ded0.discounted_db_by_coverage,
            discounted_db_cov1=ded0.discounted_db_cov1,
            discounted_db_corr=ded0.discounted_db_corr,
            discounted_db=ded0.discounted_db,
            total_db=ded0.total_db,
            total_discounted_db=ded0.total_discounted_db,
            nar_by_coverage=ded0.nar_by_coverage,
            nar_cov1=ded0.nar_cov1,
            nar_corr=ded0.nar_corr,
            nar=ded0.nar,
            total_nar=ded0.total_nar,
            coi_rates_by_coverage=ded0.coi_rates_by_coverage,
            coi_charges_by_coverage=ded0.coi_charges_by_coverage,
            coi_rate=ded0.coi_rate,
            coi_charge_cov1=ded0.coi_charge_cov1,
            coi_charge_corr=ded0.coi_charge_corr,
            coi_charge=ded0.coi_charge,
            total_coi_charge=ded0.total_coi_charge,
            epu_rate=ded0.epu_rate,
            epu_charge=ded0.epu_charge,
            epu_rates_by_coverage=ded0.epu_rates_by_coverage,
            epu_charges_by_coverage=ded0.epu_charges_by_coverage,
            mfee_charge=ded0.mfee_charge,
            av_charge=ded0.av_charge,
            pw_charge=ded0.pw_charge,
            benefit_charges=ded0.benefit_charges,
            benefit_amounts=ded0.benefit_amounts,
            benefit_rates=ded0.benefit_rates,
            benefit_charge_detail=ded0.benefit_charge_detail,
            rider_charges=ded0.rider_charges,
            rider_amounts=ded0.rider_amounts,
            rider_rates=ded0.rider_rates,
            rider_charge_detail=ded0.rider_charge_detail,
            total_deduction=ded0.total_deduction,
            av_after_deduction=policy.account_value,
            system_coi_charge=policy.system_coi_charge,
            system_expense_charge=policy.system_expense_charge,
            system_other_charge=policy.system_other_charge,
            system_monthly_deduction=policy.system_monthly_deduction,
            md_check_av_before_deduction=md_check_av_before_deduction,
            md_check_calculated_deduction=ded0.total_deduction,
            md_check_deduction_variance=ded0.total_deduction - policy.system_monthly_deduction,
            md_check_calculated_av_after_deduction=ded0.av_after_deduction,
            md_check_av_variance=ded0.av_after_deduction - policy.account_value,
            # Set 1: Loan cap/repay (beginning of month — from policy inputs)
            rg_loan_princ=policy.regular_loan_principal,
            rg_loan_accrued=policy.regular_loan_accrued,
            pf_loan_princ=policy.preferred_loan_principal,
            pf_loan_accrued=policy.preferred_loan_accrued,
            vbl_loan_princ=policy.variable_loan_principal,
            vbl_loan_accrued=policy.variable_loan_accrued,
            # Interest
            days_in_month=intr0.days_in_month,
            annual_interest_rate=intr0.annual_interest_rate,
            bonus_interest_rate=intr0.bonus_interest_rate,
            effective_annual_rate=intr0.effective_annual_rate,
            monthly_interest_rate=intr0.monthly_interest_rate,
            reg_impaired_int=intr0.reg_impaired_int,
            pref_impaired_int=intr0.pref_impaired_int,
            interest_credited=intr0.interest_credited,
            av_end_of_month=intr0.av_end_of_month,
            # Set 2: Loan accrual (end of month — after accrual)
            reg_loan_charge=loan0.reg_loan_charge,
            pref_loan_charge=loan0.pref_loan_charge,
            vbl_loan_charge=loan0.vbl_loan_charge,
            end_rg_loan_princ=loan0.rg_loan_princ,
            end_rg_loan_accrued=loan0.rg_loan_accrued,
            end_pf_loan_princ=loan0.pf_loan_princ,
            end_pf_loan_accrued=loan0.pf_loan_accrued,
            end_vbl_loan_princ=loan0.vbl_loan_princ,
            end_vbl_loan_accrued=loan0.vbl_loan_accrued,
            policy_debt=loan0.policy_debt,
            # Tracking
            premiums_ytd=policy.premiums_ytd,
            premiums_to_date=policy.premiums_paid_to_date,
            withdrawals_to_date=policy.withdrawals_to_date,
            cost_basis=policy.cost_basis,
            cumulative_interest=intr0.interest_credited,
            # Shadow
            shadow_bav=shd0.shadow_bav,
            shadow_wd_charges=shd0.shadow_wd_charges,
            shadow_sa=shd0.shadow_sa,
            shadow_target_prem=shd0.shadow_target_prem,
            shadow_prem_under_target=shd0.shadow_prem_under_target,
            shadow_prem_over_target=shd0.shadow_prem_over_target,
            shadow_target_load=shd0.shadow_target_load,
            shadow_excess_load=shd0.shadow_excess_load,
            shadow_prem_load=shd0.shadow_prem_load,
            shadow_net_prem=shd0.shadow_net_prem,
            shadow_nar_av=shd0.shadow_nar_av,
            shadow_db=shd0.shadow_db,
            shadow_coi_rate=shd0.shadow_coi_rate,
            shadow_coi=shd0.shadow_coi,
            shadow_dbd_rate=shd0.shadow_dbd_rate,
            shadow_nar=shd0.shadow_nar,
            shadow_epu_rate=shd0.shadow_epu_rate,
            shadow_epu=shd0.shadow_epu,
            shadow_mfee=shd0.shadow_mfee,
            shadow_rider_charges=shd0.shadow_rider_charges,
            shadow_md=shd0.shadow_md,
            shadow_av=shd0.shadow_av,
            shadow_days=shd0.shadow_days,
            shadow_int_rate=shd0.shadow_int_rate,
            shadow_eff_rate=shd0.shadow_eff_rate,
            shadow_interest=shd0.shadow_interest,
            shadow_eav=shd0.shadow_eav,
            shadow_eav_less_debt=shd0.shadow_eav_less_debt,
            # Safety Net / Lapse Protection
            monthly_mtp=monthly_mtp_0,
            ctp=policy.ctp,
            accumulated_mtp=accumulated_mtp_0,
            accum_mtp_less_prem=accum_mtp_less_prem_0,
            snet_active=snet_active_0,
            shadow_protection=shadow_protection_0,
            positive_sv=positive_sv_0,
            av_less_loans=av_less_loans_0,
            # End-of-month values
            scr_rate=scr_rate_0,
            scr_rates_by_coverage=scr_rates_by_coverage_0,
            surrender_charge=surrender_charge_0,
            surrender_charges_by_coverage=surrender_charges_by_coverage_0,
            surrender_value=surrender_value_0,
        )

        if timing == ProjectionTiming.CYBERLIFE_MONTHLIVERSARY:
            inforce = replace(
                inforce,
                av_after_deduction=policy.account_value,
                av_end_of_month=policy.account_value,
                interest_credited=0.0,
                cumulative_interest=0.0,
            )

        compiled_inputs = compile_month_inputs(policy, future_inputs, total_months)

        results: List[MonthlyState] = [inforce]
        state = inforce
        for _ in range(total_months):
            month_inputs = compiled_inputs.get(state.duration + 1)
            if timing == ProjectionTiming.CYBERLIFE_MONTHLIVERSARY:
                state = self.process_cyberlife_monthliversary(
                    state, policy, config, rates, bonus,
                    month_inputs=month_inputs, options=options,
                )
            else:
                state = self.process_month(
                    state, policy, config, rates, bonus,
                    month_inputs=month_inputs, options=options,
                    policy_changes=changes_by_duration.get(state.duration + 1),
                )
            results.append(state)
            if stop_on_lapse and state.lapsed:
                break

        return results

    def process_month(
        self,
        state: MonthlyState,
        policy: IllustrationPolicyData,
        config: PlancodeConfig,
        rates: IllustrationRates,
        bonus: BonusConfig,
        month_inputs=None,
        options: Optional[IllustrationOptions] = None,
        policy_changes=None,
    ) -> MonthlyState:
        """Process a single month of the calculation pipeline.

        Takes the previous month's state, produces the next. ``policy_changes`` are
        applied to ``policy`` (a private copy made in project()) at their effective
        month, before coverage/deduction reads the segments.
        """
        if options is None:
            options = IllustrationOptions()

        # ── 1. Update date/year/month/attained age ────────────
        next_year, next_month = _advance_month(
            state.policy_year, state.policy_month
        )
        duration = state.duration + 1
        attained_age = policy.issue_age + (duration - 1) // 12
        month_date = policy.issue_date + relativedelta(months=duration - 1)
        is_anniversary = next_month == 1

        # ── 2. Gather beginning values ────────────────────────
        premiums_ytd = 0.0 if is_anniversary else state.premiums_ytd
        premiums_to_date = state.premiums_to_date
        cost_basis = state.cost_basis
        av = state.av_end_of_month
        rate_year = next_year

        # ── 3-7. Policy changes / coverage after change ───────
        # Apply any dated policy change effective this month (mutates the private
        # policy copy) before coverage/deduction reads the segments. A coverage
        # change recomputes vMTP/vCTP and the guideline premiums; a material
        # change (face increase, B→A) also restarts the 7-pay period.
        tamra_reset = False
        if policy_changes:
            for change in policy_changes:
                outcome = _apply_policy_change(
                    policy, config, change, attained_age, month_date,
                    rates, rate_year, av,
                )
                av += outcome.av_adjustment
                tamra_reset = tamra_reset or outcome.material_change

        # ── 8. Minimum Target Premium calculation/accumulation ─
        # Accumulation uses vMonthlyMTP = TRUNC(vMTP/12, 2) (JE/JF); the PW
        # waive basis uses ROUND(vMTP/12, 2) (SL) — they differ by a cent when
        # the recomputed annual MTP is not an even multiple of 12 cents.
        monthly_mtp = math.trunc(policy.mtp * 100) / 100
        pw_monthly_mtp = _round_near(policy.mtp, 2)
        accumulated_mtp = state.accumulated_mtp + monthly_mtp

        # Safety-net window — needed before exception-premium eligibility.
        if policy.map_cease_date is not None:
            within_snet = month_date <= policy.map_cease_date
        else:
            within_snet = next_year <= config.snet_period
        past_snet = not within_snet
        prior_exception_mode = state.exception_prem_mode

        # ── 9. Commission Target Premium (split handled in apply_premium) ─

        # ── 10. 7702 — GLP accumulation, guideline limit, force-out ─
        # GSP/GLP are consumed floored to a monthly-divisible cent (KS/KT:
        # INT(x/12*100)*12/100) — RERUN floors even the loaded inforce values.
        gsp_floored = floor_monthly_cent(policy.gsp)
        accumulated_glp = _accumulate_guideline_premium(
            state, policy, is_anniversary, attained_age
        )
        guideline_limit = max(gsp_floored, accumulated_glp)

        # ── 11. Loan capitalization (within-bucket at anniversary) ─
        cap_loan = capitalize_loans(
            state.end_rg_loan_princ, state.end_rg_loan_accrued,
            state.end_pf_loan_princ, state.end_pf_loan_accrued,
            state.end_vbl_loan_princ, state.end_vbl_loan_accrued,
            is_anniversary,
        )

        # Force-out: limit is the GREATER of GSP and AccumGLP, capped by
        # available AV, gated by TEFRA conformance, disabled once exception
        # mode is on (KX checks the prior month's exception flag).
        guideline_forceout, withdrawals_to_date, av = _apply_guideline_forceout(
            gsp_floored,
            accumulated_glp,
            premiums_to_date,
            state.withdrawals_to_date,
            av,
            enabled=options.force_out_enabled,
            is_cvat=policy.is_cvat,
            prior_exception_mode=prior_exception_mode,
        )

        cash_flows = apply_cash_flow_inputs(
            av,
            cap_loan,
            withdrawals_to_date,
            month_inputs,
        )
        av = cash_flows.av
        cap_loan = cash_flows.loan_state
        withdrawals_to_date = cash_flows.withdrawals_to_date

        # ── 12. Apply premium (capped by guideline / TAMRA) ───
        # A material change restarted the 7-pay period: the prior window's
        # contributions no longer count (LE = 0 in month 1 of a new period).
        accumulated_7pay_base = 0.0 if tamra_reset else state.accumulated_7pay
        tamra_year = _tamra_year(policy, month_date)
        premium_cap = _guideline_premium_cap(
            options, policy, guideline_limit,
            premiums_to_date, withdrawals_to_date,
            accumulated_7pay_base, tamra_year,
        )
        prem = apply_premium(
            av, policy, config, rates, rate_year,
            premiums_ytd, premiums_to_date, cost_basis,
            gross_premium_override=month_inputs.total_premium if month_inputs is not None else None,
            premium_cap=premium_cap,
        )
        av = prem.av_after_premium
        av_before_deduction = av

        # ── 13. Monthly deduction ─────────────────────────────
        ded = calculate_deduction(
            av, policy, config, rates, rate_year,
            attained_age, prem.premiums_to_date,
            monthly_mtp=pw_monthly_mtp,
            projection_date=month_date,
        )
        av_after_charge = ded.av_after_deduction

        # ── 14. GP Exception premium ──────────────────────────
        guideline_limit_reached = _guideline_limit_reached(
            options, policy, guideline_limit, prem.premiums_to_date, withdrawals_to_date
        )
        exception = _compute_exception_premium(
            options, policy, config, rates, rate_year,
            av_after_charge=av_after_charge,
            coi_rate=ded.coi_rate,
            guideline_limit_reached=guideline_limit_reached,
            past_snet=past_snet,
            prior_exception_mode=prior_exception_mode,
            prior_lapsed=state.lapsed,
            attained_age=attained_age,
        )
        av = exception.av_after_exception

        # ── 15. Policy values / new fixed loans (gain → preferred) ─
        fixed_loan_state = apply_new_fixed_loan(
            cap_loan,
            month_inputs.regular_loan if month_inputs is not None else 0.0,
            av,
            prem.premiums_to_date,
            withdrawals_to_date,
        )

        # ── 16. Accumulation: interest crediting ──────────────
        intr = credit_interest(
            av, policy, config, rates, bonus, rate_year,
            attained_age, month_date,
            reg_loan_balance=fixed_loan_state.rg_loan_princ,
            pref_loan_balance=fixed_loan_state.pf_loan_princ,
            exact_days_interest=options.exact_days_interest,
        )
        av = intr.av_end_of_month

        # ── 16b. Accumulation: loan interest charges ──────────
        accrual_loan = accrue_loan_interest(
            fixed_loan_state,
            config,
            intr.days_in_month,
            policy.variable_loan_charge_rate,
        )

        # ── 17. Shadow account processing ─────────────────────
        shd = calculate_shadow(
            prev_shadow_eav=state.shadow_eav,
            gross_premium=prem.gross_premium,
            premiums_ytd=prem.premiums_ytd,
            policy=policy,
            config=config,
            rates=rates,
            rate_year=rate_year,
            attained_age=attained_age,
            days_in_month=intr.days_in_month,
            policy_debt=accrual_loan.policy_debt,
            shadow_rider_charges=_shadow_rider_charges_from_deduction(policy, ded),
        )

        # ── 18. Testing: SNET, shadow, exception, and lapse ───
        accum_mtp_less_prem = (
            prem.premiums_to_date - withdrawals_to_date
            - accrual_loan.policy_debt
        ) - accumulated_mtp
        snet_active = accum_mtp_less_prem >= 0 and within_snet

        shadow_protection = (
            policy.has_shadow_account
            and past_snet
            and shd.shadow_eav_less_debt > 0
        )

        scr_rate, surrender_charge, scr_rates_by_coverage, surrender_charges_by_coverage = _calculate_surrender_charge(
            policy, rates, rate_year, month_date
        )
        surrender_value = max(av - surrender_charge - accrual_loan.policy_debt, 0.0)

        ending_db = ded.gross_db

        positive_sv = config.lapse_value == "SV" and surrender_value > 0
        av_less_loans = av - accrual_loan.policy_debt
        av_loans_test = config.lapse_value == "AV" and av_less_loans > 0
        exception_protection = (
            exception.mode
            and (av - surrender_charge - accrual_loan.policy_debt) > -0.0001
        )
        any_protection = (
            snet_active or shadow_protection or positive_sv
            or av_loans_test or exception_protection
        )
        lapsed = state.lapsed or not any_protection

        # 7-pay contributions accumulate while inside the 7-pay window.
        accumulated_7pay = accumulated_7pay_base + (
            prem.gross_premium if tamra_year <= 7 else 0.0
        )

        # ── 19. Deemed cash value ─────────────────────────────
        # Not yet implemented.

        # Cumulative tracking
        cumulative_interest = state.cumulative_interest + intr.interest_credited
        cumulative_charges = state.cumulative_charges + ded.total_deduction

        return MonthlyState(
            # Counters
            date=month_date,
            policy_year=next_year,
            policy_month=next_month,
            duration=duration,
            attained_age=attained_age,
            is_anniversary=is_anniversary,
            # Set 1: Loan cap/repay (beginning of month)
            rg_loan_princ=cap_loan.rg_loan_princ,
            rg_loan_accrued=cap_loan.rg_loan_accrued,
            pf_loan_princ=cap_loan.pf_loan_princ,
            pf_loan_accrued=cap_loan.pf_loan_accrued,
            vbl_loan_princ=cap_loan.vbl_loan_princ,
            vbl_loan_accrued=cap_loan.vbl_loan_accrued,
            # Premium
            gross_premium=prem.gross_premium,
            prem_under_target=prem.prem_under_target,
            prem_over_target=prem.prem_over_target,
            target_load=prem.target_load,
            excess_load=prem.excess_load,
            flat_load=prem.flat_load,
            total_premium_load=prem.total_premium_load,
            net_premium=prem.net_premium,
            av_after_premium=prem.av_after_premium,
            requested_premium=prem.requested_premium,
            premium_cap=prem.premium_cap,
            premium_capped=prem.premium_capped,
            glp=floor_monthly_cent(policy.glp),
            gsp=gsp_floored,
            accumulated_glp=accumulated_glp,
            guideline_limit=guideline_limit,
            guideline_forceout=guideline_forceout,
            guideline_av_before_monthly_deduction=av_before_deduction,
            accumulated_7pay=accumulated_7pay,
            amount_in_7pay=accumulated_7pay_base,
            tamra_year=tamra_year,
            tamra_7pay_level=policy.tamra_7pay_level,
            guideline_limit_reached=guideline_limit_reached,
            exception_prem_mode=exception.mode,
            gp_exception_prem_gross=exception.gross,
            gp_exception_prem=exception.prem,
            exception_protection=exception_protection,
            # Deduction
            nar_av=ded.nar_av,
            standard_db=ded.standard_db,
            corridor_rate=ded.corridor_rate,
            gross_db=ded.gross_db,
            corr_amount=ded.corr_amount,
            db_by_coverage=ded.db_by_coverage,
            discounted_db_by_coverage=ded.discounted_db_by_coverage,
            discounted_db_cov1=ded.discounted_db_cov1,
            discounted_db_corr=ded.discounted_db_corr,
            discounted_db=ded.discounted_db,
            total_db=ded.total_db,
            total_discounted_db=ded.total_discounted_db,
            nar_by_coverage=ded.nar_by_coverage,
            nar_cov1=ded.nar_cov1,
            nar_corr=ded.nar_corr,
            nar=ded.nar,
            total_nar=ded.total_nar,
            coi_rates_by_coverage=ded.coi_rates_by_coverage,
            coi_charges_by_coverage=ded.coi_charges_by_coverage,
            coi_rate=ded.coi_rate,
            coi_charge_cov1=ded.coi_charge_cov1,
            coi_charge_corr=ded.coi_charge_corr,
            coi_charge=ded.coi_charge,
            total_coi_charge=ded.total_coi_charge,
            epu_rate=ded.epu_rate,
            epu_charge=ded.epu_charge,
            epu_rates_by_coverage=ded.epu_rates_by_coverage,
            epu_charges_by_coverage=ded.epu_charges_by_coverage,
            mfee_charge=ded.mfee_charge,
            av_charge=ded.av_charge,
            pw_charge=ded.pw_charge,
            benefit_charges=ded.benefit_charges,
            benefit_amounts=ded.benefit_amounts,
            benefit_rates=ded.benefit_rates,
            benefit_charge_detail=ded.benefit_charge_detail,
            rider_charges=ded.rider_charges,
            rider_amounts=ded.rider_amounts,
            rider_rates=ded.rider_rates,
            rider_charge_detail=ded.rider_charge_detail,
            total_deduction=ded.total_deduction,
            av_after_deduction=ded.av_after_deduction,
            # Interest
            days_in_month=intr.days_in_month,
            annual_interest_rate=intr.annual_interest_rate,
            bonus_interest_rate=intr.bonus_interest_rate,
            effective_annual_rate=intr.effective_annual_rate,
            monthly_interest_rate=intr.monthly_interest_rate,
            reg_impaired_int=intr.reg_impaired_int,
            pref_impaired_int=intr.pref_impaired_int,
            interest_credited=intr.interest_credited,
            av_end_of_month=av,
            # Set 2: Loan accrual (end of month)
            reg_loan_charge=accrual_loan.reg_loan_charge,
            pref_loan_charge=accrual_loan.pref_loan_charge,
            vbl_loan_charge=accrual_loan.vbl_loan_charge,
            end_rg_loan_princ=accrual_loan.rg_loan_princ,
            end_rg_loan_accrued=accrual_loan.rg_loan_accrued,
            end_pf_loan_princ=accrual_loan.pf_loan_princ,
            end_pf_loan_accrued=accrual_loan.pf_loan_accrued,
            end_vbl_loan_princ=accrual_loan.vbl_loan_princ,
            end_vbl_loan_accrued=accrual_loan.vbl_loan_accrued,
            policy_debt=accrual_loan.policy_debt,
            # End-of-month
            scr_rate=scr_rate,
            scr_rates_by_coverage=scr_rates_by_coverage,
            surrender_charge=surrender_charge,
            surrender_charges_by_coverage=surrender_charges_by_coverage,
            surrender_value=surrender_value,
            ending_db=ending_db,
            # Tracking
            premiums_ytd=prem.premiums_ytd,
            premiums_to_date=prem.premiums_to_date,
            withdrawals_to_date=withdrawals_to_date,
            cost_basis=prem.cost_basis,
            cumulative_interest=cumulative_interest,
            cumulative_charges=cumulative_charges,
            # Shadow
            shadow_bav=shd.shadow_bav,
            shadow_wd_charges=shd.shadow_wd_charges,
            shadow_sa=shd.shadow_sa,
            shadow_target_prem=shd.shadow_target_prem,
            shadow_prem_under_target=shd.shadow_prem_under_target,
            shadow_prem_over_target=shd.shadow_prem_over_target,
            shadow_target_load=shd.shadow_target_load,
            shadow_excess_load=shd.shadow_excess_load,
            shadow_prem_load=shd.shadow_prem_load,
            shadow_net_prem=shd.shadow_net_prem,
            shadow_nar_av=shd.shadow_nar_av,
            shadow_db=shd.shadow_db,
            shadow_coi_rate=shd.shadow_coi_rate,
            shadow_coi=shd.shadow_coi,
            shadow_dbd_rate=shd.shadow_dbd_rate,
            shadow_nar=shd.shadow_nar,
            shadow_epu_rate=shd.shadow_epu_rate,
            shadow_epu=shd.shadow_epu,
            shadow_mfee=shd.shadow_mfee,
            shadow_rider_charges=shd.shadow_rider_charges,
            shadow_md=shd.shadow_md,
            shadow_av=shd.shadow_av,
            shadow_days=shd.shadow_days,
            shadow_int_rate=shd.shadow_int_rate,
            shadow_eff_rate=shd.shadow_eff_rate,
            shadow_interest=shd.shadow_interest,
            shadow_eav=shd.shadow_eav,
            shadow_eav_less_debt=shd.shadow_eav_less_debt,
            # Safety Net / Lapse Protection
            monthly_mtp=monthly_mtp,
            ctp=policy.ctp,
            accumulated_mtp=accumulated_mtp,
            accum_mtp_less_prem=accum_mtp_less_prem,
            snet_active=snet_active,
            shadow_protection=shadow_protection,
            positive_sv=positive_sv,
            av_less_loans=av_less_loans,
            # Status
            lapsed=lapsed,
        )

    def process_cyberlife_monthliversary(
        self,
        state: MonthlyState,
        policy: IllustrationPolicyData,
        config: PlancodeConfig,
        rates: IllustrationRates,
        bonus: BonusConfig,
        month_inputs=None,
        options: Optional[IllustrationOptions] = None,
    ) -> MonthlyState:
        if options is None:
            options = IllustrationOptions()
        prior_date = state.date or policy.valuation_date or policy.issue_date
        month_date = prior_date + relativedelta(months=1)
        next_year, next_month, duration = _policy_counters_for_date(policy, month_date)
        attained_age = policy.issue_age + (duration - 1) // 12
        is_anniversary = next_month == 1
        rate_year = next_year

        premiums_ytd = 0.0 if is_anniversary else state.premiums_ytd
        premiums_to_date = state.premiums_to_date
        cost_basis = state.cost_basis

        if policy.map_cease_date is not None:
            within_snet = month_date <= policy.map_cease_date
        else:
            within_snet = next_year <= config.snet_period
        past_snet = not within_snet
        prior_exception_mode = state.exception_prem_mode

        cap_loan = capitalize_loans(
            state.end_rg_loan_princ, state.end_rg_loan_accrued,
            state.end_pf_loan_princ, state.end_pf_loan_accrued,
            state.end_vbl_loan_princ, state.end_vbl_loan_accrued,
            is_anniversary,
        )

        intr = credit_interest(
            state.av_end_of_month,
            policy,
            config,
            rates,
            bonus,
            rate_year,
            attained_age,
            month_date,
            reg_loan_balance=cap_loan.rg_loan_princ,
            pref_loan_balance=cap_loan.pf_loan_princ,
            exact_days_interest=options.exact_days_interest,
        )

        gsp_floored = floor_monthly_cent(policy.gsp)
        accumulated_glp = _accumulate_guideline_premium(
            state, policy, is_anniversary, attained_age
        )
        guideline_limit = max(gsp_floored, accumulated_glp)
        guideline_forceout, withdrawals_to_date, av_after_guideline = _apply_guideline_forceout(
            gsp_floored,
            accumulated_glp,
            premiums_to_date,
            state.withdrawals_to_date,
            intr.av_end_of_month,
            enabled=options.force_out_enabled,
            is_cvat=policy.is_cvat,
            prior_exception_mode=prior_exception_mode,
        )

        cash_flows = apply_cash_flow_inputs(
            av_after_guideline,
            cap_loan,
            withdrawals_to_date,
            month_inputs,
        )
        cap_loan = cash_flows.loan_state
        withdrawals_to_date = cash_flows.withdrawals_to_date

        tamra_year = _tamra_year(policy, month_date)
        premium_cap = _guideline_premium_cap(
            options, policy, guideline_limit,
            premiums_to_date, withdrawals_to_date,
            state.accumulated_7pay, tamra_year,
        )
        prem = apply_premium(
            cash_flows.av,
            policy,
            config,
            rates,
            rate_year,
            premiums_ytd,
            premiums_to_date,
            cost_basis,
            gross_premium_override=month_inputs.total_premium if month_inputs is not None else None,
            premium_cap=premium_cap,
        )
        av_before_deduction = prem.av_after_premium

        ded = calculate_deduction(
            av_before_deduction,
            policy,
            config,
            rates,
            rate_year,
            attained_age,
            prem.premiums_to_date,
            monthly_mtp=math.trunc(policy.mtp * 100) / 100,
            projection_date=month_date,
        )

        guideline_limit_reached = _guideline_limit_reached(
            options, policy, guideline_limit, prem.premiums_to_date, withdrawals_to_date
        )
        exception = _compute_exception_premium(
            options, policy, config, rates, rate_year,
            av_after_charge=ded.av_after_deduction,
            coi_rate=ded.coi_rate,
            guideline_limit_reached=guideline_limit_reached,
            past_snet=past_snet,
            prior_exception_mode=prior_exception_mode,
            prior_lapsed=state.lapsed,
            attained_age=attained_age,
        )
        av_end = exception.av_after_exception

        fixed_loan_state = apply_new_fixed_loan(
            cap_loan,
            month_inputs.regular_loan if month_inputs is not None else 0.0,
            av_end,
            prem.premiums_to_date,
            withdrawals_to_date,
        )
        accrual_loan = accrue_loan_interest(
            fixed_loan_state,
            config,
            intr.days_in_month,
            policy.variable_loan_charge_rate,
        )
        monthly_mtp = math.trunc(policy.mtp * 100) / 100
        accumulated_mtp = state.accumulated_mtp + monthly_mtp
        accum_mtp_less_prem = (
            prem.premiums_to_date - withdrawals_to_date
            - accrual_loan.policy_debt
        ) - accumulated_mtp
        av_less_loans = av_end - accrual_loan.policy_debt
        accumulated_7pay = state.accumulated_7pay + (
            prem.gross_premium if tamra_year <= 7 else 0.0
        )
        exception_protection = exception.mode and av_less_loans > -0.0001
        lapsed = state.lapsed or (av_end <= 0.0 and not exception.mode)

        return MonthlyState(
            date=month_date,
            policy_year=next_year,
            policy_month=next_month,
            duration=duration,
            attained_age=attained_age,
            is_anniversary=is_anniversary,
            rg_loan_princ=cap_loan.rg_loan_princ,
            rg_loan_accrued=cap_loan.rg_loan_accrued,
            pf_loan_princ=cap_loan.pf_loan_princ,
            pf_loan_accrued=cap_loan.pf_loan_accrued,
            vbl_loan_princ=cap_loan.vbl_loan_princ,
            vbl_loan_accrued=cap_loan.vbl_loan_accrued,
            gross_premium=prem.gross_premium,
            prem_under_target=prem.prem_under_target,
            prem_over_target=prem.prem_over_target,
            target_load=prem.target_load,
            excess_load=prem.excess_load,
            flat_load=prem.flat_load,
            total_premium_load=prem.total_premium_load,
            net_premium=prem.net_premium,
            av_after_premium=prem.av_after_premium,
            requested_premium=prem.requested_premium,
            premium_cap=prem.premium_cap,
            premium_capped=prem.premium_capped,
            glp=floor_monthly_cent(policy.glp),
            gsp=gsp_floored,
            accumulated_glp=accumulated_glp,
            guideline_limit=guideline_limit,
            guideline_forceout=guideline_forceout,
            guideline_av_before_monthly_deduction=av_before_deduction,
            accumulated_7pay=accumulated_7pay,
            tamra_year=tamra_year,
            tamra_7pay_level=policy.tamra_7pay_level,
            guideline_limit_reached=guideline_limit_reached,
            exception_prem_mode=exception.mode,
            gp_exception_prem_gross=exception.gross,
            gp_exception_prem=exception.prem,
            exception_protection=exception_protection,
            nar_av=ded.nar_av,
            standard_db=ded.standard_db,
            corridor_rate=ded.corridor_rate,
            gross_db=ded.gross_db,
            corr_amount=ded.corr_amount,
            db_by_coverage=ded.db_by_coverage,
            discounted_db_by_coverage=ded.discounted_db_by_coverage,
            discounted_db_cov1=ded.discounted_db_cov1,
            discounted_db_corr=ded.discounted_db_corr,
            discounted_db=ded.discounted_db,
            total_db=ded.total_db,
            total_discounted_db=ded.total_discounted_db,
            nar_by_coverage=ded.nar_by_coverage,
            nar_cov1=ded.nar_cov1,
            nar_corr=ded.nar_corr,
            nar=ded.nar,
            total_nar=ded.total_nar,
            coi_rates_by_coverage=ded.coi_rates_by_coverage,
            coi_charges_by_coverage=ded.coi_charges_by_coverage,
            coi_rate=ded.coi_rate,
            coi_charge_cov1=ded.coi_charge_cov1,
            coi_charge_corr=ded.coi_charge_corr,
            coi_charge=ded.coi_charge,
            total_coi_charge=ded.total_coi_charge,
            epu_rate=ded.epu_rate,
            epu_charge=ded.epu_charge,
            epu_rates_by_coverage=ded.epu_rates_by_coverage,
            epu_charges_by_coverage=ded.epu_charges_by_coverage,
            mfee_charge=ded.mfee_charge,
            av_charge=ded.av_charge,
            pw_charge=ded.pw_charge,
            benefit_charges=ded.benefit_charges,
            benefit_amounts=ded.benefit_amounts,
            benefit_rates=ded.benefit_rates,
            benefit_charge_detail=ded.benefit_charge_detail,
            rider_charges=ded.rider_charges,
            rider_amounts=ded.rider_amounts,
            rider_rates=ded.rider_rates,
            rider_charge_detail=ded.rider_charge_detail,
            total_deduction=ded.total_deduction,
            av_after_deduction=ded.av_after_deduction,
            days_in_month=intr.days_in_month,
            annual_interest_rate=intr.annual_interest_rate,
            bonus_interest_rate=intr.bonus_interest_rate,
            effective_annual_rate=intr.effective_annual_rate,
            monthly_interest_rate=intr.monthly_interest_rate,
            reg_impaired_int=intr.reg_impaired_int,
            pref_impaired_int=intr.pref_impaired_int,
            interest_credited=intr.interest_credited,
            av_end_of_month=av_end,
            reg_loan_charge=accrual_loan.reg_loan_charge,
            pref_loan_charge=accrual_loan.pref_loan_charge,
            vbl_loan_charge=accrual_loan.vbl_loan_charge,
            end_rg_loan_princ=accrual_loan.rg_loan_princ,
            end_rg_loan_accrued=accrual_loan.rg_loan_accrued,
            end_pf_loan_princ=accrual_loan.pf_loan_princ,
            end_pf_loan_accrued=accrual_loan.pf_loan_accrued,
            end_vbl_loan_princ=accrual_loan.vbl_loan_princ,
            end_vbl_loan_accrued=accrual_loan.vbl_loan_accrued,
            policy_debt=accrual_loan.policy_debt,
            premiums_ytd=prem.premiums_ytd,
            premiums_to_date=prem.premiums_to_date,
            withdrawals_to_date=withdrawals_to_date,
            cost_basis=prem.cost_basis,
            cumulative_interest=state.cumulative_interest + intr.interest_credited,
            cumulative_charges=state.cumulative_charges + ded.total_deduction,
            monthly_mtp=monthly_mtp,
            ctp=policy.ctp,
            accumulated_mtp=accumulated_mtp,
            accum_mtp_less_prem=accum_mtp_less_prem,
            av_less_loans=av_less_loans,
            lapsed=lapsed,
        )

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


def _change_duration(policy: IllustrationPolicyData, effective_date) -> int:
    """Projection duration (1-indexed month) at which a dated change takes effect."""
    issue = policy.issue_date
    if issue is None or effective_date is None:
        return 0
    months = (effective_date.year - issue.year) * 12 + (effective_date.month - issue.month)
    if effective_date.day < issue.day:
        months -= 1
    return max(1, months + 1)


def _compile_policy_changes(policy: IllustrationPolicyData, changes) -> Dict[int, list]:
    """Bucket dated policy changes by the projection duration they take effect."""
    by_duration: Dict[int, list] = {}
    for change in changes:
        by_duration.setdefault(_change_duration(policy, change.effective_date), []).append(change)
    return by_duration


def _reband_segment(rates, segment, plancode: str) -> None:
    """Re-band a segment to its current face's band and reload its COI/EPU rates.

    CyberLife/RERUN band the COI by the CURRENT specified amount, so a face change
    that crosses a band breakpoint moves the per-unit rate. SCR is band-independent
    (varies only by rateclass), so it is not reloaded here.
    """
    from suiteview.core.rates import Rates

    rates_db = Rates()
    new_band = rates_db.get_band(plancode, segment.face_amount)
    if new_band is None or int(new_band) == segment.band:
        return
    segment.band = int(new_band)
    for attr, kind in (("segment_coi", "COI"), ("segment_epu", "EPU")):
        schedule = rates_db.get_rates(
            kind, plancode, segment.issue_age, segment.rate_sex,
            segment.rate_class, scale=1, band=segment.band,
        ) or []
        getattr(rates, attr)[segment.coverage_phase] = schedule


def _load_segment_rates(rates, segment, plancode: str) -> None:
    """Load COI/EPU/SCR schedules for a NEW segment at its issue age + band.

    The face-increase segment carries its OWN surrender charge schedule from
    its issue age (RERUN TI — vFullSC sums every coverage's charge).
    """
    from suiteview.core.rates import Rates

    rates_db = Rates()
    for attr, kind in (("segment_coi", "COI"), ("segment_epu", "EPU"), ("segment_scr", "SCR")):
        schedule = rates_db.get_rates(
            kind, plancode, segment.issue_age, segment.rate_sex,
            segment.rate_class, scale=1, band=segment.band,
        ) or []
        getattr(rates, attr)[segment.coverage_phase] = schedule


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
        rates.benefit_coi[ben_key] = rates_db.get_rates(
            "BENCOI", policy.plancode, issue_age=seg.issue_age, sex=seg.rate_sex,
            rateclass=seg.rate_class, scale=1, band=seg.band, benefit_type=ben_key,
        ) or []


@dataclass
class _PolicyChangeOutcome:
    """What one applied policy change did to the projection month."""

    av_adjustment: float = 0.0       # AV movement this month (negative = charge)
    coverage_changed: bool = False   # SA moved -> targets + guideline recompute fired
    material_change: bool = False    # face increase / B->A -> new 7-pay period (KZ)


def _reduce_base_face(policy, amount, rates, change_date, rate_year, charge_scr) -> float:
    """Reduce base coverage newest-first by ``amount``; re-band what remains.

    Returns the AV adjustment (the decreased units' surrender charge when
    ``charge_scr`` — RERUN charges it on an elective face decrease, but not on
    the A->B level-DB specified-amount adjustment).
    """
    av_adjustment = 0.0
    remaining = amount
    for seg in reversed(policy.segments):
        if remaining <= 0:
            break
        cut = min(seg.face_amount, remaining)
        cut_units = cut / (seg.vpu or 1000.0)
        if charge_scr:
            schedule = rates.segment_scr.get(seg.coverage_phase, rates.scr)
            scr_rate = _rate_from_schedule(
                schedule, _coverage_year(seg, change_date, rate_year))
            av_adjustment -= scr_rate * cut_units
        seg.units -= cut_units
        seg.face_amount -= cut
        remaining -= cut
        _reband_segment(rates, seg, policy.plancode)
    policy.face_amount = sum(s.face_amount for s in policy.segments)
    _reband_benefits(rates, policy)  # benefit COI rates follow the base band
    return av_adjustment


def _append_face_increase_segment(policy, rates, delta, attained_age, change_date) -> None:
    """Append the face-increase segment, issued at the current attained age.

    CyberLife/RERUN band the increase's COI by the new TOTAL specified amount,
    not the increment's own size.
    """
    from suiteview.core.rates import Rates

    base = policy.base_segment
    new_total = policy.total_face + delta
    new_band = Rates().get_band(policy.plancode, new_total)
    new_band = int(new_band) if new_band is not None else base.band
    new_phase = max((s.coverage_phase for s in policy.segments), default=1) + 1
    new_seg = CoverageSegment(
        coverage_phase=new_phase,
        is_base=True,
        issue_date=change_date,
        issue_age=attained_age,
        rate_sex=base.rate_sex,
        rate_class=base.rate_class,
        face_amount=delta,
        original_face_amount=delta,
        units=delta / (base.vpu or 1000.0),
        vpu=base.vpu,
        band=new_band,
        original_band=new_band,
        table_rating=base.table_rating,
        flat_extra=base.flat_extra,
        status="A",
    )
    policy.segments.append(new_seg)
    _load_segment_rates(rates, new_seg, policy.plancode)
    policy.face_amount = sum(s.face_amount for s in policy.segments)


def _apply_policy_change(
    policy, config, change, attained_age, change_date, rates, rate_year, av,
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
    restarts the 7-pay period and recomputes the 7-pay level.
    """
    outcome = _PolicyChangeOutcome()
    face_before = sum(s.face_amount for s in policy.segments) or policy.face_amount

    if change.kind == PolicyChangeKind.DB_OPTION:
        old = str(policy.db_option or "").upper()
        new = str(change.value or "").upper()
        if new and new != old:
            if old == "A" and new == "B":
                # Level-DB mechanic: shift AV out of the specified amount
                # (SA-only — no AV movement, no surrender charge).
                _reduce_base_face(
                    policy, max(av, 0.0), rates, change_date, rate_year,
                    charge_scr=False,
                )
                outcome.coverage_changed = True
            elif old == "B" and new == "A":
                # Inverse: fold the AV back into the specified amount (in place,
                # no new segment — this is not an elective face increase).
                base = policy.base_segment
                if base is not None and av > 0.0:
                    base.face_amount += av
                    base.units += av / (base.vpu or 1000.0)
                    _reband_segment(rates, base, policy.plancode)
                    policy.face_amount = sum(s.face_amount for s in policy.segments)
                    _reband_benefits(rates, policy)
                    outcome.coverage_changed = True
                outcome.material_change = True  # KZ fires on "BA"
            policy.db_option = new
    elif change.kind == PolicyChangeKind.FACE_AMOUNT:
        new_total = float(change.value)
        delta = new_total - face_before
        if delta < -1e-6:
            outcome.av_adjustment += _reduce_base_face(
                policy, -delta, rates, change_date, rate_year, charge_scr=True)
            outcome.coverage_changed = True
        elif delta > 1e-6:
            _append_face_increase_segment(policy, rates, delta, attained_age, change_date)
            outcome.coverage_changed = True
            outcome.material_change = True

    if outcome.coverage_changed:
        ctp_before = policy.ctp
        targets = compute_target_premiums(policy, config, as_of=change_date)
        policy.mtp = targets.mtp_annual / 12.0
        policy.ctp = targets.ctp_annual
        _recalc_guideline_on_change(
            policy, config, change, attained_age,
            face_before=face_before,
            ctp_before=ctp_before,
            material_change=outcome.material_change,
            change_date=change_date,
        )
    return outcome


def _recalc_guideline_on_change(
    policy,
    config,
    change,
    attained_age: int,
    *,
    face_before: float,
    ctp_before: float,
    material_change: bool,
    change_date,
) -> None:
    """Recalculate GLP/GSP (and 7-pay on a material change) at a policy change.

    RERUN (Guideline_Premiums rows 5..10): the new guideline premiums are the
    attained-age delta — new = prior + (after − before) — floored to a
    monthly-divisible cent (TRUNC(x/12,2)·12). A material change restarts the
    7-pay period at the change date and fully recomputes the 7-pay level at the
    after-change state, capped at sMax7702RecalcsAllowed (=1) recalcs.

    ``change.metadata`` may inject RERUN's own recalculated values
    (``new_glp`` / ``new_gsp`` / ``new_7pay``) so the AV/segment/target
    mechanics can be penny-validated independently of guideline-calc
    calibration; otherwise the values come from the commutation calculator on
    the guaranteed COI scale.
    """
    md = change.metadata or {}
    recalc_count = getattr(policy, "_guideline_recalc_count", 0) + 1
    policy._guideline_recalc_count = recalc_count

    new_glp = md.get("new_glp")
    new_gsp = md.get("new_gsp")
    new_7pay = md.get("new_7pay")

    glp_delta = gsp_delta = 0.0
    computed_7pay: Optional[float] = None
    needs_calc = new_glp is None or new_gsp is None or new_7pay is None
    if needs_calc:
        try:
            before, after = _guideline_change_inputs(
                policy, config, attained_age, face_before, ctp_before)
            from suiteview.illustration.core.guideline_calc import (
                calculate_7pay_premium,
                calculate_glp,
                calculate_gsp,
            )

            glp_delta = calculate_glp(after) - calculate_glp(before)
            gsp_delta = calculate_gsp(after) - calculate_gsp(before)
            computed_7pay = calculate_7pay_premium(after)
        except NotImplementedError:
            # Commutation method covers level (DBO A) benefits only. Keep the
            # loaded guideline values rather than produce a quietly-wrong one.
            logger.warning(
                "Guideline recalc skipped at %s: non-level death benefit "
                "(DBO %s) needs the iterative method or injected values.",
                change_date, policy.db_option,
            )

    if new_glp is not None:
        policy.glp = floor_monthly_cent(float(new_glp))
    elif glp_delta:
        policy.glp = floor_monthly_cent(floor_monthly_cent(policy.glp) + glp_delta)
    if new_gsp is not None:
        policy.gsp = floor_monthly_cent(float(new_gsp))
    elif gsp_delta:
        policy.gsp = floor_monthly_cent(floor_monthly_cent(policy.gsp) + gsp_delta)

    # 7-pay LEVEL recalculates on ANY coverage change (KY fires on HJ), within
    # the allowed recalc count (sMax7702RecalcsAllowed = 1) unless injected;
    # only a MATERIAL change restarts the 7-pay period (KZ / LA).
    if new_7pay is not None:
        policy.tamra_7pay_level = floor_monthly_cent(float(new_7pay))
    elif computed_7pay is not None and recalc_count <= 1:
        policy.tamra_7pay_level = floor_monthly_cent(computed_7pay)
    if material_change:
        policy.tamra_7pay_start_date = change_date


def _guideline_change_inputs(policy, config, attained_age, face_before, ctp_before):
    """Build before/after GuidelinePremiumInputs at the current attained age.

    Mortality is the contract's guaranteed COI (scale 0) expressed as annual qx;
    expenses are the CURRENT loads/fees. The before/after states differ by
    specified amount, units, and target premium.
    """
    from suiteview.illustration.core.commutation import MortalityTable
    from suiteview.illustration.core.guideline_calc import (
        ExpenseAssumptions,
        GuidelinePremiumInputs,
    )

    base = policy.base_segment
    guar = load_rates(policy, config, coi_scale=0)
    coi_sched = guar.segment_coi.get(base.coverage_phase, [])
    qx = []
    for dur in range(1, len(coi_sched)):
        rate = coi_sched[dur]
        if rate is None:
            break
        monthly_q = float(rate) / 1000.0
        qx.append(min(1.0, 1.0 - (1.0 - monthly_q) ** 12))
    mortality = MortalityTable.from_rates(qx, start_age=base.issue_age, name="guar-coi")

    cur = load_rates(policy, config, coi_scale=1)
    if config.mfee == "Table":
        mfee_annual = 12.0 * get_rate(cur, "mfee", 1)
    else:
        try:
            mfee_annual = 12.0 * float(config.mfee)
        except (TypeError, ValueError):
            mfee_annual = 0.0
    if config.epu_code == "Table":
        epu_annual = 12.0 * get_rate(cur, "epu", 1)
    else:
        try:
            epu_annual = 12.0 * float(config.epu_code)
        except (TypeError, ValueError):
            epu_annual = 0.0

    def build(face: float, ctp: float) -> GuidelinePremiumInputs:
        expenses = ExpenseAssumptions(
            premium_load_target=get_rate(cur, "tpp", 1),
            premium_load_excess=get_rate(cur, "epp", 1),
            target_premium=float(ctp or 0.0),
            per_policy_fee_annual=mfee_annual,
            per_unit_charge_annual=epu_annual,
            units=face / 1000.0,
        )
        return GuidelinePremiumInputs(
            attained_age=attained_age,
            mortality=mortality,
            specified_amount=face,
            db_option=policy.db_option,
            endowment_age=100,
            guaranteed_rate=float(policy.guaranteed_interest_rate or 0.0),
            glp_rate=0.04,
            gsp_rate=0.06,
            expenses=expenses,
        )

    return build(face_before, ctp_before), build(policy.total_face, policy.ctp)


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


def _apply_guideline_forceout(
    gsp: float,
    accumulated_glp: float,
    premiums_to_date: float,
    withdrawals_to_date: float,
    account_value_before_premium: float,
    *,
    enabled: bool,
    is_cvat: bool,
    prior_exception_mode: bool,
) -> tuple[float, float, float]:
    """Guideline force-out (CalcEngine KX).

    The limit is the GREATER of GSP and accumulated GLP. The force-out is the
    cumulative premium-net-of-withdrawals above that limit, capped by available
    account value. It is disabled when TEFRA conformance is off, for CVAT
    policies, or once exception mode is on (so the exception premium is not
    immediately clawed back).
    """
    if (not enabled) or is_cvat or prior_exception_mode:
        return 0.0, withdrawals_to_date, account_value_before_premium

    guideline_limit = max(gsp, accumulated_glp)
    excess = max(0.0, (premiums_to_date - withdrawals_to_date) - guideline_limit)
    forceout = min(max(0.0, account_value_before_premium), excess)
    return forceout, withdrawals_to_date + forceout, account_value_before_premium - forceout


def _tamra_year(policy: IllustrationPolicyData, month_date) -> int:
    """Policy year within the active 7-pay window (CalcEngine LD).

    Returns 999 when there is no active 7-pay start date (no TAMRA cap).
    """
    start = policy.tamra_7pay_start_date
    if start is None or month_date is None:
        return 999
    months = (month_date.year - start.year) * 12 + (month_date.month - start.month)
    if month_date.day < start.day:
        months -= 1
    return (max(months, 0) // 12) + 1


def _guideline_premium_cap(
    options: IllustrationOptions,
    policy: IllustrationPolicyData,
    guideline_limit: float,
    premiums_to_date: float,
    withdrawals_to_date: float,
    accumulated_7pay: float,
    tamra_year: int,
) -> Optional[float]:
    """Acceptance cap on this month's premium (CalcEngine vAppliedScheduledPremium).

    The cap is the smaller of the remaining guideline room (cumulative premium
    may not exceed the greater of GSP / AccumGLP) and the remaining 7-pay room
    (cumulative 7-pay contributions may not exceed 7-pay level x TAMRA year).
    Returns None when neither limit is enforced.
    """
    cap: Optional[float] = None
    if options.guideline_cap_enabled and not policy.is_cvat:
        cap = max(0.0, guideline_limit - (premiums_to_date - withdrawals_to_date))
    if (
        options.tamra_cap_enabled
        and not policy.is_mec
        and tamra_year <= 7
        and policy.tamra_7pay_level > 0
    ):
        tamra_room = max(0.0, policy.tamra_7pay_level * tamra_year - accumulated_7pay)
        cap = tamra_room if cap is None else min(cap, tamra_room)
    return cap


def _guideline_limit_reached(
    options: IllustrationOptions,
    policy: IllustrationPolicyData,
    guideline_limit: float,
    premiums_to_date: float,
    withdrawals_to_date: float,
) -> bool:
    """True when cumulative premium has consumed the guideline room (CalcEngine SX)."""
    if not options.conform_to_tefra or policy.is_cvat:
        return False
    room = guideline_limit - (premiums_to_date - withdrawals_to_date)
    return room < 0.01


@dataclass
class _ExceptionPremium:
    mode: bool = False
    gross: float = 0.0
    prem: float = 0.0
    av_after_exception: float = 0.0


def _compute_exception_premium(
    options: IllustrationOptions,
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    rate_year: int,
    *,
    av_after_charge: float,
    coi_rate: float,
    guideline_limit_reached: bool,
    past_snet: bool,
    prior_exception_mode: bool,
    prior_lapsed: bool,
    attained_age: int,
) -> _ExceptionPremium:
    """GP exception premium (CalcEngine SY / SZ / TA / TB / TD).

    Once allowed and triggered (past safety net, no CCV, at the guideline limit,
    and account value gone negative), the policy pays the exception premium that
    brings the after-charge account value back to zero. Exception mode latches
    on for the remainder of the projection.
    """
    ccv_active = policy.has_shadow_account
    past_maturity = attained_age >= config.maturity_age

    triggered = (
        options.allow_exception_prems
        and past_snet
        and not ccv_active
        and guideline_limit_reached
        and av_after_charge < 0.0
    )
    mode = (prior_exception_mode or triggered) and not past_maturity

    result = _ExceptionPremium(mode=mode, av_after_exception=av_after_charge)
    if not (mode and past_snet and not ccv_active and not prior_lapsed):
        return result

    gross = max(0.0, -av_after_charge)
    if gross <= 0.0:
        return result

    discount = gross / 1000.0 * coi_rate
    tpp = get_rate(rates, "tpp", rate_year)
    denom = 1.0 - tpp
    if abs(denom) < 1e-9:
        denom = 1.0
    flat = config.prem_flat_load
    prem = (gross - discount + flat) / denom
    av = av_after_charge + (prem * (1.0 - tpp) - flat + discount)

    result.gross = gross
    result.prem = prem
    result.av_after_exception = av
    return result


def _calculate_surrender_charge(
    policy: IllustrationPolicyData,
    rates: IllustrationRates,
    rate_year: int,
    projection_date,
):
    segments = policy.segments or [policy.base_segment]
    segments = [segment for segment in segments if segment is not None]
    if not segments:
        scr_rate = get_rate(rates, "scr", rate_year)
        surrender_charge = scr_rate * policy.units
        return scr_rate, surrender_charge, {}, {}

    scr_rates_by_coverage = {}
    surrender_charges_by_coverage = {}
    for index, segment in enumerate(segments, start=1):
        segment_schedule = rates.segment_scr.get(segment.coverage_phase, rates.scr)
        segment_rate_year = _coverage_year(segment, projection_date, rate_year)
        segment_scr_rate = _rate_from_schedule(segment_schedule, segment_rate_year)
        segment_surrender_charge = segment_scr_rate * segment.units
        key = f"cov{index}"
        scr_rates_by_coverage[key] = segment_scr_rate
        surrender_charges_by_coverage[key] = segment_surrender_charge

    return (
        scr_rates_by_coverage.get("cov1", 0.0),
        sum(surrender_charges_by_coverage.values()),
        scr_rates_by_coverage,
        surrender_charges_by_coverage,
    )
