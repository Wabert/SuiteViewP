"""Read-only layout/database/native-window verification without stored values."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.core.profile_maintenance import plan_profile
from suiteview.core.profile_paths import profile_path, profile_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", action="store_true", help="Also require a visible responsive SuiteView launcher.")
    parser.add_argument("--screenshot", type=Path, help="Capture only the launcher, not the whole desktop.")
    args = parser.parse_args()
    plan = plan_profile(cleanup=True)
    checks = {
        "no_pending_moves": not plan["moves"],
        "no_retired_targets": not plan["remove"],
        "key_present": profile_path(".key").is_file(),
        "tokens_present": profile_path("sp_token_cache.bin").is_file(),
    }
    database = profile_path("suiteview.db")
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        checks["database_integrity"] = connection.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        counts = {}
        for table in ("connections", "saved_queries", "data_maps"):
            counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        counts["encrypted_password_fields"] = connection.execute(
            "SELECT COUNT(*) FROM connections WHERE length(encrypted_password) > 0"
        ).fetchone()[0]
    finally:
        connection.close()
    counts["saved_query_files"] = len(list(profile_path("saved_queries").glob("*.json")))
    counts["query_objects"] = len(list(profile_path("query_objects").glob("*.json")))
    counts["file_sources"] = len(list(profile_path("file_sources").glob("*.json")))
    counts["illustration_case_files"] = len(list(profile_path("illustration_cases").rglob("*.json")))
    if args.window or args.screenshot:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
        user32.FindWindowW.restype = wt.HWND
        user32.IsWindowVisible.argtypes = [wt.HWND]
        user32.IsWindowVisible.restype = wt.BOOL
        user32.IsHungAppWindow.argtypes = [wt.HWND]
        user32.IsHungAppWindow.restype = wt.BOOL
        hwnd = 0
        for _ in range(30):
            hwnd = user32.FindWindowW(None, "SuiteView")
            if hwnd and user32.IsWindowVisible(hwnd):
                break
            time.sleep(1)
        checks["launcher_visible"] = bool(hwnd and user32.IsWindowVisible(hwnd))
        checks["launcher_responsive"] = bool(hwnd and not user32.IsHungAppWindow(hwnd))
        if args.screenshot and checks["launcher_visible"]:
            from PyQt6.QtWidgets import QApplication
            app = QApplication([])
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            checks["screenshot_saved"] = app.primaryScreen().grabWindow(int(hwnd)).save(str(args.screenshot))
    print(json.dumps({
        "all_ok": all(checks.values()),
        "checks": checks,
        "counts": counts,
        "root_entries": sorted(path.name for path in profile_root().iterdir()),
    }, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
