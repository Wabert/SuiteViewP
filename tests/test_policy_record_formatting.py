"""Unit tests for CyberLife policy-record value formatting.

These cover the pure formatting helpers in
``suiteview.polview.models.policy_record_builder`` -- no DB2 required -- with a
focus on the packed ``MMDDYY`` "activity" dates that the mainframe shows
unslashed (e.g. Accounting/Billing Date -> ``71026``) while ordinary calendar
dates stay slashed (``07/10/2026``).
"""

from datetime import date, datetime

from suiteview.polview.models import policy_record_builder as prb


class TestPackedMmddyy:
    def test_single_digit_month_drops_leading_zero(self):
        # 07/10/2026 -> 071026 -> leading zero suppressed -> 71026
        assert prb._packed_mmddyy(date(2026, 7, 10)) == "71026"

    def test_two_digit_month_and_single_digit_day(self):
        # 11/05/2020 -> 110520
        assert prb._packed_mmddyy(date(2020, 11, 5)) == "110520"

    def test_two_digit_month_and_day(self):
        # 10/13/2025 -> 101325
        assert prb._packed_mmddyy(date(2025, 10, 13)) == "101325"

    def test_datetime_value(self):
        assert prb._packed_mmddyy(datetime(2025, 10, 13, 9, 30)) == "101325"

    def test_iso_string_value(self):
        assert prb._packed_mmddyy("2026-07-10") == "71026"
        assert prb._packed_mmddyy("2025-10-13 09:30:00") == "101325"

    def test_null_and_sentinels_render_zero(self):
        assert prb._packed_mmddyy(None) == "0"
        assert prb._packed_mmddyy(date(9999, 12, 31)) == "0"
        assert prb._packed_mmddyy(date(1900, 1, 1)) == "0"
        assert prb._packed_mmddyy("not-a-date") == "0"


class TestFormatLikeDateKind:
    def test_packed_kinds_render_unslashed(self):
        for kind in ("date_packed", "packed_num", "int"):
            assert prb._format_like(".00", date(2026, 7, 10), kind) == "71026"

    def test_packed_kind_from_iso_string(self):
        assert prb._format_like(".00", "2026-07-10", "date_packed") == "71026"

    def test_compound_date_kind_renders_slashed(self):
        assert prb._format_like("00/00/1900", date(2026, 7, 10), "date") == "07/10/2026"

    def test_default_kind_renders_slashed(self):
        # No kind supplied -> preserve the historical slashed rendering.
        assert prb._format_like("00/00/1900", date(2026, 7, 10)) == "07/10/2026"

    def test_high_date_sentinel_still_normalised_when_slashed(self):
        # 12/31/9999 high-date sentinel shows the mainframe null date slashed...
        assert prb._format_like("00/00/1900", date(9999, 12, 31), "date") == "00/00/1900"
        # ...but zero when the field is a packed activity date.
        assert prb._format_like(".00", date(9999, 12, 31), "date_packed") == "0"

    def test_non_date_values_ignore_kind(self):
        # A numeric code is unaffected by a date kind hint.
        assert prb._format_like("0", "5", "date_packed") == "5"


class TestFieldKindMap:
    def test_maps_cobol_names_to_kinds_from_index(self):
        screen = {
            "field_specs": [
                {"name": "Accounting Date", "cobol": "FBRPAYDT-ACCOUNTING-DATE"},
                {"name": "Billing Date", "cobol": "FBRBILDT-BILLING-DATE"},
                {"name": "Paid-To Date", "cobol": "FBRPDTDT-PAID-TO-DATE"},
                {"name": "Reserved", "cobol": None},
                {"name": "Bogus", "cobol": "NOT-A-REAL-COBOL-NAME"},
            ]
        }
        kinds = prb._field_kind_map(screen)
        assert kinds.get("Accounting Date") == "date_packed"
        assert kinds.get("Billing Date") == "packed_num"
        assert kinds.get("Paid-To Date") == "date"
        # Fields without a COBOL name or index entry are simply absent.
        assert "Reserved" not in kinds
        assert "Bogus" not in kinds

    def test_index_available(self):
        # The shipped index must load (the packed-date fix depends on it).
        assert prb._cyberdoc_index(), "cyberdoc_field_formats.json failed to load"


class TestShippedSegmentScreens:
    """Structural guarantees for the bundled ``seg_<n>.json`` screens so a
    hovered terminal value never references a field name missing from the
    ``fields`` map (which would show an empty/broken tooltip)."""

    def _screens(self):
        from suiteview.polview.ui import policy_record_viewer as prv

        return prv, {
            seg: screen for seg in prv._SEGMENTS
            if (screen := prv.load_screen(seg)) is not None
        }

    def test_shipped_screens_are_registered_and_load(self):
        prv, screens = self._screens()
        from pathlib import Path

        shipped = {path.stem.removeprefix("seg_") for path in Path(prv._DATA_DIR).glob("seg_??.json")}
        assert set(screens) == shipped

    def test_screens_have_lines_fields_and_layout(self):
        _, screens = self._screens()
        for seg, screen in screens.items():
            assert screen.get("lines"), f"seg {seg}: no terminal lines"
            assert isinstance(screen.get("fields"), dict), f"seg {seg}: no fields map"
            assert screen.get("layout_html"), f"seg {seg}: no record layout"

    def test_field_map_values_are_string_lists(self):
        _, screens = self._screens()
        for seg, screen in screens.items():
            for name, mappings in screen["fields"].items():
                assert isinstance(mappings, list), f"seg {seg}: {name} not a list"
                assert all(isinstance(m, str) for m in mappings), (
                    f"seg {seg}: {name} has non-string mapping"
                )

    def test_reference_segment_tokens_resolve_in_fields_map(self):
        # The captured-reference screens (assembled from token field-names) must
        # cover every hovered token, so each shows at least its field name.
        _, screens = self._screens()
        for seg in ("02", "66", "67"):
            screen = screens[seg]
            fields = screen["fields"]
            for line in screen["lines"]:
                for run in line:
                    name = run.get("field")
                    if name:
                        assert name in fields, (
                            f"seg {seg}: token field {name!r} missing from "
                            "fields map"
                        )


