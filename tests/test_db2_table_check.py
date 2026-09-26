"""Focused taskbar integration tests for DB2 Table Check."""

from pathlib import Path

from suiteview.taskbar_launcher.taskbar_window import SuiteViewTaskbar


def test_full_distribution_tools_menu_includes_db2_table_check():
    source = (
        Path(__file__).parents[1]
        / "suiteview"
        / "taskbar_launcher"
        / "taskbar_ui.py"
    ).read_text(encoding="utf-8")

    tools_menu_block = source.split(
        'self.tools_menu.addAction("View Screenshots"', 1
    )[1].split(
        "self.tools_menu.addSeparator()", 1
    )[0]
    assert (
        '("ADMINISTRATOR", "DB2 Table Check", self._open_db2_table_check)'
        in tools_menu_block
    )


def test_taskbar_reuses_ckpr_db2_table_check_window(monkeypatch):
    import suiteview.ui.db2_table_check_window as db2_check_module

    created_regions = []

    class FakeWindow:
        pass

    window = FakeWindow()

    def create_window(*, region):
        created_regions.append(region)
        return window

    monkeypatch.setattr(
        db2_check_module, "DB2TableCheckWindow", create_window)

    bar = SuiteViewTaskbar.__new__(SuiteViewTaskbar)
    bar.db2_check_window = None
    setup = []
    shown = []
    bar._setup_child_window = lambda child, title: setup.append((child, title))
    bar._bring_to_front = lambda child: shown.append(child)

    bar._open_db2_table_check()
    bar._open_db2_table_check()

    assert created_regions == ["CKPR"]
    assert setup == [(window, "DB2 Table Check")]
    assert shown == [window, window]