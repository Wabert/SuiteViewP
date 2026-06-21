"""Diagnose the GP exception-premium pipeline for one policy.

Runs the illustration engine on local SQLite data and prints, for the months in
a date window, every input that decides vExceptionPremMode (SY) and the premium
chain: the guideline-limit flag (SX), the AV after charge, accumulated guideline
room, the level caps, and the resulting exception mode / premium / lapse.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/diag_exception_mode.py '{"policy":"UL062614",
        "months":250,"premium":50,"mode":"M","from":"2044-01-01","to":"2046-12-31"}'
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

    import datetime
    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.models.input_set import (
        IllustrationOptions, IllustrationInputSet,
        ScheduledTransaction, TransactionKind,
    )

    policy = cmd.get("policy", "UL062614")
    region = cmd.get("region", "CKPR")
    months = int(cmd.get("months", 250))
    premium = float(cmd.get("premium", 50.0))
    mode = cmd.get("mode", "M")
    d_from = datetime.date.fromisoformat(cmd.get("from", "2044-01-01"))
    d_to = datetime.date.fromisoformat(cmd.get("to", "2046-12-31"))

    options = IllustrationOptions(
        conform_to_tefra=cmd.get("tefra", True),
        conform_to_tamra=cmd.get("tamra", True),
        allow_exception_prems=cmd.get("exception", True),
    )
    future = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1,
                             amount=premium, mode=mode)])

    clear_cache()
    pdata = build_illustration_data(policy, region=region)
    states = IllustrationEngine().project(
        pdata, months=months, options=options, future_inputs=future)

    print(f"{policy}  issue={pdata.issue_date}  val={pdata.valuation_date}  "
          f"plancode={pdata.plancode}  allow_exc={options.allow_exception_prems}")
    cols = ("date", "yr", "BOY", "SX", "NV_cap", "NW_lvl", "NU_gp",
            "AV_aftChg", "AV_end", "SYmode", "ExcGross", "ExcPrem", "lapsed")
    print("  ".join(f"{c:>10}" for c in cols))

    prior_boy_av = None
    for s in states:
        d = s.date
        if d is None or d < d_from or d > d_to:
            continue
        boy = s.is_anniversary
        row = (
            str(d), s.policy_year, "Y" if boy else "",
            "T" if s.guideline_limit_reached else "F",
            round(s.scheduled_prem_cap, 2), round(s.levelized_max_premium, 2),
            round(s.premium_allowance_detail.get("GP_Level_Allowance", 0.0), 2)
            if s.premium_allowance_detail else 0.0,
            round(s.av_after_deduction, 2), round(s.av_end_of_month, 2),
            "T" if s.exception_prem_mode else "F",
            round(s.gp_exception_prem_gross, 2), round(s.gp_exception_prem, 2),
            "T" if s.lapsed else "F",
        )
        print("  ".join(f"{str(v):>10}" for v in row))


if __name__ == "__main__":
    main()
