"""Compute joint survivor COI expectations with the Cyberlife_Rates reference module.

Development-only helper for ``tests/test_joint_survivor_coi.py``: it imports the
reference ``joint_survivor_coi.py`` (never used by SuiteView at runtime) and
prints JSON expectations. Live cases read JS_Q / PLAN_ATTR from UL_Rates schema
``rates`` read-only through the reference ``RatesJointCOI``.

Usage:
    venv\\Scripts\\python.exe tools\\rates\\capture_joint_survivor_reference.py @cases.json

Config::

    {"reference_dir": "C:\\...\\Rates_Database\\scripts",
     "cases": [
       {"name": "...", "live": {"plancode": "N91EAB00", "x": ["F", "H", 49],
                                "y": ["M", "H", 49], "years": 12},
        "ratings": [{"person": "01", "type_code": "1", "table_code": "X", ...}]},
       {"name": "...", "base": {"C": [[...], [...]], "G": [[...], [...]]},
        "rules": {"table_pct": {...}, "cap_curr_at_guar": true, ...}, "ratings": []}
     ],
     "vround": [[0.000125, 5], ...]}
"""

from __future__ import annotations

import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DEFAULT_REFERENCE = Path(r"C:\Users\ab7y02\Dev\Cyberlife_Rates\Rates_Database\scripts")


def main() -> None:
    arg = sys.argv[1]
    config = json.loads(Path(arg[1:]).read_text(encoding="utf-8")) if arg.startswith("@") else json.loads(arg)
    sys.path.insert(0, str(Path(config.get("reference_dir") or DEFAULT_REFERENCE)))
    import joint_survivor_coi as ref  # noqa: E402  (the reference implementation)

    cursor = None
    out = {"cases": [], "vround": []}
    for case in config.get("cases", []):
        ratings = [ref.Rating(**r) for r in case.get("ratings", [])]
        if "live" in case:
            if cursor is None:
                import pyodbc
                cursor = pyodbc.connect("DSN=UL_Rates", readonly=True, autocommit=True).cursor()
            live = case["live"]
            calc = ref.RatesJointCOI(cursor, "26", live["plancode"])
            x, y = ref.Insured(*live["x"]), ref.Insured(*live["y"])
            years = live["years"]
            base = {c: (calc.base_rates(c, x, years), calc.base_rates(c, y, years)) for c in ("C", "G")}
            rules = calc.rules
            attrs = {k: v for k, v in calc.attrs.items()
                     if k in ("LIVES", "JS_TABLE_PCT", "JS_FLAT_FACTOR", "JS_CAP_CURR_AT_GUAR",
                              "JS_ZERO_GUAR_AT_Q1", "JS_ZERO_CURR_AT_Q0")}
            expected = {c: calc.monthly_coi(c, x, y, years, ratings) for c in ("C", "G")}
        else:
            base = {c: tuple(v) for c, v in case["base"].items()}
            rules = ref.JointRules(**case["rules"])
            attrs = None
            expected = {c: ref.joint_monthly_coi(base, c, ratings, rules) for c in ("C", "G")}
        out["cases"].append({
            "name": case.get("name", ""), "base": {c: [list(v[0]), list(v[1])] for c, v in base.items()},
            "plan_attributes": attrs, "rules": {
                "cap_curr_at_guar": rules.cap_curr_at_guar, "zero_guar_at_q1": rules.zero_guar_at_q1,
                "zero_curr_at_q0": rules.zero_curr_at_q0, "flat_factor": rules.flat_factor},
            "ratings": case.get("ratings", []), "expected": expected,
        })
    for value, places in config.get("vround", []):
        shortest = Decimal(repr(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        out["vround"].append({"value": value, "repr": repr(value), "places": places,
                              "reference": ref.vround(value, places),
                              "shortest_repr_half_up": float(shortest)})
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
