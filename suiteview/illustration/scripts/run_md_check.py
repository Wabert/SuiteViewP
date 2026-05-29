from __future__ import annotations

import argparse

from suiteview.illustration.core.md_check import calculate_last_monthly_deduction_checks


MATRIX_POLICIES = [
    "UE000576",
    "UE006826",
    "UE015345",
    "UIP00143",
    "UIP23179",
    "U0930725",
    "UE070657",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare calculated last monthly deduction to CyberLife."
    )
    parser.add_argument(
        "policies",
        nargs="*",
        help="Policy numbers to check. Defaults to the UL illustration matrix.",
    )
    parser.add_argument("--region", default="CKPR", help="CyberLife region")
    args = parser.parse_args()

    policies = args.policies or MATRIX_POLICIES
    checks = calculate_last_monthly_deduction_checks(policies, region=args.region)

    print(
        f"{'Policy':<10} {'Val Date':<10} {'System MD':>12} {'Calc MD':>12} "
        f"{'Variance':>12} {'Sys COI':>10} {'Sys Exp':>10} {'Sys Other':>10} "
        f"{'Calc COI':>10} {'Calc EPU':>10} {'Calc Fee':>10} "
        f"{'Calc Ben':>10} {'Calc Rid':>10}"
    )
    print("-" * 150)
    for check in checks:
        print(
            f"{check.policy_number:<10} {check.valuation_date:<10} "
            f"{check.system_md:>12,.2f} {check.calculated_md:>12,.2f} "
            f"{check.variance:>12,.2f} {check.system_coi:>10,.2f} "
            f"{check.system_expense:>10,.2f} {check.system_other:>10,.2f} "
            f"{check.calculated_coi:>10,.2f} {check.calculated_epu:>10,.2f} "
            f"{check.calculated_mfee:>10,.2f} {check.calculated_benefits:>10,.2f} "
            f"{check.calculated_riders:>10,.2f}"
        )


if __name__ == "__main__":
    main()