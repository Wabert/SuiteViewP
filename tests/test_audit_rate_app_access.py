"""QUERY and RATEMANAGER entry checks, including already-created windows."""
import os
from unittest.mock import MagicMock, Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from suiteview.core import access_control as access
from suiteview.audit.audit_window import AuditWindow
from suiteview.audit.common_table_dialog import CommonTableDialog
from suiteview.audit.qdef_viewer_window import QDefViewerWindow
from suiteview.audit.query_object_viewer_window import QueryObjectViewerWindow
from suiteview.audit.unique_value_registry_window import (
    RegistryValueEditorWindow, UniqueValueRegistryWindow,
)
from suiteview.audit.dataforge.query_field_picker import QueryFieldPicker
from suiteview.ratemanager.ratemanager_window import RateManagerWindow
from suiteview.ratemanager.workup.term_window import TermWorkupPanel
from suiteview.ratemanager.workup.workup_window import RateWorkupPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def permissions(monkeypatch):
    rights = access.EffectiveAccess("USER", "READER", False, False, False)
    get_access = Mock(return_value=rights)
    monkeypatch.setattr(access, "get_access", get_access)
    monkeypatch.setattr(
        access.pyodbc, "connect",
        Mock(side_effect=AssertionError("No live database in permission tests")),
    )
    warning = Mock()
    monkeypatch.setattr(QMessageBox, "warning", warning)
    return get_access, warning


@pytest.mark.parametrize("window,args,code", [
    (AuditWindow, (), "QUERY"),
    (QDefViewerWindow, (), "QUERY"),
    (QueryObjectViewerWindow, (), "QUERY"),
    (CommonTableDialog, (), "QUERY"),
    (UniqueValueRegistryWindow, (), "QUERY"),
    (RegistryValueEditorWindow, (1, "test"), "QUERY"),
    (RateManagerWindow, (), "RATEMANAGER"),
    (TermWorkupPanel, (), "RATEMANAGER"),
    (RateWorkupPanel, (), "RATEMANAGER"),
])
def test_constructors_deny_before_ui_or_data_work(window, args, code, app, permissions):
    with pytest.raises(access.AccessDeniedError, match=code):
        window(*args)
    permissions[0].assert_called_once_with(refresh=True)


@pytest.mark.parametrize("window", [
    QDefViewerWindow, QueryObjectViewerWindow,
    CommonTableDialog, UniqueValueRegistryWindow,
])
def test_singleton_reuse_rechecks_current_permission(window, app, permissions, monkeypatch):
    get_access, warning = permissions
    existing = MagicMock()
    existing.isVisible.return_value = True
    monkeypatch.setattr(window, "_instance", existing)
    get_access.return_value = access.EffectiveAccess(
        "USER", "READER", False, False, False, frozenset({"QUERY"}),
    )
    assert window.show_instance() is existing
    existing.raise_.assert_called_once()
    existing.reset_mock()
    get_access.return_value = access.EffectiveAccess("USER", "READER", False, False, False)
    assert window.show_instance() is None
    existing.raise_.assert_not_called()
    existing.refresh.assert_not_called()
    existing.isVisible.assert_not_called()
    assert "QUERY" in warning.call_args.args[2]
    assert get_access.call_count == 2


@pytest.mark.parametrize("method,args,code", [
    (AuditWindow._open_polview_with_policy, ("POLICY", "01"), "POLVIEW"),
    (AuditWindow._open_rerun_with_policy, ("POLICY", "01"), "RERUN"),
    (AuditWindow.open_query_object_in_builder, ("query",), "QUERY"),
    (AuditWindow.open_dataforge_in_builder, ("forge",), "QUERY"),
    (QueryObjectViewerWindow._open_folder_in_suiteview_file_nav, ("folder",), "FILENAV"),
    (QueryObjectViewerWindow._open_query_object_in_new_builder, ("query",), "QUERY"),
    (QueryObjectViewerWindow._audit_window_for_builder, (), "QUERY"),
    (QueryFieldPicker._open_query_builder, ("query",), "QUERY"),
])
def test_alternate_launches_deny_before_reading_window_state(
    method, args, code, app, permissions,
):
    owner = QWidget()
    try:
        assert method(owner, *args) is None
        assert code in permissions[1].call_args.args[2]
        permissions[0].assert_called_once_with(refresh=True)
    finally:
        owner.deleteLater()


def test_direct_audit_reuse_and_builder_creation_are_guarded(permissions):
    existing = MagicMock()
    with pytest.raises(access.AccessDeniedError, match="QUERY"):
        QueryObjectViewerWindow._show_audit_window(object(), existing)
    existing.restore_window.assert_not_called()
    with pytest.raises(access.AccessDeniedError, match="QUERY"):
        QueryFieldPicker._new_audit_window_for_builder(object(), "query")


def test_permitted_rerun_handoff_uses_existing_launcher(app, permissions):
    permissions[0].return_value = access.EffectiveAccess(
        "USER", "ILLUSTRATOR", False, False, False, frozenset({"RERUN"}),
    )
    owner = QWidget()
    owner.cmb_region = Mock()
    owner.cmb_region.currentText.return_value = "CKPR"
    owner._illustration_launcher = Mock()
    try:
        AuditWindow._open_rerun_with_policy(owner, "POLICY", "01")
        owner._illustration_launcher.assert_called_once_with("POLICY", "CKPR", "01")
        permissions[1].assert_not_called()
    finally:
        owner.deleteLater()
