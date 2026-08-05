"""Premium-acceptance allowance chain (RERUN CalcEngine NC..NZ).

Pure-function tests for ``compute_premium_allowances`` — no rates database or
projection needed.
"""
import pytest

from suiteview.illustration.core.premium_allowance import (
    INF,
    compute_premium_allowances,
)


def _alw(**overrides):
    """Compute allowances with neutral (no-cap) defaults, overriding as needed."""
    kwargs = dict(
        is_cvat=False,
        is_gpt=True,
        tefra_force=False,
        tamra_force=False,
        mec_bypass=False,
        guideline_limit=0.0,
        prem_less_wd=0.0,
        force_out=0.0,
        loan_repay_from_forceout=0.0,
        seven_pay_level=0.0,
        tamra_year=1,
        tamra_month_of_year=1,
        policy_month=1,
        amount_in_7pay=0.0,
        npt_premium=0.0,
        tamra_reset=False,
        requested_scheduled=0.0,
        requested_lumpsum=0.0,
        payment_count_policy_year=12,
        payment_count_tamra_year=12,
        loan_repay_from_lumpsum=0.0,
        loan_repay_from_scheduled=0.0,
        ln_repay_left_over=0.0,
        has_loan_balance=False,
        levelizing_premium=False,
        beginning_of_year=True,
        policy_anniversary=True,
        prior_scheduled_prem_cap=0.0,
    )
    kwargs.update(overrides)
    return compute_premium_allowances(**kwargs)


def test_no_caps_accepts_full_requested_premium():
    a = _alw(requested_scheduled=500.0, requested_lumpsum=250.0)
    assert a.annual_cap_2 == INF
    assert a.applied_scheduled_premium == 500.0
    assert a.applied_lumpsum == 250.0
    assert a.applied_total_premium == 750.0


def test_guideline_cap_dollar_for_dollar():
    # GPT + TEFRA force, 300 of guideline room, 500 requested -> capped to 300.
    a = _alw(
        tefra_force=True, guideline_limit=10_000.0, prem_less_wd=9_700.0,
        requested_scheduled=500.0,
    )
    assert a.gp_allowance_0 == 300.0
    assert a.annual_cap_2 == 300.0
    assert a.applied_scheduled_premium == 300.0
    assert a.applied_total_premium == 300.0
    assert a.capped_by_guideline
    assert not a.capped_by_tamra


def test_forceout_adds_guideline_room_back():
    # Room is otherwise exhausted; the force-out frees that much room (NC).
    a = _alw(
        tefra_force=True, guideline_limit=10_000.0, prem_less_wd=10_000.0,
        force_out=300.0, requested_scheduled=500.0,
    )
    assert a.gp_allowance_0 == 300.0
    assert a.applied_total_premium == 300.0


def test_lumpsum_consumes_room_before_scheduled():
    # 300 of room; a 250 lumpsum is applied first, leaving 50 for the scheduled.
    a = _alw(
        tefra_force=True, guideline_limit=10_000.0, prem_less_wd=9_700.0,
        requested_scheduled=200.0, requested_lumpsum=250.0,
    )
    assert a.applied_lumpsum == 250.0
    assert a.gp_allowance_2 == 50.0
    assert a.applied_scheduled_premium == 50.0
    assert a.applied_total_premium == 300.0


def test_tamra_seven_pay_cap_binds():
    # 7-pay level 1000, year 1, 600 already paid -> 400 of TAMRA room.
    a = _alw(
        tamra_force=True, seven_pay_level=1_000.0, tamra_year=1,
        amount_in_7pay=600.0, requested_scheduled=500.0,
    )
    assert a.tamra_allowance_0 == 400.0
    assert a.annual_cap_2 == 400.0
    assert a.applied_scheduled_premium == 400.0
    assert a.capped_by_tamra
    assert not a.capped_by_guideline


def test_levelizing_spreads_cap_over_year_vs_dollar_for_dollar():
    base = dict(
        tefra_force=True, guideline_limit=10_000.0, prem_less_wd=9_400.0,
        requested_scheduled=500.0, payment_count_policy_year=12,
    )
    # Dollar-for-dollar: the full 500 bills this month (room is 600).
    off = _alw(**base, levelizing_premium=False)
    assert off.apply_levelized is False
    assert off.applied_scheduled_premium == 500.0

    # Levelized: 600 of annual room spread over 12 modes -> 50 per payment.
    on = _alw(**base, levelizing_premium=True)
    assert on.apply_levelized is True
    assert on.gp_level_allowance == pytest.approx(50.0)
    assert on.scheduled_prem_cap == pytest.approx(50.0)
    assert on.levelized_max_premium == pytest.approx(50.0)
    assert on.applied_scheduled_premium == pytest.approx(50.0)


