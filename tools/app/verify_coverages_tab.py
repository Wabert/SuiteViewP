"""Native no-DB check of the Query Coverages tab layout and Rider 2 [+] flow.

Renders the real AuditWindow at the supplied size and verifies that:
  * Rider 2 starts hidden behind [+], [+] adds it, its [x] removes and clears it;
  * every column fits inside the tab with and without Rider 2, without overlap;
  * range rows (Issue/Change Date, VPU, Cov Amount) sit on one line, share the
    field right edge, and line up row-for-row between Base and Rider columns;
  * the Base and Rider Class controls reach the generated SQL;
  * saved-query/New round-trips, re-showing Rider 2 when the query uses it.
Writes two screenshots (``<stem>.png`` without Rider 2, ``<stem>_rider2.png``
with it); queries nothing.

Usage:
    venv\\Scripts\\python.exe tools/app/verify_coverages_tab.py --screenshot <path>
        [--width 1329 --height 740]
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


def _right(widget, ancestor):
    x, _y, w, _h = _rect_in(widget, ancestor)
    return x + w


def _layout_checks(tab, groups, prefix):
    checks = {}
    rects = [_rect_in(group, tab) for group in groups]
    checks[f"{prefix}_columns_inside_tab"] = all(
        x >= 0 and x + w <= tab.width() and y + h <= tab.height() for x, y, w, h in rects)
    checks[f"{prefix}_columns_do_not_overlap"] = all(
        a[0] + a[2] <= b[0] for a, b in zip(rects, rects[1:]))
    return checks


def _column_checks(tab, group, widgets, class_control, name):
    checks = {}
    field_right = _right(widgets["plancode"], tab)
    checks[f"{name}_fields_not_clipped"] = field_right <= _right(group, tab) - 4
    checks[f"{name}_class_aligned"] = _right(class_control, tab) == field_right
    for key in ("issue_date", "change_date", "vpu", "spec_amt"):
        lo, hi = widgets[f"{key}_lo"], widgets[f"{key}_hi"]
        checks[f"{name}_{key}_one_line"] = (
            _rect_in(lo, tab)[1] == _rect_in(hi, tab)[1]
            and _rect_in(lo, tab)[0] > _rect_in(widgets["plancode"], tab)[0] - 1)
        checks[f"{name}_{key}_right_edge"] = _right(hi, tab) == field_right
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1329)
    parser.add_argument("--height", type=int, default=740)
    args = parser.parse_args()
    app = QApplication(sys.argv)
    with (
        patch("suiteview.audit.audit_window.load_ui_settings", return_value={}),
        patch("suiteview.audit.audit_window.save_ui_settings"),
    ):
        window = AuditWindow()
        window.resize(args.width, args.height)
        tab = window.coverages_tab
        window.tabs.setCurrentWidget(tab)
        window.show()
        app.processEvents()

        checks = {
            "rider2_hidden_by_default": not tab.rider2_visible(),
            "add_button_shown_by_default": not tab.btn_add_rider2.isHidden(),
        }
        checks.update(_layout_checks(
            tab, [tab.grp_base_cov, tab.grp_rider1, tab.btn_add_rider2], "two_covs"))
        checks.update(_column_checks(
            tab, tab.grp_base_cov, tab.base_cov_widgets, tab.val_class, "base"))
        checks.update(_column_checks(
            tab, tab.grp_rider1, tab.rider1_widgets, tab.rider1_widgets["class_code"], "rider1"))
        checks["base_rider_rows_aligned"] = all(
            _rect_in(tab.base_cov_widgets[key], tab)[1] == _rect_in(tab.rider1_widgets[key], tab)[1]
            for key in ("plancode", "gio_fio", "issue_date_lo", "spec_amt_lo", "table_03"))
        checks["class_moved_out_of_valuation"] = (
            _rect_in(tab.val_class, tab)[0] >= _rect_in(tab.grp_base_cov, tab)[0])
        sa_group = tab.txt_spec_amt_lo.parentWidget().parentWidget()
        checks["total_spec_amt_title_fits"] = (
            sa_group.title() == "Total Curr Specified Amt (Sum 02)"
            and sa_group.fontMetrics().horizontalAdvance(sa_group.title()) + 12 <= sa_group.width())

        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.screenshot), "PNG"):
            raise RuntimeError(f"Could not save screenshot: {args.screenshot}")

        base_x_before = _rect_in(tab.grp_base_cov, tab)[0]
        tab.btn_add_rider2.click()
        app.processEvents()
        checks["plus_shows_rider2"] = tab.rider2_visible() and tab.btn_add_rider2.isHidden()
        checks["columns_do_not_shift"] = _rect_in(tab.grp_base_cov, tab)[0] == base_x_before
        checks.update(_layout_checks(
            tab, [tab.grp_base_cov, tab.grp_rider1, tab.grp_rider2], "three_covs"))
        checks.update(_column_checks(
            tab, tab.grp_rider2, tab.rider2_widgets, tab.rider2_widgets["class_code"], "rider2"))

        tab.val_class.setText("1")
        tab.rider1_widgets["class_code"].setText("2")
        tab.rider2_widgets["class_code"].setText("5, 6")
        app.processEvents()
        sql = window._build_sql()
        checks["sql_base_class"] = "COVERAGE1.INS_CLS_CD IN ('1')" in sql
        checks["sql_rider1_class"] = "AND RIDER1.INS_CLS_CD IN ('2')" in sql
        checks["sql_rider2_class"] = "AND RIDER2.INS_CLS_CD IN ('5', '6')" in sql

        rider2_shot = args.screenshot.with_name(f"{args.screenshot.stem}_rider2.png")
        if not window.grab().save(str(rider2_shot), "PNG"):
            raise RuntimeError(f"Could not save screenshot: {rider2_shot}")

        saved = json.loads(json.dumps(window._cyberlife_query_object_state()))
        window._on_clear_cyberlife()
        app.processEvents()
        checks["new_hides_rider2"] = not tab.rider2_visible() and "RIDER2" not in window._build_sql()
        for key, criteria_tab in window._cyberlife_criteria_tabs():
            criteria_tab.set_state(saved["tabs"].get(key, {}))
        app.processEvents()
        checks["restore_shows_rider2"] = tab.rider2_visible()
        checks["saved_query_round_trip"] = window._build_sql() == sql

        tab.grp_rider2.btn_remove.click()
        app.processEvents()
        after_remove = window._build_sql()
        checks["remove_hides_rider2"] = not tab.rider2_visible() and not tab.btn_add_rider2.isHidden()
        checks["remove_clears_rider2_sql"] = (
            "RIDER2" not in after_remove and "RIDER1.INS_CLS_CD IN ('2')" in after_remove)
        window.close()
        app.processEvents()
    widths = {
        name: group.width()
        for name, group in (
            ("base", tab.grp_base_cov), ("rider1", tab.grp_rider1), ("rider2", tab.grp_rider2))
    }
    widths["tab"] = tab.width()
    widths["natural_min"] = tab.minimumSizeHint().width()
    print(json.dumps({"all_ok": all(checks.values()), "widths": widths, "checks": checks}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
