"""Print the key illustration calc inputs for a policy (local SQLite mode).

Useful for debugging RERUN-vs-engine input differences (shadow/CCV seed, GLP/GSP,
account value, loans, etc.).

Usage:
    venv\\Scripts\\python.exe tools/inspect_illustration_inputs.py '{"policy":"U0492070","region":"CKPR","company":"01"}'
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.core.policy_service import clear_cache, get_policy_info
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data

    policy = cmd["policy"]
    region = cmd.get("region", "CKPR")
    company = cmd.get("company")

    clear_cache()
    pi = get_policy_info(policy, region, company)

    def f(v):
        return None if v is None else float(v)

    raw = {
        "gav (IX target)": f(pi.gav),
        "ccv_target (CV)": f(pi.ccv_target),
        "accumulation_value": f(pi.accumulation_value),
        "cash_surrender_value": f(getattr(pi, "cash_surrender_value", None)),
        "glp": f(pi.glp),
        "gsp": f(pi.gsp),
        "accumulated_glp_target": f(pi.accumulated_glp_target),
        "mtp": f(pi.mtp),
        "accumulated_mtp_target": f(pi.accumulated_mtp_target),
        "total_loan_balance": f(getattr(pi, "total_loan_balance", None)),
    }

    pd = build_illustration_data(policy, region=region, company_code=company)
    derived = {
        "account_value": pd.account_value,
        "shadow_account_value": pd.shadow_account_value,
        "ccv_active": pd.ccv_active,
        "ccv_units": pd.ccv_units,
        "glp": pd.glp,
        "gsp": pd.gsp,
        "accumulated_glp": pd.accumulated_glp,
        "face_amount": pd.face_amount,
        "segments": len(pd.segments),
        "riders": [{"plancode": r.plancode, "face": r.face_amount, "units": r.units,
                    "band": r.band, "table": r.table_rating, "flat": r.flat_extra}
                   for r in pd.riders],
        "benefits": [(b.benefit_type, b.benefit_subtype, b.units) for b in pd.benefits],
    }

    print(json.dumps({"policy": policy, "pi_raw": raw, "illustration_data": derived},
                     indent=2, default=str))


if __name__ == "__main__":
    main()
