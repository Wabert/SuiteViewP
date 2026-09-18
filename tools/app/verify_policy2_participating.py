"""Verify Policy (2)/WL participation UI and saved-query wiring without querying DB2."""

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
    parser.add_argument("--wl-screenshot", type=Path)
    args = parser.parse_args()
    app = QApplication(sys.argv)
    with (
        patch("suiteview.audit.audit_window.load_ui_settings", return_value={}),
        patch("suiteview.audit.audit_window.save_ui_settings"),
    ):
        window = AuditWindow()
        window.resize(1215, 720)
        window.tabs.setCurrentWidget(window.policy2_tab)
        window.show()
        app.processEvents()
        tab = window.policy2_tab
        tab.chk_participating.setChecked(True)
        tab.list_participating.item(0).setSelected(True)
        tab.list_participating.item(1).setSelected(True)
        sql = window._build_sql()
        saved = json.loads(json.dumps(window._cyberlife_query_object_state()))
        checks = {
            "sql_uses_base": "COVERAGE1.DIV_PTP_TYP_CD ParticipationCode" in sql,
            "termination_rows_compact": (
                tab.txt_term_last_fin_date_lo.y() - tab.txt_term_entry_date_lo.y() == 24
                and tab.txt_term_date_both_lo.y() - tab.txt_term_last_fin_date_lo.y() == 24
            ),
            "participation_fits": tab.list_participating.geometry().bottom() < tab.height(),
            "three_rows_visible": tab.list_participating.verticalScrollBar().maximum() == 0,
        }
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.screenshot), "PNG"):
            raise RuntimeError(f"Could not save screenshot: {args.screenshot}")
        window._on_clear_cyberlife()
        checks["new_clears"] = (
            not tab.chk_participating.isChecked()
            and not tab.list_participating.selectedItems()
            and "DIV_PTP_TYP_CD" not in window._build_sql()
        )
        for key, criteria_tab in window._cyberlife_criteria_tabs():
            criteria_tab.set_state(saved["tabs"].get(key, {}))
        checks["saved_query_round_trip"] = sql == window._build_sql()
        if args.wl_screenshot:
            wl = window.wl_tab
            window.tabs.setCurrentWidget(wl)
            wl.btn_par.click()
            app.processEvents()
            checks["wl_par_selects_a_to_h"] = wl.selected_participation_codes() == list("ABCDEFGH")
            checks["wl_filters_base"] = (
                "TRIM(COVERAGE1.DIV_PTP_TYP_CD) IN ('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')"
                in window._build_sql().rsplit("\nWHERE ", 1)[1]
            )
            checks["wl_all_descriptions_fit"] = all(
                listbox.horizontalScrollBar().maximum() == 0
                and listbox.verticalScrollBar().maximum() == 0
                and all(
                    listbox.fontMetrics().horizontalAdvance(listbox.item(row).text()) + 4
                    <= listbox.viewport().width()
                    for row in range(listbox.count())
                )
                for listbox in (
                    wl.list_pri_div, wl.list_sec_div, wl.list_nfo, wl.list_participation_type,
                )
            )
            args.wl_screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.wl_screenshot), "PNG"):
                raise RuntimeError(f"Could not save screenshot: {args.wl_screenshot}")
            wl_sql = window._build_sql()
            saved = json.loads(json.dumps(window._cyberlife_query_object_state()))
            window._on_clear_cyberlife()
            checks["new_clears_wl"] = (
                not wl.chk_participation_type.isChecked()
                and not wl.selected_participation_codes()
                and "DIV_PTP_TYP_CD" not in window._build_sql()
            )
            for key, criteria_tab in window._cyberlife_criteria_tabs():
                criteria_tab.set_state(saved["tabs"].get(key, {}))
            checks["wl_saved_query_round_trip"] = window._build_sql() == wl_sql
        window.close()
        app.processEvents()
    print(json.dumps({"all_ok": all(checks.values()), "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
