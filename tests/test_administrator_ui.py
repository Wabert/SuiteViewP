import os
from dataclasses import replace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QAbstractItemView, QHeaderView

from suiteview.administrator.service import APP_CODES, AccessUser
from suiteview.administrator.window import AdministratorWindow
from suiteview.polview.ui.widgets import StyledInfoTableGroup
from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from tools.app.verify_administrator import ReadOnlyCaptureRepository, SyntheticRepository


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", Mock())
    monkeypatch.setattr(QMessageBox, "question", Mock(return_value=QMessageBox.StandardButton.Cancel))
    repository = SyntheticRepository()
    window = AdministratorWindow(repository=repository)
    window.show()
    app.processEvents()
    yield window, repository
    monkeypatch.setattr(QMessageBox, "question", Mock(return_value=QMessageBox.StandardButton.Discard))
    window.close()
    window.deleteLater()
    app.processEvents()


def select(window, index, key):
    window.tabs.setCurrentIndex(index)
    table = window.tables[index]
    row = next(r for r in range(table.model.rowCount()) if table.model.index(r, 0).data() == key)
    table.table_view.setCurrentIndex(table.model.index(row, 0))
    table.table_view.selectRow(row)


def answer(monkeypatch, button):
    question = Mock(return_value=button)
    monkeypatch.setattr(QMessageBox, "question", question)
    return question


def test_authorization_precedes_sensitive_ui(app, monkeypatch):
    build = Mock()
    monkeypatch.setattr(AdministratorWindow, "build_content", build)
    repository = Mock()
    repository.load.side_effect = PermissionError("Enabled ADMIN required")
    with pytest.raises(PermissionError, match="ADMIN"):
        AdministratorWindow(repository=repository)
    build.assert_not_called()


@pytest.mark.parametrize("developer", [False, True])
def test_status_identifies_developer_access_after_refresh_and_save(editor, monkeypatch, developer):
    from suiteview.administrator import window as window_module

    monkeypatch.setattr(window_module, "has_developer_access", lambda: developer)
    window, _ = editor
    window.refresh()
    expected = "Developer access (source)" if developer else "ADMIN"
    assert f" · {expected} · Refreshed" in window.status.text()
    select(window, 0, "ANALYST01")
    window.user_name.setText("Revised name")
    window.save_record()
    assert f" · {expected} · Saved" in window.status.text()


def test_dense_shared_widgets_and_stable_keys(editor):
    window, _ = editor
    assert isinstance(window, FramelessWindowBase)
    assert len(window.findChildren(StyledInfoTableGroup)) == 2
    assert [window.tabs.tabText(i) for i in (0, 1)] == ["Users", "Roles & Apps"]
    for table in window.tables:
        view = table.table_view
        assert view.verticalHeader().isHidden()
        assert not view.showGrid() and not view.alternatingRowColors()
        assert view.verticalHeader().defaultSectionSize() == 16
        assert table.header.height() == 18
        assert table.header.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch
        assert view.selectionMode() == QAbstractItemView.SelectionMode.SingleSelection
        assert view.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows
    assert window.user_id.isReadOnly()
    assert window.role_code.isReadOnly()
    assert not window.dirty


def test_checkboxes_match_query_tool_style(editor):
    from suiteview.audit.tabs._styles import make_checkbox

    window, _ = editor
    reference = make_checkbox("")
    for key in ("ANALYST", "ADMIN"):
        select(window, 1, key)
        checks = [
            window.user_enabled, window.role_all_apps, window.role_update,
            window.role_support, *window.app_checks.values(),
        ]
        for check in checks:
            assert check.styleSheet() == reference.styleSheet()
            assert check.font() == reference.font()
    reference.deleteLater()


def test_save_user_and_refresh_emit_signal(editor):
    window, repository = editor
    select(window, 0, "ANALYST01")
    original = window._originals[0]
    changed = Mock()
    window.permissions_changed.connect(changed)
    window.user_name.setText("Revised analyst")
    window.user_role.setCurrentIndex(window.user_role.findData("REVIEWER"))
    assert window.dirty and window.windowTitle().endswith("*")
    window.save_record()
    assert repository.mutations[-1][3] == original
    user = next(u for u in window.snapshot.users if u.network_id == "ANALYST01")
    assert user.name == "Revised analyst" and user.role_code == "REVIEWER"
    assert window.snapshot == repository.snapshot
    assert not window.dirty
    changed.assert_called_once()


