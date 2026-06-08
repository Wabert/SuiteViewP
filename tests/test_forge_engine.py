"""Unit tests for the DataForge DuckDB engine (suiteview/audit/dataforge/forge_engine.py).

Self-contained: uses synthetic DataFrames, no live DB2/SQL Server needed, so it
runs on the minipc. Run directly (``python tests/test_forge_engine.py``) or via
pytest.
"""
import os
import sys

import pandas as pd

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from suiteview.audit.dataforge.forge_engine import (  # noqa: E402
    FilterSpec, ForgeEngineError, JoinSpec, OutputColumn, compile_forge_sql,
    run_forge,
)


def _policies() -> pd.DataFrame:
    return pd.DataFrame({
        "company_code": ["A", "A", "B", "B", "C"],
        "policy_number": ["100", "101", "200", "201", "300"],
        "face_amount": [50000, 75000, 120000, 60000, 90000],
        "status": ["INFORCE", "INFORCE", "LAPSED", "INFORCE", "INFORCE"],
    })


def _reinsurance() -> pd.DataFrame:
    return pd.DataFrame({
        "company_code": ["A", "A", "B", "B"],
        "policy_number": ["100", "101", "200", "999"],
        "reinsurer": ["XYZ", "ACME", "XYZ", "XYZ"],
        "ceded_amount": [25000, 30000, 80000, 11111],
    })


def _sap() -> pd.DataFrame:
    return pd.DataFrame({
        "company_code": ["A", "B"],
        "policy_number": ["100", "200"],
        "gl_account": ["GL-1", "GL-2"],
    })


def test_two_way_inner_multikey():
    res = run_forge(
        {"pol": _policies(), "re": _reinsurance()},
        [JoinSpec("pol", "re", ("company_code", "policy_number"),
                  ("company_code", "policy_number"), "inner")],
    )
    df = res.dataframe
    # Matches: (A,100),(A,101),(B,200). (B,201),(C,300) have no reinsurance;
    # (B,999) has no policy. Inner => 3 rows.
    assert len(df) == 3, df
    # Collision-safe columns: company_code appears in both -> suffixed.
    assert "company_code" in df.columns
    assert "company_code__re" in df.columns
    assert "reinsurer" in df.columns
    print("  two-way inner multikey:", list(df.columns), len(df), "rows  OK")


def test_left_join_keeps_unmatched():
    res = run_forge(
        {"pol": _policies(), "re": _reinsurance()},
        [JoinSpec("pol", "re", ("company_code", "policy_number"),
                  ("company_code", "policy_number"), "left")],
    )
    df = res.dataframe
    # Left keeps all 5 policies; 2 unmatched get NULL reinsurer.
    assert len(df) == 5, df
    assert df["reinsurer"].isna().sum() == 2, df["reinsurer"].tolist()
    print("  left join keeps unmatched:", len(df), "rows,",
          int(df["reinsurer"].isna().sum()), "null reinsurer  OK")


def test_three_way_join():
    res = run_forge(
        {"pol": _policies(), "re": _reinsurance(), "sap": _sap()},
        [
            JoinSpec("pol", "re", ("company_code", "policy_number"),
                     ("company_code", "policy_number"), "inner"),
            JoinSpec("pol", "sap", ("company_code", "policy_number"),
                     ("company_code", "policy_number"), "inner"),
        ],
    )
    df = res.dataframe
    # pol-re inner = (A,100),(A,101),(B,200); of those sap has (A,100),(B,200).
    assert len(df) == 2, df
    assert set(df["gl_account"]) == {"GL-1", "GL-2"}, df["gl_account"].tolist()
    print("  three-way join:", len(df), "rows, gl_accounts",
          sorted(df["gl_account"]), " OK")


def test_source_filter_contains_and_list():
    # Source filter on reinsurer = XYZ via list; restricts re before the join.
    res = run_forge(
        {"pol": _policies(), "re": _reinsurance()},
        [JoinSpec("pol", "re", ("company_code", "policy_number"),
                  ("company_code", "policy_number"), "inner")],
        filters=[FilterSpec("re", "reinsurer", "list", items=("XYZ",))],
    )
    df = res.dataframe
    # re XYZ rows: (A,100),(B,200),(B,999). Joined to pol inner => (A,100),(B,200).
    assert len(df) == 2, df
    assert set(df["reinsurer"]) == {"XYZ"}, df["reinsurer"].tolist()
    print("  source filter (list):", len(df), "rows  OK")


