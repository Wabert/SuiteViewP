"""Illustration Inputs tab UI."""

from copy import deepcopy
from datetime import date, datetime
import logging
from typing import Optional

from dateutil.relativedelta import relativedelta
from PyQt6.QtCore import QDate, QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDoubleValidator
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractItemDelegate,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    InforceOverrideSet,
    PolicyChangeEvent,
    PolicyChangeKind,
    RollbackOverrideSet,
    validate_record_values,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.index_strategies import ag49_regimes, is_iul_plan
from suiteview.illustration.models.app_settings import get_illustration_settings
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.core.run_input_compiler import ControlDraft, InputDraft
from suiteview.polview.ui.formatting import format_date
from suiteview.ui.signals import muted_signals

from .inputs_dynamic import DynamicInputsPanel
from .issue_conditions import IssueConditionsPanel
from .styles import (
    GROUP_STYLE,
    INPUT_RADIO_STYLE,
    INPUT_TABLE_STYLE,
    ISSUE_BLUE_BG,
    ISSUE_BLUE_DARK,
    ISSUE_BLUE_PRIMARY,
    ISSUE_TAB_WIDGET_STYLE,
    PURPLE_BG,
    PURPLE_DARK,
    PURPLE_LIGHT,
    TAB_WIDGET_STYLE,
    apply_input_checkbox_style,
)
from suiteview.polview.models.policy_sections.lookup import policy_attr

logger = logging.getLogger(__name__)

# What each AG49 regime means for the illustration, keyed by regime index
# (the regime names/dates themselves come from index_strategies.json).
AG49_REGIME_NOTES = {
    1: "Issued before AG49 — the illustration still applies the original "
       "AG49 rules (the regime floor).",
    2: "Illustrated index rates capped at the benchmark index account's "
       "maximum; IP/IR multiplier crediting and asset charge apply; "
       "variable-loan credit spread up to 1.00%.",
    3: "Multipliers and bonuses may not illustrate better than the fixed "
       "account — IP/IR multiplier crediting and asset charge drop out; "
       "variable-loan credit spread capped at 0.50%.",
    4: "Extends the AG49-A caps to strategies benchmarked on the fixed "
       "account; variable-loan credit spread remains capped at 0.50%.",
}


def _ordinal(day: int) -> str:
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


LOAN_TOGGLE_STYLE = f"""
    QPushButton {{
        background-color: #F3ECFC;
        color: {PURPLE_DARK};
        border: 1px solid #7E57C2;
        border-radius: 4px;
        padding: 1px 10px;
        min-height: 20px;
        font-size: 11px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: #E6DAF8;
    }}
    QPushButton:checked {{
        background-color: #5E35A5;
        color: #FFD54F;
        border-color: #4B2383;
    }}
"""


class NavigationDelegate(QStyledItemDelegate):
    """Item delegate that keeps arrow-key navigation at the table level."""

    NAVIGATION_KEYS = {
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
        Qt.Key.Key_Up,
        Qt.Key.Key_Down,
        Qt.Key.Key_Return,
        Qt.Key.Key_Enter,
        Qt.Key.Key_Tab,
        Qt.Key.Key_Backtab,
    }

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        return self._prepare_editor(editor)

    def eventFilter(self, editor, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in self.NAVIGATION_KEYS:
            table = self.parent()
            if isinstance(table, ExcelTableWidget):
                self.commitData.emit(editor)
                self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
                table.navigate_by_key(event.key())
                return True
        return super().eventFilter(editor, event)

    def _prepare_editor(self, editor):
        if editor is not None:
            editor.installEventFilter(self)
        return editor


class ComboBoxDelegate(NavigationDelegate):
    """Simple combobox delegate for editable table columns."""

    def __init__(self, options: list[str], parent=None):
        super().__init__(parent)
        self._options = options

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItems(self._options)
        editor.setEditable(False)
        return self._prepare_editor(editor)

    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.EditRole) or index.data(Qt.ItemDataRole.DisplayRole) or ""
        value = str(value)
        combo_index = editor.findText(value)
        if combo_index >= 0:
            editor.setCurrentIndex(combo_index)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)


class ExcelTableWidget(QTableWidget):
    """QTableWidget with Excel-like arrow-key navigation and clipboard paste."""

    populate_policy_transactions_requested = pyqtSignal()
    MAX_PASTE_ROWS = 2000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy_transaction_population_enabled = False

    def init_rows(self, start: int, end: int):
        """Create 20px rows of empty right-aligned items for ``start..end-1``.

        The first column centers when it holds a Date/Year (matches the
        original table setup); paste growth reuses this so new rows look the
        same as the built-in ones.
        """
        header_item = self.horizontalHeaderItem(0)
        center_first = header_item is not None and header_item.text() in {"Date", "Year"}
        for row in range(start, end):
            self.setRowHeight(row, 20)
            for col in range(self.columnCount()):
                item = QTableWidgetItem("")
                if col == 0 and center_first:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(row, col, item)

    def contextMenuEvent(self, event):
        index = self.indexAt(event.pos())
        menu = QMenu(self)
        paste_action = menu.addAction("Paste from Clipboard")
        paste_action.setEnabled(bool((QApplication.clipboard().text() or "").strip()))
        populate_action = None
        if self.policy_transaction_population_enabled:
            menu.addSeparator()
            populate_action = menu.addAction("Populate from policy transactions")
        selected_action = menu.exec(event.globalPos())
        if selected_action is paste_action:
            row = index.row() if index.isValid() else max(self.currentRow(), 0)
            col = index.column() if index.isValid() else max(self.currentColumn(), 0)
            self.paste_from_clipboard(row, col)
        elif populate_action is not None and selected_action is populate_action:
            self.populate_policy_transactions_requested.emit()

    def paste_from_clipboard(self, start_row: int, start_col: int = 0):
        self.paste_text(QApplication.clipboard().text() or "", start_row, start_col)

    def paste_text(self, text: str, start_row: int, start_col: int = 0):
        """Paste tab-separated rows (an Excel range) starting at the given cell.

        Capped at ``MAX_PASTE_ROWS`` rows; the table grows to fit. Columns past
        the table's last column are dropped.
        """
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        while lines and not lines[-1].strip():
            lines.pop()
        lines = lines[: self.MAX_PASTE_ROWS]
        if not lines:
            return
        start_row = max(start_row, 0)
        start_col = max(start_col, 0)
        needed = start_row + len(lines)
        if needed > self.rowCount():
            grown_from = self.rowCount()
            self.setRowCount(needed)
            self.init_rows(grown_from, needed)
        for row_offset, line in enumerate(lines):
            for col_offset, value in enumerate(line.split("\t")):
                col = start_col + col_offset
                if col >= self.columnCount():
                    break
                item = self.item(start_row + row_offset, col)
                if item is not None:
                    item.setText(value.strip())

    def keyPressEvent(self, event):
        key = event.key()
        if key in {
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Tab,
            Qt.Key.Key_Backtab,
        }:
            self.navigate_by_key(key)
            return

        super().keyPressEvent(event)

    def navigate_by_key(self, key):
        if self.rowCount() == 0 or self.columnCount() == 0:
            return

        current_row = max(self.currentRow(), 0)
        current_col = max(self.currentColumn(), 0)
        next_row, next_col = current_row, current_col

        if key == Qt.Key.Key_Left:
            next_col = max(0, current_col - 1)
        elif key == Qt.Key.Key_Right:
            next_col = min(self.columnCount() - 1, current_col + 1)
        elif key == Qt.Key.Key_Up:
            next_row = max(0, current_row - 1)
        elif key == Qt.Key.Key_Down:
            next_row = min(self.rowCount() - 1, current_row + 1)
        elif key in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            next_row = min(self.rowCount() - 1, current_row + 1)
        elif key == Qt.Key.Key_Tab:
            if current_col < self.columnCount() - 1:
                next_col = current_col + 1
            else:
                next_col = 0
                next_row = min(self.rowCount() - 1, current_row + 1)
        elif key == Qt.Key.Key_Backtab:
            if current_col > 0:
                next_col = current_col - 1
            else:
                next_col = self.columnCount() - 1
                next_row = max(0, current_row - 1)

        self.setCurrentCell(next_row, next_col)
        item = self.item(next_row, next_col)
        if item is not None:
            QTimer.singleShot(0, lambda: self.editItem(item))


