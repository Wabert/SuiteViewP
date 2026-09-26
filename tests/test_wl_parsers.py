"""Source-preservation and fail-closed checks for Whole Life rate prints."""

from datetime import date
from decimal import Decimal

import pytest

from suiteview.ratemanager.schema import PackageValidationError
from suiteview.ratemanager.whole_life.parsers import (
    CV_COLUMNS, IAF_COLUMNS, PUI_COLUMNS, parse_cvf, parse_iaf, parse_nsp, parse_pui,
)


CV_REPORT = "1CKCVDVPC RUN DATE = 01/02/26 CASH VALUE RATES PAGE 1\n"
CV_LABELS = (
    "0USER ID CLASS-BASE-SUB USER DEFINED AGE PREM YEARS BENF YEARS "
    "FIRST DUR LAST DUR DURATION ZERO VALUE\n"
)
CV_GRID = " DURATION " + " ".join(f"({i:2})" for i in range(1, 11)) + "\n"
IAF_COLUMNS_LINE = (
    " **PREMIUM RATES- TYP START STOP IDENT RATE IDENT RATE IDENT RATE IDENT RATE\n"
)
PUI_START = (
    "1DATE 01/02/26 CYBERLIFE ONLINE TABLES LIST PAGE 1\n"
    "0TABLE: CJUDTPUI PROCESSING OPTIONS: USERID = ALL AUDIT# = ALL DELETED RECORDS = OMIT\n"
    "0 ENTRIES FOR USER 01\n"
    "0 PLAN CD SEX CLASS ATT AGE TAB RATE PUI RATE AUDIT# CHANGED\n"
)


def fixed(fields, width=133):
    chars = [" "] * width
    for start, text in fields:
        chars[start:start + len(text)] = text
    return "".join(chars).rstrip() + "\n"


def write(tmp_path, text):
    path = tmp_path / "source.txt"
    path.write_text(text, encoding="utf-8")
    return path


def cv_record(*, age="25", first=0, last=2, zero="37.40-", values=None, user="06"):
    if values is None:
        values = ["37.40", "100.00", "105.25"] + ["0.00"] * 7
    text = CV_LABELS
    text += f"    {user}  1-ABC-01  A B      {age}  00  00  {first:02}  {last:02}  {zero}\n"
    text += " -----\n" + CV_GRID + " -----\n"
    for start in range(0, len(values), 10):
        text += f" {start:03}-{start + 9:03}  " + " ".join(values[start:start + 10]) + "\n"
    return text


def test_cvf_rejects_embedded_nul_in_rate_key(tmp_path):
    text = CV_REPORT + cv_record().replace("1-ABC-01", "1-A\x00BC-01")
    with pytest.raises(PackageValidationError, match="identifier"):
        parse_cvf(write(tmp_path, text))


def pui_row(*, plan="WLTEST00", sex="1", rateclass="N", age="35", rating="0",
            rate="123.456789", audit="A00001", changed="01/02/2026"):
    return fixed([
        (11, plan), (23, sex), (32, rateclass), (41, age.rjust(8)),
        (50, rating), (59, rate.rjust(14)), (74, audit), (81, changed),
    ])


def iaf_plan(*, plan="WLTEST00", version="", effective="01011900", first="000",
             last="000", use="0", unit="1,000.00"):
    return fixed([
        (2, plan), (13, version), (16, effective), (25, first), (29, last), (34, use),
        (41, "100"), (46, "1"), (53, "121"), (58, "1"), (60, unit.rjust(14)),
        (75, ".00".rjust(14)), (91, "0"), (100, "0"), (102, "NONE"),
        (118, "1"), (120, "01"), (123, "00"),
    ])


def iaf_aliases(aliases=None):
    aliases = aliases or [("WLTEST00", "", "01011900")]
    return " *** PLAN SEARCH KEYS".ljust(31) + "  ".join(
        f"{plan:<11} {version:<2} {effective}" for plan, version, effective in aliases
    ) + "\n"


