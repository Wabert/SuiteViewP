"""Values Overview — the at-a-glance face of an illustration run.

Three altitudes, top to bottom:

1. KPI strip   — the outcome in six chips (ending AV/SV/DB, lapse, GP room).
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
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

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


LEDGER_COLUMNS = [
    "Year", "Month", "Age", "Withdrawals", "ForceOuts", "Loan Repay", "Prem",
    "MD", "Exception Prem", "AV", "SV", "Interest", "EAV", "SC",
    "New Loan", "LN", "ESV", "Death Benefit", "Status",
]
NUMERIC_LEDGER = set(range(len(LEDGER_COLUMNS) - 1))


class ValuesOverview(QWidget):
    """KPI strip + annual/monthly drill-down ledger."""

    monthSelected = pyqtSignal(int)        # result-row index of the highlighted month
    cellActivated = pyqtSignal(int, str)   # double-click: (result-row index, ledger column)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._year_items: dict[int, QTreeWidgetItem] = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(6)
        self.kpi_horizon = _KpiChip("PROJECTED TO")
        self.kpi_av = _KpiChip("ENDING AV")
        self.kpi_sv = _KpiChip("ENDING SV")
        self.kpi_db = _KpiChip("ENDING DB")
        self.kpi_lapse = _KpiChip("LAPSE")
        self.kpi_room = _KpiChip("GP ROOM")
        self.kpi_premium = _KpiChip("PREMIUMS IN")
        for chip in (self.kpi_horizon, self.kpi_av, self.kpi_sv, self.kpi_db,
                     self.kpi_lapse, self.kpi_room, self.kpi_premium):
            kpi_row.addWidget(chip)
        kpi_row.addStretch(1)
        layout.addLayout(kpi_row)

        self.ledger = QTreeWidget(self)
        self.ledger.setColumnCount(len(LEDGER_COLUMNS))
        self.ledger.setHeaderLabels(LEDGER_COLUMNS)
        self.ledger.setRootIsDecorated(True)
        self.ledger.setUniformRowHeights(True)
        self.ledger.setAlternatingRowColors(False)
        self.ledger.setStyleSheet(
            "QTreeWidget { background: white; border: 1px solid #B79CDE; font-size: 11px; }"
            "QTreeWidget::item { height: 17px; padding: 0px; }"
            "QTreeWidget::item:selected { background: #E8DDF8; color: #2A1458; }"
            "QHeaderView::section { background: #E8DDF8; color: #2A1458; font-size: 10px;"
            " font-weight: bold; border: none; border-right: 1px solid #B79CDE;"
            " border-bottom: 1px solid #B79CDE; padding: 2px 6px; height: 18px; }"
        )
        header = self.ledger.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.ledger.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ledger.customContextMenuRequested.connect(self._on_ledger_menu)
        self.ledger.currentItemChanged.connect(self._on_current_item)
        self.ledger.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.ledger, 1)

    def _on_current_item(self, current, _previous):
        if current is None:
            return
        index = current.data(0, Qt.ItemDataRole.UserRole)
        if index is not None:
            self.monthSelected.emit(int(index))

    def _on_item_double_clicked(self, item, column):
        index = item.data(0, Qt.ItemDataRole.UserRole)
        if index is not None:
            self.cellActivated.emit(int(index), LEDGER_COLUMNS[column])

    def _on_ledger_menu(self, pos):
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self.ledger)
        dump_annual = menu.addAction("Dump Annual Rows to Excel")
        dump_monthly = menu.addAction("Dump Annual + Monthly Rows to Excel")
        chosen = menu.exec(self.ledger.viewport().mapToGlobal(pos))
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
        for chip in (self.kpi_horizon, self.kpi_av, self.kpi_sv, self.kpi_db,
                     self.kpi_lapse, self.kpi_room, self.kpi_premium):
            chip.set("—")

    def display(self, policy, results: list):
        """Populate from the projection. ``results[0]`` is the inforce row."""
        self.clear()
        if not results:
            return

        projected = results[1:] if len(results) > 1 else []
        final = results[-1]

        # ── KPIs ──
        self.kpi_horizon.set(
            f"Yr {final.policy_year}  ·  Age {final.attained_age}")
        self.kpi_av.set(_fmt_money(final.av_end_of_month), alert=final.av_end_of_month < 0)
        self.kpi_sv.set(_fmt_money(final.surrender_value))
        self.kpi_db.set(_fmt_money(final.ending_db or final.gross_db))
        lapse_state = next((s for s in projected if s.lapsed), None)
        if lapse_state is not None:
            self.kpi_lapse.set(
                f"Yr {lapse_state.policy_year} · Age {lapse_state.attained_age}", alert=True)
        else:
            self.kpi_lapse.set("None")
        room = final.guideline_limit - (final.premiums_to_date_after_exception - final.withdrawals_to_date)
        self.kpi_room.set(_fmt_money(room), alert=room < 0)
        self.kpi_premium.set(_fmt_money(sum(s.premium_outlay for s in projected)))

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
            premium = sum(s.premium_outlay for s in months)
            loan_repay = sum(s.applied_loan_repayment for s in months)
            exception_prem = sum(s.gp_exception_prem for s in months)
            forceouts = sum(s.guideline_forceout for s in months)
            new_loan = sum(s.applied_new_loan for s in months)
            interest = sum(s.interest_credited for s in months)
            monthly_deduction = sum(s.total_deduction for s in months)
            withdrawals = eoy.withdrawals_to_date - prior_wd
            prior_wd = eoy.withdrawals_to_date
            # AV after exception premium, before interest; the matching SV nets
            # loans and the surrender charge out of that AV.
            av_pre_interest = eoy.av_after_exception
            sv_pre_interest = av_pre_interest - eoy.policy_debt - eoy.surrender_charge
            item = QTreeWidgetItem([
                str(year), str(eoy.policy_month), str(eoy.attained_age),
                _fmt_money(withdrawals, 2), _fmt_money(forceouts, 2),
                _fmt_money(loan_repay, 2),
                _fmt_money(premium, 2), _fmt_money(monthly_deduction, 2),
                _fmt_money(exception_prem, 2), _fmt_money(av_pre_interest, 2),
                _fmt_money(sv_pre_interest, 2), _fmt_money(interest, 2),
                _fmt_money(eoy.av_end_of_month, 2), _fmt_money(eoy.surrender_charge, 2),
                _fmt_money(new_loan, 2), _fmt_money(eoy.policy_debt, 2),
                _fmt_money(eoy.surrender_value, 2),
                _fmt_money(eoy.ending_db or eoy.gross_db, 0), _status_text(eoy),
            ])
            for column in range(len(LEDGER_COLUMNS)):
                if column in NUMERIC_LEDGER or column < 2:
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
                month_wd = state.withdrawals_to_date - previous_wd
                previous_wd = state.withdrawals_to_date
                av_pre_interest = state.av_after_exception
                sv_pre_interest = av_pre_interest - state.policy_debt - state.surrender_charge
                child = QTreeWidgetItem([
                    str(state.policy_year), str(state.policy_month), str(state.attained_age),
                    _fmt_money(month_wd, 2), _fmt_money(state.guideline_forceout, 2),
                    _fmt_money(state.applied_loan_repayment, 2),
                    _fmt_money(state.premium_outlay, 2), _fmt_money(state.total_deduction, 2),
                    _fmt_money(state.gp_exception_prem, 2), _fmt_money(av_pre_interest, 2),
                    _fmt_money(sv_pre_interest, 2), _fmt_money(state.interest_credited, 2),
                    _fmt_money(state.av_end_of_month, 2), _fmt_money(state.surrender_charge, 2),
                    _fmt_money(state.applied_new_loan, 2), _fmt_money(state.policy_debt, 2),
                    _fmt_money(state.surrender_value, 2),
                    _fmt_money(state.ending_db or state.gross_db, 0), _status_text(state),
                ])
                for column in range(len(LEDGER_COLUMNS)):
                    if column in NUMERIC_LEDGER or column < 2:
                        child.setTextAlignment(column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if state.lapsed and not getattr(state, "matured", False):
                    for column in range(len(LEDGER_COLUMNS)):
                        child.setForeground(column, QColor("#B71C1C"))
                child.setData(0, Qt.ItemDataRole.UserRole, result_index)
                item.addChild(child)

    def jump_to_year(self, year: int):
        """Expand and scroll the ledger to a policy year (chart click-through)."""
        item = self._year_items.get(year)
        if item is None:
            return
        self.ledger.collapseAll()
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
        ChartSeries("Surrender Value", [(xs(s), s.surrender_value) for s in projected]),
        ChartSeries("Death Benefit", [(xs(s), s.ending_db or s.gross_db) for s in projected]),
        ChartSeries("Cum Premium", premium_points),
        ChartSeries("Guideline Limit", [(xs(s), s.guideline_limit) for s in projected]),
    ]
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
_RIDER_CHARGE_LABELS = {
    "1U536": "LTR",
    "1U538": "CTR",
    "1U539": "STR",
}


@dataclass
class ChargeBand:
    name: str
    points: list = field(default_factory=list)   # [(policy_year_float, cumulative $)]
    visible: bool = True


def _benefit_charge_label(key: str) -> str:
    return _BENEFIT_CHARGE_LABELS.get(key, f"Benefit {key}")


def _rider_charge_label(key: str) -> str:
    plancode = key.split("_", 1)[0]
    for prefix, label in _RIDER_CHARGE_LABELS.items():
        if plancode.startswith(prefix):
            return label
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

    benefit_keys: list[str] = []
    rider_keys: list[str] = []
    for state in projected:
        for key in state.benefit_charge_detail:
            if key not in benefit_keys:
                benefit_keys.append(key)
        for key in state.rider_charge_detail:
            if key not in rider_keys:
                rider_keys.append(key)

    bands = [ChargeBand("Base COI")]
    bands.append(ChargeBand("Expense / Unit"))
    bands.append(ChargeBand("Monthly Fee"))
    has_av_charge = any(s.av_charge > 0 for s in projected)
    if has_av_charge:
        bands.append(ChargeBand("AV Charge"))
    for key in benefit_keys:
        bands.append(ChargeBand(_benefit_charge_label(key)))
    for key in rider_keys:
        bands.append(ChargeBand(_rider_charge_label(key)))

    totals = [0.0] * len(bands)
    for state in projected:
        x = xs(state)
        values = [_base_coi_charge(state), state.epu_charge, state.mfee_charge]
        if has_av_charge:
            values.append(state.av_charge)
        values.extend(state.benefit_charge_detail.get(key, 0.0) for key in benefit_keys)
        values.extend(state.rider_charge_detail.get(key, 0.0) for key in rider_keys)
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
