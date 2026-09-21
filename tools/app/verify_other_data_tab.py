"""Capture and verify PolView Other Data using synthetic results, with no live queries."""

import argparse
import json
import os
import sys
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="suiteview-other-data-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        import pandas as pd
        from PyQt6.QtCore import QCoreApplication, QEvent
        from PyQt6.QtWidgets import QApplication, QPushButton
        from suiteview.polview.ui.main_window import GetPolicyWindow
        from suiteview.polview.ui.tabs import (
            claims_tab, cyberlife_pdf_tab, orion_pcr_tab, sap_tab, tai_fd_tab,
        )

        app = QApplication.instance() or QApplication([])
        with ExitStack() as patches:
            for module in (cyberlife_pdf_tab, orion_pcr_tab, tai_fd_tab):
                patches.enter_context(patch.object(module, "_ul_rates_available", return_value=True))
            patches.enter_context(patch.object(sap_tab, "_vrd_prod_available", return_value=True))
            claims = patches.enter_context(patch.object(
                claims_tab.ClaimsTab, "_read_claims_file",
                return_value=pd.DataFrame({
                    "Policy_Number": ["SYNTHETIC"], "Claim_number": ["DEMO-001"],
                    "Date_of_notification": ["09/18/2026"], "Insured_name": ["Synthetic example"],
                }),
            ))
            pdf = patches.enter_context(patch.object(
                cyberlife_pdf_tab.CyberlifePdfTab, "_run_query",
                return_value=pd.DataFrame({
                    "FieldName": ["UserID", "Example field", "Another field"],
                    "DEMOBASE": ["TEST", "100", "Base example"],
                    "DEMORIDER": ["TEST", "50", "Rider example"],
                }),
            ))
            prompted = [
                patches.enter_context(patch.object(cls, "_run_query", return_value=pd.DataFrame()))
                for cls in (sap_tab.SapTab, tai_fd_tab.TaiFdTab, orion_pcr_tab.OrionPcrTab)
            ]
            window = GetPolicyWindow(enable_policy_list=False)
            policy = SimpleNamespace(
                exists=True, policy_number="SYNTHETIC", company_code="01",
                valuation_date=date(2026, 9, 18),
                get_coverages=lambda: [
                    SimpleNamespace(plancode="DEMOBASE"), SimpleNamespace(plancode="DEMORIDER"),
                ],
            )
            window._policy = policy
            window._reset_aux_tabs()
            window.lookup_bar.set_policy_display("01", "SYNTHETIC", "CKPR")
            window._show_status("SYNTHETIC UI VERIFICATION - no live data queried")
            window.resize(1200, 780)
            window.show()
            window.tabs.setCurrentWidget(window.other_data_tab)
            app.processEvents()
            tab = window.other_data_tab
            count = window.tabs.count()
            checks = {}
            screenshots = []
            for title, button in tab.buttons.items():
                button.click()
                app.processEvents()
                page = tab.pages[title]
                checks[f"{title}_embedded"] = (
                    window.tabs.currentWidget() is tab
                    and tab.stack.currentWidget() is page
                    and page.isVisible() and not page.isWindow()
                    and window.tabs.count() == count
                )
                checks[f"{title}_button_fits"] = (
                    button.contentsRect().width() >= button.fontMetrics().horizontalAdvance(title) + 12
                )
                if title in ("SAP", "TAICyberTAIFd", "orion_pcr3_r"):
                    checks[f"{title}_inputs_visible"] = (
                        page.date_from.isVisible() and page.date_to.isVisible()
                    )
                screenshot = args.output_dir / f"other-data-{title}.png"
                if not window.grab().save(str(screenshot), "PNG"):
                    raise RuntimeError(f"Cannot save screenshot: {screenshot}")
                screenshots.append(str(screenshot))
            checks["immediate_queries"] = claims.call_count == pdf.call_count == 1
            checks["prompted_queries_not_run"] = all(mock.call_count == 0 for mock in prompted)
            checks["removed_from_policy_support"] = not set(tab.pages).intersection(
                button.text() for button in window.policy_support_tab.findChildren(QPushButton)
            )
            report = {"all_ok": all(checks.values()), "synthetic_ui_only": True,
                      "checks": checks, "screenshots": screenshots}
            (args.output_dir / "other-data-verification.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8",
            )
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    print(json.dumps(report))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
