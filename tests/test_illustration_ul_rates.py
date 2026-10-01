"""RERUN's UL rate reader over UL_Rates schema ``rates`` (``ULRates``)."""
from datetime import date

import pytest

from suiteview.core.rates_errors import RatesError
from suiteview.illustration.core.ul_rates import SHADOW, ULRates
from tests.schema_rates_fake import FakeSchemaRepo

ALWAYS = date(1900, 1, 1)


def _ia_dur(age, *rates):
    return {(age, year): rate for year, rate in enumerate(rates, start=1)}


def test_current_coi_reads_each_coverage_years_calendar_scale():
    repo = FakeSchemaRepo()
    repo.add_cell("COI", [
        (ALWAYS, date(2020, 1, 1), _ia_dur(40, 1.0, 1.1, 1.2, 1.3)),
        (date(2020, 1, 1), None, _ia_dur(40, 0.5, 0.6, 0.7, 0.8)),
    ], scale="C")
    rates = ULRates(repository=repo)

    schedule = rates.get_rates("COI", "TEST", 40, "M", "N", scale=1, band=1,
                               issue_date=date(2018, 6, 1))

    # Years starting 6/2018 and 6/2019 are on the first scale; 6/2020 on is the second.
    assert schedule == [None, 1.0, 1.1, 0.7, 0.8]


def test_several_dated_scales_need_the_issue_date():
    repo = FakeSchemaRepo()
    repo.add_cell("COI", [
        (ALWAYS, date(2020, 1, 1), _ia_dur(40, 1.0)),
        (date(2020, 1, 1), None, _ia_dur(40, 0.5)),
    ], scale="C")
    with pytest.raises(RatesError, match="needs the coverage issue date"):
        ULRates(repository=repo).get_rates("COI", "TEST", 40, "M", "N", scale=1, band=1)


def test_guaranteed_scale_and_single_window_need_no_date():
    repo = FakeSchemaRepo()
    repo.add_cell("COI", [(ALWAYS, None, _ia_dur(40, 2.0, 2.5))], scale="G")
    rates = ULRates(repository=repo)
    assert rates.get_rates("COI", "TEST", 40, "M", "N", scale=0, band=1) == [None, 2.0, 2.5]
    assert rates.get_rates("COI", "TEST", 40, "M", "N", scale=1, band=1) is None


def test_surrender_charge_prefers_the_issue_state_cell():
    repo = FakeSchemaRepo()
    repo.add_cell("SCR", [(ALWAYS, None, _ia_dur(40, 30.0, 20.0))])
    repo.add_cell("SCR", [(ALWAYS, None, _ia_dur(40, 25.0, 15.0))], state="FL")
    rates = ULRates(repository=repo)
    assert rates.get_rates("SCR", "TEST", 40, "M", "N", band=1, state="FL") == [None, 25.0, 15.0]
    assert rates.get_rates("SCR", "TEST", 40, "M", "N", band=1, state="TX") == [None, 30.0, 20.0]


def test_excess_load_falls_back_to_the_premium_load_without_an_excess_rate():
    repo = FakeSchemaRepo()
    repo.add_cell("PREMLOAD_PCT", [(ALWAYS, None, {(0, 1): 0.08, (0, 2): 0.04})], scale="C", grain="DUR")
    rates = ULRates(repository=repo)
    assert rates.get_rates("TPP", "TEST", 40, "M", "N", scale=1, band=1) == [None, 0.08, 0.04]
    assert rates.get_rates("EPP", "TEST", 40, "M", "N", scale=1, band=1) == [None, 0.08, 0.04]

    repo.add_cell("PREMLOAD_EXS", [(ALWAYS, None, {(0, 1): 0.02})], scale="C", grain="DUR")
    assert ULRates(repository=repo).get_rates("EPP", "TEST", 40, "M", "N", scale=1, band=1) == [None, 0.02]


def test_shadow_account_rates_are_scale_s_on_the_base_plancode():
    repo = FakeSchemaRepo()
    repo.add_cell("COI", [(ALWAYS, None, _ia_dur(40, 0.9))], scale="S")
    repo.add_cell("MTP", [(ALWAYS, None, {(40, 0): 12.5}, "S"), (ALWAYS, None, {(40, 0): 10.0}, "G")],
                  grain="IA")
    repo.add_plan_rate("DB_DISCOUNT", {(0, 1): 0.02}, scale="S")
    rates = ULRates(repository=repo)
    assert rates.get_rates("COI", "TEST", 40, "M", "N", scale=SHADOW, band=1) == [None, 0.9]
    assert rates.get_mtp("TEST", 40, "M", "N", 1, scale=SHADOW) == 12.5
    assert rates.get_mtp("TEST", 40, "M", "N", 1) == 10.0
    assert rates.get_rates("DBD", "TEST", scale=SHADOW) == [None, 0.02]
    assert rates.get_rates("DBD", "TEST") is None


def test_shadow_db_discount_can_be_cell_level_or_plan_level():
    repo = FakeSchemaRepo()
    repo.add_cell("DB_DISCOUNT", [(ALWAYS, None, _ia_dur(40, 0.045))], scale="S")
    repo.add_cell("DB_DISCOUNT", [(ALWAYS, None, _ia_dur(40, 0.035))], scale="S", sex="F")
    repo.add_plan_rate("DB_DISCOUNT", {(0, 1): 0.02}, scale="S")
    rates = ULRates(repository=repo)

    assert rates.get_rates(
        "DBD", "TEST", 40, "M", "N", scale=SHADOW, band=1
    ) == [None, 0.045]
    assert rates.get_rates(
        "DBD", "TEST", 40, "F", "N", scale=SHADOW, band=1
    ) == [None, 0.035]
    assert rates.get_rates("DBD", "TEST", scale=SHADOW) == [None, 0.02]


