import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.models.input_set import (
    InforceOverrideSet,
    IllustrationInputSet,
    PolicyChangeKind,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.illustration.ui.inputs_dynamic import (
    DynamicInputsPanel,
    PolicyContext,
)
from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab


_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


class _FakePolicy:
    """Just enough PolicyInformation surface for context_from_policy."""

    issue_date = date(2019, 11, 9)
    base_issue_age = 50
    attained_age = 56
    valuation_date = date(2026, 5, 9)
    policy_year = 7
    maturity_age = 121
    billing_frequency = 1
    modal_premium = 153.56
    def_of_life_ins = "GPT"
    glp = 1200.0
    accumulated_glp = 5000.0
    premiums_paid_to_date = 10000.0
    withdrawals_to_date = 1000.0
    base_rate_class = "N"
    base_table_rating = 2
    base_plancode = "1U135D00"
    status_code = "0"

    def get_coverages(self):
        return []

    def get_benefits(self):
        return []


def _panel() -> DynamicInputsPanel:
    _app()
    panel = DynamicInputsPanel()
    panel.load_from_policy(_FakePolicy())
    return panel


def test_premium_row_defaults_from_forecast_date():
    panel = _panel()
    row = panel.premium_section.rows()[0]
    # Valuation 2026-05-09 -> forecast 2026-06-09 = policy year 7 (issue 2019-11-09).
    assert row.year() == 7
    assert row.age_edit.value() == 56          # 50 + 7 - 1
    assert row.mode() == "M"
    assert row.for_years_edit.value() == 65    # years 7..71
    assert row.to_age_edit.value() == 121
    assert abs(row.amount() - 153.56) < 0.005


def test_input_tab_illustrated_rate_defaults_from_plancode_gint():
    panel = _panel()

    assert panel.illustrated_rate_edit.text() == "3.000"
    assert panel.illustrated_rate() == 0.03


def test_loan_policy_allows_gp_exception_but_shadow_still_blocks():
    # A policy loan no longer disables Allow GP Exception — the premium is applied
    # to the loan first, so the policy can ride the GLP exception period with a
    # loan outstanding. An active shadow account still blocks it: the checkbox
    # lives on the Illustration Control tab now, so the panel signals
    # availability and the tab forces the checkbox off.
    _app()

    class _LoanPolicy(_FakePolicy):
        total_loan_balance = 5_000.0

    tab = IllustrationInputsTab()
    tab.dynamic_panel.load_from_policy(_LoanPolicy())
    assert tab.dynamic_panel._ctx.has_loans is True
    assert tab.dynamic_panel.exception_notice.text() == ""
    assert tab.exception_prem_check.isEnabled() is True
    assert tab.exception_prem_check.isChecked() is True

    shadow_tab = IllustrationInputsTab()
    shadow_tab.dynamic_panel.load_from_policy(_LoanPolicy(), has_shadow=True)
    assert "shadow account" in shadow_tab.dynamic_panel.exception_notice.text()
    assert shadow_tab.exception_prem_check.isEnabled() is False
    assert shadow_tab.exception_prem_check.isChecked() is False
    assert "shadow account" in shadow_tab.exception_prem_check.toolTip()
    assert shadow_tab.export_options().allow_exception_prems is False


def test_context_bar_shows_policy_debt_at_right_end():
    # Policy Debt anchors the right end of the dark context strip — the
    # policy's total_loan_balance (all six loan buckets, principal + accrued),
    # money-formatted like the bar's Face Amount. Live PolicyInformation
    # returns a Decimal; the label must take it as-is.
    from decimal import Decimal

    _app()

    class _LoanPolicy(_FakePolicy):
        total_loan_balance = Decimal("12345.67")

    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_LoanPolicy())
    assert tab.banner_policy_debt_label.text() == "12,346"


def test_context_bar_policy_debt_shows_zero_when_loan_free():
    # No debt → "0", never a hidden field (_FakePolicy has no
    # total_loan_balance at all — the missing-attribute case reads as 0 too).
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_FakePolicy())
    assert tab.banner_policy_debt_label.text() == "0"


def test_min_level_available_for_loan_policy():
    # The Prem to Maturity solver is loan-capable (it applies premium to the loan
    # first), so the premium-type dropdown offers it even with a loan outstanding.
    _app()

    class _LoanPolicy(_FakePolicy):
        total_loan_balance = 5_000.0

    panel = DynamicInputsPanel()
    panel.load_from_policy(_LoanPolicy())
    row = panel.premium_section.rows()[0]
    options = [row.type_combo.itemText(i) for i in range(row.type_combo.count())]
    assert options == [
        "INPUT", "Max Level Allowed", "Prem to Maturity", "Monthly Deduction",
        "Solve"]


def test_new_premium_row_defaults_span_to_maturity():
    # Typing a start year on a fresh premium row fills For Years / To Age out
    # to maturity (the user narrows it afterwards if they want less).
    panel = _panel()
    row = panel.premium_section.add_row()
    row.year_edit.set_value(20)
    row._year_edited()
    assert row.for_years_edit.value() == 52    # years 20..71 (maturity 121 @ issue 50)
    assert row.to_age_edit.value() == 121

    # Entering by age works the same way.
    other = panel.premium_section.add_row()
    other.age_edit.set_value(90)
    other._age_edited()
    assert other.year() == 41                  # age 90 -> policy year 41
    assert other.to_age_edit.value() == 121

    # An already-set span is respected — moving the year keeps For Years.
    row.for_years_edit.set_value(5)
    row._for_years_edited()
    row.year_edit.set_value(25)
    row._year_edited()
    assert row.for_years_edit.value() == 5


