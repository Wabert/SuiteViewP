"""CyberLife SQL ctes values section builders."""
from __future__ import annotations

from .common import *


def build_step_006(state: BuildState) -> None:
    if state.has_change_seq:
        state.sql_parts.append(f', CHANGE_SEGMENT AS (')
        state.sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, '9' AS CHG_TYP_CD FROM {state.schema}.LH_COV_TMN")
        state.sql_parts.append(f'  UNION')
        state.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, CHG_TYP_CD FROM {state.schema}.LH_NT_COV_CHG')
        state.sql_parts.append(f'  UNION')
        state.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, CHG_TYP_CD FROM {state.schema}.LH_NT_COV_CHG_SCH')
        state.sql_parts.append(f'  UNION')
        state.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, CHG_TYP_CD FROM {state.schema}.LH_SPM_BNF_CHG_SCH)')
    if state.disp_bill_mode:
        state.sql_parts.append(f', BILLMODE_POOL AS')
        state.sql_parts.append(f'  (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,')
        state.sql_parts.append(f'   PMT_FQY_PER, NSD_MD_CD')
        state.sql_parts.append(f'   FROM {state.schema}.LH_BAS_POL)')
    if state.needs_covsummary:
        state._apb_cond = " OR TEMPCOVALL.PLN_DES_SER_CD = '1U144A00'" if state.adv_apb_rider else ''
        state.sql_parts.append(f', ALL_BASE_COVS AS (')
        state.sql_parts.append(f'  SELECT TEMPCOV1.CK_SYS_CD, TEMPCOV1.TCH_POL_ID, TEMPCOV1.CK_CMP_CD')
        state.sql_parts.append(f'    , TEMPCOVALL.COV_PHA_NBR')
        state.sql_parts.append(f'    , ROUND(REAL(TEMPCOVALL.COV_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT), 2) SPECAMT')
        state.sql_parts.append(f'    , ROUND(REAL(TEMPCOVALL.OGN_SPC_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT), 2) ORIGSPECAMT')
        if state.needs_iswl_gcv:
            state.sql_parts.append(f'    , ROUND(REAL(TEMPCOVALL.LOW_DUR_1_CSV_AMT) * REAL(TEMPCOVALL.COV_UNT_QTY), 2) CV1')
            state.sql_parts.append(f'    , ROUND(REAL(TEMPCOVALL.LOW_DUR_2_CSV_AMT) * REAL(TEMPCOVALL.COV_UNT_QTY), 2) CV2')
        state.sql_parts.append(f'  FROM {state.schema}.LH_COV_PHA TEMPCOV1')
        state.sql_parts.append(f'    INNER JOIN {state.schema}.LH_COV_PHA TEMPCOVALL')
        state.sql_parts.append(f'      ON TEMPCOV1.COV_PHA_NBR = 1')
        state.sql_parts.append(f'      AND TEMPCOV1.CK_SYS_CD = TEMPCOVALL.CK_SYS_CD')
        state.sql_parts.append(f'      AND TEMPCOV1.CK_CMP_CD = TEMPCOVALL.CK_CMP_CD')
        state.sql_parts.append(f'      AND TEMPCOV1.TCH_POL_ID = TEMPCOVALL.TCH_POL_ID')
        state.sql_parts.append(f'      AND (TEMPCOVALL.PLN_DES_SER_CD = TEMPCOV1.PLN_DES_SER_CD{state._apb_cond}))')
        state.sql_parts.append(f', COVSUMMARY AS (')
        state.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID')
        state.sql_parts.append(f'    , SUM(ALL_BASE_COVS.SPECAMT) TOTAL_SA')
        state.sql_parts.append(f'    , SUM(ALL_BASE_COVS.ORIGSPECAMT) TOTAL_ORIGINAL_SA')
        if state.multi_base_covs:
            state.sql_parts.append(f'    , COUNT(ALL_BASE_COVS.COV_PHA_NBR) BASECOVCOUNT')
        if state.needs_iswl_gcv:
            state.sql_parts.append(f'    , SUM(ALL_BASE_COVS.CV1) TOTAL_CV1')
            state.sql_parts.append(f'    , SUM(ALL_BASE_COVS.CV2) TOTAL_CV2')
        state.sql_parts.append(f'  FROM ALL_BASE_COVS')
        state.sql_parts.append(f'  GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)')
    if state.needs_premwd_face:
        state.sql_parts.append(f', PREMWD_FACE AS (')
        state.sql_parts.append(f'  SELECT TEMPCOV1.CK_SYS_CD, TEMPCOV1.CK_CMP_CD, TEMPCOV1.TCH_POL_ID')
        state.sql_parts.append(f'    , SUM(ROUND(REAL(TEMPCOVALL.COV_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT), 2)) TOTAL_FACE')
        state.sql_parts.append(f'  FROM {state.schema}.LH_COV_PHA TEMPCOV1')
        state.sql_parts.append(f'    INNER JOIN {state.schema}.LH_COV_PHA TEMPCOVALL')
        state.sql_parts.append(f'      ON TEMPCOV1.COV_PHA_NBR = 1')
        state.sql_parts.append(f'      AND TEMPCOV1.CK_SYS_CD = TEMPCOVALL.CK_SYS_CD')
        state.sql_parts.append(f'      AND TEMPCOV1.CK_CMP_CD = TEMPCOVALL.CK_CMP_CD')
        state.sql_parts.append(f'      AND TEMPCOV1.TCH_POL_ID = TEMPCOVALL.TCH_POL_ID')
        state.sql_parts.append(f'      AND (TEMPCOVALL.PLN_DES_SER_CD = TEMPCOV1.PLN_DES_SER_CD')
        state.sql_parts.append(f"           OR TEMPCOVALL.PLN_DES_SER_CD = '1U144A00')")
        state.sql_parts.append(f"  WHERE (TEMPCOVALL.NXT_CHG_TYP_CD <> '0'")
        state.sql_parts.append(f'         OR (TEMPCOVALL.NXT_CHG_DT IS NOT NULL')
        state.sql_parts.append(f'             AND TEMPCOVALL.NXT_CHG_DT > CURRENT DATE))')
        state.sql_parts.append(f'  GROUP BY TEMPCOV1.CK_SYS_CD, TEMPCOV1.CK_CMP_CD, TEMPCOV1.TCH_POL_ID)')
    if state.needs_mvval:
        state.sql_parts.append(f', LASTMV AS (')
        state.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, MAX(MVRY_DT) LASTMVDT')
        state.sql_parts.append(f'  FROM {state.schema}.LH_POL_MVRY_VAL')
        state.sql_parts.append(f'  GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)')
        state.sql_parts.append(f', MVVAL AS (')
        state.sql_parts.append(f'  SELECT MV.CK_SYS_CD, MV.CK_CMP_CD, MV.TCH_POL_ID, MV.CSV_AMT')
        state.sql_parts.append(f'    , LASTMV.LASTMVDT')
        state.sql_parts.append(f'    , ROUND(REAL(MV.CSV_AMT) * REAL(ADVPROD.CDR_PCT)/100, 2) DB')
        state.sql_parts.append(f'    , CASE ADVPROD.DTH_BNF_PLN_OPT_CD')
        state.sql_parts.append(f"        WHEN '1' THEN 0")
        state.sql_parts.append(f"        WHEN '2' THEN REAL(MV.CSV_AMT)")
        state.sql_parts.append(f"        WHEN '3' THEN (TEMPPOLTOTALS.TOT_REG_PRM_AMT + TEMPPOLTOTALS.TOT_ADD_PRM_AMT)")
        state.sql_parts.append(f'        ELSE 0 END OPTDB')
        state.sql_parts.append(f'    , (TEMPPOLTOTALS.TOT_REG_PRM_AMT + TEMPPOLTOTALS.TOT_ADD_PRM_AMT) TOTALPREM')
        state.sql_parts.append(f'  FROM {state.schema}.LH_POL_MVRY_VAL MV')
        state.sql_parts.append(f'    INNER JOIN LASTMV ON MV.CK_SYS_CD = LASTMV.CK_SYS_CD')
        state.sql_parts.append(f'      AND MV.CK_CMP_CD = LASTMV.CK_CMP_CD')
        state.sql_parts.append(f'      AND MV.TCH_POL_ID = LASTMV.TCH_POL_ID')
        state.sql_parts.append(f'      AND MV.MVRY_DT = LASTMV.LASTMVDT')
        state.sql_parts.append(f'    INNER JOIN {state.schema}.LH_NON_TRD_POL ADVPROD')
        state.sql_parts.append(f'      ON MV.CK_SYS_CD = ADVPROD.CK_SYS_CD')
        state.sql_parts.append(f'      AND MV.CK_CMP_CD = ADVPROD.CK_CMP_CD')
        state.sql_parts.append(f'      AND MV.TCH_POL_ID = ADVPROD.TCH_POL_ID')
        state.sql_parts.append(f'    INNER JOIN {state.schema}.LH_POL_TOTALS TEMPPOLTOTALS')
        state.sql_parts.append(f'      ON MV.CK_SYS_CD = TEMPPOLTOTALS.CK_SYS_CD')
        state.sql_parts.append(f'      AND MV.CK_CMP_CD = TEMPPOLTOTALS.CK_CMP_CD')
        state.sql_parts.append(f'      AND MV.TCH_POL_ID = TEMPPOLTOTALS.TCH_POL_ID)')


