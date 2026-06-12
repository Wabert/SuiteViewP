"""
Build-mode colors — the single source of truth (DATAFORGE_DESIGN §8).

Every query item is color-coded by HOW it was built, everywhere it appears:
the Query Object browser, the build-mode selector dropdown, and (eventually)
the builder chrome. One color per build mode; DataForge orange is reserved
for Forges and never used by a build mode. Jewel-tone, saturated, slightly
formal — "enterprise, but crafted".
"""
from __future__ import annotations

from dataclasses import dataclass

from suiteview.audit.query_object import (
    OBJECT_KIND_ADHOC_SOURCE,
    OBJECT_KIND_CYBERLIFE,
    OBJECT_KIND_EXECUTABLE,
    OBJECT_KIND_MANUAL_SQL,
    OBJECT_KIND_VISUAL,
)


@dataclass(frozen=True)
class ModeStyle:
    """Color identity for one build mode."""
    label: str   # user-facing mode name
    color: str   # the mode's identity color (chips, text accents, borders)
    tint: str    # pale background tint of the same hue (item rows, menu rows)


MODE_STYLES: dict[str, ModeStyle] = {
    OBJECT_KIND_CYBERLIFE: ModeStyle("Cyberlife", "#1E5BA8", "#E3ECF7"),
    OBJECT_KIND_VISUAL: ModeStyle("Visual Query", "#2E7D32", "#E6F3E6"),
    OBJECT_KIND_MANUAL_SQL: ModeStyle("Manual SQL", "#5A3218", "#F4E9DC"),
    OBJECT_KIND_ADHOC_SOURCE: ModeStyle("File Source", "#B58900", "#FFF4C2"),
    OBJECT_KIND_EXECUTABLE: ModeStyle("Executable", "#374151", "#E5E7EB"),
}

_DEFAULT_STYLE = ModeStyle("Query", "#475569", "#E8ECF1")

# Reserved for DataForge — heavier than any query/group (design §8).
FORGE_STYLE = ModeStyle("DataForge", "#C2410C", "#FFEDD5")

# Query Groups: neutral but weighty — bold rows with a warm gray fill, so
# structure reads from weight and origin reads from the mode colors.
GROUP_STYLE = ModeStyle("Group", "#3F3F46", "#ECEAE6")

# The audit window's build-mode keys ("cyberlife"/"visual"/"manual_sql"/
# "file") map onto the same identities as the object kinds they produce.
BUILD_MODE_TO_KIND = {
    "cyberlife": OBJECT_KIND_CYBERLIFE,
    "visual": OBJECT_KIND_VISUAL,
    "manual_sql": OBJECT_KIND_MANUAL_SQL,
    "file": OBJECT_KIND_ADHOC_SOURCE,
}


def mode_style(kind: str) -> ModeStyle:
    """The ModeStyle for a QueryObject kind (or a sane default)."""
    return MODE_STYLES.get(kind, _DEFAULT_STYLE)


def build_mode_style(build_mode: str) -> ModeStyle:
    """The ModeStyle for an audit-window build-mode key."""
    return mode_style(BUILD_MODE_TO_KIND.get(build_mode, ""))


_MODE_ICONS: dict[str, object] = {}


def mode_icon(color: str):
    """A small rounded color chip (QIcon) — the mode's identity mark.

    Shared by the browser tree and the build-mode selector so the same
    color/pattern means the same thing everywhere.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

    icon = _MODE_ICONS.get(color)
    if icon is None:
        pm = QPixmap(10, 10)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 10, 10, 2.0, 2.0)
        painter.end()
        icon = QIcon(pm)
        _MODE_ICONS[color] = icon
    return icon
