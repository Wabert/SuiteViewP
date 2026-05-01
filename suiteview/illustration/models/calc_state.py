from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class MonthlyState:
    """Output for one month of the projection.

    Fields are ordered to match the CalcEngine pipeline sequence:
    counters -> premium -> deduction -> interest -> surrender -> tracking.
    """

    # ── 0. Counters (CalcEngine cols 2-21) ────
    date: Optional[date] = None
    policy_year: int = 0
    policy_month: int = 0           # 1-12 within year
    duration: int = 0               # Total months from issue
    attained_age: int = 0
    is_anniversary: bool = False

    # ── 0b. Loan Capitalize and Repay (cols 336-341) ──
    rg_loan_princ: float = 0.0          # After cap/repay — beginning of month
    rg_loan_accrued: float = 0.0
    pf_loan_princ: float = 0.0
    pf_loan_accrued: float = 0.0
    vbl_loan_princ: float = 0.0
    vbl_loan_accrued: float = 0.0

    # ── 1. Apply Premium (cols 367-403) ───────
    gross_premium: float = 0.0
    prem_under_target: float = 0.0  # Portion at TPP rate (under CTP)
    prem_over_target: float = 0.0   # Portion at EPP rate (over CTP)
    target_load: float = 0.0
    excess_load: float = 0.0
    flat_load: float = 0.0
    total_premium_load: float = 0.0
    net_premium: float = 0.0
    av_after_premium: float = 0.0

    # ── 2. Monthly Deduction (cols 405-516) ───
    nar_av: float = 0.0             # max(0, av_after_premium)
    standard_db: float = 0.0
    corridor_rate: float = 0.0
    gross_db: float = 0.0
    corr_amount: float = 0.0       # gross_db - standard_db

    # Per-segment death benefit discount
    discounted_db_cov1: float = 0.0
    discounted_db_corr: float = 0.0
    discounted_db: float = 0.0

    # Per-segment NAR (FIFO: AV → cov1 first, corridor last)
    nar_cov1: float = 0.0
    nar_corr: float = 0.0
    nar: float = 0.0               # total NAR

    # Per-segment COI (corridor uses cov1 rate)
    coi_rate: float = 0.0
    coi_charge_cov1: float = 0.0
    coi_charge_corr: float = 0.0
    coi_charge: float = 0.0

    epu_rate: float = 0.0
    epu_charge: float = 0.0
    mfee_charge: float = 0.0
    av_charge: float = 0.0         # % of AV charge (monthly, not /12)
    pw_charge: float = 0.0         # Premium Waiver benefit charge
    benefit_charges: float = 0.0   # Total benefit/rider charges
    total_deduction: float = 0.0
    av_after_deduction: float = 0.0

    # ── 3. Interest Credit (cols 548-585) ─────
    days_in_month: int = 0
    annual_interest_rate: float = 0.0
    bonus_interest_rate: float = 0.0
    effective_annual_rate: float = 0.0
    monthly_interest_rate: float = 0.0
    reg_impaired_int: float = 0.0       # Interest on AV backing regular loans
    pref_impaired_int: float = 0.0      # Interest on AV backing preferred loans
    interest_credited: float = 0.0
    av_end_of_month: float = 0.0

    # ── 3b. Loan Interest Accrual (cols 587-592) ──
    reg_loan_charge: float = 0.0        # Regular loan interest accrued this month
    pref_loan_charge: float = 0.0       # Preferred loan interest accrued this month
    end_rg_loan_princ: float = 0.0      # End-of-month reg loan principal
    end_rg_loan_accrued: float = 0.0    # End-of-month reg loan accrued interest
    end_pf_loan_princ: float = 0.0      # End-of-month pref loan principal
    end_pf_loan_accrued: float = 0.0    # End-of-month pref loan accrued interest
    end_vbl_loan_princ: float = 0.0     # End-of-month variable loan principal
    end_vbl_loan_accrued: float = 0.0   # End-of-month variable loan accrued interest
    policy_debt: float = 0.0            # Sum of all 6 ending loan buckets

    # ── 4. End-of-Month Values (cols 524-600) ─
    scr_rate: float = 0.0
    surrender_charge: float = 0.0
    surrender_value: float = 0.0
    ending_db: float = 0.0

    # ── 5. Shadow Account (CCV) (cols 614-648) ─
    shadow_bav: float = 0.0             # Beginning AV (prev month's shadow_eav)
    shadow_wd_charges: float = 0.0      # Withdrawals, charges, and force-outs
    shadow_sa: float = 0.0              # Shadow specified amount
    shadow_target_prem: float = 0.0     # Shadow target premium
    shadow_prem_under_target: float = 0.0
    shadow_prem_over_target: float = 0.0
    shadow_target_load: float = 0.0
    shadow_excess_load: float = 0.0
    shadow_prem_load: float = 0.0       # Total shadow premium load
    shadow_net_prem: float = 0.0
    shadow_nar_av: float = 0.0          # Not floored at 0
    shadow_db: float = 0.0              # SA + (shadow_nar_av if DBO=B)
    shadow_coi_rate: float = 0.0
    shadow_coi: float = 0.0
    shadow_dbd_rate: float = 0.0
    shadow_nar: float = 0.0
    shadow_epu_rate: float = 0.0
    shadow_epu: float = 0.0
    shadow_mfee: float = 0.0
    shadow_rider_charges: float = 0.0   # Rider charges (excl CCV charge)
    shadow_md: float = 0.0              # Total shadow monthly deduction
    shadow_av: float = 0.0              # After deduction (before interest)
    shadow_days: int = 0
    shadow_int_rate: float = 0.0
    shadow_eff_rate: float = 0.0
    shadow_interest: float = 0.0
    shadow_eav: float = 0.0             # End-of-month shadow AV
    shadow_eav_less_debt: float = 0.0   # Shadow EAV minus policy debt

    # ── 6. Safety Net / Lapse Protection (cols 265-267, 662-669) ─
    monthly_mtp: float = 0.0            # Monthly minimum target premium
    accumulated_mtp: float = 0.0        # Running accumulated MTP
    accum_mtp_less_prem: float = 0.0    # (PremTD - WD - Loans) - AccumMTP
    snet_active: bool = False           # Safety net protection active
    shadow_protection: bool = False     # Shadow account protection active
    positive_sv: bool = False           # Surrender value > 0
    av_less_loans: float = 0.0          # AV - policy debt (for MLUL lapse test)

    # ── Cumulative Tracking ───────────────────
    premiums_ytd: float = 0.0
    premiums_to_date: float = 0.0
    withdrawals_to_date: float = 0.0
    cost_basis: float = 0.0
    cumulative_interest: float = 0.0
    cumulative_charges: float = 0.0

    # ── Status ────────────────────────────────
    lapsed: bool = False
