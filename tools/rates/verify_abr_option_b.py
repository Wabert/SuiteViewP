"""Verify Option B UL death-benefit handling in the ABR APV engine.

Constructs a synthetic Option B policy (Face 100,000 + Account Value 2,206.72
= locked-in death benefit 102,206.72) and confirms:

    1. The per-month PVDB projection uses the death benefit, not the bare face
       (each row exposes a "death_benefit" of 102,206.72).
    2. Full Acceleration eligible death benefit == 102,206.72 with no
       double-scaling of the actuarial discount.
    3. Max Partial eligible death benefit == 102,206.72 - min_face.

Run: venv\\Scripts\\python.exe tools\\verify_abr_option_b.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.abrquote.models.abr_data import ABRPolicyData
from suiteview.abrquote.core.apv_engine import APVEngine


def main() -> None:
    face = 100_000.0
    account_value = 2_206.72
    expected_db = 102_206.72
    min_face = 25_000.0

    policy = ABRPolicyData(
        policy_number="UE128653",
        issue_age=40,
        attained_age=45,
        sex="M",
        face_amount=face,
        account_value=account_value,
        db_option="2",          # Option B (Increasing)
        maturity_age=95,
        issue_state="TX",
        policy_year=6,
        policy_month=1,
        product_type="UL",
    )

    assert abs(policy.default_death_benefit - expected_db) < 0.005, (
        f"default_death_benefit={policy.default_death_benefit} != {expected_db}"
    )

    # A flat, benign monthly mortality series so the projection runs.
    n_months = (policy.maturity_age - policy.issue_age) * 12
    monthly_qx = [0.0001] * n_months
    premium_schedule = [1000.0] * (policy.maturity_age - policy.issue_age)

    engine = APVEngine(annual_interest_rate=0.0545, policy_data=policy)
    rows, summary = engine.compute_detailed_table(
        monthly_qx, premium_schedule,
        death_benefit=policy.default_death_benefit,
    )

    # 1. Every row projects the locked-in death benefit.
    row_dbs = {round(r["death_benefit"], 2) for r in rows}
    print(f"Row death benefits present: {sorted(row_dbs)}")
    assert row_dbs == {expected_db}, f"Unexpected row death benefits: {row_dbs}"

    # Sanity: PVDB(t) at t=0 should equal (DB/1000) * qx * tp_x * v_benefit.
    r0 = rows[0]
    manual = (expected_db / 1000.0) * r0["qx_monthly"] * r0["tp_x"] * r0["v_benefit"]
    assert abs(r0["pvdb_t"] - manual) < 1e-9, (
        f"pvdb_t={r0['pvdb_t']} != manual {manual}"
    )
    print(f"summary death_benefit: {summary['death_benefit']:.2f}")
    assert abs(summary["death_benefit"] - expected_db) < 0.005

    # 2. Full acceleration eligible == death benefit, no double scaling.
    full = engine.compute_full_acceleration(
        admin_fee=100.0,
        apv_summary=summary,
        surrender_value=1_017.20,
        eligible_death_benefit=policy.default_death_benefit,
    )
    print(f"full eligible_db: {full['eligible_db']:.2f}")
    assert abs(full["eligible_db"] - expected_db) < 0.005
    # discount must equal the summary discount (no re-scaling since base==face)
    assert abs(full["actuarial_discount"] - summary["actuarial_discount"]) < 0.005, (
        f"full discount {full['actuarial_discount']} != summary "
        f"{summary['actuarial_discount']}"
    )

    # 3. Max partial eligible == death benefit - min_face.
    partial = engine.compute_partial_acceleration(
        full, min_face=min_face, admin_fee=100.0,
    )
    expected_partial = expected_db - min_face  # 77,206.72
    print(f"partial eligible_db: {partial['eligible_db']:.2f} "
          f"(expected {expected_partial:.2f})")
    assert abs(partial["eligible_db"] - expected_partial) < 0.005, (
        f"partial eligible {partial['eligible_db']} != {expected_partial}"
    )

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
