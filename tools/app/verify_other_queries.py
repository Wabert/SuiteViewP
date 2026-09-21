"""Verify Other Queries integration with synthetic async results, never live DB access."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
from PyQt6.QtCore import QElapsedTimer, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QLineEdit, QMessageBox


def _wait(panel):
    timer = QElapsedTimer()
    timer.start()
    while panel._active_query_worker is not None and timer.elapsed() < 5000:
        QTest.qWait(10)
    if panel._active_query_worker is not None:
        raise RuntimeError("Synthetic lookup did not finish within five seconds.")


def _synthetic_result(query, region):
    if query.columns[0] == "Field Value":
        rows = [("0", 820), ("1", 146), (None, 3)]
    elif query.columns[0] == "Base Plancode":
        rows = [
            ("BASE0001", "BF100", "RIDER001", "RF100", 120),
            ("BASE0001", "BF100", "RIDER002", "RF200", 45),
        ]
    else:
        rows = [
            ("RIDER001", "RF100", "BASE0001", "BF100", 120),
            ("RIDER001", "RF100", "BASE0002", "BF200", 72),
        ]
    if "Policy Number" in query.columns:
        rows = [(*row[:4], f"0000000{i + 1}", "01") for i, row in enumerate(rows)]
    return pd.DataFrame(rows, columns=query.columns)


def _text_pixels(view, index):
    image = view.viewport().grab(view.visualRect(index).adjusted(2, 2, -2, -2)).toImage()
    return {
        (x, y) for x in range(image.width()) for y in range(image.height())
        if max(image.pixelColor(x, y).getRgb()[:3]) < 128
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    checks = {}
    with (
        TemporaryDirectory(prefix="suiteview_other_queries_") as profile,
        patch.dict(os.environ, {"SUITEVIEW_PROFILE_DIR": str(Path(profile).resolve())}),
        patch("pyodbc.connect", side_effect=AssertionError("Live database access forbidden")),
    ):
        from suiteview.audit.audit_window import AuditWindow
        from suiteview.data import database

        with (
            patch("suiteview.audit.audit_window.load_ui_settings", return_value={}),
            patch("suiteview.audit.audit_window.save_ui_settings"),
            patch("suiteview.audit.tabs.other_queries_tab.execute_other_query",
                  side_effect=_synthetic_result) as execute,
            patch("suiteview.audit.tabs.other_queries_tab.dump_to_new_workbook") as export,
            patch.object(QMessageBox, "warning") as warning,
            patch.object(QMessageBox, "information") as information,
        ):
            window = AuditWindow()
            window.resize(1215, 720)
            tab = window.other_queries_tab
            window.tabs.setCurrentWidget(tab)
            window.show()
            app.processEvents()
            checks["native_platform"] = app.platformName() == "windows"
            names = [window.tabs.tabText(i) for i in range(window.tabs.count())]
            checks["tab_replaced"] = "Common Tables" not in names and "Other Queries" in names
            checks["no_retired_state"] = "common_tables" not in window._cyberlife_query_object_state()
            baseline = window._build_sql()
            tab.panels["riders"].inputs["plancode"].setText("base0001")
            tab.panels["bases"].inputs["plancode"].setText("rider001")
            tab.panels["values"].inputs["table"].setText("lh_bas_pol")
            tab.panels["values"].inputs["field"].setText("non_trd_pol_ind")
            saved = json.loads(json.dumps(window._cyberlife_query_object_state()))
            checks["independent_of_audit"] = baseline == window._build_sql()
            window.btn_run.click()
            checks["footer_explains_find_buttons"] = information.call_count == 1 and execute.call_count == 0
            panel = tab.panels["riders"]
            panel.btn_find.click()
            window.close()
            checks["close_waits_for_worker"] = window.isVisible() and information.call_count == 2
            _wait(panel)
            for kind in ("bases", "values"):
                tab.panels[kind].btn_find.click()
                _wait(tab.panels[kind])
            checks["three_async_queries"] = execute.call_count == 3
            checks["populated_grids"] = all(not p.table.get_filtered_dataframe().empty for p in tab.panels.values())
            for kind, panel in tab.panels.items():
                panel.btn_excel.click()
                checks[f"{kind}_export_rows"] = len(export.call_args.args[1]) == len(panel.table.get_filtered_dataframe())
            checks["exports_unsaved"] = export.call_count == 3
            tab.panels["riders"].btn_sql.click()
            checks["sql_preview"] = (
                window.tabs.currentWidget() is window.sql_tab
                and "B.PLN_DES_SER_CD = 'BASE0001'" in window.sql_tab.txt_sql.toPlainText()
            )
            tab.panels["bases"].show_policies.setChecked(True)
            tab.panels["bases"].btn_find.click()
            _wait(tab.panels["bases"])
            checks["independent_show_policies"] = (
                "Policy Number" in tab.panels["bases"].table.get_filtered_dataframe().columns
                and "Rider Count" in tab.panels["riders"].table.get_filtered_dataframe().columns
            )
            tab.panels["riders"].btn_find.click()
            window.cmb_region.setCurrentText("CKAS")
            _wait(tab.panels["riders"])
            checks["region_change_discards_stale_results"] = all(
                p.table.get_filtered_dataframe().empty for p in tab.panels.values()
            )
            checks["region_schema"] = "UNIT." in tab.panels["riders"].query().sql
            window._on_clear_cyberlife()
            checks["new_clears_inputs_and_results"] = all(
                not any(entry.text() for entry in panel.inputs.values())
                and panel.table.get_filtered_dataframe().empty
                for panel in tab.panels.values()
            )
            window.cmb_region.setCurrentText("CKPR")
            for key, criteria_tab in window._cyberlife_criteria_tabs():
                criteria_tab.set_state(saved["tabs"].get(key, {}))
            checks["saved_query_round_trip"] = window._cyberlife_query_object_state() == saved
            with patch("suiteview.audit.tabs.other_queries_tab.execute_other_query",
                       side_effect=RuntimeError("Synthetic connection error")):
                panel = tab.panels["values"]
                panel.btn_find.click()
                _wait(panel)
                checks["errors_explicit"] = warning.call_count == 1 and "failed" in panel.status.text()
            window.tabs.setCurrentWidget(tab)
            for panel in tab.panels.values():
                panel.btn_find.click()
                _wait(panel)
            app.processEvents()
            checks["fits_window"] = window.size().width() == 1215 and window.size().height() == 720
            for kind, panel in tab.panels.items():
                view = panel.table.table_view
                index = view.model().index(0, 0)
                value = view.model().data(index)
                text_pixels = _text_pixels(view, index)
                position = view.visualRect(index).center()
                QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=position)
                QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=position)
                QTest.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=position)
                QTest.keyClick(view, Qt.Key.Key_F2)
                checks[f"{kind}_clicks_preserve_cells"] = (
                    view.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
                    and view.model().data(index) == value
                    and not any(editor.isVisible() for editor in view.findChildren(QLineEdit))
                )
                selected_pixels = _text_pixels(view, index)
                checks[f"{kind}_selected_text_visible"] = (
                    bool(text_pixels)
                    and len(text_pixels & selected_pixels) >= 0.8 * len(text_pixels)
                )
                checks[f"{kind}_columns_fit"] = view.horizontalScrollBar().maximum() == 0
                checks[f"{kind}_headers_fit"] = all(
                    view.columnWidth(i) >= view.horizontalHeader().fontMetrics().horizontalAdvance(str(col)) + 24
                    for i, col in enumerate(panel.table.get_filtered_dataframe().columns)
                )
                checks[f"{kind}_dense_table"] = (
                    not view.showGrid() and not view.alternatingRowColors()
                    and not view.verticalHeader().isVisible()
                    and view.verticalHeader().defaultSectionSize() == 16
                )
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.screenshot), "PNG"):
                raise RuntimeError(f"Could not save screenshot: {args.screenshot}")
            window.close()
            window.deleteLater()
            app.processEvents()
            if database._db_instance is not None:
                database._db_instance.close()
    print(json.dumps({"all_ok": all(checks.values()), "checks": checks, "live_data_accessed": False}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
