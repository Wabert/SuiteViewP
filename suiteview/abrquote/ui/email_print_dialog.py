"""
ABR Quote — Email Print Dialog.

Shows the ABR quote summary and a manageable list of email recipients
side-by-side.  Recipients are persisted in the local SQLite database
(abr_email_recipients table).
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QMimeData
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox,
    QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QAbstractItemView,
    QWidget,
)
from PyQt6.QtGui import QGuiApplication

from ..models.abr_data import ABRPolicyData, ABRQuoteResult, MedicalAssessment
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
        assessment: Optional[MedicalAssessment] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._policy = policy
        self._result = result
        self._assessment = assessment
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
            ("Quote Date:", "quote_date"),
            ("Policy Number:", "policy_number"),
            ("Product:", "product"),
            ("Acceleration:", "acceleration"),
            ("", ""),
            ("Issue Age:", "issue_age"),
            ("Issue Date:", "issue_date"),
            ("Time in Force:", "time_in_force"),
            ("", ""),
            ("Attained Age:", "attained_age"),
            ("5 Yr. Survival Rate:", "survival_5yr"),
            ("10 Yr. Survival Rate:", "survival_10yr"),
            ("Life Expectancy in Years:", "life_expectancy"),
            ("Substandard to achieve mortality:", "substandard"),
            ("", ""),
            ("Full Acceleration Benefit:", "full_accel_benefit"),
            ("Benefit Ratio (Accl Ben/Full DB):", "full_benefit_ratio"),
            ("Reinsurers:", "reinsurers"),
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

        self._email_group = email_group
        self._email_group.setVisible(False)
        columns.addWidget(email_group, 2)

        main_layout.addLayout(columns, 1)

        # ── Footer buttons ──────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(10)

        copy_btn = QPushButton("📋  Copy to Clipboard")
        copy_btn.setStyleSheet(BUTTON_PRIMARY_STYLE)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(self._on_copy_to_clipboard)
        footer.addWidget(copy_btn)

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
        a = self._assessment

        if r:
            self._set("quote_date", r.quote_date.strftime("%m/%d/%Y") if r.quote_date else "—")

        if p:
            self._set("policy_number", p.policy_number)
            self._set("issue_age", str(p.issue_age))
            self._set("issue_date", p.issue_date.strftime("%m/%d/%Y") if p.issue_date else "—")
            self._set("attained_age", str(p.attained_age))

            # Time in force from policy year/month
            total_months = (p.policy_year - 1) * 12 + p.policy_month
            years = total_months // 12
            months = total_months % 12
            if years and months:
                self._set("time_in_force", f"{years} years, {months} months")
            elif years:
                self._set("time_in_force", f"{years} years")
            else:
                self._set("time_in_force", f"{months} months")

        if r:
            self._set("product", r.plan_description or p.plan_code if p else "—")
            self._set("full_accel_benefit", self._fmt(r.full_accel_benefit))
            self._set("full_benefit_ratio", f"{r.full_benefit_ratio * 100:.2f}%")

        if a:
            self._set("acceleration", a.rider_type)
            self._set("survival_5yr", f"{a.five_year_survival * 100:.1f}%")
            self._set("survival_10yr", f"{a.ten_year_survival * 100:.1f}%")
            self._set("life_expectancy", f"{a.life_expectancy_years:.1f}")
            sub_parts = []
            if a.use_five_year and a.use_ten_year and (a.derived_table_rating_5yr > 0 or a.derived_table_rating_10yr > 0):
                # Dual solve — show both table rating periods
                if a.derived_table_rating_5yr > 0:
                    sub_parts.append(f"Table {int(round(a.derived_table_rating_5yr))} (yrs 1-5)")
                if a.derived_table_rating_10yr > 0:
                    sub_parts.append(f"Table {int(round(a.derived_table_rating_10yr))} (yrs 6-10)")
            elif a.derived_table_rating > 0:
                sub_parts.append(f"Table {int(round(a.derived_table_rating))}")
            if a.use_increased_decrement and a.direct_increased_decrement > 0:
                sub_parts.append(f"ID {a.direct_increased_decrement:.0f}% (yr {a.incr_decrement_start_year}-{a.incr_decrement_stop_year})")
            self._set("substandard", "  |  ".join(sub_parts) if sub_parts else "None")

        self._set("reinsurers", "none")

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

    # ── Copy to Clipboard ───────────────────────────────────────────────

    def _on_copy_to_clipboard(self):
        """Copy the quote summary as HTML + plain text to the clipboard."""
        sections = self._build_summary_sections()
        html = self._build_clipboard_html(sections)
        plain = self._build_clipboard_text(sections)

        mime = QMimeData()
        mime.setHtml(html)
        mime.setText(plain)
        QGuiApplication.clipboard().setMimeData(mime)
        QMessageBox.information(self, "Copied", "ABR Quote Summary copied to clipboard.")

    def _build_summary_sections(self) -> list[tuple[str, list[tuple[str, str]]]]:
        """Collect label/value pairs grouped by titled section."""
        p = self._policy
        r = self._result
        a = self._assessment

        sections: list[tuple[str, list[tuple[str, str]]]] = []

        sec1: list[tuple[str, str]] = []
        if r:
            sec1.append(("Quote Date:", r.quote_date.strftime("%m/%d/%Y") if r.quote_date else "—"))
        if p:
            sec1.append(("Policy Number:", p.policy_number))
        if r:
            sec1.append(("Product:", r.plan_description or (p.plan_code if p else "—")))
        if a:
            sec1.append(("Acceleration:", a.rider_type))
        if sec1:
            sections.append(("Policy", sec1))

        if p:
            sec2: list[tuple[str, str]] = []
            sec2.append(("Issue Age:", str(p.issue_age)))
            sec2.append(("Issue Date:", p.issue_date.strftime("%m/%d/%Y") if p.issue_date else "—"))
            total_months = (p.policy_year - 1) * 12 + p.policy_month
            yrs, mos = total_months // 12, total_months % 12
            if yrs and mos:
                tif = f"{yrs} years, {mos} months"
            elif yrs:
                tif = f"{yrs} years"
            else:
                tif = f"{mos} months"
            sec2.append(("Time in Force:", tif))
            sections.append(("Coverage", sec2))

        sec3: list[tuple[str, str]] = []
        if p:
            sec3.append(("Attained Age:", str(p.attained_age)))
        if a:
            sec3.append(("5 Yr. Survival Rate:", f"{a.computed_survival_5yr * 100:.1f}%"))
            sec3.append(("10 Yr. Survival Rate:", f"{a.computed_survival_10yr * 100:.1f}%"))
            sec3.append(("Life Expectancy in Years:", f"{a.computed_le:.1f}"))
            if a.rider_type == "Terminal":
                sec3.append(("Substandard to achieve mortality:", "50% mortality each year"))
            else:
                sub_parts = []
                if a.use_five_year and a.use_ten_year and (a.derived_table_rating_5yr > 0 or a.derived_table_rating_10yr > 0):
                    # Dual solve — show both table rating periods
                    if a.derived_table_rating_5yr > 0:
                        sub_parts.append(f"Table {int(round(a.derived_table_rating_5yr))} (yrs 1-5)")
                    if a.derived_table_rating_10yr > 0:
                        sub_parts.append(f"Table {int(round(a.derived_table_rating_10yr))} (yrs 6-10)")
                elif a.derived_table_rating > 0:
                    sub_parts.append(f"Table {int(round(a.derived_table_rating))}")
                if a.use_increased_decrement and a.direct_increased_decrement > 0:
                    sub_parts.append(f"ID {a.direct_increased_decrement:.0f}% (yr {a.incr_decrement_start_year}-{a.incr_decrement_stop_year})")
                sec3.append(("Substandard to achieve mortality:", "  |  ".join(sub_parts) if sub_parts else "None"))
        if sec3:
            sections.append(("Assessment", sec3))

        sec4: list[tuple[str, str]] = []
        if r:
            sec4.append(("Full Acceleration Benefit:", self._fmt(r.full_accel_benefit)))
            sec4.append(("Benefit Ratio (Accl Ben/Full DB):", f"{r.full_benefit_ratio * 100:.2f}%"))
        sec4.append(("Reinsurers:", "none"))
        if sec4:
            sections.append(("Result", sec4))

        return sections

    def _build_clipboard_html(self, sections: list[tuple[str, list[tuple[str, str]]]]) -> str:
        """Build HTML table for pasting into Outlook / email clients."""
        # Crimson palette
        hdr_bg = "#5C0A14"
        hdr_fg = "#FFFFFF"
        sec_bg = "#F2E6E8"
        sec_fg = "#5C0A14"
        label_fg = "#4A5568"
        value_fg = "#1A202C"
        border_c = "#D4A0A8"

        html = (
            '<html><head><meta charset="utf-8"></head><body>'
            '<table style="border-collapse:collapse; font-family:Calibri,Arial,sans-serif;'
            f' font-size:11pt; border:1px solid {border_c}; min-width:420px;">'
            f'<tr><td colspan="2" style="background:{hdr_bg}; color:{hdr_fg};'
            ' font-weight:bold; font-size:13pt; padding:8px 12px;">ABR Quote Summary</td></tr>'
        )
        for title, pairs in sections:
            # Section header row
            html += (
                f'<tr><td colspan="2" style="background:{sec_bg}; color:{sec_fg};'
                f' font-weight:bold; font-size:10pt; padding:5px 12px;'
                f' border-top:1px solid {border_c}; border-bottom:1px solid {border_c};">{title}</td></tr>'
            )
            for lbl, val in pairs:
                html += (
                    f'<tr>'
                    f'<td style="padding:3px 12px; color:{label_fg}; white-space:nowrap;'
                    f' border-bottom:1px solid #EDF2F7;">{lbl}</td>'
                    f'<td style="padding:3px 12px; font-weight:bold; color:{value_fg};'
                    f' text-align:right; white-space:nowrap;'
                    f' border-bottom:1px solid #EDF2F7;">{val}</td>'
                    f'</tr>'
                )
        html += '</table></body></html>'
        return html

    def _build_clipboard_text(self, sections: list[tuple[str, list[tuple[str, str]]]]) -> str:
        """Build plain-text fallback for non-HTML targets (Notepad, etc.)."""
        all_pairs = [pair for _, pairs in sections for pair in pairs]
        label_w = max((len(lbl) for lbl, _ in all_pairs), default=0)
        value_w = max((len(val) for _, val in all_pairs), default=0)
        total_w = label_w + value_w + 4

        lines: list[str] = []
        lines.append("ABR Quote Summary")
        lines.append("=" * total_w)

        for title, pairs in sections:
            lines.append("")
            if title:
                lines.append(f"— {title} —")
            for lbl, val in pairs:
                lines.append(f"  {lbl:<{label_w}}  {val:>{value_w}}")

        return "\n".join(lines)
