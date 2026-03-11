"""
Audit Tool - Shared Panel Widgets
====================================
Reusable form widgets for criteria panels:
  - CheckableListBox: multi-select listbox (replaces VBA ListBox)
  - DateRangeRow: from/to date fields
  - NumericRangeRow: from/to numeric fields
  - CollapsibleSection: collapsible group box
  - CriteriaPanel: base class for all criteria panels
"""

from __future__ import annotations

from typing import Dict, List, Optional, Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QComboBox, QLineEdit, QCheckBox, QGroupBox,
    QListWidget, QListWidgetItem, QScrollArea, QFrame,
    QPushButton, QAbstractItemView, QSizePolicy,
    QToolButton, QSpacerItem,
)

from ..styles import BLUE_PRIMARY, BLUE_DARK, SILVER_LIGHT, SILVER_MID


# =============================================================================
# CheckableListBox — multi-select list matching VBA ListBox pattern
# =============================================================================
class CheckableListBox(QWidget):
    """
    Multi-select listbox with checkboxes and a toggle-all button.
    
    Maps code → display label. Selected items are returned as a list of codes.
    """
    selection_changed = pyqtSignal()

    def __init__(self, items: Dict[str, str], label: str = "",
                 max_height: int = 200, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header row with label + Select All / Clear buttons
        if label:
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(2)
            lbl = QLabel(label)
            lbl.setObjectName("SectionLabel")
            lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {BLUE_DARK};")
            header.addWidget(lbl)
            header.addStretch()
            select_all = QToolButton()
            select_all.setText("All")
            select_all.setToolTip("Select all")
            select_all.setFixedSize(28, 16)
            select_all.clicked.connect(self._select_all)
            header.addWidget(select_all)
            clear_btn = QToolButton()
            clear_btn.setText("∅")
            clear_btn.setToolTip("Clear selection")
            clear_btn.setFixedSize(28, 16)
            clear_btn.clicked.connect(self._clear_all)
            header.addWidget(clear_btn)
            layout.addLayout(header)

        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(max_height)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.list_widget.setSpacing(0)
        self.list_widget.setUniformItemSizes(True)
        self._items = items
        self._code_map: Dict[int, str] = {}  # row → code

        for i, (code, display) in enumerate(items.items()):
            item = QListWidgetItem(f"{code} — {display}" if display else code)
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.list_widget.addItem(item)
            self._code_map[i] = code

        self.list_widget.itemSelectionChanged.connect(self.selection_changed.emit)
        layout.addWidget(self.list_widget)

    def selected_codes(self) -> List[str]:
        """Return list of selected codes."""
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list_widget.selectedItems()
        ]

    def set_selected_codes(self, codes: List[str]):
        """Select items matching the given codes."""
        self.list_widget.blockSignals(True)
        self.list_widget.clearSelection()
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.data(Qt.ItemDataRole.UserRole) in codes:
                item.setSelected(True)
        self.list_widget.blockSignals(False)

    def clear_selection(self):
        """Clear all selections."""
        self.list_widget.clearSelection()

    def _select_all(self):
        self.list_widget.selectAll()

    def _clear_all(self):
        self.list_widget.clearSelection()


# =============================================================================
# DateRangeRow — paired From / To date inputs
# =============================================================================
class DateRangeRow(QWidget):
    """Two date fields (From / To) in a horizontal row."""

    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if label:
            lbl = QLabel(label)
            lbl.setFixedWidth(110)
            layout.addWidget(lbl)

        self.from_edit = QLineEdit()
        self.from_edit.setPlaceholderText("yyyy-mm-dd")
        self.from_edit.setMaximumWidth(100)
        layout.addWidget(QLabel("From:"))
        layout.addWidget(self.from_edit)

        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("yyyy-mm-dd")
        self.to_edit.setMaximumWidth(100)
        layout.addWidget(QLabel("To:"))
        layout.addWidget(self.to_edit)

        layout.addStretch()

    def get_range(self):
        """Return (low, high) as strings."""
        return self.from_edit.text().strip(), self.to_edit.text().strip()

    def set_range(self, low: str, high: str):
        self.from_edit.setText(low)
        self.to_edit.setText(high)

    def clear(self):
        self.from_edit.clear()
        self.to_edit.clear()


