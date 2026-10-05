"""Premiums and charges cease before maturity (plancode table ``PremiumAndChargeCeaseAge``).

Robert Haessly, 10/3/2026: on 1U1446/47/48, 1U1352/53/54/56/5I/5L/5E, 1U143800, 1U144500
and B11SB600 premiums cease at attained age 100 and the policy does not mature: it stays in
force to the ``PLAN_DEF`` maturity (120/121), the account value earning interest. Robert
Haessly, 10/5/2026 (LTGUL 1U143800/1U144500): no charges at all after 100 - not even the
$5.00 MFEE that UL_Rates loads to 120 and CyberLife still deducts (a CyberLife defect).
The COI past 100 is never looked up (an ISWL COI past its last loaded age is a raising
``MissingRate``).
"""
from __future__ import annotations

from datetime import date

import pytest

import suiteview.illustration.models.plancode_config as pc
from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.iswl_rates import ISWLRateBasis
from suiteview.illustration.core.rate_loader import IllustrationRates, MissingRate
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.core.ul_rates import ULRates
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import (
    CHARGE_CEASE_KEY,
    MATURITY_OVERRIDE_KEY,
    PREMIUM_CEASE_OVERRIDE_KEY,
    PlancodeConfig,
    load_plancode,
)
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
)
from tests.plan_facts_fixtures import plan_facts

PLAN = "ZZCEASE0"
GROUP_1 = ("1U144600", "1U144700", "1U144800", "1U135200", "1U135300", "1U135400", "1U135600",
           "1U135I00", "1U135L00", "1U135E00", "1U143800", "1U144500", "B11SB600")
# Robert keeps these maturity caps (premiums cease at the same age).
GROUP_2 = {"1U14L300": 100, "1A130500": 90, "1A130600": 85}

ISSUE = date(1975, 6, 15)
ISSUE_AGE = 47
VALUATION = date(2026, 6, 15)       # attained 98, policy year 52 month 1
FACE = 500_000.0


# ── load_plancode ──────────────────────────────────────────────────────────


def _load(monkeypatch, *, facts=None, **row):
    monkeypatch.setattr(pc, "_CONFIG_CACHE", {})
    monkeypatch.setattr(pc, "_TABLE_CACHE", {PLAN: {"Plancode": PLAN, "SA_Basis": "CurrentSA", **row}})
    monkeypatch.setattr(pc, "load_plan_facts", lambda _plancode: facts or plan_facts(PLAN))
    return load_plancode(PLAN)


def test_charge_cease_age_keeps_plan_def_maturity(monkeypatch):
    config = _load(monkeypatch, **{CHARGE_CEASE_KEY: 100})
    assert (config.maturity_age, config.premium_cease_age, config.charge_cease_age) == (121, 100, 100)
    assert config.illustration_overrides == ()
    assert not config.charges_ceased(99) and config.charges_ceased(100) and config.charges_ceased(120)


def test_plan_without_the_rule_never_ceases_charges(monkeypatch):
    config = _load(monkeypatch)
    assert config.charge_cease_age is None and not config.charges_ceased(120)


@pytest.mark.parametrize("value", [121, 122, 0, "100", True, 100.0])
def test_charge_cease_age_must_be_a_whole_age_before_maturity(monkeypatch, value):
    with pytest.raises(ValueError, match=CHARGE_CEASE_KEY):
        _load(monkeypatch, **{CHARGE_CEASE_KEY: value})


@pytest.mark.parametrize("override", [MATURITY_OVERRIDE_KEY, PREMIUM_CEASE_OVERRIDE_KEY])
def test_charge_cease_age_does_not_combine_with_an_age_override(monkeypatch, override):
    with pytest.raises(ValueError, match="cannot be combined"):
        _load(monkeypatch, **{CHARGE_CEASE_KEY: 100, override: 100})


def test_override_with_premiums_ceasing_before_maturity_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match=CHARGE_CEASE_KEY):
        _load(monkeypatch, **{MATURITY_OVERRIDE_KEY: 110, PREMIUM_CEASE_OVERRIDE_KEY: 100})


