"""CyberLife SQL select display section builders."""
from __future__ import annotations

from .common import *


def build_step_013(state: BuildState) -> None:

    def _rider_select_lines(info: dict, alias: str, label: str) -> list:
        lines = []
        if not (state.coverage_level and info['active']):
            return lines
        covmod_alias = f'{alias}COVMOD'
        rnl_alias = f'{alias}_RENEWALS'
        tr_alias = f'{alias}_TABLE_RATING'
        fe_alias = f'{alias}_FLAT_EXTRA'
        if info['plancode']:
            lines.append(f'  , {alias}.PLN_DES_SER_CD {label}Plancode')
        if info['prod_line']:
            lines.append(f'  , {alias}.PRD_LIN_TYP_CD {label}ProdLine')
        if info['sex_code_02']:
            lines.append(f'  , {alias}.INS_SEX_CD {label}Sex02')
        if info['person']:
            lines.append(f'  , {alias}.PRS_CD {label}Person')
        if info['lives_cov']:
            lines.append(f'  , {alias}.LIVES_COV_CD {label}LivesCov')
        if info['change_type']:
            lines.append(f'  , {alias}.NXT_CHG_TYP_CD {label}ChangeType')
        if info['change_date_lo'] or info['change_date_hi']:
            lines.append(f"  , VARCHAR_FORMAT({alias}.NXT_CHG_DT, 'MM/DD/YYYY') {label}ChangeDate")
        if info['prod_ind']:
            lines.append(f'  , {covmod_alias}.AN_PRD_ID {label}ProdInd')
        if info['cola_ind']:
            lines.append(f'  , {covmod_alias}.COLA_INCR_IND {label}ColaInd')
        if info['gio_fio']:
            lines.append(f'  , {covmod_alias}.OPT_EXER_IND {label}GioFio')
        if info['rateclass']:
            lines.append(f'  , {rnl_alias}.RT_CLS_CD {label}RateClass')
        if info['sex_code_67']:
            lines.append(f'  , {rnl_alias}.RT_SEX_CD {label}Sex67')
        if info['vpu_lo'] or info['vpu_hi']:
            lines.append(f'  , {alias}.COV_VPU_AMT {label}VPU')
        if info['spec_amt_lo'] or info['spec_amt_hi']:
            lines.append(f'  , ROUND(REAL({alias}.COV_UNT_QTY) * REAL({alias}.COV_VPU_AMT), 2) {label}SpecifiedAmount')
        if info['table_03']:
            lines.append(f'  , {tr_alias}.SST_XTR_RT_TBL_CD {label}TableRating')
        if info['flat_03'] or info['active_flat_03']:
            lines.append(f'  , {fe_alias}.SST_XTR_UNT_AMT {label}FlatExtra')
        return lines
    state._rider_select_lines = _rider_select_lines
    state.sql_parts.extend(state._rider_select_lines(state.rider1_info, 'RIDER1', 'Rider1'))
    state.sql_parts.extend(state._rider_select_lines(state.rider2_info, 'RIDER2', 'Rider2'))
    state.sql_parts.extend(state.custom_select_lines)
    state.sql_parts.extend(state.segment52_select_lines)
    state.cov1_plancode_match_only = state.plancode_tab.cov1_plancode_match_only()
    state._any_cov_plancode = bool((state.pt.txt_plancode.text().strip() or state.plancode_tab.get_plancodes()) and (not state.cov1_plancode_match_only))
    state._any_cov_product_line = bool(state.pt.chk_product_line.isChecked() and selected_codes(state.pt.list_product_line))
    state.needs_covsall = state.has_modcovsall or (not state.coverage_level and (state._any_cov_plancode or state._any_cov_product_line))
    state.sql_parts.append(f'FROM {state.schema}.LH_BAS_POL POLICY1')
    if state.needs_covsall:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_COV_PHA COVSALL')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = COVSALL.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = COVSALL.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = COVSALL.TCH_POL_ID')
    state.sql_parts.append('  INNER JOIN COVERAGE1')
    state.sql_parts.append('    ON POLICY1.CK_SYS_CD = COVERAGE1.CK_SYS_CD')
    state.sql_parts.append('    AND POLICY1.CK_CMP_CD = COVERAGE1.CK_CMP_CD')
    state.sql_parts.append('    AND POLICY1.TCH_POL_ID = COVERAGE1.TCH_POL_ID')
    if state.coverage_level:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_COV_PHA RESULTCOV')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = RESULTCOV.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = RESULTCOV.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = RESULTCOV.TCH_POL_ID')
    state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.TH_USER_GENERIC USERGEN')
    state.sql_parts.append('    ON POLICY1.CK_SYS_CD = USERGEN.CK_SYS_CD')
    state.sql_parts.append('    AND POLICY1.CK_CMP_CD = USERGEN.CK_CMP_CD')
    state.sql_parts.append('    AND POLICY1.TCH_POL_ID = USERGEN.TCH_POL_ID')
    if state.disp_trad_rates:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_FXD_PRM_POL FXD_PRM')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = FXD_PRM.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = FXD_PRM.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = FXD_PRM.TCH_POL_ID')
    if state.disp_bill_mode:
        state.sql_parts.append('  LEFT OUTER JOIN BILLMODE_POOL')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = BILLMODE_POOL.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = BILLMODE_POOL.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = BILLMODE_POOL.TCH_POL_ID')
    if state.needs_covsummary:
        state._cov_join = 'INNER JOIN' if state.multi_base_covs else 'LEFT OUTER JOIN'
        state.sql_parts.append(f'  {state._cov_join} COVSUMMARY')
        state.sql_parts.append('    ON COVSUMMARY.CK_SYS_CD = POLICY1.CK_SYS_CD')
        state.sql_parts.append('    AND COVSUMMARY.CK_CMP_CD = POLICY1.CK_CMP_CD')
        state.sql_parts.append('    AND COVSUMMARY.TCH_POL_ID = POLICY1.TCH_POL_ID')


