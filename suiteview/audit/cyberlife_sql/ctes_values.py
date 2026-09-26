"""CyberLife SQL ctes values section builders."""
from __future__ import annotations

from suiteview.audit.constants import PARTICIPATION_TYPE_DESCRIPTIONS
from suiteview.audit.cyberlife_sql.ctes import (
    _valuation_date_sql,
)
from suiteview.audit.cyberlife_sql.helpers import (
    _ISS_STATE_MAP,
    participation_description,
)
from suiteview.audit.cyberlife_sql.state import QueryContext, SqlParts
from suiteview.audit.sql_helpers import (
    esc,
)


def add_policy_year_and_grace_ctes(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.has_change_seq:
        parts.sql_parts.append(f', CHANGE_SEGMENT AS (')
        parts.sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, '9' AS CHG_TYP_CD FROM {ctx.schema}.LH_COV_TMN")
        parts.sql_parts.append(f'  UNION')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, CHG_TYP_CD FROM {ctx.schema}.LH_NT_COV_CHG')
        parts.sql_parts.append(f'  UNION')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, CHG_TYP_CD FROM {ctx.schema}.LH_NT_COV_CHG_SCH')
        parts.sql_parts.append(f'  UNION')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, CHG_TYP_CD FROM {ctx.schema}.LH_SPM_BNF_CHG_SCH)')
    if ctx.disp_bill_mode:
        parts.sql_parts.append(f', BILLMODE_POOL AS')
        parts.sql_parts.append(f'  (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,')
        parts.sql_parts.append(f'   PMT_FQY_PER, NSD_MD_CD')
        parts.sql_parts.append(f'   FROM {ctx.schema}.LH_BAS_POL)')
    if ctx.needs_covsummary:
        ctx._apb_cond = " OR TEMPCOVALL.PLN_DES_SER_CD = '1U144A00'" if ctx.adv_apb_rider else ''
        parts.sql_parts.append(f', ALL_BASE_COVS AS (')
        parts.sql_parts.append(f'  SELECT TEMPCOV1.CK_SYS_CD, TEMPCOV1.TCH_POL_ID, TEMPCOV1.CK_CMP_CD')
        parts.sql_parts.append(f'    , TEMPCOVALL.COV_PHA_NBR')
        parts.sql_parts.append(f'    , ROUND(REAL(TEMPCOVALL.COV_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT), 2) SPECAMT')
        parts.sql_parts.append(f'    , ROUND(REAL(TEMPCOVALL.OGN_SPC_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT), 2) ORIGSPECAMT')
        if ctx.needs_iswl_gcv:
            parts.sql_parts.append(f'    , ROUND(REAL(TEMPCOVALL.LOW_DUR_1_CSV_AMT) * REAL(TEMPCOVALL.COV_UNT_QTY), 2) CV1')
            parts.sql_parts.append(f'    , ROUND(REAL(TEMPCOVALL.LOW_DUR_2_CSV_AMT) * REAL(TEMPCOVALL.COV_UNT_QTY), 2) CV2')
        parts.sql_parts.append(f'  FROM {ctx.schema}.LH_COV_PHA TEMPCOV1')
        parts.sql_parts.append(f'    INNER JOIN {ctx.schema}.LH_COV_PHA TEMPCOVALL')
        parts.sql_parts.append(f'      ON TEMPCOV1.COV_PHA_NBR = 1')
        parts.sql_parts.append(f'      AND TEMPCOV1.CK_SYS_CD = TEMPCOVALL.CK_SYS_CD')
        parts.sql_parts.append(f'      AND TEMPCOV1.CK_CMP_CD = TEMPCOVALL.CK_CMP_CD')
        parts.sql_parts.append(f'      AND TEMPCOV1.TCH_POL_ID = TEMPCOVALL.TCH_POL_ID')
        parts.sql_parts.append(f'      AND (TEMPCOVALL.PLN_DES_SER_CD = TEMPCOV1.PLN_DES_SER_CD{ctx._apb_cond}))')
        parts.sql_parts.append(f', COVSUMMARY AS (')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID')
        parts.sql_parts.append(f'    , SUM(ALL_BASE_COVS.SPECAMT) TOTAL_SA')
        parts.sql_parts.append(f'    , SUM(ALL_BASE_COVS.ORIGSPECAMT) TOTAL_ORIGINAL_SA')
        if ctx.multi_base_covs:
            parts.sql_parts.append(f'    , COUNT(ALL_BASE_COVS.COV_PHA_NBR) BASECOVCOUNT')
        if ctx.needs_iswl_gcv:
            parts.sql_parts.append(f'    , SUM(ALL_BASE_COVS.CV1) TOTAL_CV1')
            parts.sql_parts.append(f'    , SUM(ALL_BASE_COVS.CV2) TOTAL_CV2')
        parts.sql_parts.append(f'  FROM ALL_BASE_COVS')
        parts.sql_parts.append(f'  GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)')
    if ctx.needs_premwd_face:
        parts.sql_parts.append(f', PREMWD_FACE AS (')
        parts.sql_parts.append(f'  SELECT TEMPCOV1.CK_SYS_CD, TEMPCOV1.CK_CMP_CD, TEMPCOV1.TCH_POL_ID')
        parts.sql_parts.append(f'    , SUM(ROUND(REAL(TEMPCOVALL.COV_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT), 2)) TOTAL_FACE')
        parts.sql_parts.append(f'  FROM {ctx.schema}.LH_COV_PHA TEMPCOV1')
        parts.sql_parts.append(f'    INNER JOIN {ctx.schema}.LH_COV_PHA TEMPCOVALL')
        parts.sql_parts.append(f'      ON TEMPCOV1.COV_PHA_NBR = 1')
        parts.sql_parts.append(f'      AND TEMPCOV1.CK_SYS_CD = TEMPCOVALL.CK_SYS_CD')
        parts.sql_parts.append(f'      AND TEMPCOV1.CK_CMP_CD = TEMPCOVALL.CK_CMP_CD')
        parts.sql_parts.append(f'      AND TEMPCOV1.TCH_POL_ID = TEMPCOVALL.TCH_POL_ID')
        parts.sql_parts.append(f'      AND (TEMPCOVALL.PLN_DES_SER_CD = TEMPCOV1.PLN_DES_SER_CD')
        parts.sql_parts.append(f"           OR TEMPCOVALL.PLN_DES_SER_CD = '1U144A00')")
        parts.sql_parts.append(f"  WHERE (TEMPCOVALL.NXT_CHG_TYP_CD <> '0'")
        parts.sql_parts.append(f'         OR (TEMPCOVALL.NXT_CHG_DT IS NOT NULL')
        parts.sql_parts.append(f'             AND TEMPCOVALL.NXT_CHG_DT > CURRENT DATE))')
        parts.sql_parts.append(f'  GROUP BY TEMPCOV1.CK_SYS_CD, TEMPCOV1.CK_CMP_CD, TEMPCOV1.TCH_POL_ID)')
    if ctx.needs_mvval:
        parts.sql_parts.append(f', LASTMV AS (')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, MAX(MVRY_DT) LASTMVDT')
        parts.sql_parts.append(f'  FROM {ctx.schema}.LH_POL_MVRY_VAL')
        parts.sql_parts.append(f'  GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)')
        parts.sql_parts.append(f', MVVAL AS (')
        parts.sql_parts.append(f'  SELECT MV.CK_SYS_CD, MV.CK_CMP_CD, MV.TCH_POL_ID, MV.CSV_AMT')
        parts.sql_parts.append(f'    , LASTMV.LASTMVDT')
        parts.sql_parts.append(f'    , ROUND(REAL(MV.CSV_AMT) * REAL(ADVPROD.CDR_PCT)/100, 2) DB')
        parts.sql_parts.append(f'    , CASE ADVPROD.DTH_BNF_PLN_OPT_CD')
        parts.sql_parts.append(f"        WHEN '1' THEN 0")
        parts.sql_parts.append(f"        WHEN '2' THEN REAL(MV.CSV_AMT)")
        parts.sql_parts.append(f"        WHEN '3' THEN (TEMPPOLTOTALS.TOT_REG_PRM_AMT + TEMPPOLTOTALS.TOT_ADD_PRM_AMT)")
        parts.sql_parts.append(f'        ELSE 0 END OPTDB')
        parts.sql_parts.append(f'    , (TEMPPOLTOTALS.TOT_REG_PRM_AMT + TEMPPOLTOTALS.TOT_ADD_PRM_AMT) TOTALPREM')
        parts.sql_parts.append(f'  FROM {ctx.schema}.LH_POL_MVRY_VAL MV')
        parts.sql_parts.append(f'    INNER JOIN LASTMV ON MV.CK_SYS_CD = LASTMV.CK_SYS_CD')
        parts.sql_parts.append(f'      AND MV.CK_CMP_CD = LASTMV.CK_CMP_CD')
        parts.sql_parts.append(f'      AND MV.TCH_POL_ID = LASTMV.TCH_POL_ID')
        parts.sql_parts.append(f'      AND MV.MVRY_DT = LASTMV.LASTMVDT')
        parts.sql_parts.append(f'    INNER JOIN {ctx.schema}.LH_NON_TRD_POL ADVPROD')
        parts.sql_parts.append(f'      ON MV.CK_SYS_CD = ADVPROD.CK_SYS_CD')
        parts.sql_parts.append(f'      AND MV.CK_CMP_CD = ADVPROD.CK_CMP_CD')
        parts.sql_parts.append(f'      AND MV.TCH_POL_ID = ADVPROD.TCH_POL_ID')
        parts.sql_parts.append(f'    INNER JOIN {ctx.schema}.LH_POL_TOTALS TEMPPOLTOTALS')
        parts.sql_parts.append(f'      ON MV.CK_SYS_CD = TEMPPOLTOTALS.CK_SYS_CD')
        parts.sql_parts.append(f'      AND MV.CK_CMP_CD = TEMPPOLTOTALS.CK_CMP_CD')
        parts.sql_parts.append(f'      AND MV.TCH_POL_ID = TEMPPOLTOTALS.TCH_POL_ID)')


