from decimal import Decimal
from types import SimpleNamespace

from suiteview.polview.ui.tabs.loans_tab import LoansTab


class _AdvancedLoanPolicy:
    is_advanced_product = True
    product_type = "UL"
    status_code = "0"
    fixed_loan_interest_rate = Decimal("6")
    preferred_loan_interest_rate = Decimal("5")

    def __init__(self):
        self.product = self
        self.status = self
        self.loans = self
        self.loan_records = SimpleNamespace(
            total_regular_loan_principal=Decimal("1000"),
            total_regular_loan_accrued=Decimal("25"),
            total_preferred_loan_principal=Decimal("0"),
            total_preferred_loan_accrued=Decimal("0"),
            total_variable_loan_principal=Decimal("0"),
            total_variable_loan_accrued=Decimal("0"),
            preferred_loans_available=False,
            policy_debt=Decimal("1025"),
        )

    @staticmethod
    def fetch_table(table):
        if table == "LH_FND_VAL_LOAN":
            return [{
                "MVRY_DT": "9999-12-31",
                "PRF_LN_IND": "0",
                "FND_ID_CD": "U1",
                "FND_VAL_PHA_NBR": 1,
                "LN_PRI_AMT": Decimal("1000"),
                "POL_LN_ITS_AMT": Decimal("25"),
                "LN_CRG_ITS_RT": Decimal("6"),
                "LN_CRE_ITS_RT": Decimal("4"),
                "LN_ITS_AMT_TYP_CD": "2",
            }]
        return []

    @staticmethod
    def data_item(table, field):
        values = {
            ("LH_NON_TRD_POL", "LN_CRE_ITS_RT"): Decimal("4"),
            ("LH_NON_TRD_POL", "PRF_LN_ITS_CRE_RT"): None,
            ("LH_BAS_POL", "LN_TYP_CD"): "5",
        }
        return values.get((table, field))


def test_advanced_loan_summary_uses_canonical_fixed_charge_rate(qtbot):
    tab = LoansTab()
    qtbot.addWidget(tab)

    tab.load_data_from_policy(_AdvancedLoanPolicy())

    assert tab._reg_group.get_value("reg_charge") == "6.00%"
    assert tab.loan_detail_group.table.item(0, 6).text() == "6.00%"


def test_loan_rate_display_preserves_zero(qtbot):
    policy = _AdvancedLoanPolicy()
    policy.fixed_loan_interest_rate = Decimal("0")
    policy.fetch_table = lambda _table: [{
        "MVRY_DT": "9999-12-31",
        "PRF_LN_IND": "0",
        "FND_ID_CD": "U1",
        "FND_VAL_PHA_NBR": 1,
        "LN_PRI_AMT": Decimal("1000"),
        "POL_LN_ITS_AMT": Decimal("25"),
        "LN_CRG_ITS_RT": Decimal("0"),
        "LN_CRE_ITS_RT": Decimal("0"),
        "LN_ITS_AMT_TYP_CD": "2",
    }]
    tab = LoansTab()
    qtbot.addWidget(tab)

    tab.load_data_from_policy(policy)

    assert tab._reg_group.get_value("reg_charge") == "0.00%"
    assert tab.loan_detail_group.table.item(0, 6).text() == "0.00%"
