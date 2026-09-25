"""CyberLife SQL where policy section builders."""
from __future__ import annotations

from .common import *


def build_step_020(state: BuildState) -> None:
    state._emit_rider_joins(state.rider1_info, 'RIDER1', 1)
    state._emit_rider_joins(state.rider2_info, 'RIDER2', 2)
    state.sql_parts.extend(state.custom_join_lines)
    state.wheres = []
    state.wheres.extend(state.custom_where_lines)
    state.wheres.extend(state.segment52_where_lines)
    if state.transaction_tab is not None:
        state.first_transaction, state.second_transaction = state.transaction_tab.criteria()
        state.wheres.extend(transaction_predicates(state.first_transaction, state.second_transaction, state.schema))
    if state.sys_code:
        state.wheres.append(f"POLICY1.CK_SYS_CD = '{esc(state.sys_code)}'")
    state.plancode = state.pt.txt_plancode.text().strip().upper()
    if state.plancode:
        state.cov_filter_alias = 'COVERAGE1' if state.cov1_plancode_match_only else state.result_cov_alias if state.coverage_level else 'COVSALL'
        state.wheres.append(f"{state.cov_filter_alias}.PLN_DES_SER_CD = '{esc(state.plancode)}'")
    state.plancode_list = state.plancode_tab.get_plancodes()
    if state.plancode_list:
        state.cov_filter_alias = 'COVERAGE1' if state.cov1_plancode_match_only else state.result_cov_alias if state.coverage_level else 'COVSALL'
        state.wheres.append(f'{state.cov_filter_alias}.PLN_DES_SER_CD IN ({in_list(state.plancode_list)})')
    state.policy_list = state.plancode_tab.get_policies()
    if state.policy_list:
        state.wheres.append(f'POLICY1.CK_POLICY_NBR IN ({in_list(state.policy_list)})')
    state._mkt_org_map = {'MLM': '1', 'CSSD': '2', 'IMG': '7', 'DIRECT': 'D'}
    state._mkt_company_map = {'CSSD': ['01'], 'IMG': ['01', '26'], 'MLM': ['01', '26'], 'DIRECT': ['01', '26']}
    state.market_org = state.pt.cmb_market.currentText().strip()
    if state.market_org and state.market_org in state._mkt_org_map:
        state.wheres.append(f"SUBSTR(POLICY1.SVC_AGC_NBR,1,1) = '{state._mkt_org_map[state.market_org]}'")
    state.company = state.pt.cmb_company.currentText().strip()
    if state.company:
        state.co_code = state.company.split(' - ')[0].strip() if ' - ' in state.company else state.company
        state.wheres.append(f"POLICY1.CK_CMP_CD = '{esc(state.co_code)}'")
    elif state.market_org and state.market_org in state._mkt_company_map:
        state.co_codes = state._mkt_company_map[state.market_org]
        if len(state.co_codes) == 1:
            state.wheres.append(f"POLICY1.CK_CMP_CD = '{state.co_codes[0]}'")
        else:
            state.conds = ' OR '.join((f"POLICY1.CK_CMP_CD = '{c}'" for c in state.co_codes))
            state.wheres.append(f'({state.conds})')
    state.form_num = state.pt.txt_form_number.text().strip()
    if state.form_num:
        state.wheres.append(f"{state.result_cov_alias}.POL_FRM_NBR LIKE '{esc(state.form_num)}%'")
    state.branch = state.pt.txt_branch.text().strip()
    if state.branch:
        state.wheres.append(f"SUBSTR(POLICY1.SVC_AGC_NBR, 2, 3) = '{esc(state.branch)}'")
    state.polnum = state.pt.txt_polnum_value.text().strip()
    if state.polnum:
        state.criteria = state.pt.cmb_polnum_criteria.currentText()
        if state.criteria == 'Starts with':
            state.wheres.append(f"POLICY1.CK_POLICY_NBR LIKE '{esc(state.polnum)}%'")
        elif state.criteria == 'Ends with':
            state.wheres.append(f"POLICY1.CK_POLICY_NBR LIKE '%{esc(state.polnum)}'")
        else:
            state.wheres.append(f"POLICY1.CK_POLICY_NBR LIKE '%{esc(state.polnum)}%'")
    if state.pt.chk_rga.isChecked():
        state.wheres.append("USERGEN.FUZGREIN_IND = 'R'")
    if state.pt.chk_status_code.isChecked():
        state.codes = selected_codes(state.pt.list_status)
        if state.codes:
            state.wheres.append(f'POLICY1.PRM_PAY_STA_REA_CD IN ({in_list(state.codes)})')
    if state.pt.chk_product_line.isChecked():
        state.codes = selected_codes(state.pt.list_product_line)
        if state.codes:
            state.cov_filter_alias = state.result_cov_alias if state.coverage_level else 'COVSALL'
            state.wheres.append(f'{state.cov_filter_alias}.PRD_LIN_TYP_CD IN ({in_list(state.codes)})')
    if state.pt.chk_state.isChecked():
        state.abbrevs = [item.text() for item in state.pt.list_state.selectedItems()]
        if state.abbrevs:
            state.st_codes = [_STATE_ABBR_TO_CODE.get(a) for a in state.abbrevs]
            state.st_codes = [c for c in state.st_codes if c]
            if state.st_codes:
                state.wheres.append(f'POLICY1.POL_ISS_ST_CD IN ({in_list(state.st_codes)})')
    if state.pt.chk_last_entry.isChecked():
        state.codes = selected_codes(state.pt.list_last_entry)
        if state.codes:
            state.wheres.append(f'POLICY1.LST_ETR_CD IN ({in_list(state.codes)})')
    if state.pt.chk_suspense.isChecked():
        state.codes = selected_codes(state.pt.list_suspense)
        if state.codes:
            state.wheres.append(f'POLICY1.SUS_CD IN ({in_list(state.codes)})')
    if state.pt.chk_billing_form.isChecked():
        state.codes = selected_codes(state.pt.list_billing_form)
        if state.codes:
            state.wheres.append(f'POLICY1.BIL_FRM_CD IN ({in_list(state.codes)})')


