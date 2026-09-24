"""Print every PolView Rates-tree matrix for a live policy (read-only).

Usage: venv\\Scripts\\python.exe tools\\rates\\dump_polview_rate_matrices.py '<json>'
JSON: {"policy": "13034048", "company": "01", "region": "CKPR", "rows": 40}

Each Rates-tree leaf's matrix (Coverages, Benefits, Fixed Premium for
ISWL/WL, Policy) is printed as compact JSON rows (the first ``rows`` data
rows); a failing leaf prints its error instead. ``only`` optionally limits the
output to leaf categories, e.g. ["Premium Rates", "Modal Premium"].
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.local_dev import local_data_enabled
from suiteview.core.policy_service import get_policy_info


def _cell(value):
    return value if isinstance(value, (int, float, str)) or value is None else str(value)


def main():
    arg = sys.argv[1]
    config = json.loads(Path(arg[1:]).read_text(encoding="utf-8")) if arg.startswith("@") else json.loads(arg)
    if local_data_enabled():
        raise RuntimeError("This helper requires live data, not SUITEVIEW_LOCAL_DATA.")
    policy = get_policy_info(
        config["policy"], region=config.get("region", "CKPR"),
        company_code=config.get("company"), use_cache=False,
    )
    if policy is None or not policy.exists:
        raise RuntimeError("Policy was not found or live policy access failed.")
    limit = int(config.get("rows", 40))
    print(json.dumps({
        "policy": policy.policy_number, "company": policy.company_code,
        "product_type": policy.product_type, "advanced": policy.is_advanced_product,
        "coverages": policy.coverage_count, "benefits": policy.benefit_count,
    }))
    leaves = [("Coverages", i, policy.build_coverage_rate_matrix) for i in range(1, policy.coverage_count + 1)]
    leaves += [("Benefits", i, policy.build_benefit_rate_matrix) for i in range(1, policy.benefit_count + 1)]
    if policy.has_fixed_premium_rates:
        for i in range(1, policy.coverage_count + 1):
            leaves.append(("Cash Values", i, policy.build_whole_life_coverage_rate_matrix))
            leaves.append(("Premium Rates", i, policy.build_premium_rate_matrix))
        leaves.append(("Modal Premium", 1, lambda _i: policy.build_modal_premium_matrix()))
    leaves.append(("Policy", 1, lambda _i: policy.build_policy_rate_matrix()))
    rates = policy._get_rates()
    only = set(config.get("only") or [])
    try:
        for category, index, build in leaves:
            if only and category not in only:
                continue
            print(f"== {category} {index}")
            try:
                matrix = build(index)
            except Exception as exc:  # report every leaf, not just the first failure
                print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
                continue
            if matrix is None:
                print(json.dumps({"matrix": None}))
                continue
            print(json.dumps({"rows": len(matrix) - 1}))
            for row in matrix[:limit + 1]:
                print(json.dumps([_cell(value) for value in row]))
    finally:
        if rates is not None:
            rates.close()


if __name__ == "__main__":
    main()
