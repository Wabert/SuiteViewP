"""Value-only record editors remain scenario-scoped and gated by Edit Record."""

from copy import deepcopy
from datetime import date

import pytest
from PyQt6.QtCore import QCoreApplication, QDate, QEvent, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDoubleSpinBox

from tests.test_value_rollback_ui import app, rollback_window
from suiteview.illustration.core.scenario_builder import build_illustration_scenario


@pytest.mark.parametrize("historical", [False, True])
def test_circled_record_values_edit_on_each_basis_and_restore(rollback_window, historical):
    window, source, dates = rollback_window
    source.premium_pay_status_code = "22"
    source.regular_loan_principal = 1_000
    source.regular_loan_accrued = 10
    source.preferred_loan_principal = 500
    source.preferred_loan_accrued = 5
    source.variable_loan_principal = 200
    source.variable_loan_accrued = 2
    original = deepcopy(source)
    if historical:
        window._on_rollback_update(dates[0])
    else:
        window._refresh_policy_basis()
    assert window._rollback_action.text() == "Edit Record"
    values = {
        "premium_pay_status_code": "21",
        "premiums_ytd": 123,
        "premiums_paid_to_date": 23_456,
        "withdrawals_to_date": 100,
        "accumulated_mtp": 6_000,
        "map_cease_date": date(2030, 3, 1),
        "mtp": 125,
        "ctp": 650,
        "cost_basis": 20_000,
        "is_mec": True,
        "tamra_7pay_start_date": date(2020, 3, 1),
        "tamra_7pay_cash_value": 2_000,
        "tamra_7pay_level": 4_000,
        "tamra_7year_lowest_db": 250_000,
        "gsp": 50_000,
        "glp": 6_000,
        "accumulated_glp": 36_000,
        "regular_loan_principal": 1_200,
        "regular_loan_accrued": 12,
        "preferred_loan_principal": 600,
        "preferred_loan_accrued": 6,
        "variable_loan_principal": 300,
        "variable_loan_accrued": 3,
        "regular_loan_charge_rate": 0.06,
        "preferred_loan_charge_rate": 0.05,
        "variable_loan_charge_rate": 0.075,
        **{f"tamra_7year_contributions.{index}": index * 100 for index in range(7)},
    }
    for name, value in values.items():
        _group, _attr, kind, editor = window.policy_tab._record_editors[name]
        assert editor.isEnabled(), name
        if kind in ("bool", "status"):
            editor.setCurrentIndex(editor.findData(value))
            editor.activated.emit(editor.currentIndex())
        elif kind == "date":
            editor.setDate(QDate(value))
            editor.editingFinished.emit()
        else:
            editor.setValue(value * 100 if kind == "rate" else value)
            editor.editingFinished.emit()
    assert window._test_warnings == []
    result = build_illustration_scenario(
        source, rollback_overrides=window.inputs_tab.export_rollback_overrides()).projectable_policy
    for name, expected in values.items():
        actual = (
            result.tamra_7year_contributions[int(name.rsplit(".", 1)[1])]
            if name.startswith("tamra_7year_contributions.") else getattr(result, name))
        assert actual == pytest.approx(expected) if isinstance(expected, float) else actual == expected
    assert source == original
    window._rollback_action.trigger()
    assert window.inputs_tab.export_rollback_overrides() is None
    for _name, (group, attr, _kind, editor) in window.policy_tab._record_editors.items():
        assert not editor.isVisibleTo(window.policy_tab)
    assert window.policy_tab.loan_values.get_value("regular_loan_principal") == "$1,000.00"
    assert window.policy_tab.loan_values.get_value("regular_loan_accrued") == "$10.00"


def _set_fund_value(table, fund, value):
    row = next(row for row in range(table.rowCount()) if table.item(row, 0).text() == fund)
    assert not table.item(row, 0).flags() & Qt.ItemFlag.ItemIsEditable
    assert table.item(row, 1).flags() & Qt.ItemFlag.ItemIsEditable
    table.item(row, 1).setData(Qt.ItemDataRole.UserRole, value)
    table.item(row, 1).setText(f"{value:,.2f}")


