"""Inspect parsed IAF rate structure for workup design verification.

Usage:
    venv\\Scripts\\python.exe tools/inspect_iaf_rates.py <iaf_file> [<iaf_file> ...]

For each file, reports (JSON to stdout):
  - plancode, pay_age, product count, rate count
  - per rate_type: count, distinct durations (condensed), distinct bands,
    distinct plan_options, scale_start dates
  - base ('**') current COI: combos, whether select/ultimate/dur0 rates exist,
    and combos that have ONLY dur-0 rates (the "looks select, acts ultimate" case)
  - guaranteed ('**' G): bands present, whether banded combos exist
"""

import json
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from suiteview.ratemanager.parser import IAFParser  # noqa: E402


def _condense(values):
    """Condense a sorted int list into range strings, e.g. [1,2,3,7] -> '1-3,7'."""
    vals = sorted(set(values))
    if not vals:
        return ""
    parts = []
    start = prev = vals[0]
    for v in vals[1:]:
        if v == prev + 1:
            prev = v
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = v
    parts.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(parts)


def inspect(path):
    result = IAFParser().parse(path)
    if result.error:
        return {"file": path, "error": result.error}

    out = {
        "file": path,
        "plancode": result.products[0].plancode if result.products else "",
        "pay_age": result.products[0].pay_age if result.products else None,
        "me_age": result.products[0].me_age if result.products else None,
        "products": len(result.products),
        "rates": len(result.rates),
        "rate_types": {},
    }

    by_type = defaultdict(list)
    for r in result.rates:
        by_type[r.rate_type].append(r)

    for rt, rows in sorted(by_type.items()):
        durs = [r.duration for r in rows]
        out["rate_types"][rt] = {
            "count": len(rows),
            "durations": _condense(durs),
            "bands": sorted({r.band for r in rows}),
            "genders": sorted({r.gender for r in rows}),
            "classes": sorted({r.rate_class for r in rows}),
            "plan_options": sorted({r.plan_option.strip() for r in rows}),
            "scale_starts": sorted({r.scale_start for r in rows}),
            "attained_ages": _condense([r.attained_age for r in rows]),
        }

    # Base current COI structure per combo
    combo_durs = defaultdict(set)
    for r in by_type.get("C", []):
        if r.plan_option.strip() == "**":
            combo_durs[(r.gender, r.rate_class, r.band)].add(r.duration)

    dur0_only, has_select, has_ult, has_dur0 = [], 0, 0, 0
    for combo, durs in sorted(combo_durs.items()):
        sel = any(0 < d < 99 for d in durs)
        ult = 99 in durs
        d0 = 0 in durs
        has_select += sel
        has_ult += ult
        has_dur0 += d0
        if d0 and not sel and not ult:
            dur0_only.append("/".join(combo))
    out["base_C"] = {
        "combos": len(combo_durs),
        "combos_with_select": has_select,
        "combos_with_ultimate99": has_ult,
        "combos_with_dur0": has_dur0,
        "combos_dur0_ONLY": dur0_only,
    }

    g_bands = sorted({r.band for r in by_type.get("G", [])
                      if r.plan_option.strip() == "**"})
    g_durs = _condense([r.duration for r in by_type.get("G", [])
                        if r.plan_option.strip() == "**"])
    out["base_G"] = {"bands": g_bands, "durations": g_durs}

    return out


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: inspect_iaf_rates.py <file> [...]"}))
        return 1
    print(json.dumps([inspect(p) for p in sys.argv[1:]], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
