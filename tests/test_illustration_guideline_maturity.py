"""Guideline calculations and their PV detail stop at min(policy maturity, 100)."""
from copy import deepcopy
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine, rate_loader
from suiteview.illustration.core.guideline_calc import (
    calculate_glp_iterative, policy_to_guideline_inputs, search_guideline_premiums,
)
from suiteview.illustration.core.guideline_pv import (
    guideline_7pay_detail, guideline_glp_detail, guideline_gsp_detail,
)
from suiteview.illustration.core.monthly_guideline import (
    build_guideline_basis, solve_guideline_premiums,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


def _policy(maturity):
    return IllustrationPolicyData(
        plancode="MATURITY", issue_date=date(2000, 6, 1), issue_age=40,
        face_amount=12000, units=12, db_option="A", maturity_age=maturity,
        current_interest_rate=0.0, glp=1000,
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(2000, 6, 1), issue_age=40,
            face_amount=12000, units=12,
        )],
    )


def _config(maturity=121):
    return PlancodeConfig(
        plancode="MATURITY", maturity_age=maturity, premium_load="0",
        epu_code="0", mfee="0", poav_code="0", corridor_code=None, snet_period=0,
    )


@pytest.mark.parametrize("maturity", [95, 100, 121])
@pytest.mark.parametrize("months_into_year", [0, 1, 11])
def test_monthly_horizon_and_all_pv_endowments_use_policy_maturity(maturity, months_into_year):
    policy = _policy(maturity)
    basis = build_guideline_basis(
        policy, _config(), IllustrationRates(), attained_age=90,
        as_of=date(2050, 6, 1), months_into_year=months_into_year,
    )
    end_age = min(maturity, 100)
    months = (end_age - 90) * 12 - months_into_year
    assert len(basis.months) == months
    assert basis.months[-1].attained_age == end_age - 1
    solved = solve_guideline_premiums(basis)
    expected_glp = policy.total_face / sum(
        1.04 ** ((months - index) / 12)
        for index, month in enumerate(basis.months) if month.is_anniversary
    )
    assert solved.glp == pytest.approx(expected_glp)
    for detail_builder, premium in (
        (guideline_glp_detail, solved.glp),
        (guideline_gsp_detail, solved.gsp),
        (guideline_7pay_detail, solved.seven_pay),
    ):
        detail = detail_builder(basis)
        assert detail["glp_rollup"]["months"] == months
        assert detail["glp_rows"][-1]["_endowment"]
        assert detail["glp_rows"][-1]["Age"] == end_age
        assert len(detail["glp_rows"]) == months + 1
        assert detail["glp_rollup"]["premium"] == pytest.approx(premium, abs=0.005)


@pytest.mark.parametrize("age", [95, 96, 100])
def test_monthly_basis_has_no_charge_months_at_or_after_policy_maturity(age):
    basis = build_guideline_basis(
        _policy(95), _config(), IllustrationRates(), attained_age=age,
    )
    assert basis.months == []
    assert solve_guideline_premiums(basis).glp == 0


@pytest.mark.parametrize("maturity", [95, 100, 121])
def test_engine_recalc_and_before_after_detail_share_maturity_bound(monkeypatch, maturity):
    policy = _policy(maturity)
    config = _config()
    monkeypatch.setattr(calc_engine, "load_rates", lambda *a, **kw: IllustrationRates())
    change_date = date(2050, 7, 1)
    expected_months = (min(maturity, 100) - 90) * 12 - 1
    solved = calc_engine._solve_guideline_state(
        policy, config, 90, change_date, IllustrationOptions(),
    )
    detail = calc_engine._safe_guideline_pv_recalc_detail(policy, config, 90, change_date)
    assert detail["glp"]["glp_rollup"]["months"] == expected_months
    assert detail["glp"]["glp_rollup"]["premium"] == pytest.approx(solved.glp, abs=0.005)
    assert detail["gsp"]["glp_rows"][-1]["Age"] == min(maturity, 100)


@pytest.mark.parametrize("maturity,requested,expected", [(95, 100, 95), (121, 100, 100), (95, 90, 90), (121, 121, 100)])
def test_policy_derived_commutation_caps_requested_endowment(monkeypatch, maturity, requested, expected):
    monkeypatch.setattr(
        rate_loader, "load_rates", lambda *a, **kw: IllustrationRates(segment_coi={1: [None] + [0.0] * 81}),
    )
    inputs = policy_to_guideline_inputs(
        _policy(maturity), _config(), 80, endowment_age=requested,
    )
    assert inputs.endowment_age == expected
    assert inputs.years_to_maturity() == expected - 80


@pytest.mark.parametrize("maturity", [95, 100, 121])
def test_search_reaches_exact_bounded_endowment_month_using_real_engine(monkeypatch, maturity):
    end_age = min(maturity, 100)
    policy = _policy(maturity)
    config = _config(maturity)
    start_age = end_age - 1
    calc_date = date(2000 + start_age - 40, 6, 1)
    original = deepcopy(policy)
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    project = calc_engine.IllustrationEngine.project
    runs = []

    def capture(self, trial, **kwargs):
        results = project(self, trial, **kwargs)
        runs.append((kwargs["months"], results[-1].date, results[-1].attained_age, len(results)))
        return results

    monkeypatch.setattr(calc_engine.IllustrationEngine, "project", capture)
    result = search_guideline_premiums(
        policy, config, IllustrationRates(), attained_age=start_age, as_of=calc_date,
    )
    assert runs
    assert set(runs) == {(12, date(calc_date.year + 1, 5, 1), end_age - 1, 13)}
    assert result.glp == pytest.approx(policy.total_face / 1.04, abs=0.01)
    assert result.gsp == pytest.approx(policy.total_face / 1.06, abs=0.01)
    assert result.seven_pay == pytest.approx(result.glp, abs=0.01)
    assert policy == original


def test_standalone_iterative_helper_requests_policy_bounded_months(monkeypatch):
    from suiteview.illustration.models.calc_state import MonthlyState

    policy = _policy(95)
    policy.attained_age = 90
    observed = []

    def project(self, trial, **kwargs):
        observed.append(kwargs["months"])
        premium = kwargs["future_inputs"].scheduled_transactions[0].amount
        return [MonthlyState(av_end_of_month=premium * 10)]

    monkeypatch.setattr(calc_engine.IllustrationEngine, "project", project)
    result = calculate_glp_iterative(policy, IllustrationRates())
    assert result.converged
    assert set(observed) == {60}
