"""Synthetic CKCVDVPD fixtures: no production rates or live database access."""

from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook

from suiteview.ratemanager.whole_life.dividend import (
    DividendValidationError,
    HEADER_COLUMNS,
    PLANKEY_COLUMNS,
    RATE_COLUMNS,
    RECORD_TYPES,
    TABLE_KEYS,
    parse_dividend,
    parse_plan_key_map,
)


PAGE = "1CKCVDVPD RUN DATE = 09/07/26 DIVIDEND RATES PAGE 1\n"
FORMATTING = (
    "0\n USR CLASS CNT USER ISS ISSUE EFFECTIVE ENDING\n"
    " ID  BASE-SUB DEFINED AGE DATE DATE DATE\n"
    "------------------------------------------------------------\n"
    "0TYPE  DURATION (1) (2) (3)\n ----  --------\n"
)


def _record(
    plan="A-TST-N1",
    age=20,
    first=1,
    last=2,
    par="0",
    pua_key=None,
    user="",
    effective="04/01/2024",
    issue="01/01/2000",
    end="00/00/0000",
    function="2",
    gross="0.000",
    description="PREMIUM PAYING DIVIDEND",
    values=None,
    user_code="00",
):
    control = (
        f"{user_code} {plan} 1 {user} {age:02d} {issue} {effective} {end} "
        f"{first:02d} {last:03d} 1 5 .000 0 5 LQ {function} 4.000 1 121 {par}"
    )
    control += f" {pua_key or ''} {gross}\n"
    text = f" RECORD TYPE = {description}\n{FORMATTING}{control}"
    for rate_type, offset in (("CASH", 0), ("PUA", 100), ("1YT", 200)):
        for start in range(first, last + 1, 10):
            stop = min(start + 9, last)
            rates = values or [f"{duration + offset}.25" for duration in range(start, stop + 1)]
            label = rate_type if start == first else ""
            text += f" {label} {start:03d}-{start + 9:03d} " + " ".join(rates) + "\n"
    return text


def _parse(tmp_path, text):
    path = tmp_path / "synthetic-dividend.txt"
    path.write_text(text, encoding="utf-8")
    return parse_dividend(path)


def _write_map(tmp_path, rows, columns=PLANKEY_COLUMNS):
    path = tmp_path / "synthetic-dividend-map.xlsx"
    book = Workbook()
    book.active.title = "WL_DIV_PLANKEY_MAP"
    book.active.append(columns)
    for row in rows:
        book.active.append(row)
    book.save(path)
    book.close()
    return path


def test_physical_columns_natural_keys_and_exact_decimal_dates(tmp_path):
    package = _parse(tmp_path, PAGE + _record(plan="a-tst-n1", user="abc"))
    assert set(package) == {"WL_DIV_HEADER", "WL_RATE_DIV"}
    header = package["WL_DIV_HEADER"][0]
    assert tuple(header) == HEADER_COLUMNS
    assert header["HEADER_ID"] == "00_D_A_TST_N1_1_ABC    _020_20000101_20240401"
    assert len(header["HEADER_ID"]) == 45
    assert header["DIV_KEY"] == "ATSTN1"
    assert header["ISSUE_DATE"] == date(2000, 1, 1)
    assert header["EFFECTIVE_DATE"] == date(2024, 4, 1)
    assert header["END_DATE"] == "00/00/0000"
    assert header["GROSS_INTEREST"] == Decimal("0.000")
    assert isinstance(header["INTEREST_RATE"], Decimal)
    assert not {"MAINT_DT", "RUN_DATE", "FILE_NAME"} & header.keys()
    row = package["WL_RATE_DIV"][0]
    assert tuple(row) == RATE_COLUMNS
    assert row["HEADER_ID"] == header["HEADER_ID"]
    assert row["CASH_RATE"] == Decimal("1.25")
    assert row["PUA_RATE"] == Decimal("101.25")
    assert row["OYT_RATE"] == Decimal("201.25")
    assert row["PUA_DIV_CASH"] is None


