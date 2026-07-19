"""Print the supplemental Expense Report page as fixed-width text for review.

Builds a synthetic two-year projection (same shape as the report tests),
assembles the IllustrationReport, and prints the expense page's lines with a
column ruler so header/value alignment can be eyeballed.

Usage:
    venv\\Scripts\\python.exe tools/preview_expense_page.py
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> None:
    from suiteview.illustration.core.report_builder import build_ul_report
    from suiteview.illustration.models.calc_state import MonthlyState
    from suiteview.illustration.models.policy_data import (
        CoverageSegment, IllustrationPolicyData,
    )
    from suiteview.illustration.ui.report_tab import PAGE_WIDTH, format_report_pages

    policy = IllustrationPolicyData(
        policy_number="U0688012", company_code="01", insured_name="JOHN DOE",
        plancode="1U143900", issue_date=date(2019, 11, 9), issue_age=50,
        attained_age=56, rate_sex="M", rate_class="N", face_amount=100000.0,
        db_option="A", account_value=6311.09, valuation_date=date(2026, 5, 9),
        segments=[CoverageSegment(face_amount=100000.0, issue_age=50)],
    )
    results = [MonthlyState(policy_year=7, policy_month=6, duration=78)]
    for year in (8, 9):
        for month in range(1, 13):
            duration = (year - 1) * 12 + month
            results.append(MonthlyState(
                date=date(2019 + year, 11, 9), policy_year=year, policy_month=month,
                duration=duration, attained_age=50 + year - 1,
                gross_premium=1234.56, requested_premium=1234.56,
                total_premium_load=117.28, total_coi_charge=851.53 / 12,
                epu_charge=32.73, mfee_charge=8.13, asset_charge=0.0,
                av_charge=0.0, benefit_charges=4.10, rider_charges=0.0,
                interest_credited=314.82 / 12,
                applied_net_withdrawal=500.0 if (year == 8 and month == 3) else 0.0,
                wd_partial_sc=75.25 if (year == 8 and month == 3) else 0.0,
                av_end_of_month=774721.66 + duration, surrender_charge=441.88,
                ending_sv=508212.76 + duration, ending_db=1727760.0,
                policy_debt=12345.67,
                annual_interest_rate=0.0635,
            ))
    report = build_ul_report(policy, results, run_date=date(2026, 7, 18))
    pages = format_report_pages(report, include_expense_report=True)
    ruler = "".join(str(i % 10) for i in range(1, PAGE_WIDTH + 1))
    print("===== LEDGER PAGE (pages[1]) =====")
    print(ruler)
    for line in pages[1]:
        print(line)
    print(ruler)
    print("\n===== EXPENSE PAGE (pages[-1]) =====")
    print(ruler)
    for line in pages[-1]:
        print(line)
    print(ruler)
    print(f"pages={len(pages)} width_ok="
          f"{all(len(l) <= PAGE_WIDTH for l in pages[-1])}")


if __name__ == "__main__":
    main()
