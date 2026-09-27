from __future__ import annotations

def _project_with_engine(engine, policy, **kwargs):
    from suiteview.illustration.api import project_policy

    if "future_inputs" in kwargs:
        kwargs["inputs"] = kwargs.pop("future_inputs")
    if "rates_override" in kwargs:
        kwargs["rates"] = kwargs.pop("rates_override")
    return project_policy(policy, engine=engine, **kwargs).states
def _load_policy_data(*args, **kwargs):
    from suiteview.illustration.api import load_policy_data

    return load_policy_data(*args, **kwargs)
import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_POLICIES = ["DEV10001", "DEV10002", "DEV10003", "DEV10004", "DEV10005"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the local policy SQLite database.")
    parser.add_argument("policy_numbers", nargs="*", help="Policy numbers to load from local mode")
    parser.add_argument("--region", default="CKPR", help="DB2 region code. Default: CKPR")
    parser.add_argument(
        "--policy-only",
        action="store_true",
        help="Only validate PolicyInformation loading; skip illustration projection.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.polview.services.policy_service import clear_cache, get_policy_info
    from suiteview.core.db2_connection import DB2Connection
    from suiteview.illustration.core.calc_engine import IllustrationEngine

    policy_numbers = args.policy_numbers or DEFAULT_POLICIES
    clear_cache()
    db = DB2Connection(args.region)
    table_probe = db.execute_query(
        "SELECT 1 FROM DB2TAB.LH_BAS_POL "
        "WHERE CK_SYS_CD = 'I' AND CK_POLICY_NBR = ? "
        "FETCH FIRST 1 ROWS ONLY",
        (policy_numbers[0],),
    )
    if len(table_probe) != 1:
        raise RuntimeError("Local DB2 table probe failed")

    loaded = []
    for policy_number in policy_numbers:
        policy_info = get_policy_info(policy_number, region=args.region, use_cache=False)
        if policy_info is None or not policy_info.exists:
            raise RuntimeError(f"PolicyInformation failed for {policy_number}")
        result = {
            "policy": policy_number,
            "company": policy_info.company_code,
            "policy_id": policy_info.policy_id,
        }
        if args.policy_only:
            loaded.append(result)
            continue

        illustration_policy = _load_policy_data(
            policy_number,
            region=args.region,
            company_code=policy_info.company_code,
        )
        states = _project_with_engine(IllustrationEngine(), illustration_policy, months=2)
        result.update({
            "plancode": illustration_policy.plancode,
            "face_amount": illustration_policy.face_amount,
            "account_value": illustration_policy.account_value,
            "states": len(states),
        })
        loaded.append(result)

    print(json.dumps({"loaded": loaded}, indent=2))


if __name__ == "__main__":
    main()