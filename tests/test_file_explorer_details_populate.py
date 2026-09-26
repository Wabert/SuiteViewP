"""FileNav details panel end-to-end: folder contents actually populate.

Regression for the FileExplorerCore split, which dropped @staticmethod from
_stat_path/_safe_startfile so every folder load raised TypeError and the
details panel stayed empty.
"""
import os

import pytest
from PyQt6.QtWidgets import QApplication

from suiteview.file_nav.file_explorer_core import FileExplorerCore
from suiteview.taskbar_launcher.file_explorer_tab import FileExplorerTab


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path / "profile"))
    return QApplication.instance() or QApplication([])


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "browse"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("x", encoding="utf-8")
    (root / "b.csv").write_text("y", encoding="utf-8")
    return root


def _names(explorer):
    model = explorer.details_model
    return sorted(model.item(row, 0).data(0x0100) for row in range(model.rowCount()))


@pytest.mark.parametrize("explorer_cls", [FileExplorerCore, FileExplorerTab])
def test_folder_contents_populate_details(app, folder, explorer_cls):
    explorer = explorer_cls()
    try:
        explorer.load_folder_contents_in_details(folder)
        app.processEvents()
        assert _names(explorer) == sorted(str(folder / n) for n in ("a.txt", "b.csv", "sub"))
    finally:
        explorer.deleteLater()


def test_safe_startfile_is_callable_on_instance(app, folder, monkeypatch):
    opened = []
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)
    explorer = FileExplorerCore()
    try:
        explorer._safe_startfile(str(folder / "a.txt"))
    finally:
        explorer.deleteLater()
    assert opened == [str(folder / "a.txt")]
