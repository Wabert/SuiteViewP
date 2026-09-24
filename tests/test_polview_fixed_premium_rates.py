"""ISWL / WL fixed-premium rates in PolView Rates: user mapping, IAF premiums,
mode factors and the modal premium (13034048's verified example), without live data."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTabWidget

from suiteview.core.modal_premium import ModalPremiumError, billing_mode, calculate_modal_premium
from suiteview.core.rates import Rates, RatesError, cyberlife_rate_user
from suiteview.polview.models import fixed_premium_rates as fpr
from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.ui.main_window import GetPolicyWindow
from suiteview.polview.ui.tabs.raw_table_tab import RawTableTab
from suiteview.polview.ui.tree_panel import PolicyRecordTreeWidget

MODEFACT_00_048 = {
    "Index(MODEFACT)": "00-048",
    "PACS": Decimal("0.51500"), "PACQ": Decimal("0.25900"), "PACM": Decimal("0.09100"),
    "DIRS": Decimal("0.51500"), "DIRQ": Decimal("0.26500"), "DIRM": Decimal("0.09300"),
    "PACS_FEE": Decimal("0.50833"), "PACQ_FEE": Decimal("0.25833"), "PACM_FEE": Decimal("0.09167"),
    "DIRS_FEE": Decimal("0.51667"), "DIRQ_FEE": Decimal("0.27500"), "DIRM_FEE": Decimal("0.11333"),
    "POLICY_FEE": Decimal("30.00"), "POLICY_FEE_ADD": "4", "POLICY_FEE_RULE": "3",
    "COLLECTION_FEE": Decimal("0.00"), "COLLECTION_FEE_ADD": "0", "MULTIPLY_ORDER": "1",
    "RATING_ORDER": "1", "ROUNDING_RULE": "1", "USER_CODE": "00", "MODE_PREM_TABLE": 48,
    "PAC_FACTOR_TABLE": 22, "PAC_FEE_FACTOR_TABLE": 23, "DIR_FACTOR_TABLE": 18,
    "DIR_FEE_FACTOR_TABLE": 15, "RULES_TABLE": 472, "FACTOR_SOURCE": "CKUDT324 2009 snapshot",
}


# -- company -> CyberLife rate user ------------------------------------------

@pytest.mark.parametrize("company,user", [("01", "00"), ("1", "00"), ("04", "04"), ("06", "06"), ("08", "08")])
def test_company_maps_to_documented_rate_user(company, user):
    assert cyberlife_rate_user(company) == user


@pytest.mark.parametrize("company", ["26", "00", "", None])
def test_unmapped_company_is_not_guessed(company):
    with pytest.raises(RatesError, match="no verified CyberLife rate-file user"):
        cyberlife_rate_user(company)


# -- modal premium arithmetic --------------------------------------------------

def test_13034048_direct_monthly_premium_is_reproduced():
    result = calculate_modal_premium(Decimal("318.50"), MODEFACT_00_048, "0", "M")
    assert (result.family, result.factor, result.fee_factor) == ("DIR", Decimal("0.09300"), Decimal("0.11333"))
    assert (result.premium, result.fee, result.total) == (Decimal("29.62"), Decimal("3.40"), Decimal("33.02"))


@pytest.mark.parametrize("form,mode,annual,expected", [
    ("G", "M", "103.50", "12.17"),   # 9.42 + round(30 x .09167) 2.75
    ("0", "Q", "115.00", "38.73"),   # round(30.475) 30.48 + 8.25
    ("0", "S", "200.00", "118.50"),  # 103.00 + round(15.5001) 15.50
    ("0", "A", "100.00", "130.00"),  # annual factor 1, fee added to all modes
])
def test_other_modes_and_pac(form, mode, annual, expected):
    assert calculate_modal_premium(Decimal(annual), MODEFACT_00_048, form, mode).total == Decimal(expected)


def test_policy_fee_is_only_added_to_its_modes():
    factors = {**MODEFACT_00_048, "POLICY_FEE_ADD": "3"}
    assert calculate_modal_premium(Decimal("100"), factors, "0", "A").fee == 0
    assert calculate_modal_premium(Decimal("100"), factors, "0", "M").fee == Decimal("3.40")


@pytest.mark.parametrize("change", [
    {"ROUNDING_RULE": "2"}, {"MULTIPLY_ORDER": "2"}, {"RATING_ORDER": "2"},
    {"POLICY_FEE_RULE": "1"}, {"COLLECTION_FEE": Decimal("1.00")}, {"POLICY_FEE_ADD": "7"},
])
def test_unverified_rules_fail_instead_of_calculating(change):
    with pytest.raises(ModalPremiumError, match="Unverified mode premium rules"):
        calculate_modal_premium(Decimal("100"), {**MODEFACT_00_048, **change}, "0", "M")


@pytest.mark.parametrize("form", ["H", "I", "F", ""])
def test_unmapped_bill_forms_fail(form):
    with pytest.raises(ModalPremiumError, match="no verified mode factor mapping"):
        calculate_modal_premium(Decimal("100"), MODEFACT_00_048, form, "M")


def test_non_standard_modes_bill_a_monthly_premium():
    assert billing_mode(1, "2") == "M"
    assert [billing_mode(f) for f in (12, 6, 3, 1)] == ["A", "S", "Q", "M"]
    with pytest.raises(ModalPremiumError):
        billing_mode(0)


# -- Rates lookups --------------------------------------------------------------

def _prem_row(rate_type, option, rate, sex="2", rateclass="N", effective="1900-01-01", version="",
              start="1900-01-01", stop=None, iar=0):
    ident = f"00{sex}{rateclass}0{option}"
    return (version, effective, 33, 33, iar, 95, 1, 95, 1, Decimal("1000"), rate_type, start, stop,
            ident, "00", sex, rateclass, "0", option, Decimal(rate), "81335200", version, effective)


def test_premium_lookup_binds_user_plan_and_age(monkeypatch):
    rates = Rates()
    fetch = Mock(return_value=[_prem_row("N", "**", "11.76"), _prem_row("N", "10", "0.98", rateclass="0")])
    monkeypatch.setattr(rates, "_fetch_rates", fetch)
    result = rates.get_wl_premium_rates("00", "81335200", 33, date(1994, 7, 6))
    sql, params = fetch.call_args.args
    assert params == ["00", "81335200", 33, 33]
    assert "[WL_RATE_PREM]" in sql and "[USER_CODE] = ?" in sql
    assert [r["RATE"] for r in result["rows"]] == [Decimal("11.76"), Decimal("0.98")]
    assert result["rows"][0]["SCALE_START"] == date(1900, 1, 1)


def test_premium_lookup_uses_latest_version_effective_by_issue(monkeypatch):
    rates = Rates()
    monkeypatch.setattr(rates, "_fetch_rates", Mock(return_value=[
        _prem_row("N", "**", "10.00", effective="1900-01-01", version="A"),
        _prem_row("N", "**", "12.00", effective="2000-01-01", version="B"),
    ]))
    assert rates.get_wl_premium_rates("00", "81335200", 33, date(1994, 7, 6))["iaf_version"] == "A"
    later = rates.get_wl_premium_rates("00", "81335200", 33, date(2001, 1, 1))
    assert [r["RATE"] for r in later["rows"]] == [Decimal("12.00")]
    with pytest.raises(RatesError, match="issue date is required"):
        rates.get_wl_premium_rates("00", "81335200", 33, None)


def test_premium_lookup_rejects_unverified_age_use_and_bad_keys(monkeypatch):
    rates = Rates()
    monkeypatch.setattr(rates, "_fetch_rates", Mock(return_value=[_prem_row("N", "**", "1", iar=1)]))
    with pytest.raises(RatesError, match="not verified"):
        rates.get_wl_premium_rates("00", "81335200", 33)
    with pytest.raises(RatesError):
        rates.get_wl_premium_rates("01A", "81335200", 33)


def test_modal_factor_lookup_distinguishes_missing_pointer_and_table(monkeypatch):
    rates = Rates()
    monkeypatch.setattr(rates, "_fetch_rates", Mock(return_value=None))
    assert rates.get_modal_factors("81335200") == {"index": None, "factors": None}
    monkeypatch.setattr(rates, "_fetch_rates", Mock(side_effect=[[("00-048",)], None]))
    assert rates.get_modal_factors("81335200") == {"index": "00-048", "factors": None}
    row = tuple(MODEFACT_00_048.values())
    fetch = Mock(side_effect=[[("00-048",)], [row]])
    monkeypatch.setattr(rates, "_fetch_rates", fetch)
    factors = rates.get_modal_factors("81335200")["factors"]
    assert factors["DIRM"] == Decimal("0.09300") and factors["POLICY_FEE_ADD"] == "4"
    assert fetch.call_args_list[0].args[1] == ["81335200"]


# -- premium cell selection -----------------------------------------------------

def _rows(*specs):
    return [dict(RATE_TYPE=t, PLAN_OPTION=o, SEX=s, RATECLASS=c, RATE=Decimal(r),
                 PREMIUM_IDENTIFIER=f"00{s}{c}0{o}", SCALE_START=date(1900, 1, 1)) for t, o, s, c, r in specs]


def test_select_prefers_exact_class_then_class_independent_rider_cells():
    rows = _rows(("N", "**", "2", "N", "11.76"), ("N", "10", "2", "0", "0.98"), ("W", "**", "2", "N", "11.76"))
    assert fpr.select_premium_row(rows, "**", "2", "N")[0]["RATE"] == Decimal("11.76")
    assert fpr.select_premium_row(rows, "10", "2", "N")[0]["RATE"] == Decimal("0.98")
    row, reason = fpr.select_premium_row(rows, "**", "1", "N")
    assert row is None and "sex 1" in reason
    row, reason = fpr.select_premium_row(rows, "71", "2", "N")
    assert row is None and "option 71" in reason
    row, reason = fpr.select_premium_row(rows, "**", "2", "S")
    assert row is None and "rate class S" in reason


def test_select_does_not_choose_between_ambiguous_cells():
    rows = _rows(("N", "**", "2", "N", "11.76"), ("N", "**", "2", "N", "12.00"))
    row, reason = fpr.select_premium_row(rows, "**", "2", "N")
    assert row is None and reason.startswith("Ambiguous: 2")


# -- matrices from a 13034048-shaped policy -------------------------------------

class FakePolicy:
    policy_number, company_code, cyberlife_rate_user_code = "13034048", "01", "00"
    valuation_date = date(2026, 9, 6)
    premium_pay_status_code = "22"
    billing_frequency, non_standard_mode_code, bill_form_code = 1, "", "0"
    modal_premium = Decimal("33.02")

    def __init__(self, premium_rows=None, factors=None):
        self.coverage = SimpleNamespace(
            cov_pha_nbr=1, plancode="81335200", issue_age=33, issue_date=date(1994, 7, 6),
            units=Decimal("25.000"), annual_premium_per_unit=Decimal("11.76"),
            table_rating=None, table_rating_code="", table_cease_date=None,
            flat_extra=None, flat_cease_date=None,
        )
        self.benefits = [
            SimpleNamespace(cov_pha_nbr=1, benefit_type_cd="1", benefit_subtype_cd="0", issue_age=33,
                            issue_date=date(1994, 7, 6), units=Decimal("25.000"), coi_rate=Decimal("0.98"),
                            cease_date=date(2056, 7, 6), rating_factor=None),
            SimpleNamespace(cov_pha_nbr=1, benefit_type_cd="3", benefit_subtype_cd="3", issue_age=33,
                            issue_date=date(1994, 7, 6), units=Decimal("25.000"), coi_rate=Decimal("0.44"),
                            cease_date=date(2021, 7, 6), rating_factor=None),
        ]
        rows = _rows(("N", "**", "2", "N", "11.76"), ("N", "10", "2", "0", "0.98"),
                     ("N", "33", "2", "0", "0.44"), ("G", "**", "2", "N", "1.53"))
        for row in rows:
            row.update(SCALE_STOP=None, VALUE_PER_UNIT=Decimal("1000"), PAY_AGE=95, PAY_AGE_USE=1,
                       ME_AGE=95, ME_AGE_USE=1)
        self.premium = {"rows": rows if premium_rows is None else premium_rows,
                        "iaf_version": "", "effective_date": date(1900, 1, 1), "versions": []}
        self.factors = {"index": "00-048", "factors": MODEFACT_00_048} if factors is None else factors
        self.rates_wl_premium = Mock(side_effect=lambda plancode, age, issued: self.premium)

    def get_coverages(self):
        return [self.coverage]

    def get_benefits(self):
        return self.benefits

    def cov_plancode(self, index):
        return self.coverage.plancode

    def cov_rate_sex_code(self, index):
        return "2"

    def renewal_cov_rateclass_by_cov(self, index):
        return "N"

    def _coverage_is_active(self, cov, as_of):
        return True

    def rates_modal_factors(self):
        return self.factors


def _lines(matrix):
    return {row[3]: row for row in matrix[1:] if row[3]}


def test_modal_premium_matrix_reproduces_pol_prm_amt():
    matrix = fpr.build_modal_premium_matrix(FakePolicy())
    assert matrix[0][2:] == ["Line", "Item", "Units", "Rate", "Amount", "Note"]
    lines = _lines(matrix)
    assert lines["Cov 01 base"][6] == "294.00"
    assert lines["Ben 01 (1/0)"][6] == "24.50"
    assert lines["Ben 02 (3/3)"][6] == "" and "excluded" in lines["Ben 02 (3/3)"][7]
    assert lines["Annual premium"][6] == "318.50"
    assert lines["DIRM"][5:7] == ["0.093", "29.62"]
    assert lines["DIRM_FEE"][5:7] == ["0.11333", "3.40"]
    assert lines["Calculated modal premium"][6] == "33.02"
    assert lines["LH_BAS_POL.POL_PRM_AMT"][6] == "33.02"
    assert lines["Stored - calculated"][6:] == ["0.00", "Match"]
    info = {row[0]: row[1] for row in matrix[1:] if row[0]}
    assert info["Factors"] == "00-048" and info["Bill Form"].startswith("0 (DIR")
    assert info["Fee Added"] == "4 (All modes)"


@pytest.mark.parametrize("factors,text", [
    ({"index": None, "factors": None}, "no POINT_MODEFACT pointer for plancode 81335200"),
    ({"index": "00-048", "factors": None}, "mode premium table 00-048 is not in RATE_MODEFACT"),
])
def test_missing_mode_factors_are_explicit(factors, text):
    matrix = fpr.build_modal_premium_matrix(FakePolicy(factors=factors))
    lines = _lines(matrix)
    assert lines["Calculated modal premium"][6] == "Not calculated"
    assert text in lines["Calculated modal premium"][7]
    assert "Stored - calculated" not in lines


def test_missing_premium_rows_are_explicit_not_zero():
    policy = FakePolicy(premium_rows=[])
    lines = _lines(fpr.build_modal_premium_matrix(policy))
    assert lines["Cov 01 base"][5] == "Not loaded"
    assert "no WL_RATE_PREM rows for 81335200, user 00, age 33" in lines["Cov 01 base"][7]
    assert lines["Calculated modal premium"][6] == "Not calculated"
    premium = fpr.build_premium_rate_matrix(policy, 1)
    body = {row[2]: row for row in premium[1:] if row[2]}
    assert body["Cov 01 base"][10].startswith("Not loaded: no WL_RATE_PREM rows")
    assert body["Ben 01 (1/0)"][12] == ""


def test_eti_rpu_has_no_billed_premium():
    policy = FakePolicy()
    policy.premium_pay_status_code = "44"
    lines = _lines(fpr.build_modal_premium_matrix(policy))
    assert "ETI/RPU" in lines["Calculated modal premium"][7]
    policy.rates_wl_premium.assert_not_called()


def test_unverified_bill_form_is_explained():
    policy = FakePolicy()
    policy.bill_form_code = "H"
    lines = _lines(fpr.build_modal_premium_matrix(policy))
    assert "Bill form H has no verified mode factor mapping" in lines["Calculated modal premium"][7]


def test_premium_rate_matrix_lists_base_benefits_and_printed_cells():
    matrix = fpr.build_premium_rate_matrix(FakePolicy(), 1)
    assert matrix[0][2:6] == ["Item", "Option", "Type", "Description"]
    rows = [row[2:] for row in matrix[1:] if row[2]]
    assert rows[0][:2] == ["Cov 01 base", "**"] and rows[0][8] == "11.76"
    assert rows[0][10:13] == ["294.00", "11.76", "Match"]
    assert rows[1][:2] == ["Ben 01 (1/0)", "10"] and rows[1][8] == "0.98"
    assert rows[2][:2] == ["Ben 02 (3/3)", "33"] and rows[2][13] == "Ceased 07/06/2021"
    assert rows[3][2:4] == ["G", "Guaranteed COI (IAF)"]
    info = {row[0]: row[1] for row in matrix[1:] if row[0]}
    assert info["Rate User"] == "00 (company 01)" and info["Sex"] == "2 (Female)"


def test_substandard_is_flagged_on_the_comparison():
    policy = FakePolicy()
    policy.coverage.table_rating, policy.coverage.table_rating_code = 2, "B"
    lines = _lines(fpr.build_modal_premium_matrix(policy))
    assert "substandard not included (Cov 01 base table B)" in lines["Stored - calculated"][7]


# -- ISWL coverage view additions -----------------------------------------------

def test_iswl_coverage_extras_add_scales_gint_and_cease_ages():
    policy = object.__new__(PolicyInformation)
    rates = SimpleNamespace(
        get_rates=Mock(return_value=[(date(1998, 5, 1), 1), (date(1900, 1, 1), 3), (date(1993, 1, 1), 2)]),
        get_age_limits=Mock(return_value={"premium_cease": 95, "benefit_cease": None}),
        get_gint=Mock(return_value=[None, 0.04, 0.04]),
    )
    policy._get_rates = lambda: rates
    policy.cov_plancode = lambda index: "81335200"
    policy.rates_coi = Mock(side_effect=lambda index, scale: [None, float(scale)])
    policy._iswl_cash_value_column = Mock(return_value=(("CVR", "WL_RATE_CV 235211 at Date"), [None, "0.00"]))
    policy._iswl_premium_rate_column = Mock(return_value=(("Prem Rate", "WL_RATE_PREM ** to age 95"), [None, "11.76"]))
    meta, extra = policy._iswl_coverage_rate_extras(1)
    assert list(extra) == ["COI S2", "COI S3", "GINT", "CVR", "Prem Rate"]
    assert extra["COI S3"] == [None, 3.0]
    assert ("  from 1900-01-01", "Scale 3") in meta and ("  from 1998-05-01", "Scale 1") in meta
    assert ("Prem Cease Age", 95) in meta and ("Ben Cease Age", "Not loaded") in meta


@pytest.fixture
def column_policy(monkeypatch):
    monkeypatch.setattr(PolicyInformation, "premium_pay_status_code", property(lambda self: self._status))
    policy = object.__new__(PolicyInformation)
    policy._status = "22"
    policy.rates_wl_cv = Mock(return_value={0: Decimal("0.00"), 31: Decimal("333.00")})
    policy.cov_cash_value_key = lambda index: "235211"
    policy.cov_issue_age = lambda index: 33
    return policy


def test_cvr_column_aligns_duration_with_the_date_column(column_policy):
    column_policy.rates_wl_cv.return_value = {d: Decimal(d) for d in range(0, 63)}
    meta, column = column_policy._iswl_cash_value_column(1)
    assert meta == ("CVR", "WL_RATE_CV 235211 at Date")
    assert column[1] == Decimal(0) and column[32] == Decimal(31) and len(column) == 64


@pytest.mark.parametrize("status", ["44", "45"])
def test_cvr_column_is_not_available_on_eti_rpu(column_policy, status):
    column_policy._status = status
    assert column_policy._iswl_cash_value_column(1) == (("CVR", "Not available on ETI/RPU"), None)
    column_policy.rates_wl_cv.assert_not_called()


def test_cvr_column_missing_and_errors_are_explicit(column_policy):
    column_policy.rates_wl_cv.return_value = {}
    assert column_policy._iswl_cash_value_column(1) == (("CVR", "Not loaded (WL_RATE_CV 235211)"), None)
    column_policy.rates_wl_cv.side_effect = RatesError("Company 26 has no verified CyberLife rate-file user mapping.")
    meta, column = column_policy._iswl_cash_value_column(1)
    assert column is None and meta[1].startswith("Error: Company 26")


def test_prem_rate_column_runs_to_the_pay_age(column_policy, monkeypatch):
    row = {"RATE": Decimal("11.76000000"), "PAY_AGE": 95, "PAY_AGE_USE": 1}
    monkeypatch.setattr(fpr, "premium_items", lambda policy, index: [SimpleNamespace(rate_row=row, reason="")])
    meta, column = column_policy._iswl_premium_rate_column(1)
    assert meta == ("Prem Rate", "WL_RATE_PREM ** to age 95")
    assert column[1:] == ["11.76"] * 62
    monkeypatch.setattr(fpr, "premium_items", lambda policy, index: [
        SimpleNamespace(rate_row=None, reason="Not loaded: no WL_RATE_PREM rows")])
    assert column_policy._iswl_premium_rate_column(1) == (("Prem Rate", "Not loaded: no WL_RATE_PREM rows"), None)


@pytest.mark.parametrize("amount,text", [
    (Decimal("25000.00000"), "25,000"), (Decimal("1234567.50"), "1,234,568"), (Decimal("0"), "0"), (None, ""),
])
def test_rates_grid_amounts_are_whole_dollars_with_commas(amount, text):
    assert PolicyInformation._whole_dollars(amount) == text


# -- Rates tree and routing -----------------------------------------------------

def _tree_policy(product, advanced, fixed):
    return SimpleNamespace(
        is_advanced_product=advanced, product_type=product, has_fixed_premium_rates=fixed,
        coverage_count=1, benefit_count=0, cov_plancode=lambda index: "81335200",
        get_benefits=lambda: [],
    )


def _branch(tree, name):
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        if (item.data(0, Qt.ItemDataRole.UserRole) or {}).get("name") == name:
            return [item.child(j).data(0, Qt.ItemDataRole.UserRole) for j in range(item.childCount())]
    return None


@pytest.mark.parametrize("product,advanced,fixed,expected", [
    ("ISWL", True, True, ["Cash Values", "Premium Rates", "Modal Premium"]),
    ("WL", False, True, ["Premium Rates", "Modal Premium"]),
    ("UL", True, False, None), ("TERM", False, False, None),
])
def test_fixed_premium_branch_only_for_iswl_and_wl(qtbot, product, advanced, fixed, expected):
    tree = PolicyRecordTreeWidget()
    qtbot.addWidget(tree)
    tree.build_rates_tree(_tree_policy(product, advanced, fixed))
    leaves = _branch(tree, "Fixed Premium")
    assert (None if leaves is None else [leaf["category"] for leaf in leaves]) == expected
    assert tree.topLevelItem(tree.topLevelItemCount() - 1).data(0, Qt.ItemDataRole.UserRole)["category"] == "Policy"


@pytest.fixture
def display(qtbot):
    tabs = QTabWidget()
    raw = RawTableTab()
    tabs.addTab(raw, "Data")
    qtbot.addWidget(tabs)
    policy = SimpleNamespace(
        is_advanced_product=True, product_type="ISWL", company_code="01",
        cyberlife_rate_user_code="00", premium_pay_status_code="22",
        cov_cash_value_key=lambda index: "235211", cov_issue_age=lambda index: 33,
        build_whole_life_coverage_rate_matrix=Mock(return_value=[["Duration", "CV"], [31, "333.00"]]),
        build_premium_rate_matrix=Mock(return_value=[["Item", "Rate"], ["Cov 01 base", "11.76"]]),
        build_modal_premium_matrix=Mock(return_value=[["Line", "Amount"], ["Modal", "33.02"]]),
    )
    return SimpleNamespace(_policy=policy, tabs=tabs, raw_table_tab=raw, _show_status=Mock())


@pytest.mark.parametrize("category,builder,title,rows", [
    ("Cash Values", "build_whole_life_coverage_rate_matrix", "Cash Value Rates - Coverage 1", [(31, "333.00")]),
    ("Premium Rates", "build_premium_rate_matrix", "Premium Rates - Coverage 1", [("Cov 01 base", "11.76")]),
    ("Modal Premium", "build_modal_premium_matrix", "Modal Premium", [("Modal", "33.02")]),
])
def test_fixed_premium_leaves_route_to_their_builders(display, category, builder, title, rows):
    GetPolicyWindow._on_rate_selected(display, category, category, 1)
    assert display.raw_table_tab._current_rows == rows
    assert display.raw_table_tab.table_label.text() == title
    getattr(display._policy, builder).assert_called_once()


def test_iswl_cash_values_missing_names_the_user_key(display):
    display._policy.build_whole_life_coverage_rate_matrix.return_value = None
    GetPolicyWindow._on_rate_selected(display, "Cash Values", "Cash Values Cov 01", 1)
    message = display._show_status.call_args.args[0]
    assert all(text in message for text in ("WL_RATE_CV", "user=00", "company 01", "235211", "33"))


@pytest.mark.parametrize("status", ["44", "45"])
def test_iswl_eti_rpu_cash_values_are_unavailable(display, status):
    display._policy.premium_pay_status_code = status
    GetPolicyWindow._on_rate_selected(display, "Cash Values", "Cash Values Cov 01", 1)
    display._policy.build_whole_life_coverage_rate_matrix.assert_not_called()
    assert "ETI or RPU" in display._show_status.call_args.args[0]
