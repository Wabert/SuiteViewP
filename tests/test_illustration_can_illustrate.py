"""Which plancodes a RERUN user may illustrate: ``dbo.SV_RERUN_Plancode_Control``.

The control table lists every in-force base plancode with its product type and
``CanIllustrate`` (UL on, everything else off, as loaded 10/8/2026). Every user without
the ``RERUNANYPLAN`` permission is held to it, in any build; ADMIN (AllApps), SUPPORT
(granted) and source runs hold the permission. ``SUITEVIEW_ILLUSTRATION_BUSINESS_MODE=1``
takes it away so developers can test the business scope. The table rows come from the
UL_Rates replay (tests/golden/ul_rates_replay.json).
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import suiteview.illustration.core.compare_runner as compare_runner
import suiteview.illustration.core.plancode_control as control
import suiteview.illustration.ui.main_window as mw
from suiteview.core import access_control
from suiteview.illustration.core.business_mode import BUSINESS_MODE_ENV
from suiteview.illustration.core.run_gates import plancode_refusal, policy_gate
from suiteview.illustration.models.index_strategies import is_iul_plan
from suiteview.illustration.models.rerun_plancode_tables import PRODUCT_TYPES, PlancodeTableError
from suiteview.illustration.ui.main_window import IllustrationWindow

_QT_APP = None

_IUL_PLANCODE = "1U144600"      # IUL08 - CanIllustrate off
_ALLOWED_PLANCODE = "1U143900"  # EXECUL (UL) - CanIllustrate on
_ISWL_PLANCODE = "B11SB200"     # ISWL - off
_PARWL_PLANCODE = "AB1S4700"    # participating whole life - off
_TERM_PLANCODE = "B15TA100"     # indeterminate premium term - off
_NOT_IN_FORCE = "1U145000"      # an Adv-table UL plancode with no in-force policy


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


@pytest.fixture(autouse=True)
def _fresh_control_cache():
    control.clear_control_cache()
    yield
    control.clear_control_cache()


# -- the shipped control table --------------------------------------------------


def test_control_table_enables_exactly_the_in_force_ul_plancodes():
    rows = control.control_rows()
    assert len(rows) > 2000
    assert {row.product_type for row in rows.values()} <= set(PRODUCT_TYPES)
    enabled = {code for code, row in rows.items() if row.can_illustrate}
    assert enabled == {code for code, row in rows.items() if row.product_type == "UL"}
    assert len(enabled) == 156
    assert _ALLOWED_PLANCODE in enabled
    assert rows[_IUL_PLANCODE].product_type == "IUL" and is_iul_plan(_IUL_PLANCODE)
    assert rows[_ISWL_PLANCODE].product_type == "ISWL"
    assert rows[_PARWL_PLANCODE].product_type == "ParWL"
    assert rows[_TERM_PLANCODE].product_type == "Term"
    assert _NOT_IN_FORCE not in rows


def test_refusal_messages():
    assert plancode_refusal(_ALLOWED_PLANCODE, any_plancode=False) is None
    assert plancode_refusal(_IUL_PLANCODE, any_plancode=False) == (
        f"Plancode {_IUL_PLANCODE} (IUL) is not enabled for in-force illustration in this release.")
    assert plancode_refusal(_NOT_IN_FORCE, any_plancode=False) == (
        f"Plancode {_NOT_IN_FORCE} is not set up for illustration (it is not in RERUN's "
        "plancode control table).")
    assert plancode_refusal(_IUL_PLANCODE, any_plancode=True) is None


def test_unreadable_control_table_fails_closed(monkeypatch):
    def boom():
        raise PlancodeTableError("UL_Rates is down")
    monkeypatch.setattr(control, "read_control_rows", boom)
    reason = plancode_refusal(_ALLOWED_PLANCODE, any_plancode=False)
    assert reason.startswith("RERUN could not read its plancode control table")
    assert "UL_Rates is down" in reason
    assert plancode_refusal(_ALLOWED_PLANCODE, any_plancode=True) is None


# -- the RERUNANYPLAN permission ------------------------------------------------


def _access(role, apps=(), all_apps=False):
    return access_control.EffectiveAccess("USER1", role, all_apps, False, True, frozenset(apps))


@pytest.mark.parametrize("access, allowed", [
    (_access("ADMIN", all_apps=True), True),
    (_access("SUPPORT", ("RERUN", "RERUNANYPLAN")), True),
    (_access("SUPPORT", ("RERUN",)), False),
    (_access("BUSINESS", ("RERUN",)), False),
    (_access("BUSINESS", ("RERUN", "RERUNANYPLAN")), True),
])
def test_permission_follows_the_role_grant(monkeypatch, access, allowed):
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    monkeypatch.setattr(access_control, "get_access", lambda refresh=False: access)
    assert "RERUNANYPLAN" in access_control.APP_CODES
    assert control.can_illustrate_any_plancode() is allowed


def test_source_runs_hold_the_permission_unless_business_mode_is_forced(monkeypatch):
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    assert control.can_illustrate_any_plancode() is True
    monkeypatch.setenv(BUSINESS_MODE_ENV, "1")
    assert control.can_illustrate_any_plancode() is False


def test_unverifiable_permission_applies_the_table(monkeypatch):
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)

    def fail(refresh=False):
        raise access_control.AccessUnavailableError("no network")
    monkeypatch.setattr(access_control, "get_access", fail)
    assert control.can_illustrate_any_plancode() is False


def _policy(plancode: str, status: str = "22"):
    return SimpleNamespace(plancode=plancode, premium_pay_status_code=status, suspense_code="0")


def test_support_without_the_grant_is_held_to_the_table_outside_business_mode():
    gate = policy_gate(_policy(_IUL_PLANCODE), business_mode=False, any_plancode=False)
    assert gate.blocks == (
        f"Plancode {_IUL_PLANCODE} (IUL) is not enabled for in-force illustration in this release.",)
    assert not policy_gate(_policy(_IUL_PLANCODE), business_mode=False, any_plancode=True).blocked


def test_compare_applies_the_plancode_gate_outside_business_mode(monkeypatch):
    monkeypatch.setattr(compare_runner, "is_business_mode", lambda: False)
    monkeypatch.setattr(control, "can_illustrate_any_plancode", lambda: False)
    spec = SimpleNamespace(scenario=SimpleNamespace(base_policy=_policy(_IUL_PLANCODE)))
    with pytest.raises(compare_runner.CompareScenarioError, match="IUL"):
        compare_runner._check_scenario_gates(spec)
    spec.scenario.base_policy = _policy(_ALLOWED_PLANCODE)
    compare_runner._check_scenario_gates(spec)


# -- the window -----------------------------------------------------------------


def _window():
    _app()
    return IllustrationWindow()


def test_source_run_illustrates_a_disabled_plancode(monkeypatch):
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    win = _window()
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _policy(_IUL_PLANCODE)
    assert win._apply_illustration_gate() is False
    assert win.run_values_btn.isEnabled() is True


@pytest.fixture
def business_window(monkeypatch):
    monkeypatch.setenv(BUSINESS_MODE_ENV, "1")
    return _window()


@pytest.mark.parametrize("plancode, product", [
    (_IUL_PLANCODE, "IUL"), (_ISWL_PLANCODE, "ISWL"),
])
def test_business_gate_blocks_disabled_plancodes(business_window, plancode, product):
    win = business_window
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _policy(plancode)
    assert win._apply_illustration_gate() is True
    assert win.run_values_btn.isEnabled() is False
    message = (f"Plancode {plancode} ({product}) is not enabled for in-force illustration "
               "in this release.")
    assert win._status_label.text() == message
    assert not win.run_notice.isHidden()
    assert message in win.run_notice.text()


def test_business_gate_blocks_a_plancode_missing_from_the_table(business_window):
    win = business_window
    win._illustration_data = _policy(_NOT_IN_FORCE)
    assert win._apply_illustration_gate() is True
    assert "not set up for illustration" in win._status_label.text()


def test_business_gate_allows_an_enabled_plancode(business_window):
    win = business_window
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _policy(_ALLOWED_PLANCODE)
    assert win._apply_illustration_gate() is False
    assert win.run_values_btn.isEnabled() is True
    assert win.run_notice.isHidden()


def test_an_administrators_edit_takes_effect_on_the_next_get(business_window, monkeypatch):
    win = business_window
    enabled = {"on": False}

    def rows():
        return {_IUL_PLANCODE: control.ControlRow(_IUL_PLANCODE, "IUL", enabled["on"])}
    monkeypatch.setattr(control, "read_control_rows", rows)
    win._illustration_data = _policy(_IUL_PLANCODE)
    assert win._apply_illustration_gate() is True
    enabled["on"] = True
    assert win._apply_illustration_gate() is True      # cached until the next Get
    control.clear_control_cache()                     # what _on_get_policy does
    win.run_values_btn.setEnabled(True)
    assert win._apply_illustration_gate() is False


class _DummyDb:
    def __init__(self, region):
        self.region = region

    def connect(self):
        pass

    def close(self):
        pass


def _load_family(win, monkeypatch, family, plancode):
    monkeypatch.setattr(mw, "DB2Connection", _DummyDb)
    monkeypatch.setattr(win, "_is_par_whole_life", lambda policy: family == "parwl")
    monkeypatch.setattr(win, "_is_indeterminate_term", lambda policy: family == "term")
    monkeypatch.setattr(win, "_is_iswl_rpu", lambda policy: family == "iswl_rpu")
    loaded = []
    monkeypatch.setattr(win, "_load_parwl_into_ui", lambda *a, **k: loaded.append("parwl"))
    monkeypatch.setattr(win, "_load_term_into_ui", lambda *a, **k: loaded.append("term"))
    monkeypatch.setattr(win, "_load_iswl_rpu_into_ui", lambda *a, **k: loaded.append("iswl_rpu"))
    win._policy = SimpleNamespace(exists=True, company_code="01", policy_number="W0000001",
                                  system_code="I", plancode=plancode)
    win._policy_info = {"CompanyCode": "01", "PolicyNumber": "W0000001"}
    win.run_values_btn.setEnabled(True)
    win._load_policy_into_ui("CKPR")
    return loaded


@pytest.mark.parametrize("family, plancode, product", [
    ("parwl", _PARWL_PLANCODE, "ParWL"),
    ("term", _TERM_PLANCODE, "Term"),
    ("iswl_rpu", _ISWL_PLANCODE, "ISWL"),
])
def test_business_refuses_par_wl_and_term_the_table_disables(
        business_window, monkeypatch, family, plancode, product):
    win = business_window
    assert _load_family(win, monkeypatch, family, plancode) == []
    assert win._workspace_stack.currentWidget() is win.tabs
    assert win.run_values_btn.isEnabled() is False
    assert win.save_case_btn.isEnabled() is False
    assert (f"Plancode {plancode} ({product}) is not enabled for in-force illustration"
            in win.run_notice.text())


def test_par_wl_opens_once_the_table_enables_it(business_window, monkeypatch):
    monkeypatch.setattr(control, "read_control_rows", lambda: {
        _PARWL_PLANCODE: control.ControlRow(_PARWL_PLANCODE, "ParWL", True)})
    assert _load_family(business_window, monkeypatch, "parwl", _PARWL_PLANCODE) == ["parwl"]


def test_developer_par_wl_still_opens_its_workspace(monkeypatch):
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    win = _window()
    assert _load_family(win, monkeypatch, "parwl", _PARWL_PLANCODE) == ["parwl"]


def test_developer_iswl_rpu_opens_its_workspace(monkeypatch):
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    win = _window()
    assert _load_family(win, monkeypatch, "iswl_rpu", _ISWL_PLANCODE) == ["iswl_rpu"]


# -- policy status (soft launch M3) ---------------------------------------------


@pytest.mark.parametrize("status", ["44", "45", "99", "54", "42", "21", ""])
def test_business_gate_blocks_status_outside_phase1(business_window, status):
    win = business_window
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _policy(_ALLOWED_PLANCODE, status)
    assert win._apply_illustration_gate() is True
    assert win.run_values_btn.isEnabled() is False
    assert win._status_label.text().startswith(f"Policy status {status or '(blank)'} (")
    assert "not supported for in-force illustration in this release" in win.run_notice.text()


def test_business_gate_extended_term_message(business_window):
    win = business_window
    win._illustration_data = _policy(_ALLOWED_PLANCODE, "44")
    win._apply_illustration_gate()
    assert win._status_label.text() == (
        "Policy status 44 (Extended Term) is not supported for in-force "
        "illustration in this release.")


def test_business_gate_allows_premium_paying_including_suspended(business_window):
    win = business_window
    win.run_values_btn.setEnabled(True)
    policy = _policy(_ALLOWED_PLANCODE, "22")
    policy.suspense_code = "2"          # suspended stays allowed (banner on Inputs)
    win._illustration_data = policy
    assert win._apply_illustration_gate() is False
    assert win.run_values_btn.isEnabled() is True


@pytest.mark.parametrize("status, label", [
    ("32", "Waiver of Premium"), ("33", "Waiver of Charges"), ("34", "Waiver of COI"),
])
def test_business_gate_blocks_disability_waiver(business_window, status, label):
    win = business_window
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _policy(_ALLOWED_PLANCODE, status)
    assert win._apply_illustration_gate() is True
    assert win.run_values_btn.isEnabled() is False
    assert win._status_label.text() == (
        f"Policy status {status} ({label}) is not supported for in-force illustration: "
        "policies on disability waiver are not illustrated in this release.")


def test_business_gate_blocks_death_claim_pending_suspense(business_window):
    win = business_window
    policy = _policy(_ALLOWED_PLANCODE)
    policy.suspense_code = "3"
    win._illustration_data = policy
    assert win._apply_illustration_gate() is True
    assert "Death Claim Pending" in win._status_label.text()


def test_developer_gets_status_warning_not_block(monkeypatch):
    monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    win = _window()
    win.run_values_btn.setEnabled(True)
    win._illustration_data = _policy(_ALLOWED_PLANCODE, "44")
    assert win._apply_illustration_gate() is False
    assert win.run_values_btn.isEnabled() is True
    assert "Policy status 44 (Extended Term)" in win.run_notice.text()
    assert "developer run allowed" in win.run_notice.text()
