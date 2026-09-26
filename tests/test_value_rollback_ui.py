"""Rollback selection is explicit, visible, and independent of the live source."""

import os
from copy import deepcopy
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QLabel

from suiteview.illustration.ui.value_rollback import (
    RollbackAmountEditor, ValueRollbackControls,
)


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def test_current_date_is_default_and_only_update_applies_selection(app):
    controls = ValueRollbackControls()
    dates = [date(2026, 8, 31), date(2026, 7, 31), date(2026, 5, 31)]
    selected = []
    controls.update_requested.connect(selected.append)
    current = date(2026, 9, 30)
    controls.set_basis(dates, None, current_date=current)
    assert controls.dates.currentData() == current
    assert [controls.dates.itemData(i) for i in range(controls.dates.count())] == [current, *dates]
    assert controls.dates.isEnabled()
    assert controls.update.isEnabled()
    assert selected == []
    controls.dates.setCurrentIndex(1)
    assert selected == []
    controls.update.click()
    assert selected == [date(2026, 8, 31)]
    controls.deleteLater()


def test_pending_date_does_not_replace_applied_date_indicator(app):
    controls = ValueRollbackControls()
    applied, pending = date(2026, 8, 31), date(2026, 7, 31)
    controls.set_basis([applied, pending], applied)
    controls.dates.setCurrentIndex(1)
    assert "08/31/2026" in controls.state_label.text()
    assert "selection not applied" in controls.state_label.text()
    controls.deleteLater()


def test_applied_date_selection_uses_value_equality_not_qt_object_identity(app):
    controls = ValueRollbackControls()
    when = date(2026, 8, 1)
    controls.set_basis([when], deepcopy(when))
    assert controls.dates.currentIndex() == 0
    assert controls.dates.currentText() == "08/01/2026"
    assert "selection not applied" not in controls.state_label.text()
    controls.deleteLater()


def test_no_history_and_incompatible_modes_disable_controls(app):
    controls = ValueRollbackControls()
    controls.set_basis([], None)
    assert not controls.dates.isEnabled()
    controls.set_basis([], None, current_date=date(2026, 9, 1))
    assert controls.dates.isEnabled()
    assert controls.update.isEnabled()
    controls.set_basis([date(2026, 8, 1)], None, enabled=False, reason="Inforce mode only")
    assert not controls.dates.isEnabled()
    assert "Inforce mode only" in controls.state_label.text()
    controls.deleteLater()


def test_coverage_editor_preserves_zero_and_requires_apply(app):
    editor = RollbackAmountEditor("Rollback Coverage", [("Phase:", 1)], 150_000)
    amounts = []
    editor.amount_applied.connect(amounts.append)
    editor.amount_edit.setValue(0)
    assert amounts == []
    editor.apply_button.click()
    assert amounts == [0]
    editor.close()


def test_date_controls_share_height_and_alignment(app):
    controls = ValueRollbackControls()
    controls.set_basis([], None, current_date=date(2026, 9, 1))
    controls.show()
    app.processEvents()
    assert controls.date_label.height() == controls.dates.height() == controls.update.height() == 26
    assert controls.date_label.y() == controls.dates.y() == controls.update.y()
    assert not controls.state_label.isVisible()
    controls.close()


