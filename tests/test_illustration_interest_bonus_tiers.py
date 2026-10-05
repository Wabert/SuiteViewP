"""ANICO1996 interest bonus: duration tiers and AN0230 conditional eligibility.

Evidence: SR113413 business requirements v2.1 (PULU "50 basis point bonus after 10 years
and a 75 basis point bonus after 20 years"), Robert Haessly's note of 8/24/2021, CyberLife
mod AN0230 and LH_NON_TRD_POL.PRO_BNS_RS_CD (DB2 CKPR 2026-10-04). Robert Haessly's ruling
of 10/5/2026: the 0.75% tier applies to 1U135900 and 1U135Q00 only; 1U135H00 gets 0.50%.
"""
from __future__ import annotations

from datetime import date

import pytest

from suiteview.illustration.core.bonus_eligibility import (
    apply_bonus_eligibility,
    earned_bonus_tier,
    projected_test_passes,
    with_recorded_stage,
)
from suiteview.illustration.core.bonus_rates import BonusConfig, load_bonus_config
from suiteview.illustration.core.calc_engine import resolve_bonus_config
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    PolicyChangeEvent,
    PolicyChangeKind,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

PULU_TWO_TIER = ("1U135900", "1U135Q00")
PULU_ONE_TIER = "1U135H00"
UL96 = ("1U135D00", "1U135K00", "1U135P00")
TODAY = date(2026, 10, 4)


def _pulu(policy_year: int, stage: str, **kwargs) -> IllustrationPolicyData:
    issue = date(2026 - policy_year + 1, 1, 1)
    values = dict(
        plancode="1U135900", issue_date=issue, valuation_date=TODAY, illustration_date=TODAY,
        policy_year=policy_year, duration=(policy_year - 1) * 12 + 9,
        prospective_bonus_stage=stage, premiums_paid_to_date=20_000.0,
        accumulated_mtp=15_000.0, mtp=125.0, modal_premium=0.0, face_amount=100_000.0,
        segments=[CoverageSegment(face_amount=100_000.0, original_face_amount=100_000.0)],
    )
    values.update(kwargs)
    return IllustrationPolicyData(**values)


def test_pulu_tiers_replace_not_add():
    bonus = load_bonus_config("1U135900", TODAY)
    assert bonus.duration_tiers() == ((10, 0.005), (20, 0.0075))
    assert bonus.bonus_conditional
    assert [bonus.duration_bonus(y) for y in (10, 11, 20, 21, 40)] == [0.0, 0.005, 0.005, 0.0075, 0.0075]


@pytest.mark.parametrize("plancode", PULU_TWO_TIER)
def test_pulu_two_tier_plans_have_the_conditional_two_tier_bonus_in_every_era(plancode):
    for as_of in (date(2005, 1, 1), date(2020, 6, 1), date(2023, 2, 1), TODAY):
        bonus = load_bonus_config(plancode, as_of)
        assert bonus.duration_tiers() == ((10, 0.005), (20, 0.0075)), (plancode, as_of)
        assert bonus.bonus_conditional


def test_1u135h00_has_only_the_conditional_half_percent_tier_in_every_era():
    for as_of in (date(2005, 1, 1), date(2020, 6, 1), date(2023, 2, 1), TODAY):
        bonus = load_bonus_config(PULU_ONE_TIER, as_of)
        assert bonus.duration_tiers() == ((10, 0.005),), as_of
        assert bonus.bonus_conditional and bonus.bonus_dur_threshold2 == 0
        assert [bonus.duration_bonus(y) for y in (10, 11, 20, 21, 40)] == [0.0, 0.005, 0.005, 0.005, 0.005]


@pytest.mark.parametrize("stage, year, expected", [
    ("6", 25, 1),   # CyberLife code 6 (tier 2 elsewhere): the one tier is earned
    ("5", 25, 1),
    ("5", 15, 1),
    ("0", 25, 0),   # failed at 11: no bonus for good
])
def test_1u135h00_recorded_stage_earns_at_most_the_one_tier(stage, year, expected):
    bonus = load_bonus_config(PULU_ONE_TIER, TODAY)
    policy = _pulu(year, stage, plancode=PULU_ONE_TIER)
    assert earned_bonus_tier(bonus, policy) == expected
    resolved = resolve_bonus_config(policy, None)
    assert resolved.duration_bonus(year) == (0.005 if expected else 0.0)
    assert with_recorded_stage(bonus, stage).duration_bonus(year) == (0.005 if expected else 0.0)


