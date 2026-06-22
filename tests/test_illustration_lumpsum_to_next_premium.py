"""Lumpsum to Next Premium — bridging-lumpsum solver and its checkbox wiring.

The solver's window/seed helpers are pure and tested directly; the bracket /
bisect loop is exercised against a deterministic stub engine (no rates database
needed). The checkbox → accessor wiring is the usual headless-Qt check.
"""
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
    LUMPSUM_SUBTYPE,
    _forecast_date,
    _next_modal_due,
    _seed_shortfall,
    _within_snet,
    solve_lumpsum_to_next_premium,
)
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import TransactionKind
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


# ── window / due-date helpers ────────────────────────────────────────────────

def _policy(**overrides) -> IllustrationPolicyData:
    kwargs = dict(
        plancode="TEST", issue_date=date(2020, 1, 15), duration=8,
        billing_frequency=12, modal_premium=500.0, map_cease_date=None,
    )
    kwargs.update(overrides)
    return IllustrationPolicyData(**kwargs)


def test_forecast_date_is_inforce_snapshot_plus_one_month():
    # issue + duration months — the first forecast row the compiler maps to.
    assert _forecast_date(_policy()) == date(2020, 9, 15)


def test_next_modal_due_annual_is_the_next_anniversary():
    policy = _policy(billing_frequency=12, duration=8)  # 8 months past issue
    next_due, gap = _next_modal_due(policy, _forecast_date(policy))
    assert next_due == date(2021, 1, 15)   # the next anniversary
    assert gap == 4                        # 4 months from the forecast date


def test_next_modal_due_quarterly_is_the_next_quarter():
    policy = _policy(billing_frequency=3, duration=8)
    next_due, gap = _next_modal_due(policy, _forecast_date(policy))
    assert gap == 1                        # 8 % 3 = 2 → 1 month to the next quarter
    assert next_due == date(2020, 10, 15)


def test_next_modal_due_when_forecast_is_on_a_due_date_jumps_a_full_interval():
    # duration 12 → forecast lands on an anniversary; bridge to the next one.
    policy = _policy(billing_frequency=12, duration=12)
    next_due, gap = _next_modal_due(policy, _forecast_date(policy))
    assert gap == 12
    assert next_due == date(2022, 1, 15)


def test_within_snet_uses_snet_period_then_map_cease_date():
    config = PlancodeConfig(snet_period=10)
    inside = MonthlyState(date=date(2025, 1, 1), policy_year=5)
    outside = MonthlyState(date=date(2031, 1, 1), policy_year=11)
    assert _within_snet(inside, _policy(), config) is True
    assert _within_snet(outside, _policy(), config) is False

    policy = _policy(map_cease_date=date(2024, 6, 15))
    assert _within_snet(MonthlyState(date=date(2024, 1, 1), policy_year=99), policy, config) is True
    assert _within_snet(MonthlyState(date=date(2025, 1, 1), policy_year=1), policy, config) is False


# ── seed shortfall (SV / AV / SNET selection) ────────────────────────────────

def test_seed_uses_surrender_value_shortfall_when_snet_gap_is_larger():
    config = PlancodeConfig(lapse_value="SV", snet_period=10)
    window = [MonthlyState(date=date(2021, 1, 1), policy_year=2, lapsed=True,
                           surrender_value=-40.0, accum_mtp_less_prem=-100.0)]
    seed, reason = _seed_shortfall(window, _policy(), config)
    assert seed == 40.0
    assert reason == "SV"


def test_seed_uses_snet_gap_when_it_is_the_lower_amount():
    config = PlancodeConfig(lapse_value="SV", snet_period=10)
    window = [
        MonthlyState(date=date(2021, 1, 1), policy_year=2, lapsed=True,
                     surrender_value=-100.0, accum_mtp_less_prem=-30.0),
        MonthlyState(date=date(2021, 2, 1), policy_year=2, lapsed=True,
                     surrender_value=-50.0, accum_mtp_less_prem=-20.0),
    ]
    seed, reason = _seed_shortfall(window, _policy(), config)
    assert seed == 30.0   # worst month's SNET gap, which beats both SV shortfalls
    assert reason == "SNET"


