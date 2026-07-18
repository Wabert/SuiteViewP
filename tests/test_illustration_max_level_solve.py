"""Max Level Allowed solve — the largest level premium the guideline acceptance
chain never caps, solved on the real projection so mid-stream guideline changes
(face decrease, DBO switch) move the answer.
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

def _stub_state(premium_capped: bool) -> SimpleNamespace:
    return SimpleNamespace(
        premium_capped=premium_capped, attained_age=121, av_end_of_month=1.0,
        premiums_to_date=0.0, gp_exception_prem_gross=0.0,
        applied_loan_repayment=0.0)


def _level_premium(future_inputs, start_year: int) -> float:
    """The solver's level premium out of a projection's scheduled transactions."""
    return max(
        t.amount for t in future_inputs.scheduled_transactions
        if t.kind == TransactionKind.PREMIUM and t.policy_year == start_year)


def test_solve_finds_cap_boundary_and_carries_policy_changes():
    # The stub caps any level premium above 500/mo. The solve must land on the
    # accepted side of that boundary, and every projection it runs must carry
    # the base input set's policy changes (they move the guidelines).
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
            premium = _level_premium(future_inputs, 3)
            return [_stub_state(premium_capped=premium > 500.0)]

    result = solve_max_level_allowed(
        policy, mode="M", start_policy_year=3, base_future_inputs=base,
        engine=_StubEngine())

    assert result.premium == pytest.approx(500.0, abs=0.02)
    assert result.mode == "M"
    assert captured
    for future in captured:
        assert future.policy_changes == [change]
        # Premiums stop at age 100 (maturity 121 > 100): the solver appends a
        # zero schedule at the policy year attaining 100 (issue age 50 -> 51).
        assert any(
            t.kind == TransactionKind.PREMIUM and t.policy_year == 51
            and t.amount == 0.0
            for t in future.scheduled_transactions)


def test_solve_binds_at_tightest_mid_projection_point():
    # A mid-projection guideline DROP can make an intermediate year the binding
    # constraint even when the endpoint has plenty of room — the max level
    # premium must respect the cumulative limit at acceptance time, not just
    # the final AccumGLP/GSP. Cumulative limits (annual premium A, 20 payment
    # years): 10,000 for years 1-4, 3,000 for years 5-9 (the drop), 100,000
    # from year 10 on. The tightest point is the LAST year of the dip:
    # A <= 3000/9 = 333.33 — far below the endpoint's 100,000/20 = 5,000.
    def _limit(year: int) -> float:
        if year < 5:
            return 10_000.0
        if year < 10:
            return 3_000.0
        return 100_000.0

    policy = IllustrationPolicyData(
        def_of_life_ins="GPT", maturity_age=121, issue_age=50,
        billing_frequency=12, modal_premium=100.0)

    class _StubEngine:
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            annual = _level_premium(future_inputs, 1)
            capped = any(
                annual * year > _limit(year) + 1e-9 for year in range(1, 21))
            return [_stub_state(premium_capped=capped)]

    result = solve_max_level_allowed(
        policy, mode="A", start_policy_year=1, engine=_StubEngine())

    assert result.premium == pytest.approx(3000.0 / 9.0, abs=0.02)


def test_solve_rejects_cvat_and_base_inputs_over_the_limit():
    cvat = IllustrationPolicyData(def_of_life_ins="CVAT", maturity_age=121)
    with pytest.raises(MaxLevelAllowedError):
        solve_max_level_allowed(cvat, engine=None)

    class _AlwaysCapped:
        def project(self, _policy, **_kw):
            return [_stub_state(premium_capped=True)]

    policy = IllustrationPolicyData(
        def_of_life_ins="GPT", maturity_age=121, issue_age=50,
        billing_frequency=1, modal_premium=100.0)
    with pytest.raises(MaxLevelAllowedError):
        solve_max_level_allowed(policy, engine=_AlwaysCapped())


# ── Real engine: a guideline change moves the solved maximum ─────────────────

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
    # level premium drops to ~ 39,000 / 719 = 54.24. The old closed form —
    # initial guideline room only — could not see this.
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
