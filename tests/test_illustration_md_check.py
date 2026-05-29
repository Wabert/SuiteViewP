from suiteview.illustration.core.md_check import calculate_last_monthly_deduction_checks
from suiteview.illustration.scripts.run_md_check import MATRIX_POLICIES


def test_matrix_monthly_deduction_checks_within_cent():
    checks = calculate_last_monthly_deduction_checks(MATRIX_POLICIES)

    assert checks
    for check in checks:
        assert abs(check.variance) < 0.01, check


def test_premium_waiver_rider_basis_checks_within_cent():
    checks = calculate_last_monthly_deduction_checks(["UL092004", "U0122714"])

    for check in checks:
        assert abs(check.variance) < 0.01, check