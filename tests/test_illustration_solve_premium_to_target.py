"""Premium Solve — the minimum level premium that carries a chosen value
(Account Value / Surrender Value / Shadow Account Value) to a target amount at
a beginning-of-year target age (age 100 → the ending value at attained age 99,
month 12). Bracket-and-bisect on the real engine; an unreachable target raises
with the best value reached so the UI can report it.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.solve_premium_to_target import (
    PremiumTargetError,
    solve_premium_to_target,
)
from suiteview.illustration.models.input_set import TransactionKind
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)


# ── Solver mechanics on a stub engine ────────────────────────────────────────

def _policy(**overrides) -> IllustrationPolicyData:
    fields = dict(
        def_of_life_ins="GPT", maturity_age=121, issue_age=50,
        billing_frequency=1, modal_premium=100.0)
    fields.update(overrides)
    return IllustrationPolicyData(**fields)


def _level_amount(future_inputs, start_year: int) -> float:
    return max(
        t.amount for t in future_inputs.scheduled_transactions
        if t.kind == TransactionKind.PREMIUM and t.policy_year == start_year)


def _stub_states(issue_age: int, years: int, value_fn) -> list:
    """Monthly states; av/sv/shadow at year Y month 12 come from value_fn(Y)."""
    states = []
    for year in range(1, years + 1):
        for month in range(1, 13):
            value = value_fn(year) if month == 12 else 0.0
            states.append(SimpleNamespace(
                policy_year=year, policy_month=month,
                attained_age=issue_age + year - 1,
                av_end_of_month=value, ending_sv=value, shadow_eav=value))
    return states


def test_solve_bisects_to_the_minimal_meeting_premium():
    # Stubbed ending AV at every year-end = premium × 100. Target: 5,000 at
    # age 60 (issue 50 → target year 10, month 12) → premium 50.00.
    class _StubEngine:
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            premium = _level_amount(future_inputs, 1)
            return _stub_states(50, 20, lambda _y: premium * 100.0)

    result = solve_premium_to_target(
        _policy(), target="av", amount=5000.0, at_age=60,
        mode="M", start_policy_year=1, engine=_StubEngine())

    assert result.premium == pytest.approx(50.00, abs=0.02)
    assert result.achieved_value >= 5000.0 - 0.005
    assert result.target == "av"
    assert result.at_age == 60


def test_solve_lands_on_the_exact_penny_at_a_sensitive_boundary():
    """The boundary premium sits just under a penny grid point: the solve must
    return THAT penny, not the next one up.

    Stubbed ending value = premium × 100 and target 3,437.99 puts the true
    boundary at 34.3799: 34.38 meets (3,438.00), 34.37 misses (3,437.00). The
    old ceiling-of-hi rounding (bracket only narrowed to a full penny)
    overshot this to 34.39. Convention: bisect until hi − lo < half a penny,
    then round up to the nearest penny and verify that candidate directly.
    """
    class _StubEngine:
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            premium = _level_amount(future_inputs, 1)
            return _stub_states(50, 20, lambda _y: premium * 100.0)

    result = solve_premium_to_target(
        _policy(ccv_active=True), target="shadow", amount=3437.99, at_age=60,
        mode="M", start_policy_year=1, engine=_StubEngine())

    assert result.premium == 34.38
    assert result.achieved_value == pytest.approx(3438.0)


def test_solve_returns_zero_when_base_inputs_already_meet_target():
    class _RichEngine:
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            return _stub_states(50, 20, lambda _y: 9_999.0)

    result = solve_premium_to_target(
        _policy(), target="av", amount=5000.0, at_age=60,
        mode="M", start_policy_year=1, engine=_RichEngine())
    assert result.premium == 0.0
    assert result.achieved_value == pytest.approx(9_999.0)


def test_solve_unreachable_target_raises_with_best_value():
    # The value plateaus at 3,000 no matter the premium (guideline cap /
    # charges) — the solve must say so rather than loop.
    class _PlateauEngine:
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            return _stub_states(50, 20, lambda _y: 3_000.0)

    with pytest.raises(PremiumTargetError) as excinfo:
        solve_premium_to_target(
            _policy(), target="av", amount=5000.0, at_age=60,
            mode="M", start_policy_year=1, engine=_PlateauEngine())
    assert excinfo.value.best_value == pytest.approx(3_000.0)
    assert "3,000.00" in str(excinfo.value)


def test_solve_lapse_before_target_age_is_unreachable():
    # The projection never reaches the target year (lapses at year 5) at any
    # premium — no target-age value exists.
    class _LapsingEngine:
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            return _stub_states(50, 5, lambda _y: 100.0)

    with pytest.raises(PremiumTargetError) as excinfo:
        solve_premium_to_target(
            _policy(), target="av", amount=5000.0, at_age=60,
            mode="M", start_policy_year=1, engine=_LapsingEngine())
    assert "no target-age value" in str(excinfo.value)


def test_solve_validates_the_request():
    with pytest.raises(PremiumTargetError):        # unknown target
        solve_premium_to_target(
            _policy(), target="db", amount=1.0, at_age=60, engine=None)
    with pytest.raises(PremiumTargetError):        # shadow without a shadow acct
        solve_premium_to_target(
            _policy(), target="shadow", amount=1.0, at_age=60, engine=None)
    with pytest.raises(PremiumTargetError):        # past maturity
        solve_premium_to_target(
            _policy(), target="av", amount=1.0, at_age=140, engine=None)
    with pytest.raises(PremiumTargetError):        # before the premium starts
        solve_premium_to_target(
            _policy(), target="av", amount=1.0, at_age=52,
            start_policy_year=10, engine=None)
    with pytest.raises(PremiumTargetError):        # no amount
        solve_premium_to_target(
            _policy(), target="av", amount=None, at_age=60, engine=None)


# ── Real engine: flat rates, exact arithmetic ────────────────────────────────

class _FlatRatesEngine(IllustrationEngine):
    def _load_rates(self, policy, config):
        return IllustrationRates()


def _test_config(_plancode) -> PlancodeConfig:
    return PlancodeConfig(
        plancode="TEST", interest_method="ExactDays", gint=0.0, dbd=0.0,
        premium_load="0", prem_flat_load=0.0, epu_code="0", mfee="0",
        poav_code="0", bonus="0", corridor_code=None, snet_period=0,
        maturity_age=121, loan_type="Arrears")


@pytest.fixture
def _flat_plancode(monkeypatch):
    from suiteview.illustration.core import calc_engine
    monkeypatch.setattr(calc_engine, "load_plancode", _test_config)
    monkeypatch.setattr(
        calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())


def _flat_policy() -> IllustrationPolicyData:
    # Huge guideline room so the cap never binds — with no charges and 0%
    # interest the ending AV is exactly 5,000 + premiums paid.
    return IllustrationPolicyData(
        plancode="TEST", def_of_life_ins="GPT",
        issue_date=date(2026, 1, 15), valuation_date=date(2026, 1, 15),
        issue_age=40, attained_age=40, maturity_age=121,
        policy_year=1, policy_month=1, duration=1,
        face_amount=100_000.0, units=100.0, db_option="A",
        account_value=5_000.0, modal_premium=100.0, billing_frequency=1,
        glp=1e9, gsp=1e9, accumulated_glp=1e9, current_interest_rate=0.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2026, 1, 15),
                                  face_amount=100_000.0, units=100.0)],
    )


def test_real_engine_av_target_matches_premium_arithmetic(_flat_plancode):
    # Payments run monthly from month 2 of year 1 through year 10: 119
    # payments by the age-50 checkpoint (end of year 10). AV target 20,000
    # needs 15,000 of premium → 15,000 / 119 = 126.06 (rounded up to the
    # cent that meets the target).
    result = solve_premium_to_target(
        _flat_policy(), target="av", amount=20_000.0, at_age=50,
        mode="M", start_policy_year=1, engine=_FlatRatesEngine())

    assert result.premium == pytest.approx(15_000.0 / 119.0, abs=0.02)
    assert result.achieved_value >= 20_000.0 - 0.005


def test_real_engine_sv_target_equals_av_on_a_chargeless_policy(_flat_plancode):
    # No surrender charge and no loans → ending SV == ending AV, so the SV
    # solve lands on the same premium.
    av = solve_premium_to_target(
        _flat_policy(), target="av", amount=20_000.0, at_age=50,
        mode="M", start_policy_year=1, engine=_FlatRatesEngine())
    sv = solve_premium_to_target(
        _flat_policy(), target="sv", amount=20_000.0, at_age=50,
        mode="M", start_policy_year=1, engine=_FlatRatesEngine())
    assert sv.premium == pytest.approx(av.premium, abs=0.02)


def test_real_engine_premium_stops_at_the_row_span(_flat_plancode):
    # The same target with the premium stopping after year 5 (end_policy_year)
    # needs a HIGHER premium — fewer payments (59) fund the same 15,000.
    result = solve_premium_to_target(
        _flat_policy(), target="av", amount=20_000.0, at_age=50,
        mode="M", start_policy_year=1, end_policy_year=5,
        engine=_FlatRatesEngine())
    assert result.premium == pytest.approx(15_000.0 / 59.0, abs=0.05)
