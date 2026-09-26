# PolicyInformation field registry

Generated from `suiteview.polview.models.policy_fields.FIELD_SPECS`.
Do not hand-edit table rows; update the registry and re-run this script.

| Property | Table | Column | Converter | Default | Applies to | Required |
| --- | --- | --- | --- | --- | --- | --- |
| application_written_date | LH_BAS_POL | APP_WRT_DT | date |  | Trad, Adv, WL, ISWL, DI | optional |
| bill_day | LH_BAS_POL | BIL_DAY_NBR | int | 0 | Trad, Adv, WL, ISWL, DI | yes |
| bill_form_code | LH_BAS_POL | BIL_FRM_CD | text |  | Trad, Adv, WL, ISWL, DI | yes |
| second_dividend_option | LH_BAS_POL | DIV_2ND_OPT_CD | text |  | Trad, Adv, WL, ISWL, DI | optional |
| identified_premium_indicator | LH_BAS_POL | IDT_PRM_IND | text |  | Trad, Adv, WL, ISWL, DI | optional |
| interest_monthliversary_number | LH_BAS_POL | INT_MLV_NBR | text |  | Trad, Adv, WL, ISWL, DI | optional |
| loan_interest_rate | LH_BAS_POL | LN_PLN_ITS_RT | decimal |  | Trad, Adv, WL, ISWL, DI | yes |
| last_anniversary | LH_BAS_POL | LST_ANV_DT | date |  | Trad, Adv, WL, ISWL, DI | yes |
| last_entry_code | LH_BAS_POL | LST_ETR_CD | text |  | Trad, Adv, WL, ISWL, DI | yes |
| last_financial_date | LH_BAS_POL | LST_FIN_DT | date |  | Trad, Adv, WL, ISWL, DI | yes |
| nfo_code | LH_BAS_POL | NFO_OPT_TYP_CD | text | 0 | Trad, Adv, WL, ISWL, DI | yes |
| non_traditional_indicator | LH_BAS_POL | NON_TRD_POL_IND | text | 0 | Trad, Adv, WL, ISWL, DI | yes |
| non_standard_mode_code | LH_BAS_POL | NSD_MD_CD | text |  | Trad, Adv, WL, ISWL, DI | yes |
| next_bill_date | LH_BAS_POL | NXT_BIL_DT | date |  | Trad, Adv, WL, ISWL, DI | yes |
| next_monthliversary_date | LH_BAS_POL | NXT_MVRY_PRC_DT | date |  | Trad, Adv, WL, ISWL, DI | yes |
| next_schedule_notice_date | LH_BAS_POL | NXT_SCH_NOT_DT | date |  | Trad, Adv, WL, ISWL, DI | optional |
| next_schedule_start_date | LH_BAS_POL | NXT_SCH_STT_DT | date |  | Trad, Adv, WL, ISWL, DI | optional |
| next_anniversary_date | LH_BAS_POL | NXT_YR_END_PRC_DT | date |  | Trad, Adv, WL, ISWL, DI | yes |
| original_entry_code | LH_BAS_POL | OGN_ETR_CD | text |  | Trad, Adv, WL, ISWL, DI | yes |
| terminate_date | LH_BAS_POL | PLN_TMN_DT | date |  | Trad, Adv, WL, ISWL, DI | yes |
| billing_frequency | LH_BAS_POL | PMT_FQY_PER | int | 0 | Trad, Adv, WL, ISWL, DI | yes |
| policy_1035_indicator | LH_BAS_POL | POL_1035_XCG_IND | text |  | Trad, Adv, WL, ISWL, DI | yes |
| issue_state_code | LH_BAS_POL | POL_ISS_ST_CD | text |  | Trad, Adv, WL, ISWL, DI | yes |
| modal_premium | LH_BAS_POL | POL_PRM_AMT | decimal |  | Trad, Adv, WL, ISWL, DI | yes |
| status_code | LH_BAS_POL | POL_STS_CD | text |  | Trad, Adv, WL, ISWL, DI | yes |
| div_option_code | LH_BAS_POL | PRI_DIV_OPT_CD | text | 0 | Trad, Adv, WL, ISWL, DI | yes |
| premium_paid_to_date | LH_BAS_POL | PRM_BILL_TO_DT | date |  | Trad, Adv, WL, ISWL, DI | yes |
| paid_to_date | LH_BAS_POL | PRM_PAID_TO_DT | date |  | Trad, Adv, WL, ISWL, DI | yes |
| premium_pay_status_code | LH_BAS_POL | PRM_PAY_STA_REA_CD | text |  | Trad, Adv, WL, ISWL, DI | yes |
| resident_state_code | LH_BAS_POL | PRM_PAY_ST_CD | text |  | Trad, Adv, WL, ISWL, DI | yes |
| reinsured_code | LH_BAS_POL | REINSURED_CD | text |  | Trad, Adv, WL, ISWL, DI | optional |
| suspense_code | LH_BAS_POL | SUS_CD | text | 0 | Trad, Adv, WL, ISWL, DI | yes |
| servicing_branch_code | LH_BAS_POL | SVC_AGC_NBR | text |  | Trad, Adv, WL, ISWL, DI | yes |
| servicing_agent_number | LH_BAS_POL | SVC_AGT_NBR | text |  | Trad, Adv, WL, ISWL, DI | yes |
| tefra_defra_guideline_indicator | LH_BAS_POL | TFDF_GDL_IND | text |  | Trad, Adv, WL, ISWL, DI | optional |
| mdo_code | LH_BAS_POL | USR_RES_CD | text |  | Trad, Adv, WL, ISWL, DI | yes |
| billing_control_number | LH_BIL_FRM_CTL | BIL_CTL_NBR | text |  | Trad, Adv, WL, ISWL, DI | optional |
| stored_cv_1 | LH_COV_PHA | LOW_DUR_1_CSV_AMT | decimal |  | Trad, Adv, WL, ISWL, DI | optional |
| stored_nsp_1 | LH_COV_PHA | LOW_DUR_1_NSP_AMT | decimal |  | Trad, Adv, WL, ISWL, DI | optional |
| stored_cv_2 | LH_COV_PHA | LOW_DUR_2_CSV_AMT | decimal |  | Trad, Adv, WL, ISWL, DI | optional |
| stored_nsp_2 | LH_COV_PHA | LOW_DUR_2_NSP_AMT | decimal |  | Trad, Adv, WL, ISWL, DI | optional |
| stored_cv_3 | LH_COV_PHA | LOW_DUR_3_CSV_AMT | decimal |  | Trad, Adv, WL, ISWL, DI | optional |
| stored_cv_0 | LH_COV_PHA | LOW_DUR_CSV_AMT | decimal |  | Trad, Adv, WL, ISWL, DI | optional |
| stored_nsp_0 | LH_COV_PHA | LOW_DUR_NSP_AMT | decimal |  | Trad, Adv, WL, ISWL, DI | optional |
| stored_cv_low_duration | LH_COV_PHA | LOW_DUR_PER | int |  | Trad, Adv, WL, ISWL, DI | optional |
| major_line_of_business | LH_COV_PHA | MAJ_LIN_OF_BUS_CD | text |  | Trad, Adv, WL, ISWL, DI | optional |
| mortality_factor_table | LH_COV_PHA | MTL_FCT_TBL_CD | text |  | Trad, Adv, WL, ISWL, DI | optional |
| mortality_fund_code | LH_COV_PHA | MTL_FUN_CD | text |  | Trad, Adv, WL, ISWL, DI | optional |
| number_of_lives_code | LH_COV_PHA | NBR_OF_LIVES_CD | text |  | Trad, Adv, WL, ISWL, DI | yes |
| nsp_extended_insurance_table | LH_COV_PHA | NSP_EI_TBL_CD | text |  | Trad, Adv, WL, ISWL, DI | optional |
| nsp_interest_rate | LH_COV_PHA | NSP_ITS_RT | decimal |  | Trad, Adv, WL, ISWL, DI | optional |
| nsp_reduced_paid_up_table | LH_COV_PHA | NSP_RPU_TBL_CD | text |  | Trad, Adv, WL, ISWL, DI | optional |
| product_line_code | LH_COV_PHA | PRD_LIN_TYP_CD | text |  | Trad, Adv, WL, ISWL, DI | yes |
| reserve_interest_rate | LH_COV_PHA | RES_ITS_RT | decimal |  | Trad, Adv, WL, ISWL, DI | optional |
| annual_policy_fee | LH_FXD_PRM_POL | POL_FEE_AMT | decimal |  | Trad, WL, DI | yes |
| corridor_percent | LH_NON_TRD_POL | CDR_PCT | decimal | 100 | Adv, ISWL | yes |
| db_option_code | LH_NON_TRD_POL | DTH_BNF_PLN_OPT_CD | text |  | Adv, ISWL | yes |
| advanced_grace_expiry | LH_NON_TRD_POL | GRA_PER_EXP_DT | date |  | Adv, ISWL | yes |
| grace_rule_code | LH_NON_TRD_POL | GRA_THD_RLE_CD | text |  | Adv, ISWL | yes |
| advanced_grace_indicator | LH_NON_TRD_POL | IN_GRA_PER_IND | text |  | Adv, ISWL | yes |
| guaranteed_interest_rate | LH_NON_TRD_POL | POL_GUA_ITS_RT | decimal |  | Adv, ISWL | yes |
| preferred_loan_interest_rate | LH_NON_TRD_POL | PRF_LN_ITS_CRG_RT | decimal |  | Adv, ISWL | yes |
| definition_of_life_code | LH_NON_TRD_POL | TFDF_CD | text |  | Adv, ISWL | yes |
| monthly_cost_of_insurance | LH_POL_MVRY_VAL | CINS_AMT | decimal |  | Adv, ISWL | yes |
| monthly_cash_surrender_value | LH_POL_MVRY_VAL | CSV_AMT | decimal |  | Adv, ISWL | yes |
| monthly_expense_charge | LH_POL_MVRY_VAL | EXP_CRG_AMT | decimal |  | Adv, ISWL | yes |
| monthly_value_date | LH_POL_MVRY_VAL | MVRY_DT | date |  | Adv, ISWL | yes |
| valuation_monthliversary_date | LH_POL_MVRY_VAL | MVRY_DT | date |  | Adv, ISWL | yes |
| monthly_net_amount_at_risk | LH_POL_MVRY_VAL | NAR_AMT | decimal |  | Adv, ISWL | optional |
| monthly_other_charge | LH_POL_MVRY_VAL | OTH_PRM_AMT | decimal |  | Adv, ISWL | yes |
| monthly_duration | LH_POL_MVRY_VAL | POL_DUR_NBR | int |  | Adv, ISWL | optional |
| target_premium | LH_POL_TARGET | TAR_PRM_AMT | decimal |  | Adv, ISWL | yes |
| traditional_grace_expiry | LH_TRD_POL | GRA_PER_EXP_DT | date |  | Trad, WL, DI | yes |
| traditional_grace_indicator | LH_TRD_POL | IN_GRA_PER_IND | text |  | Trad, WL, DI | yes |
| forced_premium_indicator | TH_BAS_POL | FORCED_PREM_IND | text |  | Trad, Adv, WL, ISWL, DI | optional |
| annuity_product_id | TH_COV_PHA | AN_PRD_ID | text |  | Trad, Adv, WL, ISWL, DI | optional |
| decrease_charge_rule | TH_NON_TRD_POL | DECR_CHRG_ALLOW | text |  | Adv, ISWL | optional |
| converted_policy_number | TH_USER_GENERIC | EXCH_POL_NUMBER | text |  | Trad, Adv, WL, ISWL, DI | optional |
| replaced_policy_number | TH_USER_REPLACEMENT | REPLACED_POLICY | text |  | Trad, Adv, WL, ISWL, DI | optional |
