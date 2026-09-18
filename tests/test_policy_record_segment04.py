"""6204 capture parity, complete benefit joins, live flags and explicit failures."""

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from suiteview.polview.models.policy_record_benefits import (
    DENY_FIELD, EXTENSION_TABLE, FLAGS, KEY_COLUMNS, PPA_FIELD, REQUEST_TABLE,
    TABLE, TABLES, build_segment_04,
)
from suiteview.polview.ui.policy_record_viewer import build_screen, load_screen
from tools.policyrecord.build_seg04_screen import build_document


CAPTURE = [
    "  6204, U0566833",
    "  04 0081 00000000 00000100 1 A 0 00 1 05/28/2058 1 0 150 48 2 05/28/2006",
    "          05/28/2058 1.00 .00 0 1000.000 1000.00 05/28/2058 X PPA       4.500 N",
    "  04 0081 00001000 10000000 1 3 9 00 1 05/28/2018 0 1 150 48 2 05/28/2006",
    "          05/28/2018 1.00 .01 0 1000.000 1000.00 05/28/2018   ULDW91    N",
]


class Policy:
    policy_number = "U0566833"
    region = "CKPR"
    company_name = "ANICO"

    def __init__(self):
        self.errors = {}
        common = {
            "TCH_POL_ID": "U0566833 TEST", "CK_CMP_CD": "01", "CK_SYS_CD": "I",
            "COV_PHA_NBR": 1, "SPM_BNF_TYP_CD": "A", "SPM_BNF_SBY_CD": "0",
            "PRS_CD": "00", "PRS_SEQ_NBR": 1, "BNF_STA_CD": "1",
            **{column: "0" for bits in FLAGS.values() for column, _ in bits},
            "IHT_BNF_IND": "1", "BNF_CEA_DT": date(2058, 5, 28),
            "COL_ICE_FQY_CD": " ", "BNF_COM_CD": "0", "RES_MTH_PLN_CD": "150",
            "BNF_ISS_AGE": 48, "AGE_SRC_CD": "2", "BNF_ISS_DT": date(2006, 5, 28),
            "BNF_PAY_UP_DT": date(2058, 5, 28), "BNF_RT_FCT": Decimal("1.00"),
            "BNF_ANN_PPU_AMT": Decimal("0.00"), "BNF_PRM_CLC_PCT": None,
            "BNF_UNT_QTY": Decimal("1000.000"), "BNF_VPU_AMT": Decimal("1000.00"),
            "BNF_OGN_CEA_DT": date(2058, 5, 28), "RNL_RT_IND": "0",
            "BNF_FRM_NBR": "PPA      ", "IFT_PCT": None, "CPI_ADJ_REJ_NBR": None,
            "OPT_DT": None, "PRT_PCT": Decimal("4.50"),
        }
        waiver = {
            **common, "SPM_BNF_TYP_CD": "3", "SPM_BNF_SBY_CD": "9", "BNF_STA_CD": "0",
            "PW_PCT_IND": "1", "UNT_REQ_IND": "1", "IHT_BNF_IND": "0",
            "BNF_CEA_DT": date(2018, 5, 28), "BNF_COM_CD": "1",
            "BNF_PAY_UP_DT": date(2018, 5, 28), "BNF_ANN_PPU_AMT": Decimal(".01"),
            "BNF_OGN_CEA_DT": date(2018, 5, 28), "RNL_RT_IND": "1",
            "BNF_FRM_NBR": "ULDW91   ", "PRT_PCT": None,
        }
        self.tables = {
            REQUEST_TABLE: [], TABLE: [common, waiver],
            EXTENSION_TABLE: [
                {**{column: row[column] for column in KEY_COLUMNS},
                 "AUTO_RATE_DENY": "N", "BENEFIT_FREQ": " ", "ABR_QUAL_IND": " "}
                for row in (common, waiver)
            ],
        }

    def fetch_table(self, table):
        return self.tables[table]

    def table_error(self, table):
        return self.errors.get(table, "")


def text(lines):
    return ["".join(run["text"] for run in line) for line in lines]


def tokens(pi, name):
    return [run for line in build_segment_04(pi) for run in line if run.get("field") == name]


def test_capture_matches_all_four_lines_including_blank_slots_and_source_is_immutable():
    pi = Policy()
    original = deepcopy(pi.tables)
    screen = build_screen("04", pi)
    assert screen["live"]
    assert text(screen["lines"])[:5] == CAPTURE
    assert pi.tables == original
    assert all(len(line) <= 80 for line in text(screen["lines"])[1:5])
    assert "CKPR-ANICO" in "".join(text(screen["lines"]))
    assert not any(run.get("example") for line in screen["lines"] for run in line)
    assert {run["field"] for line in screen["lines"] for run in line if run.get("field")} <= screen["fields"].keys()


