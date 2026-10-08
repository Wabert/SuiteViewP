"""Read-only UL reinstatement quote tab.

All financial values come from ``services.reinstatement``; this module only
lays them out. Lapse data and rates are loaded once per policy, so changing the
reinstatement date re-prices immediately without another database read.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ...services.reinstatement import (
    ReinstatementError,
    load_reinstatement_basis,
    reinstatement_eligibility,
)
from ..formatting import format_currency, format_date
from ..styles import (
    GOLD_DARK, GOLD_LIGHT, GRAY_DARK, GRAY_MID, GRAY_TEXT, GREEN_DARK, GREEN_PRIMARY,
    GREEN_SUBTLE, POLICY_INFO_FRAME_STYLE, WHITE,
)
from ..widgets import CopyableLabel
from .policy_support_config import _ACTION_BTN_STYLE

if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation

logger = logging.getLogger(__name__)

NOT_APPLICABLE = "N/A"
_ERROR_COLOR = "#B00020"

_LABEL_STYLE = f"font-size: 11px; color: {GRAY_DARK}; background: transparent; border: none;"
_VALUE_STYLE = f"font-size: 11px; color: {GRAY_DARK}; background: transparent; border: none;"
_TOTAL_LABEL_STYLE = (
    f"font-size: 11px; font-weight: bold; color: {GREEN_DARK}; background: transparent; border: none;")
_HINT_STYLE = f"font-size: 10px; color: {GRAY_TEXT}; background: transparent; border: none;"
_GRAND_STYLE = (
    f"font-size: 13px; font-weight: bold; color: {GREEN_DARK}; background: {GOLD_LIGHT};"
    f"border: 1px solid {GOLD_DARK}; border-radius: 4px; padding: 4px 8px;")
_GRAND_TITLE_STYLE = (
    f"font-size: 13px; font-weight: bold; color: {GREEN_DARK}; background: transparent; border: none;")
_COMBO_STYLE = f"""
    QComboBox {{
        background: {WHITE}; color: {GRAY_DARK};
        border: 1px solid {GRAY_MID}; border-radius: 3px;
        padding: 3px 6px; font-size: 11px; min-height: 18px;
    }}
    QComboBox:focus {{ border-color: {GREEN_PRIMARY}; }}
    QComboBox QAbstractItemView {{ background: {WHITE}; color: {GRAY_DARK}; selection-background-color: {GOLD_LIGHT}; selection-color: {GREEN_DARK}; }}
