"""Soft-launch business mode (M1): one switch hides/locks the developer surface.

Business mode is on in the packaged EXE for users without support privileges,
or in any run with SUITEVIEW_ILLUSTRATION_BUSINESS_MODE=1. Developers (source
runs, ADMIN/SUPPORT roles) keep every control.
"""
import os
from datetime import date
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import suiteview.illustration.core.business_mode as bm
from suiteview.illustration.core.business_mode import (
    BUSINESS_LOCKED_OPTIONS,
    BUSINESS_MODE_ENV,
    is_business_mode,
)
from suiteview.illustration.models.app_settings import get_illustration_settings
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab
from suiteview.illustration.ui.main_window import IllustrationWindow
from suiteview.illustration.ui.values_tab import IllustrationValuesTab

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


@pytest.fixture
def business(monkeypatch):
    monkeypatch.setenv(BUSINESS_MODE_ENV, "1")
    yield
    settings = get_illustration_settings()
    settings.set_additional_premium_types(False)


@pytest.fixture
def developer(monkeypatch):
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)


class _Policy:
    """Just enough policy surface for the inputs tab."""

    issue_date = date(2019, 11, 9)
    base_issue_age = 50
    attained_age = 56
    valuation_date = date(2026, 5, 9)
    policy_year = 7
    duration = 79
    maturity_age = 121
    billing_frequency = 1
    modal_premium = 153.56
    def_of_life_ins = "GPT"
    glp = 1200.0
    accumulated_glp = 5000.0
    premiums_paid_to_date = 10000.0
    withdrawals_to_date = 1000.0
    base_rate_class = "N"
    base_table_rating = 2
    base_plancode = "1U135D00"

    def __init__(self):
        self.coverages = SimpleNamespace(get_coverages=lambda: [])
        self.benefits = SimpleNamespace(get_benefits=lambda: [])


# ── the switch ───────────────────────────────────────────────────────


def test_source_runs_are_developer_mode(developer):
    assert is_business_mode() is False


def test_env_override_forces_business_mode(business):
    assert is_business_mode() is True


def test_env_override_only_honors_exact_one(monkeypatch):
    for value in ("true", "yes", "0", "on", ""):
        monkeypatch.setenv(BUSINESS_MODE_ENV, value)
        assert is_business_mode() is False, value


def test_packaged_user_without_support_privileges_is_business(developer, monkeypatch):
    monkeypatch.setattr(bm, "has_support_privileges", lambda: False)
    assert is_business_mode() is True
    monkeypatch.setattr(bm, "has_support_privileges", lambda: True)
    assert is_business_mode() is False


def test_unverifiable_permissions_fail_closed(developer, monkeypatch):
    def boom():
        raise RuntimeError("UL_Rates unreachable")

    monkeypatch.setattr(bm, "has_support_privileges", boom)
    assert is_business_mode() is True


# ── window ───────────────────────────────────────────────────────────


def test_business_window_hides_menus_and_locks_region(business):
    _app()
    win = IllustrationWindow()
    assert win.business_mode is True
    assert win.options_btn.isHidden()
    assert win.hamburger_btn.isHidden()
    assert win.lookup_bar.region_input.isReadOnly()
    assert win.lookup_bar.region_input.text() == "CKPR"
    assert win.values_tab.business_mode is True
    win.show_plancode_table()
    assert win._plancode_table_window is None
    settings = get_illustration_settings()
    assert not (settings.additional_premium_types or settings.testing_mode
                or settings.abr_quote_mode or settings.rollback_enabled)


def test_business_window_forces_production_region(business, monkeypatch):
    _app()
    win = IllustrationWindow()
    seen = []
    monkeypatch.setattr(win.lookup_bar, "_on_get_policy", lambda: seen.append(
        win.lookup_bar.region_input.text()))
    win.load_policy("UL000001", region="CKAS")
    assert seen == ["CKPR"]


def test_developer_window_keeps_every_control(developer):
    _app()
    win = IllustrationWindow()
    assert win.business_mode is False
    assert not win.options_btn.isHidden()
    assert not win.hamburger_btn.isHidden()
    assert not win.lookup_bar.region_input.isReadOnly()
    assert win.values_tab.business_mode is False


# ── inputs tab ───────────────────────────────────────────────────────


def _locked_values(tab: IllustrationInputsTab) -> dict:
    return {
        "enable": tab.enable_illustration_options_check.isChecked(),
        "tefra": tab.tefra_check.isChecked(),
        "stop": tab.stop_on_lapse_check.isChecked(),
        "option_a": tab.switch_to_option_a_check.isChecked(),
        "exact": tab.exact_days_check.isChecked(),
        "gp_search": tab.gp_search_check.isChecked(),
        "levelizing": tab.levelizing_check.isChecked(),
        "principal_first": tab.loan_principal_first_check.isChecked(),
        "ag49": tab.policy_ag49_check.isChecked(),
        "tamra": tab.dynamic_panel.tamra_check.isChecked(),
    }


_STANDARD = {
    "enable": False, "tefra": True, "stop": True, "option_a": False,
    "exact": False, "gp_search": False, "levelizing": True,
    "principal_first": False, "ag49": False, "tamra": True,
}


