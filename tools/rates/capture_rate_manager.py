r"""Capture a Rate Manager view without requiring desktop focus.

Usage:
    venv\Scripts\python.exe tools\rates\capture_rate_manager.py <view> <out.png>

Views:
    chooser | workup | database | manage | converters
    term-workup | term-database
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from suiteview.ratemanager.product_chooser import (  # noqa: E402
    TERM_LINE, UL_LINE,
)
from suiteview.ratemanager.ratemanager_window import RateManagerWindow  # noqa: E402


def _select(window: RateManagerWindow, view: str) -> None:
    if view == "chooser":
        window._show_chooser()
        return

    window._on_line_chosen(TERM_LINE if view.startswith("term") else UL_LINE)

    if view in ("workup", "term-workup"):
        window._show_workup()
    elif view in ("database", "term-database", "manage"):
        window._show_database()
        if view == "manage":
            window.database_panel.tabs.setCurrentWidget(
                window.database_panel.manage_tab)
    elif view == "converters":
        window._show_converters()


def main() -> None:
    view = sys.argv[1] if len(sys.argv) > 1 else "chooser"
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("rate_manager.png")

    app = QApplication([])
    window = RateManagerWindow()
    _select(window, view)
    window.show()
    app.processEvents()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not window.grab().save(str(output), "PNG"):
        raise RuntimeError(f"Could not save screenshot to {output}")
    print(output)
    window.close()


if __name__ == "__main__":
    main()
