from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RATES_DB = ROOT / "bundled_data" / "dev" / "rates.sqlite"


def _representative_scale_band(plancode: str) -> tuple[int, int]:
    """Pick a valid (scale, band) present in the rates DB for a plancode.

    Older plancodes use scale/band 0 rather than 1, so a hard-coded band=1
    would spuriously fail. Falls back to (1, 1) when nothing is found.
    """
    if not RATES_DB.exists():
        return 1, 1
    conn = sqlite3.connect(f"file:{RATES_DB.as_posix()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT Scale, Band FROM Select_RATE_COI WHERE Plancode = ? LIMIT 1",
            (plancode,),
        ).fetchone()
    except sqlite3.Error:
        row = None
    finally:
        conn.close()
    if not row:
        return 1, 1
    return int(row[0]), int(row[1])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that a local policy's base-coverage UL rates load "
        "through the same Rates path the app uses."
    )
    parser.add_argument("policy_number", help="Policy number in local offline data")
    parser.add_argument("--region", default="CKPR", help="DB2 region code. Default: CKPR")
    parser.add_argument("--company", default=None, help="Optional company code")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    from suiteview.core.policy_service import clear_cache, get_policy_info
    from suiteview.core.rates import Rates

    clear_cache()
    policy = get_policy_info(
        args.policy_number,
        region=args.region,
        company_code=args.company,
        use_cache=False,
    )
    if policy is None or not policy.exists:
        raise RuntimeError(f"Policy {args.policy_number} not found in local offline data")

    rates = Rates()
    checks = []

    for cov in policy.get_coverages():
        plancode = str(cov.plancode or "").strip()
        if not plancode:
            continue
        scale, band = _representative_scale_band(plancode)
        common_args = {
            "issue_age": int(cov.issue_age),
            "sex": cov.sex_code,
            "rateclass": cov.rate_class,
            "scale": scale,
            "band": band,
        }
        coi = rates.get_rates("COI", plancode, **common_args)
        if not coi or len(coi) <= 1:
            raise RuntimeError(f"COI rates did not load for {plancode}: {common_args}")
        checks.append({
            "coverage_phase": cov.cov_pha_nbr,
            "plancode": plancode,
            "is_base": cov.is_base,
            "sample_args": common_args,
            "coi_rate_count": len(coi) - 1,
        })

    print(json.dumps({
        "policy_number": policy.policy_number,
        "base_plancode": policy.base_plancode,
        "checks": checks,
    }, indent=2))


if __name__ == "__main__":
    main()
