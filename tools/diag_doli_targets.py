"""Diagnostic: explain why the Targets & Accumulators tab's "Definition of Life
Insurance" section is blank for a given policy.

It dumps the exact fields the UI uses to decide what to show, plus the raw
LH_COV_INS_GDL_PRM and LH_POL_TARGET rows, so we can see whether the guideline
premiums live where the code looks for them.

Run on the WORK LAPTOP (needs live DB2):

    venv\\Scripts\\python.exe tools/diag_doli_targets.py '{"policy": "U0116323", "region": "CKPR"}'
    venv\\Scripts\\python.exe tools/diag_doli_targets.py U0116323 CKPR

Output: a single JSON object on stdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.policy_service import get_policy_info, clear_cache


def _jsonable(value):
    """Make Decimals/dates/etc. JSON-serializable."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _parse_args(argv):
    if len(argv) >= 2 and argv[1].strip().startswith("{"):
        cfg = json.loads(argv[1])
        return cfg.get("policy"), cfg.get("region", "CKPR")
    policy = argv[1] if len(argv) > 1 else "U0116323"
    region = argv[2] if len(argv) > 2 else "CKPR"
    return policy, region


def run(policy_number: str, region: str) -> dict:
    clear_cache()
    pi = get_policy_info(policy_number, region, None)
    if pi is None or not getattr(pi, "exists", False):
        return {"policy": policy_number, "region": region, "found": False}

    # --- The three gates the UI uses (targets_tab.load_data_from_policy) ---
    gates = {
        # Gate 1: whole section is blanked (only "Guideline/CVAT: CVAT" shown)
        # unless this is True.
        "is_advanced_product": _jsonable(pi.is_advanced_product),
        "NON_TRD_POL_IND (LH_BAS_POL)": _jsonable(
            pi.data_item("LH_BAS_POL", "NON_TRD_POL_IND")),
        # Gate 2: GSP/GLP/AccumGLP only show when gpt_cvat in ("GP","GPT").
        "TFDF_CD (LH_NON_TRD_POL)": _jsonable(
            pi.data_item("LH_NON_TRD_POL", "TFDF_CD")),
        "tefra_defra_code": _jsonable(pi.tefra_defra_code),
        "tefra_defra": _jsonable(pi.tefra_defra),
        "gpt_cvat": _jsonable(pi.gpt_cvat),
    }

    # --- The values the UI tries to show (Gate 3: where they are read from) ---
    values = {
        "glp  (LH_COV_INS_GDL_PRM PRM_RT_TYP_CD='A')": _jsonable(pi.glp),
        "gsp  (LH_COV_INS_GDL_PRM PRM_RT_TYP_CD='S')": _jsonable(pi.gsp),
        "accumulated_glp_target (LH_POL_TARGET TAR_TYP_CD='TA')":
            _jsonable(pi.accumulated_glp_target),
        "corridor_percent": _jsonable(pi.corridor_percent),
    }

    # --- Raw rows so we can SEE where the guideline premiums actually live ---
    def dump(table):
        try:
            return [{k: _jsonable(v) for k, v in row.items()}
                    for row in pi.fetch_table(table)]
        except Exception as exc:  # pragma: no cover - diagnostic only
            return {"error": str(exc)}

    raw = {
        "LH_COV_INS_GDL_PRM": dump("LH_COV_INS_GDL_PRM"),
        "LH_POL_TARGET": dump("LH_POL_TARGET"),
    }

    # --- What the UI ends up displaying, in words ---
    if not pi.is_advanced_product:
        verdict = ("is_advanced_product is False -> entire section blanked "
                   "except 'Guideline/CVAT: CVAT'. Blank GSP/GLP is EXPECTED.")
    elif pi.gpt_cvat not in ("GP", "GPT"):
        verdict = (f"advanced but gpt_cvat={pi.gpt_cvat!r} (not GP/GPT) -> "
                   "GSP/GLP/AccumGLP rows are hidden; only NSP shows. "
                   "Check LH_NON_TRD_POL.TFDF_CD.")
    elif pi.glp is None and pi.gsp is None:
        verdict = ("advanced + GP, but glp/gsp are None because "
                   "LH_COV_INS_GDL_PRM has no PRM_RT_TYP_CD 'A'/'S' rows. "
                   "See raw LH_COV_INS_GDL_PRM vs LH_POL_TARGET below.")
    else:
        verdict = "GSP/GLP should be visible with values -- section not blank."

    return {
        "policy": policy_number,
        "region": region,
        "found": True,
        "verdict": verdict,
        "gates": gates,
        "values": values,
        "raw_tables": raw,
    }


if __name__ == "__main__":
    policy, region = _parse_args(sys.argv)
    print(json.dumps(run(policy, region), indent=2))
