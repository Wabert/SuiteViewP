"""CyberLife SQL select display section builders."""
from __future__ import annotations

from suiteview.audit.cyberlife_sql.helpers import (
    terminated_policy_predicate,
)
from suiteview.audit.cyberlife_sql.state import QueryContext, SqlParts
from suiteview.audit.sql_helpers import (
    esc,
    in_list,
)


def add_rider_selects_and_from(ctx: QueryContext, parts: SqlParts) -> None:

    def _rider_select_lines(info: dict, alias: str, label: str) -> list:
        lines = []
        if not (ctx.coverage_level and info['active']):
            return lines
        covmod_alias = f'{alias}COVMOD'
        rnl_alias = f'{alias}_RENEWALS'
        tr_alias = f'{alias}_TABLE_RATING'
        fe_alias = f'{alias}_FLAT_EXTRA'
        if info['plancode']:
            lines.append(f'  , {alias}.PLN_DES_SER_CD {label}Plancode')
        if info['class_codes']:
            lines.append(f'  , {alias}.INS_CLS_CD {label}Class')
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
    parts.sql_parts.extend(_rider_select_lines(ctx.rider1_info, 'RIDER1', 'Rider1'))
    parts.sql_parts.extend(_rider_select_lines(ctx.rider2_info, 'RIDER2', 'Rider2'))
    parts.sql_parts.extend(ctx.custom_select_lines)
    parts.sql_parts.extend(ctx.segment52_select_lines)
    parts.sql_parts.append(f'FROM {ctx.schema}.LH_BAS_POL POLICY1')
    if ctx.needs_covsall:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_COV_PHA COVSALL')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = COVSALL.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = COVSALL.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = COVSALL.TCH_POL_ID')
    parts.sql_parts.append('  INNER JOIN COVERAGE1')
    parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = COVERAGE1.CK_SYS_CD')
    parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = COVERAGE1.CK_CMP_CD')
    parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = COVERAGE1.TCH_POL_ID')
    if ctx.coverage_level:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_COV_PHA RESULTCOV')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = RESULTCOV.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = RESULTCOV.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = RESULTCOV.TCH_POL_ID')
    parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.TH_USER_GENERIC USERGEN')
    parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = USERGEN.CK_SYS_CD')
    parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = USERGEN.CK_CMP_CD')
    parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = USERGEN.TCH_POL_ID')
    if ctx.disp_trad_rates:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_FXD_PRM_POL FXD_PRM')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = FXD_PRM.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = FXD_PRM.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = FXD_PRM.TCH_POL_ID')
    if ctx.disp_bill_mode:
        parts.sql_parts.append('  LEFT OUTER JOIN BILLMODE_POOL')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = BILLMODE_POOL.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = BILLMODE_POOL.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = BILLMODE_POOL.TCH_POL_ID')
    if ctx.needs_covsummary:
        cov_join = 'INNER JOIN' if ctx.multi_base_covs else 'LEFT OUTER JOIN'
        parts.sql_parts.append(f'  {cov_join} COVSUMMARY')
        parts.sql_parts.append('    ON COVSUMMARY.CK_SYS_CD = POLICY1.CK_SYS_CD')
        parts.sql_parts.append('    AND COVSUMMARY.CK_CMP_CD = POLICY1.CK_CMP_CD')
        parts.sql_parts.append('    AND COVSUMMARY.TCH_POL_ID = POLICY1.TCH_POL_ID')


def add_policy_joins(ctx: QueryContext, parts: SqlParts) -> None:
    _add_policy_core_detail_joins(ctx, parts)
    _add_policy_modifier_joins(ctx, parts)
    _add_policy_status_joins(ctx, parts)


