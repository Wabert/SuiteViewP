"""
Generate the field mapping table and save to a markdown file.
"""
import xlrd

wb = xlrd.open_workbook("docs/COBOLDB2translation.xls")
ws = wb.sheet_by_name("Translation")

# Build complete field index
field_to_tables = {}
table_to_fields = {}
for r in range(1, ws.nrows):
    table = str(ws.cell_value(r, 3)).strip()
    field = str(ws.cell_value(r, 4)).strip()
    desc = str(ws.cell_value(r, 5)).strip() if ws.ncols > 5 else ""
    if table and field:
        if field not in field_to_tables:
            field_to_tables[field] = []
        field_to_tables[field].append((table, desc))
        if table not in table_to_fields:
            table_to_fields[table] = {}
        table_to_fields[table][field] = desc

invalid_refs = [
    ("LH_BAS_POL", "STS_CD"),
    ("LH_BAS_POL", "GRC_IND"),
    ("LH_BAS_POL", "ISSUE_DT"),
    ("LH_BAS_POL", "NXT_ANV_DT"),
    ("LH_BAS_POL", "NXT_MVRY_DT"),
    ("LH_BAS_POL", "TMN_DT"),
    ("LH_BAS_POL", "BL_DAY_NBR"),
    ("LH_BAS_POL", "REG_PRM_AMT"),
    ("LH_BAS_POL", "DEFRA_IND"),
    ("LH_BAS_POL", "GSP_AMT"),
    ("LH_BAS_POL", "GLP_AMT"),
    ("TH_BAS_POL", "TAR_PRM_AMT"),
    ("TH_BAS_POL", "MIN_PRM_AMT"),
    ("TH_BAS_POL", "DTH_BNF_PLN_OPT_CD"),
    ("TH_BAS_POL", "VUL_IND"),
    ("TH_BAS_POL", "IUL_IND"),
    ("TH_BAS_POL", "TFDF_CD"),
    ("LH_COV_PHA", "ANN_PRM_AMT"),
    ("LH_COV_PHA", "PRM_PAY_STS_CD"),
    ("LH_COV_PHA", "TMN_DT"),
    ("LH_COV_PHA", "BNF_PER_CD"),
    ("LH_COV_PHA", "ELM_PER_CD"),
    ("LH_COV_PHA", "ISSUE_AGE_YR_NBR"),
    ("LH_COV_PHA", "VLU_PER_UNT_AMT"),
    ("TH_COV_PHA", "CV_AMT"),
    ("TH_COV_PHA", "NSP_AMT"),
    ("TH_COV_PHA", "OPT_EXER_IND"),
    ("LH_COV_INS_RNL_RT", "ISS_AGE"),
    ("LH_BNF_INS_RNL_RT", "JT_INS_IND"),
    ("LH_BNF_INS_RNL_RT", "ISS_AGE"),
    ("LH_COV_SKIPPED_PER", "SKP_FRM_DT"),
    ("LH_COV_SKIPPED_PER", "SKP_TO_DT"),
    ("LH_COV_SKIPPED_PER", "SKP_TYP_CD"),
    ("LH_COV_TARGET", "TAR_VAL_AMT"),
    ("LH_CSH_VAL_LOAN", "LN_ITS_RT"),
    ("LH_CSH_VAL_LOAN", "LN_ITS_STS_CD"),
    ("LH_FND_VAL_LOAN", "LN_ITS_AMT"),
    ("LH_FND_VAL_LOAN", "LN_ITS_RT"),
    ("LH_FND_VAL_LOAN", "LN_ITS_STS_CD"),
    ("LH_AGT_COM_AMT", "COM_PCT"),
    ("LH_AGT_COM_AMT", "MKT_ORG_CD"),
    ("LH_AGT_COM_AMT", "SVC_AGT_IND"),
    ("LH_POL_FND_VAL_TOT", "CRE_ITS_RT"),
    ("LH_POL_FND_VAL_TOT", "BKT_STR_DT"),
    ("LH_POL_MVRY_VAL", "CSH_SUR_VAL_AMT"),
    ("LH_POL_MVRY_VAL", "DTH_BNF_AMT"),
    ("LH_TAMRA_MEC_PRM", "MEC_IND"),
    ("LH_LN_RPY_TRM", "PMT_NBR"),
    ("LH_LN_RPY_TRM", "PMT_DT"),
    ("LH_LN_RPY_TRM", "PMT_AMT"),
    ("LH_LN_RPY_TRM", "LN_PRI_AMT"),
    ("LH_LN_RPY_TRM", "LN_ITS_AMT"),
    ("FH_FIXED", "TRN_TYP_CD"),
    ("FH_FIXED", "TRN_SBY_CD"),
    ("FH_FIXED", "TOT_TRS_AMT"),
    ("FH_FIXED", "ACC_VAL_GRS_AMT"),
    ("FH_FIXED", "FND_ID_CD"),
    ("FH_FIXED", "COV_PHA_NBR"),
    ("LH_APPLIED_PTP", "PTP_APL_DT"),
    ("LH_APPLIED_PTP", "PTP_APL_TYP_CD"),
    ("LH_APPLIED_PTP", "PTP_GRS_AMT"),
    ("LH_APPLIED_PTP", "PTP_NET_AMT"),
    ("LH_APPLIED_PTP", "POL_DUR_NBR"),
    ("LH_UNAPPLIED_PTP", "PTP_PRO_DT"),
    ("LH_UNAPPLIED_PTP", "PTP_TYP_CD"),
    ("LH_UNAPPLIED_PTP", "PTP_GRS_AMT"),
    ("LH_UNAPPLIED_PTP", "PTP_NET_AMT"),
    ("LH_UNAPPLIED_PTP", "POL_DUR_NBR"),
    ("LH_ONE_YR_TRM_ADD", "COV_PHA_NBR"),
    ("LH_ONE_YR_TRM_ADD", "OYT_ISS_DT"),
    ("LH_ONE_YR_TRM_ADD", "OYT_FCE_AMT"),
    ("LH_ONE_YR_TRM_ADD", "OYT_CSV_AMT"),
    ("LH_PAID_UP_ADD", "PUA_ISS_DT"),
    ("LH_PAID_UP_ADD", "PUA_FCE_AMT"),
    ("LH_PAID_UP_ADD", "PUA_CSV_AMT"),
    ("LH_PTP_ON_DEP", "DEP_DT"),
    ("LH_PTP_ON_DEP", "PTP_TYP_CD"),
    ("LH_PTP_ON_DEP", "CUM_DEP_AMT"),
    ("LH_PTP_ON_DEP", "ITS_AMT"),
]

