"""Shared characterization cases for the CyberLife audit SQL builder."""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QCheckBox

from suiteview.audit.db2_table_fields import TABLE_FIELDS
from suiteview.audit.tabs.adv_tab import AdvTab
from suiteview.audit.tabs.benefits_tab import BenefitsTab
from suiteview.audit.tabs.coverages_tab import CoveragesTab
from suiteview.audit.tabs.custom_display_tab import CustomDisplayTab
from suiteview.audit.tabs.display_tab import DisplayTab
from suiteview.audit.tabs.people_tab import PeopleTab
from suiteview.audit.tabs.plancode_tab import PlancodeTab
from suiteview.audit.tabs.policy2_tab import Policy2Tab
from suiteview.audit.tabs.policy_tab import PolicyTab
from suiteview.audit.tabs.segment52_tab import Segment52Tab
from suiteview.audit.tabs.transaction_tab import TransactionTab
from suiteview.audit.tabs.wl_tab import WlTab

_QT_APP = None


@dataclass(frozen=True)
class CyberlifeSqlCase:
    name: str
    schema: str = "DB2TAB"
    sys_code: str = "I"
    max_count_text: str = "25"
    coverage_level: bool = False
    coverage_scope: str = "All Covs"
    configure: Callable[[dict[str, object]], None] = lambda _tabs: None


def ensure_app() -> QApplication:
    global _QT_APP
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _QT_APP = app
    return app


def make_tabs() -> dict[str, object]:
    ensure_app()
    return {
        "policy_tab": PolicyTab(),
        "display_tab": DisplayTab(),
        "policy2_tab": Policy2Tab(),
        "adv_tab": AdvTab(),
        "coverages_tab": CoveragesTab(),
        "plancode_tab": PlancodeTab(),
        "benefits_tab": BenefitsTab(),
        "transaction_tab": TransactionTab(),
        "custom_display_tab": CustomDisplayTab(),
        "people_tab": PeopleTab(),
        "segment52_tab": Segment52Tab(),
        "wl_tab": WlTab(),
    }


def _select_first(listbox) -> None:
    if listbox.count():
        listbox.item(0).setSelected(True)


def _policy_ranges(tabs: dict[str, object]) -> None:
    policy = tabs["policy_tab"]
    policy.txt_current_age_lo.setText("35")
    policy.txt_current_age_hi.setText("75")
    policy.txt_issue_month_lo.setText("1")
    policy.txt_issue_month_hi.setText("6")
    policy.txt_paid_to_lo.setText("01/01/2026")
    policy.chk_grace_indicator.setChecked(True)
    _select_first(policy.list_grace_indicator)


def _display_all(tabs: dict[str, object]) -> None:
    display = tabs["display_tab"]
    for checkbox in display.findChildren(QCheckBox):
        checkbox.setChecked(True)


def _policy2_loans_conversion(tabs: dict[str, object]) -> None:
    policy2 = tabs["policy2_tab"]
    policy2.chk_has_loan.setChecked(True)
    policy2.chk_has_preferred_loan.setChecked(True)
    policy2.txt_total_loan_prin_lo.setText("1")
    policy2.txt_total_accured_lint_hi.setText("8")
    policy2.chk_has_converted.setChecked(True)
    policy2.txt_term_date_both_lo.setText("2025-01-01")


def _advanced_ranges(tabs: dict[str, object]) -> None:
    adv = tabs["adv_tab"]
    adv.chk_cv_corr.setChecked(True)
    adv.chk_accum_gt_prem.setChecked(True)
    adv.rng_glp[0].setText("0")
    adv.rng_gsp[1].setText("500")


def _coverage_filters(tabs: dict[str, object]) -> None:
    coverages = tabs["coverages_tab"]
    coverages.txt_spec_amt_lo.setText("1000")
    coverages.base_cov_widgets["issue_date_lo"].setText("01/01/2020")
    coverages.base_cov_widgets["vpu_hi"].setText("1000")
    coverages.base_cov_widgets["prod_ind"].setCurrentIndex(1)


