"""Monthly Deduction premium type — engine integration.

The Monthly Deduction premium reuses the GP exception premium machinery,
retargeted: instead of grossing the after-charge account value back up to zero,
it grosses it back up by the full monthly deduction so the ending account value
equals where it stood just *before* the deduction. With zero interest and no
other premium the account value therefore stays flat at its pre-deduction value
every month, and the (reused) exception-premium gross equals the full deduction.
"""
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)


def _md_policy():
    # Healthy policy, 25 years in (past the safety net), positive account value.
    return IllustrationPolicyData(
        plancode="MDPREM",
        issue_date=date(2000, 6, 15),
        valuation_date=date(2025, 6, 15),
        issue_age=45,
        attained_age=70,
        maturity_age=121,
        policy_year=26,
        policy_month=1,
        duration=300,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        glp=12.0,
        account_value=50_000.0,
        current_interest_rate=0.0,
        guaranteed_interest_rate=0.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2000, 6, 15),
                                  face_amount=100_000.0, units=100.0)],
    )


def _patch(monkeypatch):
    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _p: PlancodeConfig(
            plancode="MDPREM", dbd=0.0, gint=0.0, corridor_code=None,
            epu_code="0", mfee="0", premium_load="0", prem_flat_load=0.0,
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())


def _rates():
    # 6 per 1,000 COI so the monthly deduction is non-trivial (~300/month).
    return IllustrationRates(coi=[0.0, 6.0], segment_coi={1: [0.0, 6.0]})


@pytest.fixture
def levelized_guideline_policy(monkeypatch):
    policy = _md_policy()
    policy.valuation_date = date(2025, 5, 15)
    policy.policy_year = 25
    policy.policy_month = 12
    policy.glp = 204.24
    policy.premiums_paid_to_date = 0.06
    policy.modal_premium = 37.12
    policy.account_value = 450.0
    config = PlancodeConfig(
        plancode=policy.plancode, dbd=0.0, gint=0.0, corridor_code=None,
        epu_code="0", mfee="100", premium_load="0", prem_flat_load=0.0,
    )
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())
    rates = IllustrationRates(coi=[0.0, 0.0], segment_coi={1: [0.0, 0.0]})
    return policy, config, rates


@pytest.mark.parametrize("timing", list(calc_engine.ProjectionTiming))
@pytest.mark.parametrize("first_month", [1, 3])
@pytest.mark.parametrize("maturity_solve", [False, True])
def test_levelized_guideline_cap_allows_midyear_gep_before_room_is_spent(
    levelized_guideline_policy, timing, first_month, maturity_solve,
):
    from dateutil.relativedelta import relativedelta

    from suiteview.illustration.core.solve_level_to_exception import (
        level_to_exception_options,
    )

    policy, _, rates = levelized_guideline_policy
    if first_month != 1:
        policy.valuation_date += relativedelta(months=first_month - 1)
        policy.duration += first_month - 1
        policy.policy_year = 26
        policy.policy_month = first_month - 1
        policy.accumulated_glp = policy.glp
    expected_cap = 17.01 if first_month == 1 else 20.41
    options = IllustrationOptions(levelizing_premium=True, allow_exception_prems=True)
    if maturity_solve:
        options = level_to_exception_options(options)
    states = IllustrationEngine().project(
        policy, months=13 - first_month, timing=timing, options=options,
        rates_override=rates, bonus_override=BonusConfig(),
    )
    assert len(states) == 14 - first_month
    before = states[1:6]
    first_gep = states[6]
    assert first_gep.policy_month == first_month + 5
    assert all(s.guideline_limit_reached and s.apply_levelized for s in states[1:])
    assert all(s.gp_exception_prem == 0 and s.av_end_of_month > 0 for s in before)
    assert [s.applied_scheduled_premium for s in states[1:7]] == pytest.approx([expected_cap] * 6)
    assert first_gep.guideline_limit - first_gep.premiums_to_date > 75.0
    assert first_gep.md_premium == 0
    assert first_gep.gp_exception_prem == pytest.approx(6 * (100.0 - expected_cap) - 450.0)
    assert first_gep.av_end_of_month == pytest.approx(0)
    assert all(s.gp_exception_mode and not s.lapsed for s in states[6:])


