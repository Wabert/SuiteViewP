"""
ABR Quote — Email Print Dialog.

Shows the ABR quote summary and a manageable list of email recipients
side-by-side.  Recipients are persisted in the local SQLite database
(abr_email_recipients table).
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QFrame,
    QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QAbstractItemView,
    QWidget,
)
from PyQt6.QtGui import QFont, QTextDocument
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

from ..models.abr_data import ABRPolicyData, ABRQuoteResult
from .abr_styles import (
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_RICH, CRIMSON_BG, CRIMSON_SUBTLE,
    CRIMSON_LIGHT, CRIMSON_SCROLL,
    SLATE_PRIMARY, SLATE_DARK, SLATE_TEXT, SLATE_LIGHT,
    WHITE, GRAY_DARK, GRAY_MID, GRAY_TEXT, GRAY_LIGHT,
    GROUP_BOX_STYLE, BUTTON_PRIMARY_STYLE, BUTTON_SLATE_STYLE,
    BUTTON_NAV_STYLE, INPUT_STYLE, DIVIDER_STYLE,
)

logger = logging.getLogger(__name__)


def _get_db():
    """Get the local SuiteView SQLite database."""
    from suiteview.data.database import get_database
    return get_database()


class EmailPrintDialog(QDialog):
    """Dialog showing ABR quote summary and email recipient management."""

    def __init__(
        self,
        policy: Optional[ABRPolicyData] = None,
        result: Optional[ABRQuoteResult] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._policy = policy
        self._result = result
        self.setWindowTitle("Email Print — ABR Quote")
        self.setMinimumSize(880, 560)
        self.resize(920, 600)
        self.setStyleSheet(f"QDialog {{ background-color: {CRIMSON_BG}; }}")

        self._build_ui()
        self._populate_summary()
        self._load_recipients()

    # ── UI Construction ─────────────────────────────────────────────────

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # ── Two-column layout: Summary (left) | Email Recipients (right) ─
        columns = QHBoxLayout()
        columns.setSpacing(10)

        # ── LEFT: Quote Summary ─────────────────────────────────────────
        summary_group = QGroupBox("ABR Quote Summary")
        summary_group.setStyleSheet(GROUP_BOX_STYLE)
        sg = QGridLayout(summary_group)
        sg.setContentsMargins(10, 16, 10, 6)
        sg.setSpacing(3)

        self._summary_labels = {}
        fields = [
            ("Policy Number:", "policy_number"),
            ("Insured:", "insured_name"),
            ("Plan Code:", "plan_code"),
            ("Quote Date:", "quote_date"),
            ("ABR Interest Rate:", "interest_rate"),
            ("", ""),
            ("— Full Acceleration —", ""),
            ("  Eligible Death Benefit:", "full_eligible_db"),
            ("  Actuarial Discount:", "full_actuarial_discount"),
            ("  Administrative Fee:", "full_admin_fee"),
            ("  Accelerated Benefit:", "full_accel_benefit"),
            ("  Benefit Ratio:", "full_benefit_ratio"),
            ("", ""),
            ("— Max Partial Acceleration —", ""),
            ("  Eligible Death Benefit:", "partial_eligible_db"),
            ("  Actuarial Discount:", "partial_actuarial_discount"),
            ("  Administrative Fee:", "partial_admin_fee"),
            ("  Accelerated Benefit:", "partial_accel_benefit"),
            ("  Benefit Ratio:", "partial_benefit_ratio"),
            ("", ""),
            ("— Premium Impact —", ""),
            ("  Premium Before:", "premium_before"),
            ("  After (Full Accel):", "premium_after_full"),
            ("  After (Partial):", "premium_after_partial"),
        ]

        row = 0
        for label_text, key in fields:
            if not label_text and not key:
                spacer = QLabel("")
                spacer.setFixedHeight(3)
                sg.addWidget(spacer, row, 0, 1, 2)
                row += 1
                continue

            if not key:
                header = QLabel(label_text)
                header.setStyleSheet(
                    f"font-size: 11px; font-weight: bold; color: {CRIMSON_DARK}; "
                    f"background: transparent; padding-top: 1px;"
                )
                sg.addWidget(header, row, 0, 1, 2)
                row += 1
                continue

            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 11px; color: {GRAY_DARK}; background: transparent;")
            sg.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignRight)

            val = QLabel("—")
            val.setStyleSheet(
                f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold; background: transparent;"
            )
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            sg.addWidget(val, row, 1, Qt.AlignmentFlag.AlignLeft)
            self._summary_labels[key] = val
            row += 1

        sg.setColumnStretch(2, 1)
        columns.addWidget(summary_group, 3)

        # ── RIGHT: Email Recipients ─────────────────────────────────────
        email_group = QGroupBox("Email Recipients")
        email_group.setStyleSheet(GROUP_BOX_STYLE)
        eg = QVBoxLayout(email_group)
        eg.setContentsMargins(10, 16, 10, 6)
        eg.setSpacing(4)

        self.email_list = QListWidget()
        self.email_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.email_list.setStyleSheet(f"""
            QListWidget {{
                font-size: 11px;
                border: 1px solid {CRIMSON_PRIMARY};
                border-radius: 4px;
                background-color: {WHITE};
                outline: none;
            }}
            QListWidget::item {{
                padding: 1px 6px;
                margin: 0px;
            }}
            QListWidget::item:selected {{
                background-color: {SLATE_LIGHT};
                color: {CRIMSON_DARK};
            }}
            QListWidget::item:hover {{
                background-color: {CRIMSON_SUBTLE};
            }}
        """)
        self.email_list.setSpacing(0)
        eg.addWidget(self.email_list, 1)

        # ── Email input (full width) ────────────────────────────────────
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Type email address…")
        self.email_input.setStyleSheet(INPUT_STYLE)
        self.email_input.returnPressed.connect(self._on_add_email)
        eg.addWidget(self.email_input)

        # ── Add / Remove buttons ────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        add_btn = QPushButton("✚ Add")
        add_btn.setStyleSheet(BUTTON_SLATE_STYLE)
        add_btn.setFixedWidth(80)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_email)
        btn_row.addWidget(add_btn)

        remove_btn = QPushButton("✕ Remove")
        remove_btn.setStyleSheet(BUTTON_NAV_STYLE)
        remove_btn.setFixedWidth(90)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(self._on_remove_email)
        btn_row.addWidget(remove_btn)

        btn_row.addStretch()
        eg.addLayout(btn_row)

        columns.addWidget(email_group, 2)

        main_layout.addLayout(columns, 1)

        # ── Footer buttons ──────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(10)

        print_btn = QPushButton("🖨  Print")
        print_btn.setStyleSheet(BUTTON_PRIMARY_STYLE)
        print_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        print_btn.clicked.connect(self._on_print)
        footer.addWidget(print_btn)

        footer.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(BUTTON_NAV_STYLE)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)

        main_layout.addLayout(footer)

    # ── Populate Summary ────────────────────────────────────────────────

    def _populate_summary(self):
        p = self._policy
        r = self._result

        if p:
            self._set("policy_number", p.policy_number)
            self._set("insured_name", p.insured_name)
            self._set("plan_code", p.plan_code)

        if r:
            self._set("quote_date", r.quote_date.strftime("%m/%d/%Y") if r.quote_date else "—")
            self._set("interest_rate", f"{r.abr_interest_rate * 100:.4f}%")

            self._set("full_eligible_db", self._fmt(r.full_eligible_db))
            self._set("full_actuarial_discount", self._fmt(r.full_actuarial_discount))
            self._set("full_admin_fee", self._fmt(r.full_admin_fee))
            self._set("full_accel_benefit", self._fmt(r.full_accel_benefit))
            self._set("full_benefit_ratio", f"{r.full_benefit_ratio * 100:.2f}%")

            self._set("partial_eligible_db", self._fmt(r.partial_eligible_db))
            self._set("partial_actuarial_discount", self._fmt(r.partial_actuarial_discount))
            self._set("partial_admin_fee", self._fmt(r.partial_admin_fee))
            self._set("partial_accel_benefit", self._fmt(r.partial_accel_benefit))
            self._set("partial_benefit_ratio", f"{r.partial_benefit_ratio * 100:.2f}%")

            self._set("premium_before", r.premium_before)
            self._set("premium_after_full", f"${r.premium_after_full:,.2f}")
            self._set("premium_after_partial", r.premium_after_partial)

    def _set(self, key: str, value: str):
        if key in self._summary_labels:
            self._summary_labels[key].setText(value)

    @staticmethod
    def _fmt(amount: float) -> str:
        if amount < 0:
            return f"(${abs(amount):,.2f})"
        return f"${amount:,.2f}"

    # ── Email Recipients ────────────────────────────────────────────────

    def _load_recipients(self):
        """Load email recipients from the database and refresh the list."""
        self.email_list.clear()
        db = _get_db()
        rows = db.fetchall(
            "SELECT id, email, display_name, organization FROM abr_email_recipients ORDER BY display_name"
        )
        for row in rows:
            display = f"{row['display_name']}  <{row['email']}>" if row['display_name'] else row['email']
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            self.email_list.addItem(item)

    def _on_add_email(self):
        raw = self.email_input.text().strip()
        if not raw:
            return

        email = raw
        display_name = ""

        if "@" not in email:
            QMessageBox.warning(self, "Invalid Email", "Please enter a valid email address.")
            return

        # Auto-detect organization from email domain
        domain = email.split("@", 1)[1] if "@" in email else ""
        organization = domain.split(".")[0] if domain else ""

        # Try to infer display name from email (First.Last@...)
        local_part = email.split("@")[0]
        if "." in local_part:
            parts = local_part.split(".")
            display_name = " ".join(p.capitalize() for p in parts)

        db = _get_db()
        try:
            db.execute(
                "INSERT INTO abr_email_recipients (email, display_name, organization) VALUES (?, ?, ?)",
                (email, display_name, organization),
            )
        except Exception as e:
            if "UNIQUE" in str(e).upper():
                QMessageBox.information(self, "Duplicate", f"{email} is already in the list.")
            else:
                QMessageBox.warning(self, "Error", str(e))
            return

        self.email_input.clear()
        self._load_recipients()

    def _on_remove_email(self):
        selected = self.email_list.selectedItems()
        if not selected:
            return

        # Confirmation dialog
        count = len(selected)
        names = ", ".join(item.text().split("<")[0].strip() or item.text() for item in selected[:3])
        if count > 3:
            names += f" and {count - 3} more"
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove {count} recipient{'s' if count > 1 else ''} from the list?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        db = _get_db()
        for item in selected:
            rid = item.data(Qt.ItemDataRole.UserRole)
            db.execute("DELETE FROM abr_email_recipients WHERE id = ?", (rid,))

        self._load_recipients()

    # ── Print ───────────────────────────────────────────────────────────

    def _on_print(self):
        """Print the quote summary with recipient list using native print dialog."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        doc = QTextDocument()
        doc.setHtml(self._build_print_html())
        doc.print(printer)

    def _build_print_html(self) -> str:
        """Build HTML content for printing."""
        p = self._policy
        r = self._result

        html = """
        <html>
        <head>
        <style>
            body { font-family: Arial, sans-serif; font-size: 11pt; }
            h1 { color: #5C0A14; font-size: 16pt; margin-bottom: 4px; }
            h2 { color: #8B1A2A; font-size: 13pt; margin-top: 14px; margin-bottom: 4px; }
            table { border-collapse: collapse; width: 100%; margin-bottom: 8px; }
            td { padding: 2px 8px; font-size: 10pt; }
            td.label { text-align: right; color: #4A5568; width: 55%; }
            td.value { font-weight: bold; color: #2D3748; }
            .recipients { margin-top: 12px; }
            .recipients li { font-size: 10pt; padding: 1px 0; }
        </style>
        </head>
        <body>
        <h1>ABR Quote Summary</h1>
        """

        if p:
            html += f"""
            <table>
                <tr><td class="label">Policy Number:</td><td class="value">{p.policy_number}</td></tr>
                <tr><td class="label">Insured:</td><td class="value">{p.insured_name}</td></tr>
                <tr><td class="label">Plan Code:</td><td class="value">{p.plan_code}</td></tr>
            </table>
            """

        if r:
            qd = r.quote_date.strftime("%m/%d/%Y") if r.quote_date else "—"
            html += f"""
            <table>
                <tr><td class="label">Quote Date:</td><td class="value">{qd}</td></tr>
                <tr><td class="label">ABR Interest Rate:</td><td class="value">{r.abr_interest_rate * 100:.4f}%</td></tr>
            </table>

            <h2>Full Acceleration</h2>
            <table>
                <tr><td class="label">Eligible Death Benefit:</td><td class="value">{self._fmt(r.full_eligible_db)}</td></tr>
                <tr><td class="label">Actuarial Discount:</td><td class="value">{self._fmt(r.full_actuarial_discount)}</td></tr>
                <tr><td class="label">Administrative Fee:</td><td class="value">{self._fmt(r.full_admin_fee)}</td></tr>
                <tr><td class="label">Accelerated Benefit:</td><td class="value">{self._fmt(r.full_accel_benefit)}</td></tr>
                <tr><td class="label">Benefit Ratio:</td><td class="value">{r.full_benefit_ratio * 100:.2f}%</td></tr>
            </table>

            <h2>Max Partial Acceleration</h2>
            <table>
                <tr><td class="label">Eligible Death Benefit:</td><td class="value">{self._fmt(r.partial_eligible_db)}</td></tr>
                <tr><td class="label">Actuarial Discount:</td><td class="value">{self._fmt(r.partial_actuarial_discount)}</td></tr>
                <tr><td class="label">Administrative Fee:</td><td class="value">{self._fmt(r.partial_admin_fee)}</td></tr>
                <tr><td class="label">Accelerated Benefit:</td><td class="value">{self._fmt(r.partial_accel_benefit)}</td></tr>
                <tr><td class="label">Benefit Ratio:</td><td class="value">{r.partial_benefit_ratio * 100:.2f}%</td></tr>
            </table>

            <h2>Premium Impact</h2>
            <table>
                <tr><td class="label">Premium Before:</td><td class="value">{r.premium_before}</td></tr>
                <tr><td class="label">After (Full Accel):</td><td class="value">${r.premium_after_full:,.2f}</td></tr>
                <tr><td class="label">After (Partial):</td><td class="value">{r.premium_after_partial}</td></tr>
            </table>
            """

        # Recipients
        db = _get_db()
        rows = db.fetchall(
            "SELECT email, display_name FROM abr_email_recipients ORDER BY display_name"
        )
        if rows:
            html += "<h2>Distribution List</h2><ul class='recipients'>"
            for row in rows:
                name = row['display_name'] or ""
                email = row['email']
                html += f"<li>{name}  &lt;{email}&gt;</li>" if name else f"<li>{email}</li>"
            html += "</ul>"

        html += "</body></html>"
        return html
