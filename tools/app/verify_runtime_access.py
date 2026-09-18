"""Verify native launcher permission controls with synthetic roles; no live DB access."""

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication, QMessageBox

from suiteview.core import access_control as access
from suiteview.core import build_env
from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    rights = access.EffectiveAccess(
        "SYNTHETIC", "READER", False, False, False, frozenset({"POLVIEW", "QUERY"}))
    checks = {}
    access.clear_access_cache()
    with (
        TemporaryDirectory(prefix="suiteview_access_") as profile,
        patch.dict(os.environ, {"USERPROFILE": profile, "HOME": profile}),
        patch.object(build_env, "is_distribution_build", return_value=True),
        patch.object(access, "_load_access", return_value=rights) as load,
        patch.object(access, "connect_access_database",
                     side_effect=AssertionError("No live DB access allowed")),
        patch.object(QMessageBox, "warning") as warning,
    ):
        bar = SuiteViewTaskbar()
        try:
            bar.show()
            app.processEvents()
            checks["native_platform"] = app.platformName() == "windows"
            checks["allowed_buttons"] = bar.polview_btn.isEnabled() and bar.audit_btn.isEnabled()
            checks["denied_buttons"] = not any(
                button.isEnabled() for button in (
                    bar.filenav_btn, bar.abrquote_btn, bar.illustration_btn,
                    bar.albert_btn, bar.scratchpad_window_btn, bar.file_history_btn,
                    bar.quick_screenshot_btn,
                )
            )
            checks["no_embedded_filenav"] = bar.tab_widget.count() == 0
            checks["database_read_only"] = build_env.is_data_read_only()
            checks["support_read_only"] = not access.can_write_support_files()
            bar._open_file_nav()
            checks["direct_entry_denied"] = warning.call_count == 1 and bar.file_nav_window is None
            checks["entry_rechecked"] = load.call_count >= 2
            screenshot = args.output_dir / "restricted-launcher.png"
            if not bar.grab().save(str(screenshot)):
                raise RuntimeError(f"Cannot save screenshot: {screenshot}")
            load.return_value = access.EffectiveAccess("SYNTHETIC", "ADMIN", True, True, True)
            bar._refresh_permissions()
            checks["refresh_applies_new_grants"] = all(
                button.isEnabled() for button in (
                    bar.polview_btn, bar.filenav_btn, bar.albert_btn, bar.illustration_btn,
                )
            )
            checks["refreshed_write_permissions"] = (
                not build_env.is_data_read_only() and access.can_write_support_files()
            )
            load.return_value = access.EffectiveAccess(
                "SYNTHETIC", "FILES_ONLY", False, False, False, frozenset({"FILENAV"}))
            access.clear_access_cache()
            bar._open_file_nav()
            checks["filenav_without_scratchpad"] = (
                bar.file_nav_window is not None
                and bar.file_nav_window.get_current_tab().scratchpad_panel is None
            )
        finally:
            if bar.file_nav_window is not None:
                bar.file_nav_window.close()
                bar.file_nav_window.deleteLater()
            bar._unregister_appbar(force=True)
            bar.tray_icon.hide()
            bar.close()
            bar.deleteLater()
            app.processEvents()
            from suiteview.data import database
            if database._db_instance is not None:
                database._db_instance.close()
            access.clear_access_cache()
    report = {"all_ok": all(checks.values()), "checks": checks, "live_data_modified": False}
    (args.output_dir / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
