"""
CyberLife (DB2) query builder — builds the audit SQL from all tab controls.
"""
from __future__ import annotations

from .sql_helpers import (
    esc, in_list, selected_codes, today_str, normalize_date,
    add_int_range, add_date_range, add_decimal_range,
)


# Issue-state code → abbreviation map (subset — full 52-entry map)
_ISS_STATE_MAP = [
    ("02", "AZ"), ("03", "AR"), ("04", "CA"), ("05", "CO"),
    ("06", "CT"), ("07", "DE"), ("08", "DC"), ("09", "FL"),
    ("10", "GA"), ("11", "ID"), ("12", "IL"), ("13", "IN"),
    ("14", "IA"), ("15", "KS"), ("16", "KY"), ("17", "LA"),
    ("18", "ME"), ("19", "MD"), ("20", "MA"), ("21", "MI"),
    ("22", "MN"), ("23", "MS"), ("24", "MO"), ("25", "MT"),
    ("26", "NE"), ("27", "NV"), ("28", "NH"), ("29", "NJ"),
    ("30", "NM"), ("31", "NY"), ("32", "NC"), ("33", "ND"),
    ("34", "OH"), ("35", "OK"), ("36", "OR"), ("37", "PA"),
    ("38", "RI"), ("39", "SC"), ("40", "SD"), ("41", "TN"),
    ("42", "TX"), ("43", "UT"), ("44", "VT"), ("45", "VA"),
    ("46", "WA"), ("47", "WV"), ("48", "WI"), ("49", "WY"),
    ("50", "AK"), ("51", "HI"), ("52", "PR"),
]

# Reverse map: state abbreviation → DB2 numeric code
_STATE_ABBR_TO_CODE = {"AL": "01"}
_STATE_ABBR_TO_CODE.update({st: code for code, st in _ISS_STATE_MAP})

# Bill mode → (PMT_FQY_PER value, NSD_MD_CD value or None for standard)
_BILL_MODE_MAP = {
    "Monthly":     ("1", None),
    "Quarterly":   ("3", None),
    "Semiannual":  ("6", None),
    "Annual":      ("12", None),
    "BiWeekly":    ("1", "2"),
    "SemiMonthly": ("1", "S"),
    "9thly":       ("1", "9"),
    "10thly":      ("1", "A"),
}


def _build_bill_mode_where(modes: list[str]) -> str:
    """Build a compound OR clause for bill mode selections.

    Bill mode maps to two POLICY1 columns: PMT_FQY_PER and NSD_MD_CD.
    Standard modes (Monthly/Q/SA/A) use PMT_FQY_PER only (1/3/6/12).
    Non-standard modes (BiWeekly etc.) have PMT_FQY_PER=1 plus a NSD_MD_CD value.
    Monthly must exclude non-standard modes that also have PMT_FQY_PER=1.
    """
    parts = []
    for mode in modes:
        mapping = _BILL_MODE_MAP.get(mode)
        if not mapping:
            continue
        freq, nsd = mapping
        if nsd is None:
            if freq == "1":  # Monthly — must exclude non-standard
                parts.append(
                    f"(POLICY1.PMT_FQY_PER = {freq}"
                    f" AND COALESCE(POLICY1.NSD_MD_CD, '') = '')")
            else:
                parts.append(f"POLICY1.PMT_FQY_PER = {freq}")
        else:
            parts.append(
                f"(POLICY1.PMT_FQY_PER = {freq}"
                f" AND POLICY1.NSD_MD_CD = '{nsd}')")
    return " OR ".join(parts)


