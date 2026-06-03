"""Illustration-themed policy list panel."""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget

from suiteview.core.db2_constants import REGIONS
from suiteview.polview.ui.tabs.policy_list_tab import PolicyListWindow

from .styles import GOLD_PRIMARY, GOLD_TEXT, PURPLE_BG, PURPLE_DARK, PURPLE_LIGHT, PURPLE_PRIMARY, PURPLE_RICH, PURPLE_SUBTLE, WHITE


class IllustrationPolicyListWindow(PolicyListWindow):
    """Policy list with Illustration purple/gold styling."""

    def __init__(self, parent_window=None):
        super().__init__(parent_window)
        self._bg_color = PURPLE_PRIMARY
        self._frame.setStyleSheet(f"""
            QFrame {{
                background: {PURPLE_PRIMARY};
                border: none;
                border-radius: 8px;
            }}
        """)

    def build_header(self):
        header = QWidget()
        header.setObjectName("policyListHeader")
        header.setFixedHeight(36)
        header.setStyleSheet(f"""
            QWidget#policyListHeader {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {PURPLE_LIGHT}, stop:0.5 {PURPLE_RICH}, stop:1 {PURPLE_DARK});
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-bottom: 2px solid {GOLD_PRIMARY};
            }}
            QLabel {{
                color: {GOLD_TEXT};
                font-size: 12px;
                font-weight: bold;
                background: transparent;
            }}
            QPushButton {{
                background: transparent;
                color: {GOLD_TEXT};
                border: 1px solid {GOLD_PRIMARY};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: bold;
                min-width: 20px;
            }}
            QPushButton:hover {{
                background-color: {GOLD_PRIMARY};
                color: {PURPLE_DARK};
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(8)

        title_label = QLabel("Policy List")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(24, 20)
        close_btn.clicked.connect(self.on_closed)
        header_layout.addWidget(close_btn)

        return header

    def build_body(self):
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        content = QWidget()
        content.setStyleSheet(f"background-color: {PURPLE_BG};")
        inner_layout = QVBoxLayout(content)
        inner_layout.setContentsMargins(8, 8, 8, 8)
        inner_layout.setSpacing(6)

        form_widget = QWidget()
        form_widget.setStyleSheet(f"""
            QLabel {{
                font-size: 10px;
                color: {PURPLE_DARK};
                font-weight: bold;
                background: transparent;
            }}
            QLineEdit {{
                border: 1px solid {PURPLE_PRIMARY};
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
                background-color: {WHITE};
            }}
            QComboBox {{
                border: 1px solid {PURPLE_PRIMARY};
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
                background-color: {WHITE};
            }}
            QPushButton {{
                background-color: {PURPLE_PRIMARY};
                color: {GOLD_TEXT};
                border: 1px solid {GOLD_PRIMARY};
                border-radius: 3px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: {PURPLE_RICH};
            }}
        """)
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(4)

        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        self.region_combo = QComboBox()
        self.region_combo.addItems(REGIONS)
        self.region_combo.setCurrentText("CKPR")
        self.region_combo.setFixedWidth(65)
        input_row.addWidget(self.region_combo)

        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText("Co")
        self.company_input.setText("01")
        self.company_input.setFixedWidth(30)
        input_row.addWidget(self.company_input)

        self.policy_input = QLineEdit()
        self.policy_input.setPlaceholderText("Policy #")
        self.policy_input.returnPressed.connect(self._add_to_history)
        input_row.addWidget(self.policy_input)

        form_layout.addLayout(input_row)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_to_history)
        form_layout.addWidget(add_btn)

        inner_layout.addWidget(form_widget)

        self.history_list = QListWidget()
        self.history_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {WHITE};
                border: 1px solid {PURPLE_PRIMARY};
                border-radius: 3px;
                font-family: 'Segoe UI';
                font-size: 9pt;
            }}
            QListWidget::item {{
                padding: 0px 4px;
                margin: 0px;
                border-bottom: none;
                min-height: 18px;
                max-height: 18px;
            }}
            QListWidget::item:selected {{
                background-color: #FFE8A3;
                color: {PURPLE_DARK};
            }}
            QListWidget::item:hover {{
                background-color: {PURPLE_SUBTLE};
            }}
        """)
        self.history_list.setSpacing(0)
        self.history_list.setUniformItemSizes(True)
        self.history_list.setIconSize(QSize(0, 0))
        self.history_list.itemClicked.connect(self._on_item_clicked)
        self.history_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self._show_context_menu)
        inner_layout.addWidget(self.history_list)

        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {PURPLE_DARK};
                border: 1px solid {PURPLE_PRIMARY};
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 9px;
                font-weight: bold;
                max-height: 18px;
            }}
            QPushButton:hover {{
                background-color: {PURPLE_PRIMARY};
                color: {GOLD_TEXT};
            }}
        """)
        self.clear_all_btn.clicked.connect(self._clear_all)
        inner_layout.addWidget(self.clear_all_btn)

        body_layout.addWidget(content)

        footer = QWidget()
        footer.setObjectName("policyListFooter")
        footer.setFixedHeight(22)
        footer.setStyleSheet(f"""
            QWidget#policyListFooter {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {PURPLE_LIGHT}, stop:0.5 {PURPLE_RICH}, stop:1 {PURPLE_DARK});
                border-top: 2px solid {GOLD_PRIMARY};
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
        """)
        body_layout.addWidget(footer)

        return body
