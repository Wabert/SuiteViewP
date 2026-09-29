"""RERUN header Tips button and its hidden-features cheat-sheet."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton

from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab
from suiteview.illustration.ui.tips import RERUN_TIPS, RerunTipsDialog, tips_html


_QT_APP = None


@pytest.fixture
def app(monkeypatch, tmp_path):
    global _QT_APP
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path / "profile"))
    from suiteview.core import access_control

    monkeypatch.setattr(access_control, "guard_app_access", lambda _code: None)
    # Module-held so the QApplication outlives this fixture; destroying it
    # would also delete process-wide QObject singletons later tests reuse.
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_every_tip_has_a_location_and_description():
    assert RERUN_TIPS
    for section in RERUN_TIPS:
        assert section.title.strip()
        assert section.tips
        for tip in section.tips:
            assert tip.where.strip() and tip.what.strip()


def test_tips_explain_how_to_reach_grid_inputs_and_policy_transactions():
    html = tips_html()
    assert IllustrationInputsTab.GRID_INPUTS_TAB_LABEL in html
    assert "Right-click the Input / Illustration Control tab bar" in html
    assert "Populate from policy" in html
    assert "Paste from Clipboard" in html


def test_tips_html_escapes_text():
    from suiteview.illustration.ui.tips import Tip, TipSection

    html = tips_html((TipSection("A & B", (Tip("<x>", "1 < 2"),)),))
    assert "A &amp; B" in html
    assert "&lt;x&gt;" in html
    assert "1 &lt; 2" in html


def test_header_tips_button_opens_one_non_modal_dialog(app):
    from suiteview.illustration.ui.main_window import IllustrationWindow

    window = IllustrationWindow()
    try:
        header_buttons = window.header_bar.findChildren(QPushButton)
        assert window.tips_btn in header_buttons
        assert window.tips_btn.text() == "Tips"

        window.tips_btn.click()
        app.processEvents()
        dialog = window._tips_dialog
        assert isinstance(dialog, RerunTipsDialog)
        assert dialog.isVisible()
        assert not dialog.isModal()
        assert "Grid Inputs" in dialog.browser.toPlainText()

        dialog.close()
        app.processEvents()
        window.tips_btn.click()
        app.processEvents()
        assert window._tips_dialog is dialog
        assert dialog.isVisible()
    finally:
        if window._tips_dialog is not None:
            window._tips_dialog.close()
        window.close()
        window.deleteLater()
        app.processEvents()