class TestSegment01Mapping:
    """Lock the Segment 01 (6201) template mappings that were corrected against
    a real CyberLife screen (policy U0175443): the billing Mode/Nonstandard-Mode
    order, the ``Other Kind`` change-report code, the reserved Change-Pending
    byte, and the blank tail indicators.  These are static assertions on
    ``seg_01.json`` so they need no live DB2."""

    def _seg01(self):
        from suiteview.polview.ui import policy_record_viewer as prv

        return prv.load_screen("01")

    @staticmethod
    def _tokens(screen):
        out = []
        for line in screen["lines"]:
            for run in line:
                if run.get("field"):
                    out.append(run)
        return out

    @staticmethod
    def _spec(screen, name):
        for spec in screen["field_specs"]:
            if spec.get("name") == name:
                return spec
        return None

    def test_billing_mode_before_nonstandard_mode(self):
        # CyberDoc: Mode (FBRBMODE, 2 bytes) precedes Nonstandard Mode
        # (FBRMDNST, 1 byte); the live screen shows ``G 1 0 0``.
        screen = self._seg01()
        tokens = self._tokens(screen)
        fields = [t["field"] for t in tokens]
        assert fields.index("Billing Mode") < fields.index("Nonstandard Mode")

        bmode = next(t for t in tokens if t["field"] == "Billing Mode")
        nmode = next(t for t in tokens if t["field"] == "Nonstandard Mode")
        assert bmode["db2"] == "LH_BAS_POL.PMT_FQY_PER"
        assert nmode["db2"] == "LH_BAS_POL.NSD_MD_CD"

        assert self._spec(screen, "Billing Mode")["byte"] == "145-146"
        assert self._spec(screen, "Nonstandard Mode")["byte"] == "147"

    def test_other_kind_carries_change_report_code(self):
        # POL_CHG_RPT_TYP_CD is the "policy change report type" -> Other Kind
        # (FBRKIND, byte 166), not the reserved Change Pending byte (152).
        screen = self._seg01()
        tokens = self._tokens(screen)
        other = next(t for t in tokens if t["field"] == "Other Kind")
        change = next(
            t for t in tokens if t["field"] == "Change Pending Code (Reserved)"
        )
        assert other["db2"] == "LH_BAS_POL.POL_CHG_RPT_TYP_CD"
        assert change.get("db2") is None

        assert (
            self._spec(screen, "Other Kind")["db2"]
            == "LH_BAS_POL.POL_CHG_RPT_TYP_CD"
        )
        assert self._spec(screen, "Change Pending Code (Reserved)")["db2"] is None

    def test_other_kind_hover_shows_db2_change_pending_reserved(self):
        screen = self._seg01()
        fields = screen["fields"]
        assert any(
            "POL_CHG_RPT_TYP_CD" in m for m in fields["Other Kind"]
        ), "Other Kind hover should cite the DB2 change-report column"
        assert not any(
            "DB2:" in m for m in fields["Change Pending Code (Reserved)"]
        ), "Change Pending (Reserved) should advertise no DB2 source"

    def test_tail_indicators_are_blank_not_fabricated(self):
        # New Business / Premium-as-Loan indicators (bytes 235-236) have no DB2
        # source and are blank on the real screen -- never fabricated amber data.
        screen = self._seg01()
        tokens = self._tokens(screen)
        for name in ("New Business Indicator", "Premium as Loan Payment Indicator"):
            tok = next(t for t in tokens if t["field"] == name)
            assert tok.get("db2") is None
            assert tok["text"].strip() == "", f"{name} should render blank"

    def test_advance_indicator_sample_is_not_a_date(self):
        # A date-shaped sample made a blank indicator render as ``00/00/1900``.
        screen = self._seg01()
        tok = next(
            t
            for t in self._tokens(screen)
            if t["field"] == "PerformancePlus Advance Indicator"
        )
        assert not prb._DATE_RE.match(tok["text"].strip())

    def test_every_seg01_token_resolves_in_fields_map(self):
        screen = self._seg01()
        fields = screen["fields"]
        for tok in self._tokens(screen):
            name = tok["field"]
            # Chrome tokens (screen name, policy, footer) carry a role and are
            # not part of the hover fields map.
            if tok.get("role"):
                continue
            assert name in fields, f"token {name!r} missing from fields map"


class TestSegment66Formatters:
    def test_date_slashed_and_null_sentinels(self):
        assert prb._seg66_date("2070-08-15") == "08/15/2070"
        assert prb._seg66_date(date(2026, 8, 15)) == "08/15/2026"
        # Blank / null / high-date sentinel all render the seg-66 null date.
        assert prb._seg66_date("") == "**/**/****"
        assert prb._seg66_date(None) == "**/**/****"
        assert prb._seg66_date("9999-12-31") == "**/**/****"

    def test_int_strips_trailing_decimals(self):
        assert prb._seg66_int("0.00") == "0"
        assert prb._seg66_int("25000") == "25000"
        assert prb._seg66_int("9999999") == "9999999"
        assert prb._seg66_int("") == "0"
        assert prb._seg66_int(None) == "0"

    def test_code_preserves_leading_zeros(self):
        assert prb._seg66_code("09") == "09"
        assert prb._seg66_code("00") == "00"
        assert prb._seg66_code("L0") == "L0"
        assert prb._seg66_code(None) == ""

    def test_decimal_formats_drop_leading_zero(self):
        assert prb._seg66_format("185.000", "dec3") == "185.000"
        assert prb._seg66_format("0.000", "dec3") == ".000"
        assert prb._seg66_format("91869.61", "dec2") == "91869.61"
        assert prb._seg66_format("", "dec2") == ".00"


class _FakePI:
    """Minimal PolicyInformation stand-in for the segment builders."""

    def __init__(self, rows, policy="U0361148", region="CKPR", company="ANICO",
                 covpha=None):
        self._rows = rows
        self._covpha = covpha or []
        self.policy_number = policy
        self.region = region
        self.company_name = company

    def fetch_table(self, table):
        if table == "LH_NON_TRD_POL":
            return list(self._rows)
        if table == "LH_COV_PHA":
            return list(self._covpha)
        return []

    def table_error(self, table):
        return ""


