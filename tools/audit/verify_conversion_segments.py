"""Verify the Cyberlife segment pages without querying DB2 or saving preferences.

Usage: venv\\Scripts\\python.exe tools\\audit\\verify_conversion_segments.py [--screenshots DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication

from suiteview.audit.audit_window import AuditWindow
from suiteview.audit.segment52_fields import SEGMENT52_FIELDS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--verify-live", action="store_true")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    with (
        patch("suiteview.audit.audit_window.load_ui_settings", return_value={}),
        patch("suiteview.audit.audit_window.save_ui_settings"),
    ):
        win = AuditWindow()
        win.show()
        win.tabs.setCurrentWidget(win.segment52_tab)
        app.processEvents()
        checks = {
            "page_registered": win.tabs.tabText(
                win.tabs.indexOf(win.segment52_tab)) == "52 Segment",
            "state_registered": "segment52" in dict(win._cyberlife_criteria_tabs()),
        }
        win.segment52_tab.ranges["APP_RECEIVED_DATE"][0].setText("1/1/2026")
        win.segment52_tab.text_inputs["SOURCE_PLAN_CODE"].setText("testplan")
        win.segment52_tab._display_all()
        win.display_tab.chk_conversion_dates.setChecked(True)
        win.display_tab.chk_post_conversion.setChecked(True)
        conversion_queries = {}
        for display, has_converted in (
            (False, False), (True, False), (False, True), (True, True),
        ):
            win.display_tab.chk_converted_pol.setChecked(display)
            win.policy2_tab.chk_has_converted.setChecked(has_converted)
            query = win._build_sql()
            name = f"source_company_display_{display}_filter_{has_converted}"
            expected = display or has_converted
            conversion_queries[name] = (query, expected)
            checks[name] = query.count(
                ", USERGEN.SOURCE_CMP_CODE SOURCE_CMP_CODE"
            ) == int(expected)
        sql = win._build_sql()
        checks["all_fields_wired"] = all(
            f"USERGEN.{field.name} {field.name}" in sql for field in SEGMENT52_FIELDS
        )
        checks["criteria_wired"] = (
            "USERGEN.APP_RECEIVED_DATE >= '2026-01-01'" in sql
            and "UPPER(TRIM(USERGEN.SOURCE_PLAN_CODE)) = 'TESTPLAN'" in sql
        )
        checks["conversion_display_wired"] = "CONVERSION_SC" in sql
        checkbox = win.display_tab.chk_post_conversion
        win.tabs.setCurrentWidget(win.display_tab)
        app.processEvents()
        checks["post_conversion_visible_and_fits"] = (
            checkbox.isVisible()
            and checkbox.width() >= checkbox.sizeHint().width()
            and win.display_tab.rect().contains(checkbox.geometry())
        )
        checks["post_conversion_wired"] = "LEFT OUTER JOIN POST_CONVERSION PC" in sql
        if args.verify_live:
            from suiteview.core.db2_connection import DB2Connection

            if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
                raise RuntimeError("Live verification requires SUITEVIEW_LOCAL_DATA disabled.")
            db = DB2Connection(win.cmb_region.currentText())
            try:
                # Compile the exact generated query without reading policy rows.
                assert "\nWHERE " in sql
                columns, rows = db.execute_query_with_headers(
                    sql.replace("\nWHERE ", "\nWHERE 1 = 0 AND ", 1))
                checks["live_sql_compiles"] = not rows
                checks["live_result_columns"] = (
                    {field.name for field in SEGMENT52_FIELDS}
                    | {"CONV_SC_ENTRY_DT", "CONV_SC_EFFECTIVE_DT",
                       "POST_CONV_POLICY", "POST_CONV_COMPANY"}
                ).issubset(columns)
                for name, (query, expected) in conversion_queries.items():
                    columns, rows = db.execute_query_with_headers(
                        query.replace("\nWHERE ", "\nWHERE 1 = 0 AND ", 1))
                    checks[f"live_{name}"] = (
                        not rows and columns.count("SOURCE_CMP_CODE") == int(expected)
                    )
            finally:
                db.close()
        saved = json.loads(json.dumps(win._cyberlife_query_object_state()))
        if args.screenshots:
            args.screenshots.mkdir(parents=True, exist_ok=True)
            for title, widget in (
                ("segment52", win.segment52_tab), ("conversion_display", win.display_tab),
            ):
                win.tabs.setCurrentWidget(widget)
                app.processEvents()
                target = args.screenshots / f"{title}.png"
                if not win.grab().save(str(target), "PNG"):
                    raise RuntimeError(f"Could not save screenshot: {target}")
        win._on_clear_cyberlife()
        cleared = win._build_sql()
        checks["clear_resets_new_controls"] = (
            "USERGEN.APP_RECEIVED_DATE" not in cleared
            and "CONVERSION_SC" not in cleared
            and "USERGEN.SOURCE_CMP_CODE" not in cleared
            and "POST_CONVERSION" not in cleared
        )
        for key, tab in win._cyberlife_criteria_tabs():
            tab.set_state(saved["tabs"].get(key, {}))
        checks["state_roundtrip"] = win._build_sql() == sql
        win.close()
        app.processEvents()
    print(json.dumps({"checks": checks, "all_ok": all(checks.values())}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
