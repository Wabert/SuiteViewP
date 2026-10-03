"""ABR Quote — the theoretical annual level premium behind an ABR quote.

Covers the reshaped run options, the Run Controls gating of the ABR Quote
checkbox, and an end-to-end solve on the flat (chargeless, 0%-interest)
engine: loan retired against the AV, Option B switched to A, annual-only
payments starting at the next anniversary, no lapse while the values run
negative, and a $1,000 surrender value at maturity.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date

import pytest

from suiteview.illustration.core.abr_quote import (
    ABR_TARGET_SV,
    abr_quote_options,
    run_abr_quote,
)
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)
from suiteview.illustration.ui.report_tab import format_abr_quote_pages
from suiteview.illustration.ui.styles import TAB_WIDGET_STYLE

_QT_APP = None


def _app():
    global _QT_APP
    from PyQt6.QtWidgets import QApplication
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


# ── Options reshape ──────────────────────────────────────────────────────────

def test_abr_quote_options_disable_every_premium_limit_and_the_lapse_test():
    base = IllustrationOptions(
        conform_to_tefra=True, conform_to_tamra=True,
        allow_exception_prems=True, pay_monthly_deduction=True,
        monthly_deduction_windows=[(1, None)],
        billable_to_md_windows=[(1, None)],
        exact_days_interest=True)

    options = abr_quote_options(base)

    assert options.conform_to_tefra is False
    assert options.conform_to_tamra is False
    assert options.no_lapse is True
    assert options.allow_exception_prems is False
    assert options.pay_monthly_deduction is False
    assert options.monthly_deduction_windows is None
    assert options.billable_to_md_windows is None
    assert options.iul_wair_crediting is False
    # Unrelated toggles ride through untouched.
    assert options.exact_days_interest is True


# ── Options-menu toggle gating (headless Qt) ─────────────────────────────────

def test_abr_quote_mode_locks_input_tab_except_the_illustrated_rate():
    from suiteview.illustration.models.app_settings import get_illustration_settings
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

    _app()
    settings = get_illustration_settings()
    settings.set_abr_quote_mode(False)
    tab = IllustrationInputsTab()
    panel = tab.dynamic_panel

    # Off by default — the Input tab is fully editable.
    assert tab.abr_quote_enabled() is False
    assert tab.abr_minimum_face_row.parent() is panel
    assert tab.input_tabs.styleSheet() == TAB_WIDGET_STYLE
    assert panel.premium_section.isEnabled() is True
    assert panel.illustrated_rate_edit.isEnabled() is True

    # Toggling ABR Quote on locks every Input-tab control except the rate.
    settings.set_abr_quote_mode(True)
    try:
        assert tab.abr_quote_enabled() is True
        for widget in (panel.premium_section, panel.loan_section,
                       panel.withdrawal_section, panel.repayment_section,
                       panel.face_section, panel.dbo_section,
                       panel.rateclass_section, panel.table_section,
                       panel.riders_panel, panel.tamra_check,
                       panel.apply_prem_to_loan_check):
            assert widget.isEnabled() is False
        # The Illustrated Rate stays editable and accepts any value.
        assert panel.illustrated_rate_edit.isEnabled() is True
        assert panel.illustrated_rate_edit.isReadOnly() is False
        assert tab.abr_minimum_face_row.isHidden() is False
        tab.abr_minimum_face_edit.setText("25,000")
        assert tab.abr_minimum_face_amount() == pytest.approx(25_000.0)

        # Toggling back off restores the panel.
        settings.set_abr_quote_mode(False)
        assert panel.premium_section.isEnabled() is True
        assert tab.abr_minimum_face_row.isHidden() is True
    finally:
        settings.set_abr_quote_mode(False)


def test_abr_quote_mode_forces_iul_allocation_to_the_fixed_fund():
    from suiteview.illustration.models.app_settings import get_illustration_settings
    from suiteview.illustration.models.index_strategies import FIXED_FUND_ID
    from suiteview.illustration.ui.inputs_dynamic import DynamicInputsPanel
    from suiteview.illustration.ui import inputs_dynamic

    _app()
    settings = get_illustration_settings()
    settings.set_abr_quote_mode(True)
    try:
        panel = DynamicInputsPanel()
        panel._ctx = inputs_dynamic.PolicyContext()
        panel._ctx.is_iul = True
        panel.set_abr_quote_mode(True)
        assert panel.iul_allocations() == {FIXED_FUND_ID: 1.0}
    finally:
        settings.set_abr_quote_mode(False)


# ── End-to-end on the flat engine ────────────────────────────────────────────

class _FlatRatesEngine(IllustrationEngine):
    def _load_rates(self, policy, config):
        return _flat_rates()


def _flat_rates() -> IllustrationRates:
    return IllustrationRates(
        shadow_coi=[None] + [0.0] * 121,
        shadow_epu=[None] + [0.0] * 121,
        shadow_int=[None] + [0.0] * 121,
        shadow_dbd=[None] + [0.0] * 121,
        shadow_tpp=[None] + [0.0] * 121,
        shadow_epp=[None] + [0.0] * 121,
    )


def _test_config(_plancode) -> PlancodeConfig:
    return PlancodeConfig(
        plancode="TEST", interest_method="ExactDays", gint=0.0, dbd=0.0,
        prem_flat_load=0.0, 
        maturity_age=121, loan_type="Arrears")


@pytest.fixture
def _flat_plancode(monkeypatch):
    from suiteview.illustration.core import calc_engine
    from suiteview.illustration.core.ul_rates import ULRates
    monkeypatch.setattr(calc_engine, "load_plancode", _test_config)
    monkeypatch.setattr(
        calc_engine,
        "load_rates",
        lambda *_args, **_kwargs: _flat_rates(),
    )
    monkeypatch.setattr(
        calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())
    monkeypatch.setattr(
        ULRates,
        "get_rates",
        lambda _self, rate_type, *_args, **_kwargs: (
            [None] + [0.0] * 121 if rate_type == "COI" else []
        ),
    )


def _loaned_option_b_policy() -> IllustrationPolicyData:
    # AV 5,000 with a 6,000 loan: the up-front loan retirement leaves the AV
    # at −1,000, so the policy MUST coast negative (lapse test off) until the
    # solved annual premium starts. With no charges and 0% interest, SV at
    # maturity = −1,000 + 80 annual payments (years 2..81) × premium; the
    # $1,000 target needs exactly 2,000 → 25.00/year.
    return IllustrationPolicyData(
        plancode="TEST", def_of_life_ins="GPT",
        issue_date=date(2026, 1, 15), valuation_date=date(2026, 1, 15),
        issue_age=40, attained_age=40, maturity_age=121,
        policy_year=1, policy_month=1, duration=1,
        face_amount=100_000.0, units=100.0, db_option="B",
        account_value=5_000.0, regular_loan_principal=6_000.0,
        modal_premium=100.0, billing_frequency=1,
        glp=1e9, gsp=1e9, accumulated_glp=1e9, current_interest_rate=0.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2026, 1, 15),
                                  face_amount=100_000.0, units=100.0)],
    )


def test_run_abr_quote_solves_the_annual_premium_on_a_loaned_option_b_policy(_flat_plancode):
    source = _loaned_option_b_policy()
    run = run_abr_quote(source, engine=_FlatRatesEngine())

    # Loan retired up front — against a COPY, never the caller's policy.
    assert run.loan_retired == pytest.approx(6_000.0)
    assert run.policy.account_value == pytest.approx(-1_000.0)
    assert run.policy.total_loan_balance == 0.0
    assert source.account_value == pytest.approx(5_000.0)
    assert source.regular_loan_principal == pytest.approx(6_000.0)

    # Option B switched to A on the first forecast month.
    assert run.db_option_switched is True
    assert run.results[1].db_option == "A"

    # Annual level premium: 2,000 over the 80 remaining anniversaries.
    assert run.premium == pytest.approx(2_000.0 / 80.0, abs=0.02)
    assert run.achieved_sv >= ABR_TARGET_SV - 0.005
    assert run.first_payment_date == date(2027, 1, 15)

    # No lapse anywhere, even while the AV is negative before the first
    # annual payment; no premium is collected before that payment.
    assert not any(state.lapsed for state in run.results)
    pre_payment = [s for s in run.results[1:] if s.date < run.first_payment_date]
    assert pre_payment and all(s.premiums_to_date == 0.0 for s in pre_payment)

    # The projection reaches maturity (age 121 anniversary row).
    assert run.results[-1].attained_age >= 120


def test_shadow_policy_uses_lower_of_regular_and_shadow_solve(_flat_plancode):
    policy = _loaned_option_b_policy()
    policy.ccv_active = True
    policy.shadow_account_value = 0.0

    run = run_abr_quote(policy, engine=_FlatRatesEngine())

    assert run.regular_premium == pytest.approx(25.0, abs=0.02)
    assert run.shadow_premium < run.regular_premium
    assert run.premium == run.shadow_premium
    assert run.premium_basis == "shadow"
    assert run.achieved_shadow >= ABR_TARGET_SV - 0.005
    report = " ".join("\n".join(format_abr_quote_pages(run, run.policy)[0]).split())
    assert "Regular-account annual premium" in report
    assert "Shadow-account annual premium" in report
    assert "lower shadow-account solve" in report


def test_max_partial_projects_next_deduction_with_reduced_face_and_av(
    _flat_plancode, monkeypatch
):
    from suiteview.illustration.core.ul_rates import ULRates

    monkeypatch.setattr(
        ULRates,
        "get_band",
        lambda _self, _plan, face, issue_date=None: 2 if face < 50_000 else 1,
    )
    monkeypatch.setattr(
        ULRates,
        "get_rates",
        lambda _self, rate_type, *_args, **_kwargs: (
            [None] + [0.0] * 121 if rate_type == "COI" else []
        ),
    )
    policy = _loaned_option_b_policy()
    policy.db_option = "A"
    policy.account_value = 10_000.0
    policy.regular_loan_principal = 0.0

    run = run_abr_quote(
        policy,
        minimum_face_amount=25_000.0,
        engine=_FlatRatesEngine(),
    )

    partial = run.max_partial
    assert partial is not None
    assert partial.locked_death_benefit == pytest.approx(100_000.0)
    assert partial.reduction_ratio == pytest.approx(0.25)
    assert partial.proportional_account_value == pytest.approx(2_500.0)
    assert partial.account_value_used == pytest.approx(2_500.0)
    assert partial.minimum_face_amount == pytest.approx(25_000.0)
    assert partial.monthly_deduction == pytest.approx(0.0)
    assert partial.monthly_deduction_date == date(2026, 2, 15)
    assert partial.band == 2
    report = " ".join("\n".join(format_abr_quote_pages(run, run.policy)[0]).split())
    assert "Minimum Face Amount Allowed: $25,000.00" in report
    assert "02/15/2026" in report
    assert "Account Value $2,500.00" in report
    assert "monthly deduction is $0.00" in report


def test_max_partial_rejects_face_above_locked_death_benefit(_flat_plancode):
    with pytest.raises(ValueError, match="cannot exceed"):
        run_abr_quote(
            _loaned_option_b_policy(),
            minimum_face_amount=150_000.0,
            engine=_FlatRatesEngine(),
        )


def test_option_b_max_partial_uses_forecast_locked_death_benefit(_flat_plancode):
    policy = _loaned_option_b_policy()
    policy.account_value = 50_000.0
    policy.regular_loan_principal = 0.0
    policy.current_interest_rate = 0.05

    run = run_abr_quote(
        policy,
        minimum_face_amount=75_000.0,
        engine=_FlatRatesEngine(),
    )

    partial = run.max_partial
    assert partial is not None
    forecast_locked_db = run.results[1].coverage_after_change["CurrentSA"]
    assert partial.locked_death_benefit == pytest.approx(forecast_locked_db)
    assert partial.locked_death_benefit > 150_000.0
    assert partial.proportional_account_value == pytest.approx(
        50_000.0 * 75_000.0 / forecast_locked_db
    )