def test_shipped_table_rows():
    rows = pc._load_plancode_table()
    for plancode in GROUP_1:
        row = rows[plancode]
        assert row[CHARGE_CEASE_KEY] == 100, plancode
        assert MATURITY_OVERRIDE_KEY not in row and PREMIUM_CEASE_OVERRIDE_KEY not in row, plancode
    # CyberLife's IMUL CCV benefit (type A) ceases at 100 (CKDRSB DSBCEADU).
    assert rows["1U143800"]["ShadowCeaseAge"] == rows["1U144500"]["ShadowCeaseAge"] == 100
    # The shadow account never outlives the charges (shadow_calc zeroes its charges after).
    assert all(rows[p]["ShadowCeaseAge"] <= rows[p][CHARGE_CEASE_KEY] for p in GROUP_1)
    for plancode, age in GROUP_2.items():
        row = rows[plancode]
        assert (row[MATURITY_OVERRIDE_KEY], row[PREMIUM_CEASE_OVERRIDE_KEY]) == (age, age), plancode
        assert CHARGE_CEASE_KEY not in row
    assert {p for p, row in rows.items() if CHARGE_CEASE_KEY in row} == set(GROUP_1)


# ── projections to 121 ─────────────────────────────────────────────────────


def _segment() -> CoverageSegment:
    return CoverageSegment(coverage_phase=1, issue_date=ISSUE, issue_age=ISSUE_AGE,
                           face_amount=FACE, original_face_amount=FACE, units=FACE / 1000)


def _policy(**changes) -> IllustrationPolicyData:
    values = dict(
        plancode=PLAN, issue_date=ISSUE, valuation_date=VALUATION, issue_age=ISSUE_AGE,
        attained_age=98, maturity_age=121, policy_year=52, policy_month=1, duration=612,
        face_amount=FACE, units=FACE / 1000, db_option="A", account_value=200_000.0,
        modal_premium=1_000.0, billing_frequency=1, current_interest_rate=0.04,
        guaranteed_interest_rate=0.04, segments=[_segment()],
        # Guideline room so the modal premium is accepted before 100.
        glp=20_000.0, gsp=1_000_000.0, accumulated_glp=1_000_000.0,
    )
    values.update(changes)
    return IllustrationPolicyData(**values)


def _coi_to_99(rate: float) -> list:
    """1-indexed by policy year: loaded through attained 99, a raising MissingRate from 100."""
    loaded = 100 - ISSUE_AGE
    return [None] + [rate] * loaded + [MissingRate(f"no COI at attained {100 + y}") for y in range(30)]


def _project(monkeypatch, config, policy, rates):
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _p: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())
    # Targets and bands do not enter these deductions; keep the projection off UL_Rates.
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *_a, **_k: TargetPremiumResult())
    monkeypatch.setattr(ULRates, "get_band", lambda *_a, **_k: None)
    return IllustrationEngine().project(policy, months=None, rates_override=rates,
                                        bonus_override=BonusConfig())


def _assert_paid_up_from_100(states):
    # The projection runs to the PLAN_DEF maturity (its last row is in the final policy year).
    assert states[-1].attained_age >= 120
    assert not any(s.lapsed for s in states)
    before = [s for s in states[1:] if s.attained_age < 100]
    after = [s for s in states[1:] if s.attained_age >= 100]
    assert before and all(s.total_deduction > 0 for s in before)
    assert len(after) >= (120 - 100) * 12
    previous = {id(s): p for p, s in zip(states, states[1:])}
    for s in after:
        assert (s.gross_premium, s.total_coi_charge, s.epu_charge) == (0.0, 0.0, 0.0)
        assert (s.av_charge, s.benefit_charges, s.rider_charges) == (0.0, 0.0, 0.0)
        # No monthly fee either, whatever the MFEE schedule loads (Robert Haessly, 10/5/2026).
        assert s.mfee_charge == s.total_deduction == 0.0
        assert s.interest_credited > 0
        # The account value grows by its interest alone; the death benefit stays in force.
        assert s.av_end_of_month == pytest.approx(
            previous[id(s)].av_end_of_month + s.interest_credited)
        assert s.total_db >= FACE
    return before, after


def _mfee_from_100(fee_at_100: float) -> list:
    """1-indexed MFEE schedule: $5 through attained 99, ``fee_at_100`` from 100 to maturity."""
    return [None] + [5.0] * (100 - ISSUE_AGE) + [fee_at_100] * (121 - 100)