def build_step_021(state: BuildState) -> None:
    if state.pt.chk_bill_mode.isChecked():
        state.modes = [item.text() for item in state.pt.list_bill_mode.selectedItems()]
        if state.modes:
            state.mode_clause = _build_bill_mode_where(state.modes)
            if state.mode_clause:
                state.wheres.append(f'({state.mode_clause})')
    add_int_range(state.wheres, f'{state.result_cov_alias}.INS_ISS_AGE', state.pt.txt_issue_age_lo, state.pt.txt_issue_age_hi)
    state.duration_expr = "TRUNCATE(MONTHS_BETWEEN('" + today_str() + f"', {state.result_cov_alias}.ISSUE_DT) / 12, 0)"
    add_int_range(state.wheres, f'({state.result_cov_alias}.INS_ISS_AGE + {state.duration_expr})', state.pt.txt_current_age_lo, state.pt.txt_current_age_hi)
    state.val_duration_expr = f'TRUNCATE(MONTHS_BETWEEN({_valuation_date_sql(state.schema)}, {state.result_cov_alias}.ISSUE_DT) / 12, 0)'
    add_int_range(state.wheres, f'({state.result_cov_alias}.INS_ISS_AGE + {state.val_duration_expr})', state.pt.txt_val_age_lo, state.pt.txt_val_age_hi)
    add_int_range(state.wheres, f'({state.duration_expr} + 1)', state.pt.txt_pol_year_lo, state.pt.txt_pol_year_hi)
    add_int_range(state.wheres, f'MONTH({state.result_cov_alias}.ISSUE_DT)', state.pt.txt_issue_month_lo, state.pt.txt_issue_month_hi)
    add_int_range(state.wheres, f'DAY({state.result_cov_alias}.ISSUE_DT)', state.pt.txt_issue_day_lo, state.pt.txt_issue_day_hi)
    add_date_range(state.wheres, f'{state.result_cov_alias}.ISSUE_DT', state.pt.txt_issued_date_lo, state.pt.txt_issued_date_hi)
    add_date_range(state.wheres, 'POLICY1.PRM_PAID_TO_DT', state.pt.txt_paid_to_lo, state.pt.txt_paid_to_hi)
    add_date_range(state.wheres, 'POLICY1.APP_WRT_DT', state.pt.txt_app_date_lo, state.pt.txt_app_date_hi)
    add_decimal_range(state.wheres, 'POLICY1.POL_PRM_AMT', state.pt.txt_billing_prem_lo, state.pt.txt_billing_prem_hi)
    if state.has_gpe_date:
        add_date_range(state.wheres, 'GRACE_TABLE.GRA_PER_EXP_DT', state.pt.txt_gpe_date_lo, state.pt.txt_gpe_date_hi)
    if state.grace_indicator:
        state.codes = selected_codes(state.pt.list_grace_indicator)
        if state.codes:
            state.conds = ' OR '.join((f"SUBSTR(GRACE_TABLE.IN_GRA_PER_IND,1,1) = '{esc(c)}'" for c in state.codes))
            state.wheres.append(f'({state.conds})')
    add_decimal_range(state.wheres, 'TAMRA.SVPY_LVL_PRM_AMT', state.p2t.txt_tamra_7pay_prem_lo, state.p2t.txt_tamra_7pay_prem_hi)
    add_decimal_range(state.wheres, 'TAMRA.SVPY_BEG_CSV_AMT', state.p2t.txt_tamra_7pay_av_lo, state.p2t.txt_tamra_7pay_av_hi)
    if state.p2t.chk_1035_amt.isChecked():
        state.wheres.append('TAMRA.XCG_1035_PMT_QTY > 0')
    if state.p2t.chk_mec.isChecked():
        state.wheres.append("TAMRA.MEC_STA_CD = '1'")
    add_decimal_range(state.wheres, 'POLICY_TOTALS.TOT_ADD_PRM_AMT', state.p2t.txt_total_addl_prem_lo, state.p2t.txt_total_addl_prem_hi)
    add_decimal_range(state.wheres, '(POLICY_TOTALS.TOT_ADD_PRM_AMT + POLICY_TOTALS.TOT_REG_PRM_AMT)', state.p2t.txt_total_prem_addl_reg_lo, state.p2t.txt_total_prem_addl_reg_hi)
    add_decimal_range(state.wheres, 'POLICY_TOTALS.TOT_WTD_AMT', state.p2t.txt_accum_wd_lo, state.p2t.txt_accum_wd_hi)
    add_decimal_range(state.wheres, 'LH_POL_YR_TOT_at_MaxDuration.YTD_TOT_PMT_AMT', state.p2t.txt_prem_ytd_lo, state.p2t.txt_prem_ytd_hi)
    add_date_range(state.wheres, 'NONTRAD.BIL_COMMENCE_DT', state.p2t.txt_bil_commence_dt_lo, state.p2t.txt_bil_commence_dt_hi)
    if state.p2t.chk_billing_suspended.isChecked():
        state.wheres.append("NONTRAD.BIL_STA_CD = '1'")
    if state.p2t.chk_failed_guideline.isChecked():
        state.wheres.append("NONTRAD.PR_LIMIT_EXC_ONL = '1'")
    if state.p2t.chk_participating.isChecked():
        state.codes = []
        for state.item in state.p2t.list_participating.selectedItems():
            state.label = state.item.text()
            if state.label not in PARTICIPATION_CODES:
                raise ValueError(f'Unknown participation category: {state.label}')
            state.codes.extend(PARTICIPATION_CODES[state.label])
        if state.codes:
            state.wheres.append(_participation_predicate(state.codes))
    if state.wl_tab is not None:
        for state.checkbox, state.listbox, state.column in ((state.wl_tab.chk_pri_div, state.wl_tab.list_pri_div, 'POLICY1.PRI_DIV_OPT_CD'), (state.wl_tab.chk_sec_div, state.wl_tab.list_sec_div, 'POLICY1.DIV_2ND_OPT_CD'), (state.wl_tab.chk_nfo, state.wl_tab.list_nfo, 'POLICY1.NFO_OPT_TYP_CD')):
            if state.checkbox.isChecked():
                state.codes = selected_codes(state.listbox)
                if state.codes:
                    state.wheres.append(f'{state.column} IN ({in_list(state.codes)})')
        if state.wl_tab.chk_participation_type.isChecked():
            state.codes = state.wl_tab.selected_participation_codes()
            if state.codes:
                state.wheres.append(_participation_predicate(state.codes))


