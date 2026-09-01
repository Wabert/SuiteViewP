import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.audit.tabs.policy_tab import PolicyTab

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_policynumber_criteria_defaults_to_contains():
    _app()
    tab = PolicyTab()

    assert tab.cmb_polnum_criteria.currentText() == "Contains"


def test_policynumber_criteria_restores_contains_when_absent_from_state():
    _app()
    tab = PolicyTab()
    tab.cmb_polnum_criteria.setCurrentText("Starts with")

    tab.set_state({})

    assert tab.cmb_polnum_criteria.currentText() == "Contains"


def test_policynumber_criteria_restores_saved_value():
    _app()
    tab = PolicyTab()

    tab.set_state({"cmb_polnum_criteria": "Ends with"})

    assert tab.cmb_polnum_criteria.currentText() == "Ends with"
