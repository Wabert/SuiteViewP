"""Declared-rate UL current crediting rate from the plan's CIRF fund (schema ``rates``)."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from suiteview.core.rates_schema import FundAssignment, FundRate, PlanDef
from suiteview.illustration.core.declared_rates import ul_current_declared_rate
from suiteview.illustration.core.input_context import _interest_assumptions
from suiteview.illustration.models.policy_data import IllustrationPolicyData

PLAN = "1U14L100"


class _Repo:
    def __init__(self, funds=None, rates=None, plans=None):
        self.funds = funds if funds is not None else [
            FundAssignment("FL4RPORT", "", "FL4RPORT", "CIRF", "CIRF 01 FL4RPORT", "")]
        self.rates = rates if rates is not None else [
            FundRate("FL4RPORT", "CINT", "C", date(2021, 1, 1), 0, None, None, Decimal("0.031")),
            FundRate("FL4RPORT", "CINT", "C", date(2023, 1, 1), 0, None, None, Decimal("0.0325")),
            FundRate("FL4RPORT", "CINT", "C", date(2024, 4, 1), 0, None, None, Decimal("0.035")),
        ]
        self.plans = plans if plans is not None else [PlanDef("00", PLAN, "00", "UL", "BASE", PLAN, ())]

    def plan_defs(self, plancode):
        return [plan for plan in self.plans if plan.plancode == plancode]

    def fund_assignments(self, company, plancode):
        return list(self.funds)

    def fund_rates(self, fund_keys):
        return [rate for rate in self.rates if rate.fund_key in fund_keys]


def test_latest_portfolio_rate_on_or_before_the_illustration_date():
    rate = ul_current_declared_rate("26", PLAN, date(2026, 9, 30), 0.03, cint_key="FL4RPORT", repo=_Repo())
    assert rate.rate == pytest.approx(0.035)
    assert rate.rate_start == date(2024, 4, 1)
    assert "FL4RPORT" in rate.source

    earlier = ul_current_declared_rate("26", PLAN, date(2024, 3, 31), 0.03, repo=_Repo())
    assert earlier.rate == pytest.approx(0.0325)


def test_declared_rate_is_floored_at_gint():
    rate = ul_current_declared_rate("26", PLAN, date(2026, 9, 30), 0.04, repo=_Repo())
    assert rate.rate == pytest.approx(0.04)


def test_no_cirf_fund_or_no_plan_keeps_gint():
    assert ul_current_declared_rate("26", PLAN, date(2026, 9, 30), 0.03, repo=_Repo(funds=[])) is None
    assert ul_current_declared_rate("26", PLAN, date(2026, 9, 30), 0.03, repo=_Repo(plans=[])) is None
    # Nothing effective yet on the illustration date.
    assert ul_current_declared_rate("26", PLAN, date(2020, 1, 1), 0.03, repo=_Repo()) is None


def test_cint_key_selects_the_plan_fund_and_ambiguity_is_not_guessed():
    funds = [FundAssignment("F1", "", "FL4RPORT", "CIRF", "", ""),
             FundAssignment("F2", "", "OTHER", "CIRF", "", "")]
    rates = _Repo().rates + [FundRate("OTHER", "CINT", "C", date(2025, 1, 1), 0, None, None, Decimal("0.05"))]
    repo = _Repo(funds=funds, rates=rates)
    assert ul_current_declared_rate("26", PLAN, date(2026, 9, 30), 0.03, cint_key="FL4RPORT",
                                    repo=repo).rate == pytest.approx(0.035)
    assert ul_current_declared_rate("26", PLAN, date(2026, 9, 30), 0.03, repo=repo) is None


def test_rga_policies_read_the_cirf_r_block_when_loaded():
    # R01: CIRF 09/01/26 carries ANICO2019 (2.55%) and 'ANICO2019 R' (2.30%).
    funds = [FundAssignment("ANICO2019", "", "ANICO2019", "CIRF", "", ""),
             FundAssignment("ANICO2019", "R", "ANICO2019 R", "CIRF", "", "")]
    rates = [FundRate("ANICO2019", "CINT", "C", date(2026, 9, 1), 0, None, None, Decimal("0.0255")),
             FundRate("ANICO2019 R", "CINT", "C", date(2026, 9, 1), 0, None, None, Decimal("0.023"))]
    repo = _Repo(funds=funds, rates=rates)
    direct = ul_current_declared_rate("26", PLAN, date(2026, 9, 30), 0.02, cint_key="ANICO2019", repo=repo)
    rga = ul_current_declared_rate("26", PLAN, date(2026, 9, 30), 0.02, cint_key="ANICO2019",
                                   rga_indicator="R", repo=repo)
    assert (direct.rate, direct.fund_key) == (pytest.approx(0.0255), "ANICO2019")
    assert (rga.rate, rga.fund_key) == (pytest.approx(0.023), "ANICO2019 R")
    # Without an R block an RGA policy shares the direct block.
    shared = ul_current_declared_rate("26", PLAN, date(2026, 9, 30), 0.03, rga_indicator="R", repo=_Repo())
    assert shared.rate == pytest.approx(0.035)


def test_new_money_rates_only_when_they_agree():
    agree = [FundRate("FL4RPORT", "CINT_NEW", "C", date(2025, 1, 1), 1, 12, None, Decimal("0.036")),
             FundRate("FL4RPORT", "CINT_ROLL", "C", date(2024, 1, 1), 0, None, None, Decimal("0.036"))]
    rate = ul_current_declared_rate("26", PLAN, date(2026, 9, 30), 0.03, repo=_Repo(rates=agree))
    assert rate.rate == pytest.approx(0.036)
    differ = [agree[0], FundRate("FL4RPORT", "CINT_ROLL", "C", date(2024, 1, 1), 0, None, None, Decimal("0.034"))]
    assert ul_current_declared_rate("26", PLAN, date(2026, 9, 30), 0.03, repo=_Repo(rates=differ)) is None


def test_rerun_illustrated_rate_defaults_to_the_sourced_declared_rate():
    policy = IllustrationPolicyData(plancode=PLAN, current_interest_rate=0.035,
                                    current_interest_rate_source="CIRF FL4RPORT CINT")
    assert _interest_assumptions(policy) == (PLAN, 0.035, 0.03)


def test_rerun_illustrated_rate_keeps_gint_without_a_sourced_rate():
    policy = IllustrationPolicyData(plancode=PLAN, current_interest_rate=0.035)
    assert _interest_assumptions(policy)[1] == 0.03
    legacy = SimpleNamespace(base_plancode=PLAN)
    assert _interest_assumptions(legacy)[1] == 0.03


@pytest.mark.parametrize("reins, expected", [("R", "R"), ("", "")])
def test_policy_service_routes_the_rga_indicator_to_the_cirf_lookup(monkeypatch, reins, expected):
    from suiteview.illustration.core import declared_rates, illustration_policy_service as svc

    source = SimpleNamespace(
        pi=SimpleNamespace(company_code="01", reins_partner=reins, fetch_table=lambda _t: []),
        plancode="1U147000", illustration_date=date(2026, 9, 30),
        plancode_config=SimpleNamespace(gint=0.02, is_iswl=False, cint_key="ANICO2019"),
    )
    seen = []

    def _declared(_company, _plan, _as_of, guaranteed, **kwargs):
        seen.append((guaranteed, kwargs["rga_indicator"]))
        return declared_rates.DeclaredRate(0.023, "ANICO2019 R", "CINT", date(2026, 9, 1))

    monkeypatch.setattr(declared_rates, "ul_current_declared_rate", _declared)
    assert svc._current_interest_rate(source)[0] == pytest.approx(0.023)
    assert seen == [(0.02, expected)]


@pytest.mark.parametrize("rows, expected", [
    ([{"GUA_FND_ITS_RT": Decimal("3.250")}], 0.0325),      # U0482280: floor above plan GINT 3.00%
    ([{"GUA_FND_ITS_RT": Decimal("3.000")}], 0.03),
    ([{"GUA_FND_ITS_RT": Decimal("2.000")}, {"GUA_FND_ITS_RT": Decimal("3.250")}], 0.0325),
    ([{"GUA_FND_ITS_RT": None}], 0.03),
    ([], 0.03),
])
def test_declared_rate_floor_is_the_fixed_fund_guaranteed_rate(monkeypatch, rows, expected):
    from suiteview.illustration.core import declared_rates, illustration_policy_service as svc

    tables = []
    source = SimpleNamespace(
        pi=SimpleNamespace(company_code="01", reins_partner="",
                           fetch_table=lambda name: tables.append(name) or rows),
        plancode="1U135K00", illustration_date=date(2026, 9, 30),
        plancode_config=SimpleNamespace(gint=0.03, is_iswl=False, cint_key="ANICO1996"),
    )
    floors = []

    def _declared(_company, _plan, _as_of, guaranteed, **_kwargs):
        floors.append(guaranteed)
        return declared_rates.DeclaredRate(max(0.0255, guaranteed), "ANICO1996", "CINT", date(2026, 5, 1))

    monkeypatch.setattr(declared_rates, "ul_current_declared_rate", _declared)
    assert svc._current_interest_rate(source)[0] == pytest.approx(expected)
    assert floors == [pytest.approx(expected)]
    assert set(tables) == {"LH_COV_FXD_FND_CTL"}

    monkeypatch.setattr(declared_rates, "ul_current_declared_rate", lambda *_a, **_k: None)
    assert svc._current_interest_rate(source) == (pytest.approx(expected), "")
