from __future__ import annotations

from suiteview.audit.criteria_specs import (
    DISPLAY_TAB_SPEC,
    POLICY2_TAB_STATE_SPEC,
    POLICY_TAB_STATE_SPEC,
    assert_tab_spec_matches_widgets,
)
from suiteview.audit.cyberlife_criteria import AuditCriteriaBundle, CriteriaCollector
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from tests.cyberlife_sql_cases import ensure_app, make_tabs


def test_specs_match_tab_widgets() -> None:
    ensure_app()
    assert_tab_spec_matches_widgets(DisplayTab(), DISPLAY_TAB_SPEC)
    assert_tab_spec_matches_widgets(PolicyTab(), POLICY_TAB_STATE_SPEC)
    assert_tab_spec_matches_widgets(Policy2Tab(), POLICY2_TAB_STATE_SPEC)


def test_old_saved_state_keys_restore_spec_tabs() -> None:
    ensure_app()
    display = DisplayTab()
    display.set_state({
        "chk_paid_to_date": True,
        "Checkbox_DisplayTradRates": True,
    })
    assert display.get_state()["chk_paid_to_date"] is True
    assert display.get_state()["Checkbox_DisplayTradRates"] is True

    policy = PolicyTab()
    status_text = policy.list_status.item(0).text()
    policy.set_state({
        "txt_plancode": "1U144A00",
        "chk_status_code": True,
        "list_status": [status_text],
    })
    policy_state = policy.get_state()
    assert policy_state["txt_plancode"] == "1U144A00"
    assert policy_state["chk_status_code"] is True
    assert policy_state["list_status"] == [status_text]

    policy2 = Policy2Tab()
    loan_text = policy2.list_loan_type.item(0).text()
    policy2.set_state({
        "chk_loan_type": True,
        "list_loan_type": [loan_text],
        "txt_total_loan_prin_lo": "100",
    })
    policy2_state = policy2.get_state()
    assert policy2_state["chk_loan_type"] is True
    assert policy2_state["list_loan_type"] == [loan_text]
    assert policy2_state["txt_total_loan_prin_lo"] == "100"


def test_criteria_collector_reads_registered_tabs() -> None:
    tabs = make_tabs()
    tabs["policy_tab"].txt_plancode.setText("1U144A00")
    tabs["display_tab"].chk_paid_to_date.setChecked(True)
    criteria = CriteriaCollector(AuditCriteriaBundle(
        schema="DB2TAB",
        sys_code="I",
        max_count_text="25",
        tabs={
            "policy": tabs["policy_tab"],
            "display": tabs["display_tab"],
            "policy2": tabs["policy2_tab"],
            "adv": tabs["adv_tab"],
            "coverages": tabs["coverages_tab"],
            "plancode": tabs["plancode_tab"],
            "benefits": tabs["benefits_tab"],
            "transaction": tabs["transaction_tab"],
            "custom_display": tabs["custom_display_tab"],
            "people": tabs["people_tab"],
            "segment52": tabs["segment52_tab"],
            "wl": tabs["wl_tab"],
        },
    )).collect()
    assert criteria.policy.txt_plancode.text() == "1U144A00"
    assert criteria.display.chk_paid_to_date.isChecked() is True
