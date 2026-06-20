"""Inputs-tab rider/benefit buttons: matured items are de-emphasized (headless Qt)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication

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
        cease_date=None, units=0.0, benefit_amount=0.0, issue_age=40, coi_rate=0.5,
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


def test_non_premium_paying_active_benefit_stays_disabled():
    _app()
    panel = RiderButtonsPanel()
    ctx = PolicyContext(valuation_date=date(2026, 6, 1))
    # Active (future cease) but not premium-paying: disabled, as before.
    panel.set_policy(_policy(
        benefits=[_ben(cov_pha_nbr=3, coi_rate=None, cease_date=date(2040, 1, 1))],
    ), ctx)
    btn = panel._buttons["ben:3:3"]
    assert btn.isEnabled() is False
    assert "ben:3:3" not in panel._matured


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
