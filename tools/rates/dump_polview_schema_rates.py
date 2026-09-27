"""Print PolView's schema-``rates`` Rates-tree leaves for live policies (read-only).

Usage: venv\\Scripts\\python.exe tools\\rates\\dump_polview_schema_rates.py '<json>'
JSON: {"policies": [{"policy": "UE063797", "company": "01"}], "region": "CKPR",
       "rows": 12, "summary": false, "only": ["Schema Coverage"]}

Each policy's schema leaves (Coverages, Benefits, Policy Rates, Fund Rates, Modal
Factors, Rate Space) go through ``build_rate_selection`` exactly as the Rates tree
does. ``summary`` prints only each leaf's header, row count and the metadata lines
under "Cells used", "Missing" and "Dated schedules"; otherwise the first ``rows``
data rows are printed too. A failing leaf prints its error and the run continues.
``@path.json`` reads the JSON from a file.
"""

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.local_dev import local_data_enabled
from suiteview.polview.services.policy_service import get_policy_info
from suiteview.polview.services.rate_selection import (
    SCHEMA_BENEFIT, SCHEMA_COVERAGE, SCHEMA_FUNDS, SCHEMA_MODAL, SCHEMA_POLICY, SCHEMA_SPACE,
    build_rate_selection,
)

SECTIONS = ("Cells used", "Missing", "Dated schedules", "Single rates")


def _cell(value):
    return value if isinstance(value, (int, float, str)) or value is None else str(value)


def _summary_lines(matrix):
    lines, section = [], None
    for row in matrix[1:]:
        name, info = str(row[0]), row[1]
        if name in SECTIONS:
            section = name
            continue
        if section and name.startswith("  "):
            lines.append(f"{section}: {name.strip()} = {info}")
        elif name.strip():
            section = None
    return lines


def _leaves(policy):
    leaves = [(SCHEMA_COVERAGE, i) for i in range(1, policy.coverages.coverage_count + 1)]
    leaves += [(SCHEMA_BENEFIT, i) for i in range(1, policy.benefits.benefit_count + 1)]
    leaves += [(SCHEMA_POLICY, 1), (SCHEMA_FUNDS, 1), (SCHEMA_MODAL, 1), (SCHEMA_SPACE, 1)]
    return leaves


def _dump(entry, config):
    policy = get_policy_info(
        entry["policy"], region=entry.get("region", config.get("region", "CKPR")),
        company_code=entry.get("company"), use_cache=False,
    )
    if policy is None or not policy.exists:
        print(json.dumps({"policy": entry["policy"], "error": "not found or live policy access failed"}))
        return
    print(json.dumps({
        "policy": policy.policy_number, "company": policy.company_code,
        "product_type": policy.product.product_type,
        "coverages": [c.plancode for c in policy.coverages.get_coverages()],
        "benefits": [b.benefit_code for b in policy.benefits.get_benefits()],
    }))
    only = set(config.get("only") or [])
    limit = int(config.get("rows", 12))
    for category, index in _leaves(policy):
        if only and category not in only:
            continue
        print(f"== {policy.policy_number} {category} {index}")
        try:
            selection = build_rate_selection(policy, category, index)
        except Exception as exc:  # report every leaf, not just the first failure
            print(json.dumps({"error": f"{type(exc).__name__}: {exc}",
                              "trace": traceback.format_exc()[-1200:]}))
            continue
        if selection.message:
            print(json.dumps({"message": selection.message}))
            continue
        matrix = selection.matrix or []
        print(json.dumps({"title": selection.display_title, "rows": max(len(matrix) - 1, 0),
                          "header": matrix[0] if matrix else []}))
        if config.get("summary"):
            if category in (SCHEMA_COVERAGE, SCHEMA_BENEFIT, SCHEMA_POLICY):
                for line in _summary_lines(matrix):
                    print("   " + line)
            continue
        for row in matrix[1:limit + 1]:
            print(json.dumps([_cell(value) for value in row]))


def main():
    arg = sys.argv[1]
    config = json.loads(Path(arg[1:]).read_text(encoding="utf-8")) if arg.startswith("@") else json.loads(arg)
    if local_data_enabled():
        raise RuntimeError("This helper requires live data, not SUITEVIEW_LOCAL_DATA.")
    for entry in config["policies"]:
        try:
            _dump(entry, config)
        except Exception as exc:
            print(json.dumps({"policy": entry.get("policy"), "error": f"{type(exc).__name__}: {exc}",
                              "trace": traceback.format_exc()[-1200:]}))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