def build_step_007(state: BuildState) -> None:
    if state.disp_monthly_deduction:
        state.sql_parts.append(f', MONTHLY_DED AS (')
        state.sql_parts.append(f'  SELECT MV.CK_SYS_CD, MV.CK_CMP_CD, MV.TCH_POL_ID')
        state.sql_parts.append(f'    , (COALESCE(MV.CINS_AMT, 0) + COALESCE(MV.OTH_PRM_AMT, 0) + COALESCE(MV.EXP_CRG_AMT, 0)) MONTHLY_DED_AMT')
        state.sql_parts.append(f'    , MV.MVRY_DT MONTHLY_DED_DT')
        state.sql_parts.append(f'  FROM {state.schema}.LH_POL_MVRY_VAL MV')
        state.sql_parts.append(f'  WHERE MV.MVRY_DT = (')
        state.sql_parts.append(f'    SELECT MAX(MV2.MVRY_DT) FROM {state.schema}.LH_POL_MVRY_VAL MV2')
        state.sql_parts.append(f'    WHERE MV2.CK_SYS_CD = MV.CK_SYS_CD')
        state.sql_parts.append(f'      AND MV2.CK_CMP_CD = MV.CK_CMP_CD')
        state.sql_parts.append(f'      AND MV2.TCH_POL_ID = MV.TCH_POL_ID))')
    if state.needs_interpolation:
        state.sql_parts.append(f', INTERPOLATION_MONTHS AS (')
        state.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID')
        state.sql_parts.append(f'    , REAL(12 - MONTHS_BETWEEN(BASPOL.NXT_MVRY_PRC_DT, BASPOL.LST_ANV_DT)) MONTHS_TO_NEXT_ANN')
        state.sql_parts.append(f'    , REAL(MONTHS_BETWEEN(BASPOL.NXT_MVRY_PRC_DT, BASPOL.LST_ANV_DT)) MONTHS_YTD')
        state.sql_parts.append(f'  FROM {state.schema}.LH_BAS_POL BASPOL)')
    if state.needs_iswl_gcv:
        state.sql_parts.append(f', ISWL_INTERPOLATED_GCV AS (')
        state.sql_parts.append(f'  SELECT COVSUMMARY.CK_SYS_CD, COVSUMMARY.CK_CMP_CD, COVSUMMARY.TCH_POL_ID')
        state.sql_parts.append(f'    , ROUND((INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN * COVSUMMARY.TOTAL_CV1')
        state.sql_parts.append(f'            + INTERPOLATION_MONTHS.MONTHS_YTD * COVSUMMARY.TOTAL_CV2)/12, 2) ISWL_GCV')
        state.sql_parts.append(f'  FROM COVSUMMARY')
        state.sql_parts.append(f'    INNER JOIN INTERPOLATION_MONTHS')
        state.sql_parts.append(f'      ON COVSUMMARY.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD')
        state.sql_parts.append(f'      AND COVSUMMARY.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD')
        state.sql_parts.append(f'      AND COVSUMMARY.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID)')
    if state.disp_account_value:
        state.sql_parts.append(f', TRAD_CV AS (')
        state.sql_parts.append(f'  SELECT COVERAGE1.CK_SYS_CD, COVERAGE1.CK_CMP_CD, COVERAGE1.TCH_POL_ID')
        state.sql_parts.append(f'    , (CASE WHEN COVERAGE1.LOW_DUR_1_CSV_AMT IS NULL THEN 0')
        state.sql_parts.append(f'            ELSE COVERAGE1.LOW_DUR_1_CSV_AMT END)')
        state.sql_parts.append(f'      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN')
        state.sql_parts.append(f'      + (CASE WHEN COVERAGE1.LOW_DUR_2_CSV_AMT IS NULL THEN 0')
        state.sql_parts.append(f'              ELSE COVERAGE1.LOW_DUR_2_CSV_AMT END)')
        state.sql_parts.append(f'      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_YTD  INTERP_CV')
        state.sql_parts.append(f'    , (CASE WHEN COVERAGE1.LOW_DUR_NSP_AMT IS NULL THEN 0')
        state.sql_parts.append(f'            ELSE COVERAGE1.LOW_DUR_NSP_AMT END)')
        state.sql_parts.append(f'      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN')
        state.sql_parts.append(f'      + (CASE WHEN COVERAGE1.LOW_DUR_1_NSP_AMT IS NULL THEN 0')
        state.sql_parts.append(f'              ELSE COVERAGE1.LOW_DUR_1_NSP_AMT END)')
        state.sql_parts.append(f'      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_YTD  INTERP_NSP')
        state.sql_parts.append(f'  FROM COVERAGE1')
        state.sql_parts.append(f'    INNER JOIN INTERPOLATION_MONTHS')
        state.sql_parts.append(f'      ON COVERAGE1.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD')
        state.sql_parts.append(f'      AND COVERAGE1.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD')
        state.sql_parts.append(f'      AND COVERAGE1.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID)')
    if state.adv_glp_neg or state.disp_glp or state.has_glp_range:
        state.sql_parts.append(f', GLP AS (')
        state.sql_parts.append(f'  SELECT DISTINCT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,')
        state.sql_parts.append(f'    TEMPGLP.GDL_PRM_AMT GLP_VALUE')
        state.sql_parts.append(f'  FROM {state.schema}.LH_COV_INS_GDL_PRM TEMPGLP')
        state.sql_parts.append(f'  WHERE TEMPGLP.COV_PHA_NBR = 1')
        state.sql_parts.append(f"    AND TEMPGLP.PRM_RT_TYP_CD = 'A')")
    if state.disp_gsp or state.has_gsp_range:
        state.sql_parts.append(f', GSP AS (')
        state.sql_parts.append(f'  SELECT DISTINCT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,')
        state.sql_parts.append(f'    TEMPGSP.GDL_PRM_AMT GSP_VALUE')
        state.sql_parts.append(f'  FROM {state.schema}.LH_COV_INS_GDL_PRM TEMPGSP')
        state.sql_parts.append(f'  WHERE TEMPGSP.COV_PHA_NBR = 1')
        state.sql_parts.append(f"    AND TEMPGSP.PRM_RT_TYP_CD = 'S')")
    if state.disp_orig_face_rpu:
        state.sql_parts.append(f', CHANGE_TYPE9 AS (')
        state.sql_parts.append(f'  SELECT TMN.CK_SYS_CD, TMN.CK_CMP_CD, TMN.TCH_POL_ID')
        state.sql_parts.append(f'    , SUM(TMN.OGN_COV_UNT_QTY) TOTALORIGUNITS')
        state.sql_parts.append(f'  FROM {state.schema}.LH_COV_TMN TMN')
        state.sql_parts.append(f'    INNER JOIN {state.schema}.LH_NT_COV_CHG COVCHG')
        state.sql_parts.append(f'      ON COVCHG.CK_SYS_CD = TMN.CK_SYS_CD')
        state.sql_parts.append(f'      AND COVCHG.CK_CMP_CD = TMN.CK_CMP_CD')
        state.sql_parts.append(f'      AND COVCHG.TCH_POL_ID = TMN.TCH_POL_ID')
        state.sql_parts.append(f'      AND COVCHG.COV_PHA_NBR = TMN.COV_PHA_NBR')
        state.sql_parts.append(f"      AND COVCHG.CHG_TYP_CD = '9'")
        state.sql_parts.append(f'  GROUP BY TMN.CK_SYS_CD, TMN.CK_CMP_CD, TMN.TCH_POL_ID)')
    if state.disp_insured1_info:
        state.sql_parts.append(f', INSURED1_INFO AS (')
        state.sql_parts.append(f'  SELECT T1.CK_SYS_CD, T1.CK_CMP_CD, T1.TCH_POL_ID')
        state.sql_parts.append(f'    , T2.CK_FST_NM FNAME')
        state.sql_parts.append(f'    , T2.CK_LST_NM LNAME')
        state.sql_parts.append(f'    , T1.BIR_DT BIRTHDT')
        state.sql_parts.append(f'  FROM {state.schema}.LH_CTT_CLIENT T1')
        state.sql_parts.append(f'    INNER JOIN {state.schema}.VH_POL_HAS_LOC_CLT T2')
        state.sql_parts.append(f'      ON T1.PRS_SEQ_NBR = T2.PRS_SEQ_NBR')
        state.sql_parts.append(f'      AND T1.PRS_CD = T2.PRS_CD')
        state.sql_parts.append(f'      AND T1.TCH_POL_ID = T2.TCH_POL_ID')
        state.sql_parts.append(f'      AND T1.CK_SYS_CD = T2.CK_SYS_CD')
        state.sql_parts.append(f'      AND T1.CK_CMP_CD = T2.CK_CMP_CD')
        state.sql_parts.append(f"  WHERE T1.PRS_CD = '00')")
    if state.has_fund_values:
        state.sql_parts.append(f', FUND_VALUES AS (')
        state.sql_parts.append(f'  SELECT CK_CMP_CD, CK_SYS_CD, TCH_POL_ID, FND_ID_CD,')
        state.sql_parts.append(f'    SUM(CSV_AMT) FUNDAMT')
        state.sql_parts.append(f'  FROM {state.schema}.LH_POL_FND_VAL_TOT')
        state.sql_parts.append(f"  WHERE MVRY_DT = '9999-12-31'")
        state.sql_parts.append(f'  GROUP BY CK_CMP_CD, CK_SYS_CD, TCH_POL_ID, FND_ID_CD)')