def test_loan_row_span_stays_empty():
    # Only premiums default the span to maturity.
    panel = _panel()
    row = panel.loan_section.rows()[0]
    row.year_edit.set_value(10)
    row._year_edited()
    assert row.for_years_edit.value() is None
    assert row.to_age_edit.value() is None


def test_loan_and_withdrawal_modes_default_to_annual():
    # Loans and Withdrawals default their Mode to Annual; Premiums follow the
    # policy billing mode and Loan Repayments keep the Monthly default.
    panel = _panel()
    assert panel.loan_section.rows()[0].mode() == "A"
    assert panel.withdrawal_section.rows()[0].mode() == "A"
    assert panel.premium_section.rows()[0].mode() == "M"
    assert panel.repayment_section.rows()[0].mode() == "M"

    # Rows added with ＋ inherit the section default too.
    assert panel.loan_section.add_row().mode() == "A"
    assert panel.withdrawal_section.add_row().mode() == "A"
    assert panel.repayment_section.add_row().mode() == "M"

    # A fresh policy load resets a user-changed mode back to the default.
    panel.loan_section.rows()[0].mode_combo.setCurrentText("Q")
    panel.load_from_policy(_FakePolicy())
    assert panel.loan_section.rows()[0].mode() == "A"


def test_allow_gp_exception_premium_checked_by_default():
    # Allow GP Exception Premium lives in the Illustration Control tab's Run
    # Controls and is on by default for a normal (non-shadow) policy.
    _app()
    tab = IllustrationInputsTab()
    tab.dynamic_panel.load_from_policy(_FakePolicy())
    assert tab.exception_prem_check.isChecked() is True
    assert tab.export_options().allow_exception_prems is True


def test_max_level_premium_defaults_and_changes_with_mode():
    panel = _panel()
    row = panel.premium_section.rows()[0]

    assert [row.type_combo.itemText(i) for i in range(row.type_combo.count())] == [
        "INPUT", "Max Level Allowed", "Prem to Maturity", "Monthly Deduction",
        "Solve"]

    # Forecast is policy year 7, month 8, so the current year still has modes
    # left (5 monthly / 1 quarterly), which the payment count now includes:
    # monthly = 43*12 + 5 = 521, quarterly = 43*4 + 1 = 173, annual = 43.
    row.type_combo.setCurrentText("Max Level Allowed")
    assert row.amount_edit.isReadOnly()
    assert abs(row.amount() - 47600.0 / 521) < 0.005      # 91.36 monthly

    row.mode_combo.setCurrentText("Q")
    assert abs(row.amount() - 47600.0 / 173) < 0.005      # 275.14 quarterly

    row.mode_combo.setCurrentText("A")
    assert abs(row.amount() - 47600.0 / 43) < 0.005       # 1,106.98 annual

    # The displayed amount is only a closed-form ESTIMATE — the authoritative
    # premium is solved on Run Values (so face/DBO changes can move the
    # guidelines). The export therefore carries NO premium schedule for the
    # row; main_window reads the request and layers the solved premium in.
    row.mode_combo.setCurrentText("Q")
    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    premium_schedule = [t for t in input_set.scheduled_transactions if t.kind == TransactionKind.PREMIUM]
    assert premium_schedule == []
    assert panel.max_level_request() == {"start_year": 7, "mode": "Q"}


def test_max_level_premium_uses_attained_age_and_age_100_cap():
    class UF002047Policy(_FakePolicy):
        attained_age = 43
        maturity_age = 95
        glp = 2936.85
        accumulated_glp = 55800.15
        premiums_paid_to_date = 8720.0
        withdrawals_to_date = 0.0

    _app()
    panel = DynamicInputsPanel()
    panel.load_from_policy(UF002047Policy())
    row = panel.premium_section.rows()[0]
    row.type_combo.setCurrentText("Max Level Allowed")
    row.mode_combo.setCurrentText("A")

    # GLP is monthly-normalized: floor(2936.85/12, 2)*12 = 2936.76, so the max
    # annual level is ((55800.15 + 2936.76*51) - 8720) / 51 = 3,859.90.
    assert abs(row.amount() - 3859.90) < 0.005


def test_max_level_premium_hidden_for_cvat():
    class CvatPolicy(_FakePolicy):
        def_of_life_ins = "CVAT"

    _app()
    panel = DynamicInputsPanel()
    panel.load_from_policy(CvatPolicy())
    row = panel.premium_section.rows()[0]

    # CVAT has no guideline premium test, so Max Level (guideline-room math) is
    # hidden — but Prem to Maturity still solves (with exceptions off).
    assert [row.type_combo.itemText(i) for i in range(row.type_combo.count())] == [
        "INPUT", "Prem to Maturity", "Monthly Deduction", "Solve"]


