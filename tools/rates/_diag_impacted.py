"""Diagnostic: list the Plancode / BenefitType / Benefit combos that the
delete would impact, with per-combo index and row counts.

Read-only. Mirrors the target-selection logic of
delete_benefit_rates_over_age.py (BenefitType prefix match + "only trim indices
that end at or below age_max" protection rule), then reports the impact grouped
by (Plancode, BenefitType, Benefit).

    venv\\Scripts\\python.exe tools/rates/_diag_impacted.py tools/rates/delete_benefit_rates_config.json
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
    prefix = str(config.get("benefit_type_prefix", "")).strip()
    age_min = int(config["age_min"])
    age_max = int(config["age_max"])

    conn = pyodbc.connect(f"DSN={dsn}", autocommit=True, timeout=15)
    cursor = conn.cursor()

    ph = ", ".join("?" for _ in plancodes)
    cursor.execute(
        f"SELECT {_quote('Plancode')}, {_quote('BenefitType')}, "
        f"{_quote('Benefit')}, {_quote('Index(BENCOI)')} "
        f"FROM {_quote('POINT_BENEFIT')} WHERE {_quote('Plancode')} IN ({ph})",
        plancodes,
    )
    pointer_rows = [tuple(r) for r in cursor.fetchall()]

    candidate = sorted({
        int(index) for _pc, btype, _bn, index in pointer_rows
        if index is not None and (not prefix or str(btype).strip().startswith(prefix))
    })
    if not candidate:
        print("No candidate indices.")
        return

    att = f"({_quote('IssueAge')} + {_quote('Duration')} - 1)"
    cph = ", ".join("?" for _ in candidate)
    cursor.execute(
        f"SELECT {_quote('Index(BENCOI)')}, MAX({att}) FROM {_quote('RATE_BENCOI')} "
        f"WHERE {_quote('Index(BENCOI)')} IN ({cph}) GROUP BY {_quote('Index(BENCOI)')}",
        candidate,
    )
    max_att = {int(r[0]): int(r[1]) for r in cursor.fetchall() if r[1] is not None}
    target = {idx for idx in candidate if max_att.get(idx) is not None and max_att[idx] <= age_max}

    # Rows in delete range per index.
    tph = ", ".join("?" for _ in sorted(target)) if target else ""
    rows_per_index: dict[int, int] = defaultdict(int)
    if target:
        cursor.execute(
            f"SELECT {_quote('Index(BENCOI)')}, COUNT(*) FROM {_quote('RATE_BENCOI')} "
            f"WHERE {_quote('Index(BENCOI)')} IN ({tph}) AND {att} BETWEEN ? AND ? "
            f"GROUP BY {_quote('Index(BENCOI)')}",
            list(sorted(target)) + [age_min, age_max],
        )
        rows_per_index = {int(r[0]): int(r[1]) for r in cursor.fetchall()}

    # Group by (Plancode, BenefitType, Benefit) over target indices only.
    combo_indices: dict = defaultdict(set)
    for pc, btype, benefit, index in pointer_rows:
        if index is None or int(index) not in target:
            continue
        combo_indices[(str(pc).strip(), str(btype).strip(), str(benefit).strip())].add(int(index))

    print(f"Impacted combos (BenefitType prefix {prefix!r}, attained age "
          f"{age_min}-{age_max}, protecting indices that extend beyond {age_max}):\n")
    print(f"{'Plancode':<10} {'BenType':<8} {'Benefit':<8} {'#idx':>5} {'#rows':>8}")
    print("-" * 44)
    grand_rows = 0
    for (pc, btype, benefit), indices in sorted(combo_indices.items()):
        r = sum(rows_per_index.get(i, 0) for i in indices)
        grand_rows += r
        print(f"{pc:<10} {btype:<8} {benefit or '(blank)':<8} {len(indices):>5} {r:>8,}")
    print("-" * 44)
    print(f"{'TOTAL':<10} {'':<8} {'':<8} {len(target):>5} {grand_rows:>8,}")

    # Distinct plancodes / benefit types impacted.
    plancodes_hit = sorted({k[0] for k in combo_indices})
    btypes_hit = sorted({k[1] for k in combo_indices})
    print(f"\nDistinct plancodes impacted ({len(plancodes_hit)}): {', '.join(plancodes_hit)}")
    print(f"Distinct BenefitTypes impacted: {', '.join(btypes_hit)}")
    conn.close()


if __name__ == "__main__":
    main()
