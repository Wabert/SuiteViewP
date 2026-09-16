"""Verify Value Rollback read-only against live data; optionally capture its native UI."""

import argparse
from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.policy_service import get_policy_info
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.core.value_rollback import available_rollback_dates, apply_value_rollback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="UE055782")
    parser.add_argument("--company", default="01")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--project", action="store_true")
    parser.add_argument("--exercise-edits", action="store_true",
                        help="Exercise current/historical inline edits and Run Values without saving.")
    parser.add_argument("--exercise-record", action="store_true",
                        help="Also exercise Edit Record loan, accumulator, tax and fund value controls.")
    parser.add_argument("--date", type=date.fromisoformat,
                        help="Verify one recorded rollback date instead of all dates.")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise ValueError("Live verification cannot use local-data mode.")
    pi = get_policy_info(args.policy, args.region, args.company)
    policy = build_illustration_data(args.policy, args.region, args.company)
    if args.inspect:
        tables = {}
        for table in (
            "LH_POL_MVRY_VAL", "LH_COV_TARGET", "LH_POL_TARGET",
            "LH_FND_VAL_LOAN", "LH_COV_INS_GDL_PRM", "LH_TAMRA_7_PY_PER",
        ):
            rows = pi.fetch_table(table)
            tables[table] = {"columns": list(rows[0]) if rows else [], "rows": rows[:3]}
        tables["FH_FIXED"] = [
            {key: row.get(key) for key in (
                "ASOF_DT", "ENTRY_DT", "TRANS", "GROSS_AMT", "SEQ_NO",
                "FCB0_REV_IND", "FCB2_REV_APPL_IND", "FBB3_PROCD_IND")}
            for row in pi.fetch_table("FH_FIXED")[:16]
        ]
        print(json.dumps(tables, default=str, indent=2))
    original = deepcopy(policy)
    results = []
    dates = available_rollback_dates(policy)
    if args.date is not None and args.date not in dates:
        raise ValueError(f"{args.date} is not an available recorded rollback date.")
    for when in ([args.date] if args.date is not None else dates):
        try:
            historical = apply_value_rollback(policy, when, allow_missing_shadow=True)
        except ValueError as exc:
            results.append({"date": when, "blocked": str(exc)})
            continue
        results.append({
            "date": when, "av": historical.account_value,
            "shadow": None if historical.rollback_requires_shadow_value else historical.shadow_account_value,
            "requires_shadow": historical.rollback_requires_shadow_value,
            "accum_mtp": historical.accumulated_mtp,
            "accum_glp": historical.accumulated_glp, "paid": historical.premiums_paid_to_date,
            "cost_basis": historical.cost_basis, "limitations": historical.rollback_limitations,
            "tamra_contributions": historical.tamra_7year_contributions,
            "historical_fund_values": historical.fund_values,
        })
        if args.project and len(results) == 1 and not historical.rollback_requires_shadow_value:
            from suiteview.illustration.core.calc_engine import IllustrationEngine
            states = IllustrationEngine().project(historical, months=2)
            results[-1]["projected_dates"] = [state.date for state in states]
    if policy != original:
        raise AssertionError("Rollback mutated the loaded policy.")
    result = {
        "policy": args.policy, "source_unchanged": True,
        "available_dates": dates, "requested_date": args.date, "results": results,
    }
    result["all_ok"] = bool(results) and not any("blocked" in row for row in results)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        result["ui"] = capture_ui(
            policy, pi, args.output_dir, when=args.date,
            exercise_edits=args.exercise_edits or args.exercise_record,
            exercise_record=args.exercise_record)
        if policy != original:
            raise AssertionError("Native value editing mutated the loaded policy.")
        result["all_ok"] &= result["ui"]["all_ok"]
        (args.output_dir / "verification.json").write_text(
            json.dumps(result, default=str, indent=2), encoding="utf-8")
    print(json.dumps(result, default=str, indent=2))
    return 0 if result["all_ok"] else 1


