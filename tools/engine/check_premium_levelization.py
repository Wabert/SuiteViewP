r"""Inspect monthly premium levelization for one illustration policy.

Usage:
    venv\Scripts\python.exe tools\engine\check_premium_levelization.py UE000032 19.21
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("policy")
    parser.add_argument("premium", type=float)
    parser.add_argument("--company")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--mode", default="M", choices=("M", "Q", "S", "A"))
    parser.add_argument("--months", type=int, default=24)
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

    clear_cache()
    policy = build_illustration_data(
        args.policy,
        region=args.region,
        company_code=args.company,
    )
    forecast_year = (policy.duration // 12) + 1
    inputs = IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.PREMIUM,
                policy_year=forecast_year,
                amount=args.premium,
                mode=args.mode,
            )
        ]
    )
    states = IllustrationEngine().project(
        policy,
        months=args.months,
        future_inputs=inputs,
        options=IllustrationOptions(levelizing_premium=True),
        stop_on_lapse=False,
    )

    rows = []
    for state in states[1:]:
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
            "has_loan": (
                state.end_rg_loan_princ
                + state.end_rg_loan_accrued
                + state.end_pf_loan_princ
                + state.end_pf_loan_accrued
                + state.end_vbl_loan_princ
                + state.end_vbl_loan_accrued
            ) > 1e-9,
        })

    print(json.dumps({
        "policy": args.policy,
        "valuation_date": policy.valuation_date.isoformat(),
        "duration": policy.duration,
        "forecast_year": forecast_year,
        "input_premium": args.premium,
        "rows": rows,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
