from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEV_DIR = ROOT / "bundled_data" / "dev"
POLICY_DB = DEV_DIR / "policy_records.sqlite"
RATES_DB = DEV_DIR / "rates.sqlite"
PLANCODE = "1U144600"

EMPTY_TABLE_COLUMNS = [
    "CK_SYS_CD",
    "TCH_POL_ID",
    "CK_CMP_CD",
    "CK_POLICY_NBR",
    "COV_PHA_NBR",
    "PRS_CD",
    "PRS_SEQ_NBR",
    "SEG_IDX_NBR",
    "PRM_RT_TYP_CD",
    "JT_INS_IND",
    "SPM_BNF_TYP_CD",
    "SPM_BNF_SBY_CD",
    "TAR_TYP_CD",
    "MVRY_DT",
    "FND_ID_CD",
    "FND_VAL_PHA_NBR",
    "ERN_DT_MO_YR_NBR",
    "AGT_COM_PHA_NBR",
    "AGT_ITS_EFF_DT",
    "ASOF_DT",
    "SEQ_NO",
]

EXTRA_EMPTY_POLICY_TABLES = {
    "LH_CSH_VAL_LOAN",
    "LH_FND_VAL_LOAN",
    "LH_CTT_CLIENT",
    "LH_LOC_CLT_ADR",
    "VH_POL_HAS_LOC_CLT",
}


def _create_table(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = sorted({key for row in rows for key in row})
    column_sql = ", ".join(f'"{column}"' for column in columns)
    conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    conn.execute(f'CREATE TABLE "{table}" ({column_sql})')
    placeholders = ", ".join("?" for _ in columns)
    insert_sql = f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})'
    conn.executemany(insert_sql, [[row.get(column) for column in columns] for row in rows])


def _create_empty_table(conn: sqlite3.Connection, table: str) -> None:
    column_sql = ", ".join(f'"{column}"' for column in EMPTY_TABLE_COLUMNS)
    conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    conn.execute(f'CREATE TABLE "{table}" ({column_sql})')


def _mapped_policy_tables() -> set[str]:
    mapping_path = ROOT / "suiteview" / "polview" / "data" / "policy_record_db2_tables.json"
    with open(mapping_path, "r") as handle:
        mapping = json.load(handle)
    tables = {table for table_list in mapping.values() for table in table_list}
    tables.update(EXTRA_EMPTY_POLICY_TABLES)
    return tables


