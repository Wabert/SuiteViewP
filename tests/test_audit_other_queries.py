"""Other Queries matches the original lookup semantics without live databases."""
import sqlite3
from unittest.mock import MagicMock

import pytest
import pyodbc

from suiteview.audit.other_queries import build_other_query, execute_other_query
from suiteview.core import access_control, db2_connection
from suiteview.core.data_access import connections


@pytest.fixture
def data():
    db = sqlite3.connect(":memory:")
    db.execute("ATTACH DATABASE ':memory:' AS DB2TAB")
    db.execute("""CREATE TABLE DB2TAB.LH_COV_PHA (
        CK_SYS_CD TEXT, CK_CMP_CD TEXT, TCH_POL_ID TEXT, COV_PHA_NBR INTEGER,
        PLN_DES_SER_CD TEXT, POL_FRM_NBR TEXT)""")
    db.execute("""CREATE TABLE DB2TAB.LH_BAS_POL (
        CK_SYS_CD TEXT, CK_CMP_CD TEXT, TCH_POL_ID TEXT, CK_POLICY_NBR TEXT)""")
    db.executemany("INSERT INTO DB2TAB.LH_BAS_POL VALUES (?, ?, ?, ?)", [
        ("I", "01", "P1", "U000001"), ("I", "01", "P2", "U000002"),
        ("I", "04", "P1", "U000003"), ("M", "01", "P1", "U000004"),
    ])
    db.executemany("INSERT INTO DB2TAB.LH_COV_PHA VALUES (?, ?, ?, ?, ?, ?)", [
        ("I", "01", "P1", 1, "BASE", "BF"),
        ("I", "01", "P1", 2, "BASE", "BF"),
        ("I", "01", "P1", 3, "RIDER", "RF"),
        ("I", "01", "P1", 4, "RIDER", "RF"),
        ("I", "01", "P1", 5, "RIDER2", "RF2"),
        ("I", "01", "P2", 1, "BASE", "BF"),
        ("I", "01", "P2", 2, "RIDER", "RF"),
        ("I", "04", "P1", 1, "OTHER", "OF"),
        ("I", "04", "P1", 2, "RIDER", "RF"),
        ("M", "01", "P1", 1, "MODEL", "MF"),
        ("M", "01", "P1", 2, "RIDER", "RF"),
    ])
    db.execute("CREATE TABLE DB2TAB.TEST_TBL (TCH_POL_ID TEXT, VALUE TEXT)")
    db.executemany("INSERT INTO DB2TAB.TEST_TBL VALUES (?, ?)", [
        ("P1", "A"), ("P1", "A"), ("P2", "A"), ("P3", None), ("P4", ""), (None, "Z"),
    ])
    yield db
    db.close()


def test_riders_count_coverages_and_exclude_same_plan_increases(data):
    query = build_other_query("riders", "CKPR", plancode=" base ")
    assert query.params == ("BASE", "BASE")
    assert data.execute(query.sql, query.params).fetchall() == [
        ("BASE", "BF", "RIDER", "RF", 3),
        ("BASE", "BF", "RIDER2", "RF2", 1),
    ]
    assert query.columns[-1] == "Rider Count"
    assert "COUNT(*)" in query.sql
    assert "COUNT(R.PLN_DES_SER_CD)" not in query.sql


def test_find_base_preserves_company_and_system_keys(data):
    query = build_other_query("bases", "CKPR", plancode="RIDER")
    assert data.execute(query.sql, query.params).fetchall() == [
        ("RIDER", "RF", "BASE", "BF", 3),
        ("RIDER", "RF", "MODEL", "MF", 1),
        ("RIDER", "RF", "OTHER", "OF", 1),
    ]
    assert "COUNT(*)" in query.sql


@pytest.mark.parametrize("kind,plan", [("riders", "BASE"), ("bases", "RIDER")])
def test_counts_include_active_and_inactive_coverages_and_policies(data, kind, plan):
    data.execute("ALTER TABLE DB2TAB.LH_COV_PHA ADD COLUMN COV_PHA_STA_CD TEXT")
    data.execute("ALTER TABLE DB2TAB.LH_BAS_POL ADD COLUMN PRM_PAY_STA_REA_CD TEXT")
    data.execute("UPDATE DB2TAB.LH_COV_PHA SET COV_PHA_STA_CD = '1'")
    data.execute("UPDATE DB2TAB.LH_BAS_POL SET PRM_PAY_STA_REA_CD = '1'")
    data.execute("UPDATE DB2TAB.LH_COV_PHA SET COV_PHA_STA_CD = '9' WHERE COV_PHA_NBR = 4")
    data.execute("UPDATE DB2TAB.LH_BAS_POL SET PRM_PAY_STA_REA_CD = '9' WHERE TCH_POL_ID = 'P2'")
    query = build_other_query(kind, "CKPR", plancode=plan)
    rows = data.execute(query.sql, query.params).fetchall()
    base_row = next(row for row in rows if "BASE" in row and "RIDER" in row)
    assert base_row[-1] == 3


