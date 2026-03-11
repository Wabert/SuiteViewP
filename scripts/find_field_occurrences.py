"""Find all occurrences of fields that need to be changed."""
import os
import re

# All the renames: (old_field, new_field, old_table_if_changing, new_table_if_changing)
renames = [
    # Row 1: LH_BAS_POL.BL_DAY_NBR -> BIL_DAY_NBR
    ("BL_DAY_NBR", "BIL_DAY_NBR", None, None),
    # Row 2: NXT_MVRY_DT -> NXT_MVRY_PRC_DT (on LH_BAS_POL)
    ("NXT_MVRY_DT", "NXT_MVRY_PRC_DT", None, None),
    # Row 3: TMN_DT -> PLN_TMN_DT (on LH_BAS_POL, also LH_COV_PHA)
    # Note: TMN_DT is used on both LH_BAS_POL and LH_COV_PHA contexts
    # Row 4: ANN_PRM_AMT -> ANN_PRM_UNT_AMT (on LH_COV_PHA)
    ("ANN_PRM_AMT", "ANN_PRM_UNT_AMT", None, None),
    # Row 5: ELM_PER_CD -> AH_ACC_ELM_PER_CD
    ("ELM_PER_CD", "AH_ACC_ELM_PER_CD", None, None),
    # Row 6: BNF_PER_CD -> AH_ACC_BNF_PER_CD
    ("BNF_PER_CD", "AH_ACC_BNF_PER_CD", None, None),
    # Row 9: TAR_VAL_AMT -> TAR_PRM_AMT (on LH_COV_TARGET)
    ("TAR_VAL_AMT", "TAR_PRM_AMT", None, None),
    # Row 10+11: LN_ITS_RT -> LN_CRG_ITS_RT
    ("LN_ITS_RT", "LN_CRG_ITS_RT", None, None),
    # Row 12: LN_ITS_AMT -> POL_LN_ITS_AMT (on LH_FND_VAL_LOAN)
    # Be careful - only on LH_FND_VAL_LOAN, not other tables
    # Row 13: BKT_STR_DT -> ITS_PER_STR_DT
    ("BKT_STR_DT", "ITS_PER_STR_DT", None, None),
    # Row 14: PTP_APL_TYP_CD -> CK_PTP_TYP_CD
    ("PTP_APL_TYP_CD", "CK_PTP_TYP_CD", None, None),
    # Row 17: OYT_FCE_AMT -> OYT_ADD_AMT
    ("OYT_FCE_AMT", "OYT_ADD_AMT", None, None),
    # Row 18: PUA_FCE_AMT -> PUA_AMT
    ("PUA_FCE_AMT", "PUA_AMT", None, None),
    # Row 20: NXT_ANV_DT -> NXT_YR_END_PRC_DT
    ("NXT_ANV_DT", "NXT_YR_END_PRC_DT", None, None),
    # Row 21: REG_PRM_AMT -> POL_PRM_AMT
    ("REG_PRM_AMT", "POL_PRM_AMT", None, None),
    # Row 28: VLU_PER_UNT_AMT -> COV_VPU_AMT
    ("VLU_PER_UNT_AMT", "COV_VPU_AMT", None, None),
    # Row 29+30: LN_ITS_STS_CD -> LN_ITS_AMT_TYP_CD
    ("LN_ITS_STS_CD", "LN_ITS_AMT_TYP_CD", None, None),
    # Row 31: CRE_ITS_RT -> VAL_PHA_ITS_RT
    ("CRE_ITS_RT", "VAL_PHA_ITS_RT", None, None),
    # Row 32: CSH_SUR_VAL_AMT -> CSV_AMT (on LH_POL_MVRY_VAL)
    ("CSH_SUR_VAL_AMT", "CSV_AMT", None, None),
    # Row 34: on LH_LN_RPY_TRM: LN_ITS_AMT -> LN_RPY_AMT
    # Row 37+38+39+40: FH_FIXED renames
    ("TOT_TRS_AMT", "GROSS_AMT", None, None),
    ("ACC_VAL_GRS_AMT", "NET_AMT", None, None),
    ("FND_ID_CD", "FUND_ID", None, None),
    # Row 40: COV_PHA_NBR -> PHASE (FH_FIXED only)
    # Row 48: ISSUE_AGE_YR_NBR -> INS_ISS_AGE
    ("ISSUE_AGE_YR_NBR", "INS_ISS_AGE", None, None),
    # Row 74: OYT_CSV_AMT -> OYT_ADD_AMT
    ("OYT_CSV_AMT", "OYT_ADD_AMT", None, None),
    # Row 76: PUA_CSV_AMT -> PUA_AMT
    ("PUA_CSV_AMT", "PUA_AMT", None, None),
    # Row 78: CUM_DEP_AMT -> PTP_DEP_AMT
    ("CUM_DEP_AMT", "PTP_DEP_AMT", None, None),
    # Row 79: ITS_AMT -> DEP_ITS_AMT (on LH_PTP_ON_DEP)
]

