"""AllocationsPanel + DynamicInputsPanel integration for IUL vs declared-rate plans."""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.models.index_strategies import load_index_strategies
from suiteview.illustration.ui.allocations_panel import AllocationsPanel
from suiteview.illustration.ui.inputs_dynamic import DynamicInputsPanel


def _fake_policy(plancode: str) -> SimpleNamespace:
    return SimpleNamespace(
        base_plancode=plancode,
        issue_date=date(2015, 3, 15),
        base_issue_age=45,
        valuation_date=date(2026, 5, 15),
        policy_year=12,
        maturity_age=100,
        attained_age=56,
        billing_frequency=1,
        status_code="0",
        base_table_rating=0,
        def_of_life_ins="GPT",
        glp=1200.0,
        accumulated_glp=14400.0,
        premiums_paid_to_date=10000.0,
        withdrawals_to_date=0.0,
        modal_premium=100.0,
        total_loan_balance=0.0,
        base_rate_class="N",
        premium_allocations={"U1": 0.5, "IX": 0.5},
    )


def test_allocations_panel_blends_from_inforce_allocations(qtbot):
    panel = AllocationsPanel()
    qtbot.addWidget(panel)
    plan = load_index_strategies("1U145500")  # IUL14
    panel.set_plan(plan, gint=0.035, inforce_allocations={"U1": 50.0, "IX": 50.0})

    blended = panel.blended()
    # Defaults: U1 -> gint 0.035, IX -> min(6.25%, AG49 6.23%) = 0.0623.
    # 0.5*0.035 + 0.5*0.0623 = 0.04865 -> TRUNC 0.0486
    assert blended.nominal == 0.0486
    assert blended.effective == 0.0486
    assert blended.guaranteed == pytest.approx(0.0175)
    assert panel.is_valid()
    assert panel.allocations() == {
        "U1": pytest.approx(0.5), "IS": 0.0, "IX": pytest.approx(0.5),
        "IC": 0.0, "IF": 0.0,
    }


def test_allocations_panel_not_applicable_state(qtbot):
    panel = AllocationsPanel()
    qtbot.addWidget(panel)
    panel.set_plan(None)
    assert panel.blended() is None
    assert panel.problems() == []
    assert panel._na_note.isVisible() or not panel._grid_host.isVisible()


def test_inputs_panel_iul_mirrors_blended_effective(qtbot):
    panel = DynamicInputsPanel()
    qtbot.addWidget(panel)
    panel.load_from_policy(_fake_policy("1U145500"))

    assert panel.illustrated_rate_edit.isReadOnly()
    blended = panel.allocations_panel.blended()
    assert blended is not None
    assert panel.illustrated_rate() == pytest.approx(blended.effective, abs=5e-6)
    assert panel.allocation_problems() == []


def test_inputs_panel_declared_rate_keeps_editable_field(qtbot):
    panel = DynamicInputsPanel()
    qtbot.addWidget(panel)
    policy = _fake_policy("1U143900")  # EXECUL — declared rate
    policy.premium_allocations = {}
    panel.load_from_policy(policy)

    assert not panel.illustrated_rate_edit.isReadOnly()
    assert panel.allocations_panel.blended() is None
    assert panel.allocation_problems() == []


def test_sweep_account_min_round_trips_through_panel(qtbot):
    panel = AllocationsPanel()
    qtbot.addWidget(panel)
    plan = load_index_strategies("1U145500")
    panel.set_plan(plan, gint=0.035, sweep_account_min=250.0)
    assert panel.sweep_account_min() == pytest.approx(250.0)

    panel._sweep_min_edit.setText("")
    assert panel.sweep_account_min() is None      # blank = no override

    panel._sweep_min_edit.setText("1200.50")
    assert panel.sweep_account_min() == pytest.approx(1200.50)


def test_sweep_account_min_none_for_declared_rate_plans(qtbot):
    panel = DynamicInputsPanel()
    qtbot.addWidget(panel)
    policy = _fake_policy("1U143900")
    policy.premium_allocations = {}
    panel.load_from_policy(policy)
    assert panel.sweep_account_min() is None


def test_iul_panel_defaults_sweep_min_from_policy(qtbot):
    panel = DynamicInputsPanel()
    qtbot.addWidget(panel)
    policy = _fake_policy("1U145500")
    policy.sweep_account_min = 300.0
    panel.load_from_policy(policy)
    assert panel.sweep_account_min() == pytest.approx(300.0)
