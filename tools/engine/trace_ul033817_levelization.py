r"""Trace the live UL033817 off-anniversary 7-Pay levelization case.

Loads live policy and rates data, configures the real Illustration inputs UI
with a $1,200 monthly INPUT premium and a forecast-date DB Option B-to-A
change, then projects through the next policy anniversary.

Usage:
    venv\Scripts\python.exe tools\trace_ul033817_levelization.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def main() -> int:
    from PyQt6.QtWidgets import QApplication

    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import (
        build_illustration_data,
    )
    from suiteview.illustration.core.input_compiler import compile_month_inputs
    from suiteview.illustration.core.scenario_builder import build_illustration_scenario
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

    app = QApplication.instance() or QApplication(sys.argv)
    policy = build_illustration_data("UL033817", region="CKPR")

    inputs_tab = IllustrationInputsTab()
    inputs_tab.load_data_from_policy(policy)
    panel = inputs_tab.dynamic_panel
    forecast_year = panel._ctx.forecast_year

    premium_row = panel.premium_section.rows()[0]
    premium_row.type_combo.setCurrentText("INPUT")
    premium_row.year_edit.set_value(forecast_year)
    premium_row._year_edited()
    premium_row.amount_edit.setText("1200.00")
    premium_row.mode_combo.setCurrentText("M")

    dbo_rows = panel.dbo_section.rows()
    dbo_row = dbo_rows[0] if dbo_rows else panel.dbo_section.add_row()
    dbo_row.year_edit.set_value(forecast_year)
    dbo_row._year_edited()
    dbo_row.value_combo.setCurrentIndex(dbo_row.value_combo.findData("A"))

    panel.tamra_check.setChecked(True)
    app.processEvents()

    input_set = inputs_tab.export_input_set()
    options = inputs_tab.export_options()
    scenario = build_illustration_scenario(
        policy,
        inforce_overrides=inputs_tab.export_inforce_overrides(),
        future_inputs=input_set,
    )
    compiled = compile_month_inputs(scenario.projectable_policy, input_set, 18)
    projected = IllustrationEngine().project(
        scenario.projectable_policy,
        months=18,
        future_inputs=input_set,
        options=options,
        stop_on_lapse=False,
    )

    traces = []
    for row in projected:
        detail = row.premium_allowance_detail
        traces.append({
            "date": row.date,
            "policy_year": row.policy_year,
            "policy_month": row.policy_month,
            "db_option": row.db_option,
            "requested_premium": row.requested_premium,
            "unscheduled_premium": row.unscheduled_premium,
            "gross_premium": row.gross_premium,
            "tamra_start_date": row.tamra_7pay_start_date,
            "tamra_year": row.tamra_year,
            "tamra_month": row.tamra_month_of_year,
            "payments_policy_year": row.payment_count_policy_year,
            "payments_tamra_year": row.payment_count_tamra_year,
            "nr_tamra_boy": detail.get("TAMRA_Level_Allowance_BOY"),
            "ns_tamra_eoy": detail.get("TAMRA_Level_Allowance_EOY"),
            "nu_guideline": detail.get("GP_Level_Allowance"),
            "nv_scheduled_cap": row.scheduled_prem_cap,
            "nw_levelized_max": row.levelized_max_premium,
            "nx_apply_levelized": row.apply_levelized,
            "nz_applied_scheduled": row.applied_scheduled_premium,
            "capped_by_tamra": row.premium_capped_by_tamra,
            "capped_by_guideline": row.premium_capped_by_guideline,
        })

    compiled_trace = []
    for duration, month in compiled.items():
        if month.total_premium is None:
            continue
        compiled_trace.append({
            "duration": duration,
            "scheduled_premium": month.scheduled_premium,
            "unscheduled_premium": month.unscheduled_premium,
            "mode": month.premium_mode,
        })

    output = {
        "policy": {
            "number": policy.policy_number,
            "valuation_date": policy.valuation_date,
            "issue_date": policy.issue_date,
            "policy_year": policy.policy_year,
            "policy_month": policy.policy_month,
            "db_option": policy.db_option,
            "seven_pay_premium": policy.tamra_7pay_level,
            "seven_pay_start_date": policy.tamra_7pay_start_date,
        },
        "ui": {
            "forecast_date": panel._ctx.forecast_date,
            "forecast_year": forecast_year,
            "conform_to_tamra": options.conform_to_tamra,
            "levelizing_premium": options.levelizing_premium,
        },
        "input_set": asdict(input_set),
        "compiled_premiums": compiled_trace,
        "projection": traces,
    }
    print(json.dumps(output, default=_json_default, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
