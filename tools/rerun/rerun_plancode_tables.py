"""Create, load and refresh RERUN's plancode tables in UL_Rates (schema ``dbo``).

* ``dbo.SV_RERUN_Adv_Plancodes`` - product rules per advanced plancode (``load_plancode``).
* ``dbo.SV_RERUN_Plancode_Control`` - every in-force base plancode, its product type and
  ``CanIllustrate`` (``core.plancode_control``).

Usage::

    venv\\Scripts\\python.exe tools\\rerun\\rerun_plancode_tables.py status
    venv\\Scripts\\python.exe tools\\rerun\\rerun_plancode_tables.py create [--apply]
    venv\\Scripts\\python.exe tools\\rerun\\rerun_plancode_tables.py load-adv --json rows.json [--apply]
    venv\\Scripts\\python.exe tools\\rerun\\rerun_plancode_tables.py upsert-adv --json rows.json [--apply]
    venv\\Scripts\\python.exe tools\\rerun\\rerun_plancode_tables.py export-adv --out rows.json
    venv\\Scripts\\python.exe tools\\rerun\\rerun_plancode_tables.py refresh-control [--apply] [--update-types]
    venv\\Scripts\\python.exe tools\\rerun\\rerun_plancode_tables.py loan-type-check

Nothing is written without ``--apply`` (the change is only reported). Writes need the
CanUpdateDatabase permission, run in one transaction and are read back before commit.

``load-adv`` loads an empty table from ``{"Plancodes": [...]}`` rows (the engine's keys);
``upsert-adv`` replaces just the given plancodes' rows.

``refresh-control`` reads every in-force base plancode (CyberLife ``CK_SYS_CD`` I,
premium-pay status 21-54, coverage phase 1) and classifies it from
``rates.PlancodeRegistry``: UL / IUL / ISWL / DI by registry type; whole life to
``ParWL`` when the registry's Participation is "Participating", else ``WL``; term,
child, family and ETI plans to ``Term``; anything else ``Other``. New plancodes are
inserted with ``CanIllustrate`` on for UL only. Existing rows keep their
``CanIllustrate`` (an administrator's decision); a changed product type is reported and
updated only with ``--update-types``; plancodes no longer in force are reported, never
deleted.

``loan-type-check`` compares each Adv row's ``LoanType`` with the in-force policies'
``LH_BAS_POL.LN_TYP_CD`` (0/6 Advance, 1/7 Arrears).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from suiteview.core.build_env import guard_data_writable  # noqa: E402
from suiteview.illustration.models.rerun_plancode_tables import (  # noqa: E402
    ADV_COLUMNS,
    ADV_CREATE_SQL,
    ADV_TABLE,
    CONTROL_COLUMNS,
    CONTROL_CREATE_SQL,
    CONTROL_TABLE,
    PRODUCT_TYPES,
    insert_sql,
    read_adv_plancode_rows,
    read_control_rows,
    row_to_db,
    table_exists,
)

IN_FORCE_SQL = """
SELECT TRIM(COV.PLN_DES_SER_CD), COUNT(*)
FROM {s}.LH_BAS_POL POL
JOIN {s}.LH_COV_PHA COV ON COV.CK_SYS_CD = POL.CK_SYS_CD AND COV.CK_CMP_CD = POL.CK_CMP_CD
 AND COV.TCH_POL_ID = POL.TCH_POL_ID AND COV.COV_PHA_NBR = 1
WHERE POL.CK_SYS_CD = 'I' AND POL.PRM_PAY_STA_REA_CD BETWEEN '21' AND '54'
GROUP BY TRIM(COV.PLN_DES_SER_CD)
"""
LOAN_TYPE_SQL = """
SELECT TRIM(COV.PLN_DES_SER_CD), POL.LN_TYP_CD, COUNT(*)
FROM {s}.LH_BAS_POL POL
JOIN {s}.LH_COV_PHA COV ON COV.CK_SYS_CD = POL.CK_SYS_CD AND COV.CK_CMP_CD = POL.CK_CMP_CD
 AND COV.TCH_POL_ID = POL.TCH_POL_ID AND COV.COV_PHA_NBR = 1
WHERE POL.CK_SYS_CD = 'I' AND POL.PRM_PAY_STA_REA_CD BETWEEN '21' AND '54'
GROUP BY TRIM(COV.PLN_DES_SER_CD), POL.LN_TYP_CD
"""
REGISTRY_SQL = ("SELECT Plancode, ProductType, ProductTypeCode, Participation "
                "FROM rates.PlancodeRegistry")
LOAN_TYPES = {"0": "Advance", "6": "Advance", "1": "Arrears", "7": "Arrears"}
_WHOLE_LIFE_CODES = {"WL", "WL_PAR", "WL_IND", "END", "END_PAR", "RPU_PLANS", "PUAR"}
_TERM_CODES = {"TERM", "TERM_IND", "TERM_DECR", "TERM_ROP", "TRAD_TERM", "ETI_PLANS", "CHILD"}


def classify(product_type: str, type_code: str, participation: str) -> str:
    """The control table's product type for a registry row."""
    code = (type_code or "").strip().upper()
    kind = (product_type or "").strip().lower()
    if code in ("UL", "IUL", "ISWL", "DI"):
        return code
    if code == "FAMILY":
        return "WL" if kind in ("whole life", "pure endowment") else "Term"
    if code in _WHOLE_LIFE_CODES:
        return "ParWL" if (participation or "").strip().lower() == "participating" else "WL"
    if code in _TERM_CODES or kind in ("term life", "transamerica term"):
        return "Term"
    return "Other"


