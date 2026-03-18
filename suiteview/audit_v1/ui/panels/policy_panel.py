"""
Policy Criteria Panel
=======================
Consolidated single-tab form providing dense, high-efficiency access to the 
most commonly used Policy (01, 51, 66) properties. Layout matches the user mockup.
"""

from __future__ import annotations

import typing
from typing import Dict

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QComboBox, QCheckBox, 
    QListWidget, QListWidgetItem, QAbstractItemView, QStyledItemDelegate
)

from .panel_widgets import CriteriaPanel

from ...models.audit_constants import (
    COMPANY_LIST, MARKET_ORG_CODES, STATE_CODES,
    AUDIT_BILLING_FORMS, GRACE_INDICATOR_CODES, OVERLOAN_INDICATOR_CODES,
    AUDIT_LAST_ENTRY_CODES, BILL_MODE_DISPLAY
)

from suiteview.polview.models.cl_polrec.policy_translations import (
    STATUS_CODES, DEF_OF_LIFE_INS_CODES, GRACE_RULE_CODES, DB_OPTION_CODES,
    DIV_OPTION_CODES, NFO_CODES, LOAN_TYPE_CODES, SUSPENSE_CODES
)

class _TightItemDelegate(QStyledItemDelegate):
    """Forces a fixed compact row height on QListWidget items."""
    ROW_H = 16

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), self.ROW_H)

MY_LIST_STYLE = """
    QListWidget {
        font-size: 11px;
        border: none;
        background-color: transparent;
        outline: none;
        padding: 0px;
        margin: 0px;
    }
    QListWidget::item {
        padding: 0px 4px;
        margin: 0px;
        border: none;
        min-height: 14px;
        max-height: 16px;
        color: #1A1A1A;
    }
    QListWidget::item:hover { background-color: rgba(0, 0, 0, 15); }
    QListWidget::item:selected { background-color: rgba(0, 0, 0, 30); font-weight: bold; }
"""


