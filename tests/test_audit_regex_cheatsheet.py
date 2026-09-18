import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel

from suiteview.audit import audit_window
from suiteview.audit.regex_cheatsheet import REGEX_SECTIONS, RegexCheatsheetWindow
from suiteview.polview.ui.widgets import CopyableLabel, StyledInfoTableGroup


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_reference_is_complete_compact_and_copyable(app):
    window = RegexCheatsheetWindow()
    try:
        window.show()
        app.processEvents()
        groups = window.findChildren(StyledInfoTableGroup)
        assert [len(entries) for _, entries in REGEX_SECTIONS] == [12, 6, 8]
        assert [group.title() for group in groups] == [
            "Expressions", "Character classes", "Useful patterns"
        ]
        for group, (_, entries) in zip(groups, REGEX_SECTIONS):
            for index, (expression, meaning) in enumerate(entries):
                key = f"entry_{index}"
                label, value = group._labels[key], group._fields[key]
                assert label.text() == expression
                assert value.text() == meaning
                assert label.height() == value.height() == 16
                # The offscreen plugin has no Windows fonts; check text fit natively.
                if app.platformName() == "windows":
                    assert label.fontMetrics().horizontalAdvance(expression) <= label.width()
                    assert value.fontMetrics().horizontalAdvance(meaning) <= value.width()
                assert isinstance(label, CopyableLabel)
                assert isinstance(value, CopyableLabel)
                assert group.rect().contains(value.mapTo(group, value.rect().bottomRight()))
        assert window.width() == 475
        assert window.height() == 570
        assert any("not SQL LIKE" in label.text() for label in window.findChildren(QLabel))
    finally:
        window.close()
        window.deleteLater()


@pytest.mark.parametrize("read_only", [False, True])
def test_header_button_opens_reuses_and_reopens_reference(app, monkeypatch, read_only):
    monkeypatch.setattr(audit_window, "is_data_read_only", lambda: read_only)
    monkeypatch.setattr(audit_window, "load_ui_settings", lambda: {})
    monkeypatch.setattr(audit_window, "save_ui_settings", lambda settings: None)
    window = audit_window.AuditWindow()
    try:
        button = window.btn_regex_cheatsheet
        assert button.text() == "RegEx Cheatsheet"
        assert window.header_bar.layout().indexOf(button) >= 0
        assert not button.isHidden()
        button.click()
        reference = window._regex_cheatsheet
        assert reference.isVisible()
        assert reference.isWindow()
        assert reference.windowModality() == Qt.WindowModality.NonModal
        button.click()
        assert window._regex_cheatsheet is reference
        reference.close()
        assert not reference.isVisible()
        button.click()
        assert window._regex_cheatsheet is reference
        assert reference.isVisible()
    finally:
        if window._regex_cheatsheet is not None:
            window._regex_cheatsheet.close()
        window.close()
        window.deleteLater()
