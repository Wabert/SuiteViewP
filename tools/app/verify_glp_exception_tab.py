"""Smoke-check the Policy Support GLP Exception panel after the target-date solve.

Builds the real PolicySupportTab widget offscreen. With --policy, Calculate uses
the shared live policy service read-only and verifies all three independent solves,
the RERUN monthly schema/formatting, and the quote workbook.

Usage:
    venv\\Scripts\\python.exe tools/app/verify_glp_exception_tab.py
"""
from __future__ import annotations

import json
import argparse
import os
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy")
    parser.add_argument("--company", default="01")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--target", default="2027-01-15")
    parser.add_argument("--expect-zero", action="store_true")
    parser.add_argument("--expect-opening-av", type=float)
    parser.add_argument("--reference", type=Path, help="JSON list of expected ledger cells keyed by Date")
    parser.add_argument("--output", type=Path, help="Also write the verification JSON here")
    parser.add_argument("--screenshot", type=Path, help="Save a native Qt capture of the quote panel")
    args = parser.parse_args()
    os.environ.setdefault(
        "QT_QPA_PLATFORM",
        "windows" if args.screenshot and sys.platform == "win32" else "offscreen",
    )
    reference = json.loads(args.reference.read_text(encoding="utf-8")) if args.reference else []
    from PyQt6.QtWidgets import QApplication

    from suiteview.polview.services.guideline_exception_adjustment import (
        GuidelineExceptionTargetForecastResult,
    )
    from suiteview.polview.ui.tabs.policy_support_tab import PolicySupportTab
    from suiteview.illustration.ui.values_overview import LEDGER_COLUMNS, monthly_ledger_cells

    app = QApplication.instance() or QApplication([])
    tab = PolicySupportTab()

    tabs = tab._glp_forecast_tabs
    tab._glp_target_date.setText(date.fromisoformat(args.target).strftime("%m/%d/%Y"))

    if args.policy:
        from suiteview.core.policy_service import get_policy_info

        policy = get_policy_info(
            args.policy, company_code=args.company, region=args.region, use_cache=False)
        if policy is None:
            raise RuntimeError("Policy could not be loaded; see the live-access error above.")
        tab._policy = policy
        tab._on_calculate_glp_exception()
        result = getattr(tab, "_glp_result", None)
        if result is None:
            raise RuntimeError(tab._glp_forecast_status_label.text())
        scenarios = {}
        all_ok = True
        for label, scenario, table in (
            ("current_glp", result, tab._glp_target_table),
            ("glp_zero", result.zero_glp, tab._glp_zero_glp_table),
            ("no_forceout", result.no_forceout, tab._glp_no_forceout_table),
        ):
            premiums = [row.premium for row in scenario.rows]
            schema_ok = [
                table._data_table.horizontalHeaderItem(i).text()
                for i in range(table.columnCount())
            ] == LEDGER_COLUMNS
            previous_wd = scenario.rows[0].state.withdrawals_to_date
            cells_ok = table.rowCount() == len(scenario.rows)
            for i, row in enumerate(scenario.rows):
                cells_ok &= [table.item(i, j).text() for j in range(table.columnCount())] == (
                    monthly_ledger_cells(row.state, previous_wd))
                previous_wd = row.state.withdrawals_to_date
            valid = (
                schema_ok and cells_ok and bool(scenario.rows)
                and all(row.date < date.fromisoformat(args.target) for row in scenario.rows)
                and not any(row.state.lapsed for row in scenario.rows)
            )
            if args.expect_zero:
                valid &= scenario.premium == 0 and not any(premiums)
            if args.expect_opening_av is not None:
                valid &= abs(scenario.rows[0].state.av_after_deduction - args.expect_opening_av) < 0.005
            if label in ("glp_zero", "no_forceout"):
                valid &= all(row.glp == 0 for row in scenario.rows)
            if label == "no_forceout":
                valid &= all(row.force_out == 0 for row in scenario.rows)
            ledger_rows = [
                {name: table.item(i, j).text() for j, name in enumerate(LEDGER_COLUMNS) if name}
                for i in range(table.rowCount())
            ]
            by_date = {row["Date"]: row for row in ledger_rows}
            reference_ok = all(
                all(by_date.get(expected["Date"], {}).get(key) == value
                    for key, value in expected.items())
                for expected in reference
            )
            valid &= reference_ok
            all_ok &= valid
            scenarios[label] = {
                "solved_premium": scenario.premium, "premium_mode": scenario.premium_mode,
                "lump_sum": scenario.lump_sum,
                "lump_sum_date": scenario.lump_sum_date.isoformat() if scenario.lump_sum_date else None,
                "opening_av": scenario.rows[0].state.av_after_deduction,
                "ledger_rows": ledger_rows,
                "reference_rows_checked": len(reference), "reference_match": reference_ok,
                "displayed_premiums": premiums, "row_count": len(scenario.rows),
                "last_forecast_date": scenario.rows[-1].date.isoformat(),
                "ending_account_value": scenario.rows[-1].account_value,
                "ending_surrender_value": scenario.rows[-1].surrender_value,
                "exception_premium": sum(row.exception_premium for row in scenario.rows),
                "forceouts": sum(row.force_out for row in scenario.rows),
                "schema_ok": schema_ok, "rerun_cells_match": cells_ok,
                "all_ok": valid,
            }
        labels = [tabs.tabText(i) for i in range(tabs.count())]
        all_ok &= labels == [
            "Min Prem To Target", "Min Prem To Target (GLP=0)",
            "Min Prem to Target (no forceout)"]
        wb = tab._build_glp_quote_workbook()
        workbook_rows = list(wb.active.values)
        workbook_ok = sum(list(row) == LEDGER_COLUMNS for row in workbook_rows) == 3
        for label, table in zip(labels, (
                tab._glp_target_table, tab._glp_zero_glp_table, tab._glp_no_forceout_table)):
            workbook_ok &= any(f"Monthly Forecast \u2014 {label}" == row[0] for row in workbook_rows)
            for i in range(table.rowCount()):
                cells = tuple(table.item(i, j).text() for j in range(table.columnCount()))
                workbook_ok &= cells in workbook_rows
        wb.close()
        all_ok &= workbook_ok
        if result.current_glp == 0:
            all_ok &= result.rows == result.zero_glp.rows
        if not any(row.force_out for row in result.zero_glp.rows):
            all_ok &= result.no_forceout.rows == result.zero_glp.rows
        out = {
            "policy": args.policy, "target": args.target,
            "forecast_tab_labels": labels, "ledger_columns": LEDGER_COLUMNS,
            "scenarios": scenarios, "workbook_ok": workbook_ok,
            "summary": tab._glp_summary_copy_text(), "all_ok": all_ok,
        }
        if args.screenshot:
            tab._content_stack.setCurrentWidget(tab._glp_exception_page)
            tab._current_section = tab.SECTION_GLP_EXCEPTION
            tab._refresh_section_buttons()
            tab.resize(1400, 850)
            tab.show()
            app.processEvents()
            if not tab.grab().save(str(args.screenshot)):
                raise RuntimeError(f"Could not save screenshot to {args.screenshot}")
            out["screenshot"] = str(args.screenshot)
        encoded = json.dumps(out, indent=2)
        print(encoded)
        if args.output:
            args.output.write_text(encoded + "\n", encoding="utf-8")
        tab.close()
        app.quit()
        return 0 if all_ok else 1

    def tooltip_for(premium: float) -> str:
        result = GuidelineExceptionTargetForecastResult(
            premium=premium,
            premium_mode="M",
            exception_start=None,
            rows=[],
            zero_glp=SimpleNamespace(premium=premium, premium_mode="M", exception_start=None,
                                    lump_sum=0, lump_sum_date=None),
            no_forceout=SimpleNamespace(
                premium=premium / 2, premium_mode="M", exception_start=None,
                lump_sum=0, lump_sum_date=None),
            current_glp=0.0,
        )
        tab._set_glp_target_tab_tooltip(result)
        tab._apply_glp_summary(result)
        return tabs.tabToolTip(tabs.indexOf(tab._glp_target_table))

    zero_tip = tooltip_for(0.0)
    positive_tip = tooltip_for(272.30)
    no_forceout_tip = tabs.tabToolTip(tabs.indexOf(tab._glp_no_forceout_table))
    summary = tab._glp_plugged_label.text()

    out = {
        "forecast_tab_labels": [tabs.tabText(i) for i in range(tabs.count())],
        "zero_premium_tooltip": zero_tip,
        "positive_premium_tooltip": positive_tip,
        "no_forceout_tooltip": no_forceout_tip,
        "no_exception_summary": summary,
        "all_ok": (
            [tabs.tabText(i) for i in range(tabs.count())]
            == ["Min Prem To Target", "Min Prem To Target (GLP=0)",
                "Min Prem to Target (no forceout)"]
            and "$0.00" in zero_tip
            and "no premium is required" in zero_tip
            and "$272.30 monthly" in positive_tip
            and "01/15/2027" in positive_tip
            and "NO EXCEPTION PREMIUM NEEDED" in summary
            and "$136.15 monthly" in no_forceout_tip
            and "GLP=0; no forceout" in no_forceout_tip
            and "comparison only" in no_forceout_tip
        ),
    }
    print(json.dumps(out, indent=2))
    app.quit()
    return 0 if out["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