def test_business_inputs_tab_hides_and_locks(business):
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_Policy())
    assert tab.business_mode is True
    assert tab.run_from_issue_btn.isHidden()
    assert not tab.input_tabs.isTabVisible(tab.input_tabs.indexOf(tab.issue_conditions))
    assert not tab.grid_inputs_tab_visible()
    assert tab.input_tabs.tabBar().contextMenuPolicy() == Qt.ContextMenuPolicy.NoContextMenu
    tab._set_grid_inputs_tab_visible(True)
    assert not tab.grid_inputs_tab_visible()
    for widget in tab._business_locked_widgets():
        assert not widget.isEnabled(), widget.text()
    assert not tab.business_lock_note.isHidden()
    assert _locked_values(tab) == _STANDARD


def test_business_saved_case_cannot_unlock_developer_settings(business, developer_case):
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_Policy())
    warnings = tab.apply_case_inputs(developer_case)
    assert _locked_values(tab) == _STANDARD
    assert any("Grid Inputs" in warning for warning in warnings)
    options = tab.export_options()
    for name, value in BUSINESS_LOCKED_OPTIONS.items():
        assert getattr(options, name) == value, name
    draft = tab.read_draft()
    assert draft.controls.stop_on_lapse is True
    assert draft.controls.run_from_issue is False
    assert draft.controls.abr_quote is False
    assert draft.input_set.dated_transactions == []


def test_business_refuses_from_issue_and_edit_record_cases(business, developer_case):
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_Policy())
    from_issue = dict(developer_case, controls=dict(
        developer_case["controls"], run_from_issue=True))
    with pytest.raises(ValueError, match="New Business"):
        tab.apply_case_inputs(from_issue)
    with pytest.raises(ValueError, match="Edit Record"):
        tab.apply_case_inputs(dict(developer_case, value_rollback={}))


def test_business_abr_quote_setting_is_ignored(business):
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_Policy())
    settings = get_illustration_settings()
    try:
        settings.set_abr_quote_mode(True)
        assert tab.abr_quote_enabled() is False
        assert not tab.dynamic_panel.tamra_check.isEnabled()
        assert tab.dynamic_panel.premium_section.isEnabled()
    finally:
        settings.set_abr_quote_mode(False)


@pytest.fixture
def developer_case(monkeypatch):
    """A saved-case state captured by a developer with every option changed."""
    _app()
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_Policy())
    tab.enable_illustration_options_check.setChecked(True)
    tab.tefra_check.setChecked(False)
    tab.stop_on_lapse_check.setChecked(False)
    tab.switch_to_option_a_check.setChecked(True)
    tab.exact_days_check.setChecked(True)
    tab.gp_search_check.setChecked(True)
    tab.levelizing_check.setChecked(False)
    tab.loan_principal_first_check.setChecked(True)
    tab.policy_ag49_check.setChecked(True)
    tab.dynamic_panel.tamra_check.setChecked(False)
    tab._set_grid_inputs_tab_visible(True)
    from PyQt6.QtWidgets import QTableWidgetItem
    tab.withdrawal_table.setItem(0, 0, QTableWidgetItem("06/09/2027"))
    tab.withdrawal_table.setItem(0, 1, QTableWidgetItem("1000"))
    state = tab.capture_case_inputs()
    assert state["controls"]["exact_days"] is True
    assert state["grids"]["withdrawals"]
    monkeypatch.setenv(BUSINESS_MODE_ENV, "1")
    return state


def test_developer_inputs_tab_unchanged(developer):
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_Policy())
    assert tab.business_mode is False
    assert not tab.run_from_issue_btn.isHidden()
    assert tab.input_tabs.isTabVisible(tab.input_tabs.indexOf(tab.issue_conditions))
    assert tab.exact_days_check.isEnabled()
    assert tab.enable_illustration_options_check.isEnabled()
    assert tab.dynamic_panel.tamra_check.isEnabled()
    assert tab.business_lock_note.isHidden()
    tab.exact_days_check.setChecked(True)
    assert tab.export_options().exact_days_interest is True


# ── values tab ───────────────────────────────────────────────────────


def _nav_titles(values: IllustrationValuesTab) -> list[str]:
    return [values.nav_tree.topLevelItem(i).text(0)
            for i in range(values.nav_tree.topLevelItemCount())]


def test_business_values_tab_hides_debug_groups():
    _app()
    values = IllustrationValuesTab()
    values.set_business_mode(True)
    values._rebuild_navigator({values.SUMMARY_GROUP: list(values.SUMMARY_COLUMNS)})
    assert _nav_titles(values) == ["Overview", "Chart", "Charges"]
    assert values.nav_search.isHidden()
    values._drill_down(0, "Account Value")
    assert values.content_stack.currentWidget() is values.overview


def test_developer_values_tab_keeps_debug_groups():
    _app()
    values = IllustrationValuesTab()
    values._rebuild_navigator({values.SUMMARY_GROUP: list(values.SUMMARY_COLUMNS)})
    titles = _nav_titles(values)
    assert values.SUMMARY_GROUP in titles
    assert values.TEFRA_TAMRA_RECALC_GROUP in titles


# ── Illustrated Rate blank handling (M2) ────────────────────────────


def test_business_blank_rate_exports_none_for_the_run_gate(business):
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_Policy())
    tab.dynamic_panel.illustrated_rate_edit.setText("")
    assert tab.illustrated_rate_blank()
    assert tab.export_inforce_overrides().current_interest_rate is None


def test_developer_blank_rate_keeps_zero(developer):
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_Policy())
    tab.dynamic_panel.illustrated_rate_edit.setText("")
    assert tab.export_inforce_overrides().current_interest_rate == 0.0
    tab.dynamic_panel.illustrated_rate_edit.setText("4.5")
    assert tab.export_inforce_overrides().current_interest_rate == pytest.approx(0.045)
