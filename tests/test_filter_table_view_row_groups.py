"""FilterTableView current-row tint and column-group divider rules."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from suiteview.ui.widgets.filter_table_view import FilterTableView

_QT_APP = None
TINT = "#E6F0FA"
RULE = "#1B5E20"


def _grid() -> FilterTableView:
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    grid = FilterTableView()
    grid.apply_ledger_style()
    columns = ["Year", "C COI", "C EPU", "G COI", "G EPU", "Note"]
    grid.set_dataframe(pd.DataFrame({name: [1, 2, 3, 4] for name in columns}))
    grid.set_column_groups([("C", ["C COI", "C EPU"]), ("G", ["G COI", "G EPU"])])
    grid.set_current_row_highlight(TINT)
    grid.set_group_dividers(RULE)
    for column in range(len(columns)):
        grid.table_view.setColumnWidth(column, 60)
    grid.resize(500, 200)
    grid.show()
    _QT_APP.processEvents()
    return grid


def _pixel(grid, row: int, column: int, dx: int) -> QColor:
    view = grid.table_view
    rect = view.visualRect(grid.model.index(row, column))
    image = view.viewport().grab().toImage()
    return QColor(image.pixel(rect.left() + dx, rect.center().y()))


def test_group_rules_mark_each_block_boundary():
    grid = _grid()
    edges = [grid._group_edges(grid.table_view, column) for column in range(6)]
    assert edges == [(False, False), (True, False), (False, False),
                     (True, False), (False, True), (False, False)]
    assert _pixel(grid, 0, 1, 0) == QColor(RULE)
    assert _pixel(grid, 0, 3, 1) == QColor(RULE)
    assert _pixel(grid, 0, 2, 0) != QColor(RULE)


def test_clicked_row_is_tinted_across_the_row_but_the_cell_keeps_selection():
    grid = _grid()
    selection = grid.table_view.selectionModel()
    selection.setCurrentIndex(grid.model.index(2, 2), QItemSelectionModel.SelectionFlag.ClearAndSelect)
    _QT_APP.processEvents()
    assert grid._highlighted_row() == 2
    assert _pixel(grid, 2, 5, 20) == QColor(TINT)
    assert _pixel(grid, 2, 0, 20) == QColor(TINT)
    assert _pixel(grid, 1, 5, 20) != QColor(TINT)
    assert _pixel(grid, 2, 2, 20) != QColor(TINT)  # the selected cell shows the selection color
    assert selection.selectedIndexes() == [grid.model.index(2, 2)]


def test_group_columns_widen_so_the_band_label_is_not_elided():
    from PyQt6.QtGui import QFontMetrics

    grid = _grid()
    grid.set_column_groups([("Guaranteed", ["G COI"])])
    grid.table_view.setColumnWidth(3, 20)
    grid.fit_column_groups_to_labels(padding=12)
    needed = QFontMetrics(grid.header.wrap_font()).horizontalAdvance("Guaranteed") + 12
    assert grid.table_view.columnWidth(3) >= needed
    wide = grid.table_view.columnWidth(3)
    grid.fit_column_groups_to_labels(padding=12)
    assert grid.table_view.columnWidth(3) == wide


def test_group_backgrounds_alternate_light_and_darker_green_and_the_current_row_paints_over_them():
    from suiteview.polview.ui.tabs.raw_table_tab import GROUP_TINTS, alternating_group_tints

    grid = _grid()
    grid.set_group_dividers(None)
    groups = [("Current", ["C COI"]), ("Guaranteed", ["C EPU", "G COI"]), ("Dividend", ["G EPU"])]
    grid.set_column_groups(groups)
    tints = alternating_group_tints(groups)
    assert tints == {"Current": GROUP_TINTS[0], "Guaranteed": GROUP_TINTS[1], "Dividend": GROUP_TINTS[0]}
    grid.set_group_backgrounds(tints)
    _QT_APP.processEvents()
    assert _pixel(grid, 0, 1, 20) == QColor(GROUP_TINTS[0])
    assert _pixel(grid, 0, 3, 20) == QColor(GROUP_TINTS[1])
    assert _pixel(grid, 0, 4, 20) == QColor(GROUP_TINTS[0])
    assert _pixel(grid, 0, 5, 20) == QColor("white")
    grid.table_view.selectionModel().setCurrentIndex(
        grid.model.index(1, 0), QItemSelectionModel.SelectionFlag.ClearAndSelect)
    _QT_APP.processEvents()
    assert _pixel(grid, 1, 3, 20) == QColor(TINT)
    light, dark = (QColor(tint).lightness() for tint in GROUP_TINTS)
    assert light > dark >= 200


def test_decorations_are_opt_in_and_can_be_turned_off():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    plain = FilterTableView()
    assert plain._row_group_delegates == []
    grid = _grid()
    grid.set_current_row_highlight(None)
    grid.set_group_dividers(None)
    assert grid._row_highlight is None and grid._group_divider is None
    assert _pixel(grid, 0, 1, 0) != QColor(RULE)
