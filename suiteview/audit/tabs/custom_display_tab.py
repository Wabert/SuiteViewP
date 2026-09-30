"""
Custom Display tab — lets the user add specific DB2 columns to the SELECT.

The tab starts with a few identical rows and an "Add Row" button for more.
Each row holds an enable checkbox, a single-select Table combo (``Seg NN -
TABLE``), and a multi-select Field combo (the same popup control used by the
Transaction tab's "Transaction 1" input).  Picking a table populates that row's
Field combo, and field picks are remembered per table so the user can switch
tables without losing selections.  When a row's checkbox is off its combos are
greyed (but still usable) and its fields are excluded from the SQL.  Multiple
rows let the user pull fields from several tables at once.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)
from PyQt6.QtGui import QFont

from ._styles import make_checkbox, make_multiselect_popup, make_combo
from ..db2_table_fields import CUSTOM_DISPLAY_TABLES, FIELD_KINDS, TABLE_FIELDS

_FONT = QFont("Segoe UI", 9)
_TABLE_COMBO_W = 190
_FIELD_COMBO_W = 220
_FIELD_DROPDOWN_ROWS = 28   # how many fields are visible in the dropdown
_CRITERIA_COMBO_W = 90
_CRITERIA_INPUT_W = 110
_NUM_ROWS = 3
_TABLE_LABELS = {db2: label for label, db2 in CUSTOM_DISPLAY_TABLES.items()}

# Criteria-type options shown in the per-row combo.  Empty string == no filter.
CRITERIA_TYPES = ["", "Contains", "Exact", "Range"]
_CRITERIA_TOOLTIP = (
    "Contains: text match anywhere in the field.\n"
    "Exact: equals, using the field's type (numbers as numbers, dates as dates).\n"
    "Range: inclusive From / To by the field's type; either end may be blank."
)
_KIND_HINTS = {"integer": "Whole number", "decimal": "Number", "date": "MM/DD/YYYY"}


def _label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    lbl.setStyleSheet("color: #1E5BA8;")
    return lbl


def _field_items(db2_table: str) -> list[tuple[str, str]]:
    """Return (label, value) pairs for a table's fields."""
    items = []
    for field, desc in TABLE_FIELDS.get(db2_table, []):
        label = f"{field}  —  {desc}" if desc else field
        items.append((label, field))
    return items


