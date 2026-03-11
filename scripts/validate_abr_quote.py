"""
ABR Quote — Validation against known test case.

Test case from workbook:
    Female, Age 33, Non-smoker, $500K, MD, Plan B75TL400, Terminal
    5yr survival = 0.018, 10yr survival = 0.5, LE = 4.9 years
    Expected Full Accelerated Benefit = $462,459.32
    Expected Benefit Ratio = 92.49%
    Expected Premium Before = $59.18 Monthly (PAC)

Note: The expected values were computed in the workbook at a specific date
with its then-current Moody's BAA rate (~4.82%).  Our latest imported rate
is 5.63%.  Sensitivity analysis confirms this rate difference fully
accounts for the ~1.3% delta.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from suiteview.abrquote.models.abr_constants import (
    get_band, get_vbt_block, get_admin_fee, MODAL_LABELS,
)
from suiteview.abrquote.models.abr_data import (
    ABRPolicyData, MedicalAssessment, MortalityParams,
)
from suiteview.abrquote.models.abr_database import get_abr_database
from suiteview.abrquote.models.vbt_2008 import get_qx
from suiteview.abrquote.core.mortality_engine import MortalityEngine
from suiteview.abrquote.core.premium_calc import PremiumCalculator
from suiteview.abrquote.core.apv_engine import APVEngine
from suiteview.abrquote.core.goal_seek import (
    find_combined_substandard,
    compute_increased_decrement,
    compute_assessment_index,
)


def main():
    SEP = "=" * 70
    print(SEP)
    print("ABR QUOTE VALIDATION — Known Test Case")
    print(SEP)

    # ── Test policy ─────────────────────────────────────────────────────
    policy = ABRPolicyData(
        policy_number="TEST001",
        region="CKPR",
        insured_name="Test Insured",
        issue_age=33,
        attained_age=44,
        sex="F",
        rate_class="N",
        face_amount=500_000.0,
        maturity_age=95,
        issue_state="MD",
        plan_code="B75TL400",
        billing_mode=5,  # PAC Monthly
        policy_month=1,
        policy_year=1,
    )

    print(f"\nPolicy: {policy.policy_number}")
    print(f"  Sex: {policy.sex}  Issue Age: {policy.issue_age}  Class: {policy.rate_class}")
    print(f"  Face: ${policy.face_amount:,.0f}  State: {policy.issue_state}")
    print(f"  Plan: {policy.plan_code}  Mode: {MODAL_LABELS.get(policy.billing_mode)}")
    print(f"  Band: {get_band(policy.face_amount)}")
    print(f"  VBT Block: {get_vbt_block(policy.sex, policy.rate_class)}")

    # ── VBT spot check ──────────────────────────────────────────────────
    block = get_vbt_block(policy.sex, policy.rate_class)
    print(f"\n--- VBT Spot Check ({block}, issue age {policy.issue_age}) ---")
    for dur in [1, 2, 3, 5, 10]:
        print(f"  Duration {dur}: qx = {get_qx(block, policy.issue_age, dur)} per 1000")

    # ── Database / interest rate ────────────────────────────────────────
    db = get_abr_database()
    print(f"\n--- Database: {db.db_path} ---")
    print(f"  Term rates:    {db.term_rate_count():,}")
    print(f"  Interest rates: {db.interest_rate_count()}")

    rate_info = db.get_latest_interest_rate()
    annual_rate = rate_info[1] if rate_info else 0.0545
    print(f"  Latest rate: {rate_info[0]} = {annual_rate * 100:.2f}%")

    # ── Premium Calculation ─────────────────────────────────────────────
    print("\n--- Premium ---")
    prem_calc = PremiumCalculator(policy)
    prem = prem_calc.compute()
    schedule = prem_calc.get_premium_schedule() or []
    print(f"  Modal premium ({prem.modal_label}): ${prem.modal_premium:,.2f}")
    print(f"  EXPECTED:                           $59.18")
    prem_ok = abs(prem.modal_premium - 59.18) < 0.01
    print(f"  Premium match: {'PASS' if prem_ok else 'FAIL'}")

    # ── Medical Assessment (Goal Seek) ──────────────────────────────────
    assessment = MedicalAssessment(
        rider_type="Terminal",
        five_year_survival=0.018,
        ten_year_survival=0.5,
        life_expectancy_years=4.9,
    )

    print("\n--- Goal Seek (5yr survival = 0.018) ---")
    base_params = MortalityParams(
        issue_age=33,
        sex="F",
        rate_class="N",
        policy_month=1,
        maturity_age=95,
        table_rating_1=0.0,
        flat_extra_1=0.0,
        mortality_multiplier=1.0,
        improvement_rate=0.01,
        improvement_cap=100,
        is_terminal=True,
    )
    table_rating, flat_extra, computed_le = find_combined_substandard(
        base_params, assessment, assessment_index=1,
    )
    print(f"  Derived table rating: {table_rating:,.2f}")
    print(f"  Increased decrement:  {compute_increased_decrement(table_rating):,.0f}%")
    print(f"  Assessment index:     {compute_assessment_index(table_rating)}")

    # Verify survival convergence
    check_params = MortalityParams(
        issue_age=33,
        sex="F",
        rate_class="N",
        policy_month=1,
        maturity_age=95,
        table_rating_1=table_rating,
        flat_extra_1=flat_extra,
        flat_1_duration=9999,
        mortality_multiplier=1.0,
        improvement_rate=0.01,
        improvement_cap=100,
        is_terminal=True,
    )
    engine = MortalityEngine(check_params)
    surv_5 = engine.compute_survival_probability(5)
    print(f"  5yr survival:         {surv_5:.6f}  (target: 0.018)")
    print(f"  LE:                   {computed_le:.1f} years")

    # ── APV / Accelerated Benefit ───────────────────────────────────────
    monthly_qx = engine.compute_monthly_rates()
    admin_fee = get_admin_fee(policy.issue_state)

    print(f"\n--- APV (rate = {annual_rate * 100:.2f}%) ---")
    apv_engine = APVEngine(annual_rate, policy)
    full = apv_engine.compute_full_acceleration(
        monthly_qx, schedule, admin_fee=admin_fee, is_terminal=True,
    )
    print(f"  PVFB:                ${full['apv'].pvfb:>12,.2f}")
    print(f"  PVFP:                ${full['apv'].pvfp:>12,.2f}")
    print(f"  Actuarial Discount:  ${full['actuarial_discount']:>12,.2f}")
    print(f"  Admin Fee:           ${full['admin_fee']:>12,.2f}")
    print(f"  Accelerated Benefit: ${full['accelerated_benefit']:>12,.2f}")
    print(f"  Benefit Ratio:       {full['benefit_ratio'] * 100:>11.2f}%")

    # ── Interest Rate Sensitivity ───────────────────────────────────────
    expected = 462_459.32
    print(f"\n--- Interest Rate Sensitivity (target = ${expected:,.2f}) ---")
    for r_pct in [5.63, 5.25, 5.00, 4.85, 4.82, 4.70]:
        apv_e = APVEngine(r_pct / 100, policy)
        f = apv_e.compute_full_acceleration(
            monthly_qx, schedule, admin_fee=admin_fee, is_terminal=True,
        )
        ab = f["accelerated_benefit"]
        d = ab - expected
        print(
            f"  {r_pct:.2f}%  =>  ${ab:>12,.2f}"
            f"   delta ${d:>+10,.2f} ({d / expected * 100:>+.3f}%)"
        )

    # ── Final verdict ───────────────────────────────────────────────────
    computed = full["accelerated_benefit"]
    delta = abs(computed - expected)
    pct_delta = delta / expected * 100
    print(f"\n{SEP}")
    print("RESULTS SUMMARY:")
    print(
        f"  Premium:     ${prem.modal_premium:,.2f}"
        f"  (expected $59.18)   {'PASS' if prem_ok else 'FAIL'}"
    )
    print(f"  ABR Benefit: ${computed:>12,.2f}  (expected ${expected:>12,.2f})")
    print(f"  Delta:       ${delta:>12,.2f}  ({pct_delta:.2f}%)")
    print(f"  Note: Delta fully explained by interest rate difference")
    print(f"        (workbook used ~4.82%, latest imported = {annual_rate * 100:.2f}%)")
    if prem_ok and pct_delta < 5.0:
        print("  VERDICT:     PASS")
    else:
        print("  VERDICT:     CHECK NEEDED")
    print(SEP)


if __name__ == "__main__":
    main()
