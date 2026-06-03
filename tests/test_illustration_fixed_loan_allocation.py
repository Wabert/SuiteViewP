from suiteview.illustration.core.loan_handler import LoanState, apply_new_fixed_loan


def test_fixed_loan_prefers_preferred_capacity_first():
    loan = LoanState(rg_loan_princ=50.0, pf_loan_princ=25.0)

    updated = apply_new_fixed_loan(
        loan=loan,
        requested_amount=120.0,
        account_value=500.0,
        premiums_to_date=300.0,
        withdrawals_to_date=50.0,
        preferred_loans_available=True,
    )

    # Preferred capacity = 500 - 75 - (300 - 50) = 175
    assert updated.pf_loan_princ == 145.0
    assert updated.rg_loan_princ == 50.0


def test_fixed_loan_spills_excess_to_regular():
    loan = LoanState(rg_loan_princ=50.0, pf_loan_princ=25.0)

    updated = apply_new_fixed_loan(
        loan=loan,
        requested_amount=250.0,
        account_value=500.0,
        premiums_to_date=300.0,
        withdrawals_to_date=50.0,
        preferred_loans_available=True,
    )

    # Preferred capacity = 175, remaining 75 goes to regular.
    assert updated.pf_loan_princ == 200.0
    assert updated.rg_loan_princ == 125.0


def test_fixed_loan_uses_regular_when_preferred_not_available():
    loan = LoanState(rg_loan_princ=10.0, pf_loan_princ=5.0)

    updated = apply_new_fixed_loan(
        loan=loan,
        requested_amount=80.0,
        account_value=500.0,
        premiums_to_date=0.0,
        withdrawals_to_date=0.0,
        preferred_loans_available=False,
    )

    assert updated.rg_loan_princ == 90.0
    assert updated.pf_loan_princ == 5.0