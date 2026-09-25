"""CyberLife SQL context section builders."""
from __future__ import annotations

from .common import *


def build_step_001(state: BuildState) -> None:
    """Build the CyberLife audit SQL from widget-free audit criteria."""
    state.schema = state.criteria.schema
    state.sys_code = state.criteria.sys_code
    state.max_count_text = state.criteria.max_count_text
    state.coverage_level = state.criteria.coverage_level
    state.coverage_scope = state.criteria.coverage_scope
    state.custom_display_tab = state.criteria.custom_display
    state.segment52_tab = state.criteria.segment52
    state.transaction_tab = state.criteria.transaction
    state.wl_tab = state.criteria.wl
    state.pt = state.criteria.policy
    state.dt = state.criteria.display
    state.p2t = state.criteria.policy2
    state.at = state.criteria.adv
    state.covt = state.criteria.coverages
    state.plancode_tab = state.criteria.plancode
    state.benefits_tab = state.criteria.benefits
    state.ppl = state.criteria.people
    state.result_cov_alias = 'RESULTCOV' if state.coverage_level else 'COVERAGE1'
    state.result_rnw_alias = 'RESULTCOV_RENEWALS' if state.coverage_level else 'COV1_RENEWALS'
    state.result_table_alias = 'RESULTCOV_TABLE_RATING' if state.coverage_level else 'TABLE_RATING1'
    state.result_flat_alias = 'RESULTCOV_FLAT_EXTRA' if state.coverage_level else 'FLAT_EXTRA1'
    state.custom_select_lines, state.custom_join_lines, state.custom_where_lines = _build_custom_display(state.custom_display_tab, state.result_cov_alias, state.schema)
    state.segment52_select_lines, state.segment52_where_lines = _build_segment52(state.segment52_tab, state.dt.chk_segment52.isChecked())
    state.has_current_age = bool(state.pt.txt_current_age_lo.text().strip() or state.pt.txt_current_age_hi.text().strip())
    state.has_val_age = bool(state.pt.txt_val_age_lo.text().strip() or state.pt.txt_val_age_hi.text().strip())
    state.has_pol_year = bool(state.pt.txt_pol_year_lo.text().strip() or state.pt.txt_pol_year_hi.text().strip())
    state.has_issue_month = bool(state.pt.txt_issue_month_lo.text().strip() or state.pt.txt_issue_month_hi.text().strip())
    state.has_issue_day = bool(state.pt.txt_issue_day_lo.text().strip() or state.pt.txt_issue_day_hi.text().strip())
    state.has_paid_to = bool(state.pt.txt_paid_to_lo.text().strip() or state.pt.txt_paid_to_hi.text().strip())
    state.has_gpe_date = bool(state.pt.txt_gpe_date_lo.text().strip() or state.pt.txt_gpe_date_hi.text().strip())
    state.grace_indicator = bool(state.pt.chk_grace_indicator.isChecked() and state.pt.list_grace_indicator.selectedItems())
    state.has_app_date = bool(state.pt.txt_app_date_lo.text().strip() or state.pt.txt_app_date_hi.text().strip())
    state.has_billing_prem = bool(state.pt.txt_billing_prem_lo.text().strip() or state.pt.txt_billing_prem_hi.text().strip())
    state.policy_product_indicator_codes = []
    if state.pt.chk_product_indicator.isChecked():
        state.policy_product_indicator_codes = selected_codes(state.pt.list_product_indicator)
    state.policy_has_product_indicator = bool(state.policy_product_indicator_codes)
    state.disp_paid_to = state.dt.chk_paid_to_date.isChecked()
    state.disp_bill_to = state.dt.chk_bill_to_date.isChecked()
    state.disp_duration = state.dt.chk_val_duration.isChecked()
    state.disp_attained_age = state.dt.chk_val_attained_age.isChecked()
    state.disp_last_acct = state.dt.chk_last_acct_date.isChecked()
    state.disp_last_fin = state.dt.chk_last_fin_date.isChecked()
    state.disp_bill_prem = state.dt.chk_billable_prem.isChecked()
    state.disp_bill_mode = state.dt.chk_billable_mode.isChecked()
    state.disp_bill_form = state.dt.chk_billable_form.isChecked()
    state.disp_mkt_org = state.dt.chk_disp_mkt_org.isChecked()
    state.disp_reinsured = state.dt.chk_reinsured_code.isChecked()
    state.disp_last_entry = state.dt.chk_last_entry_code.isChecked()
    state.disp_orig_entry = state.dt.chk_orig_entry_code.isChecked()
    state.disp_spec_amt = state.dt.chk_disp_orig_curr_sa.isChecked()
    state.disp_tch_pol_id = state.dt.chk_tch_pol_id.isChecked()
    state.disp_mod_indicator = state.dt.chk_mod_indicator.isChecked()
    state.disp_prod_line = state.dt.chk_prod_line_code.isChecked()
    state.disp_sex_02 = state.dt.chk_disp_sex_02.isChecked()
    state.disp_subseries = state.dt.chk_subseries_code.isChecked()
    state.disp_mec_status = state.dt.chk_mec_status.isChecked()
    state.disp_app_date = state.dt.chk_application_date.isChecked()
    state.disp_next_notif = state.dt.chk_next_sched_notif.isChecked()
    state.disp_next_year_end = state.dt.chk_next_year_end.isChecked()
    state.disp_next_stmt = state.dt.chk_next_sched_stmt.isChecked()
    state.disp_next_change = state.dt.chk_next_change_cov1.isChecked()
    state.disp_init_term = state.dt.chk_init_term_period.isChecked()
    state.disp_commission_target = state.dt.chk_commission_target.isChecked()
    state.disp_monthly_mtp = state.dt.chk_monthly_min_target.isChecked()
    state.disp_accum_mtp = state.dt.chk_accum_monthly_min.isChecked()
    state.disp_accum_glp = state.dt.chk_accum_glp.isChecked()
    state.disp_nsp = state.dt.chk_nsp.isChecked()
    state.disp_shadow_av = state.dt.chk_shadow_av.isChecked()
    state.disp_db_option = state.dt.chk_death_benefit_opt.isChecked()
    state.disp_def_life_ins = state.dt.chk_def_life_ins.isChecked()
    state.disp_short_pay = state.dt.chk_short_pay.isChecked()
    state.disp_gpe_date = state.dt.chk_gpe_date.isChecked()
    state.disp_term_date = state.dt.chk_termination_date.isChecked()
    state.disp_conversion_dates = state.dt.chk_conversion_dates.isChecked()
    state.disp_accum_wd = state.dt.chk_accum_withdrawals.isChecked()
    state.disp_cost_basis = state.dt.chk_cost_basis.isChecked()
    state.disp_prem_ptd = state.dt.chk_premiums_ptd.isChecked()
    state.disp_prem_ytd = state.dt.chk_premiums_paid_ytd.isChecked()
    state.disp_accum_value = state.dt.chk_accum_value.isChecked()
    state.disp_policy_debt = state.dt.chk_policy_debt.isChecked()
    state.disp_substandard = state.dt.chk_disp_substandard.isChecked()


