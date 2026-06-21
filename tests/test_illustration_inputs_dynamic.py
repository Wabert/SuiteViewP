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


def test_max_level_premium_defaults_and_changes_with_mode():
    panel = _panel()
    row = panel.premium_section.rows()[0]

    assert [row.type_combo.itemText(i) for i in range(row.type_combo.count())] == [
        "INPUT", "Max Level Allowed", "Min Level to Maturity"]

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

    row.mode_combo.setCurrentText("Q")
    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    premium_schedule = [t for t in input_set.scheduled_transactions if t.kind == TransactionKind.PREMIUM]
    assert any(t.policy_year == 8 and abs(t.amount - 47600.0 / 173) < 0.005 for t in premium_schedule)


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

    # CVAT has no guideline premium test — only INPUT, no Max/Min Level.
    assert [row.type_combo.itemText(i) for i in range(row.type_combo.count())] == ["INPUT"]


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
