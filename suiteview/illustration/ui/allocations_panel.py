"""Index-strategy allocations grid for the Illustration Inputs tab.

The IUL counterpart of the single Illustrated Rate field: one row per index
strategy (RERUN INPUT rows 36–54) with an editable allocation % and illustrated
rate, the AG49 maximum alongside, and the computed blend — Nominal, Effective
(multiplier strategies credit rate × (1 + multiplier) under AG49 ≤ 2), and the
Guaranteed blend (fixed strategy × GINT; index strategies floor at 0%).

Non-IUL plans keep the panel visible but greyed with an italic note, per the
Not-Applicable convention.
"""
from __future__ import annotations

from typing import Dict, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models.index_strategies import (
    BlendedRates,
    PlanIndexStrategies,
    allocation_problems,
    compute_blended_rates,
)

from .styles import GROUP_STYLE, INPUT_CAPTION_STYLE, INPUT_EDIT_STYLE, PURPLE_DARK

_NA_NOTE_STYLE = (
    "color: #7A6B91; background: transparent; font-size: 11px; font-style: italic;"
)
_NA_GROUP_STYLE = """
    QGroupBox {
        font-weight: bold;
        border: 2px solid #C9BBE2;
        border-radius: 8px;
        margin-top: 14px;
        background-color: #ECE9F1;
        color: #7A6B91;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 2px 10px;
        color: #ECE9F1;
        background-color: #9C8DB8;
        border: 1px solid #C9BBE2;
        border-radius: 5px;
    }
"""
_CELL_STYLE = f"color: {PURPLE_DARK}; background: transparent; font-size: 11px;"
_MUTED_CELL_STYLE = "color: #9C8DB8; background: transparent; font-size: 11px;"
_TOTAL_OK_STYLE = (
    f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;"
)
_TOTAL_BAD_STYLE = (
    "color: #B00020; background: transparent; font-size: 11px; font-weight: bold;"
)
_BLEND_VALUE_STYLE = (
    "color: #2A1458; background: #E8DDF8; border: 1px solid #B79CDE;"
    " border-radius: 3px; padding: 1px 6px; font-size: 11px; font-weight: bold;"
)
_PROBLEM_STYLE = (
    "color: #B00020; background-color: #FDECEA; border: 1px solid #C62828;"
    " border-radius: 4px; padding: 4px 8px; font-size: 10px; font-weight: bold;"
)