# One real advanced-product record (U0361148), as DB2 returns it: ISO dates,
# decimal strings, blanks.  Frozen here so the whole seg-66 mapping + grouping +
# per-field formatting is verified against the known-good 6266 screen.
_U0361148_NTP = {
    "TFDF_CD": "2", "DTH_BNF_PLN_OPT_CD": "1",
    "DCA_ORD_RLE_CD": "1", "DCA_PLN_OPT_RLE_CD": "2",
    "ICE_ORD_RLE_CD": "1", "ICE_PLN_OPT_RLE_CD": "1",
    "MT_DT": "2070-08-15", "MIN_CSV_BAL_AMT": "0",
    "MIN_CSV_BAL_ITS_RT": "4.000", "POL_GUA_ITS_RT": "4.000",
    "CSV_XPN_FQY_CD": "M", "CSV_XPN_BSS_CD": "1", "CSV_XPN_TBL_CD": "L0",
    "CSV_XPN_RLE_1_CD": "1", "CSV_XPN_RLE_2_CD": "2", "CSV_XPN_RLE_3_CD": "0",
    "CINS_NAR_RLE_CD": "1", "CINS_GUA_RT_PER_CD": "0", "CINS_GUA_RT_PER": "0",
    "CINS_GUA_END_DT": "9999-12-31", "CINS_CRG_FQY_PER": "1",
    "CINS_RT_CLC_RLE_CD": "2", "CINS_CRG_THRU_DT": "2026-08-15",
    "PRM_REC_ITS_RLE_CD": "1", "PRM_GRA_PER": "0", "PRM_FREEZE_PER": "0",
    "PRM_LD_TBL_CD": "13", "PRM_LD_RLE_1_CD": "3", "PRM_LD_RLE_2_CD": "0",
    "PRM_LD_RLE_3_CD": "0", "MAX_ADD_PMT_NBR": "999", "ADD_PMT_DBT_CD": "Y",
    "ADD_PMT_MIN_AMT": "10", "ADD_PMT_MAX_AMT": "9999999", "ADD_PMT_MAX_CD": "0",
    "PRM_TAX_CD": "0", "BIL_PLN_OPT_CD": "M", "BIL_STA_CD": "0",
    "BIL_COMMENCE_DT": "", "REN_RLE_CD": "1", "COM_RLE_CD": "A",
    "CDR_RLE_CD": "1", "CDR_AMT": "0", "CDR_PCT": "185.000",
    "MIN_SUM_ISU_AMT": "25000", "NAR_AMT": "91869.61", "DEATH_BEN_AMT": "",
    "ANN_STT_FQY_PER": "12", "CNFM_FQY_PER": "0", "FUL_SRD_ALW_CD": "0",
    "FUL_SRD_PTA_IND": "N", "FUL_SRD_CRG_TBL_CD": "15", "FUL_SRD_FST_CRG_CD": "6",
    "FUL_SRD_2ND_CRG_CD": "0", "FRE_LK_SRD_RLE_CD": "1", "PAT_SRD_ALW_CD": "0",
    "PAT_SRD_CRG_TBL_CD": "09", "PAT_SRD_FST_CRG_CD": "1",
    "PAT_SRD_2ND_CRG_CD": "0", "MIN_PAT_SRD_AMT": "100", "PAT_SRD_MAX_NBR": "999",
    "PAT_SRD_MIN_RLE_CD": "0", "PAT_SRD_MIN_MO_NBR": "0", "PAT_SRD_BAL_AMT": "0",
    "LN_ITS_DSB_RLE_CD": "A", "LN_CRE_ITS_RT_CD": "0", "LN_CRE_ITS_RT": "4.000",
    "LN_MIN_BAL_TBL_CD": "00", "LN_MIN_BAL_RLE_CD": "2", "LN_MIN_DUR": "0",
    "LN_MIN_AMT": "0.00", "PRF_LN_OPT_CD": "2", "PRF_LN_AMT_PCT": "0",
    "PRF_LN_YR_AVA_NBR": "8", "PRF_LN_ITS_CRG_RT": "6.000",
    "PRF_LN_ITS_CRE_CD": "0", "PRF_LN_ITS_CRE_RT": "6.000",
    "LST_MO_DUR_PRC_NBR": "336", "GRA_PER_DAY_NBR": "61",
    "GRA_PER_ITS_RT_CD": "1", "GRA_PER_CRE_RT": "0.000", "GRA_THD_RLE_CD": "T",
    "GRA_PER_EXP_DT": "", "LST_STT_DT": "2025-08-15", "LST_STT_TYP_CD": "1",
    "PRC_BACK_DT": "", "LST_MO_DUR_NBR": "330", "ARCH_HST_DUR_NBR": "",
    "REWARD_TYP_CD": "C", "REWARD_TBL_AGU_CD": "87", "PRO_BNS_RS_CD": "5",
    "PRO_BNS_RS_DT": "2008-08-15", "RETRO_BNS_RS_CD": "0", "RETRO_BNS_RS_DT": "",
    "GLP_CUR_RT_RLE_CD": "0", "THD_AMT": "0.00", "GAV_RULE_CODE": "0",
}

# The visible body lines of the real 6266 screen (header + 6 wrapped rows).
_SEG66_EXPECTED = [
    "66  0247  00000000  00000000  00000000  00000000  00000000  00000000  2  1  12  11",
    "08/15/2070  0  4.000  4.000  M  1  L0  120  1  0  0  **/**/****  1  2  08/15/2026  1  0",
    "0  13  300  999  Y  10  9999999  0  0  M  0  **/**/****  1  A  1  0  185.000  25000",
    "91869.61  .00  12  0  0N15601  0  0910  100  999  0  0  0  A  0  4.000  002  0  0  2  0  8",
    "6.000  0  6.000  336  61  1  .000  T  **/**/****  08/15/2025  1  **/**/****  330  0",
    "C  87  5  08/15/2008  0  **/**/****  0  .00  0  0  0  0  0  1",
]


def _visible(line):
    return "".join(str(run.get("text", "")) for run in line)


class _FakeTablesPI:
    """PolicyInformation stand-in backed by an arbitrary table dictionary."""

    def __init__(
        self,
        tables,
        policy="U0633187",
        region="CKPR",
        company="ANICO",
        table_errors=None,
    ):
        self._tables = tables
        self._table_errors = table_errors or {}
        self.policy_number = policy
        self.region = region
        self.company_name = company

    def fetch_table(self, table):
        return list(self._tables.get(table, []))

    def table_error(self, table):
        return self._table_errors.get(table, "")


_UE142109_ATM_TRS = {
    "ATM_TRS_TYP_CD": "B",
    "ATM_TRS_SEQ_NBR": 1,
    "INT_GAN_CLC_IND": "0",
    "DFL_STR_DT_ISS_IND": "0",
    "PRC_SUS_IND": "0",
    "ATM_TRS_STR_MY_NBR": 1460,
    "ATM_TRS_SUS_MY_NBR": 0,
    "ATM_TRS_RST_MY_NBR": 0,
    "LST_ACY_MY_NBR": 1519,
    "ATM_TRS_CEA_DT": "2113-07-06",
    "NXT_SCH_ACY_MY_NBR": 1520,
    "ACY_DAY_NBR": 1,
    "ATM_TRS_PRE_MNT_DT": "2021-08-01",
    "DPT_DESK_CD": "SWEEP   ",
    "ATM_TRS_STA_CD": "1",
    "COS_EVT_CD": "     ",
    "COS_ERR_CD": "  ",
    "ATM_TRS_FQY_PER": 1,
    "INT_GEN_IND": "0",
}


