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
        test_errors,
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
