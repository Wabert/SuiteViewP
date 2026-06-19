r"""Inspect live illustration premium caps for one policy.

Usage:
    venv\Scripts\python.exe tools/inspect_live_premium_caps.py --policy U0136726 --region CKPR --max-level
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("SUITEVIEW_LOCAL_DATA", None)

from PyQt6.QtWidgets import QApplication

from suiteview.core.policy_service import clear_cache, get_policy_info
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect live premium capping for a policy.")
    parser.add_argument("--policy", required=True, help="Policy number")
    parser.add_argument("--region", default="CKPR", help="DB2 region code")
    parser.add_argument("--company", default=None, help="Optional company code")
    parser.add_argument("--max-level", action="store_true", help="Use the dynamic Max Level premium row")
    parser.add_argument("--months", type=int, default=None, help="Projection months; defaults to maturity")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    app = QApplication.instance() or QApplication([])

    clear_cache()
    policy_info = get_policy_info(args.policy, args.region, args.company, use_cache=False)
    if policy_info is None or not getattr(policy_info, "exists", False):
        raise SystemExit(f"Policy not found: {args.policy}")

    company = getattr(policy_info, "company_code", None)
    policy_data = build_illustration_data(args.policy, region=args.region, company_code=company)

    tab = IllustrationInputsTab()
    tab.load_data_from_policy(policy_info)
    if args.max_level:
        row = tab.dynamic_panel.premium_section.rows()[0]
        row.type_combo.setCurrentText("Max Level")

    future_inputs = tab.export_input_set()
    scenario = build_illustration_scenario(
        policy_data,
        inforce_overrides=tab.export_inforce_overrides(),
        future_inputs=future_inputs,
    )
    months = args.months if args.months is not None else tab._months_to_maturity(scenario.projectable_policy)
    options = tab.export_options()

    states = IllustrationEngine().project(
        scenario.projectable_policy,
        months=months,
        future_inputs=scenario.future_inputs,
        options=options,
        stop_on_lapse=False,
    )

    capped = [state for state in states[1:] if state.premium_capped]
    premium_rows = [state for state in states[1:] if state.requested_premium or state.gross_premium]
    first_capped = capped[0] if capped else None

    def row(state) -> dict:
        guideline_room = state.guideline_limit - (state.premiums_to_date - state.gross_premium)
        tamra_room = None
        if state.tamra_year <= 7 and state.tamra_7pay_level > 0:
            tamra_room = state.tamra_7pay_level * state.tamra_year - state.amount_in_7pay
        return {
            "date": str(state.date),
            "policy_year": state.policy_year,
            "policy_month": state.policy_month,
            "attained_age": state.attained_age,
            "requested_premium": state.requested_premium,
            "gross_premium": state.gross_premium,
            "premium_cap": state.premium_cap,
            "premium_capped": state.premium_capped,
            "glp": state.glp,
            "accumulated_glp": state.accumulated_glp,
            "gsp": state.gsp,
            "guideline_limit": state.guideline_limit,
            "guideline_room_before_premium": guideline_room,
            "tamra_year": state.tamra_year,
            "tamra_7pay_level": state.tamra_7pay_level,
            "amount_in_7pay": state.amount_in_7pay,
            "tamra_room_before_premium": tamra_room,
            "premiums_to_date_after": state.premiums_to_date,
            "annual_interest_rate": state.annual_interest_rate,
            "bonus_interest_rate": state.bonus_interest_rate,
            "effective_annual_rate": state.effective_annual_rate,
            "interest_credited": state.interest_credited,
        }

    window = []
    if first_capped is not None:
        first_index = states.index(first_capped)
        start = max(1, first_index - 4)
        end = min(len(states), first_index + 8)
        window = [row(state) for state in states[start:end]]

    result = {
        "policy": args.policy,
        "company": company,
        "mode": "max_level" if args.max_level else "default_inputs",
        "valuation_date": str(policy_data.valuation_date),
        "issue_age": policy_data.issue_age,
        "attained_age": policy_data.attained_age,
        "maturity_age": policy_data.maturity_age,
        "modal_premium": policy_data.modal_premium,
        "tamra_7pay_start_date": str(policy_data.tamra_7pay_start_date),
        "tamra_7pay_level": policy_data.tamra_7pay_level,
        "tamra_7year_contributions": policy_data.tamra_7year_contributions,
        "states": len(states),
        "premium_months": len(premium_rows),
        "capped_months": len(capped),
        "first_capped": row(first_capped) if first_capped is not None else None,
        "first_bonus_rows": [row(state) for state in states[1:] if state.bonus_interest_rate > 0.0][:8],
        "last_premium_rows": [row(state) for state in premium_rows[-8:]],
        "first_capped_window": window,
        "options": {
            "conform_to_tefra": options.conform_to_tefra,
            "conform_to_tamra": options.conform_to_tamra,
            "cap_premiums_at_acceptance": options.cap_premiums_at_acceptance,
        },
    }
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()