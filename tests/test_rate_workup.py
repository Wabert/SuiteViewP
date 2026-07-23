"""Rate Workup unit tests — parsers, projections and reformatter fixes."""

import pytest

from suiteview.ratemanager import ckultb01_parser
from suiteview.ratemanager.benefit_db import BenefitDBSpec, build_benefit_rows
from suiteview.ratemanager.parser import ParseResult, ProductInfo, RateRecord
from suiteview.ratemanager.rate_reformatter import RateReformatter
from suiteview.ratemanager.workup.builder import (
    BENCOI_HEADERS, BENTRG_HEADERS, COI_HEADERS, EPU_HEADERS, SCR_HEADERS,
    WorkupAnalysis, WorkupSpec, _band_out_map, _build_epu, _build_scr,
    _build_linked_benefit, _expand_attained_table, _match_raw,
    _sex_candidates, _sex_out, build,
    benefit_start_index,
)
from suiteview.ratemanager.workup.spec import BenefitSelection


# ---------------------------------------------------------------------------
# CKULTB01 (EPU) parser
# ---------------------------------------------------------------------------

CKULTB01_SAMPLE = """\
1DATE  04/20/26                                     CYBERLIFE ONLINE TABLES LIST                                          PAGE    1
0TABLE: CKULTB01                  PROCESSING OPTIONS: USERID = ALL
   PLANCODE PLAN CODE                      CHAR         2  C1          CHARGE   CHARGE AMOUNT                  NUM      13, 5  N3
0          PLANCODE FREQTYPE RULECODE STATCODE SEX CODE RATECLAS BAND     EFF DATE   MONTHDUR HIGH AGE CHARGE           MAXIMUM
                     GUAR CHG         GUAR MAX     AUDIT# CHANGED
           -------- -------- -------- -------- -------- -------- -------- ---------- -------- -------- ---------------- ------------
                     ---------------- ------------ ------ ----------
           C1       M        1        **       *        *        A        01/01/1900   99,999      999           5.00000  9,999,999.0
                     0           5.00000  9,999,999.00 T02416 08/01/2019
           C3       M        1        **       *        *        *        01/01/1900      180      999          40.00000  9,999,999.0
                     0          40.00000  9,999,999.00 S68620 05/16/2017
           C3       M        1        **       *        *        *        01/01/1900   99,999      999          10.00000  9,999,999.0
                     0          10.00000  9,999,999.00 S68620 05/16/2017
"""


def test_ckultb01_parser_stitches_wrapped_maximum(tmp_path):
    path = tmp_path / "ckultb01.txt"
    path.write_text(CKULTB01_SAMPLE, encoding="utf-8")

    records = list(ckultb01_parser.iter_records(str(path)))
    assert len(records) == 3

    first = records[0]
    assert first["PLAN_CODE"] == "C1"
    assert first["FREQ_TYPE"] == "M"
    assert first["RULE_CODE"] == "1"
    assert first["STATE_CODE"] == "**"
    assert first["BAND_CODE"] == "A"
    assert first["MONTH_DUR"] == 99999
    assert first["HIGH_AGE"] == 999
    assert first["CHARGE"] == 5.0
    # "9,999,999.0" + wrapped "0" → 9,999,999.00
    assert first["MAXIMUM"] == pytest.approx(9_999_999.00)
    assert first["GUAR_CHARGE"] == 5.0
    assert first["AUDIT_NUM"] == "T02416"
    assert first["CHANGED_DATE"] == "08/01/2019"

    # Bracketed C3: 180 months then open-ended.
    assert records[1]["MONTH_DUR"] == 180
    assert records[1]["CHARGE"] == 40.0
    assert records[2]["MONTH_DUR"] == 99999
    assert records[2]["CHARGE"] == 10.0


def test_ckultb01_list_plan_groups(tmp_path):
    path = tmp_path / "ckultb01.txt"
    path.write_text(CKULTB01_SAMPLE, encoding="utf-8")
    groups = ckultb01_parser.list_plan_groups(str(path))
    assert groups == [("C1", "M", "1", 1), ("C3", "M", "1", 2)]