@pytest.mark.parametrize("description,code", RECORD_TYPES.items())
def test_all_current_record_types(tmp_path, description, code):
    package = _parse(tmp_path, PAGE + _record(description=description))
    assert package["WL_DIV_HEADER"][0]["RECORD_TYPE"] == code
    assert all(row["RECORD_TYPE"] == code for row in package["WL_RATE_DIV"])


def test_zero_date_sentinels_preserve_natural_key(tmp_path):
    package = _parse(tmp_path, PAGE + _record(issue="00/00/1900", effective="00/00/1900"))
    header = package["WL_DIV_HEADER"][0]
    assert header["ISSUE_DATE"] == header["EFFECTIVE_DATE"] == "00/00/1900"
    assert header["HEADER_ID"].endswith("_19000000_19000000")


def test_blank_user_key_and_zero_age_keep_original_header_id_padding(tmp_path):
    package = _parse(tmp_path, PAGE + _record(
        plan="1-A-N", age=0, issue="00/00/1900",
        description="REDUCED PAID-UP DIVIDEND",
    ))
    key = package["WL_DIV_HEADER"][0]["HEADER_ID"]
    assert key == "00_R_1_A  _N _1_       _000_19000000_20240401"
    assert len(key) == 45
    assert package["WL_RATE_DIV"][0]["HEADER_ID"] == key
    assert TABLE_KEYS["WL_DIV_HEADER"] == ("HEADER_ID",)
    assert TABLE_KEYS["WL_RATE_DIV"] == ("HEADER_ID", "DURATION")
    assert TABLE_KEYS["WL_DIV_PLANKEY_MAP"] == ("PLANCODE", "SEX", "RATECLASS")


@pytest.mark.parametrize("function", ["", "1"])
@pytest.mark.parametrize("gross", ["", "0.000", "8.125"])
def test_optional_function_and_gross_fields(tmp_path, function, gross):
    package = _parse(tmp_path, PAGE + _record(function=function, gross=gross))
    header = package["WL_DIV_HEADER"][0]
    assert header["INT_FUNCTION"] == (function or None)
    assert header["GROSS_INTEREST"] == (Decimal(gross) if gross else None)


def test_null_bytes_overflow_signed_values_and_terminal_short_group(tmp_path):
    text = PAGE + _record(last=12)
    text = text.replace("CASH 001-010 1.25 2.25", "CASH\x00\x00001-010\x00\x001113.641177.82")
    text = text.replace(" 011-020 11.25 12.25", " 011-020-11.25-12.25")
    package = _parse(tmp_path, text)
    rates = package["WL_RATE_DIV"]
    assert len(rates) == 12
    assert rates[0]["CASH_RATE"] == Decimal("1113.64")
    assert rates[1]["CASH_RATE"] == Decimal("1177.82")
    assert rates[-1]["CASH_RATE"] == Decimal("-12.25")


@pytest.mark.parametrize("original,corrupted", [
    ("1.25 2.25", "1\x002.25 2.25"),
    ("1.25 2.25", "1\x00.25 2.25"),
    ("1.25 2.25", "1.\x0025 2.25"),
    ("1.25 2.25", "1.25\x002.25"),
    ("A-TST-N1", "A-T\x00ST-N1"),
    ("00 A-TST", "0\x000 A-TST"),
    (" 20 01/01/2000", " 2\x000 01/01/2000"),
    ("04/01/2024", "04/\x0001/2024"),
    ("4.000", "4.\x00000"),
    ("CASH 001-010", "CA\x00SH 001-010"),
    ("CASH 001-010", "CASH 00\x001-010"),
    ("CASH 001-010", "CASH 001-0\x0010"),
])
def test_embedded_nulls_cannot_repair_numeric_or_key_tokens(tmp_path, original, corrupted):
    text = PAGE + _record().replace(original, corrupted, 1)
    with pytest.raises(DividendValidationError, match="NUL"):
        _parse(tmp_path, text)


@pytest.mark.parametrize("rate_type", ["CASH", "PUA", "1YT"])
def test_verified_null_padding_between_rate_label_and_range_is_accepted(tmp_path, rate_type):
    text = PAGE + _record().replace(f"{rate_type} 001-010 ", f"{rate_type}\x00\x00001-010\x00\x00")
    assert len(_parse(tmp_path, text)["WL_RATE_DIV"]) == 2


