"""Execute the real transaction predicates against synthetic, in-memory history."""

from dataclasses import replace
from datetime import date, timedelta
import sqlite3

import pytest

from suiteview.audit.transaction_filters import (
    TransactionCriteria, TransactionDateComparison, transaction_predicates,
)


def _single_predicate(criteria, schema, number):
    empty = TransactionCriteria()
    predicates = transaction_predicates(
        criteria if number == 1 else empty, criteria if number == 2 else empty, schema,
    )
    return predicates[0] if predicates else None


@pytest.fixture
def history():
    db = sqlite3.connect(":memory:")
    db.create_function("MONTH", 1, lambda value: date.fromisoformat(value).month if value else None)
    db.create_function("DAY", 1, lambda value: date.fromisoformat(value).day if value else None)
    db.execute("CREATE TABLE policies (CK_CMP_CD TEXT, TCH_POL_ID TEXT, ISSUE_DT TEXT)")
    db.execute("""CREATE TABLE FH_FIXED (
        CK_CMP_CD TEXT, TCH_POL_ID TEXT, TRANS TEXT, ENTRY_DT TEXT,
        ASOF_DT TEXT, GROSS_AMT REAL, ORIGIN_OF_TRANS TEXT, FUND_ID TEXT,
        FCB0_REV_IND TEXT, FCB2_REV_APPL_IND TEXT)""")
    db.executemany("INSERT INTO policies VALUES ('01', ?, '2000-03-15')", [
        (key,) for key in ("BOTH", "FIRST", "SECOND", "NONE", "SPLIT", "CROSS", "NULLS")
    ])
    rows = [
        ("01", "BOTH", "PR", 100), ("01", "BOTH", "PR", 100),
        ("01", "BOTH", "CD", 20), ("01", "BOTH", "CD", 20),
        ("01", "FIRST", "PR", 100), ("01", "SECOND", "CD", 20),
        ("01", "SPLIT", "PR", 5), ("01", "SPLIT", "XX", 100),
        ("01", "SPLIT", "CD", 20),
        ("01", "CROSS", "PR", 100), ("04", "CROSS", "CD", 20),
    ]
    db.executemany("INSERT INTO FH_FIXED VALUES (?, ?, ?, '2026-04-01', '2026-03-15', ?, 'O', 'F1', '0', '0')", rows)
    db.execute("INSERT INTO FH_FIXED VALUES ('01', 'NULLS', 'PR', NULL, NULL, NULL, NULL, NULL, NULL, NULL)")
    yield db
    db.close()


def _matches(db, first=TransactionCriteria(), second=TransactionCriteria()):
    predicates = transaction_predicates(first, second, "main")
    sql = (
        "SELECT POLICY1.TCH_POL_ID FROM policies POLICY1 "
        "JOIN policies COVERAGE1 ON POLICY1.CK_CMP_CD = COVERAGE1.CK_CMP_CD "
        "AND POLICY1.TCH_POL_ID = COVERAGE1.TCH_POL_ID"
    )
    if predicates:
        sql += " WHERE " + " AND ".join(predicates)
    return sorted(row[0] for row in db.execute(sql))


def test_empty_sections_do_not_require_history(history):
    assert _matches(history) == ["BOTH", "CROSS", "FIRST", "NONE", "NULLS", "SECOND", "SPLIT"]
    assert _single_predicate(TransactionCriteria(origin=" ", entry_date=(" ", "")), "main", 1) is None


def test_and_matches_different_rows_without_duplicates_or_cross_company_matches(history):
    first = TransactionCriteria(transaction_types=("PR",), gross_amount=("100", "100"))
    second = TransactionCriteria(transaction_types=("CD",))
    assert _matches(history, first, second) == ["BOTH"]
    assert _matches(history, first) == ["BOTH", "CROSS", "FIRST"]
    assert _matches(history, second=second) == ["BOTH", "SECOND", "SPLIT"]


def test_exclude_rejects_any_matching_row_not_just_one_nonmatching_row(history):
    criteria = TransactionCriteria(transaction_types=("PR",), gross_amount=("100", ""), exclude=True)
    assert _matches(history, criteria) == ["NONE", "NULLS", "SECOND", "SPLIT"]
    assert _matches(history, second=criteria) == ["NONE", "NULLS", "SECOND", "SPLIT"]