def test_source_filter_outer_semantics():
    # A source filter must restrict the Source *before* a LEFT join, so the
    # left side is fully preserved and only matching re rows attach.
    res = run_forge(
        {"pol": _policies(), "re": _reinsurance()},
        [JoinSpec("pol", "re", ("company_code", "policy_number"),
                  ("company_code", "policy_number"), "left")],
        filters=[FilterSpec("re", "reinsurer", "equals", value="ACME")],
    )
    df = res.dataframe
    # All 5 policies kept; only (A,101) matches ACME -> 1 non-null reinsurer.
    assert len(df) == 5, df
    assert (df["reinsurer"] == "ACME").sum() == 1, df["reinsurer"].tolist()
    assert df["reinsurer"].isna().sum() == 4
    print("  source filter preserves left-join:", len(df),
          "rows, 1 ACME  OK")


def test_result_filter_drops_unmatched_in_left_join():
    # Contrast with test_source_filter_outer_semantics: a *result* filter
    # applies to the joined output, so it DROPS the unmatched left rows.
    res = run_forge(
        {"pol": _policies(), "re": _reinsurance()},
        [JoinSpec("pol", "re", ("company_code", "policy_number"),
                  ("company_code", "policy_number"), "left")],
        result_filters=[FilterSpec("", "reinsurer", "equals", value="XYZ")],
    )
    df = res.dataframe
    # Left join = 5 rows; reinsurer == XYZ keeps only matched (A,100),(B,200).
    assert len(df) == 2, df
    assert set(df["reinsurer"]) == {"XYZ"}, df["reinsurer"].tolist()
    print("  result filter drops unmatched (left join):", len(df),
          "rows  OK")


def test_result_filter_unknown_column_errors():
    try:
        run_forge(
            {"pol": _policies()}, [],
            result_filters=[FilterSpec("", "no_such_col", "equals", value="x")])
        assert False, "expected ForgeEngineError"
    except ForgeEngineError:
        pass
    print("  result filter unknown column errors  OK")


def test_filter_modes_range_regex_contains():
    pol = _policies()
    # range: face_amount between 60000 and 90000 -> 75000,60000,90000 => 3
    r1 = run_forge({"pol": pol}, [],
                   filters=[FilterSpec("pol", "face_amount", "range",
                                       lo="60000", hi="90000")])
    assert len(r1.dataframe) == 3, r1.dataframe["face_amount"].tolist()
    # contains: status contains "laps" (case-insensitive) -> 1 LAPSED
    r2 = run_forge({"pol": pol}, [],
                   filters=[FilterSpec("pol", "status", "contains",
                                       value="laps")])
    assert len(r2.dataframe) == 1, r2.dataframe["status"].tolist()
    # regex: policy_number ^10 -> 100,101 => 2
    r3 = run_forge({"pol": pol}, [],
                   filters=[FilterSpec("pol", "policy_number", "regex",
                                       value="^10")])
    assert len(r3.dataframe) == 2, r3.dataframe["policy_number"].tolist()
    print("  filter modes range/contains/regex: 3/1/2 rows  OK")


def test_output_column_selection_and_aliases():
    res = run_forge(
        {"pol": _policies(), "re": _reinsurance()},
        [JoinSpec("pol", "re", ("company_code", "policy_number"),
                  ("company_code", "policy_number"), "inner")],
        outputs=[
            OutputColumn("pol", "policy_number", "policy"),
            OutputColumn("pol", "face_amount"),
            OutputColumn("re", "reinsurer"),
            OutputColumn("re", "ceded_amount", "ceded"),
        ],
    )
    df = res.dataframe
    assert list(df.columns) == ["policy", "face_amount", "reinsurer", "ceded"], df.columns
    assert len(df) == 3, df
    print("  output selection + aliases:", list(df.columns), " OK")


def test_contains_escapes_wildcards():
    # A value with a literal % must not act as a SQL wildcard.
    df = pd.DataFrame({"note": ["50% off", "discount", "100 percent"]})
    res = run_forge({"t": df}, [],
                    filters=[FilterSpec("t", "note", "contains", value="50%")])
    assert len(res.dataframe) == 1, res.dataframe["note"].tolist()
    assert res.dataframe.iloc[0]["note"] == "50% off"
    print("  contains escapes % wildcard: 1 row  OK")


def test_limit():
    res = run_forge({"pol": _policies()}, [], limit=2)
    assert len(res.dataframe) == 2
    print("  limit=2:", len(res.dataframe), "rows  OK")


