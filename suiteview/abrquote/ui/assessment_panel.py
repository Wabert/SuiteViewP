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
from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QCheckBox,
    QGroupBox, QFrame, QScrollArea, QMenu, QApplication,
)

from ..models.abr_data import (
    ABRPolicyData, MedicalAssessment, ABRQuoteResult,
)
from ..models.abr_database import get_abr_database
from ..core.assessment_solver import (
    AssessmentInputs,
    SubstandardSolveResult,
    solve_substandard,
    terminal_substandard,
)
from .abr_styles import (
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_RICH, CRIMSON_SUBTLE,
    SLATE_PRIMARY, SLATE_TEXT,
    WHITE, GRAY_DARK, GRAY_MID, GRAY_TEXT, GRAY_LIGHT,
    GROUP_BOX_STYLE, INPUT_STYLE, COMBOBOX_STYLE,
    BUTTON_SLATE_STYLE, LABEL_MONEY_STYLE, LABEL_MONEY_LARGE_STYLE, DIVIDER_STYLE,
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
        outer_layout.addWidget(self._build_left_column(), stretch=5)
        outer_layout.addWidget(self._build_results_scroll(), stretch=4)
        main_layout.addLayout(outer_layout, 1)
        self._build_bottom_view_calc_row(main_layout)

    def _build_left_column(self) -> QScrollArea:
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setStyleSheet(SCROLL_AREA_STYLE)
        left_widget = QWidget()
        layout = QVBoxLayout(left_widget)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        layout.addWidget(self._build_rider_configuration_group())
        layout.addWidget(self._build_assessment_format_group())
        self._build_warning_and_calculate(layout)
        layout.addWidget(self._build_derived_group())
        self._build_status_label(layout)
        layout.addStretch()

        left_scroll.setWidget(left_widget)
        return left_scroll

    def _build_rider_configuration_group(self) -> QGroupBox:
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

        self._chronic_only_widgets = [
            lbl_pd,
            self._rider_per_diem_label,
            lbl_al,
            self._rider_annual_limit_label,
        ]
        is_chronic = self.rider_combo.currentText() == "Chronic"
        for widget in self._chronic_only_widgets:
            widget.setVisible(is_chronic)
        if is_chronic:
            self._refresh_per_diem_display()

        rider_layout.setColumnStretch(2, 1)
        rider_layout.setColumnStretch(7, 1)
        self._rider_mismatch_label = QLabel("")
        self._rider_mismatch_label.setStyleSheet(
            "color: red; font-weight: bold; font-size: 11px; padding: 0 4px;"
        )
        self._rider_mismatch_label.setWordWrap(True)
        self._rider_mismatch_label.setVisible(False)
        rider_layout.addWidget(self._rider_mismatch_label, 1, 0, 1, 8)
        return rider_group

    def _build_assessment_format_group(self) -> QGroupBox:
        self.assessment_group = QGroupBox("Assessment Format")
        self.assessment_group.setStyleSheet(GROUP_BOX_STYLE)
        assess_vbox = QVBoxLayout(self.assessment_group)
        assess_vbox.setContentsMargins(12, 20, 12, 8)
        assess_vbox.setSpacing(4)

        self._add_survival_row(
            assess_vbox,
            "chk_five_year",
            "5-Year Survival Rate:",
            "five_year_input",
            "e.g. 0.018",
            "chk_return_5yr",
            "Return (drop after yr 5)",
        )
        self._add_survival_row(
            assess_vbox,
            "chk_ten_year",
            "10-Year Survival Rate:",
            "ten_year_input",
            "e.g. 0.500",
            "chk_return_10yr",
            "Return (drop after yr 10)",
        )
        self._add_survival_row(
            assess_vbox,
            "chk_le",
            "Life Expectancy:",
            "le_input",
            "e.g. 4.9",
        )
        self._add_direct_input_row(
            assess_vbox,
            "chk_incr_decrement",
            "Increased Decrement:",
            "incr_decrement_input",
            "%",
            70,
            "incr_decrement_start_input",
            "incr_decrement_stop_input",
        )
        self._add_direct_input_row(
            assess_vbox,
            "chk_table",
            "Table:",
            "table_input",
            "rating",
            70,
            "table_start_input",
            "table_stop_input",
        )
        self._add_direct_input_row(
            assess_vbox,
            "chk_flat",
            "Flat:",
            "flat_input",
            "$/1000",
            70,
            "flat_start_input",
            "flat_stop_input",
        )
        self._add_direct_input_row(
            assess_vbox,
            "chk_table_2",
            "Table 2:",
            "table_2_input",
            "rating",
            70,
            "table_2_start_input",
            "table_2_stop_input",
        )
        self._add_direct_input_row(
            assess_vbox,
            "chk_flat_2",
            "Flat 2:",
            "flat_2_input",
            "$/1000",
            70,
            "flat_2_start_input",
            "flat_2_stop_input",
        )
        return self.assessment_group

    def _assessment_checkbox(self) -> QCheckBox:
        checkbox = QCheckBox()
        checkbox.setStyleSheet(_CHECKBOX_STYLE)
        checkbox.setFixedWidth(20)
        checkbox.toggled.connect(self._on_checkbox_toggled)
        return checkbox

    def _assessment_input(self, placeholder: str, width: int, text: str = "") -> QLineEdit:
        input_widget = QLineEdit(text)
        input_widget.setPlaceholderText(placeholder)
        input_widget.setStyleSheet(INPUT_STYLE)
        input_widget.setFixedWidth(width)
        input_widget.setReadOnly(True)
        return input_widget

    def _add_survival_row(
        self,
        layout: QVBoxLayout,
        checkbox_attr: str,
        label_text: str,
        input_attr: str,
        placeholder: str,
        return_attr: str | None = None,
        return_text: str = "",
    ) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        checkbox = self._assessment_checkbox()
        setattr(self, checkbox_attr, checkbox)
        row.addWidget(checkbox)

        label = QLabel(label_text)
        label.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;")
        label.setFixedWidth(160)
        row.addWidget(label)

        input_widget = self._assessment_input(placeholder, 100)
        setattr(self, input_attr, input_widget)
        row.addWidget(input_widget)

        if return_attr:
            return_checkbox = QCheckBox(return_text)
            return_checkbox.setStyleSheet(_CHECKBOX_STYLE)
            return_checkbox.setEnabled(False)
            setattr(self, return_attr, return_checkbox)
            row.addWidget(return_checkbox)
        row.addStretch()
        layout.addLayout(row)

    def _add_direct_input_row(
        self,
        layout: QVBoxLayout,
        checkbox_attr: str,
        label_text: str,
        input_attr: str,
        placeholder: str,
        input_width: int,
        start_attr: str,
        stop_attr: str,
    ) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        checkbox = self._assessment_checkbox()
        setattr(self, checkbox_attr, checkbox)
        row.addWidget(checkbox)

        label = QLabel(label_text)
        label.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;")
        label.setFixedWidth(160)
        row.addWidget(label)

        input_widget = self._assessment_input(placeholder, input_width)
        setattr(self, input_attr, input_widget)
        row.addWidget(input_widget)
        row.addSpacing(10)
        self._add_year_input_pair(row, "Start Yr:", start_attr, "1")
        row.addSpacing(6)
        self._add_year_input_pair(row, "Stop Yr:", stop_attr, "99")
        row.addStretch()
        layout.addLayout(row)

    def _add_year_input_pair(
        self,
        row: QHBoxLayout,
        label_text: str,
        input_attr: str,
        default_text: str,
    ) -> None:
        label = QLabel(label_text)
        label.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        row.addWidget(label)
        input_widget = self._assessment_input("", 40, default_text)
        setattr(self, input_attr, input_widget)
        row.addWidget(input_widget)

    def _build_warning_and_calculate(self, layout: QVBoxLayout) -> None:
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet(
            "color: red; font-weight: bold; font-size: 11px; padding: 2px 4px;"
        )
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        calc_row = QHBoxLayout()
        calc_row.addStretch()
        self.calc_btn = QPushButton("Calculate Substandard")
        self.calc_btn.setStyleSheet(BUTTON_SLATE_STYLE)
        self.calc_btn.clicked.connect(self._on_calculate)
        calc_row.addWidget(self.calc_btn)
        calc_row.addStretch()
        layout.addLayout(calc_row)

    def _build_derived_group(self) -> QGroupBox:
        self.derived_group = QGroupBox("Derived Substandard Values")
        self.derived_group.setStyleSheet(GROUP_BOX_STYLE)
        derived_layout = QGridLayout(self.derived_group)
        derived_layout.setContentsMargins(8, 14, 8, 4)
        derived_layout.setSpacing(2)
        self._derived_labels = {}

        header_style = (
            f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;"
            f" text-decoration: underline; padding-bottom: 1px;"
        )
        label_style = f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;"
        value_style = f"color: {GRAY_DARK}; font-size: 11px;"
        self._add_derived_column(
            derived_layout,
            0,
            "Current (Unmodified)",
            [
                (1, "5-Year Survival:", "std_survival_5yr"),
                (2, "10-Year Survival:", "std_survival_10yr"),
                (3, "Life Expectancy:", "std_le"),
                (4, "Table Ratings:", "std_table_rating"),
                (5, "Flat Extra:", "std_flat_extra"),
            ],
            header_style,
            label_style,
            value_style,
        )
        derived_layout.setColumnMinimumWidth(2, 16)
        self._add_derived_column(
            derived_layout,
            3,
            "Modified (Substandard Applied)",
            [
                (1, "5-Year Survival:", "mod_survival_5yr"),
                (2, "10-Year Survival:", "mod_survival_10yr"),
                (3, "Life Expectancy:", "mod_le"),
                (4, "Table Ratings:", "table_rating"),
                (5, "Flat Extras:", "flat_extra"),
            ],
            header_style,
            label_style,
            value_style,
        )
        derived_layout.setColumnStretch(5, 1)
        self.derived_group.setVisible(False)
        return self.derived_group

    def _add_derived_column(
        self,
        layout: QGridLayout,
        start_col: int,
        title: str,
        fields: list[tuple[int, str, str]],
        header_style: str,
        label_style: str,
        value_style: str,
    ) -> None:
        header = QLabel(title)
        header.setStyleSheet(header_style)
        layout.addWidget(header, 0, start_col, 1, 2, Qt.AlignmentFlag.AlignCenter)
        for row, label_text, key in fields:
            label = QLabel(label_text)
            label.setStyleSheet(label_style)
            layout.addWidget(label, row, start_col, Qt.AlignmentFlag.AlignRight)
            value = QLabel("\u2014")
            value.setStyleSheet(value_style)
            layout.addWidget(value, row, start_col + 1, Qt.AlignmentFlag.AlignLeft)
            self._derived_labels[key] = value

    def _build_status_label(self, layout: QVBoxLayout) -> None:
        self.status_label = QLabel("Load a policy first, then enter medical assessment values.")
        self.status_label.setStyleSheet(
            f"color: {GRAY_DARK}; font-size: 11px; font-style: italic; padding: 4px;"
        )
        layout.addWidget(self.status_label)

    def _build_results_scroll(self) -> QScrollArea:
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
        return right_scroll

    def _build_bottom_view_calc_row(self, main_layout: QVBoxLayout) -> None:
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
        crimson_btn_style, reset_btn_style = self._results_button_styles()
        self._add_acceleration_amount_row(layout, crimson_btn_style, reset_btn_style)
        layout.addWidget(self._build_full_result_group())
        self._add_min_face_row(layout, crimson_btn_style, reset_btn_style)
        layout.addWidget(self._build_partial_result_group())
        layout.addWidget(self._build_premium_impact_group())
        self._add_result_messages(layout)
        layout.addStretch()

    def _results_button_styles(self) -> tuple[str, str]:
        crimson_btn_style = f"""
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
        reset_btn_style = f"""
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
        return crimson_btn_style, reset_btn_style

    def _add_acceleration_amount_row(
        self,
        layout: QVBoxLayout,
        crimson_btn_style: str,
        reset_btn_style: str,
    ) -> None:
        accel_row = QHBoxLayout()
        accel_row.setSpacing(8)
        self._accel_label = QLabel("Full Death Benefit:")
        self._accel_label.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {CRIMSON_DARK};"
        )
        accel_row.addWidget(self._accel_label)

        self._accel_reset_btn = QPushButton("Reset")
        self._accel_reset_btn.setStyleSheet(reset_btn_style)
        self._accel_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._accel_reset_btn.clicked.connect(self._on_accel_reset)
        self._accel_reset_btn.setVisible(False)
        accel_row.addWidget(self._accel_reset_btn)

        self._face_input = QLineEdit()
        self._face_input.setStyleSheet(INPUT_STYLE)
        self._face_input.setFixedWidth(150)
        self._face_input.setPlaceholderText("Death benefit")
        accel_row.addWidget(self._face_input)

        self._face_calc_btn = QPushButton("Calc")
        self._face_calc_btn.setFixedWidth(60)
        self._face_calc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._face_calc_btn.setStyleSheet(crimson_btn_style)
        self._face_calc_btn.clicked.connect(self._on_face_calc)
        accel_row.addWidget(self._face_calc_btn)
        accel_row.addStretch()
        layout.addLayout(accel_row)

    def _new_result_group(self, title: str) -> tuple[QGroupBox, QGridLayout]:
        group = QGroupBox(title)
        group.setStyleSheet(GROUP_BOX_STYLE)
        grid = QGridLayout(group)
        grid.setContentsMargins(12, 16, 12, 8)
        grid.setSpacing(4)
        grid.setHorizontalSpacing(8)
        return group, grid

    def _add_label_value_row(
        self,
        grid: QGridLayout,
        row: int,
        label_text: str,
        label_style: str,
        value_style: str,
        labels: dict[str, QLabel],
        key: str,
        value_col: int = 1,
    ) -> QLabel:
        label = QLabel(label_text)
        label.setStyleSheet(label_style)
        grid.addWidget(label, row, value_col - 1, Qt.AlignmentFlag.AlignRight)
        value = QLabel("\u2014")
        value.setStyleSheet(value_style)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(value, row, value_col, Qt.AlignmentFlag.AlignLeft)
        labels[key] = value
        return label

    def _build_full_result_group(self) -> QGroupBox:
        self.res_full_group, full_grid = self._new_result_group("Full Acceleration")
        label_style = f"font-size: 11px; color: {GRAY_DARK};"
        value_style = f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;"
        self._res_full_labels = {}
        for row, (label_text, key) in enumerate([
            ("Eligible Death Benefit:", "eligible_db"),
            ("Actuarial Discount:", "actuarial_discount"),
            ("Administrative Fee:", "admin_fee"),
        ]):
            self._add_label_value_row(
                full_grid, row, label_text, label_style, value_style, self._res_full_labels, key
            )
        self._add_full_optional_rows(full_grid, label_style, value_style)
        self._res_full_apv_labels = {}
        self._add_apv_block(full_grid, self._res_full_apv_labels, [])
        full_grid.setColumnStretch(1, 2)
        full_grid.setColumnStretch(4, 2)
        return self.res_full_group

    def _add_full_optional_rows(
        self,
        grid: QGridLayout,
        label_style: str,
        value_style: str,
    ) -> None:
        self._full_loan_lbl = self._add_label_value_row(
            grid, 3, "Loan Repayment:", label_style, value_style,
            self._res_full_labels, "loan_repayment"
        )
        self._full_loan_lbl.setVisible(False)
        self._res_full_labels["loan_repayment"].setVisible(False)

        divider = QFrame()
        divider.setStyleSheet(DIVIDER_STYLE)
        divider.setFixedHeight(2)
        grid.addWidget(divider, 4, 0, 1, 2)
        self._add_standalone_result_value(grid, 5, "Calculated Benefit:", True)
        self._add_full_ratio_row(grid)
        self._full_sv_lbl = self._add_label_value_row(
            grid, 7, "Surrender Value:", label_style, value_style,
            self._res_full_labels, "surrender_value"
        )
        self._res_full_labels["surrender_value"].setVisible(False)
        self._full_sv_lbl.setVisible(False)
        self._full_accel_lbl = QLabel("Accelerated Benefit:")
        self._full_accel_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {CRIMSON_DARK};"
        )
        grid.addWidget(self._full_accel_lbl, 8, 0, Qt.AlignmentFlag.AlignRight)
        self.res_full_accel_benefit_label = QLabel("\u2014")
        self.res_full_accel_benefit_label.setStyleSheet(LABEL_MONEY_LARGE_STYLE)
        grid.addWidget(self.res_full_accel_benefit_label, 8, 1, Qt.AlignmentFlag.AlignLeft)
        self._full_accel_lbl.setVisible(False)
        self.res_full_accel_benefit_label.setVisible(False)

    def _add_standalone_result_value(
        self,
        grid: QGridLayout,
        row: int,
        label_text: str,
        full: bool,
    ) -> None:
        label = QLabel(label_text)
        label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {CRIMSON_DARK};")
        grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignRight)
        value = QLabel("\u2014")
        value.setStyleSheet(LABEL_MONEY_LARGE_STYLE)
        grid.addWidget(value, row, 1, Qt.AlignmentFlag.AlignLeft)
        if full:
            self.res_full_benefit_label = value
        else:
            self.res_partial_benefit_label = value
            self._res_partial_static_widgets.append(label)

    def _add_full_ratio_row(self, grid: QGridLayout) -> None:
        label = QLabel("Benefit Ratio:")
        label.setStyleSheet(f"font-size: 10px; color: {GRAY_TEXT};")
        grid.addWidget(label, 6, 0, Qt.AlignmentFlag.AlignRight)
        self.res_full_ratio_label = QLabel("\u2014")
        self.res_full_ratio_label.setStyleSheet(
            f"font-size: 10px; color: {GRAY_TEXT}; font-weight: bold;"
        )
        grid.addWidget(self.res_full_ratio_label, 6, 1, Qt.AlignmentFlag.AlignLeft)

    def _add_apv_block(
        self,
        grid: QGridLayout,
        labels: dict[str, QLabel],
        static_widgets: list[QWidget],
    ) -> None:
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet(f"color: {GRAY_MID}; background: {GRAY_MID};")
        grid.addWidget(separator, 0, 2, 9, 1)
        static_widgets.append(separator)
        label_style = f"font-size: 11px; color: {GRAY_DARK};"
        value_style = f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;"
        for row, (apv_label, apv_key) in enumerate([
            ("APV_FB:", "apv_fb"),
            ("APV_FP:", "apv_fp"),
            ("APV_FD:", "apv_fd"),
        ]):
            label = QLabel(apv_label)
            label.setStyleSheet(label_style)
            grid.addWidget(label, row, 3, Qt.AlignmentFlag.AlignRight)
            value = QLabel("\u2014")
            value.setStyleSheet(value_style)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(value, row, 4, Qt.AlignmentFlag.AlignLeft)
            labels[apv_key] = value
            static_widgets.append(label)

    def _add_min_face_row(
        self,
        layout: QVBoxLayout,
        crimson_btn_style: str,
        reset_btn_style: str,
    ) -> None:
        min_face_row = QHBoxLayout()
        min_face_row.setContentsMargins(0, 2, 0, 2)
        self._min_face_label = QLabel("Min Face Amount:")
        self._min_face_label.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {CRIMSON_DARK};"
        )
        min_face_row.addWidget(self._min_face_label)
        self._min_face_reset_btn = QPushButton("Reset Min Amount")
        self._min_face_reset_btn.setStyleSheet(reset_btn_style)
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
        self._min_face_calc_btn.setStyleSheet(crimson_btn_style)
        self._min_face_calc_btn.clicked.connect(self._on_min_face_calc)
        min_face_row.addWidget(self._min_face_calc_btn)
        min_face_row.addStretch()
        layout.addLayout(min_face_row)

    def _build_partial_result_group(self) -> QGroupBox:
        self.res_partial_group, partial_grid = self._new_result_group("Max Partial Acceleration")
        label_style = f"font-size: 11px; color: {GRAY_DARK};"
        value_style = f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;"
        self._res_partial_labels = {}
        self._res_partial_static_widgets = []
        for row, (label_text, key) in enumerate([
            ("Eligible Death Benefit:", "eligible_db"),
            ("Actuarial Discount:", "actuarial_discount"),
            ("Administrative Fee:", "admin_fee"),
        ]):
            label = self._add_label_value_row(
                partial_grid, row, label_text, label_style, value_style,
                self._res_partial_labels, key
            )
            self._res_partial_static_widgets.append(label)
        self._add_partial_optional_rows(partial_grid, label_style, value_style)
        self._res_partial_apv_labels = {}
        self._add_apv_block(partial_grid, self._res_partial_apv_labels, self._res_partial_static_widgets)
        self._add_partial_not_allowed_label(partial_grid)
        partial_grid.setColumnStretch(1, 2)
        partial_grid.setColumnStretch(4, 2)
        return self.res_partial_group

    def _add_partial_optional_rows(
        self,
        grid: QGridLayout,
        label_style: str,
        value_style: str,
    ) -> None:
        self._partial_loan_lbl = self._add_label_value_row(
            grid, 3, "Loan Repayment:", label_style, value_style,
            self._res_partial_labels, "loan_repayment"
        )
        self._partial_loan_lbl.setVisible(False)
        self._res_partial_labels["loan_repayment"].setVisible(False)
        self._res_partial_static_widgets.append(self._partial_loan_lbl)
        self._add_partial_divider_and_core_rows(grid)
        self._partial_sv_lbl = self._add_label_value_row(
            grid, 7, "Surrender Value:", label_style, value_style,
            self._res_partial_labels, "surrender_value"
        )
        self._partial_sv_lbl.setVisible(False)
        self._res_partial_labels["surrender_value"].setVisible(False)
        self._res_partial_static_widgets.append(self._partial_sv_lbl)
        self._partial_accel_lbl = QLabel("Accelerated Benefit:")
        self._partial_accel_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {CRIMSON_DARK};"
        )
        grid.addWidget(self._partial_accel_lbl, 8, 0, Qt.AlignmentFlag.AlignRight)
        self.res_partial_accel_benefit_label = QLabel("\u2014")
        self.res_partial_accel_benefit_label.setStyleSheet(LABEL_MONEY_LARGE_STYLE)
        grid.addWidget(self.res_partial_accel_benefit_label, 8, 1, Qt.AlignmentFlag.AlignLeft)
        self._partial_accel_lbl.setVisible(False)
        self.res_partial_accel_benefit_label.setVisible(False)
        self._res_partial_static_widgets.append(self._partial_accel_lbl)

    def _add_partial_divider_and_core_rows(self, grid: QGridLayout) -> None:
        divider = QFrame()
        divider.setStyleSheet(DIVIDER_STYLE)
        divider.setFixedHeight(2)
        grid.addWidget(divider, 4, 0, 1, 2)
        self._res_partial_static_widgets.append(divider)
        self._add_standalone_result_value(grid, 5, "Calculated Benefit:", False)
        label = QLabel("Benefit Ratio:")
        label.setStyleSheet(f"font-size: 10px; color: {GRAY_TEXT};")
        grid.addWidget(label, 6, 0, Qt.AlignmentFlag.AlignRight)
        self._res_partial_static_widgets.append(label)
        self.res_partial_ratio_label = QLabel("\u2014")
        self.res_partial_ratio_label.setStyleSheet(
            f"font-size: 10px; color: {GRAY_TEXT}; font-weight: bold;"
        )
        grid.addWidget(self.res_partial_ratio_label, 6, 1, Qt.AlignmentFlag.AlignLeft)

    def _add_partial_not_allowed_label(self, grid: QGridLayout) -> None:
        self._partial_not_allowed_label = QLabel(
            "MAX PARTIAL NOT ALLOWED\nPOLICY ALREADY AT MINIMUM FACE"
        )
        self._partial_not_allowed_label.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {CRIMSON_DARK}; padding: 16px;"
        )
        self._partial_not_allowed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._partial_not_allowed_label.setVisible(False)
        grid.addWidget(self._partial_not_allowed_label, 0, 0, 9, 5)

    def _build_premium_impact_group(self) -> QGroupBox:
        self.res_premium_group = QGroupBox("Premium Impact")
        self.res_premium_group.setStyleSheet(GROUP_BOX_STYLE)
        prem_grid = QGridLayout(self.res_premium_group)
        prem_grid.setContentsMargins(12, 16, 12, 8)
        prem_grid.setSpacing(4)
        self._prem_row_labels = []
        for row, label_text in enumerate([
            "Premium Before:", "After (Full Accel):", "After (Max Partial):"
        ]):
            label = QLabel(label_text)
            label.setStyleSheet(
                f"font-size: 12px; font-weight: bold; color: {CRIMSON_DARK};"
            )
            prem_grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignRight)
            self._prem_row_labels.append(label)
        self._add_premium_values(prem_grid)
        prem_grid.setColumnStretch(3, 1)
        return self.res_premium_group

    def _add_premium_values(self, grid: QGridLayout) -> None:
        self.res_premium_before_label = QLabel("\u2014")
        self.res_premium_before_label.setStyleSheet(LABEL_MONEY_STYLE)
        grid.addWidget(self.res_premium_before_label, 0, 1)
        self.res_premium_after_full_label = QLabel("\u2014")
        self.res_premium_after_full_label.setStyleSheet(LABEL_MONEY_STYLE)
        grid.addWidget(self.res_premium_after_full_label, 1, 1)
        self.res_premium_after_partial_label = QLabel("\u2014")
        self.res_premium_after_partial_label.setStyleSheet(LABEL_MONEY_STYLE)
        grid.addWidget(self.res_premium_after_partial_label, 2, 1)
        self.res_premium_after_partial_input = QLineEdit()
        self.res_premium_after_partial_input.setPlaceholderText("0.00")
        self.res_premium_after_partial_input.setStyleSheet(INPUT_STYLE)
        self.res_premium_after_partial_input.setFixedWidth(120)
        self.res_premium_after_partial_input.setVisible(False)
        grid.addWidget(self.res_premium_after_partial_input, 2, 1)
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
        grid.addWidget(self._partial_prem_detail_btn, 2, 2)

    def _add_result_messages(self, layout: QVBoxLayout) -> None:
        self.res_messages_label = QLabel("")
        self.res_messages_label.setWordWrap(True)
        self.res_messages_label.setStyleSheet(
            f"color: #C62828; font-size: 13px; font-weight: bold; padding: 4px;"
        )
        self.res_messages_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.res_messages_label.customContextMenuRequested.connect(
            self._show_messages_context_menu
        )
        layout.addWidget(self.res_messages_label)

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

        if is_first_display:
            self._populate_default_acceleration_amount()
        self.res_full_group.setTitle("Full Acceleration")
        self._display_full_acceleration(result)
        at_min_face = self._display_partial_acceleration(result)
        self._display_premium_impact(result, at_min_face)
        self._display_result_messages(result)

    def _display_full_acceleration(self, result: ABRQuoteResult) -> None:
        """Render the Full Acceleration result group."""
        self._res_full_labels["eligible_db"].setText(self._fmt_money(result.full_eligible_db))
        self._res_full_labels["actuarial_discount"].setText(
            self._fmt_money(result.full_actuarial_discount)
        )
        self._res_full_labels["admin_fee"].setText(self._fmt_money(result.full_admin_fee))
        has_loan = result.full_loan_repayment > 0
        self._full_loan_lbl.setVisible(has_loan)
        self._res_full_labels["loan_repayment"].setVisible(has_loan)
        if has_loan:
            self._res_full_labels["loan_repayment"].setText(
                self._fmt_money(result.full_loan_repayment)
            )
        self.res_full_benefit_label.setText(
            f"$0.00  (calc: {self._fmt_money(result.full_accel_benefit)})"
            if result.full_accel_benefit < 0
            else self._fmt_money(result.full_accel_benefit)
        )
        self.res_full_ratio_label.setText(f"{result.full_benefit_ratio * 100:.2f}%")
        self._display_full_surrender_value(result)
        self._res_full_apv_labels["apv_fb"].setText(self._fmt_money(result.apv_fb))
        self._res_full_apv_labels["apv_fp"].setText(self._fmt_money(result.apv_fp))
        self._res_full_apv_labels["apv_fd"].setText(self._fmt_money(result.apv_fd))

    def _display_full_surrender_value(self, result: ABRQuoteResult) -> None:
        has_sv = result.full_surrender_value > 0
        self._full_sv_lbl.setVisible(has_sv)
        self._res_full_labels["surrender_value"].setVisible(has_sv)
        self._full_accel_lbl.setVisible(has_sv)
        self.res_full_accel_benefit_label.setVisible(has_sv)
        if has_sv:
            self._res_full_labels["surrender_value"].setText(
                self._fmt_money(result.full_surrender_value)
            )
            self.res_full_accel_benefit_label.setText(
                self._fmt_money(result.full_accelerated_benefit)
            )

    def _display_partial_acceleration(self, result: ABRQuoteResult) -> bool:
        """Render the Max Partial Acceleration group; return whether it is disallowed."""
        at_min_face = result.partial_eligible_db <= 0
        has_partial_loan = result.partial_loan_repayment > 0
        has_partial_sv = result.partial_surrender_value > 0
        self._set_partial_visibility(at_min_face, has_partial_loan, has_partial_sv)
        if not at_min_face:
            self._populate_partial_values(result, has_partial_loan, has_partial_sv)
        return at_min_face

    def _set_partial_visibility(
        self,
        at_min_face: bool,
        has_partial_loan: bool,
        has_partial_sv: bool,
    ) -> None:
        self._partial_not_allowed_label.setVisible(at_min_face)
        for widget in self._res_partial_static_widgets:
            if widget in (self._partial_sv_lbl, self._partial_accel_lbl):
                widget.setVisible(not at_min_face and has_partial_sv)
            else:
                widget.setVisible(not at_min_face)
        for key, value in self._res_partial_labels.items():
            if key == "loan_repayment":
                value.setVisible(not at_min_face and has_partial_loan)
            elif key == "surrender_value":
                value.setVisible(not at_min_face and has_partial_sv)
            else:
                value.setVisible(not at_min_face)
        self._partial_loan_lbl.setVisible(not at_min_face and has_partial_loan)
        self._partial_sv_lbl.setVisible(not at_min_face and has_partial_sv)
        self.res_partial_benefit_label.setVisible(not at_min_face)
        self.res_partial_ratio_label.setVisible(not at_min_face)
        self.res_partial_accel_benefit_label.setVisible(not at_min_face and has_partial_sv)
        for value in self._res_partial_apv_labels.values():
            value.setVisible(not at_min_face)

    def _populate_partial_values(
        self,
        result: ABRQuoteResult,
        has_partial_loan: bool,
        has_partial_sv: bool,
    ) -> None:
        self._res_partial_labels["eligible_db"].setText(self._fmt_money(result.partial_eligible_db))
        self._res_partial_labels["actuarial_discount"].setText(
            self._fmt_money(result.partial_actuarial_discount)
        )
        self._res_partial_labels["admin_fee"].setText(self._fmt_money(result.partial_admin_fee))
        if has_partial_loan:
            self._res_partial_labels["loan_repayment"].setText(
                self._fmt_money(result.partial_loan_repayment)
            )
        self.res_partial_benefit_label.setText(
            f"$0.00  (calc: {self._fmt_money(result.partial_accel_benefit)})"
            if result.partial_accel_benefit < 0
            else self._fmt_money(result.partial_accel_benefit)
        )
        self.res_partial_ratio_label.setText(f"{result.partial_benefit_ratio * 100:.2f}%")
        if has_partial_sv:
            self._res_partial_labels["surrender_value"].setText(
                self._fmt_money(result.partial_surrender_value)
            )
            self.res_partial_accel_benefit_label.setText(
                self._fmt_money(result.partial_accelerated_benefit)
            )
        ratio = result.partial_eligible_db / result.full_eligible_db if result.full_eligible_db > 0 else 0.0
        self._res_partial_apv_labels["apv_fb"].setText(self._fmt_money(result.apv_fb * ratio))
        self._res_partial_apv_labels["apv_fp"].setText(self._fmt_money(result.apv_fp * ratio))
        self._res_partial_apv_labels["apv_fd"].setText(self._fmt_money(result.apv_fd * ratio))

    def _display_premium_impact(self, result: ABRQuoteResult, at_min_face: bool) -> None:
        self.res_premium_before_label.setText(result.premium_before)
        self.res_premium_after_full_label.setText(f"${result.premium_after_full:,.2f}")
        is_ul = self._policy and self._policy.product_type in ("UL", "IUL", "ISWL")
        if is_ul:
            self.res_premium_after_partial_label.setVisible(False)
            self.res_premium_after_partial_input.setVisible(not at_min_face)
        elif at_min_face:
            self.res_premium_after_partial_label.setText("NOT ALLOWED")
        else:
            self.res_premium_after_partial_label.setText(result.premium_after_partial)

    def _display_result_messages(self, result: ABRQuoteResult) -> None:
        if result.messages:
            self.res_messages_label.setText(
                "\n\n".join(f"• {message}" for message in result.messages)
            )
        else:
            self.res_messages_label.setText("")

    def _populate_default_acceleration_amount(self):
        """Set the default acceleration amount based on DB option.

        Uses the shared policy default so Option B/C handling stays aligned
        with the calculation engine.
        """
        if not self._policy:
            return
        default_amount = self._policy.default_death_benefit
        self._default_accel_amount = default_amount
        self._face_input.setText(f"{default_amount:,.2f}")
        self._update_accel_reset_visibility()

    def _on_face_calc(self):
        """Recalculate Full Acceleration and Max Partial for an entered face."""
        if not self._policy or not self._result:
            return
        custom_face = self._read_custom_face_amount()
        if custom_face is None:
            return
        result = self._result
        self._display_result_messages(result)
        self.res_full_group.setTitle("Full Acceleration")

        ratio = custom_face / result.full_eligible_db if result.full_eligible_db > 0 else 0.0
        new_discount = round(result.full_actuarial_discount * ratio, 2)
        self._render_custom_full_acceleration(result, custom_face, ratio, new_discount)
        self._render_custom_partial_acceleration(result, custom_face, ratio)
        self._update_accel_reset_visibility()

    def _read_custom_face_amount(self) -> float | None:
        raw = self._face_input.text().replace("$", "").replace(",", "").strip()
        try:
            return float(raw)
        except ValueError:
            self.res_messages_label.setText("• Please enter a valid numeric face amount.")
            return None

    def _render_custom_full_acceleration(
        self,
        result: ABRQuoteResult,
        custom_face: float,
        ratio: float,
        new_discount: float,
    ) -> None:
        admin_fee = result.full_admin_fee
        new_loan = round(result.full_loan_repayment * ratio, 2) if result.full_loan_repayment > 0 else 0.0
        self._full_loan_lbl.setVisible(new_loan > 0)
        self._res_full_labels["loan_repayment"].setVisible(new_loan > 0)
        if new_loan > 0:
            self._res_full_labels["loan_repayment"].setText(self._fmt_money(new_loan))
        new_benefit = round(custom_face - new_discount - admin_fee - new_loan, 2)
        self._res_full_labels["eligible_db"].setText(self._fmt_money(custom_face))
        self._res_full_labels["actuarial_discount"].setText(self._fmt_money(new_discount))
        self._res_full_labels["admin_fee"].setText(self._fmt_money(admin_fee))
        self.res_full_benefit_label.setText(
            f"$0.00  (calc: {self._fmt_money(new_benefit)})"
            if new_benefit < 0 else self._fmt_money(new_benefit)
        )
        new_ratio = max(0.0, new_benefit) / custom_face if custom_face > 0 else 0.0
        self.res_full_ratio_label.setText(f"{new_ratio * 100:.2f}%")
        self._render_custom_full_surrender(result, ratio, new_benefit)
        self._res_full_apv_labels["apv_fb"].setText(self._fmt_money(result.apv_fb * ratio))
        self._res_full_apv_labels["apv_fp"].setText(self._fmt_money(result.apv_fp * ratio))
        self._res_full_apv_labels["apv_fd"].setText(self._fmt_money(result.apv_fd * ratio))

    def _render_custom_full_surrender(
        self,
        result: ABRQuoteResult,
        ratio: float,
        new_benefit: float,
    ) -> None:
        new_sv = round(result.full_surrender_value * ratio, 2) if result.full_surrender_value > 0 else 0.0
        has_sv = new_sv > 0
        self._full_sv_lbl.setVisible(has_sv)
        self._res_full_labels["surrender_value"].setVisible(has_sv)
        self._full_accel_lbl.setVisible(has_sv)
        self.res_full_accel_benefit_label.setVisible(has_sv)
        if has_sv:
            self._res_full_labels["surrender_value"].setText(self._fmt_money(new_sv))
            self.res_full_accel_benefit_label.setText(
                self._fmt_money(max(max(0.0, new_benefit), new_sv))
            )

    def _render_custom_partial_acceleration(
        self,
        result: ABRQuoteResult,
        custom_face: float,
        full_ratio: float,
    ) -> None:
        del full_ratio
        partial_eligible = max(0.0, custom_face - self.get_min_face_amount())
        at_min_face = partial_eligible <= 0
        has_partial_loan = result.partial_loan_repayment > 0
        has_partial_sv = result.partial_surrender_value > 0
        self._set_partial_visibility(at_min_face, has_partial_loan, has_partial_sv)
        if at_min_face:
            return
        partial_ratio = (
            partial_eligible / result.full_eligible_db
            if result.full_eligible_db > 0 else 0.0
        )
        partial_discount = round(result.full_actuarial_discount * partial_ratio, 2)
        partial_loan = round(result.full_loan_repayment * partial_ratio, 2)
        partial_benefit = round(
            partial_eligible - partial_discount - result.full_admin_fee - partial_loan,
            2,
        )
        self._set_custom_partial_values(
            result,
            partial_eligible,
            partial_discount,
            partial_loan,
            partial_benefit,
            partial_ratio,
            has_partial_sv,
        )

    def _set_custom_partial_values(
        self,
        result: ABRQuoteResult,
        partial_eligible: float,
        partial_discount: float,
        partial_loan: float,
        partial_benefit: float,
        partial_ratio: float,
        has_partial_sv: bool,
    ) -> None:
        self._res_partial_labels["eligible_db"].setText(self._fmt_money(partial_eligible))
        self._res_partial_labels["actuarial_discount"].setText(self._fmt_money(partial_discount))
        self._res_partial_labels["admin_fee"].setText(self._fmt_money(result.full_admin_fee))
        if partial_loan > 0:
            self._res_partial_labels["loan_repayment"].setText(self._fmt_money(partial_loan))
        self.res_partial_benefit_label.setText(
            f"$0.00  (calc: {self._fmt_money(partial_benefit)})"
            if partial_benefit < 0 else self._fmt_money(partial_benefit)
        )
        partial_new_ratio = max(0.0, partial_benefit) / partial_eligible if partial_eligible > 0 else 0.0
        self.res_partial_ratio_label.setText(f"{partial_new_ratio * 100:.2f}%")
        if has_partial_sv:
            partial_sv = round(result.full_surrender_value * partial_ratio, 2)
            self._res_partial_labels["surrender_value"].setText(self._fmt_money(partial_sv))
            self.res_partial_accel_benefit_label.setText(
                self._fmt_money(max(max(0.0, partial_benefit), partial_sv))
            )
        self._res_partial_apv_labels["apv_fb"].setText(self._fmt_money(result.apv_fb * partial_ratio))
        self._res_partial_apv_labels["apv_fp"].setText(self._fmt_money(result.apv_fp * partial_ratio))
        self._res_partial_apv_labels["apv_fd"].setText(self._fmt_money(result.apv_fd * partial_ratio))

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
        from .view_models import AccelerationInputState, CalcViewerModel
        after_partial = self.res_premium_after_partial_input.text().strip()

        # Read current face/min-face input values
        accel_raw = self._face_input.text().replace("$", "").replace(",", "").strip()
        try:
            accel_val = float(accel_raw)
        except ValueError:
            accel_val = 0.0
        min_face_val = self.get_min_face_amount()

        viewer = CalcViewerDialog(CalcViewerModel(
            mortality_rows=self._mort_detail,
            apv_rows=self._apv_detail,
            apv_summary=self._apv_summary,
            policy_info=self._policy_info,
            policy=self._policy,
            assessment=self._assessment,
            result=self._result,
            derived_values=self.get_derived_display_values(),
            acceleration=AccelerationInputState(
                acceleration_amount=accel_val,
                min_face_amount=min_face_val,
                after_partial_override=after_partial,
                warnings=self._get_current_warnings(),
            ),
        ), parent=None)
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
        partial_calc = max(0.0, r.partial_accel_benefit)
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
            f"  Calculated Benefit: {self._fmt_money(full_calc)}",
            f"  Benefit Ratio:      {r.full_benefit_ratio * 100:.2f}%",
        ]
        if r.full_surrender_value > 0:
            lines += [
                f"  Surrender Value:    {self._fmt_money(r.full_surrender_value)}",
                f"  Accelerated Benefit:{self._fmt_money(r.full_accelerated_benefit)}",
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
            f"  Calculated Benefit: {self._fmt_money(partial_calc)}",
            f"  Benefit Ratio:      {r.partial_benefit_ratio * 100:.2f}%",
        ]
        if r.partial_surrender_value > 0:
            lines += [
                f"  Surrender Value:    {self._fmt_money(r.partial_surrender_value)}",
                f"  Accelerated Benefit:{self._fmt_money(r.partial_accelerated_benefit)}",
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
        """Compute and display fixed terminal-rider derived values."""
        if self._policy is None:
            return
        self._render_assessment_result(
            terminal_substandard(self._policy),
            emit_ready=False,
        )

    # ── Actions ──────────────────────────────────────────────────────────

    def _read_assessment_inputs(self) -> AssessmentInputs | None:
        """Read and validate the assessment form into a pure input object."""
        flags = self._assessment_flags()
        if not (flags["has_survival"] or flags["use_table"] or flags["use_increased_decrement"]):
            self._show_warning(
                "Check at least one survival input, the Table checkbox, or Increased Decrement."
            )
            return None
        survival = self._read_survival_values(flags)
        if survival is None:
            return None
        direct = self._read_direct_values(flags)
        if direct is None:
            return None
        return AssessmentInputs(
            rider_type=self.rider_combo.currentText(),
            use_return_5yr=self.chk_return_5yr.isChecked(),
            use_return_10yr=self.chk_return_10yr.isChecked(),
            in_lieu_of=True,
            **{key: value for key, value in flags.items() if key != "has_survival"},
            **survival,
            **direct,
        )

    def _assessment_flags(self) -> dict[str, bool]:
        use_five = self.chk_five_year.isChecked()
        use_ten = self.chk_ten_year.isChecked()
        use_le = self.chk_le.isChecked()
        return {
            "use_five_year": use_five,
            "use_ten_year": use_ten,
            "use_le": use_le,
            "has_survival": use_five or use_ten or use_le,
            "use_table": self.chk_table.isChecked(),
            "use_flat": self.chk_flat.isChecked(),
            "use_table_2": self.chk_table_2.isChecked(),
            "use_flat_2": self.chk_flat_2.isChecked(),
            "use_increased_decrement": self.chk_incr_decrement.isChecked(),
        }

    def _read_survival_values(self, flags: dict[str, bool]) -> dict[str, float] | None:
        try:
            five_yr = float(self.five_year_input.text().strip()) if flags["use_five_year"] else 0.0
            ten_yr = float(self.ten_year_input.text().strip()) if flags["use_ten_year"] else 0.0
            le_val = float(self.le_input.text().strip()) if flags["use_le"] else 0.0
        except ValueError:
            self._show_warning(
                "Enter valid numeric values for all checked survival fields."
            )
            return None

        if flags["use_five_year"] and not (0 <= five_yr <= 1):
            self._show_warning("5-Year Survival must be between 0 and 1.")
            return None
        if flags["use_ten_year"] and not (0 <= ten_yr <= 1):
            self._show_warning("10-Year Survival must be between 0 and 1.")
            return None
        return {
            "five_year_survival": five_yr,
            "ten_year_survival": ten_yr,
            "life_expectancy_years": le_val,
        }

    def _read_direct_values(self, flags: dict[str, bool]) -> dict[str, float | int] | None:
        try:
            direct_table = float(self.table_input.text().strip()) if flags["use_table"] else 0.0
            table_start_yr = int(self.table_start_input.text().strip()) if flags["use_table"] else 1
            table_stop_yr = int(self.table_stop_input.text().strip()) if flags["use_table"] else 99
            direct_flat = float(self.flat_input.text().strip()) if flags["use_flat"] else 0.0
            flat_start_yr = int(self.flat_start_input.text().strip()) if flags["use_flat"] else 1
            flat_stop_yr = int(self.flat_stop_input.text().strip()) if flags["use_flat"] else 99
            direct_table_2 = float(self.table_2_input.text().strip()) if flags["use_table_2"] else 0.0
            table_2_start_yr = int(self.table_2_start_input.text().strip()) if flags["use_table_2"] else 1
            table_2_stop_yr = int(self.table_2_stop_input.text().strip()) if flags["use_table_2"] else 99
            direct_flat_2 = float(self.flat_2_input.text().strip()) if flags["use_flat_2"] else 0.0
            flat_2_start_yr = int(self.flat_2_start_input.text().strip()) if flags["use_flat_2"] else 1
            flat_2_stop_yr = int(self.flat_2_stop_input.text().strip()) if flags["use_flat_2"] else 99
            incr_pct = float(self.incr_decrement_input.text().strip()) if flags["use_increased_decrement"] else 0.0
            incr_start_yr = (
                int(self.incr_decrement_start_input.text().strip())
                if flags["use_increased_decrement"] else 1
            )
            incr_stop_yr = (
                int(self.incr_decrement_stop_input.text().strip())
                if flags["use_increased_decrement"] else 99
            )
        except ValueError:
            self._show_warning(
                "Enter valid numeric values for all checked Table / Flat fields."
            )
            return None

        return {
            "direct_table_rating": direct_table,
            "table_start_year": table_start_yr,
            "table_stop_year": table_stop_yr,
            "direct_flat_extra": direct_flat,
            "flat_start_year": flat_start_yr,
            "flat_stop_year": flat_stop_yr,
            "direct_table_rating_2": direct_table_2,
            "table_2_start_year": table_2_start_yr,
            "table_2_stop_year": table_2_stop_yr,
            "direct_flat_extra_2": direct_flat_2,
            "flat_2_start_year": flat_2_start_yr,
            "flat_2_stop_year": flat_2_stop_yr,
            "direct_increased_decrement": incr_pct,
            "incr_decrement_start_year": incr_start_yr,
            "incr_decrement_stop_year": incr_stop_yr,
        }

    def _render_assessment_result(
        self,
        result: SubstandardSolveResult,
        *,
        emit_ready: bool = True,
    ) -> None:
        """Render a core assessment result into labels and panel state."""
        self._assessment = result.assessment
        for key, value in result.derived_values.items():
            self._derived_labels[key].setText(value)
        self.derived_group.setVisible(True)
        if emit_ready:
            self.assessment_ready.emit(self._assessment)

    def _on_calculate(self):
        """Run the core goal seek to derive substandard from checked inputs."""
        self._clear_warning()
        if self._policy is None:
            self._show_warning("Please load a policy first (Step 1).")
            return

        inputs = self._read_assessment_inputs()
        if inputs is None:
            return

        self.status_label.setText("Computing substandard values (goal seek)...")
        self.calc_btn.setEnabled(False)
        try:
            result = solve_substandard(self._policy, inputs)
            self._render_assessment_result(result)
            self.status_label.setText("Substandard values computed successfully.")
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

        from ..models.abr_data import default_minimum_face
        self._default_min_face = f"{default_minimum_face(policy.product_type):,.0f}"
        self._min_face_input.setText(self._default_min_face)
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

    def get_after_partial_deduction(self) -> str:
        """Return the user-entered UL monthly deduction after max partial."""
        return self.res_premium_after_partial_input.text().strip()

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
        if self._policy is not None:
            self._render_assessment_result(
                terminal_substandard(self._policy),
                emit_ready=False,
            )
        elif self._assessment is None:
            self._assessment = MedicalAssessment(rider_type="Terminal")
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
