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


def test_excess_repayment_checkbox_defaults_off_and_drives_options():
    _app()
    tab = IllustrationInputsTab()

    # "Apply excess as premium" lives in the Loan Repayments group and is off
    # by default — repayments stop once the loan is repaid.
    assert tab.dynamic_panel.excess_repay_as_premium_check.isChecked() is False
    assert tab.export_options().apply_excess_repayment_as_premium is False

    tab.dynamic_panel.excess_repay_as_premium_check.setChecked(True)
    assert tab.export_options().apply_excess_repayment_as_premium is True


def test_iul_crediting_switches_default_and_drive_options():
    _app()
    tab = IllustrationInputsTab()

    # Blended Rate is the default crediting method; WAIR is the opt-in.
    assert tab.blended_rate_radio.isChecked() is True
    assert tab.export_options().iul_wair_crediting is False
    tab.wair_radio.setChecked(True)
    assert tab.export_options().iul_wair_crediting is True

    # "Use Policy AG49 Regime" defaults off (current regime).
    assert tab.policy_ag49_check.isChecked() is False
    assert tab.export_options().use_policy_ag49_regime is False
    tab.policy_ag49_check.setChecked(True)
    assert tab.export_options().use_policy_ag49_regime is True


def test_policy_ag49_checkbox_rebases_allocation_blend():
    from datetime import date

    from suiteview.illustration.models.index_strategies import (
        load_index_strategies,
    )

    _app()
    tab = IllustrationInputsTab()
    panel = tab.dynamic_panel.allocations_panel

    # IUL19 policy issued 2019 -> policy regime = AG49 (index 2); the current
    # regime is AG49B (index 4). 100% IP so the multiplier shows in the blend.
    plan = load_index_strategies("1U146800")
    tab.dynamic_panel._ctx.is_iul = True
    tab.dynamic_panel._ctx.issue_date = date(2019, 6, 1)
    panel.set_plan(plan, gint=0.035, inforce_allocations={"IP": 1.0})
    panel.set_ag49_index(4)  # what load_from_policy resolves with the box off

    rate = panel.rates()["IP"]
    assert panel.blended().effective == panel.blended().nominal

    # Checking the box re-bases to index 2: IP credits rate x 1.24 and the
    # 2.15% asset charge turns on — without disturbing the user's entries.
    tab.policy_ag49_check.setChecked(True)
    assert panel.allocations()["IP"] == 1.0
    assert panel.blended().effective > panel.blended().nominal
    assert panel.blended().asset_charge_rate > 0.0

    tab.policy_ag49_check.setChecked(False)
    assert panel.blended().effective == panel.blended().nominal
    assert panel.blended().asset_charge_rate == 0.0
