"""
ABR Quote — Medical Assessment Panel (Step 2).

Input form for rider type, survival rates (with enable checkboxes),
direct table/flat extra entry, and goal-seek derivation.

Rider Types:
    Terminal  — No assessment needed; mortality = 50 % per year.
    Chronic   — Full assessment with survival inputs and/or direct table/flat.
    Critical  — Same workflow as Chronic.
"""

from __future__ import annotations

import logging
from dataclasses import replace as dc_replace
from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QCheckBox,
    QGroupBox, QFrame, QScrollArea, QDialog,
    QFileDialog, QMessageBox, QMenu, QApplication,
)

from ..models.abr_data import (
    ABRPolicyData, MedicalAssessment, MortalityParams, ABRQuoteResult,
)
from ..models.abr_database import get_abr_database
from ..models.abr_constants import (
    MORTALITY_IMPROVEMENT_RATE,
    MORTALITY_IMPROVEMENT_CAP,
    MORTALITY_MULTIPLIER,
    MORTALITY_MULTIPLIER_TERMINAL,
    MATURITY_AGE,
    MODAL_LABELS, PLAN_CODE_INFO,
)
from ..core.goal_seek import (
    find_combined_substandard,
    find_dual_table_ratings,
    compute_assessment_index,
)
from ..core.mortality_engine import MortalityEngine
from .abr_styles import (
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_RICH, CRIMSON_SUBTLE,
    SLATE_PRIMARY, SLATE_DARK, SLATE_TEXT,
    WHITE, GRAY_DARK, GRAY_MID, GRAY_TEXT, GRAY_LIGHT,
    GROUP_BOX_STYLE, INPUT_STYLE, COMBOBOX_STYLE,
    BUTTON_SLATE_STYLE, BUTTON_PRIMARY_STYLE,
    LABEL_MONEY_STYLE, LABEL_MONEY_LARGE_STYLE, DIVIDER_STYLE,
    SCROLL_AREA_STYLE,
)

logger = logging.getLogger(__name__)

# Checkbox style — Crimson Slate accent
_CHECKBOX_STYLE = f"""
    QCheckBox {{
        color: {CRIMSON_DARK};
        font-weight: bold;
        font-size: 12px;
        spacing: 6px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 2px solid {CRIMSON_PRIMARY};
        border-radius: 3px;
        background: {WHITE};
    }}
    QCheckBox::indicator:checked {{
        background: {SLATE_PRIMARY};
        border-color: {SLATE_PRIMARY};
    }}
    QCheckBox::indicator:hover {{
        border-color: {SLATE_PRIMARY};
    }}
"""


