"""Validate solve_level_to_exception against the known UL062614 boundary.

The premium sweep (tools/diag_level_to_exception.py) puts the lapse↔exception
boundary at $48.00 lapses / $48.10 survives, so the solved minimum must land in
(48.00, 48.10]. Run:

    venv\\Scripts\\python.exe tools/test_level_to_exception.py '{"policy":"UL062614"}'
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
    from suiteview.illustration.core.solve_level_to_exception import (
        solve_level_to_exception, LevelToExceptionError,
    )
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, ScheduledTransaction, TransactionKind,
    )

    policy = cmd.get("policy", "UL062614")
    region = cmd.get("region", "CKPR")
    mode = cmd.get("mode")

    clear_cache()
    pdata = build_illustration_data(policy, region=region)
    print(f"{policy}  issue={pdata.issue_date}  val={pdata.valuation_date}  "
          f"plancode={pdata.plancode}  maturity_age={pdata.maturity_age}  "
          f"billing_freq={pdata.billing_frequency}  cvat={pdata.is_cvat}  "
          f"has_loans={pdata.has_loans}")

    try:
        r = solve_level_to_exception(pdata, mode=mode)
    except LevelToExceptionError as e:
        print(f"  NOT SOLVABLE: {e}")
        return

    print(f"  solved premium : {r.premium:.2f} / {r.mode}")
    print(f"  enters exception: {r.enters_exception}  start={r.exception_start}")
    print(f"  maturity AV    : {r.maturity_av:.2f}")
    print(f"  iterations     : {r.iterations}")

    if policy == "UL062614" and mode in (None, "M"):
        ok = 48.00 < r.premium <= 48.20
        print(f"  EXPECT (48.00, 48.20]: {'PASS' if ok else 'FAIL'}")

    # Min Level to Maturity (no exceptions): a guideline-bound policy can't endow
    # on its own, so the solver should report no solution.
    try:
        r0 = solve_level_to_exception(pdata, mode=mode, allow_exceptions=False)
        print(f"  no-exception solve -> {r0.premium:.2f} (endows without exceptions)")
    except LevelToExceptionError as e:
        print(f"  no-exception solve -> no solution: {e}")

    # Maturity flag: project to maturity and confirm the last row reads Maturity.
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.ui.values_overview import _status_text
    from suiteview.illustration.models.input_set import IllustrationOptions
    states = IllustrationEngine().project(
        pdata, options=IllustrationOptions(allow_exception_prems=True),
        future_inputs=IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1,
                                 amount=r.premium, mode=r.mode)]))
    last = states[-1]
    print(f"  last row: age={last.attained_age} matured={last.matured} "
          f"status={_status_text(last)!r}")

    # Prior-premium scenario: honor $100/mo from the forecast year, solve the
    # Min Level premium that takes over `start` years later.
    start = int(cmd.get("prior_start", 0))
    if start:
        prior_amt = float(cmd.get("prior_amount", 100.0))
        base = IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(kind=TransactionKind.PREMIUM,
                                 policy_year=start - 5, amount=prior_amt, mode="M")])
        r2 = solve_level_to_exception(
            pdata, mode="M", start_policy_year=start, base_future_inputs=base)
        print(f"\n  prior ${prior_amt:.0f}/mo for yrs {start-5}..{start-1}, "
              f"then Min Level from yr {start}:")
        print(f"    solved level   : {r2.premium:.2f} / {r2.mode}")
        print(f"    enters exc     : {r2.enters_exception}  start={r2.exception_start}")
        print(f"    maturity AV    : {r2.maturity_av:.2f}  iters={r2.iterations}")


if __name__ == "__main__":
    main()