@pytest.fixture
def rollback_window(app, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from suiteview.illustration.core import value_rollback
    from suiteview.illustration.models.policy_data import (
        CoverageSegment, IllustrationPolicyData,
    )
    from suiteview.illustration.ui import main_window
    from suiteview.illustration.models.app_settings import get_illustration_settings

    settings = get_illustration_settings()
    previous_rollback = settings.rollback_enabled
    settings.set_rollback_enabled(True)

    dates = [date(2026, 8, 1), date(2026, 7, 1)]
    policy = IllustrationPolicyData(
        policy_number="ROLLBACK-TEST", company_code="01", plancode="1U135D00",
        issue_date=date(2019, 3, 1), issue_age=43, attained_age=50,
        valuation_date=date(2026, 9, 1), policy_year=8, policy_month=7, duration=91,
        face_amount=300_000, units=300, db_option="A", account_value=10_000,
        premiums_paid_to_date=20_000, accumulated_mtp=8_000, accumulated_glp=30_000,
        cost_basis=19_000, modal_premium=150, annual_premium=1_800,
        segments=[CoverageSegment(
            face_amount=300_000, original_face_amount=300_000, units=300,
            issue_date=date(2019, 3, 1), issue_age=43)],
    )

    def apply(source, when, **kwargs):
        if when not in dates:
            raise ValueError("No reliable historical values for this date.")
        result = deepcopy(source)
        result.rollback_date = when
        result.rollback_source_date = source.valuation_date
        result.rollback_limitations = ["Specified amount and DB option need review."]
        result.valuation_date = when
        result.account_value = 9_500 if when == dates[0] else 9_000
        result.premiums_paid_to_date = 19_850
        result.cost_basis = 18_850
        result.duration = 90 if when == dates[0] else 89
        result.policy_month = 6 if when == dates[0] else 5
        if source.ccv_active:
            shadow = kwargs.get("shadow_account_value")
            if shadow is None and not kwargs.get("allow_missing_shadow"):
                raise ValueError("Historical shadow value is required.")
            result.rollback_requires_shadow_value = shadow is None
            if shadow is not None:
                result.shadow_account_value = shadow
        return result

    monkeypatch.setattr(value_rollback, "apply_value_rollback", apply)
    monkeypatch.setattr(value_rollback, "available_rollback_dates", lambda _: list(dates))
    monkeypatch.setattr(main_window, "available_rollback_dates", lambda _: list(dates))
    window = main_window.IllustrationWindow()
    window._test_warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: window._test_warnings.append(args[-1]))
    window._illustration_data = policy
    window.lookup_bar.set_policy_display("01", policy.policy_number, "CKPR")
    window.policy_tab.load_data_from_snapshot(policy)
    window.inputs_tab.load_data_from_policy(policy)
    window._set_active_inputs_tab(window.inputs_tab)
    window._refresh_rollback_controls()
    yield window, policy, dates
    window.close()
    window.deleteLater()
    from PyQt6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    settings.set_rollback_enabled(previous_rollback)


def test_update_changes_display_and_inputs_without_mutating_source(rollback_window):
    window, source, dates = rollback_window
    controls = window.rollback_controls
    assert controls.dates.currentData() == source.valuation_date
    controls.dates.setCurrentIndex(1)
    assert window.inputs_tab.export_rollback_overrides() is None
    controls.update.click()
    assert window.inputs_tab.export_rollback_overrides().valuation_date == dates[0]
    assert "ROLLBACK" in window.projection_mode_notice.text()
    assert "08/01/2026" in window._title_label.text()
    assert any(label.text() == "$9,500.00"
               for label in window.policy_tab.fund_values.findChildren(QLabel))
    assert window.inputs_tab._valuation_date == dates[0]
    assert window.policy_tab.rollback_dbo_combo.isEnabled()
    assert source.account_value == 10_000
    assert source.valuation_date == date(2026, 9, 1)
    assert window._last_scenario is None


def test_pending_selection_and_failed_update_keep_applied_basis(rollback_window, monkeypatch):
    from suiteview.illustration.models.input_set import RollbackOverrideSet
    from PyQt6.QtWidgets import QMessageBox

    window, source, dates = rollback_window
    window._on_rollback_update(dates[0])
    window.rollback_controls.dates.setCurrentIndex(2)
    assert "08/01/2026" in window.projection_mode_notice.text()
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[-1]))
    window._apply_rollback_selection(RollbackOverrideSet(valuation_date=date(2025, 1, 1)))
    assert messages and "reliable historical values" in messages[0]
    assert window.inputs_tab.export_rollback_overrides().valuation_date == dates[0]
    assert source.account_value == 10_000


