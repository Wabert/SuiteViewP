"""Diagnose what constrains the Max Level solve for a policy.

Projects the policy at several modal level premiums (mirroring
``solve_max_level_allowed``'s own basis: guideline + TAMRA on, GP exceptions
allowed, premium level from --start-year to age 100 then stopped) and prints,
per anniversary, the guideline picture the solve bisects against:

    age | premiums_to_date | accumGLP | gsp | guideline_limit | capped? | lapsed?

so we can see whether the solved premium is limited by a real guideline cap or
by the policy lapsing before the capping years are ever reached.

Usage:
    SUITEVIEW_LOCAL_DATA=1 venv/Scripts/python.exe tools/diag_max_level_binding.py \
        --policy U0656998 --region CKPR --premiums 50.33 60 70 71
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.illustration_policy_service import (
    build_illustration_data,
)
from suiteview.illustration.core.solve_level_to_exception import (
    level_to_exception_options,
)
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    ScheduledTransaction,
    TransactionKind,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--policy", required=True)
    p.add_argument("--region", default="CKPR")
    p.add_argument("--company", default=None)
    p.add_argument("--start-year", type=int, default=None,
                   help="Policy year the level premium starts (default: forecast year).")
    p.add_argument("--mode", default="M")
    p.add_argument("--premiums", nargs="+", type=float, required=True,
                   help="Modal premiums to project, e.g. 50.33 60 70 71")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    policy = build_illustration_data(
        args.policy, region=args.region, company_code=args.company)
    mode = args.mode.upper()
    start_year = args.start_year or int(getattr(policy, "policy_year", 1) or 1)
    options = level_to_exception_options(None, True)
    engine = IllustrationEngine()

    issue_age = int(policy.issue_age or 0)
    stop_year = None
    if policy.maturity_age > 100:
        stop_year = 100 - issue_age + 1

    print(f"Policy {args.policy}  issue_age={issue_age}  "
          f"attained_age={policy.attained_age}  maturity_age={policy.maturity_age}")
    print(f"GLP={policy.glp}  GSP={policy.gsp}  AccumGLP={policy.accumulated_glp}  "
          f"start_year={start_year}  stop_year={stop_year}")

    for premium in args.premiums:
        scheds = [ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=start_year,
            amount=float(premium), mode=mode)]
        if stop_year is not None:
            scheds.append(ScheduledTransaction(
                kind=TransactionKind.PREMIUM, policy_year=stop_year,
                amount=0.0, mode="A"))
        future = IllustrationInputSet(scheduled_transactions=scheds)
        states = engine.project(policy, options=options, future_inputs=future)

        capped = [s for s in states if s.premium_capped]
        lapsed = next((s for s in states if s.lapsed), None)
        first_cap = capped[0] if capped else None
        end = states[-1] if states else None
        print(f"\n=== premium {premium:.2f}/{mode} -> "
              f"accepted={'NO' if capped else 'yes'}  "
              f"end_age={end.attained_age if end else '?'}  "
              f"lapsed={'age %d' % lapsed.attained_age if lapsed else 'no'} ===")
        if first_cap is not None:
            print(f"  first capped: age {first_cap.attained_age}  "
                  f"premTD={first_cap.premiums_to_date:.2f}  "
                  f"accumGLP={first_cap.accumulated_glp:.2f}  "
                  f"gsp={first_cap.gsp:.2f}  "
                  f"limit={first_cap.guideline_limit:.2f}  "
                  f"requested={first_cap.requested_premium:.2f}  "
                  f"cap={first_cap.premium_cap:.2f}")
        # Anniversary snapshot (month-1 rows) for the first ~15 years + the
        # neighbourhood of any cap.
        annes = [s for s in states if getattr(s, "policy_month", 0) == 1]
        for s in annes[:18]:
            flag = "  <== CAPPED" if s.premium_capped else ""
            flag += "  <== LAPSED" if s.lapsed else ""
            print(f"  age {s.attained_age:3d}  premTD={s.premiums_to_date:10.2f}  "
                  f"accumGLP={s.accumulated_glp:10.2f}  gsp={s.gsp:10.2f}  "
                  f"limit={s.guideline_limit:10.2f}  av={s.av_end_of_month:10.2f}{flag}")


if __name__ == "__main__":
    main()