# ---------------------------------------------------------------------------
# Combo matching / sex normalization
# ---------------------------------------------------------------------------

def test_sex_candidates():
    assert _sex_candidates("1") == ["1", "M"]
    assert _sex_candidates("2") == ["2", "F"]
    assert "U" in _sex_candidates("Y")


def test_match_raw_prefers_specific_then_wildcards():
    raw = {("F", "E", "B"), ("*", "*", "A"), ("2", "E", "0")}
    # Exact CyberLife female letter match.
    assert _match_raw(("2", "E", "B"), raw) == ("F", "E", "B")
    # Band fallback to '0'.
    assert _match_raw(("2", "E", "C"), raw) == ("2", "E", "0")
    # Full wildcard.
    assert _match_raw(("1", "K", "A"), raw) == ("*", "*", "A")
    # No match at all.
    assert _match_raw(("1", "K", "D"), raw) is None


def test_benefit_start_index_convention():
    # Base index with the 2-digit type code inserted + two zeros appended.
    assert benefit_start_index(13400, "12") == 1341200
    assert benefit_start_index(13400, "21") == 1342100
    # Letters map via the subtype table: M=8, F=6, G=5, '#'=4.
    assert benefit_start_index(13400, "4M") == 1344800
    assert benefit_start_index(13400, "3F") == 1343600
    assert benefit_start_index(13400, "7G") == 1347500
    assert benefit_start_index(13400, "1#") == 1341400
    # Unmapped letter → None (user must supply the index).
    assert benefit_start_index(13400, "4E") is None


def test_sex_out_codes():
    assert _sex_out("1") == "M"
    assert _sex_out("2") == "F"
    # Unisex codes pass through unchanged.
    assert _sex_out("Y") == "Y"
    assert _sex_out("X") == "X"
    assert _sex_out("T") == "T"


def test_band_out_map_alphabetical_and_xy_exception():
    combos = [("1", "N", b) for b in ("A", "B", "C", "D")]
    assert _band_out_map(combos) == {
        "A": "1", "B": "2", "C": "3", "D": "4", "0": "0"}
    # X and Y sort FIRST: X=1, Y=2, then A, B, C.
    combos = [("1", "N", b) for b in ("X", "Y", "A", "B", "C")]
    assert _band_out_map(combos) == {
        "X": "1", "Y": "2", "A": "3", "B": "4", "C": "5", "0": "0"}
    # Unbanded plan: band '0' stays '0'.
    assert _band_out_map([("1", "N", "0")]) == {"0": "0"}


def test_mpf_exporter_converts_percent_to_decimal():
    from suiteview.ratemanager.mpf_exporter import _expand as mpf_expand
    table = {30: (5.64, "5.64%", True), 31: (1.22, "1.22", False)}
    rows = {(ia, dur): r for ia, dur, r in mpf_expand(table, renewable=True)}
    assert rows[(30, 1)] == pytest.approx(0.0564)   # percent → decimal
    assert rows[(30, 2)] == 1.22                    # factor unchanged


def test_mpf_nonrenewing_rates_stop_before_cease_age():
    from suiteview.ratemanager.mpf_exporter import _expand as mpf_expand
    table = {
        age: (float(age), str(age), False) for age in range(20, 81)
    }
    rows = mpf_expand(table, renewable=False, cease_age=65)
    issue_20 = [(dur, rate) for ia, dur, rate in rows if ia == 20]
    assert max(dur for dur, _rate in issue_20) == 45


def test_expand_attained_table_renewable_vs_level():
    table = {30: 1.0, 31: 2.0, 32: 3.0}
    renew = _expand_attained_table(table, renewable=True)
    # Issue 30: durations 1..3 walk the attained ages.
    assert (30, 1, 1.0) in renew and (30, 2, 2.0) in renew and (30, 3, 3.0) in renew
    level = _expand_attained_table(table, renewable=False, cease_age=33)
    assert (30, 1, 1.0) in level and (30, 2, 1.0) in level and (30, 3, 1.0) in level


