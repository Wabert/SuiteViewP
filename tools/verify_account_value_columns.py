r"""Verify the appended Account Value / Monthliversary Date columns.

Reads the batch workbook back (data_only) and compares the Account Value (AG)
and Monthliversary Date (AH) cells against the JSON produced by
``fetch_last_mvry_av.py``, matching by (Company col A, Policy col B). Confirms
every fetched record landed in the right row with the right value/date and
reports any mismatches.

Usage:
    venv\Scripts\python.exe tools/verify_account_value_columns.py "<workbook>" "<json>"
        [--sheet Batch]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

try:
    import openpyxl
except ImportError:
    print(json.dumps({"error": "openpyxl not installed"}))
    sys.exit(1)


def _key(company, policy):
    comp = str(company).strip() if company is not None else None
    pol = str(policy).strip() if policy is not None else None
    return (comp, pol)


def _norm_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    try:
        return value.isoformat()
    except AttributeError:
        return str(value).strip()[:10] or None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("workbook")
    ap.add_argument("json_path")
    ap.add_argument("--sheet", default=None)
    args = ap.parse_args()

    with open(args.json_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    expected = {}
    for rec in payload["records"]:
        expected[_key(rec.get("company"), rec.get("policy"))] = (
            float(rec["account_value"]) if rec.get("account_value") is not None else None,
            rec.get("monthliversary_date"),
        )

    wb = openpyxl.load_workbook(args.workbook, data_only=True, read_only=True)
    ws = wb[args.sheet] if args.sheet else wb[wb.sheetnames[0]]

    headers = {str(c.value).strip(): c.column for c in ws[1] if c.value is not None}
    av_col = headers.get("Account Value")
    date_col = headers.get("Monthliversary Date")

    checked = 0
    av_ok = 0
    date_ok = 0
    mismatches = []
    for row in ws.iter_rows(min_row=2):
        policy = row[1].value if len(row) > 1 else None
        if policy is None or not str(policy).strip():
            continue
        company = row[0].value if len(row) > 0 else None
        k = _key(company, policy)
        exp = expected.get(k)
        if exp is None:
            continue
        checked += 1
        exp_av, exp_dt = exp
        got_av = row[av_col - 1].value if av_col else None
        got_dt = _norm_date(row[date_col - 1].value) if date_col else None

        av_match = (exp_av is None and got_av is None) or (
            exp_av is not None and got_av is not None and abs(float(got_av) - exp_av) < 0.005
        )
        dt_match = (exp_dt or None) == (got_dt or None)
        if av_match:
            av_ok += 1
        if dt_match:
            date_ok += 1
        if not (av_match and dt_match) and len(mismatches) < 20:
            mismatches.append({
                "company": k[0], "policy": k[1],
                "exp_av": exp_av, "got_av": got_av,
                "exp_date": exp_dt, "got_date": got_dt,
            })

    wb.close()
    print(json.dumps({
        "workbook": args.workbook,
        "av_column": openpyxl.utils.get_column_letter(av_col) if av_col else None,
        "date_column": openpyxl.utils.get_column_letter(date_col) if date_col else None,
        "records_expected": len(expected),
        "rows_checked": checked,
        "av_matches": av_ok,
        "date_matches": date_ok,
        "mismatch_count": checked - min(av_ok, date_ok),
        "mismatch_samples": mismatches,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
