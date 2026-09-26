"""CyberLife SQL ctes policy section builders."""
from __future__ import annotations

from suiteview.audit.cyberlife_sql.ctes import (
    _conversion_sc_cte,
    _post_conversion_cte,
)
from suiteview.audit.cyberlife_sql.state import QueryContext, SqlParts
from suiteview.audit.sql_helpers import (
    normalize_date,
)


def add_policy2_ctes(ctx: QueryContext, parts: SqlParts) -> None:
    ctx.adv_gcv_lt_cv = ctx.at.chk_gcv_lt_cv.isChecked()
    ctx.adv_prem_wd_gt_face = ctx.at.chk_prem_wd_gt_face.isChecked()
    ctx.adv_grace_rule = bool(ctx.at.chk_grace_rule.isChecked() and ctx.at.list_grace_rule.selectedItems())
    ctx.adv_db_option = bool(ctx.at.chk_db_option.isChecked() and ctx.at.list_db_option.selectedItems())
    ctx.adv_orig_entry = bool(ctx.at.chk_orig_entry.isChecked() and ctx.at.list_orig_entry.selectedItems())
    ctx.adv_prem_alloc = bool(ctx.at.chk_prem_alloc.isChecked() and ctx.at.list_prem_alloc.selectedItems())
    ctx.adv_fund_id = ctx.at.txt_fund_id.text().strip()
    ctx.adv_fund_lo = ctx.at.txt_fund_lo.text().strip()
    ctx.adv_fund_hi = ctx.at.txt_fund_hi.text().strip()
    ctx.has_fund_values = bool(ctx.adv_fund_id or ctx.adv_fund_lo or ctx.adv_fund_hi)
    ctx.adv_cirf_match = ctx.at.cbo_cirf_match.currentText().strip()
    ctx.adv_cirf_val = ctx.at.txt_cirf.text().strip()
    ctx.has_accum_val = bool(ctx.at.rng_accum_val[0].text().strip() or ctx.at.rng_accum_val[1].text().strip())
    ctx.has_shadow_av = bool(ctx.at.rng_shadow_acct[0].text().strip() or ctx.at.rng_shadow_acct[1].text().strip())
    ctx.has_curr_spec_amt = bool(ctx.at.rng_curr_spec_amt[0].text().strip() or ctx.at.rng_curr_spec_amt[1].text().strip())
    ctx.has_accum_mtp = bool(ctx.at.rng_accum_mtp[0].text().strip() or ctx.at.rng_accum_mtp[1].text().strip())
    ctx.has_accum_glp_range = bool(ctx.at.rng_accum_glp[0].text().strip() or ctx.at.rng_accum_glp[1].text().strip())
    ctx.has_glp_range = bool(ctx.at.rng_glp[0].text().strip() or ctx.at.rng_glp[1].text().strip())
    ctx.has_gsp_range = bool(ctx.at.rng_gsp[0].text().strip() or ctx.at.rng_gsp[1].text().strip())
    ctx.has_type_p = bool(ctx.at.rng_type_p[0].text().strip() or ctx.at.rng_type_p[1].text().strip())
    ctx.has_type_v = bool(ctx.at.rng_type_v[0].text().strip() or ctx.at.rng_type_v[1].text().strip())
    ctx.multi_base_covs = ctx.pt.chk_multiple_base_covs.isChecked()
    ctx.is_mdo = ctx.pt.chk_is_mdo.isChecked()
    ctx.in_conversion = ctx.pt.chk_in_conversion.isChecked()
    ctx.cov_val_classes = ctx.covt.val_class.selected_values() if hasattr(ctx.covt.val_class, 'selected_values') else []
    ctx.cov_val_class = ctx.covt.val_class.text().strip()
    ctx.cov_val_base = ctx.covt.val_base.text().strip()
    ctx.cov_val_sub = ctx.covt.val_sub.text().strip()
    ctx.cov_val_mort = ctx.covt.val_mort_table.text().strip()
    ctx.cov_rpu_mort = ctx.covt.rpu_mort_table.text().strip()
    ctx.cov_eti_mort = ctx.covt.eti_mort_table.text().strip()
    ctx.cov_nfo_rate = ctx.covt.nfo_int_rate.text().strip()
    ctx.cov_val_class_ne = ctx.covt.chk_val_class_ne_plan.isChecked()
    ctx.cov_multi_base = ctx.covt.chk_multiple_base.isChecked()
    ctx.cov_gio = ctx.covt.chk_cov_gio.isChecked()
    ctx.cov_cola = ctx.covt.chk_cov_cola.isChecked()
    ctx.cov_skipped_rein = ctx.covt.chk_skipped_cov_rein.isChecked()
    ctx.cov_cv_rate = ctx.covt.chk_cv_rate_gt_zero.isChecked() or (ctx.wl_tab is not None and ctx.wl_tab.chk_cv_rate.isChecked())
    ctx.cov_gcv_gt_cv = ctx.covt.chk_gcv_gt_cv.isChecked()
    ctx.cov_gcv_lt_cv = ctx.covt.chk_gcv_lt_cv.isChecked()
    ctx.cov_non_trad = bool(ctx.covt.chk_non_trad.isChecked() and ctx.covt.list_non_trad.selectedItems())
    ctx.cov_spec_amt_lo = ctx.covt.txt_spec_amt_lo.text().strip()
    ctx.cov_spec_amt_hi = ctx.covt.txt_spec_amt_hi.text().strip()
    ctx.cov_has_spec_amt = bool(ctx.cov_spec_amt_lo or ctx.cov_spec_amt_hi)
    ctx.cov_init_term = bool(ctx.covt.chk_init_term.isChecked() and ctx.covt.list_init_term.selectedItems())
    ctx._bw = ctx.covt.base_cov_widgets
    ctx.cov_base_plancode = ctx._bw['plancode'].text().strip()
    ctx.cov_base_prod_line = ctx._bw['prod_line'].currentText().strip()
    ctx.cov_base_prod_ind = ctx._bw['prod_ind'].currentText().strip()
    ctx.cov_base_form_number = ctx._bw['form_number'].text().strip()
    ctx.cov_base_rateclass = ctx._bw['rateclass'].currentText().strip()
    ctx.cov_base_sex67 = ctx._bw['sex_code_67'].currentText().strip()
    ctx.cov_base_sex02 = ctx._bw['sex_code_02'].currentText().strip()
    ctx.cov_base_person = ctx._bw['person'].currentText().strip()
    ctx.cov_base_lives_cov = ctx._bw['lives_cov'].currentText().strip()
    ctx.cov_base_change_type = ctx._bw['change_type'].currentText().strip()
    ctx.cov_base_cease_code = ctx._bw['cease_code'].selected_values()
    ctx.cov_base_cola_ind = ctx._bw['cola_ind'].currentText().strip()
    ctx.cov_base_gio_fio = ctx._bw['gio_fio'].currentText().strip()
    ctx.cov_base_table03 = ctx._bw['table_03'].isChecked()
    ctx.cov_base_flat03 = ctx._bw['flat_03'].isChecked()
    ctx.cov_base_active_flat03 = ctx._bw['active_flat_03'].isChecked()
    ctx.cov_base_issue_lo = normalize_date(ctx._bw['issue_date_lo'].text()) or ''
    ctx.cov_base_issue_hi = normalize_date(ctx._bw['issue_date_hi'].text()) or ''
    ctx.cov_base_change_lo = normalize_date(ctx._bw['change_date_lo'].text()) or ''
    ctx.cov_base_change_hi = normalize_date(ctx._bw['change_date_hi'].text()) or ''
    ctx.cov_needs_modcov1 = bool(ctx.cov_base_prod_ind or ctx.cov_base_cola_ind or ctx.cov_base_gio_fio)
    ctx.cov_needs_renewals = bool(ctx.cov_base_rateclass or ctx.cov_base_sex67)


