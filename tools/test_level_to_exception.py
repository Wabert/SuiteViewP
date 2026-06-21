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


if __name__ == "__main__":
    main()
