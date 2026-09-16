"""Read-only 6255 reconstruction, source integrity and UL045809 capture regression."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pytest

from suiteview.polview.models.policy_record_fund_control import (
    COMMON_FIELDS, COMMON_TABLE, FIXED_FIELDS, FIXED_TABLE, FLAG_COLUMNS,
    TABLES, TIER_TABLES, build_segment_55,
)
from suiteview.polview.ui.policy_record_viewer import _SEGMENTS, build_screen


CAPTURE = [
    "  6255, UL045809",
    "  55 0079 00100001 00000000 00000000 1 GP F 0 00 0 0 0 0 0 0 0 1 0 00 0 0",
    "          **/**/****   .000 1   1 1 .000 2 999 0 0 1             .000 **/**/****",
    "  55 0079 00000001 00000000 00000000 1 U1 F 0 00 0 0 1 0 1 1 1 1 1 00 0 0",
    "          **/**/****   .000 2 3 1 1 4.000 0 0   0 0 ANICO1983   6.000 12/14/2000",
]


class Policy:
    policy_number = "UL045809"
    region = "CKPR"
    company_name = "ANICO"

    def __init__(self):
        self.tables = {table: [] for table in TABLES}
        self.errors = {}
        self.calls = []
        key = {"TCH_POL_ID": "UL045809 TEST", "CK_CMP_CD": "01", "CK_SYS_CD": "I", "COV_PHA_NBR": 1}
        common = {
            **key, "FND_ID_CD": "GP", **dict.fromkeys(FLAG_COLUMNS, "0"),
            "IRL_GNR_IND": "1", "FND_VAL_STA_IND": "1", "FND_TYP_CD": "F",
            "FND_TAX_STA_CD": "0", "FND_MIN_BAL_TBL_CD": "00",
            "INT_MIN_BAL_RLE_CD": "0", "RMD_MIN_BAL_RLE_CD": "0",
            "FND_PUR_RLE_CD": "0", "TRF_RLE_CD": "0", "WTD_RLE_CD": "0",
            "LN_RLE_CD": "0", "LN_ITS_RLE_CD": "0", "CRG_RLE_CD": "1",
            "MIN_DUR": 0, "PNY_TBL_CD": "00", "PNY_RLE_1_CD": "0",
            "PNY_RLE_2_CD": "0", "LST_TRF_DT": date(9999, 12, 31),
            "LST_TRF_TYP_CD": " ", "ANU_ASM_ITS_RT": Decimal("0.000"),
        }
        fixed = {
            **key, "FND_ID_CD": "GP", "IVM_MTH_TYP_CD": "1", "IVM_MTH_SBY_CD": " ",
            "ITS_ACCR_FQY_PER": 1, "ITS_CMPD_RLE_CD": "1",
            "GUA_FND_ITS_RT": Decimal("0.000"), "GUA_ITS_PER_RLE_CD": "2",
            "GUA_ITS_PER": 999, "ADD_GUA_PER_RLE_CD": "0", "ADD_GUA_PER": None,
            "HI_FND_VAL_PHA_NBR": 1, "CUR_ITS_RT_SER_NBR": " " * 11,
            "CUR_ITS_RT": None, "ITS_PER_END_DT": date(9999, 12, 31),
            "TIER_ITS_RT_NBR": None,
        }
        self.tables[COMMON_TABLE] = [
            common,
            {**common, "FND_ID_CD": "U1", "IRL_GNR_IND": "0",
             "FND_PUR_RLE_CD": "1", "WTD_RLE_CD": "1", "LN_RLE_CD": "1",
             "LN_ITS_RLE_CD": "1", "MIN_DUR": 1},
        ]
        self.tables[FIXED_TABLE] = [
            fixed,
            {**fixed, "FND_ID_CD": "U1", "IVM_MTH_TYP_CD": "2", "IVM_MTH_SBY_CD": "3",
             "GUA_FND_ITS_RT": Decimal("4.000"), "GUA_ITS_PER_RLE_CD": "0",
             "GUA_ITS_PER": 0, "ADD_GUA_PER_RLE_CD": " ", "HI_FND_VAL_PHA_NBR": None,
             "CUR_ITS_RT_SER_NBR": "ANICO1983  ", "CUR_ITS_RT": Decimal("6.000"),
             "ITS_PER_END_DT": date(2000, 12, 14)},
        ]

    def fetch_table(self, table):
        self.calls.append(table)
        return self.tables[table]

    def table_error(self, table):
        return self.errors.get(table, "")


def text(lines):
    return ["".join(run["text"] for run in line) for line in lines]


def tokens(pi, name):
    return [
        run for line in build_segment_55(pi) for run in line
        if run.get("field") == name
    ]


def metadata():
    path = Path(__file__).resolve().parents[1] / "suiteview" / "polview" / "data" / "policy_record_screens" / "seg_55.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_four_capture_rows_match_including_blanks_and_source_is_immutable():
    pi = Policy()
    original = deepcopy(pi.tables)
    lines = build_segment_55(pi)
    assert text(lines)[:5] == CAPTURE
    assert text(metadata()["lines"])[:5] == CAPTURE
    assert pi.tables == original
    assert pi.calls == list(TABLES)
    assert any("CK620 DISPLAY COMPLETE" in line for line in text(lines))
    assert all(len(line) <= 80 for line in text(lines)[1:5])


def test_fund_tabs_are_registered_and_dispatch_builds_the_live_55_screen():
    assert "55" in _SEGMENTS and "57" in _SEGMENTS
    assert _SEGMENTS == sorted(set(_SEGMENTS))
    screen = build_screen("55", Policy())
    assert screen["live"]
    assert text(screen["lines"])[:5] == CAPTURE


def test_absent_fund_segment_is_omitted():
    pi = Policy()
    pi.tables = {table: [] for table in TABLES}
    assert build_segment_55(pi) is None
    screen = build_screen("55", pi)
    assert screen is None


def test_unverified_fund_variant_surfaces_the_reason_in_the_viewer():
    pi = Policy()
    pi.tables[COMMON_TABLE][0]["FND_TYP_CD"] = "V"
    screen = build_screen("55", pi)
    assert not screen.get("live")
    assert "variable/unknown" in screen["live_error"]


def test_multiple_funds_are_joined_by_phase_and_fund_not_row_order():
    pi = Policy()
    for table in (COMMON_TABLE, FIXED_TABLE):
        base = deepcopy(pi.tables[table][1])
        pi.tables[table].extend([
            {**base, "COV_PHA_NBR": 10}, {**base, "COV_PHA_NBR": 2},
        ])
        pi.tables[table].reverse()
    pi.tables[FIXED_TABLE][0]["GUA_FND_ITS_RT"] = Decimal("2.125")
    pi.tables[FIXED_TABLE][1]["GUA_FND_ITS_RT"] = Decimal("9.500")
    assert [run["text"] for run in tokens(pi, "Fund Identification")] == ["GP", "U1", "U1", "U1"]
    assert [run["text"] for run in tokens(pi, "Coverage Phase")] == ["1", "1", "2", "10"]
    assert [run["text"] for run in tokens(pi, "Guaranteed Interest Rate")] == [".000", "4.000", "2.125", "9.500"]


@pytest.mark.parametrize("key,value", [
    ("COV_PHA_NBR", 2), ("FND_ID_CD", "XX"), ("CK_CMP_CD", "26"),
    ("CK_SYS_CD", "M"), ("TCH_POL_ID", "OTHER TEST"),
])
def test_fixed_join_never_crosses_any_part_of_the_composite_key(key, value):
    pi = Policy()
    pi.tables[FIXED_TABLE][1][key] = value
    with pytest.raises(ValueError, match="orphan"):
        build_segment_55(pi)


def test_null_numeric_slots_remain_distinct_from_stored_zero():
    pi = Policy()
    null_rate = tokens(pi, "Initial Interest Rate")[0]
    zero_rate = tokens(pi, "Guaranteed Interest Rate")[0]
    assert null_rate["text"] == zero_rate["text"] == ".000"
    assert null_rate["dim"] and "DB2 NULL" in null_rate["note"]
    assert not zero_rate.get("dim")
    null_high = tokens(pi, "High Phase")[1]
    zero_period = tokens(pi, "Guaranteed Interest Period")[1]
    assert null_high["text"] == zero_period["text"] == "0"
    assert null_high["dim"] and not zero_period.get("dim")


def test_null_flag_and_code_are_unknown_not_zero_or_blank():
    pi = Policy()
    pi.tables[COMMON_TABLE][0].update(ICP_ACY_IND=None, PNY_RLE_1_CD=None)
    assert tokens(pi, "Flag Byte A")[0]["text"] == "?"
    assert tokens(pi, "Flag Byte A")[0]["dim"]
    assert tokens(pi, "Penalties Rule 1")[0]["text"] == "?"
    assert tokens(pi, "Penalties Rule 1")[0]["dim"]


def test_live_flag_a_bits_are_individual_sources_and_only_reserved_bytes_are_examples():
    pi = Policy()
    pi.tables[COMMON_TABLE][1]["IDX_ANU_IND"] = "1"
    runs = tokens(pi, "Flag Byte A")
    assert "".join(run["text"] for run in runs) == "0010000100000101"
    for index, run in enumerate(runs):
        assert FLAG_COLUMNS[index % 8] in run["note"]
        assert not run.get("example")
    examples = {run["field"] for line in build_segment_55(pi) for run in line if run.get("example")}
    assert examples == {"Flag Byte B", "Flag Byte U"}


def test_dates_blank_strings_signed_rates_and_two_byte_high_phase():
    pi = Policy()
    pi.tables[COMMON_TABLE][0].update(
        LST_TRF_DT="2026-09-16", LST_TRF_TYP_CD="I",
        ANU_ASM_ITS_RT=Decimal("-0.125"),
    )
    pi.tables[FIXED_TABLE][0].update(HI_FND_VAL_PHA_NBR=300, ITS_PER_END_DT=None)
    assert tokens(pi, "Last Transfer Date")[0]["text"] == "09/16/2026"
    assert tokens(pi, "Last Transfer In/Out")[0]["text"] == "I"
    assert tokens(pi, "Assumed Interest Rate")[0]["text"] == "-.125"
    assert tokens(pi, "High Phase")[0]["text"] == "300"
    assert tokens(pi, "Current Interest Rates File Search Key")[0]["text"] == " " * 11
    assert tokens(pi, "Initial Interest Rate End Date")[0]["dim"]
    assert tokens(pi, "Initial Interest Rate End Date")[0]["text"] == "**/**/****"


@pytest.mark.parametrize("table", TABLES)
def test_every_table_error_is_loud_even_for_empty_tier_tables(table):
    pi = Policy()
    pi.errors[table] = "SELECT not authorized"
    with pytest.raises(ValueError, match=f"{table}.*SELECT not authorized"):
        build_segment_55(pi)


@pytest.mark.parametrize("table", [COMMON_TABLE, FIXED_TABLE])
def test_duplicate_control_keys_block_instead_of_arbitrarily_selecting_a_row(table):
    pi = Policy()
    pi.tables[table].append(deepcopy(pi.tables[table][0]))
    with pytest.raises(ValueError, match="duplicate"):
        build_segment_55(pi)


@pytest.mark.parametrize("table,column", [
    (COMMON_TABLE, "ANU_ASM_ITS_RT"), (COMMON_TABLE, "ICP_ACY_IND"),
    (FIXED_TABLE, "CUR_ITS_RT"), (FIXED_TABLE, "TIER_ITS_RT_NBR"),
])
def test_missing_columns_never_masquerade_as_null(table, column):
    pi = Policy()
    del pi.tables[table][0][column]
    with pytest.raises(ValueError, match=f"source column is missing: {table}.{column}"):
        build_segment_55(pi)


@pytest.mark.parametrize("table,column,value", [
    (COMMON_TABLE, "COV_PHA_NBR", None), (COMMON_TABLE, "COV_PHA_NBR", "1.5"),
    (COMMON_TABLE, "COV_PHA_NBR", 256), (COMMON_TABLE, "FND_ID_CD", ""),
    (COMMON_TABLE, "MIN_DUR", "1.5"), (COMMON_TABLE, "MIN_DUR", 1000),
    (COMMON_TABLE, "ANU_ASM_ITS_RT", "not a rate"), (COMMON_TABLE, "ANU_ASM_ITS_RT", "NaN"),
    (COMMON_TABLE, "ANU_ASM_ITS_RT", "1.0001"), (COMMON_TABLE, "ANU_ASM_ITS_RT", "100.000"),
    (COMMON_TABLE, "PNY_TBL_CD", "123"), (COMMON_TABLE, "LST_TRF_DT", "not a date"),
    (COMMON_TABLE, "ICP_ACY_IND", "2"), (FIXED_TABLE, "HI_FND_VAL_PHA_NBR", 65536),
    (FIXED_TABLE, "IVM_MTH_TYP_CD", None), (FIXED_TABLE, "IVM_MTH_SBY_CD", None),
    (FIXED_TABLE, "IVM_MTH_TYP_CD", "9"), (FIXED_TABLE, "TIER_ITS_RT_NBR", "garbage"),
    (FIXED_TABLE, "TIER_ITS_RT_NBR", "NaN"), (FIXED_TABLE, "TIER_ITS_RT_NBR", "0.5"),
    (FIXED_TABLE, "TIER_ITS_RT_NBR", 9), (FIXED_TABLE, "TIER_ITS_RT_NBR", -1),
])
def test_bad_values_do_not_round_truncate_or_turn_into_zero(table, column, value):
    pi = Policy()
    pi.tables[table][0][column] = value
    with pytest.raises(ValueError):
        build_segment_55(pi)


def test_missing_header_and_missing_fixed_extension_fail_explicitly():
    pi = Policy()
    pi.tables[COMMON_TABLE] = []
    with pytest.raises(ValueError, match="no LH_COV_IVM_FND_CTL"):
        build_segment_55(pi)
    pi = Policy()
    pi.tables[FIXED_TABLE].pop()
    with pytest.raises(ValueError, match="missing LH_COV_FXD_FND_CTL"):
        build_segment_55(pi)


@pytest.mark.parametrize("fund_type", ["V", "?", None])
def test_unverified_variable_or_unknown_fund_never_gets_a_fabricated_fixed_record(fund_type):
    pi = Policy()
    pi.tables[COMMON_TABLE][0]["FND_TYP_CD"] = fund_type
    with pytest.raises(ValueError, match="variable/unknown"):
        build_segment_55(pi)


@pytest.mark.parametrize("subtype", ["D", "T"])
def test_tier_method_blocks_even_when_tier_rows_are_missing(subtype):
    pi = Policy()
    pi.tables[FIXED_TABLE][0]["IVM_MTH_SBY_CD"] = subtype
    with pytest.raises(ValueError, match="tiered/duration"):
        build_segment_55(pi)


@pytest.mark.parametrize("table", TIER_TABLES)
def test_tier_rows_are_not_silently_discarded(table):
    pi = Policy()
    pi.tables[table].append(deepcopy(pi.tables[COMMON_TABLE][0]))
    with pytest.raises(ValueError, match="tiered/duration"):
        build_segment_55(pi)


def test_nonzero_tier_count_without_rows_is_not_an_ordinary_fixed_record():
    pi = Policy()
    pi.tables[FIXED_TABLE][0]["TIER_ITS_RT_NBR"] = 2
    with pytest.raises(ValueError, match="tiered/duration"):
        build_segment_55(pi)


def test_zero_tier_count_does_not_create_a_nonexistent_extension():
    pi = Policy()
    pi.tables[FIXED_TABLE][0]["TIER_ITS_RT_NBR"] = 0
    assert text(build_segment_55(pi))[:5] == CAPTURE


def test_hover_and_layout_mappings_share_correct_current_offsets_and_redefines():
    screen = metadata()
    runs = [run for line in build_segment_55(Policy()) for run in line if run.get("field")]
    assert {run["field"] for run in runs} <= screen["fields"].keys()
    specs = {spec["name"]: spec for spec in screen["field_specs"]}
    for table, definitions in ((COMMON_TABLE, COMMON_FIELDS), (FIXED_TABLE, FIXED_FIELDS)):
        for name, column, cobol, byte, _, _ in definitions:
            assert specs[name]["byte"] == byte
            assert specs[name]["db2"] == f"{table}.{column}"
            assert f"DB2: {table}.{column}" in screen["fields"][name]
            assert cobol in screen["layout_html"]
            assert f"{table}.{column}" in screen["layout_html"]
    assert specs["High Phase"]["byte"] == "60-61"
    assert specs["Current Interest Rates File Search Key"]["byte"] == "62-72"
    assert specs["Initial Interest Rate End Date"]["byte"] == "76-79"
    assert specs["Number of Interest Rate/Limit Pairs"]["byte"] == "80-81"
    assert specs["User Rule for guaranteed calculation"]["cobol"] == "FIFFGURL-USER-GUAR-RULE"
    assert "LH_AMT_TIERED_ITS.ITS_TIER_AMT" in screen["layout_html"]
    assert "LH_DUR_TIERED_ITS.ITS_TIER_DUR" in screen["layout_html"]
    assert "rendering guarded" in screen["layout_html"]