def test_null_padding_adjacent_to_whitespace_or_line_edges_is_accepted(tmp_path):
    text = PAGE + _record().replace("1.25 2.25", "1.25\x00\x00 2.25")
    text = "".join("\x00" + line + "\x00\n" for line in text.splitlines())
    package = _parse(tmp_path, text)
    assert package["WL_RATE_DIV"][0]["CASH_RATE"] == Decimal("1.25")
    assert package["WL_RATE_DIV"][1]["CASH_RATE"] == Decimal("2.25")


def test_same_base_participation_copies_all_three_rates(tmp_path):
    package = _parse(tmp_path, PAGE + _record(par="1", user="TST B"))
    assert package["WL_DIV_HEADER"][0]["PUA_KEY_USER_DEFINED"] == "TST B"
    for row in package["WL_RATE_DIV"]:
        assert row["PUA_DIV_CASH"] == row["CASH_RATE"]
        assert row["PUA_DIV_PUA"] == row["PUA_RATE"]
        assert row["PUA_DIV_OYT"] == row["OYT_RATE"]


@pytest.mark.parametrize("gross", ["", "0.000"])
def test_ultimate_pua_attained_age_shift_and_lookup_only_filter(tmp_path, gross):
    parent = _record(age=2, par="2", pua_key="ZREFN1", gross=gross)
    reference = _record(plan="Z-REF-N1", age=0, last=4, user="TST")
    package = _parse(tmp_path, PAGE + parent + reference)
    assert len(package["WL_DIV_HEADER"]) == 1
    header = package["WL_DIV_HEADER"][0]
    assert header["PUA_KEY"] == "ZREFN1"
    assert header["PUA_KEY_USER_DEFINED"] == "TST"
    assert package["WL_RATE_DIV"][0]["PUA_DIV_CASH"] == Decimal("3.25")
    assert package["WL_RATE_DIV"][1]["PUA_DIV_OYT"] == Decimal("204.25")


def test_exact_age_pua_takes_priority_and_has_no_shift(tmp_path):
    parent = _record(age=2, par="2", pua_key="ZREFN1")
    ultimate = _record(plan="Z-REF-N1", age=0, last=4)
    exact = _record(plan="Z-REF-N1", age=2, user="TST", values=["8.00", "9.00"])
    package = _parse(tmp_path, PAGE + parent + ultimate + exact)
    assert package["WL_RATE_DIV"][0]["PUA_DIV_CASH"] == Decimal("8.00")


def test_pua_reference_disambiguates_by_parent_base(tmp_path):
    parent = _record(age=2, par="2", pua_key="ZREFN1")
    other = _record(plan="Z-REF-N1", age=0, last=4, user="ALT")
    correct = _record(plan="Z-REF-N1", age=0, last=4, user="TST B", values=["9.00"] * 4)
    package = _parse(tmp_path, PAGE + parent + other + correct)
    assert package["WL_DIV_HEADER"][0]["PUA_KEY_USER_DEFINED"] == "TST B"
    assert package["WL_RATE_DIV"][0]["PUA_DIV_CASH"] == Decimal("9.00")


def test_pua_reference_uses_matching_effective_date_not_file_order(tmp_path):
    parent = _record(age=2, par="2", pua_key="ZREFN1")
    old = _record(plan="Z-REF-N1", age=0, last=4, effective="01/01/2020")
    current = _record(plan="Z-REF-N1", age=0, last=4, values=["9.00"] * 4)
    package = _parse(tmp_path, PAGE + parent + old + current)
    assert package["WL_RATE_DIV"][0]["PUA_DIV_CASH"] == Decimal("9.00")


@pytest.mark.parametrize("other_user", ["00", "26"])
def test_pua_lookup_never_falls_back_to_another_user(tmp_path, other_user):
    parent = _record(age=2, par="2", pua_key="ZREFN1", user_code="01")
    reference = _record(plan="Z-REF-N1", age=0, last=4, user_code=other_user)
    with pytest.raises(DividendValidationError, match="missing or ambiguous PUA reference"):
        _parse(tmp_path, PAGE + parent + reference)


