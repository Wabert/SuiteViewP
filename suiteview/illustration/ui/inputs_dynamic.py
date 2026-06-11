"""Dynamic Illustration "Input" tab — year/age driven transaction rows.

The interaction model users know from vendor illustration systems: one row of
controls per request, a ＋ at the bottom of each section to add another, a −
on every row but the first to remove it. Year and Age stay in sync both ways
(anniversary-aligned), as do For Years and To Age. Rows clamp to the
forecast-year/maturity bounds and may leave gaps but never overlap.

Sections:
  - Premiums / Loans / Withdrawals / Loan Repayments:
        Type | Year | Age | Amount | Mode | For Years | To Age
  - Face Amount / DB Option:  Type | Year | Age | New value
  - Rate Class / Table Rating: Year | Age | Current | New
  - Riders & Benefits: one button per active rider/benefit (premium-paying
    enabled); keep / change / drop with an effective year — adjusted buttons
    recolor.

Everything exports through ``collect_into(input_set, ...)`` so the engine
consumes the same ``IllustrationInputSet`` as the grid inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from dateutil.relativedelta import relativedelta
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator, QIntValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    PolicyChangeEvent,
    PolicyChangeKind,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.polview.ui.formatting import format_amount, format_date

from .styles import GROUP_STYLE, PURPLE_DARK

_MODE_INTERVALS = {"M": 1, "Q": 3, "S": 6, "A": 12}
_RATE_CLASSES = [
    ("R", "Pref+ NS"), ("P", "Pref NS"), ("T", "Std+ NS"),
    ("N", "NS"), ("Q", "Pref S"), ("S", "Smoker"),
]

_EDIT_STYLE = (
    "QLineEdit { background: white; color: #2A1458; border: 1px solid #B79CDE;"
    " border-radius: 3px; padding: 1px 4px; min-height: 18px; font-size: 11px; }"
    "QLineEdit:disabled { background: #E8DDF8; color: #7A6B91; }"
    "QLineEdit[invalid=\"true\"] { border: 1px solid #C62828; background: #FDECEA; }"
)
_COMBO_STYLE = (
    "QComboBox { background: white; color: #2A1458; border: 1px solid #B79CDE;"
    " border-radius: 3px; padding: 1px 4px; min-height: 18px; font-size: 11px; }"
    "QComboBox:disabled { background: #E8DDF8; color: #7A6B91; }"
    "QComboBox::drop-down { border-left: 1px solid #B79CDE; width: 14px; }"
)
_SMALL_BTN_STYLE = (
    "QPushButton { background: #F3ECFC; color: #4B2383; border: 1px solid #7E57C2;"
    " border-radius: 9px; min-width: 18px; max-width: 18px; min-height: 18px;"
    " max-height: 18px; font-size: 12px; font-weight: bold; padding: 0; }"
    "QPushButton:hover { background: #E6DAF8; }"
)
_CAPTION_STYLE = (
    f"color: {PURPLE_DARK}; background: transparent; font-size: 9px; font-weight: bold;"
)


@dataclass
class PolicyContext:
    """Everything the dynamic rows need to default and bound themselves."""

    issue_date: Optional[date] = None
    issue_age: int = 0
    forecast_year: int = 1        # policy year containing the first forecast month
    forecast_age: int = 0         # anniversary age at the start of that year
    maturity_age: int = 121
    default_mode: str = "M"
    modal_premium: float = 0.0
    rate_class: str = ""          # Cov 1
    table_rating: int = 0         # Cov 1
    suspended: bool = False
    valuation_date: Optional[date] = None

    @property
    def maturity_year(self) -> int:
        return max(1, self.maturity_age - self.issue_age)

    def age_for_year(self, year: int) -> int:
        return self.issue_age + year - 1

    def year_for_age(self, age: int) -> int:
        return age - self.issue_age + 1

    def anniversary(self, year: int) -> Optional[date]:
        if self.issue_date is None:
            return None
        return self.issue_date + relativedelta(years=year - 1)


def context_from_policy(policy) -> PolicyContext:
    """Build the row context from a loaded PolicyInformation."""
    issue_date = getattr(policy, "issue_date", None) or getattr(policy, "base_issue_date", None)
    issue_age = int(getattr(policy, "base_issue_age", None) or getattr(policy, "issue_age", 0) or 0)
    valuation = getattr(policy, "valuation_date", None) or getattr(policy, "last_valuation_date", None)
    forecast = valuation + relativedelta(months=1) if valuation else None
    if issue_date is not None and forecast is not None:
        months = (forecast.year - issue_date.year) * 12 + (forecast.month - issue_date.month)
        if forecast.day < issue_date.day:
            months -= 1
        forecast_year = max(1, months // 12 + 1)
    else:
        forecast_year = int(getattr(policy, "policy_year", 1) or 1)
    maturity_age = int(getattr(policy, "maturity_age", None)
                       or getattr(policy, "age_at_maturity", None) or 121)
    frequency = getattr(policy, "billing_frequency", 1)
    try:
        frequency = int(frequency)
    except (TypeError, ValueError):
        frequency = 1
    mode = {3: "Q", 6: "S", 12: "A"}.get(frequency, "M")
    status_code = str(getattr(policy, "status_code", "") or "")
    table_rating = getattr(policy, "base_table_rating", None)
    if table_rating is None:
        getter = getattr(policy, "cov_table_rating", None)
        if callable(getter):
            try:
                table_rating = getter(1)
            except Exception:
                table_rating = 0
    try:
        table_rating = int(table_rating or 0)
    except (TypeError, ValueError):
        table_rating = 0
    return PolicyContext(
        issue_date=issue_date,
        issue_age=issue_age,
        forecast_year=forecast_year,
        forecast_age=issue_age + forecast_year - 1,
        maturity_age=maturity_age,
        default_mode=mode,
        modal_premium=float(getattr(policy, "modal_premium", 0.0) or 0.0),
        rate_class=str(getattr(policy, "base_rate_class", "") or getattr(policy, "rate_class", "") or ""),
        table_rating=table_rating,
        suspended=status_code == "2",
        valuation_date=valuation,
    )


class _Field(QLineEdit):
    """Tight numeric field with an invalid state."""

    def __init__(self, width: int = 52, decimals: int = 0, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_EDIT_STYLE)
        self.setFixedWidth(width)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if decimals:
            self.setValidator(QDoubleValidator(0.0, 1e9, decimals, self))
        else:
            self.setValidator(QIntValidator(0, 9999, self))

    def value(self) -> Optional[float]:
        text = (self.text() or "").replace(",", "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def set_value(self, value: Optional[float], decimals: int = 0):
        if value is None:
            self.setText("")
        elif decimals:
            self.setText(f"{value:,.{decimals}f}")
        else:
            self.setText(str(int(value)))

    def set_invalid(self, invalid: bool, reason: str = ""):
        self.setProperty("invalid", "true" if invalid else "false")
        self.setToolTip(reason if invalid else "")
        self.style().unpolish(self)
        self.style().polish(self)


class InputRow(QWidget):
    """One dynamic request row. Emits changed() after any edit."""

    changed = pyqtSignal()
    remove_requested = pyqtSignal(object)

    def __init__(self, section: "DynamicSection", removable: bool, parent=None):
        super().__init__(parent)
        self._section = section
        self._ctx: Optional[PolicyContext] = None
        self._syncing = False
        spec = section.spec

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.type_combo = QComboBox(self)
        self.type_combo.addItems(["Input", "Solve"])
        # Solve comes later — visible so users learn it exists, but disabled.
        model_item = self.type_combo.model().item(1)
        if model_item is not None:
            model_item.setEnabled(False)
        self.type_combo.setStyleSheet(_COMBO_STYLE)
        self.type_combo.setFixedWidth(64)
        layout.addWidget(self.type_combo)

        self.year_edit = _Field(46)
        self.year_edit.editingFinished.connect(self._year_edited)
        layout.addWidget(self.year_edit)

        self.age_edit = _Field(46)
        self.age_edit.editingFinished.connect(self._age_edited)
        layout.addWidget(self.age_edit)

        self.value_combo: Optional[QComboBox] = None
        self.amount_edit: Optional[_Field] = None
        if spec.value_options is not None:
            self.value_combo = QComboBox(self)
            for code, label in spec.value_options:
                self.value_combo.addItem(label, code)
            self.value_combo.setStyleSheet(_COMBO_STYLE)
            self.value_combo.setFixedWidth(spec.value_width)
            self.value_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            layout.addWidget(self.value_combo)
        else:
            self.amount_edit = _Field(spec.value_width, decimals=2)
            self.amount_edit.editingFinished.connect(lambda: self.changed.emit())
            layout.addWidget(self.amount_edit)

        self.mode_combo: Optional[QComboBox] = None
        self.for_years_edit: Optional[_Field] = None
        self.to_age_edit: Optional[_Field] = None
        if spec.has_span:
            self.mode_combo = QComboBox(self)
            self.mode_combo.addItems(["M", "Q", "S", "A"])
            self.mode_combo.setStyleSheet(_COMBO_STYLE)
            self.mode_combo.setFixedWidth(44)
            self.mode_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            layout.addWidget(self.mode_combo)

            self.for_years_edit = _Field(52)
            self.for_years_edit.editingFinished.connect(self._for_years_edited)
            layout.addWidget(self.for_years_edit)

            self.to_age_edit = _Field(52)
            self.to_age_edit.editingFinished.connect(self._to_age_edited)
            layout.addWidget(self.to_age_edit)

        self.remove_btn = QPushButton("−")
        self.remove_btn.setStyleSheet(_SMALL_BTN_STYLE)
        self.remove_btn.setToolTip("Remove this row")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        self.remove_btn.setVisible(removable)
        layout.addWidget(self.remove_btn)
        layout.addStretch(1)

    # ── sync handlers ─────────────────────────────────────────

    def set_context(self, ctx: PolicyContext):
        self._ctx = ctx

    def _clamp_year(self, year: float) -> int:
        ctx = self._ctx
        if ctx is None:
            return int(year)
        return int(min(max(year, ctx.forecast_year), ctx.maturity_year))

    def _year_edited(self):
        if self._syncing or self._ctx is None:
            return
        self._syncing = True
        try:
            year = self.year_edit.value()
            if year is not None:
                year = self._clamp_year(year)
                self.year_edit.set_value(year)
                self.age_edit.set_value(self._ctx.age_for_year(year))
                self._resync_span(int(year))
        finally:
            self._syncing = False
        self.changed.emit()

    def _age_edited(self):
        if self._syncing or self._ctx is None:
            return
        self._syncing = True
        try:
            age = self.age_edit.value()
            if age is not None:
                year = self._clamp_year(self._ctx.year_for_age(int(age)))
                self.year_edit.set_value(year)
                self.age_edit.set_value(self._ctx.age_for_year(year))
                self._resync_span(year)
        finally:
            self._syncing = False
        self.changed.emit()

    def _resync_span(self, year: int):
        """Keep To Age consistent when the start year moves (For Years wins)."""
        if self.for_years_edit is None or self._ctx is None:
            return
        for_years = self.for_years_edit.value()
        if for_years is not None:
            self._set_span_from_years(year, int(for_years))

    def _set_span_from_years(self, year: int, for_years: int):
        ctx = self._ctx
        max_years = ctx.maturity_year - year + 1
        for_years = max(1, min(for_years, max_years))
        self.for_years_edit.set_value(for_years)
        self.to_age_edit.set_value(ctx.age_for_year(year) + for_years)

    def _for_years_edited(self):
        if self._syncing or self._ctx is None:
            return
        year = self.year_edit.value()
        for_years = self.for_years_edit.value()
        if year is None or for_years is None:
            self.changed.emit()
            return
        self._syncing = True
        try:
            self._set_span_from_years(int(year), int(for_years))
        finally:
            self._syncing = False
        self.changed.emit()

    def _to_age_edited(self):
        if self._syncing or self._ctx is None:
            return
        year = self.year_edit.value()
        to_age = self.to_age_edit.value()
        if year is None or to_age is None:
            self.changed.emit()
            return
        self._syncing = True
        try:
            start_age = self._ctx.age_for_year(int(year))
            to_age = int(min(max(to_age, start_age + 1), self._ctx.maturity_age))
            self._set_span_from_years(int(year), int(to_age - start_age))
        finally:
            self._syncing = False
        self.changed.emit()

    # ── values ────────────────────────────────────────────────

    def year(self) -> Optional[int]:
        value = self.year_edit.value()
        return int(value) if value is not None else None

    def end_year(self) -> Optional[int]:
        year = self.year()
        if year is None:
            return None
        if self.for_years_edit is None:
            return year
        for_years = self.for_years_edit.value()
        return year + int(for_years) - 1 if for_years else year

    def amount(self) -> Optional[float]:
        return self.amount_edit.value() if self.amount_edit is not None else None

    def chosen_value(self) -> Optional[str]:
        if self.value_combo is None:
            return None
        return self.value_combo.currentData()

    def mode(self) -> str:
        return self.mode_combo.currentText() if self.mode_combo is not None else "A"

    def is_filled(self) -> bool:
        if self.year() is None:
            return False
        if self.amount_edit is not None:
            return self.amount() is not None
        return bool(self.chosen_value())

    def set_overlap(self, overlapping: bool):
        self.year_edit.set_invalid(overlapping, "Overlaps another row — adjust the years.")
        if self.to_age_edit is not None:
            self.to_age_edit.set_invalid(overlapping, "Overlaps another row — adjust the years.")


@dataclass
class SectionSpec:
    title: str
    has_span: bool = True
    value_caption: str = "Amount"
    value_width: int = 84
    value_options: Optional[list] = None       # [(code, label)] -> combo instead of amount
    default_first_row: bool = False            # premium defaults from the policy


class DynamicSection(QGroupBox):
    """One request section with dynamic rows and a ＋ to add more."""

    changed = pyqtSignal()

    def __init__(self, spec: SectionSpec, parent=None):
        super().__init__(spec.title, parent)
        self.spec = spec
        self.setStyleSheet(GROUP_STYLE)
        self._ctx: Optional[PolicyContext] = None
        self._rows: list[InputRow] = []
        self._has_overlap = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 14, 6, 6)
        outer.setSpacing(2)

        captions = QHBoxLayout()
        captions.setContentsMargins(0, 0, 0, 0)
        captions.setSpacing(4)
        widths = [64, 46, 46, spec.value_width]
        labels = ["Type", "Year", "Age", spec.value_caption]
        if spec.has_span:
            widths += [44, 52, 52]
            labels += ["Mode", "For Years", "To Age"]
        for text, width in zip(labels, widths):
            caption = QLabel(text)
            caption.setStyleSheet(_CAPTION_STYLE)
            caption.setFixedWidth(width)
            captions.addWidget(caption)
        captions.addStretch(1)
        outer.addLayout(captions)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        outer.addLayout(self._rows_layout)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 2, 0, 0)
        self.add_btn = QPushButton("＋")
        self.add_btn.setStyleSheet(_SMALL_BTN_STYLE)
        self.add_btn.setToolTip("Add another row")
        self.add_btn.clicked.connect(lambda: self.add_row())
        footer.addWidget(self.add_btn)
        self.warning = QLabel("Rows overlap — later rows must start after earlier rows end.")
        self.warning.setStyleSheet(
            "color: #C62828; background: transparent; font-size: 10px; font-weight: bold;")
        self.warning.setVisible(False)
        footer.addWidget(self.warning)
        footer.addStretch(1)
        outer.addLayout(footer)

        self.add_row(removable=False)

    def add_row(self, removable: bool = True) -> InputRow:
        row = InputRow(self, removable, self)
        if self._ctx is not None:
            row.set_context(self._ctx)
        row.changed.connect(self._validate)
        row.remove_requested.connect(self._remove_row)
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        return row

    def _remove_row(self, row: InputRow):
        if row in self._rows and len(self._rows) > 1:
            self._rows.remove(row)
            row.setParent(None)
            row.deleteLater()
            self._validate()

    def rows(self) -> list[InputRow]:
        return self._rows

    def set_context(self, ctx: PolicyContext):
        self._ctx = ctx
        # Reset to a single fresh row per policy load.
        while len(self._rows) > 1:
            self._remove_row(self._rows[-1])
        first = self._rows[0]
        first.set_context(ctx)
        for widget in (first.year_edit, first.age_edit):
            widget.setText("")
        if first.amount_edit is not None:
            first.amount_edit.setText("")
        if first.for_years_edit is not None:
            first.for_years_edit.setText("")
            first.to_age_edit.setText("")
        if self.spec.default_first_row:
            first.year_edit.set_value(ctx.forecast_year)
            first.age_edit.set_value(ctx.forecast_age)
            if first.mode_combo is not None:
                first.mode_combo.setCurrentText(ctx.default_mode)
            if first.for_years_edit is not None:
                for_years = ctx.maturity_year - ctx.forecast_year + 1
                first.for_years_edit.set_value(for_years)
                first.to_age_edit.set_value(ctx.maturity_age)
            if first.amount_edit is not None and ctx.modal_premium:
                first.amount_edit.set_value(ctx.modal_premium, decimals=2)
        self._validate()

    def _validate(self):
        """Overlap check: sort filled rows; ranges may gap but not intersect."""
        filled = [(row.year(), row.end_year(), row) for row in self._rows if row.year() is not None]
        filled.sort(key=lambda entry: entry[0])
        overlapped: set = set()
        for (start_a, end_a, row_a), (start_b, end_b, row_b) in zip(filled, filled[1:]):
            if end_a is not None and start_b is not None and start_b <= end_a:
                overlapped.add(row_a)
                overlapped.add(row_b)
        for row in self._rows:
            row.set_overlap(row in overlapped)
        self._has_overlap = bool(overlapped)
        self.warning.setVisible(self._has_overlap)
        self.changed.emit()

    def has_overlap(self) -> bool:
        return self._has_overlap

    def entries(self) -> list[dict]:
        """Valid, filled rows sorted by year."""
        if self.has_overlap():
            return []
        out = []
        for row in self._rows:
            if not row.is_filled():
                continue
            out.append({
                "year": row.year(),
                "end_year": row.end_year(),
                "amount": row.amount(),
                "value": row.chosen_value(),
                "mode": row.mode(),
            })
        out.sort(key=lambda e: e["year"])
        return out


class RiderAdjustment:
    KEEP = "keep"
    CHANGE = "change"
    DROP = "drop"

    def __init__(self):
        self.action = self.KEEP
        self.new_amount: Optional[float] = None
        self.effective_year: Optional[int] = None


class RiderButtonsPanel(QGroupBox):
    """Buttons for the policy's active riders/benefits with keep/change/drop."""

    changed = pyqtSignal()

    _BTN = (
        "QPushButton {{ background: {bg}; color: {fg}; border: 1px solid {border};"
        " border-radius: 4px; padding: 3px 10px; font-size: 11px; font-weight: bold; }}"
        "QPushButton:disabled {{ background: #EDE7F6; color: #A89BC0; border: 1px dashed #C9BBE2; }}"
        "QPushButton:hover:enabled {{ background: #E6DAF8; }}"
    )

    def __init__(self, parent=None):
        super().__init__("Riders && Benefits", parent)
        self.setStyleSheet(GROUP_STYLE)
        self._ctx: Optional[PolicyContext] = None
        self._items: list[tuple] = []          # (key, label, detail_rows, premium_paying)
        self._adjustments: dict[str, RiderAdjustment] = {}
        self._buttons: dict[str, QPushButton] = {}
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 16, 8, 8)
        self._layout.setSpacing(6)
        self._note = QLabel("Load a policy to see its riders and benefits.")
        self._note.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 10px; font-style: italic;")
        self._layout.addWidget(self._note)
        self._layout.addStretch(1)

    def set_policy(self, policy, ctx: PolicyContext):
        self._ctx = ctx
        self._items = []
        self._adjustments = {}
        for index in reversed(range(self._layout.count())):
            item = self._layout.takeAt(index)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._buttons = {}

        coverages = []
        benefits = []
        try:
            coverages = [c for c in (policy.get_coverages() or []) if c.cov_pha_nbr != 1]
        except Exception:
            pass
        try:
            benefits = list(policy.get_benefits() or [])
        except Exception:
            pass

        for cov in coverages:
            label = cov.form_number or cov.plancode or f"Coverage {cov.cov_pha_nbr}"
            premium_paying = bool(getattr(cov, "rate", None) or getattr(cov, "annual_premium", None))
            rows = [
                ("Phase:", cov.cov_pha_nbr), ("Form:", cov.form_number),
                ("Plancode:", cov.plancode), ("Issue Date:", format_date(cov.issue_date)),
                ("Amount:", format_amount(cov.face_amount)), ("Issue Age:", cov.issue_age),
                ("Class:", cov.rate_class), ("Status:", cov.cov_status),
            ]
            amount = float(getattr(cov, "face_amount", 0.0) or 0.0)
            self._items.append((f"cov:{cov.cov_pha_nbr}", label, rows, premium_paying, amount))
        for ben in benefits:
            label = ben.form_number or ben.benefit_code or f"Benefit {ben.cov_pha_nbr}"
            benefit_type = str(getattr(ben, "benefit_type_cd", "") or "")
            premium_paying = bool(getattr(ben, "coi_rate", None)) and not benefit_type.startswith("#")
            rows = [
                ("Code:", ben.benefit_code), ("Type:", ben.benefit_type_cd),
                ("Description:", ben.benefit_desc), ("Issue Date:", format_date(ben.issue_date)),
                ("Cease Date:", format_date(ben.cease_date)), ("Units:", format_amount(ben.units)),
                ("Amount:", format_amount(ben.benefit_amount)), ("Issue Age:", ben.issue_age),
            ]
            amount = float(getattr(ben, "benefit_amount", 0.0) or 0.0)
            key = f"ben:{benefit_type}{getattr(ben, 'benefit_subtype_cd', '') or ''}:{ben.cov_pha_nbr}"
            self._items.append((key, label, rows, premium_paying, amount))

        if not self._items:
            note = QLabel("No riders or benefits on this policy.")
            note.setStyleSheet(
                f"color: {PURPLE_DARK}; background: transparent; font-size: 10px; font-style: italic;")
            self._layout.addWidget(note)
        for key, label, rows, premium_paying, amount in self._items:
            self._adjustments[key] = RiderAdjustment()
            btn = QPushButton(label)
            btn.setEnabled(premium_paying)
            btn.setToolTip(
                "Keep / change / drop this rider" if premium_paying
                else "Not premium-paying — no illustration adjustment")
            self._style_button(btn, RiderAdjustment.KEEP)
            btn.clicked.connect(
                lambda checked=False, k=key, l=label, r=rows, a=amount: self._open_dialog(k, l, r, a))
            self._buttons[key] = btn
            self._layout.addWidget(btn)
        self._layout.addStretch(1)

    def _style_button(self, btn: QPushButton, action: str):
        if action == RiderAdjustment.CHANGE:
            btn.setStyleSheet(self._BTN.format(bg="#FFF3D6", fg="#7B5E00", border="#D9B44A"))
        elif action == RiderAdjustment.DROP:
            btn.setStyleSheet(self._BTN.format(bg="#FBE4E4", fg="#8B1A2A", border="#C98989"))
        else:
            btn.setStyleSheet(self._BTN.format(bg="#F3ECFC", fg="#4B2383", border="#7E57C2"))

    def _open_dialog(self, key: str, label: str, rows: list, current_amount: float):
        ctx = self._ctx or PolicyContext()
        adj = self._adjustments[key]
        dlg = QDialog(self)
        dlg.setWindowTitle(label)
        dlg.setMinimumWidth(380)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(3)
        for row_index, (caption, value) in enumerate(rows):
            cap = QLabel(caption)
            cap.setStyleSheet(f"font-weight: bold; color: {PURPLE_DARK}; font-size: 11px;")
            val = QLabel("" if value is None else str(value))
            val.setStyleSheet("color: #2D3748; font-size: 11px;")
            grid.addWidget(cap, row_index, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(val, row_index, 1, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(grid)

        toggle_row = QHBoxLayout()
        group = QButtonGroup(dlg)
        keep_radio = QRadioButton("Keep rider")
        change_radio = QRadioButton("Change rider")
        drop_radio = QRadioButton("Drop rider")
        for radio in (keep_radio, change_radio, drop_radio):
            radio.setStyleSheet(
                f"QRadioButton {{ color: {PURPLE_DARK}; font-size: 11px; font-weight: bold; }}")
            group.addButton(radio)
            toggle_row.addWidget(radio)
        toggle_row.addStretch(1)
        layout.addLayout(toggle_row)

        detail_row = QHBoxLayout()
        amount_caption = QLabel("New amount:")
        amount_caption.setStyleSheet(_CAPTION_STYLE)
        amount_edit = _Field(86, decimals=2)
        year_caption = QLabel("Effective year:")
        year_caption.setStyleSheet(_CAPTION_STYLE)
        year_edit = _Field(50)
        age_caption = QLabel("Age:")
        age_caption.setStyleSheet(_CAPTION_STYLE)
        age_edit = _Field(46)
        for widget in (amount_caption, amount_edit, year_caption, year_edit, age_caption, age_edit):
            detail_row.addWidget(widget)
        detail_row.addStretch(1)
        layout.addLayout(detail_row)

        def sync_age_from_year():
            year = year_edit.value()
            if year is not None:
                year = int(min(max(year, ctx.forecast_year), ctx.maturity_year))
                year_edit.set_value(year)
                age_edit.set_value(ctx.age_for_year(year))

        def sync_year_from_age():
            age = age_edit.value()
            if age is not None:
                year = int(min(max(ctx.year_for_age(int(age)), ctx.forecast_year), ctx.maturity_year))
                year_edit.set_value(year)
                age_edit.set_value(ctx.age_for_year(year))

        year_edit.editingFinished.connect(sync_age_from_year)
        age_edit.editingFinished.connect(sync_year_from_age)

        def refresh_detail():
            changing = change_radio.isChecked()
            dropping = drop_radio.isChecked()
            for widget in (amount_caption, amount_edit):
                widget.setVisible(changing)
            for widget in (year_caption, year_edit, age_caption, age_edit):
                widget.setVisible(changing or dropping)
            if dropping:
                amount_edit.set_value(0, decimals=2)

        keep_radio.toggled.connect(refresh_detail)
        change_radio.toggled.connect(refresh_detail)
        drop_radio.toggled.connect(refresh_detail)

        {RiderAdjustment.KEEP: keep_radio,
         RiderAdjustment.CHANGE: change_radio,
         RiderAdjustment.DROP: drop_radio}[adj.action].setChecked(True)
        if adj.new_amount is not None:
            amount_edit.set_value(adj.new_amount, decimals=2)
        elif current_amount:
            amount_edit.set_value(current_amount, decimals=2)
        if adj.effective_year is not None:
            year_edit.set_value(adj.effective_year)
            age_edit.set_value(ctx.age_for_year(adj.effective_year))
        else:
            year_edit.set_value(ctx.forecast_year)
            age_edit.set_value(ctx.forecast_age)
        refresh_detail()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(self._BTN.format(bg="#F3ECFC", fg="#4B2383", border="#7E57C2"))
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dlg.exec()

        if drop_radio.isChecked():
            adj.action = RiderAdjustment.DROP
            adj.new_amount = 0.0
        elif change_radio.isChecked():
            adj.action = RiderAdjustment.CHANGE
            adj.new_amount = amount_edit.value()
        else:
            adj.action = RiderAdjustment.KEEP
            adj.new_amount = None
        year = year_edit.value()
        adj.effective_year = int(year) if year is not None else None
        self._style_button(self._buttons[key], adj.action)
        self.changed.emit()

    def collect_changes(self, ctx: PolicyContext) -> list[PolicyChangeEvent]:
        events: list[PolicyChangeEvent] = []
        for key, adj in self._adjustments.items():
            if adj.action == RiderAdjustment.KEEP or adj.effective_year is None:
                continue
            when = ctx.anniversary(adj.effective_year)
            if when is None:
                continue
            events.append(PolicyChangeEvent(
                kind=PolicyChangeKind.RIDER_DROP,
                effective_date=when,
                value=float(adj.new_amount or 0.0),
                metadata={"target": key, "action": adj.action},
            ))
        return events


class DynamicInputsPanel(QWidget):
    """The "Input" tab: suspended banner, request sections, rider buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx = PolicyContext()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        self.suspended_banner = QLabel("")
        self.suspended_banner.setWordWrap(True)
        self.suspended_banner.setStyleSheet(
            "color: #B00020; background-color: #FDECEA; border: 1px solid #C62828;"
            " border-radius: 4px; padding: 6px 10px; font-size: 11px; font-weight: bold;")
        self.suspended_banner.setVisible(False)
        outer.addWidget(self.suspended_banner)

        columns = QHBoxLayout()
        columns.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.premium_section = DynamicSection(SectionSpec(
            "Premiums", default_first_row=True))
        self.loan_section = DynamicSection(SectionSpec("Loans"))
        self.withdrawal_section = DynamicSection(SectionSpec("Withdrawals"))
        self.repayment_section = DynamicSection(SectionSpec("Loan Repayments"))
        for section in (self.premium_section, self.loan_section,
                        self.withdrawal_section, self.repayment_section):
            left.addWidget(section)
        left.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.face_section = DynamicSection(SectionSpec(
            "Face Amount Change", has_span=False, value_caption="New Face"))
        self.dbo_section = DynamicSection(SectionSpec(
            "Death Benefit Option Change", has_span=False, value_caption="New Option",
            value_width=170,
            value_options=[("A", "A — CV in Specified Amt"), ("B", "B — CV added to Specified Amt")]))
        self.rateclass_section = DynamicSection(SectionSpec(
            "Rate Class Change", has_span=False, value_caption="New Rate Class",
            value_width=120, value_options=[(c, f"{c} — {label}") for c, label in _RATE_CLASSES]))
        self.table_section = DynamicSection(SectionSpec(
            "Table Rating Change", has_span=False, value_caption="New Table",
            value_width=110,
            value_options=[("0", "0 — Standard")] + [
                (str(n), f"{n} — Table {chr(64 + n)}") for n in range(1, 17)]))
        self.current_class_label = QLabel("Current rate class: —")
        self.current_class_label.setStyleSheet(_CAPTION_STYLE)
        self.current_table_label = QLabel("Current table rating: —")
        self.current_table_label.setStyleSheet(_CAPTION_STYLE)
        right.addWidget(self.face_section)
        right.addWidget(self.dbo_section)
        right.addWidget(self.rateclass_section)
        right.addWidget(self.current_class_label)
        right.addWidget(self.table_section)
        right.addWidget(self.current_table_label)
        right.addStretch(1)

        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        outer.addLayout(columns, 1)

        self.riders_panel = RiderButtonsPanel(self)
        outer.addWidget(self.riders_panel)

    # ── loading ───────────────────────────────────────────────

    def load_from_policy(self, policy):
        self._ctx = context_from_policy(policy)
        for section in (self.premium_section, self.loan_section, self.withdrawal_section,
                        self.repayment_section, self.face_section, self.dbo_section,
                        self.rateclass_section, self.table_section):
            section.set_context(self._ctx)
        self.current_class_label.setText(
            f"Current rate class (Cov 1): {self._ctx.rate_class or '—'}")
        self.current_table_label.setText(
            f"Current table rating (Cov 1): {self._ctx.table_rating}")
        self.riders_panel.set_policy(policy, self._ctx)

        if self._ctx.suspended and self._ctx.valuation_date is not None:
            valuation = self._ctx.valuation_date
            forecast = valuation + relativedelta(months=1)
            self.suspended_banner.setText(
                f"POLICY IS SUSPENDED.  The illustration will still use current crediting "
                f"rates to illustrate from the last valuation date of "
                f"{valuation.strftime('%m/%d/%Y')}.  The forecast date remains one month "
                f"after that valuation date — {forecast.strftime('%m/%d/%Y')} — which is "
                f"in the past.")
            self.suspended_banner.setVisible(True)
        else:
            self.suspended_banner.setVisible(False)

    # ── export ────────────────────────────────────────────────

    def _expand_dated(self, entries: list[dict], kind: TransactionKind) -> list[DatedTransaction]:
        """Year/mode rows -> dated monthliversary transactions (the compiler
        only schedules premiums and loans by year)."""
        ctx = self._ctx
        out: list[DatedTransaction] = []
        for entry in entries:
            if not entry["amount"]:
                continue
            interval = _MODE_INTERVALS.get(entry["mode"], 12)
            for year in range(entry["year"], (entry["end_year"] or entry["year"]) + 1):
                anniversary = ctx.anniversary(year)
                if anniversary is None:
                    continue
                for month_offset in range(0, 12, interval):
                    out.append(DatedTransaction(
                        kind=kind,
                        effective_date=anniversary + relativedelta(months=month_offset),
                        amount=float(entry["amount"]),
                    ))
        return out

    def _scheduled(self, entries: list[dict], kind: TransactionKind,
                   metadata: Optional[dict] = None) -> list[ScheduledTransaction]:
        """Year rows -> year schedules, with explicit zero rows for the gaps
        (an engine schedule persists until the next entry)."""
        ctx = self._ctx
        out: list[ScheduledTransaction] = []
        previous_end: Optional[int] = None
        for entry in entries:
            if previous_end is not None and entry["year"] > previous_end + 1:
                out.append(ScheduledTransaction(
                    kind=kind, policy_year=previous_end + 1, amount=0.0, mode="A",
                    metadata=dict(metadata or {})))
            out.append(ScheduledTransaction(
                kind=kind, policy_year=entry["year"], amount=float(entry["amount"] or 0.0),
                mode=entry["mode"], metadata=dict(metadata or {})))
            previous_end = entry["end_year"] or entry["year"]
        if entries and previous_end is not None and previous_end < ctx.maturity_year:
            out.append(ScheduledTransaction(
                kind=kind, policy_year=previous_end + 1, amount=0.0, mode="A",
                metadata=dict(metadata or {})))
        return out

    def collect_into(self, input_set: IllustrationInputSet):
        ctx = self._ctx
        input_set.scheduled_transactions.extend(
            self._scheduled([e for e in self.premium_section.entries() if e["amount"] is not None],
                            TransactionKind.PREMIUM))
        input_set.scheduled_transactions.extend(
            self._scheduled([e for e in self.loan_section.entries() if e["amount"] is not None],
                            TransactionKind.LOAN, metadata={"loan_type": "fixed"}))
        input_set.dated_transactions.extend(
            self._expand_dated(self.withdrawal_section.entries(), TransactionKind.WITHDRAWAL))
        input_set.dated_transactions.extend(
            self._expand_dated(self.repayment_section.entries(), TransactionKind.LOAN_REPAYMENT))

        for entry in self.face_section.entries():
            when = ctx.anniversary(entry["year"])
            if when is not None and entry["amount"]:
                input_set.policy_changes.append(PolicyChangeEvent(
                    kind=PolicyChangeKind.FACE_AMOUNT, effective_date=when,
                    value=float(entry["amount"])))
        for entry in self.dbo_section.entries():
            when = ctx.anniversary(entry["year"])
            if when is not None and entry["value"]:
                input_set.policy_changes.append(PolicyChangeEvent(
                    kind=PolicyChangeKind.DB_OPTION, effective_date=when,
                    value=entry["value"]))
        for entry in self.rateclass_section.entries():
            when = ctx.anniversary(entry["year"])
            if when is not None and entry["value"]:
                input_set.policy_changes.append(PolicyChangeEvent(
                    kind=PolicyChangeKind.RATE_CLASS, effective_date=when,
                    value=entry["value"]))
        for entry in self.table_section.entries():
            when = ctx.anniversary(entry["year"])
            if when is not None and entry["value"] is not None:
                input_set.policy_changes.append(PolicyChangeEvent(
                    kind=PolicyChangeKind.SUBSTANDARD, effective_date=when,
                    value=int(entry["value"])))
        input_set.policy_changes.extend(self.riders_panel.collect_changes(ctx))
