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