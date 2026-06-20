"""Dump the Values-tab source state for a policy: Cov After Change, TEFRA/TAMRA,
and Requested Premium fields for the inforce row and the first few months.

Usage:
    venv\\Scripts\\python.exe tools/dump_values_state.py '{"policy":"S0503261","months":3}'
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SUITEVIEW_LOCAL_DATA"] = "1"


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    policy_num = cmd.get("policy", "S0503261")
    months = int(cmd.get("months", 3))

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data

    clear_cache()
    policy = build_illustration_data(policy_num, region=cmd.get("region", "CKPR"),
                                     company_code=cmd.get("company"))
    states = IllustrationEngine().project(policy, months=months)

    cov_keys = [
        "Cov 1 Active", "Cov 1 Issue Date", "Cov 1 Months from Issue",
        "Original SA Cov 1", "Current SA Cov 1", "Issue Age Cov 1",
        "Rateclass Cov 1", "Table Rating Cov 1", "CurrentSA", "LastActiveSegment",
    ]
    for i, s in enumerate(states):
        print(f"\n===== row {i}  date={s.date}  yr={s.policy_year} mo={s.policy_month} att={s.attained_age} =====")
        cov = s.coverage_after_change or {}
        print(f"  coverage_after_change: {'EMPTY' if not cov else str(len(cov)) + ' keys'}")
        for k in cov_keys:
            print(f"    {k}: {cov.get(k, '<<missing>>')}")
        print("  TAMRA: yr={} moy={} start={} lowest7yr={} accum_7pay={}".format(
            s.tamra_year, s.tamra_month_of_year, s.tamra_7pay_start_date,
            s.lowest_7yr_face, s.accumulated_7pay))
        print("  Premium: planned={} unscheduled={} mode={} pc_policy={} pc_tamra={}".format(
            s.requested_premium, s.unscheduled_premium, s.planned_premium_mode,
            s.payment_count_policy_year, s.payment_count_tamra_year))


if __name__ == "__main__":
    main()
