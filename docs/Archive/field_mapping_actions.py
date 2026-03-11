# User's Updated Field Mapping Review
# ======================================================================

# Row 1: [HIGH]
#   Code:      LH_BAS_POL.BL_DAY_NBR
#   Suggested: LH_BAS_POL.BIL_DAY_NBR
#   Reason:    Workbook has BIL_DAY_NBR = 'Billing Day'
#   ACTION:    Please make suggested Update

# Row 2: [HIGH]
#   Code:      LH_BAS_POL.NXT_MVRY_DT
#   Suggested: LH_BAS_POL.NXT_MVRY_PRC_DT
#   Reason:    Workbook: 'Next Monthliversary Date'
#   ACTION:    Please make suggested Update

# Row 3: [HIGH]
#   Code:      LH_BAS_POL.TMN_DT
#   Suggested: LH_BAS_POL.PLN_TMN_DT
#   Reason:    Workbook: 'Next Potential Termination Event Date'
#   ACTION:    Please make suggested Update

# Row 4: [HIGH]
#   Code:      LH_COV_PHA.ANN_PRM_AMT
#   Suggested: LH_COV_PHA.ANN_PRM_UNT_AMT
#   Reason:    Workbook: 'Annual Premium Per Unit'
#   ACTION:    Please make suggested Update

# Row 5: [HIGH]
#   Code:      LH_COV_PHA.ELM_PER_CD
#   Suggested: LH_COV_PHA.AH_ACC_ELM_PER_CD
#   Reason:    DI elimination period (or AH_SIC_ELM_PER_CD)
#   ACTION:    Please make suggested Update

# Row 6: [HIGH]
#   Code:      LH_COV_PHA.BNF_PER_CD
#   Suggested: LH_COV_PHA.AH_ACC_BNF_PER_CD
#   Reason:    DI benefit period (or AH_SIC_BNF_PER_CD)
#   ACTION:    Please make suggested Update

# Row 7: [HIGH]
#   Code:      LH_COV_INS_RNL_RT.ISS_AGE
#   Suggested: LH_COV_PHA.INS_ISS_AGE
#   Reason:    Issue Age lives on LH_COV_PHA
#   ACTION:    Please make suggested Update

# Row 8: [HIGH]
#   Code:      LH_BNF_INS_RNL_RT.ISS_AGE
#   Suggested: LH_COV_PHA.INS_ISS_AGE
#   Reason:    Same pattern
#   ACTION:    Please make suggested Update

# Row 9: [HIGH]
#   Code:      LH_COV_TARGET.TAR_VAL_AMT
#   Suggested: LH_COV_TARGET.TAR_PRM_AMT
#   Reason:    Likely meant 'Target Premium Amount'
#   ACTION:    Please make suggested Update

# Row 10: [HIGH]
#   Code:      LH_CSH_VAL_LOAN.LN_ITS_RT
#   Suggested: LH_CSH_VAL_LOAN.LN_CRG_ITS_RT
#   Reason:    Workbook: 'Interest Rate charged on this loan'
#   ACTION:    Please make suggested Update

# Row 11: [HIGH]
#   Code:      LH_FND_VAL_LOAN.LN_ITS_RT
#   Suggested: LH_FND_VAL_LOAN.LN_CRG_ITS_RT
#   Reason:    Same pattern as CSH_VAL_LOAN
#   ACTION:    Please make suggested Update

# Row 12: [HIGH]
#   Code:      LH_FND_VAL_LOAN.LN_ITS_AMT
#   Suggested: LH_FND_VAL_LOAN.POL_LN_ITS_AMT
#   Reason:    Workbook has this on same table
#   ACTION:    Please make suggested Update

# Row 13: [HIGH]
#   Code:      LH_POL_FND_VAL_TOT.BKT_STR_DT
#   Suggested: LH_POL_FND_VAL_TOT.ITS_PER_STR_DT
#   Reason:    Workbook: 'Period Start Date'
#   ACTION:    Please make suggested Update

# Row 14: [HIGH]
#   Code:      LH_APPLIED_PTP.PTP_APL_TYP_CD
#   Suggested: LH_APPLIED_PTP.CK_PTP_TYP_CD
#   Reason:    Workbook: 'C=Coupon, D=Dividend'
#   ACTION:    Please make suggested Update

