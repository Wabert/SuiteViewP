"""CyberLife SQL where advanced section builders."""
from __future__ import annotations

from .common import *


def build_step_023(state: BuildState) -> None:
    if state.adv_orig_entry:
        state.codes = selected_codes(state.at.list_orig_entry)
        if state.codes:
            state.wheres.append(f'POLICY1.OGN_ETR_CD IN ({in_list(state.codes)})')
    if state.adv_fund_lo:
        try:
            state.wheres.append(f'FUND_VALUES.FUNDAMT >= {float(state.adv_fund_lo)}')
        except ValueError:
            pass
    if state.adv_fund_hi:
        try:
            state.wheres.append(f'FUND_VALUES.FUNDAMT <= {float(state.adv_fund_hi)}')
        except ValueError:
            pass
    add_decimal_range(state.wheres, 'MVVAL.CSV_AMT', state.at.rng_accum_val[0], state.at.rng_accum_val[1])
    add_decimal_range(state.wheres, 'SHADOWAV.TAR_PRM_AMT', state.at.rng_shadow_acct[0], state.at.rng_shadow_acct[1])
    add_decimal_range(state.wheres, 'COVSUMMARY.TOTAL_SA', state.at.rng_curr_spec_amt[0], state.at.rng_curr_spec_amt[1])
    add_decimal_range(state.wheres, 'ACCUMMTP.TAR_PRM_AMT', state.at.rng_accum_mtp[0], state.at.rng_accum_mtp[1])
    add_decimal_range(state.wheres, 'ACCUMGLP.TAR_PRM_AMT', state.at.rng_accum_glp[0], state.at.rng_accum_glp[1])
    add_decimal_range(state.wheres, 'GLP.GLP_VALUE', state.at.rng_glp[0], state.at.rng_glp[1])
    add_decimal_range(state.wheres, 'GSP.GSP_VALUE', state.at.rng_gsp[0], state.at.rng_gsp[1])
    add_int_range(state.wheres, 'ALLOCATION_P_COUNT.FND_ALC_SEQ_NBR', state.at.rng_type_p[0], state.at.rng_type_p[1])
    add_int_range(state.wheres, 'ALLOCATION_V_COUNT.FND_ALC_SEQ_NBR', state.at.rng_type_v[0], state.at.rng_type_v[1])
    if state.adv_cirf_val:
        state._cirf = esc(state.adv_cirf_val.upper())
        state._cirf_col = 'UPPER(TRIM(FFC_SRCH.CUR_ITS_RT_SER_NBR))'
        if state.adv_cirf_match == 'Exact':
            state._cirf_pred = f"{state._cirf_col} = '{state._cirf}'"
        else:
            state._cirf_pred = f"{state._cirf_col} LIKE '%{state._cirf}%'"
        state.wheres.append(f'EXISTS (SELECT 1 FROM {state.schema}.LH_COV_FXD_FND_CTL FFC_SRCH WHERE FFC_SRCH.CK_SYS_CD = POLICY1.CK_SYS_CD AND FFC_SRCH.CK_CMP_CD = POLICY1.CK_CMP_CD AND FFC_SRCH.TCH_POL_ID = POLICY1.TCH_POL_ID AND {state._cirf_pred})')
    if state.multi_base_covs:
        state.wheres.append('(COVSUMMARY.BASECOVCOUNT > 1)')
    if state.is_mdo:
        state.wheres.append("SUBSTR(POLICY1.USR_RES_CD,1,1) = 'Y'")
    if state.in_conversion:
        state._today = today_str()
        state._dur = f"TRUNCATE(MONTHS_BETWEEN('{state._today}', COVERAGE1.ISSUE_DT) / 12, 0)"
        state._att_age = f'(COVERAGE1.INS_ISS_AGE + {state._dur})'
        state.wheres.append(f"(CASE WHEN (UPDF.CONVERSION_PERIOD = 0 AND {state._att_age} < UPDF.CONVERSION_AGE) OR (UPDF.CONVERSION_PERIOD > 0 AND {state._dur} < UPDF.CONVERSION_PERIOD AND {state._att_age} < UPDF.CONVERSION_AGE) THEN 'TRUE' ELSE 'FALSE' END) = 'TRUE'")
    if state.cov_val_classes:
        state.wheres.append(f'COVERAGE1.INS_CLS_CD IN ({in_list(state.cov_val_classes)})')
    elif state.cov_val_class:
        state.wheres.append(f"COVERAGE1.INS_CLS_CD = '{esc(state.cov_val_class)}'")
    if state.cov_val_base:
        state.wheres.append(f"COVERAGE1.PLN_BSE_SRE_CD = '{esc(state.cov_val_base)}'")
    if state.cov_val_sub:
        state.wheres.append(f"COVERAGE1.LIF_PLN_SUB_SRE_CD = '{esc(state.cov_val_sub)}'")
    if state.cov_val_mort:
        state.wheres.append(f"COVERAGE1.MTL_FCT_TBL_CD = '{esc(state.cov_val_mort)}'")
    if state.cov_rpu_mort:
        state.wheres.append(f"COVERAGE1.NSP_RPU_TBL_CD = '{esc(state.cov_rpu_mort)}'")
    if state.cov_eti_mort:
        state.wheres.append(f"COVERAGE1.NSP_EI_TBL_CD = '{esc(state.cov_eti_mort)}'")
    if state.cov_nfo_rate:
        try:
            state.wheres.append(f'COVERAGE1.NSP_ITS_RT = {float(state.cov_nfo_rate)}')
        except ValueError:
            pass
    if state.cov_val_class_ne:
        state.wheres.append('COVERAGE1.INS_CLS_CD <> SUBSTR(COVERAGE1.PLN_DES_SER_CD,3,1)')
    if state.cov_cv_rate:
        state.wheres.append('(COVERAGE1.LOW_DUR_1_CSV_AMT > 0 OR COVERAGE1.LOW_DUR_2_CSV_AMT > 0)')
    if state.cov_gcv_gt_cv:
        state.wheres.append('(ISWL_INTERPOLATED_GCV.ISWL_GCV >= MVVAL.CSV_AMT)')
    if state.cov_gcv_lt_cv:
        state.wheres.append('(ISWL_INTERPOLATED_GCV.ISWL_GCV <= MVVAL.CSV_AMT)')
    if state.cov_gio:
        state.wheres.append("MODCOVSALL.OPT_EXER_IND = 'Y'")
    if state.cov_cola:
        state.wheres.append("MODCOVSALL.COLA_INCR_IND = '1'")
    if state.cov_non_trad:
        state.codes = selected_codes(state.covt.list_non_trad)
        if state.codes:
            state.wheres.append(f'POLICY1.NON_TRD_POL_IND IN ({in_list(state.codes)})')


