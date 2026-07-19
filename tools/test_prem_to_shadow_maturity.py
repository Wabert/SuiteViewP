r"""Validate the "Prem to Shadow Maturity" solve path on a local-fixture policy.

Mirrors main_window's shadow branch: report the policy's shadow state
(ccv_active / ccv_ceased), refuse with the user-facing reason when the shadow
account can't drive a solve, otherwise solve the minimum level premium that
keeps the shadow account in force to maturity (exceptions off) and re-project
at the solved premium to confirm the run reaches maturity. Run:

    venv\Scripts\python.exe tools/test_prem_to_shadow_maturity.py '{"policy":"U0492070"}'
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
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.solve_level_to_exception import (
        LevelToExceptionError, level_to_exception_options, solve_level_to_exception,
    )
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, ScheduledTransaction, TransactionKind,
    )

    policy = cmd.get("policy", "U0492070")
    region = cmd.get("region", "CKPR")

    clear_cache()
    pdata = build_illustration_data(policy, region=region)
    print(f"{policy}  plancode={pdata.plancode}  maturity_age={pdata.maturity_age}  "
          f"cvat={pdata.is_cvat}  ccv_active={pdata.ccv_active}  "
          f"ccv_ceased={pdata.ccv_ceased}  shadow_av={pdata.shadow_account_value:.2f}")

    if not pdata.has_shadow_account:
        if pdata.ccv_ceased:
            print("  REFUSED: shadow account benefit (type A) has ceased — "
                  "the shadow account no longer governs lapse.")
        else:
            print("  REFUSED: no shadow account benefit (type A) on this policy.")
        return

    try:
        r = solve_level_to_exception(pdata, allow_exceptions=False)
    except LevelToExceptionError as e:
        print(f"  NOT SOLVABLE: {e}")
        return

    print(f"  solved premium : {r.premium:.2f} / {r.mode}")
    print(f"  maturity AV    : {r.maturity_av:.2f}  iterations={r.iterations}")

    # Re-project at the solved premium on the same basis and confirm the run
    # reaches maturity with the shadow account (not the AV) carrying it.
    # (CVAT solves force TAMRA conformance off — mirror that basis here.)
    options = level_to_exception_options(
        None, allow_exceptions=False, conform_to_tamra=not pdata.is_cvat)
    states = IllustrationEngine().project(
        pdata, options=options,
        future_inputs=IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1,
                                 amount=r.premium, mode=r.mode)]))
    last = states[-1]
    shadow_months = sum(1 for s in states if s.shadow_protection)
    print(f"  last row: age={last.attained_age}  lapsed={last.lapsed}  "
          f"matured={last.matured}  shadow_eav={last.shadow_eav:.2f}")
    print(f"  months in force via shadow protection: {shadow_months}/{len(states)}")


if __name__ == "__main__":
    main()