def build_step_014(state: BuildState) -> None:
    if state.needs_premwd_face:
        state.sql_parts.append('  INNER JOIN PREMWD_FACE')
        state.sql_parts.append('    ON PREMWD_FACE.CK_SYS_CD = POLICY1.CK_SYS_CD')
        state.sql_parts.append('    AND PREMWD_FACE.CK_CMP_CD = POLICY1.CK_CMP_CD')
        state.sql_parts.append('    AND PREMWD_FACE.TCH_POL_ID = POLICY1.TCH_POL_ID')
    if state.in_conversion or state.disp_conv_credit or state.disp_within_conv or state.disp_conv_period:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.TH_USER_PDF UPDF')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = UPDF.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = UPDF.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = UPDF.TCH_POL_ID')
        state.sql_parts.append('    AND UPDF.TYPE_SEQUENCE = 1')
    if state.disp_insured1_info:
        state.sql_parts.append('  LEFT OUTER JOIN INSURED1_INFO')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = INSURED1_INFO.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = INSURED1_INFO.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = INSURED1_INFO.TCH_POL_ID')
    if state.needs_grace_table:
        state.sql_parts.append('  INNER JOIN GRACE_TABLE')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = GRACE_TABLE.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = GRACE_TABLE.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = GRACE_TABLE.TCH_POL_ID')
    if state.has_tamra or state.disp_tamra:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_TAMRA_7_PY_PER TAMRA')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = TAMRA.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = TAMRA.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = TAMRA.TCH_POL_ID')
    if state.has_pol_totals:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_POL_TOTALS POLICY_TOTALS')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = POLICY_TOTALS.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = POLICY_TOTALS.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = POLICY_TOTALS.TCH_POL_ID')
    if state.needs_pol_yr_tot:
        state.sql_parts.append('  LEFT OUTER JOIN LH_POL_YR_TOT_at_MaxDuration')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = LH_POL_YR_TOT_at_MaxDuration.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = LH_POL_YR_TOT_at_MaxDuration.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = LH_POL_YR_TOT_at_MaxDuration.TCH_POL_ID')
    if state.has_nontrad or state.disp_db_option or state.disp_def_life_ins or state.adv_prem_wd_gt_face:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_NON_TRD_POL NONTRAD')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = NONTRAD.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = NONTRAD.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = NONTRAD.TCH_POL_ID')
    if state.has_modcovsall:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.TH_COV_PHA MODCOVSALL')
        state.sql_parts.append('    ON MODCOVSALL.CK_SYS_CD = COVSALL.CK_SYS_CD')
        state.sql_parts.append('    AND MODCOVSALL.CK_CMP_CD = COVSALL.CK_CMP_CD')
        state.sql_parts.append('    AND MODCOVSALL.TCH_POL_ID = COVSALL.TCH_POL_ID')
        state.sql_parts.append('    AND MODCOVSALL.COV_PHA_NBR = COVSALL.COV_PHA_NBR')
        if state.policy_has_product_indicator:
            state.sql_parts.append(f'    AND MODCOVSALL.AN_PRD_ID IN ({in_list(state.policy_product_indicator_codes)})')
    if state.coverage_level and state.policy_has_product_indicator:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.TH_COV_PHA RESULTCOV_MOD')
        state.sql_parts.append('    ON RESULTCOV_MOD.CK_SYS_CD = RESULTCOV.CK_SYS_CD')
        state.sql_parts.append('    AND RESULTCOV_MOD.CK_CMP_CD = RESULTCOV.CK_CMP_CD')
        state.sql_parts.append('    AND RESULTCOV_MOD.TCH_POL_ID = RESULTCOV.TCH_POL_ID')
        state.sql_parts.append('    AND RESULTCOV_MOD.COV_PHA_NBR = RESULTCOV.COV_PHA_NBR')
        state.sql_parts.append(f'    AND RESULTCOV_MOD.AN_PRD_ID IN ({in_list(state.policy_product_indicator_codes)})')
    if state.has_52r or state.disp_replacement_pol:
        state._52r_join = 'INNER JOIN' if state.has_52r else 'LEFT OUTER JOIN'
        state.sql_parts.append(f'  {state._52r_join} {state.schema}.TH_USER_REPLACEMENT USERDEF_52R')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = USERDEF_52R.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = USERDEF_52R.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = USERDEF_52R.TCH_POL_ID')
    if state.has_skipped_rein:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_COV_SKIPPED_PER REINSTATEMENT')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = REINSTATEMENT.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = REINSTATEMENT.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = REINSTATEMENT.TCH_POL_ID')
    if state.has_slr or state.disp_slr_bill_form:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_LN_RPY_TRM SLR_BILL_CONTROL')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = SLR_BILL_CONTROL.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = SLR_BILL_CONTROL.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = SLR_BILL_CONTROL.TCH_POL_ID')
    if state.has_overloan or state.disp_trad_overloan:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.TH_BAS_POL POLICY1_MOD')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = POLICY1_MOD.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = POLICY1_MOD.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = POLICY1_MOD.TCH_POL_ID')
    if state.has_term_entry or state.disp_term_date:
        state._td_join = 'INNER JOIN' if state.has_term_entry else 'LEFT OUTER JOIN'
        state.sql_parts.append(f'  {state._td_join} TERMINATION_DATES AS TD')
        state.sql_parts.append('    ON POLICY1.CK_CMP_CD = TD.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = TD.TCH_POL_ID')
        state.sql_parts.append(f'    AND {_terminated_policy_predicate()}')
    if state.has_term_both:
        state.sql_parts.append('  LEFT OUTER JOIN TERMINATION_BOTH_DATES AS TDB')
        state.sql_parts.append('    ON POLICY1.CK_CMP_CD = TDB.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = TDB.TCH_POL_ID')
        state.sql_parts.append(f'    AND {_terminated_policy_predicate()}')


