"""Runtime write enforcement without connecting to any live database."""
import os
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock, Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from suiteview.core import access_control
from suiteview.core import db2_connection
from suiteview.core.rates import Rates
from suiteview.core.build_env import ReadOnlyDataError
from suiteview.audit import query_runner, shared_field_registry as registry
from suiteview.core.sql_permissions import guard_query_sql
from suiteview.ratemanager import database_loader as loader
from suiteview.ratemanager import mortality_loader
from suiteview.ratemanager.whole_life.service import WholeLifeRepository


@pytest.fixture(autouse=True)
def no_live_database(monkeypatch):
    connect = Mock(side_effect=AssertionError("Tests must never use live databases"))
    monkeypatch.setattr(loader, "connect_dsn", connect)
    return connect


@pytest.fixture
def rights(monkeypatch):
    state = SimpleNamespace(
        can_update_database=False, role_code="ADMIN", developer=False,
    )
    get_access = Mock(side_effect=lambda **_: state)
    monkeypatch.setattr(access_control, "get_access", get_access)
    return state, get_access


@pytest.mark.parametrize("sql", [
    "DELETE FROM rates", "UPDATE rates SET rate=0", "CREATE TABLE rates (id int)",
    "TRUNCATE TABLE rates",
    "SELECT 1; DELETE FROM rates", "SELECT 1 INTO rates",
    "SELECT 1 -- read first\n; DELETE FROM rates",
    "SELECT 1 /* read first */; UPDATE rates SET rate=0",
    "WITH rows AS (DELETE FROM rates RETURNING *) SELECT * FROM rows",
    "WITH rows AS (SELECT 1 AS id) UPDATE rates SET rate=0",
    "SELECT 1 UNION SELECT 2 INTO rates",
    "SELECT * FROM OPENQUERY(server, 'DELETE FROM rates')",
    "EXEC('DELETE FROM rates')", "CALL procedure()", "SELECT NEXT VALUE FOR seq",
    "COPY rates TO 'rates.csv'", "ATTACH 'rates.db' AS rates", "",
    "SELECT * FROM postgres_query('dsn', 'DELETE FROM rates RETURNING *')",
    "SELECT mutate_rates()", "SELECT dbo.sum(1)",
])
@pytest.mark.parametrize("execute", [
    query_runner.execute_odbc_query, query_runner.execute_odbc_query_with_types,
])
def test_odbc_denies_unsafe_sql_before_connection(sql, execute, rights, no_live_database):
    with pytest.raises(ReadOnlyDataError):
        execute("UL_Rates", sql)
    no_live_database.assert_not_called()
    rights[1].assert_called_with(refresh=True)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM rates",
    "WITH recent_rates AS (SELECT * FROM rates) SELECT * FROM recent_rates",
    "SELECT 'DELETE; INTO UPDATE' AS [label] /* DROP */",
    "SELECT * FROM rates WHERE rate > 0 UNION ALL SELECT * FROM rates;",
    "SELECT * FROM rates FETCH FIRST 100 ROWS ONLY WITH UR",
    "SELECT COUNT(*), COALESCE(SUM(rate), 0) FROM rates",
    "SELECT REPLACE('UPDATE', 'UP', 'DOWN') AS label",
])
def test_read_only_role_can_still_run_read_queries(sql, rights, monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.description = [("rate",)]
    cursor.fetchall.return_value = [(1,)]
    monkeypatch.setattr(query_runner, "connect_dsn", Mock(return_value=connection))
    assert query_runner.execute_odbc_query("UL_Rates", sql) == (["rate"], [(1,)])
    cursor.execute.assert_called_once_with(sql)
    connection.close.assert_called_once()


def test_permission_is_rechecked_for_each_sql_execution(rights):
    rights[0].can_update_database = True
    guard_query_sql("DELETE FROM rates")
    rights[0].can_update_database = False
    with pytest.raises(ReadOnlyDataError):
        guard_query_sql("DELETE FROM rates")
    assert rights[1].call_count == 2


def test_duckdb_rejects_writes_before_registering_sources(rights):
    from suiteview.audit.dataforge.forge_engine import run_manual_sql

    connection = MagicMock()
    with pytest.raises(ReadOnlyDataError):
        run_manual_sql({"rates": object()}, "DELETE FROM rates", connection=connection)
    connection.register.assert_not_called()
    connection.execute.assert_not_called()


@pytest.mark.parametrize("operation", [
    lambda: loader.execute_package(None, "UL_Rates", {}, ""),
    lambda: loader.ULRatesRepository().apply_plan(None),
    lambda: loader.update_pointer_row("UL_Rates", "POINT_PVSRB", (), ()),
    lambda: loader.delete_pointer_rows("UL_Rates", "POINT_PVSRB", ()),
    lambda: loader.delete_rate_index("UL_Rates", "RATE_COI", 1, ()),
    lambda: loader._insert_rows(loader.ULRatesRepository(), None, ()),
    lambda: loader._delete_exact_rows(loader.ULRatesRepository(), None, ()),
    lambda: mortality_loader.replace_live(None),
    lambda: WholeLifeRepository().create_tables(),
    lambda: WholeLifeRepository().apply(None, set()),
    registry._ensure_source_dsn_column,
    registry._ensure_column_note_table,
    lambda: registry.fetch_and_register("table", "column"),
    lambda: registry.update_value(1, notes="note"),
    lambda: registry.add_value(1, "value"),
    lambda: registry.deactivate_value(1),
    lambda: registry.delete_registration(1),
    lambda: registry.permanently_delete_field(1),
    lambda: registry.permanently_delete_table("table"),
    lambda: registry.set_column_note("UL_Rates", "table", "column", "note"),
])
def test_direct_mutations_deny_before_any_effect(operation, rights, no_live_database):
    with pytest.raises(ReadOnlyDataError):
        operation()
    no_live_database.assert_not_called()


def test_allowed_registry_write_commits_and_failure_rolls_back(rights, monkeypatch):
    rights[0].can_update_database = True
    connection = MagicMock()
    monkeypatch.setattr(registry, "_connect", lambda: connection)
    registry.update_value(1, notes="note")
    connection.commit.assert_called_once()
    connection.close.assert_called_once()
    connection.reset_mock()
    connection.cursor.return_value.execute.side_effect = RuntimeError("write failed")
    with pytest.raises(RuntimeError, match="write failed"):
        registry.update_value(1, notes="note")
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


@pytest.mark.parametrize("schema,table,index", [
    (loader.UL_SCHEMA, "RATE_COI", 10),
    (loader.TERM_SCHEMA, "TERM_RATE_PREM", "1001_PL"),
])
@pytest.mark.parametrize("role", ["ADMIN", "SUPPORT"])
def test_allowed_rate_plan_executes_and_denied_role_cannot_reuse_it(
    schema, table, index, role, rights, monkeypatch,
):
    rights[0].can_update_database = True
    rights[0].role_code = role
    repository = loader.ULRatesRepository(schema=schema)
    connection = MagicMock()
    connection.cursor.return_value.rowcount = 2
    monkeypatch.setattr(repository, "connect", lambda: connection)
    plan = loader.ExecutionPlan(
        "PLAN", {}, {}, {}, {table: frozenset({index})}, {}, (),
    )
    assert repository.apply_plan(plan) == {table: 2}
    connection.cursor.return_value.execute.assert_called_once()
    connection.reset_mock()
    rights[0].can_update_database = False
    with pytest.raises(ReadOnlyDataError):
        repository.apply_plan(plan)
    connection.cursor.assert_not_called()


@pytest.mark.parametrize("revoked", [False, True])
def test_rate_load_rechecks_after_analysis_and_rolls_back_on_denial(
    revoked, rights, monkeypatch,
):
    rights[0].can_update_database = True
    connection = MagicMock()
    connection.cursor.return_value.rowcount = 2
    repository = loader.ULRatesRepository()
    monkeypatch.setattr(repository, "connect", lambda: connection)
    monkeypatch.setattr(repository, "close", Mock())
    monkeypatch.setattr(repository, "rollback", connection.rollback)
    monkeypatch.setattr(loader, "ULRatesRepository", lambda *args: repository)
    plan = loader.ExecutionPlan(
        "PLAN", {}, {}, {}, {"RATE_COI": frozenset({10})}, {}, (),
    )

    def analyze(*args):
        rights[0].can_update_database = not revoked
        return SimpleNamespace(signature="reviewed")

    monkeypatch.setattr(loader, "analyze_package", analyze)
    monkeypatch.setattr(loader, "create_execution_plan", lambda *args: plan)
    monkeypatch.setattr(loader, "write_backup", lambda *args: None)
    monkeypatch.setattr(loader, "verify_package_state", Mock())
    monkeypatch.setattr(loader, "_clear_rate_cache", Mock())
    package = SimpleNamespace(schema=loader.UL_SCHEMA, plancode="PLAN")
    if revoked:
        with pytest.raises(ReadOnlyDataError):
            loader.execute_package(package, "UL_Rates", {}, "reviewed")
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
        assert not any(
            call.args[0].startswith("DELETE")
            for call in connection.cursor.return_value.execute.call_args_list
        )
    else:
        loader.execute_package(package, "UL_Rates", {}, "reviewed")
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("allowed", [False, True])
@pytest.mark.parametrize("method,row", [
    ("_edit_interest_rate_dialog", ["2026-09-01", "4.5", "5"]),
    ("_edit_per_diem_dialog", ["2026", "420", "153300"]),
    ("_edit_state_variation_dialog", ["01", "TX", "Texas", "A", "250", "", "", "", ""]),
    ("_edit_min_face_dialog", ["PLAN", "10000"]),
    ("_edit_modal_factor_dialog", ["PLAN", "12", "Annual", "1"]),
    ("_edit_band_amount_dialog", ["PLAN", "1", "100000"]),
    ("_edit_policy_fee_dialog", ["PLAN", "50"]),
])
def test_abr_dialog_saves_recheck_permission_after_accept(
    method, row, allowed, app, rights, monkeypatch,
):
    from suiteview.abrquote.ui import rate_viewer_dialog as abr

    owner = QWidget()
    owner._status_label = Mock()
    owner._type_combo = Mock()
    owner._on_type_changed = Mock()
    database = MagicMock()
    get_database = Mock(return_value=database)
    monkeypatch.setattr(abr, "get_abr_database", get_database)
    error = Mock()
    monkeypatch.setattr(QMessageBox, "critical", error)
    monkeypatch.setattr(QMessageBox, "warning", Mock())

    def accept(dialog):
        rights[0].can_update_database = allowed
        return QDialog.DialogCode.Accepted

    rights[0].can_update_database = True
    monkeypatch.setattr(QDialog, "exec", accept)
    try:
        getattr(abr.RateViewerDialog, method)(owner, row)
        if allowed:
            database.connect.return_value.commit.assert_called_once()
            error.assert_not_called()
        else:
            get_database.assert_not_called()
            assert "CanUpdateDatabase" in error.call_args.args[2]
    finally:
        owner.close()
        owner.deleteLater()


@pytest.mark.parametrize("method,args", [
    ("_run_build_sql", ("DELETE FROM rates",)),
    ("_run_manual_sql_preview", ("DELETE FROM rates",)),
    ("_run_manual_sql_preview_file", ("file:test", "DELETE FROM rates")),
    ("_start_manual_sql_object", ()),
    ("open_manual_sql_object", (None,)),
    ("_on_move_to_build", ("SELECT 1",)),
])
def test_manual_actions_deny_before_accessing_editor_or_database(
    method, args, app, rights, monkeypatch, no_live_database,
):
    from suiteview.audit.audit_window import AuditWindow

    owner = QWidget()
    owner._allow_manual_sql = MethodType(AuditWindow._allow_manual_sql, owner)
    notice = Mock()
    monkeypatch.setattr(QMessageBox, "information", notice)
    try:
        getattr(AuditWindow, method)(owner, *args)
        assert "CanUpdateDatabase" in notice.call_args.args[2]
        no_live_database.assert_not_called()
    finally:
        owner.close()
        owner.deleteLater()


def test_abr_delete_rechecks_permission_after_confirmation(app, rights, monkeypatch):
    from suiteview.abrquote.ui import rate_viewer_dialog as abr

    owner = QWidget()
    owner._reject_write = Mock(return_value=False)
    owner._get_selected_row_data = Mock(return_value=["PLAN", "50"])
    owner._current_table_key = "policy_fees"
    get_database = Mock()
    monkeypatch.setattr(abr, "get_abr_database", get_database)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    error = Mock()
    monkeypatch.setattr(QMessageBox, "critical", error)
    try:
        abr.RateViewerDialog._on_delete_row(owner)
        get_database.assert_not_called()
        assert "CanUpdateDatabase" in error.call_args.args[2]
    finally:
        owner.close()
        owner.deleteLater()


@pytest.mark.parametrize("method", [
    "_run", "execute_query", "execute_query_with_headers",
    "execute_query_as_dict", "execute_scalar", "execute_query_with_headers_isolated",
])
def test_all_apps_cannot_write_through_shared_db2_helpers(
    method, monkeypatch, no_live_database,
):
    rights = access_control.EffectiveAccess("USER", "ALL_APPS", True, False, False)
    monkeypatch.setattr(access_control, "get_access", lambda **_: rights)
    database = db2_connection.DB2Connection()
    connect = Mock(side_effect=AssertionError("Denied SQL must not connect"))
    monkeypatch.setattr(database, "connect", connect)
    with pytest.raises(ReadOnlyDataError):
        getattr(database, method)("DELETE FROM DB2TAB.LH_BAS_POL")
    connect.assert_not_called()
    no_live_database.assert_not_called()


def test_all_apps_cannot_write_through_shared_rate_helper(monkeypatch, no_live_database):
    rights = access_control.EffectiveAccess("USER", "ALL_APPS", True, False, False)
    monkeypatch.setattr(access_control, "get_access", lambda **_: rights)
    database = Rates()
    connect = Mock(side_effect=AssertionError("Denied SQL must not connect"))
    monkeypatch.setattr(database, "_get_connection", connect)
    with pytest.raises(ReadOnlyDataError):
        database._fetch_rates("UPDATE RATE_COI SET Rate=0")
    connect.assert_not_called()
    no_live_database.assert_not_called()


@pytest.mark.parametrize("isolated", [False, True])
def test_read_only_shared_db2_select_preserves_parameters_and_schema_rewrite(
    isolated, rights, monkeypatch,
):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.description = [("CK_POLICY_NBR",)]
    cursor.fetchall.return_value = [("POLICY",)]
    monkeypatch.setattr(db2_connection, "local_data_enabled", lambda: False)
    monkeypatch.setattr(db2_connection.pyodbc, "connect", Mock(return_value=connection))
    database = db2_connection.DB2Connection("CKAS")
    monkeypatch.setattr(database, "connect", lambda: connection)
    execute = (
        database.execute_query_with_headers_isolated if isolated
        else database.execute_query_with_headers
    )
    assert execute(
        "SELECT CK_POLICY_NBR FROM DB2TAB.LH_BAS_POL WHERE CK_POLICY_NBR = ?",
        ("POLICY",),
    ) == (["CK_POLICY_NBR"], [("POLICY",)])
    sent_sql, parameters = cursor.execute.call_args.args
    assert sent_sql.startswith("WITH DUMBY")
    assert "UNIT.LH_BAS_POL" in sent_sql
    assert parameters == ("POLICY",)
    cursor.close.assert_called_once()
    if isolated:
        connection.close.assert_called_once()


def test_read_only_rate_select_still_returns_data(rights, monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.return_value = [(1.5,)]
    database = Rates()
    monkeypatch.setattr(database, "_get_connection", lambda: connection)
    sql = "SELECT Rate FROM Select_RATE_COI WHERE Plancode=?"
    assert database._fetch_rates(sql, ["PLAN"]) == [(1.5,)]
    cursor.execute.assert_called_once_with(sql, ["PLAN"])
    cursor.close.assert_called_once()


@pytest.mark.parametrize("sql", [
    "UPDATE SV_AccessUser SET RoleCode='ADMIN' WHERE NetworkID='USER'",
    "UPDATE SV_AccessRole SET CanUpdateDatabase=1 WHERE RoleCode='SUPPORT'",
    "EXEC('UPDATE SV_AccessUser SET RoleCode=''ADMIN''')",
    "SELECT 1; UPDATE SV_AccessUser SET RoleCode='ADMIN'",
    "SELECT 1; EXEC dbo.ChangeAccessRole 'USER', 'ADMIN'",
])
@pytest.mark.parametrize("role,can_write", [("SUPPORT", True), ("ADMIN", False)])
def test_arbitrary_access_mutations_require_admin_and_write_permission(
    sql, role, can_write, monkeypatch, no_live_database,
):
    rights = access_control.EffectiveAccess(
        "USER", role, True, can_write, True,
    )
    monkeypatch.setattr(access_control, "get_access", lambda **_: rights)
    with pytest.raises(ReadOnlyDataError, match="ADMIN.*CanUpdateDatabase"):
        query_runner.execute_odbc_query("UL_Rates", sql)
    with pytest.raises(ReadOnlyDataError, match="ADMIN.*CanUpdateDatabase"):
        db2_connection.DB2Connection().execute_query_with_headers_isolated(sql)
    no_live_database.assert_not_called()


def test_admin_with_write_permission_can_use_arbitrary_sql_guard(monkeypatch):
    rights = access_control.EffectiveAccess("USER", "ADMIN", True, True, True)
    resolver = Mock(return_value=rights)
    monkeypatch.setattr(access_control, "get_access", resolver)
    guard_query_sql("UPDATE SV_AccessUser SET RoleCode='ADMIN'")
    guard_query_sql("EXEC dbo.ChangeAccessRole 'USER', 'ADMIN'; SELECT 1")
    assert resolver.call_count == 2
    resolver.assert_called_with(refresh=True)


def test_support_can_read_and_use_controlled_registry_writes(monkeypatch):
    rights = access_control.EffectiveAccess("USER", "SUPPORT", True, True, True)
    monkeypatch.setattr(access_control, "get_access", lambda **_: rights)
    guard_query_sql(
        "WITH active_rates AS (SELECT * FROM RATE_COI) SELECT * FROM active_rates"
    )
    connection = MagicMock()
    monkeypatch.setattr(registry, "_connect", lambda: connection)
    registry.update_value(1, notes="Reviewed rate value")
    connection.commit.assert_called_once()
    assert connection.cursor.return_value.execute.call_args.args[0].startswith(
        "UPDATE [ABATBL_FIELD_VAL]"
    )


def test_source_remains_unrestricted_for_arbitrary_sql(monkeypatch, no_live_database):
    from suiteview.core import build_env

    monkeypatch.delattr(build_env.sys, "frozen", raising=False)
    guard_query_sql("EXEC dbo.ChangeAccessRole 'USER', 'ADMIN'; SELECT 1")
    no_live_database.assert_not_called()
