from copy import deepcopy
from dataclasses import asdict
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.illustration.core.guaranteed_projection import guaranteed_options, lock_values
from suiteview.illustration.core.solve_level_to_exception import solve_level_to_exception
from suiteview.illustration.models import case_bundle, case_store, imported_case_store
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import TransactionKind
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab
from suiteview.illustration.ui.saved_case_scenario import build_spec_from_tab, materialize_saved_case


@pytest.fixture
def case9(qtbot):
    policy = IllustrationPolicyData(
        policy_number="CASE9", company_code="01", region="CKPR", plancode="1U135P00",
        issue_date=date(2000, 4, 6), issue_age=43, rate_sex="F", rate_class="N",
        face_amount=48172, db_option="A", valuation_date=date(2026, 9, 6),
        account_value=4448.56, duration=318, policy_year=27, attained_age=69,
        maturity_age=95, modal_premium=56, billing_frequency=1,
        def_of_life_ins="GPT", glp=804.12,
    )
    tab = IllustrationInputsTab()
    qtbot.addWidget(tab)
    tab.load_data_from_policy(policy)
    state = tab.dynamic_panel.capture_state()
    state["apply_prem_to_loan"] = True
    state["sections"]["premiums"] = [
        {"type": "INPUT", "year": "27", "amount": "56", "mode": "M", "for_years": "3"},
        {"type": "Prem to Maturity", "year": "30", "mode": "M"},
    ]
    state["sections"]["face"] = [{"type": "Input", "year": "28", "amount": "25000"}]
    state["sections"]["loans"] = [
        {"type": "Input", "year": "29", "amount": "1000", "mode": "A", "for_years": "1"},
    ]
    assert tab.dynamic_panel.apply_state(state) == []
    return policy, tab


def _compiled(policy, inputs):
    return {
        policy.issue_date + relativedelta(months=duration - 1): values
        for duration, values in compile_month_inputs(policy, inputs, 90).items()
    }


def test_case9_dynamic_inputs_compile_loan_before_solve_with_one_off_cutoff(case9):
    policy, tab = case9
    panel = tab.dynamic_panel
    assert panel.loan_section.isEnabled()
    assert panel.forecast_loan_edit.isEnabled()
    spec = build_spec_from_tab("Case9", tab, policy)
    assert spec.min_level == {"start_year": 30, "mode": "M"}
    assert spec.options.apply_prem_to_loan
    compiled = _compiled(policy, spec.scenario.future_inputs)
    assert {when: c.regular_loan for when, c in compiled.items() if c.regular_loan} == {
        date(2028, 4, 6): 1000,
    }
    before = [c.scheduled_premium for when, c in compiled.items() if when < date(2029, 4, 6)]
    assert before == [56] * 30
    assert compiled[date(2029, 4, 6)].scheduled_premium == 0
    changes = spec.scenario.future_inputs.policy_changes
    assert len(changes) == 1
    assert changes[0].effective_date == date(2027, 4, 6)
    assert changes[0].value == 25000


def test_forecast_loan_remains_a_single_dated_input_with_prem_to_maturity(case9):
    policy, tab = case9
    tab.dynamic_panel.forecast_loan_edit.setText("125")
    inputs = tab.export_input_set()
    assert [(t.effective_date, t.amount) for t in inputs.dated_transactions
            if t.kind == TransactionKind.LOAN] == [(date(2026, 10, 6), 125)]
    compiled = _compiled(policy, inputs)
    assert sum(c.regular_loan for c in compiled.values()) == 1125


@pytest.mark.parametrize("year", [27, 29, 30, 31])
def test_one_year_loan_spans_current_before_at_and_after_solve_start(case9, year):
    policy, tab = case9
    panel = tab.dynamic_panel
    state = panel.capture_state()
    state["sections"]["loans"][0]["year"] = str(year)
    assert panel.apply_state(state) == []
    compiled = _compiled(policy, tab.export_input_set())
    # Current-year annual input starts on the forecast date, not a past anniversary.
    expected_date = date(2026, 10, 6) if year == 27 else date(1999 + year, 4, 6)
    assert {when: c.regular_loan for when, c in compiled.items() if c.regular_loan} == {
        expected_date: 1000,
    }


