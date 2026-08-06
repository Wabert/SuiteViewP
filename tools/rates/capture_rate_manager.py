"""Capture a Rate Manager view without requiring desktop focus.

Usage:
    venv\\Scripts\\python.exe tools\\capture_rate_manager.py manage output.png
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from suiteview.ratemanager.ratemanager_window import RateManagerWindow  # noqa: E402


def main() -> None:
    view = sys.argv[1] if len(sys.argv) > 1 else "load"
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("rate_manager.png")

    app = QApplication([])
    window = RateManagerWindow()
    window._show_database()
    if view == "manage":
        window.database_panel.tabs.setCurrentWidget(window.database_panel.manage_tab)
    window.show()
    app.processEvents()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not window.grab().save(str(output), "PNG"):
        raise RuntimeError(f"Could not save screenshot to {output}")
    print(output)
    window.close()


if __name__ == "__main__":
    main()