def _connect():
    connection = pyodbc.connect("DSN=UL_Rates", autocommit=False, timeout=10)
    connection.timeout = 60
    with closing(connection.cursor()) as cursor:
        database = cursor.execute("SELECT DB_NAME()").fetchone()[0]
    if str(database).upper() != "UL_RATES":
        connection.close()
        raise RuntimeError(f"Expected UL_Rates, connected to {database!r}.")
    return connection


def _db2_rows(sql: str, region: str) -> list:
    from suiteview.core.db2_connection import DB2Connection
    from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_SCHEMA_MAP

    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This tool reads live DB2 policy data only.")
    db = DB2Connection(region)
    try:
        cursor = db.connect().cursor()
        cursor.execute(sql.format(s=REGION_SCHEMA_MAP.get(region, DEFAULT_SCHEMA)))
        rows = cursor.fetchall()
        cursor.close()
        return rows
    finally:
        db.close()


def _read_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["Plancodes"] if isinstance(data, dict) else data
    return [{k: v for k, v in row.items() if v is not None} for row in rows]


def _same(expected: list[dict], actual: list[dict]) -> list[str]:
    by_code = {row["Plancode"]: row for row in actual}
    problems = []
    for row in expected:
        stored = by_code.get(row["Plancode"])
        if stored != row:
            problems.append(f"{row['Plancode']}: stored {stored} != {row}")
    return problems


def cmd_status(_args) -> dict:
    with closing(_connect()) as connection, closing(connection.cursor()) as cursor:
        report = {}
        for table in (ADV_TABLE, CONTROL_TABLE):
            exists = table_exists(cursor, table)
            count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] if exists else None
            report[table] = {"exists": exists, "rows": count}
        connection.rollback()
    return report


def cmd_create(args) -> dict:
    if args.apply:
        guard_data_writable("create RERUN's plancode tables")
    with closing(_connect()) as connection:
        try:
            with closing(connection.cursor()) as cursor:
                missing = [(table, sql) for table, sql in
                           ((ADV_TABLE, ADV_CREATE_SQL), (CONTROL_TABLE, CONTROL_CREATE_SQL))
                           if not table_exists(cursor, table)]
                if args.apply:
                    for _table, sql in missing:
                        cursor.execute(sql)
                    connection.commit()
            return {"missing": [t for t, _ in missing], "created": bool(args.apply and missing),
                    "ddl": [sql for _, sql in missing] if not args.apply else None}
        finally:
            connection.rollback()


def _write_adv(rows: list[dict], *, replace: bool, apply: bool) -> dict:
    params = [row_to_db(ADV_COLUMNS, row) for row in rows]
    codes = [row["Plancode"] for row in rows]
    if len(codes) != len(set(codes)):
        raise ValueError("The input repeats a plancode.")
    if not apply:
        return {"rows": len(rows), "validated": True, "committed": False,
                "mode": "replace given rows" if replace else "load empty table"}
    guard_data_writable(f"write {ADV_TABLE}")
    with closing(_connect()) as connection:
        try:
            with closing(connection.cursor()) as cursor:
                cursor.execute("SET XACT_ABORT ON")
                existing = cursor.execute(f"SELECT COUNT(*) FROM {ADV_TABLE}").fetchone()[0]
                if not replace and existing:
                    raise RuntimeError(f"{ADV_TABLE} already has {existing} rows; use upsert-adv.")
                if replace:
                    for code in codes:
                        cursor.execute(f"DELETE FROM {ADV_TABLE} WHERE [Plancode] = ?", code)
                cursor.executemany(insert_sql(ADV_TABLE, ADV_COLUMNS), params)
            stored = read_adv_plancode_rows(connection)
            problems = _same(rows, stored)
            if problems:
                raise RuntimeError("Read-back differs; nothing committed: " + "; ".join(problems[:5]))
            connection.commit()
            return {"rows": len(rows), "table_rows_after": len(stored), "committed": True}
        finally:
            connection.rollback()


def cmd_load_adv(args) -> dict:
    return _write_adv(_read_rows(Path(args.json)), replace=False, apply=args.apply)


def cmd_upsert_adv(args) -> dict:
    return _write_adv(_read_rows(Path(args.json)), replace=True, apply=args.apply)


def cmd_export_adv(args) -> dict:
    rows = read_adv_plancode_rows()
    Path(args.out).write_text(json.dumps({"Plancodes": rows}, indent=2) + "\n", encoding="utf-8")
    return {"rows": len(rows), "out": args.out}


