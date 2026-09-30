"""Inspect UL_Rates schema ``rates`` for one plancode, read-only.

Usage: venv\\Scripts\\python.exe tools\\rates\\inspect_schema_plan.py <plancode> [company]
       [--values RATE_TYPE[,RATE_TYPE...]] [--age N]
       venv\\Scripts\\python.exe tools\\rates\\inspect_schema_plan.py family:ISWL

Prints every ``RATE_TYPE`` definition, the plancode's ``PLAN_DEF``/``PLAN_ATTR`` rows and
all CELL/PLAN assignments (with scale windows and rate-set grain). ``--values`` also
prints the values of those rate types at issue age ``--age`` so a rate can be matched
to CyberLife policy records.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.local_dev import local_data_enabled
from suiteview.core.rates_schema import RatesSchemaRepository


def _list_family(repo, family: str) -> None:
    rows = repo._query(
        "SELECT COMPANY, PLANCODE, USER_CODE, COVERAGE_ROLE, DESCRIPTION FROM rates.PLAN_DEF "
        "WHERE PRODUCT_FAMILY = ? ORDER BY PLANCODE, COMPANY", [family])
    for row in rows:
        print(json.dumps({"company": row[0], "plancode": row[1], "user": row[2], "role": row[3],
                          "description": row[4]}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plancode", help="plancode, or family:<PRODUCT_FAMILY> to list a family's plans")
    parser.add_argument("company", nargs="?")
    parser.add_argument("--values", default="")
    parser.add_argument("--age", type=int)
    args = parser.parse_args()
    if local_data_enabled():
        raise RuntimeError("Schema rates are live UL_Rates only.")
    if args.plancode.startswith("family:"):
        with RatesSchemaRepository() as repo:
            _list_family(repo, args.plancode.split(":", 1)[1])
        return
    wanted = {v.strip().upper() for v in args.values.split(",") if v.strip()}
    with RatesSchemaRepository() as repo:
        types = repo.rate_types()
        for rt in sorted(types.values(), key=lambda t: t.rate_type):
            print(json.dumps({"RATE_TYPE": rt.rate_type, "structure": rt.structure, "unit": rt.unit,
                              "date": rt.date_meaning, "family": rt.product_family,
                              "description": rt.description}))
        plans = [p for p in repo.plan_defs(args.plancode) if not args.company or p.company == args.company]
        for plan in plans:
            print(json.dumps({"PLAN_DEF": plan.company, "user": plan.user_code, "family": plan.product_family,
                              "role": plan.coverage_role, "description": plan.description,
                              "facts": dict(plan.facts)}, default=str))
            for attr in repo.plan_attrs(plan.company, args.plancode):
                print(json.dumps({"PLAN_ATTR": attr.attr, "value": attr.value}))
            cells = repo.cell_assignments(plan.company, args.plancode)
            windows = {}
            for w in repo.schedule_windows(sorted({c.schedule_id for c in cells})):
                windows.setdefault(w.schedule_id, []).append(w)
            set_ids = sorted({w.rate_set_id for ws in windows.values() for w in ws})
            sets = repo.rate_sets(set_ids)
            summary = {}
            for c in cells:
                for w in windows.get(c.schedule_id, []):
                    key = (c.rate_type, c.benefit, w.scale, str(w.effective_from), str(w.effective_to),
                           sets[w.rate_set_id].grain if w.rate_set_id in sets else "?")
                    summary.setdefault(key, set()).add(f"{c.sex}/{c.rate_class}/{c.band}/{c.state}/{c.subseries}")
            for key, keys in sorted(summary.items()):
                print(json.dumps({"CELL": key[0], "benefit": key[1], "scale": key[2], "from": key[3],
                                  "to": key[4], "grain": key[5], "cells": sorted(keys)[:12],
                                  "cell_count": len(keys)}))
            plan_rows = repo.plan_assignments(plan.company, args.plancode)
            plan_sets = repo.rate_sets([p.rate_set_id for p in plan_rows])
            for p in plan_rows:
                info = plan_sets.get(p.rate_set_id)
                print(json.dumps({"PLAN": p.rate_type, "scale": p.scale, "state": p.state,
                                  "rate_set": p.rate_set_id, "grain": info.grain if info else "?"}))
            if not wanted:
                continue
            for c in cells:
                if c.rate_type not in wanted:
                    continue
                for w in windows.get(c.schedule_id, []):
                    values = repo.rate_values([w.rate_set_id], args.age).get(w.rate_set_id, {})
                    series = {f"{age}/{dur}": float(rate) if rate is not None else None
                              for (age, dur), rate in sorted(values.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1] or 0))}
                    print(json.dumps({"VALUES": c.rate_type, "benefit": c.benefit, "cell":
                                      f"{c.sex}/{c.rate_class}/{c.band}/{c.state}/{c.subseries}",
                                      "scale": w.scale, "from": str(w.effective_from),
                                      "values": dict(list(series.items())[:80])}))


if __name__ == "__main__":
    main()
