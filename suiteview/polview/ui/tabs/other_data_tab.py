"""Embedded, policy-scoped viewers for supplemental data sources."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ..styles import GREEN_DARK, GREEN_PRIMARY, GREEN_SUBTLE, WHITE
from .claims_tab import ClaimsTab
from .cyberlife_pdf_tab import CyberlifePdfTab
from .orion_pcr_tab import OrionPcrTab
from .sap_tab import SapTab
from .tai_fd_tab import TaiFdTab

if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


class OtherDataTab(QWidget):
    """Keep source selection, inputs and results inside one permanent tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: PolicyInformation | None = None
        self._opened: set[str] = set()
        self._selected: str | None = None
        self.setStyleSheet(f"background-color: {WHITE};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        self.nav_panel = QWidget()
        self.nav_panel.setObjectName("OtherDataNavPanel")
        self.nav_panel.setStyleSheet(f"""
            QWidget#OtherDataNavPanel {{
                background: {GREEN_SUBTLE};
                border: 2px solid {GREEN_PRIMARY};
                border-radius: 8px;
            }}
            QPushButton {{
                background: {WHITE}; color: {GREEN_DARK};
                border: 1px solid {GREEN_SUBTLE}; border-radius: 4px;
                padding: 4px 6px; font-size: 11px; min-height: 20px;
            }}
            QPushButton:hover {{ border-color: {GREEN_PRIMARY}; }}
            QPushButton:checked {{
                background: {GREEN_PRIMARY}; color: {WHITE};
                border-color: {GREEN_DARK};
            }}
        """)
        nav = QVBoxLayout(self.nav_panel)
        nav.setContentsMargins(8, 8, 8, 8)
        nav.setSpacing(7)
        self.button_group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        self.stack = QStackedWidget()
        self.empty_page = QLabel("Select a data source on the left.")
        self.empty_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_page.setStyleSheet(f"color: {GREEN_DARK};")
        self.stack.addWidget(self.empty_page)
        self.pages = {
            "SAP": SapTab(),
            "CLAIMSFILE": ClaimsTab(),
            "TAICyberTAIFd": TaiFdTab(),
            "orion_pcr3_r": OrionPcrTab(),
            "CYBERLIFE_PDF": CyberlifePdfTab(),
        }
        for index, (title, page) in enumerate(self.pages.items()):
            self.stack.addWidget(page)
            button = QPushButton(title)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.button_group.addButton(button, index)
            self.buttons[title] = button
            nav.addWidget(button)
        self.button_group.idClicked.connect(self._on_source_clicked)
        nav.addStretch(1)
        self.nav_panel.setFixedWidth(max(138, self.nav_panel.sizeHint().width()))
        layout.addWidget(self.nav_panel)
        layout.addWidget(self.stack, 1)

    def _on_source_clicked(self, index: int):
        self.select_source(tuple(self.pages)[index])

    def select_source(self, title: str):
        page = self.pages[title]
        self._selected = title
        self.buttons[title].setChecked(True)
        self.stack.setCurrentWidget(page)
        if title not in self._opened:
            self._opened.add(title)
            page.load_policy(self._policy)

    def reset(self, policy: "PolicyInformation | None" = None):
        self._policy = policy
        self._opened.clear()
        self._selected = None
        self.stack.setCurrentWidget(self.empty_page)
        self.button_group.setExclusive(False)
        for button in self.buttons.values():
            button.setChecked(False)
        self.button_group.setExclusive(True)
        for page in self.pages.values():
            page.reset()

    def export_state(self) -> dict:
        return {
            "selected": self._selected,
            "pages": {title: self.pages[title].export_state() for title in self._opened},
        }

    def restore_state(self, policy: "PolicyInformation | None", state: dict):
        self.reset(policy)
        for title, saved in state.get("pages", {}).items():
            self.pages[title].restore_state(policy, saved)
            self._opened.add(title)
        selected = state.get("selected")
        if selected is not None:
            self.select_source(selected)
