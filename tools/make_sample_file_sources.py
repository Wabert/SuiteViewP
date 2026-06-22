"""Generate sample flat files for testing the Audit File Sources feature.

Creates an internally-consistent insurance dataset under
``sample_data/file_sources/`` so you can exercise every path:

- Same-type-across-folders: ``direct/CLAIMS.csv`` + ``reinsurance/RGACLAIMS.csv``
  (identical layout — add both to one File Source as separate tables, UNION them).
- Cross-file joins: ``POLICIES.csv`` shares PolicyNumber with the claims files.
- Parsing variants under ``variants/``: a header-less CSV (test "Name Columns"),
  a pipe-delimited ``.txt``, and a fixed-width ``.txt`` (spec in the README).

Stdlib only. Run:
    venv\\Scripts\\python.exe tools/make_sample_file_sources.py
"""
import csv
import os
import sys
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = ROOT / "sample_data" / "file_sources"

POLICY_COLUMNS = ["PolicyNumber", "InsuredName", "State", "PlanCode",
                  "FaceAmount", "IssueDate", "AnnualPremium", "Status"]
POLICIES = [
    ["P0001001", "John Carter",     "TX", "WL100", "250000", "2015-03-12", "1820.50", "Active"],
    ["P0001002", "Maria Lopez",     "CA", "UL250", "500000", "2018-07-01", "3120.00", "Active"],
    ["P0001003", "David Kim",       "NY", "TERM20", "100000", "2012-11-23", "640.75", "Lapsed"],
    ["P0001004", "Susan Patel",     "FL", "WL100", "175000", "2010-01-15", "1490.20", "Active"],
    ["P0001005", "Robert Haessly",  "TX", "IUL500", "750000", "2020-05-30", "5400.00", "Active"],
    ["P0001006", "Linda Nguyen",    "CA", "UL250", "300000", "2016-09-09", "2210.40", "Death Claim"],
    ["P0001007", "James Wright",    "GA", "TERM10", "50000", "2019-02-28", "310.00", "Active"],
    ["P0001008", "Patricia Gomez",  "NY", "WL100", "200000", "2013-06-17", "1675.85", "Active"],
    ["P0001009", "Michael Brown",   "FL", "IUL500", "1000000", "2021-08-02", "7250.00", "Active"],
    ["P0001010", "Karen Davis",     "TX", "UL250", "425000", "2017-04-19", "2890.10", "Surrendered"],
    ["P0001011", "Thomas Wilson",   "GA", "TERM20", "150000", "2014-12-05", "905.60", "Active"],
    ["P0001012", "Nancy Martins",   "CA", "WL100", "225000", "2011-10-21", "1730.45", "Death Claim"],
]

CLAIM_COLUMNS = ["PolicyNumber", "ClaimNumber", "InsuredName", "State",
                 "ClaimType", "ClaimAmount", "Status", "DateReported", "DateClosed"]
# Direct business claims.
DIRECT_CLAIMS = [
    ["P0001006", "CLM-00001", "Linda Nguyen",   "CA", "Death",      "300000.00", "Closed",  "2023-02-10", "2023-04-01"],
    ["P0001012", "CLM-00002", "Nancy Martins",  "CA", "Death",      "225000.00", "Open",    "2024-11-03", ""],
    ["P0001003", "CLM-00003", "David Kim",      "NY", "Surrender",  "8450.25",   "Closed",  "2022-06-15", "2022-07-02"],
    ["P0001010", "CLM-00004", "Karen Davis",    "TX", "Surrender",  "61200.00",  "Closed",  "2023-09-20", "2023-10-11"],
    ["P0001001", "CLM-00005", "John Carter",    "TX", "ABR",        "62500.00",  "Pending", "2025-01-12", ""],
    ["P0001005", "CLM-00006", "Robert Haessly", "TX", "Disability", "1500.00",   "Open",    "2025-03-04", ""],
    ["P0001004", "CLM-00007", "Susan Patel",    "FL", "Waiver",     "1490.20",   "Closed",  "2024-01-30", "2024-02-15"],
    ["P0001009", "CLM-00008", "Michael Brown",  "FL", "ABR",        "250000.00", "Denied",  "2024-08-22", "2024-09-09"],
    ["P0001002", "CLM-00009", "Maria Lopez",    "CA", "Disability", "3120.00",   "Open",    "2025-02-18", ""],
    ["P0001008", "CLM-00010", "Patricia Gomez", "NY", "Waiver",     "1675.85",   "Closed",  "2023-12-01", "2023-12-20"],
]
# Reinsurance (RGA) claims — same layout, different folder, some shared policies.
RGA_CLAIMS = [
    ["P0001006", "RGA-10001", "Linda Nguyen",   "CA", "Death",  "150000.00", "Closed",  "2023-02-12", "2023-04-05"],
    ["P0001009", "RGA-10002", "Michael Brown",  "FL", "Death",  "500000.00", "Open",    "2025-04-01", ""],
    ["P0001005", "RGA-10003", "Robert Haessly", "TX", "Death",  "375000.00", "Pending", "2025-03-15", ""],
    ["P0001012", "RGA-10004", "Nancy Martins",  "CA", "Death",  "112500.00", "Open",    "2024-11-05", ""],
    ["P0001002", "RGA-10005", "Maria Lopez",    "CA", "Death",  "250000.00", "Closed",  "2024-05-09", "2024-06-30"],
    ["P0001011", "RGA-10006", "Thomas Wilson",  "GA", "Death",  "75000.00",  "Denied",  "2024-07-14", "2024-08-01"],
]

