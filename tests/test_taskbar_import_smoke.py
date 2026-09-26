"""Import smoke tests for the split taskbar launcher modules."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from suiteview.core.access_control import EffectiveAccess


def test_split_taskbar_imports_and_constructs_main_window(monkeypatch):
    from suiteview.taskbar_launcher import taskbar_window
    from suiteview.taskbar_launcher.taskbar_window import SuiteViewTaskbar

    rights = EffectiveAccess(
        "SMOKE", "BUSINESS", False, False, False,
        apps=frozenset({"POLVIEW", "ABR", "RERUN", "QUERY"}),
    )
    monkeypatch.setattr(taskbar_window, "get_access", lambda refresh=True: rights)
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: None)
    monkeypatch.setattr(SuiteViewTaskbar, "_register_appbar", lambda *args, **kwargs: None)
    monkeypatch.setattr(SuiteViewTaskbar, "_unregister_appbar", lambda *args, **kwargs: None)

    app = QApplication.instance() or QApplication([])
    window = SuiteViewTaskbar()
    try:
        assert window.chrome.title_label.text().startswith("SuiteView (")
        assert window.chrome.tab_widget.count() == 0
    finally:
        window.close()
        app.processEvents()
