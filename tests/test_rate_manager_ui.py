"""Focused UI behavior tests for Rate Manager controls."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

from suiteview.ratemanager.ui_helpers import (
    set_expanding_panel_visible, update_cease_age_field,
)
from suiteview.ratemanager.workup.workup_window import RateWorkupPanel


_QT_APP = QApplication.instance() or QApplication([])


def test_cease_age_field_tracks_include_and_renewable_state():
    edit = QLineEdit()

    update_cease_age_field(False, False, True, edit)
    assert not edit.isEnabled()
    assert edit.text() == "Not required"

    update_cease_age_field(True, False, True, edit)
    assert edit.isEnabled()
    assert edit.text() == ""
    assert edit.placeholderText() == "Required"

    edit.setText("65")
    update_cease_age_field(True, True, True, edit)
    assert edit.text() == "Not required"

    update_cease_age_field(True, False, True, edit)
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
    assert not cease.isEnabled()
    assert cease.text() == "Not required"


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