def build_step_022(state: BuildState) -> None:
    add_date_range(state.wheres, 'POLICY1.LST_FIN_DT', state.p2t.txt_last_fin_date_lo, state.p2t.txt_last_fin_date_hi)
    state.wheres.extend(state.term_fin_predicates)
    state.wheres.extend(state.term_both_predicates)
    if state.p2t.chk_has_converted.isChecked():
        state.wheres.append('USERGEN.EXCH_POL_NUMBER IS NOT NULL')
    if state.p2t.chk_has_replacement_pol.isChecked():
        state.wheres.append('USERDEF_52R.REPLACED_POLICY IS NOT NULL')
    if state.p2t.chk_cov_gio.isChecked():
        state.wheres.append("MODCOVSALL.OPT_EXER_IND = 'Y'")
    if state.p2t.chk_cov_cola.isChecked():
        state.wheres.append("MODCOVSALL.COLA_INCR_IND = '1'")
    if state.p2t.chk_loan_type.isChecked():
        state.codes = selected_codes(state.p2t.list_loan_type)
        if state.codes:
            state.wheres.append(f'POLICY1.LN_TYP_CD IN ({in_list(state.codes)})')
    state.loan_rate = state.p2t.txt_loan_charge_rate.text().strip()
    if state.loan_rate:
        try:
            state.wheres.append(f'POLICY1.LN_PLN_ITS_RT = {float(state.loan_rate)}')
        except ValueError:
            pass
    add_decimal_range(state.wheres, 'POLICYDEBT.LOAN_PRINCIPLE', state.p2t.txt_total_loan_prin_lo, state.p2t.txt_total_loan_prin_hi)
    add_decimal_range(state.wheres, 'POLICYDEBT.LOAN_ACCRUED', state.p2t.txt_total_accured_lint_lo, state.p2t.txt_total_accured_lint_hi)
    if state.p2t.chk_trad_overloan.isChecked():
        state.codes = selected_codes(state.p2t.list_trad_overloan)
        if state.codes:
            state.wheres.append(f'POLICY1_MOD.OVERLOAN_IND IN ({in_list(state.codes)})')
    if state.p2t.chk_non_trad.isChecked():
        state.codes = selected_codes(state.p2t.list_non_trad)
        if state.codes:
            state.wheres.append(f'POLICY1.NON_TRD_POL_IND IN ({in_list(state.codes)})')
    if state.p2t.chk_std_loan_payment.isChecked():
        state.codes = selected_codes(state.p2t.list_std_loan_payment)
        if state.codes:
            state.wheres.append(f'SLR_BILL_CONTROL.BIL_FRM_CD IN ({in_list(state.codes)})')
    if state.p2t.chk_def_life.isChecked():
        state.codes = selected_codes(state.p2t.list_def_life)
        if state.codes:
            state.wheres.append(f'NONTRAD.TFDF_CD IN ({in_list(state.codes)})')
    if state.p2t.chk_reinsurance.isChecked():
        state.codes = selected_codes(state.p2t.list_reinsurance)
        if state.codes:
            state.wheres.append(f'POLICY1.REINSURED_CD IN ({in_list(state.codes)})')
    if state.has_change_seq:
        state.codes = selected_codes(state.p2t.list_change_seq)
        if state.codes:
            state.wheres.append(f'CHANGE_SEGMENT.CHG_TYP_CD IN ({in_list(state.codes)})')
    if state.adv_cv_corr:
        state.wheres.append('(MVVAL.DB > COVSUMMARY.TOTAL_SA + MVVAL.OPTDB)')
    if state.adv_accum_gt_prem:
        state.wheres.append('(MVVAL.CSV_AMT >= MVVAL.TOTALPREM)')
    if state.adv_glp_neg:
        state.wheres.append('(GLP.GLP_VALUE < 0)')
    if state.adv_sa_lt_orig:
        state.wheres.append('(COVSUMMARY.TOTAL_SA < COVSUMMARY.TOTAL_ORIGINAL_SA)')
    if state.adv_sa_gt_orig:
        state.wheres.append('(COVSUMMARY.TOTAL_SA > COVSUMMARY.TOTAL_ORIGINAL_SA)')
    if state.adv_gcv_gt_cv:
        state.wheres.append('(ISWL_INTERPOLATED_GCV.ISWL_GCV >= MVVAL.CSV_AMT)')
    if state.adv_gcv_lt_cv:
        state.wheres.append('(ISWL_INTERPOLATED_GCV.ISWL_GCV <= MVVAL.CSV_AMT)')
    if state.adv_prem_wd_gt_face:
        state.wheres.append('((POLICY_TOTALS.TOT_REG_PRM_AMT + POLICY_TOTALS.TOT_ADD_PRM_AMT - POLICY_TOTALS.TOT_WTD_AMT) > PREMWD_FACE.TOTAL_FACE)')
    if state.adv_grace_rule:
        state.codes = selected_codes(state.at.list_grace_rule)
        if state.codes:
            state.wheres.append(f'NONTRAD.GRA_THD_RLE_CD IN ({in_list(state.codes)})')
    if state.adv_db_option:
        state.codes = selected_codes(state.at.list_db_option)
        if state.codes:
            state.wheres.append(f'NONTRAD.DTH_BNF_PLN_OPT_CD IN ({in_list(state.codes)})')
    if state.at.chk_decr_chrg_rule.isChecked() and state.at.list_decr_chrg_rule.selectedItems():
        state.codes = selected_codes(state.at.list_decr_chrg_rule)
        state.rule_preds = []
        state.known = [code for code in state.codes if code in ('0', '1')]
        if state.known:
            state.rule_preds.append(f'DECRCHG.DECR_CHRG_ALLOW IN ({in_list(state.known)})')
        if 'Blank' in state.codes:
            state.rule_preds.append("(DECRCHG.DECR_CHRG_ALLOW IS NULL OR DECRCHG.DECR_CHRG_ALLOW NOT IN ('0', '1'))")
        state.wheres.append(f"EXISTS (SELECT 1 FROM {state.schema}.TH_NON_TRD_POL DECRCHG WHERE DECRCHG.CK_SYS_CD = POLICY1.CK_SYS_CD AND DECRCHG.CK_CMP_CD = POLICY1.CK_CMP_CD AND DECRCHG.TCH_POL_ID = POLICY1.TCH_POL_ID AND ({' OR '.join(state.rule_preds)}))")
