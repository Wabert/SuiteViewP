"""Verify PolicyInformation.benefit_renewal_rate() lookup logic.

Single-purpose, offline check (no DB2): builds a bare PolicyInformation via
__new__, stubs fetch_table() with a fake LH_BNF_INS_RNL_RT, and asserts the
67-segment renewal-rate lookup matches on coverage phase, benefit type,
benefit subtype and PRM_RT_TYP_CD = "B".

Run: venv\Scripts\python.exe tools\verify_benefit_renewal_rate.py
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.polview.models.policy_information import PolicyInformation


def main():
    pi = PolicyInformation.__new__(PolicyInformation)

    # Fake 67-segment rows. The target row is type 7 / subtype 6 / phase 1 / B.
    rows = [
        # Wrong rate type (issue, not renewal) — must be ignored.
        {"COV_PHA_NBR": 1, "SPM_BNF_TYP_CD": "7", "SPM_BNF_SBY_CD": "6",
         "PRM_RT_TYP_CD": "C", "RNL_RT": "9.99"},
        # Correct match.
        {"COV_PHA_NBR": 1, "SPM_BNF_TYP_CD": "7", "SPM_BNF_SBY_CD": "6",
         "PRM_RT_TYP_CD": "B", "RNL_RT": "0.34"},
        # Right type, wrong subtype.
        {"COV_PHA_NBR": 1, "SPM_BNF_TYP_CD": "7", "SPM_BNF_SBY_CD": "1",
         "PRM_RT_TYP_CD": "B", "RNL_RT": "1.11"},
        # Different coverage phase.
        {"COV_PHA_NBR": 2, "SPM_BNF_TYP_CD": "4", "SPM_BNF_SBY_CD": "1",
         "PRM_RT_TYP_CD": "B", "RNL_RT": "2.22"},
    ]
    pi.fetch_table = lambda table_name: rows if table_name == "LH_BNF_INS_RNL_RT" else []

    results = {}

    # Exact match -> 0.34 / 100000 (RNL_RT is stored scaled)
    r = pi.benefit_renewal_rate(1, "7", "6", "B")
    results["match_7_6_phase1_B"] = str(r)
    assert r == Decimal("0.34") / 100000, r

    # ABR14-style benefit with no B row -> None (blank)
    r = pi.benefit_renewal_rate(1, "4", "1", "B")
    results["no_B_row_for_4_1_phase1"] = r
    assert r is None, r

    # Different phase benefit that does have a B row
    r = pi.benefit_renewal_rate(2, "4", "1", "B")
    results["match_4_1_phase2_B"] = str(r)
    assert r == Decimal("2.22") / 100000, r

    # Wrong rate type only (C exists, no B) for a fabricated benefit -> None
    r = pi.benefit_renewal_rate(1, "7", "9", "B")
    results["no_match_7_9"] = r
    assert r is None, r

    print(json.dumps({"ok": True, "results": results}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(json.dumps({"ok": False, "error": f"assertion failed: {exc!r}"}))
        sys.exit(1)