def test_shadow_level_premium_offered_for_shadow_policies():
    _app()
    panel = DynamicInputsPanel()
    panel.load_from_policy(_FakePolicy(), has_shadow=True)
    row = panel.premium_section.rows()[0]

    assert [row.type_combo.itemText(i) for i in range(row.type_combo.count())] == [
        "INPUT", "Max Level Allowed", "Prem to Maturity",
        "Prem to Shadow Maturity", "Monthly Deduction", "Solve"]

    # Selecting the shadow type surfaces it through shadow_level_request.
    row.type_combo.setCurrentText("Prem to Shadow Maturity")
    request = panel.shadow_level_request()
    assert request is not None
    assert request["mode"] == row.mode()

    # A ceased-but-present type-A benefit still offers the type (the run
    # explains why it can't solve); a policy with no shadow history doesn't.
    panel.load_from_policy(_FakePolicy(), has_shadow=False, shadow_ceased=True)
    row = panel.premium_section.rows()[0]
    types = [row.type_combo.itemText(i) for i in range(row.type_combo.count())]
    assert "Prem to Shadow Maturity" in types

    panel.load_from_policy(_FakePolicy())
    row = panel.premium_section.rows()[0]
    types = [row.type_combo.itemText(i) for i in range(row.type_combo.count())]
    assert "Prem to Shadow Maturity" not in types


def _set_window(row, start_year: int, for_years: int):
    """Set a premium-style row's year window (start + For Years)."""
    row.year_edit.set_value(start_year)
    row._year_edited()
    row.for_years_edit.set_value(for_years)
    row._for_years_edited()


def test_monthly_deduction_row_bounds_its_window_and_later_premium_applies():
    # Bug repro: a Monthly-Deduction premium row must be active ONLY for its
    # year window; a premium row AFTER the window must apply normally (a $0
    # INPUT row = no premium). INPUT $250 years 7-9, Monthly Deduction years
    # 10-11, then INPUT $0 years 12-15.
    _app()
    tab = IllustrationInputsTab()
    tab.dynamic_panel.load_from_policy(_FakePolicy())
    panel = tab.dynamic_panel

    r0 = panel.premium_section.rows()[0]
    r0.type_combo.setCurrentText("INPUT")
    _set_window(r0, 7, 3)
    r0.amount_edit.set_value(250.0, decimals=2)

    r1 = panel.premium_section.add_row()
    r1.type_combo.setCurrentText("Monthly Deduction")
    _set_window(r1, 10, 2)

    r2 = panel.premium_section.add_row()
    r2.type_combo.setCurrentText("INPUT")
    _set_window(r2, 12, 4)
    r2.amount_edit.set_value(0.0, decimals=2)

    # The MD window is exactly the row's year range — start through To Age —
    # not open-ended to maturity.
    assert panel.monthly_deduction_windows() == [(10, 11)]
    opts = tab.export_options()
    assert opts.pay_monthly_deduction is True
    assert opts.monthly_deduction_windows == [(10, 11)]

    # The later $0 INPUT row still exports as a scheduled premium (no premium),
    # and the MD row itself is not scheduled as a premium — the gap between the
    # $250 window and the $0 row is zero-filled, covering the MD window.
    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    prem = {t.policy_year: t.amount for t in input_set.scheduled_transactions
            if t.kind == TransactionKind.PREMIUM}
    assert prem.get(12) == 0.0          # the "no premium after MD" row
    assert prem.get(10) == 0.0          # MD window carries no scheduled premium


def test_monthly_deduction_multiple_windows_export():
    # Two MD rows -> two bounded windows, each engaging on its own range.
    _app()
    tab = IllustrationInputsTab()
    tab.dynamic_panel.load_from_policy(_FakePolicy())
    panel = tab.dynamic_panel

    r0 = panel.premium_section.rows()[0]
    r0.type_combo.setCurrentText("Monthly Deduction")
    _set_window(r0, 10, 2)

    r1 = panel.premium_section.add_row()
    r1.type_combo.setCurrentText("Monthly Deduction")
    _set_window(r1, 20, 3)

    assert panel.monthly_deduction_windows() == [(10, 11), (20, 22)]
    assert tab.export_options().monthly_deduction_windows == [(10, 11), (20, 22)]


def test_monthly_deduction_final_row_runs_to_maturity():
    # An MD row left spanning to maturity (the default fresh-row span) exports a
    # window whose end is the maturity year — it runs to the end as before.
    _app()
    tab = IllustrationInputsTab()
    tab.dynamic_panel.load_from_policy(_FakePolicy())
    panel = tab.dynamic_panel

    row = panel.premium_section.rows()[0]
    row.type_combo.setCurrentText("Monthly Deduction")
    row.year_edit.set_value(30)
    row._year_edited()                  # fresh row spans to maturity

    maturity_year = panel._ctx.maturity_year
    assert panel.monthly_deduction_windows() == [(30, maturity_year)]


def test_inputs_tab_exports_illustrated_rate_override_from_gint():
    _app()
    tab = IllustrationInputsTab()

    tab.load_data_from_policy(_FakePolicy())
    overrides = tab.export_inforce_overrides()

    assert overrides.current_interest_rate == 0.03


def test_exact_days_unchecked_exports_monthly_compounding_override():
    _app()
    tab = IllustrationInputsTab()

    assert tab.exact_days_check.isChecked() is False
    assert tab.export_options().exact_days_interest is False

    tab.exact_days_check.setChecked(True)
    assert tab.export_options().exact_days_interest is True


def test_scenario_builder_applies_current_interest_rate_override():
    base_policy = IllustrationPolicyData(current_interest_rate=0.04)

    scenario = build_illustration_scenario(
        base_policy,
        inforce_overrides=InforceOverrideSet(current_interest_rate=0.03),
    )

    assert scenario.base_policy.current_interest_rate == 0.04
    assert scenario.projectable_policy.current_interest_rate == 0.03


