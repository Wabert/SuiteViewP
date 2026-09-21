"""Read-only revised Case9 check against current source, never a frozen runtime."""

import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = {"source_root": str(ROOT), "checks": {}}
    checks = report["checks"]
    with TemporaryDirectory(prefix="suiteview-case9-") as temp:
        os.environ["SUITEVIEW_PROFILE_DIR"] = temp
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from dateutil.relativedelta import relativedelta
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from suiteview.core.rates import owned_rate_connections
        from suiteview.illustration.core.compare_runner import run_scenario
        from suiteview.illustration.core.guaranteed_projection import lock_values
        from suiteview.illustration.core.input_compiler import compile_month_inputs
        from suiteview.illustration.models import case_bundle, case_store, imported_case_store
        from suiteview.illustration.models.input_set import TransactionKind
        from suiteview.illustration.ui import inputs_dynamic
        from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab
        from suiteview.illustration.ui.main_window import IllustrationWindow
        from suiteview.illustration.ui.saved_case_scenario import (
            build_spec_from_tab, materialize_saved_case,
        )

        app = QApplication.instance() or QApplication([])
        source = Path(inputs_dynamic.__file__).resolve()
        assert source.is_relative_to(ROOT)
        report["dynamic_source"] = str(source)
        report["dynamic_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        policy = case_store.decode_policy_snapshot(json.loads(args.snapshot.read_text(encoding="utf-8")))
        original_policy = deepcopy(policy)
        assert (
            policy.policy_number, policy.company_code, policy.plancode, policy.rate_sex,
            policy.rate_class, policy.db_option, policy.face_amount, policy.issue_date,
            policy.issue_age, policy.valuation_date, policy.account_value,
        ) == (
            "U0389725", "01", "1U135P00", "F", "N", "A", 48172, date(2000, 4, 6),
            43, date(2026, 9, 6), 4448.56,
        )
        tab = IllustrationInputsTab()
        window = None
        try:
            tab.load_data_from_policy(
                policy, has_shadow=policy.has_shadow_account, shadow_ceased=policy.ccv_ceased,
            )
            state = tab.dynamic_panel.capture_state()
            state["apply_prem_to_loan"] = True
            state["sections"]["premiums"] = [
                {"type": "INPUT", "year": "27", "amount": "56", "mode": "M", "for_years": "3"},
                {"type": "Prem to Maturity", "year": "30", "mode": "M"},
            ]
            state["sections"]["face"] = [
                {"type": "Input", "year": "28", "amount": "25000"},
            ]
            state["sections"]["loans"] = [
                {"type": "Input", "year": "29", "amount": "1000", "mode": "A", "for_years": "1"},
            ]
            assert tab.dynamic_panel.apply_state(state) == []
            checks["dynamic_loan_enabled"] = tab.dynamic_panel.loan_section.isEnabled()
            spec = build_spec_from_tab("Case9 revised", tab, policy)
            checks["solve_start_and_option"] = (
                spec.min_level == {"start_year": 30, "mode": "M"}
                and spec.options.apply_prem_to_loan
            )
            months = compile_month_inputs(policy, spec.scenario.future_inputs, 306)
            dated = {
                policy.issue_date + relativedelta(months=duration - 1): value
                for duration, value in months.items()
            }
            loans = {str(when): c.regular_loan for when, c in dated.items() if c.regular_loan}
            checks["one_loan_then_zero_to_maturity"] = loans == {"2028-04-06": 1000}
            checks["billed_56_through_march_2029"] = [
                c.scheduled_premium for when, c in dated.items() if when < date(2029, 4, 6)
            ] == [56] * 30
            captured = tab.capture_case_inputs()
            case_store.save_case(
                "Case9 revised", policy_number=policy.policy_number, company_code="01",
                region="CKPR", inputs=captured, policy_snapshot=policy,
                directory=Path(temp) / "saved",
            )
            saved = case_store.load_case("Case9 revised", directory=Path(temp) / "saved")
            exported = case_bundle.write_bundle(Path(temp) / "export", [saved])
            bundle = case_bundle.read_bundle(exported)
            assert not bundle.errors
            imported_bundle = imported_case_store.save_imported_bundle(
                "Case9", bundle.cases, directory=Path(temp) / "imported",
            )
            imported = imported_case_store.load_imported_case(imported_bundle.path, saved.name)
            for name, case in (("saved", saved), ("exported", bundle.cases[0]), ("imported", imported)):
                rebuilt = materialize_saved_case(case, strict=True)
                checks[name + "_exact_roundtrip"] = (
                    case.inputs == captured and case.policy_snapshot == policy
                    and rebuilt.scenario.future_inputs == spec.scenario.future_inputs
                    and rebuilt.options == spec.options and rebuilt.min_level == spec.min_level
                )
            report["future_inputs"] = asdict(spec.scenario.future_inputs)
            report["compiled_nonzero_loans"] = loans
            report["min_level"] = spec.min_level
            messages = []

            def message(_parent, title, text, *args):
                messages.append(f"{title}: {text}")
                return QMessageBox.StandardButton.Ok

            with (owned_rate_connections(),
                  patch.object(QMessageBox, "information", message),
                  patch.object(QMessageBox, "warning", message),
                  patch.object(QMessageBox, "critical", message)):
                # Real native Run Values, with a frozen policy but changed source.
                window = IllustrationWindow()
                window._load_case_snapshot(imported)
                window._on_run_values()
                assert window.values_tab._current_view is not None, messages
                current = window.values_tab._current_view[1]
                assert window.values_tab._guaranteed_view is not None, messages
                guaranteed = window.values_tab._guaranteed_view[1]
                native_premium = window.inputs_tab.dynamic_panel.premium_section.rows()[1].amount()
                comparison = run_scenario(materialize_saved_case(imported, strict=True))
                checks["native_and_saved_runner_match"] = current == comparison.results
                checks["independent_solve_matches_native"] = (
                    native_premium == comparison.solved["min_level"]
                )
                checks["current_reaches_maturity"] = (
                    current[-1].attained_age >= policy.maturity_age
                    and not any(s.lapsed for s in current if s.attained_age < policy.maturity_age)
                )
                applied_loans = {
                    str(s.date): s.applied_new_loan for s in current[1:] if s.applied_new_loan
                }
                checks["current_applies_exactly_one_1000_loan"] = applied_loans == loans
                checks["premiums_repay_loan"] = sum(s.loan_repay_from_prem for s in current) > 0
                locked = lock_values(comparison.policy, current, comparison.future_inputs)
                locked_loans = {
                    str(t.effective_date): t.amount for t in locked.dated_transactions
                    if t.kind == TransactionKind.LOAN
                }
                checks["guaranteed_locks_current_loan"] = locked_loans == loans
                checks["guaranteed_applies_locked_loan"] = {
                    str(s.date): s.applied_new_loan for s in guaranteed[1:] if s.applied_new_loan
                } == loans
                without_loan = deepcopy(spec)
                without_loan.scenario.future_inputs.scheduled_transactions = [
                    t for t in without_loan.scenario.future_inputs.scheduled_transactions
                    if t.kind != TransactionKind.LOAN
                ]
                no_loan = run_scenario(without_loan)
                checks["solve_reflects_requested_loan"] = (
                    no_loan.solved["min_level"] != comparison.solved["min_level"]
                )
                report.update(
                    solved_monthly_premium=native_premium,
                    independently_solved_monthly_premium=comparison.solved["min_level"],
                    no_loan_solved_monthly_premium=no_loan.solved["min_level"],
                    applied_current_loans=applied_loans,
                    current_months=len(current) - 1,
                    current_last_date=str(current[-1].date),
                    current_last_age=current[-1].attained_age,
                    current_terminal_lapsed=current[-1].lapsed,
                    current_terminal_matured=current[-1].matured,
                    guaranteed_months=len(guaranteed) - 1,
                    guaranteed_last_date=str(guaranteed[-1].date),
                    guaranteed_lapsed=guaranteed[-1].lapsed,
                    no_loan_terminal_lapsed=no_loan.results[-1].lapsed,
                    no_loan_terminal_age=no_loan.results[-1].attained_age,
                    native_messages=messages,
                )
                checks["no_native_errors"] = not messages
                checks["snapshot_unchanged"] = policy == original_policy
        finally:
            tab.deleteLater()
            if window is not None:
                window.close()
                window.deleteLater()
            app.processEvents()
    report["all_ok"] = all(checks.values())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