def _policy_rows(policy_number: str, company: str, policy_id: str, *, issue_age: int, sex: str,
                 rate_class: str, face: float, account_value: float, modal: float,
                 regular_loan: float = 0.0, variable_loan: float = 0.0) -> dict[str, list[dict]]:
    units = face / 1000.0
    issue_date = "2016-06-15"
    mv_date = "2026-05-15"
    next_mv_date = "2026-06-15"
    monthly_deduction = round(account_value * 0.0012 + face / 100000.0, 2)
    coi_charge = round(monthly_deduction * 0.58, 2)
    expense_charge = round(monthly_deduction * 0.27, 2)
    other_charge = round(monthly_deduction - coi_charge - expense_charge, 2)
    premium_td = round(modal * 12 * 9.25, 2)
    premium_ytd = round(modal * 5, 2)
    glp = round(face * 0.021, 2)
    gsp = round(face * 0.39, 2)
    mtp = round(face * 0.0048, 2)
    ctp = round(face * 0.011, 2)

    key = {
        "CK_CMP_CD": company,
        "CK_POLICY_NBR": policy_number,
        "CK_SYS_CD": "I",
        "TCH_POL_ID": policy_id,
    }

    rows = {
        "LH_BAS_POL": [{
            **key,
            "STS_CD": "A",
            "NON_TRD_POL_IND": "1",
            "PMT_FQY_PER": 1,
            "NSD_MD_CD": "",
            "POL_PRM_AMT": modal,
            "BIL_DAY_NBR": 15,
            "POL_ISS_ST_CD": "44",
            "PRM_PAY_ST_CD": "44",
            "PRI_DIV_OPT_CD": "0",
            "NFO_OPT_TYP_CD": "0",
            "NXT_MVRY_PRC_DT": next_mv_date,
            "LST_FIN_DT": mv_date,
            "LST_ANV_DT": "2025-06-15",
            "NXT_BIL_DT": next_mv_date,
            "PRM_BILL_TO_DT": next_mv_date,
            "LN_TYP_CD": "6" if variable_loan else "1",
            "LN_PLN_ITS_RT": 0.06,
            "SVC_AGT_NBR": "DEV0001",
            "SVC_AGC_NBR": "ADEV1",
            "BIL_FRM_CD": "0",
        }],
        "LH_COV_PHA": [{
            **key,
            "COV_PHA_NBR": 1,
            "PLN_DES_SER_CD": PLANCODE,
            "POL_FRM_NBR": "DEV-IUL",
            "ISSUE_DT": issue_date,
            "COV_MT_EXP_DT": "2076-06-15",
            "INS_ISS_AGE": issue_age,
            "COV_UNT_QTY": units,
            "OGN_SPC_UNT_QTY": units,
            "COV_VPU_AMT": 1000,
            "PRS_CD": "00",
            "PRS_SEQ_NBR": 1,
            "LIVES_COV_CD": "1",
            "INS_SEX_CD": sex,
            "INS_CLS_CD": rate_class,
            "PRD_LIN_TYP_CD": "U",
            "ANN_PRM_UNT_AMT": round(modal * 12 / units, 6),
            "NXT_CHG_TYP_CD": "A",
            "NXT_CHG_DT": "9999-12-31",
            "PLN_TMN_DT": "9999-12-31",
        }],
        "LH_NON_TRD_POL": [{
            **key,
            "DTH_BNF_PLN_OPT_CD": "1",
            "TFDF_CD": "2",
            "POL_GUA_ITS_RT": 4.0,
            "CDR_PCT": 250,
            "GRA_PER_EXP_DT": "9999-12-31",
            "IN_GRA_PER_IND": "0",
            "GRA_THD_RLE_CD": "",
        }],
        "LH_POL_MVRY_VAL": [{
            **key,
            "MVRY_DT": mv_date,
            "CSV_AMT": account_value,
            "ACC_VAL_AMT": account_value,
            "CINS_AMT": coi_charge,
            "EXP_CRG_AMT": expense_charge,
            "OTH_PRM_AMT": other_charge,
            "NAR_AMT": max(face - account_value, 0),
            "POL_DUR_NBR": 10,
        }],
        "TH_POL_MVRY_VAL": [{
            **key,
            "MVRY_DT": mv_date,
            "CSV_AMT": account_value,
            "ACC_VAL_AMT": account_value,
            "NET_AMT_RSK": max(face - account_value, 0),
        }],
        "LH_POL_TOTALS": [{
            **key,
            "TOT_REG_PRM_AMT": premium_td,
            "TOT_ADD_PRM_AMT": 0,
            "TOT_WTD_AMT": round(account_value * 0.035, 2),
            "POL_CST_BSS_AMT": round(premium_td * 0.94, 2),
        }],
        "LH_POL_YR_TOT": [{
            **key,
            "YTD_TOT_PMT_AMT": premium_ytd,
            "YTD_ADD_PRM_AMT": 0,
        }],
        "LH_POL_TARGET": [
            {**key, "TAR_TYP_CD": "MT", "TAR_PRM_AMT": mtp, "TAR_DT": mv_date},
            {**key, "TAR_TYP_CD": "MA", "TAR_PRM_AMT": round(mtp * 115, 2), "TAR_DT": "2031-06-15"},
            {**key, "TAR_TYP_CD": "TA", "TAR_PRM_AMT": round(glp * 9.25, 2), "TAR_DT": mv_date},
            {**key, "TAR_TYP_CD": "IX", "TAR_PRM_AMT": round(account_value * 0.92, 2), "TAR_DT": mv_date},
        ],
        "LH_COM_TARGET": [{
            **key,
            "AGT_COM_PHA_NBR": 1,
            "TAR_TYP_CD": "CT",
            "TAR_PRM_AMT": ctp,
        }],
        "LH_COV_INS_GDL_PRM": [
            {**key, "COV_PHA_NBR": 1, "PRM_RT_TYP_CD": "A", "GDL_PRM_AMT": glp},
            {**key, "COV_PHA_NBR": 1, "PRM_RT_TYP_CD": "S", "GDL_PRM_AMT": gsp},
        ],
        "LH_COV_INS_RNL_RT": [
            {**key, "COV_PHA_NBR": 1, "PRM_RT_TYP_CD": "C", "JT_INS_IND": "0", "RNL_RT": 145, "RT_CLS_CD": rate_class, "RT_SEX_CD": sex, "ISS_AGE": issue_age},
            {**key, "COV_PHA_NBR": 1, "PRM_RT_TYP_CD": "M", "JT_INS_IND": "0", "RNL_RT": mtp, "RT_CLS_CD": rate_class, "RT_SEX_CD": sex, "ISS_AGE": issue_age},
            {**key, "COV_PHA_NBR": 1, "PRM_RT_TYP_CD": "T", "JT_INS_IND": "0", "RNL_RT": ctp, "RT_CLS_CD": rate_class, "RT_SEX_CD": sex, "ISS_AGE": issue_age},
        ],
        "LH_TAMRA_7_PY_PER": [{
            **key,
            "MEC_STA_CD": "N",
            "SEVN_PY_LVL_PRM_AMT": round(face * 0.026, 2),
            "SVPY_LVL_PRM_AMT": round(face * 0.026, 2),
            "SVPY_PER_STR_DT": issue_date,
            "SVPY_BEG_CSV_AMT": 0,
            "SVPY_BEG_FCE_AMT": face,
            "XCG_1035_PMT_QTY": 0,
        }],
        "LH_TAMRA_7_PY_YR": [{
            **key,
            "ACC_GLP_AMT": round(glp * 9.25, 2),
            "ACC_MTP_AMT": round(mtp * 115, 2),
            "SVPY_PRM_PAY_AMT": premium_ytd,
            "SVPY_WTD_AMT": 0,
        }],
    }

    if regular_loan:
        rows["LH_CSH_VAL_LOAN"] = [{
            **key,
            "MVRY_DT": "9999-12-31",
            "LN_TYP_CD": "1",
            "LN_PRI_AMT": regular_loan,
            "POL_LN_ITS_AMT": round(regular_loan * 0.012, 2),
            "LN_CRG_ITS_RT": 0.06,
            "LN_ITS_AMT_TYP_CD": "2",
            "PRF_LN_IND": "0",
        }]
    else:
        rows["LH_CSH_VAL_LOAN"] = [{**key, "MVRY_DT": "9999-12-31", "LN_PRI_AMT": 0}]

    if variable_loan:
        rows["LH_FND_VAL_LOAN"] = [{
            **key,
            "MVRY_DT": "9999-12-31",
            "FND_ID_CD": "LZ",
            "FND_VAL_PHA_NBR": 1,
            "LN_TYP_CD": "6",
            "LN_PRI_AMT": variable_loan,
            "POL_LN_ITS_AMT": round(variable_loan * 0.01, 2),
            "LN_CRG_ITS_RT": 0.0775,
            "LN_ITS_AMT_TYP_CD": "2",
            "PRF_LN_IND": "0",
        }]
    else:
        rows["LH_FND_VAL_LOAN"] = [{**key, "MVRY_DT": "9999-12-31", "FND_ID_CD": "A", "FND_VAL_PHA_NBR": 1, "LN_PRI_AMT": 0}]

    return rows