lines = []
lines.append("# DB2 Field Mapping — Code vs Workbook")
lines.append("")
lines.append("Fields used in our code that are NOT found in the COBOL/DB2 Translation workbook,")
lines.append("with best-guess suggested corrections.")
lines.append("")
lines.append("| # | Code Table | Code Field | Suggested Table | Suggested Field | Reasoning |")
lines.append("|---|---|---|---|---|---|")

n = 0
for code_table, code_field in invalid_refs:
    n += 1

    # Strategy 1: field exists in another table
    if code_field in field_to_tables:
        alts = field_to_tables[code_field]
        alt_tables = [t for t, d in alts]
        guess_table = alt_tables[0] if len(alt_tables) == 1 else " / ".join(alt_tables[:3])
        desc = alts[0][1][:50]
        lines.append(f"| {n} | {code_table} | `{code_field}` | {guess_table} | `{code_field}` | Field exists on other table(s): {desc} |")
        continue

    # Strategy 2: partial match within same table
    if code_table in table_to_fields:
        tbl_fields = table_to_fields[code_table]
        candidates = []
        parts = code_field.split("_")
        for tf, td in tbl_fields.items():
            tf_parts = tf.split("_")
            common = set(parts) & set(tf_parts)
            if len(common) >= 2:
                score = len(common) * 10
                # Bonus for same suffix
                if parts[-1] == tf_parts[-1]:
                    score += 5
                # Bonus for same prefix
                if parts[0] == tf_parts[0]:
                    score += 3
                candidates.append((tf, td, score))
        if candidates:
            candidates.sort(key=lambda x: -x[2])
            best = candidates[0]
            lines.append(f"| {n} | {code_table} | `{code_field}` | {code_table} | `{best[0]}` | Partial match: {best[1][:50]} |")
            continue

    # Strategy 3: field exists on alt-prefix table
    base = code_table[3:] if len(code_table) > 3 else code_table
    found = False
    for pfx in ["LH_", "TH_", "VH_", "FH_"]:
        alt_table = pfx + base
        if alt_table != code_table and alt_table in table_to_fields:
            if code_field in table_to_fields[alt_table]:
                desc = table_to_fields[alt_table][code_field]
                lines.append(f"| {n} | {code_table} | `{code_field}` | {alt_table} | `{code_field}` | Found on alt prefix table: {desc[:50]} |")
                found = True
                break
    if found:
        continue

    # Strategy 4: Table not in workbook at all
    if code_table not in table_to_fields:
        lines.append(f"| {n} | {code_table} | `{code_field}` | ??? | ??? | **Table not in workbook** |")
        continue

    # Strategy 5: Broader search - any field containing same key parts
    parts = code_field.split("_")
    broader = []
    for tf, td_list in field_to_tables.items():
        tf_parts = tf.split("_")
        common = set(parts) & set(tf_parts)
        if len(common) >= 2:
            for t, d in td_list:
                broader.append((t, tf, d, len(common)))
    if broader:
        broader.sort(key=lambda x: -x[3])
        best = broader[0]
        lines.append(f"| {n} | {code_table} | `{code_field}` | {best[0]} | `{best[1]}` | Broad match: {best[2][:50]} |")
        continue

    lines.append(f"| {n} | {code_table} | `{code_field}` | {code_table} | ??? | **No match found** |")

output = "\n".join(lines)
with open("docs/field_mapping_review.md", "w", encoding="utf-8") as f:
    f.write(output)

print(f"Written {n} entries to docs/field_mapping_review.md")