def test_scenario_builder_applies_sweep_account_min_override():
    base_policy = IllustrationPolicyData(sweep_account_min=0.0)

    scenario = build_illustration_scenario(
        base_policy,
        inforce_overrides=InforceOverrideSet(sweep_account_min=500.0),
    )

    assert scenario.base_policy.sweep_account_min == 0.0
    assert scenario.projectable_policy.sweep_account_min == 500.0


def test_year_age_sync_and_bounds():
    panel = _panel()
    row = panel.premium_section.rows()[0]
    row.age_edit.setText("60")
    row._age_edited()
    assert row.year() == 11
    # Below the forecast year clamps back up.
    row.year_edit.setText("3")
    row._year_edited()
    assert row.year() == 7
    assert row.age_edit.value() == 56
    # To Age moves For Years.
    row.to_age_edit.setText("66")
    row._to_age_edited()
    assert row.for_years_edit.value() == 10    # ages 56 -> 66


def test_premium_overlap_auto_adjusts_prior_span_and_gap_emits_zero_schedule():
    panel = _panel()
    section = panel.premium_section
    first = section.rows()[0]
    first.year_edit.setText("7")
    first._year_edited()
    first.for_years_edit.setText("3")          # years 7-9
    first._for_years_edited()
    second = section.add_row()
    second.year_edit.setText("9")              # overlaps year 9
    second._year_edited()
    second.amount_edit.setText("500")
    assert not section.has_overlap()
    assert first.end_year() == 8
    assert first.for_years_edit.value() == 2
    assert first.to_age_edit.value() == 58

    second.year_edit.setText("12")             # gap: years 10-11 unpaid
    second._year_edited()
    second.for_years_edit.setText("2")
    second._for_years_edited()
    assert not section.has_overlap()

    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    premiums = [t for t in input_set.scheduled_transactions if t.kind == TransactionKind.PREMIUM]
    by_year = {t.policy_year: t.amount for t in premiums}
    # The current year (7) is handled as DATED payments from the forecast
    # date; its schedule slot is the billing-silencing zero.
    assert by_year[7] == 0.0
    dated = [t for t in input_set.dated_transactions if t.kind == TransactionKind.PREMIUM]
    assert dated and min(t.effective_date for t in dated) == date(2026, 6, 9)
    assert by_year[8] > 0                      # the rest of the first span schedules
    assert by_year[9] == 0.0                   # gap zero
    assert by_year[12] == 500.0
    assert by_year[14] == 0.0                  # termination zero after year 13


def test_premium_age_auto_adjusts_prior_span():
    panel = _panel()
    section = panel.premium_section
    first = section.rows()[0]
    second = section.add_row()

    second.age_edit.setText("65")
    second._age_edited()

    assert second.year() == 16
    assert not section.has_overlap()
    assert first.end_year() == 15
    assert first.for_years_edit.value() == 9
    assert first.to_age_edit.value() == 65


def test_added_row_continues_from_prior_to_age():
    # ＋ starts the new row where the previous span ends: its Age is the prior
    # row's To Age (year = the year after the prior span).
    panel = _panel()
    section = panel.loan_section
    first = section.rows()[0]
    first.year_edit.set_value(10)
    first._year_edited()
    first.for_years_edit.set_value(5)          # years 10..14, to age 64
    first._for_years_edited()

    row = section.add_row()
    assert row.year() == 15
    assert row.age_edit.value() == 64          # prior row's To Age
    assert row.for_years_edit.value() is None  # loans leave the span open
    assert not section.has_overlap()


def test_added_premium_row_prefills_and_spans_to_maturity():
    panel = _panel()
    section = panel.premium_section
    first = section.rows()[0]
    first.for_years_edit.set_value(3)          # years 7..9
    first._for_years_edited()

    row = section.add_row()
    assert row.year() == 10
    assert row.age_edit.value() == 59
    assert row.to_age_edit.value() == 121      # premiums default to maturity
    assert not section.has_overlap()


def test_added_row_blank_when_prior_row_reaches_maturity():
    # The default premium row already runs to maturity (To Age 121) — the new
    # row stays blank and waits for the user.
    panel = _panel()
    row = panel.premium_section.add_row()
    assert row.year() is None
    assert row.age_edit.value() is None


def test_overlap_shows_nonblocking_notice(monkeypatch):
    from types import SimpleNamespace

    calls = []
    monkeypatch.setattr(
        "suiteview.illustration.ui.inputs_dynamic.QToolTip",
        SimpleNamespace(showText=lambda *args, **kwargs: calls.append(args)))
    panel = _panel()
    section = panel.loan_section
    first = section.rows()[0]
    first.year_edit.set_value(10)
    first._year_edited()
    first.for_years_edit.set_value(5)          # years 10..14
    first._for_years_edited()
    second = section.add_row()                 # prefilled to year 15 — clean
    assert calls == []

    second.year_edit.set_value(12)             # overlaps years 10..14
    second._year_edited()
    assert section.has_overlap()
    assert len(calls) == 1                     # notified once, non-blocking

    second.year_edit.set_value(13)             # still overlapping — no repeat
    second._year_edited()
    assert len(calls) == 1

    second.year_edit.set_value(20)             # cleared
    second._year_edited()
    assert not section.has_overlap()
    second.year_edit.set_value(12)             # a NEW overlap notifies again
    second._year_edited()
    assert len(calls) == 2


