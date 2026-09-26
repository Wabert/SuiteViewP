"""Focused UI behavior tests for Rate Manager controls."""

from pathlib import Path

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

from suiteview.ratemanager.ui_helpers import (
    set_expanding_panel_visible, update_cease_age_field,
)
from suiteview.ratemanager.database_panel import RateDatabasePanel
from suiteview.ratemanager.ratemanager_window import RateManagerWindow
from suiteview.ratemanager.product_chooser import TERM_LINE, UL_LINE
from suiteview.ratemanager.workup.workup_window import RateWorkupPanel


def test_tools_menu_uses_runtime_rate_manager_permission():
    ui_source = (
        Path(__file__).parents[1]
        / "suiteview"
        / "taskbar_launcher"
        / "taskbar_ui.py"
    ).read_text(encoding="utf-8")
    system_source = (
        Path(__file__).parents[1]
        / "suiteview"
        / "taskbar_launcher"
        / "taskbar_system.py"
    ).read_text(encoding="utf-8")

    assert '("RATEMANAGER", "Rate Manager", self.callbacks._open_rate_manager)' in ui_source
    assert '@requires_app_access("RATEMANAGER")' in system_source


_QT_APP = QApplication.instance() or QApplication([])


def test_cease_age_field_tracks_include_state():
    edit = QLineEdit()

    update_cease_age_field(False, edit)
    assert not edit.isEnabled()
    assert edit.text() == "Not required"

    update_cease_age_field(True, edit)
    assert edit.isEnabled()
    assert edit.text() == ""
    assert edit.placeholderText() == "Required"

    edit.setText("65")
    update_cease_age_field(False, edit)
    assert edit.text() == "Not required"
    update_cease_age_field(True, edit)
    assert edit.text() == "65"


def test_workup_cease_age_column_is_wide_and_rows_sync_state():
    panel = RateWorkupPanel()
    panel._add_benefit_row(
        0, "21", "coi 10 - trg 10", [], checked=False, has_iaf_coi=True)

    _code, include, renewable, cease, _mpf, _index, _has_coi = (
        panel._ben_rows[0])
    assert panel.ben_table.columnWidth(2) >= 100
    assert cease.text() == "Not required"

    include.setChecked(True)
    assert cease.isEnabled()
    assert cease.placeholderText() == "Required"

    renewable.setChecked(True)
    assert cease.isEnabled()
    assert cease.placeholderText() == "Required"


def test_processing_output_grows_and_restores_window():
    window = QWidget()
    layout = QVBoxLayout(window)
    layout.addWidget(QLineEdit())
    panel = QLineEdit()
    panel.setFixedHeight(100)
    panel.setVisible(False)
    layout.addWidget(panel)
    window.resize(400, 300)
    window.show()
    _QT_APP.processEvents()

    collapsed_height = window.height()
    set_expanding_panel_visible(window, panel, True)
    _QT_APP.processEvents()
    assert panel.isVisible()
    assert window.height() > collapsed_height

    set_expanding_panel_visible(window, panel, False)
    _QT_APP.processEvents()
    assert not panel.isVisible()
    assert window.height() == collapsed_height


def test_database_panel_exposes_all_workup_tables():
    panel = RateDatabasePanel()

    assert list(panel.load_tab._controls) == [
        "POINT_PVSRB",
        "RATE_COI",
        "RATE_TRGPREM",
        "RATE_SCR",
        "RATE_EPU",
        "POINT_BENEFIT",
        "RATE_BENCOI",
        "RATE_BENTRG",
    ]
    assert not panel.load_tab.apply_btn.isEnabled()


def test_rate_manager_has_workup_database_and_converter_views():
    window = RateManagerWindow()

    assert window._stack.currentWidget() is window.chooser
    window._on_line_chosen(UL_LINE)
    assert window._stack.currentWidget() is window.workup_panel
    window._show_database()
    assert window._stack.currentWidget() is window.database_panel
    window._show_converters()
    assert window._stack.currentIndex() == window._ul_pages[2]
    window._show_workup()
    assert window._stack.currentWidget() is window.workup_panel
    window._on_line_chosen(TERM_LINE)
    assert window._stack.currentWidget() is window.term_workup_panel
    window._show_database()
    assert window._stack.currentWidget() is window.term_database_panel