def test_manual_face_and_dbo_are_scenario_only_and_reset_on_date_change(rollback_window):
    from suiteview.illustration.core.scenario_builder import build_illustration_scenario

    window, source, dates = rollback_window
    window._on_rollback_update(dates[0])
    window._on_rollback_amount("coverage", 1, 250_000)
    window._on_rollback_dbo("B")
    overrides = window.inputs_tab.export_rollback_overrides()
    projected = build_illustration_scenario(
        source, rollback_overrides=overrides).projectable_policy
    assert projected.face_amount == 250_000
    assert projected.segments[0].units == 250
    assert projected.db_option == "B"
    assert source.face_amount == 300_000 and source.db_option == "A"
    window._on_rollback_update(dates[1])
    overrides = window.inputs_tab.export_rollback_overrides()
    assert overrides.coverage_amounts == {}
    assert overrides.db_option is None
    window.rollback_controls.dates.setCurrentIndex(0)
    window.rollback_controls.update.click()
    assert window.inputs_tab.export_rollback_overrides() is None
    assert "INFORCE" in window.projection_mode_notice.text()
    assert window.policy_tab.rollback_dbo_combo.isEnabled()
    assert window.policy_tab.account_value_input.value() == source.account_value


def test_saved_case_restores_rollback_display_and_manual_assumptions(
    rollback_window, tmp_path,
):
    from suiteview.illustration.models.case_store import save_case
    from suiteview.illustration.ui.main_window import IllustrationWindow

    window, source, dates = rollback_window
    window._on_rollback_update(dates[0])
    window._on_rollback_amount("coverage", 1, 250_000)
    window._on_rollback_dbo("B")
    case = save_case(
        "Historical Case", policy_number=source.policy_number, company_code="01",
        region="CKPR", inputs=window.inputs_tab.capture_case_inputs(),
        policy_snapshot=source, directory=tmp_path)
    restored = IllustrationWindow()
    try:
        restored._load_case_snapshot(case)
        overrides = restored.inputs_tab.export_rollback_overrides()
        assert overrides.valuation_date == dates[0]
        assert overrides.coverage_amounts == {1: 250_000}
        assert overrides.db_option == "B"
        assert "ROLLBACK" in restored._title_label.text()
        assert "08/01/2026" in restored.policy_tab.snapshot_banner_text()
        assert restored.policy_tab.rollback_dbo_combo.currentData() == "B"
        assert restored._illustration_data.valuation_date == date(2026, 9, 1)
        restored.rollback_controls.dates.setCurrentIndex(0)
        restored.rollback_controls.update.click()
        assert restored.inputs_tab.export_rollback_overrides() is None
        assert "ROLLBACK" not in restored._title_label.text()
        assert "not retrieved live" in restored.policy_tab.snapshot_banner_text()
    finally:
        restored.close()
        restored.deleteLater()


def test_abr_mode_changes_refresh_toolbar_without_applied_rollback(rollback_window):
    from suiteview.illustration.models.app_settings import get_illustration_settings

    window, _, _ = rollback_window
    settings = get_illustration_settings()
    previous = settings.abr_quote_mode
    try:
        settings.set_abr_quote_mode(True)
        assert not window.rollback_controls.dates.isEnabled()
        assert not window.policy_tab.account_value_input.isEnabled()
        settings.set_abr_quote_mode(False)
        assert window.rollback_controls.dates.isEnabled()
        assert window.policy_tab.account_value_input.isEnabled()
    finally:
        settings.set_abr_quote_mode(previous)


