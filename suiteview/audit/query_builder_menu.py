"""Shared context-menu styling for Query Builder surfaces."""
from __future__ import annotations

from PyQt6.QtWidgets import QMenu, QWidget


QUERY_BUILDER_MENU_STYLE = (
    "QMenu { background-color: #EAF3FF; color: #0A2A5C;"
    " border: 1px solid #D4AF37; font-size: 9pt; }"
    "QMenu::item { padding: 4px 18px; background-color: transparent; }"
    "QMenu::item:selected { background-color: #C7DCF4; color: #0A2A5C; }"
    "QMenu::item:disabled { color: #6B7A90; }"
    "QMenu::separator { height: 1px; background: #D4AF37; margin: 3px 6px; }"
)


def apply_query_builder_menu_style(menu: QMenu) -> QMenu:
    menu.setStyleSheet(QUERY_BUILDER_MENU_STYLE)
    return menu


def query_builder_menu(parent: QWidget | None = None) -> QMenu:
    return apply_query_builder_menu_style(QMenu(parent))