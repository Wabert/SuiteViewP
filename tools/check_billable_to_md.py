"""Offline check of the "Billable to MD" premium type.

Synthetic policy with mock rates (rising ART-style COIs so the billable
premium eventually stops carrying the policy). Verifies the sequence:

1. The scheduled billable premium pays while it keeps the policy in force.
2. The first month the lapse test would fail, ``billable_md_switched``
   latches, the billable premium stops, and the Monthly Deduction premium
   pays instead.
3. Once the guideline room runs out the MD premium caps and GP exception
   premiums take over; the policy stays in force.

Run: venv\\Scripts\\python.exe tools/check_billable_to_md.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from suiteview.illustration import CoverageSegment, IllustrationPolicyData
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import (
    IllustrationInputSet, IllustrationOptions, ScheduledTransaction,
    TransactionKind,
)


def main():
    policy = IllustrationPolicyData(
        policy_number="B2MDTEST",
        plancode="1U143900",
        issue_date=date(2016, 10, 27),
        issue_age=50,
        attained_age=59,
        rate_sex="M",
        rate_class="N",
        face_amount=90000.0,
        units=90.0,
        db_option="A",
        band=2,
        account_value=11936.84,
        modal_premium=150.0,
        annual_premium=1800.0,
        billing_frequency=1,
        premiums_paid_to_date=10800.0,
        premiums_ytd=900.0,
        guaranteed_interest_rate=0.03,
        current_interest_rate=0.0425,
        policy_year=10,
        policy_month=6,
        duration=114,
        valuation_date=date(2025, 4, 14),
        maturity_age=121,
        def_of_life_ins="GPT",
        ctp=1242.0,
        glp=2400.0,
        gsp=30000.0,
        segments=[CoverageSegment(
            coverage_phase=1, is_base=True,
            issue_date=date(2016, 10, 27),
            issue_age=50, rate_sex="M", rate_class="N",
            face_amount=90000.0, original_face_amount=90000.0,
            units=90.0, band=2,
        )],
    )

    # Mock rates — COIs rise ~9%/yr so the $150/mo billable premium fails
    # somewhere in the policy's later years.
    coi = [None] + [min(80.0, 0.50 * (1.09 ** (d - 1))) for d in range(1, 201)]
    mock_rates = IllustrationRates(
        coi=coi,
        epu=[None] + [0.10] * 200,
        scr=[None] + [0.0] * 200,
        mfee=[None] + [5.0] * 200,
        gint=[None] + [0.03] * 200,
        tpp=[None] + [0.06] * 200,
        epp=[None] + [0.02] * 200,
        mtp=10.0,
        ctp=13.80,
    )

    # What the Inputs tab exports for a "Billable to MD" row from year 10 to
    # maturity: a zero silencer schedule, then the billable schedule (the row
    # starts mid-year 10, so year 10 would be dated transactions — start the
    # schedule at year 11 and let year 10 bill the modal fallback silencer).
    future_inputs = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=10,
                             amount=0.0, mode="A"),
        ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=11,
                             amount=150.0, mode="M"),
    ])
    options = IllustrationOptions(
        allow_exception_prems=True,
        billable_to_md_windows=[(10, None)],
    )

    engine = IllustrationEngine()
    results = engine.project(
        policy, future_inputs=future_inputs, options=options,
        rates_override=mock_rates, stop_on_lapse=True,
    )

    switch_state = next((s for s in results if s.billable_md_switched), None)
    first_md = next((s for s in results if s.md_premium > 0), None)
    first_capped = next((s for s in results if s.md_premium_capped), None)
    first_exc = next((s for s in results if s.gp_exception_prem > 0), None)
    last = results[-1]

    def _label(state):
        if state is None:
            return "never"
        return (f"yr {state.policy_year} mo {state.policy_month} "
                f"(age {state.attained_age}, {state.date})")

    print(f"Projected months:      {len(results) - 1}")
    print(f"Switch latched:        {_label(switch_state)}")
    print(f"First MD premium:      {_label(first_md)}"
          + (f"  ${first_md.md_premium:,.2f}" if first_md else ""))
    print(f"MD premium capped:     {_label(first_capped)}")
    print(f"First GP exception:    {_label(first_exc)}"
          + (f"  ${first_exc.gp_exception_prem:,.2f}" if first_exc else ""))
    print(f"Final state:           {_label(last)}  AV ${last.av_end_of_month:,.2f}"
          f"  lapsed={last.lapsed}  matured={last.matured}")

    # Billable premium must stop from the month after the switch latches.
    assert switch_state is not None, "switch never latched"
    post_switch = [s for s in results if s.duration > switch_state.duration]
    billed_after = [s for s in post_switch if s.gross_premium > 0.005]
    assert not billed_after, (
        f"billable premium still paid after switch: "
        f"{[(s.policy_year, s.policy_month, s.gross_premium) for s in billed_after[:5]]}")
    # Billable premium must have been paying BEFORE the switch.
    pre_switch_paid = sum(
        s.gross_premium for s in results if s.duration < switch_state.duration)
    assert pre_switch_paid > 0, "no billable premium paid before the switch"
    # MD premium starts in the switch month itself.
    assert first_md is not None and first_md.duration == switch_state.duration, (
        "MD premium did not start in the switch month")
    # The sequence must reach the exception phase and hold to maturity.
    assert first_exc is not None, "GP exception premium never fired"
    assert first_capped is not None and first_capped.duration <= first_exc.duration
    # In force every month up to maturity (the maturity row itself may flag
    # lapsed — premium collection and the exception machinery both stop at
    # the maturity age, so its ending values are an endowment artifact).
    pre_maturity_lapsed = [s for s in results if not s.matured and s.lapsed]
    assert not pre_maturity_lapsed, (
        f"policy lapsed before maturity at "
        f"yr {pre_maturity_lapsed[0].policy_year} mo {pre_maturity_lapsed[0].policy_month}")
    assert last.matured, "projection did not reach maturity"
    # The latch never releases.
    assert all(s.billable_md_switched for s in post_switch)

    print()
    print("BILLABLE-TO-MD CHECK PASSED")


if __name__ == "__main__":
    main()
