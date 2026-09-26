"""Golden characterization for the Illustration Run Values pipeline.

The fixtures in this file are intentionally offline and deterministic.  They
exercise the UI entry point while replacing the engine and solvers with small
stubs so the goldens document ordering, solved-input handoff, report rendering
and status text before the run-service refactor.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from suiteview.illustration.core import report_builder
from suiteview.illustration.core.report_builder import _request_lines, build_ul_report
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    RollbackOverrideSet,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)
from suiteview.illustration.ui.main_window import IllustrationWindow
from suiteview.illustration.ui.report_tab import format_report_pages
from suiteview.illustration.ui.values_overview import (
    LEDGER_COLUMNS,
    monthly_ledger_cells,
)

GOLDEN_DIR = Path(__file__).parent / "golden" / "illustration_run_values"
FLOW_GOLDEN = GOLDEN_DIR / "flow_cases.json"
COMPONENT_GOLDEN = GOLDEN_DIR / "component_outputs.json"


_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _base_policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="UGOLD001",
        region="CKPR",
        company_code="01",
        insured_name="GOLDEN INSURED",
        plancode="1U143900",
        form_number="UL-GOLD",
        issue_date=date(2020, 1, 15),
        issue_age=45,
        attained_age=51,
        maturity_age=121,
        policy_year=7,
        policy_month=9,
        duration=80,
        rate_sex="M",
        rate_class="N",
        face_amount=125_000.0,
        db_option="A",
        account_value=10_000.0,
        modal_premium=125.0,
        billing_frequency=1,
        premiums_paid_to_date=9_500.0,
        withdrawals_to_date=125.0,
        valuation_date=date(2026, 9, 15),
        current_interest_rate=0.045,
        guaranteed_interest_rate=0.03,
        glp=1_200.0,
        gsp=7_500.0,
        accumulated_glp=8_400.0,
        tamra_7pay_level=5_000.0,
        tamra_7pay_start_date=date(2020, 1, 15),
        segments=[
            CoverageSegment(
                coverage_phase=1,
                issue_date=date(2020, 1, 15),
                issue_age=45,
                face_amount=125_000.0,
                units=125.0,
                rate_sex="M",
                rate_class="N",
            )
        ],
    )


def _state(month: int, *, premium: float, av: float, status: str = "") -> MonthlyState:
    return MonthlyState(
        date=date(2026, 9 + month, 15),
        policy_year=7,
        policy_month=9 + month,
        duration=80 + month,
        attained_age=51,
        requested_premium=premium,
        gross_premium=premium,
        total_deduction=40.0 + month,
        av_after_exception=av - 10.0,
        av_end_of_month=av,
        ending_sv=av - 250.0,
        ending_db=125_000.0,
        surrender_charge=250.0,
        annual_interest_rate=0.045,
        interest_credited=12.0 + month,
        glp=1_200.0,
        gsp=7_500.0,
        accumulated_glp=8_400.0 + month * 100.0,
        guideline_limit=8_400.0 + month * 100.0,
        premiums_to_date_after_exception=9_500.0 + premium,
        withdrawals_to_date=125.0,
        lapsed=status == "LAPSED",
    )


def _current_states() -> list[MonthlyState]:
    return [
        MonthlyState(
            date=date(2026, 9, 15),
            policy_year=7,
            policy_month=8,
            duration=80,
            attained_age=51,
            av_end_of_month=10_000.0,
            ending_sv=9_750.0,
            ending_db=125_000.0,
            glp=1_200.0,
            gsp=7_500.0,
            accumulated_glp=8_400.0,
            guideline_limit=8_400.0,
            premiums_to_date_after_exception=9_500.0,
            withdrawals_to_date=125.0,
        ),
        _state(1, premium=125.0, av=10_100.0),
        _state(2, premium=125.0, av=10_225.0),
    ]


def _guaranteed_states() -> list[MonthlyState]:
    states = deepcopy(_current_states())
    for state in states[1:]:
        state.av_end_of_month -= 500.0
        state.ending_sv -= 500.0
    return states


class _LoadedPolicy:
    available_companies: list = []
    exists = True
    system_code = "I"
    policy_number = "UGOLD001"
    company_code = "01"
    policy_id = "UGOLD001 QXXX"
    status_description = "Active"


class _NoDb:
    def __init__(self, region):
        self.region = region

    def connect(self):
        return None

    def close(self):
        return None


class _InputsHarness:
    def __init__(self, tab, case: dict, solved: dict):
        self._tab = tab
        self._case = case
        self._solved = solved

    def install(self, monkeypatch):
        tab = self._tab
        case = self._case
        solved = self._solved
        base_inputs = IllustrationInputSet(
            scheduled_transactions=[
                ScheduledTransaction(
                    kind=TransactionKind.PREMIUM,
                    policy_year=7,
                    amount=125.0,
                    mode="M",
                )
            ],
            dated_transactions=[
                DatedTransaction(
                    kind=TransactionKind.WITHDRAWAL,
                    effective_date=date(2026, 10, 15),
                    amount=250.0,
                )
            ],
        )
        rollback = (
            RollbackOverrideSet(valuation_date=date(2026, 8, 15))
            if case["name"] == "rollback-basis"
            else None
        )
        monkeypatch.setattr(tab, "export_inforce_overrides", lambda: None, raising=False)
        monkeypatch.setattr(tab, "export_input_set", lambda: deepcopy(base_inputs), raising=False)
        monkeypatch.setattr(tab, "run_from_issue_enabled", lambda: False, raising=False)
        monkeypatch.setattr(tab, "export_issue_overrides", lambda: None, raising=False)
        monkeypatch.setattr(tab, "export_rollback_overrides", lambda: rollback, raising=False)
        monkeypatch.setattr(tab, "projection_months", lambda _policy: 2, raising=False)
        monkeypatch.setattr(tab, "projection_duration_label", lambda _policy: "for 2 months", raising=False)
        monkeypatch.setattr(tab, "export_options", lambda: IllustrationOptions(), raising=False)
        monkeypatch.setattr(tab, "stop_on_lapse_enabled", lambda: True, raising=False)
        monkeypatch.setattr(tab, "abr_quote_enabled", lambda: case["name"] == "abr-solve", raising=False)
        monkeypatch.setattr(tab, "abr_minimum_face_amount", lambda: 75_000.0, raising=False)
        monkeypatch.setattr(tab, "lumpsum_to_next_enabled", lambda: case["name"] == "lumpsum-next-premium", raising=False)
        monkeypatch.setattr(tab, "min_level_request", lambda: {"mode": "M", "start_year": 7} if case["name"] == "min-level" else None, raising=False)
        monkeypatch.setattr(tab, "max_level_request", lambda: {"mode": "M", "start_year": 7} if case["name"] == "max-level" else None, raising=False)
        monkeypatch.setattr(tab, "shadow_level_request", lambda: {"mode": "M", "start_year": 7} if case["name"] == "shadow-level" else None, raising=False)
        monkeypatch.setattr(tab, "solve_request", lambda: {
            "target": "sv",
            "amount": 20_000.0,
            "at_age": 70,
            "mode": "M",
            "start_year": 7,
            "end_year": 12,
        } if case["name"] == "target-solve" else None, raising=False)
        monkeypatch.setattr(tab, "solve_duration_request", lambda: {
            "premium": 333.33,
            "target": "sv",
            "amount": 20_000.0,
            "at_age": 70,
            "mode": "M",
            "start_year": 7,
        } if case["name"] == "duration-solve" else None, raising=False)
        monkeypatch.setattr(tab, "loan_payoff_requests", lambda: [{
            "dates": [date(2026, 10, 15), date(2026, 11, 15)],
            "check_date": date(2026, 11, 15),
        }] if case["name"] == "loan-payoff" else [], raising=False)
        monkeypatch.setattr(tab, "set_lumpsum_amount", lambda value: solved.__setitem__("lumpsum", value), raising=False)
        monkeypatch.setattr(tab, "set_max_level_amount", lambda value: solved.__setitem__("max_level", value), raising=False)
        monkeypatch.setattr(tab, "set_min_level_amount", lambda value: solved.__setitem__("min_level", value), raising=False)
        monkeypatch.setattr(tab, "set_shadow_level_amount", lambda value: solved.__setitem__("shadow_level", value), raising=False)
        monkeypatch.setattr(tab, "set_solve_amount", lambda value: solved.__setitem__("target", value), raising=False)
        monkeypatch.setattr(tab, "set_solve_duration", lambda value: solved.__setitem__("duration", value), raising=False)
        monkeypatch.setattr(tab, "set_loan_payoff_amounts", lambda value: solved.__setitem__("loan_payoff", list(value)), raising=False)


def _install_flow_stubs(monkeypatch, case: dict, calls: list[str]):
    from suiteview.illustration.core import run_service

    monkeypatch.setattr(
        "suiteview.illustration.ui.main_window.PolicyInformation",
        lambda *_args, **_kwargs: _LoadedPolicy(),
    )
    monkeypatch.setattr("suiteview.illustration.ui.main_window.DB2Connection", _NoDb)

    def project(policy_or_number, **kwargs):
        calls.append(f"project:{kwargs.get('months')}")
        if kwargs.get("months") == 0:
            return SimpleNamespace(policy=deepcopy(_base_policy()), states=[])
        return SimpleNamespace(policy=policy_or_number, states=_current_states())

    monkeypatch.setattr(run_service, "project_policy", project)

    def scenario(policy_data, **kwargs):
        calls.append("scenario")
        if case["name"] == "shadow-level":
            policy_data.ccv_active = True
        return SimpleNamespace(
            projectable_policy=policy_data,
            future_inputs=kwargs["future_inputs"],
            inforce_overrides=kwargs.get("inforce_overrides"),
            run_from_issue=kwargs.get("run_from_issue", False),
        )

    monkeypatch.setattr(run_service, "build_illustration_scenario", scenario)

    def fixed_report(policy, results, **kwargs):
        calls.append("report")
        kwargs["run_date"] = date(2026, 9, 26)
        return build_ul_report(policy, results, **kwargs)

    monkeypatch.setattr(run_service, "build_ul_report", fixed_report)

    def guaranteed(policy, results, **_kwargs):
        calls.append("guaranteed")
        return _guaranteed_states() if case["name"] == "guaranteed-projection" else None

    monkeypatch.setattr(run_service, "run_guaranteed_projection", guaranteed)

    from suiteview.illustration.ui import report_tab

    monkeypatch.setattr(
        run_service,
        "run_abr_quote",
        lambda policy, **_kwargs: SimpleNamespace(
            policy=policy,
            results=_current_states(),
            premium=1234.56,
            illustrated_rate=0.045,
            premium_basis="SV",
            max_partial=SimpleNamespace(
                monthly_deduction=88.88,
                monthly_deduction_date=date(2026, 10, 15),
            ),
        ),
    )
    monkeypatch.setattr(
        report_tab,
        "format_abr_quote_pages",
        lambda abr, _policy: [["ABR GOLDEN", f"premium={abr.premium:,.2f}"]],
    )
    monkeypatch.setattr(
        run_service,
        "solve_lumpsum_to_next_premium",
        lambda *_args, **_kwargs: SimpleNamespace(
            lumpsum=321.09,
            forecast_date=date(2026, 10, 15),
            next_premium_date=date(2026, 11, 15),
            binding_reason="SV",
            guideline_limited=False,
            applied=321.09,
        ),
    )
    monkeypatch.setattr(
        run_service,
        "solve_max_level_allowed",
        lambda *_args, **_kwargs: SimpleNamespace(premium=444.44, mode="M"),
    )
    monkeypatch.setattr(
        run_service,
        "solve_level_to_exception",
        lambda *_args, **kwargs: SimpleNamespace(
            premium=333.33 if kwargs.get("allow_exceptions") is False else 222.22,
            mode="M",
        ),
    )
    monkeypatch.setattr(
        run_service,
        "level_to_exception_options",
        lambda options, *_args, **_kwargs: options,
    )
    monkeypatch.setattr(
        run_service,
        "solve_premium_to_target",
        lambda *_args, **_kwargs: SimpleNamespace(
            premium=555.55,
            mode="M",
            target="sv",
            achieved_value=20_100.0,
            at_age=70,
        ),
    )
    monkeypatch.setattr(
        run_service,
        "solve_premium_duration",
        lambda *_args, **_kwargs: SimpleNamespace(
            premium=333.33,
            mode="M",
            duration_years=5,
            end_policy_year=11,
            target="sv",
            achieved_value=20_050.0,
            reached_target=True,
            at_age=70,
        ),
    )
    monkeypatch.setattr(
        run_service,
        "solve_loan_payoff",
        lambda *_args, **_kwargs: SimpleNamespace(repayment=66.66),
    )


FLOW_CASES = [
    {"name": "plain-run"},
    {"name": "abr-solve"},
    {"name": "lumpsum-next-premium"},
    {"name": "max-level"},
    {"name": "min-level"},
    {"name": "shadow-level"},
    {"name": "target-solve"},
    {"name": "duration-solve"},
    {"name": "loan-payoff"},
    {"name": "guaranteed-projection"},
    {"name": "rollback-basis"},
    {"name": "snapshot-case"},
]


def _run_flow_case(monkeypatch, case: dict) -> dict:
    _app()
    calls: list[str] = []
    _install_flow_stubs(monkeypatch, case, calls)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok)
    window = IllustrationWindow()
    solved: dict = {}
    statuses: list[str] = []
    original_status = window._show_status

    def record_status(message: str):
        statuses.append(message)
        original_status(message)

    monkeypatch.setattr(window, "_show_status", record_status)
    monkeypatch.setattr(window.policy_tab, "has_pending_record_changes", lambda: False)
    _InputsHarness(window.inputs_tab, case, solved).install(monkeypatch)
    if case["name"] == "snapshot-case":
        policy = _base_policy()
        policy.policy_number = "USNAP001"
        window._snapshot_case = SimpleNamespace(
            policy_number="USNAP001",
            region="CKPR",
            company_code="01",
            policy_snapshot=policy,
            name="Golden Snapshot",
            saved_at=datetime(2026, 9, 20, 14, 5),
        )
    else:
        window._policy = _LoadedPolicy()
        window._policy_info = {
            "PolicyNumber": "UGOLD001",
            "Region": "CKPR",
            "CompanyCode": "01",
        }
        window._current_region = "CKPR"
        window._illustration_data = _base_policy()

    try:
        window._on_run_values()
        current_view = window.values_tab._current_view
        if current_view is None:
            projection_summary = {}
        else:
            _policy, results, months, _injected = current_view
            final = results[-1]
            projection_summary = {
                "months": months,
                "rows": len(results),
                "final_year": final.policy_year,
                "final_av": final.av_end_of_month,
                "final_sv": final.ending_sv,
            }
        report_state = window.report_tab.capture_session_state()
        if report_state and report_state.get("kind") == "abr":
            report_pages = report_state["pages"]
        elif report_state and report_state.get("report") is not None:
            report_pages = format_report_pages(report_state["report"])
        else:
            report_pages = []
        summary_grid = window.values_tab._tab_grids["Summary"]
        summary_rows = (
            summary_grid.df.astype(object).where(summary_grid.df.notna(), None).to_dict("records")
            if summary_grid.model is not None
            else []
        )
        return {
            "calls": calls,
            "projection": projection_summary,
            "solved_inputs": solved,
            "status_messages": statuses,
            "report_status": window.report_tab.status_label.text(),
            "report_pages": report_pages,
            "summary_rows": summary_rows,
        }
    finally:
        window.close()


def _assert_or_update(path: Path, actual):
    actual = json.loads(json.dumps(actual, sort_keys=True, default=str))
    if os.environ.get("SV_UPDATE_ILLUSTRATION_GOLDENS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected


@pytest.mark.parametrize("case", FLOW_CASES, ids=[case["name"] for case in FLOW_CASES])
def test_run_values_flow_offline_golden(monkeypatch, case):
    actual = _run_flow_case(monkeypatch, case)
    golden_path = GOLDEN_DIR / f"{case['name']}.json"
    _assert_or_update(golden_path, actual)


def test_report_and_ledger_component_golden():
    policy = _base_policy()
    results = _current_states()
    future_inputs = IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.PREMIUM,
                policy_year=7,
                amount=125.0,
                mode="M",
            ),
            ScheduledTransaction(
                kind=TransactionKind.LOAN,
                policy_year=8,
                amount=1_000.0,
                mode="A",
                metadata={"loan_type": "fixed"},
            ),
        ],
        dated_transactions=[
            DatedTransaction(
                kind=TransactionKind.WITHDRAWAL,
                effective_date=date(2026, 10, 15),
                amount=250.0,
            )
        ],
    )
    report = build_ul_report(
        policy,
        results,
        future_inputs=future_inputs,
        run_date=date(2026, 9, 26),
        guaranteed_results=_guaranteed_states(),
    )
    ledger_cells = monthly_ledger_cells(results[1], results[0].withdrawals_to_date)
    actual = {
        "request_lines": _request_lines(policy, results, future_inputs),
        "report": {
            "policy_number": report.policy_number,
            "ledger": [row.__dict__ for row in report.ledger],
            "has_guaranteed_values": report.has_guaranteed_values,
            "page_count": len(format_report_pages(report)),
            "pages": format_report_pages(report),
        },
        "ledger_columns": LEDGER_COLUMNS,
        "monthly_ledger_cells": ledger_cells,
    }
    _assert_or_update(COMPONENT_GOLDEN, actual)
