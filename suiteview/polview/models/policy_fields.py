"""PolicyInformation scalar field registry.

The registry is deliberately data-only: it states the DB2 table/column,
conversion intent, default, product applicability and required/optional status
for scalar ``PolicyInformation`` properties. ``PolicyData`` uses the optional
entries to distinguish a legitimate table-version gap from a misspelled column.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldSpec:
    """Source contract for one scalar policy property."""

    name: str
    table: str
    column: str
    converter: str = "text"
    default: Any = None
    applies_to: tuple[str, ...] = ("Trad", "Adv", "WL", "ISWL", "DI")
    required: bool = True

    @property
    def optional(self) -> bool:
        return not self.required


def _spec(
    name: str,
    table: str,
    column: str,
    converter: str = "text",
    default: Any = None,
    applies_to: tuple[str, ...] = ("Trad", "Adv", "WL", "ISWL", "DI"),
    required: bool = True,
) -> FieldSpec:
    return FieldSpec(
        name=name,
        table=table.upper(),
        column=column.upper(),
        converter=converter,
        default=default,
        applies_to=applies_to,
        required=required,
    )


FIELD_SPECS: tuple[FieldSpec, ...] = (
    _spec("status_code", "LH_BAS_POL", "POL_STS_CD", default=""),
    _spec("suspense_code", "LH_BAS_POL", "SUS_CD", default="0"),
    _spec("premium_pay_status_code", "LH_BAS_POL", "PRM_PAY_STA_REA_CD", default=""),
    _spec("paid_to_date", "LH_BAS_POL", "PRM_PAID_TO_DT", "date"),
    _spec("next_anniversary_date", "LH_BAS_POL", "NXT_YR_END_PRC_DT", "date"),
    _spec("next_monthliversary_date", "LH_BAS_POL", "NXT_MVRY_PRC_DT", "date"),
    _spec("terminate_date", "LH_BAS_POL", "PLN_TMN_DT", "date"),
    _spec("billing_frequency", "LH_BAS_POL", "PMT_FQY_PER", "int", 0),
    _spec("non_standard_mode_code", "LH_BAS_POL", "NSD_MD_CD", default=""),
    _spec("bill_day", "LH_BAS_POL", "BIL_DAY_NBR", "int", 0),
    _spec("issue_state_code", "LH_BAS_POL", "POL_ISS_ST_CD", default=""),
    _spec("resident_state_code", "LH_BAS_POL", "PRM_PAY_ST_CD", default=""),
    _spec("modal_premium", "LH_BAS_POL", "POL_PRM_AMT", "decimal"),
    _spec("annual_policy_fee", "LH_FXD_PRM_POL", "POL_FEE_AMT", "decimal", applies_to=("Trad", "WL", "DI")),
    _spec("target_premium", "LH_POL_TARGET", "TAR_PRM_AMT", "decimal", applies_to=("Adv", "ISWL")),
    _spec("div_option_code", "LH_BAS_POL", "PRI_DIV_OPT_CD", default="0"),
    _spec("nfo_code", "LH_BAS_POL", "NFO_OPT_TYP_CD", default="0"),
    _spec("db_option_code", "LH_NON_TRD_POL", "DTH_BNF_PLN_OPT_CD", default="", applies_to=("Adv", "ISWL")),
    _spec("non_traditional_indicator", "LH_BAS_POL", "NON_TRD_POL_IND", default="0"),
    _spec("product_line_code", "LH_COV_PHA", "PRD_LIN_TYP_CD", default=""),
    _spec("definition_of_life_code", "LH_NON_TRD_POL", "TFDF_CD", default="", applies_to=("Adv", "ISWL")),
    _spec("number_of_lives_code", "LH_COV_PHA", "NBR_OF_LIVES_CD", default=""),
    _spec("last_anniversary", "LH_BAS_POL", "LST_ANV_DT", "date"),
    _spec("last_financial_date", "LH_BAS_POL", "LST_FIN_DT", "date"),
    _spec("next_bill_date", "LH_BAS_POL", "NXT_BIL_DT", "date"),
    _spec("premium_paid_to_date", "LH_BAS_POL", "PRM_BILL_TO_DT", "date"),
    _spec("valuation_monthliversary_date", "LH_POL_MVRY_VAL", "MVRY_DT", "date", applies_to=("Adv", "ISWL")),
    _spec("advanced_grace_expiry", "LH_NON_TRD_POL", "GRA_PER_EXP_DT", "date", applies_to=("Adv", "ISWL")),
    _spec("traditional_grace_expiry", "LH_TRD_POL", "GRA_PER_EXP_DT", "date", applies_to=("Trad", "WL", "DI")),
    _spec("advanced_grace_indicator", "LH_NON_TRD_POL", "IN_GRA_PER_IND", default="", applies_to=("Adv", "ISWL")),
    _spec("traditional_grace_indicator", "LH_TRD_POL", "IN_GRA_PER_IND", default="", applies_to=("Trad", "WL", "DI")),
    _spec("original_entry_code", "LH_BAS_POL", "OGN_ETR_CD", default=""),
    _spec("application_written_date", "LH_BAS_POL", "APP_WRT_DT", "date", required=False),
    _spec("second_dividend_option", "LH_BAS_POL", "DIV_2ND_OPT_CD", default="", required=False),
    _spec("identified_premium_indicator", "LH_BAS_POL", "IDT_PRM_IND", default="", required=False),
    _spec("interest_monthliversary_number", "LH_BAS_POL", "INT_MLV_NBR", default="", required=False),
    _spec("last_entry_code", "LH_BAS_POL", "LST_ETR_CD", default=""),
    _spec("next_schedule_notice_date", "LH_BAS_POL", "NXT_SCH_NOT_DT", "date", required=False),
    _spec("next_schedule_start_date", "LH_BAS_POL", "NXT_SCH_STT_DT", "date", required=False),
    _spec("policy_1035_indicator", "LH_BAS_POL", "POL_1035_XCG_IND", default=""),
    _spec("reinsured_code", "LH_BAS_POL", "REINSURED_CD", default="", required=False),
    _spec("servicing_agent_number", "LH_BAS_POL", "SVC_AGT_NBR", default=""),
    _spec("servicing_branch_code", "LH_BAS_POL", "SVC_AGC_NBR", default=""),
    _spec("loan_interest_rate", "LH_BAS_POL", "LN_PLN_ITS_RT", "decimal"),
    _spec("forced_premium_indicator", "TH_BAS_POL", "FORCED_PREM_IND", default="", required=False),
    _spec("mdo_code", "LH_BAS_POL", "USR_RES_CD", default=""),
    _spec("bill_form_code", "LH_BAS_POL", "BIL_FRM_CD", default=""),
    _spec("guaranteed_interest_rate", "LH_NON_TRD_POL", "POL_GUA_ITS_RT", "decimal", applies_to=("Adv", "ISWL")),
    _spec("preferred_loan_interest_rate", "LH_NON_TRD_POL", "PRF_LN_ITS_CRG_RT", "decimal", applies_to=("Adv", "ISWL")),
    _spec("corridor_percent", "LH_NON_TRD_POL", "CDR_PCT", "decimal", "100", applies_to=("Adv", "ISWL")),
    _spec("grace_rule_code", "LH_NON_TRD_POL", "GRA_THD_RLE_CD", default="", applies_to=("Adv", "ISWL")),
    _spec("tefra_defra_guideline_indicator", "LH_BAS_POL", "TFDF_GDL_IND", default="", required=False),
    _spec("decrease_charge_rule", "TH_NON_TRD_POL", "DECR_CHRG_ALLOW", default="", applies_to=("Adv", "ISWL"), required=False),
    _spec("monthly_value_date", "LH_POL_MVRY_VAL", "MVRY_DT", "date", applies_to=("Adv", "ISWL")),
    _spec("monthly_cash_surrender_value", "LH_POL_MVRY_VAL", "CSV_AMT", "decimal", applies_to=("Adv", "ISWL")),
    _spec("monthly_cost_of_insurance", "LH_POL_MVRY_VAL", "CINS_AMT", "decimal", applies_to=("Adv", "ISWL")),
    _spec("monthly_expense_charge", "LH_POL_MVRY_VAL", "EXP_CRG_AMT", "decimal", applies_to=("Adv", "ISWL")),
    _spec("monthly_other_charge", "LH_POL_MVRY_VAL", "OTH_PRM_AMT", "decimal", applies_to=("Adv", "ISWL")),
    _spec("monthly_net_amount_at_risk", "LH_POL_MVRY_VAL", "NAR_AMT", "decimal", applies_to=("Adv", "ISWL"), required=False),
    _spec("monthly_duration", "LH_POL_MVRY_VAL", "POL_DUR_NBR", "int", applies_to=("Adv", "ISWL"), required=False),
    _spec("stored_cv_low_duration", "LH_COV_PHA", "LOW_DUR_PER", "int", required=False),
    _spec("major_line_of_business", "LH_COV_PHA", "MAJ_LIN_OF_BUS_CD", default="", required=False),
    _spec("mortality_factor_table", "LH_COV_PHA", "MTL_FCT_TBL_CD", default="", required=False),
    _spec("mortality_fund_code", "LH_COV_PHA", "MTL_FUN_CD", default="", required=False),
    _spec("nsp_extended_insurance_table", "LH_COV_PHA", "NSP_EI_TBL_CD", default="", required=False),
    _spec("nsp_interest_rate", "LH_COV_PHA", "NSP_ITS_RT", "decimal", required=False),
    _spec("nsp_reduced_paid_up_table", "LH_COV_PHA", "NSP_RPU_TBL_CD", default="", required=False),
    _spec("reserve_interest_rate", "LH_COV_PHA", "RES_ITS_RT", "decimal", required=False),
    _spec("stored_cv_0", "LH_COV_PHA", "LOW_DUR_CSV_AMT", "decimal", required=False),
    _spec("stored_cv_1", "LH_COV_PHA", "LOW_DUR_1_CSV_AMT", "decimal", required=False),
    _spec("stored_cv_2", "LH_COV_PHA", "LOW_DUR_2_CSV_AMT", "decimal", required=False),
    _spec("stored_cv_3", "LH_COV_PHA", "LOW_DUR_3_CSV_AMT", "decimal", required=False),
    _spec("stored_nsp_0", "LH_COV_PHA", "LOW_DUR_NSP_AMT", "decimal", required=False),
    _spec("stored_nsp_1", "LH_COV_PHA", "LOW_DUR_1_NSP_AMT", "decimal", required=False),
    _spec("stored_nsp_2", "LH_COV_PHA", "LOW_DUR_2_NSP_AMT", "decimal", required=False),
    _spec("billing_control_number", "LH_BIL_FRM_CTL", "BIL_CTL_NBR", default="", required=False),
    _spec("annuity_product_id", "TH_COV_PHA", "AN_PRD_ID", default="", required=False),
    _spec("converted_policy_number", "TH_USER_GENERIC", "EXCH_POL_NUMBER", default="", required=False),
    _spec("replaced_policy_number", "TH_USER_REPLACEMENT", "REPLACED_POLICY", default="", required=False),
)

FIELD_SPECS_BY_NAME = {spec.name: spec for spec in FIELD_SPECS}
OPTIONAL_COLUMNS_BY_TABLE = {
    spec.table: frozenset(s.column for s in FIELD_SPECS if s.table == spec.table and not s.required)
    for spec in FIELD_SPECS
}


def field_spec(name: str) -> FieldSpec:
    return FIELD_SPECS_BY_NAME[name]


def is_optional_column(table: str, column: str) -> bool:
    return column.upper() in OPTIONAL_COLUMNS_BY_TABLE.get(table.upper(), frozenset())
