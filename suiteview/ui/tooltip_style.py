"""Readable, consistent tooltips across every SuiteView window.

Qt styles a tooltip with the style sheets of the widget that shows it, and a
selector-less sheet such as ``"background: transparent;"`` is applied as
``* { ... }`` -- including to the tooltip popup. Hundreds of SuiteView widgets
use such sheets, so an unstyled tooltip routinely rendered as dark text on a
black, fully transparent box. An application-level ``QToolTip`` rule cannot fix
this: Qt prefers the nearer (inherited) sheet regardless of specificity.

A tooltip's *own* style sheet beats anything it inherits, so an application
event filter gives every tooltip popup :data:`TOOLTIP_STYLE` as it is shown.
The filter is installed automatically by :class:`FramelessWindowBase` and by
SuiteView startup; call :func:`install_readable_tooltips` from any other
``QApplication`` entry point. A deliberately themed area can choose a different
tooltip look for itself and its descendants with :func:`set_tooltip_style`.
"""

from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QWidget

from suiteview.ui import tokens

# Bare declarations on purpose: a selector such as "QLabel { ... }" loses to the
# inherited bare "background: transparent" rules (verified natively).
TOOLTIP_STYLE = (
    f"color: {tokens.TEXT_DARK}; background: {tokens.TOOLTIP_SURFACE}; "
    f"border: 1px solid {tokens.GOLD_BORDER};"
    " padding: 3px 6px; font-size: 11px; font-weight: normal; font-style: normal;"
    " text-decoration: none;"
)
TOOLTIP_STYLE_PROPERTY = "suiteviewTooltipStyle"
_TIP_OBJECT_NAME = "qtooltip_label"


def set_tooltip_style(widget: QWidget, style: str) -> None:
    """Use *style* (bare QSS declarations) for tooltips shown by *widget* or any
    descendant, instead of :data:`TOOLTIP_STYLE`. Keep it readable."""
    widget.setProperty(TOOLTIP_STYLE_PROPERTY, style)


def tooltip_style_for(widget: QWidget | None) -> str:
    """Return the tooltip style for tips shown by *widget*: the nearest
    :func:`set_tooltip_style` override up its parent chain, else the default."""
    while widget is not None and not sip.isdeleted(widget):
        style = widget.property(TOOLTIP_STYLE_PROPERTY)
        if isinstance(style, str) and style:
            return style
        widget = widget.parentWidget()
    return TOOLTIP_STYLE


class _ReadableTooltips(QObject):
    def __init__(self, app: QApplication):
        super().__init__(app)
        app.installEventFilter(self)

    def eventFilter(self, obj, event):
        # Qt re-applies "/* */" to the tip when it positions it, which fires
        # StyleChange; restyle then as well as on Show.
        if (event.type() in (QEvent.Type.Show, QEvent.Type.StyleChange)
                and obj.objectName() == _TIP_OBJECT_NAME):
            try:
                self._restyle(obj)
            except RuntimeError:
                pass
        return False

    def _restyle(self, tip):
        source = tip.property("_q_stylesheet_parent")
        if not isinstance(source, QWidget) or sip.isdeleted(source):
            source = QApplication.widgetAt(QCursor.pos())
        style = tooltip_style_for(source if isinstance(source, QWidget) else None)
        if tip.styleSheet() != style:
            tip.setStyleSheet(style)
            tip.adjustSize()


_instance: _ReadableTooltips | None = None


def install_readable_tooltips() -> None:
    """Give every tooltip in the running ``QApplication`` a readable style.

    Idempotent; does nothing before a ``QApplication`` exists.
    """
    global _instance
    app = QApplication.instance()
    if app is None:
        return
    if _instance is None or sip.isdeleted(_instance) or _instance.parent() is not app:
        _instance = _ReadableTooltips(app)
