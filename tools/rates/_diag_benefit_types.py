"""Diagnostic: inspect BenefitType values + per-index max attained age.

Read-only. Reads the same config file as delete_benefit_rates_over_age.py and
prints, for the requested plancodes, each distinct (BenefitType) with its index
count and the distribution of per-index MAX attained ages. This is how we
identify which benefit was over-loaded (max attained age 64) vs. which ones are
correct (59, 39, ...), and the exact stored BenefitType string to filter on.

    venv\\Scripts\\python.exe tools/rates/_diag_benefit_types.py tools/rates/delete_benefit_rates_config.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import pyodbc


def _quote(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]") + "]"


def main() -> None:
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
    dsn = str(config.get("dsn", "UL_Rates")).strip() or "UL_Rates"
    plancodes = [str(p).strip() for p in config["plancodes"] if str(p).strip()]

    conn = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=15)
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in plancodes)
    cursor.execute(
        f"SELECT {_quote('Plancode')}, {_quote('BenefitType')}, "
        f"{_quote('Benefit')}, {_quote('Index(BENCOI)')} "
        f"FROM {_quote('POINT_BENEFIT')} "
        f"WHERE {_quote('Plancode')} IN ({placeholders})",
        plancodes,
    )
    rows = [tuple(r) for r in cursor.fetchall()]

    # index -> (benefit_type, benefit)
    idx_meta: dict[int, tuple] = {}
    by_type_indices: dict = defaultdict(set)
    for plancode, btype, benefit, index in rows:
        if index is None:
            continue
        idx = int(index)
        idx_meta[idx] = (btype, benefit)
        by_type_indices[(repr(btype), repr(benefit))].add(idx)

    all_indices = sorted(idx_meta)
    max_att: dict[int, int] = {}
    if all_indices:
        ph = ", ".join("?" for _ in all_indices)
        cursor.execute(
            f"SELECT {_quote('Index(BENCOI)')}, "
            f"MAX({_quote('IssueAge')} + {_quote('Duration')} - 1) "
            f"FROM {_quote('RATE_BENCOI')} "
            f"WHERE {_quote('Index(BENCOI)')} IN ({ph}) "
            f"GROUP BY {_quote('Index(BENCOI)')}",
            all_indices,
        )
        max_att = {int(r[0]): int(r[1]) for r in cursor.fetchall() if r[1] is not None}

    print(f"Plancodes requested: {len(plancodes)}  rows in POINT_BENEFIT: {len(rows)}  "
          f"distinct indices: {len(all_indices)}")
    print("\n(BenefitType, Benefit) -> index count, distribution of per-index max attained age:")
    for (btype_r, benefit_r), indices in sorted(by_type_indices.items()):
        dist: dict = defaultdict(int)
        for idx in indices:
            dist[max_att.get(idx, None)] += 1
        dist_str = ", ".join(f"max{age}={n}" for age, n in sorted(
            dist.items(), key=lambda kv: (kv[0] is None, kv[0])))
        print(f"  BenefitType={btype_r:>6}  Benefit={benefit_r:>6}  "
              f"indices={len(indices):>4}  [{dist_str}]")

    conn.close()


if __name__ == "__main__":
    main()
