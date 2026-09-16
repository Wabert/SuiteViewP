"""Live allocation sets, source mappings and the supplied UL045809 capture."""

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from suiteview.polview.models.policy_record_allocations import ENTRY_TABLE, HEADER_TABLE
from suiteview.polview.models.policy_record_builder import build_segment_lines
from suiteview.polview.ui.policy_record_viewer import build_screen, load_screen


class Policy:
    policy_number = "UL045809"
    region = "CKPR"
    company_name = "ANICO"

    def __init__(self):
        self.tables = {
            HEADER_TABLE: [{
                "FND_TRS_TYP_CD": "P", "FND_ALC_SEQ_NBR": 1, "ALC_SRC_CD": "1",
                "AUTOCLOS_PROC_IND": "0", "MTHLVRSY_PROC_IND": "0",
                "LST_ALC_CHG_DT": date(1984, 12, 15), "CRG_DED_ALC_EFF_DT": None,
                "SWP_FROM_FUND": "  ", "ALC_MTH_CD": " ",
            }],
            ENTRY_TABLE: [{
                "FND_ALC_TYP_CD": "P", "FND_ALC_SEQ_NBR": 1, "SEG_IDX_NBR": 1,
                "COV_PHA_NBR": 1, "FND_ID_CD": "U1", "FND_ALC_DIR_CD": " ",
                "FND_XCL_IND": " ", "ALC_VAL_TYP_CD": "P",
                "FND_ALC_UNT_QTY": Decimal("0.0000"), "FND_ALC_AMT": Decimal("0.00"),
                "FND_ALC_PCT": Decimal("100.00"),
            }],
        }
        self.errors = {}

    def fetch_table(self, table):
        return self.tables[table]

    def table_error(self, table):
        return self.errors.get(table, "")


def render(pi):
    return build_segment_lines("57", pi, load_screen("57"))


def tokens(lines, field):
    return [run for line in lines for run in line if run.get("field") == field]


def values(lines, field):
    return [run["text"] for run in tokens(lines, field)]


def test_live_body_matches_capture_and_does_not_mutate_sources():
    pi = Policy()
    original = deepcopy(pi.tables)
    text = ["".join(run["text"] for run in line) for line in render(pi)]
    assert text[:2] == [
        "  6257, UL045809",
        "  57 0046 10000000 00000000 P 1 12/15/1984      1     1 U1 P 100.00",
    ]
    assert pi.tables == original
    assert build_screen("57", pi)["live"]


def test_multiple_effective_sets_sort_by_type_sequence_and_entries_by_segment_index():
    pi = Policy()
    header = pi.tables[HEADER_TABLE][0]
    entry = pi.tables[ENTRY_TABLE][0]
    pi.tables[HEADER_TABLE] = [
        {**header, "FND_ALC_SEQ_NBR": 10, "LST_ALC_CHG_DT": "2026-03-02"},
        {**header, "FND_TRS_TYP_CD": "C", "FND_ALC_SEQ_NBR": 2,
         "LST_ALC_CHG_DT": None, "CRG_DED_ALC_EFF_DT": "2026-02-01", "ALC_MTH_CD": "1"},
        {**header, "FND_ALC_SEQ_NBR": 2},
    ]
    pi.tables[ENTRY_TABLE] = [
        {**entry, "FND_ALC_TYP_CD": "C", "FND_ALC_SEQ_NBR": 2,
         "SEG_IDX_NBR": 2, "FND_ID_CD": "IX"},
        {**entry, "FND_ALC_SEQ_NBR": 10, "FND_ID_CD": "GP"},
        {**entry, "FND_ALC_TYP_CD": "C", "FND_ALC_SEQ_NBR": 2,
         "SEG_IDX_NBR": 1, "FND_ID_CD": "SW"},
        {**entry, "FND_ALC_SEQ_NBR": 2},
    ]
    lines = render(pi)
    assert values(lines, "Segment Type") == ["C", "P", "P"]
    assert values(lines, "Type Sequence") == ["2", "2", "10"]
    assert values(lines, "Number of Allocations") == ["2", "1", "1"]
    assert values(lines, "Segment Length") == ["0062", "0046", "0046"]
    assert values(lines, "Allocation Fund Identification") == ["SW", "IX", "U1", "GP"]
    assert values(lines, "Last Allocation Change Date") == [
        "02/01/2026", "12/15/1984", "03/02/2026",
    ]
    assert "CRG_DED_ALC_EFF_DT" in tokens(lines, "Last Allocation Change Date")[0]["note"]


