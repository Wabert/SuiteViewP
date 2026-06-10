"""Empirically verify the RERUN MTP/CTP formulas against the DB-loaded values.

Computes the annual vMTP / vCTP from local rates per the RERUN CalcEngine
formulas (HW/IV/JG for MTP, JQ/KP/KQ for CTP) and compares to the values loaded
from the policy fixture (policy.mtp * 12, policy.ctp). Reports each component
and which SA-basis / band variant reproduces the DB value, so the engine
implementation uses the right settings.

Usage:
    venv\\Scripts\\python.exe tools/check_target_premium.py '{"policy":"U0688012","company":"01"}'
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _round2(x: float) -> float:
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(f"{x:.12f}").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def main() -> None:
    cmd = json.loads(sys.argv[1])
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.core.policy_service import clear_cache
    from suiteview.core.rates import Rates
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.models.plancode_config import load_plancode

    policy = cmd["policy"]
    region = cmd.get("region", "CKPR")
    company = cmd.get("company")

    clear_cache()
    pd = build_illustration_data(policy, region=region, company_code=company)
    config = load_plancode(pd.plancode)
    rates_db = Rates()

    seg_rows = []
    for seg in pd.segments:
        mtp_rate = rates_db.get_mtp(pd.plancode, seg.issue_age, seg.rate_sex, seg.rate_class, seg.band) or 0.0
        tbl_mtp = rates_db.get_tbl1_mtp(pd.plancode, seg.issue_age, seg.rate_sex, seg.rate_class, seg.band) or 0.0
        ctp_rate = rates_db.get_ctp(pd.plancode, seg.issue_age, seg.rate_sex, seg.rate_class, seg.band) or 0.0
        tbl_ctp = rates_db.get_tbl1_ctp(pd.plancode, seg.issue_age, seg.rate_sex, seg.rate_class, seg.band) or 0.0
        seg_rows.append({
            "cov": seg.coverage_phase, "issue_age": seg.issue_age,
            "sex": seg.rate_sex, "rateclass": seg.rate_class,
            "band": seg.band, "original_band": seg.original_band,
            "face": seg.face_amount, "original_face": seg.original_face_amount,
            "table_rating": seg.table_rating, "flat_extra": seg.flat_extra,
            "mtp_rate": mtp_rate, "tbl1_mtp_rate": tbl_mtp,
            "ctp_rate": ctp_rate, "tbl1_ctp_rate": tbl_ctp,
        })

    # Benefit target rates (PW etc.) at the POLICY issue age.
    base = pd.base_segment
    ben_rows = []
    for ben in pd.benefits:
        ben_type = (ben.benefit_type or "")
        if not ben.is_active or ben_type.startswith("#"):
            continue
        ben_key = ben_type + (ben.benefit_subtype or "")
        ben_mtp = rates_db.get_ben_mtp(
            pd.plancode, pd.issue_age, base.rate_sex, base.rate_class, base.band, ben_key)
        ben_ctp = rates_db.get_ben_ctp(
            pd.plancode, pd.issue_age, base.rate_sex, base.rate_class, base.band, ben_key)
        ben_rows.append({
            "key": ben_key, "units": ben.units, "amount": ben.benefit_amount,
            "ben_mtp_rate": ben_mtp, "ben_ctp_rate": ben_ctp,
        })

    factor = config.table_rating_factor

    def cov_target(sa: float, rate: float, tbl_rate: float, table: int, flat: float,
                   ctp_cap_tbl: bool) -> float:
        # HW: ROUND(SA*rate/1000,2) + ROUND(table*tbl_rate*SA/1000,2) + flat term
        # CTP variant (JQ) caps the tbl rate term at MIN(6, tbl_rate).
        t = min(6.0, tbl_rate) if ctp_cap_tbl else tbl_rate
        from decimal import Decimal, ROUND_DOWN
        flat_m = float(Decimal(f"{flat / 12.0:.12f}").quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        return (
            _round2(sa * rate / 1000.0)
            + _round2(table * t * sa / 1000.0)
            + _round2(12.0 * flat_m * sa / 1000.0)
        )

    def total(kind: str, sa_attr: str) -> dict:
        is_ctp = kind == "ctp"
        cov_sum = 0.0
        for seg, row in zip(pd.segments, seg_rows):
            sa = getattr(seg, sa_attr)
            cov_sum += cov_target(
                sa,
                row["ctp_rate" if is_ctp else "mtp_rate"],
                row["tbl1_ctp_rate" if is_ctp else "tbl1_mtp_rate"],
                seg.table_rating, seg.flat_extra or 0.0,
                ctp_cap_tbl=is_ctp,
            )
        # Benefits: PW handled separately (rate x MTP-without-PW); others units x rate.
        ben_sum = 0.0
        pw_rate_mtp = 0.0
        pw_rate_ctp = 0.0
        for row in ben_rows:
            if row["key"] in ("39", "3#"):
                pw_rate_mtp = row["ben_mtp_rate"] or 0.0
                pw_rate_ctp = row["ben_ctp_rate"] or 0.0
                continue
            rate = row["ben_ctp_rate" if is_ctp else "ben_mtp_rate"] or 0.0
            ben_sum += (row["units"] or 0.0) * rate
        mtp_wo_pw = cov_sum + ben_sum
        table1 = pd.segments[0].table_rating if pd.segments else 0
        # IV: PW MTP = pw_rate * (MTP w/o PW) * (1 + factor*table). KP: CTP PW = IV.
        pw_mtp = pw_rate_mtp * mtp_wo_pw * (1.0 + factor * table1)
        return {
            "cov_sum": cov_sum, "ben_sum": ben_sum,
            "pw_rate": pw_rate_ctp if is_ctp else pw_rate_mtp,
            "pw_component_mtp_basis": pw_mtp,
            "total_with_pw": mtp_wo_pw + (_round2(pw_mtp) if is_ctp else pw_mtp),
        }

    variants = {}
    for sa_attr in ("face_amount", "original_face_amount"):
        variants[f"mtp_{sa_attr}"] = total("mtp", sa_attr)
        variants[f"ctp_{sa_attr}"] = total("ctp", sa_attr)

    print(json.dumps({
        "policy": policy,
        "plancode": pd.plancode,
        "policy_issue_age": pd.issue_age,
        "table_rating_factor": factor,
        "db_mtp_monthly": pd.mtp,
        "db_mtp_annual": round(pd.mtp * 12.0, 2),
        "db_ctp": pd.ctp,
        "segments": seg_rows,
        "benefits": ben_rows,
        "variants": {
            k: {kk: round(vv, 4) if isinstance(vv, float) else vv for kk, vv in v.items()}
            for k, v in variants.items()
        },
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
