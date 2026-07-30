r"""Render a synthetic IUL report for visual verification.

Usage:
    venv\Scripts\python.exe tools\mock_iul_report.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _policy():
    from suiteview.illustration.models.policy_data import (
        CoverageSegment,
        IllustrationPolicyData,
    )

    parameters = {
        "IX": (0.0, 0.0975, 1.0, 0.0, 0.0),
        "IF": (0.0, 9.9999, 1.0, 0.08, 0.0),
        "IS": (0.0, 9.9999, 1.0, 0.0, 0.075),
        "IC": (0.015, 0.085, 1.0, 0.0, 0.0),
    }
    market_returns = [
        0.1362, 0.0353, -0.3849, 0.2345, 0.1278,
        0.0, 0.1341, 0.2960, 0.1139, -0.0073,
        0.0954, 0.1942, -0.0624, 0.2888, 0.1626,
        0.2689, -0.1944, 0.2423, 0.2331, 0.1639,
    ]
    return IllustrationPolicyData(
        policy_number="UE017436",
        company_code="01",
        insured_name="BRICELYN IRWIN",
        plancode="1U145500",
        form_number="IUL14",
        issue_date=date(2017, 9, 21),
        issue_age=3,
        attained_age=12,
        rate_sex="F",
        rate_class="N",
        face_amount=100000.0,
        db_option="B",
        account_value=5395.01,
        modal_premium=350.0,
        billing_frequency=6,
        premiums_paid_to_date=5816.71,
        valuation_date=date(2026, 6, 21),
        illustration_date=date(2026, 7, 1),
        guaranteed_interest_rate=0.025,
        fund_values={"SW": 149.60, "IX": 2816.33, "IF": 2429.08},
        premium_allocations={
            "U1": 0.0, "IX": 0.5, "IF": 0.5, "IS": 0.0, "IC": 0.0,
        },
        index_illustration_rates={
            "IX": 0.0623, "IF": 0.0623, "IS": 0.0556, "IC": 0.0599,
        },
        index_strategy_parameters={
            fund_id: {
                "floor": values[0],
                "cap": values[1],
                "participation": values[2],
                "int_rate_spread": values[3],
                "specified_rate": values[4],
                "multiplier": 0.0,
                "asset_fee": 0.0,
            }
            for fund_id, values in parameters.items()
        },
        index_benchmark_minimum=0.0388,
        index_benchmark_maximum=0.0756,
        index_market_returns={
            "SP500": [
                {"date": date(year, 12, 31), "return": annual_return}
                for year, annual_return in zip(range(2006, 2026), market_returns)
            ]
        },
        segments=[
            CoverageSegment(
                face_amount=100000.0,
                issue_age=3,
                rate_sex="F",
                rate_class="N",
            )
        ],
    )


def _results(large_values: bool = False):
    from suiteview.illustration.models.calc_state import MonthlyState

    rows = [
        MonthlyState(
            policy_year=9,
            policy_month=9,
            duration=105,
            gsp=4309.0,
            glp=734.14,
            accumulated_glp=6607.26,
        )
    ]
    for year in range(10, 15):
        for month in range(1, 13):
            account_value = (
                42_152_076.0
                if large_values and year == 14
                else 5000.0 + year * 500.0 + month * 25.0
            )
            rows.append(MonthlyState(
                date=date(2026 + year - 10, month, 1),
                policy_year=year,
                policy_month=month,
                duration=(year - 1) * 12 + month,
                attained_age=3 + year - 1,
                requested_premium=350.0 if month in (1, 7) else 0.0,
                gross_premium=350.0 if month in (1, 7) else 0.0,
                annual_interest_rate=0.0623,
                av_end_of_month=account_value,
                ending_sv=account_value,
                ending_db=(
                    43_381_584.0
                    if large_values and year == 14
                    else 105000.0 + year * 500.0 + month * 25.0
                ),
            ))
    return rows


def main() -> None:
    from suiteview.illustration.core.report_builder import build_ul_report
    from suiteview.illustration.ui.report_tab import (
        IllustrationReportTab,
        format_report_pages,
    )

    app = QApplication.instance() or QApplication(sys.argv)
    report = build_ul_report(
        _policy(),
        _results(large_values="--large-values" in sys.argv),
        run_date=date(2026, 7, 1),
    )
    output_dir = Path.home() / ".suiteview" / "iul_report_preview"
    output_dir.mkdir(parents=True, exist_ok=True)

    pages = format_report_pages(report)
    (output_dir / "report.txt").write_text(
        "\n\n\f\n\n".join("\n".join(page) for page in pages),
        encoding="utf-8",
    )
    pdf_path = output_dir / "iul-report-preview.pdf"
    IllustrationReportTab.write_pdf(report, str(pdf_path))

    tab = IllustrationReportTab()
    tab.display_report(report)
    tab.resize(1200, 900)
    tab._sheet_host.adjustSize()
    app.processEvents()
    images = []
    for index in range(tab._sheet_layout.count()):
        widget = tab._sheet_layout.itemAt(index).widget()
        if widget is None:
            continue
        widget.adjustSize()
        image_path = output_dir / f"page-{index + 1}.png"
        widget.grab().save(str(image_path))
        images.append(str(image_path))
    print(json.dumps({
        "pages": len(pages),
        "pdf": str(pdf_path),
        "images": images,
    }, indent=2))


if __name__ == "__main__":
    main()