@pytest.mark.parametrize("timing", list(calc_engine.ProjectionTiming))
@pytest.mark.parametrize("restriction", ["below_cap", "exceptions_off", "tefra_off", "cvat", "safety_net"])
def test_midyear_gep_still_requires_guideline_binding_and_eligibility(
    levelized_guideline_policy, timing, restriction,
):
    policy, config, rates = levelized_guideline_policy
    options = IllustrationOptions(levelizing_premium=True, allow_exception_prems=True)
    if restriction == "below_cap":
        policy.modal_premium = 10.0
    elif restriction == "exceptions_off":
        options.allow_exception_prems = False
    elif restriction == "tefra_off":
        options.conform_to_tefra = False
    elif restriction == "cvat":
        policy.def_of_life_ins = "CVAT"
    else:
        config.snet_period = 100
    states = IllustrationEngine().project(
        policy, months=12, timing=timing, options=options,
        rates_override=rates, bonus_override=BonusConfig(), stop_on_lapse=False,
    )
    assert any(s.av_end_of_month < 0 for s in states[1:])
    assert all(s.gp_exception_prem == 0 for s in states)
    if restriction in ("below_cap", "tefra_off", "cvat"):
        assert all(not s.guideline_limit_reached for s in states)


@pytest.mark.parametrize(
    "doli,room,cap_enabled,allow,past_snet,shadow,age,lapsed,pays",
    [
        ("GPT", 0.0, True, True, True, False, 70, False, True),
        ("GPT", 1e-10, True, True, True, False, 70, False, True),
        ("GPT", 0.01, True, True, True, False, 70, False, False),
        ("GPT", 100.0, True, True, True, False, 70, False, False),
        ("GPT", 0.0, False, True, True, False, 70, False, False),
        ("GPT", 0.0, True, False, True, False, 70, False, False),
        ("CVAT", 0.0, True, True, True, False, 70, False, False),
        ("", 0.0, True, True, True, False, 70, False, False),
        ("GPT", 0.0, True, True, False, False, 70, False, False),
        ("GPT", 0.0, True, True, True, True, 70, False, False),
        ("GPT", 0.0, True, True, True, False, 121, False, False),
        ("GPT", 0.0, True, True, True, False, 70, True, False),
    ],
)
def test_spent_guideline_room_triggers_exception_without_annual_flag(
    doli, room, cap_enabled, allow, past_snet, shadow, age, lapsed, pays,
):
    policy = _md_policy()
    policy.def_of_life_ins = doli
    policy.ccv_active = shadow
    result = calc_engine._compute_exception_premium(calc_engine.ExceptionPremiumInput(
        options=IllustrationOptions(allow_exception_prems=allow),
        policy=policy, config=PlancodeConfig(maturity_age=121), rates=_rates(), rate_year=1,
        av_after_charge=-100.0, coi_rate=6.0,
        guideline_limit_reached=False, past_snet=past_snet,
        prior_exception_mode=False, prior_lapsed=lapsed, attained_age=age,
        guideline_limit=1_000.0, premiums_to_date=1_100.0 - room,
        withdrawals_to_date=100.0, guideline_cap_enabled=cap_enabled,
    ))
    assert (result.prem > 0) == pays
    assert result.md_prem == 0
    assert result.av_after_exception == pytest.approx(0 if pays else -100.0)


