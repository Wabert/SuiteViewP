"""Nonforfeiture (ETI/RPU) valuation date, RPU/ETI date and age, and the Policy Info header."""

from datetime import date
from types import SimpleNamespace

from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.ui.tabs.coverages_tab import CoveragesTab


def _policy(status, *, advanced=True, mvry="2022-01-07", next_mv="2026-11-07", paid_to="2022-02-07"):
    policy = object.__new__(PolicyInformation)
    bas = {"PRM_PAY_STA_REA_CD": status, "NXT_MVRY_PRC_DT": next_mv, "PRM_PAID_TO_DT": paid_to,
           "NON_TRD_POL_IND": "1" if advanced else "0"}
    cov = {"PRD_LIN_TYP_CD": "I" if advanced else "", "PLN_DES_SER_CD": ""}

    def data_item(table, field, index=0):
        return {"LH_BAS_POL": bas, "LH_COV_PHA": cov,
                "LH_POL_MVRY_VAL": {"MVRY_DT": mvry}}.get(table, {}).get(field)

    policy.data_item = data_item
    base = SimpleNamespace(cov_pha_nbr=1, issue_date=date(1988, 10, 7), issue_age=21)
    policy.coverages.get_coverages = lambda: [base]
    policy.coverages.get_base_coverages = lambda: [base]
    return policy


def test_advanced_rpu_values_at_last_monthliversary_not_the_conversion():
    policy = _policy("45")

    assert policy.values.last_account_value_date == date(2022, 1, 7)
    assert policy.values.valuation_date == date(2026, 10, 7)
    assert policy.activity.policy_year == 39
    assert policy.coverages.attained_age == 59


def test_advanced_eti_values_at_last_monthliversary():
    assert _policy("44").values.valuation_date == date(2026, 10, 7)


def test_premium_paying_advanced_still_values_at_monthly_value_date():
    assert _policy("22", mvry="2026-09-07").values.valuation_date == date(2026, 9, 7)


def test_nonforfeiture_date_and_age():
    rpu = _policy("45")
    assert rpu.status.nonforfeiture_option == "RPU"
    assert rpu.activity.nonforfeiture_date == date(2022, 2, 7)
    assert rpu.coverages.nonforfeiture_age == 54

    eti = _policy("44", advanced=False)
    assert eti.status.nonforfeiture_option == "ETI"
    assert eti.activity.nonforfeiture_date == date(2022, 2, 7)

    paying = _policy("22")
    assert paying.status.nonforfeiture_option == ""
    assert paying.activity.nonforfeiture_date is None
    assert paying.coverages.nonforfeiture_age is None


def _header_policy(option, nf_date=None, nf_age=None):
    return SimpleNamespace(
        status=SimpleNamespace(nonforfeiture_option=option),
        activity=SimpleNamespace(nonforfeiture_date=nf_date),
        coverages=SimpleNamespace(nonforfeiture_age=nf_age),
    )


def test_policy_info_shows_rpu_date_and_age_instead_of_system_and_region(qtbot):
    tab = CoveragesTab()
    qtbot.addWidget(tab)
    labels = [label for _attr, label, _value in tab.info_group.field_entries()]
    assert "System Cd" not in labels and "Region" not in labels
    assert "RPU Date" in labels and "RPU Age" in labels

    tab._populate_nonforfeiture(_header_policy("RPU", date(2022, 2, 7), 54))
    assert tab.info_group.get_value("nf_date_label") == "02/07/2022"
    assert tab.info_group.get_value("nf_age_label") == "54"

    tab._populate_nonforfeiture(_header_policy("ETI", date(2012, 10, 1), 37))
    labels = [label for _attr, label, _value in tab.info_group.field_entries()]
    assert "ETI Date" in labels and "ETI Age" in labels

    tab._populate_nonforfeiture(_header_policy(""))
    labels = [label for _attr, label, _value in tab.info_group.field_entries()]
    assert "RPU Date" in labels
    assert tab.info_group.get_value("nf_date_label") == "N/A"
    assert tab.info_group.get_value("nf_age_label") == "N/A"
