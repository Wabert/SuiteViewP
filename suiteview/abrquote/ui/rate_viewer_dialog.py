"""
Rate Viewer — Browse and filter all ABR rate tables.

Accessible from the ABR Quote header menu button. Lets users:
  - Select a rate type (Term Premium Rates, ABR Interest Rates, Per Diem)
  - Filter rows via clickable column-header dropdowns (PolView-style)
  - View the data in a styled, sortable table with copy + Excel dump
  - Add / Edit / Delete rows for Interest Rates and Per Diem tables
"""

from __future__ import annotations

import logging
from typing import Optional, List

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
    SLATE_PRIMARY, SLATE_TEXT, SLATE_DARK, SLATE_LIGHT,
    WHITE, GRAY_DARK, GRAY_LIGHT, GRAY_MID, GRAY_TEXT,
    ABR_HEADER_COLORS, ABR_BORDER_COLOR,
)
from ...ui.widgets.frameless_window import FramelessWindowBase
from ...polview.ui.widgets import FixedHeaderTableWidget
from ..models.abr_database import get_abr_database

logger = logging.getLogger(__name__)


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

        # Load initial data after the event loop starts
        QTimer.singleShot(50, lambda: self._on_type_changed(0))

        return body

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
        editable = table_key in (
            "interest_rates", "per_diem", "state_variations",
        )
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

    def _on_add_row(self):
        """Add a new row to the current editable table."""
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

    # ── Interest Rate edit dialog ──────────────────────────────────────

    def _edit_interest_rate_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit an interest rate entry.

        existing: [date_str, rate_str, iul_rate_str] or None for new.
        """
        is_new = existing is None
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Interest Rate" if is_new else "Edit Interest Rate")
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        LBL = f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;"
        INPUT = (
            f"QLineEdit {{ border: 2px solid {CRIMSON_PRIMARY}; border-radius: 4px;"
            f" padding: 6px 8px; font-size: 12px; color: {GRAY_DARK}; }}"
            f"QLineEdit:focus {{ border-color: {SLATE_PRIMARY}; background: #FFFEF5; }}"
        )

        # Date (YYYY-MM)
        lbl_date = QLabel("Date (YYYY-MM):")
        lbl_date.setStyleSheet(LBL)
        grid.addWidget(lbl_date, 0, 0)
        inp_date = QLineEdit()
        inp_date.setStyleSheet(INPUT)
        inp_date.setPlaceholderText("e.g. 2026-01")
        if existing:
            inp_date.setText(existing[0])
        grid.addWidget(inp_date, 0, 1)

        # Moody Ave Yield
        lbl_rate = QLabel("Moody Ave Yield (%):")
        lbl_rate.setStyleSheet(LBL)
        grid.addWidget(lbl_rate, 1, 0)
        inp_rate = QLineEdit()
        inp_rate.setStyleSheet(INPUT)
        inp_rate.setPlaceholderText("e.g. 5.63")
        if existing:
            inp_rate.setText(existing[1].replace(",", ""))
        grid.addWidget(inp_rate, 1, 1)

        # ABR Rate
        lbl_iul = QLabel("ABR Rate (%):")
        lbl_iul.setStyleSheet(LBL)
        grid.addWidget(lbl_iul, 2, 0)
        inp_iul = QLineEdit()
        inp_iul.setStyleSheet(INPUT)
        inp_iul.setPlaceholderText("e.g. 5.60")
        if existing and existing[2]:
            inp_iul.setText(existing[2].replace(",", ""))
        grid.addWidget(inp_iul, 2, 1)

        layout.addLayout(grid)

        # Buttons
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

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Validate & save
        dt = inp_date.text().strip()
        if not dt:
            QMessageBox.warning(self, "Validation", "Date is required.")
            return
        try:
            rate = float(inp_rate.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Moody Ave Yield must be a number.")
            return
        iul_text = inp_iul.text().strip()
        iul_rate = float(iul_text) if iul_text else None

        try:
            db = get_abr_database()
            conn = db.connect()
            cursor = conn.cursor()
            # Delete old row if editing with changed PK, or upsert
            if existing and dt != existing[0]:
                cursor.execute(
                    "DELETE FROM [SV_ABR_INTEREST_RATES] WHERE effective_date = ?",
                    (existing[0],)
                )
            cursor.execute(
                "DELETE FROM [SV_ABR_INTEREST_RATES] WHERE effective_date = ?", (dt,)
            )
            cursor.execute(
                "INSERT INTO [SV_ABR_INTEREST_RATES] "
                "(effective_date, rate, iul_var_loan_rate) VALUES (?, ?, ?)",
                (dt, rate, iul_rate)
            )
            conn.commit()
            cursor.close()
            self._status_label.setText(f"{'Added' if is_new else 'Updated'} interest rate for {dt}.")
            self._on_type_changed(self._type_combo.currentIndex())
        except Exception as e:
            logger.error(f"Error saving interest rate: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    # ── Per Diem edit dialog ───────────────────────────────────────────

    def _edit_per_diem_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a per diem entry.

        existing: [year_str, daily_str, annual_str] or None for new.
        """
        is_new = existing is None
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Per Diem" if is_new else "Edit Per Diem")
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        LBL = f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;"
        INPUT = (
            f"QLineEdit {{ border: 2px solid {CRIMSON_PRIMARY}; border-radius: 4px;"
            f" padding: 6px 8px; font-size: 12px; color: {GRAY_DARK}; }}"
            f"QLineEdit:focus {{ border-color: {SLATE_PRIMARY}; background: #FFFEF5; }}"
        )

        # Year
        lbl_year = QLabel("Year:")
        lbl_year.setStyleSheet(LBL)
        grid.addWidget(lbl_year, 0, 0)
        inp_year = QLineEdit()
        inp_year.setStyleSheet(INPUT)
        inp_year.setPlaceholderText("e.g. 2026")
        if existing:
            inp_year.setText(existing[0].replace(",", ""))
        grid.addWidget(inp_year, 0, 1)

        # Daily Limit
        lbl_daily = QLabel("Daily Limit ($):")
        lbl_daily.setStyleSheet(LBL)
        grid.addWidget(lbl_daily, 1, 0)
        inp_daily = QLineEdit()
        inp_daily.setStyleSheet(INPUT)
        inp_daily.setPlaceholderText("e.g. 430")
        if existing:
            inp_daily.setText(existing[1].replace(",", "").replace("$", ""))
        grid.addWidget(inp_daily, 1, 1)

        # Annual Limit
        lbl_annual = QLabel("Annual Limit ($):")
        lbl_annual.setStyleSheet(LBL)
        grid.addWidget(lbl_annual, 2, 0)
        inp_annual = QLineEdit()
        inp_annual.setStyleSheet(INPUT)
        inp_annual.setPlaceholderText("e.g. 156950")
        if existing:
            inp_annual.setText(existing[2].replace(",", "").replace("$", ""))
        grid.addWidget(inp_annual, 2, 1)

        layout.addLayout(grid)

        # Buttons
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

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Validate & save
        try:
            year = int(inp_year.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Year must be an integer.")
            return
        try:
            daily = float(inp_daily.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Daily Limit must be a number.")
            return
        try:
            annual = float(inp_annual.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Annual Limit must be a number.")
            return

        try:
            db = get_abr_database()
            conn = db.connect()
            cursor = conn.cursor()
            if existing:
                old_year = int(existing[0].replace(",", ""))
                if year != old_year:
                    cursor.execute(
                        "DELETE FROM [SV_ABR_PER_DIEM] WHERE year = ?", (old_year,)
                    )
            cursor.execute("DELETE FROM [SV_ABR_PER_DIEM] WHERE year = ?", (year,))
            cursor.execute(
                "INSERT INTO [SV_ABR_PER_DIEM] (year, daily_limit, annual_limit) "
                "VALUES (?, ?, ?)", (year, daily, annual)
            )
            conn.commit()
            cursor.close()
            self._status_label.setText(f"{'Added' if is_new else 'Updated'} per diem for {year}.")
            self._on_type_changed(self._type_combo.currentIndex())
        except Exception as e:
            logger.error(f"Error saving per diem: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    # ── State Variations edit dialog ─────────────────────────────────────

    def _edit_state_variation_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a state variation entry.
        
        Args:
            existing: List of values in order of table columns:
                      [cl_code, abbr, name, group, admin_fee, elect, crit, chron, term]
                      or None for new.
        """
        is_new = existing is None
        dlg = QDialog(self)
        dlg.setWindowTitle("Add State Variation" if is_new else "Edit State Variation")
        dlg.setMinimumWidth(500)
        
        # Main layout
        layout = QVBoxLayout(dlg)
        
        content_widget = QWidget()
        grid = QGridLayout(content_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        LBL = f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;"
        INPUT = (
            f"QLineEdit {{ border: 2px solid {CRIMSON_PRIMARY}; border-radius: 4px;"
            f" padding: 6px 8px; font-size: 12px; color: {GRAY_DARK}; }}"
            f"QLineEdit:focus {{ border-color: {SLATE_PRIMARY}; background: #FFFEF5; }}"
        )

        entries = {}
        
        # Note: existing is [code, abbr, state, group, admin_fee, elec, crit, chron, term]
        fields = [
            ("CL State Code:", "cl_state_code", existing[0] if existing else ""),
            ("State Abbr:", "state_abbr", existing[1] if existing else ""),
            ("State Name:", "state_name", existing[2] if existing else ""),
            ("State Group:", "state_group", existing[3] if existing else ""),
            ("Admin Fee ($):", "admin_fee", existing[4] if existing else "250.0"),
            ("Election Form:", "election_form", existing[5] if existing else ""),
            ("Disclosure Critical:", "disclosure_form_critical", existing[6] if existing else ""),
            ("Disclosure Chronic:", "disclosure_form_chronic", existing[7] if existing else ""),
            ("Disclosure Terminal:", "disclosure_form_terminal", existing[8] if existing else ""),
        ]

        for i, (label_text, key, val) in enumerate(fields):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(LBL)
            grid.addWidget(lbl, i, 0)
            
            inp = QLineEdit()
            inp.setStyleSheet(INPUT)
            inp.setText(str(val) if val is not None else "")
            entries[key] = inp
            grid.addWidget(inp, i, 1)

        layout.addWidget(content_widget)

        # Buttons
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

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Gather data
        data = {k: v.text().strip() for k, v in entries.items()}
        
        # Validate
        if not data["state_abbr"]:
             QMessageBox.warning(self, "Validation", "State Abbreviation is required.")
             return
             
        try:
            cl_code = int(data["cl_state_code"]) if data["cl_state_code"] else None
        except ValueError:
            QMessageBox.warning(self, "Validation", "CL State Code must be an integer.")
            return

        try:
            admin_fee = float(data["admin_fee"]) if data["admin_fee"] else 250.0
        except ValueError:
            QMessageBox.warning(self, "Validation", "Admin Fee must be a number.")
            return

        try:
            db = get_abr_database()
            conn = db.connect()
            cursor = conn.cursor()

            new_abbr = data["state_abbr"]
            if existing:
                old_abbr = existing[1]
                if new_abbr != old_abbr:
                    cursor.execute(
                        "DELETE FROM [SV_ABR_STATE_VARIATIONS] WHERE state_abbr = ?",
                        (old_abbr,)
                    )
            cursor.execute(
                "DELETE FROM [SV_ABR_STATE_VARIATIONS] WHERE state_abbr = ?",
                (new_abbr,)
            )
            cursor.execute(
                "INSERT INTO [SV_ABR_STATE_VARIATIONS] ("
                "    state_abbr, cl_state_code, state_name, state_group,"
                "    admin_fee, election_form, disclosure_form_critical,"
                "    disclosure_form_chronic, disclosure_form_terminal"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_abbr, cl_code, data["state_name"], data["state_group"],
                    admin_fee,
                    data["election_form"], data["disclosure_form_critical"],
                    data["disclosure_form_chronic"], data["disclosure_form_terminal"]
                )
            )
            conn.commit()
            cursor.close()

            self._status_label.setText(f"{'Added' if is_new else 'Updated'} state variation for {new_abbr}.")
            self._on_type_changed(self._type_combo.currentIndex())

        except Exception as e:
            logger.error(f"Error saving state variation: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    # ── Min Face edit dialog ───────────────────────────────────────────

    def _edit_min_face_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a min face entry.
        
        existing: [plancode, min_face_amt_str] or None for new.
        """
        is_new = existing is None
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Min Face" if is_new else "Edit Min Face")
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        LBL = f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;"
        INPUT = (
            f"QLineEdit {{ border: 2px solid {CRIMSON_PRIMARY}; border-radius: 4px;"
            f" padding: 6px 8px; font-size: 12px; color: {GRAY_DARK}; }}"
            f"QLineEdit:focus {{ border-color: {SLATE_PRIMARY}; background: #FFFEF5; }}"
        )

        lbl_pc = QLabel("Plancode:")
        lbl_pc.setStyleSheet(LBL)
        grid.addWidget(lbl_pc, 0, 0)
        inp_pc = QLineEdit()
        inp_pc.setStyleSheet(INPUT)
        inp_pc.setPlaceholderText("e.g. B75TL400")
        if existing:
            inp_pc.setText(existing[0])
        grid.addWidget(inp_pc, 0, 1)

        lbl_amt = QLabel("Min Face Amount ($):")
        lbl_amt.setStyleSheet(LBL)
        grid.addWidget(lbl_amt, 1, 0)
        inp_amt = QLineEdit()
        inp_amt.setStyleSheet(INPUT)
        inp_amt.setPlaceholderText("e.g. 50000")
        if existing:
            inp_amt.setText(existing[1].replace(",", ""))
        grid.addWidget(inp_amt, 1, 1)

        layout.addLayout(grid)

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

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        plancode = inp_pc.text().strip().upper()
        if not plancode:
            QMessageBox.warning(self, "Validation", "Plancode is required.")
            return
        try:
            amt = float(inp_amt.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Min Face Amount must be a number.")
            return

        try:
            db = get_abr_database()
            conn = db.connect()
            cursor = conn.cursor()
            if existing and plancode != existing[0].upper():
                cursor.execute(
                    "DELETE FROM [SV_ABR_MIN_FACE] WHERE plancode = ?", (existing[0],)
                )
            cursor.execute("DELETE FROM [SV_ABR_MIN_FACE] WHERE plancode = ?", (plancode,))
            cursor.execute(
                "INSERT INTO [SV_ABR_MIN_FACE] (plancode, min_face_amt) VALUES (?, ?)",
                (plancode, amt),
            )
            conn.commit()
            cursor.close()
            self._status_label.setText(f"{'Added' if is_new else 'Updated'} min face for {plancode}.")
            self._on_type_changed(self._type_combo.currentIndex())
        except Exception as e:
            logger.error(f"Error saving min face: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    # ── Modal Factor edit dialog ───────────────────────────────────────

    def _edit_modal_factor_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a modal factor entry.
        
        existing: [plancode, mode_code_str, mode_label, factor_str] or None.
        """
        is_new = existing is None
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Modal Factor" if is_new else "Edit Modal Factor")
        dlg.setMinimumWidth(400)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        LBL = f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;"
        INPUT = (
            f"QLineEdit {{ border: 2px solid {CRIMSON_PRIMARY}; border-radius: 4px;"
            f" padding: 6px 8px; font-size: 12px; color: {GRAY_DARK}; }}"
            f"QLineEdit:focus {{ border-color: {SLATE_PRIMARY}; background: #FFFEF5; }}"
        )

        # Plancode
        lbl_pc = QLabel("Plancode:")
        lbl_pc.setStyleSheet(LBL)
        grid.addWidget(lbl_pc, 0, 0)
        inp_pc = QLineEdit()
        inp_pc.setStyleSheet(INPUT)
        inp_pc.setPlaceholderText("e.g. B75TL400")
        if existing:
            inp_pc.setText(existing[0])
        grid.addWidget(inp_pc, 0, 1)

        # Mode Code
        lbl_mode = QLabel("Mode Code:")
        lbl_mode.setStyleSheet(LBL)
        grid.addWidget(lbl_mode, 1, 0)
        inp_mode = QLineEdit()
        inp_mode.setStyleSheet(INPUT)
        inp_mode.setPlaceholderText("1=Ann, 2=Semi, 3=Qtr, 4=Mon, 5=PAC, 6=BiWk")
        if existing:
            inp_mode.setText(existing[1])
        grid.addWidget(inp_mode, 1, 1)

        # Mode Label
        lbl_label = QLabel("Mode Label:")
        lbl_label.setStyleSheet(LBL)
        grid.addWidget(lbl_label, 2, 0)
        inp_label = QLineEdit()
        inp_label.setStyleSheet(INPUT)
        inp_label.setPlaceholderText("e.g. Annual")
        if existing:
            inp_label.setText(existing[2])
        grid.addWidget(inp_label, 2, 1)

        # Factor
        lbl_factor = QLabel("Factor:")
        lbl_factor.setStyleSheet(LBL)
        grid.addWidget(lbl_factor, 3, 0)
        inp_factor = QLineEdit()
        inp_factor.setStyleSheet(INPUT)
        inp_factor.setPlaceholderText("e.g. 0.0930")
        if existing:
            inp_factor.setText(existing[3].replace(",", ""))
        grid.addWidget(inp_factor, 3, 1)

        layout.addLayout(grid)

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

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        plancode = inp_pc.text().strip().upper()
        if not plancode:
            QMessageBox.warning(self, "Validation", "Plancode is required.")
            return
        try:
            mode_code = int(inp_mode.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Mode Code must be an integer.")
            return
        mode_label = inp_label.text().strip() or f"Mode {mode_code}"
        try:
            factor = float(inp_factor.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Factor must be a number.")
            return

        try:
            db = get_abr_database()
            conn = db.connect()
            cursor = conn.cursor()
            if existing:
                old_pc = existing[0].upper()
                old_mode = int(existing[1])
                if plancode != old_pc or mode_code != old_mode:
                    cursor.execute(
                        "DELETE FROM [SV_ABR_MODAL_FACTORS] "
                        "WHERE plancode = ? AND mode_code = ?",
                        (old_pc, old_mode),
                    )
            cursor.execute(
                "DELETE FROM [SV_ABR_MODAL_FACTORS] "
                "WHERE plancode = ? AND mode_code = ?",
                (plancode, mode_code),
            )
            cursor.execute(
                "INSERT INTO [SV_ABR_MODAL_FACTORS] "
                "(plancode, mode_code, mode_label, factor) VALUES (?, ?, ?, ?)",
                (plancode, mode_code, mode_label, factor),
            )
            conn.commit()
            cursor.close()
            self._status_label.setText(
                f"{'Added' if is_new else 'Updated'} modal factor for {plancode} mode {mode_code}."
            )
            self._on_type_changed(self._type_combo.currentIndex())
        except Exception as e:
            logger.error(f"Error saving modal factor: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    # ── Band Amount edit dialog ────────────────────────────────────────

    def _edit_band_amount_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a band amount entry.
        
        existing: [plancode, band_str, min_face_amt_str] or None.
        """
        is_new = existing is None
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Band Amount" if is_new else "Edit Band Amount")
        dlg.setMinimumWidth(380)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        LBL = f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;"
        INPUT = (
            f"QLineEdit {{ border: 2px solid {CRIMSON_PRIMARY}; border-radius: 4px;"
            f" padding: 6px 8px; font-size: 12px; color: {GRAY_DARK}; }}"
            f"QLineEdit:focus {{ border-color: {SLATE_PRIMARY}; background: #FFFEF5; }}"
        )

        # Plancode
        lbl_pc = QLabel("Plancode:")
        lbl_pc.setStyleSheet(LBL)
        grid.addWidget(lbl_pc, 0, 0)
        inp_pc = QLineEdit()
        inp_pc.setStyleSheet(INPUT)
        inp_pc.setPlaceholderText("e.g. B75TL400")
        if existing:
            inp_pc.setText(existing[0])
        grid.addWidget(inp_pc, 0, 1)

        # Band
        lbl_band = QLabel("Band:")
        lbl_band.setStyleSheet(LBL)
        grid.addWidget(lbl_band, 1, 0)
        inp_band = QLineEdit()
        inp_band.setStyleSheet(INPUT)
        inp_band.setPlaceholderText("1-5")
        if existing:
            inp_band.setText(existing[1])
        grid.addWidget(inp_band, 1, 1)

        # Min Face Amount
        lbl_amt = QLabel("Min Face Amount ($):")
        lbl_amt.setStyleSheet(LBL)
        grid.addWidget(lbl_amt, 2, 0)
        inp_amt = QLineEdit()
        inp_amt.setStyleSheet(INPUT)
        inp_amt.setPlaceholderText("e.g. 100000")
        if existing:
            inp_amt.setText(existing[2].replace(",", ""))
        grid.addWidget(inp_amt, 2, 1)

        layout.addLayout(grid)

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

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        plancode = inp_pc.text().strip().upper()
        if not plancode:
            QMessageBox.warning(self, "Validation", "Plancode is required.")
            return
        try:
            band = int(inp_band.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Band must be an integer.")
            return
        try:
            amt = float(inp_amt.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Min Face Amount must be a number.")
            return

        try:
            db = get_abr_database()
            conn = db.connect()
            cursor = conn.cursor()
            if existing:
                old_pc = existing[0].upper()
                old_band = int(existing[1])
                if plancode != old_pc or band != old_band:
                    cursor.execute(
                        "DELETE FROM [SV_ABR_BAND_AMOUNTS] "
                        "WHERE plancode = ? AND band = ?",
                        (old_pc, old_band),
                    )
            cursor.execute(
                "DELETE FROM [SV_ABR_BAND_AMOUNTS] WHERE plancode = ? AND band = ?",
                (plancode, band),
            )
            cursor.execute(
                "INSERT INTO [SV_ABR_BAND_AMOUNTS] "
                "(plancode, band, min_face_amt) VALUES (?, ?, ?)",
                (plancode, band, amt),
            )
            conn.commit()
            cursor.close()
            self._status_label.setText(
                f"{'Added' if is_new else 'Updated'} band amount for {plancode} band {band}."
            )
            self._on_type_changed(self._type_combo.currentIndex())
        except Exception as e:
            logger.error(f"Error saving band amount: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    # ── Policy Fee edit dialog ─────────────────────────────────────────

    def _edit_policy_fee_dialog(self, existing: Optional[list]):
        """Open a dialog to add or edit a policy fee entry.

        existing: [plancode, annual_fee_str] or None for new.
        """
        is_new = existing is None
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Policy Fee" if is_new else "Edit Policy Fee")
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        LBL = f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 12px;"
        INPUT = (
            f"QLineEdit {{ border: 2px solid {CRIMSON_PRIMARY}; border-radius: 4px;"
            f" padding: 6px 8px; font-size: 12px; color: {GRAY_DARK}; }}"
            f"QLineEdit:focus {{ border-color: {SLATE_PRIMARY}; background: #FFFEF5; }}"
        )

        lbl_pc = QLabel("Plancode:")
        lbl_pc.setStyleSheet(LBL)
        grid.addWidget(lbl_pc, 0, 0)
        inp_pc = QLineEdit()
        inp_pc.setStyleSheet(INPUT)
        inp_pc.setPlaceholderText("e.g. B75TL400")
        if existing:
            inp_pc.setText(existing[0])
        grid.addWidget(inp_pc, 0, 1)

        lbl_fee = QLabel("Annual Fee ($):")
        lbl_fee.setStyleSheet(LBL)
        grid.addWidget(lbl_fee, 1, 0)
        inp_fee = QLineEdit()
        inp_fee.setStyleSheet(INPUT)
        inp_fee.setPlaceholderText("e.g. 60.0")
        if existing:
            inp_fee.setText(existing[1].replace(",", ""))
        grid.addWidget(inp_fee, 1, 1)

        layout.addLayout(grid)

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

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        plancode = inp_pc.text().strip().upper()
        if not plancode:
            QMessageBox.warning(self, "Validation", "Plancode is required.")
            return
        try:
            fee = float(inp_fee.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Validation", "Annual Fee must be a number.")
            return

        try:
            db = get_abr_database()
            conn = db.connect()
            cursor = conn.cursor()
            if existing and plancode != existing[0].upper():
                cursor.execute(
                    "DELETE FROM [SV_ABR_POLICY_FEES] WHERE plancode = ?", (existing[0],)
                )
            cursor.execute("DELETE FROM [SV_ABR_POLICY_FEES] WHERE plancode = ?", (plancode,))
            cursor.execute(
                "INSERT INTO [SV_ABR_POLICY_FEES] (plancode, annual_fee) VALUES (?, ?)",
                (plancode, fee),
            )
            conn.commit()
            cursor.close()
            self._status_label.setText(f"{'Added' if is_new else 'Updated'} policy fee for {plancode}.")
            self._on_type_changed(self._type_combo.currentIndex())
        except Exception as e:
            logger.error(f"Error saving policy fee: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
