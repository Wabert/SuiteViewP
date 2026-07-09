"""Smoke-test the CKULTB01 (EPU) parser against a real report file.

Usage:
    venv\\Scripts\\python.exe tools/inspect_ckultb01.py <file> [max_groups]

Prints (JSON): total records, plan/freq/rule groups (first N), sample records,
distinct wildcard usage, and any suspicious values (MAXIMUM not sentinel).
"""

import json
import sys
from collections import Counter

sys.path.insert(0, ".")

from suiteview.ratemanager.ckultb01_parser import iter_records  # noqa: E402


def main():
    path = sys.argv[1]
    max_groups = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    total = 0
    groups = Counter()
    sexes = Counter()
    states = Counter()
    bands = Counter()
    classes = Counter()
    monthdurs = Counter()
    nonsentinel_max = 0
    samples = []

    for rec in iter_records(path):
        total += 1
        groups[(rec["PLAN_CODE"], rec["FREQ_TYPE"], rec["RULE_CODE"])] += 1
        sexes[rec["SEX_CODE"]] += 1
        states[rec["STATE_CODE"]] += 1
        bands[rec["BAND_CODE"]] += 1
        classes[rec["RATE_CLASS"]] += 1
        monthdurs[rec["MONTH_DUR"]] += 1
        if rec["MAXIMUM"] < 9_999_999.0:
            nonsentinel_max += 1
        if total <= 6 or (total % 50000 == 0):
            samples.append(rec)

    out = {
        "total_records": total,
        "group_count": len(groups),
        "groups_first": [
            {"plan": p, "freq": f, "rule": r, "count": n}
            for (p, f, r), n in sorted(groups.items())[:max_groups]
        ],
        "sex_codes": dict(sexes),
        "state_codes_top": dict(states.most_common(10)),
        "bands": dict(bands),
        "classes": dict(classes),
        "monthdurs_top": {str(k): v for k, v in monthdurs.most_common(12)},
        "nonsentinel_maximum_rows": nonsentinel_max,
        "samples": samples,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