# Fixed-width layout: (name, width). 1-based start positions are cumulative.
FW_SPEC = [
    ("PolicyNumber", 8),
    ("State", 2),
    ("ClaimType", 10),
    ("ClaimAmount", 12),
    ("Status", 8),
    ("DateReported", 10),
]


def _write_csv(path: Path, header, rows, *, delimiter=","):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=delimiter)
        if header is not None:
            w.writerow(header)
        w.writerows(rows)


def _fixed_width_spec_lines():
    lines, start = [], 1
    for name, width in FW_SPEC:
        lines.append(f"{name},{start},{width}")
        start += width
    return lines


def _write_fixed_width(path: Path, rows):
    # Source the fixed-width columns from the full claim rows by name.
    idx = {c: i for i, c in enumerate(CLAIM_COLUMNS)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        for row in rows:
            line = "".join(
                str(row[idx[name]])[:width].ljust(width) for name, width in FW_SPEC)
            fh.write(line + "\n")


def _write_readme(path: Path):
    spec = "\n".join(_fixed_width_spec_lines())
    path.write_text(
        "# Sample File Sources — Audit testing\n\n"
        "Generated by `tools/make_sample_file_sources.py`. An internally-consistent\n"
        "insurance dataset: every claim's `PolicyNumber` exists in `POLICIES.csv`.\n\n"
        "## Files\n\n"
        "| File | Format | Use it to test |\n"
        "|---|---|---|\n"
        "| `POLICIES.csv` | CSV, header | A second File Source to JOIN against claims |\n"
        "| `direct/CLAIMS.csv` | CSV, header | The base claims file |\n"
        "| `reinsurance/RGACLAIMS.csv` | CSV, header | **Same layout, different folder** — add it to the CLAIMS source as a 2nd member (each is its own table); UNION them in SQL |\n"
        "| `variants/CLAIMS_no_header.txt` | comma, **no header** | Choose Delimited → no header, then **Name Columns** |\n"
        "| `variants/CLAIMS_pipe.txt` | `|`-delimited | Pick a non-comma delimiter |\n"
        "| `variants/CLAIMS_fixed_width.txt` | Fixed width | The fixed-width layout (spec below) |\n\n"
        "Claim columns: " + ", ".join(CLAIM_COLUMNS) + "\n\n"
        "(`DateClosed` is blank for Open/Pending claims — handy for null tests.)\n\n"
        "## Suggested walkthrough\n\n"
        "1. New Query → **File Source**. Drag `direct/CLAIMS.csv` on → it sets the\n"
        "   format + columns. Drag `reinsurance/RGACLAIMS.csv` on → added as a 2nd\n"
        "   table (validated against the schema). Save.\n"
        "2. **SQL Query →** and try a cross-file roll-up:\n\n"
        "   ```sql\n"
        "   SELECT State, ClaimType, COUNT(*) AS claims, SUM(CAST(ClaimAmount AS DOUBLE)) AS total\n"
        "   FROM (SELECT * FROM \"CLAIMS\" UNION ALL SELECT * FROM \"RGACLAIMS\")\n"
        "   GROUP BY State, ClaimType\n"
        "   ORDER BY total DESC\n"
        "   ```\n\n"
        "3. Make a second File Source from `POLICIES.csv`, then join claims to\n"
        "   policies on `PolicyNumber` (Manual SQL, or in DataForge).\n\n"
        "## Fixed-width column spec\n\n"
        "In the File Source editor, choose **Fixed width** and paste these\n"
        "`name,start,width` lines (1-based start):\n\n"
        "```\n" + spec + "\n```\n",
        encoding="utf-8",
    )


def main():
    _write_csv(OUT / "POLICIES.csv", POLICY_COLUMNS, POLICIES)
    _write_csv(OUT / "direct" / "CLAIMS.csv", CLAIM_COLUMNS, DIRECT_CLAIMS)
    _write_csv(OUT / "reinsurance" / "RGACLAIMS.csv", CLAIM_COLUMNS, RGA_CLAIMS)
    # Header-less is a .txt so the editor's parse dialog lets you pick "no header"
    # (a .csv is auto-treated as comma + header, with no dialog).
    _write_csv(OUT / "variants" / "CLAIMS_no_header.txt", None, DIRECT_CLAIMS)
    _write_csv(OUT / "variants" / "CLAIMS_pipe.txt", CLAIM_COLUMNS, DIRECT_CLAIMS, delimiter="|")
    _write_fixed_width(OUT / "variants" / "CLAIMS_fixed_width.txt", DIRECT_CLAIMS)
    _write_readme(OUT / "README.md")

    created = sorted(p.relative_to(ROOT).as_posix()
                     for p in OUT.rglob("*") if p.is_file())
    print("Created under sample_data/file_sources/:")
    for rel in created:
        print(f"  {rel}")


if __name__ == "__main__":
    main()
