"""
Coverage Criteria Panel
=========================
Coverage-level filters: plancode, product line, sex code, rate class,
valuation fields, mortality tables, and boolean coverage flags.

Layout matches the Policy panel mockup_v2 style — 4 horizontal columns
with blue-bordered QGroupBox sections, checkable listboxes w/ tight rows.
"""

from __future__ import annotations

import typing
from typing import Dict, List

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QComboBox, QCheckBox, QTextEdit,
    QListWidget, QListWidgetItem, QAbstractItemView, QStyledItemDelegate,
)

from .panel_widgets import CriteriaPanel

from ...models.audit_constants import (
    PRODUCT_LINE_CODES, PRODUCT_INDICATOR_CODES,
    SEX_CODES, RATE_CLASS_CODES, SEX_CODES_02,
    NON_TRAD_INDICATOR_CODES, INITIAL_TERM_PERIODS,
    MORTALITY_TABLE_CODES, REINSURANCE_CODES,
)

from suiteview.polview.models.cl_polrec.policy_translations import (
    DIV_OPTION_CODES, DB_OPTION_CODES, DEF_OF_LIFE_INS_CODES,
)


# ─── Compact list delegate (same as policy_panel) ──────────────────────
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


class CoveragePanel(CriteriaPanel):
    """Coverage-level filters matching the mockup_v2 visual style."""

    # ── Helpers (identical to PolicyPanel) ─────────────────────────────

    def _create_enabled_listbox(
        self, title: str, items_dict: Dict[str, str],
        visible_rows: int = None, fmt: str = "dash",
    ):
        """Checkable QGroupBox wrapping a multi-select QListWidget."""
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

        for code, label in items_dict.items():
            text = f"{code} - {label}" if (fmt == "dash" and label) else code
            if fmt == "plain":
                text = label
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, code)
            listbox.addItem(it)

        n_items = listbox.count()
        if visible_rows is None:
            visible_rows = n_items
            if visible_rows < 3:
                visible_rows = 3
            if visible_rows > 12:
                visible_rows = 12

        listbox.setFixedHeight((visible_rows * _TightItemDelegate.ROW_H) + 2)
        layout.addWidget(listbox)

        listbox.setEnabled(False)
        group.toggled.connect(listbox.setEnabled)
        group.toggled.connect(
            lambda checked, lw=listbox: lw.clearSelection() if not checked else None
        )

        return group, listbox

    def _create_range_row(
        self, layout: QGridLayout, row: int, title: str, lbl_width: int = 140,
    ) -> typing.Tuple[QLineEdit, QLineEdit]:
        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if lbl_width:
            lbl_title.setFixedWidth(lbl_width)
        layout.addWidget(lbl_title, row, 0)

        low_input = QLineEdit()
        low_input.setPlaceholderText("Min")
        low_input.setFixedWidth(80)
        layout.addWidget(low_input, row, 1)

        lbl = QLabel("to")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl, row, 2)

        high_input = QLineEdit()
        high_input.setPlaceholderText("Max")
        high_input.setFixedWidth(80)
        layout.addWidget(high_input, row, 3)
        return low_input, high_input

    # ── Main UI build ─────────────────────────────────────────────────

    def _build_ui(self):
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(8)

        # ═══════════════════════════════════════════════════════════════
        # COLUMN 1 — Plancode / Form + Base Coverage identifiers
        # ═══════════════════════════════════════════════════════════════
        col1 = QVBoxLayout()

        # ── Plancode / Form ──
        grp_plan = QGroupBox("Plancode / Form")
        grid_plan = QGridLayout(grp_plan)
        grid_plan.setContentsMargins(4, 14, 4, 4)
        grid_plan.setHorizontalSpacing(6)
        grid_plan.setVerticalSpacing(2)

        def _add_plan_row(r, title, placeholder="", width=120):
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid_plan.addWidget(lbl, r, 0)
            le = QLineEdit()
            le.setPlaceholderText(placeholder)
            le.setFixedWidth(width)
            grid_plan.addWidget(le, r, 1)
            return le

        self.cov1_plancode_edit = _add_plan_row(0, "Cov 1 Plancode:", "e.g. 7N001A")
        self.plancode_all_edit = _add_plan_row(1, "Any Cov Plancode:", "e.g. 7N001A")
        self.form_number_edit = _add_plan_row(2, "Form # (LIKE):", "%pattern%")

        # Multiple plancodes
        lbl_multi = QLabel("Multiple Plancodes (one per line):")
        lbl_multi.setStyleSheet("font-size: 10px; font-weight: bold; color: #14407A;")
        grid_plan.addWidget(lbl_multi, 3, 0, 1, 2)
        self.multi_plancode_edit = QTextEdit()
        self.multi_plancode_edit.setMaximumHeight(52)
        self.multi_plancode_edit.setPlaceholderText("7N001A\n7N002B\n...")
        grid_plan.addWidget(self.multi_plancode_edit, 4, 0, 1, 2)

        self.show_all_covs_cb = QCheckBox("Show All Coverages (not just base)")
        grid_plan.addWidget(self.show_all_covs_cb, 5, 0, 1, 2)
        self.include_ap_cb = QCheckBox("Include AP as Base Coverage")
        grid_plan.addWidget(self.include_ap_cb, 6, 0, 1, 2)

        col1.addWidget(grp_plan)

        # ── Base Coverage Identifiers ──
        grp_base = QGroupBox("Base Coverage (02)")
        grid_base = QGridLayout(grp_base)
        grid_base.setContentsMargins(4, 14, 4, 4)
        grid_base.setHorizontalSpacing(6)
        grid_base.setVerticalSpacing(2)

        def _add_base_row(r, title, items_dict, width=160):
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid_base.addWidget(lbl, r, 0)
            cb = QComboBox()
            cb.addItem("", "")
            for code, label in items_dict.items():
                cb.addItem(f"{code} — {label}" if label else code, code)
            cb.setFixedWidth(width)
            grid_base.addWidget(cb, r, 1)
            return cb

        self.cov1_product_line = _add_base_row(0, "Product Line (02):", PRODUCT_LINE_CODES)
        self.cov1_product_ind = _add_base_row(1, "Product Ind (02):", PRODUCT_INDICATOR_CODES)

        self.table_rating_cb = QCheckBox("Table Rating")
        self.flat_extra_cb = QCheckBox("Flat Extra")
        cb_row = QHBoxLayout()
        cb_row.setSpacing(12)
        cb_row.addWidget(self.table_rating_cb)
        cb_row.addWidget(self.flat_extra_cb)
        cb_row.addStretch()
        grid_base.addLayout(cb_row, 2, 0, 1, 2)

        col1.addWidget(grp_base)

        # ── Coverage Flags ──
        grp_flags = QGroupBox("Coverage Flags")
        flags_layout = QVBoxLayout(grp_flags)
        flags_layout.setContentsMargins(4, 14, 4, 4)
        flags_layout.setSpacing(2)

        self.multiple_base_cb = QCheckBox("Multiple Base Coverages")
        self.current_sa_gt_cb = QCheckBox("Current SA > Original SA")
        self.current_sa_lt_cb = QCheckBox("Current SA < Original SA")
        self.cv_rate_gt_zero_cb = QCheckBox("CV Rate > 0 on Base")
        self.gio_cb = QCheckBox("GIO Indicator")
        self.cola_cb = QCheckBox("COLA Indicator")
        self.rpu_original_cb = QCheckBox("RPU Original Amount")
        self.val_class_not_plan_cb = QCheckBox("Val Class ≠ Plan Description")

        for cb in [
            self.multiple_base_cb, self.current_sa_gt_cb, self.current_sa_lt_cb,
            self.cv_rate_gt_zero_cb, self.gio_cb, self.cola_cb,
            self.rpu_original_cb, self.val_class_not_plan_cb,
        ]:
            flags_layout.addWidget(cb)

        col1.addWidget(grp_flags)
        col1.addStretch()

        # ═══════════════════════════════════════════════════════════════
        # COLUMN 2 — Product / Sex / Rate Class listboxes
        # ═══════════════════════════════════════════════════════════════
        col2 = QVBoxLayout()

        # Product line + indicator side-by-side
        prod_row = QHBoxLayout()
        self.grp_prodline, self.lw_prodline = self._create_enabled_listbox(
            "Product Line Codes", PRODUCT_LINE_CODES, visible_rows=12
        )
        self.grp_prodind, self.lw_prodind = self._create_enabled_listbox(
            "Product Indicators", PRODUCT_INDICATOR_CODES, visible_rows=12
        )
        prod_row.addWidget(self.grp_prodline)
        prod_row.addWidget(self.grp_prodind)
        col2.addLayout(prod_row)

        # Rateclass + Sex Code (67) side-by-side
        sex_row = QHBoxLayout()
        self.grp_rateclass, self.lw_rateclass = self._create_enabled_listbox(
            "Rateclass Code (67)", RATE_CLASS_CODES, visible_rows=10
        )
        self.grp_sex67, self.lw_sex67 = self._create_enabled_listbox(
            "Sex Code (67)", SEX_CODES, visible_rows=7
        )
        sex_row.addWidget(self.grp_rateclass)
        sex_row.addWidget(self.grp_sex67)
        col2.addLayout(sex_row)

        # Sex Code (02)
        self.grp_sex02, self.lw_sex02 = self._create_enabled_listbox(
            "Sex Code (02)", SEX_CODES_02,
        )
        col2.addWidget(self.grp_sex02)

        # Non-Trad Indicator
        self.grp_nontrad, self.lw_nontrad = self._create_enabled_listbox(
            "Non-Trad Indicator (02)", NON_TRAD_INDICATOR_CODES,
        )
        col2.addWidget(self.grp_nontrad)

        # Initial Term Period
        itp_dict = {p: p for p in INITIAL_TERM_PERIODS}
        self.grp_initterm, self.lw_initterm = self._create_enabled_listbox(
            "Initial Term Period (02)", itp_dict, visible_rows=10,
        )
        col2.addWidget(self.grp_initterm)
        col2.addStretch()

        # ═══════════════════════════════════════════════════════════════
        # COLUMN 3 — Valuation fields + Mortality Tables + Reinsurance
        # ═══════════════════════════════════════════════════════════════
        col3 = QVBoxLayout()

        # ── Valuation ──
        grp_val = QGroupBox("Valuation")
        grid_val = QGridLayout(grp_val)
        grid_val.setContentsMargins(4, 14, 4, 4)
        grid_val.setHorizontalSpacing(6)
        grid_val.setVerticalSpacing(2)

        def _add_val_row(r, title, width=80):
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid_val.addWidget(lbl, r, 0)
            le = QLineEdit()
            le.setFixedWidth(width)
            grid_val.addWidget(le, r, 1)
            return le

        self.val_class_edit = _add_val_row(0, "Val Class:")
        self.val_base_edit = _add_val_row(1, "Val Base:")
        self.val_subseries_edit = _add_val_row(2, "Val Subseries:")
        self.val_mort_edit = _add_val_row(3, "Val Mortality Tbl:")
        self.eti_mort_edit = _add_val_row(4, "ETI Mortality Tbl:")
        self.rpu_mort_edit = _add_val_row(5, "RPU Mortality Tbl:")
        self.nfo_rate_edit = _add_val_row(6, "NFO Int Rate:", 80)

        col3.addWidget(grp_val)

        # ── Mortality Table Codes ──
        self.grp_morttbl, self.lw_morttbl = self._create_enabled_listbox(
            "Mortality Table Codes", MORTALITY_TABLE_CODES, visible_rows=12,
        )
        col3.addWidget(self.grp_morttbl)

        # ── Reinsurance ──
        self.grp_reins, self.lw_reins = self._create_enabled_listbox(
            "Reinsurance Code", REINSURANCE_CODES,
        )
        col3.addWidget(self.grp_reins)
        col3.addStretch()

        # ═══════════════════════════════════════════════════════════════
        # COLUMN 4 — Div / DB / Def Life listboxes (for coverage-level)
        # ═══════════════════════════════════════════════════════════════
        col4 = QVBoxLayout()

        self.grp_primdiv, self.lw_primdiv = self._create_enabled_listbox(
            "Primary Div Option", DIV_OPTION_CODES,
        )
        col4.addWidget(self.grp_primdiv)

        self.grp_secdiv, self.lw_secdiv = self._create_enabled_listbox(
            "Secondary Div Option", DIV_OPTION_CODES,
        )
        col4.addWidget(self.grp_secdiv)

        self.grp_dbopt, self.lw_dbopt = self._create_enabled_listbox(
            "Death Benefit Option (66)", DB_OPTION_CODES,
        )
        col4.addWidget(self.grp_dbopt)

        self.grp_deflife, self.lw_deflife = self._create_enabled_listbox(
            "Def. Life Insurance (66)", DEF_OF_LIFE_INS_CODES,
        )
        col4.addWidget(self.grp_deflife)
        col4.addStretch()

        # ═══════════════════════════════════════════════════════════════
        # Assemble columns into horizontal layout
        # ═══════════════════════════════════════════════════════════════
        h_layout = QHBoxLayout()
        h_layout.addLayout(col1, 25)
        h_layout.addLayout(col2, 25)
        h_layout.addLayout(col3, 25)
        h_layout.addLayout(col4, 25)

        wrapper = QWidget()
        wrapper.setLayout(h_layout)
        self.main_layout.addWidget(wrapper)

    # ── Helpers ────────────────────────────────────────────────────────

    def _selected(self, lw: QListWidget) -> list[str]:
        return [it.data(Qt.ItemDataRole.UserRole) for it in lw.selectedItems()]

    # ── Write/reset ───────────────────────────────────────────────────

    def write_to_criteria(self, criteria):
        # Plancode / form
        criteria.cov1_plancode = self.cov1_plancode_edit.text().strip()
        criteria.plancode_all_covs = self.plancode_all_edit.text().strip()
        criteria.form_number_like = self.form_number_edit.text().strip()
        criteria.show_all_coverages = self.show_all_covs_cb.isChecked()
        criteria.include_ap_as_base = self.include_ap_cb.isChecked()

        # Multiple plancodes
        text = self.multi_plancode_edit.toPlainText().strip()
        criteria.multiple_plancodes = [
            line.strip() for line in text.splitlines() if line.strip()
        ]

        # Base coverage combos
        criteria.cov1_product_line_code = self.cov1_product_line.currentData() or ""
        criteria.cov1_product_indicator = self.cov1_product_ind.currentData() or ""

        # Listbox arrays (only if checked)
        if self.grp_prodline.isChecked():
            criteria.product_line_codes_all = self._selected(self.lw_prodline)
        if self.grp_prodind.isChecked():
            criteria.product_indicators_all = self._selected(self.lw_prodind)
        if self.grp_rateclass.isChecked():
            criteria.cov1_rateclass = self._selected(self.lw_rateclass)
        if self.grp_sex67.isChecked():
            criteria.cov1_sex_code = self._selected(self.lw_sex67)
        if self.grp_sex02.isChecked():
            criteria.cov1_sex_code_02 = self._selected(self.lw_sex02)
        if self.grp_nontrad.isChecked():
            criteria.non_trad_indicators = self._selected(self.lw_nontrad)
        if self.grp_initterm.isChecked():
            criteria.initial_term_periods = self._selected(self.lw_initterm)
        if self.grp_morttbl.isChecked():
            criteria.mortality_table_codes = self._selected(self.lw_morttbl)
        if self.grp_reins.isChecked():
            criteria.reinsurance_codes = self._selected(self.lw_reins)
        if self.grp_primdiv.isChecked():
            criteria.primary_div_options = self._selected(self.lw_primdiv)
        if self.grp_secdiv.isChecked():
            criteria.secondary_div_options = self._selected(self.lw_secdiv)
        if self.grp_dbopt.isChecked():
            criteria.db_options = self._selected(self.lw_dbopt)
        if self.grp_deflife.isChecked():
            criteria.def_of_life_ins = self._selected(self.lw_deflife)

        # Valuation single fields
        criteria.valuation_class = self.val_class_edit.text().strip()
        criteria.valuation_base = self.val_base_edit.text().strip()
        criteria.valuation_subseries = self.val_subseries_edit.text().strip()
        criteria.valuation_mortality_table = self.val_mort_edit.text().strip()
        criteria.eti_mortality_table = self.eti_mort_edit.text().strip()
        criteria.rpu_mortality_table = self.rpu_mort_edit.text().strip()
        criteria.nfo_interest_rate = self.nfo_rate_edit.text().strip()

        # Boolean flags
        criteria.table_rating = self.table_rating_cb.isChecked()
        criteria.flat_extra = self.flat_extra_cb.isChecked()
        criteria.multiple_base_coverages = self.multiple_base_cb.isChecked()
        criteria.current_sa_gt_original = self.current_sa_gt_cb.isChecked()
        criteria.current_sa_lt_original = self.current_sa_lt_cb.isChecked()
        criteria.cv_rate_gt_zero_on_base = self.cv_rate_gt_zero_cb.isChecked()
        criteria.gio_indicator = self.gio_cb.isChecked()
        criteria.cola_indicator = self.cola_cb.isChecked()
        criteria.rpu_original_amt = self.rpu_original_cb.isChecked()
        criteria.valuation_class_not_plan_description = self.val_class_not_plan_cb.isChecked()

    def reset(self, criteria):
        super().reset(criteria)

        # Text fields
        self.cov1_plancode_edit.clear()
        self.plancode_all_edit.clear()
        self.form_number_edit.clear()
        self.multi_plancode_edit.clear()
        self.show_all_covs_cb.setChecked(False)
        self.include_ap_cb.setChecked(False)

        # Combos
        self.cov1_product_line.setCurrentIndex(0)
        self.cov1_product_ind.setCurrentIndex(0)

        # Valuation
        for le in [
            self.val_class_edit, self.val_base_edit, self.val_subseries_edit,
            self.val_mort_edit, self.eti_mort_edit, self.rpu_mort_edit,
            self.nfo_rate_edit,
        ]:
            le.clear()

        # Boolean checkboxes
        for cb in [
            self.table_rating_cb, self.flat_extra_cb, self.multiple_base_cb,
            self.current_sa_gt_cb, self.current_sa_lt_cb, self.cv_rate_gt_zero_cb,
            self.gio_cb, self.cola_cb, self.rpu_original_cb, self.val_class_not_plan_cb,
        ]:
            cb.setChecked(False)

        # All groups unchecked and lists cleared
        for grp in [
            self.grp_prodline, self.grp_prodind, self.grp_rateclass,
            self.grp_sex67, self.grp_sex02, self.grp_nontrad,
            self.grp_initterm, self.grp_morttbl, self.grp_reins,
            self.grp_primdiv, self.grp_secdiv, self.grp_dbopt, self.grp_deflife,
        ]:
            grp.setChecked(False)

        for lw in [
            self.lw_prodline, self.lw_prodind, self.lw_rateclass,
            self.lw_sex67, self.lw_sex02, self.lw_nontrad,
            self.lw_initterm, self.lw_morttbl, self.lw_reins,
            self.lw_primdiv, self.lw_secdiv, self.lw_dbopt, self.lw_deflife,
        ]:
            lw.clearSelection()