def iaf_rates(pairs=None, *, kind="0", start="01011900", stop=""):
    if pairs is None:
        pairs = [("002SA**", ".00"), ("002SA3A", ".125")]
    fields = []
    if kind is not None:
        fields = [(19, kind), (23, start), (33, stop)]
    for offset, (identifier, value) in zip((43, 65, 87, 109), pairs):
        fields.extend([(offset, identifier), (offset + 8, value.rjust(12))])
    return fixed(fields)


def iaf_record(**plan_args):
    return iaf_plan(**plan_args) + iaf_aliases() + IAF_COLUMNS_LINE + iaf_rates()


def test_cvf_zero_floor_duration_mapping_and_padding(tmp_path):
    path = write(tmp_path, CV_REPORT + cv_record())
    rows = parse_cvf(path)
    assert len(rows) == 3
    assert set(rows[0]) == set(CV_COLUMNS)
    assert [r["DURATION"] for r in rows] == [0, 1, 2]
    assert [r["RATE"] for r in rows] == [Decimal("0.00"), Decimal("100"), Decimal("105.25")]
    assert all(r["DURATION_ZERO_VALUE"] == Decimal("0.00") for r in rows)
    assert rows[0]["RATE_KEY"] == "1ABC01"
    assert rows[0]["USER_DEFINED"] == "A B"
    assert rows[0]["USER_CODE"] == "06"


@pytest.mark.parametrize("header,grid,expected", [
    ("37.40-", "37.40", "0.00"),
    ("-37.40", "-37.40", "0.00"),
    ("37.40", "37.40-", "37.40"),
    ("0.00", "0.00", "0.00"),
])
def test_cvf_floors_all_durations_after_resolving_header_sign(tmp_path, header, grid, expected):
    values = [grid, "-100.00", "105.25-"] + ["0.00"] * 7
    rows = parse_cvf(write(tmp_path, CV_REPORT + cv_record(zero=header, values=values)))
    assert [r["RATE"] for r in rows] == [Decimal(expected), Decimal("0.00"), Decimal("0.00")]
    assert all(r["DURATION_ZERO_VALUE"] == Decimal(expected) for r in rows)
    assert all(isinstance(r["RATE"], Decimal) for r in rows)


def test_cvf_load_package_contains_only_nonnegative_cash_values(tmp_path):
    from suiteview.ratemanager.whole_life.service import parse_sources

    values = ["37.40", "-100.00", "105.25"] + ["0.00"] * 7
    path = write(tmp_path, CV_REPORT + cv_record(values=values))
    data = parse_sources("CVF", [str(path)]).tables["WL_RATE_CV"]
    rate = data.spec.columns.index("RATE")
    header = data.spec.columns.index("DURATION_ZERO_VALUE")
    assert [row[rate] for row in data.rows] == [
        Decimal("0.00"), Decimal("0.00"), Decimal("105.25"),
    ]
    assert all(row[header] == Decimal("0.00") for row in data.rows)


def test_cvf_floor_does_not_hide_conflicting_negative_source_rates(tmp_path):
    first = ["37.40", "-100.00", "105.25"] + ["0.00"] * 7
    second = ["37.40", "-101.00", "105.25"] + ["0.00"] * 7
    text = CV_REPORT + cv_record(values=first) + cv_record(values=second)
    with pytest.raises(PackageValidationError, match="Conflicting duplicate"):
        parse_cvf(write(tmp_path, text))


def test_cvf_nonzero_first_duration_and_in_range_zero(tmp_path):
    values = ["0.00"] * 20
    values[6] = "11.00"
    values[11] = "22.00"
    rows = parse_cvf(write(tmp_path, CV_REPORT + cv_record(
        first=5, last=11, zero=".00", values=values)))
    assert [r["DURATION"] for r in rows] == list(range(5, 12))
    assert rows[0]["RATE"] == 0
    assert rows[1]["RATE"] == 11
    assert rows[-1]["RATE"] == 22


