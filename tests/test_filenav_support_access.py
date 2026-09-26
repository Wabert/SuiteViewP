"""Generic FileNav may browse support roots, but cannot bypass their write flag."""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QStandardItem
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox, QWidget

from suiteview.core import access_control as access
from suiteview.core import support_files as support
from suiteview.file_nav import file_explorer_core as explorer
from suiteview.file_nav import sharepoint_client as sharepoint
from suiteview.ui.dialogs.batch_rename_dialog import BatchRenameDialog
from suiteview.utils.excel_template import copy_as_workbook


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def context(tmp_path, monkeypatch, qapp):
    protected = tmp_path / "home" / "Policy Support"
    protected.mkdir(parents=True)
    personal = tmp_path / "personal"
    personal.mkdir()
    state = SimpleNamespace(protected=protected, personal=personal, writable=True, loads=0)

    def load():
        state.loads += 1
        return access.EffectiveAccess(
            "TEST", "NONBUSINESS", False, False, state.writable, frozenset({"FILENAV"})
        )

    monkeypatch.setattr(support, "support_file_roots", lambda: (str(protected),))
    monkeypatch.setattr(access, "has_developer_access", lambda: False)
    monkeypatch.setattr(access, "_load_access", load)
    access.clear_access_cache()
    access.get_access()
    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, name, Mock())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    yield state
    access.clear_access_cache()


def _explorer(folder, paths=()):
    return SimpleNamespace(
        get_selected_path=lambda: str(paths[0]) if paths else None,
        get_selected_paths=lambda: [str(path) for path in paths],
        current_details_folder=str(folder),
        load_folder_contents_in_details=Mock(),
        refresh_tree=Mock(),
        clipboard={"paths": [], "operation": None},
        get_clipboard_files=lambda: [],
        _get_unique_dest_path=lambda path: path.with_name(path.stem + " copy" + path.suffix),
    )


def test_file_explorer_core_constructs_offscreen(context, monkeypatch, tmp_path):
    class FakeBookmarkManager:
        def get_bar_data(self, _bar_id):
            return {"categories": {}, "items": [], "category_colors": {}}

        def save(self):
            return None

    class FakeBookmarkContainer(QWidget):
        navigate_to_path = pyqtSignal(str)

        def __init__(self, *args, **kwargs):
            parent = kwargs.get("parent")
            super().__init__(parent)

    monkeypatch.setattr(explorer, "get_bookmark_manager", lambda: FakeBookmarkManager())
    monkeypatch.setattr(explorer, "BookmarkContainer", FakeBookmarkContainer)
    monkeypatch.setattr(explorer, "profile_path", lambda name: tmp_path / name)

    widget = explorer.FileExplorerCore()
    try:
        assert widget.details_view.model() is widget.details_sort_proxy
        assert widget.tree_view.model() is widget.model
    finally:
        widget.deleteLater()


def test_classifier_protects_children_ancestors_not_similarly_named_paths(context):
    root = context.protected
    assert support.is_support_file_path(root)
    assert support.is_support_file_path(root / "policy" / "file.xlsx")
    assert support.is_support_file_path(root.parent)
    assert support.is_support_file_path(str(root).swapcase())
    assert support.is_support_file_path("\\\\?\\" + str(root / "file.txt"))
    assert support.is_support_file_path(root / ".." / root.name / "file.xlsx")
    assert not support.is_support_file_path(root.with_name(root.name + " personal"))
    assert not support.is_support_file_path(context.personal)


def test_resolved_aliases_are_protected(context, monkeypatch):
    alias = context.personal / "junction"
    realpath = support.os.path.realpath

    def resolve(path):
        if os.path.commonpath((str(alias), path)) == str(alias):
            return str(context.protected / os.path.relpath(path, alias))
        return realpath(path)

    monkeypatch.setattr(support.os.path, "realpath", resolve)
    assert support.is_support_file_path(alias / "policy" / "file.txt")
    context.writable = False
    with pytest.raises(access.AccessDeniedError):
        support.guard_support_file_paths(alias / "policy" / "file.txt")