def test_errors():
    # Mismatched key lengths.
    try:
        JoinSpec("a", "b", ("x", "y"), ("z",), "inner")
        assert False, "expected ForgeEngineError"
    except ForgeEngineError:
        pass
    # Unknown source in join.
    try:
        compile_forge_sql({"a": ["x"]},
                          [JoinSpec("a", "ghost", ("x",), ("x",), "inner")])
        assert False, "expected ForgeEngineError"
    except ForgeEngineError:
        pass
    # Disconnected join graph.
    try:
        compile_forge_sql(
            {"a": ["k"], "b": ["k"], "c": ["k"], "d": ["k"]},
            [JoinSpec("a", "b", ("k",), ("k",), "inner"),
             JoinSpec("c", "d", ("k",), ("k",), "inner")])
        assert False, "expected ForgeEngineError (disconnected)"
    except ForgeEngineError:
        pass
    print("  error handling (key len / unknown src / disconnected)  OK")


def test_flipped_left_join_keeps_correct_side():
    # Join order forces the chain to attach the join's LEFT Source (R) onto a
    # chain that already holds its RIGHT Source (M). R LEFT JOIN M must keep ALL
    # rows of R (incl. unmatched k=99), null-padding M/L — not the other way.
    left = pd.DataFrame({"k": [1, 2, 3], "v_l": ["l1", "l2", "l3"]})
    mid = pd.DataFrame({"k": [1, 2], "v_m": ["m1", "m2"]})
    right = pd.DataFrame({"k": [1, 99], "v_r": ["r1", "r99"]})
    res = run_forge(
        {"L": left, "M": mid, "R": right},
        [
            JoinSpec("M", "L", ("k",), ("k",), "inner"),   # base = M, INNER L
            JoinSpec("R", "M", ("k",), ("k",), "left"),    # R LEFT M (flipped)
        ],
        outputs=[
            OutputColumn("R", "k", "rk"), OutputColumn("R", "v_r", "v_r"),
            OutputColumn("L", "v_l", "v_l"), OutputColumn("M", "v_m", "v_m"),
        ],
    )
    df = res.dataframe
    rkeys = sorted(df["rk"].tolist())              # R.k always present
    assert rkeys == [1, 99], rkeys                 # R rows preserved (1 and 99)
    row99 = df[df["rk"] == 99].iloc[0]
    assert row99["v_r"] == "r99"                   # R side present
    assert pd.isna(row99["v_l"]) and pd.isna(row99["v_m"])  # M/L null-padded
    print("  flipped LEFT join keeps the join's left Source  OK")


def test_multipath_outer_join_rejected():
    # a->b, b->c, a->c form a cycle; the closing a->c edge as an outer join
    # would be silently downgraded by a top-level WHERE, so it must raise.
    schemas = {"a": ["k"], "b": ["k"], "c": ["k"]}
    joins = [
        JoinSpec("a", "b", ("k",), ("k",), "inner"),
        JoinSpec("b", "c", ("k",), ("k",), "inner"),
        JoinSpec("a", "c", ("k",), ("k",), "left"),   # closes the cycle, outer
    ]
    try:
        compile_forge_sql(schemas, joins)
        assert False, "expected ForgeEngineError for multi-path outer join"
    except ForgeEngineError as e:
        assert "cycle" in str(e) or "inner" in str(e)
    # The same cycle with an inner closing edge is fine (residual predicate).
    joins[2] = JoinSpec("a", "c", ("k",), ("k",), "inner")
    sql, _ = compile_forge_sql(schemas, joins)
    assert "WHERE" in sql
    print("  multi-path outer join rejected; inner cycle allowed  OK")


# ── Aggregation (GROUP BY) ───────────────────────────────────────────────

def test_aggregate_sum_by_group():
    res = run_forge({"pol": _policies()}, [], outputs=[
        OutputColumn("pol", "status", agg="group"),
        OutputColumn("pol", "face_amount", alias="total_face", agg="sum"),
    ])
    df = res.dataframe
    assert len(df) == 2, df
    totals = dict(zip(df["status"], df["total_face"]))
    assert totals["INFORCE"] == 275000, totals
    assert totals["LAPSED"] == 120000, totals
    print("  aggregate sum by group:", totals, "OK")


