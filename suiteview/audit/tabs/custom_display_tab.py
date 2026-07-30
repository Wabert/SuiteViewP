"""
Custom Display tab — lets the user add specific DB2 columns to the SELECT.

The tab shows several identical rows.  Each row holds an enable checkbox, a
single-select Table combo, and a multi-select Field combo (the same popup
control used by the Transaction tab's "Transaction 1" input).  Picking a table
populates that row's Field combo, and field picks are remembered per table so
the user can switch tables without losing selections.  When a row's checkbox is
off its combos are greyed (but still usable) and its fields are excluded from
the SQL.  Multiple rows let the user pull fields from several tables at once.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit
from PyQt6.QtGui import QFont

from ._styles import make_checkbox, make_multiselect_popup, make_combo
from ..db2_table_fields import CUSTOM_DISPLAY_TABLES, TABLE_FIELDS

_FONT = QFont("Segoe UI", 9)
_TABLE_COMBO_W = 150
_FIELD_COMBO_W = 220
_FIELD_DROPDOWN_ROWS = 28   # how many fields are visible in the dropdown
_CRITERIA_COMBO_W = 90
_CRITERIA_INPUT_W = 130
_NUM_ROWS = 3

# Criteria-type options shown in the per-row combo.  Empty string == no filter.
CRITERIA_TYPES = ["", "Contains", "Exact"]


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
            width=_TABLE_COMBO_W, height_rows=8, multi=False,
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
        row.addWidget(self.combo_criteria)

        self.txt_criteria = QLineEdit()
        self.txt_criteria.setFont(_FONT)
        self.txt_criteria.setFixedWidth(_CRITERIA_INPUT_W)
        self._criteria_input_style()
        row.addWidget(self.txt_criteria)

        note = QLabel("(text fields only)")
        note.setFont(QFont("Segoe UI", 8, italic=True))
        note.setStyleSheet("color: #888;")
        row.addWidget(note)

        row.addStretch()
        self._refresh_muted()

    # ── Styling helpers ──────────────────────────────────────────────
    def _criteria_input_style(self):
        muted = not self.chk_enable.isChecked()
        bg = "#E4E4E4" if muted else "white"
        self.txt_criteria.setStyleSheet(
            f"QLineEdit {{ background: {bg}; border: 1px solid #1E5BA8;"
            " padding: 0px 4px; }"
        )

    # ── Event handlers ───────────────────────────────────────────────
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

    # ── Helpers ──────────────────────────────────────────────────────
    def _populate_fields(self, db2_table: str):
        self._loading = True
        self.combo_fields.set_items(_field_items(db2_table))
        selected = self._selected.get(db2_table)
        if selected:
            self.combo_fields.setText(", ".join(sorted(selected)))
        self._loading = False

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

    def criteria_filter(self) -> tuple[str, list[str], str, str] | None:
        """Text criteria for this row, or None when it should not be applied.

        Returns ``(db2_table, [fields], match_type, value)`` only when the row
        is enabled, a non-blank criteria type is chosen, the value is non-empty,
        and at least one field is selected.  The criteria is applied to every
        selected field of the row's table (OR-combined by the SQL builder).
        """
        if not self.chk_enable.isChecked():
            return None
        match_type = self.combo_criteria.currentText().strip()
        value = self.txt_criteria.text().strip()
        if not match_type or not value:
            return None
        pairs = self.selections()
        if not pairs:
            return None
        table = pairs[0][0]
        fields = [field for tbl, field in pairs if tbl == table]
        return (table, fields, match_type, value)

    def get_state(self) -> dict:
        return {
            "enabled": self.chk_enable.isChecked(),
            "selections": {
                table: sorted(fields)
                for table, fields in self._selected.items() if fields
            },
            "criteria_type": self.combo_criteria.currentText(),
            "criteria_value": self.txt_criteria.text(),
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
        self.chk_enable.setChecked(bool(state.get("enabled", False)))
        self._refresh_muted()
        if self._current_table:
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

        for _ in range(_NUM_ROWS):
            row_widget = _CustomDisplayRow()
            self.rows.append(row_widget)
            root.addWidget(row_widget)

        root.addStretch()

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

    def get_criteria_filters(self) -> list[tuple[str, list[str], str, str]]:
        """Return ``(db2_table, [fields], match_type, value)`` for each enabled
        row that has a non-blank text criteria and at least one selected field.
        """
        filters: list[tuple[str, list[str], str, str]] = []
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
        for row, row_state in zip(self.rows, row_states):
            row.set_state(row_state)