"""


def _rule(double: bool = False) -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(3 if double else 1)
    line.setStyleSheet(
        f"background: transparent; border: none; border-top: 1px solid {GREEN_PRIMARY};"
        + (f"border-bottom: 1px solid {GREEN_PRIMARY};" if double else ""))
    return line


class LedgerPanel(QGroupBox):
    """A titled two-column label/amount list with subtotal rules."""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(10, 18, 10, 8)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(3)
        self._grid.setColumnStretch(0, 1)
        self._row = 0
        self.values: dict[str, CopyableLabel] = {}
        self.labels: dict[str, QLabel] = {}
        self._copy_provider = None

    def add_row(self, key: str, label: str, *, total: bool = False, tooltip: str = "") -> CopyableLabel:
        name = QLabel(label)
        name.setStyleSheet(_TOTAL_LABEL_STYLE if total else _LABEL_STYLE)
        value = CopyableLabel("")
        value.setStyleSheet(_TOTAL_LABEL_STYLE if total else _VALUE_STYLE)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value.setMinimumWidth(90)
        value.set_copy_text_provider(lambda: self._copy_provider() if self._copy_provider else "")
        if tooltip:
            name.setToolTip(tooltip)
            value.setToolTip(tooltip)
        self._grid.addWidget(name, self._row, 0)
        self._grid.addWidget(value, self._row, 1)
        self.values[key] = value
        self.labels[key] = name
        self._row += 1
        return value

    def add_hint(self, text: str) -> QLabel:
        hint = QLabel(text)
        hint.setStyleSheet(_HINT_STYLE)
        hint.setWordWrap(True)
        self._grid.addWidget(hint, self._row, 0, 1, 2)
        self._row += 1
        return hint

    def add_rule(self, double: bool = False) -> None:
        self._grid.addWidget(_rule(double), self._row, 0, 1, 2)
        self._row += 1

    def add_control(self, label: str, widget: QWidget) -> None:
        name = QLabel(label)
        name.setStyleSheet(_LABEL_STYLE)
        self._grid.addWidget(name, self._row, 0)
        self._grid.addWidget(widget, self._row, 1)
        self._row += 1

    def add_widget(self, widget: QWidget) -> None:
        self._grid.addWidget(widget, self._row, 0, 1, 2)
        self._row += 1

    def finish(self) -> None:
        self._grid.setRowStretch(self._row, 1)

    def set_copy_provider(self, provider) -> None:
        self._copy_provider = provider

    def set(self, key: str, text: str) -> None:
        self.values[key].setText(text)

    def text(self, key: str) -> str:
        return self.values[key].text()

    def clear_values(self) -> None:
        for value in self.values.values():
            value.clear()


def _amount(value) -> str:
    return format_currency(value)


def _date_or_na(value) -> str:
    return format_date(value) if value is not None else NOT_APPLICABLE


class ReinstatementTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: PolicyInformation | None = None
        self._basis = None
        self._quote = None
        self.setStyleSheet(f"background-color: {WHITE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        layout.addWidget(self._build_header())

        panels = QHBoxLayout()
        panels.setSpacing(8)
        self.lapse_panel = self._build_lapse_panel()
        self.skipped_panel = self._build_skipped_panel()
        self.deduction_panel = self._build_deduction_panel()
        self.premium_panel = self._build_premium_panel()
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(self.lapse_panel)
        left.addWidget(self.skipped_panel)
        left.addStretch(1)
        panels.addLayout(left, 1)
        for panel in (self.lapse_panel, self.skipped_panel, self.deduction_panel, self.premium_panel):
            panel.set_copy_provider(self.copy_text)
            panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        panels.addWidget(self.deduction_panel, 1, Qt.AlignmentFlag.AlignTop)
        panels.addWidget(self.premium_panel, 1, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(panels)

        self.notes_label = QLabel()
        self.notes_label.setWordWrap(True)
        self.notes_label.setTextFormat(Qt.TextFormat.PlainText)
        self.notes_label.setStyleSheet(
            f"font-size: 10px; color: {GRAY_TEXT}; background: transparent; border: none;")
        layout.addWidget(self.notes_label)
        layout.addStretch(1)
        self.clear()

    # ── construction ────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("ReinstatementHeader")
        header.setStyleSheet(
            f"QFrame#ReinstatementHeader {{ background: {GREEN_SUBTLE};"
            f" border: 1px solid {GREEN_PRIMARY}; border-radius: 6px; }}")
        row = QHBoxLayout(header)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(8)
        self.entry_label = QLabel()
        self.entry_label.setStyleSheet(_TOTAL_LABEL_STYLE)
        row.addWidget(self.entry_label)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(self.status_label, 1)
        date_label = QLabel("Reinstatement date:")
        date_label.setStyleSheet(_TOTAL_LABEL_STYLE)
        row.addWidget(date_label)
        self.date_edit = QComboBox()
        self.date_edit.setStyleSheet(_COMBO_STYLE)
        self.date_edit.setMinimumWidth(110)
        self.date_edit.setToolTip("Monthliversaries from the last 6 months through the next month")
        self.date_edit.currentIndexChanged.connect(self._requote)
        row.addWidget(self.date_edit)
        self.calculate_button = QPushButton("Calculate")
        self.calculate_button.setStyleSheet(_ACTION_BTN_STYLE)
        self.calculate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.calculate_button.clicked.connect(self._requote)
        row.addWidget(self.calculate_button)
        return header

    def _build_lapse_panel(self) -> LedgerPanel:
        panel = LedgerPanel("Values at Lapse")
        panel.add_row("lapse_date", "Lapse date", tooltip="CyberLife TL (termination - lapse) transaction date")
        panel.add_row("values_date", "Values as of", tooltip="Last monthliversary values record")
        panel.add_rule()
        panel.add_row("account_value", "Account value")
        panel.add_row("loan_balance", "Loan balance")
        panel.add_row("surrender_charge", "Surrender charge")
        panel.add_rule()
        panel.add_row("snet_expiry", "SNET expiry date", tooltip="SafetyNet (MAP) cease date")
        panel.add_row("ccv_cease", "CCV benefit cease date")
        panel.finish()
        return panel

    def _build_skipped_panel(self) -> LedgerPanel:
        panel = LedgerPanel("Skipped Coverage Reinstatement")
        panel.add_hint("(this does not apply if you do a home office reinstatement)")
        panel.add_row("code", "Reinstatement code",
                      tooltip="Segment 66 reinstatement rule (LH_NON_TRD_POL.REN_RLE_CD). Rule 3 extends "
                              "the SNET expiry by the terminated months; any other rule ends SNET and CCV "
                              "at the termination date.")
        panel.add_rule()
        panel.add_row("values_date", "Values as of Reinstatement Date")
        panel.add_rule()
        panel.add_row("net_premium", "Reinstatement premium (net)",
                      tooltip="Reinstatement premium less the premium load")
        panel.add_row("monthly_deduction", "Approx monthly deduction",
                      tooltip="The monthly deduction on the reinstatement date")
        panel.add_row("account_value", "Approx account value (after MD)", total=True,
                      tooltip="Account value at lapse plus the net reinstatement premium, less one monthly deduction")
        panel.add_row("loan_balance", "Loan balance")
        panel.add_row("surrender_charge", "Surrender charge")
        panel.add_row("surrender_value", "Surrender value", total=True,
                      tooltip="Approx account value less surrender charge and loan balance")
        panel.add_rule()
        panel.add_row("snet_expiry", "SNET expiry date",
                      tooltip="Code 3: lapse SNET date plus the terminated months. Other codes: termination date")
        panel.add_row("ccv_cease", "CCV benefit cease date",
                      tooltip="The termination date when a CCV benefit exists")
        panel.add_row("terminated_months", "Terminated months")
        panel.finish()
        return panel

    def _build_deduction_panel(self) -> LedgerPanel:
        panel = LedgerPanel("Monthly Deduction")
        panel.add_row("deduction_date", "Monthly deduction date")
        panel.add_row("duration", "Policy year / month")
        panel.add_row("attained_age", "Attained age")
        panel.add_rule()
        panel.add_row("base_coi", "Base COI")
        panel.add_row("rider_coi", "Rider COI")
        panel.add_row("benefit_charges", "Benefit charges", tooltip="Benefit charges such as CCV and waivers")
        panel.add_row("coi_total", "COI", total=True)
        panel.add_rule()
        panel.add_row("epu", "Expense per unit (EPU)")
        panel.add_row("monthly_fee", "Monthly fee")
        panel.add_row("av_charge", "Account value charge")
        panel.add_row("fee_total", "Fees", total=True)
        panel.add_rule(double=True)
        panel.add_row("total", "Total monthly deduction", total=True)
        panel.finish()
        return panel

    def _build_premium_panel(self) -> LedgerPanel:
        panel = LedgerPanel("Reinstatement Premium")
        panel.add_row("account_value", "Account value")
        panel.add_row("policy_debt", "Policy debt")
        panel.add_row(
            "surrender_charge", "Surrender charge",
            tooltip="As of the reinstatement date, with durations from the policy issue date")
        panel.add_row("coi_x2", "2 \u00d7 COI", tooltip="Base, rider and benefit COI charges")
        panel.add_row("fees_x2", "2 \u00d7 Fees", tooltip="EPU, monthly fee and account value charge")
        panel.add_rule()
        panel.add_row("subtotal", "Subtotal", total=True)
        panel.add_hint("Surrender charge + policy debt + 2\u00d7COI + 2\u00d7fees \u2212 account value")
        panel.add_row("premium_load", "Premium load")
        panel.add_rule(double=True)
        self.premium_label = QLabel()
        self.premium_label.setStyleSheet(_GRAND_STYLE)
        grand = QWidget()
        grand.setStyleSheet("background: transparent;")
        grand_row = QHBoxLayout(grand)
        grand_row.setContentsMargins(0, 2, 0, 0)
        title = QLabel("Reinstatement Premium")
        title.setStyleSheet(_GRAND_TITLE_STYLE)
        grand_row.addWidget(title)
        grand_row.addStretch(1)
        grand_row.addWidget(self.premium_label)
        panel.add_widget(grand)
        panel.finish()
        return panel

    # ── state ───────────────────────────────────────────────────────────────

    def clear(self):
        self._policy = None
        self._basis = None
        self._quote = None
        self.entry_label.clear()
        self._set_status("Load a lapsed UL policy to quote reinstatement.")
        self._clear_values()
        self._set_date_enabled(False)

    def _clear_values(self, *, keep_lapse: bool = False):
        if not keep_lapse:
            self.lapse_panel.clear_values()
        self.deduction_panel.clear_values()
        self.skipped_panel.clear_values()
        self.premium_panel.clear_values()
        self.premium_label.clear()
        self.notes_label.clear()

    def _set_status(self, text: str, *, error: bool = False):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"font-size: 11px; color: {_ERROR_COLOR if error else GRAY_DARK};"
            "background: transparent; border: none;")

    def _set_date_enabled(self, enabled: bool):
        self.date_edit.setEnabled(enabled)
        self.calculate_button.setEnabled(enabled)

    def load_policy(self, policy: PolicyInformation, today: date | None = None):
        self.clear()
        self._policy = policy
        today = today or date.today()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            eligibility = reinstatement_eligibility(policy)
            self.entry_label.setText(
                f"Last entry: {eligibility.last_entry_code or '-'} - {eligibility.last_entry_description}")
            if not eligibility.eligible:
                self._set_status(eligibility.message, error=True)
                return
            self._set_status("Loading lapse values and rates...")
            self._basis = load_reinstatement_basis(policy, today=today)
        except ReinstatementError as exc:
            logger.warning("Reinstatement basis unavailable: %s", exc, exc_info=True)
            self._set_status(f"Unable to quote reinstatement: {exc}", error=True)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._show_lapse_values()
        default = self._basis.default_date
        self.date_edit.blockSignals(True)
        self.date_edit.clear()
        choices = self._basis.date_choices or (default,)
        for choice in choices:
            self.date_edit.addItem(format_date(choice, "%m/%d/%Y"), choice)
        self.date_edit.setCurrentIndex(choices.index(default) if default in choices else 0)
        self.date_edit.blockSignals(False)
        self._set_date_enabled(True)
        self._requote()

    def _show_lapse_values(self):
        lapse = self._basis.lapse
        panel = self.lapse_panel
        panel.set("lapse_date", format_date(lapse.lapse_date))
        panel.set("values_date", _date_or_na(lapse.values_date))
        panel.set("account_value", _amount(lapse.account_value))
        panel.set("loan_balance", _amount(lapse.loan_balance))
        panel.set("surrender_charge", _amount(lapse.surrender_charge))
        panel.set("snet_expiry", _date_or_na(lapse.snet_expiry_date))
        panel.set("ccv_cease", _date_or_na(lapse.ccv_cease_date) if lapse.has_ccv else NOT_APPLICABLE)

    def selected_date(self) -> date:
        return self.date_edit.currentData()

    def _requote(self, *_args):
        if self._basis is None or self.date_edit.currentData() is None:
            return
        self._quote = None
        self._clear_values(keep_lapse=True)
        when = self.selected_date()
        try:
            quote = self._basis.quote(when)
        except ReinstatementError as exc:
            logger.warning("Reinstatement quote unavailable: %s", exc, exc_info=True)
            self.premium_label.setText("Unavailable")
            self._set_status(f"Unable to quote reinstatement: {exc}", error=True)
            return
        self._show_quote(quote)
        self._quote = quote
        self._set_status(f"Lapsed {format_date(self._basis.lapse.lapse_date)}. "
                         f"Quote for reinstatement on {format_date(when)}.")

    def _show_quote(self, quote):
        d = quote.deduction
        panel = self.deduction_panel
        panel.set("deduction_date", format_date(d.deduction_date))
        panel.set("duration", f"{d.policy_year} / {d.policy_month}")
        panel.set("attained_age", str(d.attained_age))
        for key in ("base_coi", "rider_coi", "benefit_charges", "coi_total",
                    "epu", "monthly_fee", "av_charge", "fee_total", "total"):
            panel.set(key, _amount(getattr(d, key)))
        p = quote.premium
        panel = self.premium_panel
        for key in ("account_value", "policy_debt", "surrender_charge", "coi_x2", "fees_x2",
                    "subtotal", "premium_load"):
            panel.set(key, _amount(getattr(p, key)))
        panel.labels["premium_load"].setText(f"Premium load ({p.load_description})")
        self.premium_label.setText(format_currency(p.premium, prefix="$"))
        after = self._basis.values_after_reinstatement(quote)
        skipped = self.skipped_panel
        skipped.set("code", after.reinstatement_code or NOT_APPLICABLE)
        skipped.set("values_date", format_date(after.reinstatement_date))
        skipped.set("net_premium", _amount(after.net_premium))
        skipped.set("monthly_deduction", _amount(after.monthly_deduction))
        skipped.set("account_value", _amount(after.account_value))
        skipped.set("loan_balance", _amount(after.loan_balance))
        skipped.set("surrender_charge", _amount(after.surrender_charge))
        skipped.set("surrender_value", _amount(after.surrender_value))
        skipped.set("snet_expiry", _date_or_na(after.snet_expiry_date))
        skipped.set("ccv_cease", _date_or_na(after.ccv_cease_date))
        skipped.set("terminated_months", str(after.terminated_months))
        self.notes_label.setText("\n".join(f"\u2022 {note}" for note in quote.notes))

    def copy_text(self) -> str:
        """Plain-text quote for the clipboard (right-click Copy on any value)."""
        if self._basis is None:
            return ""
        lines = [f"UL Reinstatement Quote - {getattr(self._policy, 'policy_number', '')}".rstrip(" -")]
        sections = [("Values at Lapse", self.lapse_panel)]
        if self._quote is not None:
            sections += [("Skipped Coverage Reinstatement", self.skipped_panel),
                         ("Monthly Deduction", self.deduction_panel),
                         ("Reinstatement Premium", self.premium_panel)]
        for title, panel in sections:
            lines += ["", title]
            lines += [f"  {panel.labels[key].text()}: {panel.text(key)}" for key in panel.values]
        if self._quote is not None:
            lines.append(f"  Reinstatement premium: {self.premium_label.text()}")
            lines += ["", *(f"- {note}" for note in self._quote.notes)]
        return "\n".join(lines)
