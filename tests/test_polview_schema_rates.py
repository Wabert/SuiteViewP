"""PolView Rates views read from UL_Rates schema ``rates`` (polview.models.schema_rates)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt

from suiteview.core.rates_schema import (
    BandSpec, CellAssignment, DivAssignment, DivSchedule, DivValue, PlanAssignment, PlanDef,
    RateSetInfo, RateTypeDef, ScheduleWindow, SubseriesRow,
)
from suiteview.polview.models import schema_rates as sr
from suiteview.polview.services.rate_selection import (
    SCHEMA_BENEFIT, SCHEMA_COVERAGE, SCHEMA_POLICY, SCHEMA_SCALES, build_rate_selection,
)

def D(value) -> Decimal:
    """Rates as stored: decimal(19,8)."""
    return Decimal(str(value)).quantize(Decimal("0.00000001"))


def _plan(company="00", plancode="1U143900", family="UL"):
    return PlanDef(company, plancode, "00", family, "BASE", f"{plancode} test plan", ())


def _cell(rate_type, schedule_id, sex="M", rate_class="N", band="2", state="**", benefit="", subseries=""):
    return CellAssignment(benefit, sex, rate_class, band, state, subseries, rate_type, schedule_id)


class FakeRepo:
    """In-memory stand-in for RatesSchemaRepository."""

    def __init__(self):
        self.plans = {"1U143900": [_plan()]}
        self.bands = [
            BandSpec("1", date(1900, 1, 1), "9", D("49999.9999"), "A"),
            BandSpec("2", date(1900, 1, 1), "9", D("99999.9999"), "B"),
            BandSpec("3", date(1900, 1, 1), "9", D("999999999.9999"), "C"),
        ]
        self.types = {
            "COI": RateTypeDef("COI", "Cost of insurance", "CELL", "per 1000", "CALENDAR", "UL"),
            "SCR": RateTypeDef("SCR", "Surrender charge", "CELL", "per unit", "ISSUE", "UL"),
            "MTP": RateTypeDef("MTP", "Minimum target", "CELL", "per unit", "ISSUE", "UL"),
            "CV": RateTypeDef("CV", "Cash value", "CELL", "per unit", "ISSUE", "WL"),
            "CORR": RateTypeDef("CORR", "Corridor", "PLAN", "multiple", "NONE", "UL"),
            "GINT": RateTypeDef("GINT", "Guaranteed interest", "PLAN", "rate", "NONE", "UL"),
            "LOAN_REG_CHG": RateTypeDef("LOAN_REG_CHG", "Loan", "PLAN", "rate", "NONE", "ALL"),
        }
        self.cells = [
            _cell("COI", 1), _cell("SCR", 2), _cell("MTP", 3),
            _cell("COI", 9, benefit="39"),
        ]
        self.windows = [
            ScheduleWindow(1, "C", date(2000, 1, 1), date(2021, 1, 1), 10),
            ScheduleWindow(1, "C", date(2021, 1, 1), None, 11),
            ScheduleWindow(1, "G", date(2000, 1, 1), None, 12),
            ScheduleWindow(2, "G", date(2000, 1, 1), None, 20),
            ScheduleWindow(3, "G", date(2000, 1, 1), None, 30),
            ScheduleWindow(9, "C", date(2000, 1, 1), None, 90),
        ]
        self.sets = {
            10: RateSetInfo(10, "COI", "IA_DUR", "", ""), 11: RateSetInfo(11, "COI", "IA_DUR", "", ""),
            12: RateSetInfo(12, "COI", "IA_DUR", "", ""), 20: RateSetInfo(20, "SCR", "IA_DUR", "", ""),
            30: RateSetInfo(30, "MTP", "IA", "", ""), 90: RateSetInfo(90, "COI", "IA_DUR", "", ""),
            40: RateSetInfo(40, "CORR", "AA", "", ""), 41: RateSetInfo(41, "GINT", "DUR", "", ""),
            42: RateSetInfo(42, "LOAN_REG_CHG", "SCALAR", "", ""), 43: RateSetInfo(43, "LOAN_REG_CHG", "SCALAR", "", ""),
        }
        self.values = {
            10: {(40, d): D(d) for d in range(1, 4)},
            11: {(40, d): D(100 + d) for d in range(1, 4)},
            12: {(40, d): D(200 + d) for d in range(1, 4)},
            20: {(40, 1): D("37.5"), (40, 2): D("30")},
            30: {(40, 0): D("14.92")},
            90: {(41, 1): D("0.5")},
            40: {(40, 0): D("2.5"), (41, 0): D("2.4"), (42, 0): D("2.3")},
            41: {(0, 1): D("0.03"), (0, 2): D("0.03")},
            42: {(0, 0): D("0.06")},
            43: {(0, 0): D("0.08")},
        }
        self.plan_rows = [
            PlanAssignment("**", "CORR", "G", 40), PlanAssignment("**", "GINT", "G", 41),
            PlanAssignment("**", "LOAN_REG_CHG", "G", 42), PlanAssignment("TX", "LOAN_REG_CHG", "G", 43),
        ]
        self.divs = []
        self.div_rows = []
        self.div_data = {}
        self.subseries = []

    def rate_types(self):
        return self.types

    def plan_defs(self, plancode):
        return self.plans.get(plancode, [])

    def plan_attrs(self, company, plancode):
        return []

    def plan_bands(self, company, plancode):
        return self.bands

    def plan_subseries(self, company, plancode):
        return self.subseries

    def cell_assignments(self, company, plancode):
        return self.cells

    def schedule_windows(self, ids):
        return [w for w in self.windows if w.schedule_id in set(ids)]

    def rate_sets(self, ids):
        return {i: self.sets[i] for i in ids if i in self.sets}

    def rate_values(self, ids, issue_age):
        return {i: dict(self.values.get(i, {})) for i in ids}

    def plan_assignments(self, company, plancode):
        return self.plan_rows

    def div_assignments(self, company, plancode):
        return self.divs

    def div_schedules(self, keys):
        return [s for s in self.div_rows if s.div_key in set(keys)]

    def div_values(self, ids, ages):
        return {i: self.div_data.get(i, {}) for i in ids}

    def fund_assignments(self, company, plancode):
        return []

    def fund_rates(self, keys):
        return []

    def modal_factors(self, company, plancode):
        return []


def _policy(sex="1", rate_class="N", amount=D("75000"), benefits=(), plancode="1U143900", company="01"):
    cov = SimpleNamespace(
        plancode=plancode, issue_date=date(2019, 3, 14), issue_age=40, maturity_date=date(2022, 3, 14),
        face_amount=amount, is_base=True, cov_pha_nbr=1, table_rating_code="",
    )
    return SimpleNamespace(
        policy_number="U1040725", company_code=company,
        coverages=SimpleNamespace(get_coverages=lambda: [cov], base_plancode=plancode,
                                  base_band_specified_amount=amount),
        activity=SimpleNamespace(issue_date=date(2019, 3, 14)),
        product=SimpleNamespace(issue_state="TX"),
        rates=SimpleNamespace(
            cov_rate_sex_code=lambda index: sex,
            renewal_cov_rateclass_by_cov=lambda index: rate_class,
            data_item=lambda table, column, index: "MN",
            fetch_table=lambda name: [{"COV_PHA_NBR": 1, "JT_INS_IND": "0", "PRM_RT_TYP_CD": "C", "RT_BAN_CD": "B"}],
            get_benefit_renewal_rates=lambda phase: [],
        ),
        benefits=SimpleNamespace(get_benefits=lambda: list(benefits)),
        support=SimpleNamespace(reins_partner=""),
        values=SimpleNamespace(get_fund_values_dict=lambda: {}),
    )


def _column(matrix, name):
    index = matrix[0].index(name)
    return [row[index] for row in matrix[1:]]


def _meta(matrix):
    """Metadata by field name; a name listed in several sections joins its values with ' | '."""
    meta = {}
    for row in matrix[1:]:
        name = str(row[0]).strip()
        if name:
            meta[name] = f"{meta[name]} | {row[1]}" if name in meta else row[1]
    return meta


# -- pure helpers ---------------------------------------------------------------------

@pytest.mark.parametrize("code,expected", [("1", "M"), ("2", "F"), (" 2 ", "F"), ("T", "T"), ("u", "U"), ("", "")])
def test_rates_sex_maps_cyberlife_codes_like_the_loaders(code, expected):
    assert sr.rates_sex(code) == expected


def test_resolve_plan_prefers_company_then_rate_user_then_single_company():
    p00, p01, p04 = _plan("00"), _plan("01"), _plan("04")
    assert sr.resolve_plan([p00, p01], "01") == (p01, "")
    plan, note = sr.resolve_plan([p00], "01")
    assert plan is p00 and "rate user of policy company 01" in note
    plan, note = sr.resolve_plan([p04], "26")
    assert plan is p04 and "policy company 26 is not loaded" in note
    plan, note = sr.resolve_plan([p00, p04], "26")
    assert plan is None and "00, 04" in note
    assert sr.resolve_plan([], "01") == (None, "")


def test_band_uses_latest_spec_on_or_before_the_date_and_lowest_fitting_limit():
    bands = [
        BandSpec("1", date(1900, 1, 1), "43", D("99999.9999"), "A"),
        BandSpec("2", date(1900, 1, 1), "43", D("250000.9999"), "B"),
        BandSpec("1", date(2018, 10, 1), "43", D("99999.9999"), "A"),
        BandSpec("2", date(2018, 10, 1), "43", D("249999.9999"), "B"),
        BandSpec("3", date(2018, 10, 1), "43", D("999999999.9999"), "C"),
    ]
    assert sr.band_for_amount(bands, date(2010, 1, 1), 250000)[0].band == "2"
    assert sr.band_for_amount(bands, date(2020, 1, 1), 250000)[0].band == "3"
    assert sr.band_for_amount(bands, date(2020, 1, 1), 50000)[0].band == "1"


def test_band_unbanded_and_limitless_plans():
    unbanded = [BandSpec("0", date(1900, 1, 1), "00", None, "0")]
    spec, note = sr.band_for_amount(unbanded, date(2020, 1, 1), 1)
    assert spec.band == "0" and note == "unbanded"
    limitless = unbanded + [BandSpec("1", date(1900, 1, 1), "00", None, "A")]
    spec, note = sr.band_for_amount(limitless, date(2020, 1, 1), 1)
    assert spec is None and "no limits" in note


def test_choose_cell_exact_then_documented_fallbacks():
    key = sr.RateKey("M", "N", "2", "TX")
    exact = _cell("COI", 1)
    assert sr.choose_cell([exact, _cell("COI", 2, sex="U")], "COI", key) == (exact, [])
    chosen, notes = sr.choose_cell([_cell("COI", 3, sex="U", rate_class="*", band="0")], "COI", key)
    assert chosen.schedule_id == 3
    assert notes == ["sex U (policy M)", "class * (policy N)", "band 0 (policy 2)"]
    state_rows = [_cell("COI", 4), _cell("COI", 5, state="TX")]
    chosen, notes = sr.choose_cell(state_rows, "COI", key)
    assert chosen.schedule_id == 5 and notes == ["state TX"]


def test_choose_cell_reports_what_is_loaded_when_nothing_matches():
    chosen, notes = sr.choose_cell([_cell("COI", 1, sex="F", rate_class="S")], "COI", sr.RateKey("M", "N", "2", "TX"))
    assert chosen is None
    assert "no cell for M/N/2" in notes[0] and "loaded sex F, class S, band 2" in notes[0]


def test_choose_cell_sub_series_keyed_rows_use_the_coverage_sub_series():
    rows = [_cell("CV", 1, sex="F", band="0", subseries="FN"), _cell("CV", 2, sex="M", band="0", subseries="MN")]
    chosen, notes = sr.choose_cell(rows, "CV", sr.RateKey("M", "N", "2", "TX", "MN"))
    assert chosen.schedule_id == 2 and notes == ["sub-series MN", "band 0 (policy 2)"]
    mapped = [SubseriesRow("M", "N", "MN", "00-1-1C4-MN")]
    chosen, notes = sr.choose_cell(rows, "CV", sr.RateKey("M", "N", "0", "TX", ""), mapped)
    assert chosen.schedule_id == 2 and notes[0] == "sub-series MN from PLAN_SUBSERIES"
    chosen, notes = sr.choose_cell(rows, "CV", sr.RateKey("M", "N", "0", "TX", "ZZ"))
    assert chosen is None and "loaded FN, MN" in notes[0]


@pytest.mark.parametrize("grain,values,year,point,expected", [
    ("IA_DUR", {(40, 3): 1}, 3, False, 1),
    ("IA_DUR", {(40, 2): 1}, 3, True, 1),
    ("DUR", {(0, 3): 1}, 3, False, 1),
    ("AA", {(42, 0): 1}, 3, False, 1),
    ("IA", {(40, 0): 1}, 7, False, 1),
    ("SCALAR", {(0, 0): 1}, 7, False, 1),
])
def test_rate_at_reads_each_grain(grain, values, year, point, expected):
    assert sr.rate_at(grain, values, 40, year, point) == expected


# -- matrices -------------------------------------------------------------------------

def test_coverage_matrix_places_rates_by_structure_scale_and_date_meaning():
    matrix = sr.build_coverage_matrix(FakeRepo(), _policy(), 1)
    assert matrix[0][:5] == ["RateFields", "RateInfo", "Date", "Age", "Year"]
    assert matrix[0][5:] == ["C COI", "G COI", "G SCR"]
    # CALENDAR: each row's Date picks the COI C window (2021-01-01 split).
    assert _column(matrix, "C COI")[:3] == ["1.00", "2.00", "103.00"]
    assert _column(matrix, "G COI")[:3] == ["201.00", "202.00", "203.00"]
    # ISSUE, issue age x duration: a column; blank past the schedule.
    assert _column(matrix, "G SCR")[:3] == ["37.50", "30.00", ""]
    meta = _meta(matrix)
    assert meta["Single rates (G)"] == "" and meta["MTP"] == "14.92"
    assert meta["Band"] == "2" and meta["System Band"] == "B"
    assert meta["Sex"] == "M"


def test_coverage_matrix_keeps_business_metadata_only():
    names = {str(row[0]).strip() for row in sr.build_coverage_matrix(FakeRepo(), _policy(), 1)[1:]}
    assert {"Policy", "Plancode", "Sex", "Rateclass", "Band", "System Band", "State"} <= names
    assert not names & {"Source", "Rates company", "Description", "Leaf", "Cells used", "Dated schedules",
                        "Stored band", "Scales"}


def test_system_band_flags_a_policy_record_that_differs():
    policy = _policy()
    policy.rates.fetch_table = lambda name: [{"COV_PHA_NBR": 1, "JT_INS_IND": "0", "PRM_RT_TYP_CD": "C",
                                              "RT_BAN_CD": "C"}]
    meta = _meta(sr.build_coverage_matrix(FakeRepo(), policy, 1))
    assert meta["Band"] == "2" and meta["System Band"] == "B (policy record C)"


def test_columns_group_all_current_then_guaranteed_then_shadow_then_dividends():
    cols = [sr.Column("G", "SCR", None), sr.Column("Dividend", "DIV", None), sr.Column("S", "COI", None),
            sr.Column("C", "EPU", None), sr.Column("G", "COI", None), sr.Column("C", "COI", None),
            sr.Column("Dividend", "PUA", None)]
    assert [c.key for c in sr.ordered_columns(cols)] == [
        "C COI", "C EPU", "G COI", "G SCR", "S COI", "Dividend DIV", "Dividend PUA"]
    labels, groups = sr.column_layout(["RateFields", "Year", "C COI", "C EPU", "G COI", "Dividend RPU DIV"])
    assert labels == {"C COI": "COI", "C EPU": "EPU", "G COI": "COI", "Dividend RPU DIV": "DIV"}
    assert groups == [("C", ["C COI", "C EPU"]), ("G", ["G COI"]), ("Dividend RPU", ["Dividend RPU DIV"])]


def test_scales_sheet_lists_every_scale_window_with_its_policy_years_and_cell():
    matrix = sr.build_scales_matrix(FakeRepo(), _policy())
    assert matrix[0] == sr.SCALES_HEADER
    rows = [dict(zip(matrix[0], row)) for row in matrix[1:]]
    summary = [(r["Rate Type"], r["Scale"], r["Effective From"], r["Effective To"], r["Policy Years"])
               for r in rows]
    assert summary == [
        ("COI", "C", "2000-01-01", "2021-01-01", "1-2"),
        ("COI", "C", "2021-01-01", "open", "3"),
        ("COI", "G", "2000-01-01", "open", "1-3"),
        ("SCR", "G", "2000-01-01", "open", "all (issue date)"),
        ("MTP", "G", "2000-01-01", "open", "all (issue date)"),
    ]
    assert {r["Coverage"] for r in rows} == {"Cov 01"}
    assert rows[0]["Cell"] == "M/N/2/**" and rows[0]["Rates By"] == "each policy year's date"
    assert rows[3]["Rates By"] == "issue date" and rows[0]["Scale Name"] == "Current"


def test_scales_sheet_shows_fallbacks_and_missing_cells():
    repo = FakeRepo()
    repo.cells = [_cell("COI", 1, sex="U", band="0"), _cell("CV", 7, sex="F")]
    rows = [dict(zip(sr.SCALES_HEADER, row)) for row in sr.build_scales_matrix(repo, _policy())[1:]]
    assert rows[0]["Notes"] == "sex U (policy M); band 0 (policy 2)"
    assert rows[-1]["Rate Type"] == "CV" and rows[-1]["Notes"].startswith("Missing: no cell for M/N/2")


def test_coverage_matrix_marks_missing_windows_and_cells():
    repo = FakeRepo()
    repo.windows = [w if w.schedule_id != 1 or w.scale != "G" else
                    ScheduleWindow(1, "G", date(2021, 1, 1), None, 12) for w in repo.windows]
    repo.cells.append(_cell("CV", 7, sex="F"))
    matrix = sr.build_coverage_matrix(repo, _policy(), 1)
    assert _column(matrix, "G COI")[:3] == ["NA", "NA", "203.00"]
    assert "no cell for M/N/2" in _meta(matrix)["CV"]


def test_uncovered_issue_date_for_an_issue_rate_is_missing_not_blank():
    repo = FakeRepo()
    repo.windows = [w if w.schedule_id != 3 else ScheduleWindow(3, "G", date(2020, 1, 1), None, 30)
                    for w in repo.windows]
    meta = _meta(sr.build_coverage_matrix(repo, _policy(), 1))
    assert "G MTP" in meta and "no window covers issue date 2019-03-14" in meta["G MTP"]


def test_point_in_time_cash_values_show_duration_n_minus_1():
    repo = FakeRepo()
    repo.cells = [_cell("CV", 5, band="0", subseries="MN")]
    repo.windows = [ScheduleWindow(5, "G", date(1900, 1, 1), None, 50)]
    repo.sets[50] = RateSetInfo(50, "CV", "IA_DUR", "", "")
    repo.values[50] = {(40, 0): D("0"), (40, 1): D("15"), (40, 2): D("31")}
    matrix = sr.build_coverage_matrix(repo, _policy(), 1)
    assert _column(matrix, "G CV")[:3] == ["0.00", "15.00", "31.00"]


def test_not_loaded_plancode_names_the_legacy_view():
    repo = FakeRepo()
    repo.plans = {}
    with pytest.raises(sr.RatesNotLoaded, match="not loaded in UL_Rates schema rates yet.*Legacy"):
        sr.build_coverage_matrix(repo, _policy(), 1)


def _benefit(code="39", phase=1):
    return SimpleNamespace(
        cov_pha_nbr=phase, benefit_code=code, benefit_type_cd=code[0], benefit_subtype_cd=code[1:],
        benefit_desc=code[0], issue_date=date(2020, 3, 14), issue_age=41, cease_date=date(2022, 3, 14),
    )


def test_benefit_matrix_reads_the_benefit_cells_on_its_coverage_plancode():
    matrix = sr.build_benefit_matrix(FakeRepo(), _policy(benefits=[_benefit()]), 1)
    assert matrix[0][5:] == ["C COI"]
    assert _column(matrix, "C COI")[0] == "0.50"
    assert _meta(matrix)["Benefit"].startswith("39")


def test_benefit_renewal_class_0_keeps_the_coverage_class():
    policy = _policy(benefits=[_benefit()])
    policy.rates.get_benefit_renewal_rates = lambda phase: [SimpleNamespace(
        benefit_type="3", benefit_subtype="9", joint_indicator="0", rate_class="0")]
    ctx = sr.benefit_context(FakeRepo(), policy, 1)
    assert ctx.key.rate_class == "N"
    assert _meta(sr.build_benefit_matrix(FakeRepo(), policy, 1))["Class source"] == "coverage"


def test_benefit_not_loaded_lists_the_loaded_benefits():
    with pytest.raises(sr.RatesNotLoaded, match=r"benefit #4 .*loaded benefits: 39"):
        sr.build_benefit_matrix(FakeRepo(), _policy(benefits=[_benefit("#4")]), 1)


def test_policy_matrix_plan_rates_state_first_single_values_and_attained_age():
    matrix = sr.build_policy_matrix(FakeRepo(), _policy())
    assert matrix[0][:5] == ["RateFields", "RateInfo", "Date", "AttainedAge", "Year"]
    assert matrix[0][5:] == ["G CORR", "G GINT"]
    assert _column(matrix, "G CORR")[:3] == ["2.50", "2.40", "2.30"]
    assert _column(matrix, "G GINT")[:3] == ["0.03", "0.03", ""]
    meta = _meta(matrix)
    assert meta["LOAN_REG_CHG"] == "0.08"  # TX row wins over **
    assert not {"Source", "Rates company", "Description"} & set(meta)


def test_dividends_use_the_cohort_and_each_rows_scale_window():
    repo = FakeRepo()
    repo.divs = [DivAssignment("M", "N", "0", "**", "", "11E1MN", "")]
    repo.div_rows = [
        DivSchedule("11E1MN", "", "D", date(1900, 1, 1), date(1900, 1, 1), date(2021, 1, 1), 70, "1", None, None),
        DivSchedule("11E1MN", "", "D", date(1900, 1, 1), date(2021, 1, 1), None, 71, "1", None, None),
    ]
    repo.div_data = {70: {(40, 1): DivValue(D("1"), None, None), (40, 2): DivValue(D("2"), None, None)},
                     71: {(40, 3): DivValue(D("30"), None, None)}}
    matrix = sr.build_coverage_matrix(repo, _policy(), 1)
    assert matrix[0][-1] == "Dividend DIV"
    assert _column(matrix, "Dividend DIV")[:3] == ["1.00", "2.00", "30.00"]
    meta = _meta(matrix)
    assert meta["Single rates (Dividend)"] == "" and meta["PUA DIV"] == "PUAs use the base rates"
    scales = [dict(zip(sr.SCALES_HEADER, row)) for row in sr.build_scales_matrix(repo, _policy())[1:]]
    div = [r for r in scales if r["Rate Type"] == "DIV"]
    assert [(r["Effective From"], r["Policy Years"]) for r in div] == [("1900-01-01", "1-2"), ("2021-01-01", "3")]
    assert div[0]["Cell"].startswith("11E1MN") and "band 0" in div[0]["Notes"]


# -- selection routing -----------------------------------------------------------------

def test_schema_selection_routes_and_turns_not_loaded_into_a_message():
    def not_loaded(*_):
        raise sr.RatesNotLoaded("Plancode X is not loaded")

    policy = SimpleNamespace(rates=SimpleNamespace(
        build_schema_coverage_matrix=lambda index: [["RateFields", "C COI", "G COI"], [index, 1, 2]],
        build_schema_benefit_matrix=not_loaded,
        build_schema_policy_matrix=lambda: [["RateFields"], ["p"]],
        build_schema_scales_matrix=lambda: [sr.SCALES_HEADER, ["Cov 01"] + [""] * 10],
    ))
    selection = build_rate_selection(policy, SCHEMA_COVERAGE, 2)
    assert selection.display_title == "Rates for Coverage 2" and selection.matrix[1] == [2, 1, 2]
    assert selection.header_labels == {"C COI": "COI", "G COI": "COI"}
    assert selection.column_groups == [("C", ["C COI"]), ("G", ["G COI"])]
    selection = build_rate_selection(policy, SCHEMA_BENEFIT, 1)
    assert selection.matrix is None and selection.message == "Plancode X is not loaded"
    assert build_rate_selection(policy, SCHEMA_POLICY, 1).display_title == "Policy Level Rates"
    scales = build_rate_selection(policy, SCHEMA_SCALES, 1)
    assert scales.display_title == "Coverage Rate Scales" and scales.column_groups == []


def test_raw_table_tab_shows_the_scale_band_over_rate_type_labels(qtbot):
    from suiteview.polview.ui.tabs.raw_table_tab import RawTableTab

    tab = RawTableTab()
    qtbot.addWidget(tab)
    tab.set_data(["RateFields", "C COI", "G COI"], [("x", "1", "2")], transposed=False,
                 header_labels={"C COI": "COI", "G COI": "COI"},
                 column_groups=[("C", ["C COI"]), ("G", ["G COI"])])
    grid = tab._normal_grid
    assert [grid.model.headerData(i, Qt.Orientation.Horizontal) for i in range(3)] == ["RateFields", "COI", "COI"]
    assert grid._column_groups == [("C", ["C COI"]), ("G", ["G COI"])]
    tab.set_data(["A"], [("1",)], transposed=False)
    assert tab._normal_grid._column_groups == []