class TestSegment53LiveBuild:
    def _screen(self):
        from suiteview.polview.ui import policy_record_viewer as prv

        return prv.load_screen("53")

    def _pi(self, sweep=None, rows=None):
        tables = {
            "LH_ATM_TRS_SCH": [
                dict(row) for row in (rows or [_UE142109_ATM_TRS])
            ],
        }
        if sweep is not None:
            tables["LH_SWF_SCH"] = [sweep]
        return _FakeTablesPI(tables, policy="UE142109")

    def test_moyr_conversion_and_zero_sentinel(self):
        assert prb._seg53_moyr(0) == "00/1900"
        assert prb._seg53_moyr(1) == "01/1900"
        assert prb._seg53_moyr(12) == "12/1900"
        assert prb._seg53_moyr(13) == "01/1901"
        assert prb._seg53_moyr(1460) == "08/2021"
        assert prb._seg53_moyr(1519) == "07/2026"
        assert prb._seg53_moyr(1520) == "08/2026"

    def test_body_matches_ue142109_reference_screen(self):
        screen = self._screen()
        lines = prb.build_segment_lines("53", self._pi(), screen)
        assert lines is not None
        assert _visible(lines[0]) == _visible(screen["lines"][0])
        assert [_visible(lines[i]) for i in range(1, 4)] == [
            _visible(screen["lines"][i]) for i in range(1, 4)
        ]

    def test_unavailable_values_are_explicit_examples(self):
        lines = prb.build_segment_lines("53", self._pi(), self._screen())
        examples = {
            run["field"]
            for line in lines
            for run in line
            if run.get("example")
        }
        assert set(prb._SEG53_FLAGS) <= examples
        assert {"Charge Override", "Charge Amount"} <= examples
        assert {
            "Sweep Fund Minimum Balance",
            "Sweep Frequency",
            "Sweep Day",
            "Sweep Month",
        } <= examples
        assert "Automatic Transaction Type" not in examples
        assert "Start Date" not in examples

    def test_available_sweep_row_renders_live(self):
        sweep = {
            "ATM_TRS_TYP_CD": "B",
            "ATM_TRS_SEQ_NBR": 1,
            "SWEEP_MIN_BALANCE": "234.50",
            "SWEEP_FREQUENCY": "Q",
            "SWEEP_DAY": 15,
            "SWEEP_MONTH": 2,
        }
        lines = prb.build_segment_lines("53", self._pi(sweep), self._screen())
        tokens = {
            run["field"]: run
            for line in lines
            for run in line
            if run.get("field")
        }
        assert tokens["Sweep Fund Minimum Balance"]["text"] == "234.50"
        assert tokens["Sweep Frequency"]["text"] == "Q"
        assert tokens["Sweep Day"]["text"] == "15"
        assert tokens["Sweep Month"]["text"] == "2"
        assert not tokens["Sweep Fund Minimum Balance"].get("example")

    def test_sweep_values_only_come_from_sweep_redefine(self):
        pi = self._pi()
        pi._tables["LH_ASSET_RAL_SCH"] = [{
            "ATM_TRS_TYP_CD": "B",
            "ATM_TRS_SEQ_NBR": 1,
            "LST_RAL_VAL_AMT": "999.99",
        }]
        pi._tables["LH_AWD_SCH"] = [{
            "ATM_TRS_TYP_CD": "B",
            "ATM_TRS_SEQ_NBR": 1,
            "AWD_FQY_PER": "Q",
        }]
        lines = prb.build_segment_lines("53", pi, self._screen())
        tokens = {
            run["field"]: run
            for line in lines
            for run in line
            if run.get("field")
        }
        assert tokens["Sweep Fund Minimum Balance"]["text"] == "199.80"
        assert tokens["Sweep Frequency"]["text"] == "M"
        assert tokens["Sweep Fund Minimum Balance"]["example"]
        assert tokens["Sweep Frequency"]["example"]

    def test_sweep_access_error_is_in_example_warning(self):
        pi = _FakeTablesPI(
            {"LH_ATM_TRS_SCH": [dict(_UE142109_ATM_TRS)]},
            policy="UE142109",
            table_errors={"LH_SWF_SCH": "SQLCODE=-551 SELECT is not authorized"},
        )
        lines = prb.build_segment_lines("53", pi, self._screen())
        sweep = next(
            run
            for line in lines
            for run in line
            if run.get("field") == "Sweep Fund Minimum Balance"
        )
        assert sweep["example"]
        assert "LH_SWF_SCH" in sweep["note"]
        assert "SQLCODE=-551" in sweep["note"]

    def test_multiple_sweep_records_sort_by_type_and_sequence(self):
        sequence_two = dict(_UE142109_ATM_TRS, ATM_TRS_SEQ_NBR=2)
        sequence_one = dict(_UE142109_ATM_TRS, ATM_TRS_SEQ_NBR=1)
        lines = prb.build_segment_lines(
            "53",
            self._pi(rows=[sequence_two, sequence_one]),
            self._screen(),
        )
        sequences = [
            run["text"]
            for line in lines
            for run in line
            if run.get("field") == "Automatic Transaction Sequence"
        ]
        assert sequences == ["1", "2"]

    def test_every_live_token_has_hover_mapping(self):
        screen = self._screen()
        fields = screen["fields"]
        structural = {
            "Screen Name", "Policy Number", "Segment Identification",
            "Segment Length", "Current Date", "Part of the user ID?",
            "Region and Company",
        }
        for line in prb.build_segment_lines("53", self._pi(), screen):
            for run in line:
                name = run.get("field")
                if name and name not in structural:
                    assert name in fields, (
                        f"live token {name!r} missing from fields map"
                    )

    def test_corrected_cyberdoc_and_sweep_mappings_ship(self):
        fields = self._screen()["fields"]
        assert "COBOL: FAUATTYP-AUTO-TRANS-TYPE" in (
            fields["Automatic Transaction Type"]
        )
        assert "COBOL: FAUATSQ-AUTO-TRANS-SEQ" in (
            fields["Automatic Transaction Sequence"]
        )
        assert "COBOL: FAUATPMD-PREV-MAINT-DATE" in (
            fields["Previous Maintenance Date"]
        )
        assert "COBOL: FAUATSEV-SCRIBE-EVENT-CODE" in fields["Event Code"]
        assert "COBOL: FAUATSER-SCRIBE-ERROR-COND" in (
            fields["Error Condition"]
        )
        assert "DB2: LH_SWF_SCH.SWEEP_MIN_BALANCE" in (
            fields["Sweep Fund Minimum Balance"]
        )
        assert "Fequency" not in fields
        assert "Charge Overrider" not in fields

    def test_missing_or_unverified_type_falls_back(self):
        assert prb.build_segment_lines(
            "53", _FakeTablesPI({}), self._screen(),
        ) is None
        unsupported = dict(_UE142109_ATM_TRS, ATM_TRS_TYP_CD="A")
        assert prb.build_segment_lines(
            "53", self._pi(rows=[unsupported]), self._screen(),
        ) is None


_UE142109_GEN_FND_RLE = {
    "MVA_APP_IND": "0",
    "ALW_TRF_CD": "1",
    "TRF_CRG_TBL_CD": "00",
    "TRF_CRG_RLE_1_CD": "0",
    "TRF_CRG_RLE_2_CD": "0",
    "MIN_TRF_AMT": "0.00",
    "MAX_TRF_NBR": 999,
    "MIN_TRF_FQY_PER": 1,
    "TRF_FQY_RLE_CD": "1",
    "LST_FND_TRF_DT": "2026-07-01",
    "CRG_DSB_CD": "2",
    "MAX_ALC_FND_NBR": 999,
    "MAX_ALC_CHG_NBR": 999,
    "ALC_CHG_FQY_PER": 0,
    "MIN_ALC_PCT": "0.00",
    "ALC_MIN_BAL_RLE_CD": "0",
    "UNBUNDLED_IND": " ",
    "ME_BAND": None,
    "INDEX_LN_FUND": "1",
}

_SEG56_UE142109_EXPECTED = [
    (
        "  56  0098  00000000  00000000  00000000  00000000  1  00  "
        "0  0  .00  999  1  1  07/01/2026  2  "
    ),
    (
        "            999  999  0  .00  0                      .000  "
        ".00000        .000     .000        .000     .000  "
    ),
    "                                          1  ",
]


