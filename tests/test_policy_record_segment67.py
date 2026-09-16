"""Segment 67 regressions against the UL045809 CyberLife capture."""

from copy import deepcopy
from decimal import Decimal

import pytest

from suiteview.polview.models.policy_record_builder import (
    _packed_decimal, build_segment_lines,
)
from suiteview.polview.ui.policy_record_viewer import (
    PolicyRecordViewerWindow, build_screen, load_screen,
)


KEY = {"COV_PHA_NBR": 1, "PRS_CD": "00", "PRS_SEQ_NBR": 1}


class Policy:
    policy_number = "UL045809"
    region = "CKPR"
    company_name = "ANICO"

    def __init__(self):
        self.tables = {
            "LH_COV_INS_RNL_PER": [{
                **KEY, "PLN_DES_SER_CD": "1U130M29   ", "RENEWABLE_PRM_CD": "C",
            }],
            "LH_COV_INS_RNL_RT": [
                {
                    **KEY, "SEG_IDX_NBR": index, "PRM_RT_TYP_CD": kind,
                    "RT_SEX_CD": "1", "RT_CLS_CD": "A", "RT_BAN_CD": band,
                    "JT_INS_IND": "0", "RNL_RT": Decimal(rate),
                    "DTH_BNF_PLN_OPT_CD": None,
                }
                for index, kind, band, rate in (
                    (1, "C", "A", "337971"), (2, "C", "B", "282184"),
                    (5, "M", "A", "6430"), (6, "M", "B", "6430"),
                    (3, "T", "A", "6430"), (4, "T", "B", "6430"),
                )
            ],
            "LH_COV_INS_GDL_PRM": [
                {
                    **KEY, "SEG_IDX_NBR": index, "PRM_RT_TYP_CD": kind,
                    "RT_SEX_CD": "\x00", "RT_CLS_CD": "\x00",
                    "GDL_PRM_AMT": Decimal(amount),
                    "GDL_PRM_UNT_QTY": Decimal(units),
                    "SYS_CLC_PRM_IND": "1", "DTH_BNF_PLN_OPT_CD": None,
                }
                for index, kind, amount, units in (
                    (7, "A", "0.00", "0.000"), (8, "S", "-21949.14", "-2194.914"),
                )
            ],
        }
        self.errors = {}

    def fetch_table(self, table):
        return self.tables.get(table, [])

    def table_error(self, table):
        return self.errors.get(table, "")


def render(pi):
    return build_segment_lines("67", pi, load_screen("67"))


def fields(lines, name):
    return [
        run for line in lines for run in line
        if run.get("field") == name
    ]


def test_live_screen_and_source_rows_are_not_mutated():
    pi = Policy()
    original = deepcopy(pi.tables)
    screen = build_screen("67", pi)
    assert screen["live"] is True
    assert pi.tables == original
    assert "UL045809" in "".join(run["text"] for run in screen["lines"][0])
    assert not any(run.get("example") for line in screen["lines"] for run in line)


def test_every_live_field_has_a_hover_mapping():
    screen = load_screen("67")
    for line in render(Policy()):
        for run in line:
            if run.get("field"):
                assert run["field"] in screen["fields"]


def test_body_matches_all_three_captured_rows():
    text = ["".join(run["text"] for run in line) for line in render(Policy())]
    assert text[:4] == [
        "  6267, UL045809",
        "  67 0110 1 1U130M29    C 00 1 8 C * * 1AA 000337971C "
        "C * * 1AB 000282184C T * *",
        "          1AA 000006430C T * * 1AB 000006430C M * * 1AA "
        "000006430C M * * 1AB",
        "          000006430C A        00000000000C S        00002194914D",
    ]
    assert fields(render(Policy()), "Segment Length")[0]["text"] == "0110"
    assert fields(render(Policy()), "Number of Rate Segments")[0]["text"] == "8"


def test_indexes_not_table_order_determine_display_order():
    pi = Policy()
    baseline = render(pi)
    for rows in pi.tables.values():
        rows.reverse()
    assert render(pi) == baseline
    assert [run["text"] for run in fields(baseline, "Rate Type Code")] == [
        "C", "C", "T", "T", "M", "M", "A", "S",
    ]


