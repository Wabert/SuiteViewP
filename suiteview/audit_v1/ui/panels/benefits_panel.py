"""
Benefits Criteria Panel
=========================
Up to 3 benefit slots with type, subtype, cease dates, A&H periods.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout

from .panel_widgets import (
    CriteriaPanel, CollapsibleSection, CheckableListBox, DateRangeRow,
    make_combo, make_form_row,
)
from ...models.audit_criteria import BenefitCriteria
from ...models.audit_constants import (
    BENEFIT_TYPE_CODES, BENEFIT_CEASE_DATE_STATUS,
    ELIMINATION_PERIOD_ACCIDENT, ELIMINATION_PERIOD_SICKNESS,
    BENEFIT_PERIOD_CODES,
)


class BenefitSlotWidget(QWidget):
    """Form for a single benefit slot."""

    def __init__(self, slot_num: int, parent=None):
        super().__init__(parent)
        self.slot_num = slot_num
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.enabled_cb = QCheckBox(f"Enable Benefit {slot_num} Filter")
        layout.addWidget(self.enabled_cb)

        # Type / Subtype
        sec = CollapsibleSection("Benefit Type")
        self.benefit_type = make_combo(BENEFIT_TYPE_CODES, fixed_width=250)
        sec.add_layout(make_form_row("Benefit Type", self.benefit_type))
        # Subtype is free-text since it varies by benefit type
        from .panel_widgets import SingleValueRow
        self.subtype = SingleValueRow("Subtype", "", 80)
        sec.add_widget(self.subtype)
        layout.addWidget(sec)

        # Cease Date
        sec2 = CollapsibleSection("Cease Date")
        self.cease_status = make_combo(BENEFIT_CEASE_DATE_STATUS, fixed_width=250)
        sec2.add_layout(make_form_row("Cease Comparison", self.cease_status))
        self.cease_date = DateRangeRow("Cease Date")
        sec2.add_widget(self.cease_date)
        layout.addWidget(sec2)

        # A&H Elimination / Benefit Periods (side by side)
        sec3 = CollapsibleSection("A&H Periods")
        ah_row1 = QWidget()
        ah1_layout = QHBoxLayout(ah_row1)
        ah1_layout.setContentsMargins(0, 0, 0, 0)
        ah1_layout.setSpacing(4)
        self.elim_accident = CheckableListBox(
            ELIMINATION_PERIOD_ACCIDENT, "Elim Period (Accident)", max_height=160
        )
        ah1_layout.addWidget(self.elim_accident)
        self.elim_sickness = CheckableListBox(
            ELIMINATION_PERIOD_SICKNESS, "Elim Period (Sickness)", max_height=160
        )
        ah1_layout.addWidget(self.elim_sickness)
        sec3.add_widget(ah_row1)
        ah_row2 = QWidget()
        ah2_layout = QHBoxLayout(ah_row2)
        ah2_layout.setContentsMargins(0, 0, 0, 0)
        ah2_layout.setSpacing(4)
        self.benefit_accident = CheckableListBox(
            BENEFIT_PERIOD_CODES, "Benefit Period (Accident)", max_height=160
        )
        ah2_layout.addWidget(self.benefit_accident)
        self.benefit_sickness = CheckableListBox(
            BENEFIT_PERIOD_CODES, "Benefit Period (Sickness)", max_height=160
        )
        ah2_layout.addWidget(self.benefit_sickness)
        sec3.add_widget(ah_row2)
        layout.addWidget(sec3)

        # Post-issue flag
        self.post_issue_cb = QCheckBox("Post-Issue (benefit added after base issue)")
        layout.addWidget(self.post_issue_cb)
        layout.addStretch()

    def write_to_benefit(self, benefit: BenefitCriteria):
        benefit.enabled = self.enabled_cb.isChecked()
        benefit.benefit_type = self.benefit_type.currentData() or ""
        benefit.subtype = self.subtype.value()
        benefit.cease_date_status = self.cease_status.currentData() or ""
        benefit.low_cease_date, benefit.high_cease_date = self.cease_date.get_range()
        benefit.elimination_period_accident = self.elim_accident.selected_codes()
        benefit.elimination_period_sickness = self.elim_sickness.selected_codes()
        benefit.benefit_period_accident = self.benefit_accident.selected_codes()
        benefit.benefit_period_sickness = self.benefit_sickness.selected_codes()
        benefit.post_issue = self.post_issue_cb.isChecked()

    def reset_from_benefit(self, benefit: BenefitCriteria):
        self.enabled_cb.setChecked(benefit.enabled)
        self.benefit_type.setCurrentIndex(0)
        self.subtype.clear()
        self.cease_status.setCurrentIndex(0)
        self.cease_date.clear()
        self.elim_accident.clear_selection()
        self.elim_sickness.clear_selection()
        self.benefit_accident.clear_selection()
        self.benefit_sickness.clear_selection()
        self.post_issue_cb.setChecked(False)


class BenefitsPanel(CriteriaPanel):
    """Benefits criteria with 3 benefit slots as sub-tabs."""

    def _build_ui(self):
        self.benefit_tabs = QTabWidget()
        self.benefit_slots = []
        for i in range(1, 4):
            slot = BenefitSlotWidget(i)
            self.benefit_slots.append(slot)
            self.benefit_tabs.addTab(slot, f"Benefit {i}")
        self.main_layout.addWidget(self.benefit_tabs)

    def write_to_criteria(self, criteria):
        self.benefit_slots[0].write_to_benefit(criteria.benefit1)
        self.benefit_slots[1].write_to_benefit(criteria.benefit2)
        self.benefit_slots[2].write_to_benefit(criteria.benefit3)

    def reset(self, criteria):
        super().reset(criteria)
        self.benefit_slots[0].reset_from_benefit(criteria.benefit1)
        self.benefit_slots[1].reset_from_benefit(criteria.benefit2)
        self.benefit_slots[2].reset_from_benefit(criteria.benefit3)
