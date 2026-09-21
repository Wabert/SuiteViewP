import os
import gc
import weakref
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtWidgets import QAbstractItemView, QLineEdit, QMessageBox

from suiteview.audit.tabs import other_queries_tab as ui
from tools.app.verify_other_queries import _text_pixels


@pytest.fixture
def tab(qtbot):
    # Collect previous QObject graphs here, not only at application shutdown.
    gc.collect()
    widget = ui.OtherQueriesTab(lambda: "CKPR")
    qtbot.addWidget(widget)
    return widget


def test_panels_uppercase_and_persist_independent_inputs(tab):
    riders, bases, values = (tab.panels[name] for name in ("riders", "bases", "values"))
    riders.inputs["plancode"].setText("base")
    bases.inputs["plancode"].setText("rider")
    bases.show_policies.setChecked(True)
    values.inputs["table"].setText("lh_bas_pol")
    values.inputs["field"].setText("ck_cmp_cd")
    state = tab.get_state()
    tab.set_state({})
    tab.set_state(state)
    assert tab.get_state() == state
    assert riders.inputs["plancode"].text() == "BASE"
    assert not riders.show_policies.isChecked() and bases.show_policies.isChecked()
    assert values.inputs["table"].text() == "LH_BAS_POL"


def test_view_sql_uses_own_inputs_and_region(tab):
    panel = tab.panels["riders"]
    panel.inputs["plancode"].setText("BASE")
    receiver = Mock()
    tab.sql_requested.connect(receiver)
    panel.btn_sql.click()
    receiver.assert_called_once()
    assert "B.PLN_DES_SER_CD = 'BASE'" in receiver.call_args.args[0]
    assert "COUNT(*)" in receiver.call_args.args[0]


def test_invalid_input_does_not_start_query(tab, monkeypatch):
    run = Mock()
    warning = Mock()
    monkeypatch.setattr(ui, "run_query_async", run)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    tab.panels["values"].btn_find.click()
    run.assert_not_called()
    warning.assert_called_once()


def test_run_captures_request_and_drops_stale_response(tab, monkeypatch):
    pending = {}
    monkeypatch.setattr(ui, "run_query_async", lambda **kwargs: pending.update(kwargs))
    panel = tab.panels["riders"]
    panel.inputs["plancode"].setText("BASE")
    panel.btn_find.click()
    result = pd.DataFrame([["BASE", "BF", "RIDER", "RF", 2]], columns=panel.query().columns)
    pending["on_success"](result)
    assert panel.table.get_filtered_dataframe().equals(result)
    assert panel.btn_excel.isEnabled()
    panel.show_policies.setChecked(True)
    pending["on_success"](result)
    assert panel.table.get_filtered_dataframe().empty
    assert not panel.btn_excel.isEnabled()
    assert "changed" in panel.status.text()
    assert not tab.panels["bases"].show_policies.isChecked()


def test_failure_and_region_change_clear_results(tab, monkeypatch):
    pending = {}
    monkeypatch.setattr(ui, "run_query_async", lambda **kwargs: pending.update(kwargs))
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    panel = tab.panels["riders"]
    panel.inputs["plancode"].setText("BASE")
    panel.btn_find.click()
    pending["on_error"](RuntimeError("Connection unavailable"))
    assert "failed" in panel.status.text()
    warning.assert_called_once()
    assert panel.table.get_filtered_dataframe().empty
    assert not panel.btn_excel.isEnabled()
    tab.invalidate()
    pending["on_success"](pd.DataFrame([["BASE", "BF", "RIDER", "RF", 1]], columns=panel.query().columns))
    assert panel.table.get_filtered_dataframe().empty


def test_export_uses_unsaved_workbook_and_preserves_codes(tab, monkeypatch):
    export = Mock()
    monkeypatch.setattr(ui, "dump_to_new_workbook", export)
    panel = tab.panels["bases"]
    columns = ["Rider Plancode", "Rider Form", "Base Plancode", "Base Form", "Policy Number", "Company"]
    panel._set_results(pd.DataFrame([["RIDER", "01", "BASE", None, "000123456", "01"]], columns=columns))
    panel.btn_excel.click()
    assert export.call_args.args == (columns, [("RIDER", "01", "BASE", None, "000123456", "01")])
    assert export.call_args.kwargs["text_col_indexes"] == [1, 2, 3, 4, 5, 6]
    tab.set_state({})
    assert all(p.table.get_filtered_dataframe().empty and not p.btn_excel.isEnabled() for p in tab.panels.values())


def test_panels_release_native_widgets_and_python_wrappers(qapp):
    for _ in range(5):
        widget = ui.OtherQueriesTab(lambda: "CKPR")
        widget.panels["riders"].inputs["plancode"].setText("BASE")
        widget.set_state(widget.get_state())
        native = [
            widget,
            *widget.panels.values(),
            *(panel.table for panel in widget.panels.values()),
            *(panel.show_policies for panel in widget.panels.values()),
        ]
        references = [weakref.ref(item) for item in native]
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert all(sip.isdeleted(item) for item in native)
        del native, widget
        gc.collect()
        assert all(reference() is None for reference in references)


@pytest.mark.parametrize("kind", ["riders", "bases", "values"])
def test_result_cells_never_open_editors_or_change_on_click(tab, qtbot, kind):
    panel = tab.panels[kind]
    if kind == "values":
        panel.inputs["table"].setText("LH_BAS_POL")
        panel.inputs["field"].setText("CK_CMP_CD")
        rows = [("01", 868)]
    else:
        panel.inputs["plancode"].setText("PLAN")
        rows = [("PLAN", "FORM", "OTHER", "OTHERFORM", 868)]
    frame = pd.DataFrame(rows, columns=panel.query().columns)
    panel._set_results(frame)
    tab.resize(1215, 620)
    tab.show()
    view = panel.table.table_view
    index = view.model().index(0, 0)
    qtbot.waitUntil(lambda: view.visualRect(index).isValid())
    text_pixels = _text_pixels(view, index)
    position = view.visualRect(index).center()
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=position)
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=position)
    qtbot.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=position)
    qtbot.keyClick(view, Qt.Key.Key_F2)
    qtbot.keyClicks(view, "changed")
    assert view.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert panel.table.frozen_table_view.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert view.state() != QAbstractItemView.State.EditingState
    assert not any(editor.isVisible() for editor in view.findChildren(QLineEdit))
    assert view.model().data(index) == rows[0][0]
    assert panel.table.get_filtered_dataframe().equals(frame)
    assert view.selectionModel().hasSelection()
    assert text_pixels
    assert len(text_pixels & _text_pixels(view, index)) >= 0.8 * len(text_pixels)
