"""Small Qt signal helpers shared by SuiteView UI modules."""

from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def muted_signals(*widgets):
    """Temporarily block signals and restore each widget's prior state."""

    states = [(widget, widget.blockSignals(True)) for widget in widgets if widget is not None]
    try:
        yield
    finally:
        for widget, was_blocked in reversed(states):
            widget.blockSignals(was_blocked)
