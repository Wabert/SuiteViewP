"""
Coverages tab — CyberLife coverage criteria (VBA frmAudit Coverages, tab 3).

Layout (left to right):
  COL 1: Valuation (02) group, Policy-Level checkboxes, Non Trad Indicator,
         Total Curr Specified Amt (Sum 02) range — sum over all base coverages
  COL 2: Init Term Period (02) checkbox + listbox
  COL 3: Mortality Table Codes reference list
  COL 4: Base Coverage Criteria (02) — fields, one-line ranges, flags
  COL 5: Rider 1 Criteria — same layout plus rider-only rows
  COL 6: Rider 2 Criteria — hidden until the user clicks [+]; its [x]
         removes it again and clears its criteria
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QAbstractItemView, QSizePolicy, QToolButton,
)
from PyQt6.QtGui import QFont, QFontMetrics

from suiteview.ui import tokens

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
    make_multiselect_popup as _make_multiselect_popup,
)

# ── Compact sizing helpers ──────────────────────────────────────────────
_FONT = QFont("Segoe UI", 9)
_FONT_SM = QFont("Segoe UI", 8)
_CTRL_H = 22
_V_SPACING = 2
_H_SPACING = 4
_RANGE_W = 64
_RANGE_TO_W = 14
_RANGE_GAP = 2
# Every coverage-column input shares one width so the right edges line up;
# it equals one "[Min] to [Max]" range row.
_FIELD_W = 2 * _RANGE_W + _RANGE_TO_W + 2 * _RANGE_GAP
_MULTI_BTN_W = 18
_COV_LABEL_W = 92
_CLASS_CODE_ITEMS = [
    ("1 - Life", "1"),
    ("2 - Endowment", "2"),
    ("3 - Income Endowment", "3"),
    ("4 - Family Plan", "4"),
    ("5 - Level Term", "5"),
    ("6 - Decreasing Term", "6"),
    ("7 - Decreasing Term", "7"),
    ("8 - Other Term", "8"),
    ("9 - Deferred Annuity", "9"),
    ("C - Disability Income", "C"),
]

# Cease Reason Code (LH_COV_PHA.CEA_REA_CD) — blank at top means "no cease code"
_CEASE_CODE_ITEMS = [
    ("", ""),
    ("L - Death Claim Settled", "L"),
    ("M - Matured", "M"),
    ("N - Expired", "N"),
    ("O - Conversion", "O"),
    ("P - Coverage Surrendered", "P"),
    ("Q - Lapsed", "Q"),
    ("R - Prem paying policy terminated when converted to NFO", "R"),
    ("S - Paid-up rider terminated when converted to NFO", "S"),
    ("1 - General cease code", "1"),
]

_GRP_STYLE = (
    f"QGroupBox {{ font-weight: bold; color: {tokens.BRAND_BLUE}; border: 1px solid #6A9BD1; "
    "border-radius: 3px; margin-top: 8px; padding-top: 4px; } "
    "QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 3px; }"
)

# Reference-only list (not a criterion) keeps its green frame, with the same
# title geometry as the criteria groups so every group title lines up.
_REF_GRP_STYLE = (
    "QGroupBox { font-weight: bold; color: #2E7D32; border: 1px solid #4CAF50; "
    "border-radius: 3px; margin-top: 8px; padding-top: 4px; } "
    "QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 3px; }"
)

_GROUP_BTN_STYLE = (
    f"QToolButton {{ color: {tokens.BRAND_BLUE}; background: palette(window);"
    f" border: 1px solid #6A9BD1; border-radius: 3px; font-weight: bold; padding: 0px; }}"
    f"QToolButton:hover {{ background: {tokens.AUDIT.subtle}; border-color: {tokens.BRAND_BLUE}; }}"
    f"QToolButton:pressed {{ background: {tokens.AUDIT_PRESSED_SURFACE}; }}"
)


def _range_edit(placeholder: str) -> QLineEdit:
    le = QLineEdit()
    le.setFont(_FONT)
    le.setFixedSize(_RANGE_W, _CTRL_H)
    le.setPlaceholderText(placeholder)
    return le


def _range_box() -> tuple[QWidget, QLineEdit, QLineEdit]:
    """One compact ``[Min] to [Max]`` row, exactly ``_FIELD_W`` wide."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(_RANGE_GAP)
    lo = _range_edit("Min")
    hi = _range_edit("Max")
    lbl_to = QLabel("to")
    lbl_to.setFont(_FONT)
    lbl_to.setFixedWidth(_RANGE_TO_W)
    lbl_to.setAlignment(Qt.AlignmentFlag.AlignCenter)
    row.addWidget(lo)
    row.addWidget(lbl_to)
    row.addWidget(hi)
    box.setFixedSize(_FIELD_W, _CTRL_H)
    return box, lo, hi