def build_step_002(state: BuildState) -> None:
    state.disp_sex_rateclass = state.dt.chk_disp_sex_rateclass.isChecked()
    state.disp_tamra = state.dt.chk_tamra.isChecked()
    state.disp_gsp = state.dt.chk_gsp.isChecked()
    state.disp_glp = state.dt.chk_glp.isChecked()
    state.disp_bill_ctrl_num = state.dt.chk_billable_ctrl_num.isChecked()
    state.disp_slr_bill_form = state.dt.chk_slr_bill_form.isChecked()
    state.disp_orig_face_rpu = state.dt.chk_orig_face_rpu.isChecked()
    state.disp_prem_calc_rules = state.dt.chk_prem_calc_rules.isChecked()
    state.disp_cirf_key = state.dt.chk_cirf_key.isChecked()
    state.disp_trad_overloan = state.dt.chk_trad_overloan.isChecked()
    state.disp_replacement_pol = state.dt.chk_replacement_pol.isChecked()
    state.disp_converted_pol = state.dt.chk_converted_pol.isChecked()
    state.disp_post_conversion = state.dt.chk_post_conversion.isChecked()
    state.disp_conv_credit = state.dt.chk_conv_credit.isChecked()
    state.disp_within_conv = state.dt.chk_disp_conv_period.isChecked()
    state.disp_conv_period = state.dt.chk_disp_conv_period_calc.isChecked()
    state.disp_trad_cv_cov1 = state.dt.chk_trad_cv_cov1.isChecked()
    state.disp_account_value = state.dt.chk_account_value.isChecked()
    state.disp_insured1_info = state.dt.chk_insured1_info.isChecked()
    state.disp_monthly_deduction = state.dt.chk_monthly_deduction.isChecked()
    state.disp_active_benefits = state.dt.chk_active_benefits.isChecked()
    state.disp_active_riders = state.dt.chk_active_riders.isChecked()
    state.needs_grace_table = state.has_gpe_date or state.grace_indicator or state.disp_gpe_date
    state.sql_parts = ['WITH COVERAGE1 AS', f'  (SELECT * FROM {state.schema}.LH_COV_PHA C1 WHERE C1.COV_PHA_NBR = 1)']
    state.has_tamra = bool(state.p2t.txt_tamra_7pay_prem_lo.text().strip() or state.p2t.txt_tamra_7pay_prem_hi.text().strip() or state.p2t.txt_tamra_7pay_av_lo.text().strip() or state.p2t.txt_tamra_7pay_av_hi.text().strip() or state.p2t.chk_1035_amt.isChecked() or state.p2t.chk_mec.isChecked())
    state.has_pol_totals = bool(state.p2t.txt_total_addl_prem_lo.text().strip() or state.p2t.txt_total_addl_prem_hi.text().strip() or state.p2t.txt_total_prem_addl_reg_lo.text().strip() or state.p2t.txt_total_prem_addl_reg_hi.text().strip() or state.p2t.txt_accum_wd_lo.text().strip() or state.p2t.txt_accum_wd_hi.text().strip() or state.disp_accum_wd or state.disp_cost_basis or state.at.chk_prem_wd_gt_face.isChecked())
    state.needs_pol_yr_tot = bool(state.p2t.txt_prem_ytd_lo.text().strip() or state.p2t.txt_prem_ytd_hi.text().strip() or state.disp_prem_ytd)
    state.has_nontrad = bool(state.p2t.txt_bil_commence_dt_lo.text().strip() or state.p2t.txt_bil_commence_dt_hi.text().strip() or state.p2t.chk_billing_suspended.isChecked() or state.p2t.chk_failed_guideline.isChecked() or state.p2t.chk_def_life.isChecked() or (state.at.chk_grace_rule.isChecked() and state.at.list_grace_rule.selectedItems()) or (state.at.chk_db_option.isChecked() and state.at.list_db_option.selectedItems()))
    state.has_modcovsall = bool(state.p2t.chk_cov_gio.isChecked() or state.p2t.chk_cov_cola.isChecked() or state.policy_has_product_indicator)
    state.has_52r = bool(state.p2t.chk_is_replacement.isChecked() or state.p2t.chk_has_replacement_pol.isChecked())
    state.has_skipped_rein = state.p2t.chk_skipped_cov_rein.isChecked()
    state.has_slr = bool(state.p2t.chk_std_loan_payment.isChecked() and state.p2t.list_std_loan_payment.selectedItems())
    state.has_overloan = bool(state.p2t.chk_trad_overloan.isChecked() and state.p2t.list_trad_overloan.selectedItems())
    state.has_term_entry = bool(state.p2t.txt_term_entry_date_lo.text().strip() or state.p2t.txt_term_entry_date_hi.text().strip())
    state.term_fin_date = _termination_financial_date()
    state.term_both_date = f'COALESCE(TDB.TERM_ENTRY_DT, {state.term_fin_date})'
    state.term_fin_predicates = strict_range_predicates(state.term_fin_date, state.p2t.txt_term_last_fin_date_lo.text(), state.p2t.txt_term_last_fin_date_hi.text(), 'date', 'Termination Last Financial Date (01)')
    state.term_both_predicates = strict_range_predicates(state.term_both_date, state.p2t.txt_term_date_both_lo.text(), state.p2t.txt_term_date_both_hi.text(), 'date', 'Termination Date (both)')
    state.has_term_fin = bool(state.term_fin_predicates)
    state.has_term_both = bool(state.term_both_predicates)
    state.has_77_segment = bool(state.p2t.chk_has_loan.isChecked() or state.p2t.txt_total_loan_prin_lo.text().strip() or state.p2t.txt_total_loan_prin_hi.text().strip() or state.p2t.txt_total_accured_lint_lo.text().strip() or state.p2t.txt_total_accured_lint_hi.text().strip())
    state.has_preferred_loan = state.p2t.chk_has_preferred_loan.isChecked()
    if state.has_77_segment or state.has_preferred_loan:
        state.disp_policy_debt = True
    state.has_change_seq = bool(state.p2t.chk_change_seq.isChecked() and state.p2t.list_change_seq.selectedItems())
    state.person_name_conds = []
    if state.ppl is not None:
        state._person_first_name = state.ppl.txt_first_name.text().strip()
        if state._person_first_name:
            state.person_name_conds.append(_name_match_predicate('PERSONINFO.CK_FST_NM', state.ppl.cmb_first_name_match.currentText(), state._person_first_name))
        state._person_last_name = state.ppl.txt_last_name.text().strip()
        if state._person_last_name:
            state.person_name_conds.append(_name_match_predicate('PERSONINFO.CK_LST_NM', state.ppl.cmb_last_name_match.currentText(), state._person_last_name))
    state.has_person_info = bool(state.person_name_conds)
    state.adv_cv_corr = state.at.chk_cv_corr.isChecked()
    state.adv_accum_gt_prem = state.at.chk_accum_gt_prem.isChecked()
    state.adv_glp_neg = state.at.chk_glp_neg.isChecked()
    state.adv_sa_lt_orig = state.at.chk_sa_lt_orig.isChecked()
    state.adv_sa_gt_orig = state.at.chk_sa_gt_orig.isChecked()
    state.adv_apb_rider = state.at.chk_apb_rider.isChecked()
    state.adv_gcv_gt_cv = state.at.chk_gcv_gt_cv.isChecked()