def test_1u135h00_projected_year_11_test_still_applies():
    bonus = load_bonus_config(PULU_ONE_TIER, TODAY)
    policy = _pulu(1, "", plancode=PULU_ONE_TIER, duration=0, premiums_paid_to_date=0.0,
                   accumulated_mtp=0.0, mtp=100.0)
    level = IllustrationInputSet(scheduled_transactions=[ScheduledTransaction(
        kind=TransactionKind.PREMIUM, policy_year=1, amount=1_200.0, mode="A")])
    low = IllustrationInputSet(scheduled_transactions=[ScheduledTransaction(
        kind=TransactionKind.PREMIUM, policy_year=1, amount=1_000.0, mode="A")])
    assert earned_bonus_tier(bonus, policy, level) == 1
    assert earned_bonus_tier(bonus, policy, low) == 0


@pytest.mark.parametrize("plancode", UL96)
def test_ul96_family_history_is_one_unconditional_tier(plancode):
    history = {
        date(2020, 4, 30): 0.009, date(2020, 5, 1): 0.0065, date(2021, 6, 1): 0.005,
        date(2021, 12, 1): 0.0025, date(2022, 11, 1): 0.005, date(2023, 2, 1): 0.009, TODAY: 0.009,
    }
    for as_of, rate in history.items():
        bonus = load_bonus_config(plancode, as_of)
        assert bonus.duration_tiers() == ((10, rate),), (plancode, as_of)
        assert not bonus.bonus_conditional
        assert bonus.bonus_dur_threshold2 == 0


def test_single_tier_config_matches_the_old_rule():
    bonus = BonusConfig(bonus_dur_rate=0.009, bonus_dur_threshold=10)
    assert [bonus.duration_bonus(y) for y in (1, 10, 11, 30)] == [0.0, 0.0, 0.009, 0.009]
    assert BonusConfig().duration_bonus(50) == 0.0
    # Threshold 0: the bonus starts in policy year 1.
    assert BonusConfig(bonus_dur_rate=0.01).duration_bonus(1) == 0.01


def test_max_tier_caps_the_schedule():
    bonus = load_bonus_config("1U135900", TODAY)
    assert BonusConfig.duration_bonus(_with(bonus, 0), 25) == 0.0
    assert BonusConfig.duration_bonus(_with(bonus, 1), 25) == 0.005
    assert BonusConfig.duration_bonus(_with(bonus, 2), 25) == 0.0075


def _with(bonus: BonusConfig, tier: int) -> BonusConfig:
    from dataclasses import replace
    return replace(bonus, bonus_max_tier=tier)


def test_guaranteed_and_ny_cap_carry_the_second_tier():
    bonus = BonusConfig(bonus_dur_rate=0.005, bonus_dur_threshold=10, bonus_dur_rate2=0.0075,
                        bonus_dur_threshold2=20, bonus_dur_rate2_guar=0.001, bonus_conditional=True,
                        bonus_max_tier=1, bonus_dur_cap_to_excess_over_guar=True)
    guaranteed = bonus.guaranteed()
    assert guaranteed.duration_tiers() == ((10, 0.0), (20, 0.001))
    assert guaranteed.bonus_conditional and guaranteed.bonus_max_tier == 1
    capped = bonus.with_excess_cap(0.046, 0.04)
    assert capped.bonus_dur_rate == 0.005 and capped.bonus_dur_rate2 == 0.006


@pytest.mark.parametrize("stage, year, expected", [
    ("6", 25, 2),   # passed both tests
    ("6", 20, 2),   # code set at the 20th anniversary, ahead of year 21
    ("5", 25, 1),   # passed at 11, failed at 21: 0.50% for good
    ("0", 15, 0),   # failed at 11: no bonus for good
    ("0", 25, 0),
])
def test_recorded_stage_is_final_once_its_test_year_has_passed(stage, year, expected):
    policy = _pulu(year, stage, withdrawals_to_date=0.0)
    assert earned_bonus_tier(load_bonus_config("1U135900", TODAY), policy) == expected


def test_stage_five_before_year_21_projects_the_second_test():
    bonus = load_bonus_config("1U135900", TODAY)
    passing = _pulu(18, "5")
    assert earned_bonus_tier(bonus, passing) == 2
    failing = _pulu(18, "5", withdrawals_to_date=500.0)
    assert earned_bonus_tier(bonus, failing) == 1