@pytest.mark.parametrize("shadow", [0, 11_500])
def test_unrecovered_shadow_is_masked_and_projection_requires_explicit_entry(rollback_window, shadow):
    window, source, dates = rollback_window
    source.ccv_active = True
    source.shadow_account_value = 12_345
    window._on_rollback_update(dates[0])
    assert not window.run_values_btn.isEnabled()
    assert window.run_values_btn.text() == "Shadow Required"
    labels = [label.text() for label in window.policy_tab.fund_values.findChildren(QLabel)]
    assert "Unavailable - enter historical value" in labels
    assert "$12,345.00" not in labels
    editor = window.policy_tab.shadow_value_input
    assert editor.value() == editor.minimum()
    editor.setValue(shadow)
    editor.editingFinished.emit()
    assert window.run_values_btn.isEnabled()
    assert window.inputs_tab.export_rollback_overrides().shadow_account_value == shadow
    captured = window.inputs_tab.capture_case_inputs()
    assert captured["value_rollback"]["shadow_account_value"] == shadow
    assert source.shadow_account_value == 12_345


@pytest.mark.parametrize("historical", [False, True])
@pytest.mark.parametrize("account_value", [8_765.43, 0, -15.25])
def test_inline_value_db_and_coverage_controls_apply_on_current_or_prior_date(
    rollback_window, historical, account_value,
):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from suiteview.illustration.core.scenario_builder import build_illustration_scenario

    window, source, dates = rollback_window
    if historical:
        window._on_rollback_update(dates[0])
    original = deepcopy(source)
    tab = window.policy_tab
    assert tab.account_value_input.isEnabled()
    assert tab.rollback_dbo_combo.isEnabled()
    assert tab.policy_info.isAncestorOf(tab.rollback_dbo_combo)
    assert tab.fund_values.isAncestorOf(tab.account_value_input)
    assert tab.fund_values.isAncestorOf(tab.shadow_value_input)
    tab.account_value_input.setValue(account_value)
    QTest.keyClick(tab.account_value_input, Qt.Key.Key_Return)
    tab.shadow_value_input.setValue(-12.50)
    tab.shadow_value_input.editingFinished.emit()
    tab.rollback_dbo_combo.setCurrentIndex(1)
    tab.rollback_dbo_combo.activated.emit(1)
    tab.coverage_buttons.itemAt(0).widget().click()
    editor = tab._rollback_editor
    assert editor is not None
    assert editor.amount_edit.parentWidget() is not editor
    editor.amount_edit.setValue(250_000)
    editor.apply_button.click()
    overrides = window.inputs_tab.export_rollback_overrides()
    scenario = build_illustration_scenario(source, rollback_overrides=overrides)
    result = scenario.projectable_policy
    assert result.account_value == account_value
    assert result.shadow_account_value == -12.50
    assert result.face_amount == 250_000
    assert result.db_option == "B"
    assert tab.account_value_input.value() == account_value
    assert tab.rollback_dbo_combo.currentData() == "B"
    assert ("ROLLBACK" in window._title_label.text()) == historical
    assert source == original
    window.rollback_controls.dates.setCurrentIndex(0)
    window.rollback_controls.update.click()
    assert window.inputs_tab.export_rollback_overrides() is None
    assert tab.account_value_input.value() == source.account_value
    assert tab.rollback_dbo_combo.currentData() == source.db_option


def test_failed_inline_edit_restores_applied_value(rollback_window, monkeypatch):
    window, source, dates = rollback_window
    window._on_rollback_update(dates[0])
    tab = window.policy_tab
    prior = tab.account_value_input.value()

    def refuse(overrides):
        raise ValueError("Test basis validation failure.")

    monkeypatch.setattr(window.inputs_tab, "set_value_rollback", refuse)
    tab.account_value_input.setValue(1_000)
    tab.account_value_input.editingFinished.emit()
    assert window._test_warnings == ["Test basis validation failure."]
    assert tab.account_value_input.value() == prior
    assert source.account_value == 10_000


