"""Capture the real RERUN mode/editor UI using a synthetic policy, with no DB access."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.models.policy_data import (
    BenefitInfo, CoverageSegment, IllustrationPolicyData, RiderInfo,
)
from suiteview.illustration.ui.main_window import IllustrationWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    issue = date(2010, 5, 15)
    policy = IllustrationPolicyData(
        policy_number="DEMO-ISSUE", company_code="01", plancode="1U135D00",
        insured_name="Synthetic Example", product_type="UL", issue_date=issue,
        issue_age=40, attained_age=56, rate_sex="M", rate_class="N",
        valuation_date=date(2026, 9, 15), illustration_date=date.today(),
        duration=197, policy_year=17, policy_month=5, face_amount=150_000,
        account_value=25_000, regular_loan_principal=5_000,
        modal_premium=150, annual_premium=1800, current_interest_rate=0.0475,
        segments=[
            CoverageSegment(issue_date=issue, issue_age=40, face_amount=100_000,
                            original_face_amount=100_000, units=100),
            CoverageSegment(coverage_phase=2, issue_date=date(2015, 5, 15),
                            issue_age=45, face_amount=50_000, units=50, is_cola=True),
        ],
        riders=[
            RiderInfo(coverage_phase=3, plancode="EXAMPLE-TERM",
                      description="Original Term Rider", issue_date=issue,
                      issue_age=40, face_amount=25_000, units=25),
            RiderInfo(coverage_phase=4, plancode="EXAMPLE-LATER",
                      description="Later Rider", issue_date=date(2015, 5, 15),
                      issue_age=45, face_amount=10_000, units=10),
        ],
        benefits=[BenefitInfo(
            coverage_phase=1, form_number="Waiver of Monthly Deduction",
            benefit_type="W", benefit_subtype="1", issue_date=issue,
            issue_age=40, benefit_amount=100_000)],
    )
    window = IllustrationWindow()
    window.lookup_bar.set_policy_display("01", policy.policy_number, "CKPR")
    window.policy_tab.load_data_from_snapshot(policy)
    tab = window.inputs_tab
    tab.load_data_from_policy(policy)
    window._set_active_inputs_tab(tab)
    window.tabs.setCurrentWidget(window._inputs_stack)
    window.resize(1200, 825)
    window.show()
    app.processEvents()
    paths = []
    for mode, filename in ((False, "rerun-inforce.png"), (True, "rerun-from-issue.png")):
        tab.run_from_issue_btn.setChecked(mode)
        if mode:
            tab.issue_conditions.dbo_combo.setCurrentIndex(1)
            tab.issue_conditions.face_edit.setValue(85_000)
            tab.issue_conditions.no_lapse_years_edit.setValue(7.5)
            tab.issue_conditions._rider_checks[3].setChecked(False)
            tab.input_tabs.setCurrentWidget(tab.issue_conditions)
        app.processEvents()
        path = args.output_dir / filename
        if not window.grab().save(str(path), "PNG"):
            raise RuntimeError(f"Could not save UI capture: {path}")
        paths.append(str(path))
    checks = {
        "issue_selected": tab.run_from_issue_enabled(),
        "blue_header": window._header_colors[0] == "#123C56",
        "notice": "NEW BUSINESS" in window.projection_mode_notice.text(),
        "original_face_default_editable": tab.export_issue_overrides().face_amount == 85_000,
        "dbo_editable": tab.export_issue_overrides().db_option == "B",
        "no_lapse_period_editable": tab.export_issue_overrides().no_lapse_years == 7.5,
        "rider_removed": tab.export_issue_overrides().excluded_rider_phases == [3],
        "later_rider_excluded": not tab.issue_conditions._rider_checks[4].isEnabled(),
        "source_unchanged": policy.face_amount == 150_000 and policy.account_value == 25_000,
    }
    tab.run_from_issue_btn.setChecked(False)
    checks["returns_to_inforce"] = "INFORCE" in window.projection_mode_notice.text()
    window.close()
    print(json.dumps({"all_ok": all(checks.values()), "checks": checks, "screenshots": paths}))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