def test_guideline_levelizing_remains_disabled_by_a_loan():
    a = _alw(
        tefra_force=True, guideline_limit=10_000.0, prem_less_wd=9_400.0,
        requested_scheduled=500.0, levelizing_premium=True, has_loan_balance=True,
    )
    assert a.apply_levelized is False
    assert a.applied_scheduled_premium == 500.0


def test_loan_repay_month_applies_only_the_remainder_not_levelized_premium():
    # The month a loan is repaid: a loan is present (the PRE-repay balance), so
    # levelizing stays off and only the post-repay remainder (NY = scheduled - MI)
    # loads as premium — not the full levelized premium (NW). Regression for
    # S0503261 yr54: a 173.40 repayment out of a 174.12 scheduled premium must
    # leave 0.72 of premium, not re-apply the whole 174.12. The engine must pass
    # the pre-repay loan as has_loan_balance for this to hold.
    a = _alw(
        requested_scheduled=174.12,
        loan_repay_from_scheduled=173.40,   # MI
        has_loan_balance=True,              # pre-repay loan present
        levelizing_premium=True,
    )
    assert a.apply_levelized is False
    assert a.scheduled_less_loan_repay == pytest.approx(0.72)
    assert a.applied_scheduled_premium == pytest.approx(0.72)


def test_levelized_cap_locks_and_carries_forward_after_year_start():
    # A non-beginning-of-year month carries the prior scheduled-prem cap (NV11);
    # ample annual room so only the carried level cap binds the payment.
    a = _alw(
        tefra_force=True, guideline_limit=10_000.0, prem_less_wd=0.0,
        levelizing_premium=True, requested_scheduled=500.0,
        beginning_of_year=False, policy_anniversary=False,
        prior_scheduled_prem_cap=50.0,
    )
    assert a.scheduled_prem_cap == 50.0
    assert a.applied_scheduled_premium == pytest.approx(50.0)


def test_levelized_cap_carries_its_tamra_source_forward():
    a = _alw(
        tamra_force=True,
        seven_pay_level=1_200.0,
        tamra_year=2,
        tamra_month_of_year=2,
        requested_scheduled=500.0,
        levelizing_premium=True,
        beginning_of_year=False,
        policy_anniversary=False,
        prior_scheduled_prem_cap=100.0,
        prior_scheduled_cap_by_tamra=True,
    )

    assert a.applied_scheduled_premium == 100.0
    assert a.capped_by_tamra
    assert not a.capped_by_guideline


def test_boy_and_eoy_level_allowances_take_the_smaller():
    # TAMRA anniversary (month 4) differs from the policy month (1); a new 7-pay
    # premium becomes available later in the year. BOY governs the early part of
    # the year, EOY the later part; the cap takes the smaller so a level premium
    # breaches neither.
    a = _alw(
        tamra_force=True, seven_pay_level=1_200.0, tamra_year=2,
        amount_in_7pay=1_500.0,                # TAMRA room = 1200*2 - 1500 = 900
        tamra_month_of_year=4, policy_month=1, tamra_reset=False,
        payment_count_tamra_year=9, payment_count_policy_year=12,
        requested_scheduled=500.0, levelizing_premium=True,
    )
    assert a.tamra_allowance_2 == 900.0
    assert a.tamra_level_allowance_boy == pytest.approx(900.0 / 9)   # 100
    assert a.tamra_level_allowance_eoy == pytest.approx((900.0 + 1_200.0) / 12)  # 175
    assert a.scheduled_prem_cap == pytest.approx(100.0)             # the smaller


def test_eoy_allowance_uses_remaining_policy_year_payments():
    a = _alw(
        tamra_force=True,
        seven_pay_level=1_000.0,
        tamra_year=2,
        tamra_month_of_year=10,
        policy_month=3,
        amount_in_7pay=1_000.0,
        payment_count_policy_year=10,
        payment_count_tamra_year=3,
        requested_scheduled=1_000.0,
        levelizing_premium=True,
        beginning_of_year=False,
        prior_scheduled_prem_cap=0.0,
    )

    assert a.tamra_level_allowance_boy == pytest.approx(1_000.0 / 3)
    assert a.tamra_level_allowance_eoy == pytest.approx(2_000.0 / 10)
    assert a.scheduled_prem_cap == pytest.approx(200.0)