@pytest.mark.parametrize("reverse", [False, True])
def test_multi_user_references_resolve_without_false_ambiguity(tmp_path, reverse):
    parents = [
        _record(age=2, par="2", pua_key="ZREFN1", user_code=user)
        for user in ("01", "26")
    ]
    references = [
        _record(plan="Z-REF-N1", age=0, last=4, user_code=user, values=[value] * 4)
        for user, value in (("01", "11.00"), ("26", "26.00"))
    ]
    if reverse:
        references.reverse()
    package = _parse(tmp_path, PAGE + "".join(parents + references))
    assert len(package["WL_DIV_HEADER"]) == 2
    rates = {row["HEADER_ID"]: row for row in package["WL_RATE_DIV"]}
    for header in package["WL_DIV_HEADER"]:
        expected = Decimal("11.00") if header["USER_CODE"] == "01" else Decimal("26.00")
        assert rates[header["HEADER_ID"]]["PUA_DIV_CASH"] == expected
        assert header["DIV_KEY"] == "ATSTN1"


def test_other_user_exact_age_does_not_override_own_user_ultimate_rates(tmp_path):
    parent = _record(age=2, par="2", pua_key="ZREFN1", user_code="01")
    own_ultimate = _record(plan="Z-REF-N1", age=0, last=4, user_code="01")
    other_exact = _record(plan="Z-REF-N1", age=2, user_code="26", values=["9.00"] * 2)
    package = _parse(tmp_path, PAGE + parent + own_ultimate + other_exact)
    header = next(row for row in package["WL_DIV_HEADER"] if row["USER_CODE"] == "01")
    rates = [row for row in package["WL_RATE_DIV"] if row["HEADER_ID"] == header["HEADER_ID"]]
    assert rates[0]["PUA_DIV_CASH"] == Decimal("3.25")
    assert rates[1]["PUA_DIV_CASH"] == Decimal("4.25")


@pytest.mark.parametrize("other_scope", [
    {"user_code": "26"},
    {"description": "REDUCED PAID-UP DIVIDEND"},
])
def test_lookup_filter_keeps_unrelated_user_or_record_type_base_schedules(tmp_path, other_scope):
    parent = _record(age=2, par="2", pua_key="ZREFN1", user_code="01")
    reference = _record(plan="Z-REF-N1", age=0, last=4, user_code="01")
    other = _record(plan="Z-REF-N1", age=40, **{"user_code": "01", **other_scope})
    package = _parse(tmp_path, PAGE + parent + reference + other)
    assert len(package["WL_DIV_HEADER"]) == 2
    unrelated = next(header for header in package["WL_DIV_HEADER"] if header["ISSUE_AGE"] == 40)
    assert unrelated["DIV_KEY"] == "ZREFN1"
    rates = [row for row in package["WL_RATE_DIV"] if row["HEADER_ID"] == unrelated["HEADER_ID"]]
    assert len(rates) == 2
    assert all(row["PUA_DIV_CASH"] is None for row in rates)


def test_pua_lookup_does_not_cross_record_types(tmp_path):
    parent = _record(age=2, par="2", pua_key="ZREFN1", user_code="01")
    reference = _record(
        plan="Z-REF-N1", age=0, last=4, user_code="01",
        description="REDUCED PAID-UP DIVIDEND",
    )
    with pytest.raises(DividendValidationError, match="missing or ambiguous PUA reference"):
        _parse(tmp_path, PAGE + parent + reference)


def test_identical_duplicate_schedules_are_collapsed(tmp_path):
    text = _record()
    package = _parse(tmp_path, PAGE + text + text)
    assert len(package["WL_DIV_HEADER"]) == 1
    assert len(package["WL_RATE_DIV"]) == 2


def test_identical_duplicate_rate_rows_are_collapsed(tmp_path):
    text = _record()
    text = text.replace(" CASH 001-010 1.25 2.25\n", " CASH 001-010 1.25 2.25\n" * 2)
    assert len(_parse(tmp_path, PAGE + text)["WL_RATE_DIV"]) == 2


@pytest.mark.parametrize("changed", [
    _record(values=["7.00", "8.00"]),
    _record(gross="9.000"),
    _record(end="01/01/2029"),
])
def test_conflicting_natural_key_duplicates_fail(tmp_path, changed):
    with pytest.raises(DividendValidationError, match="conflicting duplicate HEADER_ID"):
        _parse(tmp_path, PAGE + _record() + changed)


