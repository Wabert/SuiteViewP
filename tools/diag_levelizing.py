"""Show the effect of the levelizing option on the applied (non-exception)
premium for the Level-to-Exception solve.

Solves the premium under levelizing OFF and ON, then traces the applied gross
premium through a window so the lumpy annual-cap pattern (OFF) vs the smooth
per-payment level (ON) is visible side by side.

    venv\\Scripts\\python.exe tools/diag_levelizing.py '{"policy":"UL062614",
        "from":"2042-01-01","to":"2046-09-30"}'
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
    from suiteview.illustration.core.solve_level_to_exception import solve_level_to_exception
    from suiteview.illustration.models.input_set import (
        IllustrationOptions, IllustrationInputSet, ScheduledTransaction, TransactionKind,
    )

    policy = cmd.get("policy", "UL062614")
    region = cmd.get("region", "CKPR")
    d_from = datetime.date.fromisoformat(cmd.get("from", "2042-01-01"))
    d_to = datetime.date.fromisoformat(cmd.get("to", "2046-09-30"))

    clear_cache()
    pdata = build_illustration_data(policy, region=region)

    off = IllustrationOptions(levelizing_premium=False)
    on = IllustrationOptions(levelizing_premium=True)
    r_off = solve_level_to_exception(pdata, base_options=off)
    r_on = solve_level_to_exception(pdata, base_options=on)
    print(f"{policy}  solved premium  levelizing OFF={r_off.premium:.2f}  "
          f"ON={r_on.premium:.2f}  (diff={r_on.premium - r_off.premium:+.2f})")

    from suiteview.illustration.core.solve_level_to_exception import level_to_exception_options

    def trace(premium, base):
        future = IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1,
                                 amount=premium, mode="M")])
        states = IllustrationEngine().project(
            pdata, options=level_to_exception_options(base), future_inputs=future)
        return {s.date: s for s in states if s.date}

    # Trace each at its own solved premium so we compare like-for-like runs.
    off_rows = trace(r_off.premium, off)
    on_rows = trace(r_on.premium, on)

    print(f"{'date':>11} {'OFF prem':>9} {'OFF excPrem':>11}   "
          f"{'ON prem':>9} {'ON excPrem':>11}")
    dates = sorted(d for d in off_rows if d_from <= d <= d_to)
    for d in dates:
        a, b = off_rows[d], on_rows.get(d)
        print(f"{str(d):>11} {a.gross_premium:>9.2f} {a.gp_exception_prem:>11.2f}   "
              f"{(b.gross_premium if b else 0):>9.2f} {(b.gp_exception_prem if b else 0):>11.2f}")


if __name__ == "__main__":
    main()