def _add_policy_core_detail_joins(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.needs_premwd_face:
        parts.sql_parts.append('  INNER JOIN PREMWD_FACE')
        parts.sql_parts.append('    ON PREMWD_FACE.CK_SYS_CD = POLICY1.CK_SYS_CD')
        parts.sql_parts.append('    AND PREMWD_FACE.CK_CMP_CD = POLICY1.CK_CMP_CD')
        parts.sql_parts.append('    AND PREMWD_FACE.TCH_POL_ID = POLICY1.TCH_POL_ID')
    if ctx.in_conversion or ctx.disp_conv_credit or ctx.disp_within_conv or ctx.disp_conv_period:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.TH_USER_PDF UPDF')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = UPDF.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = UPDF.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = UPDF.TCH_POL_ID')
        parts.sql_parts.append('    AND UPDF.TYPE_SEQUENCE = 1')
    if ctx.disp_insured1_info:
        parts.sql_parts.append('  LEFT OUTER JOIN INSURED1_INFO')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = INSURED1_INFO.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = INSURED1_INFO.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = INSURED1_INFO.TCH_POL_ID')
    if ctx.needs_grace_table:
        parts.sql_parts.append('  INNER JOIN GRACE_TABLE')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = GRACE_TABLE.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = GRACE_TABLE.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = GRACE_TABLE.TCH_POL_ID')
    if ctx.has_tamra or ctx.disp_tamra:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_TAMRA_7_PY_PER TAMRA')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = TAMRA.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = TAMRA.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = TAMRA.TCH_POL_ID')
    if ctx.has_pol_totals:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_POL_TOTALS POLICY_TOTALS')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = POLICY_TOTALS.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = POLICY_TOTALS.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = POLICY_TOTALS.TCH_POL_ID')
    if ctx.needs_pol_yr_tot:
        parts.sql_parts.append('  LEFT OUTER JOIN LH_POL_YR_TOT_at_MaxDuration')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = LH_POL_YR_TOT_at_MaxDuration.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = LH_POL_YR_TOT_at_MaxDuration.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = LH_POL_YR_TOT_at_MaxDuration.TCH_POL_ID')


def _add_policy_modifier_joins(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.has_nontrad or ctx.disp_db_option or ctx.disp_def_life_ins or ctx.adv_prem_wd_gt_face:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_NON_TRD_POL NONTRAD')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = NONTRAD.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = NONTRAD.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = NONTRAD.TCH_POL_ID')
    if ctx.has_modcovsall:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.TH_COV_PHA MODCOVSALL')
        parts.sql_parts.append('    ON MODCOVSALL.CK_SYS_CD = COVSALL.CK_SYS_CD')
        parts.sql_parts.append('    AND MODCOVSALL.CK_CMP_CD = COVSALL.CK_CMP_CD')
        parts.sql_parts.append('    AND MODCOVSALL.TCH_POL_ID = COVSALL.TCH_POL_ID')
        parts.sql_parts.append('    AND MODCOVSALL.COV_PHA_NBR = COVSALL.COV_PHA_NBR')
        if ctx.policy_has_product_indicator:
            parts.sql_parts.append(f'    AND MODCOVSALL.AN_PRD_ID IN ({in_list(ctx.policy_product_indicator_codes)})')
    if ctx.coverage_level and ctx.policy_has_product_indicator:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.TH_COV_PHA RESULTCOV_MOD')
        parts.sql_parts.append('    ON RESULTCOV_MOD.CK_SYS_CD = RESULTCOV.CK_SYS_CD')
        parts.sql_parts.append('    AND RESULTCOV_MOD.CK_CMP_CD = RESULTCOV.CK_CMP_CD')
        parts.sql_parts.append('    AND RESULTCOV_MOD.TCH_POL_ID = RESULTCOV.TCH_POL_ID')
        parts.sql_parts.append('    AND RESULTCOV_MOD.COV_PHA_NBR = RESULTCOV.COV_PHA_NBR')
        parts.sql_parts.append(f'    AND RESULTCOV_MOD.AN_PRD_ID IN ({in_list(ctx.policy_product_indicator_codes)})')
    if ctx.has_52r or ctx.disp_replacement_pol:
        join_type = 'INNER JOIN' if ctx.has_52r else 'LEFT OUTER JOIN'
        parts.sql_parts.append(f'  {join_type} {ctx.schema}.TH_USER_REPLACEMENT USERDEF_52R')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = USERDEF_52R.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = USERDEF_52R.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = USERDEF_52R.TCH_POL_ID')
    if ctx.has_skipped_rein:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_COV_SKIPPED_PER REINSTATEMENT')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = REINSTATEMENT.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = REINSTATEMENT.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = REINSTATEMENT.TCH_POL_ID')


