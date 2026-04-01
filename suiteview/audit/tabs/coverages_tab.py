"""
Coverages tab — faithful replica of VBA frmAudit Coverages (tab 3).

Layout (6 columns, left to right):
  COL 1: Valuation (02) group, Policy-Level checkboxes, Non Trad Indicator,
         Curr Specified Amt range
  COL 2: Init Term Period (02) checkbox + listbox
  COL 3: Mortality Table Codes checkbox + listbox
  COL 4: Base Coverage (02) — combo fields, checkboxes, date ranges
  COL 5: Rider 1 Criteria — same combo layout
  COL 6: Rider 2 Criteria — same combo layout
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QCheckBox, QComboBox, QFrame, QListWidget,
    QAbstractItemView,
)
from PyQt6.QtGui import QFont

from ..constants import (
    NON_TRAD_INDICATOR_ITEMS, INIT_TERM_PERIOD_ITEMS,
    MORTALITY_TABLE_CODE_ITEMS,
    PRODUCT_LINE_CODE_ITEMS, PRODUCT_INDICATOR_ITEMS,
    RATECLASS_67_ITEMS, SEX_CODE_67_ITEMS, SEX_CODE_02_ITEMS,
    PERSON_ITEMS, LIVES_COVERED_ITEMS, CHANGE_TYPE_02_ITEMS,
    COLA_IND_ITEMS, GIO_FIO_ITEMS, ADDL_PLANCODE_ITEMS,
)
from ._styles import (
    make_checkbox as _make_checkbox,
    make_listbox as _make_listbox,
    connect_checkbox_listbox as _connect_checkbox_listbox,
    make_combo as _make_combo,
)

# ── Compact sizing helpers ──────────────────────────────────────────────
_FONT = QFont("Segoe UI", 9)
_FONT_SM = QFont("Segoe UI", 8)
_ROW_H = 16
_CTRL_H = 22
_V_SPACING = 2
_H_SPACING = 4
_RANGE_W = 70

_GRP_STYLE = (
    "QGroupBox { font-weight: bold; color: #1E5BA8; border: 1px solid #6A9BD1; "
    "border-radius: 3px; margin-top: 8px; padding-top: 4px; } "
    "QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 3px; }"
)


class CoveragesTab(QWidget):
    """Coverages criteria tab — mirrors VBA frmAudit Coverages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    @staticmethod
    def _hsep() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #bbb;")
        sep.setFixedHeight(2)
        return sep

    @staticmethod
    def _vsep() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #bbb;")
        sep.setFixedWidth(2)
        return sep

    # ── Coverage criteria column (reusable for Base / Rider 1 / Rider 2) ─
    def _build_coverage_column(self, title: str) -> tuple[QGroupBox, dict]:
        """Build a coverage criteria group with all combos/fields. Returns (group, widgets_dict)."""
        grp = QGroupBox(title)
        grp.setStyleSheet(_GRP_STYLE)
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(6, 16, 6, 4)
        layout.setSpacing(0)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(2)

        widgets = {}

        def _add_combo_row(row, label, items, width=130):
            lbl = QLabel(label)
            lbl.setFont(_FONT_SM)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, row, 0)
            cb = _make_combo(items, width=width)
            grid.addWidget(cb, row, 1)
            return cb

        def _add_text_row(row, label, width=130):
            lbl = QLabel(label)
            lbl.setFont(_FONT_SM)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, row, 0)
            le = QLineEdit()
            le.setFont(_FONT)
            le.setFixedSize(width, _CTRL_H)
            grid.addWidget(le, row, 1)
            return le

        r = 0
        widgets["plancode"] = _add_text_row(r, "Plancode:"); r += 1
        widgets["prod_line"] = _add_combo_row(r, "Prod Line (02):", [""] + PRODUCT_LINE_CODE_ITEMS); r += 1
        widgets["prod_ind"] = _add_combo_row(r, "Prod Ind (02):", [""] + PRODUCT_INDICATOR_ITEMS); r += 1
        widgets["form_number"] = _add_text_row(r, "Form Number:"); r += 1
        widgets["rateclass"] = _add_combo_row(r, "Rateclass (67):", [""] + RATECLASS_67_ITEMS); r += 1
        widgets["sex_code_67"] = _add_combo_row(r, "Sex Code (67):", [""] + SEX_CODE_67_ITEMS); r += 1
        widgets["sex_code_02"] = _add_combo_row(r, "Sex Code (02):", [""] + SEX_CODE_02_ITEMS); r += 1
        widgets["person"] = _add_combo_row(r, "Person:", PERSON_ITEMS); r += 1
        widgets["lives_cov"] = _add_combo_row(r, "Lives Cov (02):", [""] + LIVES_COVERED_ITEMS); r += 1
        widgets["change_type"] = _add_combo_row(r, "Change Type (02):", [""] + CHANGE_TYPE_02_ITEMS); r += 1
        widgets["cola_ind"] = _add_combo_row(r, "COLA Ind:", COLA_IND_ITEMS); r += 1
        widgets["gio_fio"] = _add_combo_row(r, "GIO/FIO:", GIO_FIO_ITEMS); r += 1

        # Addl Plancode only for Rider columns
        if title != "Base Coverage Criteria (02)":
            widgets["addl_plancode"] = _add_combo_row(r, "Addl Plancode:", ADDL_PLANCODE_ITEMS); r += 1

        # Table (03) and Flat (03) checkboxes
        chk_row = QHBoxLayout()
        chk_row.setSpacing(8)
        widgets["table_03"] = _make_checkbox("Table (03)")
        widgets["flat_03"] = _make_checkbox("Flat (03)")
        chk_row.addWidget(widgets["table_03"])
        chk_row.addWidget(widgets["flat_03"])
        chk_row.addStretch()
        grid.addLayout(chk_row, r, 0, 1, 2); r += 1

        # Post Issue checkbox (for Rider columns) / Issue Date header
        if title != "Base Coverage Criteria (02)":
            widgets["post_issue"] = _make_checkbox("Post Issue")
            grid.addWidget(widgets["post_issue"], r, 0, 1, 2); r += 1

        # Issue Date range
        lbl_id = QLabel("Issue Date:")
        lbl_id.setFont(_FONT_SM)
        grid.addWidget(lbl_id, r, 0, 1, 2); r += 1

        id_row = QHBoxLayout(); id_row.setSpacing(_H_SPACING)
        widgets["issue_date_lo"] = QLineEdit()
        widgets["issue_date_lo"].setFont(_FONT)
        widgets["issue_date_lo"].setFixedSize(_RANGE_W, _CTRL_H)
        widgets["issue_date_lo"].setPlaceholderText("Min")
        lbl_to = QLabel("to"); lbl_to.setFont(_FONT)
        widgets["issue_date_hi"] = QLineEdit()
        widgets["issue_date_hi"].setFont(_FONT)
        widgets["issue_date_hi"].setFixedSize(_RANGE_W, _CTRL_H)
        widgets["issue_date_hi"].setPlaceholderText("Max")
        id_row.addWidget(widgets["issue_date_lo"])
        id_row.addWidget(lbl_to)
        id_row.addWidget(widgets["issue_date_hi"])
        id_row.addStretch()
        grid.addLayout(id_row, r, 0, 1, 2); r += 1

        # Change Date range
        lbl_cd = QLabel("Change Date:")
        lbl_cd.setFont(_FONT_SM)
        grid.addWidget(lbl_cd, r, 0, 1, 2); r += 1

        cd_row = QHBoxLayout(); cd_row.setSpacing(_H_SPACING)
        widgets["change_date_lo"] = QLineEdit()
        widgets["change_date_lo"].setFont(_FONT)
        widgets["change_date_lo"].setFixedSize(_RANGE_W, _CTRL_H)
        widgets["change_date_lo"].setPlaceholderText("Min")
        lbl_to2 = QLabel("to"); lbl_to2.setFont(_FONT)
        widgets["change_date_hi"] = QLineEdit()
        widgets["change_date_hi"].setFont(_FONT)
        widgets["change_date_hi"].setFixedSize(_RANGE_W, _CTRL_H)
        widgets["change_date_hi"].setPlaceholderText("Max")
        cd_row.addWidget(widgets["change_date_lo"])
        cd_row.addWidget(lbl_to2)
        cd_row.addWidget(widgets["change_date_hi"])
        cd_row.addStretch()
        grid.addLayout(cd_row, r, 0, 1, 2); r += 1

        layout.addLayout(grid)
        layout.addStretch()

        return grp, widgets

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ════════════════════════════════════════════════════════════════
        # COLUMN 1 — Valuation + Policy-Level + Non Trad + Curr Spec Amt
        # ════════════════════════════════════════════════════════════════
        col1 = QVBoxLayout()
        col1.setSpacing(_V_SPACING)

        # ── Valuation (02) group ────────────────────────────────────
        grp_val = QGroupBox("Valuation (02)")
        grp_val.setStyleSheet(_GRP_STYLE)
        grid_val = QGridLayout(grp_val)
        grid_val.setContentsMargins(6, 16, 6, 4)
        grid_val.setHorizontalSpacing(6)
        grid_val.setVerticalSpacing(2)

        def _val_row(row, label, width=80):
            lbl = QLabel(label)
            lbl.setFont(_FONT)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid_val.addWidget(lbl, row, 0)
            le = QLineEdit()
            le.setFont(_FONT)
            le.setFixedSize(width, _CTRL_H)
            grid_val.addWidget(le, row, 1)
            return le

        self.val_class = _val_row(0, "Class:")
        self.val_base = _val_row(1, "Base:")
        self.val_sub = _val_row(2, "Sub:")
        self.val_mort_table = _val_row(3, "Val Mort Table:")
        self.rpu_mort_table = _val_row(4, "RPU Mort Table:")
        self.eti_mort_table = _val_row(5, "ETI Mort Table:")
        self.nfo_int_rate = _val_row(6, "NFO Int Rate:")

        self.chk_val_class_ne_plan = _make_checkbox("Val Class \u2260 PlanDesc Class")
        grid_val.addWidget(self.chk_val_class_ne_plan, 7, 0, 1, 2)

        col1.addWidget(grp_val)

        # ── Policy-Level (02/09) group ──────────────────────────────
        grp_flags = QGroupBox("Policy-Level (02/09)")
        grp_flags.setStyleSheet(_GRP_STYLE)
        flags_layout = QVBoxLayout(grp_flags)
        flags_layout.setContentsMargins(6, 16, 6, 4)
        flags_layout.setSpacing(2)

        self.chk_multiple_base = _make_checkbox("Multiple Base Covs (02)")
        self.chk_cov_gio = _make_checkbox("Cov has GIO ind (02)")
        self.chk_cov_cola = _make_checkbox("Cov has COLA ind (02)")
        self.chk_skipped_cov_rein = _make_checkbox("Skipped Cov Rein (09)")
        self.chk_cv_rate_gt_zero = _make_checkbox("CV rate > 0 base cov (02)")
        self.chk_gcv_gt_cv = _make_checkbox("GCV > Current CV (ISWL)")
        self.chk_gcv_lt_cv = _make_checkbox("GCV < Current CV (ISWL)")

        for cb in [self.chk_multiple_base, self.chk_cov_gio, self.chk_cov_cola,
                    self.chk_skipped_cov_rein, self.chk_cv_rate_gt_zero,
                    self.chk_gcv_gt_cv, self.chk_gcv_lt_cv]:
            flags_layout.addWidget(cb)

        col1.addWidget(grp_flags)

        # ── Non Trad Indicator (02) ─────────────────────────────────
        grp_nontrad = QGroupBox()
        grp_nontrad.setStyleSheet(_GRP_STYLE)
        nt_layout = QVBoxLayout(grp_nontrad)
        nt_layout.setContentsMargins(6, 4, 6, 4)
        nt_layout.setSpacing(_V_SPACING)
        self.chk_non_trad = _make_checkbox("Non Trad Indicator (02)")
        nt_layout.addWidget(self.chk_non_trad)
        self.list_non_trad = _make_listbox(NON_TRAD_INDICATOR_ITEMS, height_rows=2, enabled=False)
        _connect_checkbox_listbox(self.chk_non_trad, self.list_non_trad)
        nt_layout.addWidget(self.list_non_trad)
        col1.addWidget(grp_nontrad)

        # ── Curr Specified Amt (02) ─────────────────────────────────
        grp_sa = QGroupBox("Curr Specified Amt (02)")
        grp_sa.setStyleSheet(_GRP_STYLE)
        sa_layout = QHBoxLayout(grp_sa)
        sa_layout.setContentsMargins(6, 16, 6, 4)
        sa_layout.setSpacing(_H_SPACING)
        self.txt_spec_amt_lo = QLineEdit()
        self.txt_spec_amt_lo.setFont(_FONT)
        self.txt_spec_amt_lo.setFixedSize(_RANGE_W, _CTRL_H)
        self.txt_spec_amt_lo.setPlaceholderText("Min")
        lbl_to = QLabel("to"); lbl_to.setFont(_FONT)
        self.txt_spec_amt_hi = QLineEdit()
        self.txt_spec_amt_hi.setFont(_FONT)
        self.txt_spec_amt_hi.setFixedSize(_RANGE_W, _CTRL_H)
        self.txt_spec_amt_hi.setPlaceholderText("Max")
        sa_layout.addWidget(self.txt_spec_amt_lo)
        sa_layout.addWidget(lbl_to)
        sa_layout.addWidget(self.txt_spec_amt_hi)
        sa_layout.addStretch()
        col1.addWidget(grp_sa)

        col1.addStretch()

        # ════════════════════════════════════════════════════════════════
        # COLUMN 2 — Init Term Period (02)
        # ════════════════════════════════════════════════════════════════
        col2 = QVBoxLayout()
        col2.setSpacing(_V_SPACING)

        self.chk_init_term = _make_checkbox("Term (02)")
        col2.addWidget(self.chk_init_term)
        self.list_init_term = _make_listbox(
            INIT_TERM_PERIOD_ITEMS, height_rows=29, enabled=False)
        self.list_init_term.setFixedWidth(50)
        _connect_checkbox_listbox(self.chk_init_term, self.list_init_term)
        col2.addWidget(self.list_init_term)
        col2.addStretch()

        # ════════════════════════════════════════════════════════════════
        # COLUMN 3 — Mortality Table Codes
        # ════════════════════════════════════════════════════════════════
        col3 = QVBoxLayout()
        col3.setSpacing(_V_SPACING)

        grp_mort = QGroupBox("Mortality Table Codes")
        grp_mort.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #2E7D32; border: 1px solid #4CAF50;"
            " border-radius: 3px; margin-top: 10px; padding-top: 14px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )
        mort_layout = QVBoxLayout(grp_mort)
        mort_layout.setContentsMargins(6, 16, 6, 4)
        mort_layout.setSpacing(_V_SPACING)
        self.list_mort_table = _make_listbox(
            MORTALITY_TABLE_CODE_ITEMS, height_rows=28, enabled=True)
        self.list_mort_table.setMinimumWidth(200)
        self.list_mort_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list_mort_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_mort_table.setStyleSheet(
            "QListWidget { border: 1px solid #999; background-color: #F5F5F0; color: #555; }"
            "QListWidget::item { padding: 0px 2px; }"
        )
        mort_layout.addWidget(self.list_mort_table)
        col3.addWidget(grp_mort)
        col3.addStretch()

        # ════════════════════════════════════════════════════════════════
        # COLUMNS 4-6 — Base Coverage, Rider 1, Rider 2
        # ════════════════════════════════════════════════════════════════
        self.grp_base_cov, self.base_cov_widgets = self._build_coverage_column("Base Coverage Criteria (02)")
        self.grp_rider1, self.rider1_widgets = self._build_coverage_column("Rider 1 Criteria")
        self.grp_rider2, self.rider2_widgets = self._build_coverage_column("Rider 2 Criteria")

        # ── Assemble all columns ────────────────────────────────────
        root.addLayout(col1)
        root.addWidget(self._vsep())
        root.addLayout(col2)
        root.addLayout(col3)
        root.addWidget(self._vsep())
        root.addWidget(self.grp_base_cov)
        root.addWidget(self._vsep())
        root.addWidget(self.grp_rider1)
        root.addWidget(self._vsep())
        root.addWidget(self.grp_rider2)

    # ── Profile save/load ────────────────────────────────────────────

    def _get_cov_column_state(self, widgets: dict) -> dict:
        from ..profile_manager import (
            get_lineedit_text as _t, get_checkbox_checked as _c,
            get_combo_text as _cmb,
        )
        state = {}
        for key, w in widgets.items():
            from PyQt6.QtWidgets import QLineEdit, QCheckBox, QComboBox
            if isinstance(w, QLineEdit):
                state[key] = _t(w)
            elif isinstance(w, QCheckBox):
                state[key] = _c(w)
            elif isinstance(w, QComboBox):
                state[key] = _cmb(w)
        return state

    def _set_cov_column_state(self, widgets: dict, state: dict):
        from ..profile_manager import (
            set_lineedit_text as _t, set_checkbox_checked as _c,
            set_combo_text as _cmb,
        )
        from PyQt6.QtWidgets import QLineEdit, QCheckBox, QComboBox
        for key, w in widgets.items():
            if isinstance(w, QLineEdit):
                _t(w, state.get(key, ""))
            elif isinstance(w, QCheckBox):
                _c(w, state.get(key, False))
            elif isinstance(w, QComboBox):
                _cmb(w, state.get(key, ""))

    def get_state(self) -> dict:
        from ..profile_manager import (
            get_lineedit_text as _t, get_checkbox_checked as _c,
            get_listbox_selected as _sel,
        )
        return {
            "val_class": _t(self.val_class),
            "val_base": _t(self.val_base),
            "val_sub": _t(self.val_sub),
            "val_mort_table": _t(self.val_mort_table),
            "rpu_mort_table": _t(self.rpu_mort_table),
            "eti_mort_table": _t(self.eti_mort_table),
            "nfo_int_rate": _t(self.nfo_int_rate),
            "chk_val_class_ne_plan": _c(self.chk_val_class_ne_plan),
            "chk_multiple_base": _c(self.chk_multiple_base),
            "chk_cov_gio": _c(self.chk_cov_gio),
            "chk_cov_cola": _c(self.chk_cov_cola),
            "chk_skipped_cov_rein": _c(self.chk_skipped_cov_rein),
            "chk_cv_rate_gt_zero": _c(self.chk_cv_rate_gt_zero),
            "chk_gcv_gt_cv": _c(self.chk_gcv_gt_cv),
            "chk_gcv_lt_cv": _c(self.chk_gcv_lt_cv),
            "chk_non_trad": _c(self.chk_non_trad),
            "list_non_trad": _sel(self.list_non_trad),
            "txt_spec_amt_lo": _t(self.txt_spec_amt_lo),
            "txt_spec_amt_hi": _t(self.txt_spec_amt_hi),
            "chk_init_term": _c(self.chk_init_term),
            "list_init_term": _sel(self.list_init_term),
            "base_cov": self._get_cov_column_state(self.base_cov_widgets),
            "rider1": self._get_cov_column_state(self.rider1_widgets),
            "rider2": self._get_cov_column_state(self.rider2_widgets),
        }

    def set_state(self, state: dict):
        from ..profile_manager import (
            set_lineedit_text as _t, set_checkbox_checked as _c,
            set_listbox_selected as _sel,
        )
        _t(self.val_class, state.get("val_class", ""))
        _t(self.val_base, state.get("val_base", ""))
        _t(self.val_sub, state.get("val_sub", ""))
        _t(self.val_mort_table, state.get("val_mort_table", ""))
        _t(self.rpu_mort_table, state.get("rpu_mort_table", ""))
        _t(self.eti_mort_table, state.get("eti_mort_table", ""))
        _t(self.nfo_int_rate, state.get("nfo_int_rate", ""))
        _c(self.chk_val_class_ne_plan, state.get("chk_val_class_ne_plan", False))
        _c(self.chk_multiple_base, state.get("chk_multiple_base", False))
        _c(self.chk_cov_gio, state.get("chk_cov_gio", False))
        _c(self.chk_cov_cola, state.get("chk_cov_cola", False))
        _c(self.chk_skipped_cov_rein, state.get("chk_skipped_cov_rein", False))
        _c(self.chk_cv_rate_gt_zero, state.get("chk_cv_rate_gt_zero", False))
        _c(self.chk_gcv_gt_cv, state.get("chk_gcv_gt_cv", False))
        _c(self.chk_gcv_lt_cv, state.get("chk_gcv_lt_cv", False))
        _c(self.chk_non_trad, state.get("chk_non_trad", False))
        _sel(self.list_non_trad, state.get("list_non_trad", []))
        _t(self.txt_spec_amt_lo, state.get("txt_spec_amt_lo", ""))
        _t(self.txt_spec_amt_hi, state.get("txt_spec_amt_hi", ""))
        _c(self.chk_init_term, state.get("chk_init_term", False))
        _sel(self.list_init_term, state.get("list_init_term", []))
        self._set_cov_column_state(self.base_cov_widgets, state.get("base_cov", {}))
        self._set_cov_column_state(self.rider1_widgets, state.get("rider1", {}))
        self._set_cov_column_state(self.rider2_widgets, state.get("rider2", {}))
