"""RERUN header ☰ menu and its read-only Plancode Table viewer."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.models.plancode_config import (
    load_plancode,
    plancode_table_rows,
)
from suiteview.illustration.ui.plancode_table_view import (
    PlancodeTableWindow,
    plancode_table_frame,
)


_QT_APP = None


@pytest.fixture
def app(monkeypatch, tmp_path):
    global _QT_APP
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path / "profile"))
    from suiteview.core import access_control

    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    # Module-held so the QApplication outlives this fixture; destroying it
    # would also delete process-wide QObject singletons later tests reuse.
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _close(app, *windows):
    for window in windows:
        window.close()
        window.deleteLater()
    app.processEvents()


def test_plancode_table_rows_are_copies_of_the_engine_rows():
    rows = plancode_table_rows()
    assert rows
    first = rows[0]
    assert load_plancode(first["Plancode"]).plancode == first["Plancode"]

    first["Plancode"] = "MUTATED"
    assert plancode_table_rows()[0]["Plancode"] != "MUTATED"


def test_frame_keeps_numbers_texts_mixed_columns_and_leaves_missing_blank():
    rows = [
        {"Plancode": "A", "MaturityAge": 100, "Rate": 0.06, "Flag": True, "Mixed": "0"},
        {"Plancode": "B", "MaturityAge": 121, "Mixed": 5, "Extra": [1, 2]},
    ]

    df, text_columns = plancode_table_frame(rows)

    assert list(df.columns) == ["Plancode", "MaturityAge", "Rate", "Flag", "Mixed", "Extra"]
    assert text_columns == {"Plancode", "Flag", "Mixed", "Extra"}
    assert df["MaturityAge"].tolist() == [100, 121]
    assert df.loc[0, "Rate"] == 0.06
    assert df.loc[1, "Rate"] is None
    assert df["Flag"].tolist() == ["True", None]
    assert df["Mixed"].tolist() == ["0", "5"]
    assert df.loc[1, "Extra"] == "[1, 2]"
    # Mixed-type columns were normalized, so every column sorts.
    for column in df.columns:
        df.sort_values(by=column)


def test_viewer_shows_every_plancode_with_identity_columns_frozen(app):
    window = PlancodeTableWindow()
    try:
        rows = plancode_table_rows()
        assert window.grid.model.rowCount() == len(rows)
        assert window.grid.df.columns[0] == "Plancode"
        assert window.grid._frozen_column_count == 1
        assert f"{len(rows):,} plancodes" in window.summary_label.text()
        assert window.grid.model.format_value_for_column(
            "Plancode", window.grid.df.loc[0, "Plancode"]) == rows[0]["Plancode"]
    finally:
        _close(app, window)


def test_header_hamburger_sits_left_of_title_and_opens_one_plancode_window(app):
    from suiteview.illustration.ui.main_window import IllustrationWindow

    window = IllustrationWindow()
    try:
        layout = window.header_bar.layout()
        assert layout.indexOf(window.hamburger_btn) == 0
        assert layout.indexOf(window.hamburger_btn) < layout.indexOf(window.title_label)
        assert window.hamburger_btn.text() == "☰"
        actions = [a.text() for a in window.hamburger_btn.menu().actions()]
        assert actions == ["Plancode Table…"]

        window._plancode_table_action.trigger()
        app.processEvents()
        viewer = window._plancode_table_window
        assert isinstance(viewer, PlancodeTableWindow)
        assert viewer.isVisible()

        viewer.close()
        app.processEvents()
        window._plancode_table_action.trigger()
        app.processEvents()
        assert window._plancode_table_window is viewer
        assert viewer.isVisible()
    finally:
        if window._plancode_table_window is not None:
            _close(app, window._plancode_table_window)
        _close(app, window)


def test_plancode_table_load_failure_is_loud(app, monkeypatch):
    from suiteview.illustration.ui import main_window as main_window_module

    def _broken(*_args, **_kwargs):
        raise FileNotFoundError("No plancode table found")

    shown = []
    monkeypatch.setattr(main_window_module, "PlancodeTableWindow", _broken)
    monkeypatch.setattr(
        main_window_module.QMessageBox, "critical",
        lambda _parent, title, text: shown.append((title, text)))

    window = main_window_module.IllustrationWindow()
    try:
        window.show_plancode_table()
        assert window._plancode_table_window is None
        assert shown and shown[0][0] == "Plancode Table"
        assert "No plancode table found" in shown[0][1]
    finally:
        _close(app, window)
