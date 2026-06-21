"""Sweep level premiums and report the milestones that matter for a
"Level Premium to Exception Period" solve.

For each candidate monthly premium L, project the policy and report:
  * cap@   - first month the applied premium fell BELOW L before any exception
             (i.e. the guideline capped it -> premium is NOT level)
  * exc@   - first month vExceptionPremMode turns on
  * lapse@ - first month the policy lapses
  * end AV at maturity (or at the run's end)
  * outcome - LAPSE / EXCEPTION / ENDOW

Usage:
    venv\\Scripts\\python.exe tools/diag_level_to_exception.py '{"policy":"UL062614",
        "months":900,"mode":"M","premiums":[27.67,35,42,50,60,80,100]}'
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

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.models.input_set import (
        IllustrationOptions, IllustrationInputSet,
        ScheduledTransaction, TransactionKind,
    )

    policy = cmd.get("policy", "UL062614")
    region = cmd.get("region", "CKPR")
    months = int(cmd.get("months", 900))
    mode = cmd.get("mode", "M")
    premiums = cmd.get("premiums", [27.67, 35, 42, 50, 60, 80, 100])

    options = IllustrationOptions(
        conform_to_tefra=cmd.get("tefra", True),
        conform_to_tamra=cmd.get("tamra", True),
        allow_exception_prems=cmd.get("exception", True),
    )

    clear_cache()
    pdata = build_illustration_data(policy, region=region)
    print(f"{policy}  issue={pdata.issue_date}  val={pdata.valuation_date}  "
          f"plancode={pdata.plancode}  startAV={pdata.account_value}  "
          f"maturity_age={getattr(pdata,'maturity_age',None)}")
    print(f"{'premium':>9} {'cap@':>11} {'exc@':>11} {'lapse@':>11} "
          f"{'endAV':>10}  outcome")

    for L in premiums:
        future = IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1,
                                 amount=float(L), mode=mode)])
        states = IllustrationEngine().project(
            pdata, months=months, options=options, future_inputs=future)

        cap_at = exc_at = lapse_at = None
        for s in states[1:]:  # skip inforce seed row
            if exc_at is None and s.exception_prem_mode:
                exc_at = s.date
            # "capped" = applied premium below the level, while NOT yet in
            # exception mode (exception months legitimately pay a different amt)
            if (cap_at is None and not s.exception_prem_mode
                    and s.gross_premium + 0.01 < float(L)
                    and s.date is not None):
                # ignore the final partial year where payments simply end
                cap_at = s.date
            if lapse_at is None and s.lapsed:
                lapse_at = s.date
            if exc_at and lapse_at:
                break

        end_av = states[-1].av_end_of_month if states else 0.0
        if lapse_at and not exc_at:
            outcome = "LAPSE"
        elif exc_at:
            outcome = "EXCEPTION"
        else:
            outcome = "ENDOW"
        print(f"{L:>9.2f} {str(cap_at):>11} {str(exc_at):>11} "
              f"{str(lapse_at):>11} {end_av:>10.2f}  {outcome}")


if __name__ == "__main__":
    main()
