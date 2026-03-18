"""
Rider Criteria Panel
======================
Up to 3 rider slots, each with plancode, person code, product codes,
date ranges, and boolean flags.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QTabWidget, QWidget, QVBoxLayout

from .panel_widgets import (
    CriteriaPanel, CollapsibleSection, DateRangeRow,
    SingleValueRow, make_combo, make_form_row,
)
from ...models.audit_criteria import RiderCriteria
from ...models.audit_constants import (
    PERSON_CODES, PRODUCT_LINE_CODES, PRODUCT_INDICATOR_CODES,
    SEX_CODES, SEX_CODES_02, RATE_CLASS_CODES,
    RIDER_CHANGE_TYPES, LIVES_COVERED_CODES,
    RIDER_PLANCODE_CRITERIA,
)


class RiderSlotWidget(QWidget):
    """Form for a single rider slot."""

    def __init__(self, slot_num: int, parent=None):
        super().__init__(parent)
        self.slot_num = slot_num
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Enable checkbox
        self.enabled_cb = QCheckBox(f"Enable Rider {slot_num} Filter")
        layout.addWidget(self.enabled_cb)

        # Core fields
        sec = CollapsibleSection("Rider Criteria")
        self.plancode = SingleValueRow("Plancode", "e.g. 7R001A", 120)
        sec.add_widget(self.plancode)
        self.person_code = make_combo(PERSON_CODES, fixed_width=160)
        sec.add_layout(make_form_row("Person Code", self.person_code))
        self.product_line = make_combo(PRODUCT_LINE_CODES, fixed_width=160)
        sec.add_layout(make_form_row("Product Line", self.product_line))
        self.product_indicator = make_combo(PRODUCT_INDICATOR_CODES, fixed_width=200)
        sec.add_layout(make_form_row("Product Indicator", self.product_indicator))
        self.change_type = make_combo(RIDER_CHANGE_TYPES, fixed_width=160)
        sec.add_layout(make_form_row("Change Type", self.change_type))
        self.lives_covered = make_combo(LIVES_COVERED_CODES, fixed_width=200)
        sec.add_layout(make_form_row("Lives Covered", self.lives_covered))
        self.additional_plan = make_combo(RIDER_PLANCODE_CRITERIA, fixed_width=200)
        sec.add_layout(make_form_row("vs Base Plancode", self.additional_plan))
        layout.addWidget(sec)

        # Sex / Rate class
        sec2 = CollapsibleSection("Sex & Rate Class")
        self.sex_code_67 = make_combo(SEX_CODES, fixed_width=160)
        sec2.add_layout(make_form_row("Sex Code (67)", self.sex_code_67))
        self.sex_code_02 = make_combo(SEX_CODES_02, fixed_width=160)
        sec2.add_layout(make_form_row("Sex Code (02)", self.sex_code_02))
        self.rateclass_67 = make_combo(RATE_CLASS_CODES, fixed_width=160)
        sec2.add_layout(make_form_row("Rate Class (67)", self.rateclass_67))
        layout.addWidget(sec2)

        # GIO / COLA
        sec3 = CollapsibleSection("Indicators")
        self.cola_combo = make_combo({"": "", "0": "No COLA", "1": "Has COLA"}, fixed_width=120)
        sec3.add_layout(make_form_row("COLA", self.cola_combo))
        self.gio_combo = make_combo(
            {"": "", "blank": "Blank", "N": "No", "Y": "Yes"}, fixed_width=120
        )
        sec3.add_layout(make_form_row("GIO/FIO", self.gio_combo))
        layout.addWidget(sec3)

        # Dates
        sec4 = CollapsibleSection("Date Ranges")
        self.issue_date = DateRangeRow("Issue Date")
        sec4.add_widget(self.issue_date)
        self.change_date = DateRangeRow("Change Date")
        sec4.add_widget(self.change_date)
        layout.addWidget(sec4)

        # Booleans
        self.post_issue_cb = QCheckBox("Post-Issue (rider issued after base)")
        self.table_rating_cb = QCheckBox("Table Rating")
        self.flat_extra_cb = QCheckBox("Flat Extra")
        layout.addWidget(self.post_issue_cb)
        layout.addWidget(self.table_rating_cb)
        layout.addWidget(self.flat_extra_cb)
        layout.addStretch()

    def write_to_rider(self, rider: RiderCriteria):
        rider.enabled = self.enabled_cb.isChecked()
        rider.plancode = self.plancode.value()
        rider.person_code = self.person_code.currentData() or ""
        rider.product_line_code = self.product_line.currentData() or ""
        rider.product_indicator = self.product_indicator.currentData() or ""
        rider.change_type = self.change_type.currentData() or ""
        rider.lives_covered_code = self.lives_covered.currentData() or ""
        rider.additional_plancode_criteria = self.additional_plan.currentData() or ""
        rider.sex_code_67 = self.sex_code_67.currentData() or ""
        rider.sex_code_02 = self.sex_code_02.currentData() or ""
        rider.rateclass_code_67 = self.rateclass_67.currentData() or ""
        rider.cola_indicator = self.cola_combo.currentData() or ""
        rider.gio_fio_indicator = self.gio_combo.currentData() or ""
        rider.low_issue_date, rider.high_issue_date = self.issue_date.get_range()
        rider.low_change_date, rider.high_change_date = self.change_date.get_range()
        rider.post_issue = self.post_issue_cb.isChecked()
        rider.table_rating = self.table_rating_cb.isChecked()
        rider.flat_extra = self.flat_extra_cb.isChecked()

    def reset_from_rider(self, rider: RiderCriteria):
        self.enabled_cb.setChecked(rider.enabled)
        self.plancode.set_value(rider.plancode)
        self.person_code.setCurrentIndex(0)
        self.product_line.setCurrentIndex(0)
        self.product_indicator.setCurrentIndex(0)
        self.change_type.setCurrentIndex(0)
        self.lives_covered.setCurrentIndex(0)
        self.additional_plan.setCurrentIndex(0)
        self.sex_code_67.setCurrentIndex(0)
        self.sex_code_02.setCurrentIndex(0)
        self.rateclass_67.setCurrentIndex(0)
        self.cola_combo.setCurrentIndex(0)
        self.gio_combo.setCurrentIndex(0)
        self.issue_date.clear()
        self.change_date.clear()
        self.post_issue_cb.setChecked(False)
        self.table_rating_cb.setChecked(False)
        self.flat_extra_cb.setChecked(False)


class RiderPanel(CriteriaPanel):
    """Rider criteria with 3 rider slots as sub-tabs."""

    def _build_ui(self):
        self.rider_tabs = QTabWidget()
        self.rider_slots = []
        for i in range(1, 4):
            slot = RiderSlotWidget(i)
            self.rider_slots.append(slot)
            self.rider_tabs.addTab(slot, f"Rider {i}")
        self.main_layout.addWidget(self.rider_tabs)

    def write_to_criteria(self, criteria):
        self.rider_slots[0].write_to_rider(criteria.rider1)
        self.rider_slots[1].write_to_rider(criteria.rider2)
        self.rider_slots[2].write_to_rider(criteria.rider3)

    def reset(self, criteria):
        super().reset(criteria)
        self.rider_slots[0].reset_from_rider(criteria.rider1)
        self.rider_slots[1].reset_from_rider(criteria.rider2)
        self.rider_slots[2].reset_from_rider(criteria.rider3)
