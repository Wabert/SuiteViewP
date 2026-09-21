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


def test_plancode_uppercases_and_resets():
    _app()
    tab = PolicyTab()
    tab.set_state({"txt_plancode": "u1f4m00"})
    assert tab.txt_plancode.text() == "U1F4M00"
    tab.chk_rga.setChecked(True)
    tab.set_state({})
    assert tab.txt_plancode.text() == ""
    assert not tab.chk_rga.isChecked()


def test_plancode_and_rga_saved_state_round_trip():
    _app()
    tab = PolicyTab()
    tab.txt_plancode.setText("f4m")
    tab.chk_rga.setChecked(True)
    saved = tab.get_state()
    restored = PolicyTab()
    restored.set_state(saved)
    assert restored.get_state() == saved


def test_identifier_controls_use_aligned_compact_rows():
    app = _app()
    tab = PolicyTab()
    tab.resize(1200, 590)
    tab.show()
    app.processEvents()
    controls = [
        tab.txt_plancode, tab.cmb_company, tab.cmb_market,
        tab.txt_form_number, tab.txt_branch, tab.cmb_polnum_criteria,
    ]
    assert len({widget.x() for widget in controls}) == 1
    assert all(widget.height() == 22 for widget in controls)
    assert all(b.y() - a.y() == 24 for a, b in zip(controls, controls[1:]))
    assert tab.txt_plancode.width() == tab.cmb_polnum_criteria.width()
    assert tab.chk_rga.x() == tab.txt_polnum_value.x()
    assert tab.chk_rga.geometry().center().y() == tab.txt_plancode.geometry().center().y()
    assert tab.chk_rga.x() > tab.txt_plancode.geometry().right()
    assert tab.cmb_company.geometry().right() == tab.txt_polnum_value.geometry().right()
    assert tab.txt_plancode.geometry().right() < tab.list_status.x()
    tab.close()
