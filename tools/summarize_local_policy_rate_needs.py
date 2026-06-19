from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize plancodes and benefit rate keys needed by a local policy export."
    )
    parser.add_argument("policy_number", help="Policy number to inspect from local offline data")
    parser.add_argument("--region", default="CKPR", help="DB2 region code. Default: CKPR")
    parser.add_argument("--company", default=None, help="Optional company code")
    return parser.parse_args()


def _active_benefit_key(benefit) -> str:
    benefit_type = str(getattr(benefit, "benefit_type_cd", "") or "").strip()
    benefit_subtype = str(getattr(benefit, "benefit_subtype_cd", "") or "").strip()
    return benefit_type + benefit_subtype


def main() -> None:
    args = _parse_args()
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.core.policy_service import clear_cache, get_policy_info

    clear_cache()
    policy = get_policy_info(
        args.policy_number,
        region=args.region,
        company_code=args.company,
        use_cache=False,
    )
    if policy is None or not policy.exists:
        raise RuntimeError(f"Policy {args.policy_number} not found in local offline data")

    coverages = policy.get_coverages()
    riders = policy.get_riders()
    benefits = policy.get_benefits()

    plancodes = sorted({str(cov.plancode or "").strip() for cov in coverages if str(cov.plancode or "").strip()})
    benefit_types = sorted({key for benefit in benefits if (key := _active_benefit_key(benefit)) and not key.startswith("#")})

    print(json.dumps({
        "policy_number": policy.policy_number,
        "company_code": policy.company_code,
        "system_code": policy.system_code,
        "policy_id": policy.policy_id,
        "base_plancode": policy.base_plancode,
        "plancodes": plancodes,
        "rider_plancodes": sorted({str(rider.plancode or "").strip() for rider in riders if str(rider.plancode or "").strip()}),
        "benefit_types": benefit_types,
        "coverages": [
            {
                "coverage_phase": cov.cov_pha_nbr,
                "plancode": cov.plancode,
                "issue_age": cov.issue_age,
                "sex": cov.sex_code,
                "rate_class": cov.rate_class,
                "face_amount": str(cov.face_amount) if cov.face_amount is not None else None,
                "is_base": cov.is_base,
            }
            for cov in coverages
        ],
        "benefits": [
            {
                "coverage_phase": benefit.cov_pha_nbr,
                "benefit_type": benefit.benefit_type_cd,
                "benefit_subtype": benefit.benefit_subtype_cd,
                "benefit_key": _active_benefit_key(benefit),
                "issue_age": benefit.issue_age,
            }
            for benefit in benefits
        ],
    }, indent=2))


if __name__ == "__main__":
    main()