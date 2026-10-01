"""Inspect target-rate NULLs read-only; optionally verify native Run Values.

Usage: venv\\Scripts\\python.exe tools\\engine\\verify_table_target_rates.py 000340565 --native
"""
def _load_policy_data(*args, **kwargs):
    from suiteview.illustration.api import load_policy_data

    return load_policy_data(*args, **kwargs)
import argparse
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("policy")
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()

    from suiteview.illustration.core.ul_rates import ULRates

    policy = _load_policy_data(args.policy)
    with ULRates(policy.company_code) as rates:
        rows = []
        for seg in policy.segments:
            item = {
                "phase": seg.coverage_phase, "table_rating": seg.table_rating,
                "table_cease_date": seg.table_cease_date,
                "age": seg.issue_age, "sex": seg.rate_sex, "class": seg.rate_class,
                "band": seg.band, "original_band": seg.original_band,
            }
            lookup = (policy.plancode, seg.issue_age, seg.rate_sex, seg.rate_class, seg.band)
            for kind, getter in (("MTP", rates.get_mtp), ("CTP", rates.get_ctp),
                                 ("TBL1MTP", rates.get_tbl1_mtp), ("TBL1CTP", rates.get_tbl1_ctp)):
                item[kind] = getter(*lookup, issue_date=seg.issue_date)
            rows.append(item)
        report = {
            "policy": policy.policy_number, "company": policy.company_code,
            "plancode": policy.plancode, "segments": rows,
        }
        if args.native:
            report["native"] = verify_native(policy)
        print(json.dumps(report, default=str, indent=2))


def verify_native(policy):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from suiteview.illustration.ui.main_window import IllustrationWindow

    app = QApplication.instance() or QApplication([])
    messages = []

    def message(_parent, title, text, *args):
        messages.append(f"{title}: {text}")
        return QMessageBox.StandardButton.Ok

    with (
        patch.object(QMessageBox, "information", message),
        patch.object(QMessageBox, "warning", message),
        patch.object(QMessageBox, "critical", message),
    ):
        window = IllustrationWindow()
        try:
            window._on_get_policy(policy.policy_number, policy.region, policy.company_code)
            assert window._policy is not None and window._policy.exists
            window._on_run_values()
            app.processEvents()
            assert not messages, messages
            assert window.values_tab._current_view is not None
            assert window.values_tab._guaranteed_view is not None
            report = window.report_tab.current_report()
            assert report is not None
            states = window.values_tab._current_view[1]
            assert len(states) > 1
            return {
                "current_rows": len(states),
                "guaranteed_rows": len(window.values_tab._guaranteed_view[1]),
                "report_years": len(report.ledger),
                "status": window._status_label.text(),
            }
        finally:
            window.close()
            app.processEvents()


if __name__ == "__main__":
    with TemporaryDirectory(prefix="suiteview-target-rates-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        main()