def capture_ui(policy, pi, folder, *, when=None, exercise_edits=False, exercise_record=False):
    from unittest.mock import patch
    from PyQt6.QtCore import QCoreApplication, QDate, QEvent, QPoint, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QLabel, QMessageBox, QPushButton, QScrollArea
    from suiteview.illustration.core.scenario_builder import build_illustration_scenario
    from suiteview.illustration.ui.main_window import IllustrationWindow

    app = QApplication.instance() or QApplication([])
    window = IllustrationWindow()
    window._illustration_data = policy
    window._policy = pi
    window._policy_info = {
        "PolicyNumber": policy.policy_number, "CompanyCode": policy.company_code,
        "Region": policy.region,
    }
    window.lookup_bar.set_policy_display(policy.company_code, policy.policy_number, policy.region)
    window.lookup_bar.region_input.setText(policy.region)
    window.lookup_bar.company_input.setText(policy.company_code)
    window.lookup_bar.policy_input.setText(policy.policy_number)
    window.policy_tab.load_data_from_policy(pi, window._policy_info)
    window.inputs_tab.load_data_from_policy(policy)
    window._set_active_inputs_tab(window.inputs_tab)
    window._refresh_policy_basis()
    window.resize(1200, 825)
    window.show()
    app.processEvents()
    paths = []

    def capture(name):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        path = folder / name
        if not window.grab().save(str(path), "PNG"):
            raise RuntimeError(f"Could not capture {path}")
        paths.append(str(path))

    checks = {
        "edit_record_option": window._rollback_action.text() == "Edit Record",
        "rollback_defaults_off": not window._rollback_action.isChecked(),
        "normal_date_controls_hidden": not window.rollback_controls.isVisible(),
        "normal_values_read_only": window.policy_tab.fund_values.fund_account_value.isVisible(),
        "normal_dbo_read_only": window.policy_tab.policy_info.db_option_label.isVisible(),
    }
    capture("rerun-rollback-off.png")
    window._rollback_action.trigger()
    capture("rerun-loaded-values.png")
    errors = []
    checks.update({
        "current_date_default": window.rollback_controls.dates.currentData() == policy.valuation_date,
        "current_values_editable": window.policy_tab.account_value_input.isEnabled(),
        "db_option_inline": window.policy_tab.policy_info.isAncestorOf(window.policy_tab.rollback_dbo_combo),
        "aligned_controls": len({
            (widget.y(), widget.height()) for widget in (
                window.rollback_controls.date_label, window.rollback_controls.dates,
                window.rollback_controls.update)}) == 1,
    })

    def edit_values(stage):
        tab = window.policy_tab
        new_av = tab.account_value_input.value() + 1.23
        original_dbo = tab.rollback_dbo_combo.currentData()
        new_dbo = "B" if original_dbo != "B" else "A"
        new_face = tab._coverages[0].face_amount - 1_000
        with patch.object(QMessageBox, "warning", side_effect=lambda *a: errors.append(a[-1])):
            tab.account_value_input.setValue(new_av)
            QTest.keyClick(tab.account_value_input, Qt.Key.Key_Return)
            tab.shadow_value_input.setValue(1.23)
            QTest.keyClick(tab.shadow_value_input, Qt.Key.Key_Return)
            tab.shadow_value_input.setValue(0)
            QTest.keyClick(tab.shadow_value_input, Qt.Key.Key_Return)
            tab.rollback_dbo_combo.setCurrentIndex(tab.rollback_dbo_combo.findData(new_dbo))
            tab.rollback_dbo_combo.activated.emit(tab.rollback_dbo_combo.currentIndex())
            tab.coverage_buttons.itemAt(0).widget().click()
            editor = tab._rollback_editor
            editor.amount_edit.setValue(new_face)
            path = folder / f"rerun-{stage}-editable-coverage.png"
            if not editor.grab().save(str(path), "PNG"):
                raise RuntimeError(f"Could not capture {path}")
            paths.append(str(path))
            editor.apply_button.click()
            expected = {}
            if exercise_record:
                expected = {
                    "premium_pay_status_code": "22",
                    "premiums_ytd": 125,
                    "premiums_paid_to_date": policy.premiums_paid_to_date + 10,
                    "withdrawals_to_date": 10,
                    "accumulated_mtp": policy.accumulated_mtp + 1,
                    "map_cease_date": date(2038, 4, 10),
                    "mtp": policy.mtp + 0.01,
                    "ctp": policy.ctp + 0.01,
                    "cost_basis": policy.cost_basis + 10,
                    "is_mec": True,
                    "tamra_7pay_start_date": date(2023, 4, 10),
                    "tamra_7pay_cash_value": 123,
                    "tamra_7pay_level": policy.tamra_7pay_level + 1,
                    "tamra_7year_lowest_db": new_face,
                    "gsp": policy.gsp + 1,
                    "glp": policy.glp + 1,
                    "accumulated_glp": policy.accumulated_glp + 1,
                    "regular_loan_principal": 1_000,
                    "regular_loan_accrued": 10,
                    "preferred_loan_principal": 500,
                    "preferred_loan_accrued": 5,
                    "variable_loan_principal": 200,
                    "variable_loan_accrued": 2,
                    "regular_loan_charge_rate": 0.06,
                    "preferred_loan_charge_rate": 0.05,
                    "variable_loan_charge_rate": 0.07,
                    **{f"tamra_7year_contributions.{index}":
                       policy.tamra_7year_contributions[index] + 1 for index in range(7)},
                }
                for key, value in expected.items():
                    _group, _attr, kind, control = tab._record_editors[key]
                    if kind in ("bool", "status"):
                        control.setCurrentIndex(control.findData(value))
                        control.activated.emit(control.currentIndex())
                    elif kind == "date":
                        control.setDate(QDate(value))
                        control.editingFinished.emit()
                    else:
                        control.setValue(value * 100 if kind == "rate" else value)
                        QTest.keyClick(control, Qt.Key.Key_Return)
                for table in tab._fund_tables.values():
                    for row in range(table.rowCount()):
                        if table.item(row, 0).flags() & Qt.ItemFlag.ItemIsEditable:
                            raise AssertionError("Edit Record made a fund identifier editable.")
                if stage == "current":
                    checks["existing_fund_ids_retained"] = {
                        tab.unimpaired_table.item(row, 0).text()
                        for row in range(tab.unimpaired_table.rowCount())
                    } == set(policy.fund_values)
                if stage == "current" and tab.unimpaired_table.rowCount():
                    table = tab.unimpaired_table
                    item = table.item(0, 1)
                    table._data_table.editItem(item)
                    control = table._data_table.findChild(QDoubleSpinBox)
                    if control is None:
                        raise AssertionError("Fund value cell did not open its numeric editor.")
                    fund = table.item(0, 0).text()
                    fund_value = control.value() + 10
                    control.setValue(fund_value)
                    QTest.keyClick(control, Qt.Key.Key_Return)
                    app.processEvents()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    checks["fund_draft_blocks_run_save"] = (
                        tab.has_pending_record_changes()
                        and not window.run_values_btn.isEnabled()
                        and not window.save_case_btn.isEnabled())
                    tab.apply_funds_button.click()
                    applied_funds = window.inputs_tab.export_rollback_overrides().fund_values
                    checks["fund_apply_commits"] = (
                        not tab.has_pending_record_changes()
                        and applied_funds is not None
                        and applied_funds[fund] == fund_value)
        app.processEvents()
        overrides = window.inputs_tab.export_rollback_overrides()
        if overrides is None:
            raise AssertionError(f"{stage}: inline edits did not reach the scenario.")
        edited = build_illustration_scenario(policy, rollback_overrides=overrides).projectable_policy
        checks[f"{stage}_av_edit"] = edited.account_value == new_av
        checks[f"{stage}_shadow_edit"] = edited.shadow_account_value == 0
        checks[f"{stage}_dbo_edit"] = edited.db_option == new_dbo
        checks[f"{stage}_face_edit"] = edited.segments[0].face_amount == new_face
        for key, value in expected.items():
            actual = (
                edited.tamra_7year_contributions[int(key.rsplit(".", 1)[1])]
                if key.startswith("tamra_7year_contributions.") else getattr(edited, key))
            checks[f"{stage}_{key}"] = actual == value
        capture(f"rerun-{stage}-edited-values.png")
        if exercise_record:
            scroll = tab.findChild(QScrollArea)
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            capture(f"rerun-{stage}-edited-tax-values.png")
            scroll.verticalScrollBar().setValue(0)
        window.inputs_tab.illustration_years_combo.setCurrentText("1")
        with patch.object(QMessageBox, "warning", side_effect=lambda *a: errors.append(a[-1])):
            window.run_values_btn.click()
        checks[f"{stage}_run_values"] = (
            window._last_scenario is not None
            and window._last_scenario.projectable_policy.account_value == new_av
            and "Values ready" in window._status_label.text())
        states = window.values_tab._results
        checks[f"{stage}_engine_opening_value"] = bool(states) and (
            states[0].av_after_deduction == new_av
            and states[0].date == overrides.valuation_date)
        window.tabs.setCurrentWidget(window.policy_tab)
        app.processEvents()

    if exercise_edits:
        edit_values("current")
        window.rollback_controls.dates.setCurrentIndex(0)
        window.rollback_controls.update.click()
    with patch.object(QMessageBox, "warning", side_effect=lambda *a: errors.append(a[-1])):
        choices = [policy.valuation_date, *available_rollback_dates(policy)]
        window.rollback_controls.dates.setCurrentIndex(
            choices.index(when) if when is not None else 1)
        window.rollback_controls.update.click()
    app.processEvents()
    applied = window.inputs_tab.export_rollback_overrides()
    capture("rerun-value-rollback.png")
    checks["applied"] = applied is not None
    if applied is not None:
        historical = apply_value_rollback(policy, applied.valuation_date, allow_missing_shadow=True)
        checks["historical_notice"] = "ROLLBACK" in window._title_label.text()
        checks["correct_av"] = any(
            label.text() == f"${historical.account_value:,.2f}"
            for label in window.policy_tab.fund_values.findChildren(QLabel))
        checks["projection_gate"] = (
            window.run_values_btn.isEnabled() != historical.rollback_requires_shadow_value)
        if not historical.fund_values:
            checks["total_only_fund_notice"] = window.policy_tab.historical_funds_notice.isVisible()
        checks["correct_accum_mtp"] = any(
            label.text() == f"${historical.accumulated_mtp:,.2f}"
            for label in window.policy_tab.premium_values.findChildren(QLabel))
        if not historical.is_cvat:
            checks["correct_accum_glp"] = any(
                label.text() == f"${historical.accumulated_glp:,.2f}"
                for label in window.policy_tab.mec_values.findChildren(QLabel))
        for index in range(3):
            tab = window.policy_tab
            tab.coverage_buttons.itemAt(index % (tab.coverage_buttons.count() - 1)).widget().click()
            editor = tab._rollback_editor
            if editor is None:
                raise AssertionError("Coverage/benefit details failed to reopen.")
            checks[f"editor_{index}_owned_window"] = (
                editor.isWindow()
                and editor.windowModality() == Qt.WindowModality.NonModal
                and editor.windowHandle().transientParent() == window.windowHandle())
            editor.move(window.pos() + QPoint(window.width() - 30, 30))
            app.processEvents()
            checks[f"editor_{index}_unconfined"] = not window.frameGeometry().contains(editor.frameGeometry())
            close = next(button for button in editor.header_bar.findChildren(QPushButton)
                         if button.toolTip() == "Close")
            close.click()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            checks[f"editor_{index}_closed_cleanly"] = tab._rollback_editor is None and window.isEnabled()
        scroll = window.policy_tab.findChild(QScrollArea)
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        app.processEvents()
        capture("rerun-rollback-targets.png")
        scroll.verticalScrollBar().setValue(0)
        window.policy_tab._show_detail_dialog("coverage", window.policy_tab._coverages[0])
        app.processEvents()
        editor = window.policy_tab._rollback_editor
        path = folder / "rerun-rollback-coverage.png"
        if not editor.grab().save(str(path), "PNG"):
            raise RuntimeError(f"Could not capture {path}")
        paths.append(str(path))
        editor.close()
        if exercise_edits:
            edit_values("historical")
        window.rollback_controls.dates.setCurrentIndex(0)
        window.rollback_controls.update.click()
        checks["restored"] = window.inputs_tab.export_rollback_overrides() is None
        checks["restored_av"] = any(
            label.text() == f"${policy.account_value:,.2f}"
            for label in window.policy_tab.fund_values.findChildren(QLabel))
    checks["no_errors"] = not errors
    window._rollback_action.trigger()
    checks["option_off_restores_normal"] = (
        not window.rollback_controls.isVisible()
        and not window.policy_tab.account_value_input.isVisible()
        and window.policy_tab.fund_values.fund_account_value.isVisible()
        and window.inputs_tab.export_rollback_overrides() is None)
    capture("rerun-restored-normal.png")
    window.close()
    return {"all_ok": all(checks.values()), "checks": checks, "errors": errors, "screenshots": paths}


if __name__ == "__main__":
    raise SystemExit(main())