class _CustomDisplayRow(QWidget):
    """One row: checkbox + single-select Table combo + multi-select Field combo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # db2 table name -> set of selected field names (remembered per table)
        self._selected: dict[str, set[str]] = {}
        self._current_table = ""
        self._loading = False
        self._build_ui()

    def _build_ui(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.chk_enable = make_checkbox("Include")
        self.chk_enable.toggled.connect(self._on_enable_toggled)
        row.addWidget(self.chk_enable)

        row.addSpacing(8)
        row.addWidget(_label("Table"))
        self.combo_tables = make_multiselect_popup(
            list(CUSTOM_DISPLAY_TABLES.keys()),
            width=_TABLE_COMBO_W, height_rows=len(CUSTOM_DISPLAY_TABLES), multi=False,
        )
        self.combo_tables.list_widget.itemSelectionChanged.connect(
            self._on_table_changed)
        row.addWidget(self.combo_tables)

        row.addSpacing(8)
        row.addWidget(_label("Field"))
        self.combo_fields = make_multiselect_popup(
            [], width=_FIELD_COMBO_W, height_rows=_FIELD_DROPDOWN_ROWS,
            multi=True, show_search=True,
        )
        self.combo_fields.list_widget.itemSelectionChanged.connect(
            self._on_fields_changed)
        row.addWidget(self.combo_fields)

        row.addSpacing(8)
        row.addWidget(_label("Criteria Type"))
        self.combo_criteria = make_combo(CRITERIA_TYPES, width=_CRITERIA_COMBO_W)
        self.combo_criteria.setToolTip(_CRITERIA_TOOLTIP)
        self.combo_criteria.currentTextChanged.connect(self._on_criteria_type_changed)
        row.addWidget(self.combo_criteria)

        self.txt_criteria = QLineEdit()
        self.txt_criteria.setFont(_FONT)
        self.txt_criteria.setFixedWidth(_CRITERIA_INPUT_W)
        row.addWidget(self.txt_criteria)

        # Range-only "to [  ]"; hidden otherwise but keeps its space so the
        # row never shifts.
        self.lbl_to = QLabel("to")
        self.lbl_to.setFont(_FONT)
        self.txt_criteria_to = QLineEdit()
        self.txt_criteria_to.setFont(_FONT)
        self.txt_criteria_to.setFixedWidth(_CRITERIA_INPUT_W)
        for widget in (self.lbl_to, self.txt_criteria_to):
            policy = widget.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            widget.setSizePolicy(policy)
            row.addWidget(widget)
        self._criteria_input_style()
        self._on_criteria_type_changed(self.combo_criteria.currentText())

        self.btn_remove = QPushButton("✕")
        self.btn_remove.setFont(QFont("Segoe UI", 8))
        self.btn_remove.setFixedSize(18, 18)
        self.btn_remove.setStyleSheet(
            "QPushButton { border: none; color: #999; background: transparent; }"
            "QPushButton:hover { color: #C00000; }"
            "QPushButton:disabled { color: transparent; }")
        self.btn_remove.setToolTip("Remove this row")
        row.addWidget(self.btn_remove)

        row.addStretch()
        self._refresh_muted()

    # ── Styling helpers ──────────────────────────────────────────────
    def _criteria_input_style(self):
        muted = not self.chk_enable.isChecked()
        bg = "#E4E4E4" if muted else "white"
        style = (
            f"QLineEdit {{ background: {bg}; border: 1px solid #1E5BA8;"
            " padding: 0px 4px; }"
        )
        self.txt_criteria.setStyleSheet(style)
        self.txt_criteria_to.setStyleSheet(style)

    def _refresh_criteria_hint(self):
        """Placeholder shows the expected input for the displayed table's
        selected fields (e.g. MM/DD/YYYY for date fields)."""
        kinds = FIELD_KINDS.get(self._current_table, {})
        selected = self._selected.get(self._current_table) or set()
        hints = {_KIND_HINTS.get(kinds.get(field, "text"), "") for field in selected}
        hint = hints.pop() if len(hints) == 1 else ""
        self.txt_criteria.setPlaceholderText(hint)
        self.txt_criteria_to.setPlaceholderText(hint)

    # ── Event handlers ───────────────────────────────────────────────
    def _on_criteria_type_changed(self, text: str):
        is_range = text == "Range"
        self.lbl_to.setVisible(is_range)
        self.txt_criteria_to.setVisible(is_range)
    def _refresh_muted(self):
        muted = not self.chk_enable.isChecked()
        self.combo_tables.set_muted(muted)
        self.combo_fields.set_muted(muted)
        self._criteria_input_style()

    def _on_enable_toggled(self, _on: bool):
        self._refresh_muted()

    def _on_table_changed(self):
        values = self.combo_tables.selected_values()
        label = values[0] if values else ""
        self._current_table = CUSTOM_DISPLAY_TABLES.get(label, "")
        self._populate_fields(self._current_table)

    def _on_fields_changed(self):
        if self._loading or not self._current_table:
            return
        fields = set(self.combo_fields.selected_values())
        if fields:
            self._selected[self._current_table] = fields
        else:
            self._selected.pop(self._current_table, None)
        self._refresh_criteria_hint()

    # ── Helpers ──────────────────────────────────────────────────────
    def _populate_fields(self, db2_table: str):
        self._loading = True
        self.combo_fields.set_items(_field_items(db2_table))
        selected = self._selected.get(db2_table)
        if selected:
            self.combo_fields.setText(", ".join(sorted(selected)))
        self._loading = False
        self._refresh_criteria_hint()

    # ── Public API ───────────────────────────────────────────────────
    def selections(self) -> list[tuple[str, str]]:
        """Ordered (db2_table, field) pairs for this row, or [] when disabled."""
        if not self.chk_enable.isChecked():
            return []
        result: list[tuple[str, str]] = []
        for db2 in CUSTOM_DISPLAY_TABLES.values():
            fields = self._selected.get(db2)
            if not fields:
                continue
            for field, _desc in TABLE_FIELDS.get(db2, []):
                if field in fields:
                    result.append((db2, field))
        return result

    def criteria_filter(self) -> tuple[str, list[str], str, str, str] | None:
        """Criteria for this row, or None when it should not be applied.

        Returns ``(db2_table, [fields], match_type, value, value_to)`` only
        when the row is enabled, a non-blank criteria type is chosen, a value
        is entered (for Range, at least one of From / To), and at least one
        field is selected.  ``value_to`` is only used by Range.  The criteria
        is applied to every selected field of the row's table (OR-combined by
        the SQL builder, which also validates the input against field types).
        """
        if not self.chk_enable.isChecked():
            return None
        match_type = self.combo_criteria.currentText().strip()
        value = self.txt_criteria.text().strip()
        value_to = self.txt_criteria_to.text().strip() if match_type == "Range" else ""
        if not match_type or not (value or value_to):
            return None
        pairs = self.selections()
        if not pairs:
            return None
        table = pairs[0][0]
        fields = [field for tbl, field in pairs if tbl == table]
        return (table, fields, match_type, value, value_to)

    def get_state(self) -> dict:
        return {
            "enabled": self.chk_enable.isChecked(),
            "table": self._current_table,
            "selections": {
                table: sorted(fields)
                for table, fields in self._selected.items() if fields
            },
            "criteria_type": self.combo_criteria.currentText(),
            "criteria_value": self.txt_criteria.text(),
            "criteria_value_to": self.txt_criteria_to.text(),
        }

    def set_state(self, state: dict):
        state = state or {}
        self._selected = {
            table: set(fields)
            for table, fields in (state.get("selections") or {}).items()
        }
        crit_type = state.get("criteria_type", "")
        idx = self.combo_criteria.findText(crit_type)
        self.combo_criteria.setCurrentIndex(idx if idx >= 0 else 0)
        self.txt_criteria.setText(state.get("criteria_value", ""))
        self.txt_criteria_to.setText(state.get("criteria_value_to", ""))
        self.chk_enable.setChecked(bool(state.get("enabled", False)))
        self._refresh_muted()
        label = _TABLE_LABELS.get(state.get("table") or "")
        self.combo_tables.setText(label or "")
        self._current_table = CUSTOM_DISPLAY_TABLES.get(label or "", "")
        self._populate_fields(self._current_table)


class CustomDisplayTab(QWidget):
    """Custom Display tab — add specific table fields to the SQL output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[_CustomDisplayRow] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 4, 4)
        root.setSpacing(6)

        hdr = QLabel("Add specific table fields to the SQL output")
        hdr.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        hdr.setStyleSheet("color: #333;")
        root.addWidget(hdr)

        content = QWidget()
        content.setObjectName("customDisplayRows")
        content.setStyleSheet("#customDisplayRows { background: transparent; }")
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        body.addLayout(self._rows_layout)

        self.btn_add_row = QPushButton("+ Add Row")
        self.btn_add_row.setFont(_FONT)
        self.btn_add_row.setFixedHeight(22)
        self.btn_add_row.setToolTip("Add another table/field row")
        self.btn_add_row.clicked.connect(lambda: self.add_row())
        body.addWidget(self.btn_add_row, alignment=Qt.AlignmentFlag.AlignLeft)
        body.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self._reset_rows(_NUM_ROWS)

    # ── Row management ───────────────────────────────────────────────
    def add_row(self) -> _CustomDisplayRow:
        """Append a blank row below the existing ones and return it."""
        row_widget = _CustomDisplayRow()
        row_widget.btn_remove.clicked.connect(
            lambda _checked=False, r=row_widget: self.remove_row(r))
        self.rows.append(row_widget)
        self._rows_layout.addWidget(row_widget)
        self._refresh_remove_buttons()
        return row_widget

    def remove_row(self, row_widget: _CustomDisplayRow):
        """Remove a row; the last remaining row is kept."""
        if len(self.rows) <= 1 or row_widget not in self.rows:
            return
        self.rows.remove(row_widget)
        self._rows_layout.removeWidget(row_widget)
        row_widget.deleteLater()
        self._refresh_remove_buttons()

    def _reset_rows(self, count: int):
        for row_widget in self.rows:
            self._rows_layout.removeWidget(row_widget)
            row_widget.deleteLater()
        self.rows = []
        for _ in range(max(count, 1)):
            self.add_row()

    def _refresh_remove_buttons(self):
        removable = len(self.rows) > 1
        for row_widget in self.rows:
            row_widget.btn_remove.setEnabled(removable)

    # ── Public API ───────────────────────────────────────────────────
    def get_selected_fields(self) -> list[tuple[str, str]]:
        """Return ordered (db2_table, field) pairs from all enabled rows.

        Duplicates across rows are collapsed (first occurrence wins).
        """
        result: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for row in self.rows:
            for pair in row.selections():
                if pair not in seen:
                    seen.add(pair)
                    result.append(pair)
        return result

    def get_criteria_filters(self) -> list[tuple[str, list[str], str, str, str]]:
        """Return ``(db2_table, [fields], match_type, value, value_to)`` for
        each enabled row that has criteria and at least one selected field.
        """
        filters: list[tuple[str, list[str], str, str, str]] = []
        for row in self.rows:
            crit = row.criteria_filter()
            if crit:
                filters.append(crit)
        return filters

    # ── Profile save/load ────────────────────────────────────────────
    def get_state(self) -> dict:
        return {"rows": [row.get_state() for row in self.rows]}

    def set_state(self, state: dict):
        state = state or {}
        row_states = state.get("rows") or []
        self._reset_rows(max(len(row_states), _NUM_ROWS))
        for row, row_state in zip(self.rows, row_states):
            row.set_state(row_state)
