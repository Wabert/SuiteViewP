"""Verify the native Reinstatement tab and capture a synthetic or live read-only quote.

Without ``--policy`` the tab prices an explicitly synthetic lapsed policy through
the real quote service (no database access). With ``--policy`` it loads a live
lapsed UL read-only. Synthetic captures are not evidence of a live policy quote.
"""
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

from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.polview.services import reinstatement
from suiteview.polview.services.policy_service import get_policy_info
from suiteview.polview.ui.main_window import GetPolicyWindow
from suiteview.polview.ui.tabs import reinstatement_tab

SYNTHETIC_TODAY = date(2026, 10, 7)


def synthetic_basis(today: date = SYNTHETIC_TODAY) -> reinstatement.ReinstatementBasis:
    years = 40
    policy = IllustrationPolicyData(
        policy_number="SYNTHETIC", plancode="SYNTHETIC", product_type="UL",
        issue_date=date(2015, 3, 15), valuation_date=date(2026, 2, 15),
        issue_age=40, maturity_age=121, face_amount=100000.0, units=100.0,
        account_value=-25.0, premiums_paid_to_date=12000.0, ctp=1200.0,
        map_cease_date=date(2025, 3, 15),
        segments=[CoverageSegment(
            issue_date=date(2015, 3, 15), issue_age=40, face_amount=100000.0,
            original_face_amount=100000.0, units=100.0, rate_sex="M", rate_class="N")],
    )
    rates = IllustrationRates(
        segment_coi={1: [None] + [0.12] * years},
        segment_epu={1: [None] + [0.05] * years},
        segment_scr={1: [None] + [10.0 - 0.5 * year for year in range(years)]},
        mfee=[None] + [7.5] * years,
        tpp=[None] + [0.05] * years,
        epp=[None] + [0.05] * years,
    )
    eligibility = reinstatement.ReinstatementEligibility(
        "Q", "Termination - Lapse", True, "Synthetic example")
    return reinstatement.build_reinstatement_basis(
        policy, PlancodeConfig(plancode="SYNTHETIC"), rates, eligibility=eligibility,
        lapse_date=date(2026, 3, 15), today=today,
        notes=("SYNTHETIC UI EXAMPLE - not a policy quote.",), reinstatement_code="1",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--policy", help="Omit for a synthetic demonstration.")
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
                exists=True, product_type="UL", last_entry_code="Q",
                policy_number="SYNTHETIC", company_code="01", region="CKPR",
            )
            patches.enter_context(patch.object(
                reinstatement_tab, "load_reinstatement_basis",
                side_effect=lambda *_a, **_k: synthetic_basis(),
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
            "lapse_values_present": bool(tab.lapse_panel.text("lapse_date")),
            "quote_present": tab._quote is not None,
            "premium_present": tab.premium_label.text().startswith("$"),
        }
        screenshot = args.output_dir / "polview-reinstatement.png"
        if not window.grab().save(str(screenshot), "PNG"):
            raise RuntimeError(f"Unable to save native screenshot: {screenshot}")
        report = {
            "all_ok": all(checks.values()),
            "synthetic_ui_only": not bool(args.policy),
            "checks": checks,
            "reinstatement_date": str(tab.selected_date()),
            "premium": tab.premium_label.text(),
            "status": tab.status_label.text(),
            "quote_text": tab.copy_text(),
            "screenshot": str(screenshot),
        }
        report_path = args.output_dir / "reinstatement-verification.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        window.close()
    print(json.dumps(report, indent=2))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