# Row 15: [HIGH]
#   Code:      LH_UNAPPLIED_PTP.PTP_TYP_CD
#   Suggested: LH_UNAPPLIED_PTP.CK_PTP_TYP_CD
#   Reason:    Same pattern
#   ACTION:    Please make suggested Update

# Row 16: [HIGH]
#   Code:      LH_PTP_ON_DEP.PTP_TYP_CD
#   Suggested: LH_PTP_ON_DEP.CK_PTP_TYP_CD
#   Reason:    Same pattern
#   ACTION:    Please make suggested Update

# Row 17: [HIGH]
#   Code:      LH_ONE_YR_TRM_ADD.OYT_FCE_AMT
#   Suggested: LH_ONE_YR_TRM_ADD.OYT_ADD_AMT
#   Reason:    Only amount field on this table
#   ACTION:    Please make suggested Update

# Row 18: [HIGH]
#   Code:      LH_PAID_UP_ADD.PUA_FCE_AMT
#   Suggested: LH_PAID_UP_ADD.PUA_AMT
#   Reason:    Only amount field on this table
#   ACTION:    Please make suggested Update

# Row 19: [MEDIUM]
#   Code:      LH_BAS_POL.ISSUE_DT
#   Suggested: LH_COV_PHA.ISSUE_DT
#   Reason:    Field exists on LH_COV_PHA, not LH_BAS_POL; may be a view alias
#   ACTION:    Please make suggested Update

# Row 20: [MEDIUM]
#   Code:      LH_BAS_POL.NXT_ANV_DT
#   Suggested: LH_BAS_POL.NXT_YR_END_PRC_DT
#   Reason:    Workbook has LST_ANV_DT but no NXT_ANV_DT; might be computed
#   ACTION:    Please make suggested Update

# Row 21: [MEDIUM]
#   Code:      LH_BAS_POL.REG_PRM_AMT
#   Suggested: LH_BAS_POL.POL_PRM_AMT
#   Reason:    Workbook: 'Mode Premium' — may not be same semantics
#   ACTION:    Please make suggested Update

# Row 22: [MEDIUM]
#   Code:      TH_BAS_POL.TAR_PRM_AMT
#   Suggested: LH_POL_TARGET.TAR_PRM_AMT
#   Reason:    Exists on target tables; TH_BAS_POL only has 12 fields in workbook
#   ACTION:    Please make suggested Update

# Row 23: [MEDIUM]
#   Code:      TH_BAS_POL.DTH_BNF_PLN_OPT_CD
#   Suggested: LH_NON_TRD_POL.DTH_BNF_PLN_OPT_CD
#   Reason:    Exists on LH_NON_TRD_POL; TH_BAS_POL underspec'd in workbook
#   ACTION:    Please make suggested Update

# Row 24: [MEDIUM]
#   Code:      TH_BAS_POL.TFDF_CD
#   Suggested: LH_NON_TRD_POL.TFDF_CD
#   Reason:    Exists on LH_NON_TRD_POL
#   ACTION:    Please make suggested Update

# Row 25: [MEDIUM]
#   Code:      TH_BAS_POL.MIN_PRM_AMT
#   Suggested: .
#   Reason:    No clear match; TH_BAS_POL only 12 fields in workbook
#   ACTION:    Remove any calls or reference to this table.field

# Row 26: [MEDIUM]
#   Code:      LH_COV_PHA.PRM_PAY_STS_CD
#   Suggested: .
#   Reason:    No clear match; may be a view alias for premium pay status
#   ACTION:    Remove any calls or reference to this table.field

# Row 27: [MEDIUM]
#   Code:      LH_COV_PHA.TMN_DT
#   Suggested: LH_BAS_POL.PLN_TMN_DT
#   Reason:    On LH_BAS_POL, not LH_COV_PHA
#   ACTION:    Please make suggested Update

# Row 28: [MEDIUM]
#   Code:      LH_COV_PHA.VLU_PER_UNT_AMT
#   Suggested: LH_COV_PHA.COV_VPU_AMT
#   Reason:    Value Per Unit — code already has fallback to COV_VPU_AMT
#   ACTION:    Please make suggested Update