def test_cvf_nul_padding_and_page_headers(tmp_path):
    text = (CV_REPORT + cv_record()).replace("000-009", "000-009\0\0").replace("105.25", "105.25\0\0")
    text = text.replace(" 000-009", CV_REPORT + " 000-009")
    assert len(parse_cvf(write(tmp_path, text))) == 3


@pytest.mark.parametrize("first", [1, 5])
def test_cvf_no_zero_duration_starts_grid_at_first_and_preserves_null(tmp_path, first):
    from suiteview.ratemanager.whole_life.service import parse_sources

    values = ["22.27", "0.94", "21.08", "-1.00"] + ["0.00"] * 6
    path = write(tmp_path, CV_REPORT + cv_record(
        first=first, last=first + 3, zero="NO ZERO DUR", values=values, user="00",
    ))
    audit = []
    rows = parse_cvf(path, infer_early_negatives=True, inference_audit=audit)
    assert [row["DURATION"] for row in rows] == list(range(first, first + 4))
    assert [row["RATE"] for row in rows] == [
        Decimal("22.27"), Decimal("0.94"), Decimal("21.08"), Decimal("0.00"),
    ]
    assert all(row["DURATION_ZERO_VALUE"] is None for row in rows)
    assert audit == []
    data = parse_sources("CVF", [str(path)], infer_cvf_negatives=True).tables["WL_RATE_CV"]
    assert all(row[data.spec.columns.index("DURATION_ZERO_VALUE")] is None for row in data.rows)


def test_cvf_no_zero_duration_grid_continues_across_printed_rows(tmp_path):
    values = [str(value) for value in range(1, 13)] + ["0.00"] * 8
    rows = parse_cvf(write(tmp_path, CV_REPORT + cv_record(
        first=1, last=12, zero="NO ZERO DUR", values=values,
    )))
    assert {row["DURATION"]: row["RATE"] for row in rows} == {
        duration: Decimal(duration) for duration in range(1, 13)
    }


def test_cvf_no_zero_duration_121_preserves_the_printed_decade(tmp_path):
    text = CV_REPORT + cv_record(
        first=121, last=122, zero="NO ZERO DUR",
        values=["1000.00"] + ["0.00"] * 9,
    ).replace("000-009", "120-129")
    rows = parse_cvf(write(tmp_path, text), infer_early_negatives=True)
    assert [(row["DURATION"], row["RATE"]) for row in rows] == [
        (121, Decimal("1000.00")), (122, Decimal("0.00")),
    ]
    assert all(row["DURATION_ZERO_VALUE"] is None for row in rows)


def test_cvf_no_zero_duration_cannot_hide_a_missing_first_grid_row(tmp_path):
    text = CV_REPORT + cv_record(
        first=1, last=12, zero="NO ZERO DUR", values=["0.00"] * 10,
    ).replace("000-009", "010-019")
    with pytest.raises(PackageValidationError, match="missing duration 1"):
        parse_cvf(write(tmp_path, text))


@pytest.mark.parametrize("first,last,values,match", [
    (0, 2, ["0.00"] * 10, "requires a positive FIRST"),
    (1, 11, ["0.00"] * 10, "Incomplete cash-value"),
    (1, 2, ["1.00", "2.00", "3.00"] + ["0.00"] * 7, "Nonzero padding"),
])
def test_cvf_no_zero_duration_rejects_inconsistent_or_truncated_source(
    tmp_path, first, last, values, match,
):
    with pytest.raises(PackageValidationError, match=match):
        parse_cvf(write(tmp_path, CV_REPORT + cv_record(
            first=first, last=last, zero="NO ZERO DUR", values=values,
        )))


def test_cvf_identical_duplicates_retained_and_conflicting_metadata_rejected(tmp_path):
    assert len(parse_cvf(write(tmp_path, CV_REPORT + cv_record() * 2))) == 6
    with pytest.raises(PackageValidationError, match="Conflicting duplicate"):
        parse_cvf(write(tmp_path, CV_REPORT + cv_record() + cv_record(zero="37.40")))


