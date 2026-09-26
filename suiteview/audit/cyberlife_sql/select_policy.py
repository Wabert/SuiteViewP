"""CyberLife SQL select policy section builders."""
from __future__ import annotations

from suiteview.audit.cyberlife_sql.state import QueryContext, SqlParts


def add_policy_selects(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.disp_def_life_ins:
        parts.sql_parts.append('  , (CASE')
        parts.sql_parts.append("      WHEN NONTRAD.TFDF_CD = '1' THEN '1 - GPT TEFRA'")
        parts.sql_parts.append("      WHEN NONTRAD.TFDF_CD = '2' THEN '2 - GPT DEFRA'")
        parts.sql_parts.append("      WHEN NONTRAD.TFDF_CD = '3' THEN '3 - CVAT DEFRA'")
        parts.sql_parts.append("      WHEN NONTRAD.TFDF_CD = '4' THEN '4 - GPT Selected'")
        parts.sql_parts.append("      WHEN NONTRAD.TFDF_CD = '5' THEN '5 - CVAT Selected'")
        parts.sql_parts.append('      ELSE NONTRAD.TFDF_CD')
        parts.sql_parts.append('      END) DefOfLifeIns')
    if ctx.disp_short_pay:
        parts.sql_parts.append('  , SHORTPAY_PRM.TAR_PRM_AMT SHORTPAY_AMT')
        parts.sql_parts.append("  , VARCHAR_FORMAT(SHORTPAY_PRM.TAR_DT, 'MM/DD/YYYY') SHORTPAY_CEASEDT")
        parts.sql_parts.append('  , USERDEF_52G.INITIAL_PAY_DUR SHORTPAY_DUR')
        parts.sql_parts.append('  , USERDEF_52G.INITIAL_MODE SHORTPAY_MODE')
        parts.sql_parts.append('  , USERDEF_52G.DIAL_TO_PREM_AGE SHORTPAY_DBAGE')
    if ctx.disp_gpe_date:
        parts.sql_parts.append("  , VARCHAR_FORMAT(GRACE_TABLE.GRA_PER_EXP_DT, 'MM/DD/YYYY') GPE_DT")
    if ctx.disp_term_date:
        parts.sql_parts.append("  , VARCHAR_FORMAT(TD.TERM_ENTRY_DT, 'MM/DD/YYYY') TERM_ENTRY_DT")
        parts.sql_parts.append("  , VARCHAR_FORMAT(TD.TERM_EFFECTIVE_DT, 'MM/DD/YYYY') TERM_EFFECTIVE_DT")
        parts.sql_parts.append('  , TD.TERM_TRANS_TYPES')
    if ctx.disp_conversion_dates:
        parts.sql_parts.append("  , VARCHAR_FORMAT(SC.CONV_SC_ENTRY_DT, 'MM/DD/YYYY') CONV_SC_ENTRY_DT")
        parts.sql_parts.append("  , VARCHAR_FORMAT(SC.CONV_SC_EFFECTIVE_DT, 'MM/DD/YYYY') CONV_SC_EFFECTIVE_DT")
    if ctx.disp_accum_wd:
        parts.sql_parts.append('  , POLICY_TOTALS.TOT_WTD_AMT')
    if ctx.disp_cost_basis:
        parts.sql_parts.append('  , POLICY_TOTALS.POL_CST_BSS_AMT COSTBASIS')
    if ctx.disp_prem_ptd or ctx.disp_accum_value:
        parts.sql_parts.append("  , VARCHAR_FORMAT(MVVAL.LASTMVDT, 'MM/DD/YYYY') LastMonthliverary")
        parts.sql_parts.append('  , MVVAL.CSV_AMT CurrCV')
        parts.sql_parts.append('  , MVVAL.TOTALPREM')
    if ctx.disp_prem_ytd:
        parts.sql_parts.append('  , LH_POL_YR_TOT_at_MaxDuration.YTD_TOT_PMT_AMT')
    if ctx.disp_monthly_deduction:
        parts.sql_parts.append('  , MONTHLY_DED.MONTHLY_DED_AMT')
        parts.sql_parts.append("  , VARCHAR_FORMAT(MONTHLY_DED.MONTHLY_DED_DT, 'MM/DD/YYYY') MONTHLY_DED_DT")
    if ctx.has_preferred_loan:
        parts.sql_parts.append('  , POLICYDEBT.REG_LOAN_PRINCIPLE')
        parts.sql_parts.append('  , POLICYDEBT.REG_LOAN_ACCRUED')
        parts.sql_parts.append('  , POLICYDEBT.PREF_LOAN_PRINCIPLE')
        parts.sql_parts.append('  , POLICYDEBT.PREF_LOAN_ACCRUED')
    if ctx.disp_policy_debt:
        if not ctx.has_preferred_loan:
            parts.sql_parts.append('  , POLICYDEBT.LOAN_PRINCIPLE')
            parts.sql_parts.append('  , POLICYDEBT.LOAN_ACCRUED')
        parts.sql_parts.append('  , (CASE')
        parts.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '0' THEN 'FIX'")
        parts.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '1' THEN 'FIX'")
        parts.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '6' THEN 'VAR'")
        parts.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '7' THEN 'VAR'")
        parts.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '9' THEN 'NA'")
        parts.sql_parts.append('      ELSE POLICY1.LN_TYP_CD')
        parts.sql_parts.append('      END) LOAN_TYPE')
        parts.sql_parts.append('  , (CASE')
        parts.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '0' THEN 'ADVANCE'")
        parts.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '1' THEN 'ARREARS'")
        parts.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '6' THEN 'ADVANCE'")
        parts.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '7' THEN 'ARREARS'")
        parts.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '9' THEN 'NA'")
        parts.sql_parts.append('      ELSE POLICY1.LN_TYP_CD')
        parts.sql_parts.append('      END) LOAN_TIMING')
    if ctx.disp_substandard:
        parts.sql_parts.append(f"  , (CASE WHEN {ctx.result_table_alias}.SST_XTR_RT_TBL_CD IS NULL THEN ' ' ELSE {ctx.result_table_alias}.SST_XTR_RT_TBL_CD END) TableRating")
        parts.sql_parts.append(f"  , (CASE WHEN {ctx.result_flat_alias}.SST_XTR_UNT_AMT IS NULL THEN '0' ELSE {ctx.result_flat_alias}.SST_XTR_UNT_AMT END) MONTHFLAT")
    if ctx.disp_sex_rateclass:
        parts.sql_parts.append(f'  , {ctx.result_rnw_alias}.RT_CLS_CD RenewalClass')
        parts.sql_parts.append(f'  , {ctx.result_rnw_alias}.RT_SEX_CD RenewalSex')
        parts.sql_parts.append(f'  , {ctx.result_rnw_alias}.RT_BAN_CD RenewalBand')
    if ctx.disp_tamra:
        parts.sql_parts.append('  , TAMRA.SVPY_LVL_PRM_AMT TAMRA7PAY')
    if ctx.disp_gsp:
        parts.sql_parts.append('  , GSP.GSP_VALUE')
    elif ctx.has_gsp_range:
        parts.sql_parts.append('  , GSP.GSP_VALUE')
    if ctx.disp_glp:
        parts.sql_parts.append('  , GLP.GLP_VALUE')
    elif ctx.has_glp_range:
        parts.sql_parts.append('  , GLP.GLP_VALUE')
    if ctx.disp_bill_ctrl_num:
        parts.sql_parts.append('  , BILL_CONTROL.BIL_CTL_NBR BillControl')
    if ctx.disp_slr_bill_form:
        parts.sql_parts.append('  , SLR_BILL_CONTROL.BIL_FRM_CD SLRBillForm')
    if ctx.disp_orig_face_rpu:
        parts.sql_parts.append('  , CHANGE_TYPE9.TOTALORIGUNITS')
    if ctx.disp_prem_calc_rules:
        parts.sql_parts.append('  , FIXPREM.MD_PRM_MUL_ORD_CD')
        parts.sql_parts.append('  , FIXPREM.RT_FCT_ORD_CD')
        parts.sql_parts.append('  , FIXPREM.ROU_RLE_CD')
    if ctx.disp_cirf_key:
        parts.sql_parts.append('  , FFC.CUR_ITS_RT_SER_NBR CIRF_Key')
    if ctx.disp_trad_overloan:
        parts.sql_parts.append('  , POLICY1_MOD.OVERLOAN_IND')
    if ctx.disp_replacement_pol:
        parts.sql_parts.append('  , USERDEF_52R.REPLACED_POLICY REPLACED_POL')


def add_policy_value_selects(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.disp_converted_pol or ctx.p2t.chk_has_converted:
        parts.sql_parts.append('  , USERGEN.SOURCE_CMP_CODE SOURCE_CMP_CODE')
    if ctx.disp_converted_pol:
        parts.sql_parts.append('  , USERGEN.EXCH_POL_NUMBER EXCHANGE_POL')
        parts.sql_parts.append('  , USERGEN.EXCHANGE EXCHANGE_CD')
        parts.sql_parts.append('  , USERGEN.SOURCE_COV_PHASE CONV_COV')
        parts.sql_parts.append('  , USERGEN.SOURCE_ISSUE_DATE CONV_ISSDT')
        parts.sql_parts.append('  , USERGEN.SOURCE_PLAN_CODE CONV_PLAN')
        parts.sql_parts.append('  , USERGEN.SOURCE_FACE_AMT CONV_FACE')
    if ctx.disp_post_conversion:
        parts.sql_parts.append('  , PC.POST_CONV_POLICY')
        parts.sql_parts.append('  , PC.POST_CONV_COMPANY')
    if ctx.disp_conv_credit:
        parts.sql_parts.append('  , UPDF.CONV_CREDIT_IND CN_CRED_IND')
        parts.sql_parts.append('  , UPDF.CONV_CREDIT_RULE CN_CRED_RULE')
        parts.sql_parts.append('  , UPDF.CONV_CREDIT_PERIOD CN_CRED_PERIOD')
    if ctx.disp_within_conv:
        as_of_sql = ctx.criteria.as_of_sql
        duration_expr = f"TRUNCATE(MONTHS_BETWEEN('{as_of_sql}', COVERAGE1.ISSUE_DT) / 12, 0)"
        attained_age_expr = f'(COVERAGE1.INS_ISS_AGE + {duration_expr})'
        parts.sql_parts.append('  , (CASE')
        parts.sql_parts.append(f'      WHEN (UPDF.CONVERSION_PERIOD = 0 AND {attained_age_expr} < UPDF.CONVERSION_AGE)')
        parts.sql_parts.append(f'        OR (UPDF.CONVERSION_PERIOD > 0 AND {duration_expr} < UPDF.CONVERSION_PERIOD')
        parts.sql_parts.append(f'            AND {attained_age_expr} < UPDF.CONVERSION_AGE)')
        parts.sql_parts.append("      THEN 'TRUE' ELSE 'FALSE'")
        parts.sql_parts.append('      END) AS WITHIN_CONV_PERIOD')
    if ctx.disp_conv_period:
        parts.sql_parts.append('  , UPDF.CONVERSION_PERIOD CN_PERIOD')
        parts.sql_parts.append('  , UPDF.CONVERSION_AGE CN_AGE')
        parts.sql_parts.append('  , UPDF.CONV_TO_TRM_PERIOD CN_TO_TERM_PERIOD')
    if ctx.disp_trad_cv_cov1:
        parts.sql_parts.append('  , (CASE')
        parts.sql_parts.append('      WHEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0) <> 0 OR COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0) <> 0')
        parts.sql_parts.append('      THEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0)')
        parts.sql_parts.append('      ELSE COALESCE(COVERAGE1.LOW_DUR_1_NSP_AMT, 0)')
        parts.sql_parts.append('    END) BCVR_COV1')
        parts.sql_parts.append('  , (CASE')
        parts.sql_parts.append('      WHEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0) <> 0 OR COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0) <> 0')
        parts.sql_parts.append('      THEN COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0)')
        parts.sql_parts.append('      ELSE COALESCE(COVERAGE1.LOW_DUR_2_NSP_AMT, 0)')
        parts.sql_parts.append('    END) ECVR_COV1')
        parts.sql_parts.append('  , INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN')
        parts.sql_parts.append('  , INTERPOLATION_MONTHS.MONTHS_YTD')
        parts.sql_parts.append('  , ((CASE')
        parts.sql_parts.append('      WHEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0) <> 0 OR COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0) <> 0')
        parts.sql_parts.append('      THEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0)')
        parts.sql_parts.append('      ELSE COALESCE(COVERAGE1.LOW_DUR_1_NSP_AMT, 0)')
        parts.sql_parts.append('    END)')
        parts.sql_parts.append('    * COVERAGE1.COV_UNT_QTY * INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN')
        parts.sql_parts.append('    + (CASE')
        parts.sql_parts.append('        WHEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0) <> 0 OR COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0) <> 0')
        parts.sql_parts.append('        THEN COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0)')
        parts.sql_parts.append('        ELSE COALESCE(COVERAGE1.LOW_DUR_2_NSP_AMT, 0)')
        parts.sql_parts.append('      END)')
        parts.sql_parts.append('    * COVERAGE1.COV_UNT_QTY * INTERPOLATION_MONTHS.MONTHS_YTD) / 12 CV_COV1')
    if ctx.disp_account_value:
        parts.sql_parts.append('  , MVVAL.CSV_AMT')
        parts.sql_parts.append('  , TRAD_CV.INTERP_NSP')
        parts.sql_parts.append('  , TRAD_CV.INTERP_CV')
        parts.sql_parts.append('  , COVERAGE1.ADV_PRD_IND')
        parts.sql_parts.append('  , COVERAGE1.LOW_DUR_CSV_AMT')
        parts.sql_parts.append('  , COVERAGE1.LOW_DUR_1_CSV_AMT')
        parts.sql_parts.append('  , COVERAGE1.LOW_DUR_NSP_AMT')
        parts.sql_parts.append('  , COVERAGE1.LOW_DUR_1_NSP_AMT')
    if ctx.disp_insured1_info:
        parts.sql_parts.append('  , INSURED1_INFO.FNAME')
        parts.sql_parts.append('  , INSURED1_INFO.LNAME')
        parts.sql_parts.append("  , VARCHAR_FORMAT(INSURED1_INFO.BIRTHDT, 'MM/DD/YYYY') BIRTHDT")
    if ctx.disp_active_benefits:
        parts.sql_parts.append("  , (SELECT LISTAGG(TRIM(BNF.SPM_BNF_TYP_CD) || TRIM(BNF.SPM_BNF_SBY_CD), ', ')")
        parts.sql_parts.append('            WITHIN GROUP (ORDER BY BNF.SPM_BNF_TYP_CD, BNF.SPM_BNF_SBY_CD)')
        parts.sql_parts.append(f'       FROM {ctx.schema}.LH_SPM_BNF BNF')
        parts.sql_parts.append('       WHERE BNF.CK_SYS_CD = POLICY1.CK_SYS_CD')
        parts.sql_parts.append('         AND BNF.CK_CMP_CD = POLICY1.CK_CMP_CD')
        parts.sql_parts.append('         AND BNF.TCH_POL_ID = POLICY1.TCH_POL_ID')
        parts.sql_parts.append('         AND (BNF.BNF_CEA_DT IS NULL OR BNF.BNF_CEA_DT > CURRENT DATE)')
        parts.sql_parts.append('      ) ActiveBenefits')
    if ctx.disp_active_riders:
        parts.sql_parts.append("  , (SELECT LISTAGG(DISTINCT_RIDERS.PLN_DES_SER_CD, ', ')")
        parts.sql_parts.append('            WITHIN GROUP (ORDER BY DISTINCT_RIDERS.PLN_DES_SER_CD)')
        parts.sql_parts.append('       FROM (')
        parts.sql_parts.append('         SELECT DISTINCT TRIM(RIDER.PLN_DES_SER_CD) PLN_DES_SER_CD')
        parts.sql_parts.append(f'         FROM {ctx.schema}.LH_COV_PHA RIDER')
        parts.sql_parts.append('         WHERE RIDER.CK_SYS_CD = POLICY1.CK_SYS_CD')
        parts.sql_parts.append('           AND RIDER.CK_CMP_CD = POLICY1.CK_CMP_CD')
        parts.sql_parts.append('           AND RIDER.TCH_POL_ID = POLICY1.TCH_POL_ID')
        parts.sql_parts.append('           AND RIDER.COV_PHA_NBR > 1')
        parts.sql_parts.append('           AND TRIM(RIDER.PLN_DES_SER_CD) <> TRIM(COVERAGE1.PLN_DES_SER_CD)')
        parts.sql_parts.append("           AND (RIDER.NXT_CHG_TYP_CD <> '0'")
        parts.sql_parts.append('                OR (RIDER.NXT_CHG_DT IS NOT NULL')
        parts.sql_parts.append('                    AND RIDER.NXT_CHG_DT > CURRENT DATE))')
        parts.sql_parts.append('       ) DISTINCT_RIDERS')
        parts.sql_parts.append('      ) ActiveRiders')


def add_accumulator_selects(ctx: QueryContext, parts: SqlParts) -> None:
    _add_coverage_value_selects(ctx, parts)
    _add_coverage_flag_selects(ctx, parts)
    _add_base_coverage_selects(ctx, parts)


def _add_coverage_value_selects(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.disp_trad_rates:
        parts.sql_parts.append('  , FXD_PRM.POL_FEE_AMT PolFee')
        parts.sql_parts.append('  , FXD_PRM.SAN_MD_FCT SemiAnnModalFactor')
        parts.sql_parts.append('  , FXD_PRM.QTR_MD_FCT QtrModalFactor')
        parts.sql_parts.append('  , FXD_PRM.MO_MD_FCT MoModalFactor')
        parts.sql_parts.append('  , COVERAGE1.ANN_PRM_UNT_AMT PremRate')
        parts.sql_parts.append('  , POLICY1.POL_PRM_AMT PolPremium')
    if ctx.cov_val_classes or ctx.cov_val_class:
        parts.sql_parts.append('  , COVERAGE1.INS_CLS_CD ValClass')
    if ctx.cov_val_base:
        parts.sql_parts.append('  , COVERAGE1.PLN_BSE_SRE_CD ValBase')
    if ctx.cov_val_sub:
        parts.sql_parts.append('  , COVERAGE1.LIF_PLN_SUB_SRE_CD ValSub')
    if ctx.cov_val_mort:
        parts.sql_parts.append('  , COVERAGE1.MTL_FCT_TBL_CD ValMortTable')
    if ctx.cov_rpu_mort:
        parts.sql_parts.append('  , COVERAGE1.NSP_RPU_TBL_CD RPUMortTable')
    if ctx.cov_eti_mort:
        parts.sql_parts.append('  , COVERAGE1.NSP_EI_TBL_CD ETIMortTable')
    if ctx.cov_nfo_rate:
        parts.sql_parts.append('  , COVERAGE1.NSP_ITS_RT NFOIntRate')
    if ctx.cov_non_trad:
        parts.sql_parts.append('  , POLICY1.NON_TRD_POL_IND NonTradInd')
    if ctx.cov_has_spec_amt and (not (ctx.disp_spec_amt or ctx.multi_base_covs)):
        parts.sql_parts.append('  , COVSUMMARY.TOTAL_SA CurrSpecAmt')
    if ctx.cov_init_term and (not ctx.disp_init_term):
        parts.sql_parts.append('  , COVERAGE1.INT_RNL_PER InitTermPeriod')


def _add_coverage_flag_selects(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.cov_val_class_ne:
        if not (ctx.cov_val_classes or ctx.cov_val_class):
            parts.sql_parts.append('  , COVERAGE1.INS_CLS_CD ValClass')
        parts.sql_parts.append('  , SUBSTR(COVERAGE1.PLN_DES_SER_CD, 3, 1) PlanDescClass')
    if ctx.cov_gio:
        parts.sql_parts.append('  , MODCOVSALL.OPT_EXER_IND GioInd')
    if ctx.cov_cola and (not ctx.cov_base_cola_ind):
        parts.sql_parts.append('  , MODCOVSALL.COLA_INCR_IND ColaInd')
    if ctx.cov_cv_rate:
        parts.sql_parts.append('  , COVERAGE1.LOW_DUR_1_CSV_AMT CVRate1')
        parts.sql_parts.append('  , COVERAGE1.LOW_DUR_2_CSV_AMT CVRate2')
    if ctx.cov_gcv_gt_cv or ctx.cov_gcv_lt_cv:
        parts.sql_parts.append('  , ISWL_INTERPOLATED_GCV.ISWL_GCV GCV')
        parts.sql_parts.append('  , MVVAL.CSV_AMT CurrentCV')


def _add_base_coverage_selects(ctx: QueryContext, parts: SqlParts) -> None:
    _add_base_identity_selects(ctx, parts)
    _add_base_mod_selects(ctx, parts)
    _add_base_rating_selects(ctx, parts)


def _add_base_identity_selects(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.cov_base_prod_line and (not ctx.disp_prod_line):
        parts.sql_parts.append('  , COVERAGE1.PRD_LIN_TYP_CD ProdLine')
    if ctx.cov_base_sex02 and (not ctx.disp_sex_02):
        parts.sql_parts.append('  , COVERAGE1.INS_SEX_CD Sex02')
    if ctx.cov_base_person:
        parts.sql_parts.append('  , COVERAGE1.PRS_CD Person')
    if ctx.cov_base_lives_cov:
        parts.sql_parts.append('  , COVERAGE1.LIVES_COV_CD LivesCov')
    if ctx.cov_base_change_type and (not ctx.disp_next_change):
        parts.sql_parts.append('  , COVERAGE1.NXT_CHG_TYP_CD ChangeType')
    if ctx.cov_base_change_set and (not ctx.disp_next_change):
        parts.sql_parts.append("  , VARCHAR_FORMAT(COVERAGE1.NXT_CHG_DT, 'MM/DD/YYYY') ChangeDate")


def _add_base_mod_selects(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.cov_base_prod_ind:
        parts.sql_parts.append('  , MODCOV1.AN_PRD_ID ProdInd')
    if ctx.cov_base_cola_ind:
        parts.sql_parts.append('  , MODCOV1.COLA_INCR_IND ColaInd')
    if ctx.cov_base_gio_fio:
        parts.sql_parts.append('  , MODCOV1.OPT_EXER_IND GioFio')


def _add_base_rating_selects(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.cov_base_rateclass and (not ctx.disp_sex_rateclass):
        parts.sql_parts.append('  , COV1_RENEWALS.RT_CLS_CD RateClass')
    if ctx.cov_base_sex67 and (not ctx.disp_sex_rateclass):
        parts.sql_parts.append('  , COV1_RENEWALS.RT_SEX_CD Sex67')
    if ctx.cov_base_vpu_set:
        parts.sql_parts.append('  , COVERAGE1.COV_VPU_AMT VPU')
    if ctx.cov_base_specamt_set:
        parts.sql_parts.append('  , ROUND(REAL(COVERAGE1.COV_UNT_QTY) * REAL(COVERAGE1.COV_VPU_AMT), 2) SpecifiedAmount')
    if ctx.cov_base_table03 and (not ctx.disp_substandard):
        parts.sql_parts.append('  , TABLE_RATING1.SST_XTR_RT_TBL_CD TableRating')
    if (ctx.cov_base_flat03 or ctx.cov_base_active_flat03) and (not ctx.disp_substandard):
        parts.sql_parts.append('  , FLAT_EXTRA1.SST_XTR_UNT_AMT FlatExtra')