def test_off_anniversary_new_period_uses_level_seven_pay_premium():
    a = _alw(
        tefra_force=True,
        tamra_force=True,
        guideline_limit=89_703.17,
        seven_pay_level=12_408.36,
        tamra_year=1,
        tamra_month_of_year=1,
        policy_month=8,
        tamra_reset=True,
        payment_count_policy_year=5,
        payment_count_tamra_year=12,
        requested_scheduled=1_200.0,
        levelizing_premium=True,
        beginning_of_year=False,
        policy_anniversary=False,
        prior_scheduled_prem_cap=1_200.0,
    )

    assert a.tamra_level_allowance_boy == pytest.approx(12_408.36 / 12)
    assert a.gp_level_allowance == pytest.approx(89_703.17 / 5)
    assert a.scheduled_prem_cap == pytest.approx(12_408.36 / 12)
    assert a.applied_scheduled_premium == pytest.approx(1_034.03)


def test_policy_anniversary_recalculates_all_three_rerun_level_allowances():
    a = _alw(
        tefra_force=True,
        tamra_force=True,
        guideline_limit=84_296.0,
        seven_pay_level=12_408.36,
        tamra_year=1,
        tamra_month_of_year=6,
        policy_month=1,
        amount_in_7pay=5_170.15,
        payment_count_policy_year=12,
        payment_count_tamra_year=7,
        requested_scheduled=1_200.0,
        levelizing_premium=True,
        beginning_of_year=True,
        policy_anniversary=True,
        prior_scheduled_prem_cap=900.0,
        prior_scheduled_cap_by_tamra=True,
    )

    assert a.tamra_allowance_2 == pytest.approx(7_238.21)
    assert a.tamra_level_allowance_boy == pytest.approx(7_238.21 / 7)
    assert a.tamra_level_allowance_eoy == pytest.approx(
        (7_238.21 + 12_408.36) / 12
    )
    assert a.gp_level_allowance == pytest.approx(84_296.0 / 12)
    assert a.scheduled_prem_cap == pytest.approx(1_034.03)
    assert a.applied_scheduled_premium == pytest.approx(1_034.03)


def test_later_tamra_anniversary_keeps_policy_year_level():
    a = _alw(
        tefra_force=True,
        tamra_force=True,
        guideline_limit=100_000.0,
        seven_pay_level=12_408.36,
        tamra_year=2,
        tamra_month_of_year=1,
        policy_month=8,
        amount_in_7pay=12_408.36,
        payment_count_policy_year=5,
        payment_count_tamra_year=12,
        requested_scheduled=1_200.0,
        levelizing_premium=True,
        beginning_of_year=False,
        policy_anniversary=False,
        prior_scheduled_prem_cap=1_034.03,
        prior_scheduled_cap_by_tamra=True,
    )

    assert a.scheduled_prem_cap == pytest.approx(1_034.03)
    assert a.applied_scheduled_premium == pytest.approx(1_034.03)


def test_new_tamra_period_uses_only_remaining_policy_year_guideline_room():
    a = _alw(
        tefra_force=True,
        tamra_force=True,
        guideline_limit=5_000.0,
        seven_pay_level=12_408.36,
        tamra_year=1,
        tamra_month_of_year=1,
        policy_month=8,
        tamra_reset=True,
        payment_count_policy_year=5,
        payment_count_tamra_year=12,
        requested_scheduled=1_200.0,
        levelizing_premium=True,
        beginning_of_year=False,
        policy_anniversary=False,
        prior_scheduled_prem_cap=1_200.0,
    )

    assert a.tamra_level_allowance_boy == pytest.approx(12_408.36 / 12)
    assert a.gp_level_allowance == pytest.approx(5_000.0 / 5)
    assert a.scheduled_prem_cap == pytest.approx(1_000.0)
    assert a.capped_by_guideline
    assert not a.capped_by_tamra


def test_off_anniversary_annual_mode_uses_tamra_when_no_payment_remains_this_year():
    a = _alw(
        tefra_force=True,
        tamra_force=True,
        guideline_limit=10_000.0,
        seven_pay_level=40_000.0,
        tamra_year=1,
        tamra_month_of_year=1,
        policy_month=8,
        tamra_reset=True,
        payment_count_policy_year=0,
        payment_count_tamra_year=1,
        requested_scheduled=40_000.0,
        levelizing_premium=True,
        beginning_of_year=False,
        policy_anniversary=False,
        prior_scheduled_prem_cap=40_000.0,
    )

    assert a.gp_level_allowance == INF
    assert a.scheduled_prem_cap == pytest.approx(40_000.0)


