"""Loan Pay-off — the solved "Pay-off" type in the Loan Repayments section.

The user picks a window (Year/Age, mode, For Years/To Age) and Run Values
solves the level modal repayment that zeroes the loan by the end of the
window. Repayments apply before new loans in the month order, so the balance
is zero just before any new loan that follows.

The bracket/bisect loop is exercised against a deterministic stub engine (no
rates database needed), the same way ``test_illustration_lumpsum_to_next_premium``
drives its solver. The dropdown/amount-field/collect wiring is the usual
headless-Qt check.
"""
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.solve_loan_payoff import (
    LoanPayoffError,
    solve_loan_payoff,
)
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData


# ── stub engine driving the bracket / bisect loop ────────────────────────────

def _policy(**overrides) -> IllustrationPolicyData:
    kwargs = dict(plancode="TEST", issue_date=date(2020, 1, 15), duration=12)
    kwargs.update(overrides)
    return IllustrationPolicyData(**kwargs)


class _LoanStubEngine:
    """A deterministic loan: starts at ``balance``, shrinks dollar-for-dollar
    by each repayment (applied at the beginning of its month), optionally grows
    by ``monthly_growth`` at each month end. ``ignore_repayments`` models a
    balance the repayments can never clear (bracket-failure backstop)."""

    def __init__(self, balance: float, monthly_growth: float = 0.0,
                 ignore_repayments: bool = False):
        self.balance = balance
        self.monthly_growth = monthly_growth
        self.ignore_repayments = ignore_repayments

    def project(self, policy, months, future_inputs, options, stop_on_lapse):
        repayments = {}
        for t in future_inputs.dated_transactions:
            if t.kind == TransactionKind.LOAN_REPAYMENT:
                repayments[t.effective_date] = (
                    repayments.get(t.effective_date, 0.0) + t.amount)
        balance = self.balance
        states = []
        for k in range(months + 1):
            d = policy.issue_date + relativedelta(months=policy.duration - 1 + k)
            if not self.ignore_repayments:
                balance = max(0.0, balance - repayments.get(d, 0.0))
            beginning = balance                      # post-cap/repay buckets
            balance *= 1.0 + self.monthly_growth     # end-of-month interest
            states.append(MonthlyState(
                date=d, rg_loan_princ=beginning, policy_debt=balance))
        return states


# Window: policy years 2-4 on annual mode -> repayments on the year-2/3/4
# anniversaries; the check lands on the year-5 anniversary.
_DATES = [date(2020, 1, 15) + relativedelta(years=k) for k in (1, 2, 3)]
_CHECK = date(2020, 1, 15) + relativedelta(years=4)


def test_solver_returns_zero_when_no_loan():
    result = solve_loan_payoff(
        _policy(), repayment_dates=_DATES, check_date=_CHECK,
        engine=_LoanStubEngine(balance=0.0))
    assert result.repayment == 0.0
    assert result.residual_balance == 0.0


def test_solver_splits_a_flat_balance_across_the_payments():
    # No interest: a $1,200 loan over 3 annual repayments solves to $400.
    engine = _LoanStubEngine(balance=1_200.0)
    result = solve_loan_payoff(
        _policy(), repayment_dates=_DATES, check_date=_CHECK, engine=engine)
    assert 400.0 <= result.repayment <= 400.02   # rounded UP to the paid-off side
    assert result.residual_balance == 0.0
    assert result.check_date == _CHECK


def test_solver_lands_on_the_paid_off_boundary_with_interest():
    engine = _LoanStubEngine(balance=1_200.0, monthly_growth=0.005)
    result = solve_loan_payoff(
        _policy(), repayment_dates=_DATES, check_date=_CHECK, engine=engine)
    # Interest grows the balance between payments, so the level repayment must
    # beat the flat split...
    assert result.repayment > 400.0
    assert result.residual_balance == 0.0
    # ...and it is minimal: a couple cents less no longer pays the loan off.
    def residual(amount):
        from suiteview.illustration.models.input_set import DatedTransaction
        states = engine.project(
            _policy(), 49,
            IllustrationInputSet(dated_transactions=[
                DatedTransaction(kind=TransactionKind.LOAN_REPAYMENT,
                                 effective_date=d, amount=amount)
                for d in _DATES]),
            None, False)
        return next(s.rg_loan_princ for s in states if s.date == _CHECK)
    assert residual(result.repayment) <= 0.005
    assert residual(result.repayment - 0.02) > 0.005