def collect_coverage_context(ctx: QueryContext, parts: SqlParts) -> None:

    def _rider_info(widgets: dict) -> dict:
        info = {}
        info['plancode'] = widgets['plancode'].text().strip()
        info['prod_line'] = widgets['prod_line'].currentText().strip()
        info['prod_ind'] = widgets['prod_ind'].currentText().strip()
        info['rateclass'] = widgets['rateclass'].currentText().strip()
        info['sex_code_67'] = widgets['sex_code_67'].currentText().strip()
        info['sex_code_02'] = widgets['sex_code_02'].currentText().strip()
        info['person'] = widgets['person'].currentText().strip()
        info['lives_cov'] = widgets['lives_cov'].currentText().strip()
        info['change_type'] = widgets['change_type'].currentText().strip()
        info['cease_code'] = widgets['cease_code'].selected_values()
        info['cola_ind'] = widgets['cola_ind'].currentText().strip()
        info['gio_fio'] = widgets['gio_fio'].currentText().strip()
        info['addl_plancode'] = widgets.get('addl_plancode', None)
        if info['addl_plancode'] is not None:
            info['addl_plancode'] = info['addl_plancode'].currentText().strip()
        else:
            info['addl_plancode'] = ''
        info['table_03'] = widgets['table_03'].isChecked()
        info['flat_03'] = widgets['flat_03'].isChecked()
        info['active_flat_03'] = widgets['active_flat_03'].isChecked()
        info['post_issue'] = widgets.get('post_issue', None)
        if info['post_issue'] is not None:
            info['post_issue'] = info['post_issue'].isChecked()
        else:
            info['post_issue'] = False
        info['issue_date_lo'] = normalize_date(widgets['issue_date_lo'].text()) or ''
        info['issue_date_hi'] = normalize_date(widgets['issue_date_hi'].text()) or ''
        info['change_date_lo'] = normalize_date(widgets['change_date_lo'].text()) or ''
        info['change_date_hi'] = normalize_date(widgets['change_date_hi'].text()) or ''
        info['vpu_lo'] = widgets['vpu_lo'].text().strip()
        info['vpu_hi'] = widgets['vpu_hi'].text().strip()
        info['spec_amt_lo'] = widgets['spec_amt_lo'].text().strip()
        info['spec_amt_hi'] = widgets['spec_amt_hi'].text().strip()
        info['active'] = any([info['plancode'], info['prod_line'], info['prod_ind'], info['rateclass'], info['sex_code_67'], info['sex_code_02'], info['person'], info['lives_cov'], info['change_type'], info['cease_code'], info['cola_ind'], info['gio_fio'], info['addl_plancode'], info['table_03'], info['flat_03'], info['active_flat_03'], info['post_issue'], info['issue_date_lo'], info['issue_date_hi'], info['change_date_lo'], info['change_date_hi'], info['vpu_lo'], info['vpu_hi'], info['spec_amt_lo'], info['spec_amt_hi']])
        info['needs_covmod'] = bool(info['prod_ind'] or info['cola_ind'] or info['gio_fio'])
        info['needs_renewals'] = bool(info['rateclass'] or info['sex_code_67'])
        return info
    ctx._rider_info = _rider_info
    ctx.rider1_info = ctx._rider_info(ctx.covt.rider1_widgets)
    ctx.rider2_info = ctx._rider_info(ctx.covt.rider2_widgets)
    ctx.cov_needs_modcovsall = bool(ctx.cov_gio or ctx.cov_cola)
    ctx.has_modcovsall = ctx.has_modcovsall or ctx.cov_needs_modcovsall
    ctx.has_skipped_rein = ctx.has_skipped_rein or ctx.cov_skipped_rein
    ctx.multi_base_covs = ctx.multi_base_covs or ctx.cov_multi_base
    ctx.cov_needs_covsummary = bool(ctx.cov_has_spec_amt or ctx.cov_multi_base)
    ctx.cov_needs_iswl_gcv = bool(ctx.cov_gcv_gt_cv or ctx.cov_gcv_lt_cv)
    ctx.cov_needs_mvval = bool(ctx.cov_gcv_gt_cv or ctx.cov_gcv_lt_cv)
    ctx.needs_mvval = ctx.adv_cv_corr or ctx.adv_accum_gt_prem or ctx.has_accum_val or ctx.adv_gcv_gt_cv or ctx.adv_gcv_lt_cv or ctx.cov_needs_mvval or ctx.disp_accum_value or ctx.disp_prem_ptd or ctx.disp_account_value or ctx.adv_prem_wd_gt_face
    ctx.needs_iswl_gcv = ctx.adv_gcv_gt_cv or ctx.adv_gcv_lt_cv or ctx.cov_needs_iswl_gcv
    ctx.needs_interpolation = ctx.needs_iswl_gcv or ctx.disp_trad_cv_cov1 or ctx.disp_account_value
    ctx.needs_covsummary = ctx.disp_spec_amt or ctx.multi_base_covs or ctx.adv_cv_corr or ctx.adv_sa_lt_orig or ctx.adv_sa_gt_orig or ctx.has_curr_spec_amt or ctx.needs_iswl_gcv or ctx.cov_needs_covsummary
    ctx.needs_premwd_face = ctx.adv_prem_wd_gt_face
    if ctx.needs_pol_yr_tot:
        parts.sql_parts.append(f', LH_POL_YR_TOT_withMaxDuration AS')
        parts.sql_parts.append(f'  (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, MAX(POL_YR_DUR) MAX_DURATION')
        parts.sql_parts.append(f'   FROM {ctx.schema}.LH_POL_YR_TOT')
        parts.sql_parts.append(f'   GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)')
        parts.sql_parts.append(f', LH_POL_YR_TOT_at_MaxDuration AS')
        parts.sql_parts.append(f'  (SELECT YEARTOTS.*')
        parts.sql_parts.append(f'   FROM {ctx.schema}.LH_POL_YR_TOT YEARTOTS')
        parts.sql_parts.append(f'   INNER JOIN LH_POL_YR_TOT_withMaxDuration')
        parts.sql_parts.append(f'     ON YEARTOTS.CK_SYS_CD = LH_POL_YR_TOT_withMaxDuration.CK_SYS_CD')
        parts.sql_parts.append(f'    AND YEARTOTS.CK_CMP_CD = LH_POL_YR_TOT_withMaxDuration.CK_CMP_CD')
        parts.sql_parts.append(f'    AND YEARTOTS.TCH_POL_ID = LH_POL_YR_TOT_withMaxDuration.TCH_POL_ID')
        parts.sql_parts.append(f'    AND YEARTOTS.POL_YR_DUR = LH_POL_YR_TOT_withMaxDuration.MAX_DURATION)')
    if ctx.needs_grace_table:
        parts.sql_parts.append(f', GRACE_TABLE AS')
        parts.sql_parts.append(f'  (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND')
        parts.sql_parts.append(f'   FROM {ctx.schema}.LH_NON_TRD_POL')
        parts.sql_parts.append(f'   UNION')
        parts.sql_parts.append(f'   SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND')
        parts.sql_parts.append(f'   FROM {ctx.schema}.LH_TRD_POL)')
    if ctx.disp_conversion_dates:
        parts.sql_parts.append(', ' + _conversion_sc_cte(ctx.schema))
    if ctx.disp_post_conversion:
        parts.sql_parts.append(', ' + _post_conversion_cte(ctx.schema))