def test_zero_tamra_cap_recalculates_to_zero_at_policy_anniversary():
    a = _alw(
        tamra_force=True,
        seven_pay_level=1_200.0,
        tamra_year=1,
        tamra_month_of_year=6,
        policy_month=1,
        amount_in_7pay=1_200.0,
        payment_count_policy_year=12,
        payment_count_tamra_year=12,
        requested_scheduled=500.0,
        levelizing_premium=True,
        beginning_of_year=True,
        prior_scheduled_prem_cap=0.0,
        prior_scheduled_cap_by_tamra=True,
    )

    assert a.scheduled_prem_cap == 0.0
    assert a.applied_scheduled_premium == 0.0


def test_tamra_cap_releases_when_seven_pay_period_ends():
    a = _alw(
        tamra_force=True,
        seven_pay_level=1_200.0,
        tamra_year=8,
        tamra_month_of_year=1,
        policy_month=8,
        payment_count_policy_year=5,
        payment_count_tamra_year=12,
        requested_scheduled=500.0,
        levelizing_premium=True,
        beginning_of_year=False,
        policy_anniversary=False,
        prior_scheduled_prem_cap=100.0,
        prior_scheduled_cap_by_tamra=True,
    )

    assert a.scheduled_prem_cap == INF
    assert a.applied_scheduled_premium == 500.0
    assert not a.scheduled_cap_by_tamra
    assert not a.capped_by_tamra


def test_inforce_mec_bypasses_tamra_cap():
    a = _alw(
        tamra_force=True, mec_bypass=True, seven_pay_level=1_000.0, tamra_year=1,
        amount_in_7pay=900.0, requested_scheduled=500.0,
    )
    # MEC -> TAMRA limit no longer applies, full premium accepted.
    assert a.annual_cap_2 == INF
    assert a.applied_scheduled_premium == 500.0


def test_premium_state_fields_populate_monthly_state():
    # The engine's MonthlyState mapping must match the dataclass field names.
    from suiteview.illustration.core import calc_engine
    from suiteview.illustration.models.calc_state import MonthlyState

    a = _alw(
        tefra_force=True, guideline_limit=10_000.0, prem_less_wd=9_700.0,
        requested_scheduled=500.0,
    )
    state = MonthlyState(**calc_engine._premium_state_fields(a, 500.0))
    assert state.premium_cap == 300.0
    assert state.premium_capped is True
    assert state.applied_scheduled_premium == 300.0
    assert state.prem_less_wd == 9_700.0
    assert state.premium_allowance_detail["GP_Allowance0"] == 300.0


def test_premium_allowances_respects_levelizing_option():
    # The Run-Controls checkbox flows through IllustrationOptions.levelizing_premium
    # into the engine helper and actually changes the APPLIED scheduled premium.
    from suiteview.illustration.core import calc_engine
    from suiteview.illustration.models.input_set import IllustrationOptions
    from suiteview.illustration.models.policy_data import IllustrationPolicyData

    policy = IllustrationPolicyData(def_of_life_ins="GPT", tamra_7pay_level=0.0)
    common = dict(
        guideline_limit=10_000.0, premiums_to_date=9_400.0,   # 600 of annual room
        withdrawals_before_forceout=0.0, force_out=0.0, amount_in_7pay=0.0,
        tamra_year=1, tamra_month_of_year=1, policy_month=1, tamra_reset=False,
        requested_scheduled=500.0, requested_lumpsum=0.0,
        payment_count_policy_year=12, payment_count_tamra_year=12,
        has_loan_balance=False, beginning_of_year=True, prior_scheduled_prem_cap=0.0,
    )

    on = calc_engine._premium_allowances(
        IllustrationOptions(levelizing_premium=True), policy, **common)
    assert on.apply_levelized is True
    assert on.applied_scheduled_premium == pytest.approx(50.0)   # 600/12, level

    off = calc_engine._premium_allowances(
        IllustrationOptions(levelizing_premium=False), policy, **common)
    assert off.apply_levelized is False
    assert off.applied_scheduled_premium == pytest.approx(500.0)  # dollar-for-dollar


def test_to_detail_exposes_every_named_column():
    a = _alw(requested_scheduled=100.0)
    detail = a.to_detail()
    for key in (
        "GP_Allowance0", "NPT Allowance0", "TAMRA_Allowance0", "Annual Cap0",
        "Applied1035", "GP_Allowance2", "Annual Cap2",
        "TAMRA_Level_Allowance_BOY", "TAMRA_Level_Allowance_EOY",
        "Scheduled Prem Cap", "Levelized Max Premium", "Apply Levelized Premium",
        "AppliedScheduledPremium",
    ):
        assert key in detail
    assert detail["Apply Levelized Premium"] is False
