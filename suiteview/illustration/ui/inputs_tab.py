"""Illustration Inputs tab UI."""

from datetime import date, datetime

from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractItemDelegate,
    QButtonGroup,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    InforceOverrideSet,
    PolicyChangeEvent,
    PolicyChangeKind,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.polview.ui.formatting import format_date

from .styles import GROUP_STYLE, INPUT_TABLE_STYLE, PURPLE_BG, PURPLE_DARK


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
    """QTableWidget with Excel-like arrow-key navigation during editing."""

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
        self._issue_date: date | None = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
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

        for row in range(rows):
            table.setRowHeight(row, 20)
            for col in range(len(headers)):
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, col, item)

        if headers and headers[0] in {"Date", "Year"}:
            for row in range(rows):
                first_item = table.item(row, 0)
                if first_item:
                    first_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

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
        has_warning = False
        for row in range(table.rowCount()):
            item = table.item(row, date_column)
            if item and (item.text() or "").strip() and item.background().color() == self.WARNING_BG:
                has_warning = True
                break
        self._warning_labels[warning_key].setVisible(has_warning)

    def load_data_from_policy(self, policy):
        self._issue_date = getattr(policy, "issue_date", None)
        for label in self._warning_labels.values():
            base_text = label.property("base_text") or label.text()
            label.setText(self._warning_text(base_text))

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

        return input_set

    @staticmethod
    def export_inforce_overrides() -> InforceOverrideSet:
        return InforceOverrideSet()

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
