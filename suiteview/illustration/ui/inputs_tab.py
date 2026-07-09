"""Illustration Inputs tab UI."""

from datetime import date, datetime
from typing import Optional

from dateutil.relativedelta import relativedelta
from PyQt6.QtCore import QDate, QEvent, QTimer, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractItemDelegate,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
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
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.audit.tabs._styles import _CHECKMARK_PATH, _ensure_checkmark
from suiteview.polview.ui.formatting import format_date

from .inputs_dynamic import DynamicInputsPanel
from .styles import GROUP_STYLE, INPUT_TABLE_STYLE, PURPLE_BG, PURPLE_DARK


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

    MAX_PASTE_ROWS = 2000

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
        if menu.exec(event.globalPos()) is paste_action:
            row = index.row() if index.isValid() else max(self.currentRow(), 0)
            col = index.column() if index.isValid() else max(self.currentColumn(), 0)
            self.paste_from_clipboard(row, col)

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

    WARNING_BG = QColor("#FFF0B3")
    NORMAL_BG = QColor("#FFFFFF")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._warning_labels: dict[str, QLabel] = {}
        self._pending_warning_refresh: set[str] = set()
        self._issue_date: date | None = None
        self._maturity_date: date | None = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 12)
        outer.setSpacing(6)

        outer.addWidget(self._build_valuation_banner())

        self.input_tabs = QTabWidget(self)
        self.input_tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #B79CDE; background: #F8F3FE; }"
            "QTabBar::tab { background: #E8DDF8; color: #2A1458; padding: 4px 12px;"
            " border: 1px solid #B79CDE; border-bottom: none; font-size: 11px; font-weight: bold; }"
            "QTabBar::tab:selected { background: white; color: #4B2383; }"
        )
        self.dynamic_panel = DynamicInputsPanel(self)
        self.input_tabs.addTab(self.dynamic_panel, "Input")
        self.input_tabs.addTab(self._build_transaction_tab(), "Grid Inputs")
        self.input_tabs.addTab(self._build_control_tab(), "Illustration Control")
        outer.addWidget(self.input_tabs, 1)

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
        row.addStretch(1)
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

    def _build_control_tab(self):
        tab = QWidget(self)
        tab.setStyleSheet(f"background-color: {PURPLE_BG};")
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        outer.addWidget(self._build_illustration_duration_group(), 0, Qt.AlignmentFlag.AlignTop)

        group = QGroupBox("Run Controls")
        group.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 18, 10, 10)
        layout.setSpacing(6)

        self.exact_days_check = self._make_control_checkbox("Exact Days Interest")
        self.exact_days_check.setToolTip("Checked uses exact-days interest; unchecked uses monthly compounding.")
        layout.addWidget(self.exact_days_check)

        self.tefra_check = self._make_control_checkbox("Conform to TEFRA/DEFRA")
        self.tefra_check.setChecked(True)
        self.tefra_check.setToolTip("Enforce 7702 guideline premium room for force-outs and accepted premiums.")
        layout.addWidget(self.tefra_check)

        self.tamra_check = self._make_control_checkbox("Conform to TAMRA")
        self.tamra_check.setChecked(True)
        self.tamra_check.setToolTip("Enforce the 7-pay premium room while the policy is inside the TAMRA window.")
        layout.addWidget(self.tamra_check)

        # Allow GP Exception Premium moved to the Input sheet (dynamic_panel);
        # read it from there in export_options().

        self.cap_acceptance_check = self._make_control_checkbox("Cap Premiums at Acceptance")
        self.cap_acceptance_check.setChecked(True)
        self.cap_acceptance_check.setToolTip("Apply TEFRA/TAMRA room to scheduled and unscheduled premiums when they are accepted.")
        layout.addWidget(self.cap_acceptance_check)

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

        self.stop_on_lapse_check = self._make_control_checkbox("Stop Projection on Lapse")
        self.stop_on_lapse_check.setChecked(True)
        self.stop_on_lapse_check.setToolTip("Stop projection rows once the lapse test fails.")
        layout.addWidget(self.stop_on_lapse_check)

        note = QLabel("Unchecked Exact Days uses monthly compounding.")
        note.setStyleSheet(f"color: {PURPLE_DARK}; background: transparent; font-size: 10px; font-style: italic;")
        layout.addWidget(note)

        outer.addWidget(group, 0, Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self._build_iul_crediting_group(), 0, Qt.AlignmentFlag.AlignTop)
        outer.addStretch(1)
        return tab

    def _build_iul_crediting_group(self):
        """IUL-only controls — ignored on declared-rate plans."""
        group = QGroupBox("IUL Crediting")
        group.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 18, 10, 10)
        layout.setSpacing(6)

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
        layout.addWidget(self.policy_ag49_check)
        return group

    def _build_illustration_duration_group(self):
        group = QGroupBox("Illustration Duration")
        group.setStyleSheet(GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 18, 10, 10)
        layout.setSpacing(6)

        self.duration_mode_group = QButtonGroup(self)
        self.duration_mode_group.setExclusive(True)

        date_row = QHBoxLayout()
        date_row.setContentsMargins(0, 0, 0, 0)
        date_row.setSpacing(8)
        self.illustration_to_date_radio = self._make_control_radio("Illustration to Date")
        self.illustration_to_date_edit = QDateEdit(self)
        self.illustration_to_date_edit.setCalendarPopup(True)
        self.illustration_to_date_edit.setDisplayFormat("MM/dd/yyyy")
        self.illustration_to_date_edit.setDate(QDate.currentDate())
        self.illustration_to_date_edit.setStyleSheet(self._control_input_style())
        self.illustration_to_date_edit.setMinimumWidth(120)
        self.duration_mode_group.addButton(self.illustration_to_date_radio)
        date_row.addWidget(self.illustration_to_date_radio)
        date_row.addWidget(self.illustration_to_date_edit)
        date_row.addStretch(1)
        layout.addLayout(date_row)

        years_row = QHBoxLayout()
        years_row.setContentsMargins(0, 0, 0, 0)
        years_row.setSpacing(8)
        self.illustration_years_radio = self._make_control_radio("Illustration Years")
        self.illustration_years_combo = QComboBox(self)
        self.illustration_years_combo.setEditable(True)
        self.illustration_years_combo.addItems(["1", "2", "10", "20", "Age 65", "To Maturity"])
        self.illustration_years_combo.setCurrentText("To Maturity")
        self.illustration_years_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.illustration_years_combo.setStyleSheet(self._control_input_style())
        self.illustration_years_combo.setMinimumWidth(120)
        self.duration_mode_group.addButton(self.illustration_years_radio)
        years_row.addWidget(self.illustration_years_radio)
        years_row.addWidget(self.illustration_years_combo)
        years_row.addStretch(1)
        layout.addLayout(years_row)

        self.illustration_years_radio.setChecked(True)
        self.illustration_to_date_radio.toggled.connect(self._sync_duration_controls)
        self.illustration_years_radio.toggled.connect(self._sync_duration_controls)
        self._sync_duration_controls()
        return group

    def _make_control_checkbox(self, text: str):
        _ensure_checkmark()
        icon_path = _CHECKMARK_PATH.replace("\\", "/")
        checkbox = QCheckBox(text, self)
        checkbox.setStyleSheet(
            f"QCheckBox {{ color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold; spacing: 6px; }}"
            "QCheckBox::indicator { border: 1px solid #5E35A5; width: 12px; height: 12px; background-color: white; }"
            "QCheckBox::indicator:hover { border: 1px solid #4B2383; background-color: #FBF9FE; }"
            "QCheckBox::indicator:checked {"
            "  background-color: #5E35A5; border: 1px solid #4B2383;"
            f"  image: url({icon_path});"
            "}"
        )
        return checkbox

    def _make_control_radio(self, text: str):
        radio = QRadioButton(text, self)
        radio.setStyleSheet(
            f"QRadioButton {{ color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold; spacing: 6px; }}"
            "QRadioButton::indicator { border: 1px solid #5E35A5; border-radius: 6px; width: 12px; height: 12px; background-color: white; }"
            "QRadioButton::indicator:hover { border: 1px solid #4B2383; background-color: #FBF9FE; }"
            "QRadioButton::indicator:checked { background-color: #5E35A5; border: 1px solid #4B2383; }"
        )
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
        use_date = self.illustration_to_date_radio.isChecked()
        self.illustration_to_date_edit.setEnabled(use_date)
        self.illustration_years_combo.setEnabled(not use_date)

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

        table = self._make_table(100, ["Date", "Amount"], min_height=520, stretch_columns=True)
        table.itemChanged.connect(lambda item: self._validate_date_cell(table, item, 0, "premium_dates"))
        self.unscheduled_premium_table = table
        layout.addWidget(table)
        return group

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
        elif headers == ["Date", "Amount", "Type"]:
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

    def load_data_from_policy(self, policy, *, has_shadow: bool = False):
        self._issue_date = getattr(policy, "issue_date", None)
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
        self.dynamic_panel.load_from_policy(policy, has_shadow=has_shadow)

    def _update_valuation_banner(self, policy):
        valuation_date = getattr(policy, "valuation_date", None)
        if valuation_date is not None:
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
        policy_year = getattr(policy, "policy_year", None)
        self.banner_policy_year_label.setText(str(policy_year) if policy_year else "—")
        face = (getattr(policy, "base_total_face_amount", None)
                or getattr(policy, "base_face_amount", None)
                or getattr(policy, "face_amount", None))
        try:
            self.banner_face_label.setText(f"{float(face):,.0f}" if face else "—")
        except (TypeError, ValueError):
            self.banner_face_label.setText("—")
        rateclass = (getattr(policy, "base_rate_class", None)
                     or getattr(policy, "rate_class", None))
        self.banner_rateclass_label.setText(str(rateclass) if rateclass else "—")

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
            self._collect_dated_transactions(self.unscheduled_premium_table, TransactionKind.PREMIUM)
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
        md_request = self.dynamic_panel.monthly_deduction_request()
        return IllustrationOptions(
            conform_to_tefra=self.tefra_check.isChecked(),
            conform_to_tamra=self.tamra_check.isChecked(),
            allow_exception_prems=self.dynamic_panel.exception_prem_check.isChecked(),
            exact_days_interest=self.exact_days_check.isChecked(),
            cap_premiums_at_acceptance=self.cap_acceptance_check.isChecked(),
            levelizing_premium=self.levelizing_check.isChecked(),
            guideline_by_search=self.gp_search_check.isChecked(),
            apply_prem_to_loan=self.dynamic_panel.apply_prem_to_loan_check.isChecked(),
            apply_excess_repayment_as_premium=(
                self.dynamic_panel.excess_repay_as_premium_check.isChecked()),
            pay_monthly_deduction=md_request is not None,
            monthly_deduction_start_year=(
                md_request["start_year"] if md_request else None),
            iul_wair_crediting=self.wair_radio.isChecked(),
            use_policy_ag49_regime=self.policy_ag49_check.isChecked(),
        )

    def min_level_request(self) -> Optional[dict]:
        return self.dynamic_panel.min_level_request()

    def lumpsum_to_next_enabled(self) -> bool:
        return self.dynamic_panel.lumpsum_to_next_enabled()

    def set_lumpsum_amount(self, value: Optional[float]):
        self.dynamic_panel.set_lumpsum_amount(value)

    def level_premium_active(self) -> bool:
        return self.dynamic_panel.active_level_premium_type() is not None

    def set_min_level_amount(self, value: Optional[float]):
        self.dynamic_panel.set_min_level_amount(value)

    def stop_on_lapse_enabled(self) -> bool:
        return self.stop_on_lapse_check.isChecked()

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
        )

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

        get_base_coverages = getattr(policy, "get_base_coverages", None)
        if callable(get_base_coverages):
            try:
                for coverage in get_base_coverages():
                    maturity_date = getattr(coverage, "maturity_date", None)
                    if maturity_date is not None:
                        return maturity_date
            except Exception:
                pass

        issue_date = getattr(policy, "issue_date", None)
        issue_age = getattr(policy, "base_issue_age", None) or getattr(policy, "issue_age", None)
        maturity_age = getattr(policy, "maturity_age", None) or getattr(policy, "age_at_maturity", None)
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
        start_date = getattr(policy, "valuation_date", None) or getattr(policy, "issue_date", None)
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
        attained_age = getattr(policy, "attained_age", None)
        policy_month = getattr(policy, "policy_month", 1) or 1
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