@pytest.mark.parametrize("change,match", [
    (lambda text: text.replace("CASH VALUE RATES", "NET SINGLE PREMIUM RATES"), "Unsupported CVF"),
    (lambda text: text.replace("105.25", "105.2X"), "Invalid numeric"),
    (lambda text: text.replace("105.25", "1,05.25"), "Invalid numeric"),
    (lambda text: text.replace("105.25", "1_05.25"), "Invalid numeric"),
    (lambda text: text.replace("105.25", "NaN"), "Invalid numeric"),
    (lambda text: text.replace("105.25", "105.251"), "decimal places"),
    (lambda text: text.replace("000-009", "000-008"), "ten values"),
    (lambda text: text.replace("37.40-", "38.40-"), "disagrees"),
    (lambda text: text.replace("100.00", "10\0.00"), "NUL inside"),
    (lambda text: text + " *** UNKNOWN SECTION\n", "Unsupported CVF"),
    (lambda text: text.split(" 000-009")[0], "Incomplete cash-value"),
    (lambda text: text + CV_LABELS, "header has no record"),
])
def test_cvf_rejects_malformed_or_truncated_source(tmp_path, change, match):
    path = write(tmp_path, change(CV_REPORT + cv_record()))
    with pytest.raises(PackageValidationError, match=match) as exc:
        parse_cvf(path)
    assert str(path) + ":" in str(exc.value)


@pytest.mark.parametrize("padding", ["1.00", "-1.00", "1.00-"])
def test_cvf_rejects_nonzero_padding(tmp_path, padding):
    values = ["0.00"] * 10
    values[5] = padding
    with pytest.raises(PackageValidationError, match="Nonzero padding"):
        parse_cvf(write(tmp_path, CV_REPORT + cv_record(zero=".00", values=values)))


def test_cvf_sign_inference_is_opt_in_and_audits_example(tmp_path):
    values = ["42.85", "22.27", "0.94", "21.08"] + ["0.00"] * 6
    path = write(tmp_path, CV_REPORT + cv_record(
        age="59", user="08", last=3, zero="42.85-", values=values,
    ))
    assert [r["RATE"] for r in parse_cvf(path)] == [
        Decimal("0"), Decimal("22.27"), Decimal("0.94"), Decimal("21.08"),
    ]
    audit = []
    rows = parse_cvf(path, infer_early_negatives=True, inference_audit=audit)
    assert [r["RATE"] for r in rows] == [
        Decimal("0"), Decimal("0"), Decimal("0.94"), Decimal("21.08"),
    ]
    assert len(audit) == 1
    assert audit[0] == {
        "USER_CODE": "08", "RATE_KEY": "1ABC01", "USER_DEFINED": "A B",
        "ISSUE_AGE": 59, "DURATION": 1,
        "printed_rate": "22.27", "loaded_rate": "0.00", "source_line": 7,
        "minimum_duration": 2, "minimum_rate": "0.94", "header_zero": "-42.85",
    }


