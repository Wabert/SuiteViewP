"""Readable, consistent tooltips inside PolView windows.

Qt styles a tooltip with the style sheets of the widget that shows it. Much of
PolView (like most of SuiteView) styles labels with ``background: transparent``
and dark text, so a tooltip inherited those rules and rendered as dark text on
a black, translucent box. A tooltip's *own* style sheet takes precedence over
anything it inherits, so when a tooltip opens over a registered PolView window
this filter gives it an explicit light style. Tooltips elsewhere in SuiteView
keep their existing look.
"""

from __future__ import annotations

import weakref

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QWidget

from suiteview.ui import tokens

# Bare declarations on purpose: a selector such as "QLabel { ... }" loses to the
# inherited bare "background: transparent" rules (verified natively).
TOOLTIP_STYLE = (
    f"color: {tokens.TEXT_DARK}; background: {tokens.POLVIEW_TOOLTIP_SURFACE}; "
    f"border: 1px solid {tokens.GOLD_BORDER};"
    " padding: 3px 6px; font-size: 11px; font-weight: normal; font-style: normal;"
    " text-decoration: none;"
)
_OWN_PROPERTY = "_polview_readable_tip"


class _ReadableTooltips(QObject):
    def __init__(self, app: QApplication):
        super().__init__(app)
        self._windows: "weakref.WeakSet[QWidget]" = weakref.WeakSet()
        app.installEventFilter(self)

    def register(self, window: QWidget):
        self._windows.add(window)

    def _owned(self, widget) -> bool:
        window = widget.window() if widget is not None else None
        while window is not None:
            if window in self._windows:
                return True
            parent = window.parentWidget()
            window = parent.window() if parent is not None else None
        return False

    def eventFilter(self, obj, event):
        # Qt re-applies "/* */" to the tip when it positions it, which fires
        # StyleChange; restyle then as well as on Show.
        if (event.type() in (QEvent.Type.Show, QEvent.Type.StyleChange)
                and obj.objectName() == "qtooltip_label"):
            try:
                self._restyle(obj)
            except RuntimeError:
                pass
        return False

    def _restyle(self, tip):
        source = tip.property("_q_stylesheet_parent")
        if not isinstance(source, QWidget) or sip.isdeleted(source):
            source = QApplication.widgetAt(QCursor.pos())
        if isinstance(source, QWidget) and not sip.isdeleted(source) and self._owned(source):
            if tip.styleSheet() != TOOLTIP_STYLE:
                tip.setProperty(_OWN_PROPERTY, True)
                tip.setStyleSheet(TOOLTIP_STYLE)
                tip.adjustSize()
        elif tip.property(_OWN_PROPERTY) and tip.styleSheet() == TOOLTIP_STYLE:
            tip.setProperty(_OWN_PROPERTY, False)
            tip.setStyleSheet("")
            tip.adjustSize()


_instance: _ReadableTooltips | None = None


def use_readable_tooltips(window: QWidget) -> None:
    """Give tooltips shown over *window* (and its dialogs) a legible light style."""
    global _instance
    app = QApplication.instance()
    if app is None:
        return
    if _instance is None or sip.isdeleted(_instance):
        _instance = _ReadableTooltips(app)
    _instance.register(window)
