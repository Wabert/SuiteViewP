"""Premium-acceptance allowance chain (RERUN CalcEngine NC..NZ).

Pure-function tests for ``compute_premium_allowances`` — no rates database or
projection needed.
"""
import pytest

from suiteview.illustration.core.premium_allowance import (
    INF,
    PremiumAllowanceInput,
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
    return compute_premium_allowances(PremiumAllowanceInput(**kwargs))


def _engine_alw(options, policy, **kwargs):
    """Engine-style allowance input: policy/options plus monthly state values."""
    premiums_to_date = kwargs.pop("premiums_to_date")
    withdrawals_before_forceout = kwargs.pop("withdrawals_before_forceout")
    data = dict(
        is_cvat=policy.is_cvat,
        is_gpt=policy.is_gpt,
        tefra_force=options.guideline_cap_enabled,
        tamra_force=(
            options.tamra_cap_enabled
            and policy.has_defined_life_insurance
            and policy.tamra_7pay_level > 0
        ),
        mec_bypass=policy.is_mec,
        prem_less_wd=premiums_to_date - withdrawals_before_forceout,
        loan_repay_from_forceout=0.0,
        seven_pay_level=policy.tamra_7pay_level,
        npt_premium=0.0,
        loan_repay_from_lumpsum=0.0,
        loan_repay_from_scheduled=0.0,
        ln_repay_left_over=0.0,
        levelizing_premium=options.levelizing_premium,
        policy_anniversary=kwargs.get("beginning_of_year", False),
        prior_scheduled_cap_by_guideline=False,
        prior_scheduled_cap_by_tamra=False,
        dollar_for_dollar_in_transition_year=options.dollar_for_dollar_in_transition_year,
        prior_guideline_limit_reached=False,
        prior_transition_year_active=False,
    )
    data.update(kwargs)
    return compute_premium_allowances(PremiumAllowanceInput(**data))


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


def test_transition_year_dollar_for_dollar_suppresses_levelizing():
    # The first policy year the GP guideline binds the level premium (the year the
    # policy tips into GP exception): with the opt-in on, levelizing is suppressed
    # so the scheduled premium bills dollar-for-dollar (up to the annual room)
    # instead of being spread across the year's modal payments.
    base = dict(
        tefra_force=True, guideline_limit=10_000.0, prem_less_wd=9_400.0,
        requested_scheduled=500.0, payment_count_policy_year=12,
        levelizing_premium=True,
    )
    # Levelized (opt-in off): 600 of annual room spread over 12 modes -> 50.
    off = _alw(**base)
    assert off.apply_levelized is True
    assert off.in_transition_year is False
    assert off.applied_scheduled_premium == pytest.approx(50.0)

    # Opt-in on, first capped year (prior year had not reached the limit): the
    # transition-year latch fires, levelizing is off, full 500 bills this month.
    on = _alw(
        **base,
        dollar_for_dollar_in_transition_year=True,
        prior_guideline_limit_reached=False,
    )
    assert on.in_transition_year is True
    assert on.apply_levelized is False
    assert on.applied_scheduled_premium == pytest.approx(500.0)


def test_transition_year_only_the_first_capped_year():
    # A later year in the same exception period (the prior month already reached
    # the guideline limit) is NOT the transition year — levelizing stays on so the
    # settled exception period does not re-oscillate.
    a = _alw(
        tefra_force=True, guideline_limit=10_000.0, prem_less_wd=9_400.0,
        requested_scheduled=500.0, payment_count_policy_year=12,
        levelizing_premium=True,
        dollar_for_dollar_in_transition_year=True,
        prior_guideline_limit_reached=True,
    )
    assert a.in_transition_year is False
    assert a.apply_levelized is True
    assert a.applied_scheduled_premium == pytest.approx(50.0)


def test_transition_year_carries_through_the_year():
    # Mid-year months (not the anniversary) inherit the latch from the carried
    # ``prior_transition_year_active`` flag, so the whole transition year bills
    # dollar-for-dollar, not just its first month.
    a = _alw(
        tefra_force=True, guideline_limit=10_000.0, prem_less_wd=9_400.0,
        requested_scheduled=500.0, payment_count_policy_year=12,
        levelizing_premium=True,
        dollar_for_dollar_in_transition_year=True,
        beginning_of_year=False, policy_anniversary=False,
        prior_scheduled_prem_cap=50.0,
        prior_scheduled_cap_by_guideline=True,
        prior_transition_year_active=True,
    )
    assert a.in_transition_year is True
    assert a.apply_levelized is False
    assert a.applied_scheduled_premium == pytest.approx(500.0)


def test_transition_year_dollar_for_dollar_off_by_default():
    # Without the opt-in, the transition year keeps RERUN levelizing (parity for
    # normal INPUT runs).
    a = _alw(
        tefra_force=True, guideline_limit=10_000.0, prem_less_wd=9_400.0,
        requested_scheduled=500.0, payment_count_policy_year=12,
        levelizing_premium=True,
        prior_guideline_limit_reached=False,
    )
    assert a.in_transition_year is False
    assert a.apply_levelized is True
    assert a.applied_scheduled_premium == pytest.approx(50.0)


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


def test_levelized_cap_is_a_payable_cent_amount():
    # UE000032's second illustrated policy year has $165.98 of guideline room.
    # Twelve equal payments must be $13.83; retaining fractional cents makes the
    # annual total $165.98 even though every displayed monthly payment is $13.83.
    first = _alw(
        tefra_force=True,
        guideline_limit=165.98,
        requested_scheduled=19.21,
        payment_count_policy_year=12,
        levelizing_premium=True,
    )
    assert first.gp_level_allowance == pytest.approx(165.98 / 12)
    assert first.scheduled_prem_cap == 13.83
    assert first.applied_scheduled_premium == 13.83

    carried = _alw(
        tefra_force=True,
        guideline_limit=152.15,
        prem_less_wd=13.83,
        requested_scheduled=19.21,
        payment_count_policy_year=12,
        levelizing_premium=True,
        beginning_of_year=False,
        policy_anniversary=False,
        prior_scheduled_prem_cap=first.scheduled_prem_cap,
        prior_scheduled_cap_by_guideline=True,
    )
    assert carried.scheduled_prem_cap == 13.83
    assert carried.applied_scheduled_premium == 13.83


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

    on = _engine_alw(IllustrationOptions(levelizing_premium=True), policy, **common)
    assert on.apply_levelized is True
    assert on.applied_scheduled_premium == pytest.approx(50.0)   # 600/12, level

    off = _engine_alw(IllustrationOptions(levelizing_premium=False), policy, **common)
    assert off.apply_levelized is False
    assert off.applied_scheduled_premium == pytest.approx(500.0)  # dollar-for-dollar


@pytest.mark.parametrize("payments", [12, 4, 2, 1])
@pytest.mark.parametrize("levelizing,has_loan", [(True, False), (False, False), (True, True)])
def test_maturity_options_levelize_first_guideline_capped_year(payments, levelizing, has_loan):
    from suiteview.illustration.core.solve_level_to_exception import (
        level_to_exception_options,
    )
    from suiteview.illustration.models.input_set import IllustrationOptions
    from suiteview.illustration.models.policy_data import IllustrationPolicyData

    # UE006519 year 12: $204.18 room, formerly $37.12 x 5 + $18.58 then zero.
    options = level_to_exception_options(IllustrationOptions(levelizing_premium=levelizing))
    policy = IllustrationPolicyData(def_of_life_ins="GPT", tamra_7pay_level=0.0)
    prior = None
    paid = 0.0
    amounts = []
    step = 12 // payments
    for month in range(1, 13):
        due = (month - 1) % step == 0
        allowance = _engine_alw(
            options, policy,
            guideline_limit=204.18, premiums_to_date=paid,
            withdrawals_before_forceout=0.0, force_out=0.0, amount_in_7pay=0.0,
            tamra_year=12, tamra_month_of_year=month, policy_month=month,
            tamra_reset=False, requested_scheduled=37.12 * step if due else 0.0,
            requested_lumpsum=0.0, payment_count_policy_year=payments,
            payment_count_tamra_year=payments, has_loan_balance=has_loan,
            beginning_of_year=month == 1,
            prior_scheduled_prem_cap=prior.scheduled_prem_cap if prior else 0.0,
            prior_scheduled_cap_by_guideline=prior.scheduled_cap_by_guideline if prior else False,
            prior_transition_year_active=prior.in_transition_year if prior else False,
        )
        assert allowance.apply_levelized is (levelizing and not has_loan)
        if due:
            amounts.append(allowance.applied_scheduled_premium)
        else:
            assert allowance.applied_scheduled_premium == 0.0
        paid += allowance.applied_scheduled_premium
        prior = allowance

    if levelizing and not has_loan:
        expected = {12: 17.01, 4: 51.04, 2: 102.09, 1: 204.18}[payments]
        assert amounts == pytest.approx([expected] * payments)
        assert 0 <= 204.18 - paid < payments * 0.01 + 1e-9
    else:
        assert paid == pytest.approx(204.18)
        assert amounts[0] == pytest.approx(min(37.12 * step, 204.18))
        if payments == 12:
            assert amounts == pytest.approx([37.12] * 5 + [18.58] + [0.0] * 6)


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


@pytest.mark.parametrize("requested,expected", [(37.12, True), (17.01, True), (17.0, False)])
def test_guideline_limit_latch_uses_payable_cap_not_fractional_allowance(requested, expected):
    from suiteview.illustration.core.calc_engine import _guideline_limit_reached
    from suiteview.illustration.models.plancode_config import PlancodeConfig

    allowance = _alw(
        tefra_force=True, guideline_limit=204.18,
        requested_scheduled=requested, levelizing_premium=True,
    )
    assert allowance.gp_level_allowance == pytest.approx(17.015)
    assert allowance.scheduled_prem_cap == 17.01
    config = PlancodeConfig(maturity_age=95)
    assert _guideline_limit_reached(
        config, allowance, attained_age=21, beginning_of_year=True,
        prior_limit_reached=False,
    ) is expected
    assert _guideline_limit_reached(
        config, allowance, attained_age=21, beginning_of_year=False,
        prior_limit_reached=expected,
    ) is expected
    assert not _guideline_limit_reached(
        config, allowance, attained_age=95, beginning_of_year=True,
        prior_limit_reached=True,
    )


@pytest.mark.parametrize("overrides", [
    {"tefra_force": False},
    {"tamra_force": True, "seven_pay_level": 100.0},
    {"tamra_force": True, "seven_pay_level": 204.15},
])
def test_guideline_limit_latch_requires_guideline_cap_source(overrides):
    from suiteview.illustration.core.calc_engine import _guideline_limit_reached
    from suiteview.illustration.models.plancode_config import PlancodeConfig

    inputs = dict(
        tefra_force=True, guideline_limit=204.18,
        requested_scheduled=37.12, levelizing_premium=True,
    )
    inputs.update(overrides)
    allowance = _alw(**inputs)
    assert not allowance.scheduled_cap_by_guideline
    assert not _guideline_limit_reached(
        PlancodeConfig(maturity_age=95), allowance, attained_age=21,
        beginning_of_year=True, prior_limit_reached=False,
    )
