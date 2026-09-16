"""Annual totals: frozen September 15, 2026 UL045809 captures and failure states."""

from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path

import pytest

from suiteview.polview.models.policy_record_annual_totals import (
    FIELDS_63, FIELDS_64, FLAG_COLUMNS, TABLES, build_segment_63, build_segment_64,
)

ROOT = Path(__file__).resolve().parents[1]
BUILDERS = {"63": build_segment_63, "64": build_segment_64}
SPECS = {"63": FIELDS_63, "64": FIELDS_64}


class Policy:
    policy_number = "UL045809"
    company_name = "ANICO"
    region = "CKPR"

    def __init__(self, segment, rows, error=None):
        self.segment, self.rows, self.error = segment, rows, error

    def fetch_table(self, table):
        assert table == TABLES[self.segment]
        return self.rows

    def table_error(self, table):
        assert table == TABLES[self.segment]
        return self.error


def row_for(segment):
    row = {spec[1]: 0 for spec in SPECS[segment]}
    row.update({column: "0" for column in FLAG_COLUMNS[segment]})
    row[SPECS[segment][0][1]] = 0 if segment == "63" else date(2026, 12, 31)
    return row


def runs(lines, name):
    return [run for line in lines for run in line if run.get("field") == name]


def captured_rows(segment):
    if segment == "63":
        # year, total CV, premiums, credited interest, guaranteed interest, yearly CV, opening CV
        amounts = (
            (0, "89.25", "17105.30", "697.20", "695.35", "89.25", "265.89"),
            (35, "640.66", "2316.00", "8.29", "8.17", "551.41", "89.25"),
            (36, "1691.83", "2316.00", "44.21", "44.08", "1051.17", "640.66"),
            (37, "2704.50", "2316.00", "84.83", "84.70", "1012.67", "1691.83"),
            (38, "3664.87", "2316.00", "123.91", "123.76", "960.37", "2704.50"),
            (39, "4530.17", "2316.00", "159.83", "159.70", "865.30", "3664.87"),
            (40, "2854.89", "2316.00", "192.25", "192.12", "-1675.28", "4530.17"),
            (41, "1354.74", "193.00", "88.93", "88.92", "-1500.15", "2854.89"),
            (42, "49.28", "0.00", "20.60", "20.60", "-1305.46", "1354.74"),
        )
        columns = ("POL_YR_DUR", "POL_TOT_CSV_AMT", "YTD_TOT_PMT_AMT", "YTD_CRE_ITS_AMT",
                   "YTD_GUA_RT_ITS_AMT", "YTD_CSV_AMT", "POL_YR_MVA_CSV_AMT")
        nulls = ("FND_BEG_YR_BAL_AMT", "FND_TRS_AMT", "FND_TRS_CNT_QTY", "CHG_FREE_WDWL_PCT",
                 "BEG_YR_VAR_ACT_BAL", "CRY_FWD_FRE_WD_PCT", "CRY_FWD_FRE_WD_AMT")
    else:
        amounts = tuple(
            (date(year, 12, 31), value, "1920.00" if year == 2018 else
             "193.00" if year == 2025 else "0.00" if year == 2026 else "2316.00")
            for year, value in zip(range(2018, 2027), (
                "89.40", "641.76", "1694.76", "2709.19", "3671.13",
                "4537.91", "2859.80", "1357.07", "0.00",
            ))
        )
        columns = ("CAL_YR_END_DT", "UNLOANED_CSV_AMT", "CAL_YR_REG_PRM_AMT")
        nulls = ("RQR_MIN_DTB_AMT", "REG_MIN_DTB_AMT", "INT_LIFE_FCT",
                 "CAL_YR_NRG_PRM_AMT", "PV_ADDL_BENS")
    rows = []
    for values in amounts:
        row = row_for(segment)
        row.update(zip(columns, values))
        row.update({column: None for column in nulls})
        if segment == "63":
            if row["POL_YR_DUR"] == 0:
                row.update(YTD_ADD_PRM_AMT="200.30", YTD_ADD_PRM_QTY=2)
            if row["POL_YR_DUR"] == 40:
                row["YTD_WTD_NBR"] = 1
        else:
            row["YR_END_ACT_BAL_IND"] = "0" if values[0].year == 2026 else "1"
            if values[0].year == 2024:
                row["CAL_YR_NET_WTD_AMT"] = "2450.00"
        rows.append(row)
    return rows