@pytest.mark.parametrize("kind,column,value,field,expected", [
    ("P", "FND_ALC_PCT", "0.00", "Fund Allocation Percent", ".00"),
    ("P", "FND_ALC_PCT", "50.25", "Fund Allocation Percent", "50.25"),
    ("D", "FND_ALC_AMT", "-1234.56", "Fund Allocation Dollars", "-1234.56"),
    ("U", "FND_ALC_UNT_QTY", "123456789.1234", "Fund Allocation Units", "123456789.1234"),
])
def test_value_redefines_use_the_correct_db_column_and_scale(kind, column, value, field, expected):
    pi = Policy()
    pi.tables[ENTRY_TABLE][0].update({"ALC_VAL_TYP_CD": kind, column: Decimal(value)})
    lines = render(pi)
    assert values(lines, field) == [expected]
    assert column in tokens(lines, field)[0]["note"]
    assert not tokens(lines, field)[0].get("dim")
    assert values(lines, "Segment Length") == ["0046"]


@pytest.mark.parametrize("kind,column,field", [
    ("P", "FND_ALC_PCT", "Fund Allocation Percent"),
    ("D", "FND_ALC_AMT", "Fund Allocation Dollars"),
    ("U", "FND_ALC_UNT_QTY", "Fund Allocation Units"),
])
def test_null_amount_is_not_zero(kind, column, field):
    pi = Policy()
    pi.tables[ENTRY_TABLE][0].update({"ALC_VAL_TYP_CD": kind, column: None})
    token = tokens(render(pi), field)[0]
    assert set(token["text"]) == {"?"}
    assert token["dim"]
    assert "DB2 NULL" in token["note"]


def test_low_values_and_null_characters_are_annotated_not_rendered_as_controls():
    pi = Policy()
    pi.tables[HEADER_TABLE][0].update({
        "SWP_FROM_FUND": "\x00\x00", "ALC_MTH_CD": None, "LST_ALC_CHG_DT": None,
    })
    lines = render(pi)
    for field in ("Sweep From Fund", "Allocation Method", "Last Allocation Change Date"):
        assert tokens(lines, field)[0]["dim"]
    assert "low-values" in tokens(lines, "Sweep From Fund")[0]["note"]
    assert values(lines, "Last Allocation Change Date") == ["**/**/****"]
    assert "\x00" not in "".join(run["text"] for line in lines for run in line)


def test_known_flags_are_live_and_only_unmapped_bits_are_examples():
    pi = Policy()
    pi.tables[HEADER_TABLE][0].update({
        "ALC_SRC_CD": None, "AUTOCLOS_PROC_IND": "1", "MTHLVRSY_PROC_IND": "1",
    })
    bits = tokens(render(pi), "Flag Byte A")
    assert [run["text"] for run in bits] == ["?", "1", "1", "00000"]
    assert bits[0]["dim"]
    assert [run.get("example", False) for run in bits] == [False, False, False, True]


