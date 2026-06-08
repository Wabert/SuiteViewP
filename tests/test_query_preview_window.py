"""Offscreen-Qt tests for the DataForge QueryPreviewWindow.

Forces ``QT_QPA_PLATFORM=offscreen`` so it runs headless on the minipc; if
PyQt6 is unavailable the module is skipped, not failed.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from suiteview.ui.widgets.frameless_window import FramelessWindowBase  # noqa: E402
from suiteview.audit.dataforge._query_preview_window import (  # noqa: E402
    QueryPreviewWindow, _PREVIEW_LIMIT,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _df(n: int) -> pd.DataFrame:
    return pd.DataFrame({"policy": [f"P{i}" for i in range(n)],
                         "amount": list(range(n))})


def test_is_frameless_window(app):
    win = QueryPreviewWindow("My Query", _df(3))
    try:
        assert isinstance(win, FramelessWindowBase)
        # Base class provides the live W×H footer label.
        assert hasattr(win, "_size_label")
        # Branded purple header, house gold border.
        assert win._border_color == "#D4A017"
        assert win._header_colors[0] == "#7C3AED"
    finally:
        win.deleteLater()


def test_small_df_shows_all(app):
    win = QueryPreviewWindow("Small", _df(3))
    try:
        assert win._showing_all is True
        # "Show All" affordance is hidden when everything already fits.
        assert win._btn_show_all.isVisibleTo(win) is False
        assert win._table.table_view.model().rowCount() == 3
    finally:
        win.deleteLater()


def test_large_df_preview_then_show_all(app):
    n = _PREVIEW_LIMIT + 500
    win = QueryPreviewWindow("Big", _df(n))
    try:
        assert win._showing_all is False
        assert win._btn_show_all.isVisibleTo(win) is True
        assert win._table.table_view.model().rowCount() == _PREVIEW_LIMIT

        win._on_show_all()
        assert win._showing_all is True
        assert win._btn_show_all.isVisibleTo(win) is False
        assert win._table.table_view.model().rowCount() == n
    finally:
        win.deleteLater()