def add_target_and_value_ctes(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.disp_monthly_deduction:
        parts.sql_parts.append(f', MONTHLY_DED AS (')
        parts.sql_parts.append(f'  SELECT MV.CK_SYS_CD, MV.CK_CMP_CD, MV.TCH_POL_ID')
        parts.sql_parts.append(f'    , (COALESCE(MV.CINS_AMT, 0) + COALESCE(MV.OTH_PRM_AMT, 0) + COALESCE(MV.EXP_CRG_AMT, 0)) MONTHLY_DED_AMT')
        parts.sql_parts.append(f'    , MV.MVRY_DT MONTHLY_DED_DT')
        parts.sql_parts.append(f'  FROM {ctx.schema}.LH_POL_MVRY_VAL MV')
        parts.sql_parts.append(f'  WHERE MV.MVRY_DT = (')
        parts.sql_parts.append(f'    SELECT MAX(MV2.MVRY_DT) FROM {ctx.schema}.LH_POL_MVRY_VAL MV2')
        parts.sql_parts.append(f'    WHERE MV2.CK_SYS_CD = MV.CK_SYS_CD')
        parts.sql_parts.append(f'      AND MV2.CK_CMP_CD = MV.CK_CMP_CD')
        parts.sql_parts.append(f'      AND MV2.TCH_POL_ID = MV.TCH_POL_ID))')
    if ctx.needs_interpolation:
        parts.sql_parts.append(f', INTERPOLATION_MONTHS AS (')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID')
        parts.sql_parts.append(f'    , REAL(12 - MONTHS_BETWEEN(BASPOL.NXT_MVRY_PRC_DT, BASPOL.LST_ANV_DT)) MONTHS_TO_NEXT_ANN')
        parts.sql_parts.append(f'    , REAL(MONTHS_BETWEEN(BASPOL.NXT_MVRY_PRC_DT, BASPOL.LST_ANV_DT)) MONTHS_YTD')
        parts.sql_parts.append(f'  FROM {ctx.schema}.LH_BAS_POL BASPOL)')
    if ctx.needs_iswl_gcv:
        parts.sql_parts.append(f', ISWL_INTERPOLATED_GCV AS (')
        parts.sql_parts.append(f'  SELECT COVSUMMARY.CK_SYS_CD, COVSUMMARY.CK_CMP_CD, COVSUMMARY.TCH_POL_ID')
        parts.sql_parts.append(f'    , ROUND((INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN * COVSUMMARY.TOTAL_CV1')
        parts.sql_parts.append(f'            + INTERPOLATION_MONTHS.MONTHS_YTD * COVSUMMARY.TOTAL_CV2)/12, 2) ISWL_GCV')
        parts.sql_parts.append(f'  FROM COVSUMMARY')
        parts.sql_parts.append(f'    INNER JOIN INTERPOLATION_MONTHS')
        parts.sql_parts.append(f'      ON COVSUMMARY.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD')
        parts.sql_parts.append(f'      AND COVSUMMARY.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD')
        parts.sql_parts.append(f'      AND COVSUMMARY.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID)')
    if ctx.disp_account_value:
        parts.sql_parts.append(f', TRAD_CV AS (')
        parts.sql_parts.append(f'  SELECT COVERAGE1.CK_SYS_CD, COVERAGE1.CK_CMP_CD, COVERAGE1.TCH_POL_ID')
        parts.sql_parts.append(f'    , (CASE WHEN COVERAGE1.LOW_DUR_1_CSV_AMT IS NULL THEN 0')
        parts.sql_parts.append(f'            ELSE COVERAGE1.LOW_DUR_1_CSV_AMT END)')
        parts.sql_parts.append(f'      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN')
        parts.sql_parts.append(f'      + (CASE WHEN COVERAGE1.LOW_DUR_2_CSV_AMT IS NULL THEN 0')
        parts.sql_parts.append(f'              ELSE COVERAGE1.LOW_DUR_2_CSV_AMT END)')
        parts.sql_parts.append(f'      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_YTD  INTERP_CV')
        parts.sql_parts.append(f'    , (CASE WHEN COVERAGE1.LOW_DUR_NSP_AMT IS NULL THEN 0')
        parts.sql_parts.append(f'            ELSE COVERAGE1.LOW_DUR_NSP_AMT END)')
        parts.sql_parts.append(f'      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN')
        parts.sql_parts.append(f'      + (CASE WHEN COVERAGE1.LOW_DUR_1_NSP_AMT IS NULL THEN 0')
        parts.sql_parts.append(f'              ELSE COVERAGE1.LOW_DUR_1_NSP_AMT END)')
        parts.sql_parts.append(f'      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_YTD  INTERP_NSP')
        parts.sql_parts.append(f'  FROM COVERAGE1')
        parts.sql_parts.append(f'    INNER JOIN INTERPOLATION_MONTHS')
        parts.sql_parts.append(f'      ON COVERAGE1.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD')
        parts.sql_parts.append(f'      AND COVERAGE1.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD')
        parts.sql_parts.append(f'      AND COVERAGE1.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID)')
    if ctx.adv_glp_neg or ctx.disp_glp or ctx.has_glp_range:
        parts.sql_parts.append(f', GLP AS (')
        parts.sql_parts.append(f'  SELECT DISTINCT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,')
        parts.sql_parts.append(f'    TEMPGLP.GDL_PRM_AMT GLP_VALUE')
        parts.sql_parts.append(f'  FROM {ctx.schema}.LH_COV_INS_GDL_PRM TEMPGLP')
        parts.sql_parts.append(f'  WHERE TEMPGLP.COV_PHA_NBR = 1')
        parts.sql_parts.append(f"    AND TEMPGLP.PRM_RT_TYP_CD = 'A')")
    if ctx.disp_gsp or ctx.has_gsp_range:
        parts.sql_parts.append(f', GSP AS (')
        parts.sql_parts.append(f'  SELECT DISTINCT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,')
        parts.sql_parts.append(f'    TEMPGSP.GDL_PRM_AMT GSP_VALUE')
        parts.sql_parts.append(f'  FROM {ctx.schema}.LH_COV_INS_GDL_PRM TEMPGSP')
        parts.sql_parts.append(f'  WHERE TEMPGSP.COV_PHA_NBR = 1')
        parts.sql_parts.append(f"    AND TEMPGSP.PRM_RT_TYP_CD = 'S')")
    if ctx.disp_orig_face_rpu:
        parts.sql_parts.append(f', CHANGE_TYPE9 AS (')
        parts.sql_parts.append(f'  SELECT TMN.CK_SYS_CD, TMN.CK_CMP_CD, TMN.TCH_POL_ID')
        parts.sql_parts.append(f'    , SUM(TMN.OGN_COV_UNT_QTY) TOTALORIGUNITS')
        parts.sql_parts.append(f'  FROM {ctx.schema}.LH_COV_TMN TMN')
        parts.sql_parts.append(f'    INNER JOIN {ctx.schema}.LH_NT_COV_CHG COVCHG')
        parts.sql_parts.append(f'      ON COVCHG.CK_SYS_CD = TMN.CK_SYS_CD')
        parts.sql_parts.append(f'      AND COVCHG.CK_CMP_CD = TMN.CK_CMP_CD')
        parts.sql_parts.append(f'      AND COVCHG.TCH_POL_ID = TMN.TCH_POL_ID')
        parts.sql_parts.append(f'      AND COVCHG.COV_PHA_NBR = TMN.COV_PHA_NBR')
        parts.sql_parts.append(f"      AND COVCHG.CHG_TYP_CD = '9'")
        parts.sql_parts.append(f'  GROUP BY TMN.CK_SYS_CD, TMN.CK_CMP_CD, TMN.TCH_POL_ID)')
    if ctx.disp_insured1_info:
        parts.sql_parts.append(f', INSURED1_INFO AS (')
        parts.sql_parts.append(f'  SELECT T1.CK_SYS_CD, T1.CK_CMP_CD, T1.TCH_POL_ID')
        parts.sql_parts.append(f'    , T2.CK_FST_NM FNAME')
        parts.sql_parts.append(f'    , T2.CK_LST_NM LNAME')
        parts.sql_parts.append(f'    , T1.BIR_DT BIRTHDT')
        parts.sql_parts.append(f'  FROM {ctx.schema}.LH_CTT_CLIENT T1')
        parts.sql_parts.append(f'    INNER JOIN {ctx.schema}.VH_POL_HAS_LOC_CLT T2')
        parts.sql_parts.append(f'      ON T1.PRS_SEQ_NBR = T2.PRS_SEQ_NBR')
        parts.sql_parts.append(f'      AND T1.PRS_CD = T2.PRS_CD')
        parts.sql_parts.append(f'      AND T1.TCH_POL_ID = T2.TCH_POL_ID')
        parts.sql_parts.append(f'      AND T1.CK_SYS_CD = T2.CK_SYS_CD')
        parts.sql_parts.append(f'      AND T1.CK_CMP_CD = T2.CK_CMP_CD')
        parts.sql_parts.append(f"  WHERE T1.PRS_CD = '00')")
    if ctx.has_fund_values:
        parts.sql_parts.append(f', FUND_VALUES AS (')
        parts.sql_parts.append(f'  SELECT CK_CMP_CD, CK_SYS_CD, TCH_POL_ID, FND_ID_CD,')
        parts.sql_parts.append(f'    SUM(CSV_AMT) FUNDAMT')
        parts.sql_parts.append(f'  FROM {ctx.schema}.LH_POL_FND_VAL_TOT')
        parts.sql_parts.append(f"  WHERE MVRY_DT = '9999-12-31'")
        parts.sql_parts.append(f'  GROUP BY CK_CMP_CD, CK_SYS_CD, TCH_POL_ID, FND_ID_CD)')


def add_cash_value_and_account_ctes(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.adv_prem_alloc:
        ctx.fund_items = [item.text().split(' - ')[0].strip() for item in ctx.at.list_prem_alloc.selectedItems()]
        if ctx.fund_items:
            ctx.parts = []
            for ctx.fid in ctx.fund_items:
                ctx.parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID FROM {ctx.schema}.LH_FND_ALC WHERE FND_ID_CD = '{esc(ctx.fid)}' AND FND_ALC_PCT > 0 AND FND_ALC_TYP_CD = 'P'")
            parts.sql_parts.append(f', ALLOCATION_FUNDS AS (')
            parts.sql_parts.append('\n  INTERSECT\n'.join(ctx.parts))
            parts.sql_parts.append(f')')
    parts.sql_parts.append('')
    parts.sql_parts.append('SELECT DISTINCT')
    parts.sql_parts.append('  CURRENT_DATE RunDate')
    parts.sql_parts.append('  , POLICY1.CK_POLICY_NBR PolicyNumber')
    if ctx.has_person_info:
        parts.sql_parts.append('  , PERSONINFO.CK_FST_NM PersonFirstName')
        parts.sql_parts.append('  , PERSONINFO.MDL_INT_NM PersonMiddleInitial')
        parts.sql_parts.append('  , PERSONINFO.CK_LST_NM PersonLastName')
    if ctx.coverage_level:
        parts.sql_parts.append('  , RESULTCOV.COV_PHA_NBR CovPhase')
    parts.sql_parts.append('  , POLICY1.CK_CMP_CD CompanyCode')
    parts.sql_parts.append('  , POLICY1.PRM_PAY_STA_REA_CD StatusCode')
    parts.sql_parts.append('  , POLICY1.SUS_CD SuspenseCode')
    parts.sql_parts.append('  , SUBSTR(POLICY1.SVC_AGC_NBR, 1, 1) AgentCode')
    parts.sql_parts.append("  , CASE WHEN POLICY1.POL_ISS_ST_CD = '01' THEN 'AL'")
    for ctx.code, ctx.st in _ISS_STATE_MAP:
        parts.sql_parts.append(f"    WHEN POLICY1.POL_ISS_ST_CD = '{ctx.code}' THEN '{ctx.st}'")
    parts.sql_parts.append('    ELSE POLICY1.POL_ISS_ST_CD END IssueState')
    parts.sql_parts.append(f'  , {ctx.result_cov_alias}.PLN_DES_SER_CD Plancode')
    parts.sql_parts.append(f'  , {ctx.result_cov_alias}.POL_FRM_NBR FormNumber')
    parts.sql_parts.append(f"  , VARCHAR_FORMAT({ctx.result_cov_alias}.ISSUE_DT, 'MM/DD/YYYY') IssueDt")
    parts.sql_parts.append(f'  , {ctx.result_cov_alias}.INS_ISS_AGE IssueAge')
    parts.sql_parts.append('  , USERGEN.FUZGREIN_IND RGA_Ind')
    ctx.duration_expr = "TRUNCATE(MONTHS_BETWEEN('" + ctx.criteria.as_of_sql + f"', {ctx.result_cov_alias}.ISSUE_DT) / 12, 0)"
    if ctx.has_current_age:
        parts.sql_parts.append(f'  , INTEGER({ctx.result_cov_alias}.INS_ISS_AGE + {ctx.duration_expr}) CurrentAge')
    if ctx.has_val_age:
        ctx.val_duration_expr = f'TRUNCATE(MONTHS_BETWEEN({_valuation_date_sql(ctx.schema)}, {ctx.result_cov_alias}.ISSUE_DT) / 12, 0)'
        parts.sql_parts.append(f'  , INTEGER({ctx.result_cov_alias}.INS_ISS_AGE + {ctx.val_duration_expr}) ValAttainedAge')
    if ctx.has_pol_year:
        parts.sql_parts.append(f'  , INTEGER({ctx.duration_expr} + 1) PolicyYear')
    if ctx.has_issue_month:
        parts.sql_parts.append(f'  , MONTH({ctx.result_cov_alias}.ISSUE_DT) IssueMonth')
    if ctx.has_issue_day:
        parts.sql_parts.append(f'  , DAY({ctx.result_cov_alias}.ISSUE_DT) IssueDay')
    if ctx.has_paid_to:
        parts.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.PRM_PAID_TO_DT, 'MM/DD/YYYY') PaidToDate")
    if ctx.has_gpe_date:
        parts.sql_parts.append("  , VARCHAR_FORMAT(GRACE_TABLE.GRA_PER_EXP_DT, 'MM/DD/YYYY') GPEDate")
    if ctx.has_app_date:
        parts.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.APP_WRT_DT, 'MM/DD/YYYY') AppDate")
    if ctx.has_billing_prem:
        parts.sql_parts.append('  , POLICY1.POL_PRM_AMT BillingPrem')
    if ctx.disp_paid_to:
        parts.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.PRM_PAID_TO_DT, 'MM/DD/YYYY') PaidToDate_Disp")
    if ctx.disp_bill_to:
        parts.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.PRM_BILL_TO_DT, 'MM/DD/YYYY') BillToDate")
    if ctx.disp_duration or ctx.disp_attained_age:
        ctx.disp_val_duration_expr = f'TRUNCATE(MONTHS_BETWEEN({_valuation_date_sql(ctx.schema)}, {ctx.result_cov_alias}.ISSUE_DT) / 12, 0)'
    if ctx.disp_duration:
        parts.sql_parts.append(f'  , INTEGER({ctx.disp_val_duration_expr}) ValDuration')
    if ctx.disp_attained_age:
        parts.sql_parts.append(f'  , INTEGER({ctx.result_cov_alias}.INS_ISS_AGE + {ctx.disp_val_duration_expr}) ValAttainedAge_Disp')
    if ctx.disp_last_acct:
        parts.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.LST_ACT_TRS_DT, 'MM/DD/YYYY') LastAcctDate")
    if ctx.disp_last_fin:
        parts.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.LST_FIN_DT, 'MM/DD/YYYY') LastFinDate")
    if ctx.has_term_fin:
        parts.sql_parts.append(f"  , VARCHAR_FORMAT({ctx.term_fin_date}, 'MM/DD/YYYY') TERM_LAST_FIN_DT")
    if ctx.has_term_both:
        parts.sql_parts.append(f"  , VARCHAR_FORMAT({ctx.term_both_date}, 'MM/DD/YYYY') TERM_DATE_BOTH")
        parts.sql_parts.append("  , CASE WHEN TDB.TERM_ENTRY_DT IS NOT NULL THEN 'Transaction (69)'")
        parts.sql_parts.append("      ELSE 'Last Financial (01)' END TERM_DATE_SOURCE")
    if ctx.disp_bill_prem:
        parts.sql_parts.append('  , IFNULL(POLICY1.POL_PRM_AMT, 0) BillPrem')