class _RemovableGroupBox(QGroupBox):
    """Group box with a small [x] in its title strip that requests removal."""

    removeRequested = pyqtSignal()

    def __init__(self, title: str, remove_tooltip: str, parent=None):
        super().__init__(title, parent)
        self.btn_remove = QToolButton(self)
        self.btn_remove.setText("\u00d7")
        self.btn_remove.setToolTip(remove_tooltip)
        self.btn_remove.setFixedSize(16, 16)
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setStyleSheet(_GROUP_BTN_STYLE)
        self.btn_remove.clicked.connect(self.removeRequested.emit)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.btn_remove.move(self.width() - self.btn_remove.width() - 6, 0)


class CoveragesTab(QWidget):
    """Coverages criteria tab — mirrors VBA frmAudit Coverages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ── Coverage criteria column (reusable for Base / Rider 1 / Rider 2) ─
    def _build_coverage_column(
        self, grp: QGroupBox, *, rider: bool,
    ) -> tuple[dict, QWidget]:
        """Fill a coverage criteria group; return ``(widgets, class_control)``.

        Base and rider columns share one grid so every row lines up across
        columns: rider-only rows (Addl Plancode, Post Issue) are blank space in
        the Base column. Base's Class control is ``self.val_class``
        (``COVERAGE1.INS_CLS_CD``), kept out of the widgets dict so its saved
        state key stays ``val_class``; riders store theirs as ``class_code``.
        """
        grp.setStyleSheet(_GRP_STYLE)
        grp.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(grp)
        layout.setContentsMargins(6, 14, 6, 4)
        layout.setSpacing(4)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(_H_SPACING)
        grid.setVerticalSpacing(_V_SPACING)
        grid.setColumnMinimumWidth(0, _COV_LABEL_W)

        widgets = {}
        row = 0

        def _label(text):
            lbl = QLabel(text)
            lbl.setFont(_FONT_SM)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, row, 0)

        def _add(label, widget):
            nonlocal row
            _label(label)
            grid.addWidget(widget, row, 1)
            row += 1
            return widget

        def _text():
            le = QLineEdit()
            le.setFont(_FONT)
            le.setFixedSize(_FIELD_W, _CTRL_H)
            return le

        def _combo(items):
            return _make_combo(items, width=_FIELD_W)

        def _multi(items):
            return _make_multiselect_popup(
                items, width=_FIELD_W - _MULTI_BTN_W, height_rows=len(items))

        def _blank_row():
            # A real placeholder (not an empty row) so the grid still applies
            # row spacing and Base rows line up with the Rider columns.
            nonlocal row
            spacer = QWidget()
            spacer.setFixedSize(_FIELD_W, _CTRL_H)
            grid.addWidget(spacer, row, 1)
            row += 1

        def _range(label, key):
            box, widgets[f"{key}_lo"], widgets[f"{key}_hi"] = _range_box()
            _add(label, box)

        widgets["plancode"] = _add("Plancode:", _text())
        class_control = _add("Class (02):", _multi(_CLASS_CODE_ITEMS))
        class_control.setToolTip("Coverage class code (LH_COV_PHA.INS_CLS_CD)")
        if rider:
            widgets["class_code"] = class_control
        widgets["prod_line"] = _add("Prod Line (02):", _combo([""] + PRODUCT_LINE_CODE_ITEMS))
        widgets["prod_ind"] = _add("Prod Ind (02):", _combo([""] + PRODUCT_INDICATOR_ITEMS))
        widgets["form_number"] = _add("Form Number:", _text())
        widgets["rateclass"] = _add("Rateclass (67):", _combo([""] + RATECLASS_67_ITEMS))
        widgets["sex_code_67"] = _add("Sex Code (67):", _combo([""] + SEX_CODE_67_ITEMS))
        widgets["sex_code_02"] = _add("Sex Code (02):", _combo([""] + SEX_CODE_02_ITEMS))
        widgets["person"] = _add("Person:", _combo(PERSON_ITEMS))
        widgets["lives_cov"] = _add("Lives Cov (02):", _combo([""] + LIVES_COVERED_ITEMS))
        widgets["change_type"] = _add("Change Type (02):", _combo([""] + CHANGE_TYPE_02_ITEMS))
        widgets["cease_code"] = _add("Cease Code (02):", _multi(_CEASE_CODE_ITEMS))
        widgets["cola_ind"] = _add("COLA Ind:", _combo(COLA_IND_ITEMS))
        widgets["gio_fio"] = _add("GIO/FIO:", _combo(GIO_FIO_ITEMS))
        if rider:
            widgets["addl_plancode"] = _add("Addl Plancode:", _combo(ADDL_PLANCODE_ITEMS))
        else:
            _blank_row()

        _range("Issue Date:", "issue_date")
        _range("Change Date:", "change_date")
        _range("VPU:", "vpu")
        _range("Cov Amount:", "spec_amt")
        widgets["spec_amt_lo"].parentWidget().setToolTip(
            "Coverage amount for this coverage = units \u00d7 VPU (02)")

        layout.addLayout(grid)

        # Flags: Table/Flat on one line, Active Flat/Post Issue on the next.
        # Active Flat restricts Flat (03) to non-expired flat extras (cease date
        # null/9999 or in the future); Flat matches any flat extra.
        flags = QGridLayout()
        flags.setContentsMargins(4, 0, 0, 0)
        flags.setHorizontalSpacing(10)
        flags.setVerticalSpacing(_V_SPACING)
        widgets["table_03"] = _make_checkbox("Table (03)")
        widgets["flat_03"] = _make_checkbox("Flat (03)")
        widgets["active_flat_03"] = _make_checkbox("Active Flat (03)")
        flags.addWidget(widgets["table_03"], 0, 0)
        flags.addWidget(widgets["flat_03"], 0, 1)
        flags.addWidget(widgets["active_flat_03"], 1, 0)
        if rider:
            widgets["post_issue"] = _make_checkbox("Post Issue")
            widgets["post_issue"].setToolTip("Rider issued after the base coverage")
            flags.addWidget(widgets["post_issue"], 1, 1)
        flags.setColumnStretch(2, 1)
        layout.addLayout(flags)
        layout.addStretch()

        return widgets, class_control

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

        # Class (INS_CLS_CD) lives on the Base Coverage column (self.val_class).
        self.val_base = _val_row(0, "Base:")
        self.val_sub = _val_row(1, "Sub:")
        self.val_mort_table = _val_row(2, "Val Mort Table:")
        self.rpu_mort_table = _val_row(3, "RPU Mort Table:")
        self.eti_mort_table = _val_row(4, "ETI Mort Table:")
        self.nfo_int_rate = _val_row(5, "NFO Int Rate:")

        self.chk_val_class_ne_plan = _make_checkbox("Val Class \u2260 PlanDesc Class")
        grid_val.addWidget(self.chk_val_class_ne_plan, 6, 0, 1, 2)

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
        # Fill the column instead of QListWidget's 256px default width hint.
        self.list_non_trad.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        _connect_checkbox_listbox(self.chk_non_trad, self.list_non_trad)
        nt_layout.addWidget(self.list_non_trad)
        col1.addWidget(grp_nontrad)

        # ── Total Curr Specified Amt (Sum 02) ───────────────────────
        # COVSUMMARY.TOTAL_SA: sum of units x VPU over every base coverage.
        grp_sa = QGroupBox("Total Curr Specified Amt (Sum 02)")
        grp_sa.setStyleSheet(_GRP_STYLE)
        grp_sa.setToolTip(
            "Sum of the current specified amount (units \u00d7 VPU) over all base coverages (02)")
        sa_layout = QHBoxLayout(grp_sa)
        sa_layout.setContentsMargins(6, 14, 6, 4)
        sa_layout.setSpacing(0)
        sa_box, self.txt_spec_amt_lo, self.txt_spec_amt_hi = _range_box()
        sa_layout.addWidget(sa_box)
        sa_layout.addStretch()
        # QGroupBox titles do not contribute to the size hint; keep it unclipped.
        title_font = QFont(grp_sa.font())
        title_font.setBold(True)
        grp_sa.setMinimumWidth(QFontMetrics(title_font).horizontalAdvance(grp_sa.title()) + 24)
        col1.addWidget(grp_sa)

        col1.addStretch()

        # ════════════════════════════════════════════════════════════════
        # COLUMN 2 — Init Term Period (02)
        # ════════════════════════════════════════════════════════════════
        col2 = QVBoxLayout()
        col2.setSpacing(_V_SPACING)

        grp_term = QGroupBox()
        grp_term.setStyleSheet(_GRP_STYLE)
        term_layout = QVBoxLayout(grp_term)
        term_layout.setContentsMargins(6, 4, 6, 4)
        term_layout.setSpacing(_V_SPACING)
        self.chk_init_term = _make_checkbox("Term (02)")
        self.chk_init_term.setToolTip("Initial term period (LH_COV_PHA.INT_RNL_PER)")
        term_layout.addWidget(self.chk_init_term)
        self.list_init_term = _make_listbox(
            INIT_TERM_PERIOD_ITEMS, height_rows=29, enabled=False)
        self.list_init_term.setFixedWidth(50)
        _connect_checkbox_listbox(self.chk_init_term, self.list_init_term)
        term_layout.addWidget(self.list_init_term)
        term_layout.addStretch()
        col2.addWidget(grp_term)

        # ════════════════════════════════════════════════════════════════
        # COLUMN 3 — Mortality Table Codes (reference only)
        # ════════════════════════════════════════════════════════════════
        col3 = QVBoxLayout()
        col3.setSpacing(_V_SPACING)

        grp_mort = QGroupBox("Mortality Table Codes")
        grp_mort.setStyleSheet(_REF_GRP_STYLE)
        mort_layout = QVBoxLayout(grp_mort)
        mort_layout.setContentsMargins(6, 14, 6, 4)
        mort_layout.setSpacing(_V_SPACING)
        self.list_mort_table = _make_listbox(
            MORTALITY_TABLE_CODE_ITEMS, height_rows=28, enabled=True)
        metrics = self.list_mort_table.fontMetrics()
        text_w = max(metrics.horizontalAdvance(text) for text in MORTALITY_TABLE_CODE_ITEMS)
        scroll_w = self.list_mort_table.verticalScrollBar().sizeHint().width()
        self.list_mort_table.setFixedWidth(text_w + scroll_w + 12)
        self.list_mort_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list_mort_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_mort_table.setStyleSheet(
            "QListWidget { border: 1px solid #999; background-color: #F5F5F0; color: #555; }"
            "QListWidget::item { padding: 0px 2px; }"
        )
        mort_layout.addWidget(self.list_mort_table)
        mort_layout.addStretch()
        col3.addWidget(grp_mort)

        # ════════════════════════════════════════════════════════════════
        # COLUMNS 4-6 — Base Coverage, Rider 1, optional Rider 2
        # ════════════════════════════════════════════════════════════════
        self.grp_base_cov = QGroupBox("Base Coverage Criteria (02)")
        self.base_cov_widgets, self.val_class = self._build_coverage_column(
            self.grp_base_cov, rider=False)
        self.grp_rider1 = QGroupBox("Rider 1 Criteria")
        self.rider1_widgets, _ = self._build_coverage_column(self.grp_rider1, rider=True)
        self.grp_rider2 = _RemovableGroupBox(
            "Rider 2 Criteria", "Remove Rider 2 criteria (clears its values)")
        self.rider2_widgets, _ = self._build_coverage_column(self.grp_rider2, rider=True)
        self.grp_rider2.removeRequested.connect(self._remove_rider2)

        self.btn_add_rider2 = QToolButton()
        self.btn_add_rider2.setText("+")
        self.btn_add_rider2.setToolTip("Add a Rider 2 criteria group")
        self.btn_add_rider2.setFixedSize(22, 22)
        self.btn_add_rider2.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_rider2.setStyleSheet(_GROUP_BTN_STYLE)
        self.btn_add_rider2.clicked.connect(self._add_rider2)
        add_col = QVBoxLayout()
        add_col.setContentsMargins(0, 2, 0, 0)
        add_col.addWidget(self.btn_add_rider2)
        add_col.addStretch()

        # ── Assemble all columns ────────────────────────────────────
        # Every column keeps its natural width; spare width collects to the
        # right of [+] so toggling Rider 2 never shifts the other columns.
        for col in (col1, col2, col3):
            holder = QWidget()
            holder.setLayout(col)
            col.setContentsMargins(0, 0, 0, 0)
            holder.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            root.addWidget(holder)
        root.addWidget(self.grp_base_cov)
        root.addWidget(self.grp_rider1)
        root.addWidget(self.grp_rider2)
        root.addLayout(add_col)
        root.addStretch()
        self._set_rider2_visible(False)

    # ── Optional Rider 2 group ───────────────────────────────────────

    def rider2_visible(self) -> bool:
        """Whether the optional Rider 2 group is shown (not merely painted)."""
        return not self.grp_rider2.isHidden()

    def _set_rider2_visible(self, visible: bool) -> None:
        self.grp_rider2.setVisible(visible)
        self.btn_add_rider2.setVisible(not visible)

    def _add_rider2(self) -> None:
        self._set_rider2_visible(True)

    def _remove_rider2(self) -> None:
        """Hide Rider 2 and clear it so hidden criteria never reach the SQL."""
        self._set_cov_column_state(self.rider2_widgets, {})
        self._set_rider2_visible(False)

    # ── Profile save/load ────────────────────────────────────────────

    def _get_cov_column_state(self, widgets: dict) -> dict:
        from ..profile_manager import (
            get_lineedit_text as _t, get_checkbox_checked as _c,
            get_combo_text as _cmb,
        )
        from ._styles import MultiSelectPopup
        state = {}
        for key, w in widgets.items():
            from PyQt6.QtWidgets import QLineEdit, QCheckBox, QComboBox
            if isinstance(w, MultiSelectPopup):
                state[key] = w.text()
            elif isinstance(w, QLineEdit):
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
        from ._styles import MultiSelectPopup
        from PyQt6.QtWidgets import QLineEdit, QCheckBox, QComboBox
        for key, w in widgets.items():
            if isinstance(w, MultiSelectPopup):
                w.setText(state.get(key, ""))
            elif isinstance(w, QLineEdit):
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
        rider2_state = state.get("rider2", {})
        self._set_cov_column_state(self.rider2_widgets, rider2_state)
        # Every rider control defaults to blank/unchecked, so any truthy value
        # means the saved query used Rider 2.
        self._set_rider2_visible(any(rider2_state.values()))
