"""PolView IUL fixed-account rate: bucket vs CIRF source, bonus removal, NY cap, display."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.declared_rates import DeclaredRate
from suiteview.polview.services import iul_fixed_rate as fr

NY = BonusConfig(bonus_dur_rate=0.01, bonus_dur_threshold=10, bonus_dur_cap_to_excess_over_guar=True)
PLAIN = BonusConfig(bonus_dur_rate=0.01, bonus_dur_threshold=10)


def _bucket(fund="SW", rate="3.800", impaired="0", start="2023-09-01", mvry="9999-12-31", csv=100.0):
    return {"FND_ID_CD": fund, "VAL_PHA_ITS_RT": rate, "IMPAIRED_IND": impaired,
            "ITS_RT_STR_DT": start, "MVRY_DT": mvry, "CSV_AMT": csv}


def _pi(rows, plancode="1U145900", year=9, company="26"):
    return SimpleNamespace(
        coverages=SimpleNamespace(base_plancode=plancode),
        company_code=company,
        activity=SimpleNamespace(policy_year=year),
        values=SimpleNamespace(valuation_date=date(2026, 9, 18), mv_av=lambda i=0: 1000.0),
        fetch_table=lambda table: rows if table == "LH_POL_FND_VAL_TOT" else [],
        reins_partner="",
    )


@pytest.fixture
def plan(monkeypatch):
    """Plan facts, CIRF rate and bonus row for a fake IUL plan (no UL_Rates access)."""
    state = {"cirf": DeclaredRate(0.041, "IULFIX14B@26", "CINT", date(2026, 1, 1)), "bonus": NY}
    monkeypatch.setattr(fr, "load_plan_facts",
                        lambda plancode: SimpleNamespace(gint=0.025, cint_key="IULFIX14B"))
    monkeypatch.setattr(fr, "ul_current_declared_rate", lambda *a, **k: state["cirf"])
    monkeypatch.setattr(fr, "load_bonus_config", lambda plancode, as_of: state["bonus"])
    return state


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


def test_bucket_is_the_source_and_cirf_disagreement_is_reported(plan):
    fixed = fr.iul_fixed_account_rate(_pi([_bucket()]), date(2026, 10, 3))
    assert fixed.source == fr.SOURCE_BUCKET
    assert fixed.credited_rate == pytest.approx(0.038)
    assert fixed.declared_rate == pytest.approx(0.038)
    assert fixed.cirf_disagrees


def test_bonus_in_bucket_is_removed_for_the_rate_ex_bonus(plan):
    plan["bonus"] = PLAIN
    plan["cirf"] = DeclaredRate(0.0325, "IULFIX14B", "CINT", date(2020, 5, 1))
    fixed = fr.iul_fixed_account_rate(_pi([_bucket(rate="4.250")], year=11), date(2026, 10, 3))
    assert (fixed.credited_rate, fixed.declared_rate, fixed.bonus_rate) == pytest.approx((0.0425, 0.0325, 0.01))
    assert not fixed.cirf_disagrees


def test_cirf_fallback_adds_ny_capped_bonus(plan):
    plan["cirf"] = DeclaredRate(0.03, "IULFIX14B@26", "CINT", date(2026, 1, 1))
    fixed = fr.iul_fixed_account_rate(_pi([], year=12), date(2026, 10, 3))
    assert fixed.source == fr.SOURCE_CIRF
    assert fixed.declared_rate == pytest.approx(0.03)
    assert fixed.credited_rate == pytest.approx(0.035)


def test_no_bucket_and_no_cirf_is_unavailable(plan):
    plan["cirf"] = None
    assert isinstance(fr.iul_fixed_account_rate(_pi([]), date(2026, 10, 3)), fr.IulFixedRateUnavailable)


def test_non_iul_plan_has_no_fixed_rate(plan):
    assert fr.iul_fixed_account_rate(_pi([_bucket()], plancode="1U135800"), date(2026, 10, 3)) is None


def test_apply_sets_projection_fixed_rate_ex_bonus(plan):
    plan["bonus"] = PLAIN
    fixed = fr.iul_fixed_account_rate(_pi([_bucket(rate="4.250")], year=11), date(2026, 10, 3))
    ill = SimpleNamespace(iul_declared_rate=None)
    fr.apply_fixed_rate(ill, fixed)
    assert ill.iul_declared_rate == pytest.approx(0.0325)
    untouched = SimpleNamespace(iul_declared_rate=None)
    fr.apply_fixed_rate(untouched, fr.IulFixedRateUnavailable("none"))
    assert untouched.iul_declared_rate is None


def test_ny_bonus_cap_uses_the_inforce_fixed_rate_not_gint(plan):
    """1U145900 year 11 at 3.8%: the capped bonus is 1%, not the GINT-based 0."""
    from suiteview.illustration.core.bonus_rates import fixed_account_rate

    fixed = fr.iul_fixed_account_rate(_pi([_bucket(rate="4.800")], year=11), date(2026, 10, 3))
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
    tab._load_iul_fixed_rate(
        fr.iul_fixed_account_rate(_pi([_bucket(rate="4.250")], year=11), date(2026, 10, 3)))
    fields = tab.policy_info._fields
    assert fields["iul_fixed_rate"].text() == "4.25%"
    assert fields["iul_fixed_rate_ex_bonus"].text() == "3.25%"
    assert "policy year 11: in effect" in fields["iul_fixed_rate"].toolTip()
    tab._load_iul_fixed_rate(None)
    assert fields["iul_fixed_rate"].text() == "N/A"
    assert "not an indexed UL plan" in fields["iul_fixed_rate_ex_bonus"].toolTip()


def _forecast(monkeypatch, fixed):
    from suiteview.polview.services import glp_exception as gep

    ill = SimpleNamespace(plancode="1U145900", valuation_date=date(2026, 9, 18), iul_declared_rate=None)
    monkeypatch.setattr(gep, "project_policy", lambda *a, **k: SimpleNamespace(policy=ill, rates="r", config="c"))
    monkeypatch.setattr(gep, "iul_fixed_account_rate", fixed)
    return gep._load_forecast_policy(SimpleNamespace(policy_number="UN003999", region="CKPR", company_code="26")), ill


def test_glp_forecast_uses_fixed_rate_and_fails_loudly(plan, monkeypatch):
    result, ill = _forecast(monkeypatch, lambda pi, as_of: fr.iul_fixed_account_rate(_pi([_bucket()]), as_of))
    assert result == (ill, "r", "c") and ill.iul_declared_rate == pytest.approx(0.038)
    result, _ = _forecast(monkeypatch, lambda pi, as_of: fr.IulFixedRateUnavailable("no bucket"))
    assert result == "Forecast data could not be loaded: no bucket"

    def boom(pi, as_of):
        raise ValueError("schema down")
    result, _ = _forecast(monkeypatch, boom)
    assert "IUL fixed-account rate failed: schema down" in result