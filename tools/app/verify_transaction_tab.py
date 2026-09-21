"""Verify stacked transaction criteria, SQL and saved-query wiring without live data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication, QLabel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    with (
        TemporaryDirectory(prefix="suiteview_transactions_") as profile,
        patch.dict(os.environ, {"SUITEVIEW_PROFILE_DIR": str(Path(profile).resolve())}),
        patch("pyodbc.connect", side_effect=AssertionError("No live database access")),
    ):
        from suiteview.audit.audit_window import AuditWindow
        from suiteview.data import database

        with (
            patch("suiteview.audit.audit_window.load_ui_settings", return_value={}),
            patch("suiteview.audit.audit_window.save_ui_settings"),
        ):
            window = AuditWindow()
            window.resize(1115, 720)
            window.tabs.setCurrentWidget(window.transaction_tab)
            window.show()
            app.processEvents()
            tab = window.transaction_tab
            first, second = tab.transaction1, tab.transaction2
            checks = {
                "native_platform": app.platformName() == "windows",
                "fits_requested_window": window.width() == 1115 and window.height() == 720,
                "empty_ignored": "FH_FIXED TR" not in window._build_sql(),
                "stacked": first.geometry().bottom() < second.y(),
                "both_fit": second.geometry().bottom() < tab.height(),
            }
            for number, panel in enumerate((first, second), 1):
                row_names = ("entry", "eff", "eff_month", "eff_day", "gross")
                inputs = [panel.ranges[name][0] for name in row_names]
                checks[f"section{number}_aligned_rows"] = (
                    len({edit.x() for edit in inputs}) == 1
                    and all(lower.y() - upper.y() == 24
                            for upper, lower in zip(inputs, inputs[1:]))
                )
                checks[f"section{number}_compact_month_day"] = all(
                    lo.width() == hi.width() == 40
                    and lo.y() == hi.y()
                    and checkbox.geometry().center().y() == hi.geometry().center().y()
                    and checkbox.x() == hi.x() + hi.width() + 6
                    for name, checkbox in (
                        ("eff_month", panel.chk_eff_month), ("eff_day", panel.chk_eff_day),
                    )
                    for lo, hi in (panel.ranges[name],)
                )
                checks[f"section{number}_details_beside_reversals"] = (
                    panel.txt_origin.y() == panel.txt_fund_id.y()
                    > panel.ranges["gross"][0].geometry().bottom()
                    and all(
                        choices.geometry().right() < panel.txt_origin.x()
                        and checkbox.y() <= panel.txt_origin.y() <= choices.geometry().bottom()
                        for checkbox, choices in panel.reversal_filters.values()
                    )
                )
                checks[f"section{number}_text_fits"] = all(
                    label.fontMetrics().horizontalAdvance(label.text()) <= label.width()
                    for label in panel.findChildren(QLabel)
                ) and all(
                    check.width() >= check.sizeHint().width()
                    for check in (panel.chk_eff_month, panel.chk_eff_day)
                )
                checks[f"section{number}_inputs_fit"] = all(
                    panel.rect().contains(edit.geometry())
                    for pair in panel.ranges.values() for edit in pair
                ) and panel.rect().contains(panel.txt_fund_id.geometry())
                checks[f"section{number}_flags_fit"] = all(
                    panel.rect().contains(choices.geometry())
                    and choices.verticalScrollBar().maximum() == 0
                    and checkbox.width() >= checkbox.sizeHint().width()
                    for checkbox, choices in panel.reversal_filters.values()
                )
            checks["date_comparisons_only_on_second"] = (
                not first.date_comparisons and set(second.date_comparisons) == {"entry", "eff"}
            )
            checks["date_comparisons_fit"] = all(
                combo.y() == second.ranges[name][1].y()
                and combo.height() == second.ranges[name][1].height()
                and combo.x() == second.ranges[name][1].geometry().right() + 7
                and second.rect().contains(combo.geometry())
                and max(combo.fontMetrics().horizontalAdvance(combo.itemText(i))
                        for i in range(combo.count())) + 30 <= combo.width()
                for name, combo in second.date_comparisons.items()
            )
            first.chk_exclude.setChecked(True)
            second.chk_exclude.setChecked(True)
            checks["exclude_only_ignored"] = "FH_FIXED TR" not in window._build_sql()
            first.chk_exclude.setChecked(False)
            first.transaction_types.setText("PR, PI")
            first.ranges["entry"][0].setText("01/01/2026")
            first.ranges["entry"][1].setText("09/18/2026")
            first.ranges["gross"][0].setText("100")
            second.transaction_types.setText("CD")
            second.chk_eff_month.setChecked(True)
            second.chk_eff_day.setChecked(True)
            second.txt_fund_id.setText("F1, F2")
            reversal_check, reversal_list = first.reversal_filters["is_reversal"]
            reversal_check.setChecked(True)
            reversal_list.item(0).setSelected(True)
            reversed_check, reversed_list = second.reversal_filters["reversed"]
            reversed_check.setChecked(True)
            reversed_list.item(1).setSelected(True)
            sql = window._build_sql()
            checks["both_required"] = all(
                f"EXISTS (SELECT 1 FROM DB2TAB.FH_FIXED TR{number}" in sql for number in (1, 2)
            )
            checks["exclude_and_flags_sql"] = (
                "NOT EXISTS (SELECT 1 FROM DB2TAB.FH_FIXED TR2" in sql
                and "TR1.FCB0_REV_IND IN ('0')" in sql
                and "TR2.FCB2_REV_APPL_IND IN ('1')" in sql
            )
            saved = json.loads(json.dumps(window._cyberlife_query_object_state()))
            first.set_state({})
            checks["second_alone"] = (
                "FH_FIXED TR1" not in window._build_sql()
                and "FH_FIXED TR2" in window._build_sql()
            )
            window._on_clear_cyberlife()
            checks["new_clears_both"] = "FH_FIXED TR" not in window._build_sql()
            for key, criteria_tab in window._cyberlife_criteria_tabs():
                criteria_tab.set_state(saved["tabs"].get(key, {}))
            checks["saved_query_round_trip"] = window._build_sql() == sql
            second.chk_exclude.setChecked(False)
            second.date_comparisons["entry"].setCurrentText("After Trans1 Eff Date")
            second.date_comparisons["eff"].setCurrentText("Equal Trans1 Entry Date")
            linked_sql = window._build_sql()
            checks["linked_dates_sql"] = (
                "TR2.ENTRY_DT > TR1.ASOF_DT" in linked_sql
                and "TR2.ASOF_DT = TR1.ENTRY_DT" in linked_sql
                and linked_sql.count("FROM DB2TAB.FH_FIXED TR1") == 1
                and linked_sql.count("FROM DB2TAB.FH_FIXED TR2") == 1
            )
            linked_saved = json.loads(json.dumps(window._cyberlife_query_object_state()))
            first.chk_exclude.setChecked(True)
            checks["excluded_reference_disables_comparisons"] = all(
                not combo.isEnabled() and combo.currentText() == "none"
                for combo in second.date_comparisons.values()
            )
            window._on_clear_cyberlife()
            checks["new_clears_comparisons"] = all(
                combo.isEnabled() and combo.currentText() == "none"
                for combo in second.date_comparisons.values()
            ) and "FH_FIXED TR" not in window._build_sql()
            for key, criteria_tab in window._cyberlife_criteria_tabs():
                criteria_tab.set_state(linked_saved["tabs"].get(key, {}))
            checks["linked_saved_query_round_trip"] = (
                window._build_sql() == linked_sql
                and window._cyberlife_query_object_state() == linked_saved
            )
            window.tabs.setCurrentWidget(tab)
            app.processEvents()
            checks["transaction_tab_visible"] = tab.isVisible()
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.screenshot), "PNG"):
                raise RuntimeError(f"Could not save screenshot: {args.screenshot}")
            window.close()
            window.deleteLater()
            app.processEvents()
            if database._db_instance is not None:
                database._db_instance.close()
    print(json.dumps({"all_ok": all(checks.values()), "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
