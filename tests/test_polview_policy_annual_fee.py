from decimal import Decimal

from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.ui.tabs.policy_tab import PolicyTab


def test_annual_policy_fee_reads_traditional_fixed_premium_policy():
    policy = object.__new__(PolicyInformation)
    calls = []

    def data_item(table, field, *_args):
        calls.append((table, field))
        values = {
            ("LH_BAS_POL", "NON_TRD_POL_IND"): "0",
            ("LH_FXD_PRM_POL", "POL_FEE_AMT"): "7.50",
        }
        return values.get((table, field))

    policy.data_item = data_item

    assert policy.billing.annual_policy_fee == Decimal("7.50")
    assert calls == [
        ("LH_BAS_POL", "NON_TRD_POL_IND"),
        ("LH_FXD_PRM_POL", "POL_FEE_AMT"),
    ]


def test_annual_policy_fee_skips_traditional_table_for_advanced_product():
    policy = object.__new__(PolicyInformation)
    calls = []

    def data_item(table, field, *_args):
        calls.append((table, field))
        return "1"

    policy.data_item = data_item

    assert policy.billing.annual_policy_fee is None
    assert calls == [("LH_BAS_POL", "NON_TRD_POL_IND")]


def test_policy_tab_displays_formatted_traditional_annual_fee(qtbot):
    class FakePolicy:
        company_code = "01"
        annual_policy_fee = Decimal("7.5")

        @staticmethod
        def data_item(*_args):
            return None

    tab = PolicyTab()
    qtbot.addWidget(tab)

    tab._populate_column3_from_policy(FakePolicy(), {})

    assert tab.col3.get_value("annual_fee") == "$7.50"
