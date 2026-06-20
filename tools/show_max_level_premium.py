"""Show the Illustration Input tab Max Level premium calculation for a policy.

Usage:
    venv\\Scripts\\python.exe tools/show_max_level_premium.py --policy U0361706 --region CKPR
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
# Force live DB2 unless the caller explicitly opted into local dev data.
if os.environ.get("SUITEVIEW_LOCAL_DATA") != "1":
    os.environ.pop("SUITEVIEW_LOCAL_DATA", None)

from suiteview.core.policy_service import clear_cache, get_policy_info
from suiteview.illustration.core.target_premium import floor_monthly_cent
from suiteview.illustration.ui.inputs_dynamic import context_from_policy


def _first_float(source, *names: str) -> float:
    for name in names:
        value = getattr(source, name, None)
        if value is not None:
            return float(value or 0.0)
    return 0.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show max level premium calculation for a policy.")
    parser.add_argument("--policy", required=True, help="Policy number")
    parser.add_argument("--region", default="CKPR", help="DB2 region code")
    parser.add_argument("--company", default=None, help="Optional company code")
    return parser.parse_args()


def _money(value: float) -> str:
    return f"{value:,.2f}"


def main() -> None:
    args = _parse_args()
    policy_number = args.policy
    region = args.region
    company = args.company

    clear_cache()
    policy = get_policy_info(policy_number, region, company, use_cache=False)
    if policy is None or not getattr(policy, "exists", False):
        raise SystemExit(f"Policy not found: {policy_number}")

    ctx = context_from_policy(policy)
    attained_age = int(getattr(policy, "attained_age", 0) or 0)
    maturity_age = int(getattr(policy, "maturity_age", None) or getattr(policy, "age_at_maturity", None) or 0)
    max_level_end_age = min(maturity_age, 100)
    glp = floor_monthly_cent(_first_float(policy, "glp"))  # monthly-normalized, matches the app
    accumulated_glp = _first_float(policy, "accumulated_glp", "accumulated_glp_target")
    premiums_paid_to_date = _first_float(policy, "premiums_paid_to_date", "premium_td", "total_premiums_paid")
    withdrawals_to_date = _first_float(policy, "withdrawals_to_date", "total_withdrawals")
    net_premium_td = premiums_paid_to_date - withdrawals_to_date
    total_accumulated_glp = accumulated_glp + (ctx.max_level_years * glp)

    result = {
        "policy": policy_number,
        "region": region,
        "company": getattr(policy, "company_code", None),
        "def_of_life_ins": getattr(policy, "def_of_life_ins", None)
            or getattr(policy, "def_of_life_ins_description", None)
            or getattr(policy, "def_of_life_ins_code", None),
        "issue_age": int(getattr(policy, "base_issue_age", None) or getattr(policy, "issue_age", 0) or 0),
        "attained_age": attained_age,
        "maturity_age": maturity_age,
        "max_level_end_age": max_level_end_age,
        "max_level_years": ctx.max_level_years,
        "glp": glp,
        "accumulated_glp": accumulated_glp,
        "premiums_paid_to_date": premiums_paid_to_date,
        "withdrawals_to_date": withdrawals_to_date,
        "net_premium_td": net_premium_td,
        "total_accumulated_glp_at_limit_age": total_accumulated_glp,
        "remaining_room": ctx.max_level_premium_room,
        "payment_counts": {mode: ctx.payment_count(mode) for mode in ("A", "S", "Q", "M")},
        "max_level_premiums": {mode: ctx.max_modal_level_premium(mode) for mode in ("A", "S", "Q", "M")},
        "default_mode": ctx.default_mode,
    }

    print(json.dumps(result, indent=2, default=str))
    if not ctx.is_cvat:
        print()
        print(
            "Formula: "
            f"(({_money(accumulated_glp)} + {_money(glp)} * {ctx.max_level_years}) "
            f"- ({_money(premiums_paid_to_date)} - {_money(withdrawals_to_date)})) "
            f"/ {ctx.payment_count('A')} = {_money(ctx.max_annual_level_premium)}"
        )


if __name__ == "__main__":
    main()
