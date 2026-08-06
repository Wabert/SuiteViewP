"""Dump each benefit's rate fields for a policy, as the Riders & Benefits
panel sees them (coi_rate = issue rate, renewal_rate = 67-segment B rate).

Requires SUITEVIEW_LOCAL_DATA=1 with the bundled dev SQLite policy DB.

Usage: venv\Scripts\python.exe tools\dump_benefit_rates.py '<json>'
    {"policy": "UE013383", "region": "CKPR"}
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.polview.models.policy_information import PolicyInformation


def main():
    cmd = json.loads(sys.argv[1])
    pi = PolicyInformation(cmd["policy"], region=cmd.get("region", "CKPR"))
    if not pi.exists:
        print(json.dumps({"ok": False, "error": "policy not found"}))
        sys.exit(1)

    benefits = []
    for ben in pi.get_benefits() or []:
        benefit_type = str(ben.benefit_type_cd or "")
        has_charge = bool(ben.coi_rate) or bool(ben.renewal_rate)
        benefits.append({
            "form": ben.form_number,
            "type": benefit_type,
            "subtype": ben.benefit_subtype_cd,
            "coi_rate": str(ben.coi_rate) if ben.coi_rate is not None else None,
            "renewal_rate": str(ben.renewal_rate) if ben.renewal_rate is not None else None,
            "adjustable": has_charge and not benefit_type.startswith("#"),
        })
    print(json.dumps({"ok": True, "policy": cmd["policy"], "benefits": benefits}, indent=2))


if __name__ == "__main__":
    main()