# Fields/tables to REMOVE
removes = [
    "STS_CD",           # Row 41
    "GRC_IND",          # Row 42
    "DEFRA_IND",        # Row 43
    "GSP_AMT",          # Row 44 (on LH_BAS_POL)
    "GLP_AMT",          # Row 45 (on LH_BAS_POL)
    "VUL_IND",          # Row 46
    "IUL_IND",          # Row 47
    "MIN_PRM_AMT",      # Row 25
    "PRM_PAY_STS_CD",   # Row 26
    "DTH_BNF_AMT",      # Row 33 (on LH_POL_MVRY_VAL)
    "CV_AMT",           # Row 49
    "NSP_AMT",          # Row 50
    "OPT_EXER_IND",     # Row 51
    "COM_PCT",          # Row 57 (LH_AGT_COM_AMT)
    "MKT_ORG_CD",       # Row 57 (LH_AGT_COM_AMT)
    "SVC_AGT_IND",      # Row 58
    "MEC_IND",          # Row 59 (LH_TAMRA_MEC_PRM)
    "PMT_NBR",          # Row 60
    "PMT_DT",           # Row 61
    "PMT_AMT",          # Row 62
    "PTP_APL_DT",       # Row 64
    "PTP_GRS_AMT",      # Row 65
    "PTP_NET_AMT",      # Row 66
    "PTP_PRO_DT",       # Row 68
    "OYT_ISS_DT",       # Row 73
    "PUA_ISS_DT",       # Row 75
    "DEP_DT",           # Row 77
]

# Search directories
search_dirs = [
    r"c:\Users\ab7y02\Dev\SuiteViewP\suiteview\polview\models",
]

def search_files(pattern, dirs):
    results = []
    for d in dirs:
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(".py"):
                    filepath = os.path.join(root, f)
                    with open(filepath, "r", encoding="utf-8") as fh:
                        for i, line in enumerate(fh, 1):
                            if pattern in line:
                                rel = os.path.relpath(filepath, r"c:\Users\ab7y02\Dev\SuiteViewP")
                                results.append((rel, i, line.rstrip()))
    return results

print("=" * 80)
print("RENAMES — Fields to change")
print("=" * 80)
for old, new, _, _ in renames:
    hits = search_files(f'"{old}"', search_dirs)
    if not hits:
        hits = search_files(f"'{old}'", search_dirs)
    if hits:
        print(f"\n  {old} -> {new}  ({len(hits)} occurrences)")
        for path, line, content in hits:
            print(f"    {path}:{line}  {content.strip()[:90]}")
    else:
        print(f"\n  {old} -> {new}  (0 occurrences - may not be in code)")

# Special cases
print("\n\n" + "=" * 80)
print("SPECIAL: TMN_DT -> PLN_TMN_DT")
print("=" * 80)
for h in search_files('"TMN_DT"', search_dirs):
    print(f"  {h[0]}:{h[1]}  {h[2].strip()[:90]}")

