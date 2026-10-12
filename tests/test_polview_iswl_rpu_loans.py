"""ISWL on RPU keeps its loans in the traditional loan table (VBA PopulateTradLoanDetail rule)."""

from decimal import Decimal
from types import SimpleNamespace

from suiteview.polview.models.cl_polrec.CL_POLREC_20_77 import LoanRecords
from suiteview.polview.models.policy_sections.loans import LoansSection
from suiteview.polview.models.product_rules import AdvancedRules, ISWLRules, WholeLifeRules
from suiteview.polview.ui.tabs.loans_tab import LoansTab

# Converted pre-RPU fund-loan history: no current (12/31/9999) fund rows remain.
_FUND_HISTORY = [
    {"MVRY_DT": "2020-03-02", "PRF_LN_IND": "0", "FND_ID_CD": "I1", "FND_VAL_PHA_NBR": 1,
     "LN_PRI_AMT": Decimal("7902.07"), "POL_LN_ITS_AMT": Decimal("102.18"),
     "LN_CRG_ITS_RT": Decimal("8"), "LN_ITS_AMT_TYP_CD": "2"},
    {"MVRY_DT": "2020-02-02", "PRF_LN_IND": "0", "FND_ID_CD": "I1", "FND_VAL_PHA_NBR": 1,
     "LN_PRI_AMT": Decimal("7852.73"), "POL_LN_ITS_AMT": Decimal("53.35"),
     "LN_CRG_ITS_RT": Decimal("8"), "LN_ITS_AMT_TYP_CD": "2"},
]
_CASH_VALUE_LOANS = [
    {"MVRY_DT": "9999-12-31", "PRF_LN_IND": "0", "LN_PRI_AMT": Decimal("15179.94"),
     "POL_LN_ITS_AMT": Decimal("0"), "LN_CRG_ITS_RT": Decimal("8"), "LN_ITS_AMT_TYP_CD": "1"},
    {"MVRY_DT": "2026-01-02", "PRF_LN_IND": "0", "LN_PRI_AMT": Decimal("14089.59"),
     "POL_LN_ITS_AMT": Decimal("111.41"), "LN_CRG_ITS_RT": Decimal("8"), "LN_ITS_AMT_TYP_CD": "2"},
]


class _Policy:
    """Minimal PolicyInformation stand-in wired to the real loan section and records."""

    def __init__(self, rules, premium_pay_status_code):
        self.product = SimpleNamespace(
            product_rules=rules,
            is_advanced_product=rules.is_advanced,
            product_type=rules.product_type,
        )
        self.status = SimpleNamespace(premium_pay_status_code=premium_pay_status_code)
        self.loans = LoansSection(self)
        self.loan_records = LoanRecords(self)

    def fetch_table(self, table):
        return {
            "LH_FND_VAL_LOAN": _FUND_HISTORY,
            "LH_CSH_VAL_LOAN": _CASH_VALUE_LOANS,
        }.get(table, [])

    def data_item(self, table, field, index=0):
        return {("LH_BAS_POL", "LN_TYP_CD"): "1"}.get((table, field))

    def _field(self, name):
        return {"loan_interest_rate": Decimal("8")}.get(name)


def test_iswl_rpu_uses_cash_value_loan_table():
    assert ISWLRules().active_loan_table("45") == "LH_CSH_VAL_LOAN"
    assert ISWLRules().active_loan_table(" 45 ") == "LH_CSH_VAL_LOAN"
    assert ISWLRules().active_loan_table("22") == "LH_FND_VAL_LOAN"
    assert AdvancedRules().active_loan_table("45") == "LH_FND_VAL_LOAN"
    assert WholeLifeRules().active_loan_table("45") == "LH_CSH_VAL_LOAN"


def test_iswl_rpu_loan_totals_read_current_cash_value_loan():
    policy = _Policy(ISWLRules(), "45")

    assert policy.loans.uses_fund_loans is False
    assert policy.loan_records.total_regular_loan_principal == Decimal("15179.94")
    assert policy.loan_records.policy_debt == Decimal("15179.94")
    assert policy.loans.total_loan_balance == Decimal("15179.94")


def test_iswl_premium_paying_still_uses_fund_loans():
    policy = _Policy(ISWLRules(), "22")

    assert policy.loans.uses_fund_loans is True
    assert policy.loans.loan_table == "LH_FND_VAL_LOAN"


def test_loans_tab_shows_iswl_rpu_debt(qtbot):
    tab = LoansTab()
    qtbot.addWidget(tab)

    tab.load_data_from_policy(_Policy(ISWLRules(), "45"))

    assert tab._summary_group.get_value("debt_value") == "15,179.94"
    assert tab._reg_group.get_value("reg_principal") == "15,179.94"
    assert tab.loan_detail_group.table.rowCount() == len(_CASH_VALUE_LOANS)
