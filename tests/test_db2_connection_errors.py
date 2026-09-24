import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pyodbc
import pytest
import suiteview

from suiteview.core.db2_connection import _extract_odbc_message
from suiteview.core.odbc_utils import is_communication_error, is_password_error


def test_package_configures_odbc_before_any_connection(monkeypatch):
    def connect(*args, **kwargs):
        pytest.fail("Package initialization must not open database connections")

    driver = SimpleNamespace(pooling=True, connect=connect)
    monkeypatch.setitem(sys.modules, "pyodbc", driver)
    runpy.run_path(str(Path(suiteview.__file__)))
    assert driver.pooling is False


@pytest.mark.parametrize("message", [
    "[08001] [DV][ODBC Driver] SQLCODE = -30081, TCP/IP COMMUNICATIONS ERROR",
    "[08S01] [DV][ODBC Driver]Host communication failed",
    "[08006] Connection lost",
    "[08003] Connection does not exist",
])
def test_transport_failures_are_not_password_errors(message):
    assert is_communication_error(message)
    assert not is_password_error(message)


@pytest.mark.parametrize("message", [
    "[28000] Invalid authorization",
    "[08001] SQL30082N Security processing failed",
    "SQLCODE = -30082",
    "ODBC authentication failed",
    "The password has expired",
])
def test_authentication_failures_are_not_retried_as_transport(message):
    assert is_password_error(message)
    assert not is_communication_error(message)


@pytest.mark.parametrize("message", [
    "[42501] [ODBC] User is not authorized for SELECT. SQLCODE=-551",
    "[42S02] Table not found",
    "Failed to connect: unknown driver configuration",
    "<class 'pyodbc.Error'> returned a result with an exception set",
])
def test_other_errors_do_not_invent_password_or_transport_diagnosis(message):
    assert not is_password_error(message)
    assert not is_communication_error(message)


def test_extracts_single_argument_odbc_message_from_system_error_context():
    driver_message = (
        "[IBM][CLI Driver][DB2] SQL0551N \"AB7Y02\" does not have "
        "SELECT privilege. SQLSTATE=42501 SQLCODE=-551"
    )
    try:
        try:
            raise pyodbc.Error(driver_message)
        except pyodbc.Error:
            raise SystemError(
                "<class 'pyodbc.Error'> returned a result with an exception set"
            )
    except SystemError as exc:
        assert _extract_odbc_message(exc) == driver_message


def test_strips_nul_padded_driver_buffer_data():
    error = pyodbc.Error(
        "[42501] SQLCODE = -551 ON DB2TAB.LH_SWF_SCH"
        "\x00\x00corrupt driver buffer"
    )
    assert (
        _extract_odbc_message(error)
        == "[42501] SQLCODE = -551 ON DB2TAB.LH_SWF_SCH"
    )


@pytest.mark.parametrize("state,message,transport,authentication", [
    ("08S01", "Host communication failed", True, False),
    ("28000", "Authorization rejected", False, True),
    ("42704", "Undefined table", False, False),
])
def test_preserves_separate_sqlstate_through_wrapping(state, message, transport, authentication):
    driver_error = pyodbc.Error(state, message + "\x00corrupt buffer")
    wrapper = RuntimeError("Table fetch failed")
    wrapper.__cause__ = driver_error
    detail = _extract_odbc_message(wrapper)
    assert detail == f"[{state}] {message}"
    assert is_communication_error(detail) is transport
    assert is_password_error(detail) is authentication


def test_does_not_duplicate_sqlstate_already_in_driver_message():
    detail = _extract_odbc_message(pyodbc.Error("08S01", "[08S01] Host communication failed"))
    assert detail == "[08S01] Host communication failed"
