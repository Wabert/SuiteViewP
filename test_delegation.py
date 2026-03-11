"""
Quick runtime test for Phase 1 + Phase 2 delegation changes.
Exercises all properties that were refactored to delegate to record classes.
"""
import sys
import os
import traceback

os.environ["PYTHONIOENCODING"] = "utf-8"

from suiteview.polview.models.policy_information import load_policy

def test_property(pol, name, expected_type=None):
    """Test a single property, return (name, value, ok)."""
    try:
        val = getattr(pol, name)
        type_ok = True
        if expected_type and val is not None:
            type_ok = isinstance(val, expected_type)
        status = "OK" if type_ok else f"TYPE MISMATCH (got {type(val).__name__})"
        return name, val, status
    except Exception as e:
        return name, None, f"ERROR: {e}"

def main():
    policy_number = sys.argv[1] if len(sys.argv) > 1 else "U0532652"
    print(f"Loading policy {policy_number}...")
    
    try:
        pol = load_policy(policy_number, region="CKPR")
    except Exception as e:
        print(f"Failed to load policy: {e}")
        traceback.print_exc()
        return 1
    
    print(f"Policy loaded: {pol.policy_number}")
    print(f"is_advanced_product: {pol.is_advanced_product}")
    print()
    
    # ---- Phase 1: Loan Properties ----
    phase1_props = [
        "trad_loan_count",
        "total_regular_loan_principal", "total_regular_loan_accrued",
        "total_preferred_loan_principal", "total_preferred_loan_accrued",
        "total_variable_loan_principal", "total_variable_loan_accrued",
        "policy_debt", "preferred_loans_available",
    ]
    
    # ---- Phase 2: Cash Value, TAMRA, Accumulators, Dates, Policy Props ----
    phase2_props = [
        # Cash Value
        "cash_surrender_value", "accumulation_value", "death_benefit", "net_amount_at_risk",
        # TAMRA/MEC
        "is_mec", "seven_pay_premium", "accumulated_glp", "accumulated_mtp",
        # Accumulators
        "total_regular_premium", "total_premiums_paid", "total_additional_premium",
        "total_additional_premiums", "premium_td",
        "total_regular_premium_ytd", "total_additional_premium_ytd", "premium_ytd",
        "total_withdrawals", "cost_basis", "policy_totals_count",
        # Advanced Dates
        "last_anniversary", "next_monthliversary", "last_financial_date",
        "next_bill_date", "premium_paid_to_date", "valuation_date",
        "grace_period_expiry_date", "in_grace",
        # Additional Policy
        "original_entry_code", "last_entry_code", "policy_1035_indicator",
        "servicing_agent_number", "servicing_branch_code",
        "servicing_market_org", "agency_branch_code", "is_ffs",
        "policy_loan_charge_rate", "forced_premium_indicator",
        "mdo_code", "bill_form_code",
        # Non-Trad Policy
        "guaranteed_interest_rate", "corridor_percent",
        "grace_rule_code", "tefra_defra_code", "tefra_defra", "gpt_cvat",
    ]
    
    all_props = [("PHASE 1 — Loan Properties", phase1_props),
                 ("PHASE 2 — Cash Value / TAMRA / Accumulators / Dates / Policy", phase2_props)]
    
    total = 0
    errors = 0
    
    for section_name, props in all_props:
        print(f"{'='*60}")
        print(f"  {section_name}")
        print(f"{'='*60}")
        for name in props:
            total += 1
            prop_name, val, status = test_property(pol, name)
            indicator = "PASS" if status == "OK" else "FAIL"
            val_str = repr(val) if val is not None else "None"
            if len(val_str) > 50:
                val_str = val_str[:47] + "..."
            print(f"  [{indicator}] {prop_name:40s} = {val_str:>20s}  [{status}]")
            if status != "OK":
                errors += 1
        print()
    
    # Test indexed loan access methods
    print(f"{'='*60}")
    print(f"  INDEXED ACCESS METHODS")
    print(f"{'='*60}")
    
    indexed_tests = []
    if pol.trad_loan_count > 0:
        indexed_tests.extend([
            ("trad_loan_principal", 0), ("trad_loan_accrued_interest", 0),
            ("trad_loan_interest_type", 0), ("trad_loan_interest_status", 0),
            ("trad_loan_preferred", 0),
        ])
    if pol.loan_records.loan_fund_count > 0:
        indexed_tests.extend([
            ("loan_fund_id", 0), ("loan_fund_principal", 0),
            ("loan_fund_accrued_interest", 0), ("loan_fund_mv_date", 0),
            ("loan_fund_interest_status", 0), ("loan_fund_preferred", 0),
        ])
    if pol.loan_records.loan_repay_count > 0:
        indexed_tests.extend([
            ("loan_repay_amount", 0), ("loan_repay_principal", 0),
            ("loan_repay_interest", 0),
        ])
    
    if not indexed_tests:
        print("  (no loan data for indexed tests)")
    
    for method_name, idx in indexed_tests:
        total += 1
        try:
            method = getattr(pol, method_name)
            val = method(idx)
            print(f"  [PASS] {method_name}({idx}){' ':30s} = {repr(val):>20s}  [OK]")
        except Exception as e:
            errors += 1
            print(f"  [FAIL] {method_name}({idx}){' ':30s}   [ERROR: {e}]")
    
    print()
    print(f"{'='*60}")
    print(f"  RESULTS: {total - errors}/{total} passed, {errors} errors")
    print(f"{'='*60}")
    
    return 1 if errors > 0 else 0

if __name__ == "__main__":
    sys.exit(main())
