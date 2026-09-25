"""Mixed-source Visual Queries: SQL builder ordering, federated planning/execution.

No database access: ODBC and file loading are replaced by in-memory fakes.
"""
from __future__ import annotations

import re
from decimal import Decimal

import pandas as pd
import pytest

from suiteview.audit.dynamic_query import (
    DB2,
    DUCKDB,
    SQL_SERVER,
    build_join_sql,
    choose_primary_table,
    order_join_infos,
    split_field_key,
)
from suiteview.audit.federated_query import (
    execute_federated_plan,
    plan_federated_query,
)

FILE = "file:abc"
DSN = "NEON_DSN"
POL = "DB2TAB.LH_BAS_POL"
COV = "DB2TAB.LH_COV_PHA"
CSV = "UL_SLR_202606"


def _join(left, right, how="INNER JOIN", pairs=(("k", "k"),)):
    return {"left_table": left, "right_table": right, "join_type": how,
            "alias_left": "", "alias_right": "", "on_pairs": list(pairs),
            "extra_conditions": []}


# ── SQL builder ──────────────────────────────────────────────────────────

def test_join_drawn_toward_primary_keeps_preserved_side():
    # User drew B -> A and chose "all rows from B"; A is the FROM table.
    ordered = order_join_infos("A", [_join("B", "A", "LEFT OUTER JOIN")])
    assert ordered[0]["left_table"] == "A"
    assert ordered[0]["right_table"] == "B"
    assert ordered[0]["join_type"] == "RIGHT OUTER JOIN"

    sql = build_join_sql("A", "", [], join_infos=[_join("B", "A", "LEFT OUTER JOIN",
                                                        [("b_key", "a_key")])],
                         dialect=SQL_SERVER)
    assert "FROM A\n  RIGHT OUTER JOIN B\n    ON A.[a_key] = B.[b_key]" in sql


def test_joins_are_emitted_in_connected_order():
    # B-C is listed first but only becomes reachable after A-B.
    sql = build_join_sql("A", "", [], join_infos=[_join("B", "C"), _join("A", "B")],
                         dialect=SQL_SERVER)
    assert sql.index("JOIN B") < sql.index("JOIN C")


def test_disconnected_join_is_an_explicit_error():
    with pytest.raises(ValueError, match="not connected"):
        order_join_infos("A", [_join("B", "C")])


def test_join_cycle_becomes_extra_on_condition():
    infos = [_join("A", "B"), _join("B", "C"), _join("C", "A", pairs=[("x", "y")])]
    sql = build_join_sql("A", "", [], join_infos=infos, dialect=SQL_SERVER)
    assert sql.count("JOIN") == 2
    assert "C.[x] = A.[y]" in sql


def test_field_keys_keep_dotted_file_column_names():
    known = [CSV, POL]
    assert split_field_key(f"{CSV}.SLR Output[Source.Name]", known) == (
        CSV, "SLR Output[Source.Name]")
    assert split_field_key(f"{POL}.TCH_POL_ID", known) == (POL, "TCH_POL_ID")
    sql = build_join_sql(
        CSV, "", [],
        join_infos=[_join(CSV, POL, pairs=[("PolicyId", "CK_POLICY_NBR")])],
        select_columns=[{"column": "SLR Output[Source.Name]",
                         "field_key": f"{CSV}.SLR Output[Source.Name]",
                         "aggregate": "display"}],
        dialect=DUCKDB)
    assert f'{CSV}."SLR Output[Source.Name]"' in sql
    assert '"DB2TAB.LH_BAS_POL"."CK_POLICY_NBR"' in sql


def test_primary_is_first_used_table_in_the_join_graph():
    infos = [_join(POL, CSV)]
    assert choose_primary_table([COV, CSV], infos, "x") == CSV
    assert choose_primary_table([], infos, "x") == POL
    assert choose_primary_table([], [], "x") == "x"


# ── Federated planning ───────────────────────────────────────────────────

def _plan(join_type="INNER JOIN", filters=(), select=None, display_all=False,
          left=CSV, right=POL, pairs=(("PolicyId", "CK_POLICY_NBR"),), max_count="25"):
    select = select if select is not None else [
        {"column": "PolicyId", "field_key": f"{CSV}.PolicyId", "aggregate": "display"},
        {"column": "TCH_POL_ID", "field_key": f"{POL}.TCH_POL_ID", "aggregate": "display"},
    ]
    return plan_federated_query(
        table_sources={CSV: FILE, POL: DSN},
        used_tables=[CSV, POL],
        primary_table=CSV,
        field_filters=list(filters),
        select_columns=select,
        join_infos=[_join(left, right, join_type, pairs)],
        max_count=max_count,
        display_all=display_all,
        dialect_for=lambda _dsn: DB2,
        source_labels={FILE: "UL_SLR [CSV]"},
    )


