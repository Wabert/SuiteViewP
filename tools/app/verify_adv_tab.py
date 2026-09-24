"""Native no-DB check of the Query ADV tab layout and Decrease Charge Rule wiring.

Renders the real AuditWindow at the supplied size, verifies every ADV code
list shows all rows unclipped and inside the tab, that the columns do not
overlap, that the Decrease Charge Rule filter reaches the generated SQL, and
that saved-query/New round-trips. Writes a screenshot; queries nothing.

Usage:
    venv\\Scripts\\python.exe tools/app/verify_adv_tab.py --screenshot <path>
        [--width 1100 --height 640]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication
from suiteview.audit.audit_window import AuditWindow


def _rect_in(widget, ancestor):
    top_left = widget.mapTo(ancestor, widget.rect().topLeft())
    return top_left.x(), top_left.y(), widget.width(), widget.height()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1100)
    parser.add_argument("--height", type=int, default=640)
    args = parser.parse_args()
    app = QApplication(sys.argv)
    with (
        patch("suiteview.audit.audit_window.load_ui_settings", return_value={}),
        patch("suiteview.audit.audit_window.save_ui_settings"),
    ):
        window = AuditWindow()
        window.resize(args.width, args.height)
        tab = window.adv_tab
        window.tabs.setCurrentWidget(tab)
        window.show()
        app.processEvents()

        lists = {
            "grace": tab.list_grace_rule, "db_option": tab.list_db_option,
            "decrease_charge": tab.list_decr_chrg_rule, "orig_entry": tab.list_orig_entry,
            "prem_alloc": tab.list_prem_alloc,
        }
        checks = {}
        for name, listbox in lists.items():
            x, y, w, h = _rect_in(listbox, tab)
            checks[f"{name}_inside_tab"] = x + w <= tab.width() and y + h <= tab.height()
            checks[f"{name}_all_rows_visible"] = listbox.verticalScrollBar().maximum() == 0
            checks[f"{name}_text_fits"] = all(
                listbox.fontMetrics().horizontalAdvance(listbox.item(row).text()) + 4
                <= listbox.viewport().width()
                for row in range(listbox.count())
            )
        range_right = _rect_in(tab.rng_gsp[1], tab)
        grace_left = _rect_in(tab.list_grace_rule, tab)
        grace_right = grace_left[0] + grace_left[2]
        fund_left = _rect_in(tab.txt_cirf, tab)[0]
        checks["columns_do_not_overlap"] = (
            range_right[0] + range_right[2] < grace_left[0] and grace_right < fund_left)
        checks["ranges_inside_tab"] = range_right[1] + range_right[3] <= tab.height()
        fund = _rect_in(tab.txt_fund_hi, tab)
        checks["fund_value_inside_tab"] = fund[1] + fund[3] <= tab.height()

        tab.chk_decr_chrg_rule.setChecked(True)
        tab.list_decr_chrg_rule.item(0).setSelected(True)
        app.processEvents()
        sql = window._build_sql()
        checks["sql_filters_decrease_charge_rule"] = (
            "TH_NON_TRD_POL DECRCHG" in sql and "DECRCHG.DECR_CHRG_ALLOW IN ('0')" in sql)

        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.screenshot), "PNG"):
            raise RuntimeError(f"Could not save screenshot: {args.screenshot}")

        saved = json.loads(json.dumps(window._cyberlife_query_object_state()))
        window._on_clear_cyberlife()
        checks["new_clears"] = (
            not tab.chk_decr_chrg_rule.isChecked()
            and not tab.list_decr_chrg_rule.selectedItems()
            and "DECRCHG" not in window._build_sql()
        )
        for key, criteria_tab in window._cyberlife_criteria_tabs():
            criteria_tab.set_state(saved["tabs"].get(key, {}))
        checks["saved_query_round_trip"] = window._build_sql() == sql
        window.close()
        app.processEvents()
    print(json.dumps({"all_ok": all(checks.values()), "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
