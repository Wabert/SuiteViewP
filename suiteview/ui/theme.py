"""Shared theme utilities for SuiteView UI components.

This module centralizes stylesheet loading, exposes palette helpers,
and provides a small icon cache so widgets can request icons without
re-reading them from disk each time.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, Optional
import logging

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

THEME_DIR = Path(__file__).resolve().parent
STYLESHEET_PATH = THEME_DIR / "styles.qss"
ICON_DIR = THEME_DIR / "icons"
_SUPPORTED_ICON_EXTENSIONS = (".svg", ".png", ".ico", ".icns")

# Central palette definition. Keep it lightweight so other modules can
# reference the same values without hard-coded duplicates.
PALETTE: Dict[str, str] = {
    "blue_dark": "#0A1E5E",
    "blue_primary": "#1E3A8A",
    "blue_light": "#2563EB",
    "gold_primary": "#D4AF37",
    "gold_light": "#F4D03F",
    "gold_accent": "#FFD700",
    "panel_bg": "#E8F0FF",
    "text_dark": "#0A1E5E",
}


def get_palette() -> Dict[str, str]:
    """Return a copy of the theme palette mapping."""

    return dict(PALETTE)


@lru_cache(maxsize=1)
def load_stylesheet() -> str:
    """Load and cache the global QSS stylesheet content."""

    try:
        stylesheet = STYLESHEET_PATH.read_text(encoding="utf-8")
        logger.debug("Loaded stylesheet from %s", STYLESHEET_PATH)
        return stylesheet
    except FileNotFoundError:
        logger.warning("SuiteView stylesheet missing at %s", STYLESHEET_PATH)
    except OSError as exc:
        logger.error("Unable to read stylesheet %s: %s", STYLESHEET_PATH, exc)
    return ""


def apply_global_theme(app: QApplication) -> None:
    """Apply the shared stylesheet to the given QApplication."""

    stylesheet = load_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)
    else:
        logger.info("No stylesheet applied; content missing or empty")


def _refresh_widget(widget: QWidget) -> None:
    """Force Qt to re-polish a widget after metadata changes."""

    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def apply_panel_header(widget: QWidget) -> None:
    """Tag a widget to receive the standard panel header styling."""

    if widget.objectName() != "panel_header":
        widget.setObjectName("panel_header")
    _refresh_widget(widget)


_ICON_CACHE: Dict[str, QIcon] = {}


def _resolve_icon_path(name: str) -> Optional[Path]:
    """Return the best-match icon path for the requested name, if any."""

    candidate = ICON_DIR / name
    if candidate.suffix:
        return candidate if candidate.exists() else None

    for ext in _SUPPORTED_ICON_EXTENSIONS:
        extended = candidate.with_suffix(ext)
        if extended.exists():
            return extended
    return None


def get_icon(name: str, *, builder: Optional[Callable[[], QIcon]] = None) -> QIcon:
    """Return a cached icon.

    The search order is:
    1. Previously cached icons
    2. Icon files inside ``suiteview/ui/icons`` (name with or without extension)
    3. Optional ``builder`` callable to procedurally create the icon

    A null icon is returned if nothing can be produced, but the lookup
    result is still cached so repeated calls remain inexpensive.
    """

    if name in _ICON_CACHE:
        return _ICON_CACHE[name]

    icon_path = _resolve_icon_path(name)
    icon: Optional[QIcon] = None
    if icon_path is not None:
        icon = QIcon(str(icon_path))
        logger.debug("Loaded icon '%s' from %s", name, icon_path)

    if icon is None and builder is not None:
        try:
            icon = builder()
            logger.debug("Created icon '%s' via builder", name)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Icon builder for '%s' failed: %s", name, exc)
            icon = None

    if icon is None:
        icon = QIcon()
        logger.info("Icon '%s' not found; returning empty QIcon", name)

    _ICON_CACHE[name] = icon
    return icon


def register_icon(name: str, icon: QIcon) -> None:
    """Manually add or replace a cached icon entry."""

    _ICON_CACHE[name] = icon


__all__ = [
    "apply_global_theme",
    "apply_panel_header",
    "get_icon",
    "get_palette",
    "load_stylesheet",
    "register_icon",
]