@pytest.mark.parametrize("segment", ("63", "64"))
def test_complete_frozen_capture_and_sorted_rows(segment):
    expected = json.loads((ROOT / "tools" / "policyrecord" / "annual_totals_capture.json").read_text())[segment]
    rows = captured_rows(segment)[::-1]
    original = deepcopy(rows)
    lines = BUILDERS[segment](Policy(segment, rows))
    text = ["".join(run["text"] for run in line) for line in lines]
    assert [" ".join(line.split()) for line in text[1:19]] == expected
    assert len(runs(lines, "Segment Identification")) == 9
    assert all(len(line) <= 81 for line in text[1:19])
    assert "CK620 DISPLAY COMPLETE" in "\n".join(text)
    assert "CKPR-ANICO" in "\n".join(text)
    assert rows == original


@pytest.mark.parametrize("segment", ("63", "64"))
def test_null_is_distinct_from_numeric_zero(segment):
    row = row_for(segment)
    spec = SPECS[segment][1]
    row[spec[1]] = None
    null = runs(BUILDERS[segment](Policy(segment, [row])), spec[0])[0]
    row[spec[1]] = 0
    zero = runs(BUILDERS[segment](Policy(segment, [row])), spec[0])[0]
    assert null["text"] == zero["text"] == ".00"
    assert null["dim"] and "DB2 NULL" in null["note"]
    assert "dim" not in zero and "DB2 NULL" not in zero["note"]


@pytest.mark.parametrize("segment", ("63", "64"))
def test_every_flag_bit_has_verified_source_or_example_warning(segment):
    for index, column in enumerate(FLAG_COLUMNS[segment]):
        row = row_for(segment)
        row[column] = "1"
        lines = BUILDERS[segment](Policy(segment, [row]))
        flag = runs(lines, "Flag Byte A")
        assert "".join(run["text"] for run in flag) == "0" * index + "1" + "0" * (7 - index)
        assert flag[-1]["example"] and "EXAMPLE DATA" in flag[-1]["note"]
        assert all(not run.get("example") and TABLES[segment] in run["note"] for run in flag[:-1])
        other_flags = [run for line in lines for run in line
                       if "Flag" in str(run.get("field")) and run["field"] != "Flag Byte A"]
        assert all(run["example"] for run in other_flags)


@pytest.mark.parametrize("segment", ("63", "64"))
def test_null_and_invalid_flags_are_not_zero(segment):
    row = row_for(segment)
    column = FLAG_COLUMNS[segment][0]
    row[column] = None
    flag = runs(BUILDERS[segment](Policy(segment, [row])), "Flag Byte A")
    assert flag[0]["text"] == "?" and flag[0]["dim"]
    row[column] = "Y"
    with pytest.raises(ValueError, match=column):
        BUILDERS[segment](Policy(segment, [row]))


@pytest.mark.parametrize("segment", ("63", "64"))
def test_absent_rows_and_explicit_database_failures(segment):
    assert BUILDERS[segment](Policy(segment, [])) is None
    with pytest.raises(ValueError, match="offline"):
        BUILDERS[segment](Policy(segment, [], error="offline"))
    policy = Policy(segment, [])
    def fail(table):
        raise RuntimeError("connection lost")
    policy.fetch_table = fail
    with pytest.raises(RuntimeError, match="connection lost"):
        BUILDERS[segment](policy)


@pytest.mark.parametrize("segment", ("63", "64"))
def test_every_missing_source_column_fails_explicitly(segment):
    for column in (*[spec[1] for spec in SPECS[segment]], *FLAG_COLUMNS[segment]):
        row = row_for(segment)
        del row[column]
        with pytest.raises(ValueError, match=column):
            BUILDERS[segment](Policy(segment, [row]))


@pytest.mark.parametrize("segment", ("63", "64"))
@pytest.mark.parametrize("bad", ("NaN", "Infinity", "", "abc", "1.001", "1000000000.00"))
def test_bad_amounts_are_not_rounded_or_silently_zeroed(segment, bad):
    row = row_for(segment)
    row[SPECS[segment][1][1]] = bad
    with pytest.raises(ValueError, match="Invalid Segment"):
        BUILDERS[segment](Policy(segment, [row]))