class _PctField(QLineEdit):
    """Compact percent field; exports a decimal-form value."""

    def __init__(self, decimals: int = 3, parent=None):
        super().__init__(parent)
        self.setStyleSheet(INPUT_EDIT_STYLE)
        self.setFixedWidth(56)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setValidator(QDoubleValidator(0.0, 100.0, decimals, self))

    def set_decimal(self, value: float, decimals: int = 2):
        self.setText(f"{value * 100.0:.{decimals}f}")

    def decimal(self) -> float:
        try:
            return float((self.text() or "").strip()) / 100.0
        except ValueError:
            return 0.0

    def set_invalid(self, invalid: bool):
        self.setProperty("invalid", "true" if invalid else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class _StrategyRow:
    """The widgets of one grid row, keyed by fund ID."""

    def __init__(self, fund_id: str):
        self.fund_id = fund_id
        self.label = QLabel()
        self.label.setStyleSheet(_CELL_STYLE)
        self.fund = QLabel(fund_id)
        self.fund.setStyleSheet(_CELL_STYLE)
        self.fund.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alloc = _PctField(decimals=2)
        self.rate = _PctField(decimals=3)
        self.max_rate = QLabel()
        self.max_rate.setStyleSheet(_CELL_STYLE)
        self.max_rate.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.parameter = QLabel()
        self.parameter.setStyleSheet(_MUTED_CELL_STYLE)
        self.parameter.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.crediting = QLabel()
        self.crediting.setStyleSheet(_MUTED_CELL_STYLE)
        self.crediting.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def widgets(self):
        return (self.label, self.fund, self.alloc, self.rate,
                self.max_rate, self.parameter, self.crediting)


class AllocationsPanel(QGroupBox):
    """Editable strategy-allocation grid with live blended rates."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Index Strategy Allocations", parent)
        self._plan: Optional[PlanIndexStrategies] = None
        self._gint = 0.0
        self._blended: Optional[BlendedRates] = None
        self._rows: Dict[str, _StrategyRow] = {}
        self._build_ui()
        self.set_plan(None)

    # ── construction ──────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 16, 10, 8)
        outer.setSpacing(6)

        self._na_note = QLabel("Not applicable — declared-rate product")
        self._na_note.setStyleSheet(_NA_NOTE_STYLE)
        self._na_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._na_note)

        self._grid_host = QWidget()
        self._grid_host.setStyleSheet("background: transparent;")
        grid = QGridLayout(self._grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)

        captions = ["Strategy", "Fund", "Alloc %", "Illustrated %",
                    "AG49 Max %", "Cap / Part", "Crediting %"]
        for col, text in enumerate(captions):
            caption = QLabel(text)
            caption.setStyleSheet(INPUT_CAPTION_STYLE)
            if col >= 2:
                caption.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(caption, 0, col)
        grid.setColumnStretch(len(captions), 1)
        self._grid = grid

        row_host = QHBoxLayout()
        row_host.setContentsMargins(0, 0, 0, 0)
        row_host.addWidget(self._grid_host)
        row_host.addStretch(1)
        outer.addLayout(row_host)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self._total_label = QLabel()
        self._total_label.setStyleSheet(_TOTAL_OK_STYLE)
        footer.addWidget(self._total_label)
        footer.addSpacing(18)

        self._blend_labels: Dict[str, QLabel] = {}
        for key, caption in (("nominal", "Blended Nominal"),
                             ("effective", "Blended Effective"),
                             ("guaranteed", "Guaranteed Blend")):
            cap = QLabel(caption)
            cap.setStyleSheet(INPUT_CAPTION_STYLE)
            value = QLabel("")
            value.setStyleSheet(_BLEND_VALUE_STYLE)
            footer.addWidget(cap)
            footer.addWidget(value)
            footer.addSpacing(12)
            self._blend_labels[key] = value
        footer.addStretch(1)
        self._footer_host = QWidget()
        self._footer_host.setStyleSheet("background: transparent;")
        self._footer_host.setLayout(footer)
        outer.addWidget(self._footer_host)

        self._problem_label = QLabel("")
        self._problem_label.setStyleSheet(_PROBLEM_STYLE)
        self._problem_label.setWordWrap(True)
        self._problem_label.setVisible(False)
        outer.addWidget(self._problem_label)

    def _ensure_rows(self, plan: PlanIndexStrategies):
        """(Re)build the grid rows for the plan's strategy list."""
        for row in self._rows.values():
            for widget in row.widgets():
                self._grid.removeWidget(widget)
                widget.deleteLater()
        self._rows.clear()

        for i, strat in enumerate(plan.strategies, start=1):
            row = _StrategyRow(strat.fund_id)
            row.label.setText(strat.label)
            for col, widget in enumerate(row.widgets()):
                self._grid.addWidget(widget, i, col)
            row.alloc.editingFinished.connect(self._recompute)
            row.rate.editingFinished.connect(self._recompute)
            self._rows[strat.fund_id] = row

    # ── loading ───────────────────────────────────────────────

    def set_plan(
        self,
        plan: Optional[PlanIndexStrategies],
        gint: float = 0.0,
        inforce_allocations: Optional[Dict[str, float]] = None,
    ):
        """Populate for an IUL plan, or grey out as Not-Applicable when None."""
        self._plan = plan
        self._gint = float(gint or 0.0)

        if plan is None:
            self.setStyleSheet(_NA_GROUP_STYLE)
            self._grid_host.setVisible(False)
            self._footer_host.setVisible(False)
            self._problem_label.setVisible(False)
            self._na_note.setVisible(True)
            self._blended = None
            return

        self.setStyleSheet(GROUP_STYLE)
        self._na_note.setVisible(False)
        self._grid_host.setVisible(True)
        self._footer_host.setVisible(True)

        self._ensure_rows(plan)
        allocations = _normalized_allocations(inforce_allocations, plan)
        defaults = plan.default_rates()
        for strat in plan.strategies:
            row = self._rows[strat.fund_id]
            offered = strat.is_offered
            row.alloc.setEnabled(offered)
            row.rate.setEnabled(offered)
            row.alloc.set_decimal(allocations.get(strat.fund_id, 0.0) if offered else 0.0)
            row.rate.set_decimal(defaults.get(strat.fund_id, 0.0), decimals=3)
            row.max_rate.setText(
                f"{float(strat.max_rate) * 100:.2f}" if offered else "—")
            row.label.setStyleSheet(_CELL_STYLE if offered else _MUTED_CELL_STYLE)
            row.fund.setStyleSheet(_CELL_STYLE if offered else _MUTED_CELL_STYLE)
            if strat.parameter:
                text = (f"{strat.parameter:.2f}×" if strat.parameter > 1
                        else f"{strat.parameter * 100:.2f}%")
                row.parameter.setText(text)
            else:
                row.parameter.setText("")
        self._recompute()

    # ── state ─────────────────────────────────────────────────

    def allocations(self) -> Dict[str, float]:
        return {fund_id: row.alloc.decimal() for fund_id, row in self._rows.items()
                if row.alloc.isEnabled()}

    def rates(self) -> Dict[str, float]:
        return {fund_id: row.rate.decimal() for fund_id, row in self._rows.items()
                if row.rate.isEnabled()}

    def blended(self) -> Optional[BlendedRates]:
        return self._blended

    def problems(self) -> list[str]:
        if self._plan is None:
            return []
        return allocation_problems(self._plan, self.allocations(), self.rates())

    def is_valid(self) -> bool:
        return self._plan is not None and not self.problems()

    # ── recompute ─────────────────────────────────────────────

    def _recompute(self):
        plan = self._plan
        if plan is None:
            return
        allocations = self.allocations()
        rates = self.rates()
        self._blended = compute_blended_rates(plan, allocations, rates, self._gint)

        total = sum(allocations.values())
        self._total_label.setText(f"Total Allocation  {total * 100:.2f}%")
        total_ok = abs(total - 1.0) <= 1e-9
        self._total_label.setStyleSheet(_TOTAL_OK_STYLE if total_ok else _TOTAL_BAD_STYLE)

        self._blend_labels["nominal"].setText(f"{self._blended.nominal * 100:.2f}%")
        self._blend_labels["effective"].setText(f"{self._blended.effective * 100:.2f}%")
        self._blend_labels["guaranteed"].setText(f"{self._blended.guaranteed * 100:.2f}%")

        for strat in plan.strategies:
            row = self._rows[strat.fund_id]
            if not strat.is_offered:
                row.crediting.setText("")
                continue
            rate = rates.get(strat.fund_id, 0.0)
            over_max = strat.max_rate is not None and rate > float(strat.max_rate) + 1e-9
            row.rate.set_invalid(over_max)
            if strat.is_multiplier and plan.multiplier_active:
                row.crediting.setText(f"{rate * (1.0 + strat.multiplier) * 100:.2f}")
            else:
                row.crediting.setText("")

        problems = allocation_problems(plan, allocations, rates)
        self._problem_label.setText("  •  ".join(problems))
        self._problem_label.setVisible(bool(problems))
        self.changed.emit()


def _normalized_allocations(
    raw: Optional[Dict[str, float]], plan: PlanIndexStrategies
) -> Dict[str, float]:
    """Inforce allocations → decimal form, defaulting to 100% fixed strategy.

    Accepts either decimal (0.25) or percent (25) form — DB2's FND_ALC_PCT
    scale is normalized by the total.  # TODO: verify FND_ALC_PCT scale on a
    live IUL policy (work laptop).
    """
    cleaned = {
        str(fund): float(value)
        for fund, value in (raw or {}).items()
        if value is not None and float(value) > 0.0 and plan.strategy(str(fund)) is not None
    }
    total = sum(cleaned.values())
    if total <= 0.0:
        return plan.default_allocations()
    if total > 1.5:  # percent form
        cleaned = {fund: value / 100.0 for fund, value in cleaned.items()}
    return cleaned
