"""UL rule-5 surrender charges: company-26 FFL NU1FU100 and NU1F1N00.

UL_Rates ``PLAN_DEF`` carries ``SCR_RULES`` 50 / ``SCR_TABLE`` C1 for both plans and loads
``SCR_PCT`` (10% in year 1, falling 1% a year to 0 from year 11), not a per-unit ``SCR``.
Every CKPR policy on them carries full surrender rule 5 and partial surrender rule 1
(LH_NON_TRD_POL, 10/7/2026). CyberDoc D10 rule 5: a free amount (a percentage of cash value,
0 for C1) is subtracted and the excess is multiplied by the percentage, so the full surrender
charge is ``SCR_PCT x AV``. They are therefore not FFL per-unit (rule 6) plans: no per-unit
grade, no original-units basis, no TOT_WTD_CRG_AMT credit and no partial percentage charge.
"""
from __future__ import annotations

from datetime import date

import pytest

import suiteview.illustration.models.plancode_config as pc
from suiteview.illustration.core import calc_engine
from suiteview.illustration.core import withdrawal_handler as wh
from suiteview.illustration.core.iswl_rates import (
    ULPctOfAVSurrender,
    load_ul_pct_of_av_surrender,
    rule_5_surrender_pct,
)
from suiteview.illustration.core.rate_loader import IllustrationRates, RateLookupError
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from tests.plan_facts_fixtures import plan_facts

C1 = [None, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01] + [0.0] * 30
RULE_5 = PlancodeConfig(plancode="NU1FU100", company_sub="FFL", scr_rules="50", scr_table="C1")
RULE_6 = PlancodeConfig(plancode="NU1FU200", company_sub="FFL", scr_rules="60", scr_table="70")
ISSUE = date(1984, 3, 15)


def _segment(phase=1, units=100.0, original_units=None, issue=ISSUE):
    original = units if original_units is None else original_units
    return CoverageSegment(coverage_phase=phase, issue_date=issue, issue_age=35, units=units,
                           face_amount=units * 1000.0, original_face_amount=original * 1000.0)


def _policy(*segments):
    return IllustrationPolicyData(company_code="26", plancode="NU1FU100", issue_date=ISSUE,
                                  segments=list(segments or [_segment()]))


def _rates(graded=True, phase=1):
    return IllustrationRates(pct_scr=ULPctOfAVSurrender(phase, list(C1), graded))


# -- classification ------------------------------------------------------------------

def test_rule_5_ffl_plan_is_not_a_per_unit_plan():
    assert RULE_5.ul_pct_of_av_surrender_charge
    assert not RULE_5.ffl_per_unit_surrender_charge
    assert not RULE_5.surrender_charge_on_original_units
    assert not RULE_5.partial_surrender_charge and not RULE_5.face_decrease_surrender_charge
    assert RULE_5.is_ffl and RULE_5.sa_basis == "CurrentSA"


@pytest.mark.parametrize("config", [
    RULE_6,
    PlancodeConfig(company_sub="FFL"),                    # rules not loaded: unchanged
    PlancodeConfig(company_sub="FFL", scr_rules="00"),    # no charge (08126100)
])
def test_rule_6_and_unknown_rules_stay_per_unit(config):
    assert not config.ul_pct_of_av_surrender_charge
    assert config.ffl_per_unit_surrender_charge and config.partial_surrender_charge


def test_iswl_rule_5_is_not_a_ul_pct_plan():
    iswl = PlancodeConfig(company_sub="FFL", product_family="ISWL", scr_rules="50", scr_table="C9")
    assert not iswl.ul_pct_of_av_surrender_charge and iswl.partial_surrender_charge


def test_rule_5_with_a_surrender_target_percentage_is_rejected():
    with pytest.raises(ValueError, match="SCR_PctOfSurrenderTarget conflicts"):
        PlancodeConfig(company_sub="FFL", scr_rules="50", scr_pct_of_surrender_target=(0.5,))


def test_load_plancode_takes_the_rules_from_plan_def(monkeypatch):
    monkeypatch.setattr(pc, "_CONFIG_CACHE", {})
    monkeypatch.setattr(pc, "_TABLE_CACHE", {"NU1FU100": {
        "Plancode": "NU1FU100", "SA_Basis": "CurrentSA", "CompanySub": "FFL"}})
    monkeypatch.setattr(pc, "load_plan_facts",
                        lambda code: plan_facts(code, scr_rules="50", scr_table="C1"))
    config = load_plancode("NU1FU100")
    assert (config.scr_rules, config.scr_table) == ("50", "C1")
    assert config.ul_pct_of_av_surrender_charge and not config.ffl_per_unit_surrender_charge


# -- SCR_PCT loading -----------------------------------------------------------------

class _RatesDB:
    def __init__(self, scr_pct=C1[:12], scr=None):
        self.tables = {"SCR_PCT": scr_pct, "SCR": scr}
        self.calls = []

    def get_rates(self, rate_type, plancode, **cell):
        self.calls.append((rate_type, plancode, cell))
        return self.tables.get(rate_type)


