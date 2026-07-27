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


def _source_policy(accum_glp, premium_td, withdrawals):
    return SimpleNamespace(
        accumulated_glp_target=accum_glp,
        premium_td=premium_td,
        total_withdrawals=withdrawals,
        fetch_table=lambda _name: [],   # no post-valuation premiums
    )


def test_premiums_since_valuation_reduce_room(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _rich_states(date(2026, 6, 1), 11, 500.0, target, 9_999.0)
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
    summary = gea.project_guideline_exception_forecast(source, target).summary

    assert summary.premiums_since_valuation_date == 2_000.0
    assert summary.premiums_paid_to_date == 2_000.0
    assert summary.room_available == 6_000.0
    assert summary.adjustment_to_accum_glp == 0.0     # 5,500 <= 6,000


def test_target_before_valuation_raises(monkeypatch):
    ill_policy = _ill_policy()
    states = _rich_states(date(2026, 6, 1), 1, 0.0, date(2026, 6, 1), 0.0)
    _stub_dependencies(monkeypatch, ill_policy, states)
    source = _source_policy(1.0, 0.0, 0.0)

    import pytest

    with pytest.raises(ValueError):
        gea.project_guideline_exception_forecast(source, date(2026, 4, 1))


def _rich_states(start: date, count: int, outlay: float, target: date, target_outlay: float):
    """Monthly states with the full field set the forecast rows display, plus a
    state ON the target date (excluded from the premium sum, shown in the table)."""
    states = []
    when = start
    for i in range(count):
        states.append(SimpleNamespace(
            date=when,
            premium_outlay=outlay,
            policy_year=7,
            policy_month=i + 1,
            interest_credited=1.5 * i,
            total_deduction=40.0,
            av_end_of_month=100.0 - i,
            glp=1000.0,
            accumulated_glp=8000.0,
            premiums_to_date_after_exception=outlay * (i + 1),
            withdrawals_to_date=0.0,
            policy_debt=0.0,
        ))
        when = when + relativedelta(months=1)
    states.append(SimpleNamespace(
        date=target,
        premium_outlay=target_outlay,
        policy_year=8,
        policy_month=1,
        interest_credited=0.0,
        total_deduction=40.0,
        av_end_of_month=50.0,
        glp=1000.0,
        accumulated_glp=8000.0,
        premiums_to_date_after_exception=outlay * count + target_outlay,
        withdrawals_to_date=0.0,
        policy_debt=0.0,
    ))
    return states


def test_forecast_rows_include_target_and_summary_matches(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    # 11 monthly states before target at 500 each = 5,500, plus a target-date
    # state at 9,999 that is shown but excluded from the premium sum.
    states = _rich_states(date(2026, 6, 1), 11, 500.0, target, 9_999.0)
    _stub_dependencies(monkeypatch, ill_policy, states)

    source = _source_policy(3_500.0, 0.0, 0.0)
    result = gea.project_guideline_exception_forecast(source, target)

    # Display includes every state up to AND including the target date.
    assert len(result.rows) == 12
    assert result.rows[-1].date == target
    assert result.rows[0].premium == 500.0
    assert result.rows[0].glp == 1000.0
    assert result.rows[0].accumulated_glp == 8000.0

    # Summary uses the same math as the solve; the target-date premium is excluded.
    summary = result.summary
    assert summary.total_premium_needed == 5_500.0
    assert summary.room_available == 3_500.0
    assert summary.adjustment_to_accum_glp == 2_000.0
    assert summary.premiums_to_date_on_target == 5_500.0  # premiums_paid 0 + 5,500


def test_forecast_no_adjustment_when_room_covers(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _rich_states(date(2026, 6, 1), 11, 500.0, target, 9_999.0)
    _stub_dependencies(monkeypatch, ill_policy, states)

    source = _source_policy(6_000.0, 0.0, 0.0)
    result = gea.project_guideline_exception_forecast(source, target)

    assert result.summary.adjustment_to_accum_glp == 0.0
    assert result.summary.message == "No adjustment needed"
    assert len(result.rows) == 12


def test_forecast_rows_include_guideline_force_out(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _rich_states(date(2026, 6, 1), 11, 0.0, target, 0.0)
    states[3].guideline_forceout = 123.45
    _stub_dependencies(monkeypatch, ill_policy, states)

    result = gea.project_guideline_exception_forecast(
        _source_policy(6_000.0, 0.0, 0.0), target)

    assert result.rows[3].force_out == 123.45


def _solve_states(start, count, target, *, monthly_outlay=0.0, lump=0.0,
                  accum_glp=0.0, withdrawals=0.0):
    """Projected states for a solved run: `count` months from `start` (each
    paying `monthly_outlay`, plus `lump` on the first), a hard-set AccumGLP /
    AccumWD on every row (the dual summary reads them off the used row), and an
    excluded state ON the target date."""
    states = []
    when = start
    prem_td = 0.0
    for i in range(count):
        outlay = monthly_outlay + (lump if i == 0 else 0.0)
        prem_td += outlay
        states.append(SimpleNamespace(
            date=when, premium_outlay=outlay, policy_year=7, policy_month=i + 1,
            interest_credited=0.0, total_deduction=40.0, av_end_of_month=1.0,
            glp=100.0, accumulated_glp=accum_glp,
            premiums_to_date_after_exception=prem_td,
            withdrawals_to_date=withdrawals, policy_debt=0.0))
        when = when + relativedelta(months=1)
    states.append(SimpleNamespace(
        date=target, premium_outlay=9_999.0, policy_year=8, policy_month=1,
        interest_credited=0.0, total_deduction=40.0, av_end_of_month=1.0,
        glp=100.0, accumulated_glp=accum_glp,
        premiums_to_date_after_exception=prem_td + 9_999.0,
        withdrawals_to_date=withdrawals, policy_debt=0.0))
    return states


def _stub_prem_to_maturity(monkeypatch, ill_policy, states, premium=321.0):
    _stub_dependencies(monkeypatch, ill_policy, states)
    monkeypatch.setattr(
        gea,
        "solve_level_to_exception",
        lambda *_args, **_kwargs: SimpleNamespace(premium=premium, mode="M"),
    )


def test_prem_to_maturity_shows_values_and_runs_zero_md_after_exception(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _solve_states(date(2026, 6, 1), 11, target,
                           monthly_outlay=500.0, accum_glp=3_500.0)
    states[4].exception_prem_mode = True
    states[4].gp_exception_prem = 75.0
    _stub_prem_to_maturity(monkeypatch, ill_policy, states, premium=321.0)

    result = gea.project_guideline_exception_maturity_forecast(
        _source_policy(3_500.0, 0.0, 0.0), target)

    assert result.premium == 321.0
    assert result.premium_mode == "M"
    assert result.exception_start == date(2026, 10, 1)
    assert result.exception_before_target is True
    assert result.zero_md is not None
    assert result.rows[4].in_exception_mode is True
    assert result.rows[4].exception_premium == 75.0
    assert len(result.rows) == 12


def test_prem_to_maturity_skips_zero_md_without_exception_before_target(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _solve_states(date(2026, 6, 1), 11, target,
                           monthly_outlay=100.0, accum_glp=9_000.0)
    _stub_prem_to_maturity(monkeypatch, ill_policy, states)

    result = gea.project_guideline_exception_maturity_forecast(
        _source_policy(9_000.0, 0.0, 0.0), target)

    assert result.exception_start is None
    assert result.exception_before_target is False
    assert result.zero_md is None


def test_prem_to_maturity_skips_zero_md_when_exception_is_on_target(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _solve_states(date(2026, 6, 1), 11, target,
                           monthly_outlay=100.0, accum_glp=9_000.0)
    states[-1].exception_prem_mode = True
    _stub_prem_to_maturity(monkeypatch, ill_policy, states)

    result = gea.project_guideline_exception_maturity_forecast(
        _source_policy(9_000.0, 0.0, 0.0), target)

    assert result.exception_start == target
    assert result.exception_before_target is False
    assert result.zero_md is None


def test_prem_to_maturity_options_enable_exception_premiums():
    options = gea.level_to_exception_options(
        None, allow_exceptions=True, conform_to_tamra=False)

    assert options.conform_to_tefra is True
    assert options.allow_exception_prems is True
    assert options.conform_to_tamra is False
