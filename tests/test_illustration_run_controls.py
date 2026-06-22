"""Run Controls -> IllustrationOptions wiring (headless Qt)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_levelizing_checkbox_defaults_on_and_drives_options():
    _app()
    tab = IllustrationInputsTab()

    # "Levelized capped premiums (off for loans)" is checked by default.
    assert tab.levelizing_check.isChecked() is True
    assert tab.export_options().levelizing_premium is True

    # Unchecking flows straight through to the run options.
    tab.levelizing_check.setChecked(False)
    assert tab.export_options().levelizing_premium is False


def test_apply_prem_to_loan_checkbox_defaults_off_and_drives_options():
    _app()
    tab = IllustrationInputsTab()

    # "Apply Premium to Loan First" lives on the Input panel and is off by
    # default — a normal illustration loads premium straight to the account value.
    assert tab.dynamic_panel.apply_prem_to_loan_check.isChecked() is False
    assert tab.export_options().apply_prem_to_loan is False

    tab.dynamic_panel.apply_prem_to_loan_check.setChecked(True)
    assert tab.export_options().apply_prem_to_loan is True
