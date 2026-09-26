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
        def project(
            self, _policy, months=None, future_inputs=None, timing=None,
            stop_on_lapse=True, options=None, bonus_override=None,
            rates_override=None,
        ):
            return states

    monkeypatch.setattr(gea, "IllustrationEngine", FakeEngine)

    monkeypatch.setattr(
        gea, "solve_level_to_exception",
        lambda *_a, **_k: SimpleNamespace(premium=500.0, mode="M"),
    )


def _ill_policy():
    return IllustrationPolicyData(
        policy_number="GEA001",
        issue_date=date(2020, 5, 1),
        issue_age=45,
        valuation_date=date(2026, 5, 1),
        policy_year=7,
        duration=73,
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


def test_later_premiums_do_not_change_valuation_date_room(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _rich_states(date(2026, 6, 1), 11, 500.0, target, 9_999.0)
    _stub_dependencies(monkeypatch, ill_policy, states)

    # A later receipt cannot change a quote's valuation-date opening balances.
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
    summary = gea.project_guideline_exception_target_forecast(source, target).zero_glp.summary

    assert summary.premiums_paid_to_date == 0.0
    assert summary.room_available == 8_000.0
    assert summary.adjustment_to_accum_glp == 0.0


def test_target_before_valuation_raises(monkeypatch):
    ill_policy = _ill_policy()
    states = _rich_states(date(2026, 6, 1), 1, 0.0, date(2026, 6, 1), 0.0)
    _stub_dependencies(monkeypatch, ill_policy, states)
    source = _source_policy(1.0, 0.0, 0.0)

    import pytest

    with pytest.raises(ValueError):
        gea.project_guideline_exception_target_forecast(source, date(2026, 4, 1))


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
            applied_lumpsum=0.0,
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
        applied_lumpsum=0.0,
        premiums_to_date_after_exception=outlay * count + target_outlay,
        withdrawals_to_date=0.0,
        policy_debt=0.0,
    ))
    return states


def test_forecast_rows_exclude_target_and_summary_matches(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    # 11 monthly states before target at 500 each = 5,500, plus a target-date
    # state at 9,999 that must be excluded from the forecast and premium sum.
    states = _rich_states(date(2026, 6, 1), 11, 500.0, target, 9_999.0)
    _stub_dependencies(monkeypatch, ill_policy, states)

    source = _source_policy(3_500.0, 0.0, 0.0)
    result = gea.project_guideline_exception_target_forecast(source, target).zero_glp

    assert len(result.rows) == 11
    assert result.rows[-1].date < target
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
    result = gea.project_guideline_exception_target_forecast(source, target).zero_glp

    assert result.summary.adjustment_to_accum_glp == 0.0
    assert result.summary.message == "No adjustment needed"
    assert len(result.rows) == 11


def test_adjustment_includes_existing_excess_above_accum_glp():
    summary = gea._summarize(
        _source_policy(1_000.0, 1_200.0, 100.0),
        date(2026, 5, 1), date(2027, 5, 1), 11,
        200.0,
    )
    assert summary.room_available == 0.0
    assert summary.adjustment_to_accum_glp == 300.0
    assert summary.new_accum_glp == 1_300.0


def test_forecast_rows_include_guideline_force_out(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _rich_states(date(2026, 6, 1), 11, 0.0, target, 0.0)
    states[3].guideline_forceout = 123.45
    _stub_dependencies(monkeypatch, ill_policy, states)

    result = gea.project_guideline_exception_target_forecast(
        _source_policy(6_000.0, 0.0, 0.0), target).zero_glp

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
            applied_lumpsum=lump if i == 0 else 0.0,
            premiums_to_date_after_exception=prem_td,
            withdrawals_to_date=withdrawals, policy_debt=0.0))
        when = when + relativedelta(months=1)
    states.append(SimpleNamespace(
        date=target, premium_outlay=9_999.0, policy_year=8, policy_month=1,
        interest_credited=0.0, total_deduction=40.0, av_end_of_month=1.0,
        glp=100.0, accumulated_glp=accum_glp,
        applied_lumpsum=0.0,
        premiums_to_date_after_exception=prem_td + 9_999.0,
        withdrawals_to_date=withdrawals, policy_debt=0.0))
    return states


