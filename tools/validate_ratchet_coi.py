"""Validate the ratchet-banding COI against the in-force system COI.

For each FPL83 test policy, run the inforce-month deduction two ways:
  * ratchet ON  (config.rachet_banding=True)  — the new band-split COI
  * ratchet OFF (config.rachet_banding=False) — the regular single-band COI

and compare both against the system's stored COI charge. The ratchet path should
match the system to the penny; the regular path should differ (proving the band
split is what makes it correct, not a coincidence).

Usage:
    venv\\Scripts\\python.exe tools/validate_ratchet_coi.py
    venv\\Scripts\\python.exe tools/validate_ratchet_coi.py '{"policies":["UL054426","UL058426"]}'
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SUITEVIEW_LOCAL_DATA", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.models.plancode_config import load_plancode


DEFAULT_POLICIES = ["UL054426", "UL058426"]


def _inforce_coi(policy_num: str, region: str, ratchet: bool) -> dict:
    policy = build_illustration_data(policy_num, region)
    config = load_plancode(policy.plancode)  # cached singleton
    prev = config.rachet_banding
    config.rachet_banding = ratchet
    try:
        result = IllustrationEngine().project(policy, months=1)[0]
    finally:
        config.rachet_banding = prev
    return {
        "plancode": policy.plancode,
        "segments": len(policy.segments),
        "face": policy.face_amount,
        "system_coi": round(float(policy.system_coi_charge), 2),
        "calc_coi": round(float(result.coi_charge), 2),
        "calc_total_deduction": round(float(result.total_deduction), 2),
        "system_total_deduction": round(float(policy.system_monthly_deduction), 2),
        # End-to-end check that the engine carries the band detail onto the state.
        "state_ratchet_active": bool(getattr(result, "ratchet_active", False)),
        "state_band_break": float(getattr(result, "band_break", 0.0)),
        "state_band1_nar": {k: round(v, 2) for k, v in getattr(result, "coi_band1_nar_by_coverage", {}).items()},
        "state_band2_nar": {k: round(v, 2) for k, v in getattr(result, "coi_band2_nar_by_coverage", {}).items()},
    }


def main() -> None:
    policies = DEFAULT_POLICIES
    region = "CKPR"
    if len(sys.argv) > 1:
        cmd = json.loads(sys.argv[1])
        policies = cmd.get("policies", DEFAULT_POLICIES)
        region = cmd.get("region", region)

    out = []
    for pol in policies:
        on = _inforce_coi(pol, region, ratchet=True)
        off = _inforce_coi(pol, region, ratchet=False)
        out.append({
            "policy": pol,
            "plancode": on["plancode"],
            "segments": on["segments"],
            "face": on["face"],
            "system_coi": on["system_coi"],
            "ratchet_on_coi": on["calc_coi"],
            "ratchet_off_coi": off["calc_coi"],
            "ratchet_on_matches_system": on["calc_coi"] == on["system_coi"],
            "ratchet_off_matches_system": off["calc_coi"] == on["system_coi"],
            "ratchet_changes_coi": on["calc_coi"] != off["calc_coi"],
            "state_ratchet_active": on["state_ratchet_active"],
            "state_band_break": on["state_band_break"],
            "state_band1_nar": on["state_band1_nar"],
            "state_band2_nar": on["state_band2_nar"],
        })

    print(json.dumps({"results": out}, indent=2, default=str))


if __name__ == "__main__":
    main()