# ---------------------------------------------------------------------------
# EPU bracket expansion (through a synthetic CKULTB01 file)
# ---------------------------------------------------------------------------

def test_epu_monthdur_brackets(tmp_path):
    path = tmp_path / "ckultb01.txt"
    path.write_text(CKULTB01_SAMPLE, encoding="utf-8")

    spec = WorkupSpec(
        epu_path=str(path), epu_plan="C3", epu_freq="M", epu_rule="1",
        base_index=15000)
    combos = [("1", "N", "A")]
    warnings = []
    combo_index, rows, groups = _build_epu(
        spec, combos, ia_min=0, ia_max=0, max_att_age=19,
        warnings=warnings, progress_cb=lambda f: None)

    assert combo_index == {("1", "N", "A"): 15000}
    assert groups == 1
    # Scale 1 (current): years 1-15 → 40.0 (MONTHDUR 180), 16-20 → 10.0.
    current = {(ia, dur): rate for idx, sc, ia, dur, rate in rows if sc == 1}
    assert current[(0, 1)] == 40.0
    assert current[(0, 15)] == 40.0     # month 180 — still inside the bracket
    assert current[(0, 16)] == 10.0     # month 192 — open-ended bracket
    assert current[(0, 20)] == 10.0
    guaranteed = {(ia, dur): rate for idx, sc, ia, dur, rate in rows if sc == 0}
    assert guaranteed[(0, 1)] == 40.0


# ---------------------------------------------------------------------------
# SCR AA + exception states (through a synthetic CKULTB04 file)
# ---------------------------------------------------------------------------

CKULTB04_SAMPLE = """\
1DATE  03/31/26                                     CYBERLIFE ONLINE TABLES LIST                                          PAGE    1
0          PLANCODE RULECODE STATE CD SEX CODE RATE     BANDCODE EFF DATE   HIGH DUR HI IAGE  GRPD/XIN AMOUNT         CHG PCT   ALLOW
           64       6        07       F        E        A        01/01/1900        0       16        0            0.00      3.710
                                0.000        0 S46231 08/24/2015
           64       6        42       F        E        A        01/01/1900        0       16        0            0.00      3.710
                                0.000        0 S46231 08/24/2015
           64       6        31       F        E        A        01/01/1900        0       16        0            0.00      9.999
                                0.000        0 S46231 08/24/2015
           64       6        07       F        E        A        01/01/1900      999       16        0            0.00      0.000
                                0.000        0 S46231 08/24/2015
"""


def test_scr_aa_plus_exception_states(tmp_path):
    path = tmp_path / "ckultb04.txt"
    path.write_text(CKULTB04_SAMPLE, encoding="utf-8")

    spec = WorkupSpec(
        scr_path=str(path), scr_plan="64", base_index=14000, maturity_age=20)
    combos = [("2", "E", "A")]      # CyberLife 'F' should match IAF sex '2'
    warnings = []
    combo_state_index, rows, groups = _build_scr(
        spec, combos, warnings, progress_cb=lambda f: None)

    entry = combo_state_index[("2", "E", "A")]
    # States 07 (DE) and 42 (TX) share a schedule → majority → 'AA'.
    # State 31 (NY) differs → exception row.
    assert set(entry) == {"AA", "NY"}
    assert entry["AA"] != entry["NY"]
    assert groups == 2

    by_index = {}
    for idx, ia, dur, rate in rows:
        by_index.setdefault(idx, {})[(ia, dur)] = rate
    # Source year 0 → Duration 1; zero-filled to maturity 20 (ages 16 → durs 1-4).
    assert by_index[entry["AA"]][(16, 1)] == 3.710
    assert by_index[entry["AA"]][(16, 2)] == 0.0
    assert by_index[entry["NY"]][(16, 1)] == 9.999


# ---------------------------------------------------------------------------
# Reformatter — duration-00-only and guaranteed select+ultimate
# ---------------------------------------------------------------------------