def build_cyberlife_sql(
    schema: str,
    sys_code: str,
    max_count_text: str,
    policy_tab,
    display_tab,
    policy2_tab,
    adv_tab,
    coverages_tab,
    plancode_tab,
    benefits_tab,
    transaction_tab=None,
) -> str:
    """Build the CyberLife audit SQL from all wired-up tab controls.

    Parameters
    ----------
    schema : str
        DB2 schema name derived from the selected region.
    sys_code : str
        System code from the bottom bar.
    max_count_text : str
        Max row count text (empty string for all rows).
    policy_tab, display_tab, policy2_tab, adv_tab, coverages_tab,
    plancode_tab, benefits_tab, transaction_tab
        The tab widgets with filter controls.
    """
    pt = policy_tab
    dt = display_tab
    p2t = policy2_tab
    at = adv_tab
    covt = coverages_tab

    # ── Check which range filters are active (for conditional SELECT columns) ──
    has_current_age = bool(pt.txt_current_age_lo.text().strip() or
                           pt.txt_current_age_hi.text().strip())
    has_pol_year = bool(pt.txt_pol_year_lo.text().strip() or
                        pt.txt_pol_year_hi.text().strip())
    has_issue_month = bool(pt.txt_issue_month_lo.text().strip() or
                           pt.txt_issue_month_hi.text().strip())
    has_issue_day = bool(pt.txt_issue_day_lo.text().strip() or
                         pt.txt_issue_day_hi.text().strip())
    has_paid_to = bool(pt.txt_paid_to_lo.text().strip() or
                       pt.txt_paid_to_hi.text().strip())
    has_gpe_date = bool(pt.txt_gpe_date_lo.text().strip() or
                        pt.txt_gpe_date_hi.text().strip())
    grace_indicator = bool(pt.chk_grace_indicator.isChecked() and
                           pt.list_grace_indicator.selectedItems())
    has_app_date = bool(pt.txt_app_date_lo.text().strip() or
                        pt.txt_app_date_hi.text().strip())
    has_billing_prem = bool(pt.txt_billing_prem_lo.text().strip() or
                            pt.txt_billing_prem_hi.text().strip())

    # ── Display tab checkbox states ──────────────────────────────
    disp_paid_to = dt.chk_paid_to_date.isChecked()
    disp_bill_to = dt.chk_bill_to_date.isChecked()
    disp_duration = dt.chk_current_duration.isChecked()
    disp_attained_age = dt.chk_current_attained_age.isChecked()
    disp_last_acct = dt.chk_last_acct_date.isChecked()
    disp_last_fin = dt.chk_last_fin_date.isChecked()
    disp_bill_prem = dt.chk_billable_prem.isChecked()
    disp_bill_mode = dt.chk_billable_mode.isChecked()
    disp_bill_form = dt.chk_billable_form.isChecked()
    disp_mkt_org = dt.chk_disp_mkt_org.isChecked()
    disp_reinsured = dt.chk_reinsured_code.isChecked()
    disp_last_entry = dt.chk_last_entry_code.isChecked()
    disp_orig_entry = dt.chk_orig_entry_code.isChecked()
    disp_spec_amt = dt.chk_disp_orig_curr_sa.isChecked()
    disp_tch_pol_id = dt.chk_tch_pol_id.isChecked()
    disp_mod_indicator = dt.chk_mod_indicator.isChecked()
    disp_prod_line = dt.chk_prod_line_code.isChecked()
    disp_sex_02 = dt.chk_disp_sex_02.isChecked()
    disp_subseries = dt.chk_subseries_code.isChecked()
    disp_mec_status = dt.chk_mec_status.isChecked()
    disp_app_date = dt.chk_application_date.isChecked()
    disp_next_notif = dt.chk_next_sched_notif.isChecked()
    disp_next_year_end = dt.chk_next_year_end.isChecked()
    disp_next_stmt = dt.chk_next_sched_stmt.isChecked()
    disp_next_change = dt.chk_next_change_cov1.isChecked()
    disp_init_term = dt.chk_init_term_period.isChecked()
    disp_commission_target = dt.chk_commission_target.isChecked()
    disp_monthly_mtp = dt.chk_monthly_min_target.isChecked()
    disp_accum_mtp = dt.chk_accum_monthly_min.isChecked()
    disp_accum_glp = dt.chk_accum_glp.isChecked()
    disp_nsp = dt.chk_nsp.isChecked()
    disp_shadow_av = dt.chk_shadow_av.isChecked()
    disp_db_option = dt.chk_death_benefit_opt.isChecked()
    disp_def_life_ins = dt.chk_def_life_ins.isChecked()
    disp_short_pay = dt.chk_short_pay.isChecked()
    disp_gpe_date = dt.chk_gpe_date.isChecked()
    disp_term_date = dt.chk_termination_date.isChecked()
    disp_accum_wd = dt.chk_accum_withdrawals.isChecked()
    disp_cost_basis = dt.chk_cost_basis.isChecked()
    disp_prem_ptd = dt.chk_premiums_ptd.isChecked()
    disp_prem_ytd = dt.chk_premiums_paid_ytd.isChecked()
    disp_accum_value = dt.chk_accum_value.isChecked()
    disp_policy_debt = dt.chk_policy_debt.isChecked()
    disp_substandard = dt.chk_disp_substandard.isChecked()
    disp_sex_rateclass = dt.chk_disp_sex_rateclass.isChecked()
    disp_tamra = dt.chk_tamra.isChecked()
    disp_gsp = dt.chk_gsp.isChecked()
    disp_glp = dt.chk_glp.isChecked()
    disp_bill_ctrl_num = dt.chk_billable_ctrl_num.isChecked()
    disp_slr_bill_form = dt.chk_slr_bill_form.isChecked()
    disp_orig_face_rpu = dt.chk_orig_face_rpu.isChecked()
    disp_prem_calc_rules = dt.chk_prem_calc_rules.isChecked()
    disp_cirf_key = dt.chk_cirf_key.isChecked()
    disp_trad_overloan = dt.chk_trad_overloan.isChecked()
    disp_replacement_pol = dt.chk_replacement_pol.isChecked()
    disp_converted_pol = dt.chk_converted_pol.isChecked()
    disp_conv_credit = dt.chk_conv_credit.isChecked()
    disp_within_conv = dt.chk_disp_conv_period.isChecked()
    disp_conv_period = dt.chk_disp_conv_period_calc.isChecked()
    disp_trad_cv_cov1 = dt.chk_trad_cv_cov1.isChecked()
    disp_account_value = dt.chk_account_value.isChecked()
    disp_insured1_info = dt.chk_insured1_info.isChecked()

    needs_grace_table = has_gpe_date or grace_indicator or disp_gpe_date

    # ── CTEs (only include what's needed) ────────────────────────
    sql_parts = [
        "WITH COVERAGE1 AS",
        f"  (SELECT * FROM {schema}.LH_COV_PHA C1 WHERE C1.COV_PHA_NBR = 1)",
    ]

    # ── Policy (2) tab flags ─────────────────────────────────
    has_tamra = bool(
        p2t.txt_tamra_7pay_prem_lo.text().strip() or p2t.txt_tamra_7pay_prem_hi.text().strip() or
        p2t.txt_tamra_7pay_av_lo.text().strip() or p2t.txt_tamra_7pay_av_hi.text().strip() or
        p2t.chk_1035_amt.isChecked() or p2t.chk_mec.isChecked())
    has_pol_totals = bool(
        p2t.txt_total_addl_prem_lo.text().strip() or p2t.txt_total_addl_prem_hi.text().strip() or
        p2t.txt_total_prem_addl_reg_lo.text().strip() or p2t.txt_total_prem_addl_reg_hi.text().strip() or
        p2t.txt_accum_wd_lo.text().strip() or p2t.txt_accum_wd_hi.text().strip() or
        disp_accum_wd or disp_cost_basis)
    needs_pol_yr_tot = bool(
        p2t.txt_prem_ytd_lo.text().strip() or p2t.txt_prem_ytd_hi.text().strip() or
        disp_prem_ytd)
    has_nontrad = bool(
        p2t.txt_bil_commence_dt_lo.text().strip() or p2t.txt_bil_commence_dt_hi.text().strip() or
        p2t.chk_billing_suspended.isChecked() or
        p2t.chk_failed_guideline.isChecked() or
        p2t.chk_def_life.isChecked() or
        (at.chk_grace_rule.isChecked() and at.list_grace_rule.selectedItems()) or
        (at.chk_db_option.isChecked() and at.list_db_option.selectedItems()))
    has_modcovsall = bool(p2t.chk_cov_gio.isChecked() or p2t.chk_cov_cola.isChecked())
    has_52r = bool(p2t.chk_is_replacement.isChecked() or p2t.chk_has_replacement_pol.isChecked())
    has_skipped_rein = p2t.chk_skipped_cov_rein.isChecked()
    has_slr = bool(p2t.chk_std_loan_payment.isChecked() and p2t.list_std_loan_payment.selectedItems())
    has_overloan = bool(p2t.chk_trad_overloan.isChecked() and p2t.list_trad_overloan.selectedItems())
    has_term_entry = bool(
        p2t.txt_term_entry_date_lo.text().strip() or p2t.txt_term_entry_date_hi.text().strip())
    has_77_segment = bool(
        p2t.chk_has_loan.isChecked() or
        p2t.txt_total_loan_prin_lo.text().strip() or p2t.txt_total_loan_prin_hi.text().strip() or
        p2t.txt_total_accured_lint_lo.text().strip() or p2t.txt_total_accured_lint_hi.text().strip())
    has_change_seq = bool(p2t.chk_change_seq.isChecked() and p2t.list_change_seq.selectedItems())

    # ── ADV tab flags ────────────────────────────────────────
    adv_cv_corr = at.chk_cv_corr.isChecked()
    adv_accum_gt_prem = at.chk_accum_gt_prem.isChecked()
    adv_glp_neg = at.chk_glp_neg.isChecked()
    adv_sa_lt_orig = at.chk_sa_lt_orig.isChecked()
    adv_sa_gt_orig = at.chk_sa_gt_orig.isChecked()
    adv_apb_rider = at.chk_apb_rider.isChecked()
    adv_gcv_gt_cv = at.chk_gcv_gt_cv.isChecked()
    adv_gcv_lt_cv = at.chk_gcv_lt_cv.isChecked()
    adv_grace_rule = bool(at.chk_grace_rule.isChecked() and at.list_grace_rule.selectedItems())
    adv_db_option = bool(at.chk_db_option.isChecked() and at.list_db_option.selectedItems())
    adv_orig_entry = bool(at.chk_orig_entry.isChecked() and at.list_orig_entry.selectedItems())
    adv_prem_alloc = bool(at.chk_prem_alloc.isChecked() and at.list_prem_alloc.selectedItems())
    adv_fund_id = at.txt_fund_id.text().strip()
    adv_fund_lo = at.txt_fund_lo.text().strip()
    adv_fund_hi = at.txt_fund_hi.text().strip()
    has_fund_values = bool(adv_fund_id or adv_fund_lo or adv_fund_hi)
    has_accum_val = bool(at.rng_accum_val[0].text().strip() or at.rng_accum_val[1].text().strip())
    has_shadow_av = bool(at.rng_shadow_acct[0].text().strip() or at.rng_shadow_acct[1].text().strip())
    has_curr_spec_amt = bool(at.rng_curr_spec_amt[0].text().strip() or at.rng_curr_spec_amt[1].text().strip())
    has_accum_mtp = bool(at.rng_accum_mtp[0].text().strip() or at.rng_accum_mtp[1].text().strip())
    has_accum_glp_range = bool(at.rng_accum_glp[0].text().strip() or at.rng_accum_glp[1].text().strip())
    has_type_p = bool(at.rng_type_p[0].text().strip() or at.rng_type_p[1].text().strip())
    has_type_v = bool(at.rng_type_v[0].text().strip() or at.rng_type_v[1].text().strip())
    # ── Policy tab: bottom checkboxes ──────────────────────
    multi_base_covs = pt.chk_multiple_base_covs.isChecked()
    is_mdo = pt.chk_is_mdo.isChecked()
    in_conversion = pt.chk_in_conversion.isChecked()

    # ── Coverages tab flags ──────────────────────────────────
    cov_val_class = covt.val_class.text().strip()
    cov_val_base = covt.val_base.text().strip()
    cov_val_sub = covt.val_sub.text().strip()
    cov_val_mort = covt.val_mort_table.text().strip()
    cov_rpu_mort = covt.rpu_mort_table.text().strip()
    cov_eti_mort = covt.eti_mort_table.text().strip()
    cov_nfo_rate = covt.nfo_int_rate.text().strip()
    cov_val_class_ne = covt.chk_val_class_ne_plan.isChecked()
    cov_multi_base = covt.chk_multiple_base.isChecked()
    cov_gio = covt.chk_cov_gio.isChecked()
    cov_cola = covt.chk_cov_cola.isChecked()
    cov_skipped_rein = covt.chk_skipped_cov_rein.isChecked()
    cov_cv_rate = covt.chk_cv_rate_gt_zero.isChecked()
    cov_gcv_gt_cv = covt.chk_gcv_gt_cv.isChecked()
    cov_gcv_lt_cv = covt.chk_gcv_lt_cv.isChecked()
    cov_non_trad = bool(covt.chk_non_trad.isChecked() and covt.list_non_trad.selectedItems())
    cov_spec_amt_lo = covt.txt_spec_amt_lo.text().strip()
    cov_spec_amt_hi = covt.txt_spec_amt_hi.text().strip()
    cov_has_spec_amt = bool(cov_spec_amt_lo or cov_spec_amt_hi)
    cov_init_term = bool(covt.chk_init_term.isChecked() and covt.list_init_term.selectedItems())

    # Base coverage column
    _bw = covt.base_cov_widgets
    cov_base_plancode = _bw["plancode"].text().strip()
    cov_base_prod_line = _bw["prod_line"].currentText().strip()
    cov_base_prod_ind = _bw["prod_ind"].currentText().strip()
    cov_base_form_number = _bw["form_number"].text().strip()
    cov_base_rateclass = _bw["rateclass"].currentText().strip()
    cov_base_sex67 = _bw["sex_code_67"].currentText().strip()
    cov_base_sex02 = _bw["sex_code_02"].currentText().strip()
    cov_base_person = _bw["person"].currentText().strip()
    cov_base_lives_cov = _bw["lives_cov"].currentText().strip()
    cov_base_change_type = _bw["change_type"].currentText().strip()
    cov_base_cola_ind = _bw["cola_ind"].currentText().strip()
    cov_base_gio_fio = _bw["gio_fio"].currentText().strip()
    cov_base_table03 = _bw["table_03"].isChecked()
    cov_base_flat03 = _bw["flat_03"].isChecked()
    cov_base_issue_lo = normalize_date(_bw["issue_date_lo"].text()) or ""
    cov_base_issue_hi = normalize_date(_bw["issue_date_hi"].text()) or ""
    cov_base_change_lo = normalize_date(_bw["change_date_lo"].text()) or ""
    cov_base_change_hi = normalize_date(_bw["change_date_hi"].text()) or ""
    # Base needs MODCOV1 join (TH_COV_PHA) for prod_ind, cola_ind, gio_fio
    cov_needs_modcov1 = bool(cov_base_prod_ind or cov_base_cola_ind or cov_base_gio_fio)
    # Base needs COV1_RENEWALS join (LH_COV_INS_RNL_RT) for rateclass/sex67
    cov_needs_renewals = bool(cov_base_rateclass or cov_base_sex67)

    # Rider helpers — build rider info dicts
    def _rider_info(widgets: dict) -> dict:
        info = {}
        info["plancode"] = widgets["plancode"].text().strip()
        info["prod_line"] = widgets["prod_line"].currentText().strip()
        info["prod_ind"] = widgets["prod_ind"].currentText().strip()
        info["rateclass"] = widgets["rateclass"].currentText().strip()
        info["sex_code_67"] = widgets["sex_code_67"].currentText().strip()
        info["sex_code_02"] = widgets["sex_code_02"].currentText().strip()
        info["person"] = widgets["person"].currentText().strip()
        info["lives_cov"] = widgets["lives_cov"].currentText().strip()
        info["change_type"] = widgets["change_type"].currentText().strip()
        info["cola_ind"] = widgets["cola_ind"].currentText().strip()
        info["gio_fio"] = widgets["gio_fio"].currentText().strip()
        info["addl_plancode"] = widgets.get("addl_plancode", None)
        if info["addl_plancode"] is not None:
            info["addl_plancode"] = info["addl_plancode"].currentText().strip()
        else:
            info["addl_plancode"] = ""
        info["table_03"] = widgets["table_03"].isChecked()
        info["flat_03"] = widgets["flat_03"].isChecked()
        info["post_issue"] = widgets.get("post_issue", None)
        if info["post_issue"] is not None:
            info["post_issue"] = info["post_issue"].isChecked()
        else:
            info["post_issue"] = False
        info["issue_date_lo"] = normalize_date(widgets["issue_date_lo"].text()) or ""
        info["issue_date_hi"] = normalize_date(widgets["issue_date_hi"].text()) or ""
        info["change_date_lo"] = normalize_date(widgets["change_date_lo"].text()) or ""
        info["change_date_hi"] = normalize_date(widgets["change_date_hi"].text()) or ""
        info["active"] = any([
            info["plancode"], info["prod_line"], info["prod_ind"],
            info["rateclass"], info["sex_code_67"], info["sex_code_02"],
            info["person"], info["lives_cov"], info["change_type"],
            info["cola_ind"], info["gio_fio"], info["addl_plancode"],
            info["table_03"], info["flat_03"], info["post_issue"],
            info["issue_date_lo"], info["issue_date_hi"],
            info["change_date_lo"], info["change_date_hi"],
        ])
        info["needs_covmod"] = bool(info["prod_ind"] or info["cola_ind"] or info["gio_fio"])
        info["needs_renewals"] = bool(info["rateclass"] or info["sex_code_67"])
        return info

    rider1_info = _rider_info(covt.rider1_widgets)
    rider2_info = _rider_info(covt.rider2_widgets)

    # Coverages tab needs MODCOVSALL (for cov_gio / cov_cola on any coverage)
    cov_needs_modcovsall = bool(cov_gio or cov_cola)
    # Extend shared flags with coverages tab
    has_modcovsall = has_modcovsall or cov_needs_modcovsall
    has_skipped_rein = has_skipped_rein or cov_skipped_rein
    multi_base_covs = multi_base_covs or cov_multi_base
    # Coverages tab needs COVSUMMARY (for spec amt range or multi base)
    cov_needs_covsummary = bool(cov_has_spec_amt or cov_multi_base)
    # Coverages tab needs ISWL GCV CTEs
    cov_needs_iswl_gcv = bool(cov_gcv_gt_cv or cov_gcv_lt_cv)
    # Coverages tab needs MVVAL (for GCV comparisons)
    cov_needs_mvval = bool(cov_gcv_gt_cv or cov_gcv_lt_cv)

    # Composite ADV flags
    needs_mvval = adv_cv_corr or adv_accum_gt_prem or has_accum_val or adv_gcv_gt_cv or adv_gcv_lt_cv or cov_needs_mvval or disp_accum_value or disp_prem_ptd or disp_account_value
    needs_iswl_gcv = adv_gcv_gt_cv or adv_gcv_lt_cv or cov_needs_iswl_gcv
    needs_interpolation = needs_iswl_gcv or disp_trad_cv_cov1 or disp_account_value
    needs_covsummary = (disp_spec_amt or multi_base_covs or adv_cv_corr
                        or adv_sa_lt_orig or adv_sa_gt_orig
                        or has_curr_spec_amt or needs_iswl_gcv
                        or cov_needs_covsummary)

    # LH_POL_YR_TOT CTEs — needed for Premiums Paid YTD
    if needs_pol_yr_tot:
        sql_parts.append(f", LH_POL_YR_TOT_withMaxDuration AS")
        sql_parts.append(f"  (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, MAX(POL_YR_DUR) MAX_DURATION")
        sql_parts.append(f"   FROM {schema}.LH_POL_YR_TOT")
        sql_parts.append(f"   GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)")
        sql_parts.append(f", LH_POL_YR_TOT_at_MaxDuration AS")
        sql_parts.append(f"  (SELECT YEARTOTS.*")
        sql_parts.append(f"   FROM {schema}.LH_POL_YR_TOT YEARTOTS")
        sql_parts.append(f"   INNER JOIN LH_POL_YR_TOT_withMaxDuration")
        sql_parts.append(f"     ON YEARTOTS.CK_SYS_CD = LH_POL_YR_TOT_withMaxDuration.CK_SYS_CD")
        sql_parts.append(f"    AND YEARTOTS.CK_CMP_CD = LH_POL_YR_TOT_withMaxDuration.CK_CMP_CD")
        sql_parts.append(f"    AND YEARTOTS.TCH_POL_ID = LH_POL_YR_TOT_withMaxDuration.TCH_POL_ID")
        sql_parts.append(f"    AND YEARTOTS.POL_YR_DUR = LH_POL_YR_TOT_withMaxDuration.MAX_DURATION)")

    # GPE Date / Grace Indicator require a GRACE_TABLE CTE
    if needs_grace_table:
        sql_parts.append(f", GRACE_TABLE AS")
        sql_parts.append(f"  (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND")
        sql_parts.append(f"   FROM {schema}.LH_NON_TRD_POL")
        sql_parts.append(f"   UNION")
        sql_parts.append(f"   SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND")
        sql_parts.append(f"   FROM {schema}.LH_TRD_POL)")

    # Policy(2): Termination Entry Date (69) CTEs
    if has_term_entry or disp_term_date:
        sql_parts.append(f", PRE_TERMINATION_DATES AS")
        sql_parts.append(f"  (SELECT FH.CK_CMP_CD, FH.TCH_POL_ID,")
        sql_parts.append(f"   MAX(FH.ENTRY_DT) AS TERM_ENTRY_DT")
        sql_parts.append(f"   FROM {schema}.FH_FIXED AS FH")
        sql_parts.append(f"   WHERE FH.TRANS IN ('SI', 'SF', 'TD', 'TM', 'TN', 'TL', 'TO')")
        sql_parts.append(f"   AND FH.FCB0_REV_IND = '0'")
        sql_parts.append(f"   AND FH.FCB2_REV_APPL_IND = '0'")
        sql_parts.append(f"   GROUP BY FH.CK_CMP_CD, FH.TCH_POL_ID)")
        _term_lo = normalize_date(p2t.txt_term_entry_date_lo.text()) or ""
        _term_hi = normalize_date(p2t.txt_term_entry_date_hi.text()) or ""
        if _term_lo or _term_hi:
            _tw = "WHERE 1=1"
            if _term_lo:
                _tw += f" AND PRE_TERMINATION_DATES.TERM_ENTRY_DT >= '{_term_lo}'"
            if _term_hi:
                _tw += f" AND PRE_TERMINATION_DATES.TERM_ENTRY_DT <= '{_term_hi}'"
            sql_parts.append(f", TERMINATION_DATES AS")
            sql_parts.append(f"  (SELECT * FROM PRE_TERMINATION_DATES {_tw})")
        else:
            sql_parts.append(f", TERMINATION_DATES AS")
            sql_parts.append(f"  (SELECT * FROM PRE_TERMINATION_DATES)")

    # Policy(2): Loan CTEs (77 segment)
    if has_77_segment or disp_policy_debt:
        sql_parts.append(f", ALL_LOANS AS (")
        sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PRF_LN_IND, LN_PRI_AMT,")
        sql_parts.append(f"    (CASE LN_ITS_AMT_TYP_CD WHEN '2' THEN POL_LN_ITS_AMT ELSE 0 END) LN_INT")
        sql_parts.append(f"  FROM {schema}.LH_FND_VAL_LOAN WHERE MVRY_DT = '9999-12-31'")
        sql_parts.append(f"  UNION")
        sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PRF_LN_IND, LN_PRI_AMT,")
        sql_parts.append(f"    (CASE LN_ITS_AMT_TYP_CD WHEN '2' THEN POL_LN_ITS_AMT ELSE 0 END) LN_INT")
        sql_parts.append(f"  FROM {schema}.LH_CSH_VAL_LOAN WHERE MVRY_DT = '9999-12-31')")
        sql_parts.append(f", POLICYDEBT AS (")
        sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,")
        sql_parts.append(f"    SUM(ALL_LOANS.LN_PRI_AMT) LOAN_PRINCIPLE,")
        sql_parts.append(f"    SUM(ALL_LOANS.LN_INT) LOAN_ACCRUED")
        sql_parts.append(f"  FROM ALL_LOANS")
        sql_parts.append(f"  GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)")

    # Policy(2): Change Seq (68) CTE
    if has_change_seq:
        sql_parts.append(f", CHANGE_SEGMENT AS (")
        sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, CHG_TYP_CD FROM {schema}.LH_COV_TMN")
        sql_parts.append(f"  UNION")
        sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, CHG_TYP_CD FROM {schema}.LH_NT_COV_CHG")
        sql_parts.append(f"  UNION")
        sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, CHG_TYP_CD FROM {schema}.LH_NT_COV_CHG_SCH")
        sql_parts.append(f"  UNION")
        sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, CHG_TYP_CD FROM {schema}.LH_SPM_BNF_CHG_SCH)")

    # Display tab: Billable Mode requires BILLMODE_POOL CTE
    if disp_bill_mode:
        sql_parts.append(f", BILLMODE_POOL AS")
        sql_parts.append(f"  (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,")
        sql_parts.append(f"   PMT_FQY_PER, NSD_MD_CD")
        sql_parts.append(f"   FROM {schema}.LH_BAS_POL)")

    # Display tab: Specified amount requires ALL_BASE_COVS + COVSUMMARY CTEs
    # ADV tab also uses COVSUMMARY for SA comparisons and ISWL GCV
    if needs_covsummary:
        _apb_cond = (" OR TEMPCOVALL.PLN_DES_SER_CD = '1U144A00'"
                     if adv_apb_rider else "")
        sql_parts.append(f", ALL_BASE_COVS AS (")
        sql_parts.append(f"  SELECT TEMPCOV1.CK_SYS_CD, TEMPCOV1.TCH_POL_ID, TEMPCOV1.CK_CMP_CD")
        sql_parts.append(f"    , TEMPCOVALL.COV_PHA_NBR")
        sql_parts.append(f"    , ROUND(REAL(TEMPCOVALL.COV_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT), 2) SPECAMT")
        sql_parts.append(f"    , ROUND(REAL(TEMPCOVALL.OGN_SPC_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT), 2) ORIGSPECAMT")
        if needs_iswl_gcv:
            sql_parts.append(f"    , ROUND(REAL(TEMPCOVALL.LOW_DUR_1_CSV_AMT) * REAL(TEMPCOVALL.COV_UNT_QTY), 2) CV1")
            sql_parts.append(f"    , ROUND(REAL(TEMPCOVALL.LOW_DUR_2_CSV_AMT) * REAL(TEMPCOVALL.COV_UNT_QTY), 2) CV2")
        sql_parts.append(f"  FROM {schema}.LH_COV_PHA TEMPCOV1")
        sql_parts.append(f"    INNER JOIN {schema}.LH_COV_PHA TEMPCOVALL")
        sql_parts.append(f"      ON TEMPCOV1.COV_PHA_NBR = 1")
        sql_parts.append(f"      AND TEMPCOV1.CK_SYS_CD = TEMPCOVALL.CK_SYS_CD")
        sql_parts.append(f"      AND TEMPCOV1.CK_CMP_CD = TEMPCOVALL.CK_CMP_CD")
        sql_parts.append(f"      AND TEMPCOV1.TCH_POL_ID = TEMPCOVALL.TCH_POL_ID")
        sql_parts.append(f"      AND (TEMPCOVALL.PLN_DES_SER_CD = TEMPCOV1.PLN_DES_SER_CD{_apb_cond}))")
        sql_parts.append(f", COVSUMMARY AS (")
        sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID")
        sql_parts.append(f"    , SUM(ALL_BASE_COVS.SPECAMT) TOTAL_SA")
        sql_parts.append(f"    , SUM(ALL_BASE_COVS.ORIGSPECAMT) TOTAL_ORIGINAL_SA")
        if multi_base_covs:
            sql_parts.append(f"    , COUNT(ALL_BASE_COVS.COV_PHA_NBR) BASECOVCOUNT")
        if needs_iswl_gcv:
            sql_parts.append(f"    , SUM(ALL_BASE_COVS.CV1) TOTAL_CV1")
            sql_parts.append(f"    , SUM(ALL_BASE_COVS.CV2) TOTAL_CV2")
        sql_parts.append(f"  FROM ALL_BASE_COVS")
        sql_parts.append(f"  GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)")

    # ADV: LASTMV + MVVAL CTEs (monthliversary values)
    if needs_mvval:
        sql_parts.append(f", LASTMV AS (")
        sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, MAX(MVRY_DT) LASTMVDT")
        sql_parts.append(f"  FROM {schema}.LH_POL_MVRY_VAL")
        sql_parts.append(f"  GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)")
        sql_parts.append(f", MVVAL AS (")
        sql_parts.append(f"  SELECT MV.CK_SYS_CD, MV.CK_CMP_CD, MV.TCH_POL_ID, MV.CSV_AMT")
        sql_parts.append(f"    , LASTMV.LASTMVDT")
        sql_parts.append(f"    , ROUND(REAL(MV.CSV_AMT) * REAL(ADVPROD.CDR_PCT)/100, 2) DB")
        sql_parts.append(f"    , CASE ADVPROD.DTH_BNF_PLN_OPT_CD")
        sql_parts.append(f"        WHEN '1' THEN 0")
        sql_parts.append(f"        WHEN '2' THEN REAL(MV.CSV_AMT)")
        sql_parts.append(f"        WHEN '3' THEN (TEMPPOLTOTALS.TOT_REG_PRM_AMT + TEMPPOLTOTALS.TOT_ADD_PRM_AMT)")
        sql_parts.append(f"        ELSE 0 END OPTDB")
        sql_parts.append(f"    , (TEMPPOLTOTALS.TOT_REG_PRM_AMT + TEMPPOLTOTALS.TOT_ADD_PRM_AMT) TOTALPREM")
        sql_parts.append(f"  FROM {schema}.LH_POL_MVRY_VAL MV")
        sql_parts.append(f"    INNER JOIN LASTMV ON MV.CK_SYS_CD = LASTMV.CK_SYS_CD")
        sql_parts.append(f"      AND MV.CK_CMP_CD = LASTMV.CK_CMP_CD")
        sql_parts.append(f"      AND MV.TCH_POL_ID = LASTMV.TCH_POL_ID")
        sql_parts.append(f"      AND MV.MVRY_DT = LASTMV.LASTMVDT")
        sql_parts.append(f"    INNER JOIN {schema}.LH_NON_TRD_POL ADVPROD")
        sql_parts.append(f"      ON MV.CK_SYS_CD = ADVPROD.CK_SYS_CD")
        sql_parts.append(f"      AND MV.CK_CMP_CD = ADVPROD.CK_CMP_CD")
        sql_parts.append(f"      AND MV.TCH_POL_ID = ADVPROD.TCH_POL_ID")
        sql_parts.append(f"    INNER JOIN {schema}.LH_POL_TOTALS TEMPPOLTOTALS")
        sql_parts.append(f"      ON MV.CK_SYS_CD = TEMPPOLTOTALS.CK_SYS_CD")
        sql_parts.append(f"      AND MV.CK_CMP_CD = TEMPPOLTOTALS.CK_CMP_CD")
        sql_parts.append(f"      AND MV.TCH_POL_ID = TEMPPOLTOTALS.TCH_POL_ID)")

    # INTERPOLATION_MONTHS CTE (shared by ISWL_GCV, Trad CV, Account Value)
    if needs_interpolation:
        sql_parts.append(f", INTERPOLATION_MONTHS AS (")
        sql_parts.append(f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID")
        sql_parts.append(f"    , REAL(12 - MONTHS_BETWEEN(BASPOL.NXT_MVRY_PRC_DT, BASPOL.LST_ANV_DT)) MONTHS_TO_NEXT_ANN")
        sql_parts.append(f"    , REAL(MONTHS_BETWEEN(BASPOL.NXT_MVRY_PRC_DT, BASPOL.LST_ANV_DT)) MONTHS_YTD")
        sql_parts.append(f"  FROM {schema}.LH_BAS_POL BASPOL)")

    # ADV: ISWL_INTERPOLATED_GCV CTE
    if needs_iswl_gcv:
        sql_parts.append(f", ISWL_INTERPOLATED_GCV AS (")
        sql_parts.append(f"  SELECT COVSUMMARY.CK_SYS_CD, COVSUMMARY.CK_CMP_CD, COVSUMMARY.TCH_POL_ID")
        sql_parts.append(f"    , ROUND((INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN * COVSUMMARY.TOTAL_CV2")
        sql_parts.append(f"            + INTERPOLATION_MONTHS.MONTHS_YTD * COVSUMMARY.TOTAL_CV1)/12, 2) ISWL_GCV")
        sql_parts.append(f"  FROM COVSUMMARY")
        sql_parts.append(f"    INNER JOIN INTERPOLATION_MONTHS")
        sql_parts.append(f"      ON COVSUMMARY.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD")
        sql_parts.append(f"      AND COVSUMMARY.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD")
        sql_parts.append(f"      AND COVSUMMARY.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID)")

    # Display: TRAD_CV CTE (interpolated cash value for Account Value display)
    if disp_account_value:
        sql_parts.append(f", TRAD_CV AS (")
        sql_parts.append(f"  SELECT COVERAGE1.CK_SYS_CD, COVERAGE1.CK_CMP_CD, COVERAGE1.TCH_POL_ID")
        sql_parts.append(f"    , (CASE WHEN COVERAGE1.LOW_DUR_1_CSV_AMT IS NULL THEN 0")
        sql_parts.append(f"            ELSE COVERAGE1.LOW_DUR_1_CSV_AMT END)")
        sql_parts.append(f"      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN")
        sql_parts.append(f"      + (CASE WHEN COVERAGE1.LOW_DUR_2_CSV_AMT IS NULL THEN 0")
        sql_parts.append(f"              ELSE COVERAGE1.LOW_DUR_2_CSV_AMT END)")
        sql_parts.append(f"      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_YTD  INTERP_CV")
        sql_parts.append(f"    , (CASE WHEN COVERAGE1.LOW_DUR_NSP_AMT IS NULL THEN 0")
        sql_parts.append(f"            ELSE COVERAGE1.LOW_DUR_NSP_AMT END)")
        sql_parts.append(f"      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN")
        sql_parts.append(f"      + (CASE WHEN COVERAGE1.LOW_DUR_1_NSP_AMT IS NULL THEN 0")
        sql_parts.append(f"              ELSE COVERAGE1.LOW_DUR_1_NSP_AMT END)")
        sql_parts.append(f"      * COVERAGE1.COV_UNT_QTY/12 * INTERPOLATION_MONTHS.MONTHS_YTD  INTERP_NSP")
        sql_parts.append(f"  FROM COVERAGE1")
        sql_parts.append(f"    INNER JOIN INTERPOLATION_MONTHS")
        sql_parts.append(f"      ON COVERAGE1.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD")
        sql_parts.append(f"      AND COVERAGE1.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD")
        sql_parts.append(f"      AND COVERAGE1.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID)")

    # ADV / Display: GLP CTE (guideline level premium)
    if adv_glp_neg or disp_glp:
        sql_parts.append(f", GLP AS (")
        sql_parts.append(f"  SELECT DISTINCT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,")
        sql_parts.append(f"    TEMPGLP.GDL_PRM_AMT GLP_VALUE")
        sql_parts.append(f"  FROM {schema}.LH_COV_INS_GDL_PRM TEMPGLP")
        sql_parts.append(f"  WHERE TEMPGLP.COV_PHA_NBR = 1")
        sql_parts.append(f"    AND TEMPGLP.PRM_RT_TYP_CD = 'A')")

    # Display: GSP CTE (guideline single premium)
    if disp_gsp:
        sql_parts.append(f", GSP AS (")
        sql_parts.append(f"  SELECT DISTINCT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,")
        sql_parts.append(f"    TEMPGSP.GDL_PRM_AMT GSP_VALUE")
        sql_parts.append(f"  FROM {schema}.LH_COV_INS_GDL_PRM TEMPGSP")
        sql_parts.append(f"  WHERE TEMPGSP.COV_PHA_NBR = 1")
        sql_parts.append(f"    AND TEMPGSP.PRM_RT_TYP_CD = 'S')")

    # Display: RPU Original Face (68 segment type 9 change)
    if disp_orig_face_rpu:
        sql_parts.append(f", CHANGE_TYPE9 AS (")
        sql_parts.append(f"  SELECT TMN.CK_SYS_CD, TMN.CK_CMP_CD, TMN.TCH_POL_ID")
        sql_parts.append(f"    , SUM(TMN.OGN_COV_UNT_QTY) TOTALORIGUNITS")
        sql_parts.append(f"  FROM {schema}.LH_COV_TMN TMN")
        sql_parts.append(f"    INNER JOIN {schema}.LH_NT_COV_CHG COVCHG")
        sql_parts.append(f"      ON COVCHG.CK_SYS_CD = TMN.CK_SYS_CD")
        sql_parts.append(f"      AND COVCHG.CK_CMP_CD = TMN.CK_CMP_CD")
        sql_parts.append(f"      AND COVCHG.TCH_POL_ID = TMN.TCH_POL_ID")
        sql_parts.append(f"      AND COVCHG.COV_PHA_NBR = TMN.COV_PHA_NBR")
        sql_parts.append(f"      AND COVCHG.CHG_TYP_CD = '9'")
        sql_parts.append(f"  GROUP BY TMN.CK_SYS_CD, TMN.CK_CMP_CD, TMN.TCH_POL_ID)")

    # Display: Insured1 Info (89) — primary insured name + DOB
    if disp_insured1_info:
        sql_parts.append(f", INSURED1_INFO AS (")
        sql_parts.append(f"  SELECT T1.CK_SYS_CD, T1.CK_CMP_CD, T1.TCH_POL_ID")
        sql_parts.append(f"    , T2.CK_FST_NM FNAME")
        sql_parts.append(f"    , T2.CK_LST_NM LNAME")
        sql_parts.append(f"    , T1.BIR_DT BIRTHDT")
        sql_parts.append(f"  FROM {schema}.LH_CTT_CLIENT T1")
        sql_parts.append(f"    INNER JOIN {schema}.VH_POL_HAS_LOC_CLT T2")
        sql_parts.append(f"      ON T1.PRS_SEQ_NBR = T2.PRS_SEQ_NBR")
        sql_parts.append(f"      AND T1.PRS_CD = T2.PRS_CD")
        sql_parts.append(f"      AND T1.TCH_POL_ID = T2.TCH_POL_ID")
        sql_parts.append(f"      AND T1.CK_SYS_CD = T2.CK_SYS_CD")
        sql_parts.append(f"      AND T1.CK_CMP_CD = T2.CK_CMP_CD")
        sql_parts.append(f"  WHERE T1.PRS_CD = '00')")

    # ADV: FUND_VALUES CTE (current fund value)
    if has_fund_values:
        sql_parts.append(f", FUND_VALUES AS (")
        sql_parts.append(f"  SELECT CK_CMP_CD, CK_SYS_CD, TCH_POL_ID, FND_ID_CD,")
        sql_parts.append(f"    SUM(CSV_AMT) FUNDAMT")
        sql_parts.append(f"  FROM {schema}.LH_POL_FND_VAL_TOT")
        sql_parts.append(f"  WHERE MVRY_DT = '9999-12-31'")
        sql_parts.append(f"  GROUP BY CK_CMP_CD, CK_SYS_CD, TCH_POL_ID, FND_ID_CD)")

    # ADV: ALLOCATION_FUNDS CTE (premium allocation funds — INTERSECT)
    if adv_prem_alloc:
        fund_items = [item.text().split(" - ")[0].strip()
                      for item in at.list_prem_alloc.selectedItems()]
        if fund_items:
            parts = []
            for fid in fund_items:
                parts.append(
                    f"  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID FROM {schema}.LH_FND_ALC"
                    f" WHERE FND_ID_CD = '{esc(fid)}' AND FND_ALC_PCT > 0 AND FND_ALC_TYP_CD = 'P'")
            sql_parts.append(f", ALLOCATION_FUNDS AS (")
            sql_parts.append("\n  INTERSECT\n".join(parts))
            sql_parts.append(f")")

    # ── SELECT ───────────────────────────────────────────────────
    sql_parts.append("")  # blank line between CTEs and main query
    sql_parts.append("SELECT DISTINCT")
    sql_parts.append("  CURRENT_DATE RunDate")
    sql_parts.append("  , POLICY1.CK_POLICY_NBR PolicyNumber")
    sql_parts.append("  , POLICY1.CK_CMP_CD CompanyCode")
    sql_parts.append("  , POLICY1.PRM_PAY_STA_REA_CD StatusCode")
    sql_parts.append("  , POLICY1.SUS_CD SuspenseCode")
    sql_parts.append("  , SUBSTR(POLICY1.SVC_AGC_NBR, 1, 1) AgentCode")
    # Issue state CASE expression
    sql_parts.append("  , CASE WHEN POLICY1.POL_ISS_ST_CD = '01' THEN 'AL'")
    for code, st in _ISS_STATE_MAP:
        sql_parts.append(f"    WHEN POLICY1.POL_ISS_ST_CD = '{code}' THEN '{st}'")
    sql_parts.append("    ELSE POLICY1.POL_ISS_ST_CD END IssueState")
    sql_parts.append("  , COVERAGE1.PLN_DES_SER_CD Plancode")
    sql_parts.append("  , COVERAGE1.POL_FRM_NBR FormNumber")
    sql_parts.append("  , VARCHAR_FORMAT(COVERAGE1.ISSUE_DT, 'MM/DD/YYYY') IssueDt")
    sql_parts.append("  , COVERAGE1.INS_ISS_AGE IssueAge")
    sql_parts.append("  , USERGEN.FUZGREIN_IND RGA_Ind")

    # ── Conditional SELECT columns for active range filters ──────
    duration_expr = ("TRUNCATE(MONTHS_BETWEEN('"
                     + today_str()
                     + "', COVERAGE1.ISSUE_DT) / 12, 0)")
    if has_current_age:
        sql_parts.append(f"  , INTEGER(COVERAGE1.INS_ISS_AGE + {duration_expr}) CurrentAge")
    if has_pol_year:
        sql_parts.append(f"  , INTEGER({duration_expr} + 1) PolicyYear")
    if has_issue_month:
        sql_parts.append("  , MONTH(COVERAGE1.ISSUE_DT) IssueMonth")
    if has_issue_day:
        sql_parts.append("  , DAY(COVERAGE1.ISSUE_DT) IssueDay")
    if has_paid_to:
        sql_parts.append("  , VARCHAR_FORMAT(POLICY1.PRM_PAID_TO_DT, 'MM/DD/YYYY') PaidToDate")
    if has_gpe_date:
        sql_parts.append("  , VARCHAR_FORMAT(GRACE_TABLE.GRA_PER_EXP_DT, 'MM/DD/YYYY') GPEDate")
    if has_app_date:
        sql_parts.append("  , VARCHAR_FORMAT(POLICY1.APP_WRT_DT, 'MM/DD/YYYY') AppDate")
    if has_billing_prem:
        sql_parts.append("  , POLICY1.POL_PRM_AMT BillingPrem")

    # ── Display tab: conditional SELECT columns ──────────────────
    # Circle 1: Paid To Date / Bill To Date
    if disp_paid_to:
        sql_parts.append("  , VARCHAR_FORMAT(POLICY1.PRM_PAID_TO_DT, 'MM/DD/YYYY') PaidToDate_Disp")
    if disp_bill_to:
        sql_parts.append("  , VARCHAR_FORMAT(POLICY1.PRM_BILL_TO_DT, 'MM/DD/YYYY') BillToDate")

    # Circle 2: Current Duration / Current Attained Age
    if disp_duration:
        sql_parts.append(f"  , INTEGER({duration_expr}) Duration")
    if disp_attained_age:
        sql_parts.append(f"  , INTEGER(COVERAGE1.INS_ISS_AGE + {duration_expr}) AttainedAge")

    # Circle 3: Last Accounting Date / Last Financial Date
    if disp_last_acct:
        sql_parts.append("  , VARCHAR_FORMAT(POLICY1.LST_ACT_TRS_DT, 'MM/DD/YYYY') LastAcctDate")
    if disp_last_fin:
        sql_parts.append("  , VARCHAR_FORMAT(POLICY1.LST_FIN_DT, 'MM/DD/YYYY') LastFinDate")

    # Circle 4: Billable Premium / Billable Mode / Billable Form
    if disp_bill_prem:
        sql_parts.append("  , IFNULL(POLICY1.POL_PRM_AMT, 0) BillPrem")
    if disp_bill_mode:
        sql_parts.append("  , (CASE BILLMODE_POOL.PMT_FQY_PER")
        sql_parts.append("      WHEN 1 THEN (CASE BILLMODE_POOL.NSD_MD_CD")
        sql_parts.append("        WHEN '2' THEN 'BiWeekly'")
        sql_parts.append("        WHEN 'S' THEN 'SemiMonthly'")
        sql_parts.append("        WHEN '9' THEN '9thly'")
        sql_parts.append("        WHEN 'A' THEN '10thly'")
        sql_parts.append("        ELSE 'Monthly' END)")
        sql_parts.append("      WHEN 3 THEN 'Quarterly'")
        sql_parts.append("      WHEN 6 THEN 'SemiAnnually'")
        sql_parts.append("      WHEN 12 THEN 'Annually'")
        sql_parts.append("      ELSE ' ' END) BillMode")
    if disp_bill_form:
        sql_parts.append("  , POLICY1.BIL_FRM_CD BillForm")

    # Circle 5: Market Org Code / Reinsured Code / Last Entry Code / Original Entry Code
    if disp_mkt_org:
        sql_parts.append("  , SUBSTR(POLICY1.SVC_AGC_NBR, 1, 1) MarkOrg")
    if disp_reinsured:
        sql_parts.append("  , POLICY1.REINSURED_CD ReinsuredCode")
    if disp_last_entry:
        sql_parts.append("  , POLICY1.LST_ETR_CD LastEntryCode")
        sql_parts.append("  , VARCHAR_FORMAT(POLICY1.LST_FIN_DT, 'MM/DD/YYYY') LastFinDate_Entry")
    if disp_orig_entry:
        sql_parts.append("  , POLICY1.OGN_ETR_CD OrigEntryCode")

    # Circle 6: Original and current specified amount
    if disp_spec_amt or multi_base_covs:
        sql_parts.append("  , COVSUMMARY.TOTAL_SA TotalFace")
        sql_parts.append("  , COVSUMMARY.TOTAL_ORIGINAL_SA TotalOriginalFace")

    # Circle 7: Simple POLICY1 / COVERAGE1 display columns
    if disp_tch_pol_id:
        sql_parts.append("  , POLICY1.TCH_POL_ID TCH_POL_ID")
    if disp_mod_indicator or is_mdo:
        sql_parts.append("  , SUBSTR(POLICY1.USR_RES_CD, 1, 1) MDO")
    if disp_prod_line:
        sql_parts.append("  , COVERAGE1.PRD_LIN_TYP_CD")
    if disp_sex_02:
        sql_parts.append("  , COVERAGE1.INS_SEX_CD SEX_CD")
    if disp_subseries:
        sql_parts.append("  , COVERAGE1.LIF_PLN_SUB_SRE_CD SUBSERIES")
    if disp_mec_status:
        sql_parts.append("  , (CASE")
        sql_parts.append("      WHEN POLICY1.MEC_STATUS_CD = '0' THEN '0 - NO'")
        sql_parts.append("      WHEN POLICY1.MEC_STATUS_CD = '1' THEN '1 - YES'")
        sql_parts.append("      WHEN POLICY1.MEC_STATUS_CD = '2' THEN '2 - NO'")
        sql_parts.append("      ELSE POLICY1.MEC_STATUS_CD")
        sql_parts.append("      END) MEC_INDICATOR_01")
    if disp_app_date:
        sql_parts.append("  , VARCHAR_FORMAT(POLICY1.APP_WRT_DT, 'MM/DD/YYYY') AppDt")
    if disp_next_notif:
        sql_parts.append("  , VARCHAR_FORMAT(POLICY1.NXT_SCH_NOT_DT, 'MM/DD/YYYY') NextNotifyDt")
    if disp_next_year_end:
        sql_parts.append("  , VARCHAR_FORMAT(POLICY1.NXT_YR_END_PRC_DT, 'MM/DD/YYYY') NextYearEndDt")
    if disp_next_stmt:
        sql_parts.append("  , VARCHAR_FORMAT(POLICY1.NXT_SCH_STT_DT, 'MM/DD/YYYY') NextStatementDt")
    if disp_next_change:
        sql_parts.append("  , COVERAGE1.NXT_CHG_TYP_CD NextChangeType")
        sql_parts.append("  , VARCHAR_FORMAT(COVERAGE1.NXT_CHG_DT, 'MM/DD/YYYY') NextChangeDt")
    if disp_init_term:
        sql_parts.append("  , COVERAGE1.INT_RNL_PER")
        sql_parts.append("  , COVERAGE1.SBQ_RNL_STR_DUR")
        sql_parts.append("  , COVERAGE1.SBQ_RNL_PER")

    # Circle 8: Target / value display columns
    if disp_commission_target:
        sql_parts.append("  , COMMTARGET.TAR_PRM_AMT CTP")
    if disp_monthly_mtp:
        sql_parts.append("  , MTP.TAR_PRM_AMT MonthlyMTP")
    if disp_accum_mtp:
        sql_parts.append("  , ACCUMMTP.TAR_PRM_AMT ACCUMMTP")
    if disp_accum_glp:
        sql_parts.append("  , ACCUMGLP.TAR_PRM_AMT ACCUMGLP")
    if disp_nsp:
        sql_parts.append("  , NSPTARGET.TAR_PRM_AMT NSP")
    if disp_shadow_av:
        sql_parts.append("  , SHADOWAV.TAR_PRM_AMT ShadowAV")
    if disp_db_option:
        sql_parts.append("  , NONTRAD.DTH_BNF_PLN_OPT_CD DBOpt")
    if disp_def_life_ins:
        sql_parts.append("  , (CASE")
        sql_parts.append("      WHEN NONTRAD.TFDF_CD = '1' THEN '1 - GPT TEFRA'")
        sql_parts.append("      WHEN NONTRAD.TFDF_CD = '2' THEN '2 - GPT DEFRA'")
        sql_parts.append("      WHEN NONTRAD.TFDF_CD = '3' THEN '3 - CVAT DEFRA'")
        sql_parts.append("      WHEN NONTRAD.TFDF_CD = '4' THEN '4 - GPT Selected'")
        sql_parts.append("      WHEN NONTRAD.TFDF_CD = '5' THEN '5 - CVAT Selected'")
        sql_parts.append("      ELSE NONTRAD.TFDF_CD")
        sql_parts.append("      END) DefOfLifeIns")
    if disp_short_pay:
        sql_parts.append("  , SHORTPAY_PRM.TAR_PRM_AMT SHORTPAY_AMT")
        sql_parts.append("  , VARCHAR_FORMAT(SHORTPAY_PRM.TAR_DT, 'MM/DD/YYYY') SHORTPAY_CEASEDT")
        sql_parts.append("  , USERDEF_52G.INITIAL_PAY_DUR SHORTPAY_DUR")
        sql_parts.append("  , USERDEF_52G.INITIAL_MODE SHORTPAY_MODE")
        sql_parts.append("  , USERDEF_52G.DIAL_TO_PREM_AGE SHORTPAY_DBAGE")

    # Circle 9: Columns requiring existing CTEs / JOINs
    if disp_gpe_date:
        sql_parts.append("  , VARCHAR_FORMAT(GRACE_TABLE.GRA_PER_EXP_DT, 'MM/DD/YYYY') GPE_DT")
    if disp_term_date:
        sql_parts.append("  , VARCHAR_FORMAT(TD.TERM_ENTRY_DT, 'MM/DD/YYYY') TERM_ENTRY_DT")
    if disp_accum_wd:
        sql_parts.append("  , POLICY_TOTALS.TOT_WTD_AMT")
    if disp_cost_basis:
        sql_parts.append("  , POLICY_TOTALS.POL_CST_BSS_AMT COSTBASIS")
    if disp_prem_ptd or disp_accum_value:
        sql_parts.append("  , VARCHAR_FORMAT(MVVAL.LASTMVDT, 'MM/DD/YYYY') LastMonthliverary")
        sql_parts.append("  , MVVAL.CSV_AMT CurrCV")
        sql_parts.append("  , MVVAL.TOTALPREM")
    if disp_prem_ytd:
        sql_parts.append("  , LH_POL_YR_TOT_at_MaxDuration.YTD_TOT_PMT_AMT")
    if disp_policy_debt:
        sql_parts.append("  , POLICYDEBT.LOAN_PRINCIPLE")
        sql_parts.append("  , POLICYDEBT.LOAN_ACCRUED")
        sql_parts.append("  , (CASE")
        sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '0' THEN 'FIX'")
        sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '1' THEN 'FIX'")
        sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '6' THEN 'VAR'")
        sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '7' THEN 'VAR'")
        sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '9' THEN 'NA'")
        sql_parts.append("      ELSE POLICY1.LN_TYP_CD")
        sql_parts.append("      END) LOAN_TYPE")
        sql_parts.append("  , (CASE")
        sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '0' THEN 'ADVANCE'")
        sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '1' THEN 'ARREARS'")
        sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '6' THEN 'ADVANCE'")
        sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '7' THEN 'ARREARS'")
        sql_parts.append("      WHEN POLICY1.LN_TYP_CD = '9' THEN 'NA'")
        sql_parts.append("      ELSE POLICY1.LN_TYP_CD")
        sql_parts.append("      END) LOAN_TIMING")

    # Circle 10: Batch 4 — new JOINs / CTEs required
    if disp_substandard:
        sql_parts.append("  , (CASE WHEN TABLE_RATING1.SST_XTR_RT_TBL_CD IS NULL THEN ' ' ELSE TABLE_RATING1.SST_XTR_RT_TBL_CD END) TableRating")
        sql_parts.append("  , (CASE WHEN FLAT_EXTRA1.SST_XTR_UNT_AMT IS NULL THEN '0' ELSE FLAT_EXTRA1.SST_XTR_UNT_AMT END) MONTHFLAT")
    if disp_sex_rateclass:
        sql_parts.append("  , COV1_RENEWALS.RT_CLS_CD RenewalClass")
        sql_parts.append("  , COV1_RENEWALS.RT_SEX_CD RenewalSex")
    if disp_tamra:
        sql_parts.append("  , TAMRA.SVPY_LVL_PRM_AMT TAMRA7PAY")
    if disp_gsp:
        sql_parts.append("  , GSP.GSP_VALUE")
    if disp_glp:
        sql_parts.append("  , GLP.GLP_VALUE")
    if disp_bill_ctrl_num:
        sql_parts.append("  , BILL_CONTROL.BIL_CTL_NBR BillControl")
    if disp_slr_bill_form:
        sql_parts.append("  , SLR_BILL_CONTROL.BIL_FRM_CD SLRBillForm")
    if disp_orig_face_rpu:
        sql_parts.append("  , CHANGE_TYPE9.TOTALORIGUNITS")
    if disp_prem_calc_rules:
        sql_parts.append("  , FIXPREM.MD_PRM_MUL_ORD_CD")
        sql_parts.append("  , FIXPREM.RT_FCT_ORD_CD")
        sql_parts.append("  , FIXPREM.ROU_RLE_CD")
    if disp_cirf_key:
        sql_parts.append("  , FFC.CUR_ITS_RT_SER_NBR CIRF_Key")
    if disp_trad_overloan:
        sql_parts.append("  , POLICY1_MOD.OVERLOAN_IND")
    if disp_replacement_pol:
        sql_parts.append("  , USERDEF_52R.REPLACED_POLICY REPLACED_POL")

    # Circle 11: Batch 5 — Conversion-related display fields
    if disp_converted_pol:
        sql_parts.append("  , USERGEN.EXCH_POL_NUMBER EXCHANGE_POL")
        sql_parts.append("  , USERGEN.EXCHANGE EXCHANGE_CD")
        sql_parts.append("  , USERGEN.SOURCE_COV_PHASE CONV_COV")
        sql_parts.append("  , USERGEN.SOURCE_ISSUE_DATE CONV_ISSDT")
        sql_parts.append("  , USERGEN.SOURCE_PLAN_CODE CONV_PLAN")
        sql_parts.append("  , USERGEN.SOURCE_FACE_AMT CONV_FACE")
    if disp_conv_credit:
        sql_parts.append("  , UPDF.CONV_CREDIT_IND CN_CRED_IND")
        sql_parts.append("  , UPDF.CONV_CREDIT_RULE CN_CRED_RULE")
        sql_parts.append("  , UPDF.CONV_CREDIT_PERIOD CN_CRED_PERIOD")
    if disp_within_conv:
        _today = today_str()
        _dur = f"TRUNCATE(MONTHS_BETWEEN('{_today}', COVERAGE1.ISSUE_DT) / 12, 0)"
        _att_age = f"(COVERAGE1.INS_ISS_AGE + {_dur})"
        sql_parts.append("  , (CASE")
        sql_parts.append(f"      WHEN (UPDF.CONVERSION_PERIOD = 0 AND {_att_age} < UPDF.CONVERSION_AGE)")
        sql_parts.append(f"        OR (UPDF.CONVERSION_PERIOD > 0 AND {_dur} < UPDF.CONVERSION_PERIOD")
        sql_parts.append(f"            AND {_att_age} < UPDF.CONVERSION_AGE)")
        sql_parts.append("      THEN 'TRUE' ELSE 'FALSE'")
        sql_parts.append("      END) AS WITHIN_CONV_PERIOD")
    if disp_conv_period:
        sql_parts.append("  , UPDF.CONVERSION_PERIOD CN_PERIOD")
        sql_parts.append("  , UPDF.CONVERSION_AGE CN_AGE")
        sql_parts.append("  , UPDF.CONV_TO_TRM_PERIOD CN_TO_TERM_PERIOD")

    # Circle 12: Trad Cash Value Cov1 / Account Value
    if disp_trad_cv_cov1:
        sql_parts.append("  , (CASE WHEN COVERAGE1.LOW_DUR_1_CSV_AMT IS NULL THEN '0' ELSE COVERAGE1.LOW_DUR_1_CSV_AMT END) BCVR_COV1")
        sql_parts.append("  , (CASE WHEN COVERAGE1.LOW_DUR_2_CSV_AMT IS NULL THEN '0' ELSE COVERAGE1.LOW_DUR_2_CSV_AMT END) ECVR_COV1")
        sql_parts.append("  , INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN")
        sql_parts.append("  , INTERPOLATION_MONTHS.MONTHS_YTD")
        sql_parts.append("  , (CASE WHEN COVERAGE1.LOW_DUR_1_CSV_AMT IS NULL THEN 0 ELSE COVERAGE1.LOW_DUR_1_CSV_AMT END)")
        sql_parts.append("    * COVERAGE1.COV_UNT_QTY * INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN")
        sql_parts.append("    + (CASE WHEN COVERAGE1.LOW_DUR_2_CSV_AMT IS NULL THEN 0 ELSE COVERAGE1.LOW_DUR_2_CSV_AMT END)")
        sql_parts.append("    * COVERAGE1.COV_UNT_QTY * INTERPOLATION_MONTHS.MONTHS_YTD CV_COV1")
    if disp_account_value:
        sql_parts.append("  , MVVAL.CSV_AMT")
        sql_parts.append("  , TRAD_CV.INTERP_NSP")
        sql_parts.append("  , TRAD_CV.INTERP_CV")
        sql_parts.append("  , COVERAGE1.ADV_PRD_IND")
        sql_parts.append("  , COVERAGE1.LOW_DUR_CSV_AMT")
        sql_parts.append("  , COVERAGE1.LOW_DUR_1_CSV_AMT")
        sql_parts.append("  , COVERAGE1.LOW_DUR_NSP_AMT")
        sql_parts.append("  , COVERAGE1.LOW_DUR_1_NSP_AMT")

    # Circle 13: Insured1 Info
    if disp_insured1_info:
        sql_parts.append("  , INSURED1_INFO.FNAME")
        sql_parts.append("  , INSURED1_INFO.LNAME")
        sql_parts.append("  , VARCHAR_FORMAT(INSURED1_INFO.BIRTHDT, 'MM/DD/YYYY') BIRTHDT")

    # ── Display tab: Trad rates - cov 1 ─────────────────────────
    disp_trad_rates = dt.Checkbox_DisplayTradRates.isChecked()
    if disp_trad_rates:
        sql_parts.append("  , FXD_PRM.POL_FEE_AMT PolFee")
        sql_parts.append("  , FXD_PRM.SAN_MD_FCT SemiAnnModalFactor")
        sql_parts.append("  , FXD_PRM.QTR_MD_FCT QtrModalFactor")
        sql_parts.append("  , FXD_PRM.MO_MD_FCT MoModalFactor")
        sql_parts.append("  , COVERAGE1.ANN_PRM_UNT_AMT PremRate")
        sql_parts.append("  , POLICY1.POL_PRM_AMT PolPremium")

    # ── FROM + JOINs ─────────────────────────────────────────────
    sql_parts.append(f"FROM {schema}.LH_BAS_POL POLICY1")
    sql_parts.append(f"  INNER JOIN {schema}.LH_COV_PHA COVSALL")
    sql_parts.append("    ON POLICY1.CK_SYS_CD = COVSALL.CK_SYS_CD")
    sql_parts.append("    AND POLICY1.CK_CMP_CD = COVSALL.CK_CMP_CD")
    sql_parts.append("    AND POLICY1.TCH_POL_ID = COVSALL.TCH_POL_ID")
    sql_parts.append("  INNER JOIN COVERAGE1")
    sql_parts.append("    ON POLICY1.CK_SYS_CD = COVERAGE1.CK_SYS_CD")
    sql_parts.append("    AND POLICY1.CK_CMP_CD = COVERAGE1.CK_CMP_CD")
    sql_parts.append("    AND POLICY1.TCH_POL_ID = COVERAGE1.TCH_POL_ID")
    sql_parts.append(f"  LEFT OUTER JOIN {schema}.TH_USER_GENERIC USERGEN")
    sql_parts.append("    ON POLICY1.CK_SYS_CD = USERGEN.CK_SYS_CD")
    sql_parts.append("    AND POLICY1.CK_CMP_CD = USERGEN.CK_CMP_CD")
    sql_parts.append("    AND POLICY1.TCH_POL_ID = USERGEN.TCH_POL_ID")

    # Display tab: Trad rates JOIN
    if disp_trad_rates:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_FXD_PRM_POL FXD_PRM")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = FXD_PRM.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = FXD_PRM.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = FXD_PRM.TCH_POL_ID")

    # Display tab: Billable Mode JOIN
    if disp_bill_mode:
        sql_parts.append("  LEFT OUTER JOIN BILLMODE_POOL")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = BILLMODE_POOL.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = BILLMODE_POOL.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = BILLMODE_POOL.TCH_POL_ID")

    # Display tab / ADV / Policy: COVSUMMARY JOIN
    if needs_covsummary:
        _cov_join = "INNER JOIN" if multi_base_covs else "LEFT OUTER JOIN"
        sql_parts.append(f"  {_cov_join} COVSUMMARY")
        sql_parts.append("    ON COVSUMMARY.CK_SYS_CD = POLICY1.CK_SYS_CD")
        sql_parts.append("    AND COVSUMMARY.CK_CMP_CD = POLICY1.CK_CMP_CD")
        sql_parts.append("    AND COVSUMMARY.TCH_POL_ID = POLICY1.TCH_POL_ID")

    # In conversion period / conversion display fields requires TH_USER_PDF (52-1)
    if in_conversion or disp_conv_credit or disp_within_conv or disp_conv_period:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.TH_USER_PDF UPDF")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = UPDF.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = UPDF.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = UPDF.TCH_POL_ID")
        sql_parts.append("    AND UPDF.TYPE_SEQUENCE = 1")

    # Display tab: Insured1 Info JOIN (CTE)
    if disp_insured1_info:
        sql_parts.append("  LEFT OUTER JOIN INSURED1_INFO")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = INSURED1_INFO.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = INSURED1_INFO.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = INSURED1_INFO.TCH_POL_ID")

    # GPE Date / Grace Indicator requires joining GRACE_TABLE
    if needs_grace_table:
        sql_parts.append("  INNER JOIN GRACE_TABLE")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = GRACE_TABLE.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = GRACE_TABLE.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = GRACE_TABLE.TCH_POL_ID")

    # ── Policy (2) JOINs ────────────────────────────────────────
    if has_tamra or disp_tamra:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_TAMRA_7_PY_PER TAMRA")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = TAMRA.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = TAMRA.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = TAMRA.TCH_POL_ID")
    if has_pol_totals:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_POL_TOTALS POLICY_TOTALS")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = POLICY_TOTALS.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = POLICY_TOTALS.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = POLICY_TOTALS.TCH_POL_ID")
    if needs_pol_yr_tot:
        sql_parts.append("  LEFT OUTER JOIN LH_POL_YR_TOT_at_MaxDuration")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = LH_POL_YR_TOT_at_MaxDuration.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = LH_POL_YR_TOT_at_MaxDuration.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = LH_POL_YR_TOT_at_MaxDuration.TCH_POL_ID")
    if has_nontrad or disp_db_option or disp_def_life_ins:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_NON_TRD_POL NONTRAD")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = NONTRAD.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = NONTRAD.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = NONTRAD.TCH_POL_ID")
    if has_modcovsall:
        sql_parts.append(f"  INNER JOIN {schema}.TH_COV_PHA MODCOVSALL")
        sql_parts.append("    ON MODCOVSALL.CK_SYS_CD = COVSALL.CK_SYS_CD")
        sql_parts.append("    AND MODCOVSALL.CK_CMP_CD = COVSALL.CK_CMP_CD")
        sql_parts.append("    AND MODCOVSALL.TCH_POL_ID = COVSALL.TCH_POL_ID")
        sql_parts.append("    AND MODCOVSALL.COV_PHA_NBR = COVSALL.COV_PHA_NBR")
    if has_52r or disp_replacement_pol:
        _52r_join = "INNER JOIN" if has_52r else "LEFT OUTER JOIN"
        sql_parts.append(f"  {_52r_join} {schema}.TH_USER_REPLACEMENT USERDEF_52R")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = USERDEF_52R.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = USERDEF_52R.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = USERDEF_52R.TCH_POL_ID")
    if has_skipped_rein:
        sql_parts.append(f"  INNER JOIN {schema}.LH_COV_SKIPPED_PER REINSTATEMENT")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = REINSTATEMENT.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = REINSTATEMENT.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = REINSTATEMENT.TCH_POL_ID")
    if has_slr or disp_slr_bill_form:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_LN_RPY_TRM SLR_BILL_CONTROL")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = SLR_BILL_CONTROL.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = SLR_BILL_CONTROL.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = SLR_BILL_CONTROL.TCH_POL_ID")
    if has_overloan or disp_trad_overloan:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.TH_BAS_POL POLICY1_MOD")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = POLICY1_MOD.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = POLICY1_MOD.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = POLICY1_MOD.TCH_POL_ID")
    if has_term_entry or disp_term_date:
        _td_join = "INNER JOIN" if has_term_entry else "LEFT OUTER JOIN"
        sql_parts.append(f"  {_td_join} TERMINATION_DATES AS TD")
        sql_parts.append("    ON POLICY1.CK_CMP_CD = TD.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = TD.TCH_POL_ID")
    if has_77_segment or disp_policy_debt:
        _loan_join = "INNER JOIN" if has_77_segment else "LEFT OUTER JOIN"
        sql_parts.append(f"  {_loan_join} ALL_LOANS")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = ALL_LOANS.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = ALL_LOANS.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = ALL_LOANS.TCH_POL_ID")
        if has_77_segment and p2t.chk_has_preferred_loan.isChecked():
            sql_parts.append("    AND ALL_LOANS.PRF_LN_IND = '1'")
        _debt_join = "INNER JOIN" if has_77_segment else "LEFT OUTER JOIN"
        sql_parts.append(f"  {_debt_join} POLICYDEBT")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = POLICYDEBT.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = POLICYDEBT.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = POLICYDEBT.TCH_POL_ID")
    if has_change_seq:
        sql_parts.append("  INNER JOIN CHANGE_SEGMENT")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = CHANGE_SEGMENT.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = CHANGE_SEGMENT.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = CHANGE_SEGMENT.TCH_POL_ID")

    # ── ADV tab JOINs ────────────────────────────────────────────
    if needs_mvval:
        sql_parts.append("  LEFT OUTER JOIN MVVAL")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = MVVAL.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = MVVAL.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = MVVAL.TCH_POL_ID")
    if needs_iswl_gcv:
        sql_parts.append("  INNER JOIN ISWL_INTERPOLATED_GCV")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = ISWL_INTERPOLATED_GCV.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = ISWL_INTERPOLATED_GCV.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = ISWL_INTERPOLATED_GCV.TCH_POL_ID")
    if adv_glp_neg or disp_glp:
        _glp_join = "INNER JOIN" if adv_glp_neg else "LEFT OUTER JOIN"
        sql_parts.append(f"  {_glp_join} GLP")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = GLP.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = GLP.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = GLP.TCH_POL_ID")
    # Display tab: Trad Cash Value Cov1 needs INTERPOLATION_MONTHS
    if disp_trad_cv_cov1:
        sql_parts.append("  LEFT OUTER JOIN INTERPOLATION_MONTHS")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID")
    # Display tab: Account Value needs TRAD_CV
    if disp_account_value:
        sql_parts.append("  LEFT OUTER JOIN TRAD_CV")
        sql_parts.append("    ON COVERAGE1.CK_SYS_CD = TRAD_CV.CK_SYS_CD")
        sql_parts.append("    AND COVERAGE1.CK_CMP_CD = TRAD_CV.CK_CMP_CD")
        sql_parts.append("    AND COVERAGE1.TCH_POL_ID = TRAD_CV.TCH_POL_ID")
    if has_fund_values:
        _fid = adv_fund_id
        sql_parts.append("  INNER JOIN FUND_VALUES")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = FUND_VALUES.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = FUND_VALUES.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = FUND_VALUES.TCH_POL_ID")
        if _fid:
            sql_parts.append(f"    AND FUND_VALUES.FND_ID_CD = '{esc(_fid)}'")
    if adv_prem_alloc:
        sql_parts.append("  INNER JOIN ALLOCATION_FUNDS")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = ALLOCATION_FUNDS.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = ALLOCATION_FUNDS.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = ALLOCATION_FUNDS.TCH_POL_ID")
    if has_type_p:
        sql_parts.append(f"  INNER JOIN {schema}.LH_FND_TRS_ALC_SET ALLOCATION_P_COUNT")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = ALLOCATION_P_COUNT.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = ALLOCATION_P_COUNT.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = ALLOCATION_P_COUNT.TCH_POL_ID")
        sql_parts.append("    AND ALLOCATION_P_COUNT.FND_TRS_TYP_CD = 'P'")
    if has_type_v:
        sql_parts.append(f"  INNER JOIN {schema}.LH_FND_TRS_ALC_SET ALLOCATION_V_COUNT")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = ALLOCATION_V_COUNT.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = ALLOCATION_V_COUNT.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = ALLOCATION_V_COUNT.TCH_POL_ID")
        sql_parts.append("    AND ALLOCATION_V_COUNT.FND_TRS_TYP_CD = 'V'")
    if has_shadow_av or disp_shadow_av:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_COV_TARGET SHADOWAV")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = SHADOWAV.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = SHADOWAV.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = SHADOWAV.TCH_POL_ID")
        sql_parts.append("    AND SHADOWAV.TAR_TYP_CD = 'XP'")
    if has_accum_mtp or disp_accum_mtp:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_POL_TARGET ACCUMMTP")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = ACCUMMTP.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = ACCUMMTP.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = ACCUMMTP.TCH_POL_ID")
        sql_parts.append("    AND ACCUMMTP.TAR_TYP_CD = 'MA'")
    if has_accum_glp_range or disp_accum_glp:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_POL_TARGET ACCUMGLP")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = ACCUMGLP.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = ACCUMGLP.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = ACCUMGLP.TCH_POL_ID")
        sql_parts.append("    AND ACCUMGLP.TAR_TYP_CD = 'TA'")
    # Display tab: Commission Target JOIN
    if disp_commission_target:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_COM_TARGET COMMTARGET")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = COMMTARGET.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = COMMTARGET.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = COMMTARGET.TCH_POL_ID")
        sql_parts.append("    AND COMMTARGET.TAR_TYP_CD = 'CT'")
    # Display tab: Monthly Min Target JOIN
    if disp_monthly_mtp:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_POL_TARGET MTP")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = MTP.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = MTP.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = MTP.TCH_POL_ID")
        sql_parts.append("    AND MTP.TAR_TYP_CD = 'MT'")
    # Display tab: NSP JOIN
    if disp_nsp:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_POL_TARGET NSPTARGET")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = NSPTARGET.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = NSPTARGET.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = NSPTARGET.TCH_POL_ID")
        sql_parts.append("    AND NSPTARGET.TAR_TYP_CD = 'NS'")
    # Display tab: Short pay fields JOINs
    if disp_short_pay:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_POL_TARGET SHORTPAY_PRM")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = SHORTPAY_PRM.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = SHORTPAY_PRM.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = SHORTPAY_PRM.TCH_POL_ID")
        sql_parts.append("    AND SHORTPAY_PRM.TAR_TYP_CD = 'VS'")
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.TH_USER_GENERIC USERDEF_52G")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = USERDEF_52G.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = USERDEF_52G.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = USERDEF_52G.TCH_POL_ID")

    # Display tab: GSP JOIN (CTE)
    if disp_gsp:
        sql_parts.append("  LEFT OUTER JOIN GSP")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = GSP.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = GSP.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = GSP.TCH_POL_ID")
    # Display tab: Billable Control Number JOIN
    if disp_bill_ctrl_num:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_BIL_FRM_CTL BILL_CONTROL")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = BILL_CONTROL.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = BILL_CONTROL.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = BILL_CONTROL.TCH_POL_ID")
    # Display tab: Original face for RPU JOIN (CTE)
    if disp_orig_face_rpu:
        sql_parts.append("  LEFT OUTER JOIN CHANGE_TYPE9")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = CHANGE_TYPE9.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = CHANGE_TYPE9.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = CHANGE_TYPE9.TCH_POL_ID")
    # Display tab: Prem Calc Rules JOIN
    if disp_prem_calc_rules:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_FXD_PRM_POL FIXPREM")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = FIXPREM.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = FIXPREM.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = FIXPREM.TCH_POL_ID")
    # Display tab: CIRF Key JOIN
    if disp_cirf_key:
        sql_parts.append(f"  LEFT OUTER JOIN {schema}.LH_COV_FXD_FND_CTL FFC")
        sql_parts.append("    ON POLICY1.CK_SYS_CD = FFC.CK_SYS_CD")
        sql_parts.append("    AND POLICY1.CK_CMP_CD = FFC.CK_CMP_CD")
        sql_parts.append("    AND POLICY1.TCH_POL_ID = FFC.TCH_POL_ID")

    # ── Benefits tab JOINs (up to 3 benefit rows) ───────────────
    bt = benefits_tab
    _cease_ops = {'1': '=', '2': '<', '3': '>'}
    for i in range(3):
        ben_type = bt.benefit_combos[i].currentText().strip()
        if not ben_type:
            continue
        ben_code = ben_type[0]  # first char, e.g. "1" from "1 - ADB"
        alias = f"BEN{i + 1}"
        sub_type = bt.subtype_edits[i].text().strip()
        post_issue = bt.post_issue_chks[i].isChecked()
        cease_lo = bt.cease_lo_edits[i].text().strip()
        cease_hi = bt.cease_hi_edits[i].text().strip()
        cease_status = bt.cease_status_combos[i].currentText().strip()

        sql_parts.append(f"  INNER JOIN {schema}.LH_SPM_BNF {alias}")
        sql_parts.append(f"    ON POLICY1.CK_SYS_CD = {alias}.CK_SYS_CD")
        sql_parts.append(f"    AND POLICY1.CK_CMP_CD = {alias}.CK_CMP_CD")
        sql_parts.append(f"    AND POLICY1.TCH_POL_ID = {alias}.TCH_POL_ID")
        sql_parts.append(f"    AND {alias}.SPM_BNF_TYP_CD = '{esc(ben_code)}'")
        if sub_type:
            sql_parts.append(f"    AND {alias}.SPM_BNF_SBY_CD = '{esc(sub_type)}'")
        if post_issue:
            sql_parts.append(f"    AND {alias}.BNF_ISS_DT > COVERAGE1.ISSUE_DT")
        if cease_lo:
            sql_parts.append(f"    AND {alias}.BNF_CEA_DT >= '{esc(cease_lo)}'")
        if cease_hi:
            sql_parts.append(f"    AND {alias}.BNF_CEA_DT <= '{esc(cease_hi)}'")
        if cease_status:
            cs_code = cease_status[0]  # "1", "2", or "3"
            op = _cease_ops.get(cs_code)
            if op:
                sql_parts.append(f"    AND {alias}.BNF_CEA_DT {op} {alias}.BNF_OGN_CEA_DT")

    # ── Coverages tab JOINs ─────────────────────────────────────

    # Base cov: MODCOV1 (TH_COV_PHA) for prod indicator / cola ind / gio_fio
    if cov_needs_modcov1:
        sql_parts.append(f"  INNER JOIN {schema}.TH_COV_PHA MODCOV1")
        sql_parts.append("    ON COVERAGE1.CK_SYS_CD = MODCOV1.CK_SYS_CD")
        sql_parts.append("    AND COVERAGE1.CK_CMP_CD = MODCOV1.CK_CMP_CD")
        sql_parts.append("    AND COVERAGE1.TCH_POL_ID = MODCOV1.TCH_POL_ID")
        sql_parts.append("    AND COVERAGE1.COV_PHA_NBR = MODCOV1.COV_PHA_NBR")

    # Base cov: COV1_RENEWALS (LH_COV_INS_RNL_RT) for rateclass67 / sex67
    if cov_needs_renewals or disp_sex_rateclass:
        _rnw_join = "INNER JOIN" if cov_needs_renewals else "LEFT OUTER JOIN"
        sql_parts.append(f"  {_rnw_join} {schema}.LH_COV_INS_RNL_RT COV1_RENEWALS")
        sql_parts.append("    ON COVERAGE1.CK_SYS_CD = COV1_RENEWALS.CK_SYS_CD")
        sql_parts.append("    AND COVERAGE1.CK_CMP_CD = COV1_RENEWALS.CK_CMP_CD")
        sql_parts.append("    AND COVERAGE1.TCH_POL_ID = COV1_RENEWALS.TCH_POL_ID")
        sql_parts.append("    AND COVERAGE1.COV_PHA_NBR = COV1_RENEWALS.COV_PHA_NBR")
        sql_parts.append("    AND COV1_RENEWALS.PRM_RT_TYP_CD = 'C'")

    # Base cov: TABLE_RATING1 (LH_SST_XTR_CRG) for Table (03)
    if cov_base_table03 or disp_substandard:
        _tr_join = "INNER JOIN" if cov_base_table03 else "LEFT OUTER JOIN"
        sql_parts.append(f"  {_tr_join} {schema}.LH_SST_XTR_CRG TABLE_RATING1")
        sql_parts.append("    ON COVERAGE1.CK_SYS_CD = TABLE_RATING1.CK_SYS_CD")
        sql_parts.append("    AND COVERAGE1.CK_CMP_CD = TABLE_RATING1.CK_CMP_CD")
        sql_parts.append("    AND COVERAGE1.TCH_POL_ID = TABLE_RATING1.TCH_POL_ID")
        sql_parts.append("    AND COVERAGE1.COV_PHA_NBR = TABLE_RATING1.COV_PHA_NBR")
        sql_parts.append("    AND (TABLE_RATING1.SST_XTR_TYP_CD = '0'"
                         " OR TABLE_RATING1.SST_XTR_TYP_CD = '1'"
                         " OR TABLE_RATING1.SST_XTR_TYP_CD = '3')")

    # Base cov: FLAT_EXTRA1 (LH_SST_XTR_CRG) for Flat (03)
    if cov_base_flat03 or disp_substandard:
        _fe_join = "INNER JOIN" if cov_base_flat03 else "LEFT OUTER JOIN"
        sql_parts.append(f"  {_fe_join} {schema}.LH_SST_XTR_CRG FLAT_EXTRA1")
        sql_parts.append("    ON COVERAGE1.CK_SYS_CD = FLAT_EXTRA1.CK_SYS_CD")
        sql_parts.append("    AND COVERAGE1.CK_CMP_CD = FLAT_EXTRA1.CK_CMP_CD")
        sql_parts.append("    AND COVERAGE1.TCH_POL_ID = FLAT_EXTRA1.TCH_POL_ID")
        sql_parts.append("    AND COVERAGE1.COV_PHA_NBR = FLAT_EXTRA1.COV_PHA_NBR")
        sql_parts.append("    AND (FLAT_EXTRA1.SST_XTR_TYP_CD = '2'"
                         " OR FLAT_EXTRA1.SST_XTR_TYP_CD = '4')")

    # Rider JOINs — helper to emit a rider block
    def _emit_rider_joins(info: dict, alias: str, idx: int):
        if not info["active"]:
            return
        # Main rider join to LH_COV_PHA
        sql_parts.append(f"  INNER JOIN {schema}.LH_COV_PHA {alias}")
        sql_parts.append(f"    ON POLICY1.CK_SYS_CD = {alias}.CK_SYS_CD")
        sql_parts.append(f"    AND POLICY1.CK_CMP_CD = {alias}.CK_CMP_CD")
        sql_parts.append(f"    AND POLICY1.TCH_POL_ID = {alias}.TCH_POL_ID")
        sql_parts.append(f"    AND {alias}.COV_PHA_NBR > 1")
        # Inline WHERE conditions on the rider join
        pc = info["plancode"]
        if pc:
            sql_parts.append(f"    AND {alias}.PLN_DES_SER_CD = '{esc(pc)}'")
        pl = info["prod_line"]
        if pl:
            code = pl[0]  # first char
            sql_parts.append(f"    AND {alias}.PRD_LIN_TYP_CD = '{esc(code)}'")
        sex02 = info["sex_code_02"]
        if sex02:
            code = sex02[0]
            sql_parts.append(f"    AND {alias}.INS_SEX_CD = '{esc(code)}'")
        person = info["person"]
        if person:
            code = person[:2]  # 2-char code
            sql_parts.append(f"    AND {alias}.PRS_CD = '{esc(code)}'")
        if info["post_issue"]:
            sql_parts.append(f"    AND {alias}.ISSUE_DT > COVERAGE1.ISSUE_DT")
        issue_lo = info["issue_date_lo"]
        if issue_lo:
            sql_parts.append(f"    AND {alias}.ISSUE_DT >= '{esc(issue_lo)}'")
        issue_hi = info["issue_date_hi"]
        if issue_hi:
            sql_parts.append(f"    AND {alias}.ISSUE_DT <= '{esc(issue_hi)}'")
        ct_val = info["change_type"]
        if ct_val:
            code = ct_val[0]
            sql_parts.append(f"    AND {alias}.NXT_CHG_TYP_CD = '{esc(code)}'")
        change_lo = info["change_date_lo"]
        if change_lo:
            sql_parts.append(f"    AND {alias}.NXT_CHG_DT >= '{esc(change_lo)}'")
        change_hi = info["change_date_hi"]
        if change_hi:
            sql_parts.append(f"    AND {alias}.NXT_CHG_DT <= '{esc(change_hi)}'")
        lives = info["lives_cov"]
        if lives:
            code = lives[0]
            sql_parts.append(f"    AND {alias}.LIVES_COV_CD = '{esc(code)}'")
        addl = info["addl_plancode"]
        if addl:
            c = addl[0]
            if c == "1":
                sql_parts.append(f"    AND {alias}.PLN_DES_SER_CD = COVERAGE1.PLN_DES_SER_CD")
            elif c == "2":
                sql_parts.append(f"    AND {alias}.PLN_DES_SER_CD <> COVERAGE1.PLN_DES_SER_CD")

        # Rider COVMOD join (TH_COV_PHA) for prod_ind / cola / gio_fio
        covmod_alias = f"{alias}COVMOD"
        if info["needs_covmod"]:
            sql_parts.append(f"  INNER JOIN {schema}.TH_COV_PHA {covmod_alias}")
            sql_parts.append(f"    ON {alias}.CK_SYS_CD = {covmod_alias}.CK_SYS_CD")
            sql_parts.append(f"    AND {alias}.CK_CMP_CD = {covmod_alias}.CK_CMP_CD")
            sql_parts.append(f"    AND {alias}.TCH_POL_ID = {covmod_alias}.TCH_POL_ID")
            sql_parts.append(f"    AND {alias}.COV_PHA_NBR = {covmod_alias}.COV_PHA_NBR")
            pi = info["prod_ind"]
            if pi:
                code = pi[0]
                sql_parts.append(f"    AND {covmod_alias}.AN_PRD_ID = '{esc(code)}'")
            cola = info["cola_ind"]
            if cola:
                sql_parts.append(f"    AND {covmod_alias}.COLA_INCR_IND = '{esc(cola)}'")
            gio = info["gio_fio"]
            if gio:
                if gio.lower() == "blank":
                    sql_parts.append(f"    AND {covmod_alias}.OPT_EXER_IND = ''")
                else:
                    sql_parts.append(f"    AND {covmod_alias}.OPT_EXER_IND = '{esc(gio)}'")

        # Rider RENEWALS join (LH_COV_INS_RNL_RT) for rateclass67 / sex67
        rnl_alias = f"{alias}_RENEWALS"
        if info["needs_renewals"]:
            sql_parts.append(f"  INNER JOIN {schema}.LH_COV_INS_RNL_RT {rnl_alias}")
            sql_parts.append(f"    ON {alias}.CK_SYS_CD = {rnl_alias}.CK_SYS_CD")
            sql_parts.append(f"    AND {alias}.CK_CMP_CD = {rnl_alias}.CK_CMP_CD")
            sql_parts.append(f"    AND {alias}.TCH_POL_ID = {rnl_alias}.TCH_POL_ID")
            sql_parts.append(f"    AND {alias}.COV_PHA_NBR = {rnl_alias}.COV_PHA_NBR")
            sql_parts.append(f"    AND {rnl_alias}.PRM_RT_TYP_CD = 'C'")
            rc = info["rateclass"]
            if rc:
                code = rc[0]
                sql_parts.append(f"    AND {rnl_alias}.RT_CLS_CD = '{esc(code)}'")
            sx67 = info["sex_code_67"]
            if sx67:
                code = sx67[0]
                sql_parts.append(f"    AND {rnl_alias}.RT_SEX_CD = '{esc(code)}'")

        # Rider TABLE_RATING / FLAT_EXTRA
        if info["table_03"]:
            tr_alias = f"{alias}_TABLE_RATING"
            sql_parts.append(f"  INNER JOIN {schema}.LH_SST_XTR_CRG {tr_alias}")
            sql_parts.append(f"    ON {alias}.CK_SYS_CD = {tr_alias}.CK_SYS_CD")
            sql_parts.append(f"    AND {alias}.CK_CMP_CD = {tr_alias}.CK_CMP_CD")
            sql_parts.append(f"    AND {alias}.TCH_POL_ID = {tr_alias}.TCH_POL_ID")
            sql_parts.append(f"    AND {alias}.COV_PHA_NBR = {tr_alias}.COV_PHA_NBR")
            sql_parts.append(f"    AND ({tr_alias}.SST_XTR_TYP_CD = '0'"
                             f" OR {tr_alias}.SST_XTR_TYP_CD = '1'"
                             f" OR {tr_alias}.SST_XTR_TYP_CD = '3')")
        if info["flat_03"]:
            fe_alias = f"{alias}_FLAT_EXTRA"
            sql_parts.append(f"  INNER JOIN {schema}.LH_SST_XTR_CRG {fe_alias}")
            sql_parts.append(f"    ON {alias}.CK_SYS_CD = {fe_alias}.CK_SYS_CD")
            sql_parts.append(f"    AND {alias}.CK_CMP_CD = {fe_alias}.CK_CMP_CD")
            sql_parts.append(f"    AND {alias}.TCH_POL_ID = {fe_alias}.TCH_POL_ID")
            sql_parts.append(f"    AND {alias}.COV_PHA_NBR = {fe_alias}.COV_PHA_NBR")
            sql_parts.append(f"    AND ({fe_alias}.SST_XTR_TYP_CD = '2'"
                             f" OR {fe_alias}.SST_XTR_TYP_CD = '4')")

    _emit_rider_joins(rider1_info, "RIDER1", 1)
    _emit_rider_joins(rider2_info, "RIDER2", 2)

    # ── Transaction tab JOIN (FH_FIXED — 69 segment) ────────────
    if transaction_tab is not None:
        tt = transaction_tab
        trans_code = tt.cmb_transaction.currentText().strip()
        tr_entry_lo = tt.txt_entry_lo.text().strip()
        tr_entry_hi = tt.txt_entry_hi.text().strip()
        tr_eff_lo = tt.txt_eff_lo.text().strip()
        tr_eff_hi = tt.txt_eff_hi.text().strip()
        tr_eff_month_lo = tt.txt_eff_month_lo.text().strip()
        tr_eff_month_hi = tt.txt_eff_month_hi.text().strip()
        tr_eff_day_lo = tt.txt_eff_day_lo.text().strip()
        tr_eff_day_hi = tt.txt_eff_day_hi.text().strip()
        tr_gross_lo = tt.txt_gross_lo.text().strip()
        tr_gross_hi = tt.txt_gross_hi.text().strip()
        tr_origin = tt.txt_origin.text().strip()
        tr_fund_id = tt.txt_fund_id.text().strip()
        tr_eff_day_chk = tt.chk_eff_day.isChecked()
        tr_eff_month_chk = tt.chk_eff_month.isChecked()

        has_transaction = bool(
            trans_code or tr_entry_lo or tr_entry_hi
            or tr_eff_lo or tr_eff_hi or tr_origin
            or tr_eff_month_lo or tr_eff_month_hi
            or tr_eff_day_lo or tr_eff_day_hi
            or tr_gross_lo or tr_gross_hi
            or tr_fund_id or tr_eff_day_chk or tr_eff_month_chk
        )
        if has_transaction:
            sql_parts.append(f"  INNER JOIN {schema}.FH_FIXED TR1")
            sql_parts.append("    ON POLICY1.CK_CMP_CD = TR1.CK_CMP_CD")
            sql_parts.append("    AND POLICY1.TCH_POL_ID = TR1.TCH_POL_ID")
            # Transaction type — first 2 chars of combo text (e.g. "A_" from "A_ - ...")
            if trans_code:
                code = trans_code.split(" - ", 1)[0].strip()
                sql_parts.append(f"    AND TR1.TRANS = '{esc(code)}'")
            # Entry date range
            if tr_entry_lo:
                sql_parts.append(f"    AND TR1.ENTRY_DT >= '{esc(tr_entry_lo)}'")
            if tr_entry_hi:
                sql_parts.append(f"    AND TR1.ENTRY_DT <= '{esc(tr_entry_hi)}'")
            # Effective date range
            if tr_eff_lo:
                sql_parts.append(f"    AND TR1.ASOF_DT >= '{esc(tr_eff_lo)}'")
            if tr_eff_hi:
                sql_parts.append(f"    AND TR1.ASOF_DT <= '{esc(tr_eff_hi)}'")
            # Effective day = Issue day
            if tr_eff_day_chk:
                sql_parts.append("    AND DAY(TR1.ASOF_DT) = DAY(COVERAGE1.ISSUE_DT)")
            # Effective month = Issue month
            if tr_eff_month_chk:
                sql_parts.append("    AND MONTH(TR1.ASOF_DT) = MONTH(COVERAGE1.ISSUE_DT)")
            # Eff month range
            if tr_eff_month_lo:
                sql_parts.append(f"    AND MONTH(TR1.ASOF_DT) >= {int(tr_eff_month_lo)}")
            if tr_eff_month_hi:
                sql_parts.append(f"    AND MONTH(TR1.ASOF_DT) <= {int(tr_eff_month_hi)}")
            # Eff day range
            if tr_eff_day_lo:
                sql_parts.append(f"    AND DAY(TR1.ASOF_DT) >= {int(tr_eff_day_lo)}")
            if tr_eff_day_hi:
                sql_parts.append(f"    AND DAY(TR1.ASOF_DT) <= {int(tr_eff_day_hi)}")
            # Gross amount range
            if tr_gross_lo:
                sql_parts.append(f"    AND TR1.GROSS_AMT >= {float(tr_gross_lo)}")
            if tr_gross_hi:
                sql_parts.append(f"    AND TR1.GROSS_AMT <= {float(tr_gross_hi)}")
            # ORIGIN_OF_TRANS
            if tr_origin:
                sql_parts.append(f"    AND TR1.ORIGIN_OF_TRANS = '{esc(tr_origin)}'")
            # Fund ID list — comma-separated values → IN clause
            if tr_fund_id:
                fund_ids = [f.strip() for f in tr_fund_id.split(",") if f.strip()]
                if fund_ids:
                    sql_parts.append(f"    AND TR1.FUND_ID IN ({in_list(fund_ids)})")

    # ── WHERE ────────────────────────────────────────────────────
    wheres = []

    # -- Bottom bar: System code --
    if sys_code:
        wheres.append(f"POLICY1.CK_SYS_CD = '{esc(sys_code)}'")

    # -- Policy tab: Plancode (searches all coverages) --
    plancode = pt.txt_plancode.text().strip()
    if plancode:
        wheres.append(f"COVSALL.PLN_DES_SER_CD = '{esc(plancode)}'")

    # -- Plancode tab: multiple plancodes (IN list) --
    plancode_list = plancode_tab.get_plancodes()
    if plancode_list:
        wheres.append(
            f"COVSALL.PLN_DES_SER_CD IN ({in_list(plancode_list)})")

    # -- Policy tab: Market Org --
    _mkt_org_map = {"MLM": "1", "CSSD": "2", "IMG": "7", "DIRECT": "D"}
    _mkt_company_map = {
        "CSSD": ["01"], "IMG": ["01", "26"], "MLM": ["01", "26"],
        "DIRECT": ["01", "26"],
    }
    market_org = pt.cmb_market.currentText().strip()
    if market_org and market_org in _mkt_org_map:
        wheres.append(f"SUBSTR(POLICY1.SVC_AGC_NBR,1,1) = '{_mkt_org_map[market_org]}'")

    # -- Policy tab: Company --
    company = pt.cmb_company.currentText().strip()
    if company:
        co_code = company.split(" - ")[0].strip() if " - " in company else company
        wheres.append(f"POLICY1.CK_CMP_CD = '{esc(co_code)}'")
    elif market_org and market_org in _mkt_company_map:
        co_codes = _mkt_company_map[market_org]
        if len(co_codes) == 1:
            wheres.append(f"POLICY1.CK_CMP_CD = '{co_codes[0]}'")
        else:
            conds = " OR ".join(f"POLICY1.CK_CMP_CD = '{c}'" for c in co_codes)
            wheres.append(f"({conds})")

    # -- Policy tab: Form number (starts-with LIKE) --
    form_num = pt.txt_form_number.text().strip()
    if form_num:
        wheres.append(f"COVERAGE1.POL_FRM_NBR LIKE '{esc(form_num)}%'")

    # -- Policy tab: Branch --
    branch = pt.txt_branch.text().strip()
    if branch:
        wheres.append(f"SUBSTR(POLICY1.SVC_AGC_NBR, 2, 3) = '{esc(branch)}'")

    # -- Policy tab: Policy number criteria --
    polnum = pt.txt_polnum_value.text().strip()
    if polnum:
        criteria = pt.cmb_polnum_criteria.currentText()
        if criteria == "Starts with":
            wheres.append(f"POLICY1.CK_POLICY_NBR LIKE '{esc(polnum)}%'")
        elif criteria == "Ends with":
            wheres.append(f"POLICY1.CK_POLICY_NBR LIKE '%{esc(polnum)}'")
        else:  # Contains
            wheres.append(f"POLICY1.CK_POLICY_NBR LIKE '%{esc(polnum)}%'")

    # -- Policy tab: RGA (52) --
    if pt.chk_rga.isChecked():
        wheres.append("USERGEN.FUZGREIN_IND = 'R'")

    # -- Policy tab: Status codes (checkbox + listbox) --
    if pt.chk_status_code.isChecked():
        codes = selected_codes(pt.list_status)
        if codes:
            wheres.append(f"POLICY1.PRM_PAY_STA_REA_CD IN ({in_list(codes)})")

    # -- Policy tab: Product line code (checkbox + listbox → all covs) --
    if pt.chk_product_line.isChecked():
        codes = selected_codes(pt.list_product_line)
        if codes:
            wheres.append(f"COVSALL.PRD_LIN_TYP_CD IN ({in_list(codes)})")

    # -- Policy tab: Product indicator (checkbox + listbox → any cov) --
    if pt.chk_product_indicator.isChecked():
        codes = selected_codes(pt.list_product_indicator)
        if codes:
            wheres.append(f"COVSALL.ADV_PRD_IND IN ({in_list(codes)})")

    # -- Policy tab: State (checkbox + listbox) --
    if pt.chk_state.isChecked():
        abbrevs = [item.text() for item in pt.list_state.selectedItems()]
        if abbrevs:
            st_codes = [_STATE_ABBR_TO_CODE.get(a) for a in abbrevs]
            st_codes = [c for c in st_codes if c]
            if st_codes:
                wheres.append(f"POLICY1.POL_ISS_ST_CD IN ({in_list(st_codes)})")

    # -- Policy tab: Last entry code (checkbox + listbox) --
    if pt.chk_last_entry.isChecked():
        codes = selected_codes(pt.list_last_entry)
        if codes:
            wheres.append(f"POLICY1.LST_ETR_CD IN ({in_list(codes)})")

    # -- Policy tab: Suspense code (checkbox + listbox) --
    if pt.chk_suspense.isChecked():
        codes = selected_codes(pt.list_suspense)
        if codes:
            wheres.append(f"POLICY1.SUS_CD IN ({in_list(codes)})")

    # -- Policy tab: Billing form (checkbox + listbox) --
    if pt.chk_billing_form.isChecked():
        codes = selected_codes(pt.list_billing_form)
        if codes:
            wheres.append(f"POLICY1.BIL_FRM_CD IN ({in_list(codes)})")

    # -- Policy tab: Bill mode (checkbox + listbox, complex mapping) --
    if pt.chk_bill_mode.isChecked():
        modes = [item.text() for item in pt.list_bill_mode.selectedItems()]
        if modes:
            mode_clause = _build_bill_mode_where(modes)
            if mode_clause:
                wheres.append(f"({mode_clause})")

    # -- Policy tab: Issue age range --
    add_int_range(wheres, "COVERAGE1.INS_ISS_AGE",
                  pt.txt_issue_age_lo, pt.txt_issue_age_hi)

    # -- Policy tab: Current age range (VBA: INS_ISS_AGE + Duration) --
    duration_expr = ("TRUNCATE(MONTHS_BETWEEN('"
                     + today_str()
                     + "', COVERAGE1.ISSUE_DT) / 12, 0)")
    add_int_range(
        wheres,
        f"(COVERAGE1.INS_ISS_AGE + {duration_expr})",
        pt.txt_current_age_lo, pt.txt_current_age_hi)

    # -- Policy tab: Current policy year (Duration + 1) --
    add_int_range(
        wheres,
        f"({duration_expr} + 1)",
        pt.txt_pol_year_lo, pt.txt_pol_year_hi)

    # -- Policy tab: Issue month range --
    add_int_range(wheres, "MONTH(COVERAGE1.ISSUE_DT)",
                  pt.txt_issue_month_lo, pt.txt_issue_month_hi)

    # -- Policy tab: Issue day range --
    add_int_range(wheres, "DAY(COVERAGE1.ISSUE_DT)",
                  pt.txt_issue_day_lo, pt.txt_issue_day_hi)

    # -- Policy tab: Issued date range --
    add_date_range(wheres, "COVERAGE1.ISSUE_DT",
                   pt.txt_issued_date_lo, pt.txt_issued_date_hi)

    # -- Policy tab: Paid to date range --
    add_date_range(wheres, "POLICY1.PRM_PAID_TO_DT",
                   pt.txt_paid_to_lo, pt.txt_paid_to_hi)

    # -- Policy tab: Application date range --
    add_date_range(wheres, "POLICY1.APP_WRT_DT",
                   pt.txt_app_date_lo, pt.txt_app_date_hi)

    # -- Policy tab: Billing premium amount range --
    add_decimal_range(wheres, "POLICY1.POL_PRM_AMT",
                      pt.txt_billing_prem_lo, pt.txt_billing_prem_hi)

    # -- Policy tab: GPE date range --
    if has_gpe_date:
        add_date_range(wheres, "GRACE_TABLE.GRA_PER_EXP_DT",
                       pt.txt_gpe_date_lo, pt.txt_gpe_date_hi)
    # -- Policy tab: Grace Indicator (51 or 66) --
    if grace_indicator:
        codes = selected_codes(pt.list_grace_indicator)
        if codes:
            conds = " OR ".join(
                f"SUBSTR(GRACE_TABLE.IN_GRA_PER_IND,1,1) = '{esc(c)}'" for c in codes)
            wheres.append(f"({conds})")

    # ── Policy (2) tab WHERE conditions ──────────────────────────
    # -- TAMRA 7-Pay Premium (59) --
    add_decimal_range(wheres, "TAMRA.SVPY_LVL_PRM_AMT",
                      p2t.txt_tamra_7pay_prem_lo, p2t.txt_tamra_7pay_prem_hi)
    # -- TAMRA 7-Pay Starting AV (59) --
    add_decimal_range(wheres, "TAMRA.SVPY_BEG_CSV_AMT",
                      p2t.txt_tamra_7pay_av_lo, p2t.txt_tamra_7pay_av_hi)
    # -- 1035 Amt (59) --
    if p2t.chk_1035_amt.isChecked():
        wheres.append("TAMRA.XCG_1035_PMT_QTY > 0")
    # -- MEC (59) --
    if p2t.chk_mec.isChecked():
        wheres.append("TAMRA.MEC_STA_CD = '1'")
    # -- Total Additional Prem (60) --
    add_decimal_range(wheres, "POLICY_TOTALS.TOT_ADD_PRM_AMT",
                      p2t.txt_total_addl_prem_lo, p2t.txt_total_addl_prem_hi)
    # -- Total Prem Additional + Reg (60) --
    add_decimal_range(wheres,
                      "(POLICY_TOTALS.TOT_ADD_PRM_AMT + POLICY_TOTALS.TOT_REG_PRM_AMT)",
                      p2t.txt_total_prem_addl_reg_lo, p2t.txt_total_prem_addl_reg_hi)
    # -- Accum WD (60) --
    add_decimal_range(wheres, "POLICY_TOTALS.TOT_WTD_AMT",
                      p2t.txt_accum_wd_lo, p2t.txt_accum_wd_hi)
    # -- Premium Year To Date (63) --
    add_decimal_range(wheres, "LH_POL_YR_TOT_at_MaxDuration.YTD_TOT_PMT_AMT",
                      p2t.txt_prem_ytd_lo, p2t.txt_prem_ytd_hi)
    # -- BIL_COMMENCE_DT (66) --
    add_date_range(wheres, "NONTRAD.BIL_COMMENCE_DT",
                   p2t.txt_bil_commence_dt_lo, p2t.txt_bil_commence_dt_hi)
    # -- Billing suspended (66) --
    if p2t.chk_billing_suspended.isChecked():
        wheres.append("NONTRAD.BIL_STA_CD = '1'")
    # -- Failed Guideline or TAMRA (66) --
    if p2t.chk_failed_guideline.isChecked():
        wheres.append("NONTRAD.PR_LIMIT_EXC_ONL = '1'")
    # -- Last Financial Date (01) --
    add_date_range(wheres, "POLICY1.LST_FIN_DT",
                   p2t.txt_last_fin_date_lo, p2t.txt_last_fin_date_hi)
    # -- Has converted policy (52) --
    if p2t.chk_has_converted.isChecked():
        wheres.append("USERGEN.EXCH_POL_NUMBER IS NOT NULL")
    # -- Has a replacement pol (52-R) --
    if p2t.chk_has_replacement_pol.isChecked():
        wheres.append("USERDEF_52R.REPLACED_POLICY IS NOT NULL")
    # -- Cov has GIO ind (02) --
    if p2t.chk_cov_gio.isChecked():
        wheres.append("MODCOVSALL.OPT_EXER_IND = 'Y'")
    # -- Cov has COLA ind (02) --
    if p2t.chk_cov_cola.isChecked():
        wheres.append("MODCOVSALL.COLA_INCR_IND = '1'")
    # -- Loan Type (01) --
    if p2t.chk_loan_type.isChecked():
        codes = selected_codes(p2t.list_loan_type)
        if codes:
            wheres.append(f"POLICY1.LN_TYP_CD IN ({in_list(codes)})")
    # -- Loan charge Rate (01) --
    loan_rate = p2t.txt_loan_charge_rate.text().strip()
    if loan_rate:
        try:
            wheres.append(f"POLICY1.LN_PLN_ITS_RT = {float(loan_rate)}")
        except ValueError:
            pass
    # -- Loan Principle / Accrued Interest (77) --
    add_decimal_range(wheres, "POLICYDEBT.LOAN_PRINCIPLE",
                      p2t.txt_total_loan_prin_lo, p2t.txt_total_loan_prin_hi)
    add_decimal_range(wheres, "POLICYDEBT.LOAN_ACCRUED",
                      p2t.txt_total_accured_lint_lo, p2t.txt_total_accured_lint_hi)
    # -- Trad Overloan Ind (01) --
    if p2t.chk_trad_overloan.isChecked():
        codes = selected_codes(p2t.list_trad_overloan)
        if codes:
            wheres.append(f"POLICY1_MOD.OVERLOAN_IND IN ({in_list(codes)})")
    # -- Non Trad Indicator (02) --
    if p2t.chk_non_trad.isChecked():
        codes = selected_codes(p2t.list_non_trad)
        if codes:
            wheres.append(f"POLICY1.NON_TRD_POL_IND IN ({in_list(codes)})")
    # -- Scheduled Loan Payment (20) --
    if p2t.chk_std_loan_payment.isChecked():
        codes = selected_codes(p2t.list_std_loan_payment)
        if codes:
            wheres.append(f"SLR_BILL_CONTROL.BIL_FRM_CD IN ({in_list(codes)})")
    # -- Definition of Life Insurance (66) --
    if p2t.chk_def_life.isChecked():
        codes = selected_codes(p2t.list_def_life)
        if codes:
            wheres.append(f"NONTRAD.TFDF_CD IN ({in_list(codes)})")
    # -- Reinsurance Code --
    if p2t.chk_reinsurance.isChecked():
        codes = selected_codes(p2t.list_reinsurance)
        if codes:
            wheres.append(f"POLICY1.REINSURED_CD IN ({in_list(codes)})")
    # -- Has Change Seq (68) --
    if has_change_seq:
        codes = selected_codes(p2t.list_change_seq)
        if codes:
            wheres.append(f"CHANGE_SEGMENT.CHG_TYP_CD IN ({in_list(codes)})")

    # ── ADV tab WHERE conditions ─────────────────────────────────
    # -- CV × CORR% > Specified Amount + OPTDB --
    if adv_cv_corr:
        wheres.append("(MVVAL.DB > COVSUMMARY.TOTAL_SA + MVVAL.OPTDB)")
    # -- Accumulation Value > Premiums Paid --
    if adv_accum_gt_prem:
        wheres.append("(MVVAL.CSV_AMT >= MVVAL.TOTALPREM)")
    # -- GLP is negative --
    if adv_glp_neg:
        wheres.append("(GLP.GLP_VALUE < 0)")
    # -- Current SA < Original SA --
    if adv_sa_lt_orig:
        wheres.append("(COVSUMMARY.TOTAL_SA <= COVSUMMARY.TOTAL_ORIGINAL_SA)")
    # -- Current SA > Original SA --
    if adv_sa_gt_orig:
        wheres.append("(COVSUMMARY.TOTAL_SA >= COVSUMMARY.TOTAL_ORIGINAL_SA)")
    # -- GCV > Current CV (ISWL) --
    if adv_gcv_gt_cv:
        wheres.append("(ISWL_INTERPOLATED_GCV.ISWL_GCV >= MVVAL.CSV_AMT)")
    # -- GCV < Current CV (ISWL) --
    if adv_gcv_lt_cv:
        wheres.append("(ISWL_INTERPOLATED_GCV.ISWL_GCV <= MVVAL.CSV_AMT)")
    # -- Grace Period Rule Code (66) --
    if adv_grace_rule:
        codes = selected_codes(at.list_grace_rule)
        if codes:
            wheres.append(f"NONTRAD.GRA_THD_RLE_CD IN ({in_list(codes)})")
    # -- Death Benefit Option (66) --
    if adv_db_option:
        codes = selected_codes(at.list_db_option)
        if codes:
            wheres.append(f"NONTRAD.DTH_BNF_PLN_OPT_CD IN ({in_list(codes)})")
    # -- Orig Entry Code (01) --
    if adv_orig_entry:
        codes = selected_codes(at.list_orig_entry)
        if codes:
            wheres.append(f"POLICY1.OGN_ETR_CD IN ({in_list(codes)})")
    # -- Current Fund Value range (65) --
    if adv_fund_lo:
        try:
            wheres.append(f"FUND_VALUES.FUNDAMT >= {float(adv_fund_lo)}")
        except ValueError:
            pass
    if adv_fund_hi:
        try:
            wheres.append(f"FUND_VALUES.FUNDAMT <= {float(adv_fund_hi)}")
        except ValueError:
            pass
    # -- Accumulation Value range (75) --
    add_decimal_range(wheres, "MVVAL.CSV_AMT",
                      at.rng_accum_val[0], at.rng_accum_val[1])
    # -- Shadow Account Value (58) --
    add_decimal_range(wheres, "SHADOWAV.TAR_PRM_AMT",
                      at.rng_shadow_acct[0], at.rng_shadow_acct[1])
    # -- Current Specified Amount (02) --
    add_decimal_range(wheres, "COVSUMMARY.TOTAL_SA",
                      at.rng_curr_spec_amt[0], at.rng_curr_spec_amt[1])
    # -- Accum MTP (58) --
    add_decimal_range(wheres, "ACCUMMTP.TAR_PRM_AMT",
                      at.rng_accum_mtp[0], at.rng_accum_mtp[1])
    # -- Accum GLP (58) --
    add_decimal_range(wheres, "ACCUMGLP.TAR_PRM_AMT",
                      at.rng_accum_glp[0], at.rng_accum_glp[1])
    # -- Type P Sequence (57) --
    add_int_range(wheres, "ALLOCATION_P_COUNT.FND_ALC_SEQ_NBR",
                  at.rng_type_p[0], at.rng_type_p[1])
    # -- Type V Sequence (57) --
    add_int_range(wheres, "ALLOCATION_V_COUNT.FND_ALC_SEQ_NBR",
                  at.rng_type_v[0], at.rng_type_v[1])

    # ── Policy tab: bottom checkboxes WHERE conditions ───────────
    # -- Multiple Base Covs (02) --
    if multi_base_covs:
        wheres.append("(COVSUMMARY.BASECOVCOUNT > 1)")
    # -- Is MDO (59) --
    if is_mdo:
        wheres.append("SUBSTR(POLICY1.USR_RES_CD,1,1) = 'Y'")
    # -- In conversion period (Calc) --
    if in_conversion:
        _today = today_str()
        _dur = f"TRUNCATE(MONTHS_BETWEEN('{_today}', COVERAGE1.ISSUE_DT) / 12, 0)"
        _att_age = f"(COVERAGE1.INS_ISS_AGE + {_dur})"
        wheres.append(
            f"(CASE"
            f" WHEN (UPDF.CONVERSION_PERIOD = 0 AND {_att_age} < UPDF.CONVERSION_AGE)"
            f" OR (UPDF.CONVERSION_PERIOD > 0 AND {_dur} < UPDF.CONVERSION_PERIOD"
            f" AND {_att_age} < UPDF.CONVERSION_AGE)"
            f" THEN 'TRUE' ELSE 'FALSE' END) = 'TRUE'")

    # ── Coverages tab WHERE conditions ───────────────────────────
    # Col 1 — Valuation fields (COVERAGE1 == table 02)
    if cov_val_class:
        wheres.append(f"COVERAGE1.INS_CLS_CD = '{esc(cov_val_class)}'")
    if cov_val_base:
        wheres.append(f"COVERAGE1.PLN_BSE_SRE_CD = '{esc(cov_val_base)}'")
    if cov_val_sub:
        wheres.append(f"COVERAGE1.LIF_PLN_SUB_SRE_CD = '{esc(cov_val_sub)}'")
    if cov_val_mort:
        wheres.append(f"COVERAGE1.MTL_FCT_TBL_CD = '{esc(cov_val_mort)}'")
    if cov_rpu_mort:
        wheres.append(f"COVERAGE1.NSP_RPU_TBL_CD = '{esc(cov_rpu_mort)}'")
    if cov_eti_mort:
        wheres.append(f"COVERAGE1.NSP_EI_TBL_CD = '{esc(cov_eti_mort)}'")
    if cov_nfo_rate:
        try:
            wheres.append(f"COVERAGE1.NSP_ITS_RT = {float(cov_nfo_rate)}")
        except ValueError:
            pass
    # Val Class ≠ Plan Code
    if cov_val_class_ne:
        wheres.append("COVERAGE1.INS_CLS_CD <> SUBSTR(COVERAGE1.PLN_DES_SER_CD,3,1)")
    # CV Rate > 0
    if cov_cv_rate:
        wheres.append(
            "(COVERAGE1.LOW_DUR_1_CSV_AMT > 0 OR COVERAGE1.LOW_DUR_2_CSV_AMT > 0)")
    # GCV > Current CV (ISWL)
    if cov_gcv_gt_cv:
        wheres.append("(ISWL_INTERPOLATED_GCV.ISWL_GCV >= MVVAL.CSV_AMT)")
    # GCV < Current CV (ISWL)
    if cov_gcv_lt_cv:
        wheres.append("(ISWL_INTERPOLATED_GCV.ISWL_GCV <= MVVAL.CSV_AMT)")
    # GIO on any coverage (uses MODCOVSALL)
    if cov_gio:
        wheres.append("MODCOVSALL.OPT_EXER_IND = 'Y'")
    # COLA on any coverage (uses MODCOVSALL)
    if cov_cola:
        wheres.append("MODCOVSALL.COLA_INCR_IND = '1'")
    # Non-trad indicator
    if cov_non_trad:
        codes = selected_codes(covt.list_non_trad)
        if codes:
            wheres.append(f"POLICY1.NON_TRD_POL_IND IN ({in_list(codes)})")
    # Current Specified Amount range
    add_decimal_range(wheres, "COVSUMMARY.TOTAL_SA",
                      covt.txt_spec_amt_lo, covt.txt_spec_amt_hi)
    # Initial Term Period
    if cov_init_term:
        codes = selected_codes(covt.list_init_term)
        if codes:
            wheres.append(f"COVERAGE1.INT_RNL_PER IN ({in_list(codes)})")

    # -- Base coverage column (Col 4) --
    if cov_base_plancode:
        wheres.append(f"COVERAGE1.PLN_DES_SER_CD = '{esc(cov_base_plancode)}'")
    if cov_base_prod_line:
        code = cov_base_prod_line[0]
        wheres.append(f"COVERAGE1.PRD_LIN_TYP_CD = '{esc(code)}'")
    if cov_base_form_number:
        wheres.append(f"COVERAGE1.POL_FRM_NBR LIKE '{esc(cov_base_form_number)}%'")
    if cov_base_sex02:
        code = cov_base_sex02[0]
        wheres.append(f"COVERAGE1.INS_SEX_CD = '{esc(code)}'")
    if cov_base_person:
        code = cov_base_person[:2]
        wheres.append(f"COVERAGE1.PRS_CD = '{esc(code)}'")
    if cov_base_lives_cov:
        code = cov_base_lives_cov[0]
        wheres.append(f"COVERAGE1.LIVES_COV_CD = '{esc(code)}'")
    if cov_base_change_type:
        code = cov_base_change_type[0]
        wheres.append(f"COVERAGE1.NXT_CHG_TYP_CD = '{esc(code)}'")
    add_date_range(wheres, "COVERAGE1.ISSUE_DT",
                   _bw["issue_date_lo"], _bw["issue_date_hi"])
    add_date_range(wheres, "COVERAGE1.NXT_CHG_DT",
                   _bw["change_date_lo"], _bw["change_date_hi"])
    # Base coverage MODCOV1 fields (prod_ind, cola_ind, gio_fio)
    if cov_base_prod_ind:
        code = cov_base_prod_ind[0]
        wheres.append(f"MODCOV1.AN_PRD_ID = '{esc(code)}'")
    if cov_base_cola_ind:
        wheres.append(f"MODCOV1.COLA_INCR_IND = '{esc(cov_base_cola_ind)}'")
    if cov_base_gio_fio:
        if cov_base_gio_fio.lower() == "blank":
            wheres.append("MODCOV1.OPT_EXER_IND = ''")
        else:
            wheres.append(f"MODCOV1.OPT_EXER_IND = '{esc(cov_base_gio_fio)}'")
    # Base coverage RENEWALS fields (rateclass, sex67)
    if cov_base_rateclass:
        code = cov_base_rateclass[0]
        wheres.append(f"COV1_RENEWALS.RT_CLS_CD = '{esc(code)}'")
    if cov_base_sex67:
        code = cov_base_sex67[0]
        wheres.append(f"COV1_RENEWALS.RT_SEX_CD = '{esc(code)}'")

    # ── Assemble WHERE ───────────────────────────────────────────
    if wheres:
        sql_parts.append("WHERE " + wheres[0])
        for w in wheres[1:]:
            sql_parts.append(f"  AND {w}")

    # ── FETCH FIRST ──────────────────────────────────────────────
    if max_count_text and max_count_text.isdigit():
        sql_parts.append(f"FETCH FIRST {max_count_text} ROWS ONLY")
    elif max_count_text == "":
        pass  # "All" — no row limit
    else:
        sql_parts.append("FETCH FIRST 25 ROWS ONLY")

    return "\n".join(sql_parts)