def build_step_008(state: BuildState) -> None:
    if state.adv_prem_alloc:
        state.fund_items = [item.text().split(' - ')[0].strip() for item in state.at.list_prem_alloc.selectedItems()]
        if state.fund_items:
            state.parts = []
            for state.fid in state.fund_items:
                state.parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID FROM {state.schema}.LH_FND_ALC WHERE FND_ID_CD = '{esc(state.fid)}' AND FND_ALC_PCT > 0 AND FND_ALC_TYP_CD = 'P'")
            state.sql_parts.append(f', ALLOCATION_FUNDS AS (')
            state.sql_parts.append('\n  INTERSECT\n'.join(state.parts))
            state.sql_parts.append(f')')
    state.sql_parts.append('')
    state.sql_parts.append('SELECT DISTINCT')
    state.sql_parts.append('  CURRENT_DATE RunDate')
    state.sql_parts.append('  , POLICY1.CK_POLICY_NBR PolicyNumber')
    if state.has_person_info:
        state.sql_parts.append('  , PERSONINFO.CK_FST_NM PersonFirstName')
        state.sql_parts.append('  , PERSONINFO.MDL_INT_NM PersonMiddleInitial')
        state.sql_parts.append('  , PERSONINFO.CK_LST_NM PersonLastName')
    if state.coverage_level:
        state.sql_parts.append('  , RESULTCOV.COV_PHA_NBR CovPhase')
    state.sql_parts.append('  , POLICY1.CK_CMP_CD CompanyCode')
    state.sql_parts.append('  , POLICY1.PRM_PAY_STA_REA_CD StatusCode')
    state.sql_parts.append('  , POLICY1.SUS_CD SuspenseCode')
    state.sql_parts.append('  , SUBSTR(POLICY1.SVC_AGC_NBR, 1, 1) AgentCode')
    state.sql_parts.append("  , CASE WHEN POLICY1.POL_ISS_ST_CD = '01' THEN 'AL'")
    for state.code, state.st in _ISS_STATE_MAP:
        state.sql_parts.append(f"    WHEN POLICY1.POL_ISS_ST_CD = '{state.code}' THEN '{state.st}'")
    state.sql_parts.append('    ELSE POLICY1.POL_ISS_ST_CD END IssueState')
    state.sql_parts.append(f'  , {state.result_cov_alias}.PLN_DES_SER_CD Plancode')
    state.sql_parts.append(f'  , {state.result_cov_alias}.POL_FRM_NBR FormNumber')
    state.sql_parts.append(f"  , VARCHAR_FORMAT({state.result_cov_alias}.ISSUE_DT, 'MM/DD/YYYY') IssueDt")
    state.sql_parts.append(f'  , {state.result_cov_alias}.INS_ISS_AGE IssueAge')
    state.sql_parts.append('  , USERGEN.FUZGREIN_IND RGA_Ind')
    state.duration_expr = "TRUNCATE(MONTHS_BETWEEN('" + today_str() + f"', {state.result_cov_alias}.ISSUE_DT) / 12, 0)"
    if state.has_current_age:
        state.sql_parts.append(f'  , INTEGER({state.result_cov_alias}.INS_ISS_AGE + {state.duration_expr}) CurrentAge')
    if state.has_val_age:
        state.val_duration_expr = f'TRUNCATE(MONTHS_BETWEEN({_valuation_date_sql(state.schema)}, {state.result_cov_alias}.ISSUE_DT) / 12, 0)'
        state.sql_parts.append(f'  , INTEGER({state.result_cov_alias}.INS_ISS_AGE + {state.val_duration_expr}) ValAttainedAge')
    if state.has_pol_year:
        state.sql_parts.append(f'  , INTEGER({state.duration_expr} + 1) PolicyYear')
    if state.has_issue_month:
        state.sql_parts.append(f'  , MONTH({state.result_cov_alias}.ISSUE_DT) IssueMonth')
    if state.has_issue_day:
        state.sql_parts.append(f'  , DAY({state.result_cov_alias}.ISSUE_DT) IssueDay')
    if state.has_paid_to:
        state.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.PRM_PAID_TO_DT, 'MM/DD/YYYY') PaidToDate")
    if state.has_gpe_date:
        state.sql_parts.append("  , VARCHAR_FORMAT(GRACE_TABLE.GRA_PER_EXP_DT, 'MM/DD/YYYY') GPEDate")
    if state.has_app_date:
        state.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.APP_WRT_DT, 'MM/DD/YYYY') AppDate")
    if state.has_billing_prem:
        state.sql_parts.append('  , POLICY1.POL_PRM_AMT BillingPrem')
    if state.disp_paid_to:
        state.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.PRM_PAID_TO_DT, 'MM/DD/YYYY') PaidToDate_Disp")
    if state.disp_bill_to:
        state.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.PRM_BILL_TO_DT, 'MM/DD/YYYY') BillToDate")
    if state.disp_duration or state.disp_attained_age:
        state.disp_val_duration_expr = f'TRUNCATE(MONTHS_BETWEEN({_valuation_date_sql(state.schema)}, {state.result_cov_alias}.ISSUE_DT) / 12, 0)'
    if state.disp_duration:
        state.sql_parts.append(f'  , INTEGER({state.disp_val_duration_expr}) ValDuration')
    if state.disp_attained_age:
        state.sql_parts.append(f'  , INTEGER({state.result_cov_alias}.INS_ISS_AGE + {state.disp_val_duration_expr}) ValAttainedAge_Disp')
    if state.disp_last_acct:
        state.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.LST_ACT_TRS_DT, 'MM/DD/YYYY') LastAcctDate")
    if state.disp_last_fin:
        state.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.LST_FIN_DT, 'MM/DD/YYYY') LastFinDate")
    if state.has_term_fin:
        state.sql_parts.append(f"  , VARCHAR_FORMAT({state.term_fin_date}, 'MM/DD/YYYY') TERM_LAST_FIN_DT")
    if state.has_term_both:
        state.sql_parts.append(f"  , VARCHAR_FORMAT({state.term_both_date}, 'MM/DD/YYYY') TERM_DATE_BOTH")
        state.sql_parts.append("  , CASE WHEN TDB.TERM_ENTRY_DT IS NOT NULL THEN 'Transaction (69)'")
        state.sql_parts.append("      ELSE 'Last Financial (01)' END TERM_DATE_SOURCE")
    if state.disp_bill_prem:
        state.sql_parts.append('  , IFNULL(POLICY1.POL_PRM_AMT, 0) BillPrem')