def _mk_result(rates, pay_age=10):
    return ParseResult(
        products=[ProductInfo(ref=1, plancode="TESTPLAN", version="1",
                              pay_age=pay_age, me_age=pay_age)],
        rates=rates,
    )


def _rate(rate_type, att, dur, rate, band="A", sex="1", cls="N",
          opt="**", start="01/01/1900"):
    return RateRecord(
        product_ref=1, rate_type=rate_type, scale_start=start,
        scale_stop="12/31/9999", attained_age=att, duration=dur,
        issue_age=att - dur, gender=sex, rate_class=cls, band=band,
        plan_option=opt, rate=rate)


def test_bencoi_uses_each_combo_target_issue_age_range():
    rates = [
        _rate("C", 20, 99, 0.1, sex=sex)
        for sex in ("1", "2")
    ]
    for sex, target_max in (("1", 40), ("2", 30)):
        rates.extend(
            _rate("C", age, 99, 0.2, band="0", sex=sex, opt="21")
            for age in range(10, 61)
        )
        rates.extend([
            _rate("M", 20, 0, 1.0, band="0", sex=sex, opt="21"),
            _rate("M", target_max, 0, 1.0, band="0", sex=sex, opt="21"),
        ])

    result = ParseResult(
        products=[ProductInfo(ref=1, plancode="TESTPLAN", version="1", pay_age=81)],
        rates=rates,
    )
    pointers, bencoi, _bentrg, _counts = build_benefit_rows(
        result, [BenefitDBSpec(
            code="21", renewable=False, start_index=100, cease_age=81)]
    )

    index_by_sex = {row[4]: row[7] for row in pointers}
    assert index_by_sex["1"] != index_by_sex["2"]
    ages_by_index = {
        index: {row[2] for row in bencoi if row[0] == index}
        for index in index_by_sex.values()
    }
    assert ages_by_index[index_by_sex["1"]] == set(range(20, 41))
    assert ages_by_index[index_by_sex["2"]] == set(range(20, 31))


def test_mpf_linked_bencoi_uses_iaf_target_issue_age_range():
    result = ParseResult(
        products=[ProductInfo(ref=1, plancode="TESTPLAN", version="1")],
        rates=[
            _rate("M", 20, 0, 1.0, band="0", opt="3F"),
            _rate("M", 40, 0, 1.0, band="0", opt="3F"),
        ],
    )
    mpf_items = {
        ("1", "N", "A"): {
            age: (float(age), str(age), False) for age in range(10, 61)
        }
    }

    _pointers, bencoi, _bentrg, _block = _build_linked_benefit(
        result,
        BenefitSelection(code="3F", renewable=True, mpf_code="312"),
        mpf_items,
        [("1", "N", "A")],
        200,
        "TESTPLAN",
        "1",
        [],
    )

    assert {row[2] for row in bencoi} == set(range(20, 41))


def test_nonrenewing_bencoi_stops_before_cease_age():
    rates = [_rate("C", 20, 99, 0.1)]
    rates.extend(
        _rate("C", age, 99, 0.2, band="0", opt="21")
        for age in range(20, 81)
    )
    rates.extend([
        _rate("M", 20, 0, 1.0, band="0", opt="21"),
        _rate("M", 40, 0, 1.0, band="0", opt="21"),
    ])
    result = ParseResult(
        products=[ProductInfo(ref=1, plancode="TESTPLAN", version="1", pay_age=81)],
        rates=rates,
    )

    _pointers, bencoi, _bentrg, _counts = build_benefit_rows(
        result, [BenefitDBSpec(
            code="21", renewable=False, start_index=100, cease_age=65)]
    )

    issue_20 = [row for row in bencoi if row[2] == 20 and row[1] == 1]
    assert max(row[3] for row in issue_20) == 45
    assert max(20 + row[3] - 1 for row in issue_20) == 64


def test_nonrenewing_benefit_requires_cease_age():
    result = ParseResult(
        products=[ProductInfo(ref=1, plancode="TESTPLAN", version="1", pay_age=81)],
        rates=[
            _rate("C", 20, 99, 0.1),
            _rate("C", 20, 99, 0.2, band="0", opt="21"),
        ],
    )

    with pytest.raises(ValueError, match="cease age is required"):
        build_benefit_rows(
            result,
            [BenefitDBSpec(code="21", renewable=False, start_index=100)],
        )