class IllustrationInputsTab(QWidget):
    """First-pass Illustration Inputs UI for premiums and loans."""

    run_from_issue_changed = pyqtSignal(bool)
    issue_conditions_changed = pyqtSignal()
    rollback_changed = pyqtSignal()

    WARNING_BG = QColor("#FFF0B3")
    NORMAL_BG = QColor("#FFFFFF")
    GRID_INPUTS_TAB_LABEL = "Grid Inputs"

    _EXCEPTION_TOOLTIP = (
        "Allow the guideline-premium exception premium when the policy is "
        "guideline-limited and would otherwise lapse. A Prem to Maturity run "
        "always allows exceptions regardless of this setting."
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._warning_labels: dict[str, QLabel] = {}
        self._pending_warning_refresh: set[str] = set()
        self._issue_date: date | None = None
        self._maturity_date: date | None = None
        self._loaded_policy = None
        self._valuation_date: date | None = None
        self._rollback_overrides: RollbackOverrideSet | None = None
        self._rollback_live_inputs = None
        self._basis_default_dynamic = None
        self._active_issue_mode = False
        self._mode_inputs = {}
        self._default_input_state = None
        self._issue_load_error = ""
        self._setup_ui()
        # ABR Quote (Options menu) locks every Input-tab control except the
        # Illustrated Rate. Re-apply live whenever the app-wide toggle flips,
        # and seed the current state now.
        get_illustration_settings().abr_quote_mode_changed.connect(
            self._apply_abr_quote_mode)
        self._apply_abr_quote_mode(get_illustration_settings().abr_quote_mode)
        get_illustration_settings().rollback_enabled_changed.connect(
            self._on_rollback_option_changed)

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 12)
        outer.setSpacing(6)

        # Saved-case as-of strip: visible whenever the tab shows a saved case
        # rather than live policy data — the user must never mistake a frozen
        # snapshot for the current policy. Same warning-strip pattern as the
        # suspended/exception notices.
        self.snapshot_banner = QLabel("")
        self.snapshot_banner.setWordWrap(True)
        self.snapshot_banner.setStyleSheet(
            "color: #5C3A00; background-color: #FFF4D6; border: 1px solid #D4A017;"
            " border-radius: 4px; padding: 5px 9px; font-size: 11px; font-weight: bold;")
        self.snapshot_banner.setVisible(False)
        outer.addWidget(self.snapshot_banner)

        self.run_from_issue_btn = QPushButton("Inforce | New Business - From Issue")
        self.run_from_issue_btn.setCheckable(True)
        self.run_from_issue_btn.setToolTip(
            "Start a true new-business projection on the policy issue date. "
            "Opening inforce balances are reset to zero; current illustration "
            "rates and the current Policy-tab snapshot remain unchanged.")
        self.run_from_issue_btn.toggled.connect(self._apply_run_from_issue)
        outer.addWidget(self.run_from_issue_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self._style_run_from_issue_button(False)

        self.valuation_banner = self._build_valuation_banner()
        outer.addWidget(self.valuation_banner)

        self.input_tabs = QTabWidget(self)
        self.input_tabs.setStyleSheet(TAB_WIDGET_STYLE)
        self.dynamic_panel = DynamicInputsPanel(self)
        self.abr_minimum_face_row = self._build_abr_minimum_face_row(
            self.dynamic_panel
        )
        self.dynamic_panel.layout().insertWidget(2, self.abr_minimum_face_row)
        self.input_tabs.addTab(self.dynamic_panel, "Input")
        self.transaction_tab = self._build_transaction_tab()
        self.control_tab = self._build_control_tab()
        self._grid_inputs_tab_index = self.input_tabs.addTab(
            self.transaction_tab, self.GRID_INPUTS_TAB_LABEL)
        self.input_tabs.addTab(self.control_tab, "Illustration Control")
        self.issue_conditions = IssueConditionsPanel(self)
        self.issue_conditions.changed.connect(self._on_issue_conditions_changed)
        self.input_tabs.addTab(self.issue_conditions, "At-Issue Conditions")
        outer.addWidget(self.input_tabs, 1)

        self.mode_warning = QLabel("")
        self.mode_warning.setWordWrap(True)
        self.mode_warning.setStyleSheet(
            "color: #8B1A2A; background: #FFF4D6; padding: 4px;")
        self.mode_warning.setVisible(False)
        outer.addWidget(self.mode_warning)

        # Grid Inputs is power-user territory (raw dated-transaction tables) —
        # hidden by default so the tab bar stays lean; a right-click on the
        # tab bar lets the user bring it back. Per-case, not global: see
        # capture_case_inputs/apply_case_inputs.
        self.input_tabs.setTabVisible(self._grid_inputs_tab_index, False)
        self.input_tabs.tabBar().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.input_tabs.tabBar().customContextMenuRequested.connect(
            self._show_input_tabs_context_menu)

        # Level-solve × future-change caveat: Max Level and Prem to
        # Maturity both solve a level premium against the funding/guideline
        # room measured from the forecast date, but a change AFTER the forecast
        # date can shift that room (a DB option switch reads the account value;
        # a face/rate-class/table change recalculates the guideline premiums; a
        # withdrawal drains the funding) — so the solved figure may be off.
        # Changes ON the forecast date are safe. Loan repayments never trigger
        # it (they are allowed outright). The run is still allowed; this strip
        # is the caveat. It lives at the BOTTOM of the Input panel (under Riders
        # and Benefits) so popping up never shifts the controls above it.
        self.level_solve_caveat_banner = QLabel(
            "The solved premium may be affected by changes scheduled after the "
            "forecast date — a face amount, death-benefit option, rider, "
            "rate-class, table-rating or withdrawal change entered later can "
            "shift the funding the solve measures. Changes on the forecast date "
            "are fine. The illustration will still run with this caveat.")
        self.level_solve_caveat_banner.setWordWrap(True)
        self.level_solve_caveat_banner.setStyleSheet(
            "color: #5C3A00; background-color: #FFF4D6; border: 1px solid #D4A017;"
            " border-radius: 4px; padding: 5px 9px; font-size: 11px; font-weight: bold;")
        self.level_solve_caveat_banner.setVisible(False)
        self.dynamic_panel.layout().addWidget(self.level_solve_caveat_banner)

        # Live caveat refresh: every surface that can create/clear a level-solve
        # premium row or a triggering change (dynamic sections, the riders
        # panel, and the dated grid tables) re-evaluates the strip. Withdrawals,
        # rate-class and table changes are now editable under the two level
        # solves, so they are watched too.
        for section in (self.dynamic_panel.premium_section,
                        self.dynamic_panel.face_section,
                        self.dynamic_panel.dbo_section,
                        self.dynamic_panel.withdrawal_section,
                        self.dynamic_panel.rateclass_section,
                        self.dynamic_panel.table_section):
            section.changed.connect(self._refresh_level_solve_caveat)
        self.dynamic_panel.riders_panel.changed.connect(
            self._refresh_level_solve_caveat)
        for grid in (self.face_amount_table, self.db_option_table,
                     self.withdrawal_table):
            grid.itemChanged.connect(
                lambda _item: self._refresh_level_solve_caveat())

    # ── Grid Inputs tab visibility (right-click the input_tabs tab bar) ──
    #
    # Hidden by default (power-user surface); toggled per-case, not global —
    # see capture_case_inputs/apply_case_inputs.

    def _show_input_tabs_context_menu(self, pos):
        menu = QMenu(self.input_tabs.tabBar())
        menu.setStyleSheet(
            f"QMenu {{ background: white; color: {PURPLE_DARK};"
            f" border: 1px solid {PURPLE_LIGHT}; }}"
            "QMenu::item { padding: 4px 20px; }"
            "QMenu::item:selected { background: #E6DAF8; color: #4B2383; }"
        )
        action = menu.addAction(self.GRID_INPUTS_TAB_LABEL)
        action.setCheckable(True)
        action.setChecked(self.grid_inputs_tab_visible())
        action.toggled.connect(self._set_grid_inputs_tab_visible)
        menu.exec(self.input_tabs.tabBar().mapToGlobal(pos))

    def grid_inputs_tab_visible(self) -> bool:
        return self.input_tabs.isTabVisible(self._grid_inputs_tab_index)

    def _set_grid_inputs_tab_visible(self, visible: bool):
        if not visible and self.input_tabs.currentIndex() == self._grid_inputs_tab_index:
            # Hiding the current tab must never leave a blank pane — land on
            # the always-visible "Input" tab instead.
            self.input_tabs.setCurrentIndex(0)
        self.input_tabs.setTabVisible(self._grid_inputs_tab_index, visible)
        if visible:
            self.input_tabs.setCurrentIndex(self._grid_inputs_tab_index)

    def _build_valuation_banner(self):
        """Compact date strip: valuation date, monthliversary day, first forecast month.

        Dated inputs must land on monthliversary dates and the projection's
        first row is one month after the valuation date — surfacing all three
        here saves the user a trip back to the Policy tab.
        """
        banner = QWidget(self)
        banner.setStyleSheet(
            "background-color: #2A1458; border: 1px solid #5E35A5; border-radius: 4px;"
        )
        row = QHBoxLayout(banner)
        row.setContentsMargins(10, 3, 10, 3)
        row.setSpacing(18)

        def _pair(caption: str):
            cap = QLabel(caption)
            cap.setStyleSheet(
                "color: #B79CDE; background: transparent; border: none; font-size: 10px;"
            )
            val = QLabel("—")
            val.setStyleSheet(
                "color: #FFD54F; background: transparent; border: none;"
                " font-size: 11px; font-weight: bold;"
            )
            row.addWidget(cap)
            row.addWidget(val)
            return val

        self.banner_valuation_label = _pair("Valuation Date")
        self.banner_monthliversary_label = _pair("Monthliversary Day")
        self.banner_first_forecast_label = _pair("First Forecast Month")
        self.banner_policy_year_label = _pair("Policy Year")
        self.banner_face_label = _pair("Face Amount")
        self.banner_rateclass_label = _pair("Rateclass")
        self.banner_db_option_label = _pair("DB Option")
        row.addStretch(1)
        # Anchored at the far right: current total policy debt. Always
        # visible — "0" means loan-free, never a hidden field.
        self.banner_policy_debt_label = _pair("Policy Debt")
        return banner

    def _build_transaction_tab(self):
        tab = QWidget(self)
        tab.setStyleSheet(f"background-color: {PURPLE_BG};")
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        content_row = QHBoxLayout()
        content_row.setSpacing(10)

        left_panel = QWidget(self)
        left_panel.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        left_panel.setMinimumWidth(300)
        left_panel.setMaximumWidth(340)

        left_column = QVBoxLayout()
        left_column.setSpacing(8)
        left_column.addWidget(self._build_scheduled_premium_group())
        left_column.addWidget(self._build_scheduled_loan_group())
        left_column.addWidget(self._build_face_amount_group())
        left_column.addWidget(self._build_db_option_group())
        left_column.addStretch(1)
        left_panel.setLayout(left_column)

        right_column = QHBoxLayout()
        right_column.setSpacing(8)
        right_column.addWidget(self._build_unscheduled_premium_group(), 1)
        right_column.addWidget(self._build_specific_loan_group(), 1)
        right_column.addWidget(self._build_loan_repayment_group(), 1)
        right_column.addWidget(self._build_withdrawal_group(), 1)

        content_row.addWidget(left_panel)
        content_row.addLayout(right_column, 1)
        outer.addLayout(content_row)
        outer.addStretch(1)
        return tab

    def _build_abr_minimum_face_row(self, parent: QWidget) -> QWidget:
        row = QWidget(parent)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        label = QLabel("Minimum Face Amount Allowed:")
        label.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; "
            "font-weight: bold;"
        )
        self.abr_minimum_face_edit = QLineEdit()
        self.abr_minimum_face_edit.setValidator(
            QDoubleValidator(0.01, 1_000_000_000.0, 2, self.abr_minimum_face_edit)
        )
        self.abr_minimum_face_edit.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.abr_minimum_face_edit.setFixedWidth(120)
        self.abr_minimum_face_edit.setPlaceholderText("Required")
        self.abr_minimum_face_edit.setStyleSheet(self._control_input_style())
        self.abr_minimum_face_edit.setToolTip(
            "Minimum face amount allowed after a maximum partial acceleration. "
            "Run Values uses it to calculate the next monthly deduction."
        )
        row_layout.addWidget(label)
        row_layout.addWidget(self.abr_minimum_face_edit)
        row_layout.addStretch(1)
        return row

    def _build_control_tab(self):
        tab = QWidget(self)
        tab.setStyleSheet(f"background-color: {PURPLE_BG};")
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        group = QGroupBox("Run Controls")
        group.setStyleSheet(GROUP_STYLE)
        # Two columns: the editable controls pack down the left, the two
        # always-on locked controls sit off to the right where they stay
        # visible (never hidden) but out of the working area.
        group_row = QHBoxLayout(group)
        group_row.setContentsMargins(10, 18, 10, 10)
        group_row.setSpacing(24)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        locked_column = QVBoxLayout()
        locked_column.setContentsMargins(0, 0, 0, 0)
        locked_column.setSpacing(6)
        group_row.addLayout(layout)
        group_row.addStretch(1)
        group_row.addLayout(locked_column)

        # Illustration Duration (Illustration to Date / Illustration Years) sits
        # at the top of the working column; it is gated by "Enable Illustration
        # Options" below, just like Conform to TEFRA/DEFRA and Stop on Lapse.
        self._add_illustration_duration_controls(layout)

        self.exact_days_check = self._make_control_checkbox("Exact Days Interest")
        self.exact_days_check.setToolTip("Checked uses exact-days interest; unchecked uses monthly compounding.")
        layout.addWidget(self.exact_days_check)

        # "Enable Illustration Options" unlocks the two normally-locked controls
        # below (Conform to TEFRA/DEFRA and Stop Projection on Lapse). Off by
        # default so those controls stay locked-on for a normal illustration;
        # the user opts in to override them.
        self.enable_illustration_options_check = self._make_control_checkbox(
            "Enable Illustration Options")
        self.enable_illustration_options_check.setChecked(False)
        self.enable_illustration_options_check.setToolTip(
            "Unlock the illustration options below (Conform to TEFRA/DEFRA and "
            "Stop Projection on Lapse) so they can be toggled off.")
        self.enable_illustration_options_check.toggled.connect(
            self._apply_illustration_options_enabled)
        locked_column.addWidget(self.enable_illustration_options_check)

        # Conform to TEFRA/DEFRA is normally on: an illustration that ignores the
        # 7702 guideline room can quietly produce premiums the policy could
        # never accept. Locked on until "Enable Illustration Options" is checked.
        self.tefra_check = self._make_control_checkbox("Conform to TEFRA/DEFRA")
        self.tefra_check.setChecked(True)
        self.tefra_check.setEnabled(False)
        self.tefra_check.setToolTip(
            "Normally on — 7702 guideline premium room is enforced for force-outs "
            "and accepted premiums. Enable Illustration Options to toggle it off.")
        locked_column.addWidget(self.tefra_check)

        # Conform to TAMRA lives on the Input sheet (dynamic_panel); read it
        # from there in export_options().

        # Allow GP Exception Premium (sINPUT_AllowExceptionPrems). OFF by
        # default — exception premiums past the guideline are the unusual case,
        # so the user opts in. The Input panel signals availability — an active
        # shadow account forces it off (the shadow account governs lapse, not
        # the exception premium). Prem to Maturity and Billable to MD runs
        # always allow exceptions regardless of this checkbox.
        self.exception_prem_check = self._make_control_checkbox("Allow GP Exception Premium")
        self.exception_prem_check.setChecked(False)
        self.exception_prem_check.setToolTip(self._EXCEPTION_TOOLTIP)
        layout.addWidget(self.exception_prem_check)
        self.dynamic_panel.exception_availability_changed.connect(
            self._apply_exception_availability)

        # No "Cap Premiums at Acceptance" control: capping premiums at the
        # guideline room is part of Conform to TEFRA/DEFRA, which is locked on.
        # IllustrationOptions.cap_premiums_at_acceptance stays an internal-only
        # escape hatch (PolView's GLP-exception solver sets it).

        self.levelizing_check = self._make_control_checkbox("Levelized capped premiums (off for loans)")
        self.levelizing_check.setChecked(True)
        self.levelizing_check.setToolTip(
            "When a premium cap binds, spread the allowed premium evenly across the "
            "year's modal payments instead of billing each in full until the annual "
            "room runs out mid-year. Automatically disabled on a policy that carries a loan."
        )
        layout.addWidget(self.levelizing_check)

        self.gp_search_check = self._make_control_checkbox("Find GP/TAMRA by Search Routine")
        self.gp_search_check.setToolTip(
            "Solve GLP/GSP/7-pay by premium search on the calc engine (guaranteed COIs, "
            "statutory interest, current expenses) instead of the monthly commutation formula."
        )
        layout.addWidget(self.gp_search_check)

        # Loan repayment order (fix E03). Off is RERUN's conservative default —
        # a repayment pays accrued loan interest first; on matches CyberLife,
        # which applies a repayment to principal while interest keeps accruing.
        self.loan_principal_first_check = self._make_control_checkbox(
            "Loan Repayments Pay Principal First")
        self.loan_principal_first_check.setChecked(False)
        self.loan_principal_first_check.setToolTip(
            "Checked applies a loan repayment to loan principal before accrued "
            "loan interest (as CyberLife does). Unchecked (default, conservative) "
            "pays accrued interest first. Interest-in-advance loans are unaffected.")
        layout.addWidget(self.loan_principal_first_check)

        # Normally on: rows past the lapse test are not a real illustration.
        # Locked on until "Enable Illustration Options" is checked.
        self.stop_on_lapse_check = self._make_control_checkbox("Stop Projection on Lapse")
        self.stop_on_lapse_check.setChecked(True)
        self.stop_on_lapse_check.setEnabled(False)
        self.stop_on_lapse_check.setToolTip(
            "Normally on — projection rows stop once the lapse test fails. "
            "Enable Illustration Options to toggle it off.")
        locked_column.addWidget(self.stop_on_lapse_check)

        # Switch to Option A in the exception period — off by default. When on,
        # an Option B policy that enters the GP exception period is re-run under
        # Option A (level death benefit) assumptions, which changes the COI
        # saving that discounts the exception premium. Locked off until "Enable
        # Illustration Options" is checked.
        self.switch_to_option_a_check = self._make_control_checkbox(
            "Switch to Option A in exception period")
        self.switch_to_option_a_check.setChecked(False)
        self.switch_to_option_a_check.setEnabled(False)
        self.switch_to_option_a_check.setToolTip(
            "When an Option B policy enters the GP exception period, re-run it "
            "under Option A (level death benefit) assumptions — this changes the "
            "exception premium discount. Enable Illustration Options to toggle it on.")
        locked_column.addWidget(self.switch_to_option_a_check)
        locked_column.addStretch(1)

        note = QLabel("Unchecked Exact Days uses monthly compounding.")
        note.setStyleSheet(f"color: {PURPLE_DARK}; background: transparent; font-size: 10px; font-style: italic;")
        layout.addWidget(note)
        layout.addStretch(1)

        outer.addWidget(group, 0, Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self._build_iul_crediting_group(), 0, Qt.AlignmentFlag.AlignTop)
        outer.addStretch(1)
        # Initialize the gated-control enabled state now that every widget the
        # "Enable Illustration Options" switch governs (including the duration
        # controls) exists.
        self._apply_illustration_options_enabled(
            self.enable_illustration_options_check.isChecked())
        return tab

    def _build_iul_crediting_group(self):
        """IUL-only controls — greyed out on declared-rate plans."""
        group = QGroupBox("IUL Crediting")
        group.setStyleSheet(GROUP_STYLE + (
            "QGroupBox:disabled { border: 2px solid #C9B8E4; background-color: #F2EEF8; }"
            "QGroupBox::title:disabled { color: #F2EEF8; background-color: #9B8BBE; border: 1px solid #C9B8E4; }"
        ))
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 18, 10, 10)
        layout.setSpacing(6)

        self.iul_na_note = QLabel("Not applicable — declared-rate plan (no index strategies).")
        self.iul_na_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.iul_na_note.setStyleSheet(
            "color: #8A7BA8; background: transparent; font-size: 10px; font-style: italic;")
        layout.addWidget(self.iul_na_note)

        self.iul_rate_method_group = QButtonGroup(self)
        self.iul_rate_method_group.setExclusive(True)
        self.blended_rate_radio = self._make_control_radio("Blended Rate")
        self.blended_rate_radio.setToolTip(
            "Credit one blended rate — Σ allocation % × illustrated rate (the "
            "RERUN INPUT-sheet blend). The simpler method; the default.")
        self.wair_radio = self._make_control_radio("Weighted Average Interest Rate (WAIR)")
        self.wair_radio.setToolTip(
            "Weight the sweep-minimum, loaned, and indexed slices of the account "
            "value by their own rates (RERUN CalcEngine TAV/WAIR block).")
        self.iul_rate_method_group.addButton(self.blended_rate_radio)
        self.iul_rate_method_group.addButton(self.wair_radio)
        self.blended_rate_radio.setChecked(True)
        layout.addWidget(self.blended_rate_radio)
        layout.addWidget(self.wair_radio)

        self.policy_ag49_check = self._make_control_checkbox("Use Policy AG49 Regime")
        self.policy_ag49_check.setToolTip(
            "Illustrate under the AG49 regime in effect at policy issue (Prior to "
            "AG49 / AG49 / AG49A / AG49B by issue date) instead of the current "
            "regime. Affects multiplier crediting, the IP/IR asset charge, and "
            "the variable-loan credit spread.")
        self.policy_ag49_check.toggled.connect(
            self.dynamic_panel.set_use_policy_ag49_regime)
        self.policy_ag49_check.toggled.connect(self._update_ag49_regime_panel)
        layout.addWidget(self.policy_ag49_check)
        layout.addWidget(self._build_ag49_regime_panel())
        self._update_ag49_regime_panel()
        self.iul_crediting_group = group
        # Greyed until an IUL policy loads — declared-rate plans don't credit
        # an indexed rate.
        self._set_iul_crediting_applicable(False)
        return group

    def _set_iul_crediting_applicable(self, applicable: bool):
        """Grey the IUL Crediting group on non-IUL plans (greyed, never hidden)."""
        self.iul_crediting_group.setEnabled(applicable)
        self.iul_na_note.setVisible(not applicable)

    def _build_ag49_regime_panel(self):
        """Read-only regime rows under 'Use Policy AG49 Regime' — one per AG49
        regime with its effective date and what it means for the illustration.
        The row matching the policy issue date is auto-selected; the panel is
        greyed while the checkbox is off."""
        panel = QWidget(self)
        panel.setStyleSheet("background: transparent;")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 2, 0, 0)
        panel_layout.setSpacing(1)

        self._ag49_regime_radios: dict[int, QRadioButton] = {}
        regimes = ag49_regimes()
        for pos, regime in enumerate(regimes):
            if regime["index"] == 1:
                next_start = regimes[pos + 1]["start"] if pos + 1 < len(regimes) else None
                title = "(none)"
                if next_start is not None:
                    title += f" — issued before {format_date(next_start)}"
            else:
                title = f"{regime['name']} — effective {format_date(regime['start'])}"
            radio = self._make_control_radio(title)
            # Display-only: the selection is derived from the policy issue
            # date, never clicked by the user.
            radio.setAutoExclusive(False)
            radio.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            radio.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            note = QLabel(AG49_REGIME_NOTES.get(regime["index"], ""))
            note.setWordWrap(True)
            note.setStyleSheet(
                f"QLabel {{ color: {PURPLE_DARK}; background: transparent;"
                " font-size: 10px; font-style: italic; margin-left: 18px; }"
                "QLabel:disabled { color: #9A8FB0; }"
            )
            panel_layout.addWidget(radio)
            panel_layout.addWidget(note)
            self._ag49_regime_radios[regime["index"]] = radio

        self._ag49_regime_panel = panel
        return panel

    def _ag49_issue_tier(self) -> Optional[int]:
        """The AG49 regime in effect on the policy issue date — unfloored, so a
        pre-AG49 issue resolves to the '(none)' row (the engine still floors
        its applicable index at AG49)."""
        if self._issue_date is None:
            return None
        tier = None
        for regime in ag49_regimes():
            if self._issue_date >= regime["start"]:
                tier = regime["index"]
        return tier

    def _update_ag49_regime_panel(self):
        use_policy = self.policy_ag49_check.isChecked()
        self._ag49_regime_panel.setEnabled(use_policy)
        tier = self._ag49_issue_tier() if use_policy else None
        for index, radio in self._ag49_regime_radios.items():
            radio.setChecked(index == tier)

    def _add_illustration_duration_controls(self, layout):
        """Add the Illustration Duration controls (Illustration to Date /
        Illustration Years) to ``layout``. Gated by "Enable Illustration
        Options" — see ``_apply_illustration_options_enabled`` /
        ``_sync_duration_controls``."""
        heading = QLabel("Illustration Duration")
        heading.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; "
            "font-weight: bold;")
        layout.addWidget(heading)

        self.duration_mode_group = QButtonGroup(self)
        self.duration_mode_group.setExclusive(True)

        # A grid keeps the radio labels in column 0 and the inputs in column 1,
        # so the date edit and the years combo share one left edge and line up
        # even though the two labels differ in width.
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        self.illustration_to_date_radio = self._make_control_radio("Illustration to Date")
        self.illustration_to_date_edit = QDateEdit(self)
        self.illustration_to_date_edit.setCalendarPopup(True)
        self.illustration_to_date_edit.setDisplayFormat("MM/dd/yyyy")
        self.illustration_to_date_edit.setDate(QDate.currentDate())
        self.illustration_to_date_edit.setStyleSheet(self._control_input_style())
        self.illustration_to_date_edit.setMinimumWidth(120)
        self.duration_mode_group.addButton(self.illustration_to_date_radio)
        grid.addWidget(self.illustration_to_date_radio, 0, 0)
        grid.addWidget(self.illustration_to_date_edit, 0, 1)

        self.illustration_years_radio = self._make_control_radio("Illustration Years")
        self.illustration_years_combo = QComboBox(self)
        self.illustration_years_combo.setEditable(True)
        self.illustration_years_combo.addItems(["1", "2", "10", "20", "Age 65", "To Maturity"])
        self.illustration_years_combo.setCurrentText("To Maturity")
        self.illustration_years_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.illustration_years_combo.setStyleSheet(self._control_input_style())
        self.illustration_years_combo.setMinimumWidth(120)
        self.duration_mode_group.addButton(self.illustration_years_radio)
        grid.addWidget(self.illustration_years_radio, 1, 0)
        grid.addWidget(self.illustration_years_combo, 1, 1)

        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)

        self.illustration_years_radio.setChecked(True)
        self.illustration_to_date_radio.toggled.connect(self._sync_duration_controls)
        self.illustration_years_radio.toggled.connect(self._sync_duration_controls)

    def _apply_exception_availability(self, available: bool, reason: str):
        """The Input panel gates GP exceptions per policy (active shadow
        account): force the Run Controls checkbox off with the reason as its
        tooltip while blocked; re-enable it when the block lifts."""
        if available:
            self.exception_prem_check.setEnabled(True)
            self.exception_prem_check.setToolTip(self._EXCEPTION_TOOLTIP)
        else:
            self.exception_prem_check.setChecked(False)
            self.exception_prem_check.setEnabled(False)
            self.exception_prem_check.setToolTip(reason)

    def _make_control_checkbox(self, text: str):
        checkbox = QCheckBox(text, self)
        apply_input_checkbox_style(checkbox)
        return checkbox

    def _make_control_radio(self, text: str):
        radio = QRadioButton(text, self)
        radio.setStyleSheet(INPUT_RADIO_STYLE)
        return radio

    @staticmethod
    def _control_input_style() -> str:
        return (
            "QComboBox, QDateEdit { background: white; color: #2A1458; border: 1px solid #B79CDE; "
            "border-radius: 4px; padding: 2px 6px; min-height: 20px; font-size: 11px; }"
            "QComboBox:disabled, QDateEdit:disabled { background: #E8DDF8; color: #7A6B91; }"
            "QComboBox::drop-down, QDateEdit::drop-down { border-left: 1px solid #B79CDE; width: 18px; }"
        )

    def _sync_duration_controls(self):
        # The duration controls are gated by "Enable Illustration Options": both
        # radios follow that switch, and only the active input (date vs years)
        # is enabled when the switch is on.
        options_on = self.enable_illustration_options_check.isChecked()
        self.illustration_to_date_radio.setEnabled(options_on)
        self.illustration_years_radio.setEnabled(options_on)
        use_date = self.illustration_to_date_radio.isChecked()
        self.illustration_to_date_edit.setEnabled(options_on and use_date)
        self.illustration_years_combo.setEnabled(options_on and not use_date)

    def _build_scheduled_premium_group(self):
        group = QGroupBox("Scheduled Premiums")
        group.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(3)

        table = self._make_table(4, ["Year", "Amount", "Mode"], min_height=112)
        table.setItemDelegateForColumn(2, ComboBoxDelegate(["M", "Q", "S", "A"], table))
        self.scheduled_premium_table = table
        layout.addWidget(table)
        return group

    def _build_scheduled_loan_group(self):
        group = QGroupBox("Scheduled Loans")
        group.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(3)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(4)
        toggle_label = QLabel("Loan Type:")
        toggle_label.setStyleSheet(f"color: {PURPLE_DARK}; font-size: 11px; font-weight: bold; background: transparent;")
        self.fixed_loan_toggle = QPushButton("Fixed")
        self.variable_loan_toggle = QPushButton("Variable")
        self.loan_type_group = QButtonGroup(self)
        self.loan_type_group.setExclusive(True)
        for button in [self.fixed_loan_toggle, self.variable_loan_toggle]:
            button.setCheckable(True)
            button.setStyleSheet(LOAN_TOGGLE_STYLE)
            self.loan_type_group.addButton(button)
            toggle_row.addWidget(button)
        self.fixed_loan_toggle.setChecked(True)
        toggle_row.insertWidget(0, toggle_label)
        toggle_row.addStretch(1)
        layout.addLayout(toggle_row)

        table = self._make_table(3, ["Year", "Amount", "Mode"], min_height=91)
        table.setItemDelegateForColumn(2, ComboBoxDelegate(["M", "Q", "S", "A"], table))
        self.scheduled_loan_table = table
        layout.addWidget(table)
        return group

    def _build_face_amount_group(self):
        group = QGroupBox("Face Amount")
        group.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(3)
        self.face_amount_table = self._make_table(2, ["Date", "New Face"], min_height=86)
        self.face_amount_table.itemChanged.connect(lambda item: self._validate_date_cell(self.face_amount_table, item, 0, "face_dates"))
        warning = self._make_warning_label(self._warning_text("Face amount change dates should be monthliversary dates."))
        self._warning_labels["face_dates"] = warning
        layout.addWidget(warning)
        layout.addWidget(self.face_amount_table)
        return group

    def _build_db_option_group(self):
        group = QGroupBox("DB Option")
        group.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(3)
        self.db_option_table = self._make_table(2, ["Date", "New DB Option"], min_height=86)
        self.db_option_table.itemChanged.connect(lambda item: self._validate_date_cell(self.db_option_table, item, 0, "db_option_dates"))
        warning = self._make_warning_label(self._warning_text("DB option change dates should be monthliversary dates."))
        self._warning_labels["db_option_dates"] = warning
        layout.addWidget(warning)
        layout.addWidget(self.db_option_table)
        return group

    def _build_unscheduled_premium_group(self):
        group = QGroupBox("Unscheduled Premiums")
        group.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(3)

        warning = self._make_warning_label(self._warning_text("Premium dates should be monthliversary dates."))
        self._warning_labels["premium_dates"] = warning
        layout.addWidget(warning)

        table = self._make_table(
            100,
            ["Date", "Amount", "Transaction Type"],
            min_height=520,
            stretch_columns=True,
        )
        table.policy_transaction_population_enabled = True
        table.populate_policy_transactions_requested.connect(
            self._populate_policy_premium_transactions
        )
        table.itemChanged.connect(lambda item: self._validate_date_cell(table, item, 0, "premium_dates"))
        self.unscheduled_premium_table = table
        layout.addWidget(table)
        return group

    def _populate_policy_premium_transactions(self):
        transactions = list(
            getattr(self._loaded_policy, "premium_transactions", None) or []
        )
        if not transactions:
            QMessageBox.information(
                self,
                "Policy Premium Transactions",
                "This policy has no unreversed PR, PI, PA, PF, PT, PB, or PW "
                "premium transactions to populate.",
            )
            return
        self._apply_grid(
            self.unscheduled_premium_table,
            [
                [
                    row,
                    [
                        transaction.effective_date.strftime("%m/%d/%Y"),
                        f"{transaction.amount:.2f}",
                        transaction.transaction_type,
                    ],
                ]
                for row, transaction in enumerate(transactions)
            ],
        )

    def _build_specific_loan_group(self):
        group = QGroupBox("Unscheduled Loans")
        group.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(3)

        warning = self._make_warning_label(self._warning_text("Loan dates should be monthliversary dates."))
        self._warning_labels["loan_dates"] = warning
        layout.addWidget(warning)

        table = self._make_table(100, ["Date", "Amount"], min_height=520, stretch_columns=True)
        table.itemChanged.connect(lambda item: self._validate_date_cell(table, item, 0, "loan_dates"))
        self.specific_loan_table = table
        layout.addWidget(table)
        return group

    def _build_loan_repayment_group(self):
        group = QGroupBox("Loan Repayments")
        group.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(3)

        warning = self._make_warning_label(self._warning_text("Loan repayment dates should be monthliversary dates."))
        self._warning_labels["loan_repayment_dates"] = warning
        layout.addWidget(warning)

        table = self._make_table(100, ["Date", "Amount"], min_height=520, stretch_columns=True)
        table.itemChanged.connect(lambda item: self._validate_date_cell(table, item, 0, "loan_repayment_dates"))
        self.loan_repayment_table = table
        layout.addWidget(table)
        return group

    def _build_withdrawal_group(self):
        group = QGroupBox("Withdrawals")
        group.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 14, 4, 4)
        layout.setSpacing(3)

        warning = self._make_warning_label(self._warning_text("Withdrawal dates should be monthliversary dates."))
        self._warning_labels["withdrawal_dates"] = warning
        layout.addWidget(warning)

        table = self._make_table(100, ["Date", "Amount", "Type"], min_height=520, stretch_columns=True)
        table.setItemDelegateForColumn(2, ComboBoxDelegate(["Net", "Gross"], table))
        table.itemChanged.connect(lambda item: self._validate_date_cell(table, item, 0, "withdrawal_dates"))
        self.withdrawal_table = table
        layout.addWidget(table)
        return group

    def _make_table(self, rows: int, headers: list[str], min_height: int, stretch_columns: bool = False):
        table = ExcelTableWidget(rows, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setStyleSheet(INPUT_TABLE_STYLE)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(False)
        table.setAlternatingRowColors(False)
        table.setMinimumHeight(min_height)
        table.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setTabKeyNavigation(False)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setItemDelegate(NavigationDelegate(table))

        table.init_rows(0, rows)

        if headers == ["Year", "Amount", "Mode"]:
            widths = [64, 110, 72]
        elif headers == ["Date", "Amount"]:
            widths = [96, 110]
        elif headers in (
            ["Date", "Amount", "Type"],
            ["Date", "Amount", "Transaction Type"],
        ):
            widths = [96, 104, 72]
        elif headers == ["Date", "New Face"]:
            widths = [96, 110]
        elif headers == ["Date", "New DB Option"]:
            widths = [96, 120]
        else:
            widths = [96] * len(headers)

        header = table.horizontalHeader()
        if stretch_columns:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        else:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            for col, width in enumerate(widths[: len(headers)]):
                table.setColumnWidth(col, width)

        return table

    def _make_warning_label(self, text: str):
        label = QLabel(text)
        label.setVisible(False)
        label.setProperty("base_text", text)
        label.setStyleSheet(
            f"color: {PURPLE_DARK}; background-color: #FFF0B3; border: 1px solid #D9B44A; "
            "border-radius: 4px; padding: 3px 6px; font-size: 10px;"
        )
        return label

    def _validate_date_cell(self, table: QTableWidget, item: QTableWidgetItem, date_column: int, warning_key: str):
        if item.column() != date_column:
            return

        text = (item.text() or "").strip()
        if not text:
            item.setBackground(self.NORMAL_BG)
            self._refresh_warning_state(table, date_column, warning_key)
            return

        if self._is_monthliversary(text):
            item.setBackground(self.NORMAL_BG)
        else:
            item.setBackground(self.WARNING_BG)
        self._refresh_warning_state(table, date_column, warning_key)

    def _refresh_warning_state(self, table: QTableWidget, date_column: int, warning_key: str):
        # Coalesce to one scan per event-loop turn — a clipboard paste fires
        # itemChanged per cell, and scanning the whole column each time is
        # O(rows²) on a 2,000-row paste.
        if warning_key in self._pending_warning_refresh:
            return
        self._pending_warning_refresh.add(warning_key)

        def scan():
            self._pending_warning_refresh.discard(warning_key)
            has_warning = False
            for row in range(table.rowCount()):
                item = table.item(row, date_column)
                if item and (item.text() or "").strip() and item.background().color() == self.WARNING_BG:
                    has_warning = True
                    break
            self._warning_labels[warning_key].setVisible(has_warning)

        QTimer.singleShot(0, scan)

    def set_snapshot_notice(self, text: str | None):
        """Show (or clear with None) the saved-case as-of strip."""
        self.snapshot_banner.setText(text or "")
        self.snapshot_banner.setVisible(bool(text))

    # ── Level-solve × future-change caveat ───────────────────────────

    def level_solve_change_caveat_active(self) -> bool:
        """True when a Max Level OR Prem to Maturity premium row is
        combined with a change effective AFTER the forecast date that can move
        the solved premium: a face amount / DB option / rider / rate-class /
        table-rating change (all flow through the exported input set's policy
        changes) or a withdrawal (a dated WITHDRAWAL transaction).

        Both level solves measure the funding/guideline room from the forecast
        date; a later change can shift that room, so the solved figure may be
        off. A change ON the forecast date is safe — its effect lands before
        any solved premium is paid. Loan repayments never trigger the caveat
        (they are allowed outright). The illustration still runs; this is only
        a caveat.
        """
        panel = self.dynamic_panel
        ctx = getattr(panel, "_ctx", None)
        forecast = getattr(ctx, "forecast_date", None)
        if forecast is None:
            return False
        if panel.max_level_request() is None and panel.min_level_request() is None:
            return False
        input_set = self.export_input_set()
        if any(change.effective_date is not None
               and change.effective_date > forecast
               for change in input_set.policy_changes):
            return True
        return any(
            transaction.kind == TransactionKind.WITHDRAWAL
            and transaction.effective_date is not None
            and transaction.effective_date > forecast
            for transaction in input_set.dated_transactions)

    def _refresh_level_solve_caveat(self):
        self.level_solve_caveat_banner.setVisible(
            self.level_solve_change_caveat_active())

    def load_data_from_policy(self, policy, *, has_shadow: bool = False,
                              shadow_ceased: bool = False):
        self._loaded_policy = policy
        self._valuation_date = policy_attr(policy, "valuation_date", None)
        self._rollback_overrides = None
        self._rollback_live_inputs = None
        self._inforce_shadow = (has_shadow, shadow_ceased)
        self._mode_inputs = {}
        self._active_issue_mode = False
        with muted_signals(self.run_from_issue_btn):
            self.run_from_issue_btn.setChecked(False)
        self._issue_load_error = ""
        try:
            self.issue_conditions.load_policy(policy)
        except ValueError as exc:
            self._issue_load_error = str(exc)
            self.issue_conditions.assumptions.setText(str(exc))
            logger.warning("Issue conditions unavailable: %s", exc)
        self.issue_conditions.set_issue_mode(False)
        self._issue_date = policy_attr(policy, "issue_date", None)
        self._maturity_date = self._maturity_date_from_policy(policy)
        if self._maturity_date is not None:
            self.illustration_to_date_edit.setDate(QDate(
                self._maturity_date.year,
                self._maturity_date.month,
                self._maturity_date.day,
            ))
        for label in self._warning_labels.values():
            base_text = label.property("base_text") or label.text()
            label.setText(self._warning_text(base_text))

        self._update_valuation_banner(policy)
        plancode = str(policy_attr(policy, "base_plancode", "") or getattr(policy, "plancode", "") or "")
        self._set_iul_crediting_applicable(is_iul_plan(plancode))
        self._update_ag49_regime_panel()
        self.dynamic_panel.load_from_policy(policy, has_shadow=has_shadow,
                                            shadow_ceased=shadow_ceased)
        self._basis_default_dynamic = self.dynamic_panel.capture_state()
        # Loading resets the Illustrated Rate field's read-only/validator state
        # (read-only mirror on IUL) — re-apply ABR mode so the field stays
        # editable and the rest of the panel stays locked.
        self._apply_abr_quote_mode(get_illustration_settings().abr_quote_mode)
        self._refresh_level_solve_caveat()
        self._default_input_state = self._capture_active_case_inputs()

    def run_from_issue_enabled(self) -> bool:
        return self.run_from_issue_btn.isChecked()

    def _style_run_from_issue_button(self, enabled: bool):
        if enabled:
            self.run_from_issue_btn.setStyleSheet(
                f"QPushButton {{ background: {ISSUE_BLUE_PRIMARY}; color: white;"
                f" border: 2px solid {ISSUE_BLUE_DARK}; border-radius: 5px;"
                " padding: 4px 12px; font-size: 11px; font-weight: bold; }"
                f"QPushButton:hover {{ background: {ISSUE_BLUE_DARK}; }}")
        else:
            self.run_from_issue_btn.setStyleSheet(LOAN_TOGGLE_STYLE)

    def _apply_run_from_issue(self, enabled: bool, *, restore_inputs: bool = True):
        if self._loaded_policy is not None:
            try:
                policy = self._policy_for_input_mode(enabled)
            except ValueError as exc:
                with muted_signals(self.run_from_issue_btn):
                    self.run_from_issue_btn.setChecked(self._active_issue_mode)
                self._show_mode_warnings([str(exc)])
                return
            if restore_inputs:
                self._mode_inputs[str(self._active_issue_mode)] = self._capture_active_case_inputs()
            self._active_issue_mode = enabled
            self._load_dynamic_context(policy, enabled)
            if restore_inputs:
                state = self._mode_inputs.get(str(enabled))
                if state is None:
                    state = deepcopy(self._default_input_state)
                    state["dynamic"] = self.dynamic_panel.capture_state()
                self._show_mode_warnings(self._apply_active_case_inputs(state))
        self._style_run_from_issue_button(enabled)
        self.run_from_issue_btn.setText(
            "NEW BUSINESS - FROM ISSUE" if enabled else
            "Inforce | New Business - From Issue")
        self.issue_conditions.set_issue_mode(enabled)
        bg = ISSUE_BLUE_BG if enabled else PURPLE_BG
        self.setStyleSheet(f"background-color: {bg};")
        self.input_tabs.setStyleSheet(
            ISSUE_TAB_WIDGET_STYLE if enabled else TAB_WIDGET_STYLE)
        self.dynamic_panel.setStyleSheet(f"background-color: {bg};")
        self.transaction_tab.setStyleSheet(f"background-color: {bg};")
        self.control_tab.setStyleSheet(f"background-color: {bg};")
        self.valuation_banner.setStyleSheet(
            (
                f"background-color: {ISSUE_BLUE_DARK};"
                f" border: 1px solid {ISSUE_BLUE_PRIMARY}; border-radius: 4px;"
            ) if enabled else
            "background-color: #2A1458; border: 1px solid #5E35A5; border-radius: 4px;"
        )
        if self._loaded_policy is not None:
            self._update_valuation_banner(policy)
        self.run_from_issue_changed.emit(enabled)

    def _policy_for_input_mode(self, enabled):
        if not enabled:
            if self._rollback_overrides is not None:
                return build_illustration_scenario(
                    self._loaded_policy, rollback_overrides=self._rollback_overrides,
                    allow_missing_shadow=True,
                ).projectable_policy
            return self._loaded_policy
        if self._rollback_overrides is not None:
            raise ValueError("Turn off Edit Record before selecting New Business - From Issue.")
        if self.abr_quote_enabled():
            raise ValueError("Turn off ABR Quote in Options before selecting New Business - From Issue.")
        if self._issue_load_error:
            raise ValueError(self._issue_load_error)
        return build_illustration_scenario(
            self._loaded_policy, run_from_issue=True,
            issue_overrides=self.issue_conditions.export_overrides(),
        ).projectable_policy

    def _load_dynamic_context(self, policy, enabled):
        has_shadow, shadow_ceased = (
            (policy.has_shadow_account, policy.ccv_ceased)
            if enabled or self._rollback_overrides is not None
            else self._inforce_shadow)
        self._valuation_date = policy_attr(policy, "valuation_date", None)
        self.dynamic_panel.load_from_policy(
            policy, has_shadow=has_shadow, shadow_ceased=shadow_ceased)
        self._basis_default_dynamic = self.dynamic_panel.capture_state()
        self._apply_abr_quote_mode(get_illustration_settings().abr_quote_mode)

    def set_value_rollback(self, overrides: RollbackOverrideSet | None):
        """Apply a validated basis, keeping explicit schedules and the live inputs.

        Pending toolbar date selections never call this method. Financial history
        is not copied to the user's transaction schedule.
        """
        if self._loaded_policy is None:
            raise ValueError("Load a policy before applying Edit Record.")
        if overrides is not None and not get_illustration_settings().rollback_enabled:
            raise ValueError("Enable Options > Edit Record before applying valuation edits.")
        if overrides is None and self._rollback_overrides is None:
            return self._policy_for_input_mode(self.run_from_issue_enabled())
        if overrides is not None and (
            self.run_from_issue_enabled() or self.abr_quote_enabled()
        ):
            raise ValueError(
                "Edit Record requires Inforce mode with ABR Quote turned off.")
        candidate = build_illustration_scenario(
            self._loaded_policy, rollback_overrides=overrides,
            allow_missing_shadow=True,
        ).projectable_policy
        state = self._capture_active_case_inputs()
        old_defaults = self._basis_default_dynamic
        if overrides is not None and self._rollback_overrides is None:
            self._rollback_live_inputs = deepcopy(state)
        elif overrides is None and self._rollback_live_inputs is not None:
            state = deepcopy(self._rollback_live_inputs)
            old_defaults = None
        self._rollback_overrides = deepcopy(overrides)
        self._load_dynamic_context(candidate, False)
        if old_defaults is not None:
            old_sections = old_defaults.get("sections") or {}
            new_sections = self._basis_default_dynamic.get("sections") or {}
            sections = state["dynamic"].get("sections") or {}
            for name, rows in old_sections.items():
                if sections.get(name) == rows:
                    sections[name] = deepcopy(new_sections.get(name, []))
        warnings = self._apply_active_case_inputs(state)
        self._update_valuation_banner(candidate)
        self._show_mode_warnings(warnings)
        if overrides is None:
            self._rollback_live_inputs = None
        self.rollback_changed.emit()
        return candidate

    def export_rollback_overrides(self) -> RollbackOverrideSet | None:
        return deepcopy(self._rollback_overrides)

    def _on_rollback_option_changed(self, enabled: bool):
        if not enabled and self._rollback_overrides is not None:
            self.set_value_rollback(None)

    def _show_mode_warnings(self, warnings):
        self.mode_warning.setText("\n".join(warnings))
        self.mode_warning.setVisible(bool(warnings))
        for warning in warnings:
            logger.warning("Illustration inputs: %s", warning)

    def _on_issue_conditions_changed(self):
        if not self.run_from_issue_enabled() or self._loaded_policy is None:
            return
        state = self.dynamic_panel.capture_state()
        try:
            policy = self._policy_for_input_mode(True)
        except ValueError as exc:
            self._show_mode_warnings([str(exc)])
        else:
            self._load_dynamic_context(policy, True)
            self._show_mode_warnings(self.dynamic_panel.apply_state(state))
            self._update_valuation_banner(policy)
        self.issue_conditions_changed.emit()

    def _update_valuation_banner(self, policy):
        valuation_date = policy_attr(policy, "valuation_date", None)
        if self.run_from_issue_enabled() and self._issue_date is not None:
            self.banner_valuation_label.setText("Not applicable")
            self.banner_first_forecast_label.setText(format_date(self._issue_date))
            self.banner_policy_year_label.setText("1")
        elif valuation_date is not None:
            self.banner_valuation_label.setText(format_date(valuation_date))
            self.banner_first_forecast_label.setText(
                format_date(valuation_date + relativedelta(months=1))
            )
        else:
            self.banner_valuation_label.setText("—")
            self.banner_first_forecast_label.setText("—")
        if self._issue_date is not None:
            self.banner_monthliversary_label.setText(_ordinal(self._issue_date.day))
        else:
            self.banner_monthliversary_label.setText("—")
        if not self.run_from_issue_enabled():
            policy_year = policy_attr(policy, "policy_year", None)
            self.banner_policy_year_label.setText(str(policy_year) if policy_year else "—")
        face = (policy_attr(policy, "base_total_face_amount", None)
                or policy_attr(policy, "base_face_amount", None)
                or getattr(policy, "face_amount", None))
        try:
            self.banner_face_label.setText(f"{float(face):,.0f}" if face else "—")
        except (TypeError, ValueError):
            self.banner_face_label.setText("—")
        rateclass = (policy_attr(policy, "base_rate_class", None)
                     or getattr(policy, "rate_class", None))
        self.banner_rateclass_label.setText(str(rateclass) if rateclass else "—")
        # DTH_BNF_PLN_OPT_CD "1"/"2"/"3" -> Option A/B/C
        db_code = str(policy_attr(policy, "db_option_code", "") or
                      getattr(policy, "db_option", "") or "").strip().upper()
        db_display = {"1": "A - Level", "A": "A - Level",
                      "2": "B - Increasing", "B": "B - Increasing",
                      "3": "C - ROP", "C": "C - ROP"}.get(db_code)
        self.banner_db_option_label.setText(db_display or (db_code or "—"))
        # Total policy debt = all six loan buckets (regular / preferred /
        # variable, principal + accrued interest) — the same total_loan_balance
        # the engine seeds its opening loan state from. Live PolicyInformation
        # (Decimal) and a frozen IllustrationPolicyData snapshot (float) both
        # expose it, so live and snapshot modes read the same way.
        try:
            debt = float(policy_attr(policy, "total_loan_balance", 0) or 0)
        except (TypeError, ValueError):
            debt = 0.0
        self.banner_policy_debt_label.setText(f"{debt:,.0f}")

    def export_input_set(self) -> IllustrationInputSet:
        input_set = IllustrationInputSet()

        for row in self._iter_nonempty_rows(self.scheduled_premium_table, [0, 1]):
            year = self._parse_year(self.scheduled_premium_table.item(row, 0))
            amount = self._parse_amount(self.scheduled_premium_table.item(row, 1))
            mode = self._cell_text(self.scheduled_premium_table.item(row, 2))
            if year is not None and amount is not None:
                input_set.scheduled_transactions.append(
                    ScheduledTransaction(
                        kind=TransactionKind.PREMIUM,
                        policy_year=year,
                        amount=amount,
                        mode=mode,
                    )
                )

        loan_type = "variable" if self.variable_loan_toggle.isChecked() else "fixed"
        for row in self._iter_nonempty_rows(self.scheduled_loan_table, [0, 1]):
            year = self._parse_year(self.scheduled_loan_table.item(row, 0))
            amount = self._parse_amount(self.scheduled_loan_table.item(row, 1))
            mode = self._cell_text(self.scheduled_loan_table.item(row, 2))
            if year is not None and amount is not None:
                input_set.scheduled_transactions.append(
                    ScheduledTransaction(
                        kind=TransactionKind.LOAN,
                        policy_year=year,
                        amount=amount,
                        mode=mode,
                        metadata={"loan_type": loan_type},
                    )
                )

        input_set.dated_transactions.extend(
            self._collect_dated_transactions(
                self.unscheduled_premium_table,
                TransactionKind.PREMIUM,
                subtype_column=2,
            )
        )
        input_set.dated_transactions.extend(
            self._collect_dated_transactions(self.specific_loan_table, TransactionKind.LOAN)
        )
        input_set.dated_transactions.extend(
            self._collect_dated_transactions(self.loan_repayment_table, TransactionKind.LOAN_REPAYMENT)
        )
        input_set.dated_transactions.extend(
            self._collect_dated_transactions(self.withdrawal_table, TransactionKind.WITHDRAWAL, subtype_column=2)
        )

        for row in self._iter_nonempty_rows(self.face_amount_table, [0, 1]):
            effective_date = self._parse_date(self.face_amount_table.item(row, 0))
            face_amount = self._parse_amount(self.face_amount_table.item(row, 1))
            if effective_date is not None and face_amount is not None:
                input_set.policy_changes.append(
                    PolicyChangeEvent(
                        kind=PolicyChangeKind.FACE_AMOUNT,
                        effective_date=effective_date,
                        value=face_amount,
                    )
                )

        for row in self._iter_nonempty_rows(self.db_option_table, [0, 1]):
            effective_date = self._parse_date(self.db_option_table.item(row, 0))
            db_option = self._cell_text(self.db_option_table.item(row, 1))
            if effective_date is not None and db_option:
                input_set.policy_changes.append(
                    PolicyChangeEvent(
                        kind=PolicyChangeKind.DB_OPTION,
                        effective_date=effective_date,
                        value=db_option,
                    )
                )

        # Dynamic Input tab rows (year/age driven). Appended after the grids,
        # so on a same-year schedule tie the dynamic row wins — the compiler
        # takes the LAST schedule at or before a year.
        self.dynamic_panel.collect_into(input_set)

        return input_set

    def export_options(self) -> IllustrationOptions:
        md_windows = self.dynamic_panel.monthly_deduction_windows()
        b2md_windows = self.dynamic_panel.billable_to_md_windows()
        return IllustrationOptions(
            conform_to_tefra=self.tefra_check.isChecked(),
            conform_to_tamra=self.dynamic_panel.tamra_check.isChecked(),
            # A "Billable to MD" row always allows GP exceptions — the whole
            # point of the mode is the billable → MD → exception sequence.
            # (An active shadow account still blocks them inside the engine.)
            allow_exception_prems=(
                self.exception_prem_check.isChecked() or bool(b2md_windows)),
            switch_to_option_a_in_exception=self.switch_to_option_a_check.isChecked(),
            exact_days_interest=self.exact_days_check.isChecked(),
            # cap_premiums_at_acceptance left at None — derives from
            # conform_to_tefra. Only PolView's GLP solver overrides it.
            levelizing_premium=self.levelizing_check.isChecked(),
            guideline_by_search=self.gp_search_check.isChecked(),
            apply_prem_to_loan=self.dynamic_panel.apply_prem_to_loan_check.isChecked(),
            apply_excess_repayment_as_premium=(
                self.dynamic_panel.excess_repayment_as_premium()),
            loan_repay_principal_first=self.loan_principal_first_check.isChecked(),
            pay_monthly_deduction=bool(md_windows),
            monthly_deduction_windows=(md_windows or None),
            billable_to_md_windows=(b2md_windows or None),
            iul_wair_crediting=self.wair_radio.isChecked(),
            use_policy_ag49_regime=self.policy_ag49_check.isChecked(),
        )

    def min_level_request(self) -> Optional[dict]:
        return self.dynamic_panel.min_level_request()

    def shadow_level_request(self) -> Optional[dict]:
        return self.dynamic_panel.shadow_level_request()

    def set_shadow_level_amount(self, value: Optional[float]):
        self.dynamic_panel.set_shadow_level_amount(value)

    def max_level_request(self) -> Optional[dict]:
        return self.dynamic_panel.max_level_request()

    def set_max_level_amount(self, value: Optional[float]):
        self.dynamic_panel.set_max_level_amount(value)

    def solve_request(self) -> Optional[dict]:
        return self.dynamic_panel.solve_request()

    def set_solve_amount(self, value: Optional[float]):
        self.dynamic_panel.set_solve_amount(value)

    def solve_duration_request(self) -> Optional[dict]:
        return self.dynamic_panel.solve_duration_request()

    def set_solve_duration(self, duration_years: int):
        self.dynamic_panel.set_solve_duration(duration_years)

    def lumpsum_to_next_enabled(self) -> bool:
        return self.dynamic_panel.lumpsum_to_next_enabled()

    def set_lumpsum_amount(self, value: Optional[float]):
        self.dynamic_panel.set_lumpsum_amount(value)

    def level_premium_active(self) -> bool:
        return self.dynamic_panel.active_level_premium_type() is not None

    def set_min_level_amount(self, value: Optional[float]):
        self.dynamic_panel.set_min_level_amount(value)

    def loan_payoff_requests(self) -> list:
        return self.dynamic_panel.loan_payoff_requests()

    def set_loan_payoff_amounts(self, values: list):
        self.dynamic_panel.set_loan_payoff_amounts(values)

    def stop_on_lapse_enabled(self) -> bool:
        return self.stop_on_lapse_check.isChecked()

    def _apply_illustration_options_enabled(self, enabled: bool):
        """Lock/unlock the illustration-option controls.

        When "Enable Illustration Options" is on, Conform to TEFRA/DEFRA, Stop
        Projection on Lapse, Switch to Option A in exception period, and the
        Illustration Duration controls become user-editable. When it is turned
        back off, the two locked-on controls revert to their locked-on default
        (checked + disabled), Switch to Option A reverts to off, and the
        duration controls are disabled so a normal illustration can't silently
        run without them.
        """
        for check in (self.tefra_check, self.stop_on_lapse_check):
            check.setEnabled(enabled)
            if not enabled:
                check.setChecked(True)
        self.switch_to_option_a_check.setEnabled(enabled)
        if not enabled:
            self.switch_to_option_a_check.setChecked(False)
        self._sync_duration_controls()

    def abr_quote_enabled(self) -> bool:
        return get_illustration_settings().abr_quote_mode

    def _apply_abr_quote_mode(self, enabled: bool):
        """ABR Quote (Options menu) locks every Input-tab control except the
        Illustrated Rate and Minimum Face Amount Allowed. The run itself forces
        TEFRA/DEFRA + TAMRA off, so nothing here needs to touch those."""
        self.dynamic_panel.set_abr_quote_mode(enabled)
        self.abr_minimum_face_row.setVisible(enabled)
        self.run_from_issue_btn.setEnabled(not enabled)
        if enabled and self.run_from_issue_enabled():
            self.run_from_issue_btn.setChecked(False)
            self._show_mode_warnings([
                "ABR Quote uses Inforce mode. Your from-issue inputs are preserved; "
                "turn off ABR Quote to return to New Business - From Issue."])
        if enabled and self._rollback_overrides is not None:
            self.set_value_rollback(None)
            self._show_mode_warnings([
                "ABR Quote uses the loaded Inforce basis. Edit Record was turned off."])

    def abr_minimum_face_amount(self) -> Optional[float]:
        text = self.abr_minimum_face_edit.text().replace(",", "").replace("$", "").strip()
        if not text:
            return None
        return float(text)

    def projection_months(self, policy) -> int | None:
        if self.illustration_to_date_radio.isChecked():
            return self._months_to_date(policy, self.illustration_to_date_edit.date().toPyDate())

        value = self.illustration_years_combo.currentText().strip()
        normalized = value.lower().replace(" ", "")
        if normalized in {"tomaturity", "maturity"}:
            return self._months_to_maturity(policy)
        if normalized in {"age65", "65"}:
            return self._months_to_age(policy, 65)

        try:
            years = int(value)
        except ValueError as exc:
            raise ValueError("Illustration Years must be a number, Age 65, or To Maturity.") from exc
        return max(0, years * 12)

    def projection_duration_label(self, policy) -> str:
        if self.illustration_to_date_radio.isChecked():
            return f"to {format_date(self.illustration_to_date_edit.date().toPyDate())}"

        value = self.illustration_years_combo.currentText().strip()
        normalized = value.lower().replace(" ", "")
        if normalized in {"tomaturity", "maturity"}:
            return "to maturity"
        if normalized in {"age65", "65"}:
            return "to age 65"
        return f"for {int(value)} years"

    def export_inforce_overrides(self) -> InforceOverrideSet:
        return InforceOverrideSet(
            current_interest_rate=self.dynamic_panel.illustrated_rate(),
            sweep_account_min=self.dynamic_panel.sweep_account_min(),
            iul_declared_rate=self.dynamic_panel.iul_declared_rate(),
            iul_asset_charge_rate=self.dynamic_panel.iul_asset_charge_rate(),
            premium_allocations=self.dynamic_panel.iul_allocations(),
            index_illustration_rates=self.dynamic_panel.iul_illustration_rates(),
            deemed_cash_value=self.dynamic_panel.deemed_cash_value(),
        )

    def export_issue_overrides(self):
        return self.issue_conditions.export_overrides() if self.run_from_issue_enabled() else None

    # ── saved-case capture/apply ──────────────────────────────
    #
    # The saved-case payload is the WIDGET state — the same surface a Run
    # Values consumes through export_input_set/export_options/
    # export_inforce_overrides — so a saved case can never drift from what a
    # run actually uses. Serialized as a plain JSON-safe dict for
    # models/case_store.py.

    _CASE_GRIDS = (
        ("scheduled_premiums", "scheduled_premium_table"),
        ("scheduled_loans", "scheduled_loan_table"),
        ("unscheduled_premiums", "unscheduled_premium_table"),
        ("unscheduled_loans", "specific_loan_table"),
        ("loan_repayments", "loan_repayment_table"),
        ("withdrawals", "withdrawal_table"),
        ("face_amounts", "face_amount_table"),
        ("db_options", "db_option_table"),
    )

    def capture_case_inputs(self) -> dict:
        """Snapshot the full user input state of this tab (JSON-safe)."""
        state = self._capture_active_case_inputs()
        state["issue_conditions"] = (
            self.issue_conditions.capture_state()
            if self.issue_conditions.has_policy() and not self._issue_load_error
            else None)
        state["mode_inputs"] = deepcopy(self._mode_inputs)
        rollback = self._rollback_overrides
        state["value_rollback"] = (
            {
                "valuation_date": rollback.valuation_date.isoformat(),
                "coverage_amounts": {
                    str(phase): amount for phase, amount in rollback.coverage_amounts.items()
                },
                "benefit_amounts": [
                    [*key, amount] for key, amount in rollback.benefit_amounts.items()
                ],
                "db_option": rollback.db_option,
                "shadow_account_value": rollback.shadow_account_value,
                "account_value": rollback.account_value,
                "record_values": {
                    name: value.isoformat() if isinstance(value, date) else deepcopy(value)
                    for name, value in rollback.record_values.items()
                },
                "tamra_7year_contributions": deepcopy(rollback.tamra_7year_contributions),
                "fund_values": deepcopy(rollback.fund_values),
                "impaired_fund_values": deepcopy(rollback.impaired_fund_values),
                "premium_allocations": deepcopy(rollback.premium_allocations),
            } if rollback is not None else None
        )
        state["rollback_live_inputs"] = deepcopy(self._rollback_live_inputs)
        return state

    def read_draft(self) -> InputDraft:
        """Read a plain, restorable draft from the current widget state."""

        return InputDraft(
            case_inputs=self.capture_case_inputs(),
            input_set=self.export_input_set(),
            controls=ControlDraft(
                options=self.export_options(),
                stop_on_lapse=self.stop_on_lapse_enabled(),
                run_from_issue=self.run_from_issue_enabled(),
                abr_quote=self.abr_quote_enabled(),
                abr_minimum_face_amount=self.abr_minimum_face_amount(),
            ),
            inforce_overrides=self.export_inforce_overrides(),
            issue_overrides=self.export_issue_overrides(),
            rollback_overrides=self.export_rollback_overrides(),
            max_level=self.max_level_request(),
            min_level=self.min_level_request(),
            shadow_level=self.shadow_level_request(),
            target_premium=self.solve_request(),
            duration=self.solve_duration_request(),
            lumpsum_to_next=self.lumpsum_to_next_enabled(),
            loan_payoffs=tuple(self.loan_payoff_requests()),
        )

    def render_draft(self, draft: InputDraft) -> list[str]:
        """Render a previously read draft back into this inputs widget."""

        return self.apply_case_inputs(deepcopy(draft.case_inputs))

    def _capture_active_case_inputs(self) -> dict:
        return {
            "grids": {
                name: self._capture_grid(getattr(self, attr))
                for name, attr in self._CASE_GRIDS
            },
            "scheduled_loan_type": (
                "variable" if self.variable_loan_toggle.isChecked() else "fixed"),
            # Conform to TEFRA/DEFRA and Stop Projection on Lapse are normally
            # locked on, and premium capping at acceptance rides with TEFRA. They
            # only become user state when "Enable Illustration Options" is on, so
            # capture that toggle and their values for round-tripping.
            "controls": {
                "exact_days": self.exact_days_check.isChecked(),
                "exception_prem": self.exception_prem_check.isChecked(),
                "levelizing": self.levelizing_check.isChecked(),
                "gp_search": self.gp_search_check.isChecked(),
                "loan_principal_first": self.loan_principal_first_check.isChecked(),
                "enable_illustration_options": (
                    self.enable_illustration_options_check.isChecked()),
                "conform_to_tefra": self.tefra_check.isChecked(),
                "stop_on_lapse": self.stop_on_lapse_check.isChecked(),
                "switch_to_option_a": self.switch_to_option_a_check.isChecked(),
                "duration_mode": (
                    "date" if self.illustration_to_date_radio.isChecked()
                    else "years"),
                "duration_date": self.illustration_to_date_edit.date().toString(
                    "yyyy-MM-dd"),
                "duration_years": self.illustration_years_combo.currentText(),
                "iul_rate_method": (
                    "wair" if self.wair_radio.isChecked() else "blended"),
                "use_policy_ag49": self.policy_ag49_check.isChecked(),
                "abr_minimum_face_amount": self.abr_minimum_face_edit.text(),
                "run_from_issue": self._active_issue_mode,
            },
            "dynamic": self.dynamic_panel.capture_state(),
            "ui": {
                "grid_inputs_tab_visible": self.grid_inputs_tab_visible(),
            },
        }

    def apply_case_inputs(self, state: dict) -> list[str]:
        """Apply a saved case onto this tab (already loaded for a policy).

        Returns warnings for every input that did not apply on this policy —
        the caller must surface them; nothing is silently dropped."""
        rollback_state = state.get("value_rollback")
        if rollback_state is not None and not get_illustration_settings().rollback_enabled:
            raise ValueError("Enable Options > Edit Record to load this case's valuation assumptions.")
        enabled = bool((state.get("controls") or {}).get("run_from_issue", False))
        if rollback_state and enabled:
            raise ValueError("A saved case cannot combine Edit Record and New Business - From Issue.")
        rollback = None
        if rollback_state is not None:
            if not isinstance(rollback_state, dict):
                raise ValueError("Saved Edit Record settings must be an object.")
            coverage_amounts = rollback_state.get("coverage_amounts", {})
            benefit_amounts = rollback_state.get("benefit_amounts", [])
            if not isinstance(coverage_amounts, dict) or not isinstance(benefit_amounts, list):
                raise ValueError("Saved Edit Record amount settings are malformed.")
            try:
                rollback = RollbackOverrideSet(
                    valuation_date=date.fromisoformat(rollback_state["valuation_date"]),
                    coverage_amounts={
                        int(phase): amount for phase, amount in coverage_amounts.items()
                    },
                    benefit_amounts={
                        (int(phase), kind, subtype): amount
                        for phase, kind, subtype, amount in benefit_amounts
                    },
                    db_option=rollback_state.get("db_option"),
                    shadow_account_value=rollback_state.get("shadow_account_value"),
                    account_value=rollback_state.get("account_value"),
                    record_values=validate_record_values(
                        rollback_state.get("record_values", {}), from_json=True),
                    tamra_7year_contributions=deepcopy(rollback_state.get("tamra_7year_contributions")),
                    fund_values=deepcopy(rollback_state.get("fund_values")),
                    impaired_fund_values=deepcopy(rollback_state.get("impaired_fund_values")),
                    premium_allocations=deepcopy(rollback_state.get("premium_allocations")),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Saved Edit Record settings are malformed: {exc}") from exc
            if (len(rollback.coverage_amounts) != len(coverage_amounts)
                    or len(rollback.benefit_amounts) != len(benefit_amounts)):
                raise ValueError("Saved Edit Record settings contain duplicate coverage/benefit keys.")
            # Reject invalid imported assumptions before replacing an applied basis.
            if self._loaded_policy is None:
                raise ValueError("Load a policy before applying Edit Record assumptions.")
            build_illustration_scenario(
                self._loaded_policy, rollback_overrides=rollback,
                allow_missing_shadow=True)
        if self._rollback_overrides is not None:
            self.set_value_rollback(None)
        warnings = self.issue_conditions.apply_state(state.get("issue_conditions"))
        self._mode_inputs = deepcopy(state.get("mode_inputs") or {})
        with muted_signals(self.run_from_issue_btn):
            self.run_from_issue_btn.setChecked(enabled)
        self._apply_run_from_issue(enabled, restore_inputs=False)
        if enabled != self.run_from_issue_enabled():
            raise ValueError(self.mode_warning.text())
        if rollback is not None:
            self.set_value_rollback(rollback)
            if state.get("rollback_live_inputs") is not None:
                self._rollback_live_inputs = deepcopy(state["rollback_live_inputs"])
            warnings.extend(self.mode_warning.text().splitlines())
        warnings.extend(self._apply_active_case_inputs(state))
        return warnings

    def _apply_active_case_inputs(self, state: dict) -> list[str]:
        warnings: list[str] = []
        grids = state.get("grids") or {}
        for name, attr in self._CASE_GRIDS:
            self._apply_grid(getattr(self, attr), grids.get(name) or [])
        if state.get("scheduled_loan_type") == "variable":
            self.variable_loan_toggle.setChecked(True)
        else:
            self.fixed_loan_toggle.setChecked(True)

        warnings.extend(self.dynamic_panel.apply_state(state.get("dynamic") or {}))

        controls = state.get("controls") or {}
        self.exact_days_check.setChecked(bool(controls.get("exact_days")))
        self.levelizing_check.setChecked(bool(controls.get("levelizing", True)))
        self.gp_search_check.setChecked(bool(controls.get("gp_search")))
        self.loan_principal_first_check.setChecked(
            bool(controls.get("loan_principal_first")))
        self.abr_minimum_face_edit.setText(
            str(controls.get("abr_minimum_face_amount") or "")
        )
        # Restore the illustration-options override. Enable first (which unlocks
        # the two controls), then apply their saved values; if the override is
        # off they stay locked on. Older cases without these keys default to the
        # normal locked-on behavior.
        enable_options = bool(controls.get("enable_illustration_options", False))
        self.enable_illustration_options_check.setChecked(enable_options)
        if enable_options:
            self.tefra_check.setChecked(bool(controls.get("conform_to_tefra", True)))
            self.stop_on_lapse_check.setChecked(
                bool(controls.get("stop_on_lapse", True)))
            self.switch_to_option_a_check.setChecked(
                bool(controls.get("switch_to_option_a", False)))
        # Premium capping at acceptance rides with TEFRA, so it is not captured
        # or restored separately.
        # The exception checkbox may be force-blocked on this policy (active
        # shadow account) — a saved "allow" must not sneak past the block.
        wants_exception = bool(controls.get("exception_prem", False))
        if self.exception_prem_check.isEnabled():
            self.exception_prem_check.setChecked(wants_exception)
        elif wants_exception and not self.exception_prem_check.isChecked():
            warnings.append(
                "Allow GP Exception Premium did not apply — it is blocked on "
                "this policy (active shadow account).")
        if controls.get("duration_mode") == "date":
            self.illustration_to_date_radio.setChecked(True)
            saved_date = QDate.fromString(
                str(controls.get("duration_date") or ""), "yyyy-MM-dd")
            if saved_date.isValid():
                self.illustration_to_date_edit.setDate(saved_date)
        else:
            self.illustration_years_radio.setChecked(True)
            years = str(controls.get("duration_years") or "")
            if years:
                self.illustration_years_combo.setCurrentText(years)
        self.wair_radio.setChecked(controls.get("iul_rate_method") == "wair")
        self.blended_rate_radio.setChecked(
            controls.get("iul_rate_method") != "wair")
        self.policy_ag49_check.setChecked(bool(controls.get("use_policy_ag49")))
        self._refresh_level_solve_caveat()
        # Backward-tolerant: cases saved before this field existed had the
        # tab hidden (the only state that could exist then) — default False.
        ui = state.get("ui") or {}
        self._set_grid_inputs_tab_visible(bool(ui.get("grid_inputs_tab_visible", False)))
        return warnings

    @staticmethod
    def _capture_grid(table: QTableWidget) -> list:
        """Non-empty grid rows as ``[row_index, [cell texts…]]`` pairs."""
        out = []
        for row in range(table.rowCount()):
            texts = [
                (table.item(row, col).text() if table.item(row, col) else "")
                for col in range(table.columnCount())
            ]
            if any(text.strip() for text in texts):
                out.append([row, texts])
        return out

    @staticmethod
    def _apply_grid(table: QTableWidget, entries: list):
        """Clear the grid, then restore saved rows at their saved positions."""
        for row in range(table.rowCount()):
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item is not None and item.text():
                    item.setText("")
        for entry in entries:
            row, texts = int(entry[0]), list(entry[1])
            if row >= table.rowCount():
                grown_from = table.rowCount()
                table.setRowCount(row + 1)
                table.init_rows(grown_from, row + 1)
            for col, text in enumerate(texts[: table.columnCount()]):
                item = table.item(row, col)
                if item is not None:
                    item.setText(str(text))

    @staticmethod
    def _maturity_date_from_policy(policy) -> date | None:
        maturity_date = getattr(policy, "maturity_date", None)
        if maturity_date is not None:
            return maturity_date

        segments = getattr(policy, "segments", None)
        if segments:
            for segment in segments:
                maturity_date = getattr(segment, "maturity_date", None)
                if maturity_date is not None:
                    return maturity_date

        get_base_coverages = policy_attr(policy, "get_base_coverages", None)
        if callable(get_base_coverages):
            try:
                for coverage in get_base_coverages():
                    maturity_date = getattr(coverage, "maturity_date", None)
                    if maturity_date is not None:
                        return maturity_date
            except Exception:
                pass

        issue_date = policy_attr(policy, "issue_date", None)
        issue_age = policy_attr(policy, "base_issue_age", None) or getattr(policy, "issue_age", None)
        maturity_age = getattr(policy, "maturity_age", None) or policy_attr(policy, "age_at_maturity", None)
        if issue_date is not None and issue_age is not None and maturity_age is not None:
            try:
                years_to_maturity = int(maturity_age) - int(issue_age)
            except (TypeError, ValueError):
                return None
            if years_to_maturity >= 0:
                return issue_date + relativedelta(years=years_to_maturity)
        return None

    @staticmethod
    def _months_to_date(policy, target_date: date) -> int:
        if getattr(policy, "run_from_issue", False):
            issue = policy.issue_date
            if issue is None:
                raise ValueError("Illustration from issue requires a policy issue date.")
            if target_date < issue:
                return 0
            months = (target_date.year - issue.year) * 12 + target_date.month - issue.month
            if target_date < issue + relativedelta(months=months):
                months -= 1
            return months + 1
        start_date = policy_attr(policy, "valuation_date", None) or policy_attr(policy, "issue_date", None)
        if start_date is None:
            raise ValueError("Illustration to Date requires a policy valuation date or issue date.")
        if target_date <= start_date:
            return 0
        months = (target_date.year - start_date.year) * 12 + (target_date.month - start_date.month)
        if target_date.day < start_date.day:
            months -= 1
        return max(0, months)

    @staticmethod
    def _months_to_age(policy, target_age: int) -> int:
        attained_age = policy_attr(policy, "attained_age", None)
        policy_month = policy_attr(policy, "policy_month", 1) or 1
        if attained_age is None:
            raise ValueError("Age-based illustration duration requires attained age.")
        return max(0, (target_age - int(attained_age)) * 12 - int(policy_month) + 1)

    @classmethod
    def _months_to_maturity(cls, policy) -> int:
        maturity_age = getattr(policy, "maturity_age", None)
        if maturity_age is None:
            raise ValueError("To Maturity requires a policy maturity age.")
        return cls._months_to_age(policy, int(maturity_age))

    def _collect_dated_transactions(
        self,
        table: QTableWidget,
        kind: TransactionKind,
        subtype_column: int | None = None,
    ) -> list[DatedTransaction]:
        transactions: list[DatedTransaction] = []
        for row in self._iter_nonempty_rows(table, [0, 1]):
            effective_date = self._parse_date(table.item(row, 0))
            amount = self._parse_amount(table.item(row, 1))
            subtype = self._cell_text(table.item(row, subtype_column)) if subtype_column is not None else ""
            if effective_date is not None and amount is not None:
                transactions.append(
                    DatedTransaction(
                        kind=kind,
                        effective_date=effective_date,
                        amount=amount,
                        subtype=subtype,
                    )
                )
        return transactions

    @staticmethod
    def _iter_nonempty_rows(table: QTableWidget, key_columns: list[int]):
        for row in range(table.rowCount()):
            if any((table.item(row, col).text() or "").strip() for col in key_columns if table.item(row, col) is not None):
                yield row

    @staticmethod
    def _cell_text(item: QTableWidgetItem | None) -> str:
        return (item.text() if item is not None else "").strip()

    def _parse_date(self, item: QTableWidgetItem | None) -> date | None:
        text = self._cell_text(item)
        if not text:
            return None
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _parse_year(self, item: QTableWidgetItem | None) -> int | None:
        text = self._cell_text(item)
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None

    def _parse_amount(self, item: QTableWidgetItem | None) -> float | None:
        text = self._cell_text(item)
        if not text:
            return None
        cleaned = text.replace(",", "").replace("$", "")
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = f"-{cleaned[1:-1]}"
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _warning_text(self, base_text: str):
        if self._issue_date:
            return f"{base_text} Issue date: {format_date(self._issue_date)}"
        return base_text

    @staticmethod
    def _is_monthliversary(text: str) -> bool:
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                value = datetime.strptime(text, fmt)
                return 1 <= value.day <= 28
            except ValueError:
                continue
        return False