@pytest.mark.parametrize("zero,values,expected,inferred", [
    ("42.85", ["42.85", "22.27", "0.94", "21.08"], ["42.85", "22.27", "0.94", "21.08"], 0),
    ("42.85-", ["42.85", "22.27", "22.27", "0.94", "21.08"],
     ["0", "22.27", "22.27", "0.94", "21.08"], 0),
    ("42.85-", ["42.85", "22.27", "0.94"], ["0", "22.27", "0.94"], 0),
    ("42.85-", ["42.85", "43.00", "50.00"], ["0", "43.00", "50.00"], 0),
    ("42.85-", ["42.85", "+22.27", "0.94", "21.08"], ["0", "22.27", "0.94", "21.08"], 0),
    ("42.85-", ["42.85", "22.27", "+0.94", "21.08"], ["0", "0", "0.94", "21.08"], 1),
    ("42.85-", ["42.85", "-22.27", "0.94", "21.08"], ["0", "0", "0.94", "21.08"], 0),
    ("42.85-", ["42.85", "22.27", "-0.94", "21.08"], ["0", "0", "0", "21.08"], 1),
    ("42.85-", ["42.85", "22.27", "0.00", "21.08"], ["0", "0", "0", "21.08"], 1),
    ("42.85-", ["42.85", "22.27", "12.00", "0.94", "21.08", "18.00"],
     ["0", "0", "0", "0.94", "21.08", "18.00"], 2),
])
def test_cvf_inference_respects_anchor_turning_point_and_explicit_signs(
    tmp_path, zero, values, expected, inferred,
):
    audit = []
    text = CV_REPORT + cv_record(
        zero=zero, last=len(values) - 1, values=values + ["0.00"] * (10 - len(values)),
    )
    rows = parse_cvf(write(tmp_path, text), infer_early_negatives=True, inference_audit=audit)
    assert [r["RATE"] for r in rows] == [Decimal(value) for value in expected]
    assert len(audit) == inferred


def test_cvf_inference_does_not_use_a_nonzero_start_or_padding_as_a_turn(tmp_path):
    values = ["0.00", "0.00", "22.27", "0.94", "21.08"] + ["0.00"] * 5
    rows = parse_cvf(write(tmp_path, CV_REPORT + cv_record(
        first=2, last=4, zero="0.00", values=values,
    )), infer_early_negatives=True)
    assert [r["RATE"] for r in rows] == [Decimal("22.27"), Decimal("0.94"), Decimal("21.08")]


@pytest.mark.parametrize("second_value,raises", [("23.00", True), ("+22.27", False)])
def test_cvf_inference_never_hides_raw_conflicts_or_explicit_positive_duplicates(
    tmp_path, second_value, raises,
):
    values = ["42.85", "22.27", "0.94", "21.08"] + ["0.00"] * 6
    first = cv_record(last=3, zero="42.85-", values=values)
    values[1] = second_value
    text = CV_REPORT + first + cv_record(last=3, zero="42.85-", values=values)
    audit = []
    if raises:
        with pytest.raises(PackageValidationError, match="Conflicting duplicate"):
            parse_cvf(write(tmp_path, text), infer_early_negatives=True, inference_audit=audit)
    else:
        rows = parse_cvf(write(tmp_path, text), infer_early_negatives=True, inference_audit=audit)
        assert rows[1]["RATE"] == rows[5]["RATE"] == Decimal("22.27")
    assert audit == []


def test_cvf_inference_audit_deduplicates_identical_records(tmp_path):
    values = ["42.85", "22.27", "0.94", "21.08"] + ["0.00"] * 6
    text = CV_REPORT + cv_record(last=3, zero="42.85-", values=values) * 2
    audit = []
    rows = parse_cvf(write(tmp_path, text), infer_early_negatives=True, inference_audit=audit)
    assert rows[1]["RATE"] == rows[5]["RATE"] == 0
    assert len(audit) == 1


def test_cvf_inference_publishes_no_audit_for_invalid_source(tmp_path):
    values = ["42.85", "22.27", "0.94", "21.08", "1.00"] + ["0.00"] * 5
    audit = []
    with pytest.raises(PackageValidationError, match="Nonzero padding"):
        parse_cvf(write(tmp_path, CV_REPORT + cv_record(
            last=3, zero="42.85-", values=values,
        )), infer_early_negatives=True, inference_audit=audit)
    assert audit == []