def test_workup_build_requires_base_index():
    result = build(WorkupSpec(), WorkupAnalysis())
    assert result.error.startswith(
        "Base Index is required before building rates.")


def test_workup_rate_headers_match_ul_rates_columns():
    assert COI_HEADERS == [
        "Index(COI)", "Scale", "IssueAge", "Duration", "Rate",
    ]
    assert SCR_HEADERS == ["Index(SCR)", "IssueAge", "Duration", "Rate"]
    assert EPU_HEADERS == [
        "Index(EPU)", "Scale", "IssueAge", "Duration", "Rate",
    ]
    assert BENCOI_HEADERS == [
        "Index(BENCOI)", "Scale", "IssueAge", "Duration", "Rate",
    ]
    assert BENTRG_HEADERS == [
        "Index(BENTRG)", "IssueAge", "Rate(MTP)", "Rate(CTP)",
    ]


def test_table_rating_targets_include_tbl4_and_rounded_tbl1_rates():
    result = _mk_result([
        _rate("C", 20, 99, 0.1, band="A", sex="1", cls="G"),
        _rate("M", 20, 0, 4.37, band="A", sex="1", cls="G"),
        _rate("T", 20, 0, 4.37, band="A", sex="1", cls="G"),
        _rate("M", 20, 0, 0.920, band="0", sex="1", cls="G", opt="E*"),
        _rate("T", 20, 0, 0.920, band="0", sex="1", cls="G", opt="E*"),
    ])
    reformatter = RateReformatter(result, starting_index=13400)
    computed = reformatter.compute()

    rows = list(reformatter.target_rows(
        computed["trg_reps"], computed["ia_min"], computed["ia_max"]))

    assert rows == [(13400, 20, 4.37, 0.23, 4.37, 0.23, 0.920)]


def test_ctp_uses_unbanded_main_t_rate_as_fallback():
    result = _mk_result([
        _rate("C", 20, 99, 0.1, band="A", sex="1", cls="G"),
        _rate("T", 20, 0, 4.37, band="0", sex="1", cls="G"),
    ])
    reformatter = RateReformatter(result, starting_index=13400)
    computed = reformatter.compute()

    rows = list(reformatter.target_rows(
        computed["trg_reps"], computed["ia_min"], computed["ia_max"]))

    assert rows == [(13400, 20, 4.37, None, None, None, None)]


def test_table_rating_targets_reject_different_m_and_t_tbl4_rates():
    result = _mk_result([
        _rate("C", 20, 99, 0.1, band="A", sex="1", cls="G"),
        _rate("M", 20, 0, 0.920, band="0", sex="1", cls="G", opt="E*"),
        _rate("T", 20, 0, 0.960, band="0", sex="1", cls="G", opt="E*"),
    ])
    reformatter = RateReformatter(result, starting_index=13400)
    computed = reformatter.compute()

    with pytest.raises(ValueError, match="Table-4 premium rates disagree"):
        list(reformatter.target_rows(
            computed["trg_reps"], computed["ia_min"], computed["ia_max"]))


def test_dur0_only_current_rates_act_as_ultimate():
    # Duration-00 rates at attained ages 0-9 and nothing else (1A130D29 case).
    rates = [_rate("C", att, 0, float(att + 1)) for att in range(10)]
    ref = RateReformatter(_mk_result(rates), starting_index=100)
    computed = ref.compute()
    rows = list(ref.current_coi_rows(
        computed["coi_reps"], computed["select_period"],
        computed["ia_min"], computed["ia_max"]))
    assert rows, "dur-0-only current rates must produce COI rows"
    lookup = {(ia, dur): r for _i, _s, ia, dur, r in rows}
    # Issue 0, year 1 → attained 0 → rate 1.0; year 5 → attained 4 → 5.0.
    assert lookup[(0, 1)] == 1.0
    assert lookup[(0, 5)] == 5.0
    # Issue 3, year 2 → attained 4 → 5.0.
    assert lookup[(3, 2)] == 5.0