def test_phase_person_and_sequence_each_identify_a_separate_period():
    pi = Policy()
    period = deepcopy(pi.tables["LH_COV_INS_RNL_PER"][0])
    rate = deepcopy(pi.tables["LH_COV_INS_RNL_RT"][0])
    for phase, person, sequence in ((2, "00", 1), (1, "01", 1), (1, "00", 2)):
        key = {"COV_PHA_NBR": phase, "PRS_CD": person, "PRS_SEQ_NBR": sequence}
        pi.tables["LH_COV_INS_RNL_PER"].append({**period, **key})
        pi.tables["LH_COV_INS_RNL_RT"].append({**rate, **key})
    lines = render(pi)
    assert [run["text"] for run in fields(lines, "Segment Length")] == [
        "0110", "0033", "0033", "0033",
    ]
    assert [run["text"] for run in fields(lines, "Phase Code")] == ["1", "1", "1", "2"]
    assert [run["text"] for run in fields(lines, "Person Code")] == ["00", "00", "01", "00"]
    assert [run["text"] for run in fields(lines, "Person Sequence")] == ["1", "2", "1", "1"]


def test_benefit_and_extra_entries_share_the_same_count_and_index_order():
    pi = Policy()
    pi.tables["LH_SST_XTR_RNL_RT"] = [{
        **KEY, "SEG_IDX_NBR": 9, "PRM_RT_TYP_CD": "E",
        "SST_XTR_RT_TBL_CD": "B ", "SST_XTR_PCT_IND": "1",
        "RT_SEX_CD": "P", "RT_CLS_CD": "C", "RT_BAN_CD": "T",
        "SST_XTR_PCT": Decimal("1.50"), "SST_XTR_UNT_AMT": Decimal("0.00"),
    }]
    pi.tables["LH_BNF_INS_RNL_RT"] = [{
        **KEY, "SEG_IDX_NBR": 10, "PRM_RT_TYP_CD": "B",
        "SPM_BNF_TYP_CD": "#", "SPM_BNF_SBY_CD": "1",
        "RT_SEX_CD": "2", "RT_CLS_CD": "0", "RT_BAN_CD": "0", "RNL_RT": None,
    }]
    lines = render(pi)
    assert fields(lines, "Number of Rate Segments")[0]["text"] == "10"
    assert fields(lines, "Segment Length")[0]["text"] == "0132"
    assert fields(lines, "Extra Percentage")[0]["text"] == "000150000C"
    missing = fields(lines, "Rate")[-1]
    assert missing["text"] == "??????????"
    assert "NULL" in missing["note"]
    assert "not zero" in missing["note"]
    assert fields(lines, "Benefit Type")[-1]["text"] == "#"
    assert fields(lines, "Benefit Subtype")[-1]["text"] == "1"


def test_benefit_guideline_and_adjustment_units_use_their_actual_sources():
    pi = Policy()
    pi.tables["LH_BNF_INS_GDL_PRM"] = [{
        **KEY, "SEG_IDX_NBR": 9, "PRM_RT_TYP_CD": "1",
        "SPM_BNF_TYP_CD": "E", "SPM_BNF_SBY_CD": "A",
        "RT_SEX_CD": "2", "RT_CLS_CD": "N",
        "GDL_PRM_UNT_QTY": Decimal("-1.234"),
    }]
    lines = render(pi)
    assert fields(lines, "GLP/GSP Units")[0]["text"] == "00000001234D"
    assert fields(lines, "Guideline Rate Key")[-1]["text"] == "2N"
    assert fields(lines, "Benefit Type")[-1]["text"] == "E"
    assert fields(lines, "Benefit Subtype")[-1]["text"] == "A"


def test_coverage_markers_joint_and_plan_option_are_not_raw_flags():
    pi = Policy()
    pi.tables["LH_COV_INS_RNL_RT"][0]["JT_INS_IND"] = "1"
    pi.tables["LH_COV_INS_RNL_RT"][-2]["DTH_BNF_PLN_OPT_CD"] = "2"
    lines = render(pi)
    assert fields(lines, "Benefit Type")[0]["text"] == "*"
    assert fields(lines, "Benefit Subtype")[0]["text"] == "J"
    assert fields(lines, "Benefit Subtype")[2]["text"] == "2"


def test_rate_file_guideline_uses_plan_option_and_recorded_key():
    pi = Policy()
    row = pi.tables["LH_COV_INS_GDL_PRM"][0]
    row.update({
        "SYS_CLC_PRM_IND": "0", "DTH_BNF_PLN_OPT_CD": "2",
        "RT_SEX_CD": "1", "RT_CLS_CD": "A",
    })
    lines = render(pi)
    assert fields(lines, "Benefit Type")[-2]["text"] == "*"
    assert fields(lines, "Benefit Subtype")[-2]["text"] == "2"
    assert fields(lines, "Guideline Rate Key")[0]["text"] == "1A"