@pytest.mark.parametrize("timing", list(calc_engine.ProjectionTiming))
@pytest.mark.parametrize("md_premium", [False, True])
def test_zero_glp_starts_exception_period_and_spends_av_first(monkeypatch, timing, md_premium):
    from suiteview.illustration.models.input_set import (
        DatedTransaction,
        IllustrationInputSet,
        ScheduledTransaction,
        TransactionKind,
    )
    _patch(monkeypatch)
    policy = _md_policy()
    policy.glp = 0.0
    policy.gsp = policy.accumulated_glp = 100_000.0
    policy.account_value = 1_000.0
    policy.modal_premium = 5_000.0
    inputs = IllustrationInputSet(
        scheduled_transactions=[ScheduledTransaction(TransactionKind.PREMIUM, 1, 5_000.0, "M")],
        dated_transactions=[
            DatedTransaction(TransactionKind.PREMIUM, date(2025, 7, 15), 10_000.0),
            DatedTransaction(TransactionKind.LOAN_REPAYMENT, date(2025, 7, 15), 100.0),
        ],
    )
    states = IllustrationEngine().project(
        policy, months=6, timing=timing, future_inputs=inputs,
        options=IllustrationOptions(
            allow_exception_prems=False, pay_monthly_deduction=md_premium,
            apply_excess_repayment_as_premium=True),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    assert len(states) == 7
    assert all(s.gp_exception_mode for s in states)
    first = states[1]
    assert first.av_end_of_month > 0
    assert first.gp_exception_prem == 0
    assert first.av_end_of_month < policy.account_value
    for s in states[1:]:
        assert s.gross_premium == s.md_premium == 0
        assert s.guideline_forceout == 0
        assert not s.lapsed
    assert states[-1].gp_exception_prem > 0
    assert states[-1].av_end_of_month == pytest.approx(0.0, abs=0.01)
    assert policy.account_value == 1_000.0


@pytest.mark.parametrize("doli,glp,known,from_issue,expected", [
    ("GPT", 0.0, True, False, True),
    ("CVAT", 0.0, True, False, False),
    ("", 0.0, True, False, False),
    ("GPT", 12.0, True, False, False),
    ("GPT", -12.0, True, False, False),
    ("GPT", 0.0, False, False, False),
    ("GPT", 0.0, True, True, False),
])
def test_starting_exception_classification(doli, glp, known, from_issue, expected):
    policy = IllustrationPolicyData(
        def_of_life_ins=doli, glp=glp, glp_is_known=known, run_from_issue=from_issue)
    assert policy.in_exception_period is expected


def test_guaranteed_projection_retains_locked_exception_premiums(monkeypatch):
    from suiteview.illustration.core.guaranteed_projection import (
        guaranteed_options,
        lock_values,
    )
    _patch(monkeypatch)
    policy = _md_policy()
    policy.glp = 0.0
    policy.gsp = 100_000.0
    policy.account_value = 200.0
    current = IllustrationEngine().project(
        policy, months=3, rates_override=_rates(), bonus_override=BonusConfig())
    guaranteed = IllustrationEngine().project(
        policy, months=3, future_inputs=lock_values(policy, current),
        options=guaranteed_options(), rates_override=_rates(), bonus_override=BonusConfig())
    assert current[1].gp_exception_prem > 0
    for current_row, guaranteed_row in zip(current[1:], guaranteed[1:]):
        assert guaranteed_row.gross_premium == pytest.approx(current_row.gp_exception_prem)
        assert guaranteed_row.gp_exception_prem == 0
        assert not guaranteed_row.gp_exception_mode


@pytest.mark.parametrize("account_value", [0.0, -605.2])
def test_starting_exception_ignores_billing_and_immediately_funds_empty_av(
    monkeypatch, account_value,
):
    _patch(monkeypatch)
    policy = _md_policy()
    policy.glp = 0.0
    policy.gsp = 100_000.0
    policy.modal_premium = 5_000.0
    policy.account_value = account_value
    states = IllustrationEngine().project(
        policy, months=2, rates_override=_rates(), bonus_override=BonusConfig())
    for state in states[1:]:
        assert state.gross_premium == 0
        assert state.gp_exception_prem > 0
        assert state.av_end_of_month == pytest.approx(0.0, abs=0.01)
        assert not state.lapsed


@pytest.mark.parametrize("has_shadow,past_snet", [(True, True), (False, False)])
def test_starting_exception_preserves_shadow_and_safety_net_gates(has_shadow, past_snet):
    policy = _md_policy()
    policy.glp = 0.0
    policy.ccv_active = has_shadow
    result = calc_engine._compute_exception_premium(calc_engine.ExceptionPremiumInput(
        options=IllustrationOptions(), policy=policy, config=PlancodeConfig(),
        rates=_rates(), rate_year=1,
        av_after_charge=-100.0, coi_rate=6.0,
        guideline_limit_reached=False, past_snet=past_snet,
        prior_exception_mode=True, prior_lapsed=False, attained_age=70))
    assert result.prem == 0
    assert result.av_after_exception == -100.0


def test_monthly_deduction_premium_holds_account_value_flat(monkeypatch):
    _patch(monkeypatch)
    states = IllustrationEngine().project(
        _md_policy(), months=6,
        # TEFRA off disables the guideline cap, so the MD premium is never
        # capped and the AV stays flat at its pre-deduction value.
        options=IllustrationOptions(pay_monthly_deduction=True, conform_to_tefra=False),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    projected = states[1:]  # states[0] is the inforce (month-0) snapshot
    assert len(projected) == 6
    for s in projected:
        assert s.total_deduction > 0
        assert s.md_premium_mode is True
        assert s.md_premium > 0.0
        assert s.md_premium_capped is False
        # The MD premium restores the full deduction (zero interest).
        assert s.md_premium_gross == pytest.approx(s.total_deduction)
        # Discount = the COI-saving portion of the AV bump (no load here).
        assert s.md_premium_discount == pytest.approx(s.md_premium_gross - s.md_premium)
        # Monthly Deduction is NOT the GP exception — it must not flip the
        # exception display mode or the force-out-bypassing GP exception flag.
        assert s.exception_prem_mode is False
        assert s.gp_exception_mode is False
        assert s.gp_exception_prem == 0.0
        # The premium counts toward premiums paid / cost basis (carried forward).
        assert s.premiums_to_date_after_exception == pytest.approx(
            s.premiums_to_date + s.md_premium)
        # Zero interest: the premium restores the AV to its pre-deduction value.
        assert s.av_end_of_month == pytest.approx(s.guideline_av_before_monthly_deduction)
    # The account value is held flat at its starting value across all months.
    assert projected[-1].av_end_of_month == pytest.approx(states[0].av_end_of_month)


def test_monthly_deduction_premium_capped_at_guideline(monkeypatch):
    # A GPT policy with no guideline room: the MD premium is capped to zero
    # in-month (it never over-funds, so there is no force-out claw-back) and the
    # account value declines by the deduction. With exceptions off it just runs
    # down — MD is subject to the guideline, unlike the GP exception.
    _patch(monkeypatch)
    states = IllustrationEngine().project(
        _md_policy(), months=6,
        options=IllustrationOptions(pay_monthly_deduction=True, conform_to_tefra=True),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    projected = states[1:]
    for s in projected:
        assert s.md_premium_capped is True
        assert s.md_premium == 0.0
        assert s.gp_exception_mode is False     # exceptions not allowed
        assert s.guideline_forceout == 0.0      # capped in-month, nothing to claw back
    assert projected[-1].av_end_of_month < states[0].av_end_of_month


def test_md_premium_hands_off_to_gp_exception_when_capped(monkeypatch):
    # Thin AV + tiny guideline room + exceptions allowed: the MD premium spends
    # the last of the room (capped), then the GP exception covers the residual
    # past the guideline — in the SAME month. Once latched the exception holds
    # the AV at zero and the MD premium goes silent.
    _patch(monkeypatch)
    policy = _md_policy()
    policy.account_value = 200.0   # thin → goes negative in month 1
    policy.gsp = 50.0              # tiny guideline room → partial MD, then exception
    states = IllustrationEngine().project(
        policy, months=6,
        options=IllustrationOptions(
            pay_monthly_deduction=True, conform_to_tefra=True,
            allow_exception_prems=True),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    projected = states[1:]
    first = projected[0]
    # Same-month hand-off — both premiums non-zero.
    assert first.md_premium > 0.0
    assert first.md_premium_capped is True
    assert first.md_premium_discount > 0.0
    assert first.gp_exception_prem > 0.0
    assert first.gp_exception_prem_discount > 0.0
    assert first.exception_prem_mode is True    # the GP exception (not MD) flips this
    assert first.gp_exception_mode is True
    for s in projected:
        assert s.gp_exception_mode is True       # latched
        assert s.av_end_of_month == pytest.approx(0.0, abs=0.05)
    for s in projected[1:]:
        assert s.md_premium == 0.0               # no room left once over the guideline
        assert s.gp_exception_prem > 0.0


def test_gp_exception_premium_includes_flat_load_for_1u135100():
    config = calc_engine.load_plancode("1U135100")
    assert config.prem_flat_load == 1.65
    rates = IllustrationRates(tpp=[0.0, 0.10])

    result = calc_engine._compute_exception_premium(calc_engine.ExceptionPremiumInput(
        options=IllustrationOptions(allow_exception_prems=True),
        policy=_md_policy(),
        config=config,
        rates=rates,
        rate_year=1,
        av_after_charge=-100.0,
        coi_rate=0.0,
        guideline_limit_reached=True,
        past_snet=True,
        prior_exception_mode=False,
        prior_lapsed=False,
        attained_age=70,
    ))

    # Net premium is exactly the $100 shortfall after both the 10% load and
    # 1U135100's $1.65 flat load.
    assert result.prem == pytest.approx((100.0 + 1.65) / 0.90)
    assert result.percentage_load == pytest.approx(result.prem * 0.10)
    assert result.flat_load == pytest.approx(1.65)
    assert result.gp_percentage_load == pytest.approx(result.prem * 0.10)
    assert result.gp_flat_load == pytest.approx(1.65)
    assert result.prem - result.percentage_load - result.flat_load == pytest.approx(100.0)
    assert result.av_after_exception == pytest.approx(0.0)


def test_exception_loads_are_included_in_monthly_premium_load_totals(monkeypatch):
    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _p: PlancodeConfig(
            plancode="1U135100",
            maturity_age=95,
            snet_period=10,
            dbd=0.0,
            gint=0.0,
            corridor_code=None,
            epu_code="0",
            mfee="0",
            premium_load="Table",
            prem_flat_load=1.65,
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())
    policy = _md_policy()
    policy.plancode = "1U135100"
    policy.account_value = 0.0
    policy.gsp = 0.0
    rates = IllustrationRates(
        coi=[0.0, 6.0],
        segment_coi={1: [0.0, 6.0]},
        tpp=[0.0, 0.10],
        epp=[0.0, 0.10],
    )

    state = IllustrationEngine().project(
        policy,
        months=1,
        options=IllustrationOptions(allow_exception_prems=True),
        rates_override=rates,
        bonus_override=BonusConfig(),
    )[1]

    assert state.gp_exception_prem > 0.0
    assert state.gp_exception_percentage_load == pytest.approx(
        state.gp_exception_prem * 0.10
    )
    assert state.gp_exception_flat_load == pytest.approx(1.65)
    assert state.flat_load == pytest.approx(1.65)
    assert state.target_load > 0.0
    assert state.total_premium_load == pytest.approx(
        state.target_load + state.excess_load + state.flat_load
    )


def test_option_b_switches_to_a_before_first_gp_exception(monkeypatch):
    dbd = 0.03
    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _p: PlancodeConfig(
            plancode="MDPREM", dbd=dbd, gint=0.0, corridor_code=None,
            epu_code="0", mfee="0", premium_load="0", prem_flat_load=0.0,
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())
    policy = _md_policy()
    policy.db_option = "B"
    policy.account_value = 200.0
    policy.gsp = 50.0

    states = IllustrationEngine().project(
        policy, months=3,
        options=IllustrationOptions(
            pay_monthly_deduction=True, conform_to_tefra=True,
            allow_exception_prems=True, switch_to_option_a_in_exception=True),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    option_a = _md_policy()
    option_a.account_value = 200.0
    option_a.gsp = 50.0
    option_a_states = IllustrationEngine().project(
        option_a, months=3,
        options=IllustrationOptions(
            pay_monthly_deduction=True, conform_to_tefra=True,
            allow_exception_prems=True),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )

    assert states[0].db_option == "B"
    assert states[1].gp_exception_prem > 0.0
    assert states[1].total_deduction == pytest.approx(option_a_states[1].total_deduction)
    assert states[1].gp_exception_prem_gross == pytest.approx(
        option_a_states[1].gp_exception_prem_gross
    )
    assert states[1].gp_exception_prem_discount == pytest.approx(
        option_a_states[1].gp_exception_prem_discount
    )
    assert all(state.db_option == "A" for state in states[1:])
    assert policy.db_option == "B"


def test_option_b_exception_period_uses_option_a_every_row(monkeypatch):
    # Mirrors the real "Prem to Maturity" path: NO Monthly-Deduction premium, the
    # GP exception fires purely because the policy is at the guideline limit with
    # a residual negative AV, and the exception is CARRIED FORWARD (latched) for
    # many months. Every exception row — the first trigger AND all carried-forward
    # rows — must use Option A (level DB) assumptions, so the COI feedback
    # ("Exc Prem Discount") equals gross x coi_rate/1000 rather than collapsing to
    # the near-wash Option B factor.
    dbd = 0.0425
    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _p: PlancodeConfig(
            plancode="MDPREM", dbd=dbd, gint=0.0, corridor_code=None,
            epu_code="0", mfee="0", premium_load="0", prem_flat_load=0.0,
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())
    # Force the guideline-limit-reached flag on (no room), so the exception is
    # driven by the guideline — not a capped MD premium.
    monkeypatch.setattr(calc_engine, "_guideline_limit_reached", lambda *a, **k: True)

    policy = _md_policy()
    policy.db_option = "B"
    policy.account_value = 100.0   # thin → negative every month → exception refills

    states = IllustrationEngine().project(
        policy, months=6,
        options=IllustrationOptions(
            conform_to_tefra=True, allow_exception_prems=True,
            switch_to_option_a_in_exception=True),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    exc_rows = [s for s in states[1:] if s.gp_exception_mode]
    # A multi-row exception period (not just the trigger edge).
    assert len(exc_rows) >= 3
    for s in exc_rows:
        # The policy acts as Option A for the whole exception period.
        assert s.db_option == "A"
        if s.gp_exception_prem_gross > 0.0:
            # Option A COI feedback: full COI rate, NOT the Option B near-wash.
            assert s.gp_exception_prem_discount == pytest.approx(
                s.gp_exception_prem_gross * s.coi_rate / 1000.0, rel=1e-6)
    # The caller's policy object is untouched (private-copy guard).
    assert policy.db_option == "B"


def test_option_b_exception_period_default_keeps_option_b(monkeypatch):
    # Gating check: without switch_to_option_a_in_exception, an Option B policy
    # keeps Option B assumptions through the GP exception period (the switch is
    # opt-in via the "Switch to Option A in exception period" control).
    dbd = 0.0425
    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _p: PlancodeConfig(
            plancode="MDPREM", dbd=dbd, gint=0.0, corridor_code=None,
            epu_code="0", mfee="0", premium_load="0", prem_flat_load=0.0,
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())
    monkeypatch.setattr(calc_engine, "_guideline_limit_reached", lambda *a, **k: True)

    policy = _md_policy()
    policy.db_option = "B"
    policy.account_value = 100.0

    states = IllustrationEngine().project(
        policy, months=6,
        options=IllustrationOptions(
            conform_to_tefra=True, allow_exception_prems=True),
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    exc_rows = [s for s in states[1:] if s.gp_exception_mode]
    assert len(exc_rows) >= 3
    # No opt-in -> the policy stays Option B for the whole exception period.
    for s in exc_rows:
        assert s.db_option == "B"


def test_monthly_deduction_premium_active_honors_windows():
    # The fix locus: a Monthly-Deduction premium row must be active ONLY within
    # its year window. Without windows the premium runs the whole projection
    # (the plain "pay the deduction" case); with windows it is active only in a
    # window's policy years, so the window's END is honored and later premium
    # rows can take over once it ends. (Engine-level; hermetic — no rate DB.)
    from suiteview.illustration.core.calc_engine import (
        _monthly_deduction_premium_active as active,
    )

    # Master toggle off -> never active.
    assert active(IllustrationOptions(pay_monthly_deduction=False), 30) is False

    # No windows -> active every year (whole projection).
    whole = IllustrationOptions(pay_monthly_deduction=True)
    assert all(active(whole, year) for year in (1, 30, 121))

    # A single bounded window 10..12 -> active only inside it.
    one = IllustrationOptions(
        pay_monthly_deduction=True, monthly_deduction_windows=[(10, 12)])
    assert [active(one, y) for y in range(8, 15)] == [
        False, False, True, True, True, False, False]

    # An open-ended window (end None) runs to maturity from its start.
    open_ended = IllustrationOptions(
        pay_monthly_deduction=True, monthly_deduction_windows=[(30, None)])
    assert active(open_ended, 29) is False
    assert active(open_ended, 30) is True
    assert active(open_ended, 121) is True

    # Two separate windows each engage/disengage on their own bounds; the gap
    # between them is inactive (later premium rows apply there).
    two = IllustrationOptions(
        pay_monthly_deduction=True, monthly_deduction_windows=[(10, 11), (20, 22)])
    assert [active(two, y) for y in (9, 10, 11, 12, 19, 20, 22, 23)] == [
        False, True, True, False, False, True, True, False]


def test_account_value_declines_without_monthly_deduction_premium(monkeypatch):
    _patch(monkeypatch)
    states = IllustrationEngine().project(
        _md_policy(), months=6,
        options=IllustrationOptions(),  # default: no Monthly Deduction premium
        rates_override=_rates(), bonus_override=BonusConfig(),
    )
    projected = states[1:]
    # Healthy policy, so neither premium triggers; with no premium the account
    # value falls by each month's deduction.
    assert all(s.md_premium == 0.0 and s.gp_exception_prem == 0.0 for s in projected)
    assert projected[-1].av_end_of_month < states[0].av_end_of_month


def test_option_b_shrinks_the_coi_feedback_discount(monkeypatch):
    # With an increasing death benefit (Option B) a premium also raises the DB,
    # so the COI saving is only the level-DB feedback scaled by (1 − 1/(1+dbd)^(1/12)).
    dbd = 0.03
    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _p: PlancodeConfig(
            plancode="MDPREM", dbd=dbd, gint=0.0, corridor_code=None,
            epu_code="0", mfee="0", premium_load="0", prem_flat_load=0.0,
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())

    def feedback_for(db_option: str) -> float:
        policy = _md_policy()
        policy.db_option = db_option
        s = IllustrationEngine().project(
            policy, months=1,
            options=IllustrationOptions(pay_monthly_deduction=True, conform_to_tefra=False),
            rates_override=_rates(), bonus_override=BonusConfig(),
        )[1]
        assert s.md_premium > 0.0
        # discount / AV-restoration = the COI saving per dollar of AV bump (phi).
        return s.md_premium_discount / s.md_premium_gross

    phi_a = feedback_for("A")
    phi_b = feedback_for("B")
    df = round((1.0 + dbd) ** (1.0 / 12.0), 7)
    assert phi_b == pytest.approx(phi_a * (1.0 - 1.0 / df), rel=1e-6)
    # Option C is treated like Option B here (conservative).
    assert feedback_for("C") == pytest.approx(phi_b, rel=1e-6)