def _plan_policy_filters(tabs: dict[str, object]) -> None:
    plan = tabs["plancode_tab"]
    plan.set_state({
        "plancodes": ["1U144A00", "PLAN001"],
        "policies": ["U0123456", "000289393"],
        "cov1_plancode_match_only": False,
    })


def _benefit_filters(tabs: dict[str, object]) -> None:
    benefits = tabs["benefits_tab"]
    benefits.benefit_combos[0].setCurrentIndex(1)
    benefits.subtype_edits[0].setText("A")
    benefits.post_issue_chks[0].setChecked(True)
    benefits.cease_lo_edits[0].setText("01/01/2025")


def _linked_transactions(tabs: dict[str, object]) -> None:
    transaction = tabs["transaction_tab"]
    transaction.transaction1.transaction_types.setText("PR")
    transaction.transaction2.transaction_types.setText("CD")
    transaction.transaction2.date_comparisons["entry"].setCurrentText(
        "After Trans1 Eff Date")
    transaction.transaction2.ranges["gross"][0].setText("0")


def _custom_display(tabs: dict[str, object]) -> None:
    custom = tabs["custom_display_tab"]
    row = custom.rows[0]
    row.chk_enable.setChecked(True)
    row._selected = {"LH_BAS_POL": {"APP_WRT_DT"}}
    row.combo_criteria.setCurrentText("Contains")
    row.txt_criteria.setText("abc")
    row2 = custom.rows[1]
    row2.chk_enable.setChecked(True)
    th_field = TABLE_FIELDS["TH_COV_PHA"][0][0]
    row2._selected = {"TH_COV_PHA": {th_field}}


def _people_names(tabs: dict[str, object]) -> None:
    people = tabs["people_tab"]
    people.cmb_first_name_match.setCurrentText("Begins with")
    people.txt_first_name.setText("Ann")
    people.cmb_last_name_match.setCurrentText("Contains")
    people.txt_last_name.setText("O'Brien")


def _segment52(tabs: dict[str, object]) -> None:
    segment = tabs["segment52_tab"]
    first = next(iter(segment.display_fields))
    segment.display_fields[first].setChecked(True)
    text_name = next(iter(segment.text_inputs))
    segment.match_types[text_name].setCurrentText("Ends with")
    segment.text_inputs[text_name].setText("TERM")


def _whole_life(tabs: dict[str, object]) -> None:
    wl = tabs["wl_tab"]
    wl._select_par()
    wl.chk_cv_rate.setChecked(True)
    wl.chk_pri_div.setChecked(True)
    _select_first(wl.list_pri_div)


CASES = [
    CyberlifeSqlCase("baseline"),
    CyberlifeSqlCase("policy_ranges_unit", schema="UNIT", configure=_policy_ranges),
    CyberlifeSqlCase("display_all", configure=_display_all),
    CyberlifeSqlCase("policy2_loans_conversion", configure=_policy2_loans_conversion),
    CyberlifeSqlCase("advanced_ranges", configure=_advanced_ranges),
    CyberlifeSqlCase("coverage_filters", coverage_level=True, configure=_coverage_filters),
    CyberlifeSqlCase("coverage_scope_riders", coverage_level=True,
                     coverage_scope="Covs 2+ only", configure=_plan_policy_filters),
    CyberlifeSqlCase("plans_and_policies", configure=_plan_policy_filters),
    CyberlifeSqlCase("benefits", configure=_benefit_filters),
    CyberlifeSqlCase("linked_transactions", configure=_linked_transactions),
    CyberlifeSqlCase("custom_display", coverage_level=True, configure=_custom_display),
    CyberlifeSqlCase("people_names", configure=_people_names),
    CyberlifeSqlCase("segment52", configure=_segment52),
    CyberlifeSqlCase("whole_life", configure=_whole_life),
]