# Row 29: [MEDIUM]
#   Code:      LH_CSH_VAL_LOAN.LN_ITS_STS_CD
#   Suggested: LH_CSH_VAL_LOAN.LN_ITS_AMT_TYP_CD
#   Reason:    Possibly 'Interest Amount Type Code'
#   ACTION:    Please make suggested Update

# Row 30: [MEDIUM]
#   Code:      LH_FND_VAL_LOAN.LN_ITS_STS_CD
#   Suggested: LH_FND_VAL_LOAN.LN_ITS_AMT_TYP_CD
#   Reason:    Same pattern
#   ACTION:    Please make suggested Update

# Row 31: [MEDIUM]
#   Code:      LH_POL_FND_VAL_TOT.CRE_ITS_RT
#   Suggested: .
#   Reason:    No clear match on this table
#   ACTION:    I added the correct table and field

# Row 32: [MEDIUM]
#   Code:      LH_POL_MVRY_VAL.CSH_SUR_VAL_AMT
#   Suggested: LH_POL_MVRY_VAL.CSV_AMT
#   Reason:    Probably a view column name
#   ACTION:    Please make suggested Update

# Row 33: [MEDIUM]
#   Code:      LH_POL_MVRY_VAL.DTH_BNF_AMT
#   Suggested: .
#   Reason:    Probably a view column name
#   ACTION:    Remove any calls or reference to this table.field

# Row 34: [MEDIUM]
#   Code:      LH_LN_RPY_TRM.LN_ITS_AMT
#   Suggested: LH_LN_RPY_TRM.LN_RPY_AMT
#   Reason:    Workbook: 'Repayment Amount'
#   ACTION:    Please make suggested Update

# Row 35: [MEDIUM]
#   Code:      FH_FIXED.TRN_TYP_CD
#   Suggested: FH_FIXED.TRANS
#   Reason:    Workbook uses TRANS for transaction type
#   ACTION:    Please make suggested Update

# Row 36: [MEDIUM]
#   Code:      FH_FIXED.TRN_SBY_CD
#   Suggested: FH_FIXED.TRANS
#   Reason:    May be embedded in TRANS field
#   ACTION:    Please make suggested Update

# Row 37: [MEDIUM]
#   Code:      FH_FIXED.TOT_TRS_AMT
#   Suggested: FH_FIXED.GROSS_AMT
#   Reason:    Workbook names gross amount differently
#   ACTION:    Please make suggested Update

# Row 38: [MEDIUM]
#   Code:      FH_FIXED.ACC_VAL_GRS_AMT
#   Suggested: FH_FIXED.NET_AMT
#   Reason:    Workbook: NET_AMT for accumulation value
#   ACTION:    Please make suggested Update

# Row 39: [MEDIUM]
#   Code:      FH_FIXED.FND_ID_CD
#   Suggested: FH_FIXED.FUND_ID
#   Reason:    Different naming convention
#   ACTION:    Please make suggested Update

# Row 40: [MEDIUM]
#   Code:      FH_FIXED.COV_PHA_NBR
#   Suggested: FH_FIXED.PHASE
#   Reason:    Different naming convention
#   ACTION:    Please make suggested Update

# Row 41: [LOW]
#   Code:      LH_BAS_POL.STS_CD
#   Suggested: .
#   Reason:    No match at all — status code; likely a view alias
#   ACTION:    Remove any calls or reference to this table.field

# Row 42: [LOW]
#   Code:      LH_BAS_POL.GRC_IND
#   Suggested: .
#   Reason:    No match — grace indicator
#   ACTION:    Remove any calls or reference to this table.field

# Row 43: [LOW]
#   Code:      LH_BAS_POL.DEFRA_IND
#   Suggested: .
#   Reason:    No match at all
#   ACTION:    Remove any calls or reference to this table.field

# Row 44: [LOW]
#   Code:      LH_BAS_POL.GSP_AMT
#   Suggested: .
#   Reason:    Guideline Single Premium — not in workbook
#   ACTION:    Remove any calls or reference to this table.field

# Row 45: [LOW]
#   Code:      LH_BAS_POL.GLP_AMT
#   Suggested: .
#   Reason:    Guideline Level Premium — not in workbook
#   ACTION:    Remove any calls or reference to this table.field

