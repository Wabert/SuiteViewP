"""
ABR Quote — Resources dialog.

Two-panel layout: left navigation list, right detail/text panel.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QTextEdit,
    QLabel, QSplitter, QWidget,
)

from .abr_styles import (
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_RICH, CRIMSON_BG,
    SLATE_PRIMARY, SLATE_LIGHT, WHITE, GRAY_DARK, GRAY_TEXT,
)

# ── Resource content ────────────────────────────────────────────────
_RESOURCES: dict[str, str] = {
    "Explanation of Benefit": (
        "Benefit is equal to the present value of future benefits "
        "less the present value of future payments."
    ),
    "Explanation of Interest Rate": (
        "The Moody's Ave Yield market index rate is used in the "
        "ABR calculation."
    ),
}

_NAV_ITEMS = list(_RESOURCES.keys())


class ResourcesDialog(QDialog):
    """Two-panel resources reference dialog for ABR Quote."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ABR Quote — Resources")
        self.setMinimumSize(620, 340)
        self.resize(680, 380)
        self._build_ui()
        # Select first item by default
        self._nav_list.setCurrentRow(0)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # ── Left navigation panel ───────────────────────────────────
        nav_widget = QWidget()
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(8, 8, 4, 8)
        nav_layout.setSpacing(4)

        nav_header = QLabel("Topics")
        nav_header.setStyleSheet(f"""
            font-size: 13px;
            font-weight: bold;
            color: {WHITE};
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
            border-radius: 4px;
            padding: 6px 10px;
        """)
        nav_layout.addWidget(nav_header)

        self._nav_list = QListWidget()
        self._nav_list.addItems(_NAV_ITEMS)
        self._nav_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {WHITE};
                border: 1px solid {SLATE_PRIMARY};
                border-radius: 4px;
                font-size: 12px;
                color: {GRAY_DARK};
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 10px;
            }}
            QListWidget::item:selected {{
                background-color: {CRIMSON_PRIMARY};
                color: {WHITE};
                border-radius: 3px;
            }}
            QListWidget::item:hover:!selected {{
                background-color: {SLATE_LIGHT};
            }}
        """)
        self._nav_list.currentRowChanged.connect(self._on_topic_changed)
        nav_layout.addWidget(self._nav_list)

        nav_widget.setStyleSheet(f"background-color: {CRIMSON_BG};")

        # ── Right detail panel ──────────────────────────────────────
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(4, 8, 8, 8)
        detail_layout.setSpacing(4)

        self._detail_header = QLabel()
        self._detail_header.setStyleSheet(f"""
            font-size: 13px;
            font-weight: bold;
            color: {CRIMSON_DARK};
            padding: 6px 10px;
        """)
        detail_layout.addWidget(self._detail_header)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {WHITE};
                border: 1px solid {SLATE_PRIMARY};
                border-radius: 4px;
                font-size: 12px;
                color: {GRAY_DARK};
                padding: 10px;
            }}
        """)
        detail_layout.addWidget(self._detail_text)

        detail_widget.setStyleSheet(f"background-color: {CRIMSON_BG};")

        # ── Assemble splitter ───────────────────────────────────────
        splitter.addWidget(nav_widget)
        splitter.addWidget(detail_widget)
        splitter.setStretchFactor(0, 1)   # nav: 1 part
        splitter.setStretchFactor(1, 2)   # detail: 2 parts
        splitter.setSizes([220, 460])

        layout.addWidget(splitter)

    def _on_topic_changed(self, row: int):
        if row < 0:
            return
        title = _NAV_ITEMS[row]
        self._detail_header.setText(title)
        self._detail_text.setPlainText(_RESOURCES[title])