def test_seed_uses_av_less_loans_for_av_lapse_plancodes():
    config = PlancodeConfig(lapse_value="AV", snet_period=0)  # past SNET
    window = [MonthlyState(date=date(2021, 1, 1), policy_year=2, lapsed=True,
                           av_less_loans=-75.0, surrender_value=-500.0)]
    seed, reason = _seed_shortfall(window, _policy(), config)
    assert seed == 75.0
    assert reason == "AV"


def test_seed_ignores_in_force_months():
    config = PlancodeConfig(lapse_value="SV", snet_period=10)
    window = [MonthlyState(date=date(2021, 1, 1), policy_year=2, lapsed=False,
                           surrender_value=-999.0, accum_mtp_less_prem=-999.0)]
    assert _seed_shortfall(window, _policy(), config) == (0.0, "SV")


# ── stub engine driving the bracket / bisect loop ────────────────────────────

class _StubEngine:
    """A deterministic thin policy: surrender value rises one-for-one with the
    net lumpsum, lapses while negative. ``cap`` models a guideline ceiling."""

    def __init__(self, base_sv: float, *, cap=None):
        self.base_sv = base_sv
        self.cap = cap

    def project(self, policy, months, future_inputs, options, stop_on_lapse):
        forecast = policy.issue_date + relativedelta(months=policy.duration)
        lumpsum = sum(
            t.amount for t in future_inputs.dated_transactions
            if t.kind == TransactionKind.PREMIUM and t.effective_date == forecast
        )
        applied = lumpsum if self.cap is None else min(lumpsum, self.cap)
        states = [MonthlyState(date=policy.issue_date + relativedelta(months=policy.duration - 1))]
        for k in range(1, months + 1):
            d = policy.issue_date + relativedelta(months=policy.duration - 1 + k)
            sv = self.base_sv + applied
            states.append(MonthlyState(
                date=d, policy_year=2, surrender_value=sv, av_less_loans=sv,
                accum_mtp_less_prem=sv, lapsed=sv < 0.0,
                applied_lumpsum=applied if d == forecast else 0.0))
        return states


_SV_CONFIG = PlancodeConfig(lapse_value="SV", snet_period=10)


def test_solver_returns_none_when_no_bridge_is_needed():
    engine = _StubEngine(base_sv=250.0)  # already positive — survives
    result = solve_lumpsum_to_next_premium(
        _policy(), config=_SV_CONFIG, engine=engine)
    assert result is None


def test_solver_finds_the_lumpsum_that_just_keeps_it_in_force():
    engine = _StubEngine(base_sv=-100.0)  # needs ~100 net to reach zero
    result = solve_lumpsum_to_next_premium(
        _policy(), config=_SV_CONFIG, engine=engine)
    assert result is not None
    assert result.binding_reason == "SV"
    assert result.seed_shortfall == 100.0
    # Rounded UP to the in-force side of the boundary (sv >= 0 needs lumpsum >= 100).
    assert 100.0 <= result.lumpsum <= 100.02
    assert not result.guideline_limited
    # The solved lumpsum genuinely survives the window.
    final = engine.project(
        _policy(), 6,
        _inject(result.forecast_date, result.lumpsum), None, False)
    assert all(not s.lapsed for s in final[1:])


def test_solver_flags_guideline_limited_when_the_cap_blocks_the_bridge():
    # The guideline accepts at most $20, far short of the ~$100 needed.
    engine = _StubEngine(base_sv=-100.0, cap=20.0)
    result = solve_lumpsum_to_next_premium(
        _policy(), config=_SV_CONFIG, engine=engine)
    assert result is not None
    assert result.guideline_limited is True
    assert result.applied == 20.0
    assert result.lumpsum == 20.0


def _inject(forecast, amount):
    from suiteview.illustration.models.input_set import (
        DatedTransaction, IllustrationInputSet,
    )
    return IllustrationInputSet(dated_transactions=[DatedTransaction(
        kind=TransactionKind.PREMIUM, effective_date=forecast, amount=amount,
        subtype=LUMPSUM_SUBTYPE)])


# ── checkbox → accessor wiring (headless Qt) ─────────────────────────────────

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_lumpsum_checkbox_defaults_off_and_drives_the_accessor():
    _app()
    tab = IllustrationInputsTab()
    assert tab.dynamic_panel.lumpsum_to_next_check.isChecked() is False
    assert tab.lumpsum_to_next_enabled() is False

    tab.dynamic_panel.lumpsum_to_next_check.setChecked(True)
    assert tab.lumpsum_to_next_enabled() is True