print("\n\n" + "=" * 80)
print("SPECIAL: PTP_TYP_CD -> CK_PTP_TYP_CD (on UNAPPLIED and PTP_ON_DEP)")
print("=" * 80)
for h in search_files('"PTP_TYP_CD"', search_dirs):
    print(f"  {h[0]}:{h[1]}  {h[2].strip()[:90]}")

print("\n\n" + "=" * 80)
print("SPECIAL: TRN_TYP_CD and TRN_SBY_CD -> TRANS (FH_FIXED)")
print("=" * 80)
for field in ["TRN_TYP_CD", "TRN_SBY_CD"]:
    for h in search_files(f'"{field}"', search_dirs):
        print(f"  {h[0]}:{h[1]}  {h[2].strip()[:90]}")

print("\n\n" + "=" * 80)
print("SPECIAL: COV_PHA_NBR -> PHASE (FH_FIXED only)")
print("=" * 80)
for h in search_files('"COV_PHA_NBR"', search_dirs):
    if "FH_FIXED" in h[2]:
        print(f"  {h[0]}:{h[1]}  {h[2].strip()[:90]}")

print("\n\n" + "=" * 80)
print("SPECIAL: FH_FIXED LN_ITS_AMT -> vary by table")
print("=" * 80)
for h in search_files('"LN_ITS_AMT"', search_dirs):
    print(f"  {h[0]}:{h[1]}  {h[2].strip()[:90]}")

print("\n\n" + "=" * 80)
print("SPECIAL: ITS_AMT -> DEP_ITS_AMT on LH_PTP_ON_DEP")
print("=" * 80)
for h in search_files('"ITS_AMT"', search_dirs):
    print(f"  {h[0]}:{h[1]}  {h[2].strip()[:90]}")

print("\n\n" + "=" * 80)
print("REMOVES — Fields to delete")
print("=" * 80)
for field in removes:
    hits = search_files(f'"{field}"', search_dirs)
    if hits:
        print(f"\n  REMOVE {field}  ({len(hits)} occurrences)")
        for path, line, content in hits:
            print(f"    {path}:{line}  {content.strip()[:90]}")

# Table changes
print("\n\n" + "=" * 80)
print("TABLE CHANGES")
print("=" * 80)
# Row 19: LH_BAS_POL.ISSUE_DT -> LH_COV_PHA.ISSUE_DT
for h in search_files('"LH_BAS_POL", "ISSUE_DT"', search_dirs):
    print(f"  ISSUE_DT table change: {h[0]}:{h[1]}  {h[2].strip()[:90]}")
# Row 22: TH_BAS_POL.TAR_PRM_AMT -> LH_POL_TARGET
for h in search_files('"TH_BAS_POL", "TAR_PRM_AMT"', search_dirs):
    print(f"  TAR_PRM_AMT table change: {h[0]}:{h[1]}  {h[2].strip()[:90]}")
# Row 23: TH_BAS_POL.DTH_BNF_PLN_OPT_CD -> LH_NON_TRD_POL
for h in search_files('"TH_BAS_POL", "DTH_BNF_PLN_OPT_CD"', search_dirs):
    print(f"  DTH_BNF_PLN_OPT_CD table change: {h[0]}:{h[1]}  {h[2].strip()[:90]}")
# Row 24: TH_BAS_POL.TFDF_CD -> LH_NON_TRD_POL
for h in search_files('"TH_BAS_POL", "TFDF_CD"', search_dirs):
    print(f"  TFDF_CD table change: {h[0]}:{h[1]}  {h[2].strip()[:90]}")
# Row 56: COM_PCT -> LH_AGT_COM_RT.COM_RT_PCT
for h in search_files('"COM_PCT"', search_dirs):
    print(f"  COM_PCT: {h[0]}:{h[1]}  {h[2].strip()[:90]}")