def test_new_user_requires_one_role_and_can_be_deleted(editor, monkeypatch):
    window, repository = editor
    window.new_record()
    assert not window.user_id.isReadOnly()
    window.user_id.setText("new01")
    window.user_name.setText("New colleague")
    window.save_record()
    assert not repository.mutations
    assert window.dirty
    window.user_role.setCurrentIndex(window.user_role.findData("REVIEWER"))
    window.save_record()
    assert window._originals[0] == AccessUser("NEW01", "New colleague", True, "REVIEWER")
    assert window.user_id.isReadOnly()
    window.delete_record()
    assert len(repository.mutations) == 1
    answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.delete_record()
    assert all(u.network_id != "NEW01" for u in repository.snapshot.users)


def test_disable_requires_confirmation(editor, monkeypatch):
    window, repository = editor
    select(window, 0, "ANALYST01")
    window.user_enabled.setChecked(False)
    window.save_record()
    assert not repository.mutations and window.dirty
    question = answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.save_record()
    assert "Disable" in question.call_args.args[1]
    assert "deny their next app entry and protected write" in question.call_args.args[2]
    assert not window._originals[0].enabled


def test_role_picker_preserves_unknown_and_all_apps_selections(editor, monkeypatch):
    window, repository = editor
    select(window, 1, "ANALYST")
    assert set(window.app_checks) == set(APP_CODES) | {"FUTURE_APP"}
    assert "ADMIN" not in window.app_checks
    assert window.app_checks["FUTURE_APP"].isChecked()
    assert window.role_group.get_value("affected") == "1"
    prior = window._value(1).apps
    window.role_all_apps.setChecked(True)
    assert not window.app_picker.isEnabled()
    assert "ignored" in window.app_note.text() and "preserved" in window.app_note.text()
    assert window._value(1).apps == prior
    window.role_all_apps.setChecked(False)
    assert window.app_picker.isEnabled() and window._value(1).apps == prior
    window.role_all_apps.setChecked(True)
    window.role_update.setChecked(True)
    window.save_record()
    assert not repository.mutations
    question = answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.save_record()
    assert "1 assigned user(s)" in question.call_args.args[2]
    saved = window._originals[1]
    assert saved.all_apps and saved.can_update_database and saved.apps == prior
    assert not window.dirty


def test_role_create_delete_and_assigned_protection(editor, monkeypatch):
    window, repository = editor
    select(window, 1, "ANALYST")
    assert not window.delete_buttons[1].isEnabled()
    window.delete_record()
    assert not repository.mutations
    window.new_record()
    assert not window.role_code.isReadOnly()
    window.role_code.setText("custom")
    window.role_description.setText("Specialists")
    window.app_checks["QUERY"].setChecked(True)
    answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.save_record()
    assert window._originals[1].role_code == "CUSTOM"
    assert window._originals[1].apps == frozenset({"QUERY"})
    assert window.delete_buttons[1].isEnabled()
    window.delete_record()
    assert not any(r.role_code == "CUSTOM" for r in repository.snapshot.roles)


@pytest.mark.parametrize("action", ["selection", "tab", "new", "refresh", "close"])
def test_dirty_cancel_guards(editor, monkeypatch, action):
    window, repository = editor
    select(window, 0, "ANALYST01")
    window.user_name.setText("Unsaved draft")
    load = Mock(wraps=repository.load)
    repository.load = load
    if action == "selection":
        select(window, 0, "REVIEWER01")
    elif action == "tab":
        window.tabs.setCurrentIndex(1)
    elif action == "new":
        window.new_record()
    elif action == "refresh":
        window.refresh()
    else:
        assert not window.close()
    assert window.user_name.text() == "Unsaved draft"
    assert window._originals[0].network_id == "ANALYST01"
    assert window.tabs.currentIndex() == 0
    assert window.dirty
    load.assert_not_called()


