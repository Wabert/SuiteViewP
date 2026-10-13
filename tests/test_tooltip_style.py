"""Suite-wide tooltip readability.

Qt styles a tooltip with the showing widget's style sheets, and the many
selector-less sheets such as ``"background: transparent;"`` apply to the
tooltip popup too, rendering it as dark text on a black, transparent box.
``suiteview.ui.tooltip_style`` gives every tooltip its own readable sheet; these
tests render real tooltips and measure them.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QHBoxLayout, QLabel, QToolTip, QVBoxLayout, QWidget,
)

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_app_windows_smoke import (  # noqa: E402
    WINDOW_FACTORIES, _cleanup, _exercise_window, app, no_live_access,  # noqa: F401
)

from suiteview.ui import tooltip_style  # noqa: E402
from suiteview.ui.tooltip_style import (  # noqa: E402
    TOOLTIP_STYLE, install_readable_tooltips, set_tooltip_style,
)

MAX_TIPS_PER_WINDOW = 40


def _uninstall_readable_tooltips():
    instance = tooltip_style._instance
    if instance is not None and not sip.isdeleted(instance):
        QApplication.instance().removeEventFilter(instance)
        instance.setParent(None)
    tooltip_style._instance = None


@pytest.fixture
def no_tooltip_hook(app):
    _uninstall_readable_tooltips()
    yield
    install_readable_tooltips()


def _luminance(color) -> float:
    return (0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue()) / 255


def _show_tip(app, widget, text):
    QToolTip.showText(widget.mapToGlobal(QPoint(2, 2)), text, widget)
    app.processEvents()
    return next((w for w in QApplication.topLevelWidgets()
                 if w.objectName() == "qtooltip_label" and w.isVisible()), None)


def _measure(tip):
    """Return (background colour, best text contrast) of a rendered tooltip."""
    image = tip.grab().toImage()
    counts = Counter()
    for x in range(2, image.width() - 2):
        for y in range(2, image.height() - 2):
            counts[image.pixelColor(x, y).getRgb()] += 1
    background = QColor(*counts.most_common(1)[0][0])
    contrast = max(abs(_luminance(QColor(*rgba)) - _luminance(background))
                   for rgba in counts if rgba[3])
    return background, contrast


def _assert_readable(app, widget, text, label):
    tip = _show_tip(app, widget, text)
    if tip is None:
        pytest.skip("platform does not show tooltips")
    try:
        background, contrast = _measure(tip)
        assert background.alpha() == 255, f"{label}: transparent tooltip background"
        assert contrast > 0.5, f"{label}: unreadable tooltip ({background.name()}, {contrast:.2f})"
    finally:
        QToolTip.hideText()
        app.processEvents()
    return tip


def _transparent_host_checkbox():
    """The RERUN 'Include Prem after Val date' shape: a checkbox in a host whose
    sheet is a selector-less ``background: transparent;``."""
    window = QWidget()
    layout = QVBoxLayout(window)
    host = QWidget()
    host.setStyleSheet("background: transparent;")
    QHBoxLayout(host).addWidget(QCheckBox("Include", host))
    layout.addWidget(host)
    window.show()
    QApplication.processEvents()
    return window, host.findChild(QCheckBox)


def test_selector_less_transparent_sheet_breaks_unhooked_tooltips(app, no_tooltip_hook):
    window, check = _transparent_host_checkbox()
    try:
        tip = _show_tip(app, check, "Some readable tooltip text")
        if tip is None:
            pytest.skip("platform does not show tooltips")
        background, _contrast = _measure(tip)
        assert background.alpha() == 0
    finally:
        QToolTip.hideText()
        app.processEvents()
        window.close()


def test_hook_makes_tooltip_under_transparent_sheet_readable(app):
    install_readable_tooltips()
    window, check = _transparent_host_checkbox()
    try:
        tip = _assert_readable(app, check, "Some readable tooltip text", "checkbox")
        assert tip.styleSheet() == TOOLTIP_STYLE
    finally:
        window.close()


def test_install_is_idempotent(app):
    install_readable_tooltips()
    first = tooltip_style._instance
    install_readable_tooltips()
    assert tooltip_style._instance is first


def test_set_tooltip_style_overrides_for_descendants(app):
    install_readable_tooltips()
    themed = "color: #E8F5E9; background: #0A3D0A; border: 1px solid #D4A017;"
    window = QWidget()
    window.setStyleSheet("background: transparent;")
    set_tooltip_style(window, themed)
    label = QLabel("value", window)
    window.show()
    app.processEvents()
    try:
        tip = _assert_readable(app, label, "Field name", "themed label")
        assert tip.styleSheet() == themed
    finally:
        window.close()


def test_rerun_include_premiums_checkbox_tooltip_is_readable(app, no_live_access):
    from suiteview.illustration.ui.main_window import IllustrationWindow

    window = IllustrationWindow()
    try:
        _exercise_window(window, app)
        check = window.include_premiums_check
        _assert_readable(app, check, check.toolTip() or "Include premiums", "Include Prem")
    finally:
        _cleanup(window, app)
        _reset_process_singletons()


def test_widget_style_sheets_do_not_style_tooltips_themselves():
    """The shared hook owns tooltip styling; local QToolTip rules are dead code."""
    root = Path(__file__).resolve().parents[1] / "suiteview"
    pattern = re.compile(r"QToolTip\s*\{")
    offenders = sorted(
        str(path.relative_to(root.parent))
        for path in root.rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == []


def _tooltip_candidates(window):
    widgets = [w for w in window.findChildren(QWidget) if w.isVisible()]
    with_tips = [w for w in widgets if w.toolTip()]
    # Widgets with selector-less sheets are the ones that poison inherited tips.
    bare = [w for w in widgets if w.styleSheet() and "{" not in w.styleSheet()]
    seen, ordered = set(), []
    for widget in [*with_tips, *bare]:
        if id(widget) not in seen:
            seen.add(id(widget))
            ordered.append(widget)
    return ordered[:MAX_TIPS_PER_WINDOW]


@pytest.mark.parametrize("name,factory", WINDOW_FACTORIES, ids=[name for name, _ in WINDOW_FACTORIES])
def test_every_app_window_installs_readable_tooltips(
    name, factory, app, monkeypatch, no_live_access, tmp_path, no_tooltip_hook
):
    window = factory(monkeypatch, no_live_access, tmp_path)
    try:
        assert tooltip_style._instance is not None, f"{name} did not install readable tooltips"
        _exercise_window(window, app)
        candidates = _tooltip_candidates(window)
        assert candidates
        for widget in candidates:
            label = f"{name}: {type(widget).__name__} {widget.objectName()!r}"
            _assert_readable(app, widget, widget.toolTip() or "Tooltip check", label)
    finally:
        _cleanup(window, app)
        _reset_process_singletons()


def _reset_process_singletons() -> None:
    from suiteview.illustration.models import app_settings

    app_settings._settings = None
