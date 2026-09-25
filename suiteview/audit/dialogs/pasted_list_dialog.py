"""
Paste List dialog — show pasted rows as a query table, nothing more.

Reads the clipboard as soon as it opens and shows the data exactly as pasted.
Columns are named ``C1``, ``C2`` … (or from the pasted header row); a column
that is clearly a policy number or company code is named ``PolicyNumber`` /
``CompanyCode``. Double-click a column heading to rename it. The same dialog
reopens an existing list (double-click its box on the Joins canvas) to review
the rows and rename columns. The parsing rules live in
:mod:`suiteview.audit.policy_list`.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from suiteview.audit.dialogs.tables_dialog import _BTN_SMALL_STYLE, _BTN_STYLE
from suiteview.audit.policy_list import (
    DEFAULT_LIST_NAME,
    clean_column_name,
    identify_columns,
    list_column_names,
    list_rows,
    looks_like_header,
    parse_clipboard_text,
    safe_table_name,
)

_PREVIEW_ROWS = 500


class PastedListDialog(QDialog):
    """Preview pasted rows and name their columns; see :meth:`result_data`.

    ``existing`` (``{"columns": [...], "rows": [...]}``) opens a list already in
    the query: its name is fixed and ``locked_columns`` (used on Display/Filter)
    cannot be renamed.
    """

    def __init__(self, *, taken_names: set[str], text: str | None = None,
                 existing: dict | None = None, name: str = "",
                 locked_columns: set[str] | None = None, parent=None):
        super().__init__(parent)
        self._editing = existing is not None
        self.setWindowTitle(f"Pasted List \u2014 {name}" if self._editing else "Paste List")
        self.setMinimumSize(560, 400)
        self._taken = set(taken_names)
        self._locked = set(locked_columns or ())
        self._grid: list[list[str]] = []
        self._columns: list[str] = []
        self._rows: list[list[str]] = []
        self._policy_col: int | None = None
        self._company_col: int | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(5)

        top = QHBoxLayout()
        top.addWidget(QLabel("Name"))
        self.txt_name = QLineEdit(
            name if self._editing else safe_table_name(DEFAULT_LIST_NAME, self._taken))
        self.txt_name.setFixedWidth(160)
        self.txt_name.setReadOnly(self._editing)
        top.addWidget(self.txt_name)
        top.addSpacing(14)
        self.chk_header = QCheckBox("First row is column names")
        self.chk_header.setVisible(not self._editing)
        self.chk_header.toggled.connect(self._rebuild)
        top.addWidget(self.chk_header)
        top.addStretch(1)
        lay.addLayout(top)

        hint = QLabel("Double-click a column heading to rename it.")
        hint.setStyleSheet("color: #64748B; font-size: 8pt;")
        lay.addWidget(hint)

        self.table = QTableWidget(self)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(18)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().sectionDoubleClicked.connect(self.rename_column)
        lay.addWidget(self.table, 1)

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #334155; font-size: 8pt;")
        lay.addWidget(self.lbl_count)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_add = QPushButton("Save" if self._editing else "Add to Query")
        self.btn_add.setStyleSheet(_BTN_STYLE)
        self.btn_add.clicked.connect(self._on_add)
        buttons.addWidget(self.btn_add)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(_BTN_SMALL_STYLE)
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)
        lay.addLayout(buttons)

        if self._editing:
            self._columns = list(existing.get("columns", []))
            width = len(self._columns)
            self._rows = [list(row)[:width] + [""] * (width - len(row))
                          for row in existing.get("rows", [])]
            self._show()
        elif text is None:
            clipboard = QApplication.clipboard()
            self.set_text(clipboard.text() if clipboard is not None else "")
        else:
            self.set_text(text)

    # ── Input ────────────────────────────────────────────────────────────

    def set_text(self, text: str):
        self._grid = parse_clipboard_text(text)
        self.chk_header.blockSignals(True)
        self.chk_header.setChecked(looks_like_header(self._grid))
        self.chk_header.blockSignals(False)
        self._rebuild()

    def _rebuild(self, *_args):
        has_header = self.chk_header.isChecked()
        self._policy_col, self._company_col = identify_columns(self._grid, has_header)
        self._columns = list_column_names(
            self._grid, has_header, self._policy_col, self._company_col)
        self._rows = list_rows(self._grid, has_header, self._policy_col, self._company_col)
        self._show()

    def _show(self):
        shown = self._rows[:_PREVIEW_ROWS]
        self.table.clear()
        self.table.setColumnCount(len(self._columns))
        self.table.setRowCount(len(shown))
        self.table.setHorizontalHeaderLabels(self._columns)
        for r, row in enumerate(shown):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(str(value)))
        for c, column in enumerate(self._columns):
            item = self.table.horizontalHeaderItem(c)
            if item is not None and column in self._locked:
                item.setToolTip("Used on Display or Filter \u2014 remove it there to rename.")
        self.table.resizeColumnsToContents()
        if not self._columns:
            self.lbl_count.setText("The clipboard is empty \u2014 copy rows from Excel first.")
        else:
            count = len(self._rows)
            text = f"{count} {'row' if count == 1 else 'rows'}"
            if count > _PREVIEW_ROWS:
                text += f" (first {_PREVIEW_ROWS} shown)"
            self.lbl_count.setText(text)
        self.btn_add.setEnabled(bool(self._rows))

    # ── Column names ─────────────────────────────────────────────────────

    def rename_column(self, index: int, new_name: str | None = None) -> bool:
        """Rename column ``index`` (asks the user when ``new_name`` is None)."""
        if not 0 <= index < len(self._columns):
            return False
        old = self._columns[index]
        if old in self._locked:
            QMessageBox.information(
                self, "Rename Column",
                f"{old} is used on Display or Filter. Remove it there to rename it.")
            return False
        if new_name is None:
            new_name, ok = QInputDialog.getText(
                self, "Rename Column", "Column name:", text=old)
            if not ok:
                return False
        name = clean_column_name(new_name)
        if not name or name == old:
            return False
        if any(name.upper() == other.upper()
               for i, other in enumerate(self._columns) if i != index):
            QMessageBox.warning(self, "Rename Column", f"There is already a column named {name}.")
            return False
        self._columns[index] = name
        item = self.table.horizontalHeaderItem(index)
        if item is not None:
            item.setText(name)
        self.table.resizeColumnToContents(index)
        return True

    def _on_add(self):
        if self._rows:
            self.accept()

    # ── Output ───────────────────────────────────────────────────────────

    def table_name(self) -> str:
        if self._editing:
            return self.txt_name.text()
        return safe_table_name(self.txt_name.text(), self._taken)

    def column_names(self) -> list[str]:
        return list(self._columns)

    def result_data(self) -> dict | None:
        """``{"columns": [...], "rows": [...]}`` for the query, or None when empty."""
        if not self._rows:
            return None
        return {"columns": list(self._columns), "rows": [list(row) for row in self._rows]}