def test_inner_join_restricts_database_table_by_file_keys():
    plan = _plan()
    assert plan.local_tables == [CSV]
    [step] = plan.steps
    assert step.table == POL and step.dsn == DSN
    assert step.restricted and plan.unrestricted_tables() == []
    assert [(p.column, p.from_table, p.from_column) for p in step.pushdowns] == [
        ("CK_POLICY_NBR", CSV, "PolicyId")]
    assert step.columns == ["TCH_POL_ID", "CK_POLICY_NBR"]
    assert '"DB2TAB.LH_BAS_POL"' in plan.final_sql
    assert "LIMIT 25" in plan.final_sql
    text = plan.describe()
    assert text.startswith("-- Mixed-source query")
    assert "restricted to CK_POLICY_NBR values found in UL_SLR_202606.PolicyId" in text


def test_preserved_database_side_is_never_restricted():
    # POL LEFT JOIN CSV keeps every POL row — pushing file keys would drop rows.
    plan = _plan("LEFT OUTER JOIN", left=POL, right=CSV,
                 pairs=[("CK_POLICY_NBR", "PolicyId")])
    assert plan.steps[0].pushdowns == []
    assert plan.unrestricted_tables() == [POL]
    assert "NOT RESTRICTED" in plan.describe()

    # CSV LEFT JOIN POL: POL is null-supplying, so the restriction is safe.
    plan = _plan("LEFT OUTER JOIN")
    assert plan.steps[0].pushdowns


def test_database_filters_run_on_database_and_become_not_null_in_duckdb():
    filt = {"column": "CK_CMP_CD", "field_key": f"{POL}.CK_CMP_CD",
            "mode": "combo", "value": "01"}
    plan = _plan(filters=[filt])
    step = plan.steps[0]
    assert "\"CK_CMP_CD\" = '01'" in step.render()
    assert '"DB2TAB.LH_BAS_POL"."CK_CMP_CD" IS NOT NULL' in plan.final_sql
    assert "= '01'" not in plan.final_sql


def test_display_all_stages_every_column():
    plan = _plan(display_all=True)
    assert plan.steps[0].columns is None
    assert plan.steps[0].render().startswith("SELECT *")


# ── Federated execution ──────────────────────────────────────────────────

class FakeSession:
    """Serves a DB2 table from memory, honouring the pushed-down IN list."""

    def __init__(self, table: pd.DataFrame, key: str, types: dict[str, str]):
        self.table = table
        self.key = key
        self.types = types
        self.sql: list[str] = []

    def column_types(self, dsn, table):
        return dict(self.types)

    def fetch(self, dsn, sql):
        self.sql.append(sql)
        df = self.table
        if "1 = 0" in sql:
            return df.iloc[0:0]
        match = re.search(rf'"{self.key}" IN \((.*?)\)', sql, re.S)
        if match:
            raw = [v.strip() for v in match.group(1).split(",")]
            values = {v.strip("'") for v in raw}
            df = df[df[self.key].map(lambda v: str(v).strip() in values)]
        return df.reset_index(drop=True)

    def close(self):
        pass


def _file_loader(frame):
    def load(token, table, text_columns):
        assert token == FILE and table == CSV
        df = frame.copy()
        for col in text_columns:
            df[col] = df[col].astype(str)
        return df
    return load


def test_file_keys_restrict_and_join_padded_char_keys():
    db2 = pd.DataFrame({
        "CK_POLICY_NBR": ["000123   ", "000456   ", "000999   "],
        "TCH_POL_ID": ["000123  QA", "000456  QB", "000999  QC"],
    })
    session = FakeSession(db2, "CK_POLICY_NBR", {"CK_POLICY_NBR": "CHAR", "TCH_POL_ID": "CHAR"})
    csv = pd.DataFrame({"PolicyId": ["000123", "000456"]})
    df = execute_federated_plan(_plan(), session=session, file_loader=_file_loader(csv))

    assert "IN ('000123', '000456')" in session.sql[0]
    assert sorted(df["TCH_POL_ID"]) == ["000123  QA", "000456  QB"]


def test_numeric_database_key_compares_numerically_with_text_file_key():
    db2 = pd.DataFrame({"CK_POLICY_NBR": [Decimal("123"), Decimal("456")],
                        "TCH_POL_ID": ["A", "B"]})
    session = FakeSession(db2, "CK_POLICY_NBR", {"CK_POLICY_NBR": "DECIMAL"})
    csv = pd.DataFrame({"PolicyId": ["00123"]})
    df = execute_federated_plan(_plan(), session=session, file_loader=_file_loader(csv))

    assert "IN (123)" in session.sql[0]
    assert list(df["TCH_POL_ID"]) == ["A"]


