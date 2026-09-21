"""Verify Policy identifier layout and query persistence without live DB access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication
from suiteview.audit.audit_window import AuditWindow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication(sys.argv)
    with (
        patch("suiteview.audit.audit_window.load_ui_settings", return_value={}),
        patch("suiteview.audit.audit_window.save_ui_settings"),
    ):
        window = AuditWindow()
        window.resize(1215, 720)
        window.tabs.setCurrentWidget(window.policy_tab)
        window.show()
        app.processEvents()
        tab = window.policy_tab
        checks = {}
        tab.txt_plancode.setText("u1f4")
        checks["exact_sql"] = "COVSALL.PLN_DES_SER_CD = 'U1F4'" in window._build_sql()
        tab.chk_rga.setChecked(True)
        sql = window._build_sql()
        saved = json.loads(json.dumps(window._cyberlife_query_object_state()))
        controls = [
            tab.txt_plancode, tab.cmb_company, tab.cmb_market,
            tab.txt_form_number, tab.txt_branch, tab.cmb_polnum_criteria,
        ]
        checks["aligned_controls"] = len({widget.x() for widget in controls}) == 1
        checks["compact_rows"] = all(
            b.y() - a.y() == 24 for a, b in zip(controls, controls[1:])
        )
        checks["match_text_fits"] = all(
            combo.fontMetrics().horizontalAdvance(combo.itemText(i)) + 24 <= combo.width()
            for combo in (tab.cmb_polnum_criteria,)
            for i in range(combo.count())
        )
        checks["left_column_not_widened"] = (
            tab.cmb_company.geometry().right() <= tab.txt_issue_age_hi.geometry().right()
        )
        checks["rga_beside_plancode"] = (
            tab.chk_rga.x() > tab.txt_plancode.geometry().right()
            and tab.chk_rga.geometry().center().y()
            == tab.txt_plancode.geometry().center().y()
        )
        window._on_clear_cyberlife()
        checks["new_resets"] = (
            not tab.txt_plancode.text()
            and not tab.chk_rga.isChecked()
            and "LH_COV_PHA COVSALL" not in window._build_sql()
        )
        for key, criteria_tab in window._cyberlife_criteria_tabs():
            criteria_tab.set_state(saved["tabs"].get(key, {}))
        checks["saved_query_round_trip"] = window._build_sql() == sql
        app.processEvents()
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.screenshot), "PNG"):
            raise RuntimeError(f"Could not save screenshot: {args.screenshot}")
        window.close()
        app.processEvents()
    print(json.dumps({"all_ok": all(checks.values()), "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