def test_annual_premium_current_year_not_applied_on_forecast_date():
    """An annual premium whose anniversary already passed must NOT be
    re-applied on the forecast date; the first payment is next year's
    anniversary (handled by the year schedule, not a dated transaction)."""
    panel = _panel()
    row = panel.premium_section.rows()[0]
    row.mode_combo.setCurrentText("A")         # annual mode

    input_set = IllustrationInputSet()
    panel.collect_into(input_set)

    # No dated premium lands in the current policy year (year 7): the year-7
    # anniversary (2025-11-09) is before the forecast date (2026-06-09) and
    # the next annual due date (2026-11-09) belongs to year 8.
    dated = [t for t in input_set.dated_transactions if t.kind == TransactionKind.PREMIUM]
    assert dated == []

    # The current year's schedule slot is the billing-silencing zero, and the
    # premium resumes as a year schedule from year 8 (anniversary 2026-11-09).
    premiums = [t for t in input_set.scheduled_transactions if t.kind == TransactionKind.PREMIUM]
    by_year = {t.policy_year: t.amount for t in premiums}
    assert by_year[7] == 0.0
    assert by_year[8] > 0


def test_withdrawals_expand_to_monthliversary_dates():
    panel = _panel()
    row = panel.withdrawal_section.rows()[0]
    row.year_edit.setText("11")
    row._year_edited()
    row.amount_edit.setText("1000")
    row.mode_combo.setCurrentText("A")
    row.for_years_edit.setText("1")
    row._for_years_edited()

    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    wds = [t for t in input_set.dated_transactions if t.kind == TransactionKind.WITHDRAWAL]
    assert len(wds) == 1
    assert wds[0].effective_date == date(2029, 11, 9)   # year-11 anniversary
    assert wds[0].amount == 1000.0
    assert wds[0].subtype == "net"                      # basis defaults to Net


def test_withdrawal_basis_toggle_defaults_net_and_exports_gross():
    # Each withdrawal row ends with a compact Net/Gross combo, defaulting to
    # Net; the chosen basis rides the dated transaction's subtype. Other
    # transaction sections have no basis control and export a blank subtype.
    panel = _panel()
    row = panel.withdrawal_section.rows()[0]
    assert row.basis_combo is not None
    assert row.basis_combo.currentText() == "Net"
    assert row.basis() == "net"
    assert panel.loan_section.rows()[0].basis_combo is None

    row.year_edit.setText("11")
    row._year_edited()
    row.amount_edit.setText("500")
    row.mode_combo.setCurrentText("A")
    row.for_years_edit.setText("2")
    row._for_years_edited()
    row.basis_combo.setCurrentText("Gross")

    entries = panel.withdrawal_section.entries()
    assert entries == [{
        "year": 11, "end_year": 12, "amount": 500.0, "value": None,
        "mode": "A", "type": "Input", "basis": "gross",
    }]

    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    wds = [t for t in input_set.dated_transactions if t.kind == TransactionKind.WITHDRAWAL]
    assert [t.subtype for t in wds] == ["gross", "gross"]

    # A fresh policy load resets the toggle back to Net.
    panel.load_from_policy(_FakePolicy())
    assert panel.withdrawal_section.rows()[0].basis() == "net"


def test_change_sections_export_policy_changes():
    panel = _panel()
    face = panel.face_section.rows()[0]
    face.year_edit.setText("9")
    face._year_edited()
    face.amount_edit.setText("75000")

    rc = panel.rateclass_section.rows()[0]
    rc.year_edit.setText("10")
    rc._year_edited()
    rc.value_combo.setCurrentIndex(1)          # "P"

    table = panel.table_section.rows()[0]
    table.year_edit.setText("10")
    table._year_edited()
    table.value_combo.setCurrentIndex(0)       # "0" = remove rating

    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    kinds = {(c.kind, c.effective_date) for c in input_set.policy_changes}
    assert (PolicyChangeKind.FACE_AMOUNT, date(2027, 11, 9)) in kinds
    assert (PolicyChangeKind.RATE_CLASS, date(2028, 11, 9)) in kinds
    assert (PolicyChangeKind.SUBSTANDARD, date(2028, 11, 9)) in kinds


def test_current_year_change_lands_on_forecast_date():
    panel = _panel()
    face = panel.face_section.rows()[0]
    face.year_edit.setText("7")                # current policy year
    face._year_edited()
    face.amount_edit.setText("75000")

    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    change = next(c for c in input_set.policy_changes
                  if c.kind == PolicyChangeKind.FACE_AMOUNT)
    # The year-7 anniversary (2025-11-09) is in the past — the change takes
    # effect on the forecast date instead.
    assert change.effective_date == date(2026, 6, 9)


def test_level_types_keep_face_dbo_and_riders_enabled():
    # Both level types lock withdrawals/loans/repayments (and the rate-class /
    # table change sections) but keep Face Amount / DB Option changes AND the
    # riders panel editable — clients want to see how a face reduction, DBO
    # switch, or rider drop moves the solved premium. (A rider change after
    # the forecast date under Max Level raises the same caveat strip as a
    # face/DBO change.)
    panel = _panel()
    row = panel.premium_section.rows()[0]

    for level_type in ("Prem to Maturity", "Max Level Allowed"):
        row.type_combo.setCurrentText(level_type)
        assert panel.face_section.isEnabled() is True
        assert panel.dbo_section.isEnabled() is True
        assert panel.riders_panel.isEnabled() is True
        for section in (panel.loan_section, panel.withdrawal_section,
                        panel.repayment_section, panel.rateclass_section,
                        panel.table_section):
            assert section.isEnabled() is False

    row.type_combo.setCurrentText("INPUT")
    for section in (panel.face_section, panel.dbo_section, panel.loan_section,
                    panel.withdrawal_section, panel.repayment_section,
                    panel.rateclass_section, panel.table_section,
                    panel.riders_panel):
        assert section.isEnabled() is True