def test_shadow_ctp_target_can_read_scale_s():
    repo = FakeSchemaRepo()
    repo.add_cell("CTP", [(ALWAYS, None, {(40, 0): 7.5}, "S")], grain="IA")
    repo.add_cell("CTP_TBL1", [(ALWAYS, None, {(40, 0): 0.25}, "S")], grain="IA")
    rates = ULRates(repository=repo)

    assert rates.get_ctp("TEST", 40, "M", "N", 1, scale=SHADOW) == 7.5
    assert rates.get_tbl1_ctp("TEST", 40, "M", "N", 1, scale=SHADOW) == 0.25


def test_table_target_add_on_not_loaded_is_unavailable_not_zero():
    repo = FakeSchemaRepo()
    repo.add_cell("MTP_TBL1", [(ALWAYS, None, {(40, 0): 0.0})], grain="IA")
    rates = ULRates(repository=repo)
    assert rates.get_tbl1_mtp("TEST", 40, "M", "N", 1) == 0.0
    assert rates.get_tbl1_ctp("TEST", 40, "M", "N", 1) is None


def test_unloaded_plancode_has_no_rates_and_plan_lookup_says_so():
    rates = ULRates(repository=FakeSchemaRepo())
    assert not rates.is_loaded("NOPE")
    assert rates.get_rates("COI", "NOPE", 40, "M", "N", band=1) is None
    assert rates.get_mtp("NOPE", 40, "M", "N", 1) is None
    assert rates.get_band("NOPE", 100_000) is None
    with pytest.raises(RatesError, match="NOPE is not loaded in UL_Rates schema rates"):
        rates.plan("NOPE")


def test_unisex_policy_uses_a_single_sex_plans_cells():
    repo = FakeSchemaRepo()
    repo.add_cell("COI", [(ALWAYS, None, _ia_dur(40, 0.3))], scale="G")
    assert ULRates(repository=repo).get_rates("COI", "TEST", 40, "U", "N", scale=0, band=1) == [None, 0.3]
    repo.add_cell("COI", [(ALWAYS, None, _ia_dur(40, 0.2))], scale="G", sex="F")
    assert ULRates(repository=repo).get_rates("COI", "TEST", 40, "U", "N", scale=0, band=1) is None


def test_bands_use_inclusive_upper_limits_and_the_policy_issue_date():
    repo = FakeSchemaRepo()
    repo.add_band("1", 49_999.9999)
    repo.add_band("2", 250_000.9999)
    repo.add_band("3", 999_999_999.9999)
    repo.add_band("1", 49_999.9999, start=date(2018, 10, 1))
    repo.add_band("2", 249_999.9999, start=date(2018, 10, 1))
    repo.add_band("3", 999_999_999.9999, start=date(2018, 10, 1))
    rates = ULRates(repository=repo)
    assert rates.get_band("TEST", 49_999, issue_date=date(2020, 1, 1)) == 1
    assert rates.get_band("TEST", 50_000, issue_date=date(2020, 1, 1)) == 2
    assert rates.get_band("TEST", 250_000, issue_date=date(2020, 1, 1)) == 3
    assert rates.get_band("TEST", 250_000, issue_date=date(2015, 1, 1)) == 2
    assert rates.get_band_break("TEST", 2, issue_date=date(2020, 1, 1)) == 50_000.0


def test_unbanded_plan_is_band_zero_and_amounts_above_every_limit_raise():
    repo = FakeSchemaRepo()
    repo.add_band("0", None)
    repo.add_plan("CAPPED")
    repo.add_band("1", 250_000, plancode="CAPPED")
    rates = ULRates(repository=repo)
    assert rates.get_band("TEST", 1_000_000) == 0
    with pytest.raises(RatesError, match="above every band limit"):
        rates.get_band("CAPPED", 250_001)


def test_guaranteed_interest_is_a_plan_rate_schedule():
    repo = FakeSchemaRepo()
    repo.add_plan_rate("GINT", {(0, 1): 0.03, (0, 2): 0.03, (0, 3): 0.025})
    assert ULRates(repository=repo).get_rates("GINT", "TEST") == [None, 0.03, 0.03, 0.025]


def test_benefit_rates_need_the_benefit_type():
    repo = FakeSchemaRepo()
    repo.add_cell("COI", [(ALWAYS, None, _ia_dur(40, 0.1))], benefit="39", scale="C")
    rates = ULRates(repository=repo)
    assert rates.get_rates("BENCOI", "TEST", 40, "M", "N", band=1, benefit_type="39") == [None, 0.1]
    with pytest.raises(RatesError, match="needs a benefit type"):
        rates.get_rates("BENCOI", "TEST", 40, "M", "N", band=1)


def test_a_gap_inside_a_schedule_is_loud():
    repo = FakeSchemaRepo()
    repo.add_cell("EPU", [(ALWAYS, None, {(40, 1): 0.1, (40, 3): 0.1})], scale="G")
    with pytest.raises(RatesError, match="no rate for coverage year 2"):
        ULRates(repository=repo).get_rates("EPU", "TEST", 40, "M", "N", scale=0, band=1)
