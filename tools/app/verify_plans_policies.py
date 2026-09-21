"""Verify Plans and Policies clipboard, persistence and native layout without DB access."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QMimeData, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QCheckBox


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    clipboard = app.clipboard()
    saved_clipboard = QMimeData()
    original = clipboard.mimeData()
    if original is not None:
        for fmt in original.formats():
            saved_clipboard.setData(fmt, original.data(fmt))
    checks = {}
    try:
        with (
            TemporaryDirectory(prefix="suiteview_plans_policies_") as profile,
            patch.dict(os.environ, {"SUITEVIEW_PROFILE_DIR": str(Path(profile).resolve())}),
            patch("pyodbc.connect", side_effect=AssertionError("Live DB access forbidden")),
        ):
            from suiteview.audit.audit_window import AuditWindow
            from suiteview.data import database

            with (
                patch("suiteview.audit.audit_window.load_ui_settings", return_value={}),
                patch("suiteview.audit.audit_window.save_ui_settings"),
            ):
                window = AuditWindow()
                window.resize(1215, 720)
                tab = window.plancode_tab
                window.tabs.setCurrentWidget(tab)
                window.show()
                app.processEvents()
                checks["native_platform"] = app.platformName() == "windows"
                checks["tab_renamed"] = (
                    window.tabs.tabText(window.tabs.indexOf(tab)) == "Plans and Policies"
                )
                for name, panel in (("plans", tab.plancodes), ("policies", tab.policies)):
                    panel.input.setText("single001")
                    QTest.keyClick(panel.input, Qt.Key.Key_Return)
                    checks[f"{name}_enter_adds"] = panel.values() == ["SINGLE001"]
                    panel.list_values.item(0).setSelected(True)
                    panel.btn_remove_selected.click()
                    checks[f"{name}_remove_selected"] = not panel.values()
                    panel.input.setText("delete")
                    panel.btn_add.click()
                    panel.btn_remove_all.click()
                    checks[f"{name}_remove_all"] = not panel.values()

                clipboard.setText("plan0001\r\nplan0002\tPLAN0001")
                tab.plancodes.btn_paste.click()
                clipboard.setText("000289393\r\nu0123456\tu0765432, U0123456; u0100000 u0200000")
                tab.policies.btn_paste.click()
                checks["clipboard_normalized"] = (
                    tab.get_plancodes() == ["PLAN0001", "PLAN0002"]
                    and tab.get_policies()
                    == ["000289393", "U0123456", "U0765432", "U0100000", "U0200000"]
                )
                checks["only_plans_have_cov1"] = not tab.policies.findChildren(QCheckBox)
                sql = window._build_sql()
                checks["exact_policy_sql"] = (
                    "POLICY1.CK_POLICY_NBR IN ('000289393', 'U0123456', 'U0765432', "
                    "'U0100000', 'U0200000')" in sql
                )
                checks["plans_and_policies"] = (
                    "COVSALL.PLN_DES_SER_CD IN ('PLAN0001', 'PLAN0002')" in sql
                    and "\n  AND POLICY1.CK_POLICY_NBR IN (" in sql
                )
                tab.chk_cov1_plancode_match_only.setChecked(True)
                sql = window._build_sql()
                saved = json.loads(json.dumps(window._cyberlife_query_object_state()))
                tab.policies.input.setText("draft")
                window._on_clear_cyberlife()
                checks["new_clears_lists_and_drafts"] = (
                    not tab.get_policies() and not tab.get_plancodes()
                    and not tab.policies.input.text()
                    and not tab.chk_cov1_plancode_match_only.isChecked()
                    and "POLICY1.CK_POLICY_NBR IN (" not in window._build_sql()
                )
                for key, criteria_tab in window._cyberlife_criteria_tabs():
                    criteria_tab.set_state(saved["tabs"].get(key, {}))
                checks["saved_query_round_trip"] = sql == window._build_sql()
                window.tabs.setCurrentWidget(tab)
                app.processEvents()
                checks["side_by_side"] = (
                    tab.plancodes.geometry().right() < tab.policies.x()
                    and tab.plancodes.y() == tab.policies.y()
                )
                checks["panels_fit"] = all(
                    tab.rect().contains(panel.geometry())
                    and panel.list_values.width() >= 120
                    for panel in (tab.plancodes, tab.policies)
                )
                checks["button_rows_aligned"] = all(
                    getattr(tab.plancodes, name).mapTo(tab, getattr(tab.plancodes, name).rect().topLeft()).y()
                    == getattr(tab.policies, name).mapTo(tab, getattr(tab.policies, name).rect().topLeft()).y()
                    for name in ("btn_add", "btn_remove_selected", "btn_remove_all", "btn_paste")
                )
                checks["input_text_fits"] = all(
                    panel.input.fontMetrics().horizontalAdvance("000289393") + 10 <= panel.input.width()
                    for panel in (tab.plancodes, tab.policies)
                )
                checks["all_tabs_fit"] = window.tabs.tabBar().tabRect(
                    window.tabs.count() - 1
                ).right() < window.tabs.tabBar().width()
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(args.screenshot), "PNG"):
                    raise RuntimeError(f"Could not save screenshot: {args.screenshot}")
                window.close()
                window.deleteLater()
                app.processEvents()
                if database._db_instance is not None:
                    database._db_instance.close()
    finally:
        clipboard.setMimeData(saved_clipboard)
    print(json.dumps({
        "all_ok": all(checks.values()), "checks": checks, "live_data_accessed": False,
    }, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
