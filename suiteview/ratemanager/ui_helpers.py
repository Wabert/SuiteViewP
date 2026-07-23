"""Shared Rate Manager widget-state helpers."""

from __future__ import annotations

from PyQt6.QtWidgets import QLineEdit, QWidget


def update_cease_age_field(
    include_checked: bool,
    renewable: bool,
    has_rates: bool,
    edit: QLineEdit,
) -> None:
    """Show whether a cease age is required while preserving entered values."""
    required = include_checked and not renewable and has_rates
    was_required = bool(edit.property("cease_required"))

    if required:
        saved_value = edit.property("cease_value") or ""
        if not was_required:
            edit.setText(str(saved_value))
        edit.setEnabled(True)
        edit.setPlaceholderText("Required")
    else:
        if was_required and edit.text().strip():
            edit.setProperty("cease_value", edit.text().strip())
        edit.setText("Not required")
        edit.setEnabled(False)

    edit.setProperty("cease_required", required)


def set_expanding_panel_visible(
    owner: QWidget,
    panel: QWidget,
    visible: bool,
) -> None:
    """Show a bottom panel by growing its top-level window when possible."""
    if panel.isVisible() == visible:
        return

    window = owner.window()
    spacing = owner.layout().spacing() if owner.layout() is not None else 0
    delta = panel.height() + max(spacing, 0)

    if visible:
        growth = 0
        upward_shift = 0
        if not window.isMaximized():
            geometry = window.geometry()
            available = window.screen().availableGeometry()
            new_height = min(geometry.height() + delta, available.height())
            growth = new_height - geometry.height()
            new_y = max(
                available.top(),
                min(geometry.y(), available.bottom() - new_height + 1),
            )
            upward_shift = geometry.y() - new_y
            window.setGeometry(
                geometry.x(), new_y, geometry.width(), new_height)
        owner.setProperty("expanding_panel_growth", growth)
        owner.setProperty("expanding_panel_shift", upward_shift)
        panel.setVisible(True)
        return

    panel.setVisible(False)
    if window.isMaximized():
        return

    growth = int(owner.property("expanding_panel_growth") or 0)
    upward_shift = int(owner.property("expanding_panel_shift") or 0)
    if growth or upward_shift:
        geometry = window.geometry()
        window.setGeometry(
            geometry.x(),
            geometry.y() + upward_shift,
            geometry.width(),
            max(window.minimumHeight(), geometry.height() - growth),
        )
    owner.setProperty("expanding_panel_growth", 0)
    owner.setProperty("expanding_panel_shift", 0)