class TestSegment56LiveBuild:
    def _screen(self):
        from suiteview.polview.ui import policy_record_viewer as prv

        return prv.load_screen("56")

    def _pi(self, mva=None):
        tables = {"LH_GEN_FND_RLE": [dict(_UE142109_GEN_FND_RLE)]}
        if mva is not None:
            tables["LH_MKT_VAL_ADJ_RLE"] = [mva]
        return _FakeTablesPI(tables, policy="UE142109")

    def test_body_matches_ue142109_screen(self):
        lines = prb.build_segment_lines("56", self._pi(), self._screen())
        assert lines is not None
        assert _visible(lines[0]).strip() == "6256,  UE142109"
        assert [_visible(lines[i]) for i in range(1, 4)] == (
            _SEG56_UE142109_EXPECTED
        )

    def test_shipped_reference_is_ue142109_capture(self):
        screen = self._screen()
        assert "UE142109 CyberLife capture" in screen["source"]
        assert _visible(screen["lines"][0]).strip().startswith(
            "6256,  UE142109"
        )
        assert [_visible(screen["lines"][i]) for i in range(1, 4)] == (
            _SEG56_UE142109_EXPECTED
        )

    def test_flags_and_absent_mva_values_are_example(self):
        lines = prb.build_segment_lines("56", self._pi(), self._screen())
        examples = {
            run["field"]
            for line in lines
            for run in line
            if run.get("example")
        }
        assert {"Flag Byte A", "Flag Byte B", "Flag Byte C", "User Flag Byte"} <= examples
        assert "MVA User Multiplicitive Adjustment Factor" in examples
        assert "MVA Positive Limit Percent" in examples
        assert "Allowed Transers" not in examples
        assert "Index Loan Fund Indicator" not in examples
        notes = {
            run["field"]: run.get("note")
            for line in lines
            for run in line
            if run.get("example")
        }
        assert "no LH_MKT_VAL_ADJ_RLE row" in notes[
            "MVA User Multiplicitive Adjustment Factor"
        ]

    def test_present_mva_row_renders_live(self):
        mva = {
            "MVA_DTH_BNF_RLE_CD": "1",
            "MVA_LN_RLE_CD": "0",
            "MVA_ANU_PUR_RLE_CD": "1",
            "FND_MT_DT_RLE_CD": "0",
            "DFL_REIV_OPT_CD": "1",
            "MVA_ITS_MTH_CD": "4",
            "MUL_MVA_FCT": "1.250",
            "ADD_MVA_FCT": "1250",
            "MVA_IRT_CLC_RLE_CD": "1",
            "FRE_FUL_SRD_RLE_CD": "1",
            "FUL_SRD_PCT": "10.000",
            "FRE_PAT_WTD_RLE_CD": "1",
            "PAT_WTD_PCT": "5.000",
            "FRE_AMT_ALW_CD": "P",
            "MVA_NEG_LIM_RLE_CD": "2",
            "MVA_NEG_LIM_PCT": "20.000",
            "MVA_PTV_RTT_RLE_CD": "2",
            "MVA_PTV_LIM_PCT": "20.000",
            "MVA_TRUE_UP_IND": "1",
            "MVA_IDX_SER_NBR": "MVA09",
        }
        lines = prb.build_segment_lines("56", self._pi(mva), self._screen())
        tokens = {
            run["field"]: run
            for line in lines
            for run in line
            if run.get("field")
        }
        assert tokens["MVA Death Benefit Rule"]["text"] == "1"
        assert tokens["MVA User Multiplicitive Adjustment Factor"]["text"] == "1.250"
        assert tokens["MVA Positive Limit Percent"]["text"] == "20.000"
        assert not tokens["MVA Positive Limit Percent"].get("example")

    def test_every_live_token_has_hover_mapping(self):
        screen = self._screen()
        lines = prb.build_segment_lines("56", self._pi(), screen)
        structural = {
            "Screen Name", "Policy Number", "Segment Identification",
            "Segment Length", "Current Date", "Part of the user ID?",
            "Region and Company",
        }
        for line in lines:
            for run in line:
                name = run.get("field")
                if name and name not in structural:
                    assert name in screen["fields"], (
                        f"live token {name!r} missing from fields map"
                    )

    def test_no_general_fund_row_falls_back(self):
        assert (
            prb.build_segment_lines(
                "56", _FakeTablesPI({}), self._screen(),
            )
            is None
        )


_U0633187_TAMRA_SCREENSHOT_PERIOD = {
    "GDF_SVPY_TES_IND": "0",
    "GDF_GDL_PRM_IND": "0",
    "MAT_CHG_IND": "0",
    "SVPY_PRM_CLC_IND": "1",
    "REVERSE_TO_ISS_IND": "0",
    "OVR_MEC_IND": "0",
    "MEC_STA_CD": "2",
    "TAMRA_SST_RT_CD": "0",
    "TAMRA_MEC_EFF_DT": "9999-12-31",
    "SVPY_PER_STR_DT": "2012-06-10",
    "SVPY_NXT_CHG_DT": "9999-12-31",
    "SVPY_LVL_PRM_AMT": "3513.71",
    "SVPY_WDW_PRM_AMT": None,
    "TAMRA_ITS_RT": "0.000",
    "TAMRA_GUA_PER": 0,
    "SVPY_BEG_FCE_AMT": "100000.00",
    "SVPY_BEG_CSV_AMT": None,
    "GDF_DTH_BNF_1_AMT": None,
    "GDF_DTH_BNF_2_AMT": None,
    "XCG_1035_PMT_QTY": None,
}
_U0633187_TAMRA_SCREENSHOT_PAID = [
    "2889.00", "2782.00", "2782.00", "2568.00", "1177.00", "0.00", "0.00",
]
_U0633187_TAMRA_PERIOD = {
    **_U0633187_TAMRA_SCREENSHOT_PERIOD,
    "SVPY_LVL_PRM_AMT": "3459.99",
    "SVPY_BEG_FCE_AMT": "98210.00",
}
_U0633187_TAMRA_PAID = [
    "2889.00", "2782.00", "2782.00", "2568.00",
    "2568.00", "1605.00", "1712.00",
]

_SEG59_U063_SCREENSHOT_EXPECTED = [
    (
        "59  0191  00010000  00000000  00000000  1  2  0  "
        "**/**/****  06/10/2012  **/**/****"
    ),
    (
        "3513.71  .00  .000  0  100000.00  .00  .00  .00  "
        "2889.00  .00  2782.00  .00"
    ),
    (
        "2782.00  .00  2568.00  .00  1177.00  .00  .00  .00  "
        ".00  .00  0"
    ),
]

_SEG59_U063_CURRENT_EXPECTED = [
    (
        "59  0191  00010000  00000000  00000000  1  2  0  "
        "**/**/****  06/10/2012  **/**/****"
    ),
    (
        "3459.99  .00  .000  0  98210.00  .00  .00  .00  "
        "2889.00  .00  2782.00  .00"
    ),
    (
        "2782.00  .00  2568.00  .00  2568.00  .00  1605.00  "
        "1790.00  1712.00  .00  0"
    ),
]


