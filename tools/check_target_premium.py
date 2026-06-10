"""Verify the engine's MTP/CTP computation against the DB-loaded values.

Runs ``compute_target_premiums`` (the validated implementation in
suiteview/illustration/core/target_premium.py) on a local-fixture policy and
compares the result to the values admin loaded into DB2 (policy.mtp * 12,
policy.ctp), with per-segment/benefit rate detail for auditing.

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


def main() -> None:
    cmd = json.loads(sys.argv[1])
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.core.policy_service import clear_cache
    from suiteview.core.rates import Rates
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.target_premium import compute_target_premiums
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
        args = (pd.plancode, seg.issue_age, seg.rate_sex, seg.rate_class, seg.band)
        seg_rows.append({
            "cov": seg.coverage_phase, "issue_age": seg.issue_age,
            "sex": seg.rate_sex, "rateclass": seg.rate_class,
            "band": seg.band, "face": seg.face_amount,
            "table_rating": seg.table_rating, "flat_extra": seg.flat_extra,
            "mtp_rate": rates_db.get_mtp(*args),
            "tbl1_mtp_rate": rates_db.get_tbl1_mtp(*args),
            "ctp_rate": rates_db.get_ctp(*args),
            "tbl1_ctp_rate": rates_db.get_tbl1_ctp(*args),
        })

    result = compute_target_premiums(pd, config)

    print(json.dumps({
        "policy": policy,
        "plancode": pd.plancode,
        "policy_issue_age": pd.issue_age,
        "db_mtp_monthly": pd.mtp,
        "db_ctp_annual": pd.ctp,
        "computed_mtp_annual": round(result.mtp_annual, 4),
        "computed_mtp_monthly": result.mtp_monthly,
        "computed_ctp_annual": round(result.ctp_annual, 4),
        "mtp_monthly_matches_db": abs(result.mtp_monthly - (pd.mtp or 0.0)) < 0.005,
        "ctp_matches_db": abs(result.ctp_annual - (pd.ctp or 0.0)) < 0.005,
        "target_band": result.target_band,
        "mtp_by_coverage": result.mtp_by_coverage,
        "ctp_by_coverage": result.ctp_by_coverage,
        "mtp_benefits": result.mtp_benefits,
        "ctp_benefits": result.ctp_benefits,
        "segments": seg_rows,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
