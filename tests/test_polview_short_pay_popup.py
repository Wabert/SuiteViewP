"""Account Values: the Short Pay / Dial-To button and popup."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt

from suiteview.polview.ui.tabs import short_pay_popup as sp

SHORT_PAY_ATTRS = tuple(attr for _label, attr in sp.FIELDS)


def _policy(premium=None, duration=None, mode=None, cease=None, cease_age=None, dial_to=None, issue_age=35):
    return SimpleNamespace(
        billing=SimpleNamespace(
            short_pay_premium=premium, short_pay_duration=duration, short_pay_mode=mode,
            sp_billing_cease_date=cease, sp_prem_cease_age=cease_age),
        targets=SimpleNamespace(db_dial_to_age=dial_to),
        coverages=SimpleNamespace(cov_issue_age=lambda index: issue_age),
    )


@pytest.fixture
def tab(qtbot):
    from suiteview.polview.ui.tabs.adv_prod_tab import AdvProdValuesTab

    widget = AdvProdValuesTab()
    qtbot.addWidget(widget)
    return widget


def test_short_pay_rows_moved_out_of_policy_info(tab):
    assert not set(SHORT_PAY_ATTRS) & set(tab.policy_info._fields)
    assert set(tab.short_pay_popup.info._fields) == set(SHORT_PAY_ATTRS)
    assert tab.short_pay_button.text() == sp.BUTTON_TEXT
    assert tab.policy_info._info_layout.indexOf(tab.short_pay_button) >= 0


def test_empty_policy_greys_the_button_but_it_still_opens(tab, qtbot):
    tab._load_short_pay(_policy())
    button, popup = tab.short_pay_button, tab.short_pay_popup
    assert not button.active and button.isEnabled()
    assert "italic" in button.styleSheet() and sp.EMPTY_NOTE in button.toolTip()
    assert all(not popup.info._fields[attr].text() for attr in SHORT_PAY_ATTRS)
    assert not popup.empty_note.isHidden()
    tab.show()
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert popup.isVisible()
    popup.hide()


def test_short_pay_policy_activates_the_button_and_fills_the_popup(tab):
    """UE148375 (1U147600): VS target, initial pay duration 44, mode M, dial-to age 105."""
    tab._load_short_pay(_policy(
        premium=Decimal("1234.56"), duration=44, mode="M", cease=date(2059, 3, 1), cease_age=79,
        dial_to=105))
    fields = tab.short_pay_popup.info._fields
    assert tab.short_pay_button.active
    assert "Short Pay Prem" in tab.short_pay_button.toolTip()
    assert (fields["short_pay_prem"].text(), fields["short_pay_dur"].text(), fields["short_pay_mode"].text(),
            fields["sp_prem_cease_age"].text(), fields["db_dial_to_age"].text()) == (
                "1,234.56", "44", "M", "79", "105")
    assert fields["sp_billing_cease_date"].text() == "2059-03-01"
    assert fields["sp_prem_cease_age"].toolTip()
    assert tab.short_pay_popup.empty_note.isHidden()


def test_dial_to_age_alone_activates_and_reload_clears(tab):
    tab._load_short_pay(_policy(dial_to=121))
    assert tab.short_pay_button.active
    assert tab.short_pay_popup.present_labels() == ("DB Dial-To Age",)
    tab._load_short_pay(_policy())
    assert not tab.short_pay_button.active
    assert not tab.short_pay_popup.info._fields["db_dial_to_age"].text()