class TestSegment59LiveBuild:
    def _pi(self, period, paid, policy, sixth_withdrawal="0.00"):
        years = [
            {
                "SVPY_YR_SEQ_NBR": year,
                "SVPY_PRM_PAY_AMT": amount,
                "SVPY_WTD_AMT": sixth_withdrawal if year == 6 else "0.00",
            }
            for year, amount in enumerate(paid, start=1)
        ]
        return _FakeTablesPI(
            {
                "LH_TAMRA_7_PY_PER": [dict(period)],
                "LH_TAMRA_7_PY_YR": years,
            },
            policy=policy,
        )

    def _screenshot(self):
        return self._pi(
            _U0633187_TAMRA_SCREENSHOT_PERIOD,
            _U0633187_TAMRA_SCREENSHOT_PAID,
            "U0633187",
        )

    def _u063(self):
        return self._pi(
            _U0633187_TAMRA_PERIOD,
            _U0633187_TAMRA_PAID,
            "U0633187",
            "1790.00",
        )

    def test_body_matches_u0633187_reference_screen(self):
        lines = prb.build_segment_lines("59", self._screenshot())
        assert _visible(lines[0]).strip() == "6259,  U0633187"
        assert [_visible(lines[i]).strip() for i in range(1, 4)] == (
            _SEG59_U063_SCREENSHOT_EXPECTED
        )

    def test_shipped_reference_is_u0633187_capture(self):
        from suiteview.polview.ui import policy_record_viewer as prv

        screen = prv.load_screen("59")
        assert "U0633187" in screen["source"]
        assert _visible(screen["lines"][0]).strip().startswith(
            "6259,  U0633187"
        )
        assert [
            _visible(screen["lines"][i]).strip() for i in range(1, 4)
        ] == _SEG59_U063_SCREENSHOT_EXPECTED

    def test_body_matches_u0633187_live_data(self):
        lines = prb.build_segment_lines("59", self._u063())
        assert _visible(lines[0]).strip() == "6259,  U0633187"
        assert [_visible(lines[i]).strip() for i in range(1, 4)] == (
            _SEG59_U063_CURRENT_EXPECTED
        )

    def test_only_unavailable_flag_bytes_are_example(self):
        lines = prb.build_segment_lines("59", self._u063())
        examples = {
            run["field"]
            for line in lines
            for run in line
            if run.get("example")
        }
        assert {"Flag Byte B", "Flag Byte U"} <= examples
        assert "Flag Byte A" not in examples
        assert "7-Pay Level Premium" not in examples

    def test_missing_year_row_is_explicit_example_data(self):
        pi = self._u063()
        pi._tables["LH_TAMRA_7_PY_YR"].pop()
        lines = prb.build_segment_lines("59", pi)
        examples = {
            run["field"]
            for line in lines
            for run in line
            if run.get("example")
        }
        assert "7-Pay Premiums Paid [7]" in examples
        assert "7-Pay Withdrawals [7]" in examples

    def test_every_live_token_has_hover_mapping(self):
        from suiteview.polview.ui import policy_record_viewer as prv

        fields = prv.load_screen("59")["fields"]
        structural = {
            "Screen Name", "Policy Number", "Segment Identification",
            "Segment Length", "Current Date", "Part of the user ID?",
            "Region and Company",
        }
        for line in prb.build_segment_lines("59", self._u063()):
            for run in line:
                name = run.get("field")
                if name and name not in structural:
                    assert name in fields, (
                        f"live token {name!r} missing from fields map"
                    )

    def test_1035_source_and_no_period_fallback(self):
        from suiteview.polview.ui import policy_record_viewer as prv

        source = prv.load_screen("59")["fields"]["1035 Exchange Information"]
        assert "DB2: LH_TAMRA_7_PY_PER.XCG_1035_PMT_QTY" in source
        assert prb.build_segment_lines("59", _FakeTablesPI({})) is None


class TestSegment66LiveBuild:
    def test_body_matches_reference_screen(self):
        pi = _FakePI([dict(_U0361148_NTP)])
        lines = prb.build_segment_lines("66", pi)
        assert lines is not None
        # Line 0 = screen name + policy; lines 1..6 = header + five wrapped rows.
        assert _visible(lines[0]).strip() == "6266,  U0361148"
        for i, expected in enumerate(_SEG66_EXPECTED, start=1):
            assert _visible(lines[i]).strip() == expected, (
                f"seg 66 line {i} mismatch:\n got: {_visible(lines[i]).strip()!r}\n"
                f"want: {expected!r}"
            )

    def test_flag_bytes_and_tail_fields_are_example(self):
        pi = _FakePI([dict(_U0361148_NTP)])
        lines = prb.build_segment_lines("66", pi)
        example_fields = {
            run["field"]
            for line in lines
            for run in line
            if run.get("example")
        }
        assert "Flag Byte A" in example_fields
        assert "User Flag Byte" in example_fields
        assert "Freeze Net Amount at Risk" in example_fields
        assert "Reserved Decrease Rule Code" in example_fields
        # Real DB2-sourced values are never flagged as example data.
        assert "Maturity Date" not in example_fields
        assert "Net Amount at Risk" not in example_fields

    def test_every_token_field_is_in_fields_map(self):
        from suiteview.polview.ui import policy_record_viewer as prv

        fields = prv.load_screen("66")["fields"]
        pi = _FakePI([dict(_U0361148_NTP)])
        for line in prb.build_segment_lines("66", pi):
            for run in line:
                name = run.get("field")
                if name:
                    assert name in fields, f"live token {name!r} missing from fields map"

    def test_no_advanced_record_falls_back(self):
        # A traditional policy (no LH_NON_TRD_POL row) yields no live lines, so
        # the viewer falls back to the captured-reference screen.
        assert prb.build_segment_lines("66", _FakePI([])) is None


