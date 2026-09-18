"""Shared widget-state helpers for Audit query forms."""
from __future__ import annotations

# ── Generic widget state helpers ──────────────────────────────────────

def get_lineedit_text(widget) -> str:
    return widget.text()


def get_checkbox_checked(widget) -> bool:
    return widget.isChecked()


def get_combo_text(widget) -> str:
    return widget.currentText()


def get_listbox_selected(widget) -> list[str]:
    """Return texts of selected items in a QListWidget."""
    return [
        widget.item(i).text()
        for i in range(widget.count())
        if widget.item(i).isSelected()
    ]


def set_lineedit_text(widget, value: str):
    widget.setText(value or "")


def set_checkbox_checked(widget, value: bool):
    widget.setChecked(bool(value))


def set_combo_text(widget, value: str):
    idx = widget.findText(value or "")
    if idx >= 0:
        widget.setCurrentIndex(idx)
    else:
        widget.setCurrentIndex(0)


def set_listbox_selected(widget, values: list[str]):
    """Select items in a QListWidget whose text matches values."""
    widget.clearSelection()
    value_set = set(values) if values else set()
    for i in range(widget.count()):
        item = widget.item(i)
        item.setSelected(item.text() in value_set)


def get_groupbox_checked(widget) -> bool:
    """Get checked state of a checkable QGroupBox."""
    return widget.isChecked()


def set_groupbox_checked(widget, value: bool):
    """Set checked state of a checkable QGroupBox."""
    widget.setChecked(bool(value))