def test_existing_fund_values_stage_validate_and_preserve_ids(rollback_window):
    window, source, _ = rollback_window
    source.fund_values = {"IR": 2_000, "M1": 3_000}
    source.impaired_fund_values = {"IR": 400}
    source.premium_allocations = {"IR": 0.4, "M1": 0.6}
    original = deepcopy(source)
    window._refresh_policy_basis()
    tab = window.policy_tab
    _set_fund_value(tab.unimpaired_table, "IR", 2_500)
    _set_fund_value(tab.impaired_table, "IR", 500)
    _set_fund_value(tab.allocation_table, "IR", 30)
    assert tab.has_pending_record_changes()
    assert not window.run_values_btn.isEnabled()
    assert not window.save_case_btn.isEnabled()
    tab.apply_funds_button.click()
    assert window._test_warnings
    assert tab.has_pending_record_changes()
    _set_fund_value(tab.allocation_table, "M1", 70)
    window._test_warnings.clear()
    tab.apply_funds_button.click()
    assert window._test_warnings == []
    assert not tab.has_pending_record_changes()
    assert window.run_values_btn.isEnabled()
    overrides = window.inputs_tab.export_rollback_overrides()
    result = build_illustration_scenario(source, rollback_overrides=overrides).projectable_policy
    assert result.fund_values == {"IR": 2_500, "M1": 3_000}
    assert result.impaired_fund_values == {"IR": 500}
    assert result.premium_allocations == {"IR": 0.3, "M1": 0.7}
    assert source == original
    _set_fund_value(tab.unimpaired_table, "M1", 0)
    window._on_record_value("cost_basis", 900)
    assert tab.has_pending_record_changes()
    tab.apply_funds_button.click()
    assert tab.unimpaired_table.rowCount() == 2
    assert set(window.inputs_tab.export_rollback_overrides().fund_values) == {"IR", "M1"}
    window._rollback_action.trigger()
    assert not tab.fund_edit_controls.isVisibleTo(tab)
    assert window.inputs_tab.export_rollback_overrides() is None
    assert source == original


def test_record_dates_clear_and_unknown_fund_ids_are_rejected(rollback_window):
    window, source, _ = rollback_window
    source.map_cease_date = date(2030, 1, 1)
    source.fund_values = {"IR": 1_000}
    window._refresh_policy_basis()
    editor = window.policy_tab._record_editors["map_cease_date"][3]
    editor.setDate(editor.minimumDate())
    editor.editingFinished.emit()
    assert window.inputs_tab.export_rollback_overrides().record_values["map_cease_date"] is None
    window._on_record_funds({"fund_values": {"OTHER": 50}})
    assert window._test_warnings
    result = build_illustration_scenario(
        source, rollback_overrides=window.inputs_tab.export_rollback_overrides()).projectable_policy
    assert result.fund_values == {"IR": 1_000}


def test_native_fund_delegate_commits_before_apply_and_reset(app, rollback_window):
    window, source, _ = rollback_window
    source.fund_values = {"IR": 1_000}
    window._refresh_policy_basis()
    window.show()
    app.processEvents()
    tab = window.policy_tab
    table = tab.unimpaired_table._data_table
    for apply in (True, False):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        table.editItem(table.item(0, 1))
        editor = table.findChild(QDoubleSpinBox)
        assert editor is not None
        editor.setValue(1_250 if apply else 2_000)
        QTest.keyClick(editor, Qt.Key.Key_Return)
        app.processEvents()
        assert tab.has_pending_record_changes(), (apply, table.item(0, 1).text())
        assert not window.run_values_btn.isEnabled()
        assert not window.save_case_btn.isEnabled()
        assert not window.compare_tab.isEnabled()
        if apply:
            tab.apply_funds_button.click()
        else:
            tab.reset_funds_button.click()
        assert not tab.has_pending_record_changes()
        assert window.run_values_btn.isEnabled()
        assert window.save_case_btn.isEnabled()
        assert window.compare_tab.isEnabled()
        assert "pending fund" not in window._status_label.text()
        assert window.inputs_tab.export_rollback_overrides().fund_values == {"IR": 1_250}
        assert source.fund_values == {"IR": 1_000}
