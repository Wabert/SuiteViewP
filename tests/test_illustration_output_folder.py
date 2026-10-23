"""The RERUN PDF output folder: one profile setting, changed only in its Output folder row.

Saving a PDF somewhere else in the Save dialog is a one-off and must not rewrite the
setting, and every open report page shows (and saves) the same folder.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def settings(tmp_path, monkeypatch):
    from suiteview.illustration.ui import report_pages

    path = tmp_path / "illustration_settings.json"
    monkeypatch.setattr(report_pages, "report_settings_file", lambda: path)
    return path


def _saved(path) -> str:
    return json.loads(path.read_text(encoding="utf-8")).get("report_output_folder", "")


def _choose_folder(monkeypatch, row, folder):
    from suiteview.illustration.ui import report_pages

    monkeypatch.setattr(report_pages.QFileDialog, "getExistingDirectory", lambda *a, **k: str(folder))
    row.browse_btn.click()


def test_print_to_another_folder_keeps_the_saved_output_folder(qtbot, tmp_path, settings, monkeypatch):
    from suiteview.illustration.ui import illustration_pages_view as module
    from suiteview.illustration.ui.illustration_pages_view import IllustrationPagesView, ReportPages

    chosen = tmp_path / "chosen"
    chosen.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    view = IllustrationPagesView(lambda result, run: ReportPages([["x"]], 10, "P1", "PLAN", ""),
                                 lambda result: None, "Ledger")
    qtbot.addWidget(view)
    _choose_folder(monkeypatch, view.output_folder_row, chosen)
    assert _saved(settings) == str(chosen)
    view.set_result(object())

    starts = []

    def save_dialog(parent, title, start, filters):
        starts.append(start)
        return str(elsewhere / "one-off.pdf"), filters

    monkeypatch.setattr(module.QFileDialog, "getSaveFileName", save_dialog)
    monkeypatch.setattr(view, "write_pdf", lambda path: None)
    monkeypatch.setattr(module.QDesktopServices, "openUrl", lambda url: True)
    view.print_pdf_btn.click()

    assert starts and starts[0].startswith(str(chosen))
    assert _saved(settings) == str(chosen)
    assert view.output_folder_row.edit.text() == str(chosen)


def test_ul_report_print_keeps_the_saved_output_folder(qtbot, tmp_path, settings, monkeypatch):
    from suiteview.illustration.ui import report_tab as module
    from suiteview.illustration.ui.report_tab import IllustrationReportTab

    monkeypatch.setattr(module, "_settings_file", lambda: tmp_path / "ul_settings.json")
    chosen = tmp_path / "chosen"
    chosen.mkdir()
    tab = IllustrationReportTab()
    qtbot.addWidget(tab)
    _choose_folder(monkeypatch, tab.output_folder_row, chosen)
    tab._report = SimpleNamespace(policy_number="P1", plancode="PLAN")
    monkeypatch.setattr(module, "print_blocked_reason", lambda *a, **k: None)
    monkeypatch.setattr(module.IllustrationReportTab, "write_pdf", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(module.QDesktopServices, "openUrl", lambda url: True)
    monkeypatch.setattr(module.QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(tmp_path / "one-off.pdf"), ""))
    tab._on_print_pdf()
    assert _saved(settings) == str(chosen)


def test_every_row_shows_the_one_setting_and_focus_out_never_resaves(qtbot, tmp_path, settings, monkeypatch):
    from suiteview.illustration.ui.report_pages import OutputFolderRow

    first, second = OutputFolderRow(), OutputFolderRow()
    qtbot.addWidget(first)
    qtbot.addWidget(second)
    _choose_folder(monkeypatch, first, tmp_path)
    assert second.edit.text() == str(tmp_path)

    written = []
    from suiteview.illustration.ui import report_pages
    monkeypatch.setattr(report_pages, "save_output_folder", written.append)
    second.edit.editingFinished.emit()                   # focus left the field, nothing typed
    assert written == []

    second.edit.setText("  C:/Reports  ")
    second.edit.editingFinished.emit()
    assert written == ["C:/Reports"]
