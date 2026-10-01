"""Exact Whole Life cash-value selection and duration-preserving PolView matrices."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from suiteview.core.rates import Rates
from suiteview.core.rates_errors import RatesError
from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.models.policy_sections.product import ProductSection


def test_cash_values_bind_all_natural_keys_and_keep_zero(monkeypatch):
    rates = Rates()
    fetch = Mock(return_value=[
        (0, Decimal("0.00"), 0, 1),
        (1, Decimal("18.25"), 0, 1),
    ])
    monkeypatch.setattr(rates, "_fetch_rates", fetch)
    assert rates.get_wl_cash_values(" 08 ", "1wl511", 0, " A'B ") == {
        0: Decimal("0.00"), 1: Decimal("18.25"),
    }
    sql, params = fetch.call_args.args
    assert params == ["08", "1WL511", 0, "A'B"]
    assert "A'B" not in sql
    for field in ("USER_CODE", "RATE_KEY", "ISSUE_AGE", "USER_DEFINED"):
        assert f"[{field}] = ?" in sql
    assert "ORDER BY [DURATION]" in sql


def test_cash_values_no_match_does_not_fall_back_to_another_company_or_variant(monkeypatch):
    rates = Rates()
    fetch = Mock(return_value=None)
    monkeypatch.setattr(rates, "_fetch_rates", fetch)
    assert rates.get_wl_cash_values("08", "1WL511", 59) == {}
    fetch.assert_called_once()
    assert fetch.call_args.args[1] == ["08", "1WL511", 59, ""]


def test_cash_values_queries_remain_separate_and_refreshable(monkeypatch):
    rates = Rates()
    fetch = Mock(return_value=[(5, Decimal("12.34"), 5, 5)])
    monkeypatch.setattr(rates, "_fetch_rates", fetch)
    for company, key, age, variant in [
        ("08", "1WL511", 59, ""), ("06", "1WL511", 59, ""),
        ("08", "1WL511", 60, ""), ("08", "1WL5  ", 59, "A"),
        ("08", "1WL511", 59, ""),
    ]:
        assert rates.get_wl_cash_values(company, key, age, variant) == {5: Decimal("12.34")}
        assert fetch.call_args.args[1] == [company, key, age, variant]
    assert fetch.call_count == 5


@pytest.mark.parametrize("args", [
    ("8", "1WL511", 59), ("08", "1WL51", 59), ("08", "1WL5'1", 59),
    ("08", "1WL511", None), ("08", "1WL511", -1),
    ("08", "1WL511", 1.5), ("08", "1WL511", True),
    ("08", "1WL511", 59, "TOO-LONG-KEY"),
])
def test_cash_values_invalid_selection_fails_before_query(monkeypatch, args):
    rates = Rates()
    fetch = Mock()
    monkeypatch.setattr(rates, "_fetch_rates", fetch)
    with pytest.raises(RatesError):
        rates.get_wl_cash_values(*args)
    fetch.assert_not_called()


@pytest.mark.parametrize("rows", [
    [(0, None, 0, 0)], [(0, Decimal("-1.00"), 0, 0)],
    [(0, Decimal("NaN"), 0, 0)], [(0, Decimal("1.00"), 0, 1)],
    [(0, Decimal("1.00"), 1, 0)],
    [(0, Decimal("1.00"), 0, 0), (0, Decimal("1.00"), 0, 0)],
    [(0, Decimal("1.00"), 0, 1), (1, Decimal("1.00"), 0, 2)],
])
def test_cash_values_reject_corrupt_stored_schedules(monkeypatch, rows):
    rates = Rates()
    monkeypatch.setattr(rates, "_fetch_rates", Mock(return_value=rows))
    with pytest.raises(RatesError):
        rates.get_wl_cash_values("08", "1WL511", 59)


def test_cash_values_database_failure_is_not_missing_data(monkeypatch):
    rates = Rates()
    monkeypatch.setattr(rates, "_get_connection", Mock(side_effect=RatesError("ODBC unavailable")))
    with pytest.raises(RatesError, match="ODBC unavailable"):
        rates.get_wl_cash_values("08", "1WL511", 59)


def test_interactive_connections_have_a_query_timeout(monkeypatch):
    connection = SimpleNamespace(timeout=0)
    connect = Mock(return_value=connection)
    monkeypatch.setattr("suiteview.core.rates.local_data_enabled", lambda: False)
    monkeypatch.setattr("suiteview.core.rates.pyodbc.connect", connect)
    assert Rates()._get_connection() is connection
    assert connection.timeout == Rates.QUERY_TIMEOUT > 0
    assert connect.call_args.kwargs["timeout"] == 15


def test_locked_rate_tables_time_out_with_an_explanation(monkeypatch):
    import pyodbc

    cursor = Mock()
    cursor.execute.side_effect = pyodbc.OperationalError("HYT00", "[HYT00] Query timeout expired")
    rates = Rates()
    monkeypatch.setattr(rates, "_get_connection", Mock(return_value=Mock(cursor=Mock(return_value=cursor))))
    with pytest.raises(RatesError, match="probably locked by a rate load"):
        rates.get_wl_cash_values("08", "1WL511", 59)
    cursor.close.assert_called_once()


@pytest.fixture
def policy(monkeypatch):
    policy = object.__new__(PolicyInformation)
    policy._data = SimpleNamespace(
        company_code="08", policy_number="05335420", reject_uncached_read=lambda reason: None,
    )
    policy._rates = Rates()
    coverage = SimpleNamespace(
        plancode="201WL500", issue_age=59, issue_date=date(2000, 1, 22),
        maturity_date=date(2041, 1, 22), vpu=Decimal("1000.00"), number_of_lives_code="1",
    )
    policy.coverages.get_coverages = lambda: [coverage]
    fields = {"INS_CLS_CD": "1", "PLN_BSE_SRE_CD": "WL5", "LIF_PLN_SUB_SRE_CD": "11"}
    policy.data_item = lambda table, field, index=0: fields.get(field)
    policy.data_item_count = lambda table: 1
    monkeypatch.setattr(ProductSection, "product_type", property(lambda self: "WL"))
    monkeypatch.setattr(policy._rates, "_fetch_rates", Mock(return_value=[
        (duration, Decimal(duration).quantize(Decimal("0.00")), 0, 41)
        for duration in range(42)
    ]))
    return policy


def test_policy_uses_verified_coverage_fields_not_plancode_or_band(policy):
    policy.rates.cov_band = Mock(side_effect=AssertionError("WL has no UL band lookup"))
    assert policy.rates.cov_cash_value_key(1) == "1WL511"
    values = policy.rates.rates_wl_cv(1)
    assert len(values) == 42
    assert policy._rates._fetch_rates.call_args.args[1] == ["08", "1WL511", 59, ""]


@pytest.mark.parametrize("company,user", [("01", "00"), ("04", "04"), ("06", "06"), ("08", "08")])
def test_policy_cash_values_use_the_cyberlife_rate_user_not_the_company(policy, company, user):
    policy._data.company_code = company
    policy.rates.rates_wl_cv(1)
    assert policy._rates._fetch_rates.call_args.args[1][0] == user


def test_unmapped_company_fails_instead_of_querying_its_own_code(policy):
    policy._data.company_code = "26"
    with pytest.raises(RatesError, match="26 has no verified CyberLife rate-file user"):
        policy.rates.rates_wl_cv(1)
    policy._rates._fetch_rates.assert_not_called()


def test_cash_value_matrix_compares_the_stored_02_segment_window(policy):
    stored = {"LOW_DUR_PER": 31, "LOW_DUR_CSV_AMT": "31.00", "LOW_DUR_1_CSV_AMT": "32.00",
              "LOW_DUR_2_CSV_AMT": "33.50", "INS_CLS_CD": "1", "PLN_BSE_SRE_CD": "WL5",
              "LIF_PLN_SUB_SRE_CD": "11"}
    policy.data_item = lambda table, field, index=0: stored.get(field)
    info = {row[0]: row[1] for row in policy.rates.build_whole_life_coverage_rate_matrix(1)[1:] if row[0]}
    assert info["Rate User"] == "08"
    assert info["02 Stored CV"] == "Differs: dur 33: 33.50 vs 33.00"
    stored["LOW_DUR_2_CSV_AMT"] = "33.00"
    info = {row[0]: row[1] for row in policy.rates.build_whole_life_coverage_rate_matrix(1)[1:] if row[0]}
    assert info["02 Stored CV"] == "Durations 31-33 match"


def test_policy_cash_key_uses_requested_coverage_row_and_padding(policy):
    policy.data_item_count = lambda table: 2
    calls = []

    def data_item(table, field, index=0):
        calls.append((table, field, index))
        return {"INS_CLS_CD": " 1 ", "PLN_BSE_SRE_CD": " ab ", "LIF_PLN_SUB_SRE_CD": "x"}[field]

    policy.data_item = data_item
    assert policy.rates.cov_cash_value_key(2) == "1AB X "
    assert {call[2] for call in calls} == {1}


@pytest.mark.parametrize("index", [0, -1, 2])
def test_policy_cash_key_rejects_invalid_coverage(policy, index):
    with pytest.raises(ValueError, match="out of range"):
        policy.rates.cov_cash_value_key(index)


@pytest.mark.parametrize("field,value", [
    ("INS_CLS_CD", None), ("INS_CLS_CD", ""),
    ("PLN_BSE_SRE_CD", "TOOLONG"), ("LIF_PLN_SUB_SRE_CD", None),
])
def test_policy_cash_key_missing_or_invalid_parts_are_not_guessed(policy, field, value):
    policy.data_item = lambda table, name, index=0: value if name == field else {
        "INS_CLS_CD": "1", "PLN_BSE_SRE_CD": "WL5", "LIF_PLN_SUB_SRE_CD": "11",
    }[name]
    with pytest.raises(ValueError, match=field):
        policy.rates.rates_wl_cv(1)
    policy._rates._fetch_rates.assert_not_called()


def test_policy_missing_issue_age_fails_without_query(policy):
    policy.coverages.get_coverages()[0].issue_age = None
    with pytest.raises(ValueError, match="issue age"):
        policy.rates.rates_wl_cv(1)
    policy._rates._fetch_rates.assert_not_called()


def test_whole_life_matrix_keeps_duration_zero_and_maturity(policy):
    matrix = policy.rates.build_coverage_rate_matrix(1)
    assert matrix[0] == ["RateFields", "RateInfo", "Date", "Age", "Duration", "CV"]
    assert len(matrix) == 43
    assert matrix[1][2:] == ["01/22/2000", 59, 0, Decimal("0.00")]
    assert matrix[27][2:] == ["01/22/2026", 85, 26, Decimal("26.00")]
    assert matrix[-1][2:] == ["01/22/2041", 100, 41, Decimal("41.00")]
    info = {row[0]: row[1] for row in matrix[1:] if row[0]}
    assert info["Rate Key"] == "1WL511"
    assert info["User Defined"] == "(blank)"
    assert info["CV Basis"] == "Per coverage unit"
    assert info["NSP / PUI / Div"] == "Not yet available"
    assert all(len(row) == len(matrix[0]) for row in matrix)


def test_whole_life_short_schedule_does_not_invent_rates_or_shift_nonzero_start(policy):
    policy._rates._fetch_rates.return_value = [(5, Decimal("12.34"), 5, 5)]
    matrix = policy.rates.build_coverage_rate_matrix(1)
    assert matrix[1][2:] == ["01/22/2005", 64, 5, Decimal("12.34")]
    assert all(row[2:] == ["", "", "", ""] for row in matrix[2:])


def test_whole_life_rates_do_not_require_issue_date_and_preserve_issue_age_zero(policy):
    coverage = policy.coverages.get_coverages()[0]
    coverage.issue_age = 0
    coverage.issue_date = None
    matrix = policy.rates.build_coverage_rate_matrix(1)
    assert matrix[1][2:] == ["", 0, 0, Decimal("0.00")]
    assert policy._rates._fetch_rates.call_args.args[1][2] == 0


def test_whole_life_no_match_does_not_create_na_matrix(policy):
    policy._rates._fetch_rates.return_value = None
    assert policy.rates.build_coverage_rate_matrix(1) is None


@pytest.mark.parametrize("product,advanced", [("UL", True), ("ISWL", True), ("TERM", False)])
def test_other_products_keep_existing_coverage_rate_path(policy, monkeypatch, product, advanced):
    monkeypatch.setattr(ProductSection, "product_type", property(lambda self: product))
    monkeypatch.setattr(ProductSection, "is_advanced_product", property(lambda self: advanced))
    policy.rates.build_whole_life_coverage_rate_matrix = Mock(side_effect=AssertionError("Wrong route"))
    for name in ("rates_mtp", "rates_ctp", "rates_tbl1_mtp", "rates_tbl1_ctp"):
        setattr(policy.rates, name, Mock(return_value=12.34))
    for name in ("rates_coi", "rates_epu", "rates_scr"):
        setattr(policy.rates, name, Mock(return_value=[None] + [1.25] * 42))
    for name in ("cov_flat_extra", "cov_amount", "cov_orig_amount"):
        setattr(policy.coverages, name, Mock(return_value=Decimal("0")))
    policy.rates.renewal_cov_sex_code = lambda index: "1"
    policy.rates.renewal_cov_rateclass_by_cov = lambda index: "N"
    policy.rates.cov_band = lambda index: 1
    policy.coverages.cov_table_rating = lambda index: 0
    policy.rates._iswl_coverage_rate_extras = Mock(return_value=(
        [("Prem Cease Age", 95)], {"GINT": [None] + [0.04] * 42},
    ))
    matrix = policy.rates.build_coverage_rate_matrix(1)
    ul_columns = ["COI", "EPU", "SCR", "GuarCOI", "GuarEPU"]
    assert matrix[0][5:10] == ul_columns
    assert matrix[1][5:10] == [1.25] * 5
    if product == "ISWL":
        assert matrix[0][10:] == ["GINT"]
        assert matrix[1][10:] == [0.04]
        assert ["Prem Cease Age", 95] in [row[:2] for row in matrix]
    else:
        assert matrix[0][5:] == ul_columns
        policy.rates._iswl_coverage_rate_extras.assert_not_called()
    policy._rates._fetch_rates.assert_not_called()
