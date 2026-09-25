"""CyberLife SQL ctes policy section builders."""
from __future__ import annotations

from .common import *


def build_step_003(state: BuildState) -> None:
    state.adv_gcv_lt_cv = state.at.chk_gcv_lt_cv.isChecked()
    state.adv_prem_wd_gt_face = state.at.chk_prem_wd_gt_face.isChecked()
    state.adv_grace_rule = bool(state.at.chk_grace_rule.isChecked() and state.at.list_grace_rule.selectedItems())
    state.adv_db_option = bool(state.at.chk_db_option.isChecked() and state.at.list_db_option.selectedItems())
    state.adv_orig_entry = bool(state.at.chk_orig_entry.isChecked() and state.at.list_orig_entry.selectedItems())
    state.adv_prem_alloc = bool(state.at.chk_prem_alloc.isChecked() and state.at.list_prem_alloc.selectedItems())
    state.adv_fund_id = state.at.txt_fund_id.text().strip()
    state.adv_fund_lo = state.at.txt_fund_lo.text().strip()
    state.adv_fund_hi = state.at.txt_fund_hi.text().strip()
    state.has_fund_values = bool(state.adv_fund_id or state.adv_fund_lo or state.adv_fund_hi)
    state.adv_cirf_match = state.at.cbo_cirf_match.currentText().strip()
    state.adv_cirf_val = state.at.txt_cirf.text().strip()
    state.has_accum_val = bool(state.at.rng_accum_val[0].text().strip() or state.at.rng_accum_val[1].text().strip())
    state.has_shadow_av = bool(state.at.rng_shadow_acct[0].text().strip() or state.at.rng_shadow_acct[1].text().strip())
    state.has_curr_spec_amt = bool(state.at.rng_curr_spec_amt[0].text().strip() or state.at.rng_curr_spec_amt[1].text().strip())
    state.has_accum_mtp = bool(state.at.rng_accum_mtp[0].text().strip() or state.at.rng_accum_mtp[1].text().strip())
    state.has_accum_glp_range = bool(state.at.rng_accum_glp[0].text().strip() or state.at.rng_accum_glp[1].text().strip())
    state.has_glp_range = bool(state.at.rng_glp[0].text().strip() or state.at.rng_glp[1].text().strip())
    state.has_gsp_range = bool(state.at.rng_gsp[0].text().strip() or state.at.rng_gsp[1].text().strip())
    state.has_type_p = bool(state.at.rng_type_p[0].text().strip() or state.at.rng_type_p[1].text().strip())
    state.has_type_v = bool(state.at.rng_type_v[0].text().strip() or state.at.rng_type_v[1].text().strip())
    state.multi_base_covs = state.pt.chk_multiple_base_covs.isChecked()
    state.is_mdo = state.pt.chk_is_mdo.isChecked()
    state.in_conversion = state.pt.chk_in_conversion.isChecked()
    state.cov_val_classes = state.covt.val_class.selected_values() if hasattr(state.covt.val_class, 'selected_values') else []
    state.cov_val_class = state.covt.val_class.text().strip()
    state.cov_val_base = state.covt.val_base.text().strip()
    state.cov_val_sub = state.covt.val_sub.text().strip()
    state.cov_val_mort = state.covt.val_mort_table.text().strip()
    state.cov_rpu_mort = state.covt.rpu_mort_table.text().strip()
    state.cov_eti_mort = state.covt.eti_mort_table.text().strip()
    state.cov_nfo_rate = state.covt.nfo_int_rate.text().strip()
    state.cov_val_class_ne = state.covt.chk_val_class_ne_plan.isChecked()
    state.cov_multi_base = state.covt.chk_multiple_base.isChecked()
    state.cov_gio = state.covt.chk_cov_gio.isChecked()
    state.cov_cola = state.covt.chk_cov_cola.isChecked()
    state.cov_skipped_rein = state.covt.chk_skipped_cov_rein.isChecked()
    state.cov_cv_rate = state.covt.chk_cv_rate_gt_zero.isChecked() or (state.wl_tab is not None and state.wl_tab.chk_cv_rate.isChecked())
    state.cov_gcv_gt_cv = state.covt.chk_gcv_gt_cv.isChecked()
    state.cov_gcv_lt_cv = state.covt.chk_gcv_lt_cv.isChecked()
    state.cov_non_trad = bool(state.covt.chk_non_trad.isChecked() and state.covt.list_non_trad.selectedItems())
    state.cov_spec_amt_lo = state.covt.txt_spec_amt_lo.text().strip()
    state.cov_spec_amt_hi = state.covt.txt_spec_amt_hi.text().strip()
    state.cov_has_spec_amt = bool(state.cov_spec_amt_lo or state.cov_spec_amt_hi)
    state.cov_init_term = bool(state.covt.chk_init_term.isChecked() and state.covt.list_init_term.selectedItems())
    state._bw = state.covt.base_cov_widgets
    state.cov_base_plancode = state._bw['plancode'].text().strip()
    state.cov_base_prod_line = state._bw['prod_line'].currentText().strip()
    state.cov_base_prod_ind = state._bw['prod_ind'].currentText().strip()
    state.cov_base_form_number = state._bw['form_number'].text().strip()
    state.cov_base_rateclass = state._bw['rateclass'].currentText().strip()
    state.cov_base_sex67 = state._bw['sex_code_67'].currentText().strip()
    state.cov_base_sex02 = state._bw['sex_code_02'].currentText().strip()
    state.cov_base_person = state._bw['person'].currentText().strip()
    state.cov_base_lives_cov = state._bw['lives_cov'].currentText().strip()
    state.cov_base_change_type = state._bw['change_type'].currentText().strip()
    state.cov_base_cease_code = state._bw['cease_code'].selected_values()
    state.cov_base_cola_ind = state._bw['cola_ind'].currentText().strip()
    state.cov_base_gio_fio = state._bw['gio_fio'].currentText().strip()
    state.cov_base_table03 = state._bw['table_03'].isChecked()
    state.cov_base_flat03 = state._bw['flat_03'].isChecked()
    state.cov_base_active_flat03 = state._bw['active_flat_03'].isChecked()
    state.cov_base_issue_lo = normalize_date(state._bw['issue_date_lo'].text()) or ''
    state.cov_base_issue_hi = normalize_date(state._bw['issue_date_hi'].text()) or ''
    state.cov_base_change_lo = normalize_date(state._bw['change_date_lo'].text()) or ''
    state.cov_base_change_hi = normalize_date(state._bw['change_date_hi'].text()) or ''
    state.cov_needs_modcov1 = bool(state.cov_base_prod_ind or state.cov_base_cola_ind or state.cov_base_gio_fio)
    state.cov_needs_renewals = bool(state.cov_base_rateclass or state.cov_base_sex67)