def test_solver_layers_trials_on_top_of_the_base_inputs():
    # A base (Input-typed) repayment already clears part of the loan — the
    # solved payoff only has to cover the rest.
    from suiteview.illustration.models.input_set import DatedTransaction
    base = IllustrationInputSet(dated_transactions=[DatedTransaction(
        kind=TransactionKind.LOAN_REPAYMENT, effective_date=_DATES[0],
        amount=300.0)])
    engine = _LoanStubEngine(balance=1_200.0)
    result = solve_loan_payoff(
        _policy(), repayment_dates=_DATES, check_date=_CHECK,
        base_future_inputs=base, engine=engine)
    assert 300.0 <= result.repayment <= 300.02   # (1200 - 300) / 3


def test_solver_raises_when_the_loan_cannot_be_cleared():
    engine = _LoanStubEngine(balance=1_000.0, ignore_repayments=True)
    with pytest.raises(LoanPayoffError):
        solve_loan_payoff(
            _policy(), repayment_dates=_DATES, check_date=_CHECK, engine=engine)


def test_solver_with_no_dates_is_a_no_op():
    result = solve_loan_payoff(
        _policy(), repayment_dates=[], check_date=_CHECK,
        engine=_LoanStubEngine(balance=1_000.0))
    assert result.repayment == 0.0
    assert result.iterations == 0


def test_solver_falls_back_to_ending_debt_without_a_check_date():
    # Window to maturity: no month follows, so the last projected month's
    # ending policy debt is the paid-off test.
    engine = _LoanStubEngine(balance=1_200.0)
    result = solve_loan_payoff(
        _policy(), repayment_dates=_DATES, check_date=None, engine=engine)
    assert 400.0 <= result.repayment <= 400.02


# ── UI wiring (headless Qt) ──────────────────────────────────────────────────

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.models.input_set import (
    IllustrationInputSet as _InputSet,
)
from suiteview.illustration.ui.inputs_dynamic import DynamicInputsPanel

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


class _FakePolicy:
    """Just enough PolicyInformation surface for context_from_policy."""

    issue_date = date(2019, 11, 9)
    base_issue_age = 50
    attained_age = 56
    valuation_date = date(2026, 5, 9)
    policy_year = 7
    maturity_age = 121
    billing_frequency = 1
    modal_premium = 153.56
    def_of_life_ins = "GPT"
    glp = 1200.0
    accumulated_glp = 5000.0
    premiums_paid_to_date = 10000.0
    withdrawals_to_date = 1000.0
    base_rate_class = "N"
    base_table_rating = 2
    base_plancode = "1U135D00"
    status_code = "0"

    def get_coverages(self):
        return []

    def get_benefits(self):
        return []


def _panel() -> DynamicInputsPanel:
    _app()
    panel = DynamicInputsPanel()
    panel.load_from_policy(_FakePolicy())
    return panel


def _combo_items(row):
    return [row.type_combo.itemText(i) for i in range(row.type_combo.count())]


def test_payoff_appears_only_in_the_repayment_section():
    panel = _panel()
    repay_row = panel.repayment_section.rows()[0]
    assert _combo_items(repay_row) == ["Input", "Pay-off"]
    assert repay_row.type_combo.model().item(1).isEnabled()
    # Loans / Withdrawals keep the plain Input dropdown (Solve disabled).
    assert _combo_items(panel.loan_section.rows()[0]) == ["Input", "Solve"]
    assert _combo_items(panel.withdrawal_section.rows()[0]) == ["Input", "Solve"]


