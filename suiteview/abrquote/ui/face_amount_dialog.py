"""
ABR Quote — Face Amount to Accelerate Dialog.

Standalone dialog for entering a custom face amount with
full/partial acceleration recalculation and validation.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QGroupBox, QFrame,
    QMessageBox,
)

from ..models.abr_data import ABRPolicyData, ABRQuoteResult
from .abr_styles import (
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_RICH, CRIMSON_SUBTLE,
    SLATE_PRIMARY, SLATE_DARK,
    WHITE, GRAY_DARK, GRAY_MID, GRAY_TEXT,
    GROUP_BOX_STYLE, INPUT_STYLE,
    LABEL_MONEY_STYLE, LABEL_MONEY_LARGE_STYLE, DIVIDER_STYLE,
)


class FaceAmountDialog(QDialog):
    """Dialog for entering a custom face amount and viewing recalculated results."""

    def __init__(
        self,
        policy: ABRPolicyData,
        result: ABRQuoteResult,
        parent=None,
    ):
        super().__init__(parent)
        self._policy = policy
        self._result = result
        self.setWindowTitle("Face Amount to Accelerate")
        self.setMinimumWidth(520)
        self._build_ui()
        self._populate_results()

    # ── UI Construction ──────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # ── Face Amount to Accelerate row ───────────────────────────────
        face_row = QHBoxLayout()
        face_row.setSpacing(8)

        face_lbl = QLabel("Face Amount to Accelerate:")
        face_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {CRIMSON_DARK};"
        )
        face_row.addWidget(face_lbl)

        self._face_input = QLineEdit()
        self._face_input.setStyleSheet(INPUT_STYLE)
        self._face_input.setFixedWidth(160)
        self._face_input.setEnabled(False)
        face_row.addWidget(self._face_input)

        self._face_change_btn = QPushButton("Change")
        self._face_change_btn.setFixedWidth(90)
        self._face_change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._face_change_btn.setStyleSheet(f"""
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
        """)
        self._face_change_btn.clicked.connect(self._on_face_change_accept)
        face_row.addWidget(self._face_change_btn)
        face_row.addStretch()

        layout.addLayout(face_row)

        # ── Full / Partial Acceleration ─────────────────────────────────
        self._full_group = QGroupBox("Full Acceleration")
        self._full_group.setStyleSheet(GROUP_BOX_STYLE)
        full_grid = QGridLayout(self._full_group)
        full_grid.setContentsMargins(12, 16, 12, 8)
        full_grid.setSpacing(6)
        full_grid.setHorizontalSpacing(8)

        self._full_labels = {}
        for i, (label_text, key) in enumerate([
            ("Eligible Death Benefit:", "eligible_db"),
            ("Actuarial Discount:", "actuarial_discount"),
            ("Administrative Fee:", "admin_fee"),
        ]):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 12px; color: {GRAY_DARK};")
            full_grid.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignRight)
            val = QLabel("\u2014")
            val.setStyleSheet(f"font-size: 12px; color: {GRAY_DARK}; font-weight: bold;")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            full_grid.addWidget(val, i, 1, Qt.AlignmentFlag.AlignLeft)
            self._full_labels[key] = val

        divider = QFrame()
        divider.setStyleSheet(DIVIDER_STYLE)
        divider.setFixedHeight(2)
        full_grid.addWidget(divider, 3, 0, 1, 2)

        lbl_ab = QLabel("Accelerated Benefit:")
        lbl_ab.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {CRIMSON_DARK};"
        )
        full_grid.addWidget(lbl_ab, 4, 0, Qt.AlignmentFlag.AlignRight)

        self._full_benefit_label = QLabel("\u2014")
        self._full_benefit_label.setStyleSheet(LABEL_MONEY_LARGE_STYLE)
        full_grid.addWidget(self._full_benefit_label, 4, 1, Qt.AlignmentFlag.AlignLeft)

        lbl_br = QLabel("Benefit Ratio:")
        lbl_br.setStyleSheet(f"font-size: 11px; color: {GRAY_TEXT};")
        full_grid.addWidget(lbl_br, 5, 0, Qt.AlignmentFlag.AlignRight)
        self._full_ratio_label = QLabel("\u2014")
        self._full_ratio_label.setStyleSheet(
            f"font-size: 11px; color: {GRAY_TEXT}; font-weight: bold;"
        )
        full_grid.addWidget(self._full_ratio_label, 5, 1, Qt.AlignmentFlag.AlignLeft)

        # APV column
        vsep = QFrame()
        vsep.setFrameShape(QFrame.Shape.VLine)
        vsep.setStyleSheet(f"color: {GRAY_MID}; background: {GRAY_MID};")
        full_grid.addWidget(vsep, 0, 2, 6, 1)

        apv_lbl_style = f"font-size: 12px; color: {GRAY_DARK};"
        apv_val_style = f"font-size: 12px; color: {GRAY_DARK}; font-weight: bold;"
        self._full_apv_labels = {}
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
            self._full_apv_labels[apv_key] = val

        full_grid.setColumnStretch(1, 2)
        full_grid.setColumnStretch(4, 2)
        layout.addWidget(self._full_group)

        # ── Max Partial Acceleration ────────────────────────────────────
        self._partial_group = QGroupBox("Max Partial Acceleration")
        self._partial_group.setStyleSheet(GROUP_BOX_STYLE)
        partial_grid = QGridLayout(self._partial_group)
        partial_grid.setContentsMargins(12, 16, 12, 8)
        partial_grid.setSpacing(6)
        partial_grid.setHorizontalSpacing(8)

        self._partial_labels = {}
        self._partial_static_widgets = []
        for i, (label_text, key) in enumerate([
            ("Eligible Death Benefit:", "eligible_db"),
            ("Actuarial Discount:", "actuarial_discount"),
            ("Administrative Fee:", "admin_fee"),
        ]):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 12px; color: {GRAY_DARK};")
            partial_grid.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignRight)
            val = QLabel("\u2014")
            val.setStyleSheet(f"font-size: 12px; color: {GRAY_DARK}; font-weight: bold;")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            partial_grid.addWidget(val, i, 1, Qt.AlignmentFlag.AlignLeft)
            self._partial_labels[key] = val
            self._partial_static_widgets.append(lbl)

        divider2 = QFrame()
        divider2.setStyleSheet(DIVIDER_STYLE)
        divider2.setFixedHeight(2)
        partial_grid.addWidget(divider2, 3, 0, 1, 2)
        self._partial_static_widgets.append(divider2)

        lbl_pab = QLabel("Accelerated Benefit:")
        lbl_pab.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {CRIMSON_DARK};"
        )
        partial_grid.addWidget(lbl_pab, 4, 0, Qt.AlignmentFlag.AlignRight)
        self._partial_static_widgets.append(lbl_pab)

        self._partial_benefit_label = QLabel("\u2014")
        self._partial_benefit_label.setStyleSheet(LABEL_MONEY_LARGE_STYLE)
        partial_grid.addWidget(
            self._partial_benefit_label, 4, 1, Qt.AlignmentFlag.AlignLeft
        )

        lbl_pbr = QLabel("Benefit Ratio:")
        lbl_pbr.setStyleSheet(f"font-size: 11px; color: {GRAY_TEXT};")
        partial_grid.addWidget(lbl_pbr, 5, 0, Qt.AlignmentFlag.AlignRight)
        self._partial_static_widgets.append(lbl_pbr)
        self._partial_ratio_label = QLabel("\u2014")
        self._partial_ratio_label.setStyleSheet(
            f"font-size: 11px; color: {GRAY_TEXT}; font-weight: bold;"
        )
        partial_grid.addWidget(
            self._partial_ratio_label, 5, 1, Qt.AlignmentFlag.AlignLeft
        )

        # APV column
        vsep2 = QFrame()
        vsep2.setFrameShape(QFrame.Shape.VLine)
        vsep2.setStyleSheet(f"color: {GRAY_MID}; background: {GRAY_MID};")
        partial_grid.addWidget(vsep2, 0, 2, 6, 1)
        self._partial_static_widgets.append(vsep2)

        apv_lbl_style = f"font-size: 12px; color: {GRAY_DARK};"
        apv_val_style = f"font-size: 12px; color: {GRAY_DARK}; font-weight: bold;"
        self._partial_apv_labels = {}
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
            self._partial_apv_labels[apv_key] = val
            self._partial_static_widgets.append(lbl)

        # "Not allowed" overlay
        self._partial_not_allowed_label = QLabel(
            "MAX PARTIAL NOT ALLOWED\nPOLICY ALREADY AT MINIMUM FACE"
        )
        self._partial_not_allowed_label.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {CRIMSON_DARK}; padding: 16px;"
        )
        self._partial_not_allowed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._partial_not_allowed_label.setVisible(False)
        partial_grid.addWidget(self._partial_not_allowed_label, 0, 0, 6, 5)

        partial_grid.setColumnStretch(1, 2)
        partial_grid.setColumnStretch(4, 2)
        layout.addWidget(self._partial_group)

        # ── Premium Impact ──────────────────────────────────────────────
        self._premium_group = QGroupBox("Premium Impact")
        self._premium_group.setStyleSheet(GROUP_BOX_STYLE)
        prem_grid = QGridLayout(self._premium_group)
        prem_grid.setContentsMargins(12, 16, 12, 8)
        prem_grid.setSpacing(6)

        for i, label_text in enumerate([
            "Premium Before:", "After (Full Accel):", "After (Partial):"
        ]):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"font-size: 12px; font-weight: bold; color: {CRIMSON_DARK};"
            )
            prem_grid.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignRight)

        self._premium_before_label = QLabel("\u2014")
        self._premium_before_label.setStyleSheet(LABEL_MONEY_STYLE)
        prem_grid.addWidget(self._premium_before_label, 0, 1)

        self._premium_after_full_label = QLabel("\u2014")
        self._premium_after_full_label.setStyleSheet(LABEL_MONEY_STYLE)
        prem_grid.addWidget(self._premium_after_full_label, 1, 1)

        self._premium_after_partial_label = QLabel("\u2014")
        self._premium_after_partial_label.setStyleSheet(LABEL_MONEY_STYLE)
        prem_grid.addWidget(self._premium_after_partial_label, 2, 1)

        prem_grid.setColumnStretch(2, 1)
        layout.addWidget(self._premium_group)

        # ── Messages / Warnings area ────────────────────────────────────
        self._messages_label = QLabel("")
        self._messages_label.setWordWrap(True)
        self._messages_label.setStyleSheet(
            "color: #C62828; font-size: 13px; font-weight: bold; padding: 4px;"
        )
        layout.addWidget(self._messages_label)

        layout.addStretch()

    # ── Populate initial results ─────────────────────────────────────────

    def _populate_results(self):
        """Fill all fields from the stored policy + result."""
        r = self._result
        p = self._policy

        # Face input
        self._face_input.setText(f"${p.face_amount:,.2f}")

        # Full acceleration
        self._full_labels["eligible_db"].setText(self._fmt_money(r.full_eligible_db))
        self._full_labels["actuarial_discount"].setText(
            self._fmt_money(r.full_actuarial_discount)
        )
        self._full_labels["admin_fee"].setText(self._fmt_money(r.full_admin_fee))

        if r.full_accel_benefit < 0:
            self._full_benefit_label.setText(
                f"$0.00  (calc result: {self._fmt_money(r.full_accel_benefit)})"
            )
        else:
            self._full_benefit_label.setText(self._fmt_money(r.full_accel_benefit))
        self._full_ratio_label.setText(f"{r.full_benefit_ratio * 100:.2f}%")

        # Full APV
        self._full_apv_labels["apv_fb"].setText(self._fmt_money(r.apv_fb))
        self._full_apv_labels["apv_fp"].setText(self._fmt_money(r.apv_fp))
        self._full_apv_labels["apv_fd"].setText(self._fmt_money(r.apv_fd))

        # Partial acceleration
        at_min_face = r.partial_eligible_db <= 0
        self._partial_not_allowed_label.setVisible(at_min_face)
        for w in self._partial_static_widgets:
            w.setVisible(not at_min_face)
        for val in self._partial_labels.values():
            val.setVisible(not at_min_face)
        self._partial_benefit_label.setVisible(not at_min_face)
        self._partial_ratio_label.setVisible(not at_min_face)
        for val in self._partial_apv_labels.values():
            val.setVisible(not at_min_face)

        if not at_min_face:
            self._partial_labels["eligible_db"].setText(
                self._fmt_money(r.partial_eligible_db)
            )
            self._partial_labels["actuarial_discount"].setText(
                self._fmt_money(r.partial_actuarial_discount)
            )
            self._partial_labels["admin_fee"].setText(
                self._fmt_money(r.partial_admin_fee)
            )
            if r.partial_accel_benefit < 0:
                self._partial_benefit_label.setText(
                    f"$0.00  (calc result: {self._fmt_money(r.partial_accel_benefit)})"
                )
            else:
                self._partial_benefit_label.setText(
                    self._fmt_money(r.partial_accel_benefit)
                )
            self._partial_ratio_label.setText(
                f"{r.partial_benefit_ratio * 100:.2f}%"
            )

            # Partial APV (proportionally scaled)
            if r.full_eligible_db > 0:
                ratio = r.partial_eligible_db / r.full_eligible_db
            else:
                ratio = 0.0
            self._partial_apv_labels["apv_fb"].setText(
                self._fmt_money(r.apv_fb * ratio)
            )
            self._partial_apv_labels["apv_fp"].setText(
                self._fmt_money(r.apv_fp * ratio)
            )
            self._partial_apv_labels["apv_fd"].setText(
                self._fmt_money(r.apv_fd * ratio)
            )

        # Premium impact
        self._premium_before_label.setText(r.premium_before)
        self._premium_after_full_label.setText(f"${r.premium_after_full:,.2f}")
        if at_min_face:
            self._premium_after_partial_label.setText("NOT ALLOWED")
        else:
            self._premium_after_partial_label.setText(r.premium_after_partial)

        # Messages
        if r.messages:
            bullets = "\n\n".join(f"\u2022 {m}" for m in r.messages)
            self._messages_label.setText(bullets)

    # ── Face Amount Change / Accept ──────────────────────────────────────

    def _on_face_change_accept(self):
        if self._face_change_btn.text() == "Change":
            self._face_input.setEnabled(True)
            self._face_input.setFocus()
            self._face_input.selectAll()
            self._face_change_btn.setText("Accept")
        else:
            self._accept_face_amount()

    def _revert_face_input(self):
        face = self._policy.face_amount
        self._face_input.setText(f"${face:,.2f}")
        self._face_input.setEnabled(False)
        self._face_change_btn.setText("Change")

    def _accept_face_amount(self):
        raw = self._face_input.text().replace("$", "").replace(",", "").strip()
        try:
            custom_face = float(raw)
        except ValueError:
            QMessageBox.warning(
                self, "Invalid Amount",
                "Please enter a valid numeric face amount.",
            )
            self._revert_face_input()
            return

        total_face = self._policy.face_amount
        min_allowed = 10_000.0

        if custom_face > total_face:
            QMessageBox.warning(
                self, "Invalid Amount",
                f"Face amount cannot exceed the total policy face "
                f"of ${total_face:,.2f}.",
            )
            self._revert_face_input()
            return

        if custom_face < min_allowed:
            QMessageBox.warning(
                self, "Invalid Amount",
                f"Face amount cannot be less than the minimum "
                f"of ${min_allowed:,.2f}.",
            )
            self._revert_face_input()
            return

        max_partial_eligible = self._result.partial_eligible_db
        if (max_partial_eligible > 0
                and custom_face > max_partial_eligible
                and abs(custom_face - total_face) >= 0.01):
            QMessageBox.warning(
                self, "Invalid Amount",
                f"Accelerating this amount would drop the face below the "
                f"minimum. If you want to partial accelerate you must put "
                f"an amount less than or equal to ${max_partial_eligible:,.2f}.",
            )
            self._revert_face_input()
            return

        # Lock input
        self._face_input.setEnabled(False)
        self._face_input.setText(f"${custom_face:,.2f}")
        self._face_change_btn.setText("Change")

        # Determine full vs partial label
        is_full = abs(custom_face - total_face) < 0.01
        self._full_group.setTitle(
            "Full Acceleration" if is_full else "Partial Acceleration"
        )

        # Proportional recalculation
        result = self._result
        orig_eligible = result.full_eligible_db
        orig_discount = result.full_actuarial_discount
        admin_fee = result.full_admin_fee

        if orig_eligible > 0:
            ratio = custom_face / orig_eligible
            new_discount = round(orig_discount * ratio, 2)
        else:
            ratio = 0.0
            new_discount = 0.0

        new_benefit = round(custom_face - new_discount - admin_fee, 2)
        new_ratio = new_benefit / custom_face if custom_face > 0 else 0.0

        self._full_labels["eligible_db"].setText(self._fmt_money(custom_face))
        self._full_labels["actuarial_discount"].setText(
            self._fmt_money(new_discount)
        )
        self._full_labels["admin_fee"].setText(self._fmt_money(admin_fee))

        if new_benefit < 0:
            self._full_benefit_label.setText(
                f"$0.00  (calc result: {self._fmt_money(new_benefit)})"
            )
        else:
            self._full_benefit_label.setText(self._fmt_money(new_benefit))
        self._full_ratio_label.setText(f"{new_ratio * 100:.2f}%")

        # Update APV proportionally
        self._full_apv_labels["apv_fb"].setText(
            self._fmt_money(result.apv_fb * ratio)
        )
        self._full_apv_labels["apv_fp"].setText(
            self._fmt_money(result.apv_fp * ratio)
        )
        self._full_apv_labels["apv_fd"].setText(
            self._fmt_money(result.apv_fd * ratio)
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_money(amount: float) -> str:
        if amount < 0:
            return f"(${abs(amount):,.2f})"
        return f"${amount:,.2f}"
