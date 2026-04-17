"""
FieldPickerWindow -- dockable tool window for the Field Picker panel.

Docks to the right edge of the AuditWindow.  Drag the header to undock;
double-click the header to re-dock.  Re-uses the existing FieldPickerPanel
inside a DockableToolPanel frame.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

from suiteview.ui.widgets.dockable_tool_panel import DockableToolPanel
from .field_picker_panel import FieldPickerPanel

# ── Theme colours (Audit blue/gold) ──────────────────────────────
_BLUE_RICH = "#1E5BA8"
_BLUE_GRADIENT_TOP = "#2A6BC4"
_BLUE_GRADIENT_BOT = "#14407A"
_BLUE_DARK = "#0A2A5C"
_GOLD_PRIMARY = "#D4A017"
_GOLD_TEXT = "#FFD54F"
_BODY_BG = "#F0F0F0"


class FieldPickerWindow(DockableToolPanel):
    """
    Dockable Field Picker window that sits to the right of the Audit window.

    Signals
    -------
    field_requested(table, column, type_name, display)
        Emitted when the user double-clicks a field.
    closed
        Emitted when the user closes the panel (so the parent can
        update its toggle button).
    """

    field_requested = pyqtSignal(str, str, str, str)
    closed = pyqtSignal()

    def __init__(self, parent_window: QWidget):
        # The inner panel is created before super().__init__ calls
        # build_header / build_body, so it's available when needed.
        self._picker = FieldPickerPanel()

        super().__init__(
            parent_window,
            default_width=280,
            min_width=180,
            min_height=300,
            border_color=_GOLD_PRIMARY,
            bg_color=_BODY_BG,
            corner_radius=8.0,
        )

        # Connect after super().__init__() so pyqtSignals are bound
        self._picker.field_requested.connect(self.field_requested)

    # -- DockableToolPanel overrides ----------------------------------------

    def build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("fieldPickerHeader")
        header.setFixedHeight(32)
        header.setStyleSheet(f"""
            QWidget#fieldPickerHeader {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {_BLUE_GRADIENT_TOP}, stop:0.5 {_BLUE_RICH},
                    stop:1 {_BLUE_GRADIENT_BOT});
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom: 2px solid {_GOLD_PRIMARY};
            }}
            QLabel {{
                color: {_GOLD_TEXT};
                font-size: 11px;
                font-weight: bold;
                background: transparent;
            }}
            QPushButton {{
                background: transparent;
                color: {_GOLD_TEXT};
                border: 1px solid {_GOLD_PRIMARY};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: bold;
                min-width: 20px;
            }}
            QPushButton:hover {{
                background-color: {_GOLD_PRIMARY};
                color: {_BLUE_DARK};
            }}
        """)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.setSpacing(8)

        title = QLabel("Field Picker")
        lay.addWidget(title)
        lay.addStretch()

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(24, 20)
        close_btn.clicked.connect(self.on_closed)
        lay.addWidget(close_btn)

        return header

    def build_body(self) -> QWidget:
        # Remove min/max width constraints -- the dockable frame handles sizing
        self._picker.setMinimumWidth(0)
        self._picker.setMaximumWidth(16777215)
        return self._picker

    # -- Close hook ----------------------------------------------------------

    def on_closed(self):
        self.hide()
        self.closed.emit()

    # -- Delegate to inner panel --------------------------------------------

    def set_group(self, dsn: str, tables: list[str],
                  display_names: dict[str, str]):
        self._picker.set_group(dsn, tables, display_names)

    def clear(self):
        self._picker.clear()

    def get_state(self) -> dict:
        return self._picker.get_state()

    def set_state(self, state: dict):
        self._picker.set_state(state)