def test_metadata_matches_generator_and_contains_no_captured_policy_values():
    metadata = load_screen("04")
    assert metadata == build_document()
    assert metadata["lines"] == []
    assert "COBOL: FSBBAP-ANNUAL-PREM-PER-UNIT" in metadata["fields"]["Annual Premium per Unit"]
    assert "DB2: LH_SPM_BNF.BNF_ANN_PPU_AMT" in metadata["fields"]["Annual Premium per Unit"]
    assert "81 bytes" in " ".join(metadata["fields"]["Segment Length"])


def test_absent_segment_is_omitted():
    pi = Policy()
    pi.tables = {table: [] for table in TABLES}
    assert build_segment_04(pi) is None
    assert build_screen("04", pi) is None


def test_extensions_match_full_identity_not_row_position_and_keep_source_order_per_phase():
    pi = Policy()
    for table in (TABLE, EXTENSION_TABLE):
        row = deepcopy(pi.tables[table][0])
        pi.tables[table].extend([{**row, "COV_PHA_NBR": 10}, {**row, "COV_PHA_NBR": 2}])
    pi.tables[EXTENSION_TABLE][1]["AUTO_RATE_DENY"] = "Y"
    pi.tables[EXTENSION_TABLE].reverse()
    assert [run["text"] for run in tokens(pi, "Coverage Phase")] == ["1", "1", "2", "10"]
    assert [run["text"] for run in tokens(pi, "Benefit Type")] == ["A", "3", "A", "A"]
    assert [run["text"] for run in tokens(pi, DENY_FIELD[0])] == ["N", "Y", "N", "N"]


@pytest.mark.parametrize("column,value", [
    ("TCH_POL_ID", "OTHER TEST"), ("CK_CMP_CD", "26"), ("CK_SYS_CD", "M"),
    ("COV_PHA_NBR", 2), ("SPM_BNF_TYP_CD", "B"), ("SPM_BNF_SBY_CD", "2"),
    ("PRS_CD", "01"), ("PRS_SEQ_NBR", 2), ("BNF_STA_CD", "2"),
    ("BNF_ISS_DT", date(2007, 5, 28)),
])
def test_extension_cannot_cross_any_part_of_benefit_key(column, value):
    pi = Policy()
    pi.tables[EXTENSION_TABLE][0][column] = value
    with pytest.raises(ValueError, match="orphan"):
        build_segment_04(pi)


@pytest.mark.parametrize("table", [TABLE, EXTENSION_TABLE])
def test_duplicate_keys_are_explicit_errors(table):
    pi = Policy()
    pi.tables[table].append(deepcopy(pi.tables[table][0]))
    with pytest.raises(ValueError, match="duplicate"):
        build_segment_04(pi)


def test_dates_and_numeric_key_representations_join_consistently():
    pi = Policy()
    pi.tables[EXTENSION_TABLE][0].update(BNF_ISS_DT="2006-05-28", COV_PHA_NBR=Decimal("1.0"))
    assert text(build_segment_04(pi))[:5] == CAPTURE


def test_missing_extension_is_unavailable_not_assumed_n():
    pi = Policy()
    pi.tables[EXTENSION_TABLE].pop(0)
    deny = tokens(pi, DENY_FIELD[0])[0]
    assert deny["text"] == "?" and deny["dim"]
    assert "No matching TH_SPM_BNF row" in deny["note"]


def test_null_numeric_zero_and_missing_are_distinct():
    pi = Policy()
    null = tokens(pi, "Premium Calculation Percent")[0]
    pi.tables[TABLE][0]["BNF_PRM_CLC_PCT"] = 0
    zero = tokens(pi, "Premium Calculation Percent")[0]
    assert null["text"] == zero["text"] == "0"
    assert null["dim"] and "DB2 NULL" in null["note"] and not zero.get("dim")
    pi.tables[TABLE][0].update(BNF_UNT_QTY=0, BNF_VPU_AMT=0, BNF_ISS_AGE=0, PRT_PCT=0)
    assert tokens(pi, "Number of Units")[0]["text"] == ".000"
    assert tokens(pi, "Value per Unit")[0]["text"] == ".00"
    assert tokens(pi, "Issue Age")[0]["text"] == "0"
    assert tokens(pi, PPA_FIELD[0])[0]["text"] == ".000"
    del pi.tables[TABLE][0]["BNF_VPU_AMT"]
    with pytest.raises(ValueError, match="source column is missing"):
        build_segment_04(pi)


