"""
Rate Viewer — Browse and filter all ABR rate tables.

Accessible from the ABR Quote header menu button. Lets users:
  - Select a rate type (Term Premium Rates, ABR Interest Rates, Per Diem)
  - Filter rows via clickable column-header dropdowns (PolView-style)
  - View the data in a styled, sortable table with copy + Excel dump
  - Add / Edit / Delete rows for Interest Rates and Per Diem tables
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QLineEdit, QPushButton,
    QFrame, QTableWidgetItem, QDialog, QGridLayout,
    QMessageBox,
)

from .abr_styles import (
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_RICH, CRIMSON_LIGHT, CRIMSON_BG, CRIMSON_SUBTLE,
    CRIMSON_SCROLL,
    SLATE_PRIMARY, SLATE_TEXT, SLATE_LIGHT,
    WHITE, GRAY_DARK, ABR_HEADER_COLORS, ABR_BORDER_COLOR,
)
from ...ui.widgets.frameless_window import FramelessWindowBase
from ...polview.ui.widgets import FixedHeaderTableWidget
from ..models.abr_database import get_abr_database
from ...core.build_env import ReadOnlyDataError, guard_data_writable, is_data_read_only

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EditFieldSpec:
    """Field metadata for generic rate edit dialogs."""

    label: str
    key: str
    placeholder: str = ""
    existing_index: int | None = None
    default: str = ""


# ── Rate type definitions ──────────────────────────────────────────────────

RATE_TYPES = [
    ("ABR Interest Rates", "interest_rates"),
    ("Per Diem Limits", "per_diem"),
    ("State Variations", "state_variations"),
    ("Min Face by Plancode", "min_face"),
]

# ── Shared button styles ──────────────────────────────────────────────────

_ACTION_BTN_STYLE = (
    f"QPushButton {{"
    f"  background-color: {WHITE}; color: {CRIMSON_DARK};"
    f"  border: 1px solid {CRIMSON_PRIMARY}; border-radius: 4px;"
    f"  font-size: 11px; font-weight: bold;"
    f"  padding: 4px 14px;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {CRIMSON_SUBTLE};"
    f"}}"
    f"QPushButton:pressed {{"
    f"  background-color: {CRIMSON_LIGHT};"
    f"}}"
)

_DELETE_BTN_STYLE = (
    f"QPushButton {{"
    f"  background-color: {WHITE}; color: #CC0000;"
    f"  border: 1px solid #CC0000; border-radius: 4px;"
    f"  font-size: 11px; font-weight: bold;"
    f"  padding: 4px 14px;"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: #FFF0F0;"
    f"}}"
    f"QPushButton:pressed {{"
    f"  background-color: #FFD0D0;"
    f"}}"
)


# ── Rate Viewer Window ─────────────────────────────────────────────────────

class RateViewerDialog(FramelessWindowBase):
    """Crimson Slate themed frameless window for browsing rate tables.

    Uses FixedHeaderTableWidget with filterable=True for Excel-style
    column-header dropdown filters (same as PolView tables).
    """

    def __init__(self, parent=None):
        super().__init__(
            title="SuiteView:  Rate Viewer",
            default_size=(920, 640),
            min_size=(650, 420),
            parent=parent,
            header_colors=ABR_HEADER_COLORS,
            border_color=ABR_BORDER_COLOR,
        )
        self._current_table_key = ""

    # ── FramelessWindowBase override ──────────────────────────────────

    def build_content(self) -> QWidget:
        """Build the body: controls strip + filterable table + footer."""
        body = QWidget()
        body.setObjectName("rvBody")
        body.setStyleSheet(f"""
            QWidget#rvBody {{
                background-color: {CRIMSON_BG};
            }}
        """)

        root = QVBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_controls(root)
        self._build_action_bar(root)
        self._build_rate_table(root)
        self._build_footer(root)

        QTimer.singleShot(50, lambda: self._on_type_changed(0))
        return body

    def _build_controls(self, root):
        # ── Control strip ──────────────────────────────────────────────
        controls = QWidget()
        controls.setObjectName("rvControls")
        controls.setStyleSheet(f"""
            QWidget#rvControls {{
                background-color: {WHITE};
            }}
        """)
        c_layout = QHBoxLayout(controls)
        c_layout.setContentsMargins(16, 10, 16, 10)
        c_layout.setSpacing(12)

        # Rate type selector
        type_label = QLabel("Rate Table:")
        type_label.setStyleSheet(
            f"color: {CRIMSON_DARK}; font-size: 12px; font-weight: bold; background: transparent;"
        )
        c_layout.addWidget(type_label)

        self._type_combo = QComboBox()
        self._type_combo.setMinimumWidth(220)
        self._type_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {WHITE};
                border: 2px solid {CRIMSON_PRIMARY};
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
                color: {GRAY_DARK};
                min-height: 24px;
            }}
            QComboBox:hover {{
                border-color: {SLATE_PRIMARY};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {WHITE};
                border: 2px solid {CRIMSON_PRIMARY};
                selection-background-color: {CRIMSON_PRIMARY};
                selection-color: {WHITE};
                font-size: 12px;
                outline: none;
            }}
        """)
        for display_name, _ in RATE_TYPES:
            self._type_combo.addItem(display_name)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        c_layout.addWidget(self._type_combo)

        c_layout.addStretch()

        # Quick filter input
        filter_label = QLabel("Quick Filter:")
        filter_label.setStyleSheet(
            f"color: {CRIMSON_DARK}; font-size: 12px; font-weight: bold; background: transparent;"
        )
        c_layout.addWidget(filter_label)

        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Type to highlight matching rows…")
        self._filter_input.setClearButtonEnabled(True)
        self._filter_input.setMinimumWidth(200)
        self._filter_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {WHITE};
                border: 2px solid {CRIMSON_PRIMARY};
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
                color: {GRAY_DARK};
                min-height: 24px;
            }}
            QLineEdit:focus {{
                border-color: {SLATE_PRIMARY};
                background-color: #FFFEF5;
            }}
        """)
        self._filter_input.textChanged.connect(self._on_quick_filter)
        c_layout.addWidget(self._filter_input, 1)

        root.addWidget(controls)

        # ── Gold divider ───────────────────────────────────────────────
        divider = QFrame()
        divider.setFixedHeight(2)
        divider.setStyleSheet(f"background-color: {SLATE_PRIMARY};")
        root.addWidget(divider)


    def _build_action_bar(self, root):
        # ── Action bar (Add / Edit / Delete) — visible for editable tables ──
        self._action_bar = QWidget()
        self._action_bar.setObjectName("rvActionBar")
        self._action_bar.setStyleSheet(f"""
            QWidget#rvActionBar {{
                background-color: {WHITE};
                border-bottom: 1px solid {CRIMSON_SUBTLE};
            }}
        """)
        ab_layout = QHBoxLayout(self._action_bar)
        ab_layout.setContentsMargins(16, 6, 16, 6)
        ab_layout.setSpacing(8)

        self._add_btn = QPushButton("＋ Add")
        self._add_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.clicked.connect(self._on_add_row)
        ab_layout.addWidget(self._add_btn)

        self._edit_btn = QPushButton("✎ Edit")
        self._edit_btn.setStyleSheet(_ACTION_BTN_STYLE)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.clicked.connect(self._on_edit_row)
        ab_layout.addWidget(self._edit_btn)

        self._delete_btn = QPushButton("✕ Delete")
        self._delete_btn.setStyleSheet(_DELETE_BTN_STYLE)
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.clicked.connect(self._on_delete_row)
        ab_layout.addWidget(self._delete_btn)

        ab_layout.addStretch()

        self._action_bar.setVisible(False)
        root.addWidget(self._action_bar)


    def _build_rate_table(self, root):
        # ── Table (FixedHeaderTableWidget with column filter popups) ───
        self._table = FixedHeaderTableWidget(filterable=True)
        # Override the frame/header colours to match teal theme
        self._table._outer_frame.setStyleSheet(f"""
            QFrame#outerFrame {{
                background-color: {WHITE};
                border: 1px solid {CRIMSON_PRIMARY};
                border-radius: 4px;
            }}
        """)
        self._table._data_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {WHITE};
                border: none;
                gridline-color: transparent;
                font-size: 11px;
                selection-background-color: {SLATE_LIGHT};
                selection-color: {CRIMSON_DARK};
            }}
            QTableWidget::item {{
                padding: 0px 4px;
                border: none;
            }}
            QTableWidget::item:selected {{
                background-color: {SLATE_LIGHT};
                color: {CRIMSON_DARK};
                border: none;
            }}
            QHeaderView::section {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
                color: {SLATE_TEXT};
                padding: 2px 4px;
                border: none;
                border-right: 1px solid {CRIMSON_RICH};
                font-size: 10px;
                font-weight: bold;
                height: 20px;
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
            QScrollBar:vertical {{
                background-color: {CRIMSON_SUBTLE};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {CRIMSON_SCROLL};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {CRIMSON_LIGHT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background-color: {CRIMSON_SUBTLE};
                height: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {CRIMSON_SCROLL};
                border-radius: 5px;
                min-width: 30px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {CRIMSON_LIGHT};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """)
        root.addWidget(self._table, 1)


    def _build_footer(self, root):
        # ── Footer / status strip ──────────────────────────────────────
        footer = QWidget()
        footer.setObjectName("rvFooter")
        footer.setStyleSheet(f"""
            QWidget#rvFooter {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
            }}
        """)
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(16, 6, 16, 6)
        f_layout.setSpacing(8)

        self._status_label = QLabel("Select a rate table to begin.")
        self._status_label.setStyleSheet(
            f"color: {SLATE_TEXT}; font-size: 11px; background: transparent;"
        )
        f_layout.addWidget(self._status_label)

        f_layout.addStretch()

        hint = QLabel("Click column headers to filter  •  Right-click for copy/export")
        hint.setStyleSheet(
            f"color: rgba(255,255,255,0.6); font-size: 10px; background: transparent;"
        )
        f_layout.addWidget(hint)

        root.addWidget(footer)


    # ── Data loading ───────────────────────────────────────────────────

    def _on_type_changed(self, index: int):
        """Load data for the selected rate type."""
        if index < 0 or index >= len(RATE_TYPES):
            return

        display_name, table_key = RATE_TYPES[index]
        self._current_table_key = table_key
        self._filter_input.clear()
        self._status_label.setText(f"Loading {display_name}…")

        # Show action bar only for tables we can edit directly (SV_ tables).
        # TERM-managed tables (modal_factors, band_amounts, policy_fees, min_face)
        # are read-only in the viewer — they're managed by the term rate loader.
        # Without database-write permission the action bar is hidden for
        # every table: the shared UL_Rates database is view-only.
        editable = table_key in (
            "interest_rates", "per_diem", "state_variations",
        ) and not is_data_read_only()
        self._action_bar.setVisible(editable)

        try:
            db = get_abr_database()

            viewer_map = {
                "interest_rates":   db.load_interest_rates_for_viewer,
                "term_rates":       db.load_term_rates_for_viewer,
                "per_diem":         db.load_per_diem_for_viewer,
                "state_variations": db.load_state_variations_for_viewer,
                "min_face":         db.load_min_face_for_viewer,
                "modal_factors":    db.load_modal_factors_for_viewer,
                "band_amounts":     db.load_band_amounts_for_viewer,
                "policy_fees":      db.load_policy_fees_for_viewer,
            }
            loader = viewer_map.get(table_key)
            if loader:
                headers, rows = loader()
                if rows:
                    self._populate_table(headers, rows, display_name)
                else:
                    self._table.clear()
                    self._status_label.setText(
                        f"No data found for {display_name}. "
                        f"Table may not be populated in UL_Rates."
                    )

        except Exception as e:
            logger.error(f"Error loading rates: {e}", exc_info=True)
            self._status_label.setText(
                f"Could not load {display_name} — check UL_Rates connection: {e}"
            )
            self._table.clear()

    def _populate_table(self, headers: list, rows: list, display_name: str):
        """Load data into the FixedHeaderTableWidget."""
        col_count = len(headers)
        self._table.setColumnCount(col_count)
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(len(rows))

        for r, row_data in enumerate(rows):
            for c, val in enumerate(row_data):
                if val is None:
                    item = QTableWidgetItem("")
                elif isinstance(val, float):
                    text = f"{val:,.6f}" if val < 1 else f"{val:,.2f}"
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                elif isinstance(val, int):
                    item = QTableWidgetItem(str(val))
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                else:
                    item = QTableWidgetItem(str(val))

                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(r, c, item)

        self._table.autoFitAllColumns()
        total = len(rows)
        self._status_label.setText(f"Loaded {display_name} — {total:,} rows")

    # ── Quick filter (text search → show/hide rows) ────────────────────

    def _on_quick_filter(self, text: str):
        """Show only rows containing the filter text (across all columns)."""
        text = text.strip().lower()
        row_count = self._table.rowCount()
        col_count = self._table.columnCount()

        if not text:
            # Show all rows
            for r in range(row_count):
                self._table._data_table.setRowHidden(r, False)
            return

        for r in range(row_count):
            match = False
            for c in range(col_count):
                item = self._table.item(r, c)
                if item and text in item.text().lower():
                    match = True
                    break
            self._table._data_table.setRowHidden(r, not match)

    # ── CRUD operations ────────────────────────────────────────────────

    def _get_selected_row_data(self) -> Optional[list]:
        """Return the cell values for the currently selected row, or None."""
        sel = self._table._data_table.selectedItems()
        if not sel:
            return None
        row_idx = sel[0].row()
        col_count = self._table.columnCount()
        values = []
        for c in range(col_count):
            item = self._table.item(row_idx, c)
            values.append(item.text() if item else "")
        return values

    def _reject_write(self, action: str) -> bool:
        """Recheck live permissions, including for already-open editors."""
        try:
            guard_data_writable(action)
        except ReadOnlyDataError as exc:
            QMessageBox.information(self, "Permission Required", str(exc))
            return True
        return False

    def _on_add_row(self):
        """Add a new row to the current editable table."""
        if self._reject_write("add rate data"):
            return
        if self._current_table_key == "interest_rates":
            self._edit_interest_rate_dialog(existing=None)
        elif self._current_table_key == "per_diem":
            self._edit_per_diem_dialog(existing=None)
        elif self._current_table_key == "state_variations":
            self._edit_state_variation_dialog(existing=None)
        elif self._current_table_key == "min_face":
            self._edit_min_face_dialog(existing=None)
        elif self._current_table_key == "modal_factors":
            self._edit_modal_factor_dialog(existing=None)
        elif self._current_table_key == "band_amounts":
            self._edit_band_amount_dialog(existing=None)
        elif self._current_table_key == "policy_fees":
            self._edit_policy_fee_dialog(existing=None)

    def _on_edit_row(self):
        """Edit the selected row."""
        if self._reject_write("edit rate data"):
            return
        row_data = self._get_selected_row_data()
        if row_data is None:
            QMessageBox.information(self, "Edit", "Please select a row to edit.")
            return
        if self._current_table_key == "interest_rates":
            self._edit_interest_rate_dialog(existing=row_data)
        elif self._current_table_key == "per_diem":
            self._edit_per_diem_dialog(existing=row_data)
        elif self._current_table_key == "state_variations":
            self._edit_state_variation_dialog(existing=row_data)
        elif self._current_table_key == "min_face":
            self._edit_min_face_dialog(existing=row_data)
        elif self._current_table_key == "modal_factors":
            self._edit_modal_factor_dialog(existing=row_data)
        elif self._current_table_key == "band_amounts":
            self._edit_band_amount_dialog(existing=row_data)
        elif self._current_table_key == "policy_fees":
            self._edit_policy_fee_dialog(existing=row_data)

    def _on_delete_row(self):
        """Delete the selected row from the current table."""
        if self._reject_write("delete rate data"):
            return
        row_data = self._get_selected_row_data()
        if row_data is None:
            QMessageBox.information(self, "Delete", "Please select a row to delete.")
            return

        key_text = ""
        query = ""
        pk_val = None

        if self._current_table_key == "interest_rates":
            key_text = row_data[0] # effective_date
            pk_val = key_text
            query = "DELETE FROM [SV_ABR_INTEREST_RATES] WHERE effective_date = ?"
        elif self._current_table_key == "per_diem":
            key_text = row_data[0] # year
            pk_val = int(key_text)
            query = "DELETE FROM [SV_ABR_PER_DIEM] WHERE year = ?"
        elif self._current_table_key == "state_variations":
            key_text = row_data[1] # state_abbr (PK)
            pk_val = key_text
            query = "DELETE FROM [SV_ABR_STATE_VARIATIONS] WHERE state_abbr = ?"
        elif self._current_table_key == "min_face":
            key_text = row_data[0] # plancode (PK)
            pk_val = key_text
            query = "DELETE FROM [SV_ABR_MIN_FACE] WHERE plancode = ?"
        elif self._current_table_key == "modal_factors":
            key_text = f"{row_data[0]} mode {row_data[1]}"
            pk_val = (row_data[0], int(row_data[1]))
            query = "DELETE FROM [SV_ABR_MODAL_FACTORS] WHERE plancode = ? AND mode_code = ?"
        elif self._current_table_key == "band_amounts":
            key_text = f"{row_data[0]} band {row_data[1]}"
            pk_val = (row_data[0], int(row_data[1]))
            query = "DELETE FROM [SV_ABR_BAND_AMOUNTS] WHERE plancode = ? AND band = ?"
        elif self._current_table_key == "policy_fees":
            key_text = row_data[0] # plancode (PK)
            pk_val = key_text
            query = "DELETE FROM [SV_ABR_POLICY_FEES] WHERE plancode = ?"
        else:
            return

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete the entry for '{key_text}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            guard_data_writable("delete rate data")
            db = get_abr_database()
            conn = db.connect()
            cursor = conn.cursor()
            if isinstance(pk_val, tuple):
                cursor.execute(query, pk_val)
            else:
                cursor.execute(query, (pk_val,))
            conn.commit()
            cursor.close()
            self._status_label.setText(f"Deleted entry '{key_text}'.")
            # Reload
            self._on_type_changed(self._type_combo.currentIndex())
        except Exception as e:
            logger.error(f"Error deleting row: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete: {e}")

    # ── Generic edit dialogs ─────────────────────────────────────────

    def _run_edit_dialog(
        self,
        *,
        add_title: str,
        edit_title: str,
        fields: list[EditFieldSpec],
        existing: Optional[list],
        width: int = 360,
    ) -> dict[str, str] | None:
        """Show a generic line-edit dialog and return stripped field values."""
        dlg = QDialog(self)
        dlg.setWindowTitle(add_title if existing is None else edit_title)
        dlg.setMinimumWidth(width)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        inputs = RateViewerDialog._add_edit_fields(self, grid, fields, existing)
        layout.addLayout(grid)
        RateViewerDialog._add_edit_buttons(self, layout, dlg)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return {key: widget.text().strip() for key, widget in inputs.items()}

    def _add_edit_fields(self, grid: QGridLayout, fields: list[EditFieldSpec], existing):
        label_style = f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;"
        input_style = (
            f"QLineEdit {{ border: 2px solid {CRIMSON_PRIMARY}; border-radius: 4px;"
            f" padding: 6px 8px; font-size: 12px; color: {GRAY_DARK}; }}"
            f"QLineEdit:focus {{ border-color: {SLATE_PRIMARY}; background: #FFFEF5; }}"
        )
        inputs = {}
        for row, spec in enumerate(fields):
            label = QLabel(spec.label)
            label.setStyleSheet(label_style)
            grid.addWidget(label, row, 0)
            widget = QLineEdit()
            widget.setStyleSheet(input_style)
            widget.setPlaceholderText(spec.placeholder)
            if existing and spec.existing_index is not None:
                widget.setText(str(existing[spec.existing_index] or "").replace("$", "").replace(",", ""))
            elif spec.default:
                widget.setText(spec.default)
            inputs[spec.key] = widget
            grid.addWidget(widget, row, 1)
        return inputs

    def _add_edit_buttons(self, layout: QVBoxLayout, dlg: QDialog) -> None:
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_ACTION_BTN_STYLE)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {CRIMSON_PRIMARY}; color: {WHITE};"
            f"  border: none; border-radius: 4px;"
            f"  font-size: 12px; font-weight: bold;"
            f"  padding: 6px 20px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {CRIMSON_DARK};"
            f"}}"
        )
        save_btn.setDefault(True)
        save_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _upsert_rate_row(
        self,
        action: str,
        delete_sql: str,
        delete_params: tuple,
        insert_sql: str,
        insert_params: tuple,
        status: str,
        *,
        old_delete: tuple[str, tuple] | None = None,
    ) -> None:
        try:
            guard_data_writable(action)
            db = get_abr_database()
            conn = db.connect()
            cursor = conn.cursor()
            if old_delete:
                cursor.execute(old_delete[0], old_delete[1])
            cursor.execute(delete_sql, delete_params)
            cursor.execute(insert_sql, insert_params)
            conn.commit()
            cursor.close()
            self._status_label.setText(status)
            self._on_type_changed(self._type_combo.currentIndex())
        except Exception as e:
            logger.error(f"Error saving rate data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def _warn_required(self, label: str) -> None:
        QMessageBox.warning(self, "Validation", f"{label} is required.")

    def _parse_float(self, values: dict[str, str], key: str, label: str, default=None):
        text = values.get(key, "")
        if text == "" and default is not None:
            return default
        try:
            return float(text)
        except ValueError:
            QMessageBox.warning(self, "Validation", f"{label} must be a number.")
            return None

    def _parse_int(self, values: dict[str, str], key: str, label: str, default=None):
        text = values.get(key, "")
        if text == "" and default is not None:
            return default
        try:
            return int(text)
        except ValueError:
            QMessageBox.warning(self, "Validation", f"{label} must be an integer.")
            return None

    # ── Interest Rate edit dialog ──────────────────────────────────────

    def _edit_interest_rate_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit an interest rate entry."""
        values = RateViewerDialog._run_edit_dialog(self, 
            add_title="Add Interest Rate",
            edit_title="Edit Interest Rate",
            existing=existing,
            fields=[
                EditFieldSpec("Date (YYYY-MM):", "date", "e.g. 2026-01", 0),
                EditFieldSpec("Moody Ave Yield (%):", "rate", "e.g. 5.63", 1),
                EditFieldSpec("ABR Rate (%):", "iul_rate", "e.g. 5.60", 2),
            ],
        )
        if values is None:
            return
        dt = values["date"]
        if not dt:
            RateViewerDialog._warn_required(self, "Date")
            return
        rate = RateViewerDialog._parse_float(self, values, "rate", "Moody Ave Yield")
        if rate is None:
            return
        iul_rate = None
        if values["iul_rate"]:
            iul_rate = RateViewerDialog._parse_float(self, values, "iul_rate", "ABR Rate")
            if iul_rate is None:
                return
        RateViewerDialog._upsert_rate_row(self, 
            "save interest rate data",
            "DELETE FROM [SV_ABR_INTEREST_RATES] WHERE effective_date = ?",
            (dt,),
            "INSERT INTO [SV_ABR_INTEREST_RATES] (effective_date, rate, iul_var_loan_rate) VALUES (?, ?, ?)",
            (dt, rate, iul_rate),
            f"{'Added' if existing is None else 'Updated'} interest rate for {dt}.",
            old_delete=("DELETE FROM [SV_ABR_INTEREST_RATES] WHERE effective_date = ?", (existing[0],))
            if existing and dt != existing[0] else None,
        )

    def _edit_per_diem_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a per diem entry."""
        values = RateViewerDialog._run_edit_dialog(self, 
            add_title="Add Per Diem",
            edit_title="Edit Per Diem",
            existing=existing,
            fields=[
                EditFieldSpec("Year:", "year", "e.g. 2026", 0),
                EditFieldSpec("Daily Limit ($):", "daily", "e.g. 430", 1),
                EditFieldSpec("Annual Limit ($):", "annual", "e.g. 156950", 2),
            ],
        )
        if values is None:
            return
        year = RateViewerDialog._parse_int(self, values, "year", "Year")
        daily = RateViewerDialog._parse_float(self, values, "daily", "Daily Limit")
        annual = RateViewerDialog._parse_float(self, values, "annual", "Annual Limit")
        if None in (year, daily, annual):
            return
        old_year = int(existing[0].replace(",", "")) if existing else None
        RateViewerDialog._upsert_rate_row(self, 
            "save per diem data",
            "DELETE FROM [SV_ABR_PER_DIEM] WHERE year = ?",
            (year,),
            "INSERT INTO [SV_ABR_PER_DIEM] (year, daily_limit, annual_limit) VALUES (?, ?, ?)",
            (year, daily, annual),
            f"{'Added' if existing is None else 'Updated'} per diem for {year}.",
            old_delete=("DELETE FROM [SV_ABR_PER_DIEM] WHERE year = ?", (old_year,))
            if old_year is not None and year != old_year else None,
        )

    def _edit_state_variation_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a state variation entry."""
        values = RateViewerDialog._run_edit_dialog(self, 
            add_title="Add State Variation",
            edit_title="Edit State Variation",
            existing=existing,
            width=500,
            fields=[
                EditFieldSpec("CL State Code:", "cl_state_code", "", 0),
                EditFieldSpec("State Abbr:", "state_abbr", "", 1),
                EditFieldSpec("State Name:", "state_name", "", 2),
                EditFieldSpec("State Group:", "state_group", "", 3),
                EditFieldSpec("Admin Fee ($):", "admin_fee", "", 4, "250.0"),
                EditFieldSpec("Election Form:", "election_form", "", 5),
                EditFieldSpec("Disclosure Critical:", "disclosure_form_critical", "", 6),
                EditFieldSpec("Disclosure Chronic:", "disclosure_form_chronic", "", 7),
                EditFieldSpec("Disclosure Terminal:", "disclosure_form_terminal", "", 8),
            ],
        )
        if values is None:
            return
        if not values["state_abbr"]:
            RateViewerDialog._warn_required(self, "State Abbreviation")
            return
        cl_code = None
        if values["cl_state_code"]:
            cl_code = RateViewerDialog._parse_int(self, values, "cl_state_code", "CL State Code")
            if cl_code is None:
                return
        admin_fee = RateViewerDialog._parse_float(self, values, "admin_fee", "Admin Fee", default=250.0)
        if admin_fee is None:
            return
        new_abbr = values["state_abbr"]
        RateViewerDialog._upsert_rate_row(self, 
            "save state variation data",
            "DELETE FROM [SV_ABR_STATE_VARIATIONS] WHERE state_abbr = ?",
            (new_abbr,),
            "INSERT INTO [SV_ABR_STATE_VARIATIONS] (state_abbr, cl_state_code, state_name, state_group, admin_fee, election_form, disclosure_form_critical, disclosure_form_chronic, disclosure_form_terminal) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_abbr, cl_code, values["state_name"], values["state_group"], admin_fee,
             values["election_form"], values["disclosure_form_critical"],
             values["disclosure_form_chronic"], values["disclosure_form_terminal"]),
            f"{'Added' if existing is None else 'Updated'} state variation for {new_abbr}.",
            old_delete=("DELETE FROM [SV_ABR_STATE_VARIATIONS] WHERE state_abbr = ?", (existing[1],))
            if existing and new_abbr != existing[1] else None,
        )

    def _edit_min_face_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a min face entry."""
        values = RateViewerDialog._run_edit_dialog(self, 
            add_title="Add Min Face",
            edit_title="Edit Min Face",
            existing=existing,
            fields=[
                EditFieldSpec("Plancode:", "plancode", "e.g. B75TL400", 0),
                EditFieldSpec("Min Face Amount ($):", "amount", "e.g. 50000", 1),
            ],
        )
        if values is None:
            return
        plancode = values["plancode"].upper()
        if not plancode:
            RateViewerDialog._warn_required(self, "Plancode")
            return
        amount = RateViewerDialog._parse_float(self, values, "amount", "Min Face Amount")
        if amount is None:
            return
        RateViewerDialog._upsert_rate_row(self, 
            "save min face data",
            "DELETE FROM [SV_ABR_MIN_FACE] WHERE plancode = ?",
            (plancode,),
            "INSERT INTO [SV_ABR_MIN_FACE] (plancode, min_face_amt) VALUES (?, ?)",
            (plancode, amount),
            f"{'Added' if existing is None else 'Updated'} min face for {plancode}.",
            old_delete=("DELETE FROM [SV_ABR_MIN_FACE] WHERE plancode = ?", (existing[0],))
            if existing and plancode != existing[0].upper() else None,
        )

    def _edit_modal_factor_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a modal factor entry."""
        values = RateViewerDialog._run_edit_dialog(self, 
            add_title="Add Modal Factor",
            edit_title="Edit Modal Factor",
            existing=existing,
            width=400,
            fields=[
                EditFieldSpec("Plancode:", "plancode", "e.g. B75TL400", 0),
                EditFieldSpec("Mode Code:", "mode_code", "1=Ann, 2=Semi, 3=Qtr, 4=Mon, 5=PAC, 6=BiWk", 1),
                EditFieldSpec("Mode Label:", "mode_label", "e.g. Annual", 2),
                EditFieldSpec("Factor:", "factor", "e.g. 0.0930", 3),
            ],
        )
        if values is None:
            return
        plancode = values["plancode"].upper()
        if not plancode:
            RateViewerDialog._warn_required(self, "Plancode")
            return
        mode_code = RateViewerDialog._parse_int(self, values, "mode_code", "Mode Code")
        factor = RateViewerDialog._parse_float(self, values, "factor", "Factor")
        if mode_code is None or factor is None:
            return
        mode_label = values["mode_label"] or f"Mode {mode_code}"
        old_delete = None
        if existing:
            old_pc, old_mode = existing[0].upper(), int(existing[1])
            if plancode != old_pc or mode_code != old_mode:
                old_delete = (
                    "DELETE FROM [SV_ABR_MODAL_FACTORS] WHERE plancode = ? AND mode_code = ?",
                    (old_pc, old_mode),
                )
        RateViewerDialog._upsert_rate_row(self, 
            "save modal factor data",
            "DELETE FROM [SV_ABR_MODAL_FACTORS] WHERE plancode = ? AND mode_code = ?",
            (plancode, mode_code),
            "INSERT INTO [SV_ABR_MODAL_FACTORS] (plancode, mode_code, mode_label, factor) VALUES (?, ?, ?, ?)",
            (plancode, mode_code, mode_label, factor),
            f"{'Added' if existing is None else 'Updated'} modal factor for {plancode} mode {mode_code}.",
            old_delete=old_delete,
        )

    def _edit_band_amount_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a band amount entry."""
        values = RateViewerDialog._run_edit_dialog(self, 
            add_title="Add Band Amount",
            edit_title="Edit Band Amount",
            existing=existing,
            width=380,
            fields=[
                EditFieldSpec("Plancode:", "plancode", "e.g. B75TL400", 0),
                EditFieldSpec("Band:", "band", "e.g. 1", 1),
                EditFieldSpec("Min Face Amount ($):", "amount", "e.g. 50000", 2),
            ],
        )
        if values is None:
            return
        plancode = values["plancode"].upper()
        if not plancode:
            RateViewerDialog._warn_required(self, "Plancode")
            return
        band = RateViewerDialog._parse_int(self, values, "band", "Band")
        amount = RateViewerDialog._parse_float(self, values, "amount", "Min Face Amount")
        if band is None or amount is None:
            return
        old_delete = None
        if existing:
            old_pc, old_band = existing[0].upper(), int(existing[1])
            if plancode != old_pc or band != old_band:
                old_delete = (
                    "DELETE FROM [SV_ABR_BAND_AMOUNTS] WHERE plancode = ? AND band = ?",
                    (old_pc, old_band),
                )
        RateViewerDialog._upsert_rate_row(self, 
            "save band amount data",
            "DELETE FROM [SV_ABR_BAND_AMOUNTS] WHERE plancode = ? AND band = ?",
            (plancode, band),
            "INSERT INTO [SV_ABR_BAND_AMOUNTS] (plancode, band, min_face_amt) VALUES (?, ?, ?)",
            (plancode, band, amount),
            f"{'Added' if existing is None else 'Updated'} band amount for {plancode} band {band}.",
            old_delete=old_delete,
        )

    def _edit_policy_fee_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a policy fee entry."""
        values = RateViewerDialog._run_edit_dialog(self, 
            add_title="Add Policy Fee",
            edit_title="Edit Policy Fee",
            existing=existing,
            fields=[
                EditFieldSpec("Plancode:", "plancode", "e.g. B75TL400", 0),
                EditFieldSpec("Annual Fee ($):", "fee", "e.g. 60.0", 1),
            ],
        )
        if values is None:
            return
        plancode = values["plancode"].upper()
        if not plancode:
            RateViewerDialog._warn_required(self, "Plancode")
            return
        fee = RateViewerDialog._parse_float(self, values, "fee", "Annual Fee")
        if fee is None:
            return
        RateViewerDialog._upsert_rate_row(self, 
            "save policy fee data",
            "DELETE FROM [SV_ABR_POLICY_FEES] WHERE plancode = ?",
            (plancode,),
            "INSERT INTO [SV_ABR_POLICY_FEES] (plancode, annual_fee) VALUES (?, ?)",
            (plancode, fee),
            f"{'Added' if existing is None else 'Updated'} policy fee for {plancode}.",
            old_delete=("DELETE FROM [SV_ABR_POLICY_FEES] WHERE plancode = ?", (existing[0],))
            if existing and plancode != existing[0].upper() else None,
        )