def _add_policy_status_joins(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.has_slr or ctx.disp_slr_bill_form:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_LN_RPY_TRM SLR_BILL_CONTROL')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = SLR_BILL_CONTROL.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = SLR_BILL_CONTROL.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = SLR_BILL_CONTROL.TCH_POL_ID')
    if ctx.has_overloan or ctx.disp_trad_overloan:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.TH_BAS_POL POLICY1_MOD')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = POLICY1_MOD.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = POLICY1_MOD.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = POLICY1_MOD.TCH_POL_ID')
    if ctx.has_term_entry or ctx.disp_term_date:
        join_type = 'INNER JOIN' if ctx.has_term_entry else 'LEFT OUTER JOIN'
        parts.sql_parts.append(f'  {join_type} TERMINATION_DATES AS TD')
        parts.sql_parts.append('    ON POLICY1.CK_CMP_CD = TD.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = TD.TCH_POL_ID')
        parts.sql_parts.append(f'    AND {terminated_policy_predicate()}')
    if ctx.has_term_both:
        parts.sql_parts.append('  LEFT OUTER JOIN TERMINATION_BOTH_DATES AS TDB')
        parts.sql_parts.append('    ON POLICY1.CK_CMP_CD = TDB.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = TDB.TCH_POL_ID')
        parts.sql_parts.append(f'    AND {terminated_policy_predicate()}')


def add_value_joins(ctx: QueryContext, parts: SqlParts) -> None:
    _add_conversion_and_debt_joins(ctx, parts)
    _add_person_and_value_joins(ctx, parts)
    _add_target_and_allocation_joins(ctx, parts)