def build_step_004(state: BuildState) -> None:

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
    state._rider_info = _rider_info
    state.rider1_info = state._rider_info(state.covt.rider1_widgets)
    state.rider2_info = state._rider_info(state.covt.rider2_widgets)
    state.cov_needs_modcovsall = bool(state.cov_gio or state.cov_cola)
    state.has_modcovsall = state.has_modcovsall or state.cov_needs_modcovsall
    state.has_skipped_rein = state.has_skipped_rein or state.cov_skipped_rein
    state.multi_base_covs = state.multi_base_covs or state.cov_multi_base
    state.cov_needs_covsummary = bool(state.cov_has_spec_amt or state.cov_multi_base)
    state.cov_needs_iswl_gcv = bool(state.cov_gcv_gt_cv or state.cov_gcv_lt_cv)
    state.cov_needs_mvval = bool(state.cov_gcv_gt_cv or state.cov_gcv_lt_cv)
    state.needs_mvval = state.adv_cv_corr or state.adv_accum_gt_prem or state.has_accum_val or state.adv_gcv_gt_cv or state.adv_gcv_lt_cv or state.cov_needs_mvval or state.disp_accum_value or state.disp_prem_ptd or state.disp_account_value or state.adv_prem_wd_gt_face
    state.needs_iswl_gcv = state.adv_gcv_gt_cv or state.adv_gcv_lt_cv or state.cov_needs_iswl_gcv
    state.needs_interpolation = state.needs_iswl_gcv or state.disp_trad_cv_cov1 or state.disp_account_value
    state.needs_covsummary = state.disp_spec_amt or state.multi_base_covs or state.adv_cv_corr or state.adv_sa_lt_orig or state.adv_sa_gt_orig or state.has_curr_spec_amt or state.needs_iswl_gcv or state.cov_needs_covsummary
    state.needs_premwd_face = state.adv_prem_wd_gt_face
    if state.needs_pol_yr_tot:
        state.sql_parts.append(f', LH_POL_YR_TOT_withMaxDuration AS')
        state.sql_parts.append(f'  (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, MAX(POL_YR_DUR) MAX_DURATION')
        state.sql_parts.append(f'   FROM {state.schema}.LH_POL_YR_TOT')
        state.sql_parts.append(f'   GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)')
        state.sql_parts.append(f', LH_POL_YR_TOT_at_MaxDuration AS')
        state.sql_parts.append(f'  (SELECT YEARTOTS.*')
        state.sql_parts.append(f'   FROM {state.schema}.LH_POL_YR_TOT YEARTOTS')
        state.sql_parts.append(f'   INNER JOIN LH_POL_YR_TOT_withMaxDuration')
        state.sql_parts.append(f'     ON YEARTOTS.CK_SYS_CD = LH_POL_YR_TOT_withMaxDuration.CK_SYS_CD')
        state.sql_parts.append(f'    AND YEARTOTS.CK_CMP_CD = LH_POL_YR_TOT_withMaxDuration.CK_CMP_CD')
        state.sql_parts.append(f'    AND YEARTOTS.TCH_POL_ID = LH_POL_YR_TOT_withMaxDuration.TCH_POL_ID')
        state.sql_parts.append(f'    AND YEARTOTS.POL_YR_DUR = LH_POL_YR_TOT_withMaxDuration.MAX_DURATION)')
    if state.needs_grace_table:
        state.sql_parts.append(f', GRACE_TABLE AS')
        state.sql_parts.append(f'  (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND')
        state.sql_parts.append(f'   FROM {state.schema}.LH_NON_TRD_POL')
        state.sql_parts.append(f'   UNION')
        state.sql_parts.append(f'   SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND')
        state.sql_parts.append(f'   FROM {state.schema}.LH_TRD_POL)')
    if state.disp_conversion_dates:
        state.sql_parts.append(', ' + _conversion_sc_cte(state.schema))
    if state.disp_post_conversion:
        state.sql_parts.append(', ' + _post_conversion_cte(state.schema))