def test_saved_current_edits_restore_as_current_not_historical(rollback_window, tmp_path):
    from suiteview.illustration.models.case_store import save_case
    from suiteview.illustration.ui.main_window import IllustrationWindow

    window, source, _ = rollback_window
    window._on_rollback_account(8_765.43)
    window._on_rollback_dbo("B")
    window._on_rollback_amount("coverage", 1, 250_000)
    case = save_case(
        "Edited current values", policy_number=source.policy_number, company_code="01",
        region="CKPR", inputs=window.inputs_tab.capture_case_inputs(),
        policy_snapshot=source, directory=tmp_path)
    restored = IllustrationWindow()
    try:
        restored._load_case_snapshot(case)
        assert restored.rollback_controls.dates.currentData() == source.valuation_date
        assert "ROLLBACK" not in restored._title_label.text()
        assert "EDITED VALUES" in restored._title_label.text()
        assert restored.policy_tab.account_value_input.value() == 8_765.43
        assert restored.policy_tab.rollback_dbo_combo.currentData() == "B"
        assert restored.policy_tab._coverages[0].face_amount == 250_000
        restored.rollback_controls.update.click()
        assert restored.inputs_tab.export_rollback_overrides() is None
        assert restored.policy_tab.account_value_input.value() == source.account_value
    finally:
        restored.close()
        restored.deleteLater()


def test_coverage_editor_reopens_after_header_close_and_can_leave_owner(rollback_window, app):
    from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, Qt
    from PyQt6.QtWidgets import QPushButton

    window, _, dates = rollback_window
    window.show()
    window._on_rollback_update(dates[0])
    tab = window.policy_tab
    for index in range(3):
        tab.coverage_buttons.itemAt(0).widget().click()
        editor = tab._rollback_editor
        assert editor is not None and editor.isVisible()
        assert editor.isWindow()
        assert editor.windowModality() == Qt.WindowModality.NonModal
        assert editor.windowHandle().transientParent() == window.windowHandle()
        editor.move(window.pos() + QPoint(window.width() - 30, 30))
        app.processEvents()
        assert not window.frameGeometry().contains(editor.frameGeometry())
        if index == 0:
            close = next(button for button in editor.header_bar.findChildren(QPushButton)
                         if button.toolTip() == "Close")
            close.click()
        else:
            editor.close()
        assert tab._rollback_editor is None
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert window.isEnabled()
        assert tab.account_value_input.isEnabled()


def test_rollback_option_restores_normal_view_and_clears_inactive_basis(rollback_window):
    from suiteview.illustration.models.app_settings import IllustrationSettings
    from suiteview.illustration.models.input_set import RollbackOverrideSet
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab
    from suiteview.illustration.ui.presenter import IllustrationSessionState

    assert IllustrationSettings().rollback_enabled is False
    window, source, dates = rollback_window
    window._on_rollback_update(dates[0])
    inactive = IllustrationInputsTab(window)
    inactive.load_data_from_policy(source)
    inactive.rollback_changed.connect(window._on_rollback_changed)
    inactive.set_value_rollback(RollbackOverrideSet(dates[1]))
    entry = IllustrationSessionState(
        input_draft=inactive.read_draft(),
        values={"old": "values"},
        report={"old": "report"},
        status="old status",
        scenario="old scenario",
    )
    window._session_states[("inactive", "CKPR", "01")] = entry
    window._rollback_action.trigger()
    assert not window.rollback_controls.isVisibleTo(window)
    assert window.inputs_tab.export_rollback_overrides() is None
    assert inactive.export_rollback_overrides() is None
    assert entry.input_draft.rollback_overrides is None
    assert entry.input_draft.case_inputs["value_rollback"] is None
    assert all(getattr(entry, key) is None for key in ("values", "report", "status", "scenario"))
    tab = window.policy_tab
    assert not tab.account_value_input.isVisibleTo(tab)
    assert not tab.shadow_value_input.isVisibleTo(tab)
    assert not tab.rollback_dbo_combo.isVisibleTo(tab)
    assert tab.fund_values.fund_account_value.isVisibleTo(tab)
    assert tab.policy_info.db_option_label.isVisibleTo(tab)
    assert not tab.rollback_edit_note.isVisibleTo(tab)
    assert tab.fund_values.get_value("fund_account_value") == "$10,000.00"
    assert "ROLLBACK" not in window._title_label.text()
    with pytest.raises(ValueError, match="Options > Edit Record"):
        window.inputs_tab.set_value_rollback(RollbackOverrideSet(dates[0]))
    window._rollback_action.trigger()
    assert window.rollback_controls.dates.currentData() == source.valuation_date
    assert tab.account_value_input.isVisibleTo(tab)


