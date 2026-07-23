"""App-wide (not per-policy/per-case) Illustration preferences.

These settings apply across the whole Illustration application — every policy,
every case, every inputs tab share one instance. Access it through
``get_illustration_settings()`` so the same object (and its change signals) is
seen everywhere.

Session-only: defaults are restored each time the app starts.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class IllustrationSettings(QObject):
    """Global Illustration toggles that every widget observes."""

    # Emitted whenever the "Additional Premium Types" option flips. Widgets
    # that vary their contents by this option (the Premium Type dropdowns)
    # connect to this and re-sync.
    additional_premium_types_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._additional_premium_types = False

    @property
    def additional_premium_types(self) -> bool:
        """When True, the advanced Premium Types (Billable to MD, Max Level,
        Monthly Deduction, Prem to Shadow Maturity) are offered in the Premium
        Type dropdown. Off by default — the dropdown then shows only INPUT,
        Billable Prem, Prem to Maturity, and Solve."""
        return self._additional_premium_types

    def set_additional_premium_types(self, enabled: bool):
        enabled = bool(enabled)
        if enabled == self._additional_premium_types:
            return
        self._additional_premium_types = enabled
        self.additional_premium_types_changed.emit(enabled)


_settings: IllustrationSettings | None = None


def get_illustration_settings() -> IllustrationSettings:
    """Return the process-wide Illustration settings singleton."""
    global _settings
    if _settings is None:
        _settings = IllustrationSettings()
    return _settings
