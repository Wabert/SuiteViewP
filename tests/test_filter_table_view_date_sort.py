"""FilterTableView sorts MM/DD/YYYY text columns as dates, not text."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from suiteview.ui.widgets.filter_table_view import FilterPopup, FilterTableView

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


DATES = ["01/15/2016", "01/16/2007", "", "12/31/9999", "01/17/2009", "1/2/2010", None]


def _sorted_column(df, column, order):
    _app()
    view = FilterTableView()
    view.set_dataframe(df, limit_rows=False)
    view.apply_sort(list(df.columns).index(column), order)
    return [df.loc[i, column] for i in view.model._display_indices]


def test_date_text_column_sorts_chronologically_with_blanks_last():
    df = pd.DataFrame({"NXT_CHG_DT": DATES})
    assert _sorted_column(df, "NXT_CHG_DT", Qt.SortOrder.AscendingOrder)[:5] == [
        "01/16/2007", "01/17/2009", "1/2/2010", "01/15/2016", "12/31/9999"]
    assert _sorted_column(df, "NXT_CHG_DT", Qt.SortOrder.DescendingOrder)[:5] == [
        "12/31/9999", "01/15/2016", "1/2/2010", "01/17/2009", "01/16/2007"]


def test_mixed_text_column_keeps_text_sort():
    df = pd.DataFrame({"CODE": ["01/15/2016", "B", "A"]})
    assert _sorted_column(df, "CODE", Qt.SortOrder.AscendingOrder) == [
        "01/15/2016", "A", "B"]


def test_numeric_column_sort_unchanged():
    df = pd.DataFrame({"AGE": [26, 9, 101]})
    assert _sorted_column(df, "AGE", Qt.SortOrder.AscendingOrder) == [9, 26, 101]


def test_filter_popup_lists_dates_chronologically():
    _app()
    popup = FilterPopup("ISSUEDT", ["01/17/1963", "01/15/1971", None, "01/16/1968"])
    assert popup.all_unique_values == [
        "01/17/1963", "01/16/1968", "01/15/1971", "(Blanks)"]