def test_min_level_collects_face_and_dbo_changes_only():
    # With Prem to Maturity selected the export still carries the Face Amount /
    # DB Option change events (they feed the solve), while the locked sections
    # — withdrawals, loans, repayments, rate class — stay excluded even if
    # they hold values.
    panel = _panel()
    panel.premium_section.rows()[0].type_combo.setCurrentText("Prem to Maturity")

    face = panel.face_section.rows()[0]
    face.year_edit.setText("9")
    face._year_edited()
    face.amount_edit.setText("75000")

    dbo = panel.dbo_section.rows()[0]
    dbo.year_edit.setText("10")
    dbo._year_edited()
    dbo.value_combo.setCurrentIndex(1)         # "B"

    # Values left in locked sections must not leak into the export.
    wd = panel.withdrawal_section.rows()[0]
    wd.year_edit.setText("11")
    wd._year_edited()
    wd.amount_edit.setText("1000")
    loan = panel.loan_section.rows()[0]
    loan.year_edit.setText("12")
    loan._year_edited()
    loan.amount_edit.setText("2000")
    rc = panel.rateclass_section.rows()[0]
    rc.year_edit.setText("10")
    rc._year_edited()
    rc.value_combo.setCurrentIndex(1)

    input_set = IllustrationInputSet()
    panel.collect_into(input_set)

    changes = {(c.kind, c.effective_date, c.value) for c in input_set.policy_changes}
    assert (PolicyChangeKind.FACE_AMOUNT, date(2027, 11, 9), 75000.0) in changes
    assert (PolicyChangeKind.DB_OPTION, date(2028, 11, 9), "B") in changes
    assert not any(c.kind == PolicyChangeKind.RATE_CLASS for c in input_set.policy_changes)
    kinds = {t.kind for t in input_set.dated_transactions}
    kinds |= {t.kind for t in input_set.scheduled_transactions}
    assert TransactionKind.WITHDRAWAL not in kinds
    assert TransactionKind.LOAN not in kinds
    assert TransactionKind.LOAN_REPAYMENT not in kinds


def test_max_level_collects_face_and_dbo_changes_only():
    # Max Level Allowed honors the Face Amount / DB Option change events (they
    # alter the guideline premiums the solve is bounded by), while the locked
    # sections — withdrawals, loans, repayments, rate class — stay excluded
    # even if they hold values.
    panel = _panel()
    panel.premium_section.rows()[0].type_combo.setCurrentText("Max Level Allowed")

    face = panel.face_section.rows()[0]
    face.year_edit.setText("9")
    face._year_edited()
    face.amount_edit.setText("75000")

    dbo = panel.dbo_section.rows()[0]
    dbo.year_edit.setText("10")
    dbo._year_edited()
    dbo.value_combo.setCurrentIndex(1)         # "B"

    # Values left in locked sections must not leak into the export.
    wd = panel.withdrawal_section.rows()[0]
    wd.year_edit.setText("11")
    wd._year_edited()
    wd.amount_edit.setText("1000")
    loan = panel.loan_section.rows()[0]
    loan.year_edit.setText("12")
    loan._year_edited()
    loan.amount_edit.setText("2000")
    rc = panel.rateclass_section.rows()[0]
    rc.year_edit.setText("10")
    rc._year_edited()
    rc.value_combo.setCurrentIndex(1)

    input_set = IllustrationInputSet()
    panel.collect_into(input_set)

    changes = {(c.kind, c.effective_date, c.value) for c in input_set.policy_changes}
    assert (PolicyChangeKind.FACE_AMOUNT, date(2027, 11, 9), 75000.0) in changes
    assert (PolicyChangeKind.DB_OPTION, date(2028, 11, 9), "B") in changes
    assert not any(c.kind == PolicyChangeKind.RATE_CLASS for c in input_set.policy_changes)
    kinds = {t.kind for t in input_set.dated_transactions}
    kinds |= {t.kind for t in input_set.scheduled_transactions}
    assert TransactionKind.WITHDRAWAL not in kinds
    assert TransactionKind.LOAN not in kinds
    assert TransactionKind.LOAN_REPAYMENT not in kinds


def test_min_level_solve_projection_includes_policy_changes():
    # The Prem to Maturity solver must project on the SAME policy changes the
    # user entered — every bracketing/bisection run carries the base input
    # set's policy_changes through, so the solved minimum premium reflects a
    # face reduction or DBO switch.
    from types import SimpleNamespace

    from suiteview.illustration.core.solve_level_to_exception import (
        solve_level_to_exception,
    )
    from suiteview.illustration.models.input_set import PolicyChangeEvent

    policy = IllustrationPolicyData(def_of_life_ins="GPT", maturity_age=121,
                                    billing_frequency=1, modal_premium=100.0)
    change = PolicyChangeEvent(
        kind=PolicyChangeKind.FACE_AMOUNT, effective_date=date(2027, 11, 9),
        value=75000.0)
    base = IllustrationInputSet(policy_changes=[change])

    captured = []

    class _StubEngine:
        def project(self, _policy, *, options=None, future_inputs=None, **_kw):
            captured.append(future_inputs)
            # Every premium "survives" so the solve returns at zero premium.
            return [SimpleNamespace(
                attained_age=121, av_end_of_month=1.0, premiums_to_date=0.0,
                exception_prem_mode=False, gp_exception_prem_gross=0.0,
                applied_loan_repayment=0.0, date=date(2096, 11, 9),
                policy_year=71)]

    result = solve_level_to_exception(
        policy, mode="M", start_policy_year=7,
        base_future_inputs=base, engine=_StubEngine())

    assert result.premium == 0.0
    assert captured, "the solve never projected"
    for future in captured:
        assert future.policy_changes == [change]