@pytest.mark.parametrize("key", ["\x00", None, ""])
def test_benefit_guideline_keys_are_not_guessed_from_nulls(key):
    pi = Policy()
    pi.tables["LH_BNF_INS_GDL_PRM"] = [{
        **KEY, "SEG_IDX_NBR": 9, "PRM_RT_TYP_CD": "A",
        "SPM_BNF_TYP_CD": "E", "SPM_BNF_SBY_CD": "A",
        "RT_SEX_CD": key, "RT_CLS_CD": key, "GDL_PRM_AMT": 0,
    }]
    with pytest.raises(ValueError):
        render(pi)


def test_system_guideline_adjustments_are_not_supported():
    pi = Policy()
    pi.tables["LH_COV_INS_GDL_PRM"][0]["PRM_RT_TYP_CD"] = "1"
    with pytest.raises(ValueError, match="require type A or S"):
        render(pi)


@pytest.mark.parametrize("amount", [Decimal("0.00"), None, Decimal("1.23")])
def test_dollar_extras_never_guess_fixed_vs_flexible_precision(amount):
    pi = Policy()
    pi.tables["LH_SST_XTR_RNL_RT"] = [{
        **KEY, "SEG_IDX_NBR": 9, "PRM_RT_TYP_CD": "E",
        "SST_XTR_RT_TBL_CD": "B ", "SST_XTR_PCT_IND": "0",
        "RT_SEX_CD": "1", "RT_CLS_CD": "A", "RT_BAN_CD": "A",
        "SST_XTR_UNT_AMT": amount,
    }]
    if amount:
        with pytest.raises(ValueError, match="packed precision is not verified"):
            render(pi)
    else:
        token = fields(render(pi), "Extra Unit Amount")[0]
        assert token["text"] == ("??????????" if amount is None else "000000000C")


@pytest.mark.parametrize("change,match", [
    ("missing_column", "source column is missing: RNL_RT"),
    ("duplicate_entry", "Duplicate Segment 67 entry index"),
    ("missing_index", "Non-contiguous"),
    ("orphan", "has no renewal period"),
    ("duplicate_period", "Duplicate Segment 67 renewal period"),
])
def test_malformed_data_blocks_partial_live_screens(change, match):
    pi = Policy()
    rates = pi.tables["LH_COV_INS_RNL_RT"]
    if change == "missing_column":
        del rates[0]["RNL_RT"]
    elif change == "duplicate_entry":
        rates.append(dict(rates[0]))
    elif change == "missing_index":
        rates[0]["SEG_IDX_NBR"] = 20
    elif change == "orphan":
        rates[0]["PRS_SEQ_NBR"] = 2
    elif change == "duplicate_period":
        pi.tables["LH_COV_INS_RNL_PER"].append(dict(pi.tables["LH_COV_INS_RNL_PER"][0]))
    with pytest.raises(ValueError, match=match):
        render(pi)


def test_db2_error_is_not_treated_as_an_empty_table():
    pi = Policy()
    pi.errors["LH_BNF_INS_RNL_RT"] = "SELECT not authorized"
    with pytest.raises(ValueError, match="LH_BNF_INS_RNL_RT.*SELECT not authorized"):
        render(pi)
    screen = build_screen("67", pi)
    assert not screen.get("live")
    assert "SELECT not authorized" in screen["live_error"]
    badge, kind = PolicyRecordViewerWindow._badge_for(None, "67", screen, pi, False)
    assert "LIVE DATA ERROR" in badge
    assert "CAPTURED REFERENCE" not in badge
    assert kind == "error"
    assert screen["lines"] == []
    assert screen["layout_html"] == ""


def test_empty_policy_omits_segment():
    pi = Policy()
    pi.tables.clear()
    assert render(pi) is None
    assert build_screen("67", pi) is None


@pytest.mark.parametrize("value,digits,decimals,expected", [
    ("337971", 9, 0, "000337971C"),
    ("6430", 9, 0, "000006430C"),
    ("0.00", 11, 2, "00000000000C"),
    ("-21949.14", 11, 2, "00002194914D"),
    ("-0.00", 11, 2, "00000000000C"),
    ("1.50", 9, 5, "000150000C"),
])
def test_packed_decimal_preserves_scale_and_sign(value, digits, decimals, expected):
    assert _packed_decimal(Decimal(value), digits, decimals) == expected


@pytest.mark.parametrize("value", ["1.234", "1000000000", "NaN", "Infinity"])
def test_packed_decimal_never_rounds_or_truncates(value):
    with pytest.raises(ValueError):
        _packed_decimal(value, 9, 2)
