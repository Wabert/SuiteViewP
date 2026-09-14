"""Verify native Reinstatement routing and capture a synthetic or live read-only quote."""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication

from suiteview.core.policy_service import get_policy_info
from suiteview.polview.ui.main_window import GetPolicyWindow
from suiteview.polview.ui.tabs import reinstatement_tab


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--policy", help="Omit for a synthetic UI-only demonstration.")
    parser.add_argument("--company", default="01")
    parser.add_argument("--region", default="CKPR")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    with ExitStack() as patches:
        if args.policy:
            policy = get_policy_info(
                args.policy, company_code=args.company, region=args.region, use_cache=False,
            )
            if policy is None or not policy.exists:
                raise RuntimeError("Live policy was not found.")
        else:
            policy = SimpleNamespace(
                exists=True, product_type="UL", policy_number="SYNTHETIC-QUOTE",
                company_code="01", region="CKPR",
            )
            summary = SimpleNamespace(
                last_entry_code="Q", last_entry_description="Termination - Lapse",
                termination_date=date(2024, 7, 15), current_date=date(2026, 9, 14),
                terminated_years=2, terminated_months=1,
                eligible=True, message="Synthetic example",
                quote_pay_to_date=date(2026, 8, 15),
                next_monthliversary=date(2026, 9, 15),
            )
            result = SimpleNamespace(
                summary=summary, premium=725.01, basis="Surrender value",
                breakdown=[
                    ("Starting account value", "-100.00"),
                    ("Net premium", "700.01"),
                    ("Interest before next deduction", "0.00"),
                    ("Total monthly deductions", "350.00"),
                    ("Next monthliversary debt", "200.00"),
                    ("Next surrender charge", "50.00"),
                    ("After-deduction surrender value", "0.01"),
                    ("Premium loads", "25.00"),
                    ("Required gross premium", "725.01"),
                ],
                explanation=(
                    "SYNTHETIC UI EXAMPLE - not a policy quote.\n"
                    "Starting AV + net premium + interest - deductions - debt - surrender "
                    "charge = $0.01 after the next monthly deduction. "
                    "Gross premium includes premium loads."
                ),
            )
            patches.enter_context(patch.object(
                reinstatement_tab, "reinstatement_summary", return_value=summary,
            ))
            patches.enter_context(patch.object(
                reinstatement_tab, "calculate_home_office_reinstatement", return_value=result,
            ))
        window = GetPolicyWindow(enable_policy_list=False)
        window._policy = policy
        window.lookup_bar.set_policy_display(
            policy.company_code, policy.policy_number, args.region,
        )
        window.resize(1200, 780)
        window.show()
        window.policy_support_tab._btn_reinstatement.click()
        app.processEvents()
        tab = window.reinstatement_tab
        if tab is None:
            raise RuntimeError("No Reinstatement tab was created.")
        checks = {
            "tab_selected": window.tabs.currentWidget() is tab,
            "tab_title": window.tabs.tabText(window.tabs.indexOf(tab)) == "Reinstatement",
            "quote_present": tab._result is not None,
            "both_sections_visible": tab.home_group.isVisible() and tab.skipped_group.isVisible(),
            "skipped_rules_not_invented": "not been specified" in tab.skipped_note.text(),
            "summary_present": bool(tab.summary_group.entry.text()),
            "breakdown_present": tab.home_group.table.rowCount() > 0,
        }
        screenshot = args.output_dir / "polview-reinstatement.png"
        if not window.grab().save(str(screenshot), "PNG"):
            raise RuntimeError(f"Unable to save native screenshot: {screenshot}")
        report = {
            "all_ok": all(checks.values()),
            "synthetic_ui_only": not bool(args.policy),
            "checks": checks,
            "premium": tab.home_group.premium.text(),
            "status": tab.status_label.text(),
            "screenshot": str(screenshot),
        }
        report_path = args.output_dir / "reinstatement-verification.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        window.close()
    print(json.dumps(report))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