def test_historical_theme_and_editing_follow_each_applied_date(rollback_window):
    from suiteview.illustration.ui.styles import ILLUSTRATION_HEADER_COLORS
    from suiteview.illustration.ui.value_rollback import ROLLBACK_COLORS

    window, source, dates = rollback_window
    assert window._header_colors == ILLUSTRATION_HEADER_COLORS
    window.rollback_controls.dates.setCurrentIndex(1)
    assert window._header_colors == ILLUSTRATION_HEADER_COLORS
    for when in [*dates, source.valuation_date]:
        window._on_rollback_update(when)
        assert window.policy_tab.account_value_input.isEnabled()
        assert window.policy_tab.shadow_value_input.isEnabled()
        assert window.policy_tab.rollback_dbo_combo.isEnabled()
        historical = when != source.valuation_date
        assert window._header_colors == (ROLLBACK_COLORS if historical else ILLUSTRATION_HEADER_COLORS)
        window.policy_tab.account_value_input.setValue(8_765)
        window.policy_tab.account_value_input.editingFinished.emit()
        assert window.inputs_tab.export_rollback_overrides().account_value == 8_765
    assert ROLLBACK_COLORS[-1] == "#FFFFFF"


def test_saved_rollback_case_requires_option_for_load_and_compare(rollback_window, tmp_path):
    from suiteview.illustration.models.case_store import save_case
    from suiteview.illustration.ui.saved_case_scenario import materialize_saved_case

    window, source, dates = rollback_window
    window._on_rollback_update(dates[0])
    case = save_case(
        "Opt-in rollback", policy_number=source.policy_number, company_code="01",
        region="CKPR", inputs=window.inputs_tab.capture_case_inputs(),
        policy_snapshot=source, directory=tmp_path)
    window._rollback_action.trigger()
    window._load_case_snapshot(case)
    assert window._test_warnings and "Options > Edit Record" in window._test_warnings[-1]
    assert window.inputs_tab.export_rollback_overrides() is None
    with pytest.raises(ValueError, match="Options > Edit Record"):
        materialize_saved_case(case)


def test_total_only_rollback_funds_are_labeled_and_restore_loaded_buckets(app):
    from suiteview.illustration.core.value_rollback import apply_value_rollback
    from suiteview.illustration.ui.policy_tab import IllustrationPolicyTab
    from tests.test_value_rollback_data import _policy, _complete_snapshot, WHEN

    policy = _policy()
    policy.product_type = "IUL"
    policy.plancode = "1U145500"
    policy.fund_values = {"SW": 2_000, "M1": 18_000}
    policy.premium_allocations = {"M1": 1.0}
    policy.rollback_snapshots = [_complete_snapshot()]
    tab = IllustrationPolicyTab()
    try:
        tab.load_data_from_snapshot(apply_value_rollback(policy, WHEN))
        assert tab.historical_funds_notice.isVisibleTo(tab)
        assert tab.unimpaired_table.rowCount() == 0
        assert tab.impaired_table.rowCount() == 0
        assert tab.allocation_table.rowCount() == 1
        assert any(label.text() == "$10,000.00"
                   for label in tab.fund_values.findChildren(QLabel))
        tab.load_data_from_snapshot(policy)
        assert not tab.historical_funds_notice.isVisibleTo(tab)
        assert tab.unimpaired_table.rowCount() == 2
    finally:
        tab.deleteLater()