def test_cvf_inference_provenance_is_part_of_single_and_combined_packages(tmp_path):
    from suiteview.ratemanager.whole_life.service import parse_sources, parse_workup

    values = ["42.85", "22.27", "0.94", "21.08"] + ["0.00"] * 6
    path = str(write(tmp_path, CV_REPORT + cv_record(last=3, zero="42.85-", values=values)))
    packages = [
        parse_sources("CVF", [path], infer_cvf_negatives=True),
        parse_workup({"CVF": [path]}, infer_cvf_negatives=True),
    ]
    for package in packages:
        audit = package.sources[0]["cvf_inference"]
        assert audit["enabled"] is True
        assert audit["rule"] == "negative-header-initial-decline-v1"
        assert audit["adjusted_rows"] == len(audit["adjustments"]) == 1
        assert audit["adjustments"][0]["DURATION"] == 1
    literal = parse_sources("CVF", [path])
    assert literal.sources[0]["cvf_inference"]["enabled"] is False
    assert literal.sources[0]["cvf_inference"]["adjusted_rows"] == 0
    assert literal.digest != packages[0].digest


@pytest.mark.parametrize("option", ["false", 1, None])
def test_cvf_parser_rejects_nonboolean_inference(tmp_path, option):
    with pytest.raises(PackageValidationError, match="true or false"):
        parse_cvf(write(tmp_path, CV_REPORT + cv_record()), infer_early_negatives=option)


@pytest.mark.parametrize("text", [
    CV_REPORT + cv_record(),
    PUI_START + pui_row(),
    iaf_record(),
    "NET SINGLE PREMIUM RATES\nUnknown unverified structure\n",
    "",
])
def test_nsp_never_relabels_an_unverified_source(tmp_path, text):
    with pytest.raises(PackageValidationError, match="NSP"):
        parse_nsp(write(tmp_path, text))


def test_pui_blank_keys_decimal_dates_and_user_sections(tmp_path):
    text = PUI_START + pui_row(rateclass="", rating="")
    text += "0 ENTRIES FOR USER 26 CONTINUED\n"
    text += "0 PLAN CD SEX CLASS ATT AGE TAB RATE PUI RATE AUDIT# CHANGED\n"
    text += pui_row()
    text += "0TABLE CONTAINS 3 ENTRIES OF WHICH 1 HAVE BEEN MARKED FOR DELETION.\n"
    text += "0*** END-OF-JOB ***\n"
    rows = parse_pui(write(tmp_path, text))
    assert len(rows) == 2
    assert set(rows[0]) == set(PUI_COLUMNS)
    assert rows[0]["RATECLASS"] == rows[0]["TABLE_RATING"] == ""
    assert rows[0]["RATE"] == Decimal("123.456789")
    assert rows[0]["CHANGED_DATE"] == date(2026, 1, 2)
    assert rows[1]["USER_CODE"] == "26"
    assert rows[1]["ATTAINED_AGE"] == 35


def test_pui_identical_duplicates_retained_conflicts_fail(tmp_path):
    assert len(parse_pui(write(tmp_path, PUI_START + pui_row() * 2))) == 2
    with pytest.raises(PackageValidationError, match="Conflicting duplicate"):
        parse_pui(write(tmp_path, PUI_START + pui_row() + pui_row(rate="124.000000")))


def test_pui_user_heading_repeated_across_page_break(tmp_path):
    text = PUI_START + pui_row()
    text += "0 ENTRIES FOR USER 26\n"
    text += PUI_START.replace("PAGE 1", "PAGE 2").replace("USER 01", "USER 26")
    text += pui_row()
    assert len(parse_pui(write(tmp_path, text))) == 2


@pytest.mark.parametrize("text,match", [
    (PUI_START.replace("CJUDTPUI", "OTHER") + pui_row(), "Unsupported table"),
    (PUI_START.replace("0 ENTRIES FOR USER 01\n", "") + pui_row(), "no user"),
    (PUI_START + pui_row(rate="1.1234567"), "decimal places"),
    (PUI_START + pui_row(rate="garbage"), "Invalid numeric"),
    (PUI_START + pui_row(changed="02/30/2026"), "Invalid calendar"),
    (PUI_START + pui_row(age="3X"), "Invalid integer"),
    (PUI_START + pui_row(rating="ABC"), "Malformed PUI"),
    (PUI_START + pui_row() + "new unrecognized section\n", "fixed-width"),
    (PUI_START + pui_row() + "0TABLE CONTAINS 3 ENTRIES OF WHICH 1 HAVE BEEN MARKED FOR DELETION.\n", "totals"),
    (PUI_START + pui_row() + "0*** END-OF-JOB ***\n" + pui_row(), "after END"),
    (PUI_START + pui_row() + "0 ENTRIES FOR USER 26\n", "no rate rows"),
])
def test_pui_rejects_bad_keys_values_layouts_and_totals(tmp_path, text, match):
    with pytest.raises(PackageValidationError, match=match):
        parse_pui(write(tmp_path, text))