@pytest.mark.parametrize("action", ["selection", "tab", "new", "refresh", "close"])
def test_dirty_discard_transitions(editor, monkeypatch, action):
    window, _ = editor
    select(window, 0, "ANALYST01")
    window.user_name.setText("Unsaved draft")
    answer(monkeypatch, QMessageBox.StandardButton.Discard)
    if action == "selection":
        select(window, 0, "REVIEWER01")
        assert window.user_id.text() == "REVIEWER01"
    elif action == "tab":
        window.tabs.setCurrentIndex(1)
        assert window.tabs.currentIndex() == 1
    elif action == "new":
        window.new_record()
        assert not window.user_id.text() and window._new[0]
    elif action == "refresh":
        window.refresh()
    else:
        assert window.close()
        window.show()
        assert window.isVisible()
    assert window.user_name.text() != "Unsaved draft"
    assert window.dirty == (action == "new")


def test_sort_filter_and_cancel_keep_correct_identity(editor, monkeypatch):
    window, repository = editor
    select(window, 0, "ANALYST01")
    table = window.tables[0]
    window.user_name.setText("Sorted draft")
    table.apply_sort(1, Qt.SortOrder.DescendingOrder)
    assert window._originals[0].network_id == "ANALYST01"
    select(window, 0, "REVIEWER01")
    assert window.user_name.text() == "Sorted draft"
    assert table.table_view.currentIndex().siblingAtColumn(0).data() == "ANALYST01"
    table.apply_column_filter("Network ID", {"REVIEWER01"})
    assert table.model.rowCount() == 1
    assert window.user_name.text() == "Sorted draft"
    assert not table.table_view.currentIndex().isValid()
    window.save_record()
    assert repository.mutations[-1][2].network_id == "ANALYST01"
    table = window.tables[0]
    table.apply_sort(1, Qt.SortOrder.DescendingOrder)
    select(window, 0, "REVIEWER01")
    window.user_name.setText("Correct filtered user")
    window.save_record()
    assert repository.mutations[-1][2].network_id == "REVIEWER01"


def test_failed_concurrent_save_retains_draft_and_original(editor, caplog):
    window, repository = editor
    select(window, 0, "ANALYST01")
    original = window._originals[0]
    repository.snapshot = replace(repository.snapshot, users=tuple(
        replace(u, name="Other admin's edit") if u == original else u
        for u in repository.snapshot.users
    ))
    window.user_name.setText("My draft")
    window.save_record()
    assert window.dirty and window.user_name.text() == "My draft"
    assert window._originals[0] == original
    assert not repository.mutations
    assert "Save failed" in caplog.text
    QMessageBox.warning.assert_called_once()


def test_failed_refresh_retains_draft_even_after_discard_confirmation(editor, monkeypatch):
    window, repository = editor
    window.user_name.setText("Retain until successful reload")
    repository.load = Mock(side_effect=RuntimeError("Connection unavailable"))
    answer(monkeypatch, QMessageBox.StandardButton.Discard)
    window.refresh()
    assert window.dirty and window.user_name.text() == "Retain until successful reload"
    assert "Refresh failed" in window.status.text()


@pytest.mark.parametrize("error", [PermissionError("ADMIN revoked"), RuntimeError("Network failed")])
def test_post_commit_reload_failure_blocks_duplicate_save_preserves_draft(editor, monkeypatch, error):
    window, repository = editor
    select(window, 0, "ANALYST01")
    window.user_name.setText("Committed edit")
    changed = Mock()
    window.permissions_changed.connect(changed)
    repository.load = Mock(side_effect=error)
    window.save_record()
    assert len(repository.mutations) == 1
    changed.assert_called_once()
    assert window._blocked and not window.tabs.isEnabled()
    assert window.dirty and window.user_name.text() == "Committed edit"
    assert "Saved, but reload failed" in window.status.text()
    window.save_record()
    assert len(repository.mutations) == 1
    repository.load = lambda: repository.snapshot
    answer(monkeypatch, QMessageBox.StandardButton.Discard)
    window.refresh()
    assert not window._blocked and window.tabs.isEnabled() and not window.dirty