@pytest.mark.parametrize("table,column,value", [
    (HEADER_TABLE, "FND_TRS_TYP_CD", None),
    (HEADER_TABLE, "FND_ALC_SEQ_NBR", "1.5"),
    (HEADER_TABLE, "ALC_SRC_CD", "X"),
    (HEADER_TABLE, "LST_ALC_CHG_DT", "invalid date"),
    (HEADER_TABLE, "SWP_FROM_FUND", "abc"),
    (ENTRY_TABLE, "SEG_IDX_NBR", -1),
    (ENTRY_TABLE, "SEG_IDX_NBR", 100),
    (ENTRY_TABLE, "FND_ID_CD", "\x00\x00"),
    (ENTRY_TABLE, "COV_PHA_NBR", 256),
    (ENTRY_TABLE, "ALC_VAL_TYP_CD", "X"),
    (ENTRY_TABLE, "FND_ALC_DIR_CD", "X"),
    (ENTRY_TABLE, "FND_XCL_IND", "2"),
    (ENTRY_TABLE, "FND_ALC_PCT", "NaN"),
    (ENTRY_TABLE, "FND_ALC_PCT", "1.001"),
    (ENTRY_TABLE, "FND_ALC_PCT", "1000.00"),
])
def test_bad_source_data_never_silently_rounds_or_looks_live(table, column, value):
    pi = Policy()
    pi.tables[table][0][column] = value
    with pytest.raises(ValueError):
        render(pi)
    screen = build_screen("57", pi)
    assert not screen.get("live")
    assert screen["live_error"]


@pytest.mark.parametrize("table", [HEADER_TABLE, ENTRY_TABLE])
def test_db_errors_are_not_mistaken_for_absent_segments(table):
    pi = Policy()
    pi.errors[table] = "Permission denied"
    with pytest.raises(ValueError, match="Permission denied"):
        render(pi)


def test_missing_columns_are_explicit_failures():
    pi = Policy()
    del pi.tables[ENTRY_TABLE][0]["FND_ALC_PCT"]
    with pytest.raises(ValueError, match="source column is missing: FND_ALC_PCT"):
        render(pi)


@pytest.mark.parametrize("table", [HEADER_TABLE, ENTRY_TABLE])
def test_duplicate_source_keys_are_not_arbitrarily_selected(table):
    pi = Policy()
    pi.tables[table].append(dict(pi.tables[table][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        render(pi)


def test_orphan_entries_and_gaps_are_errors():
    pi = Policy()
    pi.tables[HEADER_TABLE] = []
    with pytest.raises(ValueError, match="no matching set"):
        render(pi)
    pi = Policy()
    pi.tables[ENTRY_TABLE][0]["SEG_IDX_NBR"] = 2
    with pytest.raises(ValueError, match="Non-contiguous"):
        render(pi)


def test_empty_record_is_omitted_and_empty_set_has_zero_count():
    pi = Policy()
    pi.tables[ENTRY_TABLE] = []
    assert values(render(pi), "Number of Allocations") == ["0"]
    assert values(render(pi), "Segment Length") == ["0030"]
    pi.tables[HEADER_TABLE] = []
    assert render(pi) is None
    assert build_screen("57", pi) is None


def test_every_live_field_has_metadata_and_byte_offsets_match_the_record_diagram():
    screen = load_screen("57")
    specs = {item["name"]: item for item in screen["field_specs"]}
    assert specs["Number of Allocations"]["byte"] == "29-30"
    assert specs["Number of Allocations"]["db2"] is None
    assert specs["Allocation Filler"]["byte"] == "31-33"
    assert specs["Allocation From/To Indicator"]["byte"] == "34"
    assert specs["Fund Allocation Units"]["byte"] == "40-46"
    assert specs["Fund Allocation Dollars"]["byte"] == "40-45"
    assert specs["Fund Allocation Percent"]["byte"] == "40-42"
    assert specs["Segment Type"]["db2"] == f"{HEADER_TABLE}.FND_TRS_TYP_CD"
    assert "CRG_DED_ALC_EFF_DT" in screen["layout_html"]
    assert "FALALLOM-ALLOCATION-METHOD" in screen["layout_html"]
    fields = {run["field"] for line in render(Policy()) for run in line if run.get("field")}
    assert fields <= set(screen["fields"])