def test_iaf_preserves_source_age_range_use_identifiers_options_and_zero(tmp_path):
    rows = parse_iaf(write(tmp_path, iaf_record(first="000", last="085", use="1")), "06")
    assert len(rows) == 2
    assert set(rows[0]) == set(IAF_COLUMNS)
    assert rows[0]["FIRST_AGE"] == 0 and rows[0]["LAST_AGE"] == 85
    assert rows[0]["IAR_USE"] == 1
    assert rows[0]["RATE"] == Decimal("0")
    assert rows[0]["SCALE_STOP"] is None
    assert rows[0]["SOURCE_EFFECTIVE_DATE"] == date(1900, 1, 1)
    assert rows[0]["ME_AGE"] == 121 and rows[0]["PAY_AGE"] == 100
    assert rows[1]["PREMIUM_IDENTIFIER"] == "002SA3A"
    assert rows[1]["DURATION_CODE"] == "00"
    assert rows[1]["SEX"] == "2" and rows[1]["RATECLASS"] == "S"
    assert rows[1]["BAND"] == "A" and rows[1]["PLAN_OPTION"] == "3A"
    assert rows[1]["RATE"] == Decimal(".125")
    assert "ISSUE_AGE" not in rows[1] and "DURATION" not in rows[1]


def test_iaf_populated_blank_premium_identifier_fails_closed(tmp_path):
    text = iaf_plan() + iaf_aliases() + IAF_COLUMNS_LINE
    text += iaf_rates(pairs=[("002SA**", ".00"), ("", ".125")])

    with pytest.raises(PackageValidationError, match="Malformed premium identifier"):
        parse_iaf(write(tmp_path, text), "00")


def test_iaf_blank_premium_identifier_and_blank_rate_cell_is_skipped(tmp_path):
    text = iaf_plan() + iaf_aliases() + IAF_COLUMNS_LINE
    text += iaf_rates(pairs=[("002SA**", ".00"), ("", "")])

    rows = parse_iaf(write(tmp_path, text), "00")

    assert len(rows) == 1
    assert rows[0]["PREMIUM_IDENTIFIER"] == "002SA**"


def test_iaf_search_aliases_versions_and_effective_dates(tmp_path):
    text = iaf_plan(version="2", effective="01012025")
    text += iaf_aliases([("WLTEST00", "2", "01012025"), ("WLALIAS0", "3", "02012025")])
    text += IAF_COLUMNS_LINE + iaf_rates(kind="Y", stop="12312026", pairs=[("991S03N", "42.75")])
    rows = parse_iaf(write(tmp_path, text), "01")
    assert len(rows) == 2
    assert rows[1]["SOURCE_PLANCODE"] == "WLTEST00"
    assert rows[1]["SOURCE_IAF_VERSION"] == "2"
    assert rows[1]["PLANCODE"] == "WLALIAS0" and rows[1]["IAF_VERSION"] == "3"
    assert rows[1]["EFFECTIVE_DATE"] == date(2025, 2, 1)
    assert rows[1]["DURATION_CODE"] == "99" and rows[1]["PLAN_OPTION"] == "3N"
    assert rows[1]["RATE_TYPE"] == "Y"
    assert rows[1]["SCALE_STOP"] == date(2026, 12, 31)