@pytest.mark.parametrize("protected", [False, True])
@pytest.mark.parametrize("writable", [False, True])
@pytest.mark.parametrize("operation", ["rename", "inline_rename", "batch_rename", "delete", "mkdir"])
def test_direct_filenav_mutations(context, monkeypatch, protected, writable, operation):
    folder = context.protected if protected else context.personal
    old_path = folder / "original.txt"
    old_path.write_text("preserve", encoding="utf-8")
    browser = _explorer(folder, [old_path])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("renamed.txt", True))
    context.writable = writable
    assert access.can_write_support_files()  # Cached UI says yes; boundary must refresh.

    if operation == "inline_rename":
        item = QStandardItem("renamed.txt")
        item.setData(str(old_path), Qt.ItemDataRole.UserRole)
        browser.details_model = Mock()
        browser.on_item_renamed = Mock()
        explorer.FileExplorerCore.on_item_renamed(browser, item)
        if protected and not writable:
            assert item.data(Qt.ItemDataRole.UserRole) == str(old_path)
            assert "original.txt" in item.text()
    elif operation == "batch_rename":
        dialog = SimpleNamespace(
            get_rename_map=lambda: {str(old_path): str(folder / "renamed.txt")}
        )
        BatchRenameDialog.perform_rename(dialog)
    else:
        method = {"rename": "rename_file", "delete": "delete_file", "mkdir": "create_new_folder"}[operation]
        getattr(explorer.FileExplorerCore, method)(browser)

    allowed = writable or not protected
    assert old_path.exists() is (not allowed or operation == "mkdir")
    assert (folder / "renamed.txt").exists() is (allowed and operation != "delete")
    if not protected:
        assert context.loads == 1  # Personal operations do not query permission services.


@pytest.mark.parametrize("channel", ["internal_copy", "internal_cut", "windows", "drop"])
@pytest.mark.parametrize("direction", ["into_support", "out_of_support", "personal"])
@pytest.mark.parametrize("writable", [False, True])
@pytest.mark.parametrize("directory", [False, True])
def test_filenav_copy_and_move(
    context, channel, direction, writable, directory
):
    source_folder = context.protected if direction == "out_of_support" else context.personal
    source = source_folder / "original"
    if directory:
        source.mkdir()
        (source / "child.txt").write_text("preserve", encoding="utf-8")
    else:
        source.write_text("preserve", encoding="utf-8")
    destination = context.protected if direction == "into_support" else context.personal / "destination"
    destination.mkdir(exist_ok=True)
    browser = _explorer(destination)
    context.writable = writable

    if channel == "drop":
        explorer.FileExplorerCore.handle_dropped_files(browser, [str(source)], str(destination))
    else:
        if channel == "windows":
            browser.get_clipboard_files = lambda: [str(source)]
        else:
            browser.clipboard = {
                "paths": [str(source)],
                "operation": "cut" if channel == "internal_cut" else "copy",
            }
        explorer.FileExplorerCore.paste_file(browser)

    mutates_support = direction == "into_support" or (
        direction == "out_of_support" and channel == "internal_cut"
    )
    allowed = writable or not mutates_support
    assert (destination / source.name).exists() is allowed
    assert source.exists() is (not allowed or channel != "internal_cut")
    if mutates_support and not allowed:
        assert "CanWriteSupportFiles" in str(QMessageBox.warning.call_args)


def test_parent_delete_cannot_remove_protected_descendants(context):
    file = context.protected / "file.txt"
    file.write_text("keep", encoding="utf-8")
    context.writable = False
    browser = _explorer(context.protected.parent, [context.protected.parent])
    explorer.FileExplorerCore.delete_file(browser)
    assert file.read_text(encoding="utf-8") == "keep"


def test_generic_workbook_copy_cannot_bypass_canonical_roots(context):
    source = context.personal / "source.txt"
    source.write_text("keep", encoding="utf-8")
    context.writable = False
    with pytest.raises(access.AccessDeniedError):
        copy_as_workbook(str(source), str(context.protected / "copy.txt"))
    assert not (context.protected / "copy.txt").exists()
    copy_as_workbook(str(source), str(context.personal / "copy.txt"))
    assert (context.personal / "copy.txt").read_text(encoding="utf-8") == "keep"


def test_generic_mini_explorer_cannot_bypass_canonical_roots(context, monkeypatch):
    from suiteview.ui.widgets.mini_explorer import MiniExplorer
    from PyQt6.QtWidgets import QListWidgetItem

    path = context.protected / "original.txt"
    path.write_text("keep", encoding="utf-8")
    browser = MiniExplorer(root_path=str(context.protected))
    item = QListWidgetItem("original.txt")
    item.setData(Qt.ItemDataRole.UserRole, str(path))
    context.writable = False
    browser._delete_entry(item)
    assert path.exists()
    browser.close()
    browser.deleteLater()