def add_initial_display_selects(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.disp_bill_mode:
        parts.sql_parts.append('  , (CASE BILLMODE_POOL.PMT_FQY_PER')
        parts.sql_parts.append('      WHEN 1 THEN (CASE BILLMODE_POOL.NSD_MD_CD')
        parts.sql_parts.append("        WHEN '2' THEN 'BiWeekly'")
        parts.sql_parts.append("        WHEN 'S' THEN 'SemiMonthly'")
        parts.sql_parts.append("        WHEN '9' THEN '9thly'")
        parts.sql_parts.append("        WHEN 'A' THEN '10thly'")
        parts.sql_parts.append("        ELSE 'Monthly' END)")
        parts.sql_parts.append("      WHEN 3 THEN 'Quarterly'")
        parts.sql_parts.append("      WHEN 6 THEN 'SemiAnnually'")
        parts.sql_parts.append("      WHEN 12 THEN 'Annually'")
        parts.sql_parts.append("      ELSE ' ' END) BillMode")
    if ctx.disp_bill_form:
        parts.sql_parts.append('  , POLICY1.BIL_FRM_CD BillForm')
    if ctx.disp_mkt_org:
        parts.sql_parts.append('  , SUBSTR(POLICY1.SVC_AGC_NBR, 1, 1) MarkOrg')
    if ctx.disp_reinsured:
        parts.sql_parts.append('  , POLICY1.REINSURED_CD ReinsuredCode')
    if ctx.disp_last_entry or ctx.has_term_fin or ctx.has_term_both:
        parts.sql_parts.append('  , POLICY1.LST_ETR_CD LastEntryCode')
        parts.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.LST_FIN_DT, 'MM/DD/YYYY') LastFinDate_Entry")
    if ctx.disp_orig_entry:
        parts.sql_parts.append('  , POLICY1.OGN_ETR_CD OrigEntryCode')
    if ctx.disp_spec_amt or ctx.multi_base_covs:
        parts.sql_parts.append('  , COVSUMMARY.TOTAL_SA TotalFace')
        parts.sql_parts.append('  , COVSUMMARY.TOTAL_ORIGINAL_SA TotalOriginalFace')
    if ctx.adv_prem_wd_gt_face:
        parts.sql_parts.append('  , (POLICY_TOTALS.TOT_REG_PRM_AMT + POLICY_TOTALS.TOT_ADD_PRM_AMT) PremTD')
        parts.sql_parts.append('  , POLICY_TOTALS.TOT_WTD_AMT AccumWD')
        parts.sql_parts.append('  , PREMWD_FACE.TOTAL_FACE TotalFace')
        parts.sql_parts.append('  , ROUND(REAL(PREMWD_FACE.TOTAL_FACE) + COALESCE(REAL(MVVAL.OPTDB), 0), 2) DeathBenefit')
        if not ctx.disp_db_option:
            parts.sql_parts.append('  , NONTRAD.DTH_BNF_PLN_OPT_CD DBOpt')
    if ctx.disp_tch_pol_id:
        parts.sql_parts.append('  , POLICY1.TCH_POL_ID TCH_POL_ID')
    if ctx.disp_mod_indicator or ctx.is_mdo:
        parts.sql_parts.append('  , SUBSTR(POLICY1.USR_RES_CD, 1, 1) MDO')
    if ctx.disp_prod_line:
        parts.sql_parts.append(f'  , {ctx.result_cov_alias}.PRD_LIN_TYP_CD')
    if ctx.disp_sex_02:
        parts.sql_parts.append(f'  , {ctx.result_cov_alias}.INS_SEX_CD SEX_CD')
    if ctx.disp_subseries:
        parts.sql_parts.append(f'  , {ctx.result_cov_alias}.LIF_PLN_SUB_SRE_CD SUBSERIES')
    if ctx.disp_mec_status:
        parts.sql_parts.append('  , (CASE')
        parts.sql_parts.append("      WHEN POLICY1.MEC_STATUS_CD = '0' THEN '0 - NO'")
        parts.sql_parts.append("      WHEN POLICY1.MEC_STATUS_CD = '1' THEN '1 - YES'")
        parts.sql_parts.append("      WHEN POLICY1.MEC_STATUS_CD = '2' THEN '2 - NO'")
        parts.sql_parts.append('      ELSE POLICY1.MEC_STATUS_CD')
        parts.sql_parts.append('      END) MEC_INDICATOR_01')
    if ctx.disp_app_date:
        parts.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.APP_WRT_DT, 'MM/DD/YYYY') AppDt")
    if ctx.disp_next_notif:
        parts.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.NXT_SCH_NOT_DT, 'MM/DD/YYYY') NextNotifyDt")
    if ctx.disp_next_year_end:
        parts.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.NXT_YR_END_PRC_DT, 'MM/DD/YYYY') NextYearEndDt")
    if ctx.disp_next_stmt:
        parts.sql_parts.append("  , VARCHAR_FORMAT(POLICY1.NXT_SCH_STT_DT, 'MM/DD/YYYY') NextStatementDt")
    if ctx.disp_next_change:
        parts.sql_parts.append(f'  , {ctx.result_cov_alias}.NXT_CHG_TYP_CD NXT_CHG_TYP_CD')
        parts.sql_parts.append(f"  , VARCHAR_FORMAT({ctx.result_cov_alias}.NXT_CHG_DT, 'MM/DD/YYYY') NXT_CHG_DT")
    if ctx.disp_init_term:
        parts.sql_parts.append(f'  , {ctx.result_cov_alias}.INT_RNL_PER')
        parts.sql_parts.append(f'  , {ctx.result_cov_alias}.SBQ_RNL_STR_DUR')
        parts.sql_parts.append(f'  , {ctx.result_cov_alias}.SBQ_RNL_PER')
    if ctx.disp_commission_target:
        parts.sql_parts.append('  , COMMTARGET.TAR_PRM_AMT CTP')
    if ctx.p2t.chk_participating.isChecked() or (ctx.wl_tab is not None and ctx.wl_tab.chk_participation_type.isChecked()):
        parts.sql_parts.append('  , COVERAGE1.DIV_PTP_TYP_CD ParticipationCode')
        parts.sql_parts.append(f'  , {participation_description()} Participation')
    if ctx.wl_tab is not None and ctx.wl_tab.chk_participation_type.isChecked():
        ctx.cases = [f"WHEN TRIM(COVERAGE1.DIV_PTP_TYP_CD) = '{esc(code)}' THEN '{esc(description)}'" for code, description in PARTICIPATION_TYPE_DESCRIPTIONS.items()]
        parts.sql_parts.append('  , (CASE ' + ' '.join(ctx.cases) + " ELSE 'Unknown' END) ParticipationType")
    if ctx.disp_monthly_mtp:
        parts.sql_parts.append('  , MTP.TAR_PRM_AMT MonthlyMTP')
    if ctx.disp_accum_mtp:
        parts.sql_parts.append('  , ACCUMMTP.TAR_PRM_AMT ACCUMMTP')
    if ctx.disp_accum_glp:
        parts.sql_parts.append('  , ACCUMGLP.TAR_PRM_AMT ACCUMGLP')
    if ctx.disp_nsp:
        parts.sql_parts.append('  , NSPTARGET.TAR_PRM_AMT NSP')
    if ctx.disp_shadow_av:
        parts.sql_parts.append('  , SHADOWAV.TAR_PRM_AMT ShadowAV')
    if ctx.disp_db_option:
        parts.sql_parts.append('  , NONTRAD.DTH_BNF_PLN_OPT_CD DBOpt')