# LTGUL 1U143800/1U144500 keep a $5 MFEE to 120 in UL_Rates (CyberLife still deducts MV_EXP
# 5.00 after 100, a defect per Robert Haessly 10/5/2026); 1U1446/47/48 and 1U135* load $0
# from 100. Either way nothing is deducted from 100.
@pytest.mark.parametrize("fee_at_100", [5.0, 0.0])
def test_ul_plan_stops_premiums_and_charges_at_100_and_runs_to_121(monkeypatch, fee_at_100):
    config = PlancodeConfig(plancode=PLAN, dbd=0.04, gint=0.04, maturity_age=121,
                            premium_cease_age=100, charge_cease_age=100)
    coi = _coi_to_99(6.0)
    rates = IllustrationRates(coi=coi, segment_coi={1: coi}, mfee=_mfee_from_100(fee_at_100),
                              epu=[None] + [0.02] * 80,
                              benefit_coi={"1": [None] + [0.5] * 80})
    policy = _policy(benefits=[BenefitInfo(benefit_type="1", benefit_subtype="", units=10.0,
                                           coi_rate=0.5, is_active=True)])
    states = _project(monkeypatch, config, policy, rates)
    before, _after = _assert_paid_up_from_100(states)
    assert all(s.gross_premium == 1_000.0 for s in before)
    assert all(s.mfee_charge == 5.0 and s.epu_charge > 0 and s.benefit_charges > 0
               for s in before if s.attained_age < 99)


def test_iswl_single_premium_plan_stops_the_coi_at_100_and_runs_to_121(monkeypatch):
    config = PlancodeConfig(plancode=PLAN, product_family="ISWL", dbd=0.04, gint=0.04,
                            maturity_age=121, premium_cease_age=100, charge_cease_age=100,
                            corridor_by_age={0: 2.5, 100: 1.0})
    coi = _coi_to_99(12.0)
    iswl = ISWLRateBasis(  # as iswl_rates._single_premium_basis builds it
        plan_company="26", plan_note="", units=FACE / 1000, base_premium_per_unit=0.0,
        load_pct=[None, 0.0], net_premium_per_unit=[None, 0.0], billing_frequency=12, mode="",
        bill_form_family="", prem_factor=0.0, fee_factor=0.0, policy_fee_annual=0.0,
        billed_premium=0.0, anchor_date=VALUATION, issue_date=ISSUE, single_premium=True)
    rates = IllustrationRates(coi=coi, segment_coi={1: coi}, iswl=iswl)
    policy = _policy(plancode=PLAN, product_type="ISWL", premium_pay_status_code="42")
    states = _project(monkeypatch, config, policy, rates)
    before, _after = _assert_paid_up_from_100(states)
    assert all(s.gross_premium == 0.0 and s.total_coi_charge > 0 for s in before)


def test_other_plans_keep_charging_after_100(monkeypatch):
    config = PlancodeConfig(plancode=PLAN, dbd=0.04, gint=0.04, maturity_age=121, premium_cease_age=121)
    coi = [None] + [6.0] * 80
    rates = IllustrationRates(coi=coi, segment_coi={1: coi}, mfee=[None] + [5.0] * 80)
    states = _project(monkeypatch, config, _policy(), rates)
    after = [s for s in states[1:] if s.attained_age >= 100]
    assert after and all(s.total_coi_charge > 0 and s.mfee_charge == 5.0 for s in after)


@pytest.mark.parametrize("cease_age, excess_becomes_premium", [(98, False), (None, True)])
def test_loan_over_repayment_is_not_premium_once_premiums_cease(monkeypatch, cease_age,
                                                                excess_becomes_premium):
    """With "apply excess as premium" on, an over-repayment after the cease age repays the
    loan and the excess is discarded; before it (control) the excess is applied as premium."""
    config = PlancodeConfig(plancode=PLAN, dbd=0.04, gint=0.04, maturity_age=121,
                            premium_cease_age=cease_age or 121, charge_cease_age=cease_age)
    coi = [None] + [6.0] * 80
    rates = IllustrationRates(coi=coi, segment_coi={1: coi})
    policy = _policy(modal_premium=0.0, regular_loan_principal=1_000.0)
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(TransactionKind.LOAN_REPAYMENT, date(2026, 7, 15), 5_000.0)])
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _p: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *_a, **_k: TargetPremiumResult())
    monkeypatch.setattr(ULRates, "get_band", lambda *_a, **_k: None)
    states = IllustrationEngine().project(
        policy, months=3, future_inputs=inputs, rates_override=rates, bonus_override=BonusConfig(),
        options=IllustrationOptions(apply_excess_repayment_as_premium=True))
    repaid = [s for s in states[1:] if s.applied_loan_repayment > 0]
    assert len(repaid) == 1
    month = repaid[0]
    assert month.applied_loan_repayment == pytest.approx(1_000.0, abs=1.0)
    assert states[-1].rg_loan_princ == pytest.approx(0.0)
    assert (month.gross_premium > 3_000.0) is excess_becomes_premium
    if not excess_becomes_premium:
        assert all(s.gross_premium == 0.0 for s in states[1:])
