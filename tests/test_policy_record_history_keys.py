"""Financial-history table keys verified against live CKPR metadata."""

from unittest.mock import MagicMock

import pytest
from pyodbc import SQL_VARCHAR

from suiteview.polview.config.policy_records import POLICY_RECORD_TABLES
from suiteview.polview.models.policy_data import PolicyData


HISTORY_TABLES = POLICY_RECORD_TABLES["Policy Record 69"]


@pytest.fixture
def policy_data():
    data = PolicyData.__new__(PolicyData)
    data._exists = True
    data._policy_number = "TEST0001"
    data._policy_id = "TEST0001  QXXX"
    data._company_code = "01"
    data._system_code = "I"
    data._region = "CKPR"
    data._table_cache = {}
    data._table_errors = {}
    data._conn_mgr = MagicMock()
    cursor = data._conn_mgr.get_connection.return_value.cursor.return_value
    cursor.description = [("CK_CMP_CD",), ("TCH_POL_ID",)]
    cursor.fetchall.return_value = [("01", data._policy_id)]
    return data, cursor


@pytest.mark.parametrize("table", HISTORY_TABLES)
def test_history_uses_only_verified_policy_company_keys(policy_data, table):
    data, cursor = policy_data

    rows = data.fetch_table(table)

    sql = cursor.execute.call_args.args[0]
    assert f"FROM DB2TAB.{table} " in sql
    assert "CK_SYS_CD" not in sql
    assert "TCH_POL_ID = ? AND CK_CMP_CD = ?" in sql
    _, parameters = cursor.execute.call_args.args
    assert parameters == (data._policy_id, "01")
    cursor.setinputsizes.assert_called_once_with([
        (SQL_VARCHAR, len(data._policy_id), 0), (SQL_VARCHAR, 2, 0),
    ])
    assert rows == [{"CK_CMP_CD": "01", "TCH_POL_ID": data._policy_id}]
    assert data.table_error(table) == ""
    assert data.fetch_table(table) is rows
    cursor.execute.assert_called_once()
    cursor.close.assert_called_once()
    if table == "FH_FIXED":
        assert sql.endswith(" ORDER BY ASOF_DT DESC, SEQ_NO DESC")
    else:
        assert "ORDER BY" not in sql


@pytest.mark.parametrize(
    ("table", "ordering"),
    [
        ("LH_BAS_POL", ""),
        ("TH_BAS_POL", ""),
        ("LH_COV_PHA", " ORDER BY COV_PHA_NBR"),
        ("TH_COV_PHA", " ORDER BY COV_PHA_NBR"),
        ("LH_POL_MVRY_VAL", " ORDER BY MVRY_DT DESC"),
        ("FH_UNVERIFIED", ""),
    ],
)
def test_other_tables_keep_system_filter_and_ordering(policy_data, table, ordering):
    data, cursor = policy_data
    data._system_code = "M"

    data.fetch_table(table)

    sql, parameters = cursor.execute.call_args.args
    assert "CK_SYS_CD = ? AND TCH_POL_ID = ? AND CK_CMP_CD = ?" in sql
    assert parameters == ("M", data._policy_id, "01")
    cursor.setinputsizes.assert_called_once_with([
        (SQL_VARCHAR, 1, 0), (SQL_VARCHAR, len(data._policy_id), 0), (SQL_VARCHAR, 2, 0),
    ])
    if ordering:
        assert sql.endswith(ordering)
    else:
        assert "ORDER BY" not in sql


@pytest.mark.parametrize("table", ["FH_ACCTG", "FH_FIXED", "LH_BAS_POL"])
def test_policy_keys_are_bound_not_interpolated(policy_data, table):
    data, cursor = policy_data
    data._policy_id = "TEST'KEY"
    data._company_code = "O'NE"
    data._system_code = "I'"

    data.fetch_table(table)

    sql, parameters = cursor.execute.call_args.args
    for key in parameters:
        assert key not in sql
    assert parameters[-2:] == (data._policy_id, data._company_code)


def test_access_error_is_reported_without_unfiltered_retry(policy_data):
    data, cursor = policy_data
    cursor.execute.side_effect = RuntimeError("SQLCODE -551: not authorized")

    assert data.fetch_table("FH_ACCTG") == []
    assert data.table_error("FH_ACCTG") == "SQLCODE -551: not authorized"
    assert data.fetch_table("FH_ACCTG") == []
    cursor.execute.assert_called_once()