# Two real coverage phases of U0361148 (base 35DMP + rider 34LMP), exactly as
# DB2 returns each LH_COV_PHA row -- limited to the columns the seg-02 builder
# reads (see tools/policyrecord/extract_seg02_fixture.py).  Frozen here so the whole seg-02
# mapping + per-coverage loop + blank-collapse rules are verified against the
# known-good 6202 screen (img_002).
_U0361148_COV1 = {
    "ADJ_ETI_CD": "0", "AGE_CLC_RLE_CD": "1", "AGE_SRC_CD": "9", "AGE_USE_CD": "0",
    "AGT_COM_PHA_NBR": 1, "ANN_PRM_UNT_AMT": "0.13", "BAN_STRUCTURE_CD": "B ",
    "CEA_REA_CD": " ", "COM_BAS_CD": "1", "COM_PLN_GRP_CD": "185",
    "COM_PLN_VTN_CD": " ", "COM_RLE_CD": "0", "COV_MED_CD": "0",
    "COV_MT_EXP_DT": "2070-08-15", "COV_NFO_CD": "0", "COV_PHA_NBR": 1,
    "COV_UNT_QTY": "100.000", "COV_VPU_AMT": "1000.00", "CSH_VAL_YR": 0,
    "DCA_TRM_ITS_RT": None, "DCA_TRM_LVL_YR_DUR": None, "DCA_TRM_VPU_CUM_CD": " ",
    "DFI_CD": "0", "DIV_PTP_TYP_CD": "1", "DTH_BNF_EFF_AGE": 0,
    "EFF_DT_OVERRIDE_CD": " ", "EI_BNF_CD": "0", "EI_INT_AMT_CD": "0",
    "ETR_SRC_CD": "Z", "FTD_RID_AT_RSK_AMT": None, "FTD_RID_CDR_AMT": 0,
    "FTD_RID_PLN_OPT_CD": " ", "GUA_ISS_IND": "0", "IAF_KEY_VERSION_CD": " ",
    "IDT_PRM_GUA_PER": 0, "INS_CLS_CD": "1", "INS_ISS_AGE": 23, "INS_SEX_CD": "1",
    "INT_RNL_PER": 0, "ISSUE_DT": "1998-08-15", "JNT_ISU_ISS_AGE": None,
    "JNT_ISU_MTL_TBL_CD": "  ", "LIF_PLN_SUB_SRE_CD": "MP", "LIVES_COV_CD": "0",
    "LNG_TRM_CLM_TYP_CD": " ", "LOW_DUR_PER": None, "MAJ_LIN_OF_BUS_CD": "0",
    "MDRT_CD": " ", "MEC_STA_CD": "2", "MTL_FCT_TBL_CD": "L0", "MTL_FUN_CD": "2",
    "NBR_OF_LIVES_CD": "1", "NSP_EI_TBL_CD": "LA", "NSP_ITS_RT": None,
    "NSP_RPU_TBL_CD": "L0", "NXT_CHG_DT": "2070-08-15", "NXT_CHG_TYP_CD": "2",
    "OGN_SPC_UNT_QTY": "100.000", "PAY_UP_DT": "2070-08-15",
    "PDF_KEY_EFF_DT": "1997-12-04", "PDF_KEY_VERSION_CD": "A    ",
    "PLN_BSE_SRE_CD": "35D", "PLN_DES_SER_CD": "1U135D00   ",
    "POL_FRM_NBR": "UL96     ", "PRD_LIN_TYP_CD": "U", "PRD_PCT": "1.0000",
    "PRD_VAL_USE_CD": "2", "PREMIUM_RESID_CD": "0", "PRS_CD": "00",
    "PRS_SEQ_NBR": 1, "REFRESH_OR_RNL_AGE": 51, "RENEWABLE_PRM_CD": " ",
    "RES_ITS_RT": "4.000", "RET_OF_PRM_CD": "0", "RET_PRM_UNT_AMT": None,
    "RID_COI_BAN_RLE_CD": "3", "RID_STA_CD": "0", "RID_XPN_RLE_CD": "0",
    "RPU_BNF_CD": "0", "RT_BK_CD": "1U", "SBQ_RNL_PER": 0, "SBQ_RNL_STR_DUR": 0,
    "TRUE_AGE": 23, "UNISEX_GUA_RT_CD": " ", "UNISEX_OVR_CD": "0",
    "UNISEX_SEX_CD": " ", "UNISEX_SSR_CD": "  ", "VAL_MTH_CD": "3",
    "VAL_TBL_RFR_CD": "U1", "VAL_USE_CD": "0",
}
_U0361148_COV2 = {
    "ADJ_ETI_CD": "0", "AGE_CLC_RLE_CD": "1", "AGE_SRC_CD": "9", "AGE_USE_CD": "0",
    "AGT_COM_PHA_NBR": 1, "ANN_PRM_UNT_AMT": "0.13", "BAN_STRUCTURE_CD": "00",
    "CEA_REA_CD": " ", "COM_BAS_CD": "1", "COM_PLN_GRP_CD": "169",
    "COM_PLN_VTN_CD": " ", "COM_RLE_CD": "3", "COV_MED_CD": "0",
    "COV_MT_EXP_DT": "2045-08-15", "COV_NFO_CD": "0", "COV_PHA_NBR": 2,
    "COV_UNT_QTY": "125.000", "COV_VPU_AMT": "1000.00", "CSH_VAL_YR": 0,
    "DCA_TRM_ITS_RT": None, "DCA_TRM_LVL_YR_DUR": None, "DCA_TRM_VPU_CUM_CD": " ",
    "DFI_CD": "0", "DIV_PTP_TYP_CD": "0", "DTH_BNF_EFF_AGE": 0,
    "EFF_DT_OVERRIDE_CD": " ", "EI_BNF_CD": "0", "EI_INT_AMT_CD": "0",
    "ETR_SRC_CD": "Z", "FTD_RID_AT_RSK_AMT": None, "FTD_RID_CDR_AMT": 0,
    "FTD_RID_PLN_OPT_CD": " ", "GUA_ISS_IND": "0", "IAF_KEY_VERSION_CD": " ",
    "IDT_PRM_GUA_PER": 0, "INS_CLS_CD": "5", "INS_ISS_AGE": 23, "INS_SEX_CD": "1",
    "INT_RNL_PER": 0, "ISSUE_DT": "1998-08-15", "JNT_ISU_ISS_AGE": None,
    "JNT_ISU_MTL_TBL_CD": "  ", "LIF_PLN_SUB_SRE_CD": "MP", "LIVES_COV_CD": "0",
    "LNG_TRM_CLM_TYP_CD": " ", "LOW_DUR_PER": None, "MAJ_LIN_OF_BUS_CD": "0",
    "MDRT_CD": " ", "MEC_STA_CD": "2", "MTL_FCT_TBL_CD": "L0", "MTL_FUN_CD": "2",
    "NBR_OF_LIVES_CD": "1", "NSP_EI_TBL_CD": "LA", "NSP_ITS_RT": None,
    "NSP_RPU_TBL_CD": "L0", "NXT_CHG_DT": "2045-08-15", "NXT_CHG_TYP_CD": "2",
    "OGN_SPC_UNT_QTY": "125.000", "PAY_UP_DT": "2045-08-15",
    "PDF_KEY_EFF_DT": "1997-12-04", "PDF_KEY_VERSION_CD": "A    ",
    "PLN_BSE_SRE_CD": "34L", "PLN_DES_SER_CD": "1U534L00   ",
    "POL_FRM_NBR": "ULLT     ", "PRD_LIN_TYP_CD": "U", "PRD_PCT": "0.5000",
    "PRD_VAL_USE_CD": "2", "PREMIUM_RESID_CD": "0", "PRS_CD": "00",
    "PRS_SEQ_NBR": 1, "REFRESH_OR_RNL_AGE": 51, "RENEWABLE_PRM_CD": " ",
    "RES_ITS_RT": "4.000", "RET_OF_PRM_CD": "0", "RET_PRM_UNT_AMT": None,
    "RID_COI_BAN_RLE_CD": "0", "RID_STA_CD": "0", "RID_XPN_RLE_CD": "0",
    "RPU_BNF_CD": "0", "RT_BK_CD": "1U", "SBQ_RNL_PER": 0, "SBQ_RNL_STR_DUR": 0,
    "TRUE_AGE": 23, "UNISEX_GUA_RT_CD": " ", "UNISEX_OVR_CD": " ",
    "UNISEX_SEX_CD": " ", "UNISEX_SSR_CD": "  ", "VAL_MTH_CD": "3",
    "VAL_TBL_RFR_CD": "U1", "VAL_USE_CD": "0",
}

# The visible body of the real 6202 screen: header line + two coverage blocks
# (5 wrapped lines each).  Flag bytes A-D are bit-packed with no single DB2
# column, so they render as amber example "00000000" (excluded from must-match
# semantics but stable here).
_SEG02_EXPECTED = [
    "02  0220  00000000  00000000  00000000  00000000  1  U  0  08/15/2070  2  1  1  L0  1  2  4.000",
    "3  1  35DMP  3  0  0  1  23  23  0  9  0  08/15/1998  08/15/2070  08/15/2070",
    "100.000  1000.00  .000  0  .00  .13  0  0  0  0  0  0  1  0  Z  1U  0  0  0  100.000",
    "0  .00  51  LA  L0  .000  0  00  1  1  2  0  0  0  0  0  0  UL96",
    "1U135D00  A  12/04/1997  185  0  2  1.0000  U1  0  B",
    "02  0220  00000000  00000000  00000000  00000000  2  U  0  08/15/2045  2  1  1  L0  1  2  4.000",
    "3  5  34LMP  0  0  0  1  23  23  0  9  0  08/15/1998  08/15/2045  08/15/2045",
    "125.000  1000.00  .000  0  .00  .13  0  0  0  0  0  0  0  0  Z  1U  0  0  0  125.000",
    "0  .00  51  LA  L0  .000  0  00  1  1  2  0  0  0  0  0  ULLT",
    "1U534L00  A  12/04/1997  169  3  2  .5000  U1  0  00",
]