def test_loader_reads_scr_pct_for_the_base_phase():
    db = _RatesDB()
    policy = _policy(_segment(1), _segment(2, issue=date(1990, 3, 15)))
    basis = load_ul_pct_of_av_surrender(policy, RULE_5, db)
    assert basis.base_coverage_phase == 1 and basis.surrender_charge_graded
    assert basis.surrender_charge_pct[1] == 0.10 and basis.surrender_charge_pct[-1] == 0.0
    assert {call[0] for call in db.calls} == {"SCR", "SCR_PCT"}
    assert db.calls[-1][2]["issue_age"] == 35


def test_loader_ignores_per_unit_plans():
    assert load_ul_pct_of_av_surrender(_policy(), RULE_6, _RatesDB()) is None


@pytest.mark.parametrize("config, db, message", [
    (PlancodeConfig(plancode="X", company_sub="FFL", scr_rules="50", scr_table="Q7"), _RatesDB(),
     "table Q7"),
    (RULE_5, _RatesDB(scr_pct=None), "no SCR_PCT"),
    (RULE_5, _RatesDB(scr=[None, 5.0]), "both dollar SCR and SCR_PCT"),
    (RULE_5, _RatesDB(scr_pct=[None, 10.0]), "not a fraction"),
])
def test_loader_refuses_to_illustrate_a_zero_charge(config, db, message):
    with pytest.raises(RateLookupError, match=message):
        load_ul_pct_of_av_surrender(_policy(), config, db)


# -- full surrender charge -----------------------------------------------------------

@pytest.mark.parametrize("on, pct", [
    (date(1984, 9, 20), 0.10),     # year 1: pct(0) = pct(1)
    (date(1985, 3, 15), 0.10),     # anniversary: still year 1
    (date(1985, 9, 20), 0.095),    # year 2, m 6: 9% + 1% x 6/12
    (date(1993, 9, 20), 0.015),    # year 10, m 6
    (date(1994, 9, 20), 0.005),    # year 11, m 6: runs one year past the last nonzero row
    (date(1995, 9, 20), 0.0),
    (date(2026, 9, 20), 0.0),
])
def test_full_charge_is_a_graded_percent_of_the_account_value(on, pct):
    policy = _policy(_segment(1), _segment(2, units=50.0, issue=date(1990, 3, 15)))
    rate, total, rates, charges = calc_engine._calculate_surrender_charge(
        policy, _rates(), 1, on, RULE_5, account_value=20_000.0)
    assert rate == pytest.approx(pct) and rates["cov2"] == 0.0
    assert total == pytest.approx(pct * 20_000.0) and charges["cov2"] == 0.0


def test_ungraded_basis_steps_annually():
    assert rule_5_surrender_pct(C1, False, 2, 6) == 0.09
    assert rule_5_surrender_pct(C1, True, 2, 6) == 0.095


def test_negative_account_value_has_no_charge():
    _, total, _, _ = calc_engine._calculate_surrender_charge(
        _policy(), _rates(), 1, date(1985, 9, 20), RULE_5, account_value=-50.0)
    assert total == 0.0


def test_rule_5_policy_takes_no_withdrawal_credit_or_fallback():
    policy = _policy(_segment(units=60.0, original_units=100.0))
    wh.seed_ffl_withdrawal_credit(policy, RULE_5, 75.0, 3, ("5", "0"))
    wh.seed_ffl_withdrawal_credit(policy, RULE_5, None, 3, ())
    assert wh.ffl_withdrawal_surrender_credit(policy, RULE_5) == 0.0
    assert not wh.ffl_current_units_fallback(policy)
    wh.record_ffl_withdrawal_surrender_charge(policy, RULE_5, 40.0)
    assert wh.ffl_withdrawal_surrender_credit(policy, RULE_5) == 0.0
    assert calc_engine.surrender_charge_units(policy.segments[0], RULE_5, policy) == 60.0


def test_rule_6_gate_still_credits_per_unit_plans():
    policy = _policy()
    wh.seed_ffl_withdrawal_credit(policy, RULE_6, 75.0, 1, ("6", "0"))
    assert wh.ffl_withdrawal_surrender_credit(policy, RULE_6) == 75.0
    other = _policy()
    wh.seed_ffl_withdrawal_credit(other, RULE_6, 75.0, 1, ("5", "0"))
    assert wh.ffl_withdrawal_surrender_credit(other, RULE_6) == 0.0


# -- withdrawals in the charge period ------------------------------------------------

def test_withdrawal_in_the_charge_period_is_not_rejected_and_takes_only_the_fee():
    policy = _policy()
    rates = _rates()
    calc_engine._reject_pct_surrender_charge(rates, policy.segments, date(1986, 9, 20), 3, "A withdrawal")
    pct = calc_engine._pct_of_av_surrender_charge_pct(rates, policy.segments[0], date(1986, 9, 20), 3)
    result = wh.compute_withdrawal(
        20_000.0, policy, RULE_5, {1: 0.0}, 5_000.0,
        pct_of_av_surrender_charge=pct * 20_000.0, corridor_rate=1.0, prior_total_md=0.0,
        policy_debt=0.0, cost_basis=0.0, withdrawals_to_date=0.0, withdrawals_ytd=0.0,
        is_anniversary=False)
    assert pct == pytest.approx(0.085)
    assert result.partial_sc == 0.0
    assert result.gross_withdrawal == pytest.approx(5_000.0 + RULE_5.withdrawal_fee)
    assert result.max_net_withdrawal == pytest.approx(20_000.0 - 0.085 * 20_000.0 - RULE_5.withdrawal_fee)
