from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.core.policy_service import clear_cache, get_policy_info
    from suiteview.core.db2_connection import DB2Connection
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.calc_engine import IllustrationEngine

    clear_cache()
    db = DB2Connection("CKPR")
    table_probe = db.execute_query(
        "SELECT 1 FROM DB2TAB.LH_BAS_POL "
        "WHERE CK_SYS_CD = 'I' AND CK_POLICY_NBR = 'DEV10001' "
        "FETCH FIRST 1 ROWS ONLY"
    )
    if len(table_probe) != 1:
        raise RuntimeError("Local DB2 table probe failed")

    policy_numbers = ["DEV10001", "DEV10002", "DEV10003", "DEV10004", "DEV10005"]
    loaded = []
    for policy_number in policy_numbers:
        policy_info = get_policy_info(policy_number, region="CKPR", use_cache=False)
        if policy_info is None or not policy_info.exists:
            raise RuntimeError(f"PolicyInformation failed for {policy_number}")
        illustration_policy = build_illustration_data(
            policy_number,
            region="CKPR",
            company_code=policy_info.company_code,
        )
        states = IllustrationEngine().project(illustration_policy, months=2)
        loaded.append({
            "policy": policy_number,
            "company": policy_info.company_code,
            "plancode": illustration_policy.plancode,
            "face_amount": illustration_policy.face_amount,
            "account_value": illustration_policy.account_value,
            "states": len(states),
        })

    print(json.dumps({"loaded": loaded}, indent=2))


if __name__ == "__main__":
    main()