def build_step_015(state: BuildState) -> None:
    if state.disp_conversion_dates:
        state.sql_parts.append('  LEFT OUTER JOIN CONVERSION_SC SC')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = SC.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = SC.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = SC.TCH_POL_ID')
        state.sql_parts.append('    AND SC.SC_ROW = 1')
    if state.disp_post_conversion:
        state.sql_parts.append('  LEFT OUTER JOIN POST_CONVERSION PC')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = PC.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = PC.SOURCE_CMP_CODE')
        state.sql_parts.append('    AND POLICY1.CK_POLICY_NBR = PC.SOURCE_POLICY_NBR')
        state.sql_parts.append("    AND POLICY1.LST_ETR_CD = 'O'")
    if state.has_77_segment or state.disp_policy_debt:
        state._loan_join = 'INNER JOIN' if state.has_77_segment else 'LEFT OUTER JOIN'
        state.sql_parts.append(f'  {state._loan_join} ALL_LOANS')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = ALL_LOANS.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = ALL_LOANS.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = ALL_LOANS.TCH_POL_ID')
        if state.has_77_segment and state.has_preferred_loan:
            state.sql_parts.append("    AND ALL_LOANS.PRF_LN_IND = '1'")
        state._debt_join = 'INNER JOIN' if state.has_77_segment else 'LEFT OUTER JOIN'
        state.sql_parts.append(f'  {state._debt_join} POLICYDEBT')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = POLICYDEBT.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = POLICYDEBT.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = POLICYDEBT.TCH_POL_ID')
    if state.has_change_seq:
        state.sql_parts.append('  INNER JOIN CHANGE_SEGMENT')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = CHANGE_SEGMENT.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = CHANGE_SEGMENT.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = CHANGE_SEGMENT.TCH_POL_ID')
    if state.has_person_info:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.VH_POL_HAS_LOC_CLT PERSONINFO')
        state.sql_parts.append('    ON PERSONINFO.CK_SYS_CD = POLICY1.CK_SYS_CD')
        state.sql_parts.append('    AND PERSONINFO.CK_CMP_CD = POLICY1.CK_CMP_CD')
        state.sql_parts.append('    AND PERSONINFO.TCH_POL_ID = POLICY1.TCH_POL_ID')
        for state._cond in state.person_name_conds:
            state.sql_parts.append(f'    AND {state._cond}')
    if state.needs_mvval:
        state.sql_parts.append('  LEFT OUTER JOIN MVVAL')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = MVVAL.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = MVVAL.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = MVVAL.TCH_POL_ID')
    if state.disp_monthly_deduction:
        state.sql_parts.append('  LEFT OUTER JOIN MONTHLY_DED')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = MONTHLY_DED.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = MONTHLY_DED.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = MONTHLY_DED.TCH_POL_ID')
    if state.needs_iswl_gcv:
        state.sql_parts.append('  INNER JOIN ISWL_INTERPOLATED_GCV')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = ISWL_INTERPOLATED_GCV.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = ISWL_INTERPOLATED_GCV.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = ISWL_INTERPOLATED_GCV.TCH_POL_ID')
    if state.adv_glp_neg or state.disp_glp or state.has_glp_range:
        state._glp_join = 'INNER JOIN' if state.adv_glp_neg or state.has_glp_range else 'LEFT OUTER JOIN'
        state.sql_parts.append(f'  {state._glp_join} GLP')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = GLP.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = GLP.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = GLP.TCH_POL_ID')
    if state.disp_trad_cv_cov1:
        state.sql_parts.append('  LEFT OUTER JOIN INTERPOLATION_MONTHS')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID')
    if state.disp_account_value:
        state.sql_parts.append('  LEFT OUTER JOIN TRAD_CV')
        state.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = TRAD_CV.CK_SYS_CD')
        state.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = TRAD_CV.CK_CMP_CD')
        state.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = TRAD_CV.TCH_POL_ID')
    if state.has_fund_values:
        state._fid = state.adv_fund_id
        state.sql_parts.append('  INNER JOIN FUND_VALUES')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = FUND_VALUES.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = FUND_VALUES.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = FUND_VALUES.TCH_POL_ID')
        if state._fid:
            state.sql_parts.append(f"    AND FUND_VALUES.FND_ID_CD = '{esc(state._fid)}'")
    if state.adv_prem_alloc:
        state.sql_parts.append('  INNER JOIN ALLOCATION_FUNDS')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = ALLOCATION_FUNDS.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = ALLOCATION_FUNDS.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = ALLOCATION_FUNDS.TCH_POL_ID')
    if state.has_type_p:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_FND_TRS_ALC_SET ALLOCATION_P_COUNT')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = ALLOCATION_P_COUNT.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = ALLOCATION_P_COUNT.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = ALLOCATION_P_COUNT.TCH_POL_ID')
        state.sql_parts.append("    AND ALLOCATION_P_COUNT.FND_TRS_TYP_CD = 'P'")
    if state.has_type_v:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_FND_TRS_ALC_SET ALLOCATION_V_COUNT')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = ALLOCATION_V_COUNT.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = ALLOCATION_V_COUNT.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = ALLOCATION_V_COUNT.TCH_POL_ID')
        state.sql_parts.append("    AND ALLOCATION_V_COUNT.FND_TRS_TYP_CD = 'V'")
