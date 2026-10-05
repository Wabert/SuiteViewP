"""PolView fixed-account rate: bucket vs CIRF source, fixed funds, bonus removal, NY cap, display."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.declared_rates import DeclaredRate
from suiteview.polview.services import fixed_account_rate as fr

NY = BonusConfig(bonus_dur_rate=0.01, bonus_dur_threshold=10, bonus_dur_cap_to_excess_over_guar=True)
PLAIN = BonusConfig(bonus_dur_rate=0.01, bonus_dur_threshold=10)
ISWL = "80110429"


def _bucket(fund="SW", rate="3.800", impaired="0", start="2023-09-01", mvry="9999-12-31", csv=100.0):
    return {"FND_ID_CD": fund, "VAL_PHA_ITS_RT": rate, "IMPAIRED_IND": impaired,
            "ITS_RT_STR_DT": start, "MVRY_DT": mvry, "CSV_AMT": csv}


def _control(fund="I1", key="ELGRP0001  "):
    return {"FND_ID_CD": fund, "CUR_ITS_RT_SER_NBR": key, "COV_PHA_NBR": 1}


def _pi(rows, plancode="1U145900", year=9, company="26", control=(), stage=""):
    tables = {"LH_POL_FND_VAL_TOT": rows, "LH_COV_FXD_FND_CTL": list(control)}
    product_type = "ISWL" if plancode == ISWL else "UL"
    return SimpleNamespace(
        coverages=SimpleNamespace(base_plancode=plancode),
        product=SimpleNamespace(prospective_bonus_code=stage, product_type=product_type),
        company_code=company,
        activity=SimpleNamespace(policy_year=year),
        values=SimpleNamespace(valuation_date=date(2026, 9, 18), mv_av=lambda i=0: 1000.0),
        fetch_table=lambda table: tables.get(table, []),
        reins_partner="",
    )


@pytest.fixture
def plan(monkeypatch):
    """Plan facts, CIRF rate and bonus row for a fake plan (no UL_Rates access)."""
    state = {"cirf": DeclaredRate(0.041, "IULFIX14B@26", "CINT", date(2026, 1, 1)), "bonus": NY,
             "cint_key": "IULFIX14B"}
    monkeypatch.setattr(fr, "load_plan_facts",
                        lambda plancode: SimpleNamespace(gint=0.025, cint_key=state["cint_key"]))
    monkeypatch.setattr(fr, "ul_current_declared_rate", lambda *a, **k: state["cirf"])
    monkeypatch.setattr(fr, "load_bonus_config", lambda plancode, as_of: state["bonus"])
    return state


@pytest.fixture
def iswl(plan):
    """An ISWL plan: no bonus row, CIRF key ELGRP0001 with no UL_Rates rate."""
    plan.update(cirf=None, bonus=BonusConfig(), cint_key="ELGRP0001")
    return plan


def test_bonus_applies_only_after_threshold_year():
    assert fr.bonus_in_effect(PLAIN, 10, 0.0) == 0.0
    assert fr.bonus_in_effect(PLAIN, 11, 0.0) == 0.01


@pytest.mark.parametrize("declared", [0.025, 0.028, 0.0325, 0.035, 0.038, 0.045])
def test_ny_cap_inverse_recovers_declared_rate(declared):
    credited = declared + fr.capped_bonus(0.01, True, declared, 0.025)
    assert fr.declared_from_credited(credited, 0.01, True, 0.025) == pytest.approx(declared)


def test_plain_bonus_is_subtracted():
    assert fr.declared_from_credited(0.0425, 0.01, False, 0.025) == pytest.approx(0.0325)
    assert fr.declared_from_credited(0.0325, 0.0, False, 0.025) == 0.0325


def test_bucket_rate_prefers_current_unimpaired_fixed_funds():
    rows = [
        _bucket(rate="9.000", mvry="2026-09-18"),
        _bucket(fund="IX", rate="7.000"),
        _bucket(rate="4.000", impaired="1"),
        _bucket(fund="U1", rate="3.800"),
    ]
    bucket = fr.fixed_bucket_rate(_pi(rows))
    assert bucket.rate == pytest.approx(0.038)
    assert bucket.funds == ("U1",)
    assert bucket.rate_start == date(2023, 9, 1)


def test_impaired_bucket_used_when_it_is_the_only_one():
    assert fr.fixed_bucket_rate(_pi([_bucket(rate="3.750", impaired="1")])).rate == pytest.approx(0.0375)


def test_fixed_funds_iul_uses_u1_sw_others_use_keyed_fixed_fund_control():
    control = [_control("U1", "IULFIX14B"), _control("IX", "IULINDEX14"), _control("SW", "IULFIX14B")]
    assert fr.fixed_fund_ids(_pi([], control=control), is_iul=True) == ("U1", "SW")
    assert fr.fixed_fund_ids(_pi([], control=[_control("I1"), _control("I1")]), is_iul=False) == ("I1",)
    assert fr.policy_cirf_key(_pi([], control=control), ("U1", "SW")) == "IULFIX14B"
    blank = [_control("01", "\x00" * 11), _control("GP", " " * 11)]
    assert fr.policy_cirf_key(_pi([], control=blank), ("01",)) == ""
    assert fr.fixed_fund_ids(_pi([], control=blank), is_iul=False) == ("01",)


def test_keyless_gp_holding_fund_never_sets_the_rate():
    """UE148375 (SGUL 1U147600): U1 SGUL2021 1.50% since 2016; GP 0% blank-key holding fund since 2021."""
    control = [_control("GP", " " * 11), _control("U1", "SGUL2021   ")]
    rows = [_bucket(fund="U1", rate="1.500", start="2016-01-01", csv=1143.42),
            _bucket(fund="GP", rate="0.000", start="2021-09-12", csv=None)]
    pi = _pi(rows, control=control)
    funds = fr.fixed_fund_ids(pi, is_iul=False)
    assert funds == ("U1",)
    assert fr.fixed_bucket_rate(pi, funds).rate == pytest.approx(0.015)


def test_bucket_is_the_source_and_cirf_disagreement_is_reported(plan):
    fixed = fr.fixed_account_rate(_pi([_bucket()]), date(2026, 10, 3))
    assert fixed.source == fr.SOURCE_BUCKET and fixed.is_iul
    assert fixed.credited_rate == pytest.approx(0.038)
    assert fixed.declared_rate == pytest.approx(0.038)
    assert fixed.cirf_disagrees


def test_bonus_in_bucket_is_removed_for_the_rate_ex_bonus(plan):
    plan["bonus"] = PLAIN
    plan["cirf"] = DeclaredRate(0.0325, "IULFIX14B", "CINT", date(2020, 5, 1))
    fixed = fr.fixed_account_rate(_pi([_bucket(rate="4.250")], year=11), date(2026, 10, 3))
    assert (fixed.credited_rate, fixed.declared_rate, fixed.bonus_rate) == pytest.approx((0.0425, 0.0325, 0.01))
    assert not fixed.cirf_disagrees


def test_cirf_fallback_adds_ny_capped_bonus(plan):
    plan["cirf"] = DeclaredRate(0.03, "IULFIX14B@26", "CINT", date(2026, 1, 1))
    fixed = fr.fixed_account_rate(_pi([], year=12), date(2026, 10, 3))
    assert fixed.source == fr.SOURCE_CIRF
    assert fixed.declared_rate == pytest.approx(0.03)
    assert fixed.credited_rate == pytest.approx(0.035)


def test_no_bucket_and_no_cirf_is_unavailable(plan):
    plan["cirf"] = None
    assert isinstance(fr.fixed_account_rate(_pi([]), date(2026, 10, 3)), fr.FixedRateUnavailable)


def test_iswl_reads_its_fixed_fund_bucket_and_has_no_bonus(iswl):
    """CKPR 01 10497580 (ISWL 80110429): fund I1, 4.000% since 09/01/2009, no UL_Rates CIRF rate."""
    rows = [_bucket(fund="I1", rate="4.000", start="2003-07-01", csv=45809.37),
            _bucket(fund="I1", rate="4.000", start="2009-09-01", csv=10.74)]
    fixed = fr.fixed_account_rate(_pi(rows, plancode=ISWL, year=43, control=[_control()]), date(2026, 10, 4))
    assert not fixed.is_iul and fixed.source == fr.SOURCE_BUCKET
    assert fixed.fixed_funds == ("I1",) and fixed.cirf_key == "ELGRP0001"
    assert (fixed.credited_rate, fixed.declared_rate, fixed.bonus_rate) == pytest.approx((0.04, 0.04, 0.0))
    assert fixed.bucket.rate_start == date(2009, 9, 1)


def test_non_iul_bonus_row_is_removed(iswl):
    iswl["bonus"] = PLAIN
    fixed = fr.fixed_account_rate(
        _pi([_bucket(fund="I1", rate="4.500")], plancode=ISWL, year=11, control=[_control()]), date(2026, 10, 4))
    assert (fixed.credited_rate, fixed.declared_rate) == pytest.approx((0.045, 0.035))


def test_non_iul_without_bucket_or_cirf_names_the_cirf_key(iswl):
    fixed = fr.fixed_account_rate(_pi([], plancode=ISWL, control=[_control()]), date(2026, 10, 4))
    assert isinstance(fixed, fr.FixedRateUnavailable)
    assert "fixed funds: I1" in fixed.reason and "CIRF key ELGRP0001" in fixed.reason


def test_apply_sets_projection_fixed_rate_ex_bonus_for_iul_only(plan):
    plan["bonus"] = PLAIN
    fixed = fr.fixed_account_rate(_pi([_bucket(rate="4.250")], year=11), date(2026, 10, 3))
    ill = SimpleNamespace(iul_declared_rate=None)
    fr.apply_fixed_rate(ill, fixed)
    assert ill.iul_declared_rate == pytest.approx(0.0325)
    untouched = SimpleNamespace(iul_declared_rate=None)
    fr.apply_fixed_rate(untouched, fr.FixedRateUnavailable("none"))
    assert untouched.iul_declared_rate is None
    plan.update(cint_key="ELGRP0001", bonus=BonusConfig())
    non_iul = fr.fixed_account_rate(
        _pi([_bucket(fund="I1", rate="4.000")], plancode=ISWL, control=[_control()]), date(2026, 10, 4))
    fr.apply_fixed_rate(untouched, non_iul)
    assert untouched.iul_declared_rate is None


def test_ny_bonus_cap_uses_the_inforce_fixed_rate_not_gint(plan):
    """1U145900 year 11 at 3.8%: the capped bonus is 1%, not the GINT-based 0."""
    from suiteview.illustration.core.bonus_rates import fixed_account_rate

    fixed = fr.fixed_account_rate(_pi([_bucket(rate="4.800")], year=11), date(2026, 10, 3))
    assert fixed.declared_rate == pytest.approx(0.038)
    ill = SimpleNamespace(plancode="1U145900", iul_declared_rate=None, guaranteed_interest_rate=0.025,
                          current_interest_rate=0.025)
    assert NY.capped_for(ill).bonus_dur_rate == 0.0
    fr.apply_fixed_rate(ill, fixed)
    assert fixed_account_rate(ill) == pytest.approx(0.038)
    assert NY.capped_for(ill).bonus_dur_rate == pytest.approx(0.01)


def test_account_values_tab_shows_rate_with_and_without_bonus(plan, qtbot):
    from suiteview.polview.ui.tabs.adv_prod_tab import AdvProdValuesTab

    plan["bonus"] = PLAIN
    plan["cirf"] = DeclaredRate(0.0325, "IULFIX14B", "CINT", date(2020, 5, 1))
    tab = AdvProdValuesTab()
    qtbot.addWidget(tab)
    tab._load_fixed_rate(
        fr.fixed_account_rate(_pi([_bucket(rate="4.250")], year=11), date(2026, 10, 3)))
    fields, labels = tab.policy_info._fields, tab.policy_info._labels
    assert labels["fixed_crediting_rate"].text() == "Fixed Crediting Rate:"
    assert fields["fixed_crediting_rate"].text() == "4.25%"
    assert fields["fixed_rate_ex_bonus"].text() == "3.25%"
    assert "policy year 11: in effect" in fields["fixed_crediting_rate"].toolTip()
    tab._load_fixed_rate(fr.FixedRateUnavailable("no bucket"))
    assert fields["fixed_crediting_rate"].text() == "N/A"
    assert fields["fixed_rate_ex_bonus"].toolTip() == "no bucket"


def test_account_values_tab_shows_iswl_rate_and_missing_cirf(iswl, qtbot):
    from suiteview.polview.ui.tabs.adv_prod_tab import AdvProdValuesTab

    tab = AdvProdValuesTab()
    qtbot.addWidget(tab)
    tab._load_fixed_rate(fr.fixed_account_rate(
        _pi([_bucket(fund="I1", rate="4.000", start="2009-09-01")], plancode=ISWL, year=43,
            control=[_control()]), date(2026, 10, 4)))
    fields = tab.policy_info._fields
    assert (fields["fixed_crediting_rate"].text(), fields["fixed_rate_ex_bonus"].text()) == ("4.00%", "4.00%")
    tip = fields["fixed_crediting_rate"].toolTip()
    assert "I1 (LH_COV_FXD_FND_CTL)" in tip and "UL_Rates has no CIRF declared rate for ELGRP0001" in tip
    assert "ex bonus = crediting rate" in tip and "GLP Exception" not in tip


def _forecast(monkeypatch, fixed):
    from suiteview.polview.services import glp_exception as gep

    ill = SimpleNamespace(plancode="1U145900", valuation_date=date(2026, 9, 18), iul_declared_rate=None)
    monkeypatch.setattr(gep, "project_policy", lambda *a, **k: SimpleNamespace(policy=ill, rates="r", config="c"))
    monkeypatch.setattr(gep, "fixed_account_rate", fixed)
    return gep._load_forecast_policy(SimpleNamespace(policy_number="UN003999", region="CKPR", company_code="26")), ill


def test_glp_forecast_uses_fixed_rate_and_fails_loudly(plan, monkeypatch):
    result, ill = _forecast(monkeypatch, lambda pi, as_of: fr.fixed_account_rate(_pi([_bucket()]), as_of))
    assert result == (ill, "r", "c") and ill.iul_declared_rate == pytest.approx(0.038)
    result, _ = _forecast(monkeypatch, lambda pi, as_of: fr.FixedRateUnavailable("no bucket"))
    assert result == "Forecast data could not be loaded: no bucket"

    def boom(pi, as_of):
        raise ValueError("schema down")
    result, _ = _forecast(monkeypatch, boom)
    assert "IUL fixed-account rate failed: schema down" in result


def _anico_control(rate="3.000"):
    return {"FND_ID_CD": "U1", "CUR_ITS_RT_SER_NBR": "ANICO1996  ", "COV_PHA_NBR": 1,
            "GUA_FND_ITS_RT": rate}


@pytest.mark.parametrize("plancode, stage, bucket, ex_bonus, bonus", [
    ("1U135900", "6", "3.750", 0.03, 0.0075),   # U0424736 (1U135900, year 25)
    ("1U135900", "5", "3.500", 0.03, 0.005),    # stuck at tier 1 past year 21
    ("1U135H00", "0", "3.000", 0.03, 0.0),      # U0404037 (1U135H00): never earned a bonus
    # 1U135H00 has the 0.50% tier only (Robert Haessly, 10/5/2026), even at code 6; CyberLife's
    # bucket shows 3.75% on such policies (open item), so the ex-bonus rate reads 3.25%.
    ("1U135H00", "6", "3.750", 0.0325, 0.005),
])
def test_pulu_rate_ex_bonus_removes_the_tier_the_policy_earned(plan, plancode, stage, bucket, ex_bonus,
                                                               bonus):
    from suiteview.illustration.core.bonus_rates import load_bonus_config

    plan["bonus"] = load_bonus_config(plancode, date(2026, 10, 4))
    pi = _pi([_bucket(fund="U1", rate=bucket)], plancode=plancode, year=26, company="01",
             control=[_anico_control()], stage=stage)
    fixed = fr.fixed_account_rate(pi, date(2026, 10, 4))
    assert (fixed.declared_rate, fixed.bonus_rate) == pytest.approx((ex_bonus, bonus))


@pytest.mark.parametrize("guarantee, floor", [("3.000", 0.03), ("3.250", 0.0325)])
def test_anico1996_cirf_floor_is_the_policy_guarantee_not_gint(plan, monkeypatch, guarantee, floor):
    """SR113413: guaranteed 4% in years 1-10, then 3% (3.25% TX); plan GINT 4% is the NAR discount."""
    seen = {}

    def cirf(company, plancode, as_of, guaranteed_rate, **_kwargs):
        seen["floor"] = guaranteed_rate
        return DeclaredRate(max(0.03, guaranteed_rate), "ANICO1996", "CINT", date(2022, 11, 1))

    monkeypatch.setattr(fr, "load_plan_facts", lambda plancode: SimpleNamespace(gint=0.04, cint_key="ANICO1996"))
    monkeypatch.setattr(fr, "ul_current_declared_rate", cirf)
    plan["bonus"] = BonusConfig()
    pi = _pi([], plancode="1U135D00", year=22, company="01", control=[_anico_control(guarantee)])
    fixed = fr.fixed_account_rate(pi, date(2026, 10, 4))
    assert seen["floor"] == pytest.approx(floor)
    assert fixed.cirf.rate == pytest.approx(floor)


def test_iul_and_iswl_cirf_floor_stays_gint(plan):
    loan_fund = {"FND_ID_CD": "LF", "GUA_FND_ITS_RT": "6.000"}
    assert fr._declared_rate_floor(_pi([], control=[loan_fund]), True, 0.025) == 0.025
    assert fr._declared_rate_floor(_pi([], plancode=ISWL, control=[loan_fund]), False, 0.04) == 0.04
    assert fr._declared_rate_floor(_pi([], plancode="1U135D00"), False, 0.04) == 0.04