@pytest.mark.parametrize("kind,plan,expected", [
    ("riders", "BASE", [("U000001", "01"), ("U000001", "01"), ("U000002", "01"), ("U000001", "01")]),
    ("bases", "RIDER", [("U000001", "01"), ("U000001", "01"), ("U000002", "01"), ("U000004", "01"), ("U000003", "04")]),
])
def test_each_show_policies_toggle_returns_real_policy_number_per_coverage(data, kind, plan, expected):
    query = build_other_query(kind, "CKPR", plancode=plan, show_policies=True)
    assert query.columns[-2:] == ("Policy Number", "Company")
    assert "GROUP BY" not in query.sql
    assert [row[-2:] for row in data.execute(query.sql, query.params)] == expected


def test_values_count_records_not_distinct_policies_and_preserve_null_and_blank(data):
    query = build_other_query("values", "CKPR", table="test_tbl", field="value")
    assert query.columns == ("Field Value", "Record Count")
    assert dict(data.execute(query.sql).fetchall()) == {"A": 3, None: 1, "": 1, "Z": 0}
    assert "SUM(CASE WHEN V.TCH_POL_ID IS NOT NULL THEN 1 ELSE 0 END)" in query.sql
    assert "COUNT(V.TCH_POL_ID)" not in query.sql


def test_plancode_is_bound_not_interpolated_and_preview_escapes_literals(data):
    query = build_other_query("riders", "CKPR", plancode="x' or 1=1 --?")
    assert "OR 1=1" not in query.sql
    assert query.params == ("X' OR 1=1 --?",) * 2
    assert data.execute(query.sql, query.params).fetchall() == []
    assert query.display_sql().count("'X'' OR 1=1 --?'") == 2
    assert data.execute(query.display_sql()).fetchall() == []


@pytest.mark.parametrize("table,field", [
    ("LH_BAS_POL; DROP TABLE X", "CK_POLICY_NBR"),
    ("DB2TAB.LH_BAS_POL", "CK_POLICY_NBR"), ("LH_BAS_POL", "*"),
    ("LH_BAS_POL", "CK_POLICY_NBR) UNION SELECT X"), ("", "FIELD"), ("TABLE", ""),
])
def test_values_reject_sql_in_identifier_inputs(table, field):
    with pytest.raises(ValueError, match="unqualified name"):
        build_other_query("values", "CKPR", table=table, field=field)


@pytest.mark.parametrize("kind", ["riders", "bases"])
def test_blank_plancode_is_explicit_error(kind):
    with pytest.raises(ValueError, match="plancode"):
        build_other_query(kind, "CKPR", plancode=" ")


@pytest.mark.parametrize("region,schema", [
    ("CKPR", "DB2TAB"), ("CKMO", "DB2TAB"), ("CKAS", "UNIT"),
    ("CKCS", "CYBERTEK"), ("CKSR", "CKSR"),
])
def test_regions_apply_to_every_lookup(region, schema):
    for kind in ("riders", "bases", "values"):
        query = build_other_query(kind, region, plancode="BASE", table="LH_BAS_POL", field="CK_CMP_CD")
        assert f"FROM {schema}." in query.sql
    with pytest.raises(ValueError, match="Unknown CyberLife region"):
        build_other_query("riders", "UNKNOWN", plancode="BASE")


@pytest.mark.parametrize("kind,show_policies", [
    ("riders", False), ("riders", True), ("bases", False), ("bases", True), ("values", False),
])
def test_execution_uses_restricted_isolated_db2_and_varchar_binding(monkeypatch, kind, show_policies):
    rights = access_control.EffectiveAccess("TEST", "READER", True, False, False)
    monkeypatch.setattr(access_control, "get_access", lambda **kwargs: rights)
    monkeypatch.setattr(db2_connection, "local_data_enabled", lambda: False)
    local = MagicMock(side_effect=AssertionError("No local fallback"))
    monkeypatch.setattr(connections, "connect_local_policy_database", local)
    connection = MagicMock()
    monkeypatch.setattr(
        db2_connection.connection_factory,
        "connect_policy_db2",
        MagicMock(return_value=connection),
    )
    cursor = connection.cursor.return_value
    query = build_other_query(kind, "CKAS", plancode="BASE", show_policies=show_policies,
                              table="LH_BAS_POL", field="CK_CMP_CD")
    cursor.description = [(name,) for name in query.columns]
    cursor.fetchall.return_value = []
    frame = execute_other_query(query, "CKAS")
    assert list(frame.columns) == list(query.columns)
    assert frame.empty
    assert "UNIT." in cursor.execute.call_args.args[0]
    if query.params:
        assert cursor.execute.call_args.args[1] == query.params
        cursor.setinputsizes.assert_called_once_with([(pyodbc.SQL_VARCHAR, 4, 0)] * len(query.params))
    else:
        cursor.setinputsizes.assert_not_called()
    cursor.close.assert_called_once()
    connection.close.assert_called_once()
    connection.commit.assert_not_called()
    local.assert_not_called()


def test_query_failure_is_not_an_empty_success(monkeypatch):
    connection = MagicMock()
    monkeypatch.setattr(db2_connection, "local_data_enabled", lambda: False)
    monkeypatch.setattr(db2_connection.pyodbc, "connect", MagicMock(return_value=connection))
    connection.cursor.return_value.execute.side_effect = pyodbc.Error("42S22", "Unknown field")
    query = build_other_query("values", "CKPR", table="LH_BAS_POL", field="UNKNOWN")
    with pytest.raises(pyodbc.Error, match="Unknown field"):
        execute_other_query(query, "CKPR")
    connection.cursor.return_value.close.assert_called_once()
    connection.close.assert_called_once()
