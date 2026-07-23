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

from dataclasses import dataclass
from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta
from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator, QIntValidator
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models.app_settings import get_illustration_settings
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    PolicyChangeEvent,
    PolicyChangeKind,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.core.illustration_policy_service import coverage_or_benefit_matured
from suiteview.illustration.core.target_premium import floor_monthly_cent
from suiteview.illustration.models.index_strategies import (
    FIXED_FUND_ID,
    ag49_index_for_issue_date,
    current_ag49_index,
    is_iul_plan,
    load_index_strategies,
)
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.polview.ui.formatting import format_amount, format_date
from suiteview.ui.widgets.frameless_window import FramelessDialog

from .allocations_panel import AllocationsDialog, AllocationsPanel
from .styles import (
    GROUP_STYLE,
    ILLUSTRATION_BORDER_COLOR,
    ILLUSTRATION_HEADER_COLORS,
    INPUT_CAPTION_STYLE as _CAPTION_STYLE,
    INPUT_COMBO_STYLE as _COMBO_STYLE,
    INPUT_EDIT_STYLE as _EDIT_STYLE,
    INPUT_RADIO_STYLE as _RADIO_STYLE,
    INPUT_SMALL_BTN_STYLE as _SMALL_BTN_STYLE,
    PURPLE_BG,
    PURPLE_DARK,
    apply_input_checkbox_style,
)

_INDEX_ALLOC_BTN_STYLE = (
    "QPushButton { background-color: #F3ECFC; color: #4B2383;"
    " border: 1px solid #7E57C2; border-radius: 4px; padding: 2px 12px;"
    " font-size: 11px; font-weight: bold; }"
    "QPushButton:hover { background-color: #E8DDF8; }"
    "QPushButton:disabled { background-color: #ECE9F1; color: #9C8DB8;"
    " border: 1px solid #C9BBE2; }"
)

_MODE_INTERVALS = {"M": 1, "Q": 3, "S": 6, "A": 12}
_RATE_CLASSES = [
    ("R", "Pref+ NS"), ("P", "Pref NS"), ("T", "Std+ NS"),
    ("N", "NS"), ("Q", "Pref S"), ("S", "Smoker"),
]

# Shared editor/caption widths so the InputRow fields line up with the section
# caption row. Year/Age only ever hold a 2–3 digit number, so they stay narrow;
# the span (For Years/To Age) and Amount fields get the room instead.
_W_TYPE = 64
_W_YEAR = 36
_W_AGE = 36
_W_MODE = 48
_W_SPAN = 64
_W_BASIS = 60


def _first_float(source, *names: str) -> float:
    for name in names:
        value = getattr(source, name, None)
        if value is not None:
            return float(value or 0.0)
    return 0.0


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
    form_number: str = ""         # base coverage form (e.g. "UL501", "SPL87")
    max_level_premium_room: float = 0.0
    max_level_years: int = 0
    is_cvat: bool = False
    has_loans: bool = False       # policy carries a loan (informational)
    has_shadow: bool = False      # active shadow account (benefit type A) — gates exceptions
    shadow_ceased: bool = False   # policy HAD a type-A benefit but it has ceased
    rate_class: str = ""          # Cov 1
    table_rating: int = 0         # Cov 1
    illustrated_rate: float = 0.0
    plancode: str = ""
    is_iul: bool = False          # plan has an index-strategy row → allocation grid
    gint: float = 0.0             # plan guaranteed interest (guaranteed blend basis)
    premium_allocations: Optional[dict] = None  # inforce premium allocation % by fund ID
    sweep_account_min: float = 0.0  # sweep fund retained minimum (DB2 source TBD)
    suspended: bool = False
    valuation_date: Optional[date] = None

    forecast_date: Optional[date] = None  # valuation + 1 month (a monthliversary)

    @property
    def is_spl87(self) -> bool:
        """SPL87-form (single-premium) plan — a zero ongoing billable premium."""
        return self.form_number.strip().upper().startswith("SPL87")

    @property
    def billable_premium(self) -> float:
        """The policy's current billable premium — forced to 0 on SPL87 plans.
        Used for the 'Billable Prem' premium type and the default INPUT amount."""
        return 0.0 if self.is_spl87 else self.modal_premium

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

    def effective_date(self, year: int) -> Optional[date]:
        """When a change requested for ``year`` takes effect.

        The CURRENT policy year's anniversary is already in the past — a
        change requested for it takes effect on the FORECAST date. Later
        years take effect at the start of that year (its anniversary).
        """
        when = self.anniversary(year)
        if (
            self.forecast_date is not None
            and when is not None
            and when < self.forecast_date
        ):
            return self.forecast_date
        return when

    def _forecast_months_since_issue(self) -> Optional[int]:
        """Whole monthliversaries from issue to the first forecast month."""
        if self.issue_date is None or self.forecast_date is None:
            return None
        months = (
            (self.forecast_date.year - self.issue_date.year) * 12
            + (self.forecast_date.month - self.issue_date.month)
        )
        if self.forecast_date.day < self.issue_date.day:
            months -= 1
        return months

    def payment_count(self, mode: str) -> int:
        """Number of modal payments from the forecast month to min(maturity, 100).

        The whole years to the limit age contribute ``freq`` payments each, plus
        any modal due dates still left in the CURRENT policy year (from the
        forecast month to the next anniversary) — so e.g. a few quarters left
        this year are counted, not just whole_years * frequency.
        """
        interval = _MODE_INTERVALS.get(mode, 12)
        freq = 12 // interval
        whole_year_payments = max(0, self.max_level_years) * freq

        n_forecast = self._forecast_months_since_issue()
        if n_forecast is None:
            return whole_year_payments
        # Modal due months in a policy year are 1, 1+interval, ...; count those
        # on or after the forecast month within the current year.
        forecast_month = n_forecast % 12 + 1  # 1..12
        remaining_this_year = sum(
            1 for month in range(forecast_month, 13) if (month - 1) % interval == 0
        )
        return whole_year_payments + remaining_this_year

    def max_modal_level_premium(self, mode: str) -> float:
        if self.is_cvat or self.max_level_premium_room <= 0.0:
            return 0.0
        count = self.payment_count(mode)
        if count <= 0:
            return 0.0
        return self.max_level_premium_room / count

    @property
    def max_annual_level_premium(self) -> float:
        return self.max_modal_level_premium("A")


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
    attained_age = int(getattr(policy, "attained_age", None) or (issue_age + forecast_year - 1) or 0)
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
    plancode = str(getattr(policy, "base_plancode", "") or getattr(policy, "plancode", "") or "")
    illustrated_rate = 0.0
    gint = 0.0
    if plancode:
        gint = load_plancode(plancode).gint
        illustrated_rate = gint
    if illustrated_rate == 0.0:
        illustrated_rate = float(
            getattr(policy, "current_interest_rate", None)
            or getattr(policy, "guaranteed_interest_rate", 0.0)
            or 0.0
        )
        if illustrated_rate > 1.0:
            illustrated_rate /= 100.0
    def_of_life_ins = str(
        getattr(policy, "def_of_life_ins", "")
        or getattr(policy, "def_of_life_insurance", "")
        or getattr(policy, "definition_of_life_insurance", "")
        or "GPT"
    ).upper()
    is_cvat = def_of_life_ins == "CVAT"
    max_level_end_age = min(maturity_age, 100)
    max_level_years = max(0, max_level_end_age - attained_age - 1)
    # GLP normalized to a monthly mode — rounddown(GLP/12, 2) * 12 — to match the
    # engine's GLP everywhere (the Values-tab GLP column and accumulation).
    glp = floor_monthly_cent(_first_float(policy, "glp"))
    accumulated_glp = _first_float(policy, "accumulated_glp", "accumulated_glp_target")
    premiums_paid_to_date = _first_float(policy, "premiums_paid_to_date", "premium_td", "total_premiums_paid")
    withdrawals_to_date = _first_float(policy, "withdrawals_to_date", "total_withdrawals")
    total_accumulated_glp_at_limit_age = accumulated_glp + (max_level_years * glp)
    premium_room = max(
        0.0,
        total_accumulated_glp_at_limit_age
        - (
            premiums_paid_to_date
            - withdrawals_to_date
        ),
    )
    return PolicyContext(
        issue_date=issue_date,
        issue_age=issue_age,
        forecast_year=forecast_year,
        forecast_age=issue_age + forecast_year - 1,
        forecast_date=forecast,
        maturity_age=maturity_age,
        default_mode=mode,
        modal_premium=float(getattr(policy, "modal_premium", 0.0) or 0.0),
        form_number=str(getattr(policy, "form_number", "")
                        or getattr(policy, "base_form_number", "") or ""),
        max_level_premium_room=premium_room,
        max_level_years=max_level_years,
        is_cvat=is_cvat,
        has_loans=bool(getattr(policy, "total_loan_balance", 0) or 0),
        rate_class=str(getattr(policy, "base_rate_class", "") or getattr(policy, "rate_class", "") or ""),
        table_rating=table_rating,
        illustrated_rate=illustrated_rate,
        plancode=plancode,
        is_iul=is_iul_plan(plancode),
        gint=gint,
        premium_allocations=_premium_allocations_from_policy(policy),
        sweep_account_min=float(getattr(policy, "sweep_account_min", 0.0) or 0.0),
        suspended=status_code == "2",
        valuation_date=valuation,
    )


def _premium_allocations_from_policy(policy) -> Optional[dict]:
    """Inforce premium allocation % by fund ID, from either data shape.

    ``IllustrationPolicyData`` carries ``premium_allocations`` directly;
    ``PolicyInformation`` looks it up in DB2 (LH_FND_ALC). Missing tables or
    a non-IUL policy simply return None → the grid defaults to 100% fixed.
    """
    direct = getattr(policy, "premium_allocations", None)
    if direct:
        return dict(direct)
    getter = getattr(policy, "get_premium_allocation_dict", None)
    if callable(getter):
        try:
            allocations = getter()
            return {str(k): float(v) for k, v in allocations.items()} or None
        except Exception:
            return None
    return None


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


