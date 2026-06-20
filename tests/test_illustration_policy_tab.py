import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.ui.main_window import IllustrationWindow
from suiteview.illustration.ui.policy_tab import IllustrationPolicyTab


_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_policy_tab_rate_warning_is_distinct_and_above_policy_info():
    _app()
    tab = IllustrationPolicyTab()

    assert tab.rate_warning_label.isHidden()

    tab.set_rate_warnings(["Missing illustration rates for active rider/benefit charges: Benefit 39"])

    assert not tab.rate_warning_label.isHidden()
    assert "font-weight: bold" in tab.rate_warning_label.styleSheet()
    assert "#FFF0B3" in tab.rate_warning_label.styleSheet()
    content_layout = tab.rate_warning_label.parentWidget().layout()
    assert content_layout.indexOf(tab.rate_warning_label) < content_layout.indexOf(tab.policy_info)


def test_policy_tab_monthly_deduction_fields_are_under_insured_dob():
    _app()
    tab = IllustrationPolicyTab()

    def position(attr_name: str):
        layout = tab.policy_info._info_layout
        widget = tab.policy_info._labels[attr_name]
        row, column, _, _ = layout.getItemPosition(layout.indexOf(widget))
        return row, column

    insured_row, insured_col = position("insured_dob")
    cyberlife_row, cyberlife_col = position("cyberlife_md")
    calculated_row, calculated_col = position("calculated_md")

    assert cyberlife_col == insured_col
    assert calculated_col == insured_col
    assert cyberlife_row == insured_row + 2
    assert calculated_row == insured_row + 3


def test_policy_tab_sets_monthly_deduction_values_from_check():
    _app()
    tab = IllustrationPolicyTab()

    tab.set_monthly_deduction_check(SimpleNamespace(
        system_monthly_deduction=123.45,
        md_check_calculated_deduction=123.46,
    ))

    assert tab.policy_info.get_value("cyberlife_md") == "$123.45"
    assert tab.policy_info.get_value("calculated_md") == "$123.46"


def test_monthly_deduction_warning_only_when_cent_values_differ():
    equal_check = SimpleNamespace(
        system_monthly_deduction=123.451,
        md_check_calculated_deduction=123.454,
    )
    mismatch_check = SimpleNamespace(
        system_monthly_deduction=123.45,
        md_check_calculated_deduction=123.46,
    )

    assert IllustrationWindow._monthly_deduction_warnings(equal_check) == []
    warnings = IllustrationWindow._monthly_deduction_warnings(mismatch_check)

    assert len(warnings) == 1
    assert "Monthly deduction check mismatch" in warnings[0]
    assert "CyberLife MD $123.45" in warnings[0]
    assert "Calculated MD $123.46" in warnings[0]


def test_blank_definition_of_life_warning_uses_policy_warning_area():
    warnings = IllustrationWindow._definition_of_life_warnings(SimpleNamespace(
        has_defined_life_insurance=False,
    ))

    assert warnings == [
        "Definition of Life Insurance is not defined for this policy. "
        "Check the issue date and issue state to confirm if this looks accurate."
    ]

    _app()
    tab = IllustrationPolicyTab()
    tab.set_rate_warnings(warnings)

    assert not tab.rate_warning_label.isHidden()
    assert warnings[0] in tab.rate_warning_label.text()


def test_defined_life_insurance_has_no_definition_warning():
    assert IllustrationWindow._definition_of_life_warnings(SimpleNamespace(
        has_defined_life_insurance=True,
    )) == []


def test_fund_values_split_into_unimpaired_and_impaired_tables():
    _app()
    tab = IllustrationPolicyTab()

    for table in (tab.unimpaired_table, tab.impaired_table):
        assert table.columnCount() == 2
        headers = [table._data_table.horizontalHeaderItem(c).text() for c in range(2)]
        assert headers == ["Fund ID", "Fund Value"]
        # Both tables live inside the single Fund Values group (not separate groups).
        assert tab.fund_values.isAncestorOf(table)


def test_fund_tables_reconcile_to_account_value():
    _app()
    tab = IllustrationPolicyTab()

    from decimal import Decimal

    class FundPolicy:
        exists = True
        policy_number = "U0000001"
        company_code = "01"
        system_code = "I"
        region = "CKPR"

        def get_coverages(self):
            return []

        def get_benefits(self):
            return []

        def get_fund_values_dict(self):
            return {"01": Decimal("800.00"), "LZ": Decimal("0.00")}

        def get_loan_values_dict(self):
            return {"01": Decimal("200.00")}

    tab._policy = FundPolicy()
    tab._coverages = []
    tab._populate_fund_values(tab._policy)

    # Unimpaired drops the zero bucket; impaired shows the loan-collateralized part.
    assert tab.unimpaired_table.rowCount() == 1
    assert tab.impaired_table.rowCount() == 1
    # 800 (free) + 200 (impaired) reconciles to the account value.
    assert tab.unimpaired_table.item(0, 1).text() == "$800.00"
    assert tab.impaired_table.item(0, 1).text() == "$200.00"


def test_7pay_start_date_is_directly_under_cost_basis():
    _app()
    tab = IllustrationPolicyTab()

    def position(attr_name: str):
        layout = tab.tax_values._info_layout
        widget = tab.tax_values._labels[attr_name]
        row, column, _, _ = layout.getItemPosition(layout.indexOf(widget))
        return row, column

    cost_row, cost_col = position("cost_basis")
    start_row, start_col = position("seven_pay_start_date")

    assert start_col == cost_col
    assert start_row == cost_row + 1