def create_policy_db() -> int:
    policies = [
        ("DEV10001", "AA", "DEV-POL-001", dict(issue_age=35, sex="M", rate_class="N", face=250000, account_value=48250.75, modal=250.00)),
        ("DEV10002", "AA", "DEV-POL-002", dict(issue_age=42, sex="F", rate_class="N", face=500000, account_value=91320.10, modal=500.00, regular_loan=12500.00)),
        ("DEV10003", "AA", "DEV-POL-003", dict(issue_age=51, sex="M", rate_class="S", face=150000, account_value=22750.25, modal=185.00, variable_loan=8200.00)),
        ("DEV10004", "BB", "DEV-POL-004", dict(issue_age=29, sex="F", rate_class="P", face=300000, account_value=30110.40, modal=300.00)),
        ("DEV10005", "BB", "DEV-POL-005", dict(issue_age=60, sex="M", rate_class="N", face=100000, account_value=57100.00, modal=135.00, regular_loan=5000.00)),
    ]
    tables: dict[str, list[dict]] = {}
    for policy_number, company, policy_id, kwargs in policies:
        for table, rows in _policy_rows(policy_number, company, policy_id, **kwargs).items():
            tables.setdefault(table, []).extend(rows)

    DEV_DIR.mkdir(parents=True, exist_ok=True)
    if POLICY_DB.exists():
        POLICY_DB.unlink()
    conn = sqlite3.connect(POLICY_DB)
    try:
        for table in sorted(_mapped_policy_tables() - set(tables)):
            _create_empty_table(conn, table)
        for table, rows in tables.items():
            _create_table(conn, table, rows)
        conn.commit()
    finally:
        conn.close()
    return len(policies)