def test_dur0_alongside_select_warns_and_is_ignored():
    rates = [
        _rate("C", 5, 1, 0.5),          # select
        _rate("C", 5, 99, 0.9),         # ultimate
        _rate("C", 5, 0, 0.7),          # ambiguous dur-0
    ]
    ref = RateReformatter(_mk_result(rates))
    assert any("duration-00 current-COI" in w for w in ref.warnings)


def test_guaranteed_select_plus_ultimate_expands_like_current():
    # G select years 1-2 for issue age 3, then ultimate at attained ages.
    rates = [_rate("C", att, 99, 0.1) for att in range(10)]
    rates += [
        _rate("G", 4, 1, 1.1, band="0"),    # issue 3, year 1
        _rate("G", 5, 2, 1.2, band="0"),    # issue 3, year 2
    ]
    rates += [_rate("G", att, 99, 9.0, band="0") for att in range(10)]
    ref = RateReformatter(_mk_result(rates))
    computed = ref.compute()
    rows = list(ref.guaranteed_coi_rows(
        computed["coi_reps"], computed["ia_min"], computed["ia_max"]))
    lookup = {(ia, dur): r for _i, _s, ia, dur, r in rows}
    # Select years come from the G select table…
    assert lookup[(3, 1)] == 1.1
    assert lookup[(3, 2)] == 1.2
    # …later years fall to the ultimate rate.
    assert lookup[(3, 3)] == 9.0
    # Other issue ages inside the select period fall back to ultimate.
    assert lookup[(0, 1)] == 9.0


def test_artifact_issue_ages_are_dropped():
    # Issue age 0's rates start at duration 17 (a 16+ plan padded down to 0);
    # issue age 16 starts at duration 1 and must survive.
    rows = [
        (13400, 0, 0, 17, 0.06169),
        (13400, 0, 0, 18, 0.07086),
        (13400, 0, 16, 1, 0.06169),
        (13400, 0, 16, 2, 0.07086),
        (13400, 1, 0, 17, 0.04),      # same artifact on another scale
        (13400, 1, 16, 1, 0.04),
    ]
    removed = set()
    kept = list(RateReformatter.filter_artifact_issue_ages(iter(rows), removed))
    assert kept == [
        (13400, 0, 16, 1, 0.06169),
        (13400, 0, 16, 2, 0.07086),
        (13400, 1, 16, 1, 0.04),
    ]
    assert removed == {(13400, 0, 0), (13400, 1, 0)}


def test_scr_state_map_override(tmp_path):
    path = tmp_path / "ckultb04.txt"
    path.write_text(CKULTB04_SAMPLE, encoding="utf-8")
    # User confirms 31 is really 'XX' (overriding the NY recommendation).
    spec = WorkupSpec(
        scr_path=str(path), scr_plan="64", base_index=14000, maturity_age=20,
        state_map={"31": "XX"})
    warnings = []
    combo_state_index, _rows, _groups = _build_scr(
        spec, [("2", "E", "A")], warnings, progress_cb=lambda f: None)
    assert set(combo_state_index[("2", "E", "A")]) == {"AA", "XX"}


def test_scan_ckultb04_collects_states(tmp_path):
    from suiteview.ratemanager.workup.builder import _scan_ckultb04
    path = tmp_path / "ckultb04.txt"
    path.write_text(CKULTB04_SAMPLE, encoding="utf-8")
    plans, states = _scan_ckultb04(str(path))
    assert plans == [("64", 4)]
    assert states == {"64": ["07", "31", "42"]}


def test_unmapped_rate_types_warn():
    rates = [_rate("C", 5, 99, 0.1), _rate("W", 5, 0, 100.0), _rate("N", 5, 0, 1.0)]
    ref = RateReformatter(_mk_result(rates))
    joined = " ".join(ref.warnings)
    assert "'W'" in joined and "'N'" in joined