def test_riders_panel_excludes_base_coverages():
    """Riders & Benefits should list riders only — never base coverage
    segments (is_base, including base increases beyond phase 1)."""
    from types import SimpleNamespace

    def _cov(phase, is_base):
        return SimpleNamespace(
            cov_pha_nbr=phase, form_number=f"F{phase}", plancode="1U143900",
            issue_date=date(2019, 11, 9), face_amount=10000.0, issue_age=50,
            rate_class="N", cov_status="0", is_base=is_base, rate=0.5,
            annual_premium=20.0)

    class PolicyWithBaseAndRider(_FakePolicy):
        def get_coverages(self):
            # phase 1 base, phase 2 base increase, phase 3 rider
            return [_cov(1, True), _cov(2, True), _cov(3, False)]

    _app()
    panel = DynamicInputsPanel()
    panel.load_from_policy(PolicyWithBaseAndRider())

    cov_keys = {k for k in panel.riders_panel._buttons if k.startswith("cov:")}
    assert cov_keys == {"cov:3"}


def test_riders_panel_enables_renewal_rated_benefit():
    """A waiver benefit (e.g. ULDW91) has a zero issue rate (BNF_ANN_PPU_AMT)
    but a real charge in the renewal-rate segment — it must be adjustable.
    Free ABR (#-type) benefits stay disabled."""
    from types import SimpleNamespace

    def _ben(type_cd, subtype_cd, form, coi_rate, renewal_rate):
        return SimpleNamespace(
            cov_pha_nbr=1, benefit_code=type_cd + subtype_cd,
            benefit_type_cd=type_cd, benefit_subtype_cd=subtype_cd,
            benefit_desc=type_cd, form_number=form,
            issue_date=date(2019, 11, 9), cease_date=None,
            units=250.0, benefit_amount=250000.0, issue_age=50,
            coi_rate=coi_rate, renewal_rate=renewal_rate)

    class PolicyWithWaiver(_FakePolicy):
        def get_benefits(self):
            return [
                _ben("#", "4", "ABR14-TM", None, None),
                _ben("3", "9", "ULDW91", None, 7100.0),
            ]

    _app()
    panel = DynamicInputsPanel()
    panel.load_from_policy(PolicyWithWaiver())

    assert not panel.riders_panel._buttons["ben:#4:1"].isEnabled()
    waiver_btn = panel.riders_panel._buttons["ben:39:1"]
    assert waiver_btn.isEnabled()
    assert waiver_btn.toolTip() == "Keep / change / drop this rider"


def test_suspended_banner():
    _app()

    class Suspended(_FakePolicy):
        status_code = "2"

    panel = DynamicInputsPanel()
    panel.load_from_policy(Suspended())
    assert panel.suspended_banner.isVisible() or panel.suspended_banner.text()
    assert "SUSPENDED" in panel.suspended_banner.text()
    assert "05/09/2026" in panel.suspended_banner.text()   # valuation date
    assert "06/09/2026" in panel.suspended_banner.text()   # forecast date


def test_excess_repayment_toggle_states_and_placement():
    panel = _panel()

    # Two exclusive radio buttons: exactly one selected, "Stop at payoff" by
    # default (the engine's flag-off behavior — the excess is discarded).
    assert panel.excess_stop_radio.isChecked() is True
    assert panel.excess_apply_radio.isChecked() is False
    assert panel.excess_repayment_as_premium() is False

    panel.excess_apply_radio.setChecked(True)
    assert panel.excess_stop_radio.isChecked() is False
    assert panel.excess_repayment_as_premium() is True

    panel.excess_stop_radio.setChecked(True)
    assert panel.excess_apply_radio.isChecked() is False
    assert panel.excess_repayment_as_premium() is False

    # The radios live at the TOP of the Loan Repayments group (a header
    # widget above the column captions), mirroring the Premiums lumpsum row.
    header_item = panel.repayment_section.layout().itemAt(0)
    header_widget = header_item.widget()
    assert header_widget is not None
    assert panel.excess_stop_radio in header_widget.findChildren(type(panel.excess_stop_radio))


def test_sections_pack_to_top_with_trailing_stretch():
    # Every DynamicSection ends with a stretch so grid-row surplus height
    # collects at the bottom instead of spreading the controls apart (the
    # Loans group next to the taller Premiums group showed this).
    panel = _panel()
    for section in (panel.premium_section, panel.loan_section,
                    panel.withdrawal_section, panel.repayment_section):
        layout = section.layout()
        last = layout.itemAt(layout.count() - 1)
        assert last.spacerItem() is not None


