"""Load-time problems surface where the user acts (should-do 4, M6 second half).

Missing illustration rates block Run for business users (developers get a
warning); a monthly-deduction mismatch over $0.01 is a prominent banner on the
Inputs tab and in the run notice, and never blocks.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import suiteview.illustration.ui.main_window as mw
from suiteview.illustration.core.business_mode import BUSINESS_MODE_ENV
from suiteview.illustration.core.run_gates import monthly_deduction_mismatch_notice
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab
from suiteview.illustration.ui.main_window import IllustrationWindow

_QT_APP = None
_MISSING = ("Missing illustration rates for active rider/benefit charges: "
            "Rider 06582004, Rider 06582016")


def _window(monkeypatch, business: bool) -> IllustrationWindow:
    global _QT_APP
    if business:
        monkeypatch.setenv(BUSINESS_MODE_ENV, "1")
    else:
        monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    _QT_APP = QApplication.instance() or QApplication([])
    return IllustrationWindow()


def _md(calculated: float, cyberlife: float = 100.0):
    return SimpleNamespace(system_monthly_deduction=cyberlife,
                           md_check_calculated_deduction=calculated)


@pytest.mark.parametrize("calculated, shown", [
    (100.00, False), (100.01, False), (99.99, False), (100.02, True), (99.5, True),
])
def test_md_mismatch_threshold_is_one_cent(calculated, shown):
    notice = monthly_deduction_mismatch_notice(_md(calculated))
    assert bool(notice) is shown
    if shown:
        assert notice.startswith("MONTHLY DEDUCTION CHECK:")
        assert f"${calculated:,.2f}" in notice and "$100.00" in notice


def _phase1_policy():
    return SimpleNamespace(plancode="1U143900", premium_pay_status_code="22",
                           suspense_code="0")


def test_business_missing_rates_block_run(monkeypatch):
    win = _window(monkeypatch, True)
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _phase1_policy()
    win._load_rate_problems = (_MISSING,)
    assert win._apply_illustration_gate() is True
    assert not win.run_values_btn.isEnabled()
    assert "can't be illustrated in this release: illustration rates are missing" in (
        win.run_notice.text())
    assert "Rider 06582004" in win._status_label.text()


def test_business_unloadable_illustration_data_blocks_run(monkeypatch):
    win = _window(monkeypatch, True)
    win.run_values_btn.setEnabled(True)
    win._illustration_data = None
    win._load_rate_problems = ("Unable to load illustration data/rates: no COI table",)
    assert win._apply_illustration_gate() is True
    assert not win.run_values_btn.isEnabled()


def test_developer_missing_rates_warn_only(monkeypatch):
    win = _window(monkeypatch, False)
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _phase1_policy()
    win._load_rate_problems = (_MISSING,)
    assert win._apply_illustration_gate() is False
    assert win.run_values_btn.isEnabled()
    assert "Business users are blocked" in win.run_notice.text()


@pytest.mark.parametrize("business", [True, False])
def test_md_mismatch_warns_without_blocking(monkeypatch, business):
    win = _window(monkeypatch, business)
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _phase1_policy()
    win._load_md_warning = monthly_deduction_mismatch_notice(_md(101.25))
    assert win._apply_illustration_gate() is False
    assert win.run_values_btn.isEnabled()
    assert "MONTHLY DEDUCTION CHECK" in win.run_notice.text()
    assert "#D4A017" in win.run_notice.styleSheet()          # amber, not the red block


def test_saved_case_snapshot_checks_its_own_rates_in_business(monkeypatch):
    # No live load checks run for a snapshot: stale live findings are dropped and
    # the snapshot's own rates are checked, with the same refusal text.
    from suiteview.illustration.core.run_gates import missing_rates_block

    win = _window(monkeypatch, True)
    snapshot = _phase1_policy()
    checked = []
    monkeypatch.setattr(mw, "missing_rate_findings",
                        lambda policy: checked.append(policy) or (_MISSING,))
    win._load_md_warning = "stale live MD warning"
    win._snapshot_case = SimpleNamespace(name="case")
    win._snapshot_load_problems(snapshot)
    win._illustration_data = snapshot
    win.run_values_btn.setEnabled(True)
    assert checked == [snapshot]
    assert win._apply_illustration_gate() is True
    assert not win.run_values_btn.isEnabled()
    assert win.run_notice.text() == missing_rates_block((_MISSING,))
    assert "stale live MD warning" not in win.run_notice.text()


def test_saved_case_snapshot_with_rates_runs_in_business(monkeypatch):
    win = _window(monkeypatch, True)
    monkeypatch.setattr(mw, "missing_rate_findings", lambda policy: ())
    win._load_rate_problems = (_MISSING,)            # stale finding from a live load
    win._snapshot_case = SimpleNamespace(name="case")
    win._snapshot_load_problems(_phase1_policy())
    win._illustration_data = _phase1_policy()
    win.run_values_btn.setEnabled(True)
    assert win._apply_illustration_gate() is False
    assert win.run_values_btn.isEnabled()


def test_developer_saved_case_snapshot_skips_the_rate_load(monkeypatch):
    win = _window(monkeypatch, False)

    def never(policy):
        raise AssertionError("developers keep the load-time warning only")

    monkeypatch.setattr(mw, "missing_rate_findings", never)
    win._load_rate_problems = (_MISSING,)
    win._snapshot_case = SimpleNamespace(name="case")
    win._snapshot_load_problems(_phase1_policy())
    win._illustration_data = _phase1_policy()
    win.run_values_btn.setEnabled(True)
    assert win._apply_illustration_gate() is False


def test_load_checks_record_missing_rates_and_md_mismatch(monkeypatch):
    win = _window(monkeypatch, True)
    policy_data = SimpleNamespace(plancode="1U143900", has_defined_life_insurance=True)
    monkeypatch.setattr(mw, "coverage_segment_data_warnings", lambda policy: [])
    monkeypatch.setattr(mw, "load_policy_data", lambda *a, **k: policy_data)
    monkeypatch.setattr(mw, "load_plancode", lambda plancode: SimpleNamespace())
    monkeypatch.setattr(mw, "load_rates", lambda policy, config: SimpleNamespace())
    monkeypatch.setattr(mw, "missing_required_rate_warnings", lambda policy, rates: [_MISSING])
    monkeypatch.setattr(mw, "benefit_rate_override_warnings", lambda rates: [])
    monkeypatch.setattr(mw, "plan_basis_warnings", lambda config, policy: [])
    monkeypatch.setattr(mw, "project_policy", lambda *a, **k: SimpleNamespace(
        states=[_md(103.0)]))
    warnings, md_check = win._policy_load_checks("UL000001", "CKPR", "01")
    assert _MISSING in warnings
    assert win._load_rate_problems == (_MISSING,)
    assert "difference $3.00" in win._load_md_warning
    assert md_check.md_check_calculated_deduction == 103.0


def test_inputs_tab_load_warning_banner():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    tab = IllustrationInputsTab()
    assert tab.load_warning_banner.isHidden()
    assert tab.load_warning_banner.styleSheet() == ""
    tab.set_load_warning("MONTHLY DEDUCTION CHECK: test")
    assert not tab.load_warning_banner.isHidden()
    assert tab.load_warning_banner.text() == "MONTHLY DEDUCTION CHECK: test"
    tab.set_load_warning(None)
    assert tab.load_warning_banner.isHidden()
