"""UL Illustration projection engine — orchestrates the monthly pipeline.

Public API:
    engine = IllustrationEngine()
    results = engine.project(policy, months=12)  # → List[MonthlyState]
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.bonus_rates import BonusConfig, load_bonus_config
from suiteview.illustration.core.interest_calc import credit_interest
from suiteview.illustration.core.loan_handler import LoanState, accrue_loan_interest, capitalize_loans
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.premium_handler import apply_premium
from suiteview.illustration.core.rate_loader import (
    IllustrationRates,
    get_rate,
    load_rates,
)
from suiteview.illustration.core.shadow_calc import calculate_shadow
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import IllustrationPolicyData


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
    ) -> List[MonthlyState]:
        """Run monthly projection from current policy state.

        Args:
            policy: Populated IllustrationPolicyData.
            months: Number of months to project. If None, projects to maturity age.

        Returns:
            List of MonthlyState, one per projected month.
        """
        config = load_plancode(policy.plancode)
        rates = self._load_rates(policy, config)

        # Load bonus config from tRates_IntBonus based on valuation date
        val_date = policy.valuation_date or policy.issue_date
        bonus = load_bonus_config(policy.plancode, val_date)

        if months is None:
            remaining_years = policy.maturity_age - policy.attained_age
            remaining_months = remaining_years * 12 - policy.policy_month + 1
            total_months = max(remaining_months, 0)
        else:
            total_months = months

        # Inforce snapshot (month 0) — AV from CyberLife is after-deduction.
        # We must credit interest to roll AV to end-of-month before projecting.
        rate_year_inforce = policy.policy_year
        month_date_inforce = (
            policy.valuation_date
            if policy.valuation_date
            else policy.issue_date + relativedelta(months=policy.duration)
        )
        intr0 = credit_interest(
            policy.account_value, policy, config, rates, bonus,
            rate_year_inforce, policy.attained_age, month_date_inforce,
            reg_loan_balance=policy.regular_loan_principal,
            pref_loan_balance=policy.preferred_loan_principal,
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
        loan0 = accrue_loan_interest(loan0, config, intr0.days_in_month)

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
        )

        # Safety Net / Lapse Protection for inforce month
        monthly_mtp_0 = math.trunc(policy.mtp * 100) / 100
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

        scr_rate_0 = get_rate(rates, "scr", rate_year_inforce)
        surrender_charge_0 = scr_rate_0 * policy.units
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
            av_after_deduction=policy.account_value,
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
            accumulated_mtp=accumulated_mtp_0,
            accum_mtp_less_prem=accum_mtp_less_prem_0,
            snet_active=snet_active_0,
            shadow_protection=shadow_protection_0,
            positive_sv=positive_sv_0,
            av_less_loans=av_less_loans_0,
            # End-of-month values
            scr_rate=scr_rate_0,
            surrender_charge=surrender_charge_0,
            surrender_value=surrender_value_0,
        )

        results: List[MonthlyState] = [inforce]
        state = inforce
        for _ in range(total_months):
            state = self.process_month(state, policy, config, rates, bonus)
            results.append(state)
            if state.lapsed:
                break

        return results

    def process_month(
        self,
        state: MonthlyState,
        policy: IllustrationPolicyData,
        config: PlancodeConfig,
        rates: IllustrationRates,
        bonus: BonusConfig,
    ) -> MonthlyState:
        """Process a single month of the calculation pipeline.

        Pure function — takes the previous month's state, produces the next.
        """
        # ── Step 0: Advance Counters ──────────────────────────
        next_year, next_month = _advance_month(
            state.policy_year, state.policy_month
        )
        duration = state.duration + 1
        attained_age = policy.issue_age + (duration - 1) // 12
        month_date = policy.issue_date + relativedelta(months=duration - 1)
        is_anniversary = next_month == 1

        # Reset YTD on anniversary
        premiums_ytd = 0.0 if is_anniversary else state.premiums_ytd
        premiums_to_date = state.premiums_to_date
        cost_basis = state.cost_basis

        # Start with end-of-month AV from previous month
        av = state.av_end_of_month

        # Rate arrays are 1-indexed by policy year (not monthly duration)
        rate_year = next_year

        # ── Step 0b: Loan Capitalization (at anniversary) ─────
        # Set 1 reads from previous month's Set 2 (ending balances)
        cap_loan = capitalize_loans(
            state.end_rg_loan_princ, state.end_rg_loan_accrued,
            state.end_pf_loan_princ, state.end_pf_loan_accrued,
            state.end_vbl_loan_princ, state.end_vbl_loan_accrued,
            is_anniversary,
        )

        # ── Step 1: Apply Premium ─────────────────────────────
        prem = apply_premium(
            av, policy, config, rates, rate_year,
            premiums_ytd, premiums_to_date, cost_basis,
        )
        av = prem.av_after_premium

        # ── Step 2: Monthly Deduction ─────────────────────────
        ded = calculate_deduction(
            av, policy, config, rates, rate_year,
            attained_age, prem.premiums_to_date,
            monthly_mtp=math.trunc(policy.mtp * 100) / 100,
        )
        av = ded.av_after_deduction

        # ── Step 3: Interest Credit ──────────────────────────
        intr = credit_interest(
            av, policy, config, rates, bonus, rate_year,
            attained_age, month_date,
            reg_loan_balance=cap_loan.rg_loan_princ,
            pref_loan_balance=cap_loan.pf_loan_princ,
        )
        av = intr.av_end_of_month

        # ── Step 3b: Loan Interest Accrual ────────────────────
        accrual_loan = accrue_loan_interest(cap_loan, config, intr.days_in_month)

        # ── Step 3c: Shadow Account (CCV) ─────────────────────
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
        )

        # ── Step 3d: Safety Net Accumulation ──────────────────
        monthly_mtp = math.trunc(policy.mtp * 100) / 100
        accumulated_mtp = state.accumulated_mtp + monthly_mtp
        accum_mtp_less_prem = (
            prem.premiums_to_date - state.withdrawals_to_date
            - accrual_loan.policy_debt
        ) - accumulated_mtp

        if policy.map_cease_date is not None:
            within_snet = month_date <= policy.map_cease_date
        else:
            within_snet = next_year <= config.snet_period
        snet_active = accum_mtp_less_prem >= 0 and within_snet

        # Shadow protection (after SNET period, CCV keeps policy alive)
        past_snet = not within_snet
        shadow_protection = (
            policy.has_shadow_account
            and past_snet
            and shd.shadow_eav_less_debt > 0
        )

        # ── Step 4: End-of-Month Values ──────────────────────
        scr_rate = get_rate(rates, "scr", rate_year)
        surrender_charge = scr_rate * policy.units
        surrender_value = max(av - surrender_charge - accrual_loan.policy_debt, 0.0)

        ending_db = ded.gross_db

        # Multi-factor lapse check (RERUN YL-YS)
        positive_sv = config.lapse_value == "SV" and surrender_value > 0
        av_less_loans = av - accrual_loan.policy_debt
        av_loans_test = config.lapse_value == "AV" and av_less_loans > 0
        any_protection = snet_active or shadow_protection or positive_sv or av_loans_test
        lapsed = state.lapsed or not any_protection

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
            # Deduction
            nar_av=ded.nar_av,
            standard_db=ded.standard_db,
            corridor_rate=ded.corridor_rate,
            gross_db=ded.gross_db,
            corr_amount=ded.corr_amount,
            discounted_db_cov1=ded.discounted_db_cov1,
            discounted_db_corr=ded.discounted_db_corr,
            discounted_db=ded.discounted_db,
            nar_cov1=ded.nar_cov1,
            nar_corr=ded.nar_corr,
            nar=ded.nar,
            coi_rate=ded.coi_rate,
            coi_charge_cov1=ded.coi_charge_cov1,
            coi_charge_corr=ded.coi_charge_corr,
            coi_charge=ded.coi_charge,
            epu_rate=ded.epu_rate,
            epu_charge=ded.epu_charge,
            mfee_charge=ded.mfee_charge,
            av_charge=ded.av_charge,
            pw_charge=ded.pw_charge,
            benefit_charges=ded.benefit_charges,
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
            end_rg_loan_princ=accrual_loan.rg_loan_princ,
            end_rg_loan_accrued=accrual_loan.rg_loan_accrued,
            end_pf_loan_princ=accrual_loan.pf_loan_princ,
            end_pf_loan_accrued=accrual_loan.pf_loan_accrued,
            end_vbl_loan_princ=accrual_loan.vbl_loan_princ,
            end_vbl_loan_accrued=accrual_loan.vbl_loan_accrued,
            policy_debt=accrual_loan.policy_debt,
            # End-of-month
            scr_rate=scr_rate,
            surrender_charge=surrender_charge,
            surrender_value=surrender_value,
            ending_db=ending_db,
            # Tracking
            premiums_ytd=prem.premiums_ytd,
            premiums_to_date=prem.premiums_to_date,
            withdrawals_to_date=state.withdrawals_to_date,
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
            accumulated_mtp=accumulated_mtp,
            accum_mtp_less_prem=accum_mtp_less_prem,
            snet_active=snet_active,
            shadow_protection=shadow_protection,
            positive_sv=positive_sv,
            av_less_loans=av_less_loans,
            # Status
            lapsed=lapsed,
        )

    def _load_rates(
        self,
        policy: IllustrationPolicyData,
        config: PlancodeConfig,
    ) -> IllustrationRates:
        """Load rates with engine-level caching."""
        seg = policy.base_segment
        if seg is None:
            return IllustrationRates()

        cache_key = (
            f"{policy.plancode}|{seg.issue_age}|{seg.rate_sex}|"
            f"{seg.rate_class}|{seg.band}"
        )

        if cache_key not in self._rates_cache:
            self._rates_cache[cache_key] = load_rates(policy, config)

        return self._rates_cache[cache_key]


def _advance_month(policy_year: int, policy_month: int) -> tuple[int, int]:
    """Advance policy year/month by one month."""
    if policy_month == 12:
        return policy_year + 1, 1
    return policy_year, policy_month + 1