# Row 46: [LOW]
#   Code:      TH_BAS_POL.VUL_IND
#   Suggested: .
#   Reason:    TH_BAS_POL only 12 fields in workbook; likely more on actual DB2
#   ACTION:    Please make suggested Update

# Row 47: [LOW]
#   Code:      TH_BAS_POL.IUL_IND
#   Suggested: .
#   Reason:    Same — workbook TH_BAS_POL underspecified
#   ACTION:    Remove any calls or reference to this table.field

# Row 48: [LOW]
#   Code:      LH_COV_PHA.ISSUE_AGE_YR_NBR
#   Suggested: LH_COV_PHA.INS_ISS_AGE
#   Reason:    May be alternate field for issue age
#   ACTION:    Please make suggested Update

# Row 49: [LOW]
#   Code:      TH_COV_PHA.CV_AMT
#   Suggested: .
#   Reason:    TH_COV_PHA only 6 fields in workbook
#   ACTION:    Remove any calls or reference to this table.field

# Row 50: [LOW]
#   Code:      TH_COV_PHA.NSP_AMT
#   Suggested: .
#   Reason:    TH_COV_PHA only 6 fields in workbook
#   ACTION:    Remove any calls or reference to this table.field

# Row 51: [LOW]
#   Code:      TH_COV_PHA.OPT_EXER_IND
#   Suggested: .
#   Reason:    GIO option exercise indicator — not in workbook
#   ACTION:    Remove any calls or reference to this table.field

# Row 52: [LOW]
#   Code:      LH_BNF_INS_RNL_RT.JT_INS_IND
#   Suggested: LH_COV_INS_RNL_RT.JT_INS_IND
#   Reason:    Table not in workbook; exists on LH_COV_INS_RNL_RT
#   ACTION:    Please make suggested Update

# Row 53: [LOW]
#   Code:      LH_COV_SKIPPED_PER.SKP_FRM_DT
#   Suggested: .
#   Reason:    Table exists in workbook but these fields not listed
#   ACTION:    Remove any calls or reference to this table.field

# Row 54: [LOW]
#   Code:      LH_COV_SKIPPED_PER.SKP_TO_DT
#   Suggested: .
#   Reason:    Table exists in workbook but these fields not listed
#   ACTION:    Remove any calls or reference to this table.field

# Row 55: [LOW]
#   Code:      LH_COV_SKIPPED_PER.SKP_TYP_CD
#   Suggested: .
#   Reason:    Table exists in workbook but these fields not listed
#   ACTION:    Remove any calls or reference to this table.field

# Row 56: [LOW]
#   Code:      LH_AGT_COM_AMT.COM_PCT
#   Suggested: LH_AGT_COM_RT.COM_RT_PCT
#   Reason:    LH_AGT_COM_AMT only 10 fields; COM_RT_PCT is on LH_AGT_COM_RT
#   ACTION:    Please make suggested Update

# Row 57: [LOW]
#   Code:      LH_AGT_COM_AMT.MKT_ORG_CD
#   Suggested: .
#   Reason:    Not found on LH_AGT_COM_AMT
#   ACTION:    Remove any calls or reference to this table.field

# Row 58: [LOW]
#   Code:      LH_AGT_COM_AMT.SVC_AGT_IND
#   Suggested: .
#   Reason:    Not found on LH_AGT_COM_AMT
#   ACTION:    Remove any calls or reference to this table.field

# Row 59: [LOW]
#   Code:      LH_TAMRA_MEC_PRM.MEC_IND
#   Suggested: .
#   Reason:    Table not well documented in workbook
#   ACTION:    Remove any calls or reference to this table.field

# Row 60: [LOW]
#   Code:      LH_LN_RPY_TRM.PMT_NBR
#   Suggested: .
#   Reason:    Table exists but field names differ
#   ACTION:    Remove any calls or reference to this table.field

# Row 61: [LOW]
#   Code:      LH_LN_RPY_TRM.PMT_DT
#   Suggested: .
#   Reason:    No match found
#   ACTION:    Remove any calls or reference to this table.field

# Row 62: [LOW]
#   Code:      LH_LN_RPY_TRM.PMT_AMT
#   Suggested: .
#   Reason:    No match found
#   ACTION:    Remove any calls or reference to this table.field

