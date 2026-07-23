"""Values Overview — the at-a-glance face of an illustration run.

Three altitudes, top to bottom:

1. KPI strip   — the outcome in chips (ending AV/SV/DB, lapse, premiums in).
2. Value chart — hand-painted AV / SV / DB / cumulative-premium / guideline
                 lines over policy years, with hover readout and click-to-jump.
3. Ledger      — one row per policy YEAR (the printed-illustration view), each
                 expandable to its twelve monthliversary rows.

The deep per-column grids stay on their own sub-tabs; this view is the summary
+ drill-down entry point.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models.rider_config import load_rider_config
from .styles import PURPLE_BG, PURPLE_DARK

CHART_BG = QColor("#FFFFFF")
GRID_COLOR = QColor("#EDE7F6")
AXIS_COLOR = QColor("#B79CDE")
TEXT_COLOR = QColor("#4B2383")
CROSSHAIR_COLOR = QColor("#9575CD")

SERIES_COLORS = {
    "Account Value": QColor("#5E35A5"),
    "Surrender Value": QColor("#00695C"),
    "Death Benefit": QColor("#8B1A2A"),
    "Cum Premium": QColor("#C9A227"),
    "Guideline Limit": QColor("#4A6FA5"),
    "Accum 7-Pay Prem": QColor("#B03A8C"),
    "Policy Debt": QColor("#BF360C"),   # burnt copper — the liability line
}
DASHED_SERIES = {"Guideline Limit", "Cum Premium", "Accum 7-Pay Prem"}
# Default view: AV vs cumulative premium vs the guideline ceiling.
DEFAULT_HIDDEN = {"Surrender Value", "Death Benefit"}


@dataclass
class ChartSeries:
    name: str
    points: list = field(default_factory=list)   # [(policy_year_float, value)]
    visible: bool = True


def _fmt_money(value: float, decimals: int = 0) -> str:
    return f"{value:,.{decimals}f}"


def _fmt_axis(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.4g}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.4g}k"
    return f"{value:.4g}"


class PolicyValueChart(QWidget):
    """Dense, hand-painted multi-series line chart of policy values by year.

    Hover shows a crosshair readout; clicking emits the policy year so the
    ledger can jump there. Legend chips toggle series.
    """

    yearClicked = pyqtSignal(int)

    MARGIN_LEFT = 56
    MARGIN_RIGHT = 10
    MARGIN_TOP = 26
    MARGIN_BOTTOM = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self._series: list[ChartSeries] = []
        self._issue_age: int = 0
        self._hover_x: float | None = None
        self._legend_rects: list[tuple[QRectF, str]] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(170)

    def set_data(self, series: list[ChartSeries], issue_age: int):
        self._series = series
        self._issue_age = issue_age
        self._hover_x = None
        self.update()

    def clear(self):
        self._series = []
        self.update()

    # ── geometry helpers ──────────────────────────────────────

    def _plot_rect(self) -> QRectF:
        return QRectF(
            self.MARGIN_LEFT, self.MARGIN_TOP,
            max(10.0, self.width() - self.MARGIN_LEFT - self.MARGIN_RIGHT),
            max(10.0, self.height() - self.MARGIN_TOP - self.MARGIN_BOTTOM),
        )

    def _ranges(self):
        xs = [p[0] for s in self._series if s.visible for p in s.points]
        ys = [p[1] for s in self._series if s.visible for p in s.points]
        if not xs or not ys:
            return None
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(0.0, min(ys)), max(ys)
        if x1 - x0 < 1e-9:
            x1 = x0 + 1.0
        if y1 - y0 < 1e-9:
            y1 = y0 + 1.0
        return x0, x1, y0, y1 * 1.04

    def _to_px(self, x, y, rng, rect: QRectF) -> QPointF:
        x0, x1, y0, y1 = rng
        px = rect.left() + (x - x0) / (x1 - x0) * rect.width()
        py = rect.bottom() - (y - y0) / (y1 - y0) * rect.height()
        return QPointF(px, py)

    # ── painting ──────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), CHART_BG)

        rng = self._ranges()
        rect = self._plot_rect()
        small = QFont(self.font())
        small.setPointSizeF(7.5)
        painter.setFont(small)
        metrics = QFontMetrics(small)

        self._paint_legend(painter, metrics)
        if rng is None:
            painter.setPen(QPen(TEXT_COLOR))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Run Values to chart the projection.")
            return

        x0, x1, y0, y1 = rng

        # Horizontal $ guides — light, no chart junk.
        painter.setPen(QPen(GRID_COLOR, 1))
        steps = 4
        for i in range(steps + 1):
            y = y0 + (y1 - y0) * i / steps
            p = self._to_px(x0, y, rng, rect)
            painter.drawLine(QPointF(rect.left(), p.y()), QPointF(rect.right(), p.y()))
            painter.setPen(QPen(TEXT_COLOR))
            painter.drawText(
                QRectF(0, p.y() - 7, self.MARGIN_LEFT - 6, 14),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                _fmt_axis(y),
            )
            painter.setPen(QPen(GRID_COLOR, 1))

        # X-axis year/age ticks.
        span = x1 - x0
        tick = 1 if span <= 12 else 2 if span <= 24 else 5 if span <= 60 else 10
        painter.setPen(QPen(TEXT_COLOR))
        year = int(x0) + (0 if x0 == int(x0) else 1)
        while year <= x1 + 1e-9:
            if (year - int(x0)) % tick == 0:
                p = self._to_px(year, y0, rng, rect)
                painter.setPen(QPen(AXIS_COLOR, 1))
                painter.drawLine(QPointF(p.x(), rect.bottom()), QPointF(p.x(), rect.bottom() + 3))
                painter.setPen(QPen(TEXT_COLOR))
                painter.drawText(
                    QRectF(p.x() - 24, rect.bottom() + 4, 48, 12),
                    Qt.AlignmentFlag.AlignCenter, f"Yr {year}")
                painter.drawText(
                    QRectF(p.x() - 24, rect.bottom() + 15, 48, 12),
                    Qt.AlignmentFlag.AlignCenter, f"{self._issue_age + year - 1}")
            year += 1

        painter.setPen(QPen(AXIS_COLOR, 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        # Series lines (clear any brush left over from legend swatches —
        # QPainter fills open paths with the active brush).
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for series in self._series:
            if not series.visible or not series.points:
                continue
            color = SERIES_COLORS.get(series.name, TEXT_COLOR)
            pen = QPen(color, 1.6)
            if series.name in DASHED_SERIES:
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setWidthF(1.2)
            painter.setPen(pen)
            path = QPainterPath()
            prev_x: float | None = None
            for index, (x, y) in enumerate(series.points):
                p = self._to_px(x, y, rng, rect)
                # Break the line across gaps (e.g. the 7-pay series stops when
                # a TAMRA window closes and resumes when a change opens a new one).
                if index == 0 or (prev_x is not None and x - prev_x > 0.2):
                    path.moveTo(p)
                else:
                    path.lineTo(p)
                prev_x = x
            painter.drawPath(path)

        self._paint_crosshair(painter, rng, rect, metrics)

    def _paint_legend(self, painter: QPainter, metrics: QFontMetrics):
        self._legend_rects = []
        x = float(self.MARGIN_LEFT)
        for series in self._series:
            color = SERIES_COLORS.get(series.name, TEXT_COLOR)
            label = series.name
            w = metrics.horizontalAdvance(label) + 18
            chip = QRectF(x, 5, w, 15)
            self._legend_rects.append((chip, series.name))
            swatch = QRectF(x + 3, 10, 8, 5)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color if series.visible else QColor("#D7CCE8"))
            painter.drawRect(swatch)
            painter.setPen(QPen(TEXT_COLOR if series.visible else QColor("#9E91B5")))
            painter.drawText(
                QRectF(x + 14, 5, w - 14, 15),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            x += w + 8

    def _paint_crosshair(self, painter, rng, rect: QRectF, metrics: QFontMetrics):
        if self._hover_x is None:
            return
        x0, x1, y0, y1 = rng
        year_f = self._hover_x
        if not (x0 <= year_f <= x1):
            return
        p = self._to_px(year_f, y0, rng, rect)
        painter.setPen(QPen(CROSSHAIR_COLOR, 1, Qt.PenStyle.DotLine))
        painter.drawLine(QPointF(p.x(), rect.top()), QPointF(p.x(), rect.bottom()))

        lines = [f"Year {int(round(year_f))}   Age {self._issue_age + int(round(year_f)) - 1}"]
        for series in self._series:
            if not series.visible or not series.points:
                continue
            nearest = min(series.points, key=lambda pt: abs(pt[0] - year_f))
            lines.append(f"{series.name}:  {_fmt_money(nearest[1])}")
        width = max(metrics.horizontalAdvance(line) for line in lines) + 12
        height = len(lines) * 13 + 6
        bx = p.x() + 8
        if bx + width > rect.right():
            bx = p.x() - width - 8
        box = QRectF(bx, rect.top() + 4, width, height)
        painter.setPen(QPen(AXIS_COLOR))
        painter.setBrush(QColor(255, 255, 255, 235))
        painter.drawRoundedRect(box, 3, 3)
        painter.setPen(QPen(TEXT_COLOR))
        for index, line in enumerate(lines):
            painter.drawText(
                QRectF(box.left() + 6, box.top() + 3 + index * 13, width - 8, 13),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)

    # ── interaction ───────────────────────────────────────────

    def _x_to_year(self, px: float) -> float | None:
        rng = self._ranges()
        if rng is None:
            return None
        x0, x1, _, _ = rng
        rect = self._plot_rect()
        if rect.width() <= 0:
            return None
        return x0 + (px - rect.left()) / rect.width() * (x1 - x0)

    def mouseMoveEvent(self, event):
        self._hover_x = self._x_to_year(event.position().x())
        self.update()

    def leaveEvent(self, event):
        self._hover_x = None
        self.update()

    def mousePressEvent(self, event):
        for chip, name in self._legend_rects:
            if chip.contains(event.position()):
                for series in self._series:
                    if series.name == name:
                        series.visible = not series.visible
                self.update()
                return
        year = self._x_to_year(event.position().x())
        if year is not None:
            self.yearClicked.emit(int(round(year)))


class _KpiChip(QWidget):
    """Caption-over-value chip in the banner style."""

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 3, 10, 4)
        layout.setSpacing(0)
        self.caption = QLabel(caption)
        self.caption.setStyleSheet(
            "color: #B79CDE; background: transparent; border: none; font-size: 9px;")
        self.value = QLabel("—")
        self.value.setStyleSheet(
            "color: #FFD54F; background: transparent; border: none;"
            " font-size: 13px; font-weight: bold;")
        layout.addWidget(self.caption)
        layout.addWidget(self.value)
        self.setStyleSheet(
            "background-color: #2A1458; border: 1px solid #5E35A5; border-radius: 4px;")

    def set(self, text: str, alert: bool = False):
        self.value.setText(text)
        color = "#FF8A80" if alert else "#FFD54F"
        self.value.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
            " font-size: 13px; font-weight: bold;")


# Ledger layout: locators (frozen) | rollups | value waterfall | spacer | the
# individual cash-flow columns the rollups summarize. Shadow EAV is only shown
# for shadow-account products (the column is hidden otherwise — see display()).
LEDGER_COLUMNS = [
    "Year", "Month", "Age", "Age EOY", "Date",
    "Contributions", "Distributions",
    "MD", "AV", "SV", "Interest", "EAV", "SC", "LN", "ESV", "Shadow EAV",
    "Death Benefit", "Status",
    "",  # spacer — visual break before the relocated cash-flow detail
    "GLP", "GSP", "TotalGP", "SubjectPayments",
    "Withdrawals", "ForceOuts", "Loan Repay", "Prem", "Exception Prem", "New Loan",
]
# Year | Month | Age | Date stay put while the value columns scroll.
FROZEN_LEDGER_COLUMN_COUNT = LEDGER_COLUMNS.index("Date") + 1
SPACER_COLUMN = LEDGER_COLUMNS.index("")
SHADOW_EAV_COLUMN = LEDGER_COLUMNS.index("Shadow EAV")
NUMERIC_LEDGER = {
    index for index, name in enumerate(LEDGER_COLUMNS) if name not in ("Status", "")
}
# Solid fill for the spacer column so the division between the value waterfall
# and the cash-flow detail reads at a glance.
SPACER_BRUSH = QBrush(QColor("#B79CDE"))


def _fmt_date(when) -> str:
    return f"{when:%m/%d/%Y}" if when else ""


def _ledger_cells(
    year, month, age, age_eoy, when, *,
    withdrawals, forceouts, loan_repay, premium, monthly_deduction,
    exception_prem, av, sv, interest, eav, sc, new_loan, loan_balance,
    esv, shadow_eav, death_benefit, status,
    glp, gsp, total_gp, subject_payments,
) -> list[str]:
    """One ledger row in LEDGER_COLUMNS order (annual and monthly share it).

    ``age`` is the attained age during the period (age at the anniversary that
    began the policy year); ``age_eoy`` is the age reached at the end of the
    policy year (age + 1) — the same EOY age the printed illustration shows.

    Contributions rolls up the money-in columns (Loan Repay + Prem + Exception
    Prem); Distributions the money-out columns (Withdrawals + ForceOuts + New
    Loan). Both keep the source columns' display signs.

    SubjectPayments is the amount tested against the total-GP limit: accumulated
    premiums paid less accumulated withdrawals.
    """
    contributions = loan_repay + premium + exception_prem
    distributions = withdrawals + forceouts + new_loan
    return [
        str(year), str(month), str(age), str(age_eoy), _fmt_date(when),
        _fmt_money(contributions, 2), _fmt_money(distributions, 2),
        _fmt_money(monthly_deduction, 2), _fmt_money(av, 2), _fmt_money(sv, 2),
        _fmt_money(interest, 2), _fmt_money(eav, 2), _fmt_money(sc, 2),
        _fmt_money(loan_balance, 2), _fmt_money(esv, 2),
        _fmt_money(shadow_eav, 2),
        _fmt_money(death_benefit, 0), status,
        "",
        _fmt_money(glp, 2), _fmt_money(gsp, 2),
        _fmt_money(total_gp, 2), _fmt_money(subject_payments, 2),
        _fmt_money(withdrawals, 2), _fmt_money(forceouts, 2),
        _fmt_money(loan_repay, 2), _fmt_money(premium, 2),
        _fmt_money(exception_prem, 2), _fmt_money(new_loan, 2),
    ]


class ValuesOverview(QWidget):
    """KPI strip + annual/monthly drill-down ledger."""

    cellActivated = pyqtSignal(int, str)   # double-click: (result-row index, ledger column)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._year_items: dict[int, QTreeWidgetItem] = {}
        self._updating_frozen_width = False
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(6)
        self.kpi_av = _KpiChip("ENDING AV")
        self.kpi_sv = _KpiChip("ENDING SV")
        self.kpi_db = _KpiChip("ENDING DB")
        self.kpi_lapse = _KpiChip("LAPSE")
        self.kpi_premium = _KpiChip("PREMIUMS IN")
        for chip in (self.kpi_av, self.kpi_sv, self.kpi_db,
                     self.kpi_lapse, self.kpi_premium):
            kpi_row.addWidget(chip)
        kpi_row.addStretch(1)
        layout.addLayout(kpi_row)

        # QTreeView selector so the SAME sheet styles both the QTreeWidget
        # ledger and its frozen QTreeView twin.
        ledger_style = (
            "QTreeView { background: white; border: 1px solid #B79CDE; font-size: 11px; }"
            "QTreeView::item { height: 17px; padding: 0px; }"
            "QTreeView::item:selected { background: #E8DDF8; color: #2A1458; }"
            "QHeaderView::section { background: #E8DDF8; color: #2A1458; font-size: 10px;"
            " font-weight: bold; border: none; border-right: 1px solid #B79CDE;"
            " border-bottom: 1px solid #B79CDE; padding: 2px 6px; height: 18px; }"
        )
        self.ledger = QTreeWidget(self)
        self.ledger.setColumnCount(len(LEDGER_COLUMNS))
        self.ledger.setHeaderLabels(LEDGER_COLUMNS)
        self.ledger.setRootIsDecorated(True)
        self.ledger.setUniformRowHeights(True)
        self.ledger.setAlternatingRowColors(False)
        self.ledger.setStyleSheet(ledger_style)
        header = self.ledger.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(SPACER_COLUMN, QHeaderView.ResizeMode.Fixed)
        self.ledger.setColumnWidth(SPACER_COLUMN, 14)
        self.ledger.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ledger.customContextMenuRequested.connect(
            lambda pos: self._show_ledger_menu(self.ledger.viewport().mapToGlobal(pos)))
        self.ledger.itemDoubleClicked.connect(self._on_item_double_clicked)

        # ── Frozen locator pane ── Year | Month | Age | Date stay visible while
        # the value columns scroll. Same sibling-pane pattern as
        # FilterTableView.set_frozen_column_count: a narrow QTreeView shares the
        # ledger's model + selection model; each pane hides the other's columns.
        self.frozen_ledger = QTreeView(self)
        self.frozen_ledger.setModel(self.ledger.model())
        self.frozen_ledger.setSelectionModel(self.ledger.selectionModel())
        self.frozen_ledger.setRootIsDecorated(True)
        self.frozen_ledger.setUniformRowHeights(True)
        self.frozen_ledger.setAlternatingRowColors(False)
        self.frozen_ledger.setStyleSheet(ledger_style)
        self.frozen_ledger.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frozen_ledger.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frozen_header = self.frozen_ledger.header()
        # Interactive + explicit resizeColumnToContents (not ResizeToContents):
        # the lazy mode re-sizes during paint without a reliable signal, leaving
        # the pane's fixed width stale/clipped.
        frozen_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        frozen_header.setStretchLastSection(False)
        for column in range(len(LEDGER_COLUMNS)):
            frozen = column < FROZEN_LEDGER_COLUMN_COUNT
            self.frozen_ledger.setColumnHidden(column, not frozen)
            self.ledger.setColumnHidden(column, frozen)
        self.frozen_ledger.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.frozen_ledger.customContextMenuRequested.connect(
            lambda pos: self._show_ledger_menu(self.frozen_ledger.viewport().mapToGlobal(pos)))
        self.frozen_ledger.doubleClicked.connect(self._on_frozen_double_clicked)

        # Keep the panes in lockstep: rows (vertical scroll) and tree expansion.
        # Cross-connected setValue/expand terminate naturally — a no-op change
        # emits no signal.
        self.ledger.verticalScrollBar().valueChanged.connect(
            self.frozen_ledger.verticalScrollBar().setValue)
        self.frozen_ledger.verticalScrollBar().valueChanged.connect(
            self.ledger.verticalScrollBar().setValue)
        self.ledger.expanded.connect(self._on_ledger_expand_changed)
        self.ledger.collapsed.connect(self._on_ledger_collapse_changed)
        self.frozen_ledger.expanded.connect(self._on_frozen_expand_changed)
        self.frozen_ledger.collapsed.connect(self._on_frozen_collapse_changed)
        # The scrolling pane loses viewport height to its horizontal scrollbar;
        # reserve the same strip under the frozen pane so rows stay aligned.
        self.ledger.horizontalScrollBar().rangeChanged.connect(
            lambda *_args: self._sync_frozen_bottom_inset())
        frozen_header.sectionResized.connect(
            lambda *_args: self._update_frozen_ledger_width())

        ledger_row = QWidget(self)
        row_layout = QHBoxLayout(ledger_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        frozen_container = QWidget(ledger_row)
        frozen_column = QVBoxLayout(frozen_container)
        frozen_column.setContentsMargins(0, 0, 0, 0)
        frozen_column.setSpacing(0)
        frozen_column.addWidget(self.frozen_ledger, 1)
        self.frozen_bottom_spacer = QWidget(frozen_container)
        self.frozen_bottom_spacer.setFixedHeight(0)
        frozen_column.addWidget(self.frozen_bottom_spacer)
        row_layout.addWidget(frozen_container)
        row_layout.addWidget(self.ledger, 1)
        layout.addWidget(ledger_row, 1)
        self._update_frozen_ledger_width()

    def _update_frozen_ledger_width(self):
        if self._updating_frozen_width:
            return
        self._updating_frozen_width = True
        try:
            header = self.frozen_ledger.header()
            for column in range(FROZEN_LEDGER_COLUMN_COUNT):
                self.frozen_ledger.resizeColumnToContents(column)
            width = sum(header.sectionSize(column) for column in range(FROZEN_LEDGER_COLUMN_COUNT))
            self.frozen_ledger.setFixedWidth(width + self.frozen_ledger.frameWidth() * 2)
        finally:
            self._updating_frozen_width = False

    # Expansion state is per-view; mirror it so both panes lay out the same
    # rows, then refit the locator widths (children indent under Year).
    def _on_ledger_expand_changed(self, index):
        self.frozen_ledger.expand(index)
        self._update_frozen_ledger_width()

    def _on_ledger_collapse_changed(self, index):
        self.frozen_ledger.collapse(index)
        self._update_frozen_ledger_width()

    def _on_frozen_expand_changed(self, index):
        self.ledger.expand(index)
        self._update_frozen_ledger_width()

    def _on_frozen_collapse_changed(self, index):
        self.ledger.collapse(index)
        self._update_frozen_ledger_width()

    def _sync_frozen_bottom_inset(self):
        scrollbar = self.ledger.horizontalScrollBar()
        needs_scrollbar = scrollbar.maximum() > scrollbar.minimum()
        inset = scrollbar.height() if (needs_scrollbar and scrollbar.isVisible()) else 0
        if inset == 0 and needs_scrollbar:
            inset = scrollbar.sizeHint().height()
        self.frozen_bottom_spacer.setFixedHeight(inset)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # A width change can add/remove the ledger's horizontal scrollbar.
        self._sync_frozen_bottom_inset()

    def _on_frozen_double_clicked(self, index):
        row_index = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        if row_index is not None:
            self.cellActivated.emit(int(row_index), LEDGER_COLUMNS[index.column()])

    def _on_item_double_clicked(self, item, column):
        index = item.data(0, Qt.ItemDataRole.UserRole)
        if index is not None:
            self.cellActivated.emit(int(index), LEDGER_COLUMNS[column])

    def _show_ledger_menu(self, global_pos):
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self.ledger)
        dump_annual = menu.addAction("Dump Annual Rows to Excel")
        dump_monthly = menu.addAction("Dump Annual + Monthly Rows to Excel")
        chosen = menu.exec(global_pos)
        if chosen is dump_annual:
            self._dump_ledger(include_months=False)
        elif chosen is dump_monthly:
            self._dump_ledger(include_months=True)

    def _dump_ledger(self, include_months: bool):
        from suiteview.core.excel_export import ExcelExportError, dump_to_new_workbook

        rows = []
        for index in range(self.ledger.topLevelItemCount()):
            item = self.ledger.topLevelItem(index)
            rows.append([item.text(c) for c in range(len(LEDGER_COLUMNS))])
            if include_months:
                for child_index in range(item.childCount()):
                    child = item.child(child_index)
                    rows.append([child.text(c) for c in range(len(LEDGER_COLUMNS))])
        try:
            dump_to_new_workbook(LEDGER_COLUMNS, rows, sheet_name="Illustration Ledger")
        except ExcelExportError as exc:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Export Error", f"Could not export:\n{exc}")

    # ── data ──────────────────────────────────────────────────

    def clear(self):
        self.ledger.clear()
        self._year_items = {}
        for chip in (self.kpi_av, self.kpi_sv, self.kpi_db,
                     self.kpi_lapse, self.kpi_premium):
            chip.set("—")

    def display(self, policy, results: list):
        """Populate from the projection. ``results[0]`` is the inforce row."""
        self.clear()
        if not results:
            return

        projected = results[1:] if len(results) > 1 else []
        final = results[-1]

        # ── KPIs ──
        self.kpi_av.set(_fmt_money(final.av_end_of_month), alert=final.av_end_of_month < 0)
        self.kpi_sv.set(_fmt_money(final.ending_sv))
        self.kpi_db.set(_fmt_money(final.ending_db or final.gross_db))
        # A matured final month can carry the lapsed flag (e.g. a shadow- or
        # SNET-carried policy endowing with a negative AV) — that's Maturity,
        # not a lapse, so it doesn't trip the KPI.
        lapse_state = next(
            (s for s in projected if s.lapsed and not getattr(s, "matured", False)),
            None)
        if lapse_state is not None:
            self.kpi_lapse.set(
                f"{_fmt_date(lapse_state.date)} · Age {lapse_state.attained_age}", alert=True)
        else:
            self.kpi_lapse.set("None")
        self.kpi_premium.set(_fmt_money(sum(s.premium_outlay for s in projected)))

        # Shadow EAV only applies to shadow-account products — hide it otherwise.
        has_shadow = bool(getattr(policy, "has_shadow_account", False))
        self.ledger.setColumnHidden(SHADOW_EAV_COLUMN, not has_shadow)

        # ── ledger: annual rows with monthly children ──
        # Each entry keeps its index into ``results`` so selection and
        # double-click can hand the exact month to the inspector / detail tabs.
        by_year: dict[int, list] = {}
        for result_index, state in enumerate(projected, start=1):
            by_year.setdefault(state.policy_year, []).append((result_index, state))

        bold = QFont()
        bold.setBold(True)
        prior_wd = results[0].withdrawals_to_date
        for year in sorted(by_year):
            month_entries = by_year[year]
            months = [state for _, state in month_entries]
            eoy_index, eoy = month_entries[-1]
            # Prem excludes the GP exception premium (it has its own column), so
            # Prem + Exception Prem == premium_outlay with no double count.
            premium = sum(s.premium_outlay - s.gp_exception_prem for s in months)
            loan_repay = sum(s.applied_loan_repayment for s in months)
            exception_prem = sum(s.gp_exception_prem for s in months)
            forceouts = sum(s.guideline_forceout for s in months)
            new_loan = sum(s.applied_new_loan for s in months)
            interest = sum(s.interest_credited for s in months)
            monthly_deduction = sum(s.total_deduction for s in months)
            # withdrawals_to_date includes the guideline force-out (CalcEngine
            # folds it back in as new room); net it out so the Withdrawals
            # column shows only true gross withdrawals and Distributions
            # (Withdrawals + ForceOuts + New Loan) does not double-count it.
            withdrawals = eoy.withdrawals_to_date - prior_wd - forceouts
            prior_wd = eoy.withdrawals_to_date
            # AV after exception premium, before interest; the matching SV nets
            # loans and the surrender charge out of that AV.
            av_pre_interest = eoy.av_after_exception
            sv_pre_interest = av_pre_interest - eoy.policy_debt - eoy.surrender_charge
            item = QTreeWidgetItem(_ledger_cells(
                year, eoy.policy_month, eoy.attained_age, eoy.attained_age + 1, eoy.date,
                withdrawals=withdrawals, forceouts=forceouts,
                loan_repay=loan_repay, premium=premium,
                monthly_deduction=monthly_deduction, exception_prem=exception_prem,
                av=av_pre_interest, sv=sv_pre_interest, interest=interest,
                eav=eoy.av_end_of_month, sc=eoy.surrender_charge,
                new_loan=new_loan, loan_balance=eoy.policy_debt,
                esv=eoy.ending_sv, shadow_eav=eoy.shadow_eav,
                death_benefit=eoy.ending_db or eoy.gross_db,
                status=_status_text(eoy),
                glp=eoy.glp, gsp=eoy.gsp, total_gp=eoy.guideline_limit,
                subject_payments=eoy.premiums_to_date_after_exception - eoy.withdrawals_to_date,
            ))
            item.setBackground(SPACER_COLUMN, SPACER_BRUSH)
            for column in range(len(LEDGER_COLUMNS)):
                if column in NUMERIC_LEDGER:
                    item.setTextAlignment(column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setFont(column, bold)
            if eoy.lapsed and not getattr(eoy, "matured", False):
                for column in range(len(LEDGER_COLUMNS)):
                    item.setForeground(column, QColor("#B71C1C"))
            item.setData(0, Qt.ItemDataRole.UserRole, eoy_index)
            self._year_items[year] = item
            self.ledger.addTopLevelItem(item)

            previous_wd = (
                by_year[year - 1][-1][1].withdrawals_to_date
                if year - 1 in by_year else results[0].withdrawals_to_date
            )
            for result_index, state in month_entries:
                # Net the force-out out of the withdrawal delta (see annual row).
                month_wd = (
                    state.withdrawals_to_date - previous_wd
                    - state.guideline_forceout)
                previous_wd = state.withdrawals_to_date
                av_pre_interest = state.av_after_exception
                sv_pre_interest = av_pre_interest - state.policy_debt - state.surrender_charge
                child = QTreeWidgetItem(_ledger_cells(
                    state.policy_year, state.policy_month, state.attained_age,
                    state.attained_age + 1, state.date,
                    withdrawals=month_wd, forceouts=state.guideline_forceout,
                    loan_repay=state.applied_loan_repayment,
                    premium=state.premium_outlay - state.gp_exception_prem,
                    monthly_deduction=state.total_deduction,
                    exception_prem=state.gp_exception_prem,
                    av=av_pre_interest, sv=sv_pre_interest,
                    interest=state.interest_credited,
                    eav=state.av_end_of_month, sc=state.surrender_charge,
                    new_loan=state.applied_new_loan, loan_balance=state.policy_debt,
                    esv=state.ending_sv, shadow_eav=state.shadow_eav,
                    death_benefit=state.ending_db or state.gross_db,
                    status=_status_text(state),
                    glp=state.glp, gsp=state.gsp, total_gp=state.guideline_limit,
                    subject_payments=state.premiums_to_date_after_exception - state.withdrawals_to_date,
                ))
                child.setBackground(SPACER_COLUMN, SPACER_BRUSH)
                for column in range(len(LEDGER_COLUMNS)):
                    if column in NUMERIC_LEDGER:
                        child.setTextAlignment(column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if state.lapsed and not getattr(state, "matured", False):
                    for column in range(len(LEDGER_COLUMNS)):
                        child.setForeground(column, QColor("#B71C1C"))
                child.setData(0, Qt.ItemDataRole.UserRole, result_index)
                item.addChild(child)
        self._update_frozen_ledger_width()
        self._sync_frozen_bottom_inset()

    def jump_to_year(self, year: int):
        """Expand and scroll the ledger to a policy year (chart click-through)."""
        item = self._year_items.get(year)
        if item is None:
            return
        # collapseAll does not emit per-item collapsed signals, so collapse the
        # frozen twin explicitly to keep the panes' row layouts identical.
        self.ledger.collapseAll()
        self.frozen_ledger.collapseAll()
        item.setExpanded(True)
        self.ledger.scrollToItem(item, QTreeWidget.ScrollHint.PositionAtTop)
        self.ledger.setCurrentItem(item)


def build_chart_series(projected: list) -> list[ChartSeries]:
    """Chart series from projected monthly states (x = fractional policy year)."""

    def xs(state):
        return state.policy_year + (state.policy_month - 1) / 12.0

    # Total premium paid to date already includes the MD and GP exception
    # premiums (carried forward in premiums_to_date_after_exception), so use it
    # directly rather than re-accumulating (which would double-count).
    premium_points = [
        (xs(state), state.premiums_to_date_after_exception) for state in projected
    ]

    series = [
        ChartSeries("Account Value", [(xs(s), s.av_end_of_month) for s in projected]),
        ChartSeries("Surrender Value", [(xs(s), s.ending_sv) for s in projected]),
        ChartSeries("Death Benefit", [(xs(s), s.ending_db or s.gross_db) for s in projected]),
        ChartSeries("Cum Premium", premium_points),
        ChartSeries("Guideline Limit", [(xs(s), s.guideline_limit) for s in projected]),
    ]
    # Total policy debt (all six ending loan buckets: principal + accrued
    # interest — the ledger's LN / Loan group's Ending LB). Only charted when
    # the policy actually borrows at some point (existing or illustrated
    # loan); a loan-free projection gets no series and no dead legend chip.
    if any(s.policy_debt > 0 for s in projected):
        series.append(ChartSeries(
            "Policy Debt", [(xs(s), s.policy_debt) for s in projected]))
    # Accumulated 7-pay contributions, only while a 7-pay window is running
    # (TAMRA year 1-7). A material change restarts the window mid-projection,
    # so the line can break and resume against the NEW window's accumulation.
    seven_pay_points = [
        (xs(s), s.accumulated_7pay)
        for s in projected
        if 1 <= s.tamra_year <= 7 and s.tamra_7pay_level > 0
    ]
    if seven_pay_points:
        series.append(ChartSeries("Accum 7-Pay Prem", seven_pay_points))
    for entry in series:
        entry.visible = entry.name not in DEFAULT_HIDDEN
    return series


_CHARGE_BAND_PALETTE = [
    QColor("#5E35A5"),  # base COI — primary purple
    QColor("#C9A227"),  # EPU
    QColor("#00695C"),  # monthly fee
    QColor("#8B1A2A"),  # benefit/rider cycle starts
    QColor("#4A6FA5"),
    QColor("#B03A8C"),
    QColor("#7B5E00"),
    QColor("#2E7D32"),
    QColor("#5C0A14"),
]

_BENEFIT_CHARGE_LABELS = {"39": "Premium Waiver", "3#": "Stip Premium Waiver", "76": "GIO"}


@dataclass
class ChargeBand:
    name: str
    points: list = field(default_factory=list)   # [(policy_year_float, cumulative $)]
    visible: bool = True


def _benefit_charge_label(key: str) -> str:
    return _BENEFIT_CHARGE_LABELS.get(key, f"Benefit {key}")


def _rider_charge_label(key: str) -> str:
    """Short legend alias (CTR/STR/LTR/...) from rider_table.json, looked up
    by the full plancode — never a prefix guess."""
    plancode = key.split("_", 1)[0]
    config = load_rider_config(plancode)
    if config is not None and config.cov_type:
        return config.cov_type
    return f"Rider {plancode}"


def _base_coi_charge(state) -> float:
    if state.total_coi_charge > 0:
        return state.total_coi_charge
    detailed_charge = sum(state.coi_charges_by_coverage.values()) + state.coi_charge_corr
    if detailed_charge > 0:
        return detailed_charge
    return state.coi_charge


def build_charge_bands(projected: list) -> list[ChargeBand]:
    """Cumulative charge bands for the stacked proportion chart.

    Base COI (incl. substandard and the corridor slice), per-unit expense
    (EPU), the monthly fee, the %-of-AV charge when present, and one band per
    benefit / rider charge stream.
    """

    def xs(state):
        return state.policy_year + (state.policy_month - 1) / 12.0

    # Keys grouped by display label (first-seen order) — multiple charge
    # streams resolving to the same label stack into a single band.
    benefit_keys: dict[str, list[str]] = {}
    rider_keys: dict[str, list[str]] = {}
    for state in projected:
        for key in state.benefit_charge_detail:
            keys = benefit_keys.setdefault(_benefit_charge_label(key), [])
            if key not in keys:
                keys.append(key)
        for key in state.rider_charge_detail:
            keys = rider_keys.setdefault(_rider_charge_label(key), [])
            if key not in keys:
                keys.append(key)

    bands = [ChargeBand("Base COI")]
    bands.append(ChargeBand("Expense / Unit"))
    bands.append(ChargeBand("Monthly Fee"))
    has_av_charge = any(s.av_charge > 0 for s in projected)
    if has_av_charge:
        bands.append(ChargeBand("AV Charge"))
    for label in benefit_keys:
        bands.append(ChargeBand(label))
    for label in rider_keys:
        bands.append(ChargeBand(label))

    totals = [0.0] * len(bands)
    for state in projected:
        x = xs(state)
        values = [_base_coi_charge(state), state.epu_charge, state.mfee_charge]
        if has_av_charge:
            values.append(state.av_charge)
        values.extend(sum(state.benefit_charge_detail.get(key, 0.0) for key in keys)
                      for keys in benefit_keys.values())
        values.extend(sum(state.rider_charge_detail.get(key, 0.0) for key in keys)
                      for keys in rider_keys.values())
        for index, value in enumerate(values):
            totals[index] += max(value, 0.0)
            bands[index].points.append((x, totals[index]))
    return [band for band in bands if band.points and band.points[-1][1] > 0.005]


class AccumulatedChargesChart(QWidget):
    """Stacked area chart of ACCUMULATED charges — each band's share of the
    total cost of the policy over the projection.

    Same hand-painted aesthetic as PolicyValueChart: hover crosshair with the
    per-band split at that point, legend chips toggle bands out of the stack.
    """

    MARGIN_LEFT = 56
    MARGIN_RIGHT = 10
    MARGIN_TOP = 26
    MARGIN_BOTTOM = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bands: list[ChargeBand] = []
        self._issue_age: int = 0
        self._hover_x: float | None = None
        self._legend_rects: list[tuple[QRectF, str]] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(170)

    def set_data(self, bands: list[ChargeBand], issue_age: int):
        self._bands = bands
        self._issue_age = issue_age
        self._hover_x = None
        self.update()

    def clear(self):
        self._bands = []
        self.update()

    def _band_color(self, index: int) -> QColor:
        return _CHARGE_BAND_PALETTE[index % len(_CHARGE_BAND_PALETTE)]

    def _plot_rect(self) -> QRectF:
        return QRectF(
            self.MARGIN_LEFT, self.MARGIN_TOP,
            max(10.0, self.width() - self.MARGIN_LEFT - self.MARGIN_RIGHT),
            max(10.0, self.height() - self.MARGIN_TOP - self.MARGIN_BOTTOM),
        )

    def _visible(self) -> list[ChargeBand]:
        return [band for band in self._bands if band.visible and band.points]

    def _stack_tops(self):
        """Per-x stacked cumulative boundaries for the visible bands."""
        visible = self._visible()
        if not visible:
            return None, None
        xs_all = [p[0] for p in visible[0].points]
        tops: list[list[float]] = []
        running = [0.0] * len(xs_all)
        for band in visible:
            level = []
            for index, (_, value) in enumerate(band.points[:len(xs_all)]):
                running[index] = running[index] + value
                level.append(running[index])
            tops.append(level)
        return xs_all, tops

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), CHART_BG)

        small = QFont(self.font())
        small.setPointSizeF(7.5)
        painter.setFont(small)
        metrics = QFontMetrics(small)
        self._paint_legend(painter, metrics)

        xs_all, tops = self._stack_tops()
        rect = self._plot_rect()
        if not xs_all:
            painter.setPen(QPen(TEXT_COLOR))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Run Values to chart accumulated charges.")
            return

        x0, x1 = xs_all[0], xs_all[-1]
        if x1 - x0 < 1e-9:
            x1 = x0 + 1.0
        y1 = max(tops[-1]) * 1.04 if tops[-1] else 1.0
        y0 = 0.0

        def to_px(x, y):
            px = rect.left() + (x - x0) / (x1 - x0) * rect.width()
            py = rect.bottom() - (y - y0) / (y1 - y0) * rect.height()
            return QPointF(px, py)

        # $ guides
        painter.setPen(QPen(GRID_COLOR, 1))
        for i in range(5):
            y = y0 + (y1 - y0) * i / 4
            p = to_px(x0, y)
            painter.drawLine(QPointF(rect.left(), p.y()), QPointF(rect.right(), p.y()))
            painter.setPen(QPen(TEXT_COLOR))
            painter.drawText(
                QRectF(0, p.y() - 7, self.MARGIN_LEFT - 6, 14),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                _fmt_axis(y),
            )
            painter.setPen(QPen(GRID_COLOR, 1))

        # X ticks (year/age)
        span = x1 - x0
        tick = 1 if span <= 12 else 2 if span <= 24 else 5 if span <= 60 else 10
        year = int(x0) + (0 if x0 == int(x0) else 1)
        while year <= x1 + 1e-9:
            if (year - int(x0)) % tick == 0:
                p = to_px(year, y0)
                painter.setPen(QPen(AXIS_COLOR, 1))
                painter.drawLine(QPointF(p.x(), rect.bottom()), QPointF(p.x(), rect.bottom() + 3))
                painter.setPen(QPen(TEXT_COLOR))
                painter.drawText(QRectF(p.x() - 24, rect.bottom() + 4, 48, 12),
                                 Qt.AlignmentFlag.AlignCenter, f"Yr {year}")
                painter.drawText(QRectF(p.x() - 24, rect.bottom() + 15, 48, 12),
                                 Qt.AlignmentFlag.AlignCenter, f"{self._issue_age + year - 1}")
            year += 1

        # Stacked bands: fill between the prior boundary and this band's top.
        visible = self._visible()
        lower = [0.0] * len(xs_all)
        for band, level in zip(visible, tops):
            color = QColor(self._band_color(self._bands.index(band)))
            color.setAlpha(165)
            path = QPainterPath()
            path.moveTo(to_px(xs_all[0], lower[0]))
            for x, y in zip(xs_all, level):
                path.lineTo(to_px(x, y))
            for x, y in zip(reversed(xs_all), reversed(lower)):
                path.lineTo(to_px(x, y))
            path.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPath(path)
            lower = list(level)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(AXIS_COLOR, 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        self._paint_crosshair(painter, metrics, rect, xs_all, tops, to_px)

    def _paint_legend(self, painter: QPainter, metrics: QFontMetrics):
        self._legend_rects = []
        x = float(self.MARGIN_LEFT)
        for index, band in enumerate(self._bands):
            color = self._band_color(index)
            w = metrics.horizontalAdvance(band.name) + 18
            chip = QRectF(x, 5, w, 15)
            self._legend_rects.append((chip, band.name))
            swatch = QRectF(x + 3, 10, 8, 5)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color if band.visible else QColor("#D7CCE8"))
            painter.drawRect(swatch)
            painter.setPen(QPen(TEXT_COLOR if band.visible else QColor("#9E91B5")))
            painter.drawText(QRectF(x + 14, 5, w - 14, 15),
                             Qt.AlignmentFlag.AlignVCenter, band.name)
            x += w + 6

    def _paint_crosshair(self, painter, metrics, rect, xs_all, tops, to_px):
        if self._hover_x is None or not xs_all:
            return
        # Snap to the nearest sample.
        nearest_index = min(range(len(xs_all)), key=lambda i: abs(xs_all[i] - self._hover_x))
        x = xs_all[nearest_index]
        p = to_px(x, 0)
        painter.setPen(QPen(CROSSHAIR_COLOR, 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(p.x(), rect.top()), QPointF(p.x(), rect.bottom()))

        visible = self._visible()
        total = tops[-1][nearest_index] if tops else 0.0
        lines = [f"Year {int(x)}  -  Total {_fmt_money(total)}"]
        lower = 0.0
        for band, level in zip(visible, tops):
            amount = level[nearest_index] - lower
            lower = level[nearest_index]
            share = (amount / total * 100.0) if total > 0 else 0.0
            lines.append(f"{band.name}:  {_fmt_money(amount)}  ({share:.1f}%)")
        width = max(metrics.horizontalAdvance(line) for line in lines) + 14
        height = len(lines) * 13 + 8
        bx = min(p.x() + 8, rect.right() - width)
        by = rect.top() + 4
        painter.setPen(QPen(AXIS_COLOR))
        painter.setBrush(QColor(255, 255, 255, 235))
        painter.drawRect(QRectF(bx, by, width, height))
        painter.setPen(QPen(TEXT_COLOR))
        for index, line in enumerate(lines):
            painter.drawText(QRectF(bx + 7, by + 4 + index * 13, width - 10, 13),
                             Qt.AlignmentFlag.AlignVCenter, line)

    def mouseMoveEvent(self, event):
        rect = self._plot_rect()
        xs_all, tops = self._stack_tops()
        if not xs_all or not rect.contains(event.position()):
            self._hover_x = None
            self.update()
            return
        x0, x1 = xs_all[0], xs_all[-1]
        frac = (event.position().x() - rect.left()) / max(rect.width(), 1.0)
        self._hover_x = x0 + frac * (x1 - x0)
        self.update()

    def leaveEvent(self, event):
        self._hover_x = None
        self.update()

    def mousePressEvent(self, event):
        for chip, name in self._legend_rects:
            if chip.contains(event.position()):
                for band in self._bands:
                    if band.name == name:
                        band.visible = not band.visible
                        self.update()
                        return
        super().mousePressEvent(event)


def _status_text(state) -> str:
    if getattr(state, "matured", False):
        return "Maturity"
    if state.lapsed:
        return "LAPSED"
    flags = []
    # "Bill to MD" hand-off: once the scheduled billable premium can no longer
    # carry the policy, the Monthly Deduction premium pays instead. Flag the
    # periods where an MD premium is actually being used.
    if getattr(state, "md_premium", 0.0) > 0:
        flags.append("MDCap" if getattr(state, "md_premium_capped", False) else "MDPrem")
    if getattr(state, "exception_prem_mode", False):
        flags.append("ExcPrem")
    if getattr(state, "snet_active", False):
        flags.append("SNET")
    if getattr(state, "shadow_protection", False):
        flags.append("Shadow")
    if getattr(state, "guideline_forceout", 0.0) > 0:
        flags.append("ForceOut")
    if getattr(state, "premium_capped", False):
        flags.append("PremCap")
    return " ".join(flags)
