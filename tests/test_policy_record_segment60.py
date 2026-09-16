"""Live Segment 60 regression against the supplied UL045809 screen."""

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from suiteview.polview.models.policy_record_builder import build_segment_lines
from suiteview.polview.ui.policy_record_viewer import build_screen, load_screen


class Policy:
    policy_number = "UL045809"
    region = "CKPR"
    company_name = "ANICO"

    def __init__(self):
        self.tables = {
            "LH_POL_TOTALS": [{
                "TOT_REG_PRM_AMT": Decimal("46726.00"),
                "TOT_ADD_PRM_AMT": Decimal("1365.25"), "TOT_ADD_PRM_QTY": 3,
                "TOT_PRM_LD_AMT": Decimal("4458.28"),
                "HI_YR_TOT_PRM_AMT": Decimal("2316.00"),
                "TOT_PRM_TAX_AMT": Decimal("0.00"), "TOT_TAX_PRM_AMT": Decimal("0.00"),
                "TOT_WTD_AMT": Decimal("13987.30"),
                "TOT_WTD_CRG_AMT": Decimal("0.00"), "TOT_WTD_QTY": 3,
                "POL_CST_BSS_AMT": Decimal("34103.95"),
                "ANU_ITS_ICM_AMT": None, "ANU_CST_BSS_AMT": None,
                "LST_CRG_FRE_WTD_DT": date(9999, 12, 31),
                "LST_MVA_FRE_WTD_DT": date(9999, 12, 31),
                "MVA_CSV_AMT": None, "TOT_FRE_WTD_AMT": Decimal("0.00"),
                "MO_ADD_PMT_QTY": 0, "TOT_RED_FEE_AMT": None,
                "TOT_FRS_YR_PRM_AMT": None, "TOT_FRE_WTD_PCT": None,
                "TOT_LTC_CST_OF_INS": None,
            }],
            "LH_MO_ADD_PMT": [],
        }
        self.errors = {}

    def fetch_table(self, table):
        return self.tables[table]

    def table_error(self, table):
        return self.errors.get(table, "")


def render(pi):
    return build_segment_lines("60", pi, load_screen("60"))


def token_map(lines):
    return {run["field"]: run for line in lines for run in line if run.get("field")}


def test_body_matches_all_three_captured_rows():
    pi = Policy()
    original = deepcopy(pi.tables)
    text = ["".join(run["text"] for run in line) for line in render(pi)]
    assert text[:4] == [
        "  6260, UL045809",
        "  60 0139 00000000 00000000 46726.00 1365.25 3 4458.28 2316.00 .00 .00 .00",
        "          13987.30 .00 3 34103.95 .00 .00 **/**/**** **/**/**** .00 .00 .00 .00",
        "          .00 0",
    ]
    assert pi.tables == original
    assert build_screen("60", pi)["live"] is True


def test_null_amounts_match_screen_but_remain_distinct_from_stored_zero():
    tokens = token_map(render(Policy()))
    null = tokens["MVA Amount"]
    zero = tokens["Total Withdrawal Charges"]
    assert null["text"] == zero["text"] == ".00"
    assert null["dim"] is True
    assert "DB2 NULL" in null["note"]
    assert not zero.get("dim")
    assert "DB2 NULL" not in zero["note"]


def test_reserved_flags_are_explicit_examples_not_claimed_as_db2_values():
    tokens = token_map(render(Policy()))
    assert {name for name, token in tokens.items() if token.get("example")} == {
        "Flag Byte A", "User Flag Byte",
    }


def test_every_field_has_hover_and_current_layout_has_ltc():
    screen = load_screen("60")
    tokens = token_map(render(Policy()))
    assert set(tokens) <= set(screen["fields"])
    assert "TOT_LTC_CST_OF_INS" in tokens["LTC Cost of Insurance Since Issue"]["note"]
    specs = {spec["name"]: spec for spec in screen["field_specs"]}
    assert specs["LTC Cost of Insurance Since Issue"]["byte"] == "112-117"
    assert specs["Used Accumulators"]["byte"] == "139"
    assert specs["Additional Payments by Month"]["byte"] == "140-211"
    assert tokens["Used Accumulators"]["text"] == "0"


def test_dates_and_negative_amounts_retain_source_values():
    pi = Policy()
    pi.tables["LH_POL_TOTALS"][0].update({
        "LST_CRG_FRE_WTD_DT": "2026-08-05", "LST_MVA_FRE_WTD_DT": None,
        "ANU_CST_BSS_AMT": Decimal("-123.45"),
    })
    tokens = token_map(render(pi))
    assert tokens["Last Charge Free Withdrawal Date"]["text"] == "08/05/2026"
    assert tokens["Last MVA Free Withdrawal Date"]["text"] == "**/**/****"
    assert tokens["Last MVA Free Withdrawal Date"]["dim"]
    assert tokens["Policy Net (POST TEFRA) Cost Basis"]["text"] == "-123.45"


@pytest.mark.parametrize("column,value", [
    ("TOT_ADD_PRM_QTY", "3.5"), ("TOT_REG_PRM_AMT", "1.001"),
    ("TOT_REG_PRM_AMT", "not money"), ("TOT_REG_PRM_AMT", "NaN"),
    ("LST_CRG_FRE_WTD_DT", "not a date"),
])
def test_bad_values_never_silently_round_or_become_zero(column, value):
    pi = Policy()
    pi.tables["LH_POL_TOTALS"][0][column] = value
    with pytest.raises(ValueError):
        render(pi)


def test_missing_column_blocks_live_screen_with_explicit_error():
    pi = Policy()
    del pi.tables["LH_POL_TOTALS"][0]["TOT_LTC_CST_OF_INS"]
    with pytest.raises(ValueError, match="source column is missing"):
        render(pi)
    screen = build_screen("60", pi)
    assert not screen.get("live")
    assert "TOT_LTC_CST_OF_INS" in screen["live_error"]


def test_table_error_is_not_an_empty_optional_array():
    pi = Policy()
    pi.errors["LH_MO_ADD_PMT"] = "SELECT not authorized"
    with pytest.raises(ValueError, match="LH_MO_ADD_PMT.*SELECT not authorized"):
        render(pi)


def test_multiple_totals_rows_are_not_arbitrarily_selected():
    pi = Policy()
    pi.tables["LH_POL_TOTALS"].append(dict(pi.tables["LH_POL_TOTALS"][0]))
    with pytest.raises(ValueError, match="exactly one"):
        render(pi)


def test_absent_segment_is_omitted():
    pi = Policy()
    pi.tables["LH_POL_TOTALS"] = []
    assert render(pi) is None
    assert build_screen("60", pi) is None


@pytest.mark.parametrize("count,monthly", [
    (1, []), (0, [{"MO_SEQ_NBR": 1, "MO_ADD_PRM_AMT": 0}]), (None, []),
])
def test_unverified_monthly_extension_does_not_invent_a_counter(count, monthly):
    pi = Policy()
    pi.tables["LH_POL_TOTALS"][0]["MO_ADD_PMT_QTY"] = count
    pi.tables["LH_MO_ADD_PMT"] = monthly
    with pytest.raises(ValueError, match="monthly"):
        render(pi)