def test_include_and_exclude_blocks_compose_without_cross_company_matches(history):
    first = TransactionCriteria(transaction_types=("PR",), gross_amount=("100", ""))
    second = TransactionCriteria(transaction_types=("CD",), exclude=True)
    assert _matches(history, first, second) == ["CROSS", "FIRST"]
    assert _matches(history, second, first) == ["CROSS", "FIRST"]
    assert _matches(history, replace(first, exclude=True), second) == ["NONE", "NULLS"]


def test_exclude_without_criteria_is_ignored(history):
    empty = TransactionCriteria(exclude=True)
    assert _single_predicate(empty, "main", 1) is None
    assert _matches(history, empty, empty) == _matches(history)


@pytest.mark.parametrize("field,column,matching_one", [
    ("is_reversal_values", "FCB0_REV_IND", "FIRST"),
    ("reversed_values", "FCB2_REV_APPL_IND", "SECOND"),
])
@pytest.mark.parametrize("values", [("0",), ("1",), ("0", "1")])
def test_reversal_flags_are_independent_and_null_is_not_zero(history, field, column, matching_one, values):
    history.execute("UPDATE FH_FIXED SET FCB0_REV_IND = '1' WHERE TCH_POL_ID = 'FIRST'")
    history.execute("UPDATE FH_FIXED SET FCB2_REV_APPL_IND = '1' WHERE TCH_POL_ID = 'SECOND'")
    known = ["BOTH", "CROSS", "FIRST", "SECOND", "SPLIT"]
    expected = [key for key in known if (key == matching_one and "1" in values)
                or (key != matching_one and "0" in values)]
    criteria = replace(TransactionCriteria(), **{field: values})
    assert _matches(history, criteria) == expected
    assert _matches(history, second=criteria) == expected
    sql = _single_predicate(criteria, "main", 2)
    assert f"TR2.{column} IN (" in sql
    assert _matches(history, replace(criteria, exclude=True)) == [
        key for key in _matches(history) if key not in expected
    ]


def test_both_flags_and_type_must_match_the_same_transaction(history):
    history.execute("UPDATE FH_FIXED SET FCB0_REV_IND = '1' WHERE TRANS = 'PR'")
    history.execute("UPDATE FH_FIXED SET FCB2_REV_APPL_IND = '1' WHERE TRANS = 'CD'")
    criteria = TransactionCriteria(is_reversal_values=("1",), reversed_values=("1",))
    assert _matches(history, criteria) == []
    history.execute("UPDATE FH_FIXED SET FCB2_REV_APPL_IND = '1' WHERE TCH_POL_ID = 'FIRST'")
    assert _matches(history, criteria) == ["FIRST"]
    assert _matches(history, replace(criteria, transaction_types=("CD",))) == []


def test_same_row_can_satisfy_both_sections(history):
    first = TransactionCriteria(transaction_types=("PR",), gross_amount=("100", ""))
    second = TransactionCriteria(transaction_types=("PR",), origin="O")
    assert _matches(history, first, second) == ["BOTH", "CROSS", "FIRST"]


def test_multiple_transaction_types_are_or_within_one_section(history):
    criteria = TransactionCriteria(transaction_types=("PR", "CD"), gross_amount=("20", ""))
    assert _matches(history, criteria) == ["BOTH", "CROSS", "FIRST", "SECOND", "SPLIT"]


@pytest.mark.parametrize("criteria", [
    TransactionCriteria(entry_date=("04/01/2026", "04/01/2026")),
    TransactionCriteria(effective_date=("2026-03-15", "2026-03-15")),
    TransactionCriteria(effective_month=("3", "3")),
    TransactionCriteria(effective_day=("15", "15")),
    TransactionCriteria(gross_amount=("5", "100")),
    TransactionCriteria(origin="O"),
    TransactionCriteria(fund_ids="F2, F1"),
    TransactionCriteria(on_issue_month=True),
    TransactionCriteria(on_issue_day=True),
])
def test_each_criterion_alone_activates_either_section(history, criteria):
    expected = ["BOTH", "CROSS", "FIRST", "SECOND", "SPLIT"]
    assert _matches(history, criteria) == expected
    assert _matches(history, second=criteria) == expected


