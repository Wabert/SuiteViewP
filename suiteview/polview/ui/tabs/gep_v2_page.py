"""Policy Support > GEP v2: Max and Min premium-schedule projections.

The page renders :mod:`suiteview.polview.services.gep_v2`. That service pays a
premium on each anniversary before the target and on the target monthliversary,
and nothing in between. The ledgers show each projection month by month (Max,
Min w Forceouts, Min No outs), with the premium-date rows in bold. The
Calculation Summary is two compact blocks: each scenario's premium, target AV
before MD and forceouts on the left; the GEP exception, current/new AccumGLP and
premium to the target date (with and without forceouts) on the right. The GLP
Exception page is separate and unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

from suiteview.core.excel_export import ExcelExportError, dump_to_new_workbook, write_table
from suiteview.illustration.ui.values_overview import LEDGER_COLUMNS, monthly_ledger_cells
from suiteview.ui.tokens import STATUS_ERROR

from ...services.gep_v2 import (
    MAX_PREMIUM_LABEL,
    MIN_FORCEOUTS_LABEL,
    MIN_NO_OUTS_LABEL,
    GepV2Result,
    GepV2Scenario,
    project_gep_v2,
)
from ...services.glp_exception import check_forecast_availability, is_glp_exception_eligible
from ..styles import GRAY_DARK, GRAY_TEXT, GREEN_DARK, POLICY_INFO_FRAME_STYLE, WHITE
from ..widgets import CopyableLabel, FixedHeaderTableWidget
from .policy_support_config import (
    _ACTION_BTN_STYLE,
    _FILTER_INPUT_STYLE,
    _GLP_FORECAST_TABS_STYLE,
    _STATUS_STYLE,
)

AV_BEFORE_MD_COLUMN = "AV bf MD"
# The shared RERUN ledger plus the target test value, placed just before MD.
GEP_V2_COLUMNS = (
    LEDGER_COLUMNS[:LEDGER_COLUMNS.index("MD")]
    + [AV_BEFORE_MD_COLUMN]
    + LEDGER_COLUMNS[LEDGER_COLUMNS.index("MD"):]
)
SUMMARY_COLUMNS = ["Item", "Amount"]
GEP_EXCEPTION_LABEL = "GEP Exception Required"
ACCUM_GLP_LABEL = "AccumGLP"
PREMIUM_TO_TARGET_LABEL = "Premium to Target Date"
PREM_ITEM = "Prem"
AV_ITEM = "AV bf MD"
FORCEOUTS_ITEM = "Force outs"
WITH_FORCEOUTS_ITEM = "With Forceouts"
WITHOUT_FORCEOUTS_ITEM = "Without Forceouts"
CURRENT_ITEM = "Current"
NEW_ITEM = "New"
# Ledger tab order; export sheets follow it.
SCENARIO_TABS = (MAX_PREMIUM_LABEL, MIN_FORCEOUTS_LABEL, MIN_NO_OUTS_LABEL)
NOT_REQUIRED_TEXT = "Not required"
INELIGIBLE_TEXT = "GEP v2 is available only for UL policies using Guideline Premium."
NOTE_TEXT = (
    "A premium is paid on each policy anniversary before the target date and on the "
    "target date itself; nothing is paid in between, and the account value may go "
    "negative without lapsing. The policy makes a premium date if the account value "
    "after that premium and before that day's monthly deduction is not negative. "
    "Each Max premium is what the GPT limit allows as if received just before its date, "
    "so that anniversary's new GLP does not count (earlier anniversaries' GLP does), and "
    "forceouts apply. Each Min premium is the least needed for its date, without the "
    "guideline limit ($0 if none is needed): Min w Forceouts takes every guideline "
    "forceout in full, even when it drives the account value negative (its own premiums "
    "are never forced out); Min No outs suppresses forceouts, as if a negative GLP were "
    "zero. The TAMRA 7-pay limit is not enforced; a resulting MEC is flagged."
)
_TAB_TOOLTIPS = (
    "On each premium date, pays what the GPT limit allows just before that date "
    "(the ending policy year's limit on an anniversary).",
    "On each premium date, pays the least premium that keeps the policy in force with "
    "guideline forceouts taken in full, even when they drive the account value negative.",
    "On each premium date, pays the least premium that keeps the policy in force with "
    "guideline forceouts suppressed (a negative GLP treated as zero).",
)
_EXPORT_SHEETS = ("Max Premium", "Min Prem w Forceouts", "Min Prem No outs")
_EMPHASIS_COLUMNS = (AV_BEFORE_MD_COLUMN, "Prem")


def ledger_cells(state, previous_withdrawals: float) -> list[str]:
    """One GEP v2 ledger row: the shared monthly cells plus AV before MD."""
    cells = monthly_ledger_cells(state, previous_withdrawals)
    index = GEP_V2_COLUMNS.index(AV_BEFORE_MD_COLUMN)
    av_before_md = float(state.guideline_av_before_monthly_deduction or 0.0)
    return cells[:index] + [f"{av_before_md:,.2f}"] + cells[index:]


def scenario_ledger_rows(scenario: GepV2Scenario) -> list[list[str]]:
    rows = []
    previous_withdrawals = scenario.states[0].withdrawals_to_date if scenario.states else 0.0
    for state in scenario.states:
        rows.append(ledger_cells(state, previous_withdrawals))
        previous_withdrawals = state.withdrawals_to_date
    return rows


def _money(value: float) -> str:
    return f"-${-value:,.2f}" if value < 0 else f"${value:,.2f}"


@dataclass(frozen=True)
class SummaryItem:
    """One ``label = value`` pair on a Calculation Summary line.

    ``alert`` is True when the value is a required action (an exception premium
    or an AccumGLP increase) and ``muted`` when it reads "Not required".
    """

    label: str
    text: str
    tooltip: str = ""
    alert: bool = False
    muted: bool = False


@dataclass(frozen=True)
class SummaryLine:
    label: str
    items: tuple[SummaryItem, ...]


def _exception_item(label: str, required: float, tooltip: str) -> SummaryItem:
    if required > 0.0:
        return SummaryItem(label, _money(required), tooltip, alert=True)
    return SummaryItem(label, NOT_REQUIRED_TEXT, tooltip, muted=True)


def summary_blocks(result: GepV2Result) -> tuple[tuple[SummaryLine, ...], tuple[SummaryLine, ...]]:
    """The Calculation Summary as two side-by-side blocks of lines.

    Left: each scenario's total premium and target-date AV before MD (plus
    the forceouts taken on Min w Forceouts). Right: the GEP exception with and
    without forceouts, the current and new AccumGLP, and the premium needed to
    reach the target date with and without forceouts.
    """
    av_tip = "Account value on the target date after its premium, before its monthly deduction"

    def scenario_line(scenario: GepV2Scenario, *extra: SummaryItem) -> SummaryLine:
        return SummaryLine(scenario.label, (
            SummaryItem(PREM_ITEM, _money(scenario.total_premium),
                        "Total premium paid on the premium dates"),
            SummaryItem(AV_ITEM, _money(scenario.target_av_before_md), av_tip),
            *extra,
        ))

    forced = result.min_premium_forceouts
    left = (
        scenario_line(result.max_premium),
        scenario_line(forced, SummaryItem(
            FORCEOUTS_ITEM, _money(forced.total_forceouts),
            "Guideline forceouts taken through the target date, even below a zero AV")),
        scenario_line(result.min_premium_no_outs),
    )
    exception_tip = "Min Prem {} total less the Max Premium Projection total"
    increased = result.new_accum_glp > result.current_accum_glp
    right = (
        SummaryLine(GEP_EXCEPTION_LABEL, (
            _exception_item(WITH_FORCEOUTS_ITEM, result.gep_exception_forceouts,
                            exception_tip.format("w Forceouts")),
            _exception_item(WITHOUT_FORCEOUTS_ITEM, result.gep_exception_no_outs,
                            exception_tip.format("No outs")),
        )),
        SummaryLine(ACCUM_GLP_LABEL, (
            SummaryItem(CURRENT_ITEM, _money(result.current_accum_glp),
                        "AccumGLP on the quote's opening date"),
            SummaryItem(NEW_ITEM, _money(result.new_accum_glp),
                        "Current AccumGLP + GEP Exception Required with forceouts",
                        alert=increased),
        )),
        SummaryLine(PREMIUM_TO_TARGET_LABEL, (
            SummaryItem(WITH_FORCEOUTS_ITEM, _money(forced.total_premium),
                        "Min Prem w Forceouts: total premium through the target date"),
            SummaryItem(WITHOUT_FORCEOUTS_ITEM,
                        _money(result.min_premium_no_outs.total_premium),
                        "Min Prem No outs: total premium through the target date"),
        )),
    )
    return left, right


def summary_rows(result: GepV2Result) -> list[list[str]]:
    """The Calculation Summary flattened to ``[item, amount]`` rows for export."""
    left, right = summary_blocks(result)
    return [
        [f"{line.label}: {item.label}", item.text]
        for line in (*left, *right) for item in line.items
    ]


def basis_text(result: GepV2Result) -> str:
    """One line naming the quote basis: target, premium dates and opening value."""
    parts = [f"Target {result.target_date:%m/%d/%Y}"]
    if result.premium_date != result.target_date:
        parts.append(f"last premium on the next monthliversary {result.premium_date:%m/%d/%Y}")
    count = len(result.premium_dates)
    parts.append(f"{count} premium date{'s' if count != 1 else ''}")
    interim = result.interim
    if interim is not None and interim.is_rolled_forward:
        parts.append(
            f"opens from the Interim AV Quote {interim.quote_date:%m/%d/%Y} "
            f"({_money(interim.account_value)}, including {_money(interim.gross_premium)} "
            "received since the monthliversary)")
    else:
        parts.append(f"opens from the {result.valuation_date:%m/%d/%Y} monthliversary values")
    text = "; ".join(parts) + "."
    mec = [s.label for s in result.scenarios if s.becomes_mec]
    if mec:
        text = f"{text} MEC: the {' and '.join(mec)} premiums make the policy a MEC."
    if result.interim_unavailable_reason:
        text = f"{text} {result.interim_unavailable_reason}"
    return text


# Which items sit on each summary line, in order: (left block, right block).
_SUMMARY_LAYOUT = (
    (
        (MAX_PREMIUM_LABEL, (PREM_ITEM, AV_ITEM)),
        (MIN_FORCEOUTS_LABEL, (PREM_ITEM, AV_ITEM, FORCEOUTS_ITEM)),
        (MIN_NO_OUTS_LABEL, (PREM_ITEM, AV_ITEM)),
    ),
    (
        (GEP_EXCEPTION_LABEL, (WITH_FORCEOUTS_ITEM, WITHOUT_FORCEOUTS_ITEM)),
        (ACCUM_GLP_LABEL, (CURRENT_ITEM, NEW_ITEM)),
        (PREMIUM_TO_TARGET_LABEL, (WITH_FORCEOUTS_ITEM, WITHOUT_FORCEOUTS_ITEM)),
    ),
)
_SUMMARY_LINE_STYLE = (f"font-size: 11px; font-weight: bold; color: {GREEN_DARK}; "
                       "background: transparent; border: none;")
_SUMMARY_ITEM_STYLE = (f"font-size: 11px; color: {GRAY_DARK}; "
                       "background: transparent; border: none;")
_SUMMARY_VALUE_STYLE = (f"font-size: 11px; font-weight: bold; color: {GRAY_DARK}; "
                        "background: transparent; border: none;")
_SUMMARY_ALERT_STYLE = (f"font-size: 11px; font-weight: bold; color: {STATUS_ERROR}; "
                        "background: transparent; border: none;")
_SUMMARY_MUTED_STYLE = (f"font-size: 11px; font-style: italic; color: {GRAY_TEXT}; "
                        "background: transparent; border: none;")
# Grid columns per block: the line label, then up to three "item =" / value pairs.
_BLOCK_COLUMNS = 1 + 2 * max(len(items) for block in _SUMMARY_LAYOUT for _, items in block)


class GepV2SummaryPanel(QGroupBox):
    """Calculation Summary in two side-by-side blocks to keep it three lines tall."""

    def __init__(self, parent=None):
        super().__init__("Calculation Summary", parent)
        self.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 16, 8, 4)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        self._values: dict[tuple[str, str], QLabel] = {}
        self._names: dict[tuple[str, str], QLabel] = {}
        for block, lines in enumerate(_SUMMARY_LAYOUT):
            first = block * (_BLOCK_COLUMNS + 1)
            for row, (line, items) in enumerate(lines):
                grid.addWidget(_label(f"{line}:", _SUMMARY_LINE_STYLE), row, first)
                for index, item in enumerate(items):
                    name = _label(f"{item} =", _SUMMARY_ITEM_STYLE)
                    value = CopyableLabel("")
                    value.setStyleSheet(_SUMMARY_VALUE_STYLE)
                    value.setMinimumWidth(78)
                    value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    column = first + 1 + 2 * index
                    grid.addWidget(name, row, column)
                    grid.addWidget(value, row, column + 1)
                    self._names[(line, item)] = name
                    self._values[(line, item)] = value
            if block == 0:
                grid.setColumnMinimumWidth(_BLOCK_COLUMNS, 28)
        grid.setColumnStretch(len(_SUMMARY_LAYOUT) * (_BLOCK_COLUMNS + 1), 1)

    def value(self, line: str, item: str) -> str:
        return self._values[(line, item)].text()

    def clear(self) -> None:
        for key, value in self._values.items():
            value.setText("")
            value.setStyleSheet(_SUMMARY_VALUE_STYLE)
            value.setToolTip("")
            self._names[key].setToolTip("")
        self.setToolTip("")

    def show_result(self, result: GepV2Result) -> None:
        for lines in summary_blocks(result):
            for line in lines:
                for item in line.items:
                    value = self._values[(line.label, item.label)]
                    value.setText(item.text)
                    value.setStyleSheet(
                        _SUMMARY_ALERT_STYLE if item.alert
                        else _SUMMARY_MUTED_STYLE if item.muted
                        else _SUMMARY_VALUE_STYLE)
                    value.setToolTip(item.tooltip)
                    self._names[(line.label, item.label)].setToolTip(item.tooltip)
        self.setToolTip(basis_text(result))


class GepV2Page(QWidget):
    """Max / Min target-date premium projections with a shared summary."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy = None
        self._cache_key: tuple = ()
        self._default_target_text = ""
        self._cache: dict[tuple, dict] = {}
        self._result: Optional[GepV2Result] = None
        self._setup_ui()

    @staticmethod
    def quote_date() -> date:
        """The quote runs as of today, opening from today's Interim AV Quote."""
        return date.today()

    @property
    def result(self) -> Optional[GepV2Result]:
        return self._result

    # -- UI ----------------------------------------------------------------

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {WHITE};")
        self.setAutoFillBackground(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        status_frame = QGroupBox("GEP v2")
        status_frame.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        grid = QGridLayout(status_frame)
        grid.setContentsMargins(8, 18, 8, 6)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        label_style = (f"font-size: 11px; font-weight: bold; color: {GREEN_DARK}; "
                       "background: transparent; border: none;")

        grid.addWidget(_label("Forecast Status:", label_style), 0, 0)
        self._status_label = QLabel("Load an eligible policy to check forecast data")
        self._status_label.setStyleSheet(_STATUS_STYLE)
        self._status_label.setWordWrap(True)
        grid.addWidget(self._status_label, 0, 1, 1, 3)

        grid.addWidget(_label("Target Date:", label_style), 1, 0)
        self._target_date = QLineEdit()
        self._target_date.setPlaceholderText("MM/DD/YYYY")
        self._target_date.setStyleSheet(_FILTER_INPUT_STYLE)
        self._target_date.returnPressed.connect(self._on_calculate)
        grid.addWidget(self._target_date, 1, 1)

        self._calculate_btn = QPushButton("Calculate")
        self._calculate_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self._calculate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._calculate_btn.clicked.connect(self._on_calculate)
        grid.addWidget(self._calculate_btn, 1, 2)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        self._export_btn = QPushButton("Export")
        self._export_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setToolTip("Open the summary and every projection in a new Excel workbook")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export)
        buttons.addWidget(self._export_btn)
        buttons.addStretch(1)
        grid.addLayout(buttons, 1, 3)

        note = QLabel(NOTE_TEXT)
        note.setWordWrap(True)
        note.setStyleSheet(
            f"font-size: 10px; color: {GRAY_DARK}; background: transparent; "
            "border: none; padding: 2px 4px;")
        grid.addWidget(note, 2, 0, 1, 4)
        grid.setColumnStretch(3, 1)
        layout.addWidget(status_frame)

        self._forecast_frame = QGroupBox("Monthly Forecast")
        self._forecast_frame.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        self._forecast_frame.setMinimumHeight(220)
        forecast_layout = QVBoxLayout(self._forecast_frame)
        forecast_layout.setContentsMargins(6, 18, 6, 6)
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_GLP_FORECAST_TABS_STYLE)
        self._tables = tuple(_ledger_table() for _ in SCENARIO_TABS)
        for index, (table, label, tip) in enumerate(
                zip(self._tables, SCENARIO_TABS, _TAB_TOOLTIPS)):
            self._tabs.addTab(table, label)
            self._tabs.setTabToolTip(index, tip)
        forecast_layout.addWidget(self._tabs, 1)
        self._forecast_frame.setVisible(False)
        layout.addWidget(self._forecast_frame, 1)

        self._summary = GepV2SummaryPanel()
        self._summary.setVisible(False)
        layout.addWidget(self._summary, 0)

    # -- Policy and availability --------------------------------------------

    def set_policy(self, policy, *, cache_key: tuple, default_target_text: str):
        """Remember the loaded policy; ``refresh()`` checks it when shown."""
        self._policy = policy
        self._cache_key = cache_key
        self._default_target_text = default_target_text
        self.clear_results()
        self._calculate_btn.setEnabled(False)
        self._set_status(
            "Select GEP v2 to check forecast data"
            if is_glp_exception_eligible(policy) else INELIGIBLE_TEXT)

    def refresh(self):
        """Check forecast availability and restore a cached quote for this policy."""
        self.clear_results()
        policy = self._policy
        if not policy or not getattr(policy, "exists", False):
            self._set_status("Load an eligible policy to check forecast data")
            self._calculate_btn.setEnabled(False)
            return
        if not is_glp_exception_eligible(policy):
            self._set_status(INELIGIBLE_TEXT)
            self._calculate_btn.setEnabled(False)
            return
        availability = check_forecast_availability(policy)
        self._set_status(availability.message, is_error=not availability.available)
        self._calculate_btn.setEnabled(availability.available)
        cached = self._cache.get(self._cache_key)
        if cached:
            self._target_date.setText(cached["target_text"])
            self._display(cached["result"])
        else:
            self._target_date.setText(self._default_target_text)

    # -- Calculation ---------------------------------------------------------

    def _on_calculate(self):
        if not self._policy or not self._calculate_btn.isEnabled():
            return
        target_text = self._target_date.text().strip()
        if not target_text:
            self._fail("Enter a Target Date before calculating")
            return
        try:
            target = datetime.strptime(target_text, "%m/%d/%Y").date()
        except ValueError:
            self._fail("Target Date must be entered as MM/DD/YYYY")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = project_gep_v2(self._policy, target, quote_date=self.quote_date())
        except Exception as exc:
            self._fail(str(exc) or type(exc).__name__)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._set_status(
            result.interim_unavailable_reason or "Data for forecasting is available")
        self._display(result)
        self._cache[self._cache_key] = {"target_text": target_text, "result": result}

    def _fail(self, message: str):
        self._set_status(message, is_error=True)
        self.clear_results()

    def _set_status(self, text: str, *, is_error: bool = False):
        self._status_label.setStyleSheet(
            f"font-size: 10px; color: {STATUS_ERROR}; font-weight: bold; "
            "background: transparent; border: none; padding: 2px 4px;"
            if is_error else _STATUS_STYLE)
        self._status_label.setText(text)

    # -- Display -------------------------------------------------------------

    def clear_results(self):
        self._result = None
        for table in self._tables:
            table.setRowCount(0)
        self._summary.clear()
        self._summary.setVisible(False)
        self._forecast_frame.setVisible(False)
        self._export_btn.setEnabled(False)
        for index, label in enumerate(SCENARIO_TABS):
            self._tabs.setTabText(index, label)

    def summary_value(self, line: str, item: str) -> str:
        """Displayed Calculation Summary value for ``item`` on ``line``."""
        return self._summary.value(line, item)

    def _display(self, result: GepV2Result):
        self._result = result
        for index, (table, scenario) in enumerate(zip(self._tables, result.scenarios)):
            self._fill_ledger(table, scenario)
            self._tabs.setTabText(
                index, f"{scenario.label} ({_money(scenario.total_premium)})")
        self._summary.show_result(result)
        self._summary.setVisible(True)
        self._forecast_frame.setVisible(True)
        self._export_btn.setEnabled(True)

    @staticmethod
    def _fill_ledger(table: FixedHeaderTableWidget, scenario: GepV2Scenario):
        rows = scenario_ledger_rows(scenario)
        table.setRowCount(len(rows))
        emphasis = {GEP_V2_COLUMNS.index(name) for name in _EMPHASIS_COLUMNS}
        premium_dates = {payment.date for payment in scenario.payments}
        premium_rows = [
            index for index, state in enumerate(scenario.states) if state.date in premium_dates]
        for row_index, values in enumerate(rows):
            for col_index, text in enumerate(values):
                alignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                if GEP_V2_COLUMNS[col_index] in ("Date", "Status", ""):
                    alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                item = QTableWidgetItem(text)
                if row_index in premium_rows and col_index in emphasis:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                table.setItem(row_index, col_index, item, alignment)
        table.autoFitAllColumns()
        _widen_for_bold(table, [(row, col) for row in premium_rows for col in emphasis])

    # -- Copy and export -----------------------------------------------------

    def export_sheets(self) -> list[tuple[str, list[str], list[list[str]]]]:
        """``(sheet name, headers, rows)`` for the summary and every projection."""
        result = self._result
        if result is None:
            return []
        summary = [*summary_rows(result), ["", ""], ["Basis", basis_text(result)]]
        return [
            ("GEP v2 Summary", SUMMARY_COLUMNS, summary),
            *((name, GEP_V2_COLUMNS, scenario_ledger_rows(scenario))
              for name, scenario in zip(_EXPORT_SHEETS, result.scenarios)),
        ]

    def _on_export(self):
        sheets = self.export_sheets()
        if not sheets:
            QMessageBox.information(self, "Export GEP v2", "Calculate GEP v2 before exporting.")
            return
        try:
            (name, headers, rows), *others = sheets
            _excel, workbook, first = dump_to_new_workbook(headers, rows, sheet_name=name)
            previous = first
            for name, headers, rows in others:
                sheet = workbook.Worksheets.Add(None, previous)
                sheet.Name = name
                # write_table freezes panes on the active window.
                sheet.Activate()
                write_table(sheet, headers, rows)
                previous = sheet
            first.Activate()
        except ExcelExportError as exc:
            QMessageBox.warning(self, "Excel Error", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", f"Failed to export GEP v2:\n{exc}")


def _label(text: str, style: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(style)
    return label


def _widen_for_bold(table: FixedHeaderTableWidget, cells) -> None:
    """Autofit measures the base font; widen columns so bold cells are not clipped."""
    bold = QFont(table._data_table.font())
    bold.setBold(True)
    metrics = QFontMetrics(bold)
    for row, column in cells:
        item = table.item(row, column)
        if item is None:
            continue
        needed = metrics.horizontalAdvance(item.text()) + 16
        if needed > table.columnWidth(column):
            table.setColumnWidth(column, needed)


def _ledger_table() -> FixedHeaderTableWidget:
    table = FixedHeaderTableWidget()
    table.setAutoFillBackground(True)
    table._data_table.viewport().setAutoFillBackground(True)
    table.setColumnCount(len(GEP_V2_COLUMNS))
    table.setHorizontalHeaderLabels(GEP_V2_COLUMNS)
    table._data_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table._data_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table._data_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    return table