def build_step_009(state: BuildState) -> None:
    if state.disp_bill_mode:
        state.sql_parts.append('  , (CASE BILLMODE_POOL.PMT_FQY_PER')
        state.sql_parts.append('      WHEN 1 THEN (CASE BILLMODE_POOL.NSD_MD_CD')
        state.sql_parts.append("        WHEN '2' THEN 'BiWeekly'")
        state.sql_parts.append("        WHEN 'S' THEN 'SemiMonthly'")
        state.sql_parts.append("        WHEN '9' THEN '9thly'")
        state.sql_parts.append("        WHEN 'A' THEN '10thly'")
        state.sql_parts.append("        ELSE 'Monthly' END)")
        state.sql_parts.append("      WHEN 3 THEN 'Quarterly'")
        state.sql_parts.append("      WHEN 6 THEN 'SemiAnnually'")
        state.sql_parts.append("      WHEN 12 THEN 'Annually'")
        state.sql_parts.append("      ELSE ' ' END) BillMode")
    if state.disp_bill_form:
        state.sql_parts.append('  , POLICY1.BIL_FRM_CD BillForm')
    if state.disp_mkt_org:
        state.sql_parts.append('  , SUBSTR(POLICY1.SVC_AGC_NBR, 1, 1) MarkOrg')
    if state.disp_reinsured:
        state.sql_parts.append('  , POLICY1.REINSURED_CD ReinsuredCode')
    if state.disp_last_entry or state.has_term_fin or state.has_term_both:
        state.sql_parts.append('  , POLICY1.LST_ETR_CD LastEntryCode')
        state.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.LST_FIN_DT, 'MM/DD/YYYY') LastFinDate_Entry")
    if state.disp_orig_entry:
        state.sql_parts.append('  , POLICY1.OGN_ETR_CD OrigEntryCode')
    if state.disp_spec_amt or state.multi_base_covs:
        state.sql_parts.append('  , COVSUMMARY.TOTAL_SA TotalFace')
        state.sql_parts.append('  , COVSUMMARY.TOTAL_ORIGINAL_SA TotalOriginalFace')
    if state.adv_prem_wd_gt_face:
        state.sql_parts.append('  , (POLICY_TOTALS.TOT_REG_PRM_AMT + POLICY_TOTALS.TOT_ADD_PRM_AMT) PremTD')
        state.sql_parts.append('  , POLICY_TOTALS.TOT_WTD_AMT AccumWD')
        state.sql_parts.append('  , PREMWD_FACE.TOTAL_FACE TotalFace')
        state.sql_parts.append('  , ROUND(REAL(PREMWD_FACE.TOTAL_FACE) + COALESCE(REAL(MVVAL.OPTDB), 0), 2) DeathBenefit')
        if not state.disp_db_option:
            state.sql_parts.append('  , NONTRAD.DTH_BNF_PLN_OPT_CD DBOpt')
    if state.disp_tch_pol_id:
        state.sql_parts.append('  , POLICY1.TCH_POL_ID TCH_POL_ID')
    if state.disp_mod_indicator or state.is_mdo:
        state.sql_parts.append('  , SUBSTR(POLICY1.USR_RES_CD, 1, 1) MDO')
    if state.disp_prod_line:
        state.sql_parts.append(f'  , {state.result_cov_alias}.PRD_LIN_TYP_CD')
    if state.disp_sex_02:
        state.sql_parts.append(f'  , {state.result_cov_alias}.INS_SEX_CD SEX_CD')
    if state.disp_subseries:
        state.sql_parts.append(f'  , {state.result_cov_alias}.LIF_PLN_SUB_SRE_CD SUBSERIES')
    if state.disp_mec_status:
        state.sql_parts.append('  , (CASE')
        state.sql_parts.append("      WHEN POLICY1.MEC_STATUS_CD = '0' THEN '0 - NO'")
        state.sql_parts.append("      WHEN POLICY1.MEC_STATUS_CD = '1' THEN '1 - YES'")
        state.sql_parts.append("      WHEN POLICY1.MEC_STATUS_CD = '2' THEN '2 - NO'")
        state.sql_parts.append('      ELSE POLICY1.MEC_STATUS_CD')
        state.sql_parts.append('      END) MEC_INDICATOR_01')
    if state.disp_app_date:
        state.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.APP_WRT_DT, 'MM/DD/YYYY') AppDt")
    if state.disp_next_notif:
        state.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.NXT_SCH_NOT_DT, 'MM/DD/YYYY') NextNotifyDt")
    if state.disp_next_year_end:
        state.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.NXT_YR_END_PRC_DT, 'MM/DD/YYYY') NextYearEndDt")
    if state.disp_next_stmt:
        state.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.NXT_SCH_STT_DT, 'MM/DD/YYYY') NextStatementDt")
    if state.disp_next_change:
        state.sql_parts.append(f'  , {state.result_cov_alias}.NXT_CHG_TYP_CD NXT_CHG_TYP_CD')
        state.sql_parts.append(f"  , VARCHAR_FORMAT({state.result_cov_alias}.NXT_CHG_DT, 'MM/DD/YYYY') NXT_CHG_DT")
    if state.disp_init_term:
        state.sql_parts.append(f'  , {state.result_cov_alias}.INT_RNL_PER')
        state.sql_parts.append(f'  , {state.result_cov_alias}.SBQ_RNL_STR_DUR')
        state.sql_parts.append(f'  , {state.result_cov_alias}.SBQ_RNL_PER')
    if state.disp_commission_target:
        state.sql_parts.append('  , COMMTARGET.TAR_PRM_AMT CTP')
    if state.p2t.chk_participating.isChecked() or (state.wl_tab is not None and state.wl_tab.chk_participation_type.isChecked()):
        state.sql_parts.append('  , COVERAGE1.DIV_PTP_TYP_CD ParticipationCode')
        state.sql_parts.append(f'  , {_participation_description()} Participation')
    if state.wl_tab is not None and state.wl_tab.chk_participation_type.isChecked():
        state.cases = [f"WHEN TRIM(COVERAGE1.DIV_PTP_TYP_CD) = '{esc(code)}' THEN '{esc(description)}'" for code, description in PARTICIPATION_TYPE_DESCRIPTIONS.items()]
        state.sql_parts.append('  , (CASE ' + ' '.join(state.cases) + " ELSE 'Unknown' END) ParticipationType")
    if state.disp_monthly_mtp:
        state.sql_parts.append('  , MTP.TAR_PRM_AMT MonthlyMTP')
    if state.disp_accum_mtp:
        state.sql_parts.append('  , ACCUMMTP.TAR_PRM_AMT ACCUMMTP')
    if state.disp_accum_glp:
        state.sql_parts.append('  , ACCUMGLP.TAR_PRM_AMT ACCUMGLP')
    if state.disp_nsp:
        state.sql_parts.append('  , NSPTARGET.TAR_PRM_AMT NSP')
    if state.disp_shadow_av:
        state.sql_parts.append('  , SHADOWAV.TAR_PRM_AMT ShadowAV')
    if state.disp_db_option:
        state.sql_parts.append('  , NONTRAD.DTH_BNF_PLN_OPT_CD DBOpt')
