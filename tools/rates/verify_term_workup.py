r"""Build a Term rate workup from an IAF and compare it to the live database.

The retired Term_Rates scripts already loaded ~47 plancodes into UL_Rates, so
those rows are the reference: a correct port must reproduce them exactly.
This runs the new builder for one plancode and diffs every table against what
is currently in the database.

Usage:
    venv\Scripts\python.exe tools\rates\verify_term_workup.py "<json>"
    venv\Scripts\python.exe tools\rates\verify_term_workup.py @args.json

    {"iaf": "<IAF file>", "base_index": 1000, "first_level": 10,
     "ren_level": 1, "out": "<scratch folder>", "dsn": "UL_Rates",
     "fee": 60, "modefact": "1", "bandspec": "1", "sample": 5}

Pass a "cases" array to verify several plancodes in one connection; keys
outside "cases" act as defaults for every case.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import pyodbc

from suiteview.ratemanager.workup import term_builder
from suiteview.ratemanager.workup.term_spec import (
    BandStructureSelection, ModeFactorSelection, TermBenefitSelection,
    TermWorkupSpec,
)


# Rate tables keyed by index, and the pointer tables keyed by their own
# natural keys. Each entry is (index/scope column, comparison columns).
RATE_TABLES = {
    "TERM_RATE_PREM": ("Index(PREM)", ["Scale", "IssueAge", "Duration", "Rate"]),
    "TERM_RATE_BEN": ("Index(BEN)", ["Scale", "IssueAge", "Duration", "Rate"]),
}
POINTER_TABLES = {
    "TERM_POINT_PVSRB": ["Sex", "Rateclass", "Band", "Index(PREM)"],
    "TERM_POINT_BENEFIT": [
        "BenefitType", "Benefit", "Sex", "Rateclass", "Band", "Index(BEN)",
    ],
}


def _norm(value) -> str:
    """Normalize a value for comparison across CSV text and SQL numerics.

    Index values such as '1001_30' are identifiers, not numbers — but
    ``float()`` happily parses them because Python allows underscores inside
    numeric literals ('1001_30' → 100130.0). Guard against that so indexes
    compare as text.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if "_" in text:
        return text
    try:
        number = float(text)
    except ValueError:
        return text
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    return f"{number:.6f}"


def _read_csv(path: str):
    import csv
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        headers = next(reader, [])
        return headers, [row for row in reader]


def _db_rows(cursor, table: str, columns, where: str, params):
    col_list = ", ".join(f"[{c}]" for c in columns)
    cursor.execute(f"SELECT {col_list} FROM [{table}] WHERE {where}", params)
    return [tuple(_norm(v) for v in row) for row in cursor.fetchall()]


def _compare(built, live, sample: int) -> dict:
    built_set, live_set = set(built), set(live)
    missing = sorted(live_set - built_set)      # in DB, not produced
    extra = sorted(built_set - live_set)        # produced, not in DB
    return {
        "built_rows": len(built),
        "live_rows": len(live),
        "built_unique": len(built_set),
        "live_unique": len(live_set),
        "match": not missing and not extra,
        "missing_from_build": len(missing),
        "extra_in_build": len(extra),
        "missing_sample": missing[:sample],
        "extra_sample": extra[:sample],
    }


def _run_case(cfg: dict, cursor, sample: int) -> dict:
    """Build one plancode's workup and diff it against the live tables."""
    out_dir = cfg.get("out") or os.path.dirname(cfg["iaf"])

    spec = TermWorkupSpec(
        output_dir=out_dir,
        iaf_path=cfg["iaf"],
        base_index=int(cfg["base_index"]),
        first_level=int(cfg.get("first_level", 1)),
        ren_level=int(cfg.get("ren_level", 1)),
        fee=float(cfg.get("fee", 0)),
        modefact=ModeFactorSelection(index=str(cfg.get("modefact", "0"))),
        bandspec=BandStructureSelection(index=str(cfg.get("bandspec", "0"))),
    )

    analysis = term_builder.analyze(spec)
    if analysis.error:
        return {"iaf": os.path.basename(cfg["iaf"]), "error": analysis.error}

    spec.plancode = analysis.plancode
    spec.issue_version = analysis.issue_version
    overrides = cfg.get("benefits", {})
    spec.benefits = [
        TermBenefitSelection(
            code=code,
            label=label,
            renewable=overrides.get(code, {}).get("renewable", True),
            cease_age=overrides.get(code, {}).get("cease_age"),
            max_duration=overrides.get(code, {}).get("max_duration"),
            first_level=overrides.get(code, {}).get("first_level"),
            ren_level=overrides.get(code, {}).get("ren_level"),
        )
        for (code, label, _combos, _durs, _count) in analysis.benefits
    ]

    result = term_builder.build(spec, analysis)
    if result.error:
        return {"plancode": analysis.plancode, "error": result.error}

    report = {
        "plancode": analysis.plancode,
        "maturity": analysis.maturity_label,
        "rate_space": analysis.rate_space_summary(),
        "output_path": result.output_path,
        "table_counts": dict(result.table_counts),
        "warnings": result.warnings,
        "comparison": {},
    }

    for table, columns in POINTER_TABLES.items():
        headers, rows = _read_csv(
            os.path.join(result.output_path, f"{table}.csv"))
        positions = [headers.index(c) for c in columns]
        built = [tuple(_norm(row[p]) for p in positions) for row in rows]
        live = _db_rows(cursor, table, columns,
                        "[Plancode] = ? AND [IssueVersion] = ?",
                        (analysis.plancode, analysis.issue_version))
        report["comparison"][table] = _compare(built, live, sample)

    for table, (index_col, columns) in RATE_TABLES.items():
        headers, rows = _read_csv(
            os.path.join(result.output_path, f"{table}.csv"))
        idx_pos = headers.index(index_col)
        positions = [headers.index(c) for c in columns]
        built = [
            tuple([_norm(row[idx_pos])] + [_norm(row[p]) for p in positions])
            for row in rows
        ]
        indexes = sorted({row[idx_pos] for row in rows})
        live = []
        if indexes:
            placeholders = ",".join("?" * len(indexes))
            live = _db_rows(cursor, table, [index_col] + columns,
                            f"[{index_col}] IN ({placeholders})", indexes)
        report["comparison"][table] = _compare(built, live, sample)

    report["all_match"] = all(
        entry["match"] for entry in report["comparison"].values())
    return report


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: verify_term_workup.py <json|@file>"}))
        sys.exit(1)
    arg = sys.argv[1]
    if arg.startswith("@"):
        with open(arg[1:], "r", encoding="utf-8-sig") as handle:
            cfg = json.load(handle)
    else:
        cfg = json.loads(arg)

    sample = int(cfg.get("sample", 5))
    cases = cfg.get("cases") or [cfg]
    defaults = {k: v for k, v in cfg.items() if k not in ("cases", "sample")}

    conn = pyodbc.connect(f"DSN={cfg.get('dsn', 'UL_Rates')}",
                          autocommit=True, timeout=30)
    try:
        cursor = conn.cursor()
        reports = [_run_case({**defaults, **case}, cursor, sample)
                   for case in cases]
        cursor.close()
    finally:
        conn.close()

    if len(reports) == 1:
        print(json.dumps(reports[0], indent=2, default=str))
        return
    print(json.dumps({
        "all_match": all(r.get("all_match") for r in reports),
        "cases": reports,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
