"""Verify the ABR PVFB drops a level-term rider when it expires.

Reproduces the UE066696 issue: a policy whose primary-insured death benefit is
the base face plus a level-term rider that expires mid-term. The rider face must
be included in the projected death benefit (PVFB) up to its expiry month and then
dropped, rather than held level for the whole projection.

Constructs a synthetic policy (base 100,000 + 25,000 level-term rider expiring at
absolute policy month 192) and confirms:

    1. death_benefit_at() returns 125,000 through month 192 and 100,000 after.
    2. The per-month PVDB projection reflects that drop (early rows carry 125,000,
       later rows carry 100,000).
    3. Dropping the rider lowers PVFB, so the actuarial discount is larger than
       the old (buggy) level-125,000 projection.

Run: venv\\Scripts\\python.exe tools\\rates\\verify_abr_rider_drop.py
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.abrquote.models.abr_data import ABRPolicyData, DBLayer
from suiteview.abrquote.core.apv_engine import APVEngine


def _run(policy: ABRPolicyData):
    n_months = (policy.maturity_age - policy.issue_age) * 12
    monthly_qx = [0.0008] * n_months
    premium_schedule = [500.0] * (policy.maturity_age - policy.issue_age)
    engine = APVEngine(annual_interest_rate=0.0545, policy_data=policy)
    return engine.compute_detailed_table(
        monthly_qx, premium_schedule,
        death_benefit=policy.default_death_benefit,
    )


def main() -> None:
    base_face = 100_000.0
    rider_face = 25_000.0
    total_face = base_face + rider_face
    rider_expiry_month = 192  # absolute policy month the rider drops after

    policy = ABRPolicyData(
        policy_number="UE066696",
        issue_age=35,
        attained_age=45,
        sex="M",
        face_amount=total_face,           # current primary-insured face (base+rider)
        db_option="1",                    # Option A (level)
        maturity_age=95,
        issue_state="TX",
        policy_year=11,
        policy_month=1,
        product_type="TERM",
        db_layers=[
            DBLayer(face_amount=base_face, expiry_month=None),          # base to maturity
            DBLayer(face_amount=rider_face, expiry_month=rider_expiry_month),
        ],
    )

    # 1. death_benefit_at() drops the rider at the right month.
    assert policy.death_benefit_at(rider_expiry_month) == total_face, "rider should be in force at expiry month"
    assert policy.death_benefit_at(rider_expiry_month + 1) == base_face, "rider should drop after expiry month"
    assert policy.default_death_benefit == total_face
    print(f"death_benefit_at({rider_expiry_month}) = {policy.death_benefit_at(rider_expiry_month):,.0f}")
    print(f"death_benefit_at({rider_expiry_month + 1}) = {policy.death_benefit_at(rider_expiry_month + 1):,.0f}")

    # 2. Per-month projection reflects the drop.
    rows, summary = _run(policy)
    dbs = sorted({round(r["death_benefit"], 2) for r in rows})
    print(f"Row death benefits present: {dbs}")
    assert dbs == [base_face, total_face], f"expected both {base_face} and {total_face}, got {dbs}"

    current_month = (policy.policy_year - 1) * 12 + policy.policy_month
    for r in rows:
        expected = total_face if r["month"] <= rider_expiry_month else base_face
        assert round(r["death_benefit"], 2) == expected, (
            f"month {r['month']}: db={r['death_benefit']} expected {expected}"
        )
    print(f"current abs month = {current_month}; rider expires after {rider_expiry_month}")
    print(f"summary death_benefit (initial) = {summary['death_benefit']:,.2f}")
    assert summary["death_benefit"] == total_face

    declining_discount = summary["actuarial_discount"]
    print(f"declining-rider actuarial discount = {declining_discount:,.2f}")

    # 3. Compare against the level-125k (bug) projection.
    #    Dropping future benefit lowers PVFB, so the accelerated net value
    #    (PVFB - PVFP) shrinks and the actuarial discount GROWS relative to the
    #    old level-125k projection. It also differs from a level-100k projection.
    level_hi = replace(policy, db_layers=[])           # falls back to level face_amount (125k)
    _, sum_hi = _run(level_hi)
    level_lo = replace(policy, db_layers=[], face_amount=base_face)
    _, sum_lo = _run(level_lo)
    print(f"level-125k discount (old buggy) = {sum_hi['actuarial_discount']:,.2f}")
    print(f"level-100k discount             = {sum_lo['actuarial_discount']:,.2f}")

    assert declining_discount > sum_hi["actuarial_discount"], (
        "dropping the rider should increase the discount vs the level-125k projection"
    )
    assert declining_discount != sum_hi["actuarial_discount"], (
        "declining projection must differ from the old level-125k projection"
    )

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