class PolicyPanel(CriteriaPanel):
    """Comprehensive single-tab Policy Criteria UI."""

    def _create_enabled_listbox(self, title: str, items_dict: Dict[str, str], visible_rows: int = None, fmt: str = "dash"):
        group = QGroupBox()
        group.setCheckable(True)
        group.setChecked(False)
        group.setTitle(title)
        
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        listbox = QListWidget()
        listbox.setStyleSheet(MY_LIST_STYLE)
        listbox.setItemDelegate(_TightItemDelegate(listbox))
        listbox.setUniformItemSizes(True)
        listbox.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        
        # Populate items. UserRole stores the actual data code.
        for code, label in items_dict.items():
            text = f"{code} - {label}" if (fmt == "dash" and label) else code
            if fmt == "plain": text = label
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, code)
            listbox.addItem(it)

        n_items = listbox.count()
        if visible_rows is None:
            visible_rows = n_items
            if visible_rows < 3: visible_rows = 3
            if visible_rows > 12: visible_rows = 12
            
        listbox.setFixedHeight((visible_rows * _TightItemDelegate.ROW_H) + 2)
        layout.addWidget(listbox)
        
        # Disable list if group is unchecked, enable on check
        listbox.setEnabled(False)
        group.toggled.connect(listbox.setEnabled)
        # Clear selection if unchecking
        group.toggled.connect(lambda checked, lw=listbox: lw.clearSelection() if not checked else None)
        
        return group, listbox

    def _create_range_row(self, layout: QGridLayout, row: int, title: str) -> typing.Tuple[QLineEdit, QLineEdit]:
        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(lbl_title, row, 0)
        
        low_input = QLineEdit()
        low_input.setPlaceholderText("Min")
        low_input.setFixedWidth(105)
        layout.addWidget(low_input, row, 1)
        
        lbl = QLabel("to")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl, row, 2)
        
        high_input = QLineEdit()
        high_input.setPlaceholderText("Max")
        high_input.setFixedWidth(105)
        layout.addWidget(high_input, row, 3)
        return low_input, high_input


    def _build_ui(self):
        # We will add columns directly to the main layout
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(8)

        # -- Column 1: General Info & Dates --
        col1 = QVBoxLayout()
        
        # Identifiers
        self.group_ids = QGroupBox("Identifiers")
        grid_ids = QGridLayout(self.group_ids)
        grid_ids.setContentsMargins(4, 14, 4, 4)
        grid_ids.setHorizontalSpacing(6)
        grid_ids.setVerticalSpacing(2)
        
        def add_id_row(r_idx, title, widget_or_layout):
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid_ids.addWidget(lbl, r_idx, 0)
            if isinstance(widget_or_layout, QWidget):
                grid_ids.addWidget(widget_or_layout, r_idx, 1)
            else:
                grid_ids.addLayout(widget_or_layout, r_idx, 1)

        pol_layout = QHBoxLayout()
        pol_layout.setContentsMargins(0, 0, 0, 0)
        pol_layout.setSpacing(4)
        self.pol_prefix = QLineEdit()
        self.pol_num = QLineEdit()
        pol_layout.addWidget(self.pol_prefix)
        pol_layout.addWidget(self.pol_num)
        add_id_row(0, "Policy:", pol_layout)

        self.company_combo = QComboBox()
        self.company_combo.addItems(COMPANY_LIST)
        add_id_row(1, "Company:", self.company_combo)
        
        self.market_combo = QComboBox()
        # Market org choices
        market_list = [""] + [f"{k} - {v}" for k, v in MARKET_ORG_CODES.items()]
        self.market_combo.addItems(market_list)
        add_id_row(2, "Market:", self.market_combo)
        
        self.branch_entry = QLineEdit()
        add_id_row(3, "3 div Branch #:", self.branch_entry)
        
        self.loan_charge_entry = QLineEdit()
        add_id_row(4, "Loan Charge Rate:", self.loan_charge_entry)
        
        self.chkbx_billing = QCheckBox("Billing Suspended (66)")
        grid_ids.addWidget(self.chkbx_billing, 5, 0, 1, 2)
        
        col1.addWidget(self.group_ids)
        
        # Ranges
        self.group_ranges = QGroupBox("Ranges")
        grid_ranges = QGridLayout(self.group_ranges)
        grid_ranges.setContentsMargins(2, 12, 2, 2)
        grid_ranges.setHorizontalSpacing(4)
        grid_ranges.setVerticalSpacing(1)
        
        self.paid_min, self.paid_max = self._create_range_row(grid_ranges, 0, "Paid To Date:")
        self.gpe_min, self.gpe_max = self._create_range_row(grid_ranges, 1, "GPE Date (51/66):")
        self.app_min, self.app_max = self._create_range_row(grid_ranges, 2, "Application Date (01):")
        self.bil_min, self.bil_max = self._create_range_row(grid_ranges, 3, "BIL Commence DT:")
        self.lastfin_min, self.lastfin_max = self._create_range_row(grid_ranges, 4, "Last Financial Date:")
        self.billprem_min, self.billprem_max = self._create_range_row(grid_ranges, 5, "Billing Prem Amt:")
        
        col1.addWidget(self.group_ranges)
        col1.addStretch()


        # -- Column 2: Status & Codes --
        col2 = QVBoxLayout()
        status_state_layout = QHBoxLayout()
        
        self.grp_status, self.lw_status = self._create_enabled_listbox("Status Code (01)", STATUS_CODES, visible_rows=20)
        self.grp_status.setFixedWidth(190)
        
        # State abbreviations list (e.g. "AL - 01", "AZ - 02")
        # Removing leading zeroes on the number display by casting to int, for exact visual match
        states_dict = {k: f"{k} - {int(v)}" for k, v in STATE_CODES.items()}
        self.grp_state, self.lw_state = self._create_enabled_listbox("State", states_dict, visible_rows=20, fmt="plain")
        self.grp_state.setFixedWidth(100)
        
        status_state_layout.addWidget(self.grp_status)
        status_state_layout.addWidget(self.grp_state)
        status_state_layout.addStretch() 
        
        col2.addLayout(status_state_layout)
        self.grp_billform, self.lw_billform = self._create_enabled_listbox("Billing Form (01)", AUDIT_BILLING_FORMS)
        col2.addWidget(self.grp_billform)
        
        self.grp_billmode, self.lw_billmode = self._create_enabled_listbox("Bill Mode (01)", BILL_MODE_DISPLAY)
        col2.addWidget(self.grp_billmode)
        col2.addStretch()


        # -- Column 3: Product Specific & Riders --
        col3 = QVBoxLayout()
        self.grp_deflife, self.lw_deflife = self._create_enabled_listbox("Def. Life Insurance (66)", DEF_OF_LIFE_INS_CODES)
        col3.addWidget(self.grp_deflife)
        
        self.grp_grace, self.lw_grace = self._create_enabled_listbox("Grace Indicator (51/66)", GRACE_INDICATOR_CODES)
        col3.addWidget(self.grp_grace)
        
        self.grp_gracerule, self.lw_gracerule = self._create_enabled_listbox("Grace Period Rule (66)", GRACE_RULE_CODES)
        col3.addWidget(self.grp_gracerule)
        
        self.grp_lastentry, self.lw_lastentry = self._create_enabled_listbox("Last Entry Code (01)", AUDIT_LAST_ENTRY_CODES)
        col3.addWidget(self.grp_lastentry)
        
        self.grp_overloan, self.lw_overloan = self._create_enabled_listbox("Trad Overloan Ind (01)", OVERLOAN_INDICATOR_CODES)
        col3.addWidget(self.grp_overloan)
        
        self.grp_dbopt, self.lw_dbopt = self._create_enabled_listbox("Death Benefit Option (66)", DB_OPTION_CODES)
        col3.addWidget(self.grp_dbopt)
        col3.addStretch()


        # -- Column 4: Whole Life Options --
        col4 = QVBoxLayout()
        self.grp_primdiv, self.lw_primdiv = self._create_enabled_listbox("Primary Div Option (01)", DIV_OPTION_CODES)
        col4.addWidget(self.grp_primdiv)
        
        self.grp_secdiv, self.lw_secdiv = self._create_enabled_listbox("Secondary Div Option (01)", DIV_OPTION_CODES)
        col4.addWidget(self.grp_secdiv)
        
        self.grp_nfo, self.lw_nfo = self._create_enabled_listbox("NFO Code (01)", NFO_CODES)
        col4.addWidget(self.grp_nfo)
        
        self.grp_loantype, self.lw_loantype = self._create_enabled_listbox("Loan Type (01)", LOAN_TYPE_CODES)
        col4.addWidget(self.grp_loantype)
        
        self.grp_suspense, self.lw_suspense = self._create_enabled_listbox("Suspense Code (01)", SUSPENSE_CODES)
        col4.addWidget(self.grp_suspense)
        col4.addStretch()


        # Add columns to main layout (acting as horizontal)
        # CriteriaPanel inherits from self.main_layout which is a QVBoxLayout.
        # So we nest these into a QHBoxLayout.
        h_layout = QHBoxLayout()
        h_layout.addLayout(col1, 20)
        h_layout.addLayout(col2, 30)
        h_layout.addLayout(col3, 35)
        h_layout.addLayout(col4, 15)
        
        wrapper = QWidget()
        wrapper.setLayout(h_layout)
        self.main_layout.addWidget(wrapper)


    def _selected(self, lw: QListWidget) -> list[str]:
        return [it.data(Qt.ItemDataRole.UserRole) for it in lw.selectedItems()]

    def write_to_criteria(self, criteria):
        # Arrays
        if self.grp_status.isChecked(): criteria.status_codes = self._selected(self.lw_status)
        if self.grp_state.isChecked(): criteria.states = self._selected(self.lw_state)
        if self.grp_billform.isChecked(): criteria.billing_forms = self._selected(self.lw_billform)
        if self.grp_billmode.isChecked(): criteria.billing_modes = self._selected(self.lw_billmode)
        if self.grp_deflife.isChecked(): criteria.def_of_life_ins = self._selected(self.lw_deflife)
        if self.grp_grace.isChecked(): criteria.grace_indicators = self._selected(self.lw_grace)
        if self.grp_gracerule.isChecked(): criteria.grace_period_rules = self._selected(self.lw_gracerule)
        if self.grp_lastentry.isChecked(): criteria.last_entry_codes = self._selected(self.lw_lastentry)
        if self.grp_overloan.isChecked(): criteria.overloan_indicators = self._selected(self.lw_overloan)
        if self.grp_dbopt.isChecked(): criteria.db_options = self._selected(self.lw_dbopt)
        if self.grp_primdiv.isChecked(): criteria.primary_div_options = self._selected(self.lw_primdiv)
        if self.grp_secdiv.isChecked(): criteria.secondary_div_options = self._selected(self.lw_secdiv)
        if self.grp_nfo.isChecked(): criteria.nfo_options = self._selected(self.lw_nfo)
        if self.grp_loantype.isChecked(): criteria.loan_types = self._selected(self.lw_loantype)
        if self.grp_suspense.isChecked(): criteria.suspense_codes = self._selected(self.lw_suspense)

        # Identifiers
        if self.company_combo.currentIndex() > 0:
            criteria.company = self.company_combo.currentText().split(" - ")[0]
        if self.market_combo.currentIndex() > 0:
            criteria.market_org = self.market_combo.currentText().split(" - ")[0]
        
        prefix = self.pol_prefix.text().strip()
        num = self.pol_num.text().strip()
        if prefix or num:
            # Simple pattern concatenation
            criteria.policy_number_pattern = f"{prefix}{num}"
            criteria.policy_number_criteria = "1" # "starts with"
            
        criteria.branch_number = self.branch_entry.text().strip()
        criteria.loan_charge_rate = self.loan_charge_entry.text().strip()
        criteria.billing_suspended = self.chkbx_billing.isChecked()
        
        # Ranges
        criteria.low_paid_to_date = self.paid_min.text().strip()
        criteria.high_paid_to_date = self.paid_max.text().strip()
        criteria.low_gpe_date = self.gpe_min.text().strip()
        criteria.high_gpe_date = self.gpe_max.text().strip()
        criteria.low_app_date = self.app_min.text().strip()
        criteria.high_app_date = self.app_max.text().strip()
        criteria.low_bill_commence_date = self.bil_min.text().strip()
        criteria.high_bill_commence_date = self.bil_max.text().strip()
        criteria.low_last_financial_date = self.lastfin_min.text().strip()
        criteria.high_last_financial_date = self.lastfin_max.text().strip()
        criteria.low_billing_prem = self.billprem_min.text().strip()
        criteria.high_billing_prem = self.billprem_max.text().strip()


    def reset(self, criteria):
        super().reset(criteria)
        self.pol_prefix.clear()
        self.pol_num.clear()
        self.company_combo.setCurrentIndex(0)
        self.market_combo.setCurrentIndex(0)
        self.branch_entry.clear()
        self.loan_charge_entry.clear()
        self.chkbx_billing.setChecked(False)
        
        self.paid_min.clear()
        self.paid_max.clear()
        self.gpe_min.clear()
        self.gpe_max.clear()
        self.app_min.clear()
        self.app_max.clear()
        self.bil_min.clear()
        self.bil_max.clear()
        self.lastfin_min.clear()
        self.lastfin_max.clear()
        self.billprem_min.clear()
        self.billprem_max.clear()
        
        for grp in [
            self.grp_status, self.grp_state, self.grp_billform, self.grp_billmode,
            self.grp_deflife, self.grp_grace, self.grp_gracerule, self.grp_lastentry,
            self.grp_overloan, self.grp_dbopt, self.grp_primdiv, self.grp_secdiv,
            self.grp_nfo, self.grp_loantype, self.grp_suspense
        ]:
            grp.setChecked(False)
            
        for lw in [
            self.lw_status, self.lw_state, self.lw_billform, self.lw_billmode,
            self.lw_deflife, self.lw_grace, self.lw_gracerule, self.lw_lastentry,
            self.lw_overloan, self.lw_dbopt, self.lw_primdiv, self.lw_secdiv,
            self.lw_nfo, self.lw_loantype, self.lw_suspense
        ]:
            lw.clearSelection()
