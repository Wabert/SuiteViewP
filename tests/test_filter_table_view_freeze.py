"""FilterTableView freeze-pane + read-only ledger behavior."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PyQt6.QtWidgets import QApplication

import suiteview.ui.widgets.filter_table_view as ftv
from suiteview.ui.widgets.filter_table_view import FilterTableView

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _grid(cols: int = 8, rows: int = 5) -> FilterTableView:
    _app()
    grid = FilterTableView()
    grid.set_frozen_column_count(2)
    grid.set_dataframe(pd.DataFrame({f"C{i}": list(range(rows)) for i in range(cols)}))
    return grid


def test_filtering_enabled_by_default():
    grid = _grid()
    assert grid._filtering_enabled is True


def test_filtering_disabled_blocks_filter_popup(monkeypatch):
    grid = _grid()
    grid.set_filtering_enabled(False)

    def boom(*args, **kwargs):
        raise AssertionError("filter popup must not open when filtering is disabled")

    monkeypatch.setattr(ftv, "FilterPopup", boom)
    grid.show_filter_popup(0)  # must return early, not build a popup
    assert grid.column_filters == {}


def test_frozen_bottom_spacer_reflects_computed_inset():
    grid = _grid()
    grid.resize(120, 200)
    grid.table_view.setColumnWidth(2, 400)
    grid._sync_frozen_bottom_inset()

    # The spacer (a real layout widget, not a viewport margin Qt can clobber)
    # always carries the reserved inset so the frozen rows stay aligned.
    assert grid.frozen_bottom_spacer.height() == grid._frozen_bottom_inset


def test_full_row_selection_sets_behavior_on_both_panes():
    from PyQt6.QtWidgets import QTableView

    grid = _grid()
    grid.set_full_row_selection(True)
    assert grid.table_view.selectionBehavior() == QTableView.SelectionBehavior.SelectRows
    assert grid.frozen_table_view.selectionBehavior() == QTableView.SelectionBehavior.SelectRows