def build_step_005(state: BuildState) -> None:
    if state.has_term_entry or state.disp_term_date or state.has_term_both:
        state.sql_parts.append(f', TERMINATION_TRANS AS')
        state.sql_parts.append(f'  (SELECT FH.CK_CMP_CD, FH.TCH_POL_ID,')
        state.sql_parts.append(f'    FH.ENTRY_DT, FH.ASOF_DT, FH.TRANS')
        state.sql_parts.append(f'   FROM {state.schema}.FH_FIXED AS FH')
        state.sql_parts.append(f"   WHERE FH.TRANS IN ('SC', 'SI', 'SF', 'TD', 'TM', 'TN', 'TL', 'TO')")
        state.sql_parts.append(f"   AND FH.FCB0_REV_IND = '0'")
        state.sql_parts.append(f"   AND FH.FCB2_REV_APPL_IND = '0')")
        state.sql_parts.append(f', PRE_TERMINATION_DATES AS')
        state.sql_parts.append(f'  (SELECT TT.CK_CMP_CD, TT.TCH_POL_ID,')
        state.sql_parts.append(f'   MAX(TT.ENTRY_DT) AS TERM_ENTRY_DT')
        state.sql_parts.append(f'   FROM TERMINATION_TRANS AS TT')
        state.sql_parts.append(f'   GROUP BY TT.CK_CMP_CD, TT.TCH_POL_ID)')
        state.sql_parts.append(f', TERMINATION_ENTRY_EFFECTIVE_DATES AS')
        state.sql_parts.append(f'  (SELECT CK_CMP_CD, TCH_POL_ID, ENTRY_DT,')
        state.sql_parts.append(f'    MAX(ASOF_DT) AS TERM_EFFECTIVE_DT')
        state.sql_parts.append(f'   FROM TERMINATION_TRANS')
        state.sql_parts.append(f'   GROUP BY CK_CMP_CD, TCH_POL_ID, ENTRY_DT)')
        state.sql_parts.append(f', TERMINATION_ENTRY_TRANS_TYPES AS')
        state.sql_parts.append(f'  (SELECT CK_CMP_CD, TCH_POL_ID, ENTRY_DT,')
        state.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'SC' THEN 1 ELSE 0 END) AS HAS_SC,")
        state.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'SI' THEN 1 ELSE 0 END) AS HAS_SI,")
        state.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'SF' THEN 1 ELSE 0 END) AS HAS_SF,")
        state.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TD' THEN 1 ELSE 0 END) AS HAS_TD,")
        state.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TM' THEN 1 ELSE 0 END) AS HAS_TM,")
        state.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TN' THEN 1 ELSE 0 END) AS HAS_TN,")
        state.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TL' THEN 1 ELSE 0 END) AS HAS_TL,")
        state.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TO' THEN 1 ELSE 0 END) AS HAS_TO")
        state.sql_parts.append(f'   FROM TERMINATION_TRANS')
        state.sql_parts.append(f'   GROUP BY CK_CMP_CD, TCH_POL_ID, ENTRY_DT)')
        state.sql_parts.append(f', TERMINATION_ENTRY_DETAILS AS')
        state.sql_parts.append(f'  (SELECT PTD.CK_CMP_CD, PTD.TCH_POL_ID, PTD.TERM_ENTRY_DT,')
        state.sql_parts.append(f'    TED.TERM_EFFECTIVE_DT,')
        state.sql_parts.append(f'    SUBSTR(')
        state.sql_parts.append(f"      CASE WHEN TTT.HAS_SC = 1 THEN ', SC' ELSE '' END ||")
        state.sql_parts.append(f"      CASE WHEN TTT.HAS_SI = 1 THEN ', SI' ELSE '' END ||")
        state.sql_parts.append(f"      CASE WHEN TTT.HAS_SF = 1 THEN ', SF' ELSE '' END ||")
        state.sql_parts.append(f"      CASE WHEN TTT.HAS_TD = 1 THEN ', TD' ELSE '' END ||")
        state.sql_parts.append(f"      CASE WHEN TTT.HAS_TM = 1 THEN ', TM' ELSE '' END ||")
        state.sql_parts.append(f"      CASE WHEN TTT.HAS_TN = 1 THEN ', TN' ELSE '' END ||")
        state.sql_parts.append(f"      CASE WHEN TTT.HAS_TL = 1 THEN ', TL' ELSE '' END ||")
        state.sql_parts.append(f"      CASE WHEN TTT.HAS_TO = 1 THEN ', TO' ELSE '' END,")
        state.sql_parts.append(f'      3) AS TERM_TRANS_TYPES')
        state.sql_parts.append(f'   FROM PRE_TERMINATION_DATES AS PTD')
        state.sql_parts.append(f'   INNER JOIN TERMINATION_ENTRY_EFFECTIVE_DATES AS TED')
        state.sql_parts.append(f'     ON PTD.CK_CMP_CD = TED.CK_CMP_CD')
        state.sql_parts.append(f'    AND PTD.TCH_POL_ID = TED.TCH_POL_ID')
        state.sql_parts.append(f'    AND PTD.TERM_ENTRY_DT = TED.ENTRY_DT')
        state.sql_parts.append(f'   INNER JOIN TERMINATION_ENTRY_TRANS_TYPES AS TTT')
        state.sql_parts.append(f'     ON PTD.CK_CMP_CD = TTT.CK_CMP_CD')
        state.sql_parts.append(f'    AND PTD.TCH_POL_ID = TTT.TCH_POL_ID')
        state.sql_parts.append(f'    AND PTD.TERM_ENTRY_DT = TTT.ENTRY_DT)')
        state._term_lo = normalize_date(state.p2t.txt_term_entry_date_lo.text()) or ''
        state._term_hi = normalize_date(state.p2t.txt_term_entry_date_hi.text()) or ''
        if state._term_lo or state._term_hi:
            state._tw = 'WHERE 1=1'
            if state._term_lo:
                state._tw += f" AND TERMINATION_ENTRY_DETAILS.TERM_ENTRY_DT >= '{state._term_lo}'"
            if state._term_hi:
                state._tw += f" AND TERMINATION_ENTRY_DETAILS.TERM_ENTRY_DT <= '{state._term_hi}'"
            state.sql_parts.append(f', TERMINATION_DATES AS')
            state.sql_parts.append(f'  (SELECT * FROM TERMINATION_ENTRY_DETAILS {state._tw})')
        else:
            state.sql_parts.append(f', TERMINATION_DATES AS')
            state.sql_parts.append(f'  (SELECT * FROM TERMINATION_ENTRY_DETAILS)')
        if state.has_term_both:
            state.sql_parts.append(', TERMINATION_BOTH_DATES AS')
            state.sql_parts.append('  (SELECT CK_CMP_CD, TCH_POL_ID, MAX(ENTRY_DT) AS TERM_ENTRY_DT')
            state.sql_parts.append('   FROM TERMINATION_TRANS')
            state.sql_parts.append("   WHERE ENTRY_DT < DATE('9999-12-31')")
            state.sql_parts.append('   GROUP BY CK_CMP_CD, TCH_POL_ID)')
    if state.has_77_segment or state.disp_policy_debt:
        state.sql_parts.append(f', ALL_LOANS AS (')
        state.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PRF_LN_IND, LN_PRI_AMT,')
        state.sql_parts.append(f"    (CASE LN_ITS_AMT_TYP_CD WHEN '2' THEN POL_LN_ITS_AMT ELSE 0 END) LN_INT")
        state.sql_parts.append(f"  FROM {state.schema}.LH_FND_VAL_LOAN WHERE MVRY_DT = '9999-12-31'")
        state.sql_parts.append(f'  UNION')
        state.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PRF_LN_IND, LN_PRI_AMT,')
        state.sql_parts.append(f"    (CASE LN_ITS_AMT_TYP_CD WHEN '2' THEN POL_LN_ITS_AMT ELSE 0 END) LN_INT")
        state.sql_parts.append(f"  FROM {state.schema}.LH_CSH_VAL_LOAN WHERE MVRY_DT = '9999-12-31')")
        state.sql_parts.append(f', POLICYDEBT AS (')
        state.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,')
        state.sql_parts.append(f'    SUM(ALL_LOANS.LN_PRI_AMT) LOAN_PRINCIPLE,')
        state.sql_parts.append(f'    SUM(ALL_LOANS.LN_INT) LOAN_ACCRUED,')
        state.sql_parts.append(f"    SUM(CASE WHEN COALESCE(ALL_LOANS.PRF_LN_IND, '0') <> '1'")
        state.sql_parts.append(f'      THEN ALL_LOANS.LN_PRI_AMT ELSE 0 END) REG_LOAN_PRINCIPLE,')
        state.sql_parts.append(f"    SUM(CASE WHEN COALESCE(ALL_LOANS.PRF_LN_IND, '0') <> '1'")
        state.sql_parts.append(f'      THEN ALL_LOANS.LN_INT ELSE 0 END) REG_LOAN_ACCRUED,')
        state.sql_parts.append(f"    SUM(CASE WHEN ALL_LOANS.PRF_LN_IND = '1'")
        state.sql_parts.append(f'      THEN ALL_LOANS.LN_PRI_AMT ELSE 0 END) PREF_LOAN_PRINCIPLE,')
        state.sql_parts.append(f"    SUM(CASE WHEN ALL_LOANS.PRF_LN_IND = '1'")
        state.sql_parts.append(f'      THEN ALL_LOANS.LN_INT ELSE 0 END) PREF_LOAN_ACCRUED')
        state.sql_parts.append(f'  FROM ALL_LOANS')
        state.sql_parts.append(f'  GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)')
