"""Shared UI helpers."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator


@contextmanager
def muted_signals(*widgets) -> Iterator[None]:
    """Temporarily block Qt signals and restore each widget's prior state."""
    previous = []
    for widget in widgets:
        if widget is None:
            continue
        previous.append((widget, widget.blockSignals(True)))
    try:
        yield
    finally:
        for widget, was_blocked in reversed(previous):
            widget.blockSignals(was_blocked)