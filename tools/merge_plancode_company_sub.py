"""Merge the CompanySub column from RERUN's plancode table into plancode_table.json.

RERUN keeps CompanySub in Rates_Control!C12:BE206 (Plancode in col C,
CompanySub in col BC). sblnFFL = (sCompanySub = "FFL") drives the FFL premium
waiver target basis in the CalcEngine.

Usage:
    venv\\Scripts\\python.exe tools/merge_plancode_company_sub.py '<json>'

JSON arg:
    {"workbook": "docs/Illustration_UL/RERUN (v20.0).xlsm",
     "table": "suiteview/illustration/plancodes/plancode_table.json",
     "write": true}

With "write": false (default) it only reports what would change.
"""
import json
import sys

import openpyxl


def main():
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    workbook = cmd.get("workbook", "docs/Illustration_UL/RERUN (v20.0).xlsm")
    table_path = cmd.get(
        "table", "suiteview/illustration/plancodes/plancode_table.json"
    )
    write = bool(cmd.get("write", False))

    wb = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    ws = wb["Rates_Control"]
    # Plancode table range C12:BE206 — col C = Plancode, col BC = CompanySub.
    company_sub = {}
    for row in ws.iter_rows(min_row=12, max_row=206, min_col=3, max_col=55):
        plancode = str(row[0].value or "").strip()
        if not plancode:
            continue
        sub = str(row[52].value or "").strip()  # BC = col 55 -> offset 52 from C
        company_sub[plancode] = sub
    wb.close()

    with open(table_path, "r") as f:
        data = json.load(f)

    updated, missing_in_rerun = [], []
    for entry in data.get("Plancodes", []):
        plancode = str(entry.get("Plancode", "")).strip()
        sub = company_sub.get(plancode)
        if sub is None:
            missing_in_rerun.append(plancode)
            continue
        if entry.get("CompanySub") != sub:
            entry["CompanySub"] = sub
            updated.append(f"{plancode}={sub}")

    json_plancodes = {
        str(e.get("Plancode", "")).strip() for e in data.get("Plancodes", [])
    }
    missing_in_json = sorted(set(company_sub) - json_plancodes)

    if write:
        with open(table_path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    print(json.dumps({
        "rerun_rows": len(company_sub),
        "json_rows": len(data.get("Plancodes", [])),
        "updated": len(updated),
        "updated_detail": updated,
        "ffl_count": sum(1 for s in company_sub.values() if s == "FFL"),
        "missing_in_rerun": missing_in_rerun,
        "missing_in_json": missing_in_json,
        "written": write,
    }, indent=2))


if __name__ == "__main__":
    main()