class TestSegment02LiveBuild:
    def _pi(self):
        return _FakePI([], covpha=[dict(_U0361148_COV1), dict(_U0361148_COV2)])

    def test_body_matches_reference_screen(self):
        lines = prb.build_segment_lines("02", self._pi())
        assert lines is not None
        # Line 0 = screen name + policy; lines 1..10 = two coverage blocks.
        assert _visible(lines[0]).strip() == "6202,  U0361148"
        for i, expected in enumerate(_SEG02_EXPECTED, start=1):
            assert _visible(lines[i]).strip() == expected, (
                f"seg 02 line {i} mismatch:\n got: {_visible(lines[i]).strip()!r}\n"
                f"want: {expected!r}"
            )

    def test_flag_bytes_are_example(self):
        lines = prb.build_segment_lines("02", self._pi())
        example_fields = {
            run["field"] for line in lines for run in line if run.get("example")
        }
        assert {"Flag Byte A", "Flag Byte B", "Flag Byte C", "Flag Byte D"} <= example_fields
        # Real DB2-sourced values are never flagged as example data.
        assert "Number of Units" not in example_fields
        assert "Issue Date" not in example_fields

    def test_every_token_field_is_in_fields_map(self):
        from suiteview.polview.ui import policy_record_viewer as prv

        fields = prv.load_screen("02")["fields"]
        for line in prb.build_segment_lines("02", self._pi()):
            for run in line:
                name = run.get("field")
                if name:
                    assert name in fields, f"live token {name!r} missing from fields map"

    def test_overridden_columns_render_expected_values(self):
        # The five OVERRIDES corrections, checked at the value level.
        lines = prb.build_segment_lines("02", self._pi())
        texts = {run.get("field"): run.get("text")
                 for line in lines for run in line if run.get("field")}
        # idx55 Orig Spec Amount Units -> OGN_SPC_UNT_QTY (not a cash value).
        assert texts["Values-Per-Unit: Orig Spec Amount Units"] == "125.000"
        # idx92 renamed to Percent, sourced from PRD_PCT (4dp).
        assert texts["Production Control Data: Percent"] == ".5000"
        # idx47 Participation Type sourced from DIV_PTP_TYP_CD.
        assert texts["Participation Type"] == "0"

    def test_no_coverage_rows_falls_back(self):
        # A policy with no LH_COV_PHA rows yields no live lines, so the viewer
        # falls back to the captured-reference screen.
        assert prb.build_segment_lines("02", _FakePI([])) is None


class TestFooterNormalization:
    """The terminal footer chrome (date / user id / region) is normalized for
    display: the date is always today, and the user-id and region tokens carry
    no hover popup."""

    def _prv(self):
        from suiteview.polview.ui import policy_record_viewer as prv

        return prv

    def test_current_date_token_is_today(self):
        from datetime import datetime

        prv = self._prv()
        screen = {"lines": [[
            {"text": "10/15/16", "field": "Current Date"},
            {"text": "  ", "field": None},
            {"text": "B7Y02", "field": "Part of the user ID?"},
        ]]}
        out = prv._normalize_footer(screen)
        today = datetime.now().strftime("%m/%d/%y")
        assert out["lines"][0][0]["text"] == today
        assert out["lines"][0][0]["field"] == "Current Date"

    def test_user_and_region_tokens_lose_their_field(self):
        prv = self._prv()
        screen = {"lines": [
            [{"text": "B7Y02", "field": "Part of the user ID?"}],
            [{"text": "CKPR-ANICO", "field": "Region and Company"}],
        ]}
        out = prv._normalize_footer(screen)
        # field cleared -> no tooltip -- but the visible text is preserved.
        assert out["lines"][0][0]["field"] is None
        assert out["lines"][0][0]["text"] == "B7Y02"
        assert out["lines"][1][0]["field"] is None
        assert out["lines"][1][0]["text"] == "CKPR-ANICO"

    def test_other_fields_untouched(self):
        prv = self._prv()
        screen = {"lines": [[
            {"text": "08/15/2070", "field": "Maturity Date"},
        ]]}
        out = prv._normalize_footer(screen)
        assert out["lines"][0][0]["field"] == "Maturity Date"
        assert out["lines"][0][0]["text"] == "08/15/2070"

    def test_no_policy_never_returns_a_captured_screen(self):
        prv = self._prv()
        for seg in ("02", "67"):
            assert prv.build_screen(seg, None) is None

    def test_live_screen_footer_is_normalized(self):
        # The live path (build_segment_lines + _append_screen_footer) is
        # normalized the same way: today's date, no hoverable user/region.
        from datetime import datetime

        prv = self._prv()
        pi = _FakePI([dict(_U0361148_NTP)])
        screen = prv.build_screen("66", pi)
        assert screen.get("live") is True
        today = datetime.now().strftime("%m/%d/%y")
        runs = [run for line in screen["lines"] for run in line]
        assert any(
            r.get("field") == "Current Date" and r["text"] == today for r in runs
        )
        assert not any(
            r.get("field") in ("Part of the user ID?", "Region and Company")
            for r in runs
        )


class TestTooltipNoWrap:
    """Tooltips keep the field name and each source mapping on one line; only
    the not-real-data warning (and note) are allowed to wrap."""

    def _tooltip(self, *args, **kwargs):
        from suiteview.polview.ui.policy_record_viewer import _MainframeToken

        return _MainframeToken._build_tooltip(*args, **kwargs)

    def test_field_name_is_nowrap(self):
        html = self._tooltip("Valuation Code: Base", [])
        assert "<nobr><b>Valuation Code: Base</b></nobr>" in html

    def test_mappings_are_nowrap(self):
        html = self._tooltip(
            "Maturity Date",
            ["COBOL: FULMTDAT-MATURITY-DATE", "DB2: LH_NON_TRD_POL.MT_DT"],
        )
        assert "<nobr>COBOL: FULMTDAT-MATURITY-DATE</nobr>" in html
        assert "<nobr>DB2: LH_NON_TRD_POL.MT_DT</nobr>" in html

    def test_warning_and_note_wrap(self):
        html = self._tooltip(
            "Freeze Net Amount at Risk", [], example=True,
            note="This value is not stored in DB2 for this policy.",
        )
        # The warning banner and the note are NOT wrapped in <nobr> so they can
        # break across lines within the tooltip.
        assert "EXAMPLE DATA" in html
        assert "<nobr>" not in html.split("EXAMPLE DATA")[0]
        assert "<i>This value is not stored in DB2 for this policy.</i>" in html

    def test_db2_error_note_is_html_escaped(self):
        html = self._tooltip(
            "Sweep Fund Minimum Balance",
            ["DB2: LH_SWF_SCH.SWEEP_MIN_BALANCE"],
            example=True,
            note="<class 'pyodbc.Error'> returned an error",
        )
        assert "&lt;class &#x27;pyodbc.Error&#x27;&gt;" in html
        assert "<class 'pyodbc.Error'>" not in html
