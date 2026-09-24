"""Read-only live trace of target premiums before and after a face increase."""

import argparse
from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.core.summary_results import project_summary_row
from suiteview.illustration.core.target_premium import compute_target_premiums
from suiteview.illustration.models.input_set import (
    IllustrationInputSet, PolicyChangeEvent, PolicyChangeKind,
)
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.illustration.ui.values_tab import IllustrationValuesTab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--company")
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--face", required=True, type=float)
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--expect-monthly", type=float)
    parser.add_argument("--expect-loaded-match", action="store_true")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise ValueError("Live verification cannot use local policy data.")
    policy = build_illustration_data(args.policy, args.region, args.company)
    original = deepcopy(policy)
    if args.date <= policy.valuation_date:
        raise ValueError("The face change must follow the loaded valuation date.")
    if args.face <= policy.total_face:
        raise ValueError("The requested face must exceed the loaded face.")
    config = load_plancode(policy.plancode)
    inputs = IllustrationInputSet(policy_changes=[PolicyChangeEvent(
        kind=PolicyChangeKind.FACE_AMOUNT, effective_date=args.date, value=args.face,
    )])
    months = (
        (args.date.year - policy.valuation_date.year) * 12
        + args.date.month - policy.valuation_date.month + 2
    )
    before = compute_target_premiums(policy, config, as_of=policy.valuation_date)
    checks = {}
    if args.expect_loaded_match:
        checks["loaded_target_reconciles"] = abs(before.mtp_monthly - policy.mtp) < 1e-8
    engine = IllustrationEngine()
    control = engine.project(policy, months=months)
    states = engine.project(policy, months=months, future_inputs=inputs)
    changed = [state for state in states if state.date >= args.date]
    checks["face_increased"] = bool(changed) and all(
        abs(state.coverage_after_change["CurrentSA"] - args.face) < 1e-8
        for state in changed
    )
    checks["control_unchanged"] = all(
        abs(state.monthly_mtp - policy.mtp) < 1e-8 for state in control
    )
    if args.expect_monthly is not None:
        checks["expected_monthly"] = bool(changed) and all(
            abs(state.monthly_mtp - args.expect_monthly) < 1e-8 for state in changed
        )
    checks["display_and_export"] = all(
        IllustrationValuesTab._target_premium_values(state)["vMonthlyMTP"]
        == project_summary_row(policy, state)["MonthlyMTP"] == state.monthly_mtp
        and abs(
            IllustrationValuesTab._target_premium_values(state)["vMTP"]
            - state.mtp_detail["vMTP"]
        ) < 1e-8
        for state in changed
    )
    checks["accumulation"] = all(
        abs(state.accumulated_mtp - previous.accumulated_mtp - state.monthly_mtp) < 1e-8
        for previous, state in zip(states, states[1:])
    )
    rows = [{
        "date": state.date,
        "face": state.coverage_after_change["CurrentSA"],
        "mtp_without_pw": state.mtp_detail["MTP w/o PW"],
        "pw_rate_raw": state.mtp_detail["PW MTPR"],
        "pw_mtp": state.mtp_detail["PW MTP"],
        "mtp_annual": state.mtp_annual,
        "monthly_mtp": state.monthly_mtp,
        "accumulated_mtp": state.accumulated_mtp,
        "ctp_annual": state.ctp_detail["vCTP"],
    } for state in states]
    checks["source_unchanged"] = policy == original
    ok = all(checks.values())
    print(json.dumps({
        "policy": args.policy, "plancode": policy.plancode,
        "company": policy.company_code, "valuation_date": policy.valuation_date,
        "loaded_monthly_mtp": policy.mtp, "original_face": policy.total_face,
        "config": {"is_ffl": config.is_ffl, "sa_basis": config.sa_basis,
                   "table_rating_factor": config.table_rating_factor},
        "recomputed_loaded_monthly_mtp": before.mtp_monthly,
        "rows": rows, "checks": checks, "all_ok": ok,
    }, default=str, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
