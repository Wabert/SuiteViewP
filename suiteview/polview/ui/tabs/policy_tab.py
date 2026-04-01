"""
Policy tab – three-column policy detail view (Policy Information,
Billing & Valuation, Marketing & Loan).
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from ..formatting import format_currency, format_date, format_rate, US_DATE_FMT
from ..widgets import StyledInfoTableGroup
from ...models.cl_polrec.policy_translations import (
    translate_state_code,
    translate_company_code,
    translate_product_line_code,
    translate_entry_code,
    translate_last_entry_code,
    translate_div_option_code,
    translate_mec_indicator,
    translate_reinsurance_code,
    translate_nfo_code,
    translate_bill_form_code,
    translate_loan_type_code,
    translate_market_org,
    translate_bill_mode_from_frequency,
    translate_mortality_table_code,
    translate_grace_indicator,
    translate_tefra_defra_ind,
    translate_multiply_order_code,
    translate_rating_order_code,
)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


class PolicyTab(QWidget):
    """
    Tab for Policy information - matches VBA Excel SuiteView layout.

    Layout:
    - Three columns of name/value pairs:
      Column 1: Policy identification, status, dates, indicators
      Column 2: Billing/Premium, entry codes, dividend options, valuation tables
      Column 3: Marketing/Servicing, Class/Base/Sub, Loan info
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db_data = {}
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(8)

        self.col1 = StyledInfoTableGroup("Policy Information", columns=1,
                                         show_info=True, show_table=False)
        self._setup_column1_fields()
        columns_layout.addWidget(self.col1)

        self.col2 = StyledInfoTableGroup("Billing & Valuation", columns=1,
                                         show_info=True, show_table=False)
        self._setup_column2_fields()
        columns_layout.addWidget(self.col2)

        self.col3 = StyledInfoTableGroup("Marketing & Loan", columns=1,
                                         show_info=True, show_table=False)
        self._setup_column3_fields()
        columns_layout.addWidget(self.col3)

        main_layout.addLayout(columns_layout, stretch=1)

    # ── field setup ──────────────────────────────────────────────────────

    def _setup_column1_fields(self):
        c = self.col1
        c.add_field("Policynumber", "pol_number", 160, 120)
        c.add_field("Company", "company", 160, 120)
        c.add_field("Plancode", "plancode", 160, 120)
        c.add_field("Product Line Code", "prod_line", 160, 120)
        c.add_field("ANICO Product Indicator", "an_prd_id", 160, 120)
        c.add_field("Advanced Product Indicator", "non_trd_ind", 160, 120)
        c.add_field("Issue State", "issue_state", 160, 120)
        c.add_field("Billing Status", "prm_pay_sta", 160, 120)
        c.add_field("Suspend Billing Code", "sus_cd", 160, 120)
        c.add_field("Grace Indicator", "in_grace", 160, 120)
        c.add_field("GPE Date", "gpe_date", 160, 120)
        c.add_field("Paid-To Date", "prm_paid_to", 160, 120)
        c.add_field("Billed-To Date", "prm_bill_to", 160, 120)
        c.add_field("Application Date", "app_wrt_dt", 160, 120)
        c.add_field("Last Anniversary Processed", "lst_anv_dt", 160, 120)
        c.add_field("Next Bill Date", "nxt_bil_dt", 160, 120)
        c.add_field("Next Scheduled Notification Date", "nxt_sch_not", 160, 120)
        c.add_field("Next Scheduled Statement Date", "nxt_sch_stt", 160, 120)
        c.add_field("Next Monthliversary Date", "nxt_mvry_prc", 160, 120)
        c.add_field("Next Year-End Date", "nxt_yr_end", 160, 120)
        c.add_field("Last Financial Date", "lst_fin_dt2", 160, 120)
        c.add_field("1035 Exchange Indicator", "pol_1035", 160, 120)
        c.add_field("Indeterminate Premium Indicator", "idt_prm_ind", 160, 120)
        c.add_field("Policy Under TEFRA/DEFRA", "tfdf_gdl", 160, 120)
        c.add_field("Initial Monthliversary", "int_mlv_nbr", 160, 120)
        c.add_field("Reinsured Code", "reinsured", 160, 120)

    def _setup_column2_fields(self):
        c = self.col2
        c.add_field("Premium Mode", "prm_mode", 130, 120)
        c.add_field("Modal Premium", "modal_prm", 130, 120)
        c.add_field("Billing Form", "bil_form", 130, 120)
        c.add_field("Billing Control Number", "bil_ctl_nbr", 130, 120)
        c.add_field("Replaced Policy", "replaced_pol", 130, 120)
        c.add_field("Original Entry Code", "ogn_etr_cd", 130, 120)
        c.add_field("Converted Policy", "conv_pol", 130, 120)
        c.add_field("Last Entry Code", "lst_etr_cd", 130, 120)
        c.add_field("MDO", "mdo", 130, 120)
        c.add_field("ByPass Lapse", "bypass_lapse", 130, 120)
        c.add_field("MEC Indicator", "mec_status", 130, 120)
        c.add_field("Nonforfeiture Option", "nfo_opt", 130, 120)
        c.add_field("Dividend Option", "pri_div_opt", 130, 120)
        c.add_field("Dividend Secondary", "div_2nd_opt", 130, 120)
        c.add_field("Mortality Table", "mtl_tbl", 130, 120)
        c.add_field("Description", "mtl_desc", 130, 120)
        c.add_field("Valuation Interest Rate", "res_its_rt", 130, 120)
        c.add_field("Function", "mtl_fun_cd", 130, 120)
        c.add_field("EI Table", "nsp_ei_tbl", 130, 120)
        c.add_field("Description", "nsp_ei_desc", 130, 120)
        c.add_field("RPU Table", "nsp_rpu_tbl", 130, 120)
        c.add_field("Description", "nsp_rpu_desc", 130, 120)
        c.add_field("NSP Interest Rate", "nsp_its_rt", 130, 120)

    def _setup_column3_fields(self):
        c = self.col3
        c.add_field("Marketing Org", "mkt_org", 130, 100)
        c.add_field("Servicing Branch", "svc_branch", 130, 100)
        c.add_field("Agency Branch", "agency_br", 130, 100)
        c.add_field("MDO", "mdo3", 130, 100)
        c.add_field("Servicing Agent", "svc_agent", 130, 100)
        c.add_field("Class", "class_cd", 130, 100)
        c.add_field("Base", "base_cd", 130, 100)
        c.add_field("Sub", "sub_cd", 130, 100)
        c.add_field("Loan Interest Type Code", "ln_typ", 130, 100)
        c.add_field("Loan Interest Rate", "ln_rate", 130, 100)
        c.add_field("Semi-Ann Factor", "san_md_fct", 130, 100)
        c.add_field("Quarterly Factor", "qtr_md_fct", 130, 100)
        c.add_field("Monthly Factor", "mo_md_fct", 130, 100)
        c.add_field("Multiply Order Code", "md_prm_ord", 130, 100)
        c.add_field("Rating Order Code", "rt_fct_ord", 130, 100)
        c.add_field("Rounding Rule", "rou_rle_cd", 130, 100)

    # ── PolicyInformation path ───────────────────────────────────────────

    def load_data_from_policy(self, policy: 'PolicyInformation', policy_info: dict = None):
        try:
            if not policy.exists:
                return
            if policy_info is None:
                policy_info = {
                    "PolicyID": policy.policy_id,
                    "PolicyNumber": policy.policy_number,
                    "CompanyCode": policy.company_code,
                    "SystemCode": policy.system_code,
                    "Region": policy.region,
                }
            self._populate_column1_from_policy(policy, policy_info)
            self._populate_column2_from_policy(policy)
            self._populate_column3_from_policy(policy, policy_info)
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _populate_column1_from_policy(self, policy, policy_info: dict):
        c = self.col1
        c.set_value("pol_number", policy_info.get("PolicyNumber", policy.policy_number))
        c.set_value("company", translate_company_code(str(policy.company_code)))
        c.set_value("plancode", policy.base_plancode)
        prod_line = policy.product_line_code
        c.set_value("prod_line", f"{prod_line} - {translate_product_line_code(prod_line)}")
        c.set_value("an_prd_id", str(policy.data_item("TH_COV_PHA", "AN_PRD_ID") or ""))
        c.set_value("non_trd_ind", str(policy.data_item("LH_BAS_POL", "NON_TRD_POL_IND") or ""))

        state_code = str(policy.issue_state_code or "")
        try:
            c.set_value("issue_state", translate_state_code(int(state_code)) if state_code else "")
        except (ValueError, TypeError):
            c.set_value("issue_state", state_code)
        c.set_value("prm_pay_sta", str(policy.data_item("LH_BAS_POL", "PRM_PAY_STA_REA_CD") or ""))
        c.set_value("sus_cd", str(policy.data_item("LH_BAS_POL", "SUS_CD") or ""))
        if policy.is_advanced_product:
            grace_val = str(policy.data_item("LH_NON_TRD_POL", "IN_GRA_PER_IND") or "0")
        else:
            grace_val = str(policy.data_item("LH_TRD_POL", "IN_GRA_PER_IND") or "0")
        c.set_value("in_grace", f"{grace_val} - {translate_grace_indicator(grace_val)}")
        c.set_value("gpe_date", format_date(policy.grace_period_expiry_date, US_DATE_FMT))

        c.set_value("prm_paid_to", format_date(policy.paid_to_date, US_DATE_FMT))
        c.set_value("prm_bill_to", format_date(policy.data_item("LH_BAS_POL", "PRM_BILL_TO_DT"), US_DATE_FMT))
        c.set_value("app_wrt_dt", format_date(policy.data_item("LH_BAS_POL", "APP_WRT_DT"), US_DATE_FMT))
        c.set_value("lst_anv_dt", format_date(policy.last_anniversary, US_DATE_FMT))
        c.set_value("nxt_bil_dt", format_date(policy.next_bill_date, US_DATE_FMT))
        c.set_value("nxt_sch_not", format_date(policy.data_item("LH_BAS_POL", "NXT_SCH_NOT_DT"), US_DATE_FMT))
        c.set_value("nxt_sch_stt", format_date(policy.data_item("LH_BAS_POL", "NXT_SCH_STT_DT"), US_DATE_FMT))
        c.set_value("nxt_mvry_prc", format_date(policy.data_item("LH_BAS_POL", "NXT_MVRY_PRC_DT"), US_DATE_FMT))
        c.set_value("nxt_yr_end", format_date(policy.data_item("LH_BAS_POL", "NXT_YR_END_PRC_DT"), US_DATE_FMT))
        c.set_value("lst_fin_dt2", format_date(policy.data_item("LH_BAS_POL", "LST_FIN_DT"), US_DATE_FMT))

        c.set_value("pol_1035", str(policy.data_item("LH_BAS_POL", "POL_1035_XCG_IND") or ""))
        c.set_value("idt_prm_ind", str(policy.data_item("LH_BAS_POL", "IDT_PRM_IND") or ""))
        tfdf = str(policy.data_item("LH_BAS_POL", "TFDF_GDL_IND") or "")
        c.set_value("tfdf_gdl", f"{tfdf} - {translate_tefra_defra_ind(tfdf)}" if tfdf else "")
        c.set_value("int_mlv_nbr", str(policy.data_item("LH_BAS_POL", "INT_MLV_NBR") or ""))
        rein_cd = str(policy.data_item("LH_BAS_POL", "REINSURED_CD") or "").strip()
        c.set_value("reinsured", translate_reinsurance_code(rein_cd))

    def _populate_column2_from_policy(self, policy):
        c = self.col2
        prm_mode = translate_bill_mode_from_frequency(
            str(policy.data_item("LH_BAS_POL", "PMT_FQY_PER") or ""),
            str(policy.data_item("LH_BAS_POL", "NSD_MD_CD") or ""),
        )
        c.set_value("prm_mode", prm_mode)
        c.set_value("modal_prm", format_currency(policy.data_item("LH_BAS_POL", "POL_PRM_AMT"), "$"))

        bil_form = str(policy.data_item("LH_BAS_POL", "BIL_FRM_CD") or "")
        c.set_value("bil_form", translate_bill_form_code(bil_form))
        c.set_value("bil_ctl_nbr", str(policy.data_item("LH_BIL_FRM_CTL", "BIL_CTL_NBR") or ""))
        c.set_value("replaced_pol", str(policy.data_item("TH_USER_REPLACEMENT", "REPLACED_POLICY") or ""))

        ogn = str(policy.data_item("LH_BAS_POL", "OGN_ETR_CD") or "")
        c.set_value("ogn_etr_cd", f"{ogn} - {translate_entry_code(ogn)}")
        c.set_value("conv_pol", str(policy.data_item("TH_USER_GENERIC", "EXCH_POL_NUMBER") or "Null").strip())
        lst = str(policy.data_item("LH_BAS_POL", "LST_ETR_CD") or "")
        c.set_value("lst_etr_cd", f"{lst} - {translate_last_entry_code(lst)}")

        usr_res = str(policy.data_item("LH_BAS_POL", "USR_RES_CD") or "")
        c.set_value("mdo", usr_res[:1] if usr_res else "")
        c.set_value("bypass_lapse", usr_res[-1:] if len(usr_res) > 1 else "")
        c.set_value("mec_status", translate_mec_indicator(policy.mec_indicator))

        nfo = policy.nfo_code
        if policy.is_advanced_product:
            c.set_value("nfo_opt", "Surrender value")
        else:
            c.set_value("nfo_opt", f"{nfo} - {policy.nfo_description}")

        pri_div = policy.div_option_code
        c.set_value("pri_div_opt", f"{pri_div} - {policy.div_option_description}")
        div_2nd = str(policy.data_item("LH_BAS_POL", "DIV_2ND_OPT_CD") or "")
        c.set_value("div_2nd_opt", f"{div_2nd} - {translate_div_option_code(div_2nd)}")

        mtl_tbl_cd = str(policy.data_item("LH_COV_PHA", "MTL_FCT_TBL_CD") or "").strip()
        c.set_value("mtl_tbl", mtl_tbl_cd)
        c.set_value("mtl_desc", translate_mortality_table_code(mtl_tbl_cd))
        res_rt = policy.data_item("LH_COV_PHA", "RES_ITS_RT")
        c.set_value("res_its_rt", format_rate(res_rt, decimals=2, suffix="%"))
        c.set_value("mtl_fun_cd", str(policy.data_item("LH_COV_PHA", "MTL_FUN_CD") or ""))

        nsp_ei_cd = str(policy.data_item("LH_COV_PHA", "NSP_EI_TBL_CD") or "").strip()
        c.set_value("nsp_ei_tbl", nsp_ei_cd)
        c.set_value("nsp_ei_desc", translate_mortality_table_code(nsp_ei_cd))
        nsp_rpu_cd = str(policy.data_item("LH_COV_PHA", "NSP_RPU_TBL_CD") or "").strip()
        c.set_value("nsp_rpu_tbl", nsp_rpu_cd)
        c.set_value("nsp_rpu_desc", translate_mortality_table_code(nsp_rpu_cd))
        nsp_rt = policy.data_item("LH_COV_PHA", "NSP_ITS_RT")
        if nsp_rt and str(nsp_rt) != "Null":
            c.set_value("nsp_its_rt", format_rate(nsp_rt, decimals=2, suffix="%"))
        else:
            c.set_value("nsp_its_rt", "")

    def _populate_column3_from_policy(self, policy, policy_info: dict):
        c = self.col3
        svc_agc = str(policy.data_item("LH_BAS_POL", "SVC_AGC_NBR") or "").strip()
        company_code = str(policy.company_code)
        mkt_org_code = svc_agc[:1] if svc_agc else ""
        c.set_value("mkt_org", translate_market_org(company_code, mkt_org_code))
        c.set_value("svc_branch", svc_agc)
        c.set_value("agency_br", svc_agc[1:4] if len(svc_agc) > 1 else "")
        usr_res3 = str(policy.data_item("LH_BAS_POL", "USR_RES_CD") or "")
        c.set_value("mdo3", usr_res3[:1] if usr_res3 else "")
        c.set_value("svc_agent", str(policy.data_item("LH_BAS_POL", "SVC_AGT_NBR") or "").strip())

        c.set_value("class_cd", str(policy.data_item("LH_COV_PHA", "INS_CLS_CD") or ""))
        c.set_value("base_cd", str(policy.data_item("LH_COV_PHA", "PLN_BSE_SRE_CD") or ""))
        c.set_value("sub_cd", str(policy.data_item("LH_COV_PHA", "LIF_PLN_SUB_SRE_CD") or ""))

        ln_typ = str(policy.data_item("LH_BAS_POL", "LN_TYP_CD") or "")
        if ln_typ == "9":
            c.set_value("ln_typ", "Loans not allowed")
            c.set_value("ln_rate", "")
        else:
            c.set_value("ln_typ", translate_loan_type_code(ln_typ))
            if ln_typ not in ("6", "7"):
                c.set_value("ln_rate", format_rate(policy.data_item("LH_BAS_POL", "LN_PLN_ITS_RT"), decimals=2, suffix="%"))
            else:
                c.set_value("ln_rate", "")

        c.set_value("san_md_fct", str(policy.data_item("LH_FXD_PRM_POL", "SAN_MD_FCT") or ""))
        c.set_value("qtr_md_fct", str(policy.data_item("LH_FXD_PRM_POL", "QTR_MD_FCT") or ""))
        c.set_value("mo_md_fct", str(policy.data_item("LH_FXD_PRM_POL", "MO_MD_FCT") or ""))
        md_ord = str(policy.data_item("LH_FXD_PRM_POL", "MD_PRM_MUL_ORD_CD") or "").strip()
        c.set_value("md_prm_ord", f"{md_ord} - {translate_multiply_order_code(md_ord)}" if md_ord else "")
        rt_ord = str(policy.data_item("LH_FXD_PRM_POL", "RT_FCT_ORD_CD") or "").strip()
        c.set_value("rt_fct_ord", f"{rt_ord} - {translate_rating_order_code(rt_ord)}" if rt_ord else "")
        c.set_value("rou_rle_cd", str(policy.data_item("LH_FXD_PRM_POL", "ROU_RLE_CD") or ""))
