"""Grid Inputs tab visibility (headless Qt).

The "Grid Inputs" sub-tab (raw dated-transaction tables, inside the
Illustration Inputs tab's input_tabs QTabWidget) is power-user territory —
hidden by default, revealed via a checkable right-click context menu on the
tab bar. setTabVisible() is used (not add/removeTab) so tab indices stay
stable. Per-case persistence is covered in tests/test_illustration_case_store.py;
this file covers the tab-bar widget behavior itself.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def _tab() -> IllustrationInputsTab:
    _app()
    return IllustrationInputsTab()


def test_grid_inputs_tab_is_hidden_by_default():
    tab = _tab()
    index = tab._grid_inputs_tab_index
    assert tab.input_tabs.tabText(index) == "Grid Inputs"
    assert tab.grid_inputs_tab_visible() is False
    assert tab.input_tabs.isTabVisible(index) is False
    # Hidden, not removed — the index stays stable/addressable.
    assert tab.input_tabs.count() == 3


def test_context_menu_toggle_shows_and_hides_the_tab():
    tab = _tab()
    index = tab._grid_inputs_tab_index

    # Simulate checking the context-menu entry (the checkable QAction's
    # toggled signal is wired directly to this setter).
    tab._set_grid_inputs_tab_visible(True)
    assert tab.grid_inputs_tab_visible() is True
    assert tab.input_tabs.isTabVisible(index) is True
    assert tab.input_tabs.currentIndex() == index   # switches to it

    tab._set_grid_inputs_tab_visible(False)
    assert tab.grid_inputs_tab_visible() is False
    assert tab.input_tabs.isTabVisible(index) is False


def test_hiding_the_current_grid_inputs_tab_switches_to_a_neighbor():
    tab = _tab()
    index = tab._grid_inputs_tab_index
    tab._set_grid_inputs_tab_visible(True)
    tab.input_tabs.setCurrentIndex(index)
    assert tab.input_tabs.currentIndex() == index

    tab._set_grid_inputs_tab_visible(False)
    # Never left on the now-hidden tab — lands on "Input" instead.
    assert tab.input_tabs.currentIndex() != index
    assert tab.input_tabs.tabText(tab.input_tabs.currentIndex()) == "Input"


def test_context_menu_action_is_checkable_and_reflects_current_visibility():
    tab = _tab()
    tab.show()
    try:
        menu_actions = []

        # _show_input_tabs_context_menu builds+execs a QMenu synchronously,
        # which would block waiting for a click in a real event loop. Patch
        # QMenu.exec to capture the built menu instead of showing it.
        from PyQt6.QtWidgets import QMenu

        original_exec = QMenu.exec

        def fake_exec(self, *args, **kwargs):
            menu_actions.extend(self.actions())
            return None

        QMenu.exec = fake_exec
        try:
            tab._show_input_tabs_context_menu(tab.input_tabs.tabBar().rect().center())
        finally:
            QMenu.exec = original_exec

        assert len(menu_actions) == 1
        action = menu_actions[0]
        assert action.text() == "Grid Inputs"
        assert action.isCheckable()
        assert action.isChecked() is False
    finally:
        tab.hide()
