"""Verify Include Prem after Val date on a live policy through Run Values, read-only.

Usage: venv\\Scripts\\python.exe tools\\app\\verify_premiums_after_valuation.py <policy> [company]
       [--months 24] [--synthetic YYYY-MM-DD:GROSS:NET] [--screenshot-dir DIR]

Loads the live policy, prints the premiums received after its valuation date (FH_FIXED,
pending), then runs ``execute_run`` twice - with and without the option - billing the
modal premium, and prints the starting values, the first projected months and the
report's cover disclosure. ``--screenshot-dir`` also drives the real window (Policy tab
before/after the option, then Run Values and the Report tab). Nothing is written to DB2.
Example with a pending receipt: UE000576 (10/04/2026 PR after the 09/27/2026 valuation).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.local_dev import local_data_enabled

_MODE = {1: "M", 3: "Q", 6: "S", 12: "A"}


def _run(policy, include: bool, months: int):
    from suiteview.illustration.core.run_service import (
        PolicyBasis, RunControls, RunRequest, SolveRequestSet, execute_run,
    )
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, IllustrationOptions, ScheduledTransaction, TransactionKind,
    )

    mode = _MODE.get(int(policy.billing_frequency or 1), "M")
    inputs = IllustrationInputSet(scheduled_transactions=[ScheduledTransaction(
        TransactionKind.PREMIUM, policy.policy_year, float(policy.modal_premium), mode=mode)])
    return execute_run(RunRequest(
        basis=PolicyBasis(policy.policy_number, company_code=policy.company_code, policy_data=policy),
        inputs=inputs,
        controls=RunControls(options=IllustrationOptions(), projection_months=months,
                             duration_label=f"for {months} months", stop_on_lapse=False),
        solves=SolveRequestSet(),
        include_premiums_after_valuation=include,
    ))


def _starting(policy) -> dict:
    from suiteview.illustration.core.premiums_after_valuation import net_premiums_after_valuation

    included = policy.premiums_after_valuation_included
    return {
        "account_value": policy.account_value,
        "shadow_account_value": policy.shadow_account_value,
        "net_credited_on_forecast_date": net_premiums_after_valuation(policy) if included else 0.0,
        "shadow_net_credited_on_forecast_date": policy.premiums_after_valuation_shadow_net,
        "premiums_paid_to_date": policy.premiums_paid_to_date,
        "premiums_ytd": policy.premiums_ytd,
        "cost_basis": policy.cost_basis,
        "tamra_7year_contributions": policy.tamra_7year_contributions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy")
    parser.add_argument("company", nargs="?")
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument(
        "--synthetic", metavar="YYYY-MM-DD:GROSS:NET",
        help="replace the captured receipts with one hypothetical receipt (exercises the "
             "shadow load on real plan rates when no live policy has a pending premium)")
    parser.add_argument("--screenshot-dir", type=Path,
                        help="also capture the native window before/after the option and its report")
    args = parser.parse_args()
    if local_data_enabled():
        raise RuntimeError("This helper reads live data only.")
    from datetime import date

    from suiteview.illustration.api import load_policy_data
    from suiteview.illustration.models.policy_data import PremiumAfterValuation

    policy = load_policy_data(args.policy, company_code=args.company)
    if args.synthetic:
        when, gross, net = args.synthetic.split(":")
        policy.premiums_after_valuation = [
            PremiumAfterValuation(date.fromisoformat(when), float(gross), float(net), "SYNTHETIC")]
        policy.premiums_after_valuation_error = ""
    print(json.dumps({
        "policy": policy.policy_number, "plancode": policy.plancode,
        "valuation_date": policy.valuation_date, "has_shadow": policy.has_shadow_account,
        "premiums_after_valuation": policy.premiums_after_valuation,
        "unavailable": policy.premiums_after_valuation_error,
    }, default=str, indent=1))
    if policy.premiums_after_valuation_error or not policy.premiums_after_valuation:
        return 1
    for include in (False, True):
        result = _run(policy, include, args.months)
        start = result.scenario.projectable_policy
        print(f"\n=== include_premiums_after_valuation={include} ===")
        print(json.dumps(_starting(start), default=str))
        for state in result.current[: 4]:
            print(f"{state.date}  prem {state.gross_premium:>10,.2f}"
                  f"  AV {state.av_end_of_month:>12,.2f}"
                  f"  shadow {getattr(state, 'shadow_eav', 0.0) or 0.0:>12,.2f}")
        report = result.report.report
        print("AV basis:", report.av_basis_line)
        for line in report.policy_status_lines:
            print("STATUS:", line)
        print("STATUS BAR:", result.status)
        if result.report.guaranteed_error:
            print("GUARANTEED ERROR:", result.report.guaranteed_error)
    if args.screenshot_dir:
        _capture_window(policy, args.screenshot_dir)
    return 0


def _capture_window(policy, folder: Path) -> None:
    """Drive the real RERUN window: Policy tab off/on, then Run Values and the Report."""
    from unittest.mock import patch

    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from suiteview.illustration.ui.main_window import IllustrationWindow
    from suiteview.polview.services.policy_service import get_policy_info

    folder.mkdir(parents=True, exist_ok=True)
    pi = get_policy_info(policy.policy_number, company_code=policy.company_code)
    app = QApplication.instance() or QApplication([])
    window = IllustrationWindow()
    window._illustration_data = policy
    window._policy = pi
    window._policy_info = {
        "PolicyNumber": policy.policy_number, "CompanyCode": policy.company_code,
        "Region": policy.region,
    }
    window.lookup_bar.set_policy_display(policy.company_code, policy.policy_number, policy.region)
    window.policy_tab.load_data_from_policy(pi, window._policy_info)
    window.inputs_tab.load_data_from_policy(policy)
    window._set_active_inputs_tab(window.inputs_tab)
    window._refresh_rollback_controls()
    window._refresh_policy_basis()
    window.resize(1220, 900)
    window.show()

    def capture(name):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        path = folder / name
        if not window.grab().save(str(path), "PNG"):
            raise RuntimeError(f"Could not capture {path}")
        print("captured", path)

    window.tabs.setCurrentWidget(window.policy_tab)
    capture("1_policy_option_off.png")
    window.include_premiums_check.setChecked(True)
    capture("2_policy_option_on.png")
    with patch.object(QMessageBox, "information"), patch.object(QMessageBox, "warning"), \
            patch.object(QMessageBox, "critical"):
        window._on_run_values()
    window.tabs.setCurrentWidget(window.report_tab)
    capture("3_report_option_on.png")
    print("status:", window._status_label.text())
    window.close()


if __name__ == "__main__":
    raise SystemExit(main())
