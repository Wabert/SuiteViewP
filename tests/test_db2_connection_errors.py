import pyodbc

from suiteview.core.db2_connection import _extract_odbc_message


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
