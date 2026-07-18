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


def test_allow_gp_exception_checkbox_lives_in_run_controls_and_drives_options():
    _app()
    tab = IllustrationInputsTab()

    # "Allow GP Exception Premium" sits in the Illustration Control tab's Run
    # Controls group (moved back from the Input sheet) and is on by default.
    assert tab.exception_prem_check.isChecked() is True
    assert tab.export_options().allow_exception_prems is True

    # Unchecking flows straight through to the run options.
    tab.exception_prem_check.setChecked(False)
    assert tab.export_options().allow_exception_prems is False


def test_shadow_account_signal_forces_exception_checkbox_off():
    from datetime import date

    _app()

    class _ShadowPolicy:
        issue_date = date(2019, 11, 9)
        base_issue_age = 50
        attained_age = 56
        valuation_date = date(2026, 5, 9)
        policy_year = 7
        maturity_age = 121
        billing_frequency = 1
        modal_premium = 153.56
        def_of_life_ins = "GPT"
        base_plancode = ""
        status_code = "0"

        def get_coverages(self):
            return []

        def get_benefits(self):
            return []

    # The Input panel signals exception availability; the tab applies it to
    # the Run Controls checkbox — forced off (with the reason as tooltip) for
    # an active shadow account, re-enabled when a non-shadow policy loads.
    tab = IllustrationInputsTab()
    tab.dynamic_panel.load_from_policy(_ShadowPolicy(), has_shadow=True)
    assert tab.exception_prem_check.isChecked() is False
    assert tab.exception_prem_check.isEnabled() is False
    assert "shadow account" in tab.exception_prem_check.toolTip()
    assert tab.export_options().allow_exception_prems is False

    tab.dynamic_panel.load_from_policy(_ShadowPolicy(), has_shadow=False)
    assert tab.exception_prem_check.isEnabled() is True
    assert "shadow account" not in tab.exception_prem_check.toolTip()


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


def test_excess_repayment_toggle_defaults_to_stop_and_drives_options():
    _app()
    tab = IllustrationInputsTab()

    # The excess-repayment radios sit at the top of the Loan Repayments group
    # and default to "Stop at payoff" — repayments stop once the loan is
    # repaid, matching the engine's flag-off behavior.
    assert tab.dynamic_panel.excess_stop_radio.isChecked() is True
    assert tab.dynamic_panel.excess_apply_radio.isChecked() is False
    assert tab.export_options().apply_excess_repayment_as_premium is False

    # "Apply excess as premium" flows straight through to the run options —
    # and switching back to "Stop at payoff" clears the flag again.
    tab.dynamic_panel.excess_apply_radio.setChecked(True)
    assert tab.export_options().apply_excess_repayment_as_premium is True
    tab.dynamic_panel.excess_stop_radio.setChecked(True)
    assert tab.export_options().apply_excess_repayment_as_premium is False


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


def test_iul_crediting_group_greyed_unless_iul_plan():
    _app()
    tab = IllustrationInputsTab()

    # No policy loaded -> the whole IUL Crediting group is greyed with the
    # not-applicable note showing (greyed, never hidden).
    assert tab.iul_crediting_group.isEnabled() is False
    assert tab.iul_na_note.isVisible() is False  # not shown yet — widget itself hidden with parent
    assert tab.iul_na_note.isVisibleTo(tab.iul_crediting_group) is True

    # An IUL plancode enables the group and drops the note.
    tab._set_iul_crediting_applicable(True)
    assert tab.iul_crediting_group.isEnabled() is True
    assert tab.iul_na_note.isVisibleTo(tab.iul_crediting_group) is False

    # Back to a declared-rate plan -> greyed again.
    tab._set_iul_crediting_applicable(False)
    assert tab.iul_crediting_group.isEnabled() is False
    assert tab.iul_na_note.isVisibleTo(tab.iul_crediting_group) is True


def test_ag49_regime_panel_selects_issue_date_regime():
    from datetime import date

    _app()
    tab = IllustrationInputsTab()
    tab._set_iul_crediting_applicable(True)  # regime rows live inside the IUL group

    # One display row per regime: (none) / AG49 / AG49A / AG49B.
    assert sorted(tab._ag49_regime_radios) == [1, 2, 3, 4]

    # Box off -> panel greyed, nothing selected.
    assert tab._ag49_regime_panel.isEnabled() is False
    assert not any(r.isChecked() for r in tab._ag49_regime_radios.values())

    # Box on with no policy loaded -> enabled but still no selection.
    tab.policy_ag49_check.setChecked(True)
    assert tab._ag49_regime_panel.isEnabled() is True
    assert not any(r.isChecked() for r in tab._ag49_regime_radios.values())

    # The row matching the policy issue date is auto-selected.
    for issue, expected in [
        (date(2014, 1, 1), 1),   # pre-AG49 -> (none)
        (date(2016, 6, 1), 2),   # AG49
        (date(2021, 1, 1), 3),   # AG49A
        (date(2024, 1, 1), 4),   # AG49B
    ]:
        tab._issue_date = issue
        tab._update_ag49_regime_panel()
        checked = [i for i, r in tab._ag49_regime_radios.items() if r.isChecked()]
        assert checked == [expected]

    # Unchecking the box clears the selection and greys the panel again.
    tab.policy_ag49_check.setChecked(False)
    assert tab._ag49_regime_panel.isEnabled() is False
    assert not any(r.isChecked() for r in tab._ag49_regime_radios.values())


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
