"""Ctrl+C / context-menu Copy of SharePoint files in FileNav.

Copying downloads the selected files, then puts real local files on the clipboard
so they paste into Windows Explorer or a local FileNav folder.
"""
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from suiteview.file_nav.file_explorer_core import FileExplorerCore
from suiteview.file_nav.sharepoint_client import make_sp_path


@pytest.fixture
def explorer(monkeypatch, tmp_path):
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path / "profile"))
    app = QApplication.instance() or QApplication([])
    explorer = FileExplorerCore()
    folder_sp = make_sp_path("drive1", "folder1")
    explorer.current_details_folder = folder_sp
    entries = [
        {"name": "a.pdf", "is_folder": False, "size": 10, "modified": "", "web_url": "",
         "sp_id": "item-a"},
        {"name": "Sub", "is_folder": True, "size": 0, "modified": "", "web_url": "",
         "sp_id": "item-sub"},
        {"name": "b.xlsx", "is_folder": False, "size": 20, "modified": "", "web_url": "",
         "sp_id": "item-b"},
    ]
    for entry in entries:
        explorer.details_model.appendRow(
            explorer._create_sp_details_row(entry, make_sp_path("drive1", entry["sp_id"])))
    app.processEvents()
    yield explorer
    explorer.deleteLater()


def _select_all(explorer):
    view = explorer.details_view
    view.selectAll()
    return view


def test_selected_sp_files_skips_folders(explorer):
    _select_all(explorer)
    names = sorted(name for _, name in explorer._selected_sp_files())
    assert names == ["a.pdf", "b.xlsx"]


def test_ctrl_c_downloads_then_sets_local_file_clipboard(explorer, tmp_path, monkeypatch):
    _select_all(explorer)
    downloads = []

    def fake_download(sp_path, name, dest_path=None, on_done=None):
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(name, encoding="utf-8")
        downloads.append(dest)
        on_done(str(dest))

    monkeypatch.setattr(explorer, "open_sharepoint_file", fake_download)
    explorer.copy_file()

    assert sorted(p.name for p in downloads) == ["a.pdf", "b.xlsx"]
    assert explorer.clipboard["operation"] == "copy"
    assert sorted(Path(p).name for p in explorer.clipboard["paths"]) == ["a.pdf", "b.xlsx"]
    assert sorted(Path(p).name for p in explorer.get_clipboard_files()) == ["a.pdf", "b.xlsx"]


def test_cancelled_download_leaves_clipboard_untouched(explorer, monkeypatch):
    _select_all(explorer)
    explorer.clipboard = {"paths": ["keep"], "operation": "copy"}
    monkeypatch.setattr(explorer, "open_sharepoint_file",
                        lambda *args, **kwargs: None)
    explorer.copy_file()
    assert explorer.clipboard == {"paths": ["keep"], "operation": "copy"}


def test_sp_context_menu_offers_copy(explorer, monkeypatch):
    from suiteview.file_nav import file_explorer_sharepoint as module

    labels = []

    class SpyMenu(module.QMenu):
        def exec(self, *_args):
            labels.extend(action.text() for action in self.actions())

    monkeypatch.setattr(module, "QMenu", SpyMenu)
    proxy = explorer.details_sort_proxy
    row = next(r for r in range(proxy.rowCount()) if proxy.index(r, 0).data() == "a.pdf")
    index = proxy.index(row, 0)
    explorer.show_sp_details_context_menu(explorer.details_view.rect().center(), index)
    assert any(label.startswith("📋 Copy") for label in labels)