class _RateField(QLineEdit):
    """Percent field that exports an annual rate as a decimal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_EDIT_STYLE)
        self.setFixedWidth(58)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setValidator(QDoubleValidator(0.0, 99.999, 3, self))

    def set_rate(self, annual_rate: float):
        self.setText(f"{annual_rate * 100.0:.3f}")

    def rate(self) -> float:
        try:
            return float((self.text() or "").strip()) / 100.0
        except ValueError:
            return 0.0


# Premium-type dropdown values (premium section only). The two level types are a
# GPT-only "solve" the engine fills in on Run Values: Max Level is the largest
# level premium the guideline acceptance chain never caps; Prem to Maturity is
# the minimum level premium that keeps the policy in force to maturity.
_TYPE_INPUT = "INPUT"
# "Billable Prem" is a convenience input type: selecting it fills the row's
# amount with the policy's current billable premium and its billing mode, so the
# user need not re-key them. It otherwise behaves exactly like an INPUT premium.
# SPL87-form plans (single-premium) have a zero billable premium.
_TYPE_BILLABLE = "Billable Prem"
# "Billable to MD" models what many owners actually do: pay the billed premium
# for as long as it keeps the policy alive, then pay only what the policy needs.
# The row fills with the billable premium and billing mode (editable, like
# Billable Prem) and pays as a normal scheduled premium; the engine watches
# each month and — the FIRST month that premium can no longer keep the policy
# in force — permanently switches to the Monthly Deduction premium, which the
# GP exception premium backstops once the guideline room runs out (exceptions
# are always allowed for this premium type, regardless of the checkbox). The
# row's year window bounds the whole billable → MD → exception sequence.
_TYPE_BILLABLE_TO_MD = "Billable to MD"
# "Max Level" is the maximum level guideline premium (may not reach
# maturity). The row shows a closed-form estimate from the CURRENT guideline
# room immediately; Run Values solves it exactly on the real projection so any
# Face Amount / DB Option change's effect on the guidelines is reflected.
# "Prem to Maturity" is solved by the engine (amount filled on Run Values);
# GP exception premiums are ALWAYS allowed for this premium type — the solve
# rides the GLP exception period when the guideline caps further funding,
# regardless of the Allow GP Exception Premium checkbox.
_TYPE_MAX_LEVEL = "Max Level"
_TYPE_MIN_LEVEL = "Prem to Maturity"
# "Prem to Shadow Maturity" (shadow-account policies only) is the minimum level
# premium that keeps the SHADOW account in force to maturity — the shadow
# account governs lapse once past the safety-net period, so the real account
# value may run negative while the policy stays in force. Solved with GP
# exceptions off (an active shadow account blocks them).
_TYPE_SHADOW_LEVEL = "Prem to Shadow Maturity"
_LEVEL_TYPES = (_TYPE_MAX_LEVEL, _TYPE_MIN_LEVEL, _TYPE_SHADOW_LEVEL)
# "Solve" is a target-value premium solve: the Premium Solve criteria group
# (below the Premiums section) picks the value to hit — Account Value,
# Surrender Value, or Shadow Account Value — the target amount, and the
# beginning-of-year age it must be reached AT (age 100 → the ending value at
# attained age 99, month 12). Run Values solves the minimum level premium that
# meets the criteria and fills this row's amount; an unreachable target pops a
# message instead.
_TYPE_SOLVE = "Solve"
# "Monthly Deduction" pays, each month, exactly the policy's monthly deduction
# (grossed up by the COI rate and premium load) so the account value after the
# deduction equals where it stood just before it. The engine reuses the GP
# exception premium machinery, retargeted; it is mutually exclusive with the
# Allow GP Exception Premium toggle. The mode is forced to M (monthly).
_TYPE_MONTHLY_DEDUCTION = "Monthly Deduction"
# "Pay-off" (Loan Repayments section only) is a solved repayment: the user
# picks the window (Year/Age, mode, For Years/To Age) and Run Values solves
# the level modal repayment that zeroes the loan by the end of the window —
# repayments apply before new loans, so the balance is zero just before any
# new loan that follows. The amount field is display-only.
_TYPE_PAYOFF = "Pay-off"


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
        self.type_combo.setStyleSheet(_COMBO_STYLE)
        self.type_combo.setFixedWidth(spec.type_width)
        self._sync_type_options()
        self.type_combo.currentIndexChanged.connect(self._type_changed)
        layout.addWidget(self.type_combo)

        # The Premium Type dropdown's contents depend on the app-wide
        # "Additional Premium Types" option. Re-sync whenever it flips so the
        # advanced types appear/disappear live across every open policy/case.
        if spec.allow_max_level_premium:
            get_illustration_settings().additional_premium_types_changed.connect(
                self._on_additional_premium_types_changed)

        self.year_edit = _Field(_W_YEAR)
        self.year_edit.editingFinished.connect(self._year_edited)
        layout.addWidget(self.year_edit)

        self.age_edit = _Field(_W_AGE)
        self.age_edit.editingFinished.connect(self._age_edited)
        layout.addWidget(self.age_edit)

        # The value column is the row's ONE flexible width. Every other field
        # is fixed, so when a section gets less than its natural width (the
        # four change sections share a window row) Qt would otherwise clamp
        # the trailing widgets inward and draw the − button ON the value
        # field. Letting the value give up width absorbs the squeeze instead:
        # it grows to its design width when there is room (stretch 1, capped
        # by the maximum) and shrinks toward its minimum when there isn't.
        self.value_combo: Optional[QComboBox] = None
        self.amount_edit: Optional[_Field] = None
        if spec.value_options is not None:
            self.value_combo = QComboBox(self)
            for code, label in spec.value_options:
                self.value_combo.addItem(label, code)
            self.value_combo.setStyleSheet(_COMBO_STYLE)
            self.value_combo.setMinimumWidth(80)
            self.value_combo.setMaximumWidth(spec.value_width)
            self.value_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            layout.addWidget(self.value_combo, 1)
        else:
            self.amount_edit = _Field(spec.value_width, decimals=2)
            self.amount_edit.setMinimumWidth(64)
            self.amount_edit.setMaximumWidth(spec.value_width)
            self.amount_edit.editingFinished.connect(lambda: self.changed.emit())
            layout.addWidget(self.amount_edit, 1)

        self.mode_combo: Optional[QComboBox] = None
        self.for_years_edit: Optional[_Field] = None
        self.to_age_edit: Optional[_Field] = None
        if spec.has_span:
            self.mode_combo = QComboBox(self)
            self.mode_combo.addItems(["M", "Q", "S", "A"])
            self.mode_combo.setCurrentText(spec.default_mode)
            self.mode_combo.setStyleSheet(_COMBO_STYLE)
            self.mode_combo.setFixedWidth(_W_MODE)
            self.mode_combo.currentIndexChanged.connect(self._mode_changed)
            layout.addWidget(self.mode_combo)

            self.for_years_edit = _Field(_W_SPAN)
            self.for_years_edit.editingFinished.connect(self._for_years_edited)
            layout.addWidget(self.for_years_edit)

            self.to_age_edit = _Field(_W_SPAN)
            self.to_age_edit.editingFinished.connect(self._to_age_edited)
            layout.addWidget(self.to_age_edit)

        # Withdrawal basis: Net (default) means the client receives the entered
        # amount and the policy is charged that plus any fee/surrender charge;
        # Gross means the entered amount is what comes out of the policy.
        self.basis_combo: Optional[QComboBox] = None
        if spec.has_basis:
            self.basis_combo = QComboBox(self)
            self.basis_combo.addItems(["Net", "Gross"])
            self.basis_combo.setStyleSheet(_COMBO_STYLE)
            self.basis_combo.setFixedWidth(_W_BASIS)
            self.basis_combo.setToolTip(
                "Net: the client receives this amount (charges come out of the "
                "policy on top). Gross: this amount leaves the policy (the client "
                "receives it less charges).")
            self.basis_combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            layout.addWidget(self.basis_combo)

        self.remove_btn = QPushButton("−")
        self.remove_btn.setStyleSheet(_SMALL_BTN_STYLE)
        self.remove_btn.setToolTip("Remove this row")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        # Reserve the button's slot even when hidden (the first row has no −)
        # so every row lays out identically and the section is sized with room
        # for the button — otherwise adding a row squeezes the − into the
        # section edge, overlapping the value field.
        policy = self.remove_btn.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.remove_btn.setSizePolicy(policy)
        self.remove_btn.setVisible(removable)
        layout.addWidget(self.remove_btn)
        # Zero-stretch tail: it absorbs leftover width only AFTER the value
        # column (stretch 1) has grown to its design width, and gives width
        # up first when the section is squeezed.
        layout.addStretch(0)

    # ── sync handlers ─────────────────────────────────────────

    def set_context(self, ctx: PolicyContext):
        self._ctx = ctx
        self._sync_type_options()
        self._refresh_max_level_amount()

    def _sync_type_options(self):
        current = self.type_combo.currentText()
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        if self._section.spec.allow_max_level_premium:
            # Max Level is guideline-room math, so it is GPT-only; Prem to
            # Maturity solves for CVAT too (with exceptions off — CVAT has no
            # guideline cap or exception machinery). The Min Level solver is
            # loan-capable (it applies premium to the loan first), so a policy
            # loan doesn't hide it. Prem to Shadow Maturity appears only when
            # the policy carries a shadow-account benefit (type A) — including
            # a ceased one, so the run can explain why it can't solve.
            #
            # The advanced types (Billable to MD, Max Level, Monthly Deduction,
            # Prem to Shadow Maturity) are gated behind the app-wide
            # "Additional Premium Types" option (off by default) — when off the
            # dropdown shows only INPUT, Billable Prem, Prem to Maturity, Solve.
            ctx = self._ctx
            show_additional = get_illustration_settings().additional_premium_types
            options = [_TYPE_INPUT, _TYPE_BILLABLE]
            if show_additional:
                options.append(_TYPE_BILLABLE_TO_MD)
            if show_additional and not (ctx is not None and ctx.is_cvat):
                options.append(_TYPE_MAX_LEVEL)
            options.append(_TYPE_MIN_LEVEL)
            if show_additional and ctx is not None and (ctx.has_shadow or ctx.shadow_ceased):
                options.append(_TYPE_SHADOW_LEVEL)
            if show_additional:
                options.append(_TYPE_MONTHLY_DEDUCTION)
            # "Solve" (target-value premium solve) works on any product — it
            # bisects the real projection under the user's own run options.
            options.append(_TYPE_SOLVE)
            self.type_combo.addItems(options)
            self.type_combo.setFixedWidth(self._section.spec.type_width)
            if current in options:
                self.type_combo.setCurrentText(current)
        elif self._section.spec.allow_payoff:
            options = ["Input", _TYPE_PAYOFF]
            self.type_combo.addItems(options)
            self.type_combo.setFixedWidth(self._section.spec.type_width)
            if current in options:
                self.type_combo.setCurrentText(current)
        else:
            self.type_combo.addItems(["Input", "Solve"])
            model_item = self.type_combo.model().item(1)
            if model_item is not None:
                model_item.setEnabled(False)
            self.type_combo.setFixedWidth(self._section.spec.type_width)
            if current in {"Input", "Solve"}:
                self.type_combo.setCurrentText(current)
        self.type_combo.blockSignals(False)

    def _on_additional_premium_types_changed(self, _enabled: bool):
        """Re-sync the Premium Type dropdown when the app-wide option flips.
        If the row's current type was an advanced one that's now hidden, the
        combo falls back to INPUT — emit changed so the inputs recompute."""
        previous = self.type_combo.currentText()
        self._sync_type_options()
        if self.type_combo.currentText() != previous:
            self.changed.emit()

    def _type_changed(self, _index: int):
        # Selecting "Billable Prem" or "Billable to MD" fills the amount + mode
        # from the policy's billable premium; Billable Prem then behaves like a
        # plain INPUT premium, Billable to MD adds the engine-side MD hand-off.
        if (self.premium_type() in (_TYPE_BILLABLE, _TYPE_BILLABLE_TO_MD)
                and self._ctx is not None):
            self._apply_billable_premium()
        self._refresh_max_level_amount()
        self.changed.emit()

    def _apply_billable_premium(self):
        """Fill the row with the policy's billable premium and billing mode.
        SPL87-form plans have a zero billable premium."""
        ctx = self._ctx
        if self.amount_edit is not None:
            self.amount_edit.set_value(ctx.billable_premium, decimals=2)
        if self.mode_combo is not None and self.mode_combo.currentText() != ctx.default_mode:
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentText(ctx.default_mode)
            self.mode_combo.blockSignals(False)

    def _mode_changed(self, _index: int):
        self._refresh_max_level_amount()
        self.changed.emit()

    def premium_type(self) -> str:
        """The premium-type dropdown value (premium section)."""
        return self.type_combo.currentText()

    def is_min_level(self) -> bool:
        return (self._section.spec.allow_max_level_premium
                and self.type_combo.currentText() == _TYPE_MIN_LEVEL)

    def is_max_level(self) -> bool:
        return (self._section.spec.allow_max_level_premium
                and self.type_combo.currentText() == _TYPE_MAX_LEVEL)

    def is_shadow_level(self) -> bool:
        return (self._section.spec.allow_max_level_premium
                and self.type_combo.currentText() == _TYPE_SHADOW_LEVEL)

    def is_monthly_deduction(self) -> bool:
        return self.type_combo.currentText() == _TYPE_MONTHLY_DEDUCTION

    def is_billable_to_md(self) -> bool:
        return self.type_combo.currentText() == _TYPE_BILLABLE_TO_MD

    def is_solve(self) -> bool:
        """A Premiums "Solve" row — target-value premium, solved on Run Values."""
        return (self._section.spec.allow_max_level_premium
                and self.type_combo.currentText() == _TYPE_SOLVE)

    def is_payoff(self) -> bool:
        """A Loan Repayments "Pay-off" row — amount is solved on Run Values."""
        return (self._section.spec.allow_payoff
                and self.type_combo.currentText() == _TYPE_PAYOFF)

    def set_amount_display(self, value: Optional[float]):
        """Fill the (disabled) amount field with a solved value for display."""
        if self.amount_edit is None:
            return
        if value is None:
            self.amount_edit.setText("")
        else:
            self.amount_edit.set_value(value, decimals=2)

    def _refresh_max_level_amount(self):
        ptype = self.type_combo.currentText()
        # Monthly Deduction forces the mode to M (it is recomputed and paid every
        # month) and locks the mode combo while selected.
        self._apply_monthly_deduction_mode(ptype == _TYPE_MONTHLY_DEDUCTION)
        if self.amount_edit is None:
            return
        # Max Level is guideline-room math → GPT only; Prem to (Shadow) Maturity
        # solves for any product the type dropdown offered it on.
        level_capable = (
            self._section.spec.allow_max_level_premium
            and self._ctx is not None
        )
        max_capable = level_capable and not self._ctx.is_cvat
        if max_capable and ptype == _TYPE_MAX_LEVEL:
            # Closed-form ESTIMATE from the current guideline room — read-only,
            # filled now. Run Values solves the exact maximum on the real
            # projection (reflecting any Face Amount / DB Option changes) and
            # overwrites this display.
            self.amount_edit.setEnabled(True)
            self.amount_edit.setReadOnly(True)
            self.amount_edit.set_value(self._ctx.max_modal_level_premium(self.mode()), decimals=2)
            self.amount_edit.setToolTip(
                "Maximum level premium the guideline limits allow — estimated here "
                "from the current guideline room divided by the modal payments to "
                "maturity (capped at age 100). Solved exactly when you Run Values, "
                "including the effect of any Face Amount / DB Option changes on "
                "the guideline premiums.")
        elif level_capable and ptype == _TYPE_MIN_LEVEL:
            # Solved on Run Values — disabled and blank until the run fills it.
            self.amount_edit.setText("")
            self.amount_edit.setReadOnly(True)
            self.amount_edit.setEnabled(False)
            self.amount_edit.setToolTip(
                "Minimum level premium that keeps the policy in force to maturity. "
                "Solved when you Run Values. On GPT policies GP exception premiums "
                "are always allowed for this premium type — the run ignores the "
                "Allow GP Exception Premium checkbox. CVAT policies solve without "
                "exceptions (there is no guideline cap to ride).")
        elif level_capable and ptype == _TYPE_SHADOW_LEVEL:
            # Solved on Run Values — disabled and blank until the run fills it.
            self.amount_edit.setText("")
            self.amount_edit.setReadOnly(True)
            self.amount_edit.setEnabled(False)
            self.amount_edit.setToolTip(
                "Minimum level premium that keeps the shadow account in force to "
                "maturity — the shadow account governs lapse, so the regular "
                "account value may run negative while the policy stays in force. "
                "Solved when you Run Values.")
        elif ptype == _TYPE_MONTHLY_DEDUCTION:
            # Solved in-engine each month (varies with the deduction) — blank and
            # disabled; only the start year is read off this row.
            self.amount_edit.setText("")
            self.amount_edit.setReadOnly(True)
            self.amount_edit.setEnabled(False)
            self.amount_edit.setToolTip(
                "Pays the policy's monthly deduction each month — grossed up for the "
                "COI rate and premium load — so the account value stays where it was "
                "just before the deduction. The mode is forced to M.")
        elif self.is_payoff():
            # Solved on Run Values — disabled and blank until the run fills it.
            self.amount_edit.setText("")
            self.amount_edit.setReadOnly(True)
            self.amount_edit.setEnabled(False)
            self.amount_edit.setToolTip(
                "Level repayment at this mode that pays the loan off completely by "
                "the end of the period — the balance is zero just before any new "
                "loan that follows. Solved when you Run Values.")
        elif self.is_solve():
            # Solved on Run Values from the Premium Solve criteria group —
            # disabled and blank until the run fills it.
            self.amount_edit.setText("")
            self.amount_edit.setReadOnly(True)
            self.amount_edit.setEnabled(False)
            self.amount_edit.setToolTip(
                "Minimum level premium that reaches the Premium Solve target "
                "(value, amount, and age set in the group below). Solved when "
                "you Run Values; a target the policy cannot reach reports "
                "instead of filling this field.")
        elif ptype == _TYPE_BILLABLE_TO_MD:
            # Editable like Billable Prem — the amount/mode were auto-filled
            # from the billable premium; the hand-off is engine-side.
            self.amount_edit.setEnabled(True)
            self.amount_edit.setReadOnly(False)
            self.amount_edit.setToolTip(
                "Pays this premium on its mode until the first month it can no "
                "longer keep the policy in force, then switches permanently to "
                "paying the Monthly Deduction each month. Once the guideline "
                "room runs out, GP exception premiums keep the policy alive — "
                "they are always allowed for this premium type, regardless of "
                "the Allow GP Exception Premium checkbox.")
        else:
            self.amount_edit.setEnabled(True)
            self.amount_edit.setReadOnly(False)
            self.amount_edit.setToolTip("")

    def _apply_monthly_deduction_mode(self, force_monthly: bool):
        """Lock the mode to M while Monthly Deduction is selected; else unlock."""
        if self.mode_combo is None:
            return
        if force_monthly:
            if self.mode_combo.currentText() != "M":
                self.mode_combo.blockSignals(True)
                self.mode_combo.setCurrentText("M")
                self.mode_combo.blockSignals(False)
            self.mode_combo.setEnabled(False)
        else:
            self.mode_combo.setEnabled(True)


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
        if for_years is None and self._section.spec.default_span_to_maturity:
            # A fresh premium row runs to maturity until the user says otherwise.
            for_years = self._ctx.maturity_year - year + 1
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

    def basis(self) -> str:
        """Withdrawal basis — "net" (default) or "gross"."""
        if self.basis_combo is None:
            return "net"
        return self.basis_combo.currentText().lower()

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

    def set_end_year(self, end_year: int):
        if self.for_years_edit is None or self._ctx is None:
            return
        year = self.year()
        if year is None or end_year < year:
            return
        self._set_span_from_years(year, end_year - year + 1)

    # ── saved-case capture/apply ──────────────────────────────

    def capture_state(self) -> dict:
        """JSON-safe snapshot of every editable field on this row."""
        state: dict = {
            "type": self.type_combo.currentText(),
            "year": self.year_edit.text(),
            "age": self.age_edit.text(),
        }
        if self.amount_edit is not None:
            state["amount"] = self.amount_edit.text()
        if self.value_combo is not None:
            state["value"] = self.value_combo.currentData()
        if self.mode_combo is not None:
            state["mode"] = self.mode_combo.currentText()
            state["for_years"] = self.for_years_edit.text()
            state["to_age"] = self.to_age_edit.text()
        if self.basis_combo is not None:
            state["basis"] = self.basis_combo.currentText()
        return state

    def apply_state(self, state: dict) -> list[str]:
        """Restore a captured snapshot. Returns warnings for anything that
        could not land on this policy (e.g. a premium type the policy's
        dropdown does not offer) — never a silent drop."""
        warnings: list[str] = []
        section_title = self._section.spec.title
        saved_type = str(state.get("type") or "")
        if saved_type:
            index = self.type_combo.findText(saved_type)
            if index >= 0:
                self.type_combo.setCurrentIndex(index)
            else:
                warnings.append(
                    f"{section_title}: type '{saved_type}' is not available on "
                    f"this policy — row kept as "
                    f"'{self.type_combo.currentText()}'.")
        if self.mode_combo is not None and state.get("mode"):
            self.mode_combo.setCurrentText(str(state["mode"]))
        self.year_edit.setText(str(state.get("year") or ""))
        self.age_edit.setText(str(state.get("age") or ""))
        if self.amount_edit is not None:
            self.amount_edit.setText(str(state.get("amount") or ""))
        if self.value_combo is not None:
            saved_value = state.get("value")
            if saved_value is None:
                self.value_combo.setCurrentIndex(0)
            else:
                index = self.value_combo.findData(saved_value)
                if index >= 0:
                    self.value_combo.setCurrentIndex(index)
                else:
                    warnings.append(
                        f"{section_title}: value '{saved_value}' is not "
                        f"offered on this policy — row left at "
                        f"'{self.value_combo.currentText()}'.")
        if self.for_years_edit is not None:
            self.for_years_edit.setText(str(state.get("for_years") or ""))
            self.to_age_edit.setText(str(state.get("to_age") or ""))
        if self.basis_combo is not None and state.get("basis"):
            self.basis_combo.setCurrentText(str(state["basis"]))
        return warnings

    def blank(self):
        """Clear every field back to the section defaults (pre-apply reset)."""
        self.type_combo.setCurrentIndex(0)
        self.year_edit.setText("")
        self.age_edit.setText("")
        if self.amount_edit is not None:
            self.amount_edit.setText("")
        if self.value_combo is not None:
            self.value_combo.setCurrentIndex(0)
        if self.mode_combo is not None:
            self.mode_combo.setCurrentText(self._section.spec.default_mode)
            self.for_years_edit.setText("")
            self.to_age_edit.setText("")
        if self.basis_combo is not None:
            self.basis_combo.setCurrentIndex(0)


@dataclass
class SectionSpec:
    title: str
    has_span: bool = True
    value_caption: str = "Amount"
    value_width: int = 110
    value_options: Optional[list] = None       # [(code, label)] -> combo instead of amount
    default_first_row: bool = False            # premium defaults from the policy
    default_span_to_maturity: bool = False     # empty For Years/To Age -> maturity
    auto_adjust_prior_span: bool = False
    allow_max_level_premium: bool = False
    allow_payoff: bool = False                  # "Pay-off" solve type (loan repayments)
    type_width: int = _W_TYPE                   # Type column width (wider for level types)
    has_basis: bool = False                     # Net/Gross basis combo (withdrawals)
    default_mode: str = "M"                     # Mode combo default for new rows


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
        self._outer = outer
        self._header_count = 0

        captions = QHBoxLayout()
        captions.setContentsMargins(0, 0, 0, 0)
        captions.setSpacing(4)
        widths = [spec.type_width, _W_YEAR, _W_AGE, spec.value_width]
        labels = ["Type", "Year", "Age", spec.value_caption]
        if spec.has_span:
            widths += [_W_MODE, _W_SPAN, _W_SPAN]
            labels += ["Mode", "For Years", "To Age"]
        if spec.has_basis:
            widths += [_W_BASIS]
            labels += ["Net/Gross"]
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

        self._footer = QHBoxLayout()
        self._footer.setContentsMargins(0, 2, 0, 0)
        self.add_btn = QPushButton("＋")
        self.add_btn.setStyleSheet(_SMALL_BTN_STYLE)
        self.add_btn.setToolTip("Add another row")
        self.add_btn.clicked.connect(lambda: self.add_row())
        self._footer.addWidget(self.add_btn)
        self.warning = QLabel("Rows overlap — later rows must start after earlier rows end.")
        self.warning.setStyleSheet(
            "color: #C62828; background: transparent; font-size: 10px; font-weight: bold;")
        self.warning.setVisible(False)
        self._footer.addWidget(self.warning)
        self._footer.addStretch(1)
        outer.addLayout(self._footer)
        # Pack the contents to the TOP. Sections share grid rows with taller
        # neighbors (e.g. Loans next to Premiums with its lumpsum header), and
        # without a trailing stretch the QVBoxLayout distributes the surplus
        # height between the caption row, the rows, and the ＋ footer — the
        # controls spread apart. The stretch absorbs the leftover at the
        # bottom instead, keeping the spacing tight and consistent.
        outer.addStretch(1)

        self.add_row(removable=False)

    def add_footer_widget(self, widget: QWidget):
        """Place an extra control in the section footer, left of the stretch."""
        self._footer.insertWidget(self._footer.count() - 1, widget)

    def add_bottom_widget(self, widget: QWidget):
        """Place a widget under the rows and ＋ footer, above the trailing
        stretch (e.g. the Premium Solve criteria group)."""
        self._outer.insertWidget(self._outer.count() - 1, widget)

    def add_header_widget(self, widget: QWidget):
        """Place a control at the top of the section, above the column captions."""
        self._outer.insertWidget(self._header_count, widget)
        self._header_count += 1

    def add_row(self, removable: bool = True) -> InputRow:
        row = InputRow(self, removable, self)
        if self._ctx is not None:
            row.set_context(self._ctx)
        row.changed.connect(self._validate)
        row.remove_requested.connect(self._remove_row)
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._prefill_continuation(row)
        return row

    def _prefill_continuation(self, row: InputRow):
        """Start a new span row where the previous rows end.

        The added row's Age defaults to the latest To Age among the other
        rows (its Year is the year after that span ends), so consecutive
        requests chain without overlapping. A prior row already running to
        maturity leaves the new row blank for the user to fill.
        """
        ctx = self._ctx
        if ctx is None or not self.spec.has_span:
            return
        ends = [other.end_year() for other in self._rows
                if other is not row and other.year() is not None]
        if not ends:
            return
        next_year = max(ends) + 1
        if next_year > ctx.maturity_year:
            return
        row.year_edit.set_value(next_year)
        row.age_edit.set_value(ctx.age_for_year(next_year))
        row._resync_span(next_year)
        self._validate()

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
        if first.basis_combo is not None:
            first.basis_combo.setCurrentIndex(0)   # back to the Net default
        if first.mode_combo is not None:
            first.mode_combo.setCurrentText(self.spec.default_mode)
        if self.spec.default_first_row:
            first.type_combo.setCurrentIndex(0)
            first.year_edit.set_value(ctx.forecast_year)
            first.age_edit.set_value(ctx.forecast_age)
            if first.mode_combo is not None:
                first.mode_combo.setCurrentText(ctx.default_mode)
            if first.for_years_edit is not None:
                for_years = ctx.maturity_year - ctx.forecast_year + 1
                first.for_years_edit.set_value(for_years)
                first.to_age_edit.set_value(ctx.maturity_age)
            # Default INPUT amount is the billable premium — 0 on SPL87 plans,
            # which set it explicitly rather than leaving it blank.
            if first.amount_edit is not None:
                if ctx.is_spl87:
                    first.amount_edit.set_value(0.0, decimals=2)
                elif ctx.billable_premium:
                    first.amount_edit.set_value(ctx.billable_premium, decimals=2)
            first._refresh_max_level_amount()
        self._validate()

    def _validate(self):
        """Overlap check: sort filled rows; ranges may gap but not intersect."""
        self._auto_adjust_prior_spans()
        filled = [(row.year(), row.end_year(), row) for row in self._rows if row.year() is not None]
        filled.sort(key=lambda entry: entry[0])
        overlapped: set = set()
        offending: Optional[InputRow] = None
        for (start_a, end_a, row_a), (start_b, end_b, row_b) in zip(filled, filled[1:]):
            if end_a is not None and start_b is not None and start_b <= end_a:
                overlapped.add(row_a)
                overlapped.add(row_b)
                if offending is None:
                    offending = row_b
        for row in self._rows:
            row.set_overlap(row in overlapped)
        was_overlapping = self._has_overlap
        self._has_overlap = bool(overlapped)
        self.warning.setVisible(self._has_overlap)
        if self._has_overlap and not was_overlapping and offending is not None:
            self._notify_overlap(offending)
        self.changed.emit()

    def _notify_overlap(self, row: InputRow):
        """Non-blocking heads-up at the offending row when an overlap appears
        (on top of the red field outlines and the footer warning)."""
        anchor = row.year_edit
        QToolTip.showText(
            anchor.mapToGlobal(QPoint(0, anchor.height() + 2)),
            self.warning.text(), anchor, QRect(), 4000)

    def _auto_adjust_prior_spans(self):
        if not self.spec.auto_adjust_prior_span:
            return
        filled = [(row.year(), row.end_year(), row) for row in self._rows if row.year() is not None]
        filled.sort(key=lambda entry: entry[0])
        for (start_a, end_a, row_a), (start_b, _end_b, _row_b) in zip(filled, filled[1:]):
            if end_a is not None and start_b is not None and start_a < start_b <= end_a:
                row_a.set_end_year(start_b - 1)

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
            entry = {
                "year": row.year(),
                "end_year": row.end_year(),
                "amount": row.amount(),
                "value": row.chosen_value(),
                "mode": row.mode(),
                "type": row.premium_type(),
            }
            if self.spec.has_basis:
                entry["basis"] = row.basis()       # "net" (default) | "gross"
            out.append(entry)
        out.sort(key=lambda e: e["year"])
        return out

    # ── saved-case capture/apply ──────────────────────────────

    def capture_rows(self) -> list[dict]:
        """Snapshot of every row, in display order (JSON-safe)."""
        return [row.capture_state() for row in self._rows]

    def apply_rows(self, rows: list[dict]) -> list[str]:
        """Rebuild the section from a captured snapshot; returns warnings."""
        warnings: list[str] = []
        while len(self._rows) > 1:
            self._remove_row(self._rows[-1])
        states = list(rows) or [{}]
        while len(self._rows) < len(states):
            self.add_row()
        for row, state in zip(self._rows, states):
            row.blank()
            warnings.extend(row.apply_state(state))
        self._validate()
        return warnings


class RiderAdjustment:
    KEEP = "keep"
    CHANGE = "change"
    DROP = "drop"

    def __init__(self):
        self.action = self.KEEP
        self.new_amount: Optional[float] = None
        self.effective_year: Optional[int] = None
        self.effective_date: Optional[date] = None   # set when entered by date


_SEGMENT_STYLE = f"""
    QPushButton {{
        background-color: #F3ECFC;
        color: {PURPLE_DARK};
        border: 1px solid #7E57C2;
        padding: 3px 14px;
        font-size: 11px;
        font-weight: bold;
    }}
    QPushButton:hover:enabled {{ background-color: #E6DAF8; }}
    QPushButton:checked {{
        background-color: #5E35A5;
        color: #FFD54F;
        border-color: #4B2383;
    }}
    QPushButton:disabled {{
        background-color: #EDE7F6;
        color: #A89BC0;
        border-color: #C9BBE2;
    }}
    QPushButton:checked:disabled {{
        background-color: #D5C9E8;
        color: #8E82A8;
        border-color: #C9BBE2;
    }}
"""


class RiderButtonsPanel(QGroupBox):
    """Buttons for the policy's active riders/benefits with keep/change/drop."""

    changed = pyqtSignal()

    _BTN = (
        "QPushButton {{ background: {bg}; color: {fg}; border: 1px solid {border};"
        " border-radius: 4px; padding: 3px 10px; font-size: 11px; font-weight: bold; }}"
        "QPushButton:disabled {{ background: #EDE7F6; color: #A89BC0; border: 1px dashed #C9BBE2; }}"
        "QPushButton:hover:enabled {{ background: #E6DAF8; }}"
    )
    # Matured / ceased riders wear the same greyed, dashed look as the disabled
    # (non-premium-paying) buttons, but stay enabled so the user can still click
    # through to view the rider's details. Italic marks "no longer in force."
    _MATURED_BTN = (
        "QPushButton { background: #EDE7F6; color: #A89BC0; border: 1px dashed #C9BBE2;"
        " border-radius: 4px; padding: 3px 10px; font-size: 11px; font-weight: bold;"
        " font-style: italic; }"
        "QPushButton:hover { background: #E6DAF8; }"
    )

    def __init__(self, parent=None):
        super().__init__("Riders && Benefits", parent)
        self.setStyleSheet(GROUP_STYLE)
        self._ctx: Optional[PolicyContext] = None
        self._items: list[tuple] = []          # (key, label, detail_rows, premium_paying, amount, matured)
        self._adjustments: dict[str, RiderAdjustment] = {}
        self._buttons: dict[str, QPushButton] = {}
        self._matured: set[str] = set()        # keys whose rider/benefit has already matured
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
        self._matured = set()
        as_of = ctx.valuation_date or ctx.forecast_date or date.today()
        for index in reversed(range(self._layout.count())):
            item = self._layout.takeAt(index)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._buttons = {}

        if not hasattr(policy, "get_coverages"):
            # IllustrationPolicyData (a saved-case snapshot): riders/benefits
            # are already-materialized dataclasses. Build the same items —
            # with the SAME keys — so saved rider decisions land identically.
            self._build_items_from_snapshot(policy, as_of)
            self._finish_item_buttons()
            return

        coverages = []
        benefits = []
        try:
            # Riders only — base coverage segments (is_base, or phase 1 as a
            # fallback) belong to the base policy, not the rider adjustments.
            coverages = [
                c for c in (policy.get_coverages() or [])
                if not (getattr(c, "is_base", False) or c.cov_pha_nbr == 1)
            ]
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
            self._items.append(
                (f"cov:{cov.cov_pha_nbr}", label, rows, premium_paying, amount,
                 coverage_or_benefit_matured(cov, as_of)))
        for ben in benefits:
            label = ben.form_number or ben.benefit_code or f"Benefit {ben.cov_pha_nbr}"
            benefit_type = str(getattr(ben, "benefit_type_cd", "") or "")
            # Charged benefits are adjustable. Waiver-style benefits (e.g.
            # ULDW91) carry a zero issue rate (BNF_ANN_PPU_AMT) with the real
            # charge in the renewal-rate segment, so check both rate sources.
            has_charge = bool(getattr(ben, "coi_rate", None)) or bool(
                getattr(ben, "renewal_rate", None))
            premium_paying = has_charge and not benefit_type.startswith("#")
            rows = [
                ("Code:", ben.benefit_code), ("Type:", ben.benefit_type_cd),
                ("Description:", ben.benefit_desc), ("Issue Date:", format_date(ben.issue_date)),
                ("Cease Date:", format_date(ben.cease_date)), ("Units:", format_amount(ben.units)),
                ("Amount:", format_amount(ben.benefit_amount)), ("Issue Age:", ben.issue_age),
            ]
            amount = float(getattr(ben, "benefit_amount", 0.0) or 0.0)
            key = f"ben:{benefit_type}{getattr(ben, 'benefit_subtype_cd', '') or ''}:{ben.cov_pha_nbr}"
            self._items.append(
                (key, label, rows, premium_paying, amount, coverage_or_benefit_matured(ben, as_of)))

        self._finish_item_buttons()

    def _build_items_from_snapshot(self, policy, as_of):
        """Items from IllustrationPolicyData.riders/.benefits (no DB2 surface).

        Keys mirror the PolicyInformation build exactly —
        ``cov:<phase>`` / ``ben:<type><subtype>:<phase>`` — so a case's saved
        rider decisions apply onto a snapshot-loaded tab without warnings.
        """
        for rider in (getattr(policy, "riders", None) or []):
            label = rider.plancode or f"Coverage {rider.coverage_phase}"
            premium_paying = bool(rider.premium_rate or rider.coi_rate)
            rows = [
                ("Phase:", rider.coverage_phase), ("Plancode:", rider.plancode),
                ("Issue Date:", format_date(rider.issue_date)),
                ("Amount:", format_amount(rider.face_amount)),
                ("Issue Age:", rider.issue_age), ("Class:", rider.rate_class),
                ("Status:", rider.status),
            ]
            matured = (coverage_or_benefit_matured(rider, as_of)
                       or not rider.is_active)
            self._items.append(
                (f"cov:{rider.coverage_phase}", label, rows, premium_paying,
                 float(rider.face_amount or 0.0), matured))
        for ben in (getattr(policy, "benefits", None) or []):
            benefit_type = str(ben.benefit_type or "")
            subtype = str(ben.benefit_subtype or "")
            label = f"Benefit {benefit_type}{subtype}".strip()
            premium_paying = bool(ben.coi_rate) and not benefit_type.startswith("#")
            rows = [
                ("Type:", benefit_type), ("Subtype:", subtype),
                ("Issue Date:", format_date(ben.issue_date)),
                ("Cease Date:", format_date(ben.cease_date)),
                ("Units:", format_amount(ben.units)),
                ("Amount:", format_amount(ben.benefit_amount)),
                ("Issue Age:", ben.issue_age),
            ]
            matured = (coverage_or_benefit_matured(ben, as_of)
                       or not ben.is_active)
            key = f"ben:{benefit_type}{subtype}:{ben.coverage_phase}"
            self._items.append(
                (key, label, rows, premium_paying,
                 float(ben.benefit_amount or 0.0), matured))

    def _finish_item_buttons(self):
        if not self._items:
            note = QLabel("No riders or benefits on this policy.")
            note.setStyleSheet(
                f"color: {PURPLE_DARK}; background: transparent; font-size: 10px; font-style: italic;")
            self._layout.addWidget(note)
        for key, label, rows, premium_paying, amount, matured in self._items:
            self._adjustments[key] = RiderAdjustment()
            if matured:
                self._matured.add(key)
            btn = QPushButton(label)
            # Matured riders stay clickable (view their details) but wear the
            # de-emphasized look; non-premium-paying active ones are disabled.
            btn.setEnabled(matured or premium_paying)
            if matured:
                btn.setToolTip("Already matured — view details (no illustration adjustment)")
            elif premium_paying:
                btn.setToolTip("Keep / change / drop this rider")
            else:
                btn.setToolTip("Not premium-paying — no illustration adjustment")
            self._style_button(btn, RiderAdjustment.KEEP, matured=matured)
            btn.clicked.connect(
                lambda checked=False, k=key, l=label, r=rows, a=amount: self._open_dialog(k, l, r, a))
            self._buttons[key] = btn
            self._layout.addWidget(btn)
        self._layout.addStretch(1)

    def _style_button(self, btn: QPushButton, action: str, matured: bool = False):
        if matured:
            btn.setStyleSheet(self._MATURED_BTN)
            return
        if action == RiderAdjustment.CHANGE:
            btn.setStyleSheet(self._BTN.format(bg="#FFF3D6", fg="#7B5E00", border="#D9B44A"))
        elif action == RiderAdjustment.DROP:
            btn.setStyleSheet(self._BTN.format(bg="#FBE4E4", fg="#8B1A2A", border="#C98989"))
        else:
            btn.setStyleSheet(self._BTN.format(bg="#F3ECFC", fg="#4B2383", border="#7E57C2"))

    def _open_dialog(self, key: str, label: str, rows: list, current_amount: float):
        ctx = self._ctx or PolicyContext()
        adj = self._adjustments[key]
        dlg = FramelessDialog(
            label, self,
            header_colors=ILLUSTRATION_HEADER_COLORS,
            border_color=ILLUSTRATION_BORDER_COLOR,
            body_color=PURPLE_BG,
        )
        dlg.setMinimumWidth(380)
        layout = dlg.body_layout

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

        # Segmented action toggle — one clearly-lit selection, no radios.
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(0)
        group = QButtonGroup(dlg)
        group.setExclusive(True)
        keep_btn = QPushButton("Keep rider")
        change_btn = QPushButton("Change rider")
        drop_btn = QPushButton("Drop rider")
        for index, button in enumerate((keep_btn, change_btn, drop_btn)):
            button.setCheckable(True)
            button.setStyleSheet(_SEGMENT_STYLE)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(button)
            toggle_row.addWidget(button)
        toggle_row.addStretch(1)
        layout.addLayout(toggle_row)

        # Detail controls stay in place — greyed when not applicable, so the
        # dialog never reflows as the toggle moves.
        detail_grid = QGridLayout()
        detail_grid.setHorizontalSpacing(8)
        detail_grid.setVerticalSpacing(4)

        amount_caption = QLabel("New amount")
        amount_caption.setStyleSheet(_CAPTION_STYLE)
        amount_edit = _Field(90, decimals=2)
        detail_grid.addWidget(amount_caption, 0, 0)
        detail_grid.addWidget(amount_edit, 1, 0)

        effective_caption = QLabel("Effective")
        effective_caption.setStyleSheet(_CAPTION_STYLE)
        by_year_btn = QPushButton("Year")
        by_date_btn = QPushButton("Date")
        when_group = QButtonGroup(dlg)
        when_group.setExclusive(True)
        when_row = QHBoxLayout()
        when_row.setSpacing(0)
        for button in (by_year_btn, by_date_btn):
            button.setCheckable(True)
            button.setStyleSheet(_SEGMENT_STYLE)
            when_group.addButton(button)
            when_row.addWidget(button)
        detail_grid.addWidget(effective_caption, 0, 1)
        detail_grid.addLayout(when_row, 1, 1)

        year_caption = QLabel("Year")
        year_caption.setStyleSheet(_CAPTION_STYLE)
        year_edit = _Field(50)
        age_caption = QLabel("Age")
        age_caption.setStyleSheet(_CAPTION_STYLE)
        age_edit = _Field(46)
        detail_grid.addWidget(year_caption, 0, 2)
        detail_grid.addWidget(year_edit, 1, 2)
        detail_grid.addWidget(age_caption, 0, 3)
        detail_grid.addWidget(age_edit, 1, 3)

        from PyQt6.QtWidgets import QDateEdit
        from PyQt6.QtCore import QDate

        date_caption = QLabel("Date (monthliversary)")
        date_caption.setStyleSheet(_CAPTION_STYLE)
        date_edit = QDateEdit(dlg)
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("MM/dd/yyyy")
        date_edit.setStyleSheet(
            "QDateEdit { background: white; color: #2A1458; border: 1px solid #B79CDE;"
            " border-radius: 3px; padding: 1px 4px; min-height: 18px; font-size: 11px; }"
            "QDateEdit:disabled { background: #E8DDF8; color: #7A6B91; }")
        date_warning = QLabel("Not a monthliversary — will use the year instead.")
        date_warning.setStyleSheet(
            "color: #C62828; background: transparent; font-size: 9px; font-weight: bold;")
        date_warning.setVisible(False)
        detail_grid.addWidget(date_caption, 0, 4)
        detail_grid.addWidget(date_edit, 1, 4)
        detail_grid.addWidget(date_warning, 2, 4)
        detail_grid.setColumnStretch(5, 1)
        layout.addLayout(detail_grid)

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

        def check_monthliversary():
            chosen = date_edit.date().toPyDate()
            ok = ctx.issue_date is not None and chosen.day == ctx.issue_date.day
            date_warning.setVisible(by_date_btn.isChecked() and not ok)

        year_edit.editingFinished.connect(sync_age_from_year)
        age_edit.editingFinished.connect(sync_year_from_age)
        date_edit.dateChanged.connect(lambda _d: check_monthliversary())

        def refresh_detail():
            adjusting = change_btn.isChecked() or drop_btn.isChecked()
            by_date = by_date_btn.isChecked()
            amount_caption.setEnabled(change_btn.isChecked())
            amount_edit.setEnabled(change_btn.isChecked())
            for widget in (effective_caption, by_year_btn, by_date_btn):
                widget.setEnabled(adjusting)
            for widget in (year_caption, year_edit, age_caption, age_edit):
                widget.setEnabled(adjusting and not by_date)
            for widget in (date_caption, date_edit):
                widget.setEnabled(adjusting and by_date)
            if drop_btn.isChecked():
                amount_edit.set_value(0, decimals=2)
            check_monthliversary()

        for button in (keep_btn, change_btn, drop_btn, by_year_btn, by_date_btn):
            button.toggled.connect(lambda _on: refresh_detail())

        {RiderAdjustment.KEEP: keep_btn,
         RiderAdjustment.CHANGE: change_btn,
         RiderAdjustment.DROP: drop_btn}[adj.action].setChecked(True)
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
        if adj.effective_date is not None:
            by_date_btn.setChecked(True)
            date_edit.setDate(QDate(adj.effective_date.year, adj.effective_date.month,
                                    adj.effective_date.day))
        else:
            by_year_btn.setChecked(True)
            default_date = ctx.forecast_date or ctx.anniversary(ctx.forecast_year)
            if default_date is not None:
                date_edit.setDate(QDate(default_date.year, default_date.month, default_date.day))
        refresh_detail()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(self._BTN.format(bg="#F3ECFC", fg="#4B2383", border="#7E57C2"))
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dlg.exec()

        if drop_btn.isChecked():
            adj.action = RiderAdjustment.DROP
            adj.new_amount = 0.0
        elif change_btn.isChecked():
            adj.action = RiderAdjustment.CHANGE
            adj.new_amount = amount_edit.value()
        else:
            adj.action = RiderAdjustment.KEEP
            adj.new_amount = None
        year = year_edit.value()
        adj.effective_year = int(year) if year is not None else None
        chosen = date_edit.date().toPyDate()
        is_monthliversary = ctx.issue_date is not None and chosen.day == ctx.issue_date.day
        adj.effective_date = chosen if (by_date_btn.isChecked() and is_monthliversary) else None
        self._style_button(self._buttons[key], adj.action, matured=key in self._matured)
        self.changed.emit()

    def collect_changes(self, ctx: PolicyContext) -> list[PolicyChangeEvent]:
        events: list[PolicyChangeEvent] = []
        for key, adj in self._adjustments.items():
            if adj.action == RiderAdjustment.KEEP:
                continue
            # A matured rider/benefit is already out of the engine's coverage
            # set — any keep/change/drop the user clicks is view-only.
            if key in self._matured:
                continue
            when = adj.effective_date
            if when is None and adj.effective_year is not None:
                # Current-year requests land on the forecast date; later
                # years at that year's anniversary.
                when = ctx.effective_date(adj.effective_year)
            if when is None:
                continue
            events.append(PolicyChangeEvent(
                kind=PolicyChangeKind.RIDER_DROP,
                effective_date=when,
                value=float(adj.new_amount or 0.0),
                metadata={"target": key, "action": adj.action},
            ))
        return events

    # ── saved-case capture/apply ──────────────────────────────

    def capture_adjustments(self) -> dict:
        """Non-KEEP rider decisions, keyed like collect_changes (JSON-safe).

        The button label rides along so a later load onto a policy without
        the rider can name it in the warning."""
        out: dict = {}
        for key, adj in self._adjustments.items():
            if adj.action == RiderAdjustment.KEEP:
                continue
            button = self._buttons.get(key)
            out[key] = {
                "action": adj.action,
                "new_amount": adj.new_amount,
                "effective_year": adj.effective_year,
                "effective_date": (
                    adj.effective_date.isoformat() if adj.effective_date else None),
                "label": button.text() if button is not None else key,
            }
        return out

    def apply_adjustments(self, saved: dict) -> list[str]:
        """Restore saved rider decisions onto this policy's riders.

        Every saved decision that has no matching rider here (or whose rider
        has matured) becomes a warning — nothing is silently dropped."""
        warnings: list[str] = []
        for key, adj in self._adjustments.items():
            adj.action = RiderAdjustment.KEEP
            adj.new_amount = None
            adj.effective_year = None
            adj.effective_date = None
            self._style_button(self._buttons[key], RiderAdjustment.KEEP,
                               matured=key in self._matured)
        for key, data in (saved or {}).items():
            label = str(data.get("label") or key)
            action = str(data.get("action") or RiderAdjustment.CHANGE)
            adj = self._adjustments.get(key)
            if adj is None:
                warnings.append(
                    f"Rider decision '{action}' for {label} did not apply — "
                    f"this policy has no matching rider/benefit.")
                continue
            if key in self._matured:
                warnings.append(
                    f"Rider decision '{action}' for {label} did not apply — "
                    f"the rider/benefit has already matured on this policy.")
                continue
            adj.action = action
            amount = data.get("new_amount")
            adj.new_amount = float(amount) if amount is not None else None
            year = data.get("effective_year")
            adj.effective_year = int(year) if year is not None else None
            when = data.get("effective_date")
            adj.effective_date = date.fromisoformat(when) if when else None
            self._style_button(self._buttons[key], adj.action, matured=False)
        self.changed.emit()
        return warnings


class DynamicInputsPanel(QWidget):
    """The "Input" tab: suspended banner, request sections, rider buttons."""

    # GP exception availability for the loaded policy: (available, reason).
    # The Allow GP Exception Premium checkbox lives on the Illustration
    # Control tab (Run Controls); the tab listens to this signal and forces
    # the checkbox off — with the reason as its tooltip — when an active
    # shadow account blocks exceptions.
    exception_availability_changed = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx = PolicyContext()
        # Illustration Control's "Use Policy AG49 Regime": checked illustrates
        # under the regime at policy issue (RERUN CP79 = MAX(2, date tier));
        # unchecked under the current regime.
        self._use_policy_ag49 = False
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

        # Notice shown when GP exception premiums are unavailable (loan / shadow).
        self.exception_notice = QLabel("")
        self.exception_notice.setWordWrap(True)
        self.exception_notice.setStyleSheet(
            "color: #5C3A00; background-color: #FFF4D6; border: 1px solid #D4A017;"
            " border-radius: 4px; padding: 5px 9px; font-size: 11px; font-weight: bold;")
        self.exception_notice.setVisible(False)
        outer.addWidget(self.exception_notice)

        rate_row = QHBoxLayout()
        rate_row.setSpacing(4)
        rate_label = QLabel("Illustrated Rate")
        rate_label.setStyleSheet(_CAPTION_STYLE)
        self.illustrated_rate_edit = _RateField(self)
        rate_suffix = QLabel("%")
        rate_suffix.setStyleSheet(_CAPTION_STYLE)
        # Apply Premium to Loan First (sInput_ApplyPremToLoan): the requested
        # premium repays the policy loan before any of it loads onto the account
        # value. A no-op on a loan-free policy.
        self.apply_prem_to_loan_check = QCheckBox("Apply Premium to Loan First")
        apply_input_checkbox_style(self.apply_prem_to_loan_check)
        self.apply_prem_to_loan_check.setToolTip(
            "Apply the requested premium to repay the policy loan first. The lumpsum "
            "then the scheduled premium repay the loan up to its payoff; only what "
            "remains is loaded onto the account value.")
        # Conform to TAMRA lives on the Input sheet next to Apply Premium to
        # Loan First (moved from the Illustration Control tab). On by default.
        self.tamra_check = QCheckBox("Conform to TAMRA")
        self.tamra_check.setChecked(True)
        apply_input_checkbox_style(self.tamra_check)
        self.tamra_check.setToolTip(
            "Enforce the 7-pay premium room while the policy is inside the TAMRA window.")
        # Lump Sum: a one-off premium the user applies on the forecast date. It
        # runs through the premium-acceptance chain like any unscheduled premium.
        # Disabled while "Lumpsum to Next Premium" solves the bridge instead — the
        # solved amount is then displayed here after a run.
        self.lumpsum_caption = QLabel("Lump Sum")
        self.lumpsum_caption.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;")
        self.lumpsum_edit = _Field(90, decimals=2)
        self.lumpsum_edit.setToolTip(
            "A one-off premium applied on the forecast date, through the premium-"
            "acceptance chain. Disabled while 'Lumpsum to Next Premium' is checked; "
            "the solved bridge amount is shown here after a run.")
        # Lumpsum to Next Premium: when the policy is too thin to coast from the
        # forecast date to its next modal premium, apply a solved lumpsum on the
        # forecast date that carries it in force until that premium is collected.
        self.lumpsum_to_next_check = QCheckBox("Lumpsum to Next Premium")
        apply_input_checkbox_style(self.lumpsum_to_next_check)
        self.lumpsum_to_next_check.setToolTip(
            "If the policy would lapse before its next modal premium, apply a solved "
            "lumpsum on the forecast date that keeps it in force until that premium is "
            "collected. Sized from the surrender-value (or AV-less-loans) shortfall, or "
            "the safety-net gap when lower, then refined on the engine.")
        self.lumpsum_to_next_check.toggled.connect(self._on_lumpsum_to_next_toggled)
        # IUL plans: the Index Allocations dialog computes the blended rate; the
        # Illustrated Rate field becomes its read-only mirror (Blended Effective —
        # RERUN feeds the engine PolicyRates!CH4 = the effective blend). Declared-
        # rate plans keep the editable field and the button greys out (visible,
        # never hidden, per the Not-Applicable convention).
        self.index_alloc_btn = QPushButton("Index Allocations…")
        self.index_alloc_btn.setStyleSheet(_INDEX_ALLOC_BTN_STYLE)
        self.index_alloc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.index_alloc_btn.clicked.connect(self._open_allocations_dialog)
        self.index_alloc_btn.setEnabled(False)
        self.index_alloc_btn.setToolTip("Not applicable — declared-rate product")
        rate_row.addWidget(rate_label)
        rate_row.addWidget(self.illustrated_rate_edit)
        rate_row.addWidget(rate_suffix)
        rate_row.addSpacing(12)
        rate_row.addWidget(self.index_alloc_btn)
        rate_row.addSpacing(24)
        rate_row.addWidget(self.apply_prem_to_loan_check)
        rate_row.addSpacing(16)
        rate_row.addWidget(self.tamra_check)
        rate_row.addStretch(1)
        outer.addLayout(rate_row)

        # The allocations panel lives inside its popup dialog; this widget keeps
        # querying it (blended/problems/sweep min) between openings.
        self.allocations_panel = AllocationsPanel()
        self.allocations_panel.changed.connect(self._on_allocations_changed)
        self._allocations_dialog = AllocationsDialog(self.allocations_panel, self)

        # Transactions: a 2×2 grid spanning the full width — Premiums next to
        # Loans, Withdrawals next to Loan Repayments below — so each gets room
        # for its entry fields.
        self.premium_section = DynamicSection(SectionSpec(
            "Premiums", default_first_row=True, default_span_to_maturity=True,
            auto_adjust_prior_span=True, allow_max_level_premium=True, type_width=150))
        # Lump sum controls live at the top of the Premiums group.
        lumpsum_header = QWidget()
        lumpsum_row = QHBoxLayout(lumpsum_header)
        lumpsum_row.setContentsMargins(0, 0, 0, 8)
        lumpsum_row.setSpacing(4)
        lumpsum_row.addWidget(self.lumpsum_caption)
        lumpsum_row.addWidget(self.lumpsum_edit)
        lumpsum_row.addSpacing(12)
        lumpsum_row.addWidget(self.lumpsum_to_next_check)
        lumpsum_row.addStretch(1)
        self.premium_section.add_header_widget(lumpsum_header)
        # Premium Solve criteria — visible only while a "Solve" premium row is
        # selected. The row's Year/Mode/span say WHEN the premium pays; this
        # group says WHAT it must achieve: a target value, amount, and the
        # beginning-of-year age to reach it at (age 100 → the ending value at
        # attained age 99, month 12).
        self.solve_criteria = QWidget()
        solve_row = QHBoxLayout(self.solve_criteria)
        solve_row.setContentsMargins(0, 6, 0, 0)
        solve_row.setSpacing(4)
        solve_caption = QLabel("Solve for")
        solve_caption.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent;"
            " font-size: 11px; font-weight: bold;")
        self.solve_target_combo = QComboBox()
        self.solve_target_combo.setStyleSheet(_COMBO_STYLE)
        self.solve_target_combo.setFixedWidth(150)
        self.solve_target_combo.setToolTip(
            "The policy value the solved premium must carry to the target "
            "amount at the target age.")
        solve_amount_caption = QLabel("Amount")
        solve_amount_caption.setStyleSheet(_CAPTION_STYLE)
        self.solve_amount_edit = _Field(90, decimals=2)
        self.solve_amount_edit.setToolTip(
            "The ending value to reach — e.g. 1 to just stay positive, or a "
            "target cash value.")
        solve_age_caption = QLabel("At Age")
        solve_age_caption.setStyleSheet(_CAPTION_STYLE)
        self.solve_age_edit = _Field(_W_AGE)
        self.solve_age_edit.setToolTip(
            "Beginning-of-year age the value must be reached at. Solving for "
            "age 100 checks the ending value at attained age 99, end of "
            "policy month 12.")
        solve_row.addWidget(solve_caption)
        solve_row.addSpacing(6)
        solve_row.addWidget(self.solve_target_combo)
        solve_row.addSpacing(10)
        solve_row.addWidget(solve_amount_caption)
        solve_row.addWidget(self.solve_amount_edit)
        solve_row.addSpacing(10)
        solve_row.addWidget(solve_age_caption)
        solve_row.addWidget(self.solve_age_edit)
        solve_row.addStretch(1)
        self.solve_criteria.setVisible(False)
        self.premium_section.add_bottom_widget(self.solve_criteria)
        self.loan_section = DynamicSection(SectionSpec("Loans", default_mode="A"))
        self.withdrawal_section = DynamicSection(SectionSpec(
            "Withdrawals", has_basis=True, default_mode="A"))
        self.repayment_section = DynamicSection(SectionSpec(
            "Loan Repayments", allow_payoff=True))
        # Excess-repayment behavior (apply_excess_repayment_as_premium): what a
        # repayment larger than the loan payoff does with its excess. Two
        # exclusive radio buttons at the top of the group, mirroring the
        # Premiums lumpsum header. "Stop at payoff" is the default — the excess
        # is discarded; "Apply excess as premium" runs it through the
        # acceptance chain instead.
        self.excess_stop_radio = QRadioButton("Stop at payoff")
        self.excess_stop_radio.setToolTip(
            "A loan repayment larger than the loan payoff stops at the payoff — "
            "the excess is discarded.")
        self.excess_apply_radio = QRadioButton("Apply excess as premium")
        self.excess_apply_radio.setToolTip(
            "A loan repayment larger than the loan payoff applies its excess as "
            "premium — it runs through the premium-acceptance chain and gets the "
            "premium load.")
        self._excess_repay_group = QButtonGroup(self)
        self._excess_repay_group.setExclusive(True)
        excess_header = QWidget()
        excess_row = QHBoxLayout(excess_header)
        excess_row.setContentsMargins(0, 0, 0, 8)
        excess_row.setSpacing(0)
        excess_caption = QLabel("Excess Repayment")
        excess_caption.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;")
        excess_row.addWidget(excess_caption)
        for radio in (self.excess_stop_radio, self.excess_apply_radio):
            radio.setStyleSheet(_RADIO_STYLE)
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            self._excess_repay_group.addButton(radio)
            excess_row.addSpacing(10)
            excess_row.addWidget(radio)
        excess_row.addStretch(1)
        self.excess_stop_radio.setChecked(True)   # current-default: stop at payoff
        self.repayment_section.add_header_widget(excess_header)

        transactions = QGridLayout()
        transactions.setHorizontalSpacing(10)
        transactions.setVerticalSpacing(8)
        transactions.addWidget(self.premium_section, 0, 0)
        transactions.addWidget(self.loan_section, 0, 1)
        transactions.addWidget(self.withdrawal_section, 1, 0)
        transactions.addWidget(self.repayment_section, 1, 1)
        transactions.setColumnStretch(0, 1)
        transactions.setColumnStretch(1, 1)
        outer.addLayout(transactions)

        # Policy changes: four compact single-row groups in a line along the
        # bottom. Rate Class / Table Rating carry their "current value" caption.
        self.face_section = DynamicSection(SectionSpec(
            "Face Amount Change", has_span=False, value_caption="New Face"))
        self.dbo_section = DynamicSection(SectionSpec(
            "Death Benefit Option Change", has_span=False, value_caption="New Option",
            value_width=120,
            value_options=[("A", "A — Level"), ("B", "B — Increasing")]))
        self.rateclass_section = DynamicSection(SectionSpec(
            "Rate Class Change", has_span=False, value_caption="New Rate Class",
            value_width=120, value_options=[(c, f"{c} — {label}") for c, label in _RATE_CLASSES]))
        self.table_section = DynamicSection(SectionSpec(
            "Table Rating Change", has_span=False, value_caption="New Table",
            value_width=110,
            value_options=[("0", "0 — Standard")] + [
                (str(n), f"{n} — Table {chr(64 + n)}") for n in range(1, 17)]))
        changes_row = QHBoxLayout()
        changes_row.setSpacing(10)
        changes_row.addWidget(self.face_section, 1)
        changes_row.addWidget(self.dbo_section, 1)
        changes_row.addWidget(self.rateclass_section, 1)
        changes_row.addWidget(self.table_section, 1)
        outer.addLayout(changes_row)

        outer.addStretch(1)

        self.riders_panel = RiderButtonsPanel(self)
        outer.addWidget(self.riders_panel)

        # A level type (Max/Min) on a premium row locks the other sections
        # (Prem to Maturity keeps Face Amount / DB Option changes open).
        self.premium_section.changed.connect(self._on_premium_changed)

    # ── loading ───────────────────────────────────────────────

    def load_from_policy(self, policy, *, has_shadow: bool = False,
                         shadow_ceased: bool = False):
        self._ctx = context_from_policy(policy)
        self._ctx.has_shadow = has_shadow
        self._ctx.shadow_ceased = shadow_ceased
        # A freshly retrieved policy starts with an empty lump sum.
        self.lumpsum_edit.clear()
        for section in (self.premium_section, self.loan_section, self.withdrawal_section,
                        self.repayment_section, self.face_section, self.dbo_section,
                        self.rateclass_section, self.table_section):
            section.set_context(self._ctx)
        # Premium Solve criteria reset for the new policy: fresh target list
        # (shadow only when applicable), cleared amount, age-100 default.
        self.solve_amount_edit.setText("")
        self.solve_age_edit.setText("")
        self._populate_solve_targets()
        self._refresh_solve_group()
        if self._ctx.is_iul:
            plan = load_index_strategies(self._ctx.plancode)
            self.illustrated_rate_edit.setReadOnly(True)
            self.index_alloc_btn.setEnabled(True)
            self.index_alloc_btn.setToolTip(
                "Index strategy allocations and illustrated rates — the blended "
                "rate mirrors into the Illustrated Rate field.")
            self.allocations_panel.set_plan(
                plan, self._ctx.gint, self._ctx.premium_allocations,
                sweep_account_min=self._ctx.sweep_account_min)
            self.allocations_panel.set_ag49_index(self._resolved_ag49_index())
            # set_plan recomputes and _on_allocations_changed mirrors the blend
        else:
            self.allocations_panel.set_plan(None)
            self.index_alloc_btn.setEnabled(False)
            self.index_alloc_btn.setToolTip("Not applicable — declared-rate product")
            self.illustrated_rate_edit.setReadOnly(False)
            self.illustrated_rate_edit.set_rate(self._ctx.illustrated_rate)
        self.riders_panel.set_policy(policy, self._ctx)
        # Reset the lock state + exception notice/checkbox for the freshly loaded
        # policy (the premium section reset to one INPUT row doesn't emit changed).
        self._on_premium_changed()

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

    def illustrated_rate(self) -> float:
        return self.illustrated_rate_edit.rate()

    def sweep_account_min(self) -> Optional[float]:
        """Sweep minimum from the allocations panel (None for non-IUL plans)."""
        return self.allocations_panel.sweep_account_min()

    def iul_declared_rate(self) -> Optional[float]:
        """Fixed-strategy illustrated rate — the engine's WAIR declared rate
        (RERUN UJ). None on declared-rate plans."""
        if not self._ctx.is_iul:
            return None
        return self.allocations_panel.rates().get(FIXED_FUND_ID)

    def iul_asset_charge_rate(self) -> Optional[float]:
        """Blended IP/IR asset-charge rate (RERUN SU) from the allocations
        panel, already re-based on the resolved AG49 regime. None on
        declared-rate plans."""
        if not self._ctx.is_iul:
            return None
        blended = self.allocations_panel.blended()
        return blended.asset_charge_rate if blended is not None else None

    def _open_allocations_dialog(self):
        self._allocations_dialog.exec()

    def _resolved_ag49_index(self) -> int:
        if self._use_policy_ag49:
            return ag49_index_for_issue_date(self._ctx.issue_date)
        return current_ag49_index()

    def set_use_policy_ag49_regime(self, checked: bool):
        """Re-base the allocation blend on the regime at policy issue (checked)
        or the current regime (unchecked)."""
        self._use_policy_ag49 = bool(checked)
        self.allocations_panel.set_ag49_index(self._resolved_ag49_index())

    def _on_allocations_changed(self):
        """Mirror the Blended Effective rate into the read-only rate field."""
        blended = self.allocations_panel.blended()
        if blended is not None and self._ctx.is_iul:
            self.illustrated_rate_edit.set_rate(blended.effective)

    def allocation_problems(self) -> list[str]:
        """Validation messages from the IUL allocation grid (empty for non-IUL)."""
        if not self._ctx.is_iul:
            return []
        return self.allocations_panel.problems()

    def lumpsum_to_next_enabled(self) -> bool:
        return self.lumpsum_to_next_check.isChecked()

    def excess_repayment_as_premium(self) -> bool:
        """Excess-repayment radio state — True when the excess of a loan
        repayment over the payoff is applied as premium (default: stop at
        payoff, the excess is discarded)."""
        return self.excess_apply_radio.isChecked()

    def _on_lumpsum_to_next_toggled(self, checked: bool):
        # Solving the bridge owns the lump sum: disable the manual field while
        # checked, and clear it on either toggle — a stale figure never rides
        # along, and unchecking discards the solved amount just shown.
        self.lumpsum_edit.setEnabled(not checked)
        self.lumpsum_edit.clear()

    def manual_lumpsum(self) -> Optional[float]:
        """The typed lump sum, or None while the bridge solver owns it."""
        if self.lumpsum_to_next_check.isChecked():
            return None
        return self.lumpsum_edit.value()

    def set_lumpsum_amount(self, value: Optional[float]):
        """Display the solved bridge lumpsum after a run (field stays disabled)."""
        self.lumpsum_edit.set_value(value, decimals=2)

    # ── Level-premium types (Max Level / Prem to Maturity) ────

    def active_level_premium_type(self) -> Optional[str]:
        """The level type selected on any premium row, or None."""
        for row in self.premium_section.rows():
            if row.premium_type() in _LEVEL_TYPES:
                return row.premium_type()
        return None

    def min_level_request(self) -> Optional[dict]:
        """``{'start_year', 'mode'}`` for the Prem to Maturity row, or None.

        The row has no amount until the run solves it, so main_window detects it
        here and solves on the projectable policy. On GPT policies GP exception
        premiums are always allowed for this premium type — the solve (and its
        displayed run) ignores the Allow GP Exception Premium checkbox. CVAT
        policies solve with exceptions off (no guideline cap to ride).
        """
        if self._ctx is None:
            return None
        for row in self.premium_section.rows():
            if row.is_min_level():
                year = row.year() or self._ctx.forecast_year
                return {"start_year": int(year), "mode": row.mode()}
        return None

    def set_min_level_amount(self, value: Optional[float]):
        """Fill the Prem to Maturity row's (disabled) amount field after a run."""
        for row in self.premium_section.rows():
            if row.is_min_level():
                row.set_amount_display(value)
                return

    def shadow_level_request(self) -> Optional[dict]:
        """``{'start_year', 'mode'}`` for the Prem to Shadow Maturity row, or None.

        Solved on Run Values against the shadow account's own lapse test. The
        run validates the shadow state (an existing-but-ceased type-A benefit
        can't be solved) and reports why when it can't run.
        """
        if self._ctx is None:
            return None
        for row in self.premium_section.rows():
            if row.is_shadow_level():
                year = row.year() or self._ctx.forecast_year
                return {"start_year": int(year), "mode": row.mode()}
        return None

    def set_shadow_level_amount(self, value: Optional[float]):
        """Fill the Prem to Shadow Maturity row's (disabled) amount field after a run."""
        for row in self.premium_section.rows():
            if row.is_shadow_level():
                row.set_amount_display(value)
                return

    def max_level_request(self) -> Optional[dict]:
        """``{'start_year', 'mode'}`` for the Max Level row, or None.

        The row shows a closed-form estimate from the current guideline room,
        but the authoritative amount is solved on Run Values against the real
        projection — the cumulative guideline allowance chain, including any
        Face Amount / DB Option change's effect on GLP/GSP mid-projection —
        so main_window detects the row here and solves on the projectable
        policy, then fills the display.
        """
        if self._ctx is None or self._ctx.is_cvat:
            return None
        for row in self.premium_section.rows():
            if row.is_max_level():
                year = row.year() or self._ctx.forecast_year
                return {"start_year": int(year), "mode": row.mode()}
        return None

    def set_max_level_amount(self, value: Optional[float]):
        """Fill the Max Level row's (read-only) amount field after a run."""
        for row in self.premium_section.rows():
            if row.is_max_level():
                row.set_amount_display(value)
                return

    def monthly_deduction_windows(self) -> list[tuple[int, Optional[int]]]:
        """Year windows for the active Monthly Deduction premium rows.

        One ``(start_year, end_year)`` per Monthly Deduction row — the same
        year window (start through For Years / To Age) any other premium row
        carries — sorted by start year, empty when there is no such row. The
        premium is solved in-engine each month within its window; once the
        window ends the following premium rows apply normally.
        """
        ctx = self._ctx
        if ctx is None:
            return []
        windows: list[tuple[int, Optional[int]]] = []
        for row in self.premium_section.rows():
            if not row.is_monthly_deduction():
                continue
            start = row.year() or ctx.forecast_year
            end = row.end_year()
            windows.append((int(start), int(end) if end is not None else None))
        windows.sort(key=lambda window: window[0])
        return windows

    def billable_to_md_windows(self) -> list[tuple[int, Optional[int]]]:
        """Year windows for the active "Billable to MD" premium rows.

        Same shape as :meth:`monthly_deduction_windows`. Within a window the
        row's billable premium pays as a normal scheduled premium; the engine
        switches to the Monthly Deduction premium (then GP exceptions) the
        first month the billable premium can no longer keep the policy in
        force. The presence of any window also forces GP exceptions on for
        the run — the whole point of the mode is to reach the exception phase.
        """
        ctx = self._ctx
        if ctx is None:
            return []
        windows: list[tuple[int, Optional[int]]] = []
        for row in self.premium_section.rows():
            if not row.is_billable_to_md():
                continue
            start = row.year() or ctx.forecast_year
            end = row.end_year()
            windows.append((int(start), int(end) if end is not None else None))
        windows.sort(key=lambda window: window[0])
        return windows

    def loan_payoff_requests(self) -> list[dict]:
        """The Pay-off rows in the Loan Repayments section, ready to solve.

        One dict per row, sorted by start year so main_window can solve them
        chronologically (an earlier payoff's repayments — and any new loans
        between windows — feed the later window's balance):
        ``{'start_year', 'end_year', 'mode', 'dates', 'check_date'}`` where
        ``dates`` are the expanded modal repayment dates (forecast-clamped like
        any repayment row) and ``check_date`` is the anniversary ending the
        window — where the solver requires the loan balance to be zero, just
        before any new loan that month.
        """
        ctx = self._ctx
        if (ctx is None or self.active_level_premium_type() is not None
                or self.repayment_section.has_overlap()):
            return []
        out = []
        for row in self.repayment_section.rows():
            if not row.is_payoff() or row.year() is None:
                continue
            end_year = row.end_year() or row.year()
            entry = {"year": row.year(), "end_year": end_year,
                     "amount": 1.0, "mode": row.mode()}
            dates = [t.effective_date for t in
                     self._expand_dated([entry], TransactionKind.LOAN_REPAYMENT)]
            if not dates:
                continue
            out.append({
                "start_year": row.year(), "end_year": end_year,
                "mode": row.mode(), "dates": dates,
                "check_date": ctx.anniversary(end_year + 1),
            })
        out.sort(key=lambda request: request["start_year"])
        return out

    def set_loan_payoff_amounts(self, values: list):
        """Fill the Pay-off rows' (disabled) amount fields after a run.

        ``values`` line up with :meth:`loan_payoff_requests` — start-year order.
        """
        rows = [row for row in self.repayment_section.rows()
                if row.is_payoff() and row.year() is not None]
        rows.sort(key=lambda row: row.year())
        for row, value in zip(rows, values):
            row.set_amount_display(value)

    def _on_premium_changed(self):
        # Level types lock the non-premium inputs, but not uniformly:
        #   • Max Level / Prem to Maturity lock ONLY new loans —
        #     withdrawals, loan repayments, and rate-class / table changes
        #     stay editable and feed the solve (a withdrawal, downgrade or
        #     rating change moves the funding the solve measures).
        #   • Prem to Shadow Maturity keeps the full lock (all five below).
        # Both keep the Face Amount / DB Option changes AND the riders/benefits
        # open in every case — clients want to see how a face reduction, DBO
        # switch, or rider drop moves the solved premium. (A face/DBO/rider/
        # rate-class/table change OR a withdrawal after the forecast date under
        # Max Level / Prem to Maturity raises the caveat strip — the inputs tab
        # watches those sections too.) The exception availability is refreshed,
        # and the Premium Solve criteria group shows only while a Solve row is
        # selected.
        self._apply_section_locks()
        self._refresh_exception_availability()
        self._refresh_solve_group()

    def _refresh_exception_availability(self):
        # An active shadow account blocks GP exceptions (the shadow account
        # governs lapse, not the exception premium). A policy loan no longer
        # blocks them — premium is applied to the loan first, so the policy can
        # ride the GLP exception period with a loan outstanding. A Monthly
        # Deduction premium does NOT block it — the two work together: the MD
        # premium funds the deduction up to the guideline limit, and the GP
        # exception is the backstop once the policy caps out and runs negative.
        # The Allow GP Exception Premium checkbox itself lives on the
        # Illustration Control tab; the panel shows the notice here and signals
        # the tab, which forces the checkbox off while blocked.
        ctx = self._ctx
        if ctx is not None and ctx.has_shadow:
            reason = "Allow Exceptions is not available due to an active shadow account."
        else:
            reason = ""
        self.exception_notice.setText(reason)
        self.exception_notice.setVisible(bool(reason))
        self.exception_availability_changed.emit(not reason, reason)

    def _selected_level_types(self) -> set[str]:
        """The level premium types selected across the premium rows."""
        return {row.premium_type() for row in self.premium_section.rows()
                if row.premium_type() in _LEVEL_TYPES}

    # ── Premium Solve (target-value) ──────────────────────────

    def _refresh_solve_group(self):
        self.solve_criteria.setVisible(
            any(row.is_solve() for row in self.premium_section.rows()))

    def _populate_solve_targets(self):
        """(Re)build the Solve-for combo for the loaded policy — the shadow
        target appears only on a policy with an active shadow account."""
        current = self.solve_target_combo.currentData()
        self.solve_target_combo.blockSignals(True)
        self.solve_target_combo.clear()
        self.solve_target_combo.addItem("Account Value", "av")
        self.solve_target_combo.addItem("Surrender Value", "sv")
        if self._ctx is not None and self._ctx.has_shadow:
            self.solve_target_combo.addItem("Shadow Account Value", "shadow")
        index = self.solve_target_combo.findData(current)
        self.solve_target_combo.setCurrentIndex(max(0, index))
        self.solve_target_combo.blockSignals(False)
        # Default target age: the age-100 checkpoint (or maturity if sooner).
        if self._ctx is not None and self.solve_age_edit.value() is None:
            self.solve_age_edit.set_value(min(100, self._ctx.maturity_age))

    def solve_request(self) -> Optional[dict]:
        """The Solve row's request for Run Values, or None.

        ``{'start_year', 'end_year', 'mode', 'target', 'amount', 'at_age'}`` —
        year/mode/span from the premium row (span None → pays to maturity),
        target criteria from the Premium Solve group. ``amount``/``at_age``
        may be None when the user left them blank; the window validates and
        reports rather than solving on a guess.
        """
        if self._ctx is None:
            return None
        for row in self.premium_section.rows():
            if not row.is_solve():
                continue
            year = row.year() or self._ctx.forecast_year
            end_year = row.end_year()
            if end_year is not None and end_year >= self._ctx.maturity_year:
                end_year = None                    # to maturity → no stop row
            amount = self.solve_amount_edit.value()
            age = self.solve_age_edit.value()
            return {
                "start_year": int(year),
                "end_year": int(end_year) if end_year is not None else None,
                "mode": row.mode(),
                "target": self.solve_target_combo.currentData() or "av",
                "amount": float(amount) if amount is not None else None,
                "at_age": int(age) if age is not None else None,
            }
        return None

    def set_solve_amount(self, value: Optional[float]):
        """Fill the Solve row's (read-only) amount field after a run."""
        for row in self.premium_section.rows():
            if row.is_solve():
                row.set_amount_display(value)
                return

    def _apply_section_locks(self):
        # Lock the non-premium input sections per the active level type. The
        # Face Amount / DB Option change sections and the riders panel are
        # never locked here (they stay editable under every level type so the
        # solves can reflect them — they alter the guideline premiums that
        # bound Max Level and the funding need behind Prem to Maturity).
        #   • No level type: everything below is editable.
        #   • Max Level / Prem to Maturity: lock ONLY new loans;
        #     withdrawals, loan repayments, rate-class and table changes feed
        #     the solve, so they stay editable.
        #   • Prem to Shadow Maturity (or it mixed with another level type):
        #     lock all five — the shadow solve honors only the premium rows
        #     plus face/DBO/riders.
        types = self._selected_level_types()
        lock_all = _TYPE_SHADOW_LEVEL in types
        lock_loans = bool(types)          # any level type locks new loans
        self.loan_section.setEnabled(not lock_loans)
        for section in (self.withdrawal_section, self.repayment_section,
                        self.rateclass_section, self.table_section):
            section.setEnabled(not lock_all)

    # ── saved-case capture/apply ──────────────────────────────

    def _case_sections(self) -> dict[str, DynamicSection]:
        return {
            "premiums": self.premium_section,
            "loans": self.loan_section,
            "withdrawals": self.withdrawal_section,
            "repayments": self.repayment_section,
            "face": self.face_section,
            "dbo": self.dbo_section,
            "rateclass": self.rateclass_section,
            "table": self.table_section,
        }

    def capture_state(self) -> dict:
        """JSON-safe snapshot of the whole Input panel (saved-case payload)."""
        state: dict = {
            "illustrated_rate": self.illustrated_rate_edit.text(),
            "lumpsum": self.lumpsum_edit.text(),
            "lumpsum_to_next": self.lumpsum_to_next_check.isChecked(),
            "apply_prem_to_loan": self.apply_prem_to_loan_check.isChecked(),
            "tamra": self.tamra_check.isChecked(),
            "excess_repayment_as_premium": self.excess_apply_radio.isChecked(),
            "sections": {
                name: section.capture_rows()
                for name, section in self._case_sections().items()
            },
            "riders": self.riders_panel.capture_adjustments(),
            "solve": {
                "target": self.solve_target_combo.currentData() or "av",
                "amount": self.solve_amount_edit.text(),
                "at_age": self.solve_age_edit.text(),
            },
        }
        if self._ctx.is_iul:
            state["allocations"] = {
                "allocations": self.allocations_panel.allocations(),
                "rates": self.allocations_panel.rates(),
                "sweep_min": self.allocations_panel.sweep_account_min(),
            }
        return state

    def apply_state(self, state: dict) -> list[str]:
        """Apply a saved case's Input-panel snapshot onto the loaded policy.

        Call after ``load_from_policy`` so the rows resolve against the current
        policy's context. Returns warnings for every piece that did not apply
        (missing riders, unavailable premium types, non-IUL allocations…)."""
        warnings: list[str] = []
        # Lumpsum-to-next first — its toggle clears/disables the manual field.
        self.lumpsum_to_next_check.setChecked(bool(state.get("lumpsum_to_next")))
        if not self.lumpsum_to_next_check.isChecked():
            self.lumpsum_edit.setText(str(state.get("lumpsum") or ""))
        self.apply_prem_to_loan_check.setChecked(
            bool(state.get("apply_prem_to_loan")))
        self.tamra_check.setChecked(bool(state.get("tamra", True)))
        (self.excess_apply_radio
         if state.get("excess_repayment_as_premium")
         else self.excess_stop_radio).setChecked(True)

        sections = state.get("sections") or {}
        for name, section in self._case_sections().items():
            warnings.extend(section.apply_rows(sections.get(name) or []))
        warnings.extend(
            self.riders_panel.apply_adjustments(state.get("riders") or {}))

        # Premium Solve criteria (after the premium rows so the group's
        # visibility reflects the applied Solve row). A saved shadow target
        # that this policy can't offer falls back to Account Value — loudly.
        solve = state.get("solve") or {}
        if solve:
            self.solve_amount_edit.setText(str(solve.get("amount") or ""))
            self.solve_age_edit.setText(str(solve.get("at_age") or ""))
            target = str(solve.get("target") or "av")
            index = self.solve_target_combo.findData(target)
            if index >= 0:
                self.solve_target_combo.setCurrentIndex(index)
            elif target == "shadow":
                self.solve_target_combo.setCurrentIndex(0)
                warnings.append(
                    "Premium Solve target 'Shadow Account Value' did not "
                    "apply — this policy has no active shadow account; "
                    "using Account Value instead.")
        self._refresh_solve_group()

        alloc_state = state.get("allocations")
        if alloc_state:
            # On an IUL plan the Illustrated Rate is the read-only mirror of
            # the blend — apply_state recomputes it. On a declared-rate plan
            # this warns (nothing to apply the allocations to).
            warnings.extend(self.allocations_panel.apply_state(
                alloc_state.get("allocations"),
                alloc_state.get("rates"),
                alloc_state.get("sweep_min")))
        if not self._ctx.is_iul:
            rate_text = str(state.get("illustrated_rate") or "")
            if rate_text:
                self.illustrated_rate_edit.setText(rate_text)
        elif not alloc_state:
            warnings.append(
                "The case carries no index allocations (it was saved on a "
                "declared-rate policy) — this IUL policy keeps its current "
                "allocation grid.")

        # Refresh the level-type section locks and exception availability for
        # the restored premium rows.
        self._on_premium_changed()
        return warnings

    # ── export ────────────────────────────────────────────────

    def _expand_dated(self, entries: list[dict], kind: TransactionKind,
                      on_due_dates: bool = False) -> list[DatedTransaction]:
        """Year/mode rows -> dated monthliversary transactions (the compiler
        only schedules premiums and loans by year).

        Within the CURRENT policy year the grid starts at the forecast date —
        the year's anniversary is already behind us.

        ``on_due_dates`` keeps transactions on their natural due dates
        (anniversary plus each modal interval) and simply drops the ones that
        fall before the forecast date, instead of clamping the first one onto
        the forecast date. Premiums use this so an already-billed payment in
        the current policy year (e.g. an annual premium due on a past
        anniversary) is not re-applied on the forecast date.
        """
        ctx = self._ctx
        out: list[DatedTransaction] = []
        for entry in entries:
            if not entry["amount"]:
                continue
            # Withdrawal rows carry a Net/Gross basis; it rides along on the
            # transaction subtype ("net" | "gross", "" for kinds without one).
            subtype = entry.get("basis") or ""
            # Per-entry metadata (e.g. the Billable-to-MD tag) rides along on
            # every transaction the entry expands to.
            entry_meta = dict(entry.get("metadata") or {})
            entry_meta.setdefault("mode", entry["mode"])
            interval = _MODE_INTERVALS.get(entry["mode"], 12)
            for year in range(entry["year"], (entry["end_year"] or entry["year"]) + 1):
                anniversary = ctx.anniversary(year)
                next_anniversary = ctx.anniversary(year + 1)
                if anniversary is None or next_anniversary is None:
                    continue
                when = anniversary
                if not on_due_dates and ctx.forecast_date is not None and when < ctx.forecast_date:
                    when = ctx.forecast_date
                while when < next_anniversary:
                    if on_due_dates and ctx.forecast_date is not None and when < ctx.forecast_date:
                        when = when + relativedelta(months=interval)
                        continue
                    out.append(DatedTransaction(
                        kind=kind, effective_date=when, amount=float(entry["amount"]),
                        subtype=subtype, metadata=dict(entry_meta)))
                    when = when + relativedelta(months=interval)
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

    def _split_current_year(self, entries: list[dict]) -> tuple[list[dict], list[dict]]:
        """Split spans touching the CURRENT policy year out for dated handling.

        The current year's anniversary is in the past, so a year-schedule
        would never pay this year — its payments are expanded to dated
        monthliversary transactions from the forecast date instead; the rest
        of the span stays a schedule from next year on.
        """
        ctx = self._ctx
        dated: list[dict] = []
        scheduled: list[dict] = []
        for entry in entries:
            start = entry["year"]
            end = entry["end_year"] or start
            if start <= ctx.forecast_year:
                dated.append({**entry, "year": start, "end_year": min(end, ctx.forecast_year)})
                if end > ctx.forecast_year:
                    scheduled.append({**entry, "year": ctx.forecast_year + 1, "end_year": end})
            else:
                scheduled.append(entry)
        return dated, scheduled

    def collect_into(self, input_set: IllustrationInputSet):
        ctx = self._ctx
        md_active = bool(self.monthly_deduction_windows())
        # Level rows (Max/Min/Shadow) are solved on Run Values — the Max Level
        # row's displayed amount is only a closed-form estimate — and Monthly
        # Deduction rows are solved in-engine, so all four are excluded here.
        # main_window solves the level premiums separately and layers them in;
        # the engine pays Monthly Deduction from a run option.
        # "Solve" rows are excluded like the level rows: their amount field
        # holds the PREVIOUS run's solved display value, and main_window
        # layers the freshly solved premium in — collecting it here would
        # double-pay it.
        prem_entries = [
            e for e in self.premium_section.entries()
            if e["amount"] is not None
            and e.get("type") not in (
                _TYPE_MAX_LEVEL, _TYPE_MIN_LEVEL, _TYPE_SHADOW_LEVEL,
                _TYPE_MONTHLY_DEDUCTION, _TYPE_SOLVE)
        ]
        # A "Billable to MD" row pays real scheduled premiums like any INPUT
        # row; the tag lets the compiler mark its dated (current-year)
        # payments so the engine can stop them once the MD hand-off latches.
        # (Post-switch scheduled premiums are suppressed by the row's year
        # window — billable_to_md_windows on the run options.)
        for entry in prem_entries:
            if entry.get("type") == _TYPE_BILLABLE_TO_MD:
                entry["metadata"] = {"billable_to_md": True}
        dated_prem, sched_prem = self._split_current_year(prem_entries)
        if prem_entries or md_active:
            # Any premium input REPLACES the billed default from the forecast
            # year on: silence billing with a zero schedule, then layer the
            # requested premiums (dated this year, schedules after). A Monthly
            # Deduction premium pays only the deduction, so it silences the
            # default modal billing too.
            input_set.scheduled_transactions.append(ScheduledTransaction(
                kind=TransactionKind.PREMIUM, policy_year=ctx.forecast_year,
                amount=0.0, mode="A"))
        input_set.dated_transactions.extend(
            self._expand_dated(dated_prem, TransactionKind.PREMIUM, on_due_dates=True))
        input_set.scheduled_transactions.extend(
            self._scheduled(sched_prem, TransactionKind.PREMIUM))

        # Manual lump sum: a one-off premium applied on the forecast date, through
        # the acceptance chain. The bridge solver owns it while 'Lumpsum to Next
        # Premium' is checked, so manual_lumpsum() returns None in that case.
        lumpsum = self.manual_lumpsum()
        if lumpsum and ctx.forecast_date is not None:
            input_set.dated_transactions.append(DatedTransaction(
                kind=TransactionKind.PREMIUM, effective_date=ctx.forecast_date,
                amount=float(lumpsum), subtype="manual_lumpsum"))

        # Level premium types honor the Face Amount / DB Option change sections
        # AND the riders panel (all stay enabled so the solved premium reflects
        # the entered policy changes — a face reduction, DBO switch, or rider
        # drop moves the guideline premiums that bound Max Level and the funding
        # need behind Prem to Maturity); the solvers carry the input set's
        # policy_changes into every projection they run.
        #   • Prem to Shadow Maturity keeps its full lock — only the face/DBO
        #     changes and riders feed it (nothing else is editable).
        #   • Max Level / Prem to Maturity additionally honor the now-
        #     editable withdrawals, loan repayments, and rate-class / table
        #     changes — but NEVER a new loan (that section stays locked). Pay-off
        #     repayment rows are still excluded here (unsolved under a level type).
        types = self._selected_level_types()
        if _TYPE_SHADOW_LEVEL in types:
            self._collect_face_dbo_changes(input_set)
            input_set.policy_changes.extend(self.riders_panel.collect_changes(ctx))
            return
        # No level type -> new loans are honored too; Max/Min level -> excluded.
        self._collect_side_inputs(input_set, include_loans=not types)

    def _collect_side_inputs(self, input_set: IllustrationInputSet, *,
                             include_loans: bool):
        """Withdrawals, loan repayments, face/DBO/rate-class/table changes and
        riders -> the exported input set.

        Shared by the normal export and the Max Level / Prem to Maturity
        level solves. Those two level types honor every side input EXCEPT new
        loans, so ``include_loans`` gates only the new-loan schedule. Pay-off
        repayment rows are always excluded — main_window solves and layers them
        (and never solves them under a level type)."""
        ctx = self._ctx
        if include_loans:
            loan_entries = [e for e in self.loan_section.entries()
                            if e["amount"] is not None]
            dated_loan, sched_loan = self._split_current_year(loan_entries)
            input_set.dated_transactions.extend(
                self._expand_dated(dated_loan, TransactionKind.LOAN))
            input_set.scheduled_transactions.extend(
                self._scheduled(sched_loan, TransactionKind.LOAN,
                                metadata={"loan_type": "fixed"}))
        input_set.dated_transactions.extend(
            self._expand_dated(self.withdrawal_section.entries(),
                               TransactionKind.WITHDRAWAL))
        repay_entries = [e for e in self.repayment_section.entries()
                         if e.get("type") != _TYPE_PAYOFF]
        input_set.dated_transactions.extend(
            self._expand_dated(repay_entries, TransactionKind.LOAN_REPAYMENT))

        self._collect_face_dbo_changes(input_set)
        for entry in self.rateclass_section.entries():
            when = ctx.effective_date(entry["year"])
            if when is not None and entry["value"]:
                input_set.policy_changes.append(PolicyChangeEvent(
                    kind=PolicyChangeKind.RATE_CLASS, effective_date=when,
                    value=entry["value"]))
        for entry in self.table_section.entries():
            when = ctx.effective_date(entry["year"])
            if when is not None and entry["value"] is not None:
                input_set.policy_changes.append(PolicyChangeEvent(
                    kind=PolicyChangeKind.SUBSTANDARD, effective_date=when,
                    value=int(entry["value"])))
        input_set.policy_changes.extend(self.riders_panel.collect_changes(ctx))

    def _collect_face_dbo_changes(self, input_set: IllustrationInputSet):
        """Face Amount / DB Option change rows -> policy-change events.

        Shared by the normal export and the level-premium paths (both Max
        Level Allowed and Prem to Maturity keep these two sections editable)."""
        ctx = self._ctx
        for entry in self.face_section.entries():
            when = ctx.effective_date(entry["year"])
            if when is not None and entry["amount"]:
                input_set.policy_changes.append(PolicyChangeEvent(
                    kind=PolicyChangeKind.FACE_AMOUNT, effective_date=when,
                    value=float(entry["amount"])))
        for entry in self.dbo_section.entries():
            when = ctx.effective_date(entry["year"])
            if when is not None and entry["value"]:
                input_set.policy_changes.append(PolicyChangeEvent(
                    kind=PolicyChangeKind.DB_OPTION, effective_date=when,
                    value=entry["value"]))
