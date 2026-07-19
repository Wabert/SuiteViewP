"""Max Level Allowed solve — the closed-form room premium: remaining lifetime
guideline room (engine MAX(GSP, AccumGLP) at the end of the paying window,
after any base-input policy changes recalc the guidelines) spread level over
the modal payments to get there. The projection applies it and lets the
guideline cap clip transiently tight years — a transient early cap must NOT
collapse the answer (that was the old "never capped anywhere" bisection).
"""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.solve_max_level_allowed import (
    MaxLevelAllowedError,
    solve_max_level_allowed,
)
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    PolicyChangeEvent,
    PolicyChangeKind,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)


# ── Solver mechanics on a stub engine ────────────────────────────────────────

def _stub_state(policy_year=0, policy_month=0, attained_age=0, gsp=0.0,
                accumulated_glp=0.0, prem_less_wd=0.0) -> SimpleNamespace:
    return SimpleNamespace(
        policy_year=policy_year, policy_month=policy_month,
        attained_age=attained_age, gsp=gsp, accumulated_glp=accumulated_glp,
        prem_less_wd=prem_less_wd, premium_capped=False,
        av_end_of_month=1.0, premiums_to_date=0.0,
        gp_exception_prem_gross=0.0, applied_loan_repayment=0.0)


def _stub_projection(issue_age: int, years: int, *, gsp: float,
                     accum_final: float, prem_less_wd: float) -> list:
    """Seed row + full monthly stream for `years` policy years."""
    states = [_stub_state()]                       # inforce seed row (skipped)
    for year in range(1, years + 1):
        for month in range(1, 13):
            states.append(_stub_state(
                policy_year=year, policy_month=month,
                attained_age=issue_age + year - 1,
                gsp=gsp, accumulated_glp=accum_final,
                prem_less_wd=prem_less_wd))
    return states


def _level_amount(future_inputs, start_year: int) -> float:
    """The level premium the solver scheduled at its start year."""
    return max(
        t.amount for t in future_inputs.scheduled_transactions
        if t.kind == TransactionKind.PREMIUM and t.policy_year == start_year)


def test_solve_spreads_room_over_payments_and_carries_policy_changes():
    # Room = MAX(GSP, AccumGLP at end) − consumed = max(1000, 10000) − 200
    # = 9,800 over monthly payments years 3..50 (issue 50 → age-100 stop at
    # year 51): 48 × 12 = 576 → 17.013… → floored to 17.01. Exactly two
    # projections run (zero probe + final), both carrying the base policy
    # changes and the age-100 stop row; the probe's level row is 0.00 so it
    # terminates base premiums exactly like the real level premium will.
    policy = IllustrationPolicyData(
        def_of_life_ins="GPT", maturity_age=121, issue_age=50,
        billing_frequency=1, modal_premium=100.0)
    change = PolicyChangeEvent(
        kind=PolicyChangeKind.FACE_AMOUNT, effective_date=date(2027, 11, 9),
        value=75000.0)
    base = IllustrationInputSet(policy_changes=[change])

    captured = []

    class _StubEngine:
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            captured.append(future_inputs)
            return _stub_projection(50, 71, gsp=1000.0, accum_final=10000.0,
                                    prem_less_wd=200.0)

    result = solve_max_level_allowed(
        policy, mode="M", start_policy_year=3, base_future_inputs=base,
        engine=_StubEngine())

    assert result.premium == pytest.approx(9800.0 / 576.0, abs=0.01)
    assert result.premium == 17.01                 # floored to the resolution
    assert result.mode == "M"
    assert result.iterations == 2
    assert len(captured) == 2
    probe, final = captured
    assert _level_amount(probe, 3) == 0.0          # zero-premium probe
    assert _level_amount(final, 3) == 17.01
    for future in captured:
        assert future.policy_changes == [change]
        # Premiums stop at age 100 (maturity 121 > 100): the solver appends a
        # zero schedule at the policy year attaining 100 (issue age 50 -> 51).
        assert any(
            t.kind == TransactionKind.PREMIUM and t.policy_year == 51
            and t.amount == 0.0
            for t in future.scheduled_transactions)


def test_solve_counts_only_modal_due_months_in_the_window():
    # Quarterly from year 2: due months 1/4/7/10 in years 2..50 → 49 × 4 = 196
    # payments. Room 9,800 → 50.00/quarter.
    policy = IllustrationPolicyData(
        def_of_life_ins="GPT", maturity_age=121, issue_age=50,
        billing_frequency=3, modal_premium=100.0)

    class _StubEngine:
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            return _stub_projection(50, 71, gsp=0.0, accum_final=10000.0,
                                    prem_less_wd=200.0)

    result = solve_max_level_allowed(
        policy, mode="Q", start_policy_year=2, engine=_StubEngine())
    assert result.premium == pytest.approx(9800.0 / 196.0, abs=0.01)