@pytest.mark.parametrize("segment", ("63", "64"))
def test_signed_fraction_and_multiple_continuations(segment):
    row = row_for(segment)
    for name, column, _, digits, decimals in SPECS[segment][1:]:
        row[column] = "-" + "9" * (digits - decimals) + ("." + "9" * decimals if decimals else "")
    row[SPECS[segment][1][1]] = "-0.25"
    lines = BUILDERS[segment](Policy(segment, [row]))
    assert runs(lines, SPECS[segment][1][0])[0]["text"] == "-.25"
    data = [line for line in lines[1:] if any(run.get("field") in {s[0] for s in SPECS[segment]} for run in line)]
    assert len(data) >= 3
    assert all(sum(len(run["text"]) for run in line) <= 81 for line in data)


@pytest.mark.parametrize("segment", ("63", "64"))
def test_duplicate_and_missing_year_keys(segment):
    row = row_for(segment)
    with pytest.raises(ValueError, match="duplicate"):
        BUILDERS[segment](Policy(segment, [row, row]))
    row[SPECS[segment][0][1]] = None
    with pytest.raises(ValueError, match="NULL"):
        BUILDERS[segment](Policy(segment, [row]))


@pytest.mark.parametrize("value", (-1, 256, "2.5", "NaN"))
def test_invalid_policy_year(value):
    row = row_for("63")
    row["POL_YR_DUR"] = value
    with pytest.raises(ValueError, match="POL_YR_DUR"):
        build_segment_63(Policy("63", [row]))


@pytest.mark.parametrize("value", ("2026-02-30", "2026-06-30", "9999-12-31", "1900-12-31", "bad"))
def test_invalid_calendar_year_end(value):
    row = row_for("64")
    row["CAL_YR_END_DT"] = value
    with pytest.raises(ValueError, match="CAL_YR_END_DT"):
        build_segment_64(Policy("64", [row]))


@pytest.mark.parametrize("value", ("2024-12-31", date(2024, 12, 31), datetime(2024, 12, 31, 12)))
def test_calendar_dates_and_life_factor_precision(value):
    row = row_for("64")
    row.update(CAL_YR_END_DT=value, INT_LIFE_FCT="27.4")
    lines = build_segment_64(Policy("64", [row]))
    assert runs(lines, "Calender Year-End Date")[0]["text"] == "12/31/2024"
    assert runs(lines, "Initial Expectation of Life Factor")[0]["text"] == "27.4"
    assert "".join(run["text"] for run in runs(lines, "Flag Byte A")) == "00000000"
    row["INT_LIFE_FCT"] = "27.45"
    with pytest.raises(ValueError, match="INT_LIFE_FCT"):
        build_segment_64(Policy("64", [row]))


@pytest.mark.parametrize("segment", ("63", "64"))
def test_screen_metadata_matches_all_emitted_fields(segment):
    path = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / f"seg_{segment}.json"
    screen = json.loads(path.read_text(encoding="utf-8"))
    specs = {spec["name"]: spec for spec in screen["field_specs"]}
    for name, column, cobol, digits, decimals in SPECS[segment]:
        assert specs[name]["db2"] == f"{TABLES[segment]}.{column}"
        assert specs[name]["cobol"] == cobol
        assert specs[name]["digits"] == digits
        assert specs[name]["decimals"] == decimals
        assert f"DB2: {TABLES[segment]}.{column}" in screen["layout_html"]
    expected_end = "106-108" if segment == "63" else "69-74"
    assert specs[SPECS[segment][-1][0]]["byte"] == expected_end
    assert expected_end in screen["layout_html"]
    assert screen["lines"] and screen["layout_html"]


@pytest.mark.parametrize("segment", ("63", "64"))
def test_registered_live_screen_integration_and_error_state(segment):
    from suiteview.polview.ui.policy_record_viewer import _SEGMENTS, build_screen

    assert segment in _SEGMENTS
    screen = build_screen(segment, Policy(segment, captured_rows(segment)))
    assert screen["live"] is True
    for line in screen["lines"]:
        for run in line:
            if run.get("field"):
                assert run["field"] in screen["fields"]
    assert build_screen(segment, Policy(segment, [])) is None
    failed = build_screen(segment, Policy(segment, [], error="SELECT denied"))
    assert not failed.get("live")
    assert "SELECT denied" in failed["live_error"]