def _stub_min_prem_to_target(monkeypatch, ill_policy, states, premium=321.0):
    """Stub the solve and record the kwargs it was called with."""
    _stub_dependencies(monkeypatch, ill_policy, states)
    calls = []

    def fake_solve(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(premium=premium, mode="M")

    monkeypatch.setattr(gea, "solve_level_to_exception", fake_solve)
    return calls


def test_solve_horizon_is_the_target_date_not_maturity(monkeypatch):
    """The solve must stop at the target date.

    A maturity solve would demand premium the policy does not need by the target
    and so could wrongly report that the AccumGLP has to be opened up.
    """
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _solve_states(date(2026, 6, 1), 11, target,
                           monthly_outlay=0.0, accum_glp=9_000.0)
    calls = _stub_min_prem_to_target(monkeypatch, ill_policy, states, premium=0.0)

    gea.project_guideline_exception_target_forecast(
        _source_policy(9_000.0, 0.0, 0.0), target)

    # valuation 2026-05-01 → target 2027-05-01 is 11 deductions strictly before.
    assert calls and calls[0]["horizon_months"] == 11


def test_zero_solved_premium_explicitly_overrides_billing(monkeypatch):
    """A $0 minimum means the account value alone carries the policy.

    A zero premium transaction must override the policy's billed premium.
    """
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _solve_states(date(2026, 6, 1), 11, target,
                           monthly_outlay=0.0, accum_glp=9_000.0)
    _stub_min_prem_to_target(monkeypatch, ill_policy, states, premium=0.0)

    captured = {}

    class CapturingEngine:
        def project(
            self, _policy, months=None, future_inputs=None, timing=None,
            stop_on_lapse=True, options=None, bonus_override=None,
            rates_override=None,
        ):
            captured["future_inputs"] = future_inputs
            return states

    monkeypatch.setattr(gea, "IllustrationEngine", CapturingEngine)

    result = gea.project_guideline_exception_target_forecast(
        _source_policy(9_000.0, 0.0, 0.0), target)

    assert result.premium == 0.0
    scheduled = captured["future_inputs"].scheduled_transactions
    assert len(scheduled) == 1
    assert scheduled[0].amount == 0.0
    assert result.exception_start is None
    assert result.zero_glp.premium == 0.0


def test_positive_solved_premium_schedules_a_premium_row(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _solve_states(date(2026, 6, 1), 11, target,
                           monthly_outlay=100.0, accum_glp=9_000.0)
    _stub_min_prem_to_target(monkeypatch, ill_policy, states, premium=250.0)

    captured = {}

    class CapturingEngine:
        def project(
            self, _policy, months=None, future_inputs=None, timing=None,
            stop_on_lapse=True, options=None, bonus_override=None,
            rates_override=None,
        ):
            captured["future_inputs"] = future_inputs
            return states

    monkeypatch.setattr(gea, "IllustrationEngine", CapturingEngine)

    gea.project_guideline_exception_target_forecast(
        _source_policy(9_000.0, 0.0, 0.0), target)

    scheduled = captured["future_inputs"].scheduled_transactions
    assert len(scheduled) == 1
    assert scheduled[0].amount == 250.0
    assert scheduled[0].mode == "M"


def test_min_prem_to_target_shows_values_and_runs_zero_glp_after_exception(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _solve_states(date(2026, 6, 1), 11, target,
                           monthly_outlay=500.0, accum_glp=3_500.0)
    states[4].exception_prem_mode = True
    states[4].gp_exception_prem = 75.0
    _stub_min_prem_to_target(monkeypatch, ill_policy, states, premium=321.0)

    result = gea.project_guideline_exception_target_forecast(
        _source_policy(3_500.0, 0.0, 0.0), target)

    assert result.premium == 321.0
    assert result.premium_mode == "M"
    assert result.exception_start == date(2026, 10, 1)
    assert result.exception_before_target is True
    assert result.zero_glp.premium == 321.0
    assert result.rows[4].in_exception_mode is True
    assert result.rows[4].exception_premium == 75.0
    assert len(result.rows) == 11


def test_min_prem_to_target_runs_zero_glp_without_exception_before_target(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _solve_states(date(2026, 6, 1), 11, target,
                           monthly_outlay=100.0, accum_glp=9_000.0)
    _stub_min_prem_to_target(monkeypatch, ill_policy, states)

    result = gea.project_guideline_exception_target_forecast(
        _source_policy(9_000.0, 0.0, 0.0), target)

    assert result.exception_start is None
    assert result.exception_before_target is False
    assert result.zero_glp.rows


def test_min_prem_to_target_runs_zero_glp_when_exception_is_on_target(monkeypatch):
    ill_policy = _ill_policy()
    target = date(2027, 5, 1)
    states = _solve_states(date(2026, 6, 1), 11, target,
                           monthly_outlay=100.0, accum_glp=9_000.0)
    states[-1].exception_prem_mode = True
    _stub_min_prem_to_target(monkeypatch, ill_policy, states)

    result = gea.project_guideline_exception_target_forecast(
        _source_policy(9_000.0, 0.0, 0.0), target)

    assert result.exception_start is None
    assert result.exception_before_target is False
    assert result.zero_glp.rows


def test_min_prem_to_target_options_enable_exception_premiums():
    options = gea.level_to_exception_options(
        None, allow_exceptions=True, conform_to_tamra=False)

    assert options.conform_to_tefra is True
    assert options.allow_exception_prems is True
    assert options.conform_to_tamra is False


def test_all_solves_preserve_targets_and_count_premium_without_loan_repayment(monkeypatch):
    from suiteview.illustration.models.calc_state import MonthlyState

    ill_policy = _ill_policy()
    ill_policy.glp = 1200.0
    ill_policy.gsp = 5000.0
    ill_policy.accumulated_glp = ill_policy.premiums_paid_to_date = 9000.0
    ill_policy.withdrawals_to_date = 100.0
    target = date(2027, 5, 1)
    _stub_dependencies(monkeypatch, ill_policy, [])
    solves, projections = [], []

    def solve(policy, **kwargs):
        solves.append((policy.glp, policy.gsp, policy.accumulated_glp,
                       policy.premiums_paid_to_date, policy.withdrawals_to_date, kwargs))
        premium = 10.0 if policy.glp else (
            20.0 if kwargs["base_options"].force_out_enabled else 30.0)
        return SimpleNamespace(premium=premium, mode="Q")

    class Engine:
        def project(
            self, policy, months=None, future_inputs=None, timing=None,
            stop_on_lapse=True, options=None, bonus_override=None,
            rates_override=None,
        ):
            projections.append((policy.glp, options, months))
            tx = future_inputs.scheduled_transactions[0]
            assert tx.amount == (10.0 if policy.glp else (
                20.0 if options.force_out_enabled else 30.0))
            assert tx.mode == "Q"
            assert not future_inputs.dated_transactions
            return [
                MonthlyState(
                    date=date(2026, 6, 1) + relativedelta(months=i),
                    gross_premium=tx.amount, gp_exception_prem=5.0,
                    applied_loan_repayment=100.0, applied_regular_loan=50.0,
                    guideline_forceout=2.0, withdrawals_to_date=100 + 2 * (i + 1),
                ) for i in range(12)
            ]

    monkeypatch.setattr(gea, "solve_level_to_exception", solve)
    monkeypatch.setattr(gea, "IllustrationEngine", Engine)
    result = gea.project_guideline_exception_target_forecast(
        _source_policy(9000.0, 9000.0, 100.0), target)
    assert [call[:5] for call in solves] == [
        (1200.0, 5000.0, 9000.0, 9000.0, 100.0),
        (0.0, 5000.0, 9000.0, 9000.0, 100.0),
        (0.0, 5000.0, 9000.0, 9000.0, 100.0),
    ]
    assert all(call[5]["allow_exceptions"] and call[5]["conform_to_tamra"]
               and call[5]["horizon_months"] == 11
               and call[5]["fund_transition_cleanly"] is False for call in solves)
    assert all(opts.conform_to_tefra and opts.conform_to_tamra
               and opts.guideline_cap_enabled and opts.tamra_cap_enabled
               and opts.allow_exception_prems and not opts.billable_to_md_windows
               and months == 11 for _, opts, months in projections)
    assert [call[5]["base_options"].force_out_enabled for call in solves] == [True, True, False]
    assert [opts.force_out_enabled for _, opts, _ in projections] == [True, True, False]
    assert result.no_forceout.premium == 30.0
    assert result.no_forceout.summary.total_premium_needed == 11 * (30 + 5)
    assert result.zero_glp.summary.total_premium_needed == 11 * (20 + 5)
    assert result.zero_glp.summary.adjustment_to_accum_glp == 175.0
    assert len(result.rows) == len(result.zero_glp.rows) == 11
    assert ill_policy.glp == 1200.0
