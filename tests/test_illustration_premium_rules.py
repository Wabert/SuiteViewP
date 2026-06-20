"""Premium rules: GLP monthly-mode normalization and no-premium-at-maturity."""
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.target_premium import floor_monthly_cent
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


# ── GLP normalized to a monthly mode: GLP = rounddown(GLP/12, 2) * 12 ─────────

def test_glp_normalizes_to_monthly_twelfths():
    # 2519.75 / 12 = 209.97916… -> floor to 209.97 -> * 12 = 2519.64
    assert floor_monthly_cent(2519.75) == 2519.64
    # Already a clean 12x stays put (idempotent).
    assert floor_monthly_cent(2519.64) == 2519.64
    # The twelfth is an exact cent amount.
    assert round(floor_monthly_cent(2519.75) / 12, 2) * 12 == pytest.approx(floor_monthly_cent(2519.75))


# ── No premium is collected on the maturity date ─────────────────────────────

def _project_to_maturity(maturity_age: int):
    calc_engine.load_plancode = lambda _p: PlancodeConfig(
        plancode="TEST", interest_method="ExactDays", gint=0.0, dbd=0.0,
        premium_load="0", prem_flat_load=0.0, epu_code="0", mfee="0",
        poav_code="0", bonus="0", corridor_code=None, snet_period=0,
        maturity_age=maturity_age, loan_type="Arrears")
    calc_engine.load_bonus_config = lambda _p, _d: BonusConfig()

    policy = IllustrationPolicyData(
        plancode="TEST",
        issue_date=date(2026, 1, 15),
        valuation_date=date(2026, 1, 15),
        issue_age=45,
        attained_age=45,
        maturity_age=maturity_age,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=100_000.0,
        modal_premium=100.0,
        glp=1_000_000.0,   # ample guideline room so the modal premium bills
        gsp=1_000_000.0,
        current_interest_rate=0.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2026, 1, 15),
                                  face_amount=100_000.0, units=100.0)],
    )
    return IllustrationEngine().project(
        policy, months=None, options=IllustrationOptions(),
        rates_override=IllustrationRates(), bonus_override=BonusConfig())


def test_payment_count_held_at_year_start_and_counts_current_year_modes():
    from suiteview.illustration.core.calc_engine import _tamra_premium_display
    from suiteview.illustration.models.calc_state import MonthlyState

    policy = IllustrationPolicyData(
        issue_date=date(2019, 11, 9), issue_age=50, maturity_age=121,
        face_amount=100_000.0, billing_frequency=3,  # quarterly
        tamra_7pay_start_date=None,
        segments=[CoverageSegment(coverage_phase=1, face_amount=100_000.0)],
    )
    # Full policy year (anniversary, month 1): 12 / 3 = 4 quarterly payments.
    full = _tamra_premium_display(MonthlyState(), policy, date(2027, 11, 9), 1, None)
    assert full["planned_premium_mode"] == "Q"
    assert full["payment_count_policy_year"] == 4
    # No active 7-pay period -> no TAMRA-year count.
    assert full["payment_count_tamra_year"] == 0

    # Mid-year start (forecast month 8) with no prior count -> remaining modes:
    # INT((13-8)/3) = 1 quarterly payment left this year.
    partial = _tamra_premium_display(MonthlyState(), policy, date(2026, 6, 9), 8, None)
    assert partial["payment_count_policy_year"] == 1

    # Held: a later month in the same year carries the prior count, not recomputed.
    prior = MonthlyState(payment_count_policy_year=4)
    held = _tamra_premium_display(prior, policy, date(2027, 12, 9), 2, None)
    assert held["payment_count_policy_year"] == 4


def test_no_premium_on_maturity_date():
    states = _project_to_maturity(maturity_age=47)
    maturity = states[-1]

    assert maturity.date == date(2028, 1, 15)      # the maturity anniversary
    assert maturity.attained_age == 47
    assert maturity.gross_premium == 0.0           # endows — no premium collected
    # A normal projected month still bills the modal premium.
    assert any(s.gross_premium == 100.0 for s in states[1:-1])
