r"""Verify total policy debt for one policy via PolicyInformation (ground truth).

Prints total_loan_balance / principal / interest so a batch aggregation can be
checked against the canonical PolicyInformation logic.

Usage:
    venv\Scripts\python.exe tools/verify_policy_debt.py <policy> [company] [region]
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")
from suiteview.core.policy_service import get_policy_info  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: verify_policy_debt.py <policy> [company] [region]"}))
        sys.exit(1)
    policy = sys.argv[1]
    company = sys.argv[2] if len(sys.argv) > 2 else None
    region = sys.argv[3] if len(sys.argv) > 3 else "CKPR"

    pi = get_policy_info(policy, company_code=company, region=region)
    if not pi or not pi.exists:
        print(json.dumps({"policy": policy, "found": False}))
        return

    print(json.dumps({
        "policy": policy,
        "company": pi.company_code,
        "tch_pol_id": pi.policy_id,
        "found": True,
        "total_loan_balance": str(pi.total_loan_balance),
        "total_loan_principal": str(pi.total_loan_principal),
        "total_loan_interest": str(pi.total_loan_interest),
    }, indent=2))


if __name__ == "__main__":
    main()