@pytest.mark.parametrize("field", ["entry_date", "effective_date", "effective_month", "effective_day", "gross_amount"])
@pytest.mark.parametrize("upper_only", [False, True])
def test_one_sided_bounds_are_active(field, upper_only):
    value = "2026-03-15" if "date" in field else "1"
    criteria = replace(TransactionCriteria(), **{field: ("", value) if upper_only else (value, "")})
    sql = _single_predicate(criteria, "DB2TAB", 2)
    assert ("<=" if upper_only else ">=") in sql


def test_issue_month_and_day_belong_to_each_independent_section(history):
    criteria = TransactionCriteria(on_issue_month=True, on_issue_day=True)
    assert "MONTH(TR2.ASOF_DT) = MONTH(COVERAGE1.ISSUE_DT)" in _single_predicate(criteria, "main", 2)
    history.execute("UPDATE policies SET ISSUE_DT = '2000-02-15' WHERE TCH_POL_ID = 'FIRST'")
    history.execute("UPDATE policies SET ISSUE_DT = '2000-03-16' WHERE TCH_POL_ID = 'SECOND'")
    assert _matches(history, second=criteria) == ["BOTH", "CROSS", "SPLIT"]


def test_zero_negative_amounts_and_escaped_literals(history):
    history.execute(
        "INSERT INTO FH_FIXED VALUES ('01', 'NONE', 'PR', '2026-01-01', '2026-01-01', ?, ?, ?, '0', '0')",
        (-0.01, "O'R", "F'1"),
    )
    criteria = TransactionCriteria(gross_amount=("-0.01", "0"), origin="O'R", fund_ids="F'1")
    assert _matches(history, criteria) == ["NONE"]
    assert _matches(history, replace(criteria, gross_amount=("0", ""))) == []


@pytest.mark.parametrize("field,value", [
    ("entry_date", ("not a date", "")),
    ("effective_date", ("2026-02-30", "")),
    ("entry_date", ("2026-04-02", "2026-04-01")),
    ("gross_amount", ("100", "10")),
    ("gross_amount", ("NaN", "")),
    ("gross_amount", ("", "Infinity")),
    ("effective_month", ("0", "")),
    ("effective_month", ("", "13")),
    ("effective_day", ("1.5", "")),
    ("effective_day", ("", "32")),
    ("effective_day", ("20", "10")),
    ("fund_ids", ","),
    ("fund_ids", "F1,,F2"),
    ("is_reversal_values", ("2",)),
    ("reversed_values", ("",)),
])
@pytest.mark.parametrize("number", [1, 2])
def test_invalid_criteria_report_the_section(field, value, number):
    criteria = replace(TransactionCriteria(), **{field: value})
    with pytest.raises(ValueError, match=f"Transaction {number} -"):
        _single_predicate(criteria, "DB2TAB", number)


def _insert_dated_row(history, key, trans, entry, effective, *, company="01", gross=100, flag="0"):
    history.execute(
        "INSERT INTO FH_FIXED VALUES (?, ?, ?, ?, ?, ?, 'O', 'F1', ?, '0')",
        (company, key, trans, entry, effective, gross, flag),
    )