@pytest.mark.parametrize("name", FLAGS)
def test_every_flag_bit_is_live_and_null_is_unknown(name):
    pi = Policy()
    for bit, (column, _) in enumerate(FLAGS[name]):
        for flag_column, _ in FLAGS[name]:
            pi.tables[TABLE][0][flag_column] = "0"
        pi.tables[TABLE][0][column] = "1"
        values = tokens(pi, name)[:8]
        assert "".join(run["text"] for run in values) == "0" * bit + "1" + "0" * (7 - bit)
        assert column in values[bit]["note"]
        assert not any(run.get("example") or run.get("dim") for run in values)
    pi.tables[TABLE][0][FLAGS[name][0][0]] = None
    assert tokens(pi, name)[0]["text"] == "?"
    assert tokens(pi, name)[0]["dim"]


def test_renewable_indicator_factor_precision_negative_values_and_sentinel_dates():
    pi = Policy()
    pi.tables[TABLE][0].update(
        BNF_RT_FCT=Decimal("2.50"), BNF_ANN_PPU_AMT=Decimal("-.01"),
        BNF_PAY_UP_DT=date(9999, 12, 31), BNF_OGN_CEA_DT=None,
    )
    assert [run["text"] for run in tokens(pi, "Renewable Rate Indicator")] == ["X", " "]
    assert tokens(pi, "Rating Factor")[0]["text"] == "2.50"
    assert tokens(pi, "Annual Premium per Unit")[0]["text"] == "-.01"
    assert tokens(pi, "Pay-Up Date")[0]["text"] == "**/**/****"
    assert tokens(pi, "Original Cease Date")[0]["dim"]


def test_cola_use_code_reads_frequency_instead_of_status():
    pi = Policy()
    for table in (TABLE, EXTENSION_TABLE):
        pi.tables[table][0]["SPM_BNF_TYP_CD"] = "U"
    pi.tables[TABLE][0].update(PRT_PCT=None, COL_ICE_FQY_CD="2")
    use = tokens(pi, "Use Code")[0]
    assert use["text"] == "2" and "COL_ICE_FQY_CD" in use["note"]


@pytest.mark.parametrize("column,value", [
    ("BNF_RT_FCT", "1.001"), ("BNF_VPU_AMT", "NaN"),
    ("BNF_UNT_QTY", "1000000"), ("BNF_ISS_AGE", "1.5"),
    ("RNL_RT_IND", "X"), ("BNF_FRM_NBR", "TOO LONG FORM"),
    ("BNF_FRM_NBR", "NEW\nLINE"), ("MAT_EXTN_IND", "Y"),
    ("BNF_PAY_UP_DT", "not-a-date"),
    ("COV_PHA_NBR", "NaN"), ("PRS_SEQ_NBR", "invalid"), ("BNF_ISS_DT", "not-a-date"),
])
def test_invalid_data_is_never_rounded_or_replaced_with_a_sample(column, value):
    pi = Policy()
    pi.tables[TABLE][0][column] = value
    screen = build_screen("04", pi)
    assert column in screen["live_error"]
    assert not screen.get("live") and screen["lines"] == []


@pytest.mark.parametrize("table,column,value", [
    (TABLE, "IFT_PCT", Decimal("5.00")), (TABLE, "CPI_ADJ_REJ_NBR", 1),
    (TABLE, "OPT_DT", date(2030, 1, 1)),
    (EXTENSION_TABLE, "BENEFIT_FREQ", "M"), (EXTENSION_TABLE, "ABR_QUAL_IND", "Y"),
])
def test_unverified_variants_are_explicit_not_silently_discarded(table, column, value):
    pi = Policy()
    pi.tables[table][0][column] = value
    screen = build_screen("04", pi)
    assert column in screen["live_error"] and screen["lines"] == []


def test_all_coverage_requests_and_orphan_extensions_are_not_assumed_absent():
    pi = Policy()
    pi.tables = {table: [] for table in TABLES}
    pi.tables[REQUEST_TABLE] = [{"request": "unverified"}]
    assert "all-coverage" in build_screen("04", pi)["live_error"]
    pi = Policy()
    pi.tables[TABLE] = []
    assert "orphan" in build_screen("04", pi)["live_error"]


@pytest.mark.parametrize("table,column", [
    (TABLE, "BNF_ISS_DT"), (EXTENSION_TABLE, "BNF_STA_CD"),
    (TABLE, "IF_POL_IND"), (EXTENSION_TABLE, "AUTO_RATE_DENY"),
])
def test_missing_columns_are_named_in_errors(table, column):
    pi = Policy()
    del pi.tables[table][0][column]
    screen = build_screen("04", pi)
    assert table in screen["live_error"] and column in screen["live_error"]


@pytest.mark.parametrize("table", TABLES)
def test_db_errors_remain_visible(table):
    pi = Policy()
    pi.errors[table] = "SELECT denied"
    screen = build_screen("04", pi)
    assert table in screen["live_error"] and "SELECT denied" in screen["live_error"]
    assert screen["lines"] == []