def test_projected_test_premium_withdrawal_and_face_legs():
    short = _pulu(18, "5", premiums_paid_to_date=14_000.0, accumulated_mtp=15_000.0)
    assert not projected_test_passes(short, None, 21)
    # Scenario premiums before the 21st anniversary make up the shortfall.
    paying = IllustrationInputSet(scheduled_transactions=[ScheduledTransaction(
        kind=TransactionKind.PREMIUM, policy_year=18, amount=1_200.0, mode="A")])
    assert projected_test_passes(short, paying, 21)
    # A month without a scenario premium bills the modal premium, as the engine does.
    modal = _pulu(18, "5", premiums_paid_to_date=14_000.0, modal_premium=100.0)
    assert projected_test_passes(modal, None, 21)

    policy = _pulu(18, "5")
    # Issued 2009-01-01: the 21st anniversary (the test) is 2029-01-01.
    withdrawal = IllustrationInputSet(dated_transactions=[DatedTransaction(
        kind=TransactionKind.WITHDRAWAL, effective_date=date(2028, 6, 1), amount=1_000.0)])
    assert not projected_test_passes(policy, withdrawal, 21)
    after_test = IllustrationInputSet(dated_transactions=[DatedTransaction(
        kind=TransactionKind.WITHDRAWAL, effective_date=date(2029, 6, 1), amount=1_000.0)])
    assert projected_test_passes(policy, after_test, 21)

    decrease = IllustrationInputSet(policy_changes=[PolicyChangeEvent(
        kind=PolicyChangeKind.FACE_AMOUNT, effective_date=date(2028, 1, 1), value=80_000.0)])
    assert not projected_test_passes(policy, decrease, 21)
    increase = IllustrationInputSet(policy_changes=[PolicyChangeEvent(
        kind=PolicyChangeKind.FACE_AMOUNT, effective_date=date(2028, 1, 1), value=120_000.0)])
    assert projected_test_passes(policy, increase, 21)

    decreased = _pulu(18, "5", segments=[
        CoverageSegment(face_amount=90_000.0, original_face_amount=100_000.0)])
    assert not projected_test_passes(decreased, None, 21)


def test_projected_first_test_accumulates_map_over_the_first_120_months():
    policy = _pulu(1, "", duration=0, premiums_paid_to_date=0.0, accumulated_mtp=0.0, mtp=100.0)
    level = IllustrationInputSet(scheduled_transactions=[ScheduledTransaction(
        kind=TransactionKind.PREMIUM, policy_year=1, amount=1_200.0, mode="A")])
    assert projected_test_passes(policy, level, 11)
    low = IllustrationInputSet(scheduled_transactions=[ScheduledTransaction(
        kind=TransactionKind.PREMIUM, policy_year=1, amount=1_000.0, mode="A")])
    assert not projected_test_passes(policy, low, 11)
    assert earned_bonus_tier(load_bonus_config("1U135900", TODAY), policy, low) == 0


def test_blank_stage_after_the_test_year_uses_in_force_values():
    bonus = load_bonus_config("1U135900", TODAY)
    assert earned_bonus_tier(bonus, _pulu(25, "")) == 2
    assert earned_bonus_tier(bonus, _pulu(25, "", withdrawals_to_date=10.0)) == 0


def test_resolve_bonus_config_applies_eligibility_only_to_conditional_plans():
    stuck = resolve_bonus_config(_pulu(25, "5"), None)
    assert stuck.bonus_max_tier == 1 and stuck.duration_bonus(25) == 0.005
    ul96 = resolve_bonus_config(_pulu(25, "0", plancode="1U135D00"), None)
    assert ul96.bonus_max_tier is None and ul96.duration_bonus(25) == 0.009
    override = BonusConfig()
    assert resolve_bonus_config(_pulu(25, "0"), override) is override


def test_recorded_stage_cap_for_the_current_year_display():
    bonus = load_bonus_config("1U135Q00", TODAY)
    assert with_recorded_stage(bonus, "0").duration_bonus(26) == 0.0
    assert with_recorded_stage(bonus, "5").duration_bonus(26) == 0.005
    assert with_recorded_stage(bonus, "6").duration_bonus(26) == 0.0075
    assert with_recorded_stage(bonus, "").bonus_max_tier is None
    ul96 = load_bonus_config("1U135D00", TODAY)
    assert with_recorded_stage(ul96, "0") is ul96
    assert apply_bonus_eligibility(ul96, _pulu(25, "0", plancode="1U135D00")) is ul96
