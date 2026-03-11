"""
ABR Quote — Results Panel (Step 3).

Displays full and partial acceleration results, premium impact,
and provides export to Excel functionality.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QFrame,
    QFileDialog, QMessageBox,
)

from ..models.abr_data import ABRPolicyData, MedicalAssessment, ABRQuoteResult
from ..models.abr_constants import PLAN_CODE_INFO
from .abr_styles import (
    CRIMSON_DARK,
    SLATE_PRIMARY, SLATE_DARK,
    WHITE, GRAY_DARK, GRAY_TEXT,
    GROUP_BOX_STYLE, BUTTON_PRIMARY_STYLE, BUTTON_SLATE_STYLE, BUTTON_NAV_STYLE,
    LABEL_MONEY_STYLE, LABEL_MONEY_LARGE_STYLE, DIVIDER_STYLE,
)
from .calc_viewer import CalcViewerDialog

logger = logging.getLogger(__name__)


class ResultsPanel(QWidget):
    """Step 3 panel — display ABR quote results and export.

    Signals:
        new_quote_requested: User wants to start over.
    """

    new_quote_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: Optional[ABRQuoteResult] = None
        self._policy: Optional[ABRPolicyData] = None
        self._assessment: Optional[MedicalAssessment] = None
        # Detailed calc data for viewer
        self._mort_detail: list[dict] = []
        self._apv_detail: list[dict] = []
        self._apv_summary: dict = {}
        self._policy_info: str = ""
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # ── Full Acceleration ───────────────────────────────────────────
        self.full_group = QGroupBox("Full Acceleration")
        self.full_group.setStyleSheet(GROUP_BOX_STYLE)
        full_layout = QGridLayout(self.full_group)
        full_layout.setContentsMargins(12, 16, 12, 8)
        full_layout.setSpacing(6)

        self._full_labels = {}
        full_fields = [
            ("Eligible Death Benefit:", "eligible_db"),
            ("Actuarial Discount:", "actuarial_discount"),
            ("Administrative Fee:", "admin_fee"),
        ]

        for i, (label_text, key) in enumerate(full_fields):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 12px; color: {GRAY_DARK};")
            full_layout.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignRight)

            val = QLabel("—")
            val.setStyleSheet(f"font-size: 12px; color: {GRAY_DARK}; font-weight: bold;")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            full_layout.addWidget(val, i, 1, Qt.AlignmentFlag.AlignLeft)
            self._full_labels[key] = val

        # Divider
        divider = QFrame()
        divider.setStyleSheet(DIVIDER_STYLE)
        divider.setFixedHeight(2)
        full_layout.addWidget(divider, len(full_fields), 0, 1, 2)

        # Accelerated Benefit (large)
        lbl_ab = QLabel("Accelerated Benefit:")
        lbl_ab.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {CRIMSON_DARK};")
        full_layout.addWidget(lbl_ab, len(full_fields) + 1, 0, Qt.AlignmentFlag.AlignRight)

        self.full_benefit_label = QLabel("—")
        self.full_benefit_label.setStyleSheet(LABEL_MONEY_LARGE_STYLE)
        full_layout.addWidget(
            self.full_benefit_label, len(full_fields) + 1, 1,
            Qt.AlignmentFlag.AlignLeft,
        )

        # Benefit ratio
        lbl_br = QLabel("Benefit Ratio:")
        lbl_br.setStyleSheet(f"font-size: 11px; color: {GRAY_TEXT};")
        full_layout.addWidget(lbl_br, len(full_fields) + 2, 0, Qt.AlignmentFlag.AlignRight)

        self.full_ratio_label = QLabel("—")
        self.full_ratio_label.setStyleSheet(f"font-size: 11px; color: {GRAY_TEXT}; font-weight: bold;")
        full_layout.addWidget(
            self.full_ratio_label, len(full_fields) + 2, 1,
            Qt.AlignmentFlag.AlignLeft,
        )

        full_layout.setColumnStretch(2, 1)
        layout.addWidget(self.full_group)

        # ── Max Partial Acceleration ────────────────────────────────────
        self.partial_group = QGroupBox("Max Partial Acceleration")
        self.partial_group.setStyleSheet(GROUP_BOX_STYLE)
        partial_layout = QGridLayout(self.partial_group)
        partial_layout.setContentsMargins(12, 16, 12, 8)
        partial_layout.setSpacing(6)

        self._partial_labels = {}
        partial_fields = [
            ("Eligible Death Benefit:", "eligible_db"),
            ("Actuarial Discount:", "actuarial_discount"),
            ("Administrative Fee:", "admin_fee"),
        ]

        for i, (label_text, key) in enumerate(partial_fields):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 12px; color: {GRAY_DARK};")
            partial_layout.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignRight)

            val = QLabel("—")
            val.setStyleSheet(f"font-size: 12px; color: {GRAY_DARK}; font-weight: bold;")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            partial_layout.addWidget(val, i, 1, Qt.AlignmentFlag.AlignLeft)
            self._partial_labels[key] = val

        divider2 = QFrame()
        divider2.setStyleSheet(DIVIDER_STYLE)
        divider2.setFixedHeight(2)
        partial_layout.addWidget(divider2, len(partial_fields), 0, 1, 2)

        lbl_pab = QLabel("Accelerated Benefit:")
        lbl_pab.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {CRIMSON_DARK};")
        partial_layout.addWidget(lbl_pab, len(partial_fields) + 1, 0, Qt.AlignmentFlag.AlignRight)

        self.partial_benefit_label = QLabel("—")
        self.partial_benefit_label.setStyleSheet(LABEL_MONEY_LARGE_STYLE)
        partial_layout.addWidget(
            self.partial_benefit_label, len(partial_fields) + 1, 1,
            Qt.AlignmentFlag.AlignLeft,
        )

        lbl_pbr = QLabel("Benefit Ratio:")
        lbl_pbr.setStyleSheet(f"font-size: 11px; color: {GRAY_TEXT};")
        partial_layout.addWidget(lbl_pbr, len(partial_fields) + 2, 0, Qt.AlignmentFlag.AlignRight)

        self.partial_ratio_label = QLabel("—")
        self.partial_ratio_label.setStyleSheet(f"font-size: 11px; color: {GRAY_TEXT}; font-weight: bold;")
        partial_layout.addWidget(
            self.partial_ratio_label, len(partial_fields) + 2, 1,
            Qt.AlignmentFlag.AlignLeft,
        )

        partial_layout.setColumnStretch(2, 1)
        layout.addWidget(self.partial_group)

        # ── Premium Impact ──────────────────────────────────────────────
        self.premium_group = QGroupBox("Premium Impact")
        self.premium_group.setStyleSheet(GROUP_BOX_STYLE)
        premium_layout = QGridLayout(self.premium_group)
        premium_layout.setContentsMargins(12, 16, 12, 8)
        premium_layout.setSpacing(6)

        premium_layout.addWidget(
            self._make_label("Premium Before:"), 0, 0, Qt.AlignmentFlag.AlignRight
        )
        self.premium_before_label = QLabel("—")
        self.premium_before_label.setStyleSheet(LABEL_MONEY_STYLE)
        premium_layout.addWidget(self.premium_before_label, 0, 1)

        premium_layout.addWidget(
            self._make_label("After (Full Accel):"), 1, 0, Qt.AlignmentFlag.AlignRight
        )
        self.premium_after_full_label = QLabel("—")
        self.premium_after_full_label.setStyleSheet(LABEL_MONEY_STYLE)
        premium_layout.addWidget(self.premium_after_full_label, 1, 1)

        premium_layout.addWidget(
            self._make_label("After (Partial):"), 2, 0, Qt.AlignmentFlag.AlignRight
        )
        self.premium_after_partial_label = QLabel("—")
        self.premium_after_partial_label.setStyleSheet(LABEL_MONEY_STYLE)
        premium_layout.addWidget(self.premium_after_partial_label, 2, 1)

        premium_layout.setColumnStretch(2, 1)
        layout.addWidget(self.premium_group)

        # ── Messages ────────────────────────────────────────────────────
        self.messages_label = QLabel("")
        self.messages_label.setWordWrap(True)
        self.messages_label.setStyleSheet(
            "color: #C62828; font-size: 13px; font-weight: bold; padding: 4px;"
        )
        layout.addWidget(self.messages_label)

        # ── Action buttons ──────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self.export_btn = QPushButton("Export to Excel")
        self.export_btn.setStyleSheet(BUTTON_SLATE_STYLE)
        self.export_btn.clicked.connect(self._on_export)
        btn_row.addWidget(self.export_btn)

        self.copy_btn = QPushButton("Copy Summary")
        self.copy_btn.setStyleSheet(BUTTON_PRIMARY_STYLE)
        self.copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(self.copy_btn)

        self.view_calc_btn = QPushButton("View Calculated Values")
        self.view_calc_btn.setStyleSheet(BUTTON_PRIMARY_STYLE)
        self.view_calc_btn.setToolTip(
            "Inspect month-by-month mortality derivation and APV computation"
        )
        self.view_calc_btn.clicked.connect(self._on_view_calc)
        self.view_calc_btn.setEnabled(False)
        btn_row.addWidget(self.view_calc_btn)

        btn_row.addStretch()

        self.new_quote_btn = QPushButton("New Quote")
        self.new_quote_btn.setStyleSheet(BUTTON_NAV_STYLE)
        self.new_quote_btn.clicked.connect(self.new_quote_requested.emit)
        btn_row.addWidget(self.new_quote_btn)

        layout.addLayout(btn_row)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {CRIMSON_DARK};")
        return lbl

    @staticmethod
    def _fmt_money(amount: float) -> str:
        if amount < 0:
            return f"(${abs(amount):,.2f})"
        return f"${amount:,.2f}"

    # ── Public API ──────────────────────────────────────────────────────

    def set_policy(self, policy: ABRPolicyData):
        self._policy = policy

    def set_assessment(self, assessment: MedicalAssessment):
        self._assessment = assessment

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
        self.view_calc_btn.setEnabled(bool(mort_detail))

    def display_results(self, result: ABRQuoteResult):
        """Populate all result fields."""
        self._result = result

        # Full acceleration
        self._full_labels["eligible_db"].setText(self._fmt_money(result.full_eligible_db))
        self._full_labels["actuarial_discount"].setText(
            self._fmt_money(result.full_actuarial_discount)
        )
        self._full_labels["admin_fee"].setText(self._fmt_money(result.full_admin_fee))

        if result.full_accel_benefit < 0:
            self.full_benefit_label.setText(
                f"$0.00  (calc result: {self._fmt_money(result.full_accel_benefit)})"
            )
        else:
            self.full_benefit_label.setText(self._fmt_money(result.full_accel_benefit))
        self.full_ratio_label.setText(f"{result.full_benefit_ratio * 100:.2f}%")

        # Partial acceleration
        self._partial_labels["eligible_db"].setText(self._fmt_money(result.partial_eligible_db))
        self._partial_labels["actuarial_discount"].setText(
            self._fmt_money(result.partial_actuarial_discount)
        )
        self._partial_labels["admin_fee"].setText(self._fmt_money(result.partial_admin_fee))

        if result.partial_accel_benefit < 0:
            self.partial_benefit_label.setText(
                f"$0.00  (calc result: {self._fmt_money(result.partial_accel_benefit)})"
            )
        else:
            self.partial_benefit_label.setText(self._fmt_money(result.partial_accel_benefit))
        self.partial_ratio_label.setText(f"{result.partial_benefit_ratio * 100:.2f}%")

        # Premium impact
        self.premium_before_label.setText(result.premium_before)
        self.premium_after_full_label.setText(f"${result.premium_after_full:,.2f}")
        self.premium_after_partial_label.setText(result.premium_after_partial)

        # Messages
        if result.messages:
            self.messages_label.setText("\n".join(result.messages))
        else:
            self.messages_label.setText("")

    # ── View Calculated Values ────────────────────────────────────────

    def _on_view_calc(self):
        """Open the detailed calculation viewer window (modeless)."""
        if not self._mort_detail:
            return
        viewer = CalcViewerDialog(
            mortality_rows=self._mort_detail,
            apv_rows=self._apv_detail,
            apv_summary=self._apv_summary,
            policy_info=self._policy_info,
            parent=None,
        )
        viewer.show()
        # Keep a reference so the window isn't garbage-collected
        self._calc_viewer = viewer

    # ── Export ───────────────────────────────────────────────────────────

    def _on_export(self):
        """Export results to an Excel workbook."""
        if self._result is None:
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export ABR Quote",
            f"ABR_Quote_{self._policy.policy_number if self._policy else 'Unknown'}.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not filename:
            return

        try:
            self._write_excel(filename)
            QMessageBox.information(
                self, "Export Complete",
                f"ABR Quote exported to:\n{filename}",
            )
        except Exception as e:
            logger.error(f"Export error: {e}", exc_info=True)
            QMessageBox.warning(
                self, "Export Error",
                f"Could not export:\n{e}",
            )

    def _write_excel(self, filepath: str):
        """Write results to Excel workbook matching the ABR output format."""
        import openpyxl
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

        wb = openpyxl.Workbook()
        r = self._result
        p = self._policy

        # ── Sheet 1: Output - Full ──────────────────────────────────────
        ws = wb.active
        ws.title = "Output - Full"

        # Header styling
        header_font = Font(bold=True, size=12)
        money_font = Font(bold=True, size=11)
        label_font = Font(size=11)

        plan_info = PLAN_CODE_INFO.get(p.plan_code.upper(), ("", "")) if p else ("", "")

        row = 1
        ws.cell(row=row, column=1, value="ABR QUOTE — FULL ACCELERATION").font = header_font
        row += 2
        ws.cell(row=row, column=1, value="Policy Number:").font = label_font
        ws.cell(row=row, column=2, value=p.policy_number if p else "").font = money_font
        row += 1
        ws.cell(row=row, column=1, value="Insured:").font = label_font
        ws.cell(row=row, column=2, value=p.insured_name if p else "").font = money_font
        row += 1
        ws.cell(row=row, column=1, value="Plan:").font = label_font
        ws.cell(row=row, column=2, value=f"{plan_info[1]} ({plan_info[0]}-Year Level)").font = money_font
        row += 2

        # Section 5: Accelerated Benefit Payment
        ws.cell(row=row, column=1, value="ACCELERATED BENEFIT PAYMENT").font = header_font
        row += 1
        ws.cell(row=row, column=1, value="Total Eligible Death Benefit:").font = label_font
        ws.cell(row=row, column=2, value=r.full_eligible_db).number_format = '$#,##0.00'
        row += 1
        ws.cell(row=row, column=1, value="An Actuarial Discount:").font = label_font
        ws.cell(row=row, column=2, value=-r.full_actuarial_discount).number_format = '($#,##0.00)'
        row += 1
        ws.cell(row=row, column=1, value="An Administrative Charge:").font = label_font
        ws.cell(row=row, column=2, value=-r.full_admin_fee).number_format = '($#,##0.00)'
        row += 1
        ws.cell(row=row, column=1, value="Any Policy Debt:").font = label_font
        ws.cell(row=row, column=2, value=0).number_format = '$#,##0.00'
        row += 1

        ws.cell(row=row, column=1, value="Total Accelerated Benefit Payment:").font = Font(bold=True, size=12)
        ws.cell(row=row, column=2, value=r.full_accel_benefit).number_format = '$#,##0.00'
        ws.cell(row=row, column=2).font = Font(bold=True, size=12)
        row += 2

        ws.cell(row=row, column=1, value="Premium Before:").font = label_font
        ws.cell(row=row, column=2, value=r.premium_before).font = money_font
        row += 1
        ws.cell(row=row, column=1, value="Premium After:").font = label_font
        ws.cell(row=row, column=2, value=f"${r.premium_after_full:,.2f}").font = money_font
        row += 1
        ws.cell(row=row, column=1, value="Benefit Ratio:").font = label_font
        ws.cell(row=row, column=2, value=r.full_benefit_ratio).number_format = '0.00%'

        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['B'].width = 20

        # ── Sheet 2: Output - Max Partial ───────────────────────────────
        ws2 = wb.create_sheet("Output - Max Partial")

        row = 1
        ws2.cell(row=row, column=1, value="ABR QUOTE — MAX PARTIAL ACCELERATION").font = header_font
        row += 2
        ws2.cell(row=row, column=1, value="Policy Number:").font = label_font
        ws2.cell(row=row, column=2, value=p.policy_number if p else "").font = money_font
        row += 2

        ws2.cell(row=row, column=1, value="ACCELERATED BENEFIT PAYMENT").font = header_font
        row += 1
        ws2.cell(row=row, column=1, value="Total Eligible Death Benefit:").font = label_font
        ws2.cell(row=row, column=2, value=r.partial_eligible_db).number_format = '$#,##0.00'
        row += 1
        ws2.cell(row=row, column=1, value="An Actuarial Discount:").font = label_font
        ws2.cell(row=row, column=2, value=-r.partial_actuarial_discount).number_format = '($#,##0.00)'
        row += 1
        ws2.cell(row=row, column=1, value="An Administrative Charge:").font = label_font
        ws2.cell(row=row, column=2, value=-r.partial_admin_fee).number_format = '($#,##0.00)'
        row += 1

        ws2.cell(row=row, column=1, value="Total Accelerated Benefit Payment:").font = Font(bold=True, size=12)
        ws2.cell(row=row, column=2, value=r.partial_accel_benefit).number_format = '$#,##0.00'
        ws2.cell(row=row, column=2).font = Font(bold=True, size=12)
        row += 2

        ws2.cell(row=row, column=1, value="Premium After (Partial):").font = label_font
        ws2.cell(row=row, column=2, value=r.premium_after_partial).font = money_font
        row += 1
        ws2.cell(row=row, column=1, value="Benefit Ratio:").font = label_font
        ws2.cell(row=row, column=2, value=r.partial_benefit_ratio).number_format = '0.00%'

        ws2.column_dimensions['A'].width = 35
        ws2.column_dimensions['B'].width = 20

        wb.save(filepath)

    def _on_copy(self):
        """Copy summary text to clipboard."""
        if self._result is None:
            return

        r = self._result
        p = self._policy

        lines = [
            "ABR QUOTE SUMMARY",
            f"Policy: {p.policy_number if p else 'N/A'}",
            f"Insured: {p.insured_name if p else 'N/A'}",
            "",
            "FULL ACCELERATION:",
            f"  Eligible DB:        {self._fmt_money(r.full_eligible_db)}",
            f"  Actuarial Discount: {self._fmt_money(r.full_actuarial_discount)}",
            f"  Admin Fee:          {self._fmt_money(r.full_admin_fee)}",
            f"  Accel. Benefit:     {self._fmt_money(r.full_accel_benefit)}",
            f"  Benefit Ratio:      {r.full_benefit_ratio * 100:.2f}%",
            "",
            "MAX PARTIAL ACCELERATION:",
            f"  Eligible DB:        {self._fmt_money(r.partial_eligible_db)}",
            f"  Actuarial Discount: {self._fmt_money(r.partial_actuarial_discount)}",
            f"  Admin Fee:          {self._fmt_money(r.partial_admin_fee)}",
            f"  Accel. Benefit:     {self._fmt_money(r.partial_accel_benefit)}",
            f"  Benefit Ratio:      {r.partial_benefit_ratio * 100:.2f}%",
            "",
            f"Premium Before:  {r.premium_before}",
            f"Premium After (Full):    ${r.premium_after_full:,.2f}",
            f"Premium After (Partial): {r.premium_after_partial}",
        ]

        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(lines))
        self.messages_label.setText("Summary copied to clipboard.")
