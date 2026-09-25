"""CyberLife SQL select policy section builders."""
from __future__ import annotations

from .common import *


def build_step_010(state: BuildState) -> None:
    if state.disp_def_life_ins:
        state.sql_parts.append('  , (CASE')
        state.sql_parts.append("      WHEN NONTRAD.TFDF_CD = '1' THEN '1 - GPT TEFRA'")
        state.sql_parts.append("      WHEN NONTRAD.TFDF_CD = '2' THEN '2 - GPT DEFRA'")
        state.sql_parts.append("      WHEN NONTRAD.TFDF_CD = '3' THEN '3 - CVAT DEFRA'")
        state.sql_parts.append("      WHEN NONTRAD.TFDF_CD = '4' THEN '4 - GPT Selected'")
        state.sql_parts.append("      WHEN NONTRAD.TFDF_CD = '5' THEN '5 - CVAT Selected'")
        state.sql_parts.append('      ELSE NONTRAD.TFDF_CD')
        state.sql_parts.append('      END) DefOfLifeIns')
    if state.disp_short_pay:
        state.sql_parts.append('  , SHORTPAY_PRM.TAR_PRM_AMT SHORTPAY_AMT')
        state.sql_parts.append("  , VARCHAR_FORMAT(SHORTPAY_PRM.TAR_DT, 'MM/DD/YYYY') SHORTPAY_CEASEDT")
        state.sql_parts.append('  , USERDEF_52G.INITIAL_PAY_DUR SHORTPAY_DUR')
        state.sql_parts.append('  , USERDEF_52G.INITIAL_MODE SHORTPAY_MODE')
        state.sql_parts.append('  , USERDEF_52G.DIAL_TO_PREM_AGE SHORTPAY_DBAGE')
    if state.disp_gpe_date:
        state.sql_parts.append("  , VARCHAR_FORMAT(GRACE_TABLE.GRA_PER_EXP_DT, 'MM/DD/YYYY') GPE_DT")
    if state.disp_term_date:
        state.sql_parts.append("  , VARCHAR_FORMAT(TD.TERM_ENTRY_DT, 'MM/DD/YYYY') TERM_ENTRY_DT")
        state.sql_parts.append("  , VARCHAR_FORMAT(TD.TERM_EFFECTIVE_DT, 'MM/DD/YYYY') TERM_EFFECTIVE_DT")
        state.sql_parts.append('  , TD.TERM_TRANS_TYPES')
    if state.disp_conversion_dates:
        state.sql_parts.append("  , VARCHAR_FORMAT(SC.CONV_SC_ENTRY_DT, 'MM/DD/YYYY') CONV_SC_ENTRY_DT")
        state.sql_parts.append("  , VARCHAR_FORMAT(SC.CONV_SC_EFFECTIVE_DT, 'MM/DD/YYYY') CONV_SC_EFFECTIVE_DT")
    if state.disp_accum_wd:
        state.sql_parts.append('  , POLICY_TOTALS.TOT_WTD_AMT')
    if state.disp_cost_basis:
        state.sql_parts.append('  , POLICY_TOTALS.POL_CST_BSS_AMT COSTBASIS')
    if state.disp_prem_ptd or state.disp_accum_value:
        state.sql_parts.append("  , VARCHAR_FORMAT(MVVAL.LASTMVDT, 'MM/DD/YYYY') LastMonthliverary")
        state.sql_parts.append('  , MVVAL.CSV_AMT CurrCV')
        state.sql_parts.append('  , MVVAL.TOTALPREM')
    if state.disp_prem_ytd:
        state.sql_parts.append('  , LH_POL_YR_TOT_at_MaxDuration.YTD_TOT_PMT_AMT')
    if state.disp_monthly_deduction:
        state.sql_parts.append('  , MONTHLY_DED.MONTHLY_DED_AMT')
        state.sql_parts.append("  , VARCHAR_FORMAT(MONTHLY_DED.MONTHLY_DED_DT, 'MM/DD/YYYY') MONTHLY_DED_DT")
    if state.has_preferred_loan:
        state.sql_parts.append('  , POLICYDEBT.REG_LOAN_PRINCIPLE')
        state.sql_parts.append('  , POLICYDEBT.REG_LOAN_ACCRUED')
        state.sql_parts.append('  , POLICYDEBT.PREF_LOAN_PRINCIPLE')
        state.sql_parts.append('  , POLICYDEBT.PREF_LOAN_ACCRUED')
    if state.disp_policy_debt:
        if not state.has_preferred_loan:
            state.sql_parts.append('  , POLICYDEBT.LOAN_PRINCIPLE')
            state.sql_parts.append('  , POLICYDEBT.LOAN_ACCRUED')
        state.sql_parts.append('  , (CASE')
        state.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '0' THEN 'FIX'")
        state.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '1' THEN 'FIX'")
        state.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '6' THEN 'VAR'")
        state.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '7' THEN 'VAR'")
        state.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '9' THEN 'NA'")
        state.sql_parts.append('      ELSE POLICY1.LN_TYP_CD')
        state.sql_parts.append('      END) LOAN_TYPE')
        state.sql_parts.append('  , (CASE')
        state.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '0' THEN 'ADVANCE'")
        state.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '1' THEN 'ARREARS'")
        state.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '6' THEN 'ADVANCE'")
        state.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '7' THEN 'ARREARS'")
        state.sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '9' THEN 'NA'")
        state.sql_parts.append('      ELSE POLICY1.LN_TYP_CD')
        state.sql_parts.append('      END) LOAN_TIMING')
    if state.disp_substandard:
        state.sql_parts.append(f"  , (CASE WHEN {state.result_table_alias}.SST_XTR_RT_TBL_CD IS NULL THEN ' ' ELSE {state.result_table_alias}.SST_XTR_RT_TBL_CD END) TableRating")
        state.sql_parts.append(f"  , (CASE WHEN {state.result_flat_alias}.SST_XTR_UNT_AMT IS NULL THEN '0' ELSE {state.result_flat_alias}.SST_XTR_UNT_AMT END) MONTHFLAT")
    if state.disp_sex_rateclass:
        state.sql_parts.append(f'  , {state.result_rnw_alias}.RT_CLS_CD RenewalClass')
        state.sql_parts.append(f'  , {state.result_rnw_alias}.RT_SEX_CD RenewalSex')
        state.sql_parts.append(f'  , {state.result_rnw_alias}.RT_BAN_CD RenewalBand')
    if state.disp_tamra:
        state.sql_parts.append('  , TAMRA.SVPY_LVL_PRM_AMT TAMRA7PAY')
    if state.disp_gsp:
        state.sql_parts.append('  , GSP.GSP_VALUE')
    elif state.has_gsp_range:
        state.sql_parts.append('  , GSP.GSP_VALUE')
    if state.disp_glp:
        state.sql_parts.append('  , GLP.GLP_VALUE')
    elif state.has_glp_range:
        state.sql_parts.append('  , GLP.GLP_VALUE')
    if state.disp_bill_ctrl_num:
        state.sql_parts.append('  , BILL_CONTROL.BIL_CTL_NBR BillControl')
    if state.disp_slr_bill_form:
        state.sql_parts.append('  , SLR_BILL_CONTROL.BIL_FRM_CD SLRBillForm')
    if state.disp_orig_face_rpu:
        state.sql_parts.append('  , CHANGE_TYPE9.TOTALORIGUNITS')
    if state.disp_prem_calc_rules:
        state.sql_parts.append('  , FIXPREM.MD_PRM_MUL_ORD_CD')
        state.sql_parts.append('  , FIXPREM.RT_FCT_ORD_CD')
        state.sql_parts.append('  , FIXPREM.ROU_RLE_CD')
    if state.disp_cirf_key:
        state.sql_parts.append('  , FFC.CUR_ITS_RT_SER_NBR CIRF_Key')
    if state.disp_trad_overloan:
        state.sql_parts.append('  , POLICY1_MOD.OVERLOAN_IND')
    if state.disp_replacement_pol:
        state.sql_parts.append('  , USERDEF_52R.REPLACED_POLICY REPLACED_POL')


