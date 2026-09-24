"""Inputs-tab rider/benefit buttons: matured items are de-emphasized (headless Qt)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QApplication, QPushButton

from suiteview.illustration.core.illustration_policy_service import coverage_or_benefit_matured
from suiteview.illustration.ui.inputs_dynamic import (
    PolicyContext,
    RiderAdjustment,
    RiderButtonsPanel,
)

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _cov(**kw):
    base = dict(
        cov_pha_nbr=2, form_number="R-1", plancode="1U900", issue_date=date(2000, 1, 1),
        face_amount=50_000.0, issue_age=40, rate_class="N", cov_status="A",
        rate=1.25, annual_premium=120.0, maturity_date=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _ben(**kw):
    base = dict(
        cov_pha_nbr=3, form_number="B-1", benefit_code="WP", benefit_type_cd="3",
        benefit_subtype_cd="", benefit_desc="Waiver", issue_date=date(2000, 1, 1),
        pay_up_date=None, cease_date=None, units=0.0, benefit_amount=0.0, issue_age=40, coi_rate=0.5,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _policy(coverages=(), benefits=()):
    return SimpleNamespace(
        get_coverages=lambda: list(coverages),
        get_benefits=lambda: list(benefits),
    )


def test_rider_matured_predicate():
    as_of = date(2026, 6, 1)
    assert coverage_or_benefit_matured(SimpleNamespace(cease_date=date(2020, 1, 1)), as_of) is True
    assert coverage_or_benefit_matured(SimpleNamespace(maturity_date=date(2026, 6, 1)), as_of) is True  # on the date
    assert coverage_or_benefit_matured(SimpleNamespace(maturity_date=date(2040, 1, 1)), as_of) is False  # future
    assert coverage_or_benefit_matured(SimpleNamespace(terminate_date=date(2019, 1, 1)), as_of) is True
    assert coverage_or_benefit_matured(SimpleNamespace(), as_of) is False
    assert coverage_or_benefit_matured(SimpleNamespace(cease_date=date(2020, 1, 1)), None) is False


def test_matured_benefit_deemphasized_but_clickable():
    _app()
    panel = RiderButtonsPanel()
    ctx = PolicyContext(valuation_date=date(2026, 6, 1))
    panel.set_policy(_policy(
        coverages=[_cov(cov_pha_nbr=2, maturity_date=date(2040, 1, 1))],   # active rider
        benefits=[_ben(cov_pha_nbr=3, cease_date=date(2020, 1, 1))],       # matured benefit
    ), ctx)

    cov_key, ben_key = "cov:2", "ben:3:3"
    assert ben_key in panel._matured
    assert cov_key not in panel._matured

    # Matured benefit: still clickable, but wears the de-emphasized (italic) look.
    matured_btn = panel._buttons[ben_key]
    assert matured_btn.isEnabled() is True
    assert "italic" in matured_btn.styleSheet()
    assert "matured" in matured_btn.toolTip().lower()

    # Active premium-paying rider: enabled, normal (non-italic) styling.
    assert panel._buttons[cov_key].isEnabled() is True
    assert "italic" not in panel._buttons[cov_key].styleSheet()


@pytest.mark.parametrize("snapshot", [False, True])
@pytest.mark.parametrize("issue_rate", [None, 0.0])
def test_renewal_rated_benefit_can_be_dropped_and_restored(monkeypatch, snapshot, issue_rate):
    from suiteview.illustration.models.policy_data import BenefitInfo, IllustrationPolicyData
    from suiteview.illustration.ui.inputs_dynamic import FramelessDialog

    _app()
    panel = RiderButtonsPanel()
    ctx = PolicyContext(
        valuation_date=date(2026, 9, 15), issue_date=date(2002, 2, 15),
        issue_age=34, forecast_date=date(2026, 10, 15), forecast_year=25,
        forecast_age=58, maturity_age=95,
    )
    if snapshot:
        policy = IllustrationPolicyData(benefits=[BenefitInfo(
            coverage_phase=1, benefit_type="3", benefit_subtype="9",
            coi_rate=issue_rate, pay_up_date=date(2028, 2, 15),
            cease_date=date(2028, 2, 15),
        )])
    else:
        policy = _policy(benefits=[_ben(
            cov_pha_nbr=1, benefit_subtype_cd="9", coi_rate=issue_rate,
            renewal_rate=7100.0, pay_up_date=date(2028, 2, 15),
            cease_date=date(2028, 2, 15),
        )])
    panel.set_policy(policy, ctx)

    def choose_drop(dialog):
        buttons = {b.text(): b for b in dialog.findChildren(QPushButton)}
        assert buttons["Drop rider"].isEnabled()
        buttons["Drop rider"].click()
        dialog.accept()
        return 1

    monkeypatch.setattr(FramelessDialog, "exec", choose_drop)
    item = panel._items[0]
    panel._open_dialog(item[0], item[1], item[2], item[4], item[3])
    events = panel.collect_changes(ctx)
    assert len(events) == 1
    assert events[0].metadata == {"target": "ben:39:1", "action": "drop"}
    assert events[0].effective_date == date(2026, 10, 15)
    assert events[0].value == 0
    saved = panel.capture_adjustments()
    panel.set_policy(policy, ctx)
    assert panel.apply_adjustments(saved) == []
    assert panel.collect_changes(ctx) == events
    panel.deleteLater()


@pytest.mark.parametrize("administrative", [False, True])
def test_view_only_benefit_dialog_actions_disabled(monkeypatch, administrative):
    from suiteview.illustration.models.policy_data import BenefitInfo, IllustrationPolicyData
    from suiteview.illustration.ui.inputs_dynamic import FramelessDialog

    _app()
    panel = RiderButtonsPanel()
    ctx = PolicyContext(valuation_date=date(2026, 9, 15))
    panel.set_policy(IllustrationPolicyData(benefits=[BenefitInfo(
        benefit_type="#" if administrative else "3", benefit_subtype="9",
        coi_rate=1.0, cease_date=None if administrative else date(2026, 9, 15),
    )]), ctx)

    def inspect(dialog):
        buttons = {b.text(): b for b in dialog.findChildren(QPushButton)}
        for name in ("Keep rider", "Change rider", "Drop rider"):
            assert not buttons[name].isEnabled()
        dialog.accept()
        return 1

    monkeypatch.setattr(FramelessDialog, "exec", inspect)
    item = panel._items[0]
    panel._open_dialog(item[0], item[1], item[2], item[4], item[3])
    assert panel.collect_changes(ctx) == []
    panel.deleteLater()


def test_policy_tab_matured_button_is_paler_but_clickable():
    _app()
    from suiteview.illustration.ui.policy_tab import IllustrationPolicyTab

    tab = IllustrationPolicyTab()
    tab._coverages = [
        _cov(cov_pha_nbr=2, form_number="ACTIVE", maturity_date=date(2040, 1, 1)),
        _cov(cov_pha_nbr=3, form_number="MATURED", maturity_date=date(2020, 1, 1)),
    ]
    tab._benefits = []
    tab._as_of = date(2026, 6, 1)
    tab._populate_coverage_buttons()

    buttons = {}
    for i in range(tab.coverage_buttons.count()):
        widget = tab.coverage_buttons.itemAt(i).widget()
        if widget is not None:
            buttons[widget.text()] = widget

    # Matured -> paler (italic) style, still enabled/clickable.
    assert "italic" in buttons["MATURED"].styleSheet()
    assert buttons["MATURED"].isEnabled() is True
    assert "matured" in buttons["MATURED"].toolTip().lower()
    # Active -> normal rich style.
    assert "italic" not in buttons["ACTIVE"].styleSheet()


def test_matured_adjustments_are_view_only():
    _app()
    panel = RiderButtonsPanel()
    ctx = PolicyContext(valuation_date=date(2026, 6, 1), issue_date=date(2000, 1, 1), issue_age=40)
    panel.set_policy(_policy(
        benefits=[_ben(cov_pha_nbr=3, cease_date=date(2020, 1, 1))],
    ), ctx)
    ben_key = "ben:3:3"
    adj = panel._adjustments[ben_key]
    adj.action = RiderAdjustment.DROP
    adj.new_amount = 0.0
    adj.effective_year = 30
    # A matured item never emits an engine change event.
    assert panel.collect_changes(ctx) == []
