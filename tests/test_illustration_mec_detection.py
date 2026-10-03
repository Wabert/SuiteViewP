"""Monthly MEC detection uses the seven-pay anniversary, not the policy anniversary."""
from copy import deepcopy
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine, guaranteed_projection
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.compare_runner import _mec_status
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.report_builder import _annualize
from suiteview.illustration.models.input_set import (
    DatedTransaction, IllustrationInputSet, IllustrationOptions,
    PolicyChangeEvent, PolicyChangeKind, ScheduledTransaction, TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.illustration.ui.values_overview import _status_text


@pytest.fixture
def basis(monkeypatch):
    config = PlancodeConfig(
        plancode="MECTEST",
    )
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    monkeypatch.setattr(guaranteed_projection, "load_plancode", lambda _: config)
    monkeypatch.setattr(
        guaranteed_projection, "load_rates", lambda *args, **kwargs: IllustrationRates())
    policy = IllustrationPolicyData(
        plancode="MECTEST", issue_date=date(2000, 9, 1),
        valuation_date=date(2026, 10, 1), duration=314,
        policy_year=27, policy_month=2, issue_age=40, attained_age=66,
        maturity_age=95, face_amount=110000, units=110, db_option="A",
        account_value=20000, current_interest_rate=0, glp=100000,
        tamra_7pay_start_date=date(2026, 10, 1), tamra_7pay_level=10897.44,
        tamra_7year_contributions=[10897.44, 0, 0, 0, 0, 0, 0],
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(2000, 9, 1),
            face_amount=110000, units=110,
        )],
    )
    inputs = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(TransactionKind.PREMIUM, 1, 0, "A"),
        ScheduledTransaction(TransactionKind.PREMIUM, 28, 10897.44, "A"),
    ])
    return policy, inputs


def _project(policy, inputs, *, conform=False, months=12,
             timing=calc_engine.ProjectionTiming.ILLUSTRATION):
    options = IllustrationOptions(conform_to_tamra=conform, conform_to_tefra=False)
    results = calc_engine.IllustrationEngine().project(
        policy, future_inputs=inputs, months=months, options=options, timing=timing,
        rates_override=IllustrationRates(), bonus_override=BonusConfig(),
    )
    return results, options


@pytest.mark.parametrize("timing", list(calc_engine.ProjectionTiming))
@pytest.mark.parametrize("conform", [False, True])
def test_off_cycle_seven_pay_year_detects_mec_or_caps_premium(basis, timing, conform):
    policy, inputs = basis
    original = deepcopy(policy)
    results, options = _project(policy, inputs, timing=timing, conform=conform)
    september = next(s for s in results if s.date == date(2027, 9, 1))
    october = results[-1]

    assert september.policy_year == 28
    assert september.tamra_year == 1
    assert september.tamra_7pay_start_date == date(2026, 10, 1)
    assert october.tamra_year == 2
    assert all(not s.is_mec for s in results if s.date < september.date)
    if conform:
        assert september.gross_premium == 0
        assert september.premium_capped_by_tamra
        assert not any(s.is_mec for s in results)
        assert _mec_status(policy, results[1:]) == "Not a MEC"
    else:
        assert september.gross_premium == 10897.44
        assert september.accumulated_7pay == 21794.88
        assert september.is_mec
        assert september.mec_year == 28
        assert october.accumulated_7pay == october.tamra_year * october.tamra_7pay_level
        assert october.is_mec and october.mec_year == 28
        assert "MEC" in _status_text(september)
        assert _mec_status(policy, results[1:]) == "Becomes MEC (Yr 28)"
        ledger, year, _ = _annualize(policy, results, options)
        assert year == 28
        assert "&" in next(r.markers for r in ledger if r.year == 28)
    assert policy == original
    assert not policy.is_mec
    if timing == calc_engine.ProjectionTiming.ILLUSTRATION:
        guaranteed = guaranteed_projection.run_guaranteed_projection(
            policy, results, base_options=options, base_future_inputs=inputs,
        )
        assert [(s.date, s.is_mec, s.mec_year) for s in guaranteed] == [
            (s.date, s.is_mec, s.mec_year) for s in results
        ]


@pytest.mark.parametrize("timing", list(calc_engine.ProjectionTiming))
def test_mec_latches_beyond_seven_pay_window_without_contaminating_next_run(basis, timing):
    policy, inputs = basis
    results, _ = _project(policy, inputs, timing=timing, months=84)
    assert results[-1].tamra_year == 8
    assert all(s.is_mec and s.mec_year == 28 for s in results if s.date >= date(2027, 9, 1))
    rerun, _ = _project(policy, inputs, timing=timing, conform=True)
    assert not any(s.is_mec for s in rerun)


@pytest.mark.parametrize(
    ("level", "prior", "payment", "start", "expected"),
    [
        (100, 99, 1, date(2026, 10, 1), False),
        (100, 99, 1.01, date(2026, 10, 1), True),
        (0, 0, 0, date(2026, 10, 1), False),
        (0, 0, 0.01, date(2026, 10, 1), True),
        (100, 1000, 1000, None, False),
        (100, 1000, 1000, date(2000, 9, 1), False),
    ],
)
def test_mec_threshold_and_active_window(basis, level, prior, payment, start, expected):
    policy, inputs = basis
    policy.tamra_7pay_level = level
    policy.tamra_7pay_start_date = start
    policy.tamra_7year_contributions = [prior, 0, 0, 0, 0, 0, 0]
    inputs.dated_transactions = [
        DatedTransaction(TransactionKind.PREMIUM, date(2026, 11, 1), payment),
    ]
    results, _ = _project(policy, inputs, months=1)
    assert results[-1].is_mec is expected
    assert results[-1].mec_year == (27 if expected else 0)


@pytest.mark.parametrize("timing", list(calc_engine.ProjectionTiming))
def test_loaded_mec_remains_mec_without_new_discovery_year(basis, timing):
    policy, inputs = basis
    policy.is_mec = True
    results, _ = _project(policy, inputs, conform=True, timing=timing)
    assert all(s.is_mec and s.mec_year == 0 for s in results)
    assert _mec_status(policy, results[1:]) == "MEC (inforce)"


def test_b2a_starts_off_cycle_window_and_later_change_keeps_first_mec_year(basis, monkeypatch):
    policy, inputs = basis
    policy.valuation_date = date(2026, 9, 1)
    policy.policy_month = 1
    policy.duration = 313
    policy.db_option = "B"
    policy.tamra_7pay_start_date = policy.issue_date
    inputs.dated_transactions = [
        DatedTransaction(TransactionKind.PREMIUM, date(2026, 10, 1), 10897.44),
    ]
    recalc = {"new_glp": 100000, "new_gsp": 100000, "new_7pay": 10897.44}
    inputs.policy_changes = [
        PolicyChangeEvent(PolicyChangeKind.DB_OPTION, date(2026, 10, 1), "A", recalc),
        PolicyChangeEvent(PolicyChangeKind.FACE_AMOUNT, date(2031, 9, 1), 105000, recalc),
    ]
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_: None)
    original = deepcopy(policy)
    results, _ = _project(policy, inputs, months=62)
    october = results[1]
    assert october.tamra_7pay_start_date == date(2026, 10, 1)
    assert october.amount_in_7pay == 0
    assert october.accumulated_7pay == 10897.44
    assert not october.is_mec
    first = next(s for s in results if s.is_mec)
    assert first.date == date(2027, 9, 1)
    assert first.mec_year == 28
    assert results[-1].mec_year == 28
    assert policy == original