def build_step_011(state: BuildState) -> None:
    if state.disp_converted_pol or state.p2t.chk_has_converted.isChecked():
        state.sql_parts.append('  , USERGEN.SOURCE_CMP_CODE SOURCE_CMP_CODE')
    if state.disp_converted_pol:
        state.sql_parts.append('  , USERGEN.EXCH_POL_NUMBER EXCHANGE_POL')
        state.sql_parts.append('  , USERGEN.EXCHANGE EXCHANGE_CD')
        state.sql_parts.append('  , USERGEN.SOURCE_COV_PHASE CONV_COV')
        state.sql_parts.append('  , USERGEN.SOURCE_ISSUE_DATE CONV_ISSDT')
        state.sql_parts.append('  , USERGEN.SOURCE_PLAN_CODE CONV_PLAN')
        state.sql_parts.append('  , USERGEN.SOURCE_FACE_AMT CONV_FACE')
    if state.disp_post_conversion:
        state.sql_parts.append('  , PC.POST_CONV_POLICY')
        state.sql_parts.append('  , PC.POST_CONV_COMPANY')
    if state.disp_conv_credit:
        state.sql_parts.append('  , UPDF.CONV_CREDIT_IND CN_CRED_IND')
        state.sql_parts.append('  , UPDF.CONV_CREDIT_RULE CN_CRED_RULE')
        state.sql_parts.append('  , UPDF.CONV_CREDIT_PERIOD CN_CRED_PERIOD')
    if state.disp_within_conv:
        state._today = today_str()
        state._dur = f"TRUNCATE(MONTHS_BETWEEN('{state._today}', COVERAGE1.ISSUE_DT) / 12, 0)"
        state._att_age = f'(COVERAGE1.INS_ISS_AGE + {state._dur})'
        state.sql_parts.append('  , (CASE')
        state.sql_parts.append(f'      WHEN (UPDF.CONVERSION_PERIOD = 0 AND {state._att_age} < UPDF.CONVERSION_AGE)')
        state.sql_parts.append(f'        OR (UPDF.CONVERSION_PERIOD > 0 AND {state._dur} < UPDF.CONVERSION_PERIOD')
        state.sql_parts.append(f'            AND {state._att_age} < UPDF.CONVERSION_AGE)')
        state.sql_parts.append("      THEN 'TRUE' ELSE 'FALSE'")
        state.sql_parts.append('      END) AS WITHIN_CONV_PERIOD')
    if state.disp_conv_period:
        state.sql_parts.append('  , UPDF.CONVERSION_PERIOD CN_PERIOD')
        state.sql_parts.append('  , UPDF.CONVERSION_AGE CN_AGE')
        state.sql_parts.append('  , UPDF.CONV_TO_TRM_PERIOD CN_TO_TERM_PERIOD')
    if state.disp_trad_cv_cov1:
        state.sql_parts.append('  , (CASE')
        state.sql_parts.append('      WHEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0) <> 0 OR COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0) <> 0')
        state.sql_parts.append('      THEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0)')
        state.sql_parts.append('      ELSE COALESCE(COVERAGE1.LOW_DUR_1_NSP_AMT, 0)')
        state.sql_parts.append('    END) BCVR_COV1')
        state.sql_parts.append('  , (CASE')
        state.sql_parts.append('      WHEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0) <> 0 OR COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0) <> 0')
        state.sql_parts.append('      THEN COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0)')
        state.sql_parts.append('      ELSE COALESCE(COVERAGE1.LOW_DUR_2_NSP_AMT, 0)')
        state.sql_parts.append('    END) ECVR_COV1')
        state.sql_parts.append('  , INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN')
        state.sql_parts.append('  , INTERPOLATION_MONTHS.MONTHS_YTD')
        state.sql_parts.append('  , ((CASE')
        state.sql_parts.append('      WHEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0) <> 0 OR COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0) <> 0')
        state.sql_parts.append('      THEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0)')
        state.sql_parts.append('      ELSE COALESCE(COVERAGE1.LOW_DUR_1_NSP_AMT, 0)')
        state.sql_parts.append('    END)')
        state.sql_parts.append('    * COVERAGE1.COV_UNT_QTY * INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN')
        state.sql_parts.append('    + (CASE')
        state.sql_parts.append('        WHEN COALESCE(COVERAGE1.LOW_DUR_1_CSV_AMT, 0) <> 0 OR COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0) <> 0')
        state.sql_parts.append('        THEN COALESCE(COVERAGE1.LOW_DUR_2_CSV_AMT, 0)')
        state.sql_parts.append('        ELSE COALESCE(COVERAGE1.LOW_DUR_2_NSP_AMT, 0)')
        state.sql_parts.append('      END)')
        state.sql_parts.append('    * COVERAGE1.COV_UNT_QTY * INTERPOLATION_MONTHS.MONTHS_YTD) / 12 CV_COV1')
    if state.disp_account_value:
        state.sql_parts.append('  , MVVAL.CSV_AMT')
        state.sql_parts.append('  , TRAD_CV.INTERP_NSP')
        state.sql_parts.append('  , TRAD_CV.INTERP_CV')
        state.sql_parts.append('  , COVERAGE1.ADV_PRD_IND')
        state.sql_parts.append('  , COVERAGE1.LOW_DUR_CSV_AMT')
        state.sql_parts.append('  , COVERAGE1.LOW_DUR_1_CSV_AMT')
        state.sql_parts.append('  , COVERAGE1.LOW_DUR_NSP_AMT')
        state.sql_parts.append('  , COVERAGE1.LOW_DUR_1_NSP_AMT')
    if state.disp_insured1_info:
        state.sql_parts.append('  , INSURED1_INFO.FNAME')
        state.sql_parts.append('  , INSURED1_INFO.LNAME')
        state.sql_parts.append("  , VARCHAR_FORMAT(INSURED1_INFO.BIRTHDT, 'MM/DD/YYYY') BIRTHDT")
    if state.disp_active_benefits:
        state.sql_parts.append("  , (SELECT LISTAGG(TRIM(BNF.SPM_BNF_TYP_CD) || TRIM(BNF.SPM_BNF_SBY_CD), ', ')")
        state.sql_parts.append('            WITHIN GROUP (ORDER BY BNF.SPM_BNF_TYP_CD, BNF.SPM_BNF_SBY_CD)')
        state.sql_parts.append(f'       FROM {state.schema}.LH_SPM_BNF BNF')
        state.sql_parts.append('       WHERE BNF.CK_SYS_CD = POLICY1.CK_SYS_CD')
        state.sql_parts.append('         AND BNF.CK_CMP_CD = POLICY1.CK_CMP_CD')
        state.sql_parts.append('         AND BNF.TCH_POL_ID = POLICY1.TCH_POL_ID')
        state.sql_parts.append('         AND (BNF.BNF_CEA_DT IS NULL OR BNF.BNF_CEA_DT > CURRENT DATE)')
        state.sql_parts.append('      ) ActiveBenefits')
    if state.disp_active_riders:
        state.sql_parts.append("  , (SELECT LISTAGG(DISTINCT_RIDERS.PLN_DES_SER_CD, ', ')")
        state.sql_parts.append('            WITHIN GROUP (ORDER BY DISTINCT_RIDERS.PLN_DES_SER_CD)')
        state.sql_parts.append('       FROM (')
        state.sql_parts.append('         SELECT DISTINCT TRIM(RIDER.PLN_DES_SER_CD) PLN_DES_SER_CD')
        state.sql_parts.append(f'         FROM {state.schema}.LH_COV_PHA RIDER')
        state.sql_parts.append('         WHERE RIDER.CK_SYS_CD = POLICY1.CK_SYS_CD')
        state.sql_parts.append('           AND RIDER.CK_CMP_CD = POLICY1.CK_CMP_CD')
        state.sql_parts.append('           AND RIDER.TCH_POL_ID = POLICY1.TCH_POL_ID')
        state.sql_parts.append('           AND RIDER.COV_PHA_NBR > 1')
        state.sql_parts.append('           AND TRIM(RIDER.PLN_DES_SER_CD) <> TRIM(COVERAGE1.PLN_DES_SER_CD)')
        state.sql_parts.append("           AND (RIDER.NXT_CHG_TYP_CD <> '0'")
        state.sql_parts.append('                OR (RIDER.NXT_CHG_DT IS NOT NULL')
        state.sql_parts.append('                    AND RIDER.NXT_CHG_DT > CURRENT DATE))')
        state.sql_parts.append('       ) DISTINCT_RIDERS')
        state.sql_parts.append('      ) ActiveRiders')
    state.disp_trad_rates = state.dt.Checkbox_DisplayTradRates.isChecked()


