"""ABR Quote blocks Whole Life (Par and Non-Par) unless the user is ADMIN/SUPPORT."""

from __future__ import annotations

import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.abrquote.core.eligibility import (
    WHOLE_LIFE_NOT_AVAILABLE, abr_product_restriction,
)
from suiteview.abrquote.models.abr_data import ABRPolicyData, MedicalAssessment
from suiteview.abrquote.ui import policy_panel as policy_panel_module
from suiteview.abrquote.ui.abr_window import ABRQuoteWindow
from suiteview.abrquote.ui.output_panel import OutputPanel
from suiteview.abrquote.ui.policy_panel import PolicyPanel
from suiteview.core import access_control
from suiteview.core.access_control import AccessUnavailableError, EffectiveAccess


def _access(role: str, *, developer: bool = False) -> EffectiveAccess:
    return EffectiveAccess(
        "TESTER", role, True, False, True,
        apps=frozenset(access_control.APP_CODES), developer=developer,
    )


def _policy(product_type: str, number: str = "WL000001") -> ABRPolicyData:
    return ABRPolicyData(
        policy_number=number,
        region="CKPR",
        company="01 - Test Co",
        product_type=product_type,
        plan_code="PLAN01",
        issue_date=date(2000, 1, 1),
        issue_age=40,
        attained_age=65,
        face_amount=100_000.0,
        maturity_age=121,
    )


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def role(monkeypatch):
    """Set the effective SuiteView role returned by ``get_access``."""
    state = {"access": _access("BUSINESS")}
    monkeypatch.setattr(access_control, "get_access", lambda refresh=False: state["access"])

    def set_role(value):
        state["access"] = value

    return set_role


@pytest.fixture
def window(app, role, monkeypatch):
    monkeypatch.setattr(OutputPanel, "_check_onedrive_sync", lambda self: None)
    for name in ("_populate_rate_info", "_populate_riders_benefits", "_populate_premium_schedule"):
        monkeypatch.setattr(PolicyPanel, name, lambda self: None)
    win = ABRQuoteWindow()
    yield win
    win.close()


@pytest.mark.parametrize("product_type", ["WL", "wl", " WL "])
def test_whole_life_is_restricted(product_type):
    assert abr_product_restriction(product_type) == WHOLE_LIFE_NOT_AVAILABLE


@pytest.mark.parametrize("product_type", ["TERM", "UL", "IUL", "ISWL", "", None])
def test_other_products_are_not_restricted(product_type):
    assert abr_product_restriction(product_type) is None


@pytest.mark.parametrize("access,expected", [
    (_access("ADMIN"), True),
    (_access("SUPPORT"), True),
    (_access("BUSINESS"), False),
    (_access("NONBUSINESS"), False),
    (_access("DEVELOPER", developer=True), True),
])
def test_support_privileges_follow_role(access, expected):
    assert access.has_support_privileges is expected


def test_business_user_cannot_quote_whole_life(window):
    prior = _policy("UL", "UL000001")
    window.policy_panel.set_policy(prior)
    window._set_step(1)
    assert window._policy is prior

    window.policy_panel.set_policy(_policy("WL"))

    panel = window.policy_panel
    assert panel.quote_block_reason() == WHOLE_LIFE_NOT_AVAILABLE
    assert not panel.eligibility_banner.isHidden()
    assert WHOLE_LIFE_NOT_AVAILABLE in panel.eligibility_banner.text()
    assert window._policy is None
    assert window._current_step == 0
    assert WHOLE_LIFE_NOT_AVAILABLE in window.status_label.text()
    assert not window._email_print_btn.isEnabled()
    assert [btn.isEnabled() for btn in window._step_labels] == [True, False, False]

    window._on_step_clicked(1)
    window._on_step_clicked(2)
    assert window._current_step == 0

    window._assessment = MedicalAssessment(rider_type="Terminal")
    window._run_calculation()
    assert "Calculating" not in window.status_label.text()
    assert "Quoting is disabled" in window.status_label.text()


def test_loading_quotable_policy_after_whole_life_unlocks_steps(window):
    window.policy_panel.set_policy(_policy("WL"))
    assert window._quote_blocked

    ul = _policy("UL", "UL000002")
    window.policy_panel.set_policy(ul)

    assert window.policy_panel.quote_block_reason() is None
    assert window.policy_panel.eligibility_banner.isHidden()
    assert window._policy is ul
    assert all(btn.isEnabled() for btn in window._step_labels)
    window._on_step_clicked(1)
    assert window._current_step == 1


@pytest.mark.parametrize("role_code", ["ADMIN", "SUPPORT"])
def test_admin_and_support_can_quote_whole_life(window, role, role_code):
    role(_access(role_code))
    wl = _policy("WL")
    window.policy_panel.set_policy(wl)

    panel = window.policy_panel
    assert panel.quote_block_reason() is None
    assert not panel.eligibility_banner.isHidden()
    assert WHOLE_LIFE_NOT_AVAILABLE in panel.eligibility_banner.text()
    assert "ADMIN/SUPPORT" in panel.eligibility_banner.text()
    assert window._policy is wl
    assert all(btn.isEnabled() for btn in window._step_labels)


def test_unverifiable_access_fails_closed(window, monkeypatch):
    def unavailable():
        raise AccessUnavailableError("offline")

    monkeypatch.setattr(policy_panel_module, "has_support_privileges", unavailable)
    window.policy_panel.set_policy(_policy("WL"))

    assert window.policy_panel.quote_block_reason() == WHOLE_LIFE_NOT_AVAILABLE
    assert window._policy is None


def test_retrieve_whole_life_shows_clear_message(window, monkeypatch):
    wl = _policy("WL")
    warnings = []
    monkeypatch.setattr(policy_panel_module, "find_policy_companies", lambda *_: ["01"])
    monkeypatch.setattr(
        policy_panel_module, "build_abr_policy", lambda *a, **kw: (wl, None),
    )
    monkeypatch.setattr(policy_panel_module, "fetch_reinsurer_list", lambda *a: [])
    monkeypatch.setattr(
        policy_panel_module.QMessageBox, "warning",
        lambda parent, title, text: warnings.append((title, text)),
    )

    window.load_policy("WL000001")

    assert warnings == [(
        "ABR Quote Not Available",
        f"Policy WL000001: {WHOLE_LIFE_NOT_AVAILABLE}\n\nQuoting is disabled for this policy.",
    )]
    assert window._policy is None
    assert window._quote_blocked
