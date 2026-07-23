"""Diagnostic: reproduce the "Billable to MD" hand-off for U0370005.

Mirrors the Inputs-tab UI flow: build the policy, solve the lumpsum-to-next-
premium bridge, layer it in, then run the Billable-to-MD schedule and dump the
per-month values around the hand-off.

Run: venv\\Scripts\\python.exe tools/diag_b2md_u0370005.py
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from suiteview.illustration.core.batch_runner import _billable_to_md_run
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.illustration_policy_service import (
    build_illustration_data,
)
from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
    solve_lumpsum_to_next_premium,
)
from suiteview.illustration.models.input_set import (
    DatedTransaction, IllustrationInputSet, TransactionKind,
)

POLICY = "U0370005"


def main():
    policy = build_illustration_data(POLICY, region="CKPR")
    print(f"plancode={policy.plancode} form={policy.form_number} "
          f"freq={policy.billing_frequency} modal={policy.modal_premium}")
    print(f"AV={policy.account_value} polyr={policy.policy_year} "
          f"polmo={policy.policy_month} dur={policy.duration} "
          f"val={policy.valuation_date} issue={policy.issue_date}")

    engine = IllustrationEngine()
    future, options = _billable_to_md_run(policy)

    # Solve the lumpsum-to-next-premium bridge exactly like the UI does.
    lr = solve_lumpsum_to_next_premium(
        policy, base_future_inputs=future, base_options=options, engine=engine)
    if lr is not None and lr.lumpsum > 0:
        print(f"\nLumpsum-to-next: ${lr.lumpsum:,.2f} applied={lr.applied:,.2f} "
              f"on {lr.forecast_date} -> next due {lr.next_premium_date} "
              f"reason={lr.binding_reason} guideline_limited={lr.guideline_limited}")
        dated = list(future.dated_transactions)
        dated.append(DatedTransaction(
            kind=TransactionKind.PREMIUM, effective_date=lr.forecast_date,
            amount=lr.lumpsum, subtype="lumpsum_to_next_premium"))
        future = IllustrationInputSet(
            scheduled_transactions=list(future.scheduled_transactions),
            dated_transactions=dated,
            policy_changes=list(future.policy_changes))
        # Suppress the b2md hand-off until the bridge reaches the next premium.
        from dataclasses import replace as _replace
        options = _replace(
            options, billable_to_md_no_latch_before=lr.next_premium_date)
    else:
        print("\nLumpsum-to-next: none needed")

    states = engine.project(
        deepcopy(policy), options=options, future_inputs=future,
        stop_on_lapse=True)

    print("\n dur  yr mo  age | grossPrem  mdPrem  gpExc |    AVend      SV    "
          "| switch md_mode exc_mode lapsed")
    switch_dur = next(
        (s.duration for s in states if s.billable_md_switched), None)
    for s in states[:40]:
        sv = getattr(s, "surrender_value", None)
        sv_txt = f"{sv:9.2f}" if sv is not None else "   n/a  "
        mark = " <== SWITCH" if s.duration == switch_dur else ""
        print(f"{s.duration:4d} {s.policy_year:3d}{s.policy_month:3d} "
              f"{s.attained_age:4d} | {s.gross_premium:8.2f} {s.md_premium:7.2f} "
              f"{s.gp_exception_prem:7.2f} | {s.av_end_of_month:9.2f} {sv_txt} "
              f"| {int(s.billable_md_switched)}      {int(s.md_premium_mode)}"
              f"       {int(s.gp_exception_mode)}        {int(s.lapsed)}{mark}")

    switch = next((s for s in states if s.billable_md_switched), None)
    first_md = next((s for s in states if s.md_premium > 0), None)
    first_exc = next((s for s in states if s.gp_exception_prem > 0), None)
    print(f"\nSwitch latched: {switch.date if switch else 'never'} "
          f"(yr {switch.policy_year} mo {switch.policy_month})"
          if switch else "Switch latched: never")
    print(f"First MD premium: {first_md.date if first_md else 'never'}")
    print(f"First GP exception: {first_exc.date if first_exc else 'never'}")


if __name__ == "__main__":
    main()