def build_step_012(state: BuildState) -> None:
    if state.disp_trad_rates:
        state.sql_parts.append('  , FXD_PRM.POL_FEE_AMT PolFee')
        state.sql_parts.append('  , FXD_PRM.SAN_MD_FCT SemiAnnModalFactor')
        state.sql_parts.append('  , FXD_PRM.QTR_MD_FCT QtrModalFactor')
        state.sql_parts.append('  , FXD_PRM.MO_MD_FCT MoModalFactor')
        state.sql_parts.append('  , COVERAGE1.ANN_PRM_UNT_AMT PremRate')
        state.sql_parts.append('  , POLICY1.POL_PRM_AMT PolPremium')
    state.cov_base_change_set = bool(state.cov_base_change_lo or state.cov_base_change_hi)
    state.cov_base_vpu_set = bool(state._bw['vpu_lo'].text().strip() or state._bw['vpu_hi'].text().strip())
    state.cov_base_specamt_set = bool(state._bw['spec_amt_lo'].text().strip() or state._bw['spec_amt_hi'].text().strip())
    if state.cov_val_classes or state.cov_val_class:
        state.sql_parts.append('  , COVERAGE1.INS_CLS_CD ValClass')
    if state.cov_val_base:
        state.sql_parts.append('  , COVERAGE1.PLN_BSE_SRE_CD ValBase')
    if state.cov_val_sub:
        state.sql_parts.append('  , COVERAGE1.LIF_PLN_SUB_SRE_CD ValSub')
    if state.cov_val_mort:
        state.sql_parts.append('  , COVERAGE1.MTL_FCT_TBL_CD ValMortTable')
    if state.cov_rpu_mort:
        state.sql_parts.append('  , COVERAGE1.NSP_RPU_TBL_CD RPUMortTable')
    if state.cov_eti_mort:
        state.sql_parts.append('  , COVERAGE1.NSP_EI_TBL_CD ETIMortTable')
    if state.cov_nfo_rate:
        state.sql_parts.append('  , COVERAGE1.NSP_ITS_RT NFOIntRate')
    if state.cov_non_trad:
        state.sql_parts.append('  , POLICY1.NON_TRD_POL_IND NonTradInd')
    if state.cov_has_spec_amt and (not (state.disp_spec_amt or state.multi_base_covs)):
        state.sql_parts.append('  , COVSUMMARY.TOTAL_SA CurrSpecAmt')
    if state.cov_init_term and (not state.disp_init_term):
        state.sql_parts.append('  , COVERAGE1.INT_RNL_PER InitTermPeriod')
    if state.cov_val_class_ne:
        if not (state.cov_val_classes or state.cov_val_class):
            state.sql_parts.append('  , COVERAGE1.INS_CLS_CD ValClass')
        state.sql_parts.append('  , SUBSTR(COVERAGE1.PLN_DES_SER_CD, 3, 1) PlanDescClass')
    if state.cov_gio:
        state.sql_parts.append('  , MODCOVSALL.OPT_EXER_IND GioInd')
    if state.cov_cola and (not state.cov_base_cola_ind):
        state.sql_parts.append('  , MODCOVSALL.COLA_INCR_IND ColaInd')
    if state.cov_cv_rate:
        state.sql_parts.append('  , COVERAGE1.LOW_DUR_1_CSV_AMT CVRate1')
        state.sql_parts.append('  , COVERAGE1.LOW_DUR_2_CSV_AMT CVRate2')
    if state.cov_gcv_gt_cv or state.cov_gcv_lt_cv:
        state.sql_parts.append('  , ISWL_INTERPOLATED_GCV.ISWL_GCV GCV')
        state.sql_parts.append('  , MVVAL.CSV_AMT CurrentCV')
    if state.cov_base_prod_line and (not state.disp_prod_line):
        state.sql_parts.append('  , COVERAGE1.PRD_LIN_TYP_CD ProdLine')
    if state.cov_base_sex02 and (not state.disp_sex_02):
        state.sql_parts.append('  , COVERAGE1.INS_SEX_CD Sex02')
    if state.cov_base_person:
        state.sql_parts.append('  , COVERAGE1.PRS_CD Person')
    if state.cov_base_lives_cov:
        state.sql_parts.append('  , COVERAGE1.LIVES_COV_CD LivesCov')
    if state.cov_base_change_type and (not state.disp_next_change):
        state.sql_parts.append('  , COVERAGE1.NXT_CHG_TYP_CD ChangeType')
    if state.cov_base_change_set and (not state.disp_next_change):
        state.sql_parts.append("  , VARCHAR_FORMAT(COVERAGE1.NXT_CHG_DT, 'MM/DD/YYYY') ChangeDate")
    if state.cov_base_prod_ind:
        state.sql_parts.append('  , MODCOV1.AN_PRD_ID ProdInd')
    if state.cov_base_cola_ind:
        state.sql_parts.append('  , MODCOV1.COLA_INCR_IND ColaInd')
    if state.cov_base_gio_fio:
        state.sql_parts.append('  , MODCOV1.OPT_EXER_IND GioFio')
    if state.cov_base_rateclass and (not state.disp_sex_rateclass):
        state.sql_parts.append('  , COV1_RENEWALS.RT_CLS_CD RateClass')
    if state.cov_base_sex67 and (not state.disp_sex_rateclass):
        state.sql_parts.append('  , COV1_RENEWALS.RT_SEX_CD Sex67')
    if state.cov_base_vpu_set:
        state.sql_parts.append('  , COVERAGE1.COV_VPU_AMT VPU')
    if state.cov_base_specamt_set:
        state.sql_parts.append('  , ROUND(REAL(COVERAGE1.COV_UNT_QTY) * REAL(COVERAGE1.COV_VPU_AMT), 2) SpecifiedAmount')
    if state.cov_base_table03 and (not state.disp_substandard):
        state.sql_parts.append('  , TABLE_RATING1.SST_XTR_RT_TBL_CD TableRating')
    if (state.cov_base_flat03 or state.cov_base_active_flat03) and (not state.disp_substandard):
        state.sql_parts.append('  , FLAT_EXTRA1.SST_XTR_UNT_AMT FlatExtra')