def test_solve_rejects_cvat_and_base_inputs_over_the_limit():
    cvat = IllustrationPolicyData(def_of_life_ins="CVAT", maturity_age=121)
    with pytest.raises(MaxLevelAllowedError):
        solve_max_level_allowed(cvat, engine=None)

    # Base inputs already past the lifetime room → nothing to solve.
    class _RoomlessEngine:
        def project(self, _policy, **_kw):
            return _stub_projection(50, 71, gsp=1000.0, accum_final=10000.0,
                                    prem_less_wd=20000.0)

    policy = IllustrationPolicyData(
        def_of_life_ins="GPT", maturity_age=121, issue_age=50,
        billing_frequency=1, modal_premium=100.0)
    with pytest.raises(MaxLevelAllowedError):
        solve_max_level_allowed(policy, engine=_RoomlessEngine())


# ── Real engine: room math + guideline changes + transient caps ──────────────

class _FlatRatesEngine(IllustrationEngine):
    """Engine with empty rates — no COIs/expenses, so the guideline acceptance
    chain is the only thing shaping the projection."""

    def _load_rates(self, policy, config):
        return IllustrationRates()


def _test_config(_plancode) -> PlancodeConfig:
    return PlancodeConfig(
        plancode="TEST", interest_method="ExactDays", gint=0.0, dbd=0.0,
        premium_load="0", prem_flat_load=0.0, epu_code="0", mfee="0",
        poav_code="0", bonus="0", corridor_code=None, snet_period=0,
        maturity_age=121, loan_type="Arrears")


def _gpt_policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        plancode="TEST",
        def_of_life_ins="GPT",
        issue_date=date(2026, 1, 15),
        valuation_date=date(2026, 1, 15),
        issue_age=40,
        attained_age=40,
        maturity_age=121,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=5_000.0,
        modal_premium=100.0,
        billing_frequency=1,
        glp=1_200.0,
        gsp=1_200.0,
        accumulated_glp=1_200.0,   # year-1 GLP banked at issue
        current_interest_rate=0.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2026, 1, 15),
                                  face_amount=100_000.0, units=100.0)],
    )


@pytest.fixture
def _flat_plancode(monkeypatch):
    from suiteview.illustration.core import calc_engine
    monkeypatch.setattr(calc_engine, "load_plancode", _test_config)
    monkeypatch.setattr(
        calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())


def test_real_engine_max_level_matches_guideline_room(_flat_plancode):
    # GLP = GSP = 1,200/yr, payments monthly from month 2 of year 1 through the
    # year attaining age 100 (years 1..60 -> 719 payments), AccumGLP at the
    # last payment year = 1200 * 60 = 72,000. Max monthly level premium
    # ~ 72,000 / 719 = 100.14.
    engine = _FlatRatesEngine()
    result = solve_max_level_allowed(
        _gpt_policy(), mode="M", start_policy_year=1, engine=engine)

    assert result.premium == pytest.approx(100.14, abs=0.25)


def test_real_engine_guideline_drop_lowers_max_level(_flat_plancode):
    # A face decrease at the year-6 anniversary halves the guideline premiums
    # (injected: GLP/GSP 1,200 -> 600). AccumGLP through the last payment year
    # is then 1200*5 + 600*55 = 39,000 instead of 72,000, so the max monthly
    # level premium drops to ~ 39,000 / 719 = 54.24. The initial-room-only
    # closed form could not see this; the zero-premium probe does.
    engine = _FlatRatesEngine()
    change = PolicyChangeEvent(
        kind=PolicyChangeKind.FACE_AMOUNT,
        effective_date=date(2031, 1, 15),          # year-6 anniversary
        value=50_000.0,
        metadata={"new_glp": 600.0, "new_gsp": 600.0, "new_7pay": 600.0},
    )
    base = IllustrationInputSet(policy_changes=[change])

    unchanged = solve_max_level_allowed(
        _gpt_policy(), mode="M", start_policy_year=1, engine=engine)
    changed = solve_max_level_allowed(
        _gpt_policy(), mode="M", start_policy_year=1,
        base_future_inputs=base, engine=engine)

    assert changed.premium < unchanged.premium
    assert changed.premium == pytest.approx(54.24, abs=0.25)


def test_real_engine_transient_early_cap_does_not_collapse_the_answer(
        _flat_plancode):
    # A policy already funded right up to its current guideline (paid 1,150 of
    # the 1,200 year-1 room) has almost no room THIS year, but the lifetime
    # room is 72,000 − 1,150 = 70,850 over 719 payments ≈ 98.53/mo. The old
    # never-capped bisection collapsed to the tight first years (a fraction of
    # GLP/12); the closed form spreads the lifetime room and lets the cap clip
    # the early payments instead.
    policy = _gpt_policy()
    policy.premiums_paid_to_date = 1_150.0
    engine = _FlatRatesEngine()

    result = solve_max_level_allowed(
        policy, mode="M", start_policy_year=1, engine=engine)

    assert result.premium == pytest.approx(70_850.0 / 719.0, abs=0.25)
    # Sanity: the early years' cap really does bind at this premium — the
    # answer rides the cap rather than shrinking to it.
    from suiteview.illustration.core.solve_level_to_exception import (
        level_to_exception_options,
    )
    from suiteview.illustration.models.input_set import ScheduledTransaction
    future = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1,
                             amount=result.premium, mode="M"),
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=61,
                             amount=0.0, mode="A"),
    ])
    states = engine.project(
        policy, options=level_to_exception_options(None, True),
        future_inputs=future, stop_on_lapse=False)
    assert any(s.premium_capped for s in states)