def test_pushdown_is_chunked_and_empty_keys_fetch_no_rows():
    db2 = pd.DataFrame({"CK_POLICY_NBR": ["1", "2", "3"], "TCH_POL_ID": ["a", "b", "c"]})
    session = FakeSession(db2, "CK_POLICY_NBR", {"CK_POLICY_NBR": "CHAR"})
    csv = pd.DataFrame({"PolicyId": ["1", "2"]})
    df = execute_federated_plan(_plan(), session=session, file_loader=_file_loader(csv),
                                chunk_size=1)
    assert len(session.sql) == 2
    assert sorted(df["TCH_POL_ID"]) == ["a", "b"]

    session = FakeSession(db2, "CK_POLICY_NBR", {"CK_POLICY_NBR": "CHAR"})
    empty = pd.DataFrame({"PolicyId": pd.Series([], dtype=object)})
    df = execute_federated_plan(_plan(), session=session, file_loader=_file_loader(empty))
    assert "1 = 0" in session.sql[0]
    assert df.empty


def test_filter_on_null_supplying_database_table_keeps_where_semantics():
    # CSV LEFT JOIN POL WHERE POL.CK_CMP_CD = '01': policies without a matching
    # '01' row are removed, exactly as the single-database WHERE would.
    db2 = pd.DataFrame({"CK_POLICY_NBR": ["1"], "TCH_POL_ID": ["a"], "CK_CMP_CD": ["01"]})
    session = FakeSession(db2, "CK_POLICY_NBR", {"CK_POLICY_NBR": "CHAR"})
    csv = pd.DataFrame({"PolicyId": ["1", "2"]})
    filt = {"column": "CK_CMP_CD", "field_key": f"{POL}.CK_CMP_CD",
            "mode": "combo", "value": "01"}
    df = execute_federated_plan(_plan("LEFT OUTER JOIN", filters=[filt]), session=session,
                                file_loader=_file_loader(csv))
    assert list(df["PolicyId"]) == ["1"]


def test_decimal_value_columns_survive_duckdb_join():
    db2 = pd.DataFrame({"CK_POLICY_NBR": ["1", "2"],
                        "POL_PRM_AMT": [Decimal("125.50"), None]})
    session = FakeSession(db2, "CK_POLICY_NBR", {"CK_POLICY_NBR": "CHAR"})
    csv = pd.DataFrame({"PolicyId": ["1", "2"]})
    df = execute_federated_plan(_plan(display_all=True), session=session,
                                file_loader=_file_loader(csv))
    by_policy = dict(zip(df["PolicyId"], df["POL_PRM_AMT"]))
    assert float(by_policy["1"]) == 125.5
    assert pd.isna(by_policy["2"])


def test_join_keys_are_compared_without_changing_displayed_values():
    # Review regression: normalizing keys must not rewrite the user's columns.
    db2 = pd.DataFrame({"CK_POLICY_NBR": [Decimal("123")], "TCH_POL_ID": ["A"]})
    session = FakeSession(db2, "CK_POLICY_NBR", {"CK_POLICY_NBR": "DECIMAL"})
    csv = pd.DataFrame({"PolicyId": ["00123", "ABC9"]})
    select = [
        {"column": "PolicyId", "field_key": f"{CSV}.PolicyId", "aggregate": "display"},
        {"column": "TCH_POL_ID", "field_key": f"{POL}.TCH_POL_ID", "aggregate": "display"},
    ]
    for display_all in (False, True):
        plan = _plan("LEFT OUTER JOIN", select=select, display_all=display_all)
        assert "__svk" in plan.final_sql
        df = execute_federated_plan(plan, session=session, file_loader=_file_loader(csv))
        assert not [c for c in df.columns if str(c).startswith("__svk")]
        rows = dict(zip(df["PolicyId"], df["TCH_POL_ID"]))
        assert rows["00123"] == "A"
        assert pd.isna(rows["ABC9"])  # kept, key shown as pasted


def test_outer_join_chains_start_from_a_preserved_table():
    from suiteview.audit.dynamic_query import (
        find_outer_join_ambiguity, outer_join_ambiguity)

    chain = [_join("A", "B", "LEFT OUTER JOIN"), _join("B", "C", "LEFT OUTER JOIN")]
    # Field order no longer decides the FROM table: C and B are optional sides.
    assert choose_primary_table(["C", "B", "A"], chain) == "A"
    assert find_outer_join_ambiguity(chain) is None

    mixed = [_join("A", "B", "LEFT OUTER JOIN"), _join("B", "C")]
    assert find_outer_join_ambiguity(mixed) == ("B", "A", "C")
    assert "optional side" in outer_join_ambiguity(mixed)
    # An inner join on the preserved side is fine.
    assert find_outer_join_ambiguity(
        [_join("A", "B", "LEFT OUTER JOIN"), _join("A", "C")]) is None


def test_file_only_query_runs_without_database():
    plan = plan_federated_query(
        table_sources={CSV: FILE}, used_tables=[CSV], primary_table=CSV,
        field_filters=[], select_columns=[], join_infos=[], max_count="1",
        dialect_for=lambda _dsn: DB2)
    assert plan.steps == []
    csv = pd.DataFrame({"PolicyId": ["1", "2"]})
    df = execute_federated_plan(plan, session=FakeSession(csv, "x", {}),
                                file_loader=_file_loader(csv))
    assert len(df) == 1