def test_iaf_pagination_rate_type_changes_and_continuations(tmp_path):
    text = iaf_record()
    text += "1                                                  TEST COMPANY\n"
    text += "0DATE 01/02/26 PRINT ISSUE AGE DESCRIPTION FILE PAGE 2\n"
    text += IAF_COLUMNS_LINE + iaf_rates(kind=None, pairs=[("992NA*A", "1.25000")])
    text += IAF_COLUMNS_LINE + iaf_rates(kind="G", pairs=[("992NA*A", "2.34567")])
    rows = parse_iaf(write(tmp_path, text), "00")
    assert len(rows) == 4
    assert rows[2]["RATE_TYPE"] == "0" and rows[3]["RATE_TYPE"] == "G"
    assert rows[3]["RATE"] == Decimal("2.34567")


def test_iaf_identical_duplicates_retained_conflicts_fail(tmp_path):
    assert len(parse_iaf(write(tmp_path, iaf_record() * 2), "00")) == 4
    with pytest.raises(PackageValidationError, match="Conflicting duplicate"):
        parse_iaf(write(tmp_path, iaf_record() + iaf_record().replace(".125", ".250")), "00")


def test_iaf_page_repeats_last_rate_heading_before_new_plan(tmp_path):
    text = iaf_record()
    text += "0DATE 01/02/26 PRINT ISSUE AGE DESCRIPTION FILE PAGE 2\n"
    text += IAF_COLUMNS_LINE
    text += iaf_record(first="001", last="001")
    assert len(parse_iaf(write(tmp_path, text), "00")) == 4


@pytest.mark.parametrize("change,match", [
    (lambda text: text.replace("01011900", "02301900"), "Invalid calendar"),
    (lambda text: text.replace("002SA3A", "XX2SA3A"), "Malformed premium"),
    (lambda text: text.replace(".125", "NaN"), "Invalid numeric"),
    (lambda text: text.replace(".125", "1e3"), "Invalid numeric"),
    (lambda text: text.replace("1,000.00", "1,00X.00"), "Invalid numeric"),
    (lambda text: text.replace("                   0", "                   Z"), "Unknown IAF"),
    (lambda text: text.replace("WLTEST00      01011900", "OTHER000      01011900"), "own key"),
    (lambda text: text + " *** ADV PROD. CTL. unknown layout\n", "Unsupported IAF"),
    (lambda text: text + IAF_COLUMNS_LINE, "Truncated IAF"),
    (lambda text: text + IAF_COLUMNS_LINE + iaf_rates(kind="G", pairs=[]), "Truncated IAF"),
])
def test_iaf_rejects_malformed_or_unknown_content(tmp_path, change, match):
    with pytest.raises(PackageValidationError, match=match):
        parse_iaf(write(tmp_path, change(iaf_record())), "00")


@pytest.mark.parametrize("user", ["", "1", "001", "AA"])
def test_iaf_requires_explicit_source_user(tmp_path, user):
    with pytest.raises(PackageValidationError, match="two digits"):
        parse_iaf(write(tmp_path, iaf_record()), user)


def test_iaf_empty_scale_before_another_scale_fails(tmp_path):
    text = iaf_record() + iaf_rates(kind="G", pairs=[])
    text += iaf_rates(kind="Y", pairs=[("001N0**", "12.00")])
    with pytest.raises(PackageValidationError, match="Previous premium scale"):
        parse_iaf(write(tmp_path, text), "00")


def test_iaf_date_only_scale_then_cells_is_valid(tmp_path):
    text = iaf_plan() + iaf_aliases() + IAF_COLUMNS_LINE
    text += iaf_rates(kind="C", pairs=[])
    text += iaf_rates(kind=None, pairs=[("001N0**", "0.12345")])
    assert parse_iaf(write(tmp_path, text), "00")[0]["RATE"] == Decimal(".12345")


def test_all_parsers_reject_empty_inputs(tmp_path):
    path = write(tmp_path, "")
    for parse in (parse_cvf, parse_pui, lambda p: parse_iaf(p, "00")):
        with pytest.raises(PackageValidationError, match="No supported"):
            parse(path)