def test_mutation_revocation_blocks_ui_and_retains_draft(editor):
    window, repository = editor
    window.user_name.setText("Do not lose")
    repository.save_user = Mock(side_effect=PermissionError("ADMIN revoked"))
    window.save_record()
    assert window._blocked and not window.tabs.isEnabled()
    assert window.user_name.text() == "Do not lose" and window.dirty
    assert not repository.mutations


def test_role_delete_race_is_reported_without_losing_selection(editor, monkeypatch):
    window, repository = editor
    select(window, 1, "UNASSIGNED")
    repository.snapshot = replace(
        repository.snapshot,
        users=repository.snapshot.users + (AccessUser("LATEUSER", "Late", True, "UNASSIGNED"),),
    )
    answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.delete_record()
    assert window._originals[1].role_code == "UNASSIGNED"
    assert not repository.mutations
    assert "Delete failed" in window.status.text()


def test_native_click_cancel_restores_single_selected_identity(editor, app):
    window, _ = editor
    select(window, 0, "ANALYST01")
    window.user_name.setText("Retained draft")
    table = window.tables[0]
    table.apply_sort(1, Qt.SortOrder.DescendingOrder)
    target = next(
        table.model.index(row, 0) for row in range(table.model.rowCount())
        if table.model.index(row, 0).data() == "REVIEWER01"
    )
    QTest.mouseClick(
        table.table_view.viewport(), Qt.MouseButton.LeftButton,
        pos=table.table_view.visualRect(target).center(),
    )
    app.processEvents()
    selected = table.table_view.selectionModel().selectedRows()
    assert [index.data() for index in selected] == ["ANALYST01"]
    assert window.user_name.text() == "Retained draft"


def test_role_draft_is_guarded_and_failed_save_preserves_app_choices(editor, monkeypatch):
    window, repository = editor
    select(window, 1, "ANALYST")
    window.app_checks["FILENAV"].setChecked(True)
    window.tabs.setCurrentIndex(0)
    assert window.tabs.currentIndex() == 1 and window.dirty
    original = window._originals[1]
    repository.save_role = Mock(side_effect=RuntimeError("Concurrent role update"))
    answer(monkeypatch, QMessageBox.StandardButton.Yes)
    window.save_record()
    assert window._originals[1] == original and window.dirty
    assert window.app_checks["FILENAV"].isChecked()
    assert window.app_checks["FUTURE_APP"].isChecked()
    assert "Save failed" in window.status.text()


def test_enforcement_scope_notice_is_persistent_across_tabs_and_refresh(editor, app):
    window, _ = editor
    text = window.enforcement_notice.text()
    assert "Runtime permissions" in text
    assert "Source developer runs remain unrestricted" in text
    for index in (0, 1):
        window.tabs.setCurrentIndex(index)
        window.refresh()
        app.processEvents()
        assert window.enforcement_notice.isVisible()
        assert window.enforcement_notice.text() == text


def test_live_capture_adapter_allows_load_and_blocks_every_write():
    real = Mock()
    repository = ReadOnlyCaptureRepository(real)
    assert repository.load() is real.load.return_value
    for method in ("save_user", "save_role"):
        with pytest.raises(PermissionError, match="read-only"):
            getattr(repository, method)(Mock(), original=None)
        getattr(real, method).assert_not_called()
    for method in ("delete_user", "delete_role"):
        with pytest.raises(PermissionError, match="read-only"):
            getattr(repository, method)(Mock())
        getattr(real, method).assert_not_called()
    assert repository.mutations == ["save_user", "save_role", "delete_user", "delete_role"]


def test_short_ids_keep_header_single_line_and_long_details_start_at_left(editor):
    window, repository = editor
    repository.snapshot = replace(
        repository.snapshot,
        users=(AccessUser("A1", "Administrator", True, "ADMIN"),),
        roles=tuple(
            replace(r, description="A long role description that needs horizontal editing space")
            if r.role_code == "ADMIN" else r for r in repository.snapshot.roles
        ),
    )
    window.refresh()
    table = window.tables[0]
    metrics = QFontMetrics(table.header.wrap_font())
    assert table.table_view.columnWidth(0) >= (
        metrics.horizontalAdvance("Network ID") + table.header.sort_icon_width + 8
    )
    assert window.role_description.cursorPosition() == 0
    assert window.role_description.toolTip() == window.role_description.text()