def test_page_break_during_continuation_preserves_rate_type(tmp_path):
    text = _record(last=12)
    text = text.replace("  011-020 11.25", PAGE + " RECORD TYPE = PREMIUM PAYING DIVIDEND\n" + FORMATTING + "  011-020 11.25")
    assert len(_parse(tmp_path, PAGE + text)["WL_RATE_DIV"]) == 12


@pytest.mark.parametrize("text,message", [
    ("", "empty or incomplete"),
    (PAGE, "empty or incomplete"),
    (_record(), "expected CKCVDVPD"),
    (PAGE + _record() + "unexpected text\n", "unrecognized"),
    (PAGE.replace("09/07/26", "02/30/26") + _record(), "invalid report run date"),
    (PAGE + _record(description="UNKNOWN"), "unknown dividend RECORD TYPE"),
    (PAGE + "CASH 001-010 1.00\n", "before a control row"),
    (PAGE + _record().replace("CASH 001-010", "001-010", 1), "no CASH/PUA/1YT"),
    (PAGE + _record().replace(" 1YT 001-010 201.25 202.25\n", ""), "incomplete OYT_RATE"),
    (PAGE + _record().replace("1.25 2.25", "1.25"), "rate value count"),
    (PAGE + _record().replace("1.25 2.25", "1.25 2.25 3.25"), "rate value count"),
    (PAGE + _record().replace("1.25 2.25", "1.25 junk"), "invalid rate value"),
    (PAGE + _record().replace("1.25 2.25", "1.251 2.25"), "invalid rate value"),
    (PAGE + _record().replace("1.25 2.25", "NaN 2.25"), "invalid rate value"),
    (PAGE + _record().replace("CASH 001-010", "CASH 003-012"), "outside"),
    (PAGE + _record().replace("CASH 001-010", "CASH 001-999"), "outside"),
    (PAGE + _record() + "RECORD TYPE = TERMINATION DIVIDEND\n", "empty or incomplete"),
])
def test_malformed_partial_sources_fail_with_context(tmp_path, text, message):
    with pytest.raises(DividendValidationError, match=message):
        _parse(tmp_path, text)


@pytest.mark.parametrize("options,message", [
    ({"issue": "02/30/2024"}, "ISSUE_DATE"),
    ({"effective": "01/00/1900"}, "EFFECTIVE_DATE"),
    ({"end": "99/99/9999"}, "END_DATE"),
    ({"plan": "AA-TST-N1"}, "CLASS"),
    ({"plan": "A-TOOLONG-N1"}, "BASE_SERIES"),
    ({"user": "TOOLONG"}, "USER_DEFINED"),
    ({"age": 1000}, "ISSUE_AGE"),
    ({"first": 2, "last": 1}, "FIRST_DURATION"),
    ({"par": "3"}, "PUA_PARTICIPATING"),
    ({"par": "2"}, "requires PUA_KEY"),
    ({"gross": "NaN.0"}, "GROSS_INTEREST"),
    ({"gross": "1.000 EXTRA FIELD"}, "unexpected trailing"),
])
def test_bad_header_values_fail(tmp_path, options, message):
    with pytest.raises(DividendValidationError, match=message):
        _parse(tmp_path, PAGE + _record(**options))


def test_conflicting_duplicate_duration_fails(tmp_path):
    text = _record().replace(" CASH 001-010 1.25 2.25\n", " CASH 001-010 1.25 2.25\n CASH 001-010 9.25 2.25\n")
    with pytest.raises(DividendValidationError, match="conflicting duplicate CASH_RATE"):
        _parse(tmp_path, PAGE + text)


@pytest.mark.parametrize("reference,message", [
    ("", "missing or ambiguous PUA reference"),
    (_record(plan="Z-REF-N1", age=0, last=2), "missing duration"),
    (
        _record(plan="Z-REF-N1", age=0, last=4, user="TST A")
        + _record(plan="Z-REF-N1", age=0, last=4, user="TST B"),
        "ambiguous PUA reference",
    ),
])
def test_missing_partial_or_ambiguous_pua_references_fail(tmp_path, reference, message):
    parent = _record(age=2, par="2", pua_key="ZREFN1")
    with pytest.raises(DividendValidationError, match=message):
        _parse(tmp_path, PAGE + parent + reference)