# Row 63: [LOW]
#   Code:      LH_LN_RPY_TRM.LN_PRI_AMT
#   Suggested: LH_CSH_VAL_LOAN.LN_PRI_AMT
#   Reason:    Exists on CSH_VAL_LOAN / FND_VAL_LOAN, not RPY_TRM
#   ACTION:    Please make suggested Update

# Row 64: [LOW]
#   Code:      LH_APPLIED_PTP.PTP_APL_DT
#   Suggested: .
#   Reason:    No match found
#   ACTION:    Remove any calls or reference to this table.field

# Row 65: [LOW]
#   Code:      LH_APPLIED_PTP.PTP_GRS_AMT
#   Suggested: .
#   Reason:    No match found
#   ACTION:    Remove any calls or reference to this table.field

# Row 66: [LOW]
#   Code:      LH_APPLIED_PTP.PTP_NET_AMT
#   Suggested: .
#   Reason:    No match found
#   ACTION:    Remove any calls or reference to this table.field

# Row 67: [LOW]
#   Code:      LH_APPLIED_PTP.POL_DUR_NBR
#   Suggested: LH_POL_MVRY_VAL.POL_DUR_NBR
#   Reason:    Exists on other tables, not LH_APPLIED_PTP
#   ACTION:    Please make suggested Update

# Row 68: [LOW]
#   Code:      LH_UNAPPLIED_PTP.PTP_PRO_DT
#   Suggested: .
#   Reason:    No match found
#   ACTION:    Remove any calls or reference to this table.field

# Row 69: [LOW]
#   Code:      LH_UNAPPLIED_PTP.PTP_GRS_AMT
#   Suggested: .
#   Reason:    No match found
#   ACTION:    Remove any calls or reference to this table.field

# Row 70: [LOW]
#   Code:      LH_UNAPPLIED_PTP.PTP_NET_AMT
#   Suggested: .
#   Reason:    No match found
#   ACTION:    Remove any calls or reference to this table.field

# Row 71: [LOW]
#   Code:      LH_UNAPPLIED_PTP.POL_DUR_NBR
#   Suggested: LH_POL_MVRY_VAL.POL_DUR_NBR
#   Reason:    Exists on other tables
#   ACTION:    Please make suggested Update

# Row 72: [LOW]
#   Code:      LH_ONE_YR_TRM_ADD.COV_PHA_NBR
#   Suggested: LH_COV_PHA.COV_PHA_NBR
#   Reason:    Exists on LH_COV_PHA, not this table
#   ACTION:    Please make suggested Update

# Row 73: [LOW]
#   Code:      LH_ONE_YR_TRM_ADD.OYT_ISS_DT
#   Suggested: .
#   Reason:    No match found
#   ACTION:    Remove any calls or reference to this table.field

# Row 74: [LOW]
#   Code:      LH_ONE_YR_TRM_ADD.OYT_CSV_AMT
#   Suggested: LH_ONE_YR_TRM_ADD.OYT_ADD_AMT
#   Reason:    Only amount field on this table
#   ACTION:    Please make suggested Update

# Row 75: [LOW]
#   Code:      LH_PAID_UP_ADD.PUA_ISS_DT
#   Suggested: .
#   Reason:    No match found
#   ACTION:    Remove any calls or reference to this table.field

# Row 76: [LOW]
#   Code:      LH_PAID_UP_ADD.PUA_CSV_AMT
#   Suggested: LH_PAID_UP_ADD.PUA_AMT
#   Reason:    Only amount field on this table
#   ACTION:    Please make suggested Update

# Row 77: [LOW]
#   Code:      LH_PTP_ON_DEP.DEP_DT
#   Suggested: .
#   Reason:    No match found
#   ACTION:    Remove any calls or reference to this table.field

# Row 78: [LOW]
#   Code:      LH_PTP_ON_DEP.CUM_DEP_AMT
#   Suggested: LH_PTP_ON_DEP.PTP_DEP_AMT
#   Reason:    Partial — workbook: deposit amount
#   ACTION:    Please make suggested Update

# Row 79: [LOW]
#   Code:      LH_PTP_ON_DEP.ITS_AMT
#   Suggested: LH_PTP_ON_DEP.DEP_ITS_AMT
#   Reason:    Partial — workbook: 'Interest Amount'
#   ACTION:    Please make suggested Update
