"""RERUN Reinstatement tab: status 97/99 UL policies start from the reinstatement quote."""
import os
from datetime import date
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import suiteview.illustration.ui.main_window as mw
from suiteview.illustration.core.business_mode import BUSINESS_MODE_ENV
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab
from suiteview.illustration.ui.main_window import IllustrationWindow
from suiteview.polview.services import reinstatement as rein
from suiteview.polview.ui.tabs import reinstatement_tab

YEARS = 40
ISSUE = date(2015, 3, 15)
LAPSE = date(2026, 3, 15)
TODAY = date(2026, 10, 7)
_QT_APP = None


def lapse_basis(**changes):
    values = dict(
        policy_number="SYNTHETIC", plancode="1U135D00", product_type="UL",
        premium_pay_status_code="99", issue_date=ISSUE, valuation_date=date(2026, 2, 15),
        issue_age=40, attained_age=50, policy_year=11, policy_month=12, duration=132,
        maturity_age=121, face_amount=100000.0, units=100.0, account_value=-25.0,
        premiums_paid_to_date=12000.0, ctp=1200.0, map_cease_date=date(2030, 3, 15),
        segments=[CoverageSegment(
            issue_date=ISSUE, issue_age=40, face_amount=100000.0,
            original_face_amount=100000.0, units=100.0, rate_sex="M", rate_class="N")],
    )
    values.update(changes)
    rates = IllustrationRates(
        segment_coi={1: [None] + [0.12] * YEARS},
        segment_epu={1: [None] + [0.05] * YEARS},
        segment_scr={1: [None] + [10.0 - 0.5 * year for year in range(YEARS)]},
        mfee=[None] + [7.5] * YEARS,
        tpp=[None] + [0.05] * YEARS,
        epp=[None] + [0.05] * YEARS,
    )
    return rein.build_reinstatement_basis(
        IllustrationPolicyData(**values), PlancodeConfig(plancode="SYNTHETIC"), rates,
        eligibility=rein.ReinstatementEligibility("Q", "Termination - Lapse", True, "Eligible"),
        lapse_date=LAPSE, today=TODAY)


def live_policy(status="99", last_entry="Q"):
    return SimpleNamespace(
        exists=True, product_type="UL", last_entry_code=last_entry, policy_number="SYNTHETIC",
        company_code="01", region="CKPR", premium_pay_status_code=status,
        get_live_transactions=lambda _codes: [], terminate_date=None)


@pytest.fixture
def window(monkeypatch):
    global _QT_APP
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    _QT_APP = QApplication.instance() or QApplication([])
    monkeypatch.setattr(reinstatement_tab, "load_reinstatement_basis",
                        lambda *_a, **_k: lapse_basis())
    win = IllustrationWindow()
    # The live Policy tab render needs a real PolicyInformation; not under test here.
    monkeypatch.setattr(win, "_refresh_policy_basis", lambda: None)
    win._policy = live_policy()
    win._policy_info = {"PolicyNumber": "SYNTHETIC", "CompanyCode": "01", "Region": "CKPR"}
    win._illustration_data = lapse_basis().policy
    return win


def load(win):
    win._load_reinstatement()
    inputs = IllustrationInputsTab()
    win._set_active_inputs_tab(inputs)
    inputs.load_data_from_policy(win._illustration_data)
    win._apply_reinstatement_inputs()
    return inputs


def test_status_99_adds_the_reinstatement_tab_beside_policy(window):
    load(window)
    index = window.tabs.indexOf(window.reinstatement_tab)
    assert window.tabs.tabText(index) == "Reinstatement"
    assert index == window.tabs.indexOf(window.policy_tab) + 1


@pytest.mark.parametrize("status", ["22", "54", "98"])
def test_other_statuses_get_no_reinstatement_tab(window, status):
    window._policy = live_policy(status=status)
    lapsed = window._illustration_data
    load(window)
    assert window.reinstatement_tab is None or window.tabs.indexOf(window.reinstatement_tab) == -1
    assert window._illustration_data is lapsed
    assert window.inputs_tab.reinstatement_note() == ""


def test_illustration_starts_on_the_reinstatement_date_with_the_premium_as_lumpsum(window):
    inputs = load(window)
    quote = window.reinstatement_tab.quote
    start = window._reinstatement_start
    assert quote.reinstatement_date == date(2026, 9, 15)
    assert window._illustration_data is start.policy
    assert start.policy.valuation_date == quote.reinstatement_date
    assert start.policy.account_value == pytest.approx(-25.0 - float(quote.deduction.total))
    assert inputs.valuation_banner is not None
    assert inputs.banner_valuation_label.text() == "9/15/2026"
    assert inputs.banner_first_forecast_label.text() == "10/15/2026"
    assert inputs.dynamic_panel.lumpsum_edit.value() == pytest.approx(float(quote.premium.premium))
    note = inputs.dynamic_panel.lumpsum_note
    assert not note.isHidden()
    assert note.text() == "This is the Premium needed to reinstate on 9/15/2026"
    assert "bold" in note.styleSheet() and "#B00020" in note.styleSheet()
    assert "REINSTATEMENT" in window.projection_mode_notice.text()


def test_run_uses_the_reinstated_basis_not_a_fresh_reload(window):
    load(window)
    request = window._read_run_request()
    assert request.basis.policy_data is window._reinstatement_start.policy
    lumpsums = [t for t in request.inputs.dated_transactions if t.subtype == "manual_lumpsum"]
    assert [t.effective_date for t in lumpsums] == [date(2026, 10, 15)]


def test_choosing_another_reinstatement_date_reseats_the_illustration(window):
    inputs = load(window)
    combo = window.reinstatement_tab.date_edit
    combo.setCurrentIndex(combo.findText("08/15/2026"))
    quote = window.reinstatement_tab.quote
    assert quote.reinstatement_date == date(2026, 8, 15)
    assert window._illustration_data.valuation_date == date(2026, 8, 15)
    assert inputs.banner_valuation_label.text() == "8/15/2026"
    assert inputs.dynamic_panel.lumpsum_edit.value() == pytest.approx(float(quote.premium.premium))
    assert inputs.reinstatement_note().endswith("8/15/2026")


def test_unreinstatable_policy_keeps_the_lapse_basis_and_warns(window, monkeypatch):
    window._policy = live_policy(last_entry="X")
    lapsed = window._illustration_data
    inputs = load(window)
    assert window.tabs.indexOf(window.reinstatement_tab) != -1
    assert window._reinstatement_start is None
    assert window._illustration_data is lapsed
    assert "Reinstatement illustration unavailable" in window._reinstatement_warning
    assert inputs.dynamic_panel.lumpsum_note.isHidden()
    _blocks, warnings = window._load_problem_gate()
    assert any("Reinstatement illustration unavailable" in w for w in warnings)


def test_new_business_hides_the_reinstatement_note(window):
    inputs = load(window)
    inputs.run_from_issue_btn.setChecked(True)
    assert inputs.dynamic_panel.lumpsum_note.isHidden()


def test_loading_another_policy_removes_the_tab(window):
    load(window)
    window._clear_reinstatement()
    assert window.tabs.indexOf(window.reinstatement_tab) == -1
    assert window._reinstatement_start is None
