"""Backfill synthetic (non-PII) birthdates into the local dev policy DB.

The offline export (tools/export_local_policy_data.py) historically nulled
LH_CTT_CLIENT.BIR_DT. This tool writes a synthetic DOB for every row that
represents a meaningful person (INS_AGE > 0 or non-blank GENDER_CD):

    DOB = base-coverage issue date (LH_COV_PHA.ISSUE_DT, COV_PHA_NBR=1)
          minus that row's INS_AGE years, keeping the issue month/day.

An issue-anniversary DOB makes age-last-birthday and age-nearest-birthday
both reproduce INS_AGE on the issue date. Placeholder rows (INS_AGE=0 and
blank GENDER_CD) stay NULL. Dates are written in ISO YYYY-MM-DD, matching
every other *_DT column in the DB.

Note: LH_BAS_POL has no issue-date column — the app's PolicyInformation
.issue_date reads LH_COV_PHA.ISSUE_DT, so that is the join used here
(TCH_POL_ID + CK_CMP_CD, COV_PHA_NBR=1).

Usage:
    backfill_synthetic_dob.py ['<json>']

    {"db": "<path>", "dry_run": true}   # both keys optional

Prints a JSON report per policy: each person row (PRS_CD/PRS_SEQ_NBR,
INS_AGE, GENDER_CD) and the synthetic BIR_DT written (or null if skipped).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from export_local_policy_data import is_meaningful_person, synthetic_birth_date

DEFAULT_DB = TOOLS_DIR.parent / "bundled_data" / "dev" / "policy_records.sqlite"

PERSON_CODES = {
    "00": "Primary Insured",
    "01": "Joint Insured",
    "10": "Owner",
    "20": "Payor",
    "30": "Beneficiary",
    "40": "Spouse",
    "50": "Dependent",
    "60": "Other",
    "70": "Assignee",
    "A0": "Power of Attorney",
}


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    db_path = Path(cmd.get("db", DEFAULT_DB))
    dry_run = bool(cmd.get("dry_run", False))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    policies: dict[str, list[dict]] = {}
    updated = 0
    skipped = 0
    missing_issue_date = 0
    try:
        rows = conn.execute(
            """
            SELECT c.rowid AS ROWID_, c.TCH_POL_ID, c.CK_CMP_CD,
                   c.PRS_CD, c.PRS_SEQ_NBR, c.INS_AGE, c.GENDER_CD, c.BIR_DT,
                   b.CK_POLICY_NBR, p.ISSUE_DT
            FROM LH_CTT_CLIENT c
            LEFT JOIN LH_BAS_POL b
                   ON b.TCH_POL_ID = c.TCH_POL_ID AND b.CK_CMP_CD = c.CK_CMP_CD
            LEFT JOIN LH_COV_PHA p
                   ON p.TCH_POL_ID = c.TCH_POL_ID AND p.CK_CMP_CD = c.CK_CMP_CD
                  AND p.COV_PHA_NBR = 1
            ORDER BY b.CK_POLICY_NBR, c.PRS_CD, c.PRS_SEQ_NBR
            """
        ).fetchall()

        for row in rows:
            policy_number = str(row["CK_POLICY_NBR"] or row["TCH_POL_ID"]).strip()
            prs_cd = str(row["PRS_CD"] or "").strip()
            ins_age = int(row["INS_AGE"] or 0)
            gender = str(row["GENDER_CD"] or "").strip()
            issue_dt_raw = row["ISSUE_DT"]

            entry = {
                "prs_cd": prs_cd,
                "person": PERSON_CODES.get(prs_cd, prs_cd),
                "prs_seq_nbr": row["PRS_SEQ_NBR"],
                "ins_age": ins_age,
                "gender_cd": gender,
                "issue_date": issue_dt_raw,
                "bir_dt": None,
            }

            if not is_meaningful_person(row["INS_AGE"], row["GENDER_CD"]):
                entry["status"] = "skipped (no meaningful person)"
                skipped += 1
            elif not issue_dt_raw:
                entry["status"] = "skipped (no base-coverage issue date)"
                missing_issue_date += 1
            else:
                issue_date = date.fromisoformat(str(issue_dt_raw)[:10])
                dob = synthetic_birth_date(issue_date, ins_age)
                entry["bir_dt"] = dob.isoformat()
                entry["status"] = "updated"
                if not dry_run:
                    conn.execute(
                        "UPDATE LH_CTT_CLIENT SET BIR_DT = ? WHERE rowid = ?",
                        (dob.isoformat(), row["ROWID_"]),
                    )
                updated += 1

            policies.setdefault(policy_number, []).append(entry)

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    print(json.dumps({
        "db": str(db_path),
        "dry_run": dry_run,
        "rows_updated": updated,
        "rows_skipped_placeholder": skipped,
        "rows_skipped_no_issue_date": missing_issue_date,
        "policies": policies,
    }, indent=2))


if __name__ == "__main__":
    main()
