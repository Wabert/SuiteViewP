"""Par WL riders and benefits: shown on the Illustration Inputs like the UL ones, keep or drop.

A dropped term rider stops billing and leaves the death benefit on its drop date (with any
benefit on its phase); a dropped benefit stops billing. The base coverage and the paid-up
additions rider cannot be dropped.
"""
from __future__ import annotations

from datetime import date

import pytest

from suiteview.illustration.core.ledger_report import format_ledger_pages
from suiteview.illustration.core.parwl.engine import ParWLEngine, ParWLProjectionError
from suiteview.illustration.core.parwl.report import build_parwl_report
from suiteview.illustration.models.parwl import (
    ROLE_TERM_RIDER,
    ParWLBenefit,
    ParWLCoverage,
    ParWLInputs,
    RiderDrop,
    droppable_riders,
    with_riders_dropped,
)
from tests.test_illustration_parwl import make_policy, make_rates

DROP = date(2028, 2, 13)                 # the year 27 anniversary
VALUATION = date(2026, 9, 13)


def _policy():
    base = make_policy().base
    rider = ParWLCoverage(**{**vars(base), "phase": 3, "plancode": "08572500", "role": ROLE_TERM_RIDER,
                             "units": 25.0, "annual_premium_per_unit": 17.48, "pay_up_date": date(2040, 2, 13),
                             "maturity_date": date(2040, 2, 13), "form_number": "TR-25",
                             "description": "Level Term Rider"})
    waiver = ParWLBenefit(1, "30", "Premium Waiver", 10.0, 1000.0, 0.27, 1.0, date(2002, 2, 13), 49,
                          date(2037, 2, 13), form_number="WP-100")
    rider_adb = ParWLBenefit(3, "70", "Accidental Death", 25.0, 1000.0, 0.71, 1.0, date(2002, 2, 13), 49,
                             date(2037, 2, 13), form_number="ADB-3")
    policy = make_policy(loans=())
    return make_policy(loans=(), coverages=policy.coverages + (rider,), benefits=(waiver, rider_adb))


def _month(result, when):
    return next(m for m in result.months if m.when == when)


def test_droppable_riders_are_term_riders_and_benefits_only():
    assert set(droppable_riders(_policy())) == {"cov:3", "ben:30:1", "ben:70:3"}


def test_dropped_term_rider_stops_its_premium_face_and_phase_benefits():
    policy = _policy()
    kept = ParWLEngine(policy, make_rates()).run()
    dropped = ParWLEngine(policy, make_rates(), ParWLInputs(rider_drops=[RiderDrop("cov:3", DROP)])).run()
    before = date(2028, 1, 13)
    assert _month(dropped, before).rider_premium == _month(kept, before).rider_premium > 0
    assert _month(dropped, before).term_rider_face == 25000.0
    after = _month(dropped, DROP)
    assert (after.rider_premium, after.term_rider_face) == (0.0, 0.0)
    assert _month(kept, DROP).term_rider_face == 25000.0
    # the ADB on the rider's phase goes with it; the base's waiver stays
    assert 0 < after.benefit_premium < _month(kept, DROP).benefit_premium
    assert any("Level Term Rider (08572500) is dropped on 02/13/2028" in note for note in dropped.notes)
    assert dropped.policy is policy                                   # the result keeps the record


def test_dropped_benefit_stops_billing_from_its_date():
    policy = _policy()
    kept = ParWLEngine(policy, make_rates()).run()
    dropped = ParWLEngine(policy, make_rates(), ParWLInputs(rider_drops=[RiderDrop("ben:30:1", DROP)])).run()
    assert _month(dropped, date(2028, 1, 13)).benefit_premium == _month(kept, date(2028, 1, 13)).benefit_premium
    assert _month(dropped, DROP).benefit_premium < _month(kept, DROP).benefit_premium
    assert _month(dropped, DROP).term_rider_face == 25000.0
    view = with_riders_dropped(policy, [RiderDrop("ben:30:1", DROP)])
    assert view.benefits[0].cease_date == DROP and view.benefits[1].cease_date == date(2037, 2, 13)