def test_max_level_caveat_banner_flags_post_forecast_policy_changes():
    # Max Level Allowed spreads the guideline room measured at ZERO premium;
    # a policy change AFTER the forecast date can recalc the guidelines off
    # premium-dependent state, so combining the two shows a caveat strip up
    # top. Changes ON the forecast date are safe. The run stays allowed.
    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_FakePolicy())
    assert not tab.max_level_caveat_banner.isVisibleTo(tab)

    # Max Level selected, no policy changes -> no caveat.
    prem_row = tab.dynamic_panel.premium_section.rows()[0]
    prem_row.type_combo.setCurrentText("Max Level Allowed")
    assert tab.dynamic_panel.max_level_request() is not None
    assert not tab.max_level_caveat_banner.isVisibleTo(tab)

    # A face change AFTER the forecast year -> caveat visible.
    face_row = tab.dynamic_panel.face_section.rows()[0]
    face_row.year_edit.set_value(9)                # anniversary > forecast
    face_row.amount_edit.set_value(40_000, decimals=0)
    tab._refresh_max_level_caveat()                # typing triggers this live
    assert tab.max_level_change_caveat_active()
    assert tab.max_level_caveat_banner.isVisibleTo(tab)
    assert "after the forecast date" in tab.max_level_caveat_banner.text()

    # Moved to the forecast year: the change date clamps to the forecast
    # date itself -> safe, caveat clears.
    face_row.year_edit.set_value(7)
    tab._refresh_max_level_caveat()
    assert not tab.max_level_change_caveat_active()
    assert not tab.max_level_caveat_banner.isVisibleTo(tab)

    # Post-forecast change WITHOUT Max Level -> no caveat either.
    face_row.year_edit.set_value(9)
    prem_row.type_combo.setCurrentIndex(0)         # back to the INPUT type
    assert tab.dynamic_panel.max_level_request() is None
    tab._refresh_max_level_caveat()
    assert not tab.max_level_caveat_banner.isVisibleTo(tab)


def test_solve_type_shows_criteria_group_and_builds_request():
    # Selecting the "Solve" premium type reveals the Premium Solve criteria
    # group under the Premiums rows; the row amount goes read-only (filled by
    # Run Values). The request carries the row's year/mode/span plus the
    # group's target/amount/age. The shadow target appears only on a policy
    # with an active shadow account.
    panel = _panel()
    assert not panel.solve_criteria.isVisibleTo(panel)
    targets = [panel.solve_target_combo.itemData(i)
               for i in range(panel.solve_target_combo.count())]
    assert targets == ["av", "sv"]                 # no shadow on this policy
    assert panel.solve_age_edit.value() == 100     # age-100 default

    row = panel.premium_section.rows()[0]
    row.type_combo.setCurrentText("Solve")
    assert panel.solve_criteria.isVisibleTo(panel)
    assert row.amount_edit.isReadOnly()

    panel.solve_amount_edit.set_value(100_000, decimals=2)
    panel.solve_age_edit.set_value(100)
    request = panel.solve_request()
    assert request == {
        "start_year": 7, "end_year": None,         # row span runs to maturity
        "mode": "M", "target": "av",
        "amount": 100_000.0, "at_age": 100,
    }
    # The solved value lands in the row's read-only amount field.
    panel.set_solve_amount(123.45)
    assert row.amount_edit.text() == "123.45"
    # The criteria persist into a saved case.
    solve_state = panel.capture_state()["solve"]
    assert solve_state["target"] == "av"
    assert solve_state["at_age"] == "100"

    row.type_combo.setCurrentIndex(0)              # back to INPUT
    assert not panel.solve_criteria.isVisibleTo(panel)
    assert panel.solve_request() is None

    # A shadow-account policy offers the shadow target.
    shadow_panel = DynamicInputsPanel()
    shadow_panel.load_from_policy(_FakePolicy(), has_shadow=True)
    targets = [shadow_panel.solve_target_combo.itemData(i)
               for i in range(shadow_panel.solve_target_combo.count())]
    assert targets == ["av", "sv", "shadow"]


def test_caveat_banner_sits_under_riders_and_fires_on_rider_changes():
    # The Max Level caveat strip lives at the BOTTOM of the Input panel —
    # under Riders and Benefits — so popping up never shifts the controls
    # above it. A rider change scheduled after the forecast date triggers it
    # exactly like a face/DBO change (riders flow through the exported policy
    # changes).
    from suiteview.illustration.ui.inputs_dynamic import RiderAdjustment

    _app()
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(_FakePolicy())
    layout = tab.dynamic_panel.layout()
    assert layout.itemAt(layout.count() - 1).widget() is tab.max_level_caveat_banner
    assert layout.itemAt(layout.count() - 2).widget() is tab.dynamic_panel.riders_panel

    tab.dynamic_panel.premium_section.rows()[0].type_combo.setCurrentText(
        "Max Level Allowed")
    assert not tab.max_level_caveat_banner.isVisibleTo(tab.dynamic_panel)

    # Rider drop at year 9 — the year-9 anniversary is after the forecast
    # date → caveat on. (Riders stay editable under Max Level.)
    assert tab.dynamic_panel.riders_panel.isEnabled()
    drop = RiderAdjustment()
    drop.action = RiderAdjustment.DROP
    drop.effective_year = 9
    tab.dynamic_panel.riders_panel._adjustments["cov:3"] = drop
    tab._refresh_max_level_caveat()                # panel emits changed live
    assert tab.max_level_change_caveat_active()
    assert tab.max_level_caveat_banner.isVisibleTo(tab.dynamic_panel)

    # Moved to the current year: the change clamps to the forecast date
    # itself → safe, caveat clears.
    drop.effective_year = 7
    tab._refresh_max_level_caveat()
    assert not tab.max_level_change_caveat_active()
    assert not tab.max_level_caveat_banner.isVisibleTo(tab.dynamic_panel)
