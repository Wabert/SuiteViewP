"""Delete over-loaded benefit COI rates from the shared UL_Rates database.

Context
-------
Some BenefitType-4 benefit rates were loaded to the maturity age (65) instead of
the payup age (60). In ``RATE_BENCOI`` a rate's *attained age* is
``IssueAge + Duration - 1`` (see ``suiteview/ratemanager/benefit_db.py``). Rates
should stop before the cease age, so with cease age 60 the last charged attained
age is 59. This script removes the extra ``RATE_BENCOI`` rows whose attained age
falls in a given inclusive range (default 60-64) for the benefit COI indices
that a set of plancodes point at.

Only ``RATE_BENCOI`` is touched. ``POINT_BENEFIT`` (the pointer) and
``RATE_BENTRG`` (target premiums, keyed by IssueAge only) are left untouched.

Safety
------
* Read-only PREVIEW by default. It writes nothing unless ``"commit": true`` is
  present in the config (or ``--commit`` is passed).
* Benefit COI indices are shared across plancodes. The preview reports every
  plancode/benefit that references each affected index so a shared index can't be
  trimmed by surprise. (Per the task owner, the fix is intentionally extended to
  any co-referencing plancode, since they share the identical over-loaded rates.)
* Before any DELETE the exact rows are backed up to CSV under
  ``~/.suiteview/rate_manager_backups/<timestamp>_delete_benefit_rates/``.
* The DELETE runs inside a single serializable transaction; the same range is
  re-counted afterwards and the transaction only commits when 0 rows remain.
* Refuses to run in a read-only (SuiteView Light) edition.

Usage
-----
    # read-only preview (default)
    venv\\Scripts\\python.exe tools/rates/delete_benefit_rates_over_age.py tools/rates/delete_benefit_rates_config.json

    # execute the delete
    venv\\Scripts\\python.exe tools/rates/delete_benefit_rates_over_age.py tools/rates/delete_benefit_rates_config.json --commit

The single positional argument is either a path to a JSON config file or an
inline JSON string with keys: ``plancodes`` (list), ``benefit_type`` (str or
null for all), ``age_min``, ``age_max``, ``dsn``, and optional ``commit``.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pyodbc

# Make the repo importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.build_env import guard_data_writable  # noqa: E402

BENCOI_TABLE = "RATE_BENCOI"
BENCOI_COLUMNS = ("Index(BENCOI)", "Scale", "IssueAge", "Duration", "Rate")
POINTER_TABLE = "POINT_BENEFIT"


def _quote(identifier: str) -> str:
    return "[" + identifier.replace("]", "]]") + "]"


def _load_config(arg: str) -> dict:
    path = Path(arg)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return json.loads(arg)


def _fetch_pointer_rows(cursor, plancodes: list[str]) -> list[tuple]:
    placeholders = ", ".join("?" for _ in plancodes)
    cursor.execute(
        f"SELECT {_quote('Plancode')}, {_quote('BenefitType')}, "
        f"{_quote('Benefit')}, {_quote('Index(BENCOI)')} "
        f"FROM {_quote(POINTER_TABLE)} "
        f"WHERE {_quote('Plancode')} IN ({placeholders})",
        plancodes,
    )
    return [tuple(r) for r in cursor.fetchall()]


def _attained_expr() -> str:
    return f"({_quote('IssueAge')} + {_quote('Duration')} - 1)"


def _fetch_rows_in_range(cursor, indices, age_min, age_max) -> list[tuple]:
    placeholders = ", ".join("?" for _ in indices)
    cols = ", ".join(_quote(c) for c in BENCOI_COLUMNS)
    cursor.execute(
        f"SELECT {cols} FROM {_quote(BENCOI_TABLE)} "
        f"WHERE {_quote('Index(BENCOI)')} IN ({placeholders}) "
        f"AND {_attained_expr()} BETWEEN ? AND ? "
        f"ORDER BY {_quote('Index(BENCOI)')}, {_quote('Scale')}, "
        f"{_quote('IssueAge')}, {_quote('Duration')}",
        list(indices) + [age_min, age_max],
    )
    return [tuple(r) for r in cursor.fetchall()]


def _fetch_max_attained(cursor, indices) -> dict[int, int]:
    placeholders = ", ".join("?" for _ in indices)
    cursor.execute(
        f"SELECT {_quote('Index(BENCOI)')}, MAX({_attained_expr()}) "
        f"FROM {_quote(BENCOI_TABLE)} "
        f"WHERE {_quote('Index(BENCOI)')} IN ({placeholders}) "
        f"GROUP BY {_quote('Index(BENCOI)')}",
        list(indices),
    )
    return {int(r[0]): int(r[1]) for r in cursor.fetchall() if r[1] is not None}


def _fetch_index_references(cursor, indices: list[int]) -> list[tuple]:
    placeholders = ", ".join("?" for _ in indices)
    cursor.execute(
        f"SELECT {_quote('Index(BENCOI)')}, {_quote('Plancode')}, "
        f"{_quote('BenefitType')}, {_quote('Benefit')} "
        f"FROM {_quote(POINTER_TABLE)} "
        f"WHERE {_quote('Index(BENCOI)')} IN ({placeholders})",
        indices,
    )
    return [tuple(r) for r in cursor.fetchall()]


def _write_backup(rows: list[tuple]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    folder = (
        Path.home() / ".suiteview" / "rate_manager_backups"
        / f"{timestamp}_delete_benefit_rates"
    )
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / f"{BENCOI_TABLE}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(BENCOI_COLUMNS)
        writer.writerows(rows)
    return path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: delete_benefit_rates_over_age.py <config.json> [--commit]")
        sys.exit(2)

    config = _load_config(sys.argv[1])
    commit = ("--commit" in sys.argv[2:]) or bool(config.get("commit"))
    dsn = str(config.get("dsn", "UL_Rates")).strip() or "UL_Rates"
    plancodes = [str(p).strip() for p in config["plancodes"] if str(p).strip()]
    prefix = str(config.get("benefit_type_prefix", "")).strip()
    age_min = int(config["age_min"])
    age_max = int(config["age_max"])

    if commit:
        guard_data_writable("delete benefit COI rates")

    print(f"=== Delete benefit COI rates (attained age {age_min}-{age_max}) ===")
    print(f"DSN={dsn}  benefit_type_prefix={prefix!r}  "
          f"plancodes={len(plancodes)}  mode={'COMMIT' if commit else 'PREVIEW'}")

    conn = pyodbc.connect(f"DSN={dsn}", autocommit=False, timeout=15)
    try:
        cursor = conn.cursor()

        # 1. Pointer rows for the requested plancodes.
        pointer_rows = _fetch_pointer_rows(cursor, plancodes)
        matched_plancodes = {str(r[0]).strip() for r in pointer_rows}
        missing = sorted(set(plancodes) - matched_plancodes)
        if missing:
            print(f"\n[!] {len(missing)} plancode(s) not found in {POINTER_TABLE}: "
                  f"{', '.join(missing)}")

        # Candidate indices: BenefitType starting with the prefix (e.g. '4' -> '4M').
        candidate_indices: set[int] = set()
        for plancode, btype, benefit, index in pointer_rows:
            if prefix and not str(btype).strip().startswith(prefix):
                continue
            if index is not None:
                candidate_indices.add(int(index))
        candidate_indices = sorted(candidate_indices)

        if not candidate_indices:
            print("\nNo benefit COI indices match the benefit-type prefix. Nothing to do.")
            return
        print(f"\nCandidate Index(BENCOI) values matching prefix {prefix!r}: "
              f"{len(candidate_indices)}")

        # 2. Protection rule: only trim indices whose rates END at or below
        #    age_max. An index that extends BEYOND age_max is a genuinely longer
        #    benefit (not the load-to-65 mistake) and must be left untouched,
        #    otherwise deleting age_min-age_max would punch a hole in it.
        max_before = _fetch_max_attained(cursor, candidate_indices)
        target_indices = [
            idx for idx in candidate_indices
            if max_before.get(idx) is not None and max_before[idx] <= age_max
        ]
        protected = [
            idx for idx in candidate_indices
            if max_before.get(idx) is not None and max_before[idx] > age_max
        ]
        no_rows = [idx for idx in candidate_indices if max_before.get(idx) is None]
        if protected:
            print(f"\n[protected] {len(protected)} index(es) extend beyond age "
                  f"{age_max} (e.g. to {max(max_before[i] for i in protected)}) "
                  "— left UNTOUCHED:")
            print(f"    {', '.join(str(i) for i in protected)}")
        if no_rows:
            print(f"\n[skip] {len(no_rows)} candidate index(es) have no RATE_BENCOI "
                  f"rows — nothing to delete.")

        if not target_indices:
            print("\nNo indices to trim after protection rule. Nothing to do.")
            return
        print(f"\nTarget Index(BENCOI) values to trim ({len(target_indices)}): "
              f"{', '.join(str(i) for i in target_indices)}")

        # 3. Who else references the target indices?
        refs = _fetch_index_references(cursor, target_indices)
        by_index: dict[int, set[str]] = defaultdict(set)
        for index, plancode, btype, benefit in refs:
            by_index[int(index)].add(str(plancode).strip())
        extra = sorted(
            {pc for idx in target_indices for pc in by_index.get(idx, set())}
            - set(plancodes)
        )
        if extra:
            print(f"\n[!] Target indices are ALSO referenced by "
                  f"{len(extra)} plancode(s) NOT in your list:")
            print(f"    {', '.join(extra)}")
            print("    These will be affected too (fix extended, as requested).")
        else:
            print("\nNo other plancodes reference the target indices.")

        # 4. Rows in the delete range.
        rows = _fetch_rows_in_range(cursor, target_indices, age_min, age_max)
        print(f"\nRows in RATE_BENCOI with attained age {age_min}-{age_max}: "
              f"{len(rows):,}")
        if rows:
            scale_counts: dict = defaultdict(int)
            for _idx, scale, _ia, _dur, _rate in rows:
                scale_counts[int(scale)] += 1
            print("  by Scale: " + ", ".join(
                f"{s}={scale_counts[s]:,}" for s in sorted(scale_counts)))
            print("  sample (Index, Scale, IssueAge, Duration, AttAge, Rate):")
            for r in rows[:10]:
                idx, scale, ia, dur, rate = r
                print(f"    {idx}, {scale}, {ia}, {dur}, "
                      f"att={int(ia) + int(dur) - 1}, {rate}")

        if not rows:
            print("\nNothing to delete in the requested range.")
            return

        if not commit:
            print("\nPREVIEW only — no changes made. Re-run with --commit to delete.")
            return

        # 5. Backup, then delete inside a serializable transaction.
        backup_path = _write_backup(rows)
        print(f"\nBacked up {len(rows):,} rows to: {backup_path}")

        cursor.execute("SET XACT_ABORT ON")
        cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        placeholders = ", ".join("?" for _ in target_indices)
        cursor.execute(
            f"DELETE FROM {_quote(BENCOI_TABLE)} "
            f"WHERE {_quote('Index(BENCOI)')} IN ({placeholders}) "
            f"AND {_attained_expr()} BETWEEN ? AND ?",
            list(target_indices) + [age_min, age_max],
        )
        deleted = max(cursor.rowcount, 0)
        print(f"DELETE affected {deleted:,} rows.")

        remaining = _fetch_rows_in_range(cursor, target_indices, age_min, age_max)
        if remaining:
            conn.rollback()
            print(f"[ABORT] {len(remaining):,} rows still in range after delete. "
                  "Rolled back — no changes committed.")
            sys.exit(1)

        max_after = _fetch_max_attained(cursor, target_indices)
        bad = sorted(i for i in target_indices if max_after.get(i, 0) > age_min - 1)
        if bad:
            conn.rollback()
            print(f"[ABORT] {len(bad)} index(es) still exceed attained age "
                  f"{age_min - 1} after delete. Rolled back.")
            sys.exit(1)
        conn.commit()
        print(f"Verification passed (0 rows remain in range; all target indices "
              f"now end at attained age {age_min - 1} or below). COMMITTED.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