def _duration_rows(table: str, plancode: str, base_rate: float, count: int = 121) -> list[dict]:
    rows = []
    for duration in range(1, count + 1):
        rows.append({
            "Plancode": plancode,
            "IssueVersion": 1,
            "IssueAge": 35,
            "Sex": "M",
            "Rateclass": "N",
            "Scale": 1,
            "Band": 1,
            "Rate": round(base_rate * (1 + duration * 0.006), 8),
        })
    return rows


def _all_demo_rate_rows(table: str, base_rate: float) -> list[dict]:
    rows = []
    for issue_age, sex, rate_class, factor in [
        (35, "M", "N", 1.00),
        (42, "F", "N", 0.92),
        (51, "M", "S", 1.45),
        (29, "F", "P", 0.78),
        (60, "M", "N", 1.80),
    ]:
        for duration in range(1, 122):
            rows.append({
                "Plancode": PLANCODE,
                "IssueVersion": 1,
                "IssueAge": issue_age,
                "Sex": sex,
                "Rateclass": rate_class,
                "Scale": 1,
                "Band": 1,
                "Rate": round(base_rate * factor * (1 + duration * 0.006), 8),
            })
    return rows


def create_rates_db() -> None:
    DEV_DIR.mkdir(parents=True, exist_ok=True)
    if RATES_DB.exists():
        RATES_DB.unlink()
    conn = sqlite3.connect(RATES_DB)
    try:
        tables = {
            "Select_RATE_COI": _all_demo_rate_rows("Select_RATE_COI", 0.072),
            "Select_RATE_EPU": _all_demo_rate_rows("Select_RATE_EPU", 0.018),
            "Select_RATE_SCR": _all_demo_rate_rows("Select_RATE_SCR", 7.5),
            "Select_RATE_MFEE": _all_demo_rate_rows("Select_RATE_MFEE", 5.0),
            "Select_RATE_EPP": _all_demo_rate_rows("Select_RATE_EPP", 0.06),
            "Select_RATE_TPP": _all_demo_rate_rows("Select_RATE_TPP", 1.0),
            "Select_RATE_POAV": _duration_rows("Select_RATE_POAV", PLANCODE, 0.001),
            "Select_RATE_GINT": [{"Plancode": PLANCODE, "IssueVersion": 1, "Rate": 0.04} for _ in range(121)],
            "Select_RATE_RLNCRG": [{"Plancode": PLANCODE, "IssueVersion": 1, "Rate": 0.04} for _ in range(121)],
            "Select_RATE_RLNCRD": [{"Plancode": PLANCODE, "IssueVersion": 1, "Rate": 0.055} for _ in range(121)],
            "Select_RATE_PLNCRG": [{"Plancode": PLANCODE, "IssueVersion": 1, "Rate": 0.04} for _ in range(121)],
            "Select_RATE_PLNCRD": [{"Plancode": PLANCODE, "IssueVersion": 1, "Rate": 0.055} for _ in range(121)],
            "Select_RATE_BANDSPECS": [{"Plancode": PLANCODE, "IssueVersion": 1, "SpecifiedAmount": 0, "Band": 1}],
        }
        single_value_rows = []
        for issue_age, sex, rate_class, factor in [
            (35, "M", "N", 1.00),
            (42, "F", "N", 0.92),
            (51, "M", "S", 1.45),
            (29, "F", "P", 0.78),
            (60, "M", "N", 1.80),
        ]:
            single_value_rows.append({
                "Plancode": PLANCODE,
                "IssueVersion": 1,
                "IssueAge": issue_age,
                "Sex": sex,
                "Rateclass": rate_class,
                "Band": 1,
                "Rate": round(1200 * factor, 2),
            })
        tables["Select_RATE_MTP"] = single_value_rows
        tables["Select_RATE_CTP"] = [{**row, "Rate": round(row["Rate"] * 2.1, 2)} for row in single_value_rows]
        tables["Select_RATE_TBL1MTP"] = [{**row, "Rate": round(row["Rate"] * 1.15, 2)} for row in single_value_rows]
        tables["Select_RATE_TBL1CTP"] = [{**row, "Rate": round(row["Rate"] * 2.35, 2)} for row in single_value_rows]

        for table, rows in tables.items():
            _create_table(conn, table, rows)
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    policy_count = create_policy_db()
    create_rates_db()
    print(json.dumps({
        "policy_db": str(POLICY_DB),
        "rates_db": str(RATES_DB),
        "plancode": PLANCODE,
        "policy_count": policy_count,
        "enable_with": "SUITEVIEW_LOCAL_DATA=1",
    }, indent=2))


if __name__ == "__main__":
    main()