@pytest.mark.parametrize("writable", [False, True])
@pytest.mark.parametrize("protected", [False, True])
def test_sharepoint_download_destination_scope(context, monkeypatch, writable, protected):
    folder = context.protected if protected else context.personal
    destination = folder / "new" / "download.txt"
    response = Mock(ok=True, headers={}, iter_content=lambda **kwargs: [b"downloaded"])
    request = Mock()
    request.return_value.__enter__ = Mock(return_value=response)
    request.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(sharepoint.requests, "get", request)
    client = SimpleNamespace(get_token=Mock(return_value="fake-token"))
    context.writable = writable

    if protected and not writable:
        with pytest.raises(access.AccessDeniedError):
            sharepoint.SharePointClient.download_file(client, "drive", "item", destination)
        assert not destination.parent.exists()
        request.assert_not_called()
        client.get_token.assert_not_called()
    else:
        sharepoint.SharePointClient.download_file(client, "drive", "item", destination)
        assert destination.read_bytes() == b"downloaded"


def test_download_rechecks_after_network_delay_before_overwrite(context, monkeypatch):
    destination = context.protected / "original.txt"
    destination.write_text("keep", encoding="utf-8")
    response = Mock(ok=True, headers={})

    def response_after_revocation():
        context.writable = False
        return response

    request = Mock()
    request.return_value.__enter__ = Mock(side_effect=response_after_revocation)
    request.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(sharepoint.requests, "get", request)
    client = SimpleNamespace(get_token=lambda: "fake-token")

    with pytest.raises(access.AccessDeniedError):
        sharepoint.SharePointClient.download_file(client, "drive", "item", destination)
    assert destination.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("operation", ["save", "preview"])
@pytest.mark.parametrize("protected", [False, True])
@pytest.mark.parametrize("writable", [False, True])
def test_outlook_attachment_destinations(context, monkeypatch, operation, protected, writable):
    from suiteview.core.outlook_manager import OutlookManager

    folder = context.protected if protected else context.personal
    attachment = SimpleNamespace(
        FileName="attachment.txt",
        SaveAsFile=Mock(side_effect=lambda path: Path(path).write_bytes(b"attachment")),
    )
    item = SimpleNamespace(Attachments=SimpleNamespace(Count=1, Item=lambda index: attachment))
    manager = SimpleNamespace(
        connected=True, namespace=SimpleNamespace(GetItemFromID=lambda email_id: item)
    )
    monkeypatch.setenv("TEMP", str(folder))
    destination = (
        folder / "SuiteView_Email_Previews" / "attachment.txt"
        if operation == "preview" else folder / "new" / "attachment.txt"
    )
    context.writable = writable

    def save():
        if operation == "preview":
            return OutlookManager.get_attachment_preview_path(manager, "email", 1)
        return OutlookManager.save_attachment(manager, "email", 1, str(destination))

    if protected and not writable:
        with pytest.raises(access.AccessDeniedError):
            save()
        assert not destination.parent.exists()
        attachment.SaveAsFile.assert_not_called()
    else:
        assert save()
        assert destination.read_bytes() == b"attachment"


def test_email_clipboard_reports_protected_preview_denial(context, monkeypatch):
    from suiteview.core.outlook_manager import OutlookManager
    from suiteview.ui.email_attachments_window import EmailAttachmentsWindow

    attachment = SimpleNamespace(FileName="attachment.txt", SaveAsFile=Mock())
    item = SimpleNamespace(Attachments=SimpleNamespace(Item=lambda index: attachment))
    manager = SimpleNamespace(
        connected=True,
        is_connected=lambda: True,
        namespace=SimpleNamespace(GetItemFromID=lambda email_id: item),
    )
    manager.get_attachment_preview_path = lambda email_id, index: (
        OutlookManager.get_attachment_preview_path(manager, email_id, index)
    )
    panel = SimpleNamespace(outlook=manager, status_label=Mock())
    clipboard = Mock()
    monkeypatch.setattr(QApplication, "clipboard", lambda: clipboard)
    monkeypatch.setenv("TEMP", str(context.protected))
    context.writable = False

    EmailAttachmentsWindow.copy_attachment_to_clipboard(panel, "email", 1)

    assert not (context.protected / "SuiteView_Email_Previews").exists()
    attachment.SaveAsFile.assert_not_called()
    clipboard.setMimeData.assert_not_called()
    assert "CanWriteSupportFiles" in str(QMessageBox.warning.call_args)