@pytest.mark.parametrize("drop, message", [
    (RiderDrop("cov:1", DROP), "only those can be dropped"),            # the base
    (RiderDrop("cov:2", DROP), "only those can be dropped"),            # the PUA rider
    (RiderDrop("ben:99:1", DROP), "only those can be dropped"),
    (RiderDrop("cov:3", date(2026, 8, 13)), "before the valuation date"),
    (RiderDrop("cov:3", date(2028, 2, 14)), "not a monthliversary"),
])
def test_bad_rider_drops_are_refused_loudly(drop, message):
    with pytest.raises(ParWLProjectionError, match=message):
        ParWLEngine(_policy(), make_rates(), ParWLInputs(rider_drops=[drop]))


def test_report_states_the_drop_and_the_rider_ends_on_it():
    result = ParWLEngine(_policy(), make_rates(), ParWLInputs(rider_drops=[RiderDrop("cov:3", DROP)])).run()
    report = build_parwl_report(result, date(2026, 9, 29))
    assert "LEVEL TERM RIDER (08572500) IS DROPPED ON 02/13/2028 (YEAR 27)" in report.assumption_lines
    assert "LEVEL TERM RIDER (08572500) - $25,000 TO 02/13/2028" in report.other_coverage
    assert any("ACCIDENTAL DEATH TO 02/13/2028" == line for line in report.other_coverage)
    assert all(len(line) <= report.width for page in format_ledger_pages(report) for line in page)


# -- Illustration Inputs ----------------------------------------------------------------

def test_inputs_show_rider_buttons_and_read_drops(qtbot):
    from PyQt6.QtWidgets import QPushButton

    from suiteview.illustration.ui.parwl_inputs import ParWLInputsTab

    tab = ParWLInputsTab()
    qtbot.addWidget(tab)
    tab.load_policy(_policy())
    labels = [b.text() for b in tab.riders_panel.findChildren(QPushButton)]
    assert labels == ["NB1PU300", "TR-25", "WP-100", "ADB-3"]             # no base coverage button
    assert "Keep / drop" in tab.riders_panel._buttons["cov:3"].toolTip()
    assert "View only" in tab.riders_panel._buttons["cov:2"].toolTip()     # PUA rider: its own payments input
    assert tab.read_inputs().rider_drops == []

    changed = []
    tab.inputs_changed.connect(lambda: changed.append(True))
    warnings = tab.riders_panel.apply_adjustments({
        "cov:3": {"action": "drop", "effective_year": 27},
        "ben:30:1": {"action": "drop", "effective_year": 25},           # the current year: the valuation date
        "cov:2": {"action": "drop", "effective_year": 27, "label": "NB1PU300"},
    })
    assert changed
    assert warnings == ["Rider decision 'drop' for NB1PU300 did not apply — "
                        "the rider/benefit cannot be adjusted in this illustration."]
    drops = tab.read_inputs().rider_drops
    assert sorted(drops, key=lambda d: d.key) == [RiderDrop("ben:30:1", VALUATION), RiderDrop("cov:3", DROP)]

    tab.load_policy(_policy())                                            # a fresh load keeps everything
    assert tab.read_inputs().rider_drops == []


def test_rider_dialog_offers_keep_and_drop_only(qtbot, monkeypatch):
    from PyQt6.QtWidgets import QPushButton

    from suiteview.illustration.ui import inputs_dynamic
    from suiteview.illustration.ui.parwl_inputs import ParWLInputsTab

    tab = ParWLInputsTab()
    qtbot.addWidget(tab)
    tab.load_policy(_policy())
    seen = {}

    def fake_exec(dialog):
        for button in dialog.findChildren(QPushButton):
            seen[button.text()] = button.isEnabled()
            if button.text() == "Drop rider":
                button.setChecked(True)
        return 0

    monkeypatch.setattr(inputs_dynamic.FramelessDialog, "exec", fake_exec)
    tab.riders_panel._buttons["cov:3"].click()
    assert seen["Keep rider"] and seen["Drop rider"] and not seen["Change rider"]
    assert [d.key for d in tab.read_inputs().rider_drops] == ["cov:3"]