def test_payoff_disables_the_amount_field_until_solved():
    panel = _panel()
    row = panel.repayment_section.rows()[0]
    assert row.amount_edit.isEnabled()
    row.type_combo.setCurrentText("Pay-off")
    assert row.is_payoff()
    assert not row.amount_edit.isEnabled()
    assert row.amount_edit.text() == ""
    # Back to Input re-enables it.
    row.type_combo.setCurrentText("Input")
    assert row.amount_edit.isEnabled()


def _fill_payoff_row(row, year, mode, for_years):
    row.type_combo.setCurrentText("Pay-off")
    row.year_edit.set_value(year)
    row._year_edited()
    row.mode_combo.setCurrentText(mode)
    row.for_years_edit.set_value(for_years)
    row._for_years_edited()


def test_loan_payoff_request_expands_dates_and_check_date():
    panel = _panel()
    _fill_payoff_row(panel.repayment_section.rows()[0], 8, "A", 3)
    requests = panel.loan_payoff_requests()
    assert len(requests) == 1
    request = requests[0]
    assert request["start_year"] == 8
    assert request["end_year"] == 10
    assert request["mode"] == "A"
    # Annual repayments on the year-8/9/10 anniversaries (issue 2019-11-09)...
    assert request["dates"] == [date(2026, 11, 9), date(2027, 11, 9), date(2028, 11, 9)]
    # ...and the balance is checked on the anniversary that ends the window.
    assert request["check_date"] == date(2029, 11, 9)


def test_loan_payoff_request_clamps_the_current_year_to_the_forecast_date():
    # Year 7's anniversary (2025-11-09) is behind the forecast date
    # (2026-06-09) — the first repayment lands on the forecast date instead.
    panel = _panel()
    _fill_payoff_row(panel.repayment_section.rows()[0], 7, "A", 1)
    requests = panel.loan_payoff_requests()
    assert len(requests) == 1
    assert requests[0]["dates"] == [date(2026, 6, 9)]
    assert requests[0]["check_date"] == date(2026, 11, 9)


def test_payoff_rows_never_export_as_plain_repayments():
    panel = _panel()
    _fill_payoff_row(panel.repayment_section.rows()[0], 8, "A", 3)
    # Even after a run fills the display amount, collect_into must not export
    # the Pay-off row — main_window layers the solved repayments itself.
    panel.set_loan_payoff_amounts([123.45])
    assert panel.repayment_section.rows()[0].amount() == 123.45
    input_set = _InputSet()
    panel.collect_into(input_set)
    assert not any(t.kind == TransactionKind.LOAN_REPAYMENT
                   for t in input_set.dated_transactions)


def test_input_repayment_rows_still_export():
    panel = _panel()
    row = panel.repayment_section.rows()[0]
    row.year_edit.set_value(8)
    row._year_edited()
    row.amount_edit.set_value(50.0, decimals=2)
    input_set = _InputSet()
    panel.collect_into(input_set)
    repay = [t for t in input_set.dated_transactions
             if t.kind == TransactionKind.LOAN_REPAYMENT]
    assert repay and all(t.amount == 50.0 for t in repay)


def test_payoff_requests_sorted_and_filled_in_year_order():
    panel = _panel()
    # Two windows entered out of order: years 20-22 first, then 8-10.
    _fill_payoff_row(panel.repayment_section.rows()[0], 20, "A", 3)
    _fill_payoff_row(panel.repayment_section.add_row(), 8, "A", 3)
    requests = panel.loan_payoff_requests()
    assert [r["start_year"] for r in requests] == [8, 20]
    panel.set_loan_payoff_amounts([111.11, 222.22])
    by_year = {row.year(): row.amount()
               for row in panel.repayment_section.rows()}
    assert by_year == {8: 111.11, 20: 222.22}


def test_level_premium_type_suppresses_payoff_requests():
    panel = _panel()
    _fill_payoff_row(panel.repayment_section.rows()[0], 8, "A", 3)
    assert panel.loan_payoff_requests()
    panel.premium_section.rows()[0].type_combo.setCurrentText("Min to Maturity")
    assert panel.loan_payoff_requests() == []
