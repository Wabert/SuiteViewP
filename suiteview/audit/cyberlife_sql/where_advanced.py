"""CyberLife SQL where advanced section builders."""
from __future__ import annotations

from suiteview.audit.cyberlife_sql.helpers import (
    cease_code_predicate,
)
from suiteview.audit.cyberlife_sql.state import QueryContext, SqlParts
from suiteview.audit.sql_helpers import (
    add_date_range,
    add_decimal_range,
    add_int_range,
    esc,
    in_list,
    selected_codes,
    today_str,
)


def add_advanced_where(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.adv_orig_entry:
        ctx.codes = selected_codes(ctx.at.list_orig_entry)
        if ctx.codes:
            parts.wheres.append(f'POLICY1.OGN_ETR_CD IN ({in_list(ctx.codes)})')
    if ctx.adv_fund_lo:
        try:
            parts.wheres.append(f'FUND_VALUES.FUNDAMT >= {float(ctx.adv_fund_lo)}')
        except ValueError:
            pass
    if ctx.adv_fund_hi:
        try:
            parts.wheres.append(f'FUND_VALUES.FUNDAMT <= {float(ctx.adv_fund_hi)}')
        except ValueError:
            pass
    add_decimal_range(parts.wheres, 'MVVAL.CSV_AMT', ctx.at.rng_accum_val[0], ctx.at.rng_accum_val[1])
    add_decimal_range(parts.wheres, 'SHADOWAV.TAR_PRM_AMT', ctx.at.rng_shadow_acct[0], ctx.at.rng_shadow_acct[1])
    add_decimal_range(parts.wheres, 'COVSUMMARY.TOTAL_SA', ctx.at.rng_curr_spec_amt[0], ctx.at.rng_curr_spec_amt[1])
    add_decimal_range(parts.wheres, 'ACCUMMTP.TAR_PRM_AMT', ctx.at.rng_accum_mtp[0], ctx.at.rng_accum_mtp[1])
    add_decimal_range(parts.wheres, 'ACCUMGLP.TAR_PRM_AMT', ctx.at.rng_accum_glp[0], ctx.at.rng_accum_glp[1])
    add_decimal_range(parts.wheres, 'GLP.GLP_VALUE', ctx.at.rng_glp[0], ctx.at.rng_glp[1])
    add_decimal_range(parts.wheres, 'GSP.GSP_VALUE', ctx.at.rng_gsp[0], ctx.at.rng_gsp[1])
    add_int_range(parts.wheres, 'ALLOCATION_P_COUNT.FND_ALC_SEQ_NBR', ctx.at.rng_type_p[0], ctx.at.rng_type_p[1])
    add_int_range(parts.wheres, 'ALLOCATION_V_COUNT.FND_ALC_SEQ_NBR', ctx.at.rng_type_v[0], ctx.at.rng_type_v[1])
    if ctx.adv_cirf_val:
        ctx._cirf = esc(ctx.adv_cirf_val.upper())
        ctx._cirf_col = 'UPPER(TRIM(FFC_SRCH.CUR_ITS_RT_SER_NBR))'
        if ctx.adv_cirf_match == 'Exact':
            ctx._cirf_pred = f"{ctx._cirf_col} = '{ctx._cirf}'"
        else:
            ctx._cirf_pred = f"{ctx._cirf_col} LIKE '%{ctx._cirf}%'"
        parts.wheres.append(f'EXISTS (SELECT 1 FROM {ctx.schema}.LH_COV_FXD_FND_CTL FFC_SRCH WHERE FFC_SRCH.CK_SYS_CD = POLICY1.CK_SYS_CD AND FFC_SRCH.CK_CMP_CD = POLICY1.CK_CMP_CD AND FFC_SRCH.TCH_POL_ID = POLICY1.TCH_POL_ID AND {ctx._cirf_pred})')
    if ctx.multi_base_covs:
        parts.wheres.append('(COVSUMMARY.BASECOVCOUNT > 1)')
    if ctx.is_mdo:
        parts.wheres.append("SUBSTR(POLICY1.USR_RES_CD,1,1) = 'Y'")
    if ctx.in_conversion:
        ctx._today = today_str()
        ctx._dur = f"TRUNCATE(MONTHS_BETWEEN('{ctx._today}', COVERAGE1.ISSUE_DT) / 12, 0)"
        ctx._att_age = f'(COVERAGE1.INS_ISS_AGE + {ctx._dur})'
        parts.wheres.append(f"(CASE WHEN (UPDF.CONVERSION_PERIOD = 0 AND {ctx._att_age} < UPDF.CONVERSION_AGE) OR (UPDF.CONVERSION_PERIOD > 0 AND {ctx._dur} < UPDF.CONVERSION_PERIOD AND {ctx._att_age} < UPDF.CONVERSION_AGE) THEN 'TRUE' ELSE 'FALSE' END) = 'TRUE'")
    if ctx.cov_val_classes:
        parts.wheres.append(f'COVERAGE1.INS_CLS_CD IN ({in_list(ctx.cov_val_classes)})')
    elif ctx.cov_val_class:
        parts.wheres.append(f"COVERAGE1.INS_CLS_CD = '{esc(ctx.cov_val_class)}'")
    if ctx.cov_val_base:
        parts.wheres.append(f"COVERAGE1.PLN_BSE_SRE_CD = '{esc(ctx.cov_val_base)}'")
    if ctx.cov_val_sub:
        parts.wheres.append(f"COVERAGE1.LIF_PLN_SUB_SRE_CD = '{esc(ctx.cov_val_sub)}'")
    if ctx.cov_val_mort:
        parts.wheres.append(f"COVERAGE1.MTL_FCT_TBL_CD = '{esc(ctx.cov_val_mort)}'")
    if ctx.cov_rpu_mort:
        parts.wheres.append(f"COVERAGE1.NSP_RPU_TBL_CD = '{esc(ctx.cov_rpu_mort)}'")
    if ctx.cov_eti_mort:
        parts.wheres.append(f"COVERAGE1.NSP_EI_TBL_CD = '{esc(ctx.cov_eti_mort)}'")
    if ctx.cov_nfo_rate:
        try:
            parts.wheres.append(f'COVERAGE1.NSP_ITS_RT = {float(ctx.cov_nfo_rate)}')
        except ValueError:
            pass
    if ctx.cov_val_class_ne:
        parts.wheres.append('COVERAGE1.INS_CLS_CD <> SUBSTR(COVERAGE1.PLN_DES_SER_CD,3,1)')
    if ctx.cov_cv_rate:
        parts.wheres.append('(COVERAGE1.LOW_DUR_1_CSV_AMT > 0 OR COVERAGE1.LOW_DUR_2_CSV_AMT > 0)')
    if ctx.cov_gcv_gt_cv:
        parts.wheres.append('(ISWL_INTERPOLATED_GCV.ISWL_GCV >= MVVAL.CSV_AMT)')
    if ctx.cov_gcv_lt_cv:
        parts.wheres.append('(ISWL_INTERPOLATED_GCV.ISWL_GCV <= MVVAL.CSV_AMT)')
    if ctx.cov_gio:
        parts.wheres.append("MODCOVSALL.OPT_EXER_IND = 'Y'")
    if ctx.cov_cola:
        parts.wheres.append("MODCOVSALL.COLA_INCR_IND = '1'")
    if ctx.cov_non_trad:
        ctx.codes = selected_codes(ctx.covt.list_non_trad)
        if ctx.codes:
            parts.wheres.append(f'POLICY1.NON_TRD_POL_IND IN ({in_list(ctx.codes)})')


def assemble_sql(ctx: QueryContext, parts: SqlParts) -> None:
    add_decimal_range(parts.wheres, 'COVSUMMARY.TOTAL_SA', ctx.covt.txt_spec_amt_lo, ctx.covt.txt_spec_amt_hi)
    if ctx.cov_init_term:
        ctx.codes = selected_codes(ctx.covt.list_init_term)
        if ctx.codes:
            parts.wheres.append(f'COVERAGE1.INT_RNL_PER IN ({in_list(ctx.codes)})')
    if ctx.cov_base_plancode:
        parts.wheres.append(f"COVERAGE1.PLN_DES_SER_CD = '{esc(ctx.cov_base_plancode)}'")
    if ctx.cov_base_prod_line:
        ctx.code = ctx.cov_base_prod_line[0]
        parts.wheres.append(f"COVERAGE1.PRD_LIN_TYP_CD = '{esc(ctx.code)}'")
    if ctx.cov_base_form_number:
        parts.wheres.append(f"COVERAGE1.POL_FRM_NBR LIKE '{esc(ctx.cov_base_form_number)}%'")
    if ctx.cov_base_sex02:
        ctx.code = ctx.cov_base_sex02[0]
        parts.wheres.append(f"COVERAGE1.INS_SEX_CD = '{esc(ctx.code)}'")
    if ctx.cov_base_person:
        ctx.code = ctx.cov_base_person[:2]
        parts.wheres.append(f"COVERAGE1.PRS_CD = '{esc(ctx.code)}'")
    if ctx.cov_base_lives_cov:
        ctx.code = ctx.cov_base_lives_cov[0]
        parts.wheres.append(f"COVERAGE1.LIVES_COV_CD = '{esc(ctx.code)}'")
    if ctx.cov_base_change_type:
        ctx.code = ctx.cov_base_change_type[0]
        parts.wheres.append(f"COVERAGE1.NXT_CHG_TYP_CD = '{esc(ctx.code)}'")
    ctx._cease_pred = cease_code_predicate('COVERAGE1.CEA_REA_CD', ctx.cov_base_cease_code)
    if ctx._cease_pred:
        parts.wheres.append(ctx._cease_pred)
    add_date_range(parts.wheres, 'COVERAGE1.ISSUE_DT', ctx._bw['issue_date_lo'], ctx._bw['issue_date_hi'])
    add_date_range(parts.wheres, 'COVERAGE1.NXT_CHG_DT', ctx._bw['change_date_lo'], ctx._bw['change_date_hi'])
    if ctx.cov_base_prod_ind:
        ctx.code = ctx.cov_base_prod_ind[0]
        parts.wheres.append(f"MODCOV1.AN_PRD_ID = '{esc(ctx.code)}'")
    if ctx.cov_base_cola_ind:
        parts.wheres.append(f"MODCOV1.COLA_INCR_IND = '{esc(ctx.cov_base_cola_ind)}'")
    if ctx.cov_base_gio_fio:
        if ctx.cov_base_gio_fio.lower() == 'blank':
            parts.wheres.append("MODCOV1.OPT_EXER_IND = ''")
        else:
            parts.wheres.append(f"MODCOV1.OPT_EXER_IND = '{esc(ctx.cov_base_gio_fio)}'")
    if ctx.cov_base_rateclass:
        ctx.code = ctx.cov_base_rateclass[0]
        parts.wheres.append(f"COV1_RENEWALS.RT_CLS_CD = '{esc(ctx.code)}'")
    if ctx.cov_base_sex67:
        ctx.code = ctx.cov_base_sex67[0]
        parts.wheres.append(f"COV1_RENEWALS.RT_SEX_CD = '{esc(ctx.code)}'")
    add_decimal_range(parts.wheres, 'COVERAGE1.COV_VPU_AMT', ctx._bw['vpu_lo'], ctx._bw['vpu_hi'])
    add_decimal_range(parts.wheres, '(REAL(COVERAGE1.COV_UNT_QTY) * REAL(COVERAGE1.COV_VPU_AMT))', ctx._bw['spec_amt_lo'], ctx._bw['spec_amt_hi'])
    if ctx.coverage_level:
        if ctx.coverage_scope == 'Cov 1 only':
            parts.wheres.append('RESULTCOV.COV_PHA_NBR = 1')
        elif ctx.coverage_scope == 'Covs 2+ only':
            parts.wheres.append('RESULTCOV.COV_PHA_NBR > 1')
        ctx.rider_match_aliases = []
        if ctx.rider1_info['active']:
            ctx.rider_match_aliases.append('RIDER1')
        if ctx.rider2_info['active']:
            ctx.rider_match_aliases.append('RIDER2')
        if ctx.rider_match_aliases:
            ctx.checks = [f'RESULTCOV.COV_PHA_NBR = {alias}.COV_PHA_NBR' for alias in ctx.rider_match_aliases]
            parts.wheres.append('(' + ' OR '.join(ctx.checks) + ')')
    if parts.wheres:
        parts.sql_parts.append('WHERE ' + parts.wheres[0])
        for ctx.w in parts.wheres[1:]:
            parts.sql_parts.append(f'  AND {ctx.w}')
    if ctx.max_count_text and ctx.max_count_text.isdigit():
        parts.sql_parts.append(f'FETCH FIRST {ctx.max_count_text} ROWS ONLY')
    elif ctx.max_count_text == '':
        pass
    else:
        parts.sql_parts.append('FETCH FIRST 25 ROWS ONLY')
    parts.result = '\n'.join(parts.sql_parts)

