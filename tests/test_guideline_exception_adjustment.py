from datetime import date
from types import SimpleNamespace

from dateutil.relativedelta import relativedelta

from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.polview.services import glp_exception
from suiteview.polview.services import guideline_exception_adjustment as gea


def _stub_dependencies(monkeypatch, ill_policy, states):
    """Wire the service's collaborators to deterministic fakes."""
    monkeypatch.setattr(
        gea,
        "check_forecast_availability",
        lambda _policy: glp_exception.GlpForecastAvailability(True, "available", ill_policy),
    )

    class FakeEngine:
        def project(self, _policy, options=None, future_inputs=None,
                    months=None, stop_on_lapse=True, **_kw):
            return states

    monkeypatch.setattr(gea, "IllustrationEngine", FakeEngine)

    # Skip the lumpsum-to-next bridge (imported inside the service function) so
    # the test isolates the premium-sum + room math.
    monkeypatch.setattr(
        "suiteview.illustration.core.solve_lumpsum_to_next_premium."
        "solve_lumpsum_to_next_premium",
        lambda *_a, **_k: None,
    )


def _ill_policy():
    return IllustrationPolicyData(
        policy_number="GEA001",
        issue_date=date(2020, 5, 1),
        issue_age=45,
        valuation_date=date(2026, 5, 1),
        policy_year=7,
        duration=72,
        maturity_age=121,
        account_value=1_000.0,
        premiums_paid_to_date=0.0,
        withdrawals_to_date=0.0,
        accumulated_glp=0.0,
    )


def _states(start: date, count: int, outlay: float, target_outlay: float, target: date):
    """`count` monthly states from `start`, each paying `outlay`, plus one state
    ON the target date paying `target_outlay` (which must be excluded)."""
    states = []
    when = start
    for _ in range(count):
        states.append(SimpleNamespace(date=when, premium_outlay=outlay))
        when = when + relativedelta(months=1)
    states.append(SimpleNamespace(date=target, premium_outlay=target_outlay))
    return states


def _source_policy(accum_glp, premium_td, withdrawals):
    return SimpleNamespace(
        accumulated_glp_target=accum_glp,
        premium_td=premium_td,
        total_withdrawals=withdrawals,
        fetch_table=lambda _name: [],   # no post-valuation premiums
    )


def test_adjustment_needed_when_premium_exceeds_room(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    # 11 monthly states before target (2026-06 .. 2027-04) at 500 each = 5,500,
    # plus a 9,999 state ON the target date that must be excluded.
    states = _states(date(2026, 6, 1), 11, 500.0, 9_999.0, target)
    _stub_dependencies(monkeypatch, ill_policy, states)

    # AccumGLP 3,500, no premiums paid, no withdrawals -> room 3,500.
    source = _source_policy(3_500.0, 0.0, 0.0)
    result = gea.solve_guideline_exception_adjustment(source, target)

    assert result.total_premium_needed == 5_500.0     # target-date state excluded
    assert result.room_available == 3_500.0
    assert result.adjustment_to_accum_glp == 2_000.0  # 5,500 - 3,500
    assert result.new_accum_glp == 5_500.0
    assert "Increase AccumGLP" in result.message


def test_no_adjustment_when_room_covers_premium(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _states(date(2026, 6, 1), 11, 500.0, 9_999.0, target)
    _stub_dependencies(monkeypatch, ill_policy, states)

    # Room 6,000 comfortably covers the 5,500 needed.
    source = _source_policy(6_000.0, 0.0, 0.0)
    result = gea.solve_guideline_exception_adjustment(source, target)

    assert result.total_premium_needed == 5_500.0
    assert result.room_available == 6_000.0
    assert result.adjustment_to_accum_glp == 0.0
    assert result.message == "No adjustment needed"


def test_premiums_since_valuation_reduce_room(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _states(date(2026, 6, 1), 11, 500.0, 9_999.0, target)
    _stub_dependencies(monkeypatch, ill_policy, states)

    # 2,000 of premium paid AFTER the valuation date raises premiums-paid and so
    # shrinks the room: room = max(0, 8,000 - (0 + 2,000)) = 6,000.
    source = SimpleNamespace(
        accumulated_glp_target=8_000.0,
        premium_td=0.0,
        total_withdrawals=0.0,
        fetch_table=lambda name: (
            [{
                "ASOF_DT": "2026-08-01",
                "TRN_TYP_CD": "PR",
                "GROSS_AMT": "2000",
                "NET_AMT": "1900",
            }] if name == "FH_FIXED" else []
        ),
    )
    result = gea.solve_guideline_exception_adjustment(source, target)

    assert result.premiums_since_valuation_date == 2_000.0
    assert result.premiums_paid_to_date == 2_000.0
    assert result.room_available == 6_000.0
    assert result.adjustment_to_accum_glp == 0.0     # 5,500 <= 6,000


def test_target_before_valuation_raises(monkeypatch):
    ill_policy = _ill_policy()
    states = _states(date(2026, 6, 1), 1, 0.0, 0.0, date(2026, 6, 1))
    _stub_dependencies(monkeypatch, ill_policy, states)
    source = _source_policy(1.0, 0.0, 0.0)

    import pytest

    with pytest.raises(ValueError):
        gea.solve_guideline_exception_adjustment(source, date(2026, 4, 1))
