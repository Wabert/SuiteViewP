r"""Inspect monthly premium levelization for one illustration policy.

Usage:
    venv\Scripts\python.exe tools\engine\check_premium_levelization.py UE000032 19.21
    venv\Scripts\python.exe tools\engine\check_premium_levelization.py UE006519 37.12 --native --year 12 --expect-level

Live policy/rate access is read-only. Native verification saves its temporary
case in an isolated profile and compares Run Values with saved-case Compare.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def native_projection(policy, mode):
    """Exercise Run Values and saved-case Compare against one live snapshot."""
    from copy import deepcopy
    from unittest.mock import patch

    from PyQt6.QtWidgets import QApplication, QMessageBox
    from suiteview.core.rates import owned_rate_connections
    from suiteview.illustration.core.compare_runner import run_scenario
    from suiteview.illustration.models import case_store
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab
    from suiteview.illustration.ui.main_window import IllustrationWindow
    from suiteview.illustration.ui.saved_case_scenario import materialize_saved_case

    app = QApplication.instance() or QApplication([])
    original = deepcopy(policy)
    tab = IllustrationInputsTab()
    window = None
    messages = []

    def message(_parent, title, text, *args):
        messages.append(f"{title}: {text}")
        return QMessageBox.StandardButton.Ok

    try:
        tab.load_data_from_policy(
            policy, has_shadow=policy.has_shadow_account, shadow_ceased=policy.ccv_ceased,
        )
        state = tab.dynamic_panel.capture_state()
        state["sections"]["premiums"] = [{
            "type": "Prem to Maturity", "year": str(policy.duration // 12 + 1), "mode": mode,
        }]
        assert tab.dynamic_panel.apply_state(state) == []
        tab.levelizing_check.setChecked(True)
        saved = case_store.save_case(
            "Levelization verification", policy_number=policy.policy_number,
            company_code=policy.company_code, region=policy.region,
            inputs=tab.capture_case_inputs(), policy_snapshot=policy,
        )
        restored = case_store.load_case(saved.name)
        with (owned_rate_connections(),
              patch.object(QMessageBox, "information", message),
              patch.object(QMessageBox, "warning", message),
              patch.object(QMessageBox, "critical", message)):
            window = IllustrationWindow()
            window._load_case_snapshot(restored)
            window._on_run_values()
            assert not messages, messages
            assert window.values_tab._current_view is not None
            assert window.values_tab._guaranteed_view is not None
            states = window.values_tab._current_view[1]
            comparison = run_scenario(materialize_saved_case(restored, strict=True))
            assert states == comparison.results, "Run Values and saved Compare differ."
            premium = window.inputs_tab.dynamic_panel.premium_section.rows()[0].amount()
            assert premium == comparison.solved["min_level"]
            assert policy == original
            assert states[-1].attained_age >= policy.maturity_age
            assert not any(s.lapsed for s in states if s.attained_age < policy.maturity_age)
            return states, premium
    finally:
        if window is not None:
            window.close()
        tab.close()
        app.processEvents()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("policy")
    parser.add_argument("premium", type=float)
    parser.add_argument("--company")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--mode", default="M", choices=("M", "Q", "S", "A"))
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--prem-to-maturity", action="store_true")
    parser.add_argument("--solve", action="store_true",
                        help="Solve Prem to Maturity instead of using the supplied premium.")
    parser.add_argument("--native", action="store_true",
                        help="Verify native Run Values and saved Compare with default UI assumptions.")
    parser.add_argument("--year", type=int, help="Only report this policy year.")
    parser.add_argument("--expect-level", action="store_true",
                        help="Require a complete year of equal nonzero modal payments.")
    parser.add_argument("--local-data", action="store_true")
    args = parser.parse_args()

    if args.local_data:
        os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import (
        build_illustration_data,
    )
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet,
        IllustrationOptions,
        ScheduledTransaction,
        TransactionKind,
    )
    from suiteview.illustration.core.solve_level_to_exception import (
        level_to_exception_options,
        solve_level_to_exception,
    )

    clear_cache()
    policy = build_illustration_data(
        args.policy,
        region=args.region,
        company_code=args.company,
    )
    forecast_year = (policy.duration // 12) + 1
    options = IllustrationOptions(levelizing_premium=True)
    premium = args.premium
    solved = None
    if args.solve and not args.native:
        solved = solve_level_to_exception(
            policy, mode=args.mode, start_policy_year=forecast_year,
            base_options=options,
        )
        premium = solved.premium
    if args.prem_to_maturity or args.solve:
        options = level_to_exception_options(
            options, allow_exceptions=not policy.is_cvat,
            conform_to_tamra=not policy.is_cvat,
        )
    inputs = IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.PREMIUM,
                policy_year=forecast_year,
                amount=premium,
                mode=args.mode,
            )
        ]
    )
    if args.native:
        states, premium = native_projection(policy, args.mode)
    else:
        states = IllustrationEngine().project(
            policy,
            months=None if args.solve else args.months,
            future_inputs=inputs,
            options=options,
            stop_on_lapse=args.solve,
        )
    if args.solve or args.native:
        assert states[-1].attained_age >= policy.maturity_age
        assert not any(s.lapsed for s in states if s.attained_age < policy.maturity_age)

    rows = []
    for state in states[1:]:
        if args.year is not None and state.policy_year != args.year:
            continue
        rows.append({
            "date": state.date.isoformat(),
            "policy_year": state.policy_year,
            "policy_month": state.policy_month,
            "requested": state.requested_premium,
            "applied": state.applied_scheduled_premium,
            "cap": state.scheduled_prem_cap,
            "gp_level_allowance": state.premium_allowance_detail.get(
                "GP_Level_Allowance"
            ),
            "payment_count": state.payment_count_policy_year,
            "levelized": state.apply_levelized,
            "transition_year": state.premium_allowance_detail["In Transition Year"],
            "exception_premium": state.gp_exception_prem_gross,
            "has_loan": (
                state.end_rg_loan_princ
                + state.end_rg_loan_accrued
                + state.end_pf_loan_princ
                + state.end_pf_loan_accrued
                + state.end_vbl_loan_princ
                + state.end_vbl_loan_accrued
            ) > 1e-9,
        })

    all_level = (
        len(rows) == 12
        and {row["policy_month"] for row in rows} == set(range(1, 13))
        and len({round(row["applied"], 8) for row in rows if row["requested"] > 0}) == 1
        and all(row["applied"] > 0 and row["levelized"]
                for row in rows if row["requested"] > 0)
        and any(row["requested"] > 0 for row in rows)
    )
    print(json.dumps({
        "policy": args.policy,
        "valuation_date": policy.valuation_date.isoformat(),
        "duration": policy.duration,
        "forecast_year": forecast_year,
        "input_premium": premium,
        "solved_ending_av": solved.ending_av if solved else None,
        "native_and_saved_compare_match": True if args.native else None,
        "projection_end_date": states[-1].date.isoformat(),
        "projection_end_age": states[-1].attained_age,
        "all_level": all_level,
        "rows": rows,
    }, indent=2))
    if args.expect_level and not all_level:
        raise AssertionError("Expected a complete year of equal nonzero levelized payments.")
    return 0


if __name__ == "__main__":
    with TemporaryDirectory(prefix="suiteview-levelization-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        raise SystemExit(main())