def _add_conversion_and_debt_joins(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.disp_conversion_dates:
        parts.sql_parts.append('  LEFT OUTER JOIN CONVERSION_SC SC')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = SC.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = SC.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = SC.TCH_POL_ID')
        parts.sql_parts.append('    AND SC.SC_ROW = 1')
    if ctx.disp_post_conversion:
        parts.sql_parts.append('  LEFT OUTER JOIN POST_CONVERSION PC')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = PC.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = PC.SOURCE_CMP_CODE')
        parts.sql_parts.append('    AND POLICY1.CK_POLICY_NBR = PC.SOURCE_POLICY_NBR')
        parts.sql_parts.append("    AND POLICY1.LST_ETR_CD = 'O'")
    if ctx.has_77_segment or ctx.disp_policy_debt:
        loan_join = 'INNER JOIN' if ctx.has_77_segment else 'LEFT OUTER JOIN'
        parts.sql_parts.append(f'  {loan_join} ALL_LOANS')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = ALL_LOANS.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = ALL_LOANS.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = ALL_LOANS.TCH_POL_ID')
        if ctx.has_77_segment and ctx.has_preferred_loan:
            parts.sql_parts.append("    AND ALL_LOANS.PRF_LN_IND = '1'")
        debt_join = 'INNER JOIN' if ctx.has_77_segment else 'LEFT OUTER JOIN'
        parts.sql_parts.append(f'  {debt_join} POLICYDEBT')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = POLICYDEBT.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = POLICYDEBT.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = POLICYDEBT.TCH_POL_ID')


def _add_person_and_value_joins(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.has_change_seq:
        parts.sql_parts.append('  INNER JOIN CHANGE_SEGMENT')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = CHANGE_SEGMENT.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = CHANGE_SEGMENT.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = CHANGE_SEGMENT.TCH_POL_ID')
    if ctx.has_person_info:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.VH_POL_HAS_LOC_CLT PERSONINFO')
        parts.sql_parts.append('    ON PERSONINFO.CK_SYS_CD = POLICY1.CK_SYS_CD')
        parts.sql_parts.append('    AND PERSONINFO.CK_CMP_CD = POLICY1.CK_CMP_CD')
        parts.sql_parts.append('    AND PERSONINFO.TCH_POL_ID = POLICY1.TCH_POL_ID')
        for condition in ctx.person_name_conds:
            parts.sql_parts.append(f'    AND {condition}')
    if ctx.needs_mvval:
        parts.sql_parts.append('  LEFT OUTER JOIN MVVAL')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = MVVAL.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = MVVAL.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = MVVAL.TCH_POL_ID')
    if ctx.disp_monthly_deduction:
        parts.sql_parts.append('  LEFT OUTER JOIN MONTHLY_DED')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = MONTHLY_DED.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = MONTHLY_DED.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = MONTHLY_DED.TCH_POL_ID')
    if ctx.needs_iswl_gcv:
        parts.sql_parts.append('  INNER JOIN ISWL_INTERPOLATED_GCV')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = ISWL_INTERPOLATED_GCV.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = ISWL_INTERPOLATED_GCV.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = ISWL_INTERPOLATED_GCV.TCH_POL_ID')
    if ctx.adv_glp_neg or ctx.disp_glp or ctx.has_glp_range:
        glp_join = 'INNER JOIN' if ctx.adv_glp_neg or ctx.has_glp_range else 'LEFT OUTER JOIN'
        parts.sql_parts.append(f'  {glp_join} GLP')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = GLP.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = GLP.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = GLP.TCH_POL_ID')
    if ctx.disp_trad_cv_cov1:
        parts.sql_parts.append('  LEFT OUTER JOIN INTERPOLATION_MONTHS')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID')
    if ctx.disp_account_value:
        parts.sql_parts.append('  LEFT OUTER JOIN TRAD_CV')
        parts.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = TRAD_CV.CK_SYS_CD')
        parts.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = TRAD_CV.CK_CMP_CD')
        parts.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = TRAD_CV.TCH_POL_ID')


def _add_target_and_allocation_joins(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.has_fund_values:
        parts.sql_parts.append('  INNER JOIN FUND_VALUES')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = FUND_VALUES.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = FUND_VALUES.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = FUND_VALUES.TCH_POL_ID')
        if ctx.adv_fund_id:
            parts.sql_parts.append(f"    AND FUND_VALUES.FND_ID_CD = '{esc(ctx.adv_fund_id)}'")
    if ctx.adv_prem_alloc:
        parts.sql_parts.append('  INNER JOIN ALLOCATION_FUNDS')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = ALLOCATION_FUNDS.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = ALLOCATION_FUNDS.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = ALLOCATION_FUNDS.TCH_POL_ID')
    if ctx.has_type_p:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_FND_TRS_ALC_SET ALLOCATION_P_COUNT')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = ALLOCATION_P_COUNT.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = ALLOCATION_P_COUNT.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = ALLOCATION_P_COUNT.TCH_POL_ID')
        parts.sql_parts.append("    AND ALLOCATION_P_COUNT.FND_TRS_TYP_CD = 'P'")
    if ctx.has_type_v:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_FND_TRS_ALC_SET ALLOCATION_V_COUNT')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = ALLOCATION_V_COUNT.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = ALLOCATION_V_COUNT.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = ALLOCATION_V_COUNT.TCH_POL_ID')
        parts.sql_parts.append("    AND ALLOCATION_V_COUNT.FND_TRS_TYP_CD = 'V'")