def add_policy_and_coverage_ctes(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.has_term_entry or ctx.disp_term_date or ctx.has_term_both:
        parts.sql_parts.append(f', TERMINATION_TRANS AS')
        parts.sql_parts.append(f'  (SELECT FH.CK_CMP_CD, FH.TCH_POL_ID,')
        parts.sql_parts.append(f'    FH.ENTRY_DT, FH.ASOF_DT, FH.TRANS')
        parts.sql_parts.append(f'   FROM {ctx.schema}.FH_FIXED AS FH')
        parts.sql_parts.append(f"   WHERE FH.TRANS IN ('SC', 'SI', 'SF', 'TD', 'TM', 'TN', 'TL', 'TO')")
        parts.sql_parts.append(f"   AND FH.FCB0_REV_IND = '0'")
        parts.sql_parts.append(f"   AND FH.FCB2_REV_APPL_IND = '0')")
        parts.sql_parts.append(f', PRE_TERMINATION_DATES AS')
        parts.sql_parts.append(f'  (SELECT TT.CK_CMP_CD, TT.TCH_POL_ID,')
        parts.sql_parts.append(f'   MAX(TT.ENTRY_DT) AS TERM_ENTRY_DT')
        parts.sql_parts.append(f'   FROM TERMINATION_TRANS AS TT')
        parts.sql_parts.append(f'   GROUP BY TT.CK_CMP_CD, TT.TCH_POL_ID)')
        parts.sql_parts.append(f', TERMINATION_ENTRY_EFFECTIVE_DATES AS')
        parts.sql_parts.append(f'  (SELECT CK_CMP_CD, TCH_POL_ID, ENTRY_DT,')
        parts.sql_parts.append(f'    MAX(ASOF_DT) AS TERM_EFFECTIVE_DT')
        parts.sql_parts.append(f'   FROM TERMINATION_TRANS')
        parts.sql_parts.append(f'   GROUP BY CK_CMP_CD, TCH_POL_ID, ENTRY_DT)')
        parts.sql_parts.append(f', TERMINATION_ENTRY_TRANS_TYPES AS')
        parts.sql_parts.append(f'  (SELECT CK_CMP_CD, TCH_POL_ID, ENTRY_DT,')
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'SC' THEN 1 ELSE 0 END) AS HAS_SC,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'SI' THEN 1 ELSE 0 END) AS HAS_SI,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'SF' THEN 1 ELSE 0 END) AS HAS_SF,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TD' THEN 1 ELSE 0 END) AS HAS_TD,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TM' THEN 1 ELSE 0 END) AS HAS_TM,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TN' THEN 1 ELSE 0 END) AS HAS_TN,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TL' THEN 1 ELSE 0 END) AS HAS_TL,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TO' THEN 1 ELSE 0 END) AS HAS_TO")
        parts.sql_parts.append(f'   FROM TERMINATION_TRANS')
        parts.sql_parts.append(f'   GROUP BY CK_CMP_CD, TCH_POL_ID, ENTRY_DT)')
        parts.sql_parts.append(f', TERMINATION_ENTRY_DETAILS AS')
        parts.sql_parts.append(f'  (SELECT PTD.CK_CMP_CD, PTD.TCH_POL_ID, PTD.TERM_ENTRY_DT,')
        parts.sql_parts.append(f'    TED.TERM_EFFECTIVE_DT,')
        parts.sql_parts.append(f'    SUBSTR(')
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_SC = 1 THEN ', SC' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_SI = 1 THEN ', SI' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_SF = 1 THEN ', SF' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_TD = 1 THEN ', TD' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_TM = 1 THEN ', TM' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_TN = 1 THEN ', TN' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_TL = 1 THEN ', TL' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_TO = 1 THEN ', TO' ELSE '' END,")
        parts.sql_parts.append(f'      3) AS TERM_TRANS_TYPES')
        parts.sql_parts.append(f'   FROM PRE_TERMINATION_DATES AS PTD')
        parts.sql_parts.append(f'   INNER JOIN TERMINATION_ENTRY_EFFECTIVE_DATES AS TED')
        parts.sql_parts.append(f'     ON PTD.CK_CMP_CD = TED.CK_CMP_CD')
        parts.sql_parts.append(f'    AND PTD.TCH_POL_ID = TED.TCH_POL_ID')
        parts.sql_parts.append(f'    AND PTD.TERM_ENTRY_DT = TED.ENTRY_DT')
        parts.sql_parts.append(f'   INNER JOIN TERMINATION_ENTRY_TRANS_TYPES AS TTT')
        parts.sql_parts.append(f'     ON PTD.CK_CMP_CD = TTT.CK_CMP_CD')
        parts.sql_parts.append(f'    AND PTD.TCH_POL_ID = TTT.TCH_POL_ID')
        parts.sql_parts.append(f'    AND PTD.TERM_ENTRY_DT = TTT.ENTRY_DT)')
        ctx._term_lo = normalize_date(ctx.p2t.txt_term_entry_date_lo.text()) or ''
        ctx._term_hi = normalize_date(ctx.p2t.txt_term_entry_date_hi.text()) or ''
        if ctx._term_lo or ctx._term_hi:
            ctx._tw = 'WHERE 1=1'
            if ctx._term_lo:
                ctx._tw += f" AND TERMINATION_ENTRY_DETAILS.TERM_ENTRY_DT >= '{ctx._term_lo}'"
            if ctx._term_hi:
                ctx._tw += f" AND TERMINATION_ENTRY_DETAILS.TERM_ENTRY_DT <= '{ctx._term_hi}'"
            parts.sql_parts.append(f', TERMINATION_DATES AS')
            parts.sql_parts.append(f'  (SELECT * FROM TERMINATION_ENTRY_DETAILS {ctx._tw})')
        else:
            parts.sql_parts.append(f', TERMINATION_DATES AS')
            parts.sql_parts.append(f'  (SELECT * FROM TERMINATION_ENTRY_DETAILS)')
        if ctx.has_term_both:
            parts.sql_parts.append(', TERMINATION_BOTH_DATES AS')
            parts.sql_parts.append('  (SELECT CK_CMP_CD, TCH_POL_ID, MAX(ENTRY_DT) AS TERM_ENTRY_DT')
            parts.sql_parts.append('   FROM TERMINATION_TRANS')
            parts.sql_parts.append("   WHERE ENTRY_DT < DATE('9999-12-31')")
            parts.sql_parts.append('   GROUP BY CK_CMP_CD, TCH_POL_ID)')
    if ctx.has_77_segment or ctx.disp_policy_debt:
        parts.sql_parts.append(f', ALL_LOANS AS (')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PRF_LN_IND, LN_PRI_AMT,')
        parts.sql_parts.append(f"    (CASE LN_ITS_AMT_TYP_CD WHEN '2' THEN POL_LN_ITS_AMT ELSE 0 END) LN_INT")
        parts.sql_parts.append(f"  FROM {ctx.schema}.LH_FND_VAL_LOAN WHERE MVRY_DT = '9999-12-31'")
        parts.sql_parts.append(f'  UNION')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PRF_LN_IND, LN_PRI_AMT,')
        parts.sql_parts.append(f"    (CASE LN_ITS_AMT_TYP_CD WHEN '2' THEN POL_LN_ITS_AMT ELSE 0 END) LN_INT")
        parts.sql_parts.append(f"  FROM {ctx.schema}.LH_CSH_VAL_LOAN WHERE MVRY_DT = '9999-12-31')")
        parts.sql_parts.append(f', POLICYDEBT AS (')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,')
        parts.sql_parts.append(f'    SUM(ALL_LOANS.LN_PRI_AMT) LOAN_PRINCIPLE,')
        parts.sql_parts.append(f'    SUM(ALL_LOANS.LN_INT) LOAN_ACCRUED,')
        parts.sql_parts.append(f"    SUM(CASE WHEN COALESCE(ALL_LOANS.PRF_LN_IND, '0') <> '1'")
        parts.sql_parts.append(f'      THEN ALL_LOANS.LN_PRI_AMT ELSE 0 END) REG_LOAN_PRINCIPLE,')
        parts.sql_parts.append(f"    SUM(CASE WHEN COALESCE(ALL_LOANS.PRF_LN_IND, '0') <> '1'")
        parts.sql_parts.append(f'      THEN ALL_LOANS.LN_INT ELSE 0 END) REG_LOAN_ACCRUED,')
        parts.sql_parts.append(f"    SUM(CASE WHEN ALL_LOANS.PRF_LN_IND = '1'")
        parts.sql_parts.append(f'      THEN ALL_LOANS.LN_PRI_AMT ELSE 0 END) PREF_LOAN_PRINCIPLE,')
        parts.sql_parts.append(f"    SUM(CASE WHEN ALL_LOANS.PRF_LN_IND = '1'")
        parts.sql_parts.append(f'      THEN ALL_LOANS.LN_INT ELSE 0 END) PREF_LOAN_ACCRUED')
        parts.sql_parts.append(f'  FROM ALL_LOANS')
        parts.sql_parts.append(f'  GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)')

