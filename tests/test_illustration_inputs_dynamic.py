import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    PolicyChangeKind,
    TransactionKind,
)
from suiteview.illustration.ui.inputs_dynamic import (
    DynamicInputsPanel,
    PolicyContext,
)


_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


class _FakePolicy:
    """Just enough PolicyInformation surface for context_from_policy."""

    issue_date = date(2019, 11, 9)
    base_issue_age = 50
    valuation_date = date(2026, 5, 9)
    policy_year = 7
    maturity_age = 121
    billing_frequency = 1
    modal_premium = 153.56
    base_rate_class = "N"
    base_table_rating = 2
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


def test_overlap_blocks_export_and_gap_emits_zero_schedule():
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
    assert section.has_overlap()
    assert section.entries() == []

    second.year_edit.setText("12")             # gap: years 10-11 unpaid
    second._year_edited()
    second.for_years_edit.setText("2")
    second._for_years_edited()
    assert not section.has_overlap()

    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    premiums = [t for t in input_set.scheduled_transactions if t.kind == TransactionKind.PREMIUM]
    by_year = {t.policy_year: t.amount for t in premiums}
    assert by_year[7] > 0
    assert by_year[10] == 0.0                  # gap zero
    assert by_year[12] == 500.0
    assert by_year[14] == 0.0                  # termination zero after year 13


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