def control_plan(region: str) -> tuple[dict[str, str], dict[str, int], list[str]]:
    """``({plancode: product type}, {plancode: in-force count}, notes)`` from DB2 + registry."""
    from suiteview.core.rates_schema import RatesSchemaRepository

    counts = {str(p).strip(): int(n) for p, n in _db2_rows(IN_FORCE_SQL, region) if str(p).strip()}
    with RatesSchemaRepository() as repo:
        registry = {str(p).strip().upper(): (t, c, part)
                    for p, t, c, part in repo._query(REGISTRY_SQL)}
    types, notes = {}, []
    for plancode in sorted(counts):
        found = registry.get(plancode.upper())
        if found is None:
            types[plancode] = "Other"
            notes.append(f"{plancode}: not in rates.PlancodeRegistry -> Other")
        else:
            types[plancode] = classify(*found)
    return types, counts, notes


def cmd_refresh_control(args) -> dict:
    types, counts, notes = control_plan(args.region)
    current = read_control_rows()
    new = {p: t for p, t in types.items() if p.upper() not in current}
    changed = {p: (current[p.upper()].product_type, t) for p, t in types.items()
               if p.upper() in current and current[p.upper()].product_type != t}
    gone = sorted(p for p in current if p not in {code.upper() for code in types})
    report = {
        "in_force_plancodes": len(types),
        "by_type": dict(collections.Counter(types.values())),
        "new": len(new), "new_can_illustrate": sum(1 for t in new.values() if t == "UL"),
        "type_changes": {p: f"{a} -> {b}" for p, (a, b) in changed.items()},
        "no_longer_in_force": gone, "notes": notes,
        "updated_types": bool(args.update_types and changed), "committed": False,
    }
    bad = sorted(set(types.values()) - set(PRODUCT_TYPES))
    if bad:
        raise RuntimeError(f"Unknown product types {bad}.")
    if not args.apply or not (new or (args.update_types and changed)):
        return report
    guard_data_writable(f"write {CONTROL_TABLE}")
    with closing(_connect()) as connection:
        try:
            with closing(connection.cursor()) as cursor:
                cursor.execute("SET XACT_ABORT ON")
                if new:
                    cursor.executemany(insert_sql(CONTROL_TABLE, CONTROL_COLUMNS), [
                        row_to_db(CONTROL_COLUMNS, {"Plancode": p, "ProductType": t,
                                                    "CanIllustrate": t == "UL"})
                        for p, t in sorted(new.items())])
                if args.update_types:
                    for plancode, (_old, product_type) in changed.items():
                        cursor.execute(
                            f"UPDATE {CONTROL_TABLE} SET [ProductType] = ?, "
                            "[UpdatedAt] = SYSDATETIME(), [UpdatedBy] = SUSER_SNAME() "
                            "WHERE [Plancode] = ?", product_type, plancode)
            stored = read_control_rows(connection)
            missing = [p for p in new if p.upper() not in stored]
            if missing:
                raise RuntimeError(f"Read-back is missing {missing[:5]}; nothing committed.")
            connection.commit()
            report["committed"] = True
            report["table_rows_after"] = len(stored)
            return report
        finally:
            connection.rollback()


def cmd_loan_type_check(args) -> dict:
    adv = {row["Plancode"].upper(): row["LoanType"] for row in read_adv_plancode_rows()}
    coded: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for plancode, code, count in _db2_rows(LOAN_TYPE_SQL, args.region):
        plancode = str(plancode).strip().upper()
        if plancode in adv:
            coded[plancode][LOAN_TYPES.get(str(code).strip(), f"code {code}")] += int(count)
    mismatches, mixed = {}, {}
    for plancode, kinds in sorted(coded.items()):
        real = {k for k in kinds if k in ("Advance", "Arrears")}
        if len(real) > 1:
            mixed[plancode] = dict(kinds)
        elif real and adv[plancode] not in real:
            mismatches[plancode] = {"table": adv[plancode], "in_force": dict(kinds)}
    return {"plancodes_in_force": len(coded), "mismatches": mismatches, "mixed": mixed,
            "agree": len(coded) - len(mismatches) - len(mixed)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    create = sub.add_parser("create")
    create.add_argument("--apply", action="store_true")
    for name in ("load-adv", "upsert-adv"):
        load = sub.add_parser(name)
        load.add_argument("--json", required=True)
        load.add_argument("--apply", action="store_true")
    export = sub.add_parser("export-adv")
    export.add_argument("--out", required=True)
    refresh = sub.add_parser("refresh-control")
    refresh.add_argument("--region", default="CKPR")
    refresh.add_argument("--apply", action="store_true")
    refresh.add_argument("--update-types", action="store_true")
    loans = sub.add_parser("loan-type-check")
    loans.add_argument("--region", default="CKPR")
    args = parser.parse_args()
    handler = {
        "status": cmd_status, "create": cmd_create, "load-adv": cmd_load_adv,
        "upsert-adv": cmd_upsert_adv, "export-adv": cmd_export_adv,
        "refresh-control": cmd_refresh_control, "loan-type-check": cmd_loan_type_check,
    }[args.command]
    print(json.dumps(handler(args), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