def build_step_024(state: BuildState) -> None:
    add_decimal_range(state.wheres, 'COVSUMMARY.TOTAL_SA', state.covt.txt_spec_amt_lo, state.covt.txt_spec_amt_hi)
    if state.cov_init_term:
        state.codes = selected_codes(state.covt.list_init_term)
        if state.codes:
            state.wheres.append(f'COVERAGE1.INT_RNL_PER IN ({in_list(state.codes)})')
    if state.cov_base_plancode:
        state.wheres.append(f"COVERAGE1.PLN_DES_SER_CD = '{esc(state.cov_base_plancode)}'")
    if state.cov_base_prod_line:
        state.code = state.cov_base_prod_line[0]
        state.wheres.append(f"COVERAGE1.PRD_LIN_TYP_CD = '{esc(state.code)}'")
    if state.cov_base_form_number:
        state.wheres.append(f"COVERAGE1.POL_FRM_NBR LIKE '{esc(state.cov_base_form_number)}%'")
    if state.cov_base_sex02:
        state.code = state.cov_base_sex02[0]
        state.wheres.append(f"COVERAGE1.INS_SEX_CD = '{esc(state.code)}'")
    if state.cov_base_person:
        state.code = state.cov_base_person[:2]
        state.wheres.append(f"COVERAGE1.PRS_CD = '{esc(state.code)}'")
    if state.cov_base_lives_cov:
        state.code = state.cov_base_lives_cov[0]
        state.wheres.append(f"COVERAGE1.LIVES_COV_CD = '{esc(state.code)}'")
    if state.cov_base_change_type:
        state.code = state.cov_base_change_type[0]
        state.wheres.append(f"COVERAGE1.NXT_CHG_TYP_CD = '{esc(state.code)}'")
    state._cease_pred = _cease_code_predicate('COVERAGE1.CEA_REA_CD', state.cov_base_cease_code)
    if state._cease_pred:
        state.wheres.append(state._cease_pred)
    add_date_range(state.wheres, 'COVERAGE1.ISSUE_DT', state._bw['issue_date_lo'], state._bw['issue_date_hi'])
    add_date_range(state.wheres, 'COVERAGE1.NXT_CHG_DT', state._bw['change_date_lo'], state._bw['change_date_hi'])
    if state.cov_base_prod_ind:
        state.code = state.cov_base_prod_ind[0]
        state.wheres.append(f"MODCOV1.AN_PRD_ID = '{esc(state.code)}'")
    if state.cov_base_cola_ind:
        state.wheres.append(f"MODCOV1.COLA_INCR_IND = '{esc(state.cov_base_cola_ind)}'")
    if state.cov_base_gio_fio:
        if state.cov_base_gio_fio.lower() == 'blank':
            state.wheres.append("MODCOV1.OPT_EXER_IND = ''")
        else:
            state.wheres.append(f"MODCOV1.OPT_EXER_IND = '{esc(state.cov_base_gio_fio)}'")
    if state.cov_base_rateclass:
        state.code = state.cov_base_rateclass[0]
        state.wheres.append(f"COV1_RENEWALS.RT_CLS_CD = '{esc(state.code)}'")
    if state.cov_base_sex67:
        state.code = state.cov_base_sex67[0]
        state.wheres.append(f"COV1_RENEWALS.RT_SEX_CD = '{esc(state.code)}'")
    add_decimal_range(state.wheres, 'COVERAGE1.COV_VPU_AMT', state._bw['vpu_lo'], state._bw['vpu_hi'])
    add_decimal_range(state.wheres, '(REAL(COVERAGE1.COV_UNT_QTY) * REAL(COVERAGE1.COV_VPU_AMT))', state._bw['spec_amt_lo'], state._bw['spec_amt_hi'])
    if state.coverage_level:
        if state.coverage_scope == 'Cov 1 only':
            state.wheres.append('RESULTCOV.COV_PHA_NBR = 1')
        elif state.coverage_scope == 'Covs 2+ only':
            state.wheres.append('RESULTCOV.COV_PHA_NBR > 1')
        state.rider_match_aliases = []
        if state.rider1_info['active']:
            state.rider_match_aliases.append('RIDER1')
        if state.rider2_info['active']:
            state.rider_match_aliases.append('RIDER2')
        if state.rider_match_aliases:
            state.checks = [f'RESULTCOV.COV_PHA_NBR = {alias}.COV_PHA_NBR' for alias in state.rider_match_aliases]
            state.wheres.append('(' + ' OR '.join(state.checks) + ')')
    if state.wheres:
        state.sql_parts.append('WHERE ' + state.wheres[0])
        for state.w in state.wheres[1:]:
            state.sql_parts.append(f'  AND {state.w}')
    if state.max_count_text and state.max_count_text.isdigit():
        state.sql_parts.append(f'FETCH FIRST {state.max_count_text} ROWS ONLY')
    elif state.max_count_text == '':
        pass
    else:
        state.sql_parts.append('FETCH FIRST 25 ROWS ONLY')
    state._result = '\n'.join(state.sql_parts)