# =============================================================================
# NumericRangeRow — paired From / To numeric inputs
# =============================================================================
class NumericRangeRow(QWidget):
    """Two numeric fields (Low / High) in a horizontal row."""

    def __init__(self, label: str = "", suffix: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if label:
            lbl = QLabel(label)
            lbl.setFixedWidth(110)
            layout.addWidget(lbl)

        self.low_edit = QLineEdit()
        self.low_edit.setPlaceholderText("Min")
        self.low_edit.setMaximumWidth(80)
        layout.addWidget(self.low_edit)

        layout.addWidget(QLabel("–"))

        self.high_edit = QLineEdit()
        self.high_edit.setPlaceholderText("Max")
        self.high_edit.setMaximumWidth(80)
        layout.addWidget(self.high_edit)

        if suffix:
            layout.addWidget(QLabel(suffix))

        layout.addStretch()

    def get_range(self):
        """Return (low, high) as strings."""
        return self.low_edit.text().strip(), self.high_edit.text().strip()

    def set_range(self, low: str, high: str):
        self.low_edit.setText(low)
        self.high_edit.setText(high)

    def clear(self):
        self.low_edit.clear()
        self.high_edit.clear()


# =============================================================================
# SingleValueRow — label + single input field
# =============================================================================
class SingleValueRow(QWidget):
    """Label + single text input."""

    def __init__(self, label: str, placeholder: str = "", width: int = 100, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        lbl = QLabel(label)
        lbl.setFixedWidth(110)
        layout.addWidget(lbl)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setMaximumWidth(width)
        layout.addWidget(self.edit)
        layout.addStretch()

    def value(self) -> str:
        return self.edit.text().strip()

    def set_value(self, val: str):
        self.edit.setText(val)

    def clear(self):
        self.edit.clear()


# =============================================================================
# CollapsibleSection — group box (always expanded, checkbox enables/disables)
# =============================================================================
class CollapsibleSection(QGroupBox):
    """
    QGroupBox with a checkbox that enables/disables its content area.

    Content is ALWAYS visible (power-user layout). The checkbox only
    toggles the enabled state of child widgets — nothing is ever hidden.
    The ``initially_open`` parameter controls whether the section starts
    enabled (checked) or disabled (unchecked).
    """

    def __init__(self, title: str, parent=None, initially_open: bool = True):
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(initially_open)
        self.toggled.connect(self._on_toggle)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 2, 4, 2)
        self._content_layout.setSpacing(2)

        main = QVBoxLayout(self)
        main.setContentsMargins(4, 4, 4, 4)
        main.addWidget(self._content)

        # Always visible — just set enabled state
        self._content.setEnabled(initially_open)

    def _on_toggle(self, checked: bool):
        """Enable/disable content — never hide."""
        self._content.setEnabled(checked)

    def content_layout(self) -> QVBoxLayout:
        """Return the layout to add widgets into."""
        return self._content_layout

    def add_widget(self, widget):
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        self._content_layout.addLayout(layout)


# =============================================================================
# StyledFormGroup — PolView-style blue/gold group box for audit panels
# =============================================================================
class StyledFormGroup(QGroupBox):
    """
    Styled form group matching PolView's StyledInfoTableGroup visual pattern.
    Blue-bordered rounded box with gold-on-blue title badge.
    All fields are always visible (no collapsing).
    Supports multi-column grid layout.
    """

    def __init__(self, title: str, columns: int = 1, parent=None):
        super().__init__(title, parent)
        from ..styles import STYLED_FORM_GROUP_CSS
        self.setStyleSheet(STYLED_FORM_GROUP_CSS)
        self._columns = columns
        self._grid = QGridLayout()
        self._grid.setContentsMargins(8, 8, 8, 6)
        self._grid.setSpacing(4)
        self._grid.setVerticalSpacing(3)
        self._current_row = 0
        self._current_col = 0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 14, 4, 4)
        outer.addLayout(self._grid)
        outer.addStretch()

    def add_widget(self, widget, col_span: int = 1):
        """Add a widget at the next grid position."""
        self._grid.addWidget(widget, self._current_row, self._current_col,
                             1, col_span)
        self._current_col += col_span
        if self._current_col >= self._columns:
            self._current_col = 0
            self._current_row += 1

    def add_row(self, *widgets):
        """Add multiple widgets across one row (one per column)."""
        for i, w in enumerate(widgets):
            if w is not None:
                self._grid.addWidget(w, self._current_row, i)
        self._current_row += 1
        self._current_col = 0

    def add_widget_at(self, widget, row: int, col: int,
                      row_span: int = 1, col_span: int = 1):
        """Add a widget at an exact grid position."""
        self._grid.addWidget(widget, row, col, row_span, col_span)
        # Update tracking so subsequent add_widget calls don't overlap
        if row >= self._current_row:
            self._current_row = row + row_span
            self._current_col = 0

    def next_row(self):
        """Move to the next row."""
        if self._current_col > 0:
            self._current_col = 0
            self._current_row += 1

    def grid(self) -> QGridLayout:
        """Direct access to the grid layout."""
        return self._grid


# =============================================================================
# CriteriaPanel — base class for all criteria tab panels
# =============================================================================
class CriteriaPanel(QScrollArea):
    """
    Base class for a criteria tab panel.
    
    Subclasses override _build_ui() to add form fields inside self.container.
    Must implement write_to_criteria(criteria) and reset(criteria).
    """

    def __init__(self, criteria, parent=None):
        super().__init__(parent)
        self.criteria = criteria
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.container = QWidget()
        self.container.setObjectName("CriteriaPanel")
        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(6)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._build_ui()

        self.main_layout.addStretch()
        self.setWidget(self.container)

    def _build_ui(self):
        """Override in subclasses to build form fields."""
        raise NotImplementedError

    def write_to_criteria(self, criteria):
        """Write panel state to criteria dataclass. Override in subclasses."""
        raise NotImplementedError

    def reset(self, criteria):
        """Reset panel to match new criteria state. Override in subclasses."""
        self.criteria = criteria


# =============================================================================
# Helper: make a combo from a dict
# =============================================================================
def make_combo(items: Dict[str, str], include_blank: bool = True,
               fixed_width: int = 200) -> QComboBox:
    """Create a QComboBox from a code→label dict."""
    combo = QComboBox()
    if include_blank:
        combo.addItem("", "")
    for code, label in items.items():
        combo.addItem(f"{code} — {label}" if label else code, code)
    combo.setFixedWidth(fixed_width)
    return combo


def make_form_row(label: str, widget: QWidget, label_width: int = 110) -> QHBoxLayout:
    """Create a horizontal label + widget row."""
    row = QHBoxLayout()
    row.setSpacing(4)
    lbl = QLabel(label)
    lbl.setFixedWidth(label_width)
    row.addWidget(lbl)
    row.addWidget(widget)
    row.addStretch()
    return row