def test_aggregate_count_by_group():
    res = run_forge({"pol": _policies()}, [], outputs=[
        OutputColumn("pol", "company_code", agg="group"),
        OutputColumn("pol", "policy_number", alias="n", agg="count"),
    ])
    df = res.dataframe
    counts = {k: int(v) for k, v in zip(df["company_code"], df["n"])}
    assert counts == {"A": 2, "B": 2, "C": 1}, counts
    print("  aggregate count by group:", counts, "OK")


def test_all_aggregate_single_row():
    res = run_forge({"pol": _policies()}, [], outputs=[
        OutputColumn("pol", "policy_number", alias="n", agg="count"),
        OutputColumn("pol", "face_amount", alias="total", agg="sum"),
    ])
    df = res.dataframe
    assert len(df) == 1, df
    assert int(df["n"][0]) == 5, df
    assert int(df["total"][0]) == 395000, df
    print("  all-aggregate single row:", int(df["total"][0]), "OK")


def test_aggregate_after_join():
    res = run_forge(
        {"pol": _policies(), "re": _reinsurance()},
        [JoinSpec("pol", "re", ("company_code", "policy_number"),
                  ("company_code", "policy_number"), "inner")],
        outputs=[
            OutputColumn("re", "reinsurer", agg="group"),
            OutputColumn("re", "ceded_amount", alias="total_ceded", agg="sum"),
        ],
    )
    df = res.dataframe
    totals = {k: int(v) for k, v in zip(df["reinsurer"], df["total_ceded"])}
    # Inner-matched re rows: A100->XYZ 25000, A101->ACME 30000, B200->XYZ 80000.
    assert totals == {"XYZ": 105000, "ACME": 30000}, totals
    print("  aggregate after join:", totals, "OK")


def test_compile_emits_group_by():
    schemas = {"pol": list(_policies().columns)}
    sql, _ = compile_forge_sql(schemas, [], outputs=[
        OutputColumn("pol", "status", agg="group"),
        OutputColumn("pol", "face_amount", agg="sum"),
    ])
    assert "GROUP BY" in sql, sql
    assert "SUM(" in sql, sql
    print("  compile emits GROUP BY  OK")


def test_no_aggregate_has_no_group_by():
    schemas = {"pol": list(_policies().columns)}
    sql, _ = compile_forge_sql(schemas, [], outputs=[
        OutputColumn("pol", "status"),
        OutputColumn("pol", "face_amount"),
    ])
    assert "GROUP BY" not in sql, sql
    print("  no aggregate => no GROUP BY  OK")


def test_bad_aggregate_raises():
    try:
        OutputColumn("pol", "face_amount", agg="median")
    except ForgeEngineError:
        print("  bad aggregate rejected  OK")
    else:
        raise AssertionError("expected ForgeEngineError for agg='median'")


def test_display_vocabulary_treated_as_group():
    # The Display tab serializes the non-aggregated state as "display" and the
    # aggregate label uppercase ("COUNT"); the engine must accept both.
    res = run_forge({"pol": _policies()}, [], outputs=[
        OutputColumn("pol", "company_code", agg="display"),
        OutputColumn("pol", "policy_number", alias="n", agg="COUNT"),
    ])
    df = res.dataframe
    counts = {k: int(v) for k, v in zip(df["company_code"], df["n"])}
    assert counts == {"A": 2, "B": 2, "C": 1}, counts
    # "none" and "" are also non-aggregate synonyms.
    OutputColumn("pol", "x", agg="none")
    OutputColumn("pol", "x", agg="")
    print("  'display'/'COUNT'/'none' vocabulary accepted  OK")


def main():
    tests = [
        test_two_way_inner_multikey,
        test_left_join_keeps_unmatched,
        test_three_way_join,
        test_source_filter_contains_and_list,
        test_source_filter_outer_semantics,
        test_result_filter_drops_unmatched_in_left_join,
        test_result_filter_unknown_column_errors,
        test_filter_modes_range_regex_contains,
        test_output_column_selection_and_aliases,
        test_contains_escapes_wildcards,
        test_limit,
        test_flipped_left_join_keeps_correct_side,
        test_multipath_outer_join_rejected,
        test_errors,
        test_aggregate_sum_by_group,
        test_aggregate_count_by_group,
        test_all_aggregate_single_row,
        test_aggregate_after_join,
        test_compile_emits_group_by,
        test_no_aggregate_has_no_group_by,
        test_bad_aggregate_raises,
        test_display_vocabulary_treated_as_group,
    ]
    print("=" * 60)
    print("DataForge engine tests")
    print("=" * 60)
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("=" * 60)
    print(f"All {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