def test_invalid_encoding_fails_instead_of_replacing_bytes(tmp_path):
    path = tmp_path / "bad-encoding.txt"
    path.write_bytes(PAGE.encode() + b"\xff")
    with pytest.raises(DividendValidationError, match="invalid UTF-8"):
        parse_dividend(path)


def test_mapping_normalizes_literal_blank_and_identical_duplicates(tmp_path):
    first = ("plan0001", "m", "n", "a1", "(blank)", "atsta1")
    path = _write_map(tmp_path, [first, first, ("PLAN0002", "F", 0, "00", None, "BTST00")])
    rows = parse_plan_key_map(path)
    assert len(rows) == 2
    assert tuple(rows[0]) == PLANKEY_COLUMNS
    assert rows[0] == dict(zip(PLANKEY_COLUMNS, ("PLAN0001", "M", "N", "A1", None, "ATSTA1")))
    assert rows[1]["RATECLASS"] == "0"


@pytest.mark.parametrize("user_key,expected", [
    (None, None), ("", None), ("(blank)", None),
    (0, "0"), ("0", "0"), ("00", "00"),
])
def test_mapping_preserves_zero_user_keys_as_distinct_from_blank(tmp_path, user_key, expected):
    row = ("PLAN0001", "M", "N", "A1", user_key, "ATSTA1")
    rows = parse_plan_key_map(_write_map(tmp_path, [row]))
    assert rows[0]["USER_KEY"] == expected


@pytest.mark.parametrize("column,value,message", [
    (0, None, "PLANCODE"),
    (0, "TOOLONGPLAN", "PLANCODE"),
    (1, "MM", "SEX"),
    (2, "=1+1", "literal identifier"),
    (3, "AAA", "SUBSERIES"),
    (4, "ABC", "USER_KEY"),
    (5, "#N/A", "literal identifier"),
    (5, True, "literal identifier"),
    (5, "??????", "invalid identifier"),
])
def test_invalid_mapping_cells_rejected(tmp_path, column, value, message):
    row = ["PLAN0001", "M", "N", "A1", None, "ATSTA1"]
    row[column] = value
    with pytest.raises(DividendValidationError, match=message):
        parse_plan_key_map(_write_map(tmp_path, [row]))


def test_mapping_conflicting_duplicates_rejected(tmp_path):
    rows = [
        ("PLAN0001", "M", "N", "A1", None, "ATSTA1"),
        ("PLAN0001", "M", "N", "A2", None, "ATSTA2"),
    ]
    with pytest.raises(DividendValidationError, match="conflicting duplicate"):
        parse_plan_key_map(_write_map(tmp_path, rows))


def test_mapping_ignores_formatting_only_trailing_columns(tmp_path):
    row = ("PLAN0001", "M", "N", "A1", None, "ATSTA1")
    path = _write_map(tmp_path, [row + (None,)], PLANKEY_COLUMNS + (None,))
    assert len(parse_plan_key_map(path)) == 1


def test_mapping_rejects_extra_data_under_empty_trailing_heading(tmp_path):
    row = ("PLAN0001", "M", "N", "A1", None, "ATSTA1", "UNEXPECTED")
    path = _write_map(tmp_path, [row], PLANKEY_COLUMNS + (None,))
    with pytest.raises(DividendValidationError, match="unexpected data beyond"):
        parse_plan_key_map(path)


@pytest.mark.parametrize("columns,rows,message", [
    (PLANKEY_COLUMNS, [], "no data rows"),
    (PLANKEY_COLUMNS[:-1], [], "expected mapping columns"),
    (PLANKEY_COLUMNS + ("EXTRA",), [], "expected mapping columns"),
])
def test_invalid_mapping_layout_rejected(tmp_path, columns, rows, message):
    with pytest.raises(DividendValidationError, match=message):
        parse_plan_key_map(_write_map(tmp_path, rows, columns))
