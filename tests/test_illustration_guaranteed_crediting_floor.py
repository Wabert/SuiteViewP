"""Guaranteed crediting at the policy guarantee for the ANICO1996 4%-GINT plans.

Product specs Section M and SR113413: the guaranteed rate is 4% in policy years 1-10 and
3% thereafter (3.25% in Texas), the policy's LH_COV_FXD_FND_CTL.GUA_FND_ITS_RT. The plan
GINT (4%) stays the NAR discount, so monthly deductions do not change.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import guaranteed_projection, illustration_policy_service
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.declared_rates import policy_guaranteed_rate
from suiteview.illustration.core.interest_calc import credit_interest
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def _pi(*rates):
    rows = [{"FND_ID_CD": "U1", "GUA_FND_ITS_RT": rate} for rate in rates]
    return SimpleNamespace(fetch_table=lambda table: rows if table == "LH_COV_FXD_FND_CTL" else [])


def _source(plancode, gint, *rates, iswl=False):
    from suiteview.illustration.models.plancode_config import PRODUCT_FAMILY_ISWL

    config = PlancodeConfig(plancode=plancode, gint=gint, dbd=gint)
    if iswl:
        config.product_family = PRODUCT_FAMILY_ISWL
    return SimpleNamespace(pi=_pi(*rates), plancode=plancode, plancode_config=config)


def test_policy_guarantee_is_the_highest_fund_rate_else_gint():
    assert policy_guaranteed_rate(_pi("3.000", "3.250"), 0.04) == pytest.approx(0.0325)
    assert policy_guaranteed_rate(_pi(), 0.04) == 0.04
    assert policy_guaranteed_rate(_pi("0.000"), 0.03) == 0.03


@pytest.mark.parametrize("plancode, gint, rates, expected", [
    ("1U135D00", 0.04, ("3.000",), 0.03),
    ("1U135900", 0.04, ("3.250",), 0.0325),
    ("1U135P00", 0.03, ("3.000",), None),     # DIUL: GINT is already 3%
    ("1U143900", 0.03, ("3.000",), None),
    ("1U135D00", 0.04, (), None),
])
def test_legacy_guaranteed_crediting_rate_only_where_it_differs_from_gint(plancode, gint, rates, expected):
    rate = illustration_policy_service._legacy_guaranteed_crediting_rate(_source(plancode, gint, *rates))
    assert rate == (pytest.approx(expected) if expected is not None else None)


def test_iul_and_iswl_keep_gint(monkeypatch):
    monkeypatch.setattr(illustration_policy_service, "is_iul_plan", lambda plancode: plancode == "IUL")
    assert illustration_policy_service._legacy_guaranteed_crediting_rate(_source("IUL", 0.025, "6.000")) is None
    assert illustration_policy_service._legacy_guaranteed_crediting_rate(
        _source("ISWL", 0.04, "3.000", iswl=True)) is None


def test_ultimate_rate_replaces_the_crediting_rate_after_year_10():
    policy = IllustrationPolicyData(plancode="1U135D00", current_interest_rate=0.04, ultimate_interest_rate=0.03)
    config = PlancodeConfig(plancode="1U135D00", gint=0.04, dbd=0.04)

    def rate(year):
        return credit_interest(1_000.0, policy, config, IllustrationRates(), BonusConfig(), year, 50,
                               date(2026, 10, 1)).annual_interest_rate

    assert (rate(10), rate(11), rate(30)) == (0.04, 0.03, 0.03)
    policy.ultimate_interest_rate = None
    assert rate(30) == 0.04


def test_guaranteed_projection_credits_gint_then_the_policy_guarantee(monkeypatch):
    captured = {}

    class _Engine:
        def project(self, gpolicy, **kwargs):
            captured["policy"] = gpolicy
            captured["bonus"] = kwargs["bonus_override"]
            return []

    monkeypatch.setattr(guaranteed_projection, "load_plancode",
                        lambda plancode: PlancodeConfig(plancode=plancode, gint=0.04, dbd=0.04))
    monkeypatch.setattr(guaranteed_projection, "load_rates", lambda *a, **k: IllustrationRates())
    policy = IllustrationPolicyData(
        plancode="1U135D00", issue_date=date(2004, 12, 28), valuation_date=date(2026, 9, 28),
        policy_year=22, duration=262, guaranteed_interest_rate=0.04, current_interest_rate=0.0325,
        guaranteed_crediting_rate=0.0325)
    states = [MonthlyState(duration=262), MonthlyState(duration=263)]
    guaranteed_projection.run_guaranteed_projection(policy, states, engine=_Engine())
    gpolicy = captured["policy"]
    assert gpolicy.current_interest_rate == 0.04          # years 1-10
    assert gpolicy.ultimate_interest_rate == 0.0325       # years 11+
    assert gpolicy.guaranteed_interest_rate == 0.04       # NAR discount unchanged
    assert policy.ultimate_interest_rate is None          # the current-side policy is untouched

    plain = IllustrationPolicyData(plancode="1U143900", guaranteed_interest_rate=0.03,
                                   current_interest_rate=0.035, issue_date=date(2010, 1, 1))
    guaranteed_projection.run_guaranteed_projection(plain, states, engine=_Engine())
    assert captured["policy"].ultimate_interest_rate is None
    assert captured["policy"].current_interest_rate == 0.03