@pytest.mark.parametrize("field,column", [
    ("entry_comparison", "ENTRY_DT"), ("effective_comparison", "ASOF_DT"),
])
@pytest.mark.parametrize("comparison,operator,reference", [
    (TransactionDateComparison.AFTER_ENTRY, ">", "ENTRY_DT"),
    (TransactionDateComparison.BEFORE_ENTRY, "<", "ENTRY_DT"),
    (TransactionDateComparison.EQUAL_ENTRY, "=", "ENTRY_DT"),
    (TransactionDateComparison.AFTER_EFFECTIVE, ">", "ASOF_DT"),
    (TransactionDateComparison.BEFORE_EFFECTIVE, "<", "ASOF_DT"),
    (TransactionDateComparison.EQUAL_EFFECTIVE, "=", "ASOF_DT"),
])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_all_date_comparisons_execute_with_strict_boundaries(
    history, field, column, comparison, operator, reference, offset,
):
    history.execute("DELETE FROM FH_FIXED")
    target = date(2026, 3, 15)
    first_entry = target.isoformat() if reference == "ENTRY_DT" else "2026-06-01"
    first_eff = target.isoformat() if reference == "ASOF_DT" else "2026-06-01"
    second_date = (target + timedelta(days=offset)).isoformat()
    _insert_dated_row(history, "BOTH", "PR", first_entry, first_eff)
    _insert_dated_row(
        history, "BOTH", "CD",
        second_date if column == "ENTRY_DT" else "2026-10-01",
        second_date if column == "ASOF_DT" else "2026-10-01",
    )
    first = TransactionCriteria(transaction_types=("PR",))
    second = replace(TransactionCriteria(transaction_types=("CD",)), **{field: comparison})
    matches = offset > 0 if operator == ">" else offset < 0 if operator == "<" else offset == 0
    assert _matches(history, first, second) == (["BOTH"] if matches else [])
    sql = " AND ".join(transaction_predicates(first, second, "main"))
    assert f"TR2.{column} {operator} TR1.{reference}" in sql
    assert "CK_SYS_CD" not in sql
    assert "JOIN" not in sql


def test_both_comparisons_use_the_same_pair_not_different_anchors_or_partners(history):
    history.execute("DELETE FROM FH_FIXED")
    # Each PR satisfies only one comparison against the CD.
    _insert_dated_row(history, "SPLIT", "PR", "2026-01-01", "2026-01-01")
    _insert_dated_row(history, "SPLIT", "PR", "2026-03-01", "2026-03-01")
    _insert_dated_row(history, "SPLIT", "CD", "2026-02-01", "2026-02-01")
    # Each CD satisfies only one comparison against the PR.
    _insert_dated_row(history, "SECOND", "PR", "2026-02-01", "2026-02-01")
    _insert_dated_row(history, "SECOND", "CD", "2026-03-01", "2026-03-01")
    _insert_dated_row(history, "SECOND", "CD", "2026-01-01", "2026-01-01")
    # Duplicate qualifying pairs return just one policy.
    for _ in range(2):
        _insert_dated_row(history, "BOTH", "PR", "2026-01-01", "2026-03-01")
        _insert_dated_row(history, "BOTH", "CD", "2026-02-01", "2026-02-01")
    # A later anchor does not supersede an earlier qualifying one.
    _insert_dated_row(history, "BOTH", "PR", "2026-04-01", "2026-04-01")
    # A different policy or company cannot supply the partner.
    _insert_dated_row(history, "CROSS", "PR", "2026-01-01", "2026-03-01")
    _insert_dated_row(history, "CROSS", "CD", "2026-02-01", "2026-02-01", company="04")
    first = TransactionCriteria(transaction_types=("PR",))
    second = TransactionCriteria(
        transaction_types=("CD",),
        entry_comparison=TransactionDateComparison.AFTER_ENTRY,
        effective_comparison=TransactionDateComparison.BEFORE_EFFECTIVE,
    )
    assert _matches(history, first, second) == ["BOTH"]
    assert _matches(history, first, replace(second, exclude=True)) == ["CROSS", "SECOND", "SPLIT"]


def test_linked_exclude_rejects_any_pair_even_with_an_unmatched_anchor(history):
    history.execute("DELETE FROM FH_FIXED")
    for key in ("BOTH", "FIRST", "CROSS"):
        _insert_dated_row(history, key, "PR", "2026-01-01", "2026-01-01")
    _insert_dated_row(history, "BOTH", "CD", "2026-02-01", "2026-02-01")
    _insert_dated_row(history, "BOTH", "PR", "2026-03-01", "2026-03-01")
    _insert_dated_row(history, "FIRST", "CD", "2025-12-01", "2025-12-01")
    _insert_dated_row(history, "CROSS", "CD", "2026-02-01", "2026-02-01", company="04")
    first = TransactionCriteria(transaction_types=("PR",))
    second = TransactionCriteria(
        transaction_types=("CD",), entry_comparison=TransactionDateComparison.AFTER_ENTRY,
        exclude=True,
    )
    assert _matches(history, first, second) == ["CROSS", "FIRST"]