class AssessmentPanel(QWidget):
    """Step 2 panel — medical assessment input and substandard derivation.

    Signals:
        assessment_ready(MedicalAssessment): Emitted when assessment is computed.
    """

    assessment_ready = pyqtSignal(object)  # MedicalAssessment
    min_face_calc_requested = pyqtSignal()  # recalculate with new min face

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional[ABRPolicyData] = None
        self._assessment: Optional[MedicalAssessment] = None
        self._result: Optional[ABRQuoteResult] = None
        self._default_accel_amount: float = 0.0  # default face for reset
        self._default_min_face: str = "50,000"    # default min face for reset
        self._policy_abr_subtypes: set[str] = set()
        self._policy_abr_rider_types: set[str] = set()
        # Detailed calc data for viewer
        self._mort_detail: list[dict] = []
        self._apv_detail: list[dict] = []
        self._apv_summary: dict = {}
        self._policy_info: str = ""
        self._partial_prem_breakdown: dict | None = None
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        outer_layout = QHBoxLayout()
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(8)

        # ── Left column: assessment inputs ──────────────────────────────
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setStyleSheet(SCROLL_AREA_STYLE)
        left_widget = QWidget()
        layout = QVBoxLayout(left_widget)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        # ── Rider Type Selection ────────────────────────────────────────
        rider_group = QGroupBox("Rider Configuration")
        rider_group.setStyleSheet(GROUP_BOX_STYLE)
        rider_layout = QGridLayout(rider_group)
        rider_layout.setContentsMargins(12, 16, 12, 8)
        rider_layout.setSpacing(8)

        rider_layout.addWidget(
            self._make_label("Rider Type:"), 0, 0, Qt.AlignmentFlag.AlignRight
        )
        self.rider_combo = QComboBox()
        self.rider_combo.addItems(["Chronic", "Critical", "Terminal"])
        self.rider_combo.setStyleSheet(COMBOBOX_STYLE)
        self.rider_combo.currentTextChanged.connect(self._on_rider_changed)
        rider_layout.addWidget(self.rider_combo, 0, 1)

        # Per diem / annual limit labels — shown only for Chronic rider
        per_diem_style = f"font-size: 11px; color: {GRAY_DARK};"
        per_diem_val_style = f"font-size: 11px; color: {CRIMSON_DARK}; font-weight: bold;"

        lbl_pd = QLabel("Per Diem:")
        lbl_pd.setStyleSheet(per_diem_style)
        rider_layout.addWidget(lbl_pd, 0, 3, Qt.AlignmentFlag.AlignRight)
        self._rider_per_diem_label = QLabel("\u2014")
        self._rider_per_diem_label.setStyleSheet(per_diem_val_style)
        rider_layout.addWidget(self._rider_per_diem_label, 0, 4)

        lbl_al = QLabel("Annual Limit:")
        lbl_al.setStyleSheet(per_diem_style)
        rider_layout.addWidget(lbl_al, 0, 5, Qt.AlignmentFlag.AlignRight)
        self._rider_annual_limit_label = QLabel("\u2014")
        self._rider_annual_limit_label.setStyleSheet(per_diem_val_style)
        rider_layout.addWidget(self._rider_annual_limit_label, 0, 6)

        # Container list for show/hide
        self._chronic_only_widgets = [lbl_pd, self._rider_per_diem_label,
                                      lbl_al, self._rider_annual_limit_label]
        is_chronic = self.rider_combo.currentText() == "Chronic"
        for w in self._chronic_only_widgets:
            w.setVisible(is_chronic)
        if is_chronic:
            self._refresh_per_diem_display()

        rider_layout.setColumnStretch(2, 1)
        rider_layout.setColumnStretch(7, 1)

        # Rider type mismatch warning — shown when selected rider is not on the policy
        self._rider_mismatch_label = QLabel("")
        self._rider_mismatch_label.setStyleSheet(
            "color: red; font-weight: bold; font-size: 11px; padding: 0 4px;"
        )
        self._rider_mismatch_label.setWordWrap(True)
        self._rider_mismatch_label.setVisible(False)
        rider_layout.addWidget(self._rider_mismatch_label, 1, 0, 1, 8)

        layout.addWidget(rider_group)

        # ── Assessment Format (survival + direct inputs) ────────────────
        self.assessment_group = QGroupBox("Assessment Format")
        self.assessment_group.setStyleSheet(GROUP_BOX_STYLE)
        assess_vbox = QVBoxLayout(self.assessment_group)
        assess_vbox.setContentsMargins(12, 20, 12, 8)
        assess_vbox.setSpacing(4)

        # (Substandard mode is always "In Lieu Of" — radio UI removed)

        # ── Row 0: 5-Year Survival ───────────────────────────────────────
        row0 = QHBoxLayout()
        row0.setSpacing(6)

        self.chk_five_year = QCheckBox()
        self.chk_five_year.setStyleSheet(_CHECKBOX_STYLE)
        self.chk_five_year.setFixedWidth(20)
        self.chk_five_year.toggled.connect(self._on_checkbox_toggled)
        row0.addWidget(self.chk_five_year)

        lbl_5yr = QLabel("5-Year Survival Rate:")
        lbl_5yr.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;")
        lbl_5yr.setFixedWidth(160)
        row0.addWidget(lbl_5yr)

        self.five_year_input = QLineEdit()
        self.five_year_input.setPlaceholderText("e.g. 0.018")
        self.five_year_input.setStyleSheet(INPUT_STYLE)
        self.five_year_input.setFixedWidth(100)
        self.five_year_input.setReadOnly(True)
        row0.addWidget(self.five_year_input)

        self.chk_return_5yr = QCheckBox("Return (drop after yr 5)")
        self.chk_return_5yr.setStyleSheet(_CHECKBOX_STYLE)
        self.chk_return_5yr.setEnabled(False)
        row0.addWidget(self.chk_return_5yr)

        row0.addStretch()
        assess_vbox.addLayout(row0)

        # ── Row 1: 10-Year Survival ──────────────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        self.chk_ten_year = QCheckBox()
        self.chk_ten_year.setStyleSheet(_CHECKBOX_STYLE)
        self.chk_ten_year.setFixedWidth(20)
        self.chk_ten_year.toggled.connect(self._on_checkbox_toggled)
        row1.addWidget(self.chk_ten_year)

        lbl_10yr = QLabel("10-Year Survival Rate:")
        lbl_10yr.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;")
        lbl_10yr.setFixedWidth(160)
        row1.addWidget(lbl_10yr)

        self.ten_year_input = QLineEdit()
        self.ten_year_input.setPlaceholderText("e.g. 0.500")
        self.ten_year_input.setStyleSheet(INPUT_STYLE)
        self.ten_year_input.setFixedWidth(100)
        self.ten_year_input.setReadOnly(True)
        row1.addWidget(self.ten_year_input)

        self.chk_return_10yr = QCheckBox("Return (drop after yr 10)")
        self.chk_return_10yr.setStyleSheet(_CHECKBOX_STYLE)
        self.chk_return_10yr.setEnabled(False)
        row1.addWidget(self.chk_return_10yr)

        row1.addStretch()
        assess_vbox.addLayout(row1)

        # ── Row 2: Life Expectancy ──────────────────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self.chk_le = QCheckBox()
        self.chk_le.setStyleSheet(_CHECKBOX_STYLE)
        self.chk_le.setFixedWidth(20)
        self.chk_le.toggled.connect(self._on_checkbox_toggled)
        row2.addWidget(self.chk_le)

        lbl_le = QLabel("Life Expectancy:")
        lbl_le.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;")
        lbl_le.setFixedWidth(160)
        row2.addWidget(lbl_le)

        self.le_input = QLineEdit()
        self.le_input.setPlaceholderText("e.g. 4.9")
        self.le_input.setStyleSheet(INPUT_STYLE)
        self.le_input.setFixedWidth(100)
        self.le_input.setReadOnly(True)
        row2.addWidget(self.le_input)

        row2.addStretch()
        assess_vbox.addLayout(row2)

        # ── Row 2b: Increased Decrement ──────────────────────────────────
        row2b = QHBoxLayout()
        row2b.setSpacing(6)

        self.chk_incr_decrement = QCheckBox()
        self.chk_incr_decrement.setStyleSheet(_CHECKBOX_STYLE)
        self.chk_incr_decrement.setFixedWidth(20)
        self.chk_incr_decrement.toggled.connect(self._on_checkbox_toggled)
        row2b.addWidget(self.chk_incr_decrement)

        lbl_id = QLabel("Increased Decrement:")
        lbl_id.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;")
        lbl_id.setFixedWidth(160)
        row2b.addWidget(lbl_id)

        self.incr_decrement_input = QLineEdit()
        self.incr_decrement_input.setPlaceholderText("%")
        self.incr_decrement_input.setStyleSheet(INPUT_STYLE)
        self.incr_decrement_input.setFixedWidth(70)
        self.incr_decrement_input.setReadOnly(True)
        row2b.addWidget(self.incr_decrement_input)

        row2b.addSpacing(10)

        lbl_id_start = QLabel("Start Yr:")
        lbl_id_start.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        row2b.addWidget(lbl_id_start)

        self.incr_decrement_start_input = QLineEdit("1")
        self.incr_decrement_start_input.setStyleSheet(INPUT_STYLE)
        self.incr_decrement_start_input.setFixedWidth(40)
        self.incr_decrement_start_input.setReadOnly(True)
        row2b.addWidget(self.incr_decrement_start_input)

        row2b.addSpacing(6)

        lbl_id_stop = QLabel("Stop Yr:")
        lbl_id_stop.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        row2b.addWidget(lbl_id_stop)

        self.incr_decrement_stop_input = QLineEdit("99")
        self.incr_decrement_stop_input.setStyleSheet(INPUT_STYLE)
        self.incr_decrement_stop_input.setFixedWidth(40)
        self.incr_decrement_stop_input.setReadOnly(True)
        row2b.addWidget(self.incr_decrement_stop_input)

        row2b.addStretch()
        assess_vbox.addLayout(row2b)

        # ── Row 3: Table ─────────────────────────────────────────────────
        row3 = QHBoxLayout()
        row3.setSpacing(6)

        self.chk_table = QCheckBox()
        self.chk_table.setStyleSheet(_CHECKBOX_STYLE)
        self.chk_table.setFixedWidth(20)
        self.chk_table.toggled.connect(self._on_checkbox_toggled)
        row3.addWidget(self.chk_table)

        lbl_table = QLabel("Table:")
        lbl_table.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;")
        lbl_table.setFixedWidth(160)
        row3.addWidget(lbl_table)

        self.table_input = QLineEdit()
        self.table_input.setPlaceholderText("rating")
        self.table_input.setStyleSheet(INPUT_STYLE)
        self.table_input.setFixedWidth(70)
        self.table_input.setReadOnly(True)
        row3.addWidget(self.table_input)

        row3.addSpacing(10)

        lbl_t_start = QLabel("Start Yr:")
        lbl_t_start.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        row3.addWidget(lbl_t_start)

        self.table_start_input = QLineEdit("1")
        self.table_start_input.setStyleSheet(INPUT_STYLE)
        self.table_start_input.setFixedWidth(40)
        self.table_start_input.setReadOnly(True)
        row3.addWidget(self.table_start_input)

        row3.addSpacing(6)

        lbl_t_stop = QLabel("Stop Yr:")
        lbl_t_stop.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        row3.addWidget(lbl_t_stop)

        self.table_stop_input = QLineEdit("99")
        self.table_stop_input.setStyleSheet(INPUT_STYLE)
        self.table_stop_input.setFixedWidth(40)
        self.table_stop_input.setReadOnly(True)
        row3.addWidget(self.table_stop_input)

        row3.addStretch()
        assess_vbox.addLayout(row3)

        # ── Row 4: Flat ──────────────────────────────────────────────────
        row4 = QHBoxLayout()
        row4.setSpacing(6)

        self.chk_flat = QCheckBox()
        self.chk_flat.setStyleSheet(_CHECKBOX_STYLE)
        self.chk_flat.setFixedWidth(20)
        self.chk_flat.toggled.connect(self._on_checkbox_toggled)
        row4.addWidget(self.chk_flat)

        lbl_flat = QLabel("Flat:")
        lbl_flat.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;")
        lbl_flat.setFixedWidth(160)
        row4.addWidget(lbl_flat)

        self.flat_input = QLineEdit()
        self.flat_input.setPlaceholderText("$/1000")
        self.flat_input.setStyleSheet(INPUT_STYLE)
        self.flat_input.setFixedWidth(70)
        self.flat_input.setReadOnly(True)
        row4.addWidget(self.flat_input)

        row4.addSpacing(10)

        lbl_f_start = QLabel("Start Yr:")
        lbl_f_start.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        row4.addWidget(lbl_f_start)

        self.flat_start_input = QLineEdit("1")
        self.flat_start_input.setStyleSheet(INPUT_STYLE)
        self.flat_start_input.setFixedWidth(40)
        self.flat_start_input.setReadOnly(True)
        row4.addWidget(self.flat_start_input)

        row4.addSpacing(6)

        lbl_f_stop = QLabel("Stop Yr:")
        lbl_f_stop.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        row4.addWidget(lbl_f_stop)

        self.flat_stop_input = QLineEdit("99")
        self.flat_stop_input.setStyleSheet(INPUT_STYLE)
        self.flat_stop_input.setFixedWidth(40)
        self.flat_stop_input.setReadOnly(True)
        row4.addWidget(self.flat_stop_input)

        row4.addStretch()
        assess_vbox.addLayout(row4)

        # ── Row 5: Table 2 ───────────────────────────────────────────────
        row5 = QHBoxLayout()
        row5.setSpacing(6)

        self.chk_table_2 = QCheckBox()
        self.chk_table_2.setStyleSheet(_CHECKBOX_STYLE)
        self.chk_table_2.setFixedWidth(20)
        self.chk_table_2.toggled.connect(self._on_checkbox_toggled)
        row5.addWidget(self.chk_table_2)

        lbl_table_2 = QLabel("Table 2:")
        lbl_table_2.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;")
        lbl_table_2.setFixedWidth(160)
        row5.addWidget(lbl_table_2)

        self.table_2_input = QLineEdit()
        self.table_2_input.setPlaceholderText("rating")
        self.table_2_input.setStyleSheet(INPUT_STYLE)
        self.table_2_input.setFixedWidth(70)
        self.table_2_input.setReadOnly(True)
        row5.addWidget(self.table_2_input)

        row5.addSpacing(10)

        lbl_t2_start = QLabel("Start Yr:")
        lbl_t2_start.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        row5.addWidget(lbl_t2_start)

        self.table_2_start_input = QLineEdit("1")
        self.table_2_start_input.setStyleSheet(INPUT_STYLE)
        self.table_2_start_input.setFixedWidth(40)
        self.table_2_start_input.setReadOnly(True)
        row5.addWidget(self.table_2_start_input)

        row5.addSpacing(6)

        lbl_t2_stop = QLabel("Stop Yr:")
        lbl_t2_stop.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        row5.addWidget(lbl_t2_stop)

        self.table_2_stop_input = QLineEdit("99")
        self.table_2_stop_input.setStyleSheet(INPUT_STYLE)
        self.table_2_stop_input.setFixedWidth(40)
        self.table_2_stop_input.setReadOnly(True)
        row5.addWidget(self.table_2_stop_input)

        row5.addStretch()
        assess_vbox.addLayout(row5)

        # ── Row 6: Flat 2 ────────────────────────────────────────────────
        row6 = QHBoxLayout()
        row6.setSpacing(6)

        self.chk_flat_2 = QCheckBox()
        self.chk_flat_2.setStyleSheet(_CHECKBOX_STYLE)
        self.chk_flat_2.setFixedWidth(20)
        self.chk_flat_2.toggled.connect(self._on_checkbox_toggled)
        row6.addWidget(self.chk_flat_2)

        lbl_flat_2 = QLabel("Flat 2:")
        lbl_flat_2.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;")
        lbl_flat_2.setFixedWidth(160)
        row6.addWidget(lbl_flat_2)

        self.flat_2_input = QLineEdit()
        self.flat_2_input.setPlaceholderText("$/1000")
        self.flat_2_input.setStyleSheet(INPUT_STYLE)
        self.flat_2_input.setFixedWidth(70)
        self.flat_2_input.setReadOnly(True)
        row6.addWidget(self.flat_2_input)

        row6.addSpacing(10)

        lbl_f2_start = QLabel("Start Yr:")
        lbl_f2_start.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        row6.addWidget(lbl_f2_start)

        self.flat_2_start_input = QLineEdit("1")
        self.flat_2_start_input.setStyleSheet(INPUT_STYLE)
        self.flat_2_start_input.setFixedWidth(40)
        self.flat_2_start_input.setReadOnly(True)
        row6.addWidget(self.flat_2_start_input)

        row6.addSpacing(6)

        lbl_f2_stop = QLabel("Stop Yr:")
        lbl_f2_stop.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        row6.addWidget(lbl_f2_stop)

        self.flat_2_stop_input = QLineEdit("99")
        self.flat_2_stop_input.setStyleSheet(INPUT_STYLE)
        self.flat_2_stop_input.setFixedWidth(40)
        self.flat_2_stop_input.setReadOnly(True)
        row6.addWidget(self.flat_2_stop_input)

        row6.addStretch()
        assess_vbox.addLayout(row6)

        layout.addWidget(self.assessment_group)

        # ── Warning label (below assessment group, bold red) ───────────
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet(
            "color: red; font-weight: bold; font-size: 11px; padding: 2px 4px;"
        )
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        # ── Calculate button ────────────────────────────────────────────
        calc_row = QHBoxLayout()
        calc_row.addStretch()
        self.calc_btn = QPushButton("Calculate Substandard")
        self.calc_btn.setStyleSheet(BUTTON_SLATE_STYLE)
        self.calc_btn.clicked.connect(self._on_calculate)
        calc_row.addWidget(self.calc_btn)
        calc_row.addStretch()
        layout.addLayout(calc_row)

        # ── Derived Substandard Results ─────────────────────────────────
        self.derived_group = QGroupBox("Derived Substandard Values")
        self.derived_group.setStyleSheet(GROUP_BOX_STYLE)
        derived_layout = QGridLayout(self.derived_group)
        derived_layout.setContentsMargins(8, 14, 8, 4)
        derived_layout.setSpacing(2)

        self._derived_labels = {}

        HEADER_STYLE = (
            f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;"
            f" text-decoration: underline; padding-bottom: 1px;"
        )
        LABEL_STYLE = f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;"
        VALUE_STYLE = f"color: {GRAY_DARK}; font-size: 11px;"

        # ── Left column header: Current (Unmodified) ─────────────────
        hdr_left = QLabel("Current (Unmodified)")
        hdr_left.setStyleSheet(HEADER_STYLE)
        derived_layout.addWidget(hdr_left, 0, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)

        left_fields = [
            (1, "5-Year Survival:", "std_survival_5yr"),
            (2, "10-Year Survival:", "std_survival_10yr"),
            (3, "Life Expectancy:", "std_le"),
            (4, "Table Rating:", "std_table_rating"),
            (5, "Flat Extra:", "std_flat_extra"),
        ]
        for row, label_text, key in left_fields:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(LABEL_STYLE)
            derived_layout.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignRight)
            val = QLabel("\u2014")
            val.setStyleSheet(VALUE_STYLE)
            derived_layout.addWidget(val, row, 1, Qt.AlignmentFlag.AlignLeft)
            self._derived_labels[key] = val

        # ── Spacer column ────────────────────────────────────────────
        derived_layout.setColumnMinimumWidth(2, 16)

        # ── Right column header: Modified (Substandard Applied) ──────
        hdr_right = QLabel("Modified (Substandard Applied)")
        hdr_right.setStyleSheet(HEADER_STYLE)
        derived_layout.addWidget(hdr_right, 0, 3, 1, 2, Qt.AlignmentFlag.AlignCenter)

        right_fields = [
            (1, "5-Year Survival:", "mod_survival_5yr"),
            (2, "10-Year Survival:", "mod_survival_10yr"),
            (3, "Life Expectancy:", "mod_le"),
            (4, "Table Ratings:", "table_rating"),
            (5, "Flat Extras:", "flat_extra"),
        ]
        for row, label_text, key in right_fields:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(LABEL_STYLE)
            derived_layout.addWidget(lbl, row, 3, Qt.AlignmentFlag.AlignRight)
            val = QLabel("\u2014")
            val.setStyleSheet(VALUE_STYLE)
            derived_layout.addWidget(val, row, 4, Qt.AlignmentFlag.AlignLeft)
            self._derived_labels[key] = val

        derived_layout.setColumnStretch(5, 1)
        self.derived_group.setVisible(False)
        layout.addWidget(self.derived_group)

        # ── Status ──────────────────────────────────────────────────────
        self.status_label = QLabel("Load a policy first, then enter medical assessment values.")
        self.status_label.setStyleSheet(
            f"color: {GRAY_DARK}; font-size: 11px; font-style: italic; padding: 4px;"
        )
        layout.addWidget(self.status_label)

        layout.addStretch()

        left_scroll.setWidget(left_widget)
        outer_layout.addWidget(left_scroll, stretch=5)

        # ── Right column: Results ───────────────────────────────────────
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet(SCROLL_AREA_STYLE)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 4, 8, 4)
        right_layout.setSpacing(10)

        self._build_results_column(right_layout)

        right_scroll.setWidget(right_widget)
        self.results_column = right_scroll
        outer_layout.addWidget(right_scroll, stretch=4)

        main_layout.addLayout(outer_layout, 1)

        # ── Bottom-right View Calc button ───────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(8, 2, 12, 6)
        bottom_row.addStretch()

        self.res_view_calc_btn = QPushButton("View Calc")
        self.res_view_calc_btn.setStyleSheet(
            f"QPushButton {{ color: {SLATE_TEXT}; background: transparent; "
            f"border: 1px solid {SLATE_PRIMARY}; border-radius: 3px; "
            f"padding: 2px 10px; font-size: 10px; }}"
            f"QPushButton:hover {{ background: {CRIMSON_SUBTLE}; }}"
            f"QPushButton:disabled {{ color: rgba(0,0,0,0.3); border-color: rgba(0,0,0,0.15); }}"
        )
        self.res_view_calc_btn.setToolTip("Inspect month-by-month mortality and APV")
        self.res_view_calc_btn.clicked.connect(self._on_res_view_calc)
        self.res_view_calc_btn.setEnabled(False)
        bottom_row.addWidget(self.res_view_calc_btn)

        main_layout.addLayout(bottom_row)

    # ── Right column builder ────────────────────────────────────────────

    def _build_results_column(self, layout: QVBoxLayout):
        """Build the results groups (Full, Partial, Premium) in the right column."""

        # ── Acceleration amount label + input + Calc ────────────────────
        accel_row = QHBoxLayout()
        accel_row.setSpacing(8)

        _crimson_btn_style = f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CRIMSON_RICH}, stop:1 {CRIMSON_PRIMARY});
                color: {WHITE};
                border: 1px solid {CRIMSON_DARK};
                border-radius: 5px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CRIMSON_PRIMARY}, stop:1 {CRIMSON_DARK});
            }}
        """

        _reset_btn_style = f"""
            QPushButton {{
                background: transparent;
                color: {CRIMSON_PRIMARY};
                border: 1px solid {CRIMSON_PRIMARY};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {CRIMSON_SUBTLE};
            }}
        """

        self._accel_label = QLabel("Full Face Amount:")
        self._accel_label.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {CRIMSON_DARK};")
        accel_row.addWidget(self._accel_label)

        self._accel_reset_btn = QPushButton("Reset Full Face")
        self._accel_reset_btn.setStyleSheet(_reset_btn_style)
        self._accel_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._accel_reset_btn.clicked.connect(self._on_accel_reset)
        self._accel_reset_btn.setVisible(False)
        accel_row.addWidget(self._accel_reset_btn)

        self._face_input = QLineEdit()
        self._face_input.setStyleSheet(INPUT_STYLE)
        self._face_input.setFixedWidth(150)
        self._face_input.setPlaceholderText("Face amount")
        accel_row.addWidget(self._face_input)

        self._face_calc_btn = QPushButton("Calc")
        self._face_calc_btn.setFixedWidth(60)
        self._face_calc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._face_calc_btn.setStyleSheet(_crimson_btn_style)
        self._face_calc_btn.clicked.connect(self._on_face_calc)
        accel_row.addWidget(self._face_calc_btn)

        accel_row.addStretch()
        layout.addLayout(accel_row)

        # ── Full Acceleration ───────────────────────────────────────────
        self.res_full_group = QGroupBox("Full Acceleration")
        self.res_full_group.setStyleSheet(GROUP_BOX_STYLE)
        full_grid = QGridLayout(self.res_full_group)
        full_grid.setContentsMargins(12, 16, 12, 8)
        full_grid.setSpacing(4)
        full_grid.setHorizontalSpacing(8)

        self._res_full_labels = {}
        for i, (label_text, key) in enumerate([
            ("Eligible Death Benefit:", "eligible_db"),
            ("Actuarial Discount:", "actuarial_discount"),
            ("Administrative Fee:", "admin_fee"),
        ]):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 11px; color: {GRAY_DARK};")
            full_grid.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignRight)
            val = QLabel("\u2014")
            val.setStyleSheet(f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            full_grid.addWidget(val, i, 1, Qt.AlignmentFlag.AlignLeft)
            self._res_full_labels[key] = val

        # Loan Repayment row (visible only for UL/IUL/ISWL)
        self._full_loan_lbl = QLabel("Loan Repayment:")
        self._full_loan_lbl.setStyleSheet(f"font-size: 11px; color: {GRAY_DARK};")
        full_grid.addWidget(self._full_loan_lbl, 3, 0, Qt.AlignmentFlag.AlignRight)
        self._res_full_labels["loan_repayment"] = QLabel("\u2014")
        self._res_full_labels["loan_repayment"].setStyleSheet(f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;")
        self._res_full_labels["loan_repayment"].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        full_grid.addWidget(self._res_full_labels["loan_repayment"], 3, 1, Qt.AlignmentFlag.AlignLeft)
        self._full_loan_lbl.setVisible(False)
        self._res_full_labels["loan_repayment"].setVisible(False)

        divider = QFrame()
        divider.setStyleSheet(DIVIDER_STYLE)
        divider.setFixedHeight(2)
        full_grid.addWidget(divider, 4, 0, 1, 2)

        lbl_ab = QLabel("Calculated Benefit:")
        lbl_ab.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {CRIMSON_DARK};")
        full_grid.addWidget(lbl_ab, 5, 0, Qt.AlignmentFlag.AlignRight)

        self.res_full_benefit_label = QLabel("\u2014")
        self.res_full_benefit_label.setStyleSheet(LABEL_MONEY_LARGE_STYLE)
        full_grid.addWidget(self.res_full_benefit_label, 5, 1, Qt.AlignmentFlag.AlignLeft)

        lbl_br = QLabel("Benefit Ratio:")
        lbl_br.setStyleSheet(f"font-size: 10px; color: {GRAY_TEXT};")
        full_grid.addWidget(lbl_br, 6, 0, Qt.AlignmentFlag.AlignRight)
        self.res_full_ratio_label = QLabel("\u2014")
        self.res_full_ratio_label.setStyleSheet(f"font-size: 10px; color: {GRAY_TEXT}; font-weight: bold;")
        full_grid.addWidget(self.res_full_ratio_label, 6, 1, Qt.AlignmentFlag.AlignLeft)

        # Surrender Value row (visible only for UL/IUL/ISWL with surrender value)
        self._full_sv_lbl = QLabel("Surrender Value:")
        self._full_sv_lbl.setStyleSheet(f"font-size: 11px; color: {GRAY_DARK};")
        full_grid.addWidget(self._full_sv_lbl, 7, 0, Qt.AlignmentFlag.AlignRight)
        self._res_full_labels["surrender_value"] = QLabel("\u2014")
        self._res_full_labels["surrender_value"].setStyleSheet(f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;")
        self._res_full_labels["surrender_value"].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        full_grid.addWidget(self._res_full_labels["surrender_value"], 7, 1, Qt.AlignmentFlag.AlignLeft)
        self._full_sv_lbl.setVisible(False)
        self._res_full_labels["surrender_value"].setVisible(False)

        # Accelerated Benefit row (max of calc benefit and surrender, UL only)
        self._full_accel_lbl = QLabel("Accelerated Benefit:")
        self._full_accel_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {CRIMSON_DARK};")
        full_grid.addWidget(self._full_accel_lbl, 8, 0, Qt.AlignmentFlag.AlignRight)
        self.res_full_accel_benefit_label = QLabel("\u2014")
        self.res_full_accel_benefit_label.setStyleSheet(LABEL_MONEY_LARGE_STYLE)
        full_grid.addWidget(self.res_full_accel_benefit_label, 8, 1, Qt.AlignmentFlag.AlignLeft)
        self._full_accel_lbl.setVisible(False)
        self.res_full_accel_benefit_label.setVisible(False)

        # ── Vertical separator between main values and APV block ────────
        vsep_full = QFrame()
        vsep_full.setFrameShape(QFrame.Shape.VLine)
        vsep_full.setStyleSheet(f"color: {GRAY_MID}; background: {GRAY_MID};")
        full_grid.addWidget(vsep_full, 0, 2, 9, 1)

        # APV component labels — right column (cols 3 & 4)
        apv_lbl_style = f"font-size: 11px; color: {GRAY_DARK};"
        apv_val_style  = f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;"
        self._res_full_apv_labels = {}
        for j, (apv_label, apv_key) in enumerate([
            ("APV_FB:", "apv_fb"),
            ("APV_FP:", "apv_fp"),
            ("APV_FD:", "apv_fd"),
        ]):
            lbl = QLabel(apv_label)
            lbl.setStyleSheet(apv_lbl_style)
            full_grid.addWidget(lbl, j, 3, Qt.AlignmentFlag.AlignRight)
            val = QLabel("\u2014")
            val.setStyleSheet(apv_val_style)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            full_grid.addWidget(val, j, 4, Qt.AlignmentFlag.AlignLeft)
            self._res_full_apv_labels[apv_key] = val

        full_grid.setColumnStretch(1, 2)
        full_grid.setColumnStretch(4, 2)
        layout.addWidget(self.res_full_group)

        # ── Min Face Amount input ───────────────────────────────────────
        min_face_row = QHBoxLayout()
        min_face_row.setContentsMargins(0, 2, 0, 2)
        self._min_face_label = QLabel("Min Face Amount:")
        self._min_face_label.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {CRIMSON_DARK};")
        min_face_row.addWidget(self._min_face_label)

        self._min_face_reset_btn = QPushButton("Reset Min Amount")
        self._min_face_reset_btn.setStyleSheet(_reset_btn_style)
        self._min_face_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._min_face_reset_btn.clicked.connect(self._on_min_face_reset)
        self._min_face_reset_btn.setVisible(False)
        min_face_row.addWidget(self._min_face_reset_btn)

        self._min_face_input = QLineEdit()
        self._min_face_input.setStyleSheet(INPUT_STYLE)
        self._min_face_input.setFixedWidth(120)
        self._min_face_input.setText("50,000")
        min_face_row.addWidget(self._min_face_input)

        self._min_face_calc_btn = QPushButton("Calc")
        self._min_face_calc_btn.setFixedWidth(60)
        self._min_face_calc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._min_face_calc_btn.setStyleSheet(_crimson_btn_style)
        self._min_face_calc_btn.clicked.connect(self._on_min_face_calc)
        min_face_row.addWidget(self._min_face_calc_btn)

        min_face_row.addStretch()
        layout.addLayout(min_face_row)

        # ── Max Partial Acceleration ────────────────────────────────────
        self.res_partial_group = QGroupBox("Max Partial Acceleration")
        self.res_partial_group.setStyleSheet(GROUP_BOX_STYLE)
        partial_grid = QGridLayout(self.res_partial_group)
        partial_grid.setContentsMargins(12, 16, 12, 8)
        partial_grid.setSpacing(4)
        partial_grid.setHorizontalSpacing(8)

        self._res_partial_labels = {}
        self._res_partial_static_widgets = []  # track all widgets to hide when at min face
        for i, (label_text, key) in enumerate([
            ("Eligible Death Benefit:", "eligible_db"),
            ("Actuarial Discount:", "actuarial_discount"),
            ("Administrative Fee:", "admin_fee"),
        ]):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 11px; color: {GRAY_DARK};")
            partial_grid.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignRight)
            val = QLabel("\u2014")
            val.setStyleSheet(f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            partial_grid.addWidget(val, i, 1, Qt.AlignmentFlag.AlignLeft)
            self._res_partial_labels[key] = val
            self._res_partial_static_widgets.append(lbl)

        # Loan Repayment row (visible only for UL/IUL/ISWL)
        self._partial_loan_lbl = QLabel("Loan Repayment:")
        self._partial_loan_lbl.setStyleSheet(f"font-size: 11px; color: {GRAY_DARK};")
        partial_grid.addWidget(self._partial_loan_lbl, 3, 0, Qt.AlignmentFlag.AlignRight)
        self._res_partial_labels["loan_repayment"] = QLabel("\u2014")
        self._res_partial_labels["loan_repayment"].setStyleSheet(f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;")
        self._res_partial_labels["loan_repayment"].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        partial_grid.addWidget(self._res_partial_labels["loan_repayment"], 3, 1, Qt.AlignmentFlag.AlignLeft)
        self._partial_loan_lbl.setVisible(False)
        self._res_partial_labels["loan_repayment"].setVisible(False)
        self._res_partial_static_widgets.append(self._partial_loan_lbl)

        divider2 = QFrame()
        divider2.setStyleSheet(DIVIDER_STYLE)
        divider2.setFixedHeight(2)
        partial_grid.addWidget(divider2, 4, 0, 1, 2)
        self._res_partial_static_widgets.append(divider2)

        lbl_pab = QLabel("Calculated Benefit:")
        lbl_pab.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {CRIMSON_DARK};")
        partial_grid.addWidget(lbl_pab, 5, 0, Qt.AlignmentFlag.AlignRight)
        self._res_partial_static_widgets.append(lbl_pab)

        self.res_partial_benefit_label = QLabel("\u2014")
        self.res_partial_benefit_label.setStyleSheet(LABEL_MONEY_LARGE_STYLE)
        partial_grid.addWidget(self.res_partial_benefit_label, 5, 1, Qt.AlignmentFlag.AlignLeft)

        lbl_pbr = QLabel("Benefit Ratio:")
        lbl_pbr.setStyleSheet(f"font-size: 10px; color: {GRAY_TEXT};")
        partial_grid.addWidget(lbl_pbr, 6, 0, Qt.AlignmentFlag.AlignRight)
        self._res_partial_static_widgets.append(lbl_pbr)
        self.res_partial_ratio_label = QLabel("\u2014")
        self.res_partial_ratio_label.setStyleSheet(f"font-size: 10px; color: {GRAY_TEXT}; font-weight: bold;")
        partial_grid.addWidget(self.res_partial_ratio_label, 6, 1, Qt.AlignmentFlag.AlignLeft)

        # Surrender Value row (visible only for UL/IUL/ISWL with surrender value)
        self._partial_sv_lbl = QLabel("Surrender Value:")
        self._partial_sv_lbl.setStyleSheet(f"font-size: 11px; color: {GRAY_DARK};")
        partial_grid.addWidget(self._partial_sv_lbl, 7, 0, Qt.AlignmentFlag.AlignRight)
        self._res_partial_labels["surrender_value"] = QLabel("\u2014")
        self._res_partial_labels["surrender_value"].setStyleSheet(f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;")
        self._res_partial_labels["surrender_value"].setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        partial_grid.addWidget(self._res_partial_labels["surrender_value"], 7, 1, Qt.AlignmentFlag.AlignLeft)
        self._partial_sv_lbl.setVisible(False)
        self._res_partial_labels["surrender_value"].setVisible(False)
        self._res_partial_static_widgets.append(self._partial_sv_lbl)

        # Accelerated Benefit row (max of calc benefit and surrender, UL only)
        self._partial_accel_lbl = QLabel("Accelerated Benefit:")
        self._partial_accel_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {CRIMSON_DARK};")
        partial_grid.addWidget(self._partial_accel_lbl, 8, 0, Qt.AlignmentFlag.AlignRight)
        self.res_partial_accel_benefit_label = QLabel("\u2014")
        self.res_partial_accel_benefit_label.setStyleSheet(LABEL_MONEY_LARGE_STYLE)
        partial_grid.addWidget(self.res_partial_accel_benefit_label, 8, 1, Qt.AlignmentFlag.AlignLeft)
        self._partial_accel_lbl.setVisible(False)
        self.res_partial_accel_benefit_label.setVisible(False)
        self._res_partial_static_widgets.append(self._partial_accel_lbl)

        # ── Vertical separator between main values and APV block ────────
        vsep_partial = QFrame()
        vsep_partial.setFrameShape(QFrame.Shape.VLine)
        vsep_partial.setStyleSheet(f"color: {GRAY_MID}; background: {GRAY_MID};")
        partial_grid.addWidget(vsep_partial, 0, 2, 9, 1)
        self._res_partial_static_widgets.append(vsep_partial)

        # APV component labels — right column (cols 3 & 4)
        apv_lbl_style = f"font-size: 11px; color: {GRAY_DARK};"
        apv_val_style  = f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;"
        self._res_partial_apv_labels = {}
        for j, (apv_label, apv_key) in enumerate([
            ("APV_FB:", "apv_fb"),
            ("APV_FP:", "apv_fp"),
            ("APV_FD:", "apv_fd"),
        ]):
            lbl = QLabel(apv_label)
            lbl.setStyleSheet(apv_lbl_style)
            partial_grid.addWidget(lbl, j, 3, Qt.AlignmentFlag.AlignRight)
            val = QLabel("\u2014")
            val.setStyleSheet(apv_val_style)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            partial_grid.addWidget(val, j, 4, Qt.AlignmentFlag.AlignLeft)
            self._res_partial_apv_labels[apv_key] = val
            self._res_partial_static_widgets.append(lbl)

        # "Not allowed" overlay label — shown when policy is at minimum face
        self._partial_not_allowed_label = QLabel(
            "MAX PARTIAL NOT ALLOWED\nPOLICY ALREADY AT MINIMUM FACE"
        )
        self._partial_not_allowed_label.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {CRIMSON_DARK}; padding: 16px;"
        )
        self._partial_not_allowed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._partial_not_allowed_label.setVisible(False)
        partial_grid.addWidget(self._partial_not_allowed_label, 0, 0, 9, 5)

        partial_grid.setColumnStretch(1, 2)
        partial_grid.setColumnStretch(4, 2)
        layout.addWidget(self.res_partial_group)

        # ── Premium Impact ──────────────────────────────────────────────
        self.res_premium_group = QGroupBox("Premium Impact")
        self.res_premium_group.setStyleSheet(GROUP_BOX_STYLE)
        prem_grid = QGridLayout(self.res_premium_group)
        prem_grid.setContentsMargins(12, 16, 12, 8)
        prem_grid.setSpacing(4)

        self._prem_row_labels = []
        for i, label_text in enumerate(["Premium Before:", "After (Full Accel):", "After (Max Partial):"]):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {CRIMSON_DARK};")
            prem_grid.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignRight)
            self._prem_row_labels.append(lbl)

        self.res_premium_before_label = QLabel("\u2014")
        self.res_premium_before_label.setStyleSheet(LABEL_MONEY_STYLE)
        prem_grid.addWidget(self.res_premium_before_label, 0, 1)

        self.res_premium_after_full_label = QLabel("\u2014")
        self.res_premium_after_full_label.setStyleSheet(LABEL_MONEY_STYLE)
        prem_grid.addWidget(self.res_premium_after_full_label, 1, 1)

        # After (Partial): read-only label for non-UL, editable input for UL
        self.res_premium_after_partial_label = QLabel("\u2014")
        self.res_premium_after_partial_label.setStyleSheet(LABEL_MONEY_STYLE)
        prem_grid.addWidget(self.res_premium_after_partial_label, 2, 1)

        self.res_premium_after_partial_input = QLineEdit()
        self.res_premium_after_partial_input.setPlaceholderText("0.00")
        self.res_premium_after_partial_input.setStyleSheet(INPUT_STYLE)
        self.res_premium_after_partial_input.setFixedWidth(120)
        self.res_premium_after_partial_input.setVisible(False)
        prem_grid.addWidget(self.res_premium_after_partial_input, 2, 1)

        # 🔎 View premium calculation button next to After (Partial)
        self._partial_prem_detail_btn = QPushButton("🔎")
        self._partial_prem_detail_btn.setFixedSize(22, 20)
        self._partial_prem_detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._partial_prem_detail_btn.setToolTip("View premium calculation breakdown")
        self._partial_prem_detail_btn.setStyleSheet(
            f"QPushButton {{ font-size: 11px; border: 1px solid {CRIMSON_PRIMARY};"
            f" border-radius: 3px; background: {WHITE}; padding: 0; }}"
            f"QPushButton:hover {{ background: {CRIMSON_SUBTLE}; }}"
        )
        self._partial_prem_detail_btn.clicked.connect(self._show_partial_premium_breakdown)
        self._partial_prem_detail_btn.setVisible(False)
        prem_grid.addWidget(self._partial_prem_detail_btn, 2, 2)

        prem_grid.setColumnStretch(3, 1)
        layout.addWidget(self.res_premium_group)

        # ── Messages ────────────────────────────────────────────────────
        self.res_messages_label = QLabel("")
        self.res_messages_label.setWordWrap(True)
        self.res_messages_label.setStyleSheet(
            f"color: #C62828; font-size: 13px; font-weight: bold; padding: 4px;"
        )
        self.res_messages_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.res_messages_label.customContextMenuRequested.connect(self._show_messages_context_menu)
        layout.addWidget(self.res_messages_label)

        layout.addStretch()

    # ── Results helpers ─────────────────────────────────────────────────

    @staticmethod
    def _fmt_money(amount: float) -> str:
        if amount < 0:
            return f"(${abs(amount):,.2f})"
        return f"${amount:,.2f}"

    def display_results(self, result: ABRQuoteResult):
        """Populate the right-column result fields."""
        is_first_display = self._result is None
        self._result = result
        self.results_column.setVisible(True)

        # Default the acceleration amount based on DB option —
        # only on the first display; preserve user edits on recalcs.
        if is_first_display:
            self._populate_default_acceleration_amount()
        self.res_full_group.setTitle("Full Acceleration")

        # Full acceleration
        self._res_full_labels["eligible_db"].setText(self._fmt_money(result.full_eligible_db))
        self._res_full_labels["actuarial_discount"].setText(
            self._fmt_money(result.full_actuarial_discount)
        )
        self._res_full_labels["admin_fee"].setText(self._fmt_money(result.full_admin_fee))

        # Show Loan Repayment row only for UL/IUL/ISWL with a non-zero loan
        has_loan = result.full_loan_repayment > 0
        self._full_loan_lbl.setVisible(has_loan)
        self._res_full_labels["loan_repayment"].setVisible(has_loan)
        if has_loan:
            self._res_full_labels["loan_repayment"].setText(self._fmt_money(result.full_loan_repayment))

        if result.full_accel_benefit < 0:
            self.res_full_benefit_label.setText(
                f"$0.00  (calc: {self._fmt_money(result.full_accel_benefit)})"
            )
        else:
            self.res_full_benefit_label.setText(self._fmt_money(result.full_accel_benefit))
        self.res_full_ratio_label.setText(f"{result.full_benefit_ratio * 100:.2f}%")

        # Surrender Value and Accelerated Benefit rows (UL/IUL/ISWL only)
        has_sv = result.full_surrender_value > 0
        self._full_sv_lbl.setVisible(has_sv)
        self._res_full_labels["surrender_value"].setVisible(has_sv)
        self._full_accel_lbl.setVisible(has_sv)
        self.res_full_accel_benefit_label.setVisible(has_sv)
        if has_sv:
            self._res_full_labels["surrender_value"].setText(self._fmt_money(result.full_surrender_value))
            calc_benefit = max(0.0, result.full_accel_benefit)
            accel_benefit = max(calc_benefit, result.full_surrender_value)
            self.res_full_accel_benefit_label.setText(self._fmt_money(accel_benefit))

        # Full APV components
        self._res_full_apv_labels["apv_fb"].setText(self._fmt_money(result.apv_fb))
        self._res_full_apv_labels["apv_fp"].setText(self._fmt_money(result.apv_fp))
        self._res_full_apv_labels["apv_fd"].setText(self._fmt_money(result.apv_fd))

        # Partial acceleration — check if at minimum face
        at_min_face = result.partial_eligible_db <= 0
        has_partial_loan = result.partial_loan_repayment > 0
        has_partial_sv = result.partial_surrender_value > 0
        self._partial_not_allowed_label.setVisible(at_min_face)
        # Hide/show the normal partial detail widgets
        for w in self._res_partial_static_widgets:
            # Surrender-value and accel-benefit labels are in static widgets
            # but need special visibility handling
            if w in (self._partial_sv_lbl, self._partial_accel_lbl):
                w.setVisible(not at_min_face and has_partial_sv)
            else:
                w.setVisible(not at_min_face)
        for key, val in self._res_partial_labels.items():
            if key == "loan_repayment":
                val.setVisible(not at_min_face and has_partial_loan)
            elif key == "surrender_value":
                val.setVisible(not at_min_face and has_partial_sv)
            else:
                val.setVisible(not at_min_face)
        # Also control loan label visibility
        self._partial_loan_lbl.setVisible(not at_min_face and has_partial_loan)
        self._partial_sv_lbl.setVisible(not at_min_face and has_partial_sv)
        self.res_partial_benefit_label.setVisible(not at_min_face)
        self.res_partial_ratio_label.setVisible(not at_min_face)
        self.res_partial_accel_benefit_label.setVisible(not at_min_face and has_partial_sv)
        for val in self._res_partial_apv_labels.values():
            val.setVisible(not at_min_face)

        if not at_min_face:
            self._res_partial_labels["eligible_db"].setText(self._fmt_money(result.partial_eligible_db))
            self._res_partial_labels["actuarial_discount"].setText(
                self._fmt_money(result.partial_actuarial_discount)
            )
            self._res_partial_labels["admin_fee"].setText(self._fmt_money(result.partial_admin_fee))
            if has_partial_loan:
                self._res_partial_labels["loan_repayment"].setText(self._fmt_money(result.partial_loan_repayment))
            if result.partial_accel_benefit < 0:
                self.res_partial_benefit_label.setText(
                    f"$0.00  (calc: {self._fmt_money(result.partial_accel_benefit)})"
                )
            else:
                self.res_partial_benefit_label.setText(self._fmt_money(result.partial_accel_benefit))
            self.res_partial_ratio_label.setText(f"{result.partial_benefit_ratio * 100:.2f}%")

            # Surrender Value and Accelerated Benefit for partial
            if has_partial_sv:
                self._res_partial_labels["surrender_value"].setText(self._fmt_money(result.partial_surrender_value))
                calc_benefit = max(0.0, result.partial_accel_benefit)
                accel_benefit = max(calc_benefit, result.partial_surrender_value)
                self.res_partial_accel_benefit_label.setText(self._fmt_money(accel_benefit))

            # Partial APV components (proportionally scaled)
            if result.full_eligible_db > 0:
                ratio = result.partial_eligible_db / result.full_eligible_db
            else:
                ratio = 0.0
            self._res_partial_apv_labels["apv_fb"].setText(
                self._fmt_money(result.apv_fb * ratio)
            )
            self._res_partial_apv_labels["apv_fp"].setText(
                self._fmt_money(result.apv_fp * ratio)
            )
            self._res_partial_apv_labels["apv_fd"].setText(
                self._fmt_money(result.apv_fd * ratio)
            )

        # Premium impact
        self.res_premium_before_label.setText(result.premium_before)
        self.res_premium_after_full_label.setText(f"${result.premium_after_full:,.2f}")
        is_ul = self._policy and self._policy.product_type in ("UL", "IUL", "ISWL")
        if is_ul:
            # UL: After (Partial) is a user input — don't overwrite it
            self.res_premium_after_partial_label.setVisible(False)
            self.res_premium_after_partial_input.setVisible(not at_min_face)
        elif at_min_face:
            self.res_premium_after_partial_label.setText("NOT ALLOWED")
        else:
            self.res_premium_after_partial_label.setText(result.premium_after_partial)

        # Messages
        if result.messages:
            bullets = "\n\n".join(f"\u2022 {m}" for m in result.messages)
            self.res_messages_label.setText(bullets)
        else:
            self.res_messages_label.setText("")

        # If user had a custom acceleration amount, re-apply proportional
        # recalculation so the Full Acceleration section stays in sync.
        if not is_first_display:
            raw = self._face_input.text().replace("$", "").replace(",", "").strip()
            try:
                current = float(raw)
            except ValueError:
                current = 0.0
            if current > 0 and abs(current - self._default_accel_amount) >= 0.01:
                self._on_face_calc()

    # ── Acceleration amount controls ──────────────────────────────────

    def _populate_default_acceleration_amount(self):
        """Set the default acceleration amount based on DB option.

        DB Option A (code "1"): Face Amount
        DB Option B (code "2"): Face Amount + Account Value
        DB Option C (code "3"): Face Amount + Total Premiums Paid
        Otherwise:              Face Amount
        """
        if not self._policy:
            return
        p = self._policy
        db_opt = p.db_option
        if db_opt == "2":
            default_amount = p.face_amount + p.account_value
        elif db_opt == "3":
            default_amount = p.face_amount + p.premiums_paid_to_date
        else:
            default_amount = p.face_amount
        self._default_accel_amount = default_amount
        self._face_input.setText(f"{default_amount:,.2f}")
        self._update_accel_reset_visibility()

    def _on_face_calc(self):
        """Recalculate Full Acceleration (and Max Partial) with the user-entered full face amount."""
        if not self._policy or not self._result:
            return

        raw = self._face_input.text().replace("$", "").replace(",", "").strip()
        try:
            custom_face = float(raw)
        except ValueError:
            self.res_messages_label.setText("\u2022 Please enter a valid numeric face amount.")
            return

        result = self._result

        # Restore any result messages (remove stale validation messages)
        if result.messages:
            bullets = "\n\n".join(f"\u2022 {m}" for m in result.messages)
            self.res_messages_label.setText(bullets)
        else:
            self.res_messages_label.setText("")

        # Title always stays Full Acceleration
        self.res_full_group.setTitle("Full Acceleration")

        # ── Full Acceleration — proportional recalculation ─────────────
        orig_eligible = result.full_eligible_db
        orig_discount = result.full_actuarial_discount
        admin_fee = result.full_admin_fee

        if orig_eligible > 0:
            ratio = custom_face / orig_eligible
            new_discount = round(orig_discount * ratio, 2)
        else:
            ratio = 0.0
            new_discount = 0.0

        # Loan repayment — proportionally scaled
        orig_loan = result.full_loan_repayment
        if orig_eligible > 0 and orig_loan > 0:
            new_loan = round(orig_loan * ratio, 2)
            self._full_loan_lbl.setVisible(True)
            self._res_full_labels["loan_repayment"].setVisible(True)
            self._res_full_labels["loan_repayment"].setText(self._fmt_money(new_loan))
            new_benefit = round(custom_face - new_discount - admin_fee - new_loan, 2)
        else:
            new_benefit = round(custom_face - new_discount - admin_fee, 2)

        # Surrender value — proportionally scaled
        orig_sv = result.full_surrender_value
        if orig_eligible > 0 and orig_sv > 0:
            new_sv = round(orig_sv * ratio, 2)
        else:
            new_sv = 0.0

        new_ratio = max(0.0, new_benefit) / custom_face if custom_face > 0 else 0.0

        self._res_full_labels["eligible_db"].setText(self._fmt_money(custom_face))
        self._res_full_labels["actuarial_discount"].setText(self._fmt_money(new_discount))
        self._res_full_labels["admin_fee"].setText(self._fmt_money(admin_fee))

        if new_benefit < 0:
            self.res_full_benefit_label.setText(
                f"$0.00  (calc: {self._fmt_money(new_benefit)})"
            )
        else:
            self.res_full_benefit_label.setText(self._fmt_money(new_benefit))
        self.res_full_ratio_label.setText(f"{new_ratio * 100:.2f}%")

        # Surrender Value and Accelerated Benefit — proportionally scaled
        has_sv = new_sv > 0
        self._full_sv_lbl.setVisible(has_sv)
        self._res_full_labels["surrender_value"].setVisible(has_sv)
        self._full_accel_lbl.setVisible(has_sv)
        self.res_full_accel_benefit_label.setVisible(has_sv)
        if has_sv:
            self._res_full_labels["surrender_value"].setText(self._fmt_money(new_sv))
            calc_benefit = max(0.0, new_benefit)
            accel_benefit = max(calc_benefit, new_sv)
            self.res_full_accel_benefit_label.setText(self._fmt_money(accel_benefit))

        # APV components — proportionally scaled
        if orig_eligible > 0:
            self._res_full_apv_labels["apv_fb"].setText(
                self._fmt_money(result.apv_fb * ratio)
            )
            self._res_full_apv_labels["apv_fp"].setText(
                self._fmt_money(result.apv_fp * ratio)
            )
            self._res_full_apv_labels["apv_fd"].setText(
                self._fmt_money(result.apv_fd * ratio)
            )

        # ── Max Partial Acceleration — (Full Face - Min Face) ──────────
        min_face = self.get_min_face_amount()
        partial_eligible = max(0.0, custom_face - min_face)
        at_min_face = partial_eligible <= 0
        self._partial_not_allowed_label.setVisible(at_min_face)
        for w in self._res_partial_static_widgets:
            if w in (self._partial_sv_lbl, self._partial_accel_lbl):
                w.setVisible(not at_min_face and result.partial_surrender_value > 0)
            else:
                w.setVisible(not at_min_face)
        has_partial_loan = result.partial_loan_repayment > 0
        has_partial_sv = result.partial_surrender_value > 0
        for key, val in self._res_partial_labels.items():
            if key == "loan_repayment":
                val.setVisible(not at_min_face and has_partial_loan)
            elif key == "surrender_value":
                val.setVisible(not at_min_face and has_partial_sv)
            else:
                val.setVisible(not at_min_face)
        self._partial_loan_lbl.setVisible(not at_min_face and has_partial_loan)
        for val in self._res_partial_apv_labels.values():
            val.setVisible(not at_min_face)
        self.res_partial_benefit_label.setVisible(not at_min_face)
        self.res_partial_ratio_label.setVisible(not at_min_face)

        if not at_min_face:
            if orig_eligible > 0:
                partial_ratio = partial_eligible / orig_eligible
            else:
                partial_ratio = 0.0

            partial_discount = round(orig_discount * partial_ratio, 2)
            partial_loan = round(orig_loan * partial_ratio, 2) if orig_loan > 0 else 0.0
            if partial_loan > 0:
                partial_benefit = round(partial_eligible - partial_discount - admin_fee - partial_loan, 2)
                self._res_partial_labels["loan_repayment"].setText(self._fmt_money(partial_loan))
            else:
                partial_benefit = round(partial_eligible - partial_discount - admin_fee, 2)

            partial_new_ratio = max(0.0, partial_benefit) / partial_eligible if partial_eligible > 0 else 0.0

            self._res_partial_labels["eligible_db"].setText(self._fmt_money(partial_eligible))
            self._res_partial_labels["actuarial_discount"].setText(self._fmt_money(partial_discount))
            self._res_partial_labels["admin_fee"].setText(self._fmt_money(admin_fee))

            if partial_benefit < 0:
                self.res_partial_benefit_label.setText(
                    f"$0.00  (calc: {self._fmt_money(partial_benefit)})"
                )
            else:
                self.res_partial_benefit_label.setText(self._fmt_money(partial_benefit))
            self.res_partial_ratio_label.setText(f"{partial_new_ratio * 100:.2f}%")

            if has_partial_sv:
                partial_sv = round(orig_sv * partial_ratio, 2)
                self._res_partial_labels["surrender_value"].setText(self._fmt_money(partial_sv))
                self.res_partial_accel_benefit_label.setText(
                    self._fmt_money(max(max(0.0, partial_benefit), partial_sv))
                )
            self.res_partial_accel_benefit_label.setVisible(not at_min_face and has_partial_sv)

            self._res_partial_apv_labels["apv_fb"].setText(
                self._fmt_money(result.apv_fb * partial_ratio)
            )
            self._res_partial_apv_labels["apv_fp"].setText(
                self._fmt_money(result.apv_fp * partial_ratio)
            )
            self._res_partial_apv_labels["apv_fd"].setText(
                self._fmt_money(result.apv_fd * partial_ratio)
            )

        self._update_accel_reset_visibility()

    def _on_min_face_calc(self):
        """Emit signal to recalculate with the new min face amount."""
        self._update_min_face_reset_visibility()
        self.min_face_calc_requested.emit()

    def _on_min_face_reset(self):
        """Reset min face amount to the default and recalculate."""
        self._min_face_input.setText(self._default_min_face)
        self._update_min_face_reset_visibility()
        self.min_face_calc_requested.emit()

    def _on_accel_reset(self):
        """Reset acceleration amount to the default and recalculate."""
        if self._default_accel_amount > 0:
            self._face_input.setText(f"{self._default_accel_amount:,.2f}")
        self._update_accel_reset_visibility()
        self._on_face_calc()

    def _update_min_face_reset_visibility(self):
        """Show/hide the Reset Min Amount button based on current vs. default."""
        current = self._min_face_input.text().replace("$", "").replace(",", "").strip()
        default = self._default_min_face.replace("$", "").replace(",", "").strip()
        differs = current != default
        self._min_face_label.setVisible(not differs)
        self._min_face_reset_btn.setVisible(differs)

    def _update_accel_reset_visibility(self):
        """Show/hide the Reset Accel Amount button based on current vs. default."""
        if self._default_accel_amount <= 0:
            self._accel_label.setVisible(True)
            self._accel_reset_btn.setVisible(False)
            return
        raw = self._face_input.text().replace("$", "").replace(",", "").strip()
        try:
            current = float(raw)
        except ValueError:
            self._accel_label.setVisible(True)
            self._accel_reset_btn.setVisible(False)
            return
        differs = abs(current - self._default_accel_amount) >= 0.01
        self._accel_label.setVisible(not differs)
        self._accel_reset_btn.setVisible(differs)

    def set_calc_data(
        self,
        mort_detail: list[dict],
        apv_detail: list[dict],
        apv_summary: dict,
        policy_info: str = "",
    ):
        """Store detailed calculation tables for the viewer."""
        self._mort_detail = mort_detail
        self._apv_detail = apv_detail
        self._apv_summary = apv_summary
        self._policy_info = policy_info
        self.res_view_calc_btn.setEnabled(bool(mort_detail))

    def _reset_assessment_inputs(self):
        """Reset all assessment inputs to their default empty state.

        Called when a new policy is loaded so the user starts from scratch.
        """
        # Reset rider type back to Chronic (block signal to avoid
        # triggering _on_rider_changed before we finish resetting)
        self.rider_combo.blockSignals(True)
        self.rider_combo.setCurrentText("Chronic")
        self.rider_combo.blockSignals(False)

        # Restore visibility (Terminal hides these)
        self.assessment_group.setVisible(True)
        self.calc_btn.setVisible(True)

        # Uncheck all survival / direct-input checkboxes
        for chk in (
            self.chk_five_year, self.chk_ten_year, self.chk_le,
            self.chk_incr_decrement,
            self.chk_table, self.chk_flat,
            self.chk_table_2, self.chk_flat_2,
            self.chk_return_5yr, self.chk_return_10yr,
        ):
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)

        # Clear survival text inputs
        self.five_year_input.clear()
        self.ten_year_input.clear()
        self.le_input.clear()

        # Clear increased decrement inputs and reset start/stop defaults
        self.incr_decrement_input.clear()
        self.incr_decrement_start_input.setText("1")
        self.incr_decrement_stop_input.setText("99")

        # Clear direct table/flat inputs and reset start/stop defaults
        self.table_input.clear()
        self.table_start_input.setText("1")
        self.table_stop_input.setText("99")
        self.flat_input.clear()
        self.flat_start_input.setText("1")
        self.flat_stop_input.setText("99")
        self.table_2_input.clear()
        self.table_2_start_input.setText("1")
        self.table_2_stop_input.setText("99")
        self.flat_2_input.clear()
        self.flat_2_start_input.setText("1")
        self.flat_2_stop_input.setText("99")

        # Update disabled styling
        self._on_checkbox_toggled()



        # Hide derived group and clear results
        self.derived_group.setVisible(False)
        for lbl in self._derived_labels.values():
            lbl.setText("\u2014")
        self._assessment = None
        self.clear_results()

    def clear_results(self):
        """Reset the results column to default empty state."""
        self._result = None
        self._face_input.clear()
        # Reset all result labels to dashes
        for lbl_dict in (self._res_full_labels, self._res_partial_labels):
            for val in lbl_dict.values():
                val.setText("\u2014")
        self.res_full_benefit_label.setText("\u2014")
        self.res_full_ratio_label.setText("\u2014")
        self.res_partial_benefit_label.setText("\u2014")
        self.res_partial_ratio_label.setText("\u2014")
        # Reset surrender value / accel benefit labels
        self.res_full_accel_benefit_label.setText("\u2014")
        self.res_partial_accel_benefit_label.setText("\u2014")
        self._full_sv_lbl.setVisible(False)
        self._res_full_labels["surrender_value"].setVisible(False)
        self._full_accel_lbl.setVisible(False)
        self.res_full_accel_benefit_label.setVisible(False)
        self._partial_sv_lbl.setVisible(False)
        self._res_partial_labels["surrender_value"].setVisible(False)
        self._partial_accel_lbl.setVisible(False)
        self.res_partial_accel_benefit_label.setVisible(False)
        # APV labels
        for lbl_dict in (self._res_full_apv_labels, self._res_partial_apv_labels):
            for val in lbl_dict.values():
                val.setText("\u2014")
        self.res_premium_before_label.setText("\u2014")
        self.res_premium_after_full_label.setText("\u2014")
        self.res_premium_after_partial_label.setText("\u2014")
        self.res_premium_after_partial_input.clear()
        self.res_messages_label.setText("")
        self.res_view_calc_btn.setEnabled(False)
        self._partial_prem_breakdown = None
        self._partial_prem_detail_btn.setVisible(False)

    # ── Partial premium breakdown ────────────────────────────────────────

    def set_partial_premium_breakdown(self, breakdown: dict | None):
        """Store the min-face premium breakdown for the viewer button."""
        self._partial_prem_breakdown = breakdown
        # Don't show detail button for UL — After (Partial) is user input
        is_ul = self._policy and self._policy.product_type in ("UL", "IUL", "ISWL")
        self._partial_prem_detail_btn.setVisible(breakdown is not None and not is_ul)

    def _show_partial_premium_breakdown(self):
        """Show a dialog with per-coverage premium calculation for the partial
        (min face) premium.  Uses the same shared dialog as the Policy Info screen."""
        from .premium_breakdown_dialog import show_premium_breakdown_dialog
        show_premium_breakdown_dialog(
            self._partial_prem_breakdown,
            parent=self,
            title="Partial Premium Calculation Breakdown",
        )

    # ── Result action buttons ───────────────────────────────────────────

    def _get_current_warnings(self) -> list[str]:
        """Collect warning strings currently shown in the messages label."""
        text = self.res_messages_label.text().strip()
        if not text:
            return []
        # Each bullet is separated by double newline; strip the bullet char
        return [line.lstrip("\u2022 ").strip() for line in text.split("\n") if line.strip()]

    def _on_res_view_calc(self):
        """Open the detailed calculation viewer window (modeless)."""
        if not self._mort_detail:
            return
        from .calc_viewer import CalcViewerDialog
        after_partial = self.res_premium_after_partial_input.text().strip()

        # Read current face/min-face input values
        accel_raw = self._face_input.text().replace("$", "").replace(",", "").strip()
        try:
            accel_val = float(accel_raw)
        except ValueError:
            accel_val = 0.0
        min_face_val = self.get_min_face_amount()

        viewer = CalcViewerDialog(
            mortality_rows=self._mort_detail,
            apv_rows=self._apv_detail,
            apv_summary=self._apv_summary,
            policy_info=self._policy_info,
            policy=self._policy,
            assessment=self._assessment,
            result=self._result,
            derived_values=self.get_derived_display_values(),
            after_partial_override=after_partial,
            warnings=self._get_current_warnings(),
            accel_amount_input=accel_val,
            min_face_amount_input=min_face_val,
            parent=None,
        )
        viewer.show()
        self._calc_viewer = viewer

    def _on_res_export(self):
        """Delegate export to the results panel (if available via parent)."""
        if self._result is None:
            return
        # Find the results panel through the window to avoid duplicating export code
        window = self.window()
        if hasattr(window, 'results_panel'):
            window.results_panel._on_export()

    def _on_res_copy(self):
        """Copy summary text to clipboard."""
        if self._result is None:
            return
        r = self._result
        p = self._policy
        full_calc = max(0.0, r.full_accel_benefit)
        full_accel = max(full_calc, r.full_surrender_value) if r.full_surrender_value > 0 else full_calc
        partial_calc = max(0.0, r.partial_accel_benefit)
        partial_accel = max(partial_calc, r.partial_surrender_value) if r.partial_surrender_value > 0 else partial_calc
        lines = [
            "ABR QUOTE SUMMARY",
            f"Policy: {p.policy_number if p else 'N/A'}",
            f"Insured: {p.insured_name if p else 'N/A'}",
            "",
            "FULL ACCELERATION:",
            f"  Eligible DB:        {self._fmt_money(r.full_eligible_db)}",
            f"  Actuarial Discount: {self._fmt_money(r.full_actuarial_discount)}",
            f"  Admin Fee:          {self._fmt_money(r.full_admin_fee)}",
        ]
        if r.full_loan_repayment > 0:
            lines.append(f"  Loan Repayment:     {self._fmt_money(r.full_loan_repayment)}")
        lines += [
            f"  Calc. Benefit:      {self._fmt_money(full_calc)}",
            f"  Benefit Ratio:      {r.full_benefit_ratio * 100:.2f}%",
        ]
        if r.full_surrender_value > 0:
            lines += [
                f"  Surrender Value:    {self._fmt_money(r.full_surrender_value)}",
                f"  Accel. Benefit:     {self._fmt_money(full_accel)}",
            ]
        lines += [
            "",
            "MAX PARTIAL ACCELERATION:",
            f"  Eligible DB:        {self._fmt_money(r.partial_eligible_db)}",
            f"  Actuarial Discount: {self._fmt_money(r.partial_actuarial_discount)}",
            f"  Admin Fee:          {self._fmt_money(r.partial_admin_fee)}",
        ]
        if r.partial_loan_repayment > 0:
            lines.append(f"  Loan Repayment:     {self._fmt_money(r.partial_loan_repayment)}")
        lines += [
            f"  Calc. Benefit:      {self._fmt_money(partial_calc)}",
            f"  Benefit Ratio:      {r.partial_benefit_ratio * 100:.2f}%",
        ]
        if r.partial_surrender_value > 0:
            lines += [
                f"  Surrender Value:    {self._fmt_money(r.partial_surrender_value)}",
                f"  Accel. Benefit:     {self._fmt_money(partial_accel)}",
            ]
        lines += [
            "",
            f"Premium Before:  {r.premium_before}",
            f"Premium After (Full):    ${r.premium_after_full:,.2f}",
            f"Premium After (Partial): {r.premium_after_partial}",
        ]

        current_warnings = self._get_current_warnings()
        if current_warnings:
            lines.append("")
            lines.append("MESSAGES / WARNINGS:")
            for msg in current_warnings:
                lines.append(f"  \u2022 {msg}")
        elif r.messages:
            lines.append("")
            lines.append("MESSAGES / WARNINGS:")
            for msg in r.messages:
                lines.append(f"  \u2022 {msg}")

        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(lines))
        self.status_label.setText("Summary copied to clipboard.")

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;")
        return lbl

    # ── Warning helpers ──────────────────────────────────────────────────

    def _show_messages_context_menu(self, pos):
        """Right-click menu to copy warning messages to clipboard."""
        text = self.res_messages_label.text().strip()
        if not text:
            return
        menu = QMenu(self)
        copy_action = menu.addAction("Copy Warnings")
        action = menu.exec(self.res_messages_label.mapToGlobal(pos))
        if action == copy_action:
            QApplication.clipboard().setText(text)
            self.status_label.setText("Warnings copied to clipboard.")

    def _show_warning(self, text: str):
        """Display a bold red warning below the assessment group."""
        self.warning_label.setText(text)
        self.warning_label.setVisible(True)

    def _clear_warning(self):
        """Hide the warning label."""
        self.warning_label.setText("")
        self.warning_label.setVisible(False)

    # ── Checkbox toggle handler ──────────────────────────────────────────

    def _on_checkbox_toggled(self):
        """Enable / disable input fields based on their checkbox state."""
        # Survival inputs — toggle readOnly + visual style
        self._toggle_input(self.five_year_input, self.chk_five_year.isChecked())
        self.chk_return_5yr.setEnabled(self.chk_five_year.isChecked())
        self._toggle_input(self.ten_year_input, self.chk_ten_year.isChecked())
        self.chk_return_10yr.setEnabled(self.chk_ten_year.isChecked())
        self._toggle_input(self.le_input, self.chk_le.isChecked())

        # Increased Decrement inputs
        incr = self.chk_incr_decrement.isChecked()
        self._toggle_input(self.incr_decrement_input, incr)
        self._toggle_input(self.incr_decrement_start_input, incr)
        self._toggle_input(self.incr_decrement_stop_input, incr)

        # Table 1 inputs
        tbl = self.chk_table.isChecked()
        self._toggle_input(self.table_input, tbl)
        self._toggle_input(self.table_start_input, tbl)
        self._toggle_input(self.table_stop_input, tbl)

        # Flat 1 inputs
        flt = self.chk_flat.isChecked()
        self._toggle_input(self.flat_input, flt)
        self._toggle_input(self.flat_start_input, flt)
        self._toggle_input(self.flat_stop_input, flt)

        # Table 2 inputs
        tbl2 = self.chk_table_2.isChecked()
        self._toggle_input(self.table_2_input, tbl2)
        self._toggle_input(self.table_2_start_input, tbl2)
        self._toggle_input(self.table_2_stop_input, tbl2)

        # Flat 2 inputs
        flt2 = self.chk_flat_2.isChecked()
        self._toggle_input(self.flat_2_input, flt2)
        self._toggle_input(self.flat_2_start_input, flt2)
        self._toggle_input(self.flat_2_stop_input, flt2)

    def _toggle_input(self, widget: QLineEdit, enabled: bool):
        """Toggle a QLineEdit between editable and read-only with visual feedback."""
        widget.setReadOnly(not enabled)
        if enabled:
            widget.setStyleSheet(INPUT_STYLE)
        else:
            widget.setStyleSheet(INPUT_STYLE + f"""
                QLineEdit {{
                    background-color: {GRAY_LIGHT};
                    color: {GRAY_TEXT};
                }}
            """)

    # ── Rider type change handler ────────────────────────────────────────

    def _refresh_per_diem_display(self):
        """Fetch and display current-year per diem / annual limit values."""
        try:
            db = get_abr_database()
            perdiem = db.get_per_diem(date.today().year)
            if perdiem:
                self._rider_per_diem_label.setText(f"${perdiem[0]:,.2f}/day")
                self._rider_annual_limit_label.setText(f"${perdiem[1]:,.2f}")
            else:
                self._rider_per_diem_label.setText("\u2014")
                self._rider_annual_limit_label.setText("\u2014")
        except Exception:
            logger.debug("Could not load per diem for rider display", exc_info=True)

    def _on_rider_changed(self, rider_type: str):
        """Show/hide assessment inputs based on rider type.

        Terminal: no assessment — mortality is 50 %/yr.
        Chronic / Critical: full assessment inputs.
        """
        is_terminal = (rider_type == "Terminal")
        is_chronic = (rider_type == "Chronic")

        # Show per diem / annual limit only for Chronic rider
        for w in self._chronic_only_widgets:
            w.setVisible(is_chronic)
        if is_chronic:
            self._refresh_per_diem_display()

        # Enable/disable the entire assessment section and button
        self.assessment_group.setVisible(not is_terminal)
        self.calc_btn.setVisible(not is_terminal)
        self.derived_group.setVisible(False)
        self.clear_results()

        # Validate rider type against policy ABR riders
        self._validate_rider_type()

        if is_terminal:
            self._assessment = None
            self.status_label.setText(
                "Terminal rider — no assessment needed. "
                "Mortality = 50 % per year."
            )
            # Auto-run calculation for Terminal if a policy is loaded
            if self._policy:
                self._populate_terminal_derived()
                self._assessment = self.create_terminal_assessment()
                self.assessment_ready.emit(self._assessment)
        else:
            if self._policy:
                self.status_label.setText(
                    "Check the inputs you want to use and enter values."
                )

    # ── Terminal derived values ───────────────────────────────────────────

    def _populate_terminal_derived(self):
        """Compute and display derived substandard values for Terminal rider.

        Terminal uses is_terminal=True which forces 50 %/yr mortality in the
        engine, so there is no goal-seek and no assessment substandard.
        We still show the derived survival / LE so the user can see them.
        """
        p = self._policy
        if p is None:
            return

        abs_policy_month = (p.policy_year - 1) * 12 + p.policy_month

        # Standard (unmodified) params — no terminal, no substandard
        std_params = MortalityParams(
            issue_age=p.issue_age,
            sex=p.rate_sex or p.sex,
            rate_class=p.rate_class,
            policy_month=abs_policy_month,
            maturity_age=p.maturity_age or MATURITY_AGE,
            table_rating_1=0.0,
            table_1_start_month=1,
            table_1_last_month=9999,
            flat_extra_1=0.0,
            flat_1_start_month=1,
            flat_1_duration=9999,
            mortality_multiplier=MORTALITY_MULTIPLIER,
            improvement_rate=MORTALITY_IMPROVEMENT_RATE,
            improvement_cap=MORTALITY_IMPROVEMENT_CAP,
            is_terminal=False,
        )
        std_engine = MortalityEngine(std_params)
        std_le = std_engine.compute_life_expectancy()
        std_survival_5yr = std_engine.compute_survival_probability(5)
        std_survival_10yr = std_engine.compute_survival_probability(10)

        # Terminal (modified) params — is_terminal=True, 50 %/yr mortality
        term_params = MortalityParams(
            issue_age=p.issue_age,
            sex=p.rate_sex or p.sex,
            rate_class=p.rate_class,
            policy_month=abs_policy_month,
            maturity_age=p.maturity_age or MATURITY_AGE,
            table_rating_1=0.0,
            table_1_start_month=1,
            table_1_last_month=9999,
            flat_extra_1=0.0,
            flat_1_start_month=1,
            flat_1_duration=9999,
            mortality_multiplier=MORTALITY_MULTIPLIER_TERMINAL,
            improvement_rate=0.0,
            improvement_cap=MORTALITY_IMPROVEMENT_CAP,
            is_terminal=True,
        )
        term_engine = MortalityEngine(term_params)
        term_le = term_engine.compute_life_expectancy()
        term_survival_5yr = term_engine.compute_survival_probability(5)
        term_survival_10yr = term_engine.compute_survival_probability(10)

        # Stash for create_terminal_assessment
        self._term_survival_5yr = term_survival_5yr
        self._term_survival_10yr = term_survival_10yr
        self._term_le = term_le

        # ── Populate left column (Current / Unmodified) ─────────────────
        self._derived_labels["std_survival_5yr"].setText(
            f"{std_survival_5yr:.4f}  ({std_survival_5yr * 100:.2f}%)"
        )
        self._derived_labels["std_survival_10yr"].setText(
            f"{std_survival_10yr:.4f}  ({std_survival_10yr * 100:.2f}%)"
        )
        std_le_age = p.attained_age + round(std_le)
        self._derived_labels["std_le"].setText(
            f"{std_le:.1f} years (age {std_le_age})"
        )
        if p.table_rating > 0:
            self._derived_labels["std_table_rating"].setText(
                f"Table {p.table_rating}"
            )
        else:
            self._derived_labels["std_table_rating"].setText("None")
        if p.flat_extra > 0:
            flat_txt = f"${p.flat_extra:.3f}/1000"
            if p.flat_to_age > 0:
                flat_txt += f" (to age {p.flat_to_age})"
            self._derived_labels["std_flat_extra"].setText(flat_txt)
        else:
            self._derived_labels["std_flat_extra"].setText("None")

        # ── Populate right column (Modified / Terminal Applied) ─────────
        self._derived_labels["mod_survival_5yr"].setText(
            f"{term_survival_5yr:.4f}  ({term_survival_5yr * 100:.2f}%)"
        )
        self._derived_labels["mod_survival_10yr"].setText(
            f"{term_survival_10yr:.4f}  ({term_survival_10yr * 100:.2f}%)"
        )
        term_le_age = p.attained_age + round(term_le)
        self._derived_labels["mod_le"].setText(
            f"{term_le:.1f} years (age {term_le_age})"
        )
        self._derived_labels["table_rating"].setText("Annual Mortality = 0.5000")
        self._derived_labels["flat_extra"].setText("\u2014")

        self.derived_group.setVisible(True)

    # ── Actions ──────────────────────────────────────────────────────────

    def _on_calculate(self):
        """Run goal seek to derive substandard from the checked inputs."""
        self._clear_warning()
        if self._policy is None:
            self._show_warning("Please load a policy first (Step 1).")
            return

        rider_type = self.rider_combo.currentText()

        # Validate: at least one survival input or direct table must be checked
        has_five = self.chk_five_year.isChecked()
        has_ten = self.chk_ten_year.isChecked()
        has_le = self.chk_le.isChecked()
        has_survival = has_five or has_ten or has_le
        has_table_direct = self.chk_table.isChecked()
        has_flat_direct = self.chk_flat.isChecked()
        has_table_2_direct = self.chk_table_2.isChecked()
        has_flat_2_direct = self.chk_flat_2.isChecked()
        has_incr_decrement = self.chk_incr_decrement.isChecked()

        if not has_survival and not has_table_direct and not has_incr_decrement and not has_incr_decrement:
            self._show_warning(
                "Check at least one survival input, the Table checkbox, or Increased Decrement."
            )
            return

        # Parse checked survival inputs
        five_yr = ten_yr = le_val = 0.0
        try:
            if has_five:
                five_yr = float(self.five_year_input.text().strip())
            if has_ten:
                ten_yr = float(self.ten_year_input.text().strip())
            if has_le:
                le_val = float(self.le_input.text().strip())
        except ValueError:
            self._show_warning(
                "Enter valid numeric values for all checked survival fields."
            )
            return

        # Validate ranges
        if has_five and not (0 <= five_yr <= 1):
            self._show_warning("5-Year Survival must be between 0 and 1.")
            return
        if has_ten and not (0 <= ten_yr <= 1):
            self._show_warning("10-Year Survival must be between 0 and 1.")
            return

        # Parse direct table/flat (set 1)
        direct_table = 0.0
        table_start_yr = 1
        table_stop_yr = 99
        direct_flat = 0.0
        flat_start_yr = 1
        flat_stop_yr = 99

        # Parse increased decrement
        incr_decrement_pct = 0.0
        incr_decrement_start_yr = 1
        incr_decrement_stop_yr = 99

        # Parse direct table/flat (set 2)
        direct_table_2 = 0.0
        table_2_start_yr = 1
        table_2_stop_yr = 99
        direct_flat_2 = 0.0
        flat_2_start_yr = 1
        flat_2_stop_yr = 99

        try:
            if has_table_direct:
                direct_table = float(self.table_input.text().strip())
                table_start_yr = int(self.table_start_input.text().strip())
                table_stop_yr = int(self.table_stop_input.text().strip())
            if has_flat_direct:
                direct_flat = float(self.flat_input.text().strip())
                flat_start_yr = int(self.flat_start_input.text().strip())
                flat_stop_yr = int(self.flat_stop_input.text().strip())
            if has_table_2_direct:
                direct_table_2 = float(self.table_2_input.text().strip())
                table_2_start_yr = int(self.table_2_start_input.text().strip())
                table_2_stop_yr = int(self.table_2_stop_input.text().strip())
            if has_flat_2_direct:
                direct_flat_2 = float(self.flat_2_input.text().strip())
                flat_2_start_yr = int(self.flat_2_start_input.text().strip())
                flat_2_stop_yr = int(self.flat_2_stop_input.text().strip())
            if has_incr_decrement:
                incr_decrement_pct = float(self.incr_decrement_input.text().strip())
                incr_decrement_start_yr = int(self.incr_decrement_start_input.text().strip())
                incr_decrement_stop_yr = int(self.incr_decrement_stop_input.text().strip())
        except ValueError:
            self._show_warning(
                "Enter valid numeric values for all checked Table / Flat fields."
            )
            return

        self.status_label.setText("Computing substandard values (goal seek)...")
        self.calc_btn.setEnabled(False)

        try:
            p = self._policy

            # Build base mortality params (standard — no table/flat)
            # Convert month-within-year to absolute policy month since issue
            abs_policy_month = (p.policy_year - 1) * 12 + p.policy_month

            # Determine mortality multiplier and improvement from rider type
            # Excel: mort_mult = IF(B28="C", 75%, 100%)
            #        MI        = IF(B28="C", 0.01, 0)
            is_terminal = (rider_type == "Terminal")
            if is_terminal:
                mort_mult = MORTALITY_MULTIPLIER_TERMINAL   # 100%
                mi_rate = 0.0                                # no improvement
            else:
                mort_mult = MORTALITY_MULTIPLIER            # 75%
                mi_rate = MORTALITY_IMPROVEMENT_RATE         # 1%

            # ── Determine if policy substandards should be included ──────
            is_in_lieu_of = True  # always "In Lieu Of"

            # Base params always start clean (no substandard) so the goal
            # seek solves correctly.  The policy's existing substandards
            # are added to additional_tables/additional_flats later when
            # "In Addition To" is selected.
            base_params = MortalityParams(
                issue_age=p.issue_age,
                sex=p.rate_sex or p.sex,  # rate_sex from 67 segment
                rate_class=p.rate_class,
                policy_month=abs_policy_month,
                maturity_age=p.maturity_age or MATURITY_AGE,
                table_rating_1=0.0,
                table_1_start_month=1,
                table_1_last_month=9999,
                flat_extra_1=0.0,
                flat_1_start_month=1,
                flat_1_duration=9999,
                mortality_multiplier=mort_mult,
                improvement_rate=mi_rate,
                improvement_cap=MORTALITY_IMPROVEMENT_CAP,
                is_terminal=is_terminal,
            )

            # ── Determine table rating(s) from survival inputs ──────────
            table_rating = 0.0
            table_rating_5yr = 0.0
            table_rating_10yr = 0.0
            computed_le = 0.0
            is_dual_solve = has_five and has_ten

            if is_dual_solve:
                # Two-solve: 5yr table + 10yr table (relative to current month)
                table_rating_5yr, table_rating_10yr, computed_le = find_dual_table_ratings(
                    base_params,
                    five_yr,
                    ten_yr,
                    return_after_10yr=self.chk_return_10yr.isChecked(),
                )
                table_rating = table_rating_5yr  # primary for display

            elif has_five:
                # Single 5yr solve (direct table/flat are add-ons, NOT replacements)
                table_rating, _, computed_le = find_combined_substandard(
                    base_params,
                    MedicalAssessment(five_year_survival=five_yr),
                    assessment_index=1,
                )
                table_rating_5yr = table_rating
                # Handle Return checkbox — table drops after 5 years
                if self.chk_return_5yr.isChecked():
                    final_p = dc_replace(
                        base_params,
                        table_rating_1=table_rating,
                        table_1_start_month=abs_policy_month,
                        table_1_last_month=abs_policy_month + 59,
                    )
                    engine = MortalityEngine(final_p)
                    computed_le = engine.compute_life_expectancy()

            elif has_ten:
                # Single 10yr solve
                table_rating, _, computed_le = find_combined_substandard(
                    base_params,
                    MedicalAssessment(ten_year_survival=ten_yr),
                    assessment_index=3,
                )
                # Handle Return checkbox — table drops after 10 years
                if self.chk_return_10yr.isChecked():
                    final_p = dc_replace(
                        base_params,
                        table_rating_1=table_rating,
                        table_1_start_month=abs_policy_month,
                        table_1_last_month=abs_policy_month + 119,
                    )
                    engine = MortalityEngine(final_p)
                    computed_le = engine.compute_life_expectancy()

            elif has_le:
                # LE solve
                table_rating, _, computed_le = find_combined_substandard(
                    base_params,
                    MedicalAssessment(life_expectancy_years=le_val),
                    assessment_index=5,
                )

            elif has_table_direct:
                # No survival inputs — use direct table as primary (no solve)
                table_rating = direct_table

            # ── Build additional tables/flats from direct user inputs ─────
            # IMPORTANT: When there is NO survival solve, the direct Table 1
            # rating becomes the primary table_rating_1.  We must NOT also
            # put it into additional_tables, or it gets applied twice.
            has_survival_solve = has_five or has_ten or has_le
            additional_tables = []
            additional_flats = []

            # "In Addition To" — carry policy's existing substandards as
            # additional layers so they are not overwritten by dc_replace.
            if not is_in_lieu_of:
                if p.table_rating > 0:
                    additional_tables.append(
                        (float(p.table_rating), 1, 9999)
                    )
                if p.table_rating_2 > 0:
                    additional_tables.append(
                        (float(p.table_rating_2), 1, 9999)
                    )
                if p.flat_extra > 0:
                    flat_last = 9999
                    if p.flat_to_age > 0:
                        remaining = max(0, p.flat_to_age - p.attained_age) * 12
                        flat_last = abs_policy_month + remaining
                    additional_flats.append(
                        (p.flat_extra, 1, flat_last)
                    )

            if has_table_direct and direct_table > 0 and has_survival_solve:
                # Only add as additional when a survival solve owns the primary slot
                # Start/stop years are relative to quote date, not policy issue
                # Stop year is exclusive: drops off at beginning of stop year
                t_start_m = abs_policy_month + (table_start_yr - 1) * 12
                t_stop_m = abs_policy_month + (table_stop_yr - 1) * 12 - 1
                additional_tables.append((direct_table, t_start_m, t_stop_m))

            if has_flat_direct and direct_flat > 0:
                # Start/stop years are relative to quote date, not policy issue
                # Stop year is exclusive: drops off at beginning of stop year
                f_start_m = abs_policy_month + (flat_start_yr - 1) * 12
                f_stop_m = abs_policy_month + (flat_stop_yr - 1) * 12 - 1
                additional_flats.append((direct_flat, f_start_m, f_stop_m))

            if has_table_2_direct and direct_table_2 > 0:
                t2_start_m = abs_policy_month + (table_2_start_yr - 1) * 12
                t2_stop_m = abs_policy_month + (table_2_stop_yr - 1) * 12 - 1
                additional_tables.append((direct_table_2, t2_start_m, t2_stop_m))

            if has_flat_2_direct and direct_flat_2 > 0:
                f2_start_m = abs_policy_month + (flat_2_start_yr - 1) * 12
                f2_stop_m = abs_policy_month + (flat_2_stop_yr - 1) * 12 - 1
                additional_flats.append((direct_flat_2, f2_start_m, f2_stop_m))

            # Increased Decrement → convert to equivalent table rating
            # ID% means mortality factor = 1 + ID/100
            # Table rating formula: factor = 1 + table_rating × 0.25
            # So table_rating = (ID/100) / 0.25 = ID / 25
            if has_incr_decrement and incr_decrement_pct > 0:
                id_table_rating = incr_decrement_pct / 25.0
                id_start_m = abs_policy_month + (incr_decrement_start_yr - 1) * 12
                id_stop_m = abs_policy_month + (incr_decrement_stop_yr - 1) * 12 - 1
                additional_tables.append((id_table_rating, id_start_m, id_stop_m))

            # ── Compute derived values with ALL ratings combined ────────
            # Always build the full final params for LE and survival calc.
            # Table period boundaries MUST be anchored to abs_policy_month
            # so the mortality engine (which starts its loop at policy_month)
            # applies ratings over the correct window.
            if is_dual_solve:
                p1_start = abs_policy_month
                p1_end = abs_policy_month + 59
                p2_start = abs_policy_month + 60
                p2_end = abs_policy_month + 119
                last_month_p2 = p2_end if self.chk_return_10yr.isChecked() else 9999
                final_params = dc_replace(
                    base_params,
                    table_rating_1=table_rating_5yr,
                    table_1_start_month=p1_start,
                    table_1_last_month=p1_end,
                    table_rating_2=table_rating_10yr,
                    table_2_start_month=p2_start,
                    table_2_last_month=last_month_p2,
                    additional_tables=additional_tables,
                    additional_flats=additional_flats,
                )
            elif has_survival_solve:
                # Single solve — respect Return checkbox
                if has_five and self.chk_return_5yr.isChecked():
                    t1_last = abs_policy_month + 59
                elif has_ten and self.chk_return_10yr.isChecked():
                    t1_last = abs_policy_month + 119
                else:
                    t1_last = 9999
                final_params = dc_replace(
                    base_params,
                    table_rating_1=table_rating,
                    table_1_start_month=abs_policy_month,
                    table_1_last_month=t1_last,
                    additional_tables=additional_tables,
                    additional_flats=additional_flats,
                )
            else:
                # No survival solve — direct table is the primary rating
                # Start/stop years are relative to quote date
                # Stop year is exclusive: drops off at beginning of stop year
                t_start_m = abs_policy_month + (table_start_yr - 1) * 12
                t_stop_m = abs_policy_month + (table_stop_yr - 1) * 12 - 1
                final_params = dc_replace(
                    base_params,
                    table_rating_1=table_rating,
                    table_1_start_month=t_start_m,
                    table_1_last_month=t_stop_m,
                    additional_tables=additional_tables,
                    additional_flats=additional_flats,
                )

            engine = MortalityEngine(final_params)
            computed_le = engine.compute_life_expectancy()
            survival_5yr = engine.compute_survival_probability(5)
            survival_10yr = engine.compute_survival_probability(10)

            # ── Compute standard (unmodified) values ────────────────────
            std_engine = MortalityEngine(base_params)
            std_le = std_engine.compute_life_expectancy()
            std_survival_5yr = std_engine.compute_survival_probability(5)
            std_survival_10yr = std_engine.compute_survival_probability(10)

            assessment_idx = compute_assessment_index(table_rating)

            # ── Build assessment result ─────────────────────────────────
            self._assessment = MedicalAssessment(
                rider_type=rider_type,
                use_five_year=has_five,
                use_ten_year=has_ten,
                use_le=has_le,
                use_increased_decrement=has_incr_decrement,
                use_table=has_table_direct,
                use_flat=has_flat_direct,
                use_table_2=has_table_2_direct,
                use_flat_2=has_flat_2_direct,
                use_return_5yr=self.chk_return_5yr.isChecked(),
                use_return_10yr=self.chk_return_10yr.isChecked(),
                in_lieu_of=True,
                five_year_survival=five_yr,
                ten_year_survival=ten_yr,
                life_expectancy_years=le_val if le_val else computed_le,
                life_expectancy_rounded=round(le_val if le_val else computed_le),
                direct_increased_decrement=incr_decrement_pct,
                incr_decrement_start_year=incr_decrement_start_yr,
                incr_decrement_stop_year=incr_decrement_stop_yr,
                direct_table_rating=direct_table,
                table_start_year=table_start_yr,
                table_stop_year=table_stop_yr,
                direct_flat_extra=direct_flat,
                flat_start_year=flat_start_yr,
                flat_stop_year=flat_stop_yr,
                direct_table_rating_2=direct_table_2,
                table_2_start_year=table_2_start_yr,
                table_2_stop_year=table_2_stop_yr,
                direct_flat_extra_2=direct_flat_2,
                flat_2_start_year=flat_2_start_yr,
                flat_2_stop_year=flat_2_stop_yr,
                derived_table_rating=table_rating,
                derived_table_rating_5yr=table_rating_5yr,
                derived_table_rating_10yr=table_rating_10yr,
                derived_flat_extra=direct_flat if has_flat_direct else 0.0,
                derived_increased_decrement=incr_decrement_pct if has_incr_decrement else 0.0,
                assessment_index=assessment_idx,
                computed_survival_5yr=survival_5yr,
                computed_survival_10yr=survival_10yr,
                computed_le=computed_le,
            )

            # ── Populate derived labels ─────────────────────────────────
            # Left: standard (unmodified) — including policy substandards
            self._derived_labels["std_survival_5yr"].setText(
                f"{std_survival_5yr:.4f}  ({std_survival_5yr * 100:.2f}%)"
            )
            self._derived_labels["std_survival_10yr"].setText(
                f"{std_survival_10yr:.4f}  ({std_survival_10yr * 100:.2f}%)"
            )
            std_le_age = p.attained_age + round(std_le)
            self._derived_labels["std_le"].setText(f"{std_le:.1f} years (age {std_le_age})")

            # Policy substandard baseline
            if p.table_rating > 0 or p.table_rating_2 > 0:
                tbl_parts = []
                if p.table_rating > 0:
                    tbl_parts.append(f"Table {p.table_rating}")
                if p.table_rating_2 > 0:
                    tbl_parts.append(f"Table {p.table_rating_2}")
                self._derived_labels["std_table_rating"].setText(
                    "  |  ".join(tbl_parts)
                )
            else:
                self._derived_labels["std_table_rating"].setText("None")

            if p.flat_extra > 0:
                flat_txt = f"${p.flat_extra:.3f}/1000"
                if p.flat_to_age > 0:
                    flat_txt += f" (to age {p.flat_to_age})"
                self._derived_labels["std_flat_extra"].setText(flat_txt)
            else:
                self._derived_labels["std_flat_extra"].setText("None")

            # Right: modified (substandard applied)
            self._derived_labels["mod_survival_5yr"].setText(
                f"{survival_5yr:.4f}  ({survival_5yr * 100:.2f}%)"
            )
            self._derived_labels["mod_survival_10yr"].setText(
                f"{survival_10yr:.4f}  ({survival_10yr * 100:.2f}%)"
            )
            mod_le_age = p.attained_age + round(computed_le)
            self._derived_labels["mod_le"].setText(f"{computed_le:.1f} years (age {mod_le_age})")


            # Table ratings display — always show year range
            maturity_age = p.maturity_age or MATURITY_AGE
            yrs_to_maturity = maturity_age - p.attained_age

            # Did a survival solve produce the table_rating, or was it
            # entered directly by the user?  When entered directly (no
            # survival input checked) we must NOT show it twice — once as
            # a derived rating and again as a "+Tbl" add-on.
            has_survival_solve = has_five or has_ten or has_le

            tbl_parts = []
            # Show the policy's existing table rating(s) if "In Addition To"
            if not is_in_lieu_of and p.table_rating > 0:
                tbl_parts.append(f"Policy Tbl {p.table_rating} (existing)")
            if not is_in_lieu_of and p.table_rating_2 > 0:
                tbl_parts.append(f"Policy Tbl {p.table_rating_2} (existing)")

            if is_dual_solve:
                # 5yr period always covers years 1-5
                tbl_parts.append(f"5yr: {table_rating_5yr:.2f} (yrs 1-5)")
                # 6-10yr period: if Return checked, ends at yr 10; else to maturity
                if self.chk_return_10yr.isChecked():
                    p2_label = "yrs 6-10"
                else:
                    p2_label = f"yrs 6-{yrs_to_maturity}"
                tbl_parts.append(f"6-10yr: {table_rating_10yr:.2f} ({p2_label})")
            elif table_rating > 0 and has_survival_solve:
                # Single survival solve — show derived rating with applicable range
                if has_five and self.chk_return_5yr.isChecked():
                    yr_label = "yrs 1-5"
                elif has_ten and self.chk_return_10yr.isChecked():
                    yr_label = "yrs 1-10"
                else:
                    yr_label = f"yrs 1-{yrs_to_maturity}"
                tbl_parts.append(f"{table_rating:.2f} ({yr_label})")
            # Direct table inputs (add-on or sole source)
            if has_table_direct and direct_table > 0:
                tbl_parts.append(f"Tbl {direct_table:.0f} (yr {table_start_yr}-{table_stop_yr - 1})")
            if has_table_2_direct and direct_table_2 > 0:
                tbl_parts.append(f"Tbl2 {direct_table_2:.0f} (yr {table_2_start_yr}-{table_2_stop_yr - 1})")
            if has_incr_decrement and incr_decrement_pct > 0:
                id_table = incr_decrement_pct / 25.0
                tbl_parts.append(
                    f"ID {incr_decrement_pct:.0f}% "
                    f"(Tbl {id_table:.0f}, yr {incr_decrement_start_yr}-{incr_decrement_stop_yr - 1})"
                )
            self._derived_labels["table_rating"].setText(
                "  |  ".join(tbl_parts) if tbl_parts else "None"
            )

            # Flat extras display
            flat_parts = []
            # Show the policy's existing flat extra if "In Addition To"
            if not is_in_lieu_of and p.flat_extra > 0:
                fe_txt = f"Policy ${p.flat_extra:.3f}"
                if p.flat_to_age > 0:
                    fe_txt += f" (to age {p.flat_to_age})"
                else:
                    fe_txt += " (existing)"
                flat_parts.append(fe_txt)

            if has_flat_direct and direct_flat > 0:
                flat_parts.append(f"${direct_flat:.3f} (yr {flat_start_yr}-{flat_stop_yr - 1})")
            if has_flat_2_direct and direct_flat_2 > 0:
                flat_parts.append(f"${direct_flat_2:.3f} (yr {flat_2_start_yr}-{flat_2_stop_yr - 1})")
            self._derived_labels["flat_extra"].setText(
                "  |  ".join(flat_parts) if flat_parts else "None"
            )

            self.derived_group.setVisible(True)
            self.status_label.setText("Substandard values computed successfully.")
            self.assessment_ready.emit(self._assessment)

        except Exception as e:
            logger.error(f"Goal seek error: {e}", exc_info=True)
            self._show_warning(f"Calculation error: {e}")
        finally:
            self.calc_btn.setEnabled(True)

    # ── Public API ──────────────────────────────────────────────────────

    def set_policy(self, policy: ABRPolicyData):
        """Set the policy data from Step 1."""
        self._policy = policy
        self._reset_assessment_inputs()

        # Populate min face amount: $50,000 for TERM, $25,000 for all others
        if policy.product_type == "TERM":
            self._min_face_input.setText("50,000")
            self._default_min_face = "50,000"
        else:
            self._min_face_input.setText("25,000")
            self._default_min_face = "25,000"
        self._update_min_face_reset_visibility()

        # UL/IUL/ISWL: rename Premium Impact → Monthly Deduction Impact
        # and switch After (Partial) to an editable input
        is_ul = policy.product_type in ("UL", "IUL", "ISWL")
        self.res_premium_group.setTitle(
            "Monthly Deduction Impact" if is_ul else "Premium Impact"
        )
        # Rename "Premium Before:" → "Last Monthly Deduction:" for UL
        self._prem_row_labels[0].setText(
            "Last Monthly Deduction:" if is_ul else "Premium Before:"
        )
        self.res_premium_after_partial_label.setVisible(not is_ul)
        self.res_premium_after_partial_input.setVisible(is_ul)
        # Hide the detail button for UL since After (Partial) is user input
        self._partial_prem_detail_btn.setVisible(False)
        if is_ul:
            self.res_premium_after_partial_input.clear()

        # Refresh per diem display now that the DB is definitely available
        if self.rider_combo.currentText() == "Chronic":
            self._refresh_per_diem_display()

        rider = self.rider_combo.currentText()
        if rider == "Terminal":
            self._populate_terminal_derived()
            self._assessment = self.create_terminal_assessment()
            self.assessment_ready.emit(self._assessment)
            self.status_label.setText(
                f"Policy {policy.policy_number} loaded. "
                "Terminal rider — no assessment needed. Mortality = 50 % per year."
            )
        else:
            self.status_label.setText(
                f"Policy {policy.policy_number} loaded. Enter survival inputs."
            )

    def get_assessment(self) -> Optional[MedicalAssessment]:
        """Return the computed assessment."""
        return self._assessment

    def get_derived_display_values(self) -> dict:
        """Return the derived substandard display text for all labels."""
        return {key: lbl.text() for key, lbl in self._derived_labels.items()}

    def is_terminal(self) -> bool:
        """Return True if the rider type is Terminal."""
        return self.rider_combo.currentText() == "Terminal"

    def get_min_face_amount(self) -> float:
        """Return the user-entered minimum face amount."""
        raw = self._min_face_input.text().replace("$", "").replace(",", "").strip()
        try:
            return float(raw)
        except ValueError:
            return 50_000.0

    def create_terminal_assessment(self) -> MedicalAssessment:
        """Create a default assessment for Terminal rider (50 % mortality/yr).

        No goal seek, no substandard.
        """
        self._assessment = MedicalAssessment(
            rider_type="Terminal",
            computed_survival_5yr=getattr(self, '_term_survival_5yr', 0.0),
            computed_survival_10yr=getattr(self, '_term_survival_10yr', 0.0),
            computed_le=getattr(self, '_term_le', 0.0),
        )
        self.assessment_ready.emit(self._assessment)
        return self._assessment

    def set_assessment_values(self, five_yr: float, ten_yr: float, le: float):
        """Programmatically set survival input values (for testing)."""
        self.chk_five_year.setChecked(True)
        self.five_year_input.setText(str(five_yr))
        self.chk_ten_year.setChecked(True)
        self.ten_year_input.setText(str(ten_yr))
        self.chk_le.setChecked(True)
        self.le_input.setText(str(le))

    # ── ABR rider validation ─────────────────────────────────────────────

    # Mapping from benefit subtype code to rider type name
    _ABR_SUBTYPE_TO_RIDER = {
        "1": "Terminal", "4": "Terminal",
        "2": "Critical", "5": "Critical",
        "3": "Chronic",  "6": "Chronic",
    }

    def set_policy_abr_riders(self, abr_subtypes: set[str]):
        """Store the ABR benefit subtypes found on the policy and validate."""
        self._policy_abr_subtypes = abr_subtypes
        # Derive which rider types are present on the policy
        self._policy_abr_rider_types: set[str] = set()
        for sub in abr_subtypes:
            rtype = self._ABR_SUBTYPE_TO_RIDER.get(sub)
            if rtype:
                self._policy_abr_rider_types.add(rtype)
        self._validate_rider_type()

    def _validate_rider_type(self):
        """Check if selected rider type exists on the policy and show/hide warning."""
        if not hasattr(self, '_policy_abr_rider_types') or not self._policy_abr_rider_types:
            # No ABR riders found on policy — hide warning
            self._rider_mismatch_label.setVisible(False)
            return
        selected = self.rider_combo.currentText()
        if selected not in self._policy_abr_rider_types:
            present = ", ".join(sorted(self._policy_abr_rider_types))
            self._rider_mismatch_label.setText(
                f"\u26A0 {selected} rider not found on the policy. "
                f"Policy has: {present}"
            )
            self._rider_mismatch_label.setVisible(True)
        else:
            self._rider_mismatch_label.setVisible(False)