def test_case9_saved_export_import_roundtrip_recompiles_exact_dynamic_inputs(case9, tmp_path):
    policy, tab = case9
    original = build_spec_from_tab("Case9", tab, policy)
    captured = tab.capture_case_inputs()
    case_store.save_case(
        "Case9", policy_number=policy.policy_number, company_code="01", region="CKPR",
        inputs=captured, policy_snapshot=policy, directory=tmp_path / "saved",
    )
    saved = case_store.load_case("Case9", directory=tmp_path / "saved")
    exported = case_bundle.write_bundle(tmp_path / "export", [saved])
    decoded = case_bundle.read_bundle(exported)
    assert not decoded.errors
    stored = imported_case_store.save_imported_bundle(
        "Imported", decoded.cases, directory=tmp_path / "imported",
    )
    imported = imported_case_store.load_imported_case(stored.path, "Case9")
    for case in (saved, decoded.cases[0], imported):
        assert case.inputs == captured
        assert case.policy_snapshot == policy
        rebuilt = materialize_saved_case(case, strict=True)
        assert rebuilt.scenario.future_inputs == original.scenario.future_inputs
        assert rebuilt.options == original.options
        assert rebuilt.min_level == original.min_level


def test_solver_varies_only_premiums_and_retains_pre_start_loan_on_every_trial(case9):
    policy, tab = case9
    base = tab.export_input_set()
    before = deepcopy(base)
    candidates = []

    class Engine:
        def project(self, policy, *, future_inputs, options, **kwargs):
            assert options.apply_prem_to_loan
            compiled = _compiled(policy, future_inputs)
            assert compiled[date(2028, 4, 6)].regular_loan == 1000
            assert sum(c.regular_loan for c in compiled.values()) == 1000
            assert compiled[date(2028, 4, 6)].scheduled_premium == 56
            assert future_inputs.policy_changes == base.policy_changes
            premium = compiled[date(2029, 4, 6)].scheduled_premium
            candidates.append(premium)
            return [MonthlyState(
                attained_age=95 if premium >= 75 else 80,
                av_end_of_month=1, date=date(2052, 4, 6), policy_year=53,
            )]

    solved = solve_level_to_exception(
        policy, mode="M", start_policy_year=30, base_future_inputs=base,
        base_options=tab.export_options(), engine=Engine(),
    )
    assert solved.premium == pytest.approx(75, abs=0.01)
    assert len(set(candidates)) > 3
    assert asdict(base) == asdict(before)


def test_guaranteed_locks_applied_loan_and_diverted_premium_without_double_repayment(case9):
    policy, tab = case9
    current = [
        MonthlyState(duration=318, date=date(2026, 9, 6)),
        MonthlyState(
            duration=337, date=date(2028, 4, 6),
            applied_regular_loan=1000, gross_premium=56,
        ),
        MonthlyState(
            duration=338, date=date(2028, 5, 6),
            applied_loan_repayment=56, loan_repay_from_prem=56, gross_premium=0,
        ),
    ]
    base = tab.export_input_set()
    locked = lock_values(policy, current, base)
    compiled = _compiled(policy, locked)
    assert sum(c.regular_loan for c in compiled.values()) == 1000
    assert compiled[date(2028, 4, 6)].regular_loan == 1000
    repayment = [t for t in locked.dated_transactions if t.kind == TransactionKind.LOAN_REPAYMENT]
    assert [(t.effective_date, t.amount) for t in repayment] == [(date(2028, 5, 6), 56)]
    assert not any(t.kind == TransactionKind.PREMIUM and t.effective_date == date(2028, 5, 6)
                   for t in locked.dated_transactions)
    assert locked.policy_changes == base.policy_changes
    options = guaranteed_options(tab.export_options())
    assert not options.apply_prem_to_loan
    assert not options.restrict_loans_to_sv