def test_existing_filters_constrain_the_linked_rows(history):
    history.execute("DELETE FROM FH_FIXED")
    for key in ("BOTH", "FIRST", "SECOND", "SPLIT"):
        _insert_dated_row(history, key, "PR", "2026-01-01", "2026-01-01",
                          gross=5 if key == "FIRST" else 100)
        _insert_dated_row(history, key, "CD", "2026-02-01", "2026-03-15",
                          flag="1" if key == "SECOND" else "0")
    history.execute("UPDATE FH_FIXED SET ENTRY_DT = '2027-02-01' WHERE TCH_POL_ID = 'SPLIT' AND TRANS = 'CD'")
    first = TransactionCriteria(transaction_types=("PR",), gross_amount=("100", ""))
    second = TransactionCriteria(
        transaction_types=("CD",), entry_date=("", "2026-12-31"), fund_ids="F1",
        is_reversal_values=("0",), on_issue_month=True, on_issue_day=True,
        entry_comparison=TransactionDateComparison.AFTER_ENTRY,
    )
    assert _matches(history, first, second) == ["BOTH"]
    assert _matches(history, first, replace(second, exclude=True)) == ["SECOND", "SPLIT"]


@pytest.mark.parametrize("first_null", [False, True])
@pytest.mark.parametrize("comparison", list(TransactionDateComparison)[1:])
def test_null_dates_never_satisfy_comparisons(history, first_null, comparison):
    history.execute("DELETE FROM FH_FIXED")
    anchor = None if first_null else "2026-01-01"
    partner = "2026-01-01" if first_null else None
    _insert_dated_row(history, "BOTH", "PR", anchor, anchor)
    _insert_dated_row(history, "BOTH", "CD", partner, partner)
    first = TransactionCriteria(transaction_types=("PR",))
    second = TransactionCriteria(transaction_types=("CD",), entry_comparison=comparison)
    assert _matches(history, first, second) == []
    assert _matches(history, first, replace(second, exclude=True)) == ["BOTH"]


def test_comparison_alone_uses_any_reference_row_and_equality_can_use_same_row(history):
    second = TransactionCriteria(entry_comparison=TransactionDateComparison.EQUAL_ENTRY)
    assert _matches(history, second=second) == ["BOTH", "CROSS", "FIRST", "SECOND", "SPLIT"]
    assert _matches(history, second=replace(second, entry_comparison=TransactionDateComparison.AFTER_ENTRY)) == []


def test_nested_sql_formatting_preserves_literal_contents(history):
    history.execute("UPDATE FH_FIXED SET ORIGIN_OF_TRANS = ? WHERE TRANS = 'CD'", ("O'\nR",))
    first = TransactionCriteria(transaction_types=("PR",))
    second = TransactionCriteria(
        transaction_types=("CD",), origin="O'\nR",
        entry_comparison=TransactionDateComparison.EQUAL_ENTRY,
    )
    assert _matches(history, first, second) == ["BOTH", "SPLIT"]


@pytest.mark.parametrize("field", ["entry_comparison", "effective_comparison"])
def test_invalid_or_excluded_reference_is_an_explicit_error(field):
    empty = TransactionCriteria()
    linked = replace(empty, **{field: TransactionDateComparison.EQUAL_ENTRY})
    with pytest.raises(ValueError, match="Transaction 1.*only available in Transaction 2"):
        transaction_predicates(linked, empty, "DB2TAB")
    with pytest.raises(ValueError, match="Transaction 2.*Transaction 1 Exclude"):
        transaction_predicates(replace(empty, exclude=True), linked, "DB2TAB")
    with pytest.raises(ValueError, match="Transaction 2.*select a listed"):
        transaction_predicates(empty, replace(empty, **{field: "invalid"}), "DB2TAB")
