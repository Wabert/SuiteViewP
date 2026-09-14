"""Render the real taskbar and shared Albert composer using only synthetic inputs."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "Email Manager" / "outlook-albert"))

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from assignment import Assignment
from compose import ComposeWindow
from compose_support import InstanceLease
from workops_browser import load_workops
from suiteview.taskbar_launcher import albert_launcher
from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--check-workops", action="store_true",
                        help="Read the real saved inventory and report only counts, without refreshing it")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    catalog = {
        "models": [{"id": "claude-sonnet-5", "name": "Claude Sonnet 5",
                    "thinking_levels": [{"id": "high", "label": "High"}],
                    "default_thinking": "high"}],
        "recommended": {"model_id": "claude-sonnet-5", "thinking_level": "high"},
    }
    results = {}
    if args.check_workops:
        saved = load_workops()
        results["saved_workops"] = {
            "cached_at": saved["cached_at"],
            "categories": {category: sum(row["category"] == category for row in saved["items"])
                           for category in saved["categories"]},
            "warning_count": len(saved["warnings"]),
        }
    synthetic_workops = {
        "categories": ["Projects", "Requests", "ToDos", "SDLCs"],
        "cached_at": "2026-09-13 21:00 (synthetic)", "warnings": [],
        "items": [
            {"category": category, "id": identity, "title": title, "status": status,
             "key": category + "\\" + identity, "path": "C:\\Synthetic\\" + identity, "problem": ""}
            for category, identity, title, status in [
                ("Projects", "P12", "Valuation review", "Active"),
                ("Requests", "R28", "Rate comparison", "Closed"),
                ("ToDos", "T3", "Check workbook", "Active"),
                ("SDLCs", "123456", "Reporting change", "Active"),
            ]
        ],
    }
    with TemporaryDirectory(prefix="albert-ui-") as temporary, ExitStack() as stack:
        # Retain the real layout/mode transitions without reserving desktop space,
        # touching bookmarks/settings, or starting any tool or VS Code session.
        for method in ("_setup_system_tray", "_connect_screen_change_handlers",
                       "add_new_tab", "_register_appbar", "_unregister_appbar",
                       "_apply_toolwindow_style"):
            stack.enter_context(patch.object(SuiteViewTaskbar, method))
        with patch.object(SuiteViewTaskbar, "_enter_compact_mode"):
            bar = SuiteViewTaskbar()
        bar._hidden_to_tray = True
        bar._enter_compact_mode()
        bar.show()
        QTest.qWait(100)
        assert bar.albert_btn.isVisible()
        assert bar.header_bar.rect().contains(bar.albert_btn.geometry())
        results["docked_button_visible"] = True
        assert bar.header_bar.grab().save(str(args.output / "albert-taskbar.png"))
        bar._enter_floating_mode()
        QTest.qWait(100)
        assert bar.albert_btn.isVisible()
        assert bar.header_bar.rect().contains(bar.albert_btn.geometry())
        assert bar.close_btn.geometry().left() > bar.albert_btn.geometry().right()
        results["floating_button_visible"] = True
        assert bar.grab().save(str(args.output / "albert-floating-taskbar.png"))
        windows = []

        def open_synthetic():
            task = Assignment.new_task(temporary)
            lease = InstanceLease(temporary)
            stack.callback(lease.release)
            window = ComposeWindow(
                task, "New task", None, None, None, model_catalog=catalog,
                instance_number=lease.number, workops_loader=lambda: synthetic_workops)
            windows.append(window)
            window.show()

        stack.enter_context(patch.object(albert_launcher, "launch_albert", open_synthetic))
        QTest.mouseClick(bar.albert_btn, Qt.MouseButton.LeftButton)
        QTest.qWait(100)
        assert len(windows) == 1
        window = windows[0]
        assert window.windowTitle() == "Albert (1)"
        assert not window.send_button.isEnabled()
        window.instructions.setPlainText(
            "Compare the options for this task and summarize your recommendation.\n\n"
            "No email is attached.")
        assert window.send_button.isEnabled()
        assert window.rect().contains(window.send_button.mapTo(window, window.send_button.rect().bottomRight()))
        assert window.grab().save(str(args.output / "albert-standalone-composer.png"))
        QTest.mouseClick(bar.albert_btn, Qt.MouseButton.LeftButton)
        QTest.qWait(100)
        assert windows[1].windowTitle() == "Albert (2)"
        windows[1].close()
        window.raise_()
        window.workops_button.click()
        for _ in range(100):
            if window.workops_worker is None:
                break
            QTest.qWait(20)
        assert window.workops_worker is None and window.workops_loaded
        assert window.workops_panel.isVisible()
        assert window.splitter.indexOf(window.workops_panel) == 0
        assert window.workops_panel.tree.topLevelItemCount() == 4
        window.assignment.prepare("Compare the options", window.instructions.toPlainText(), "instructions", [])
        window.assignment.details["title"] = "Albert - Compare the options"
        window.assignment.mark("submitted")
        window._restore()
        assert window.windowTitle() == "Albert (1) - Compare the options"
        window.worker = object()
        window._notice(window.status, "Connecting to Albert...")
        window._count()
        QTest.qWait(90)
        first_angle = window.busy_indicator.angle
        QTest.qWait(90)
        assert first_angle != window.busy_indicator.angle
        assert window.grab().save(str(args.output / "albert-workops-connecting.png"))
        window.worker = None
        window._restore()
        window._count()
        QTest.qWait(50)
        assert not window.busy_indicator.timer.isActive()
        assert window.rect().contains(window.send_button.mapTo(window, window.send_button.rect().bottomRight()))
        assert window.grab().save(str(args.output / "albert-workops-submitted.png"))
        results["numbered_instances"] = [1, 2]
        results["animated_indicator_verified"] = True
        results["workops_panel_visible"] = True
        results["click_opens_shared_composer"] = True
        results["expanded_composer_size"] = [window.width(), window.height()]
        results["qt_platform"] = app.platformName()
        results["device_pixel_ratio"] = window.devicePixelRatioF()
        results["no_external_submission"] = True
        window.close()
        bar.hide()
        bar.deleteLater()
        app.processEvents()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
