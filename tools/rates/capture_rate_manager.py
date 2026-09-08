r"""Capture a Rate Manager view without requiring desktop focus.

Usage:
    venv\Scripts\python.exe tools\rates\capture_rate_manager.py <view> <out.png>
        [--width 840 --height 620]
        [--cvf-path <file> --infer-cvf-negatives] (wl-workup preview only; no DB writes)

Views:
    chooser | workup | database | manage | converters
    term-workup | term-database | wl-workup | wl-database
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QEventLoop  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from suiteview.ratemanager.product_chooser import (  # noqa: E402
    TERM_LINE, UL_LINE, WL_LINE,
)
from suiteview.ratemanager.ratemanager_window import RateManagerWindow  # noqa: E402


def _select(window: RateManagerWindow, view: str) -> None:
    if view == "chooser":
        window._show_chooser()
        return

    line = (
        WL_LINE if view.startswith("wl-")
        else TERM_LINE if view.startswith("term-") else UL_LINE
    )
    window._on_line_chosen(line)

    if view in ("workup", "term-workup", "wl-workup"):
        window._show_workup()
    elif view in ("database", "term-database", "wl-database", "manage"):
        window._show_database()
        if view == "manage":
            window.database_panel.tabs.setCurrentWidget(
                window.database_panel.manage_tab)
    elif view == "converters":
        window._show_converters()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("view", nargs="?", default="chooser", choices=(
        "chooser", "workup", "database", "manage", "converters",
        "term-workup", "term-database", "wl-workup", "wl-database",
    ))
    parser.add_argument("output", nargs="?", type=Path, default=Path("rate_manager.png"))
    parser.add_argument("--width", type=int, default=1120)
    parser.add_argument("--height", type=int, default=850)
    parser.add_argument("--cvf-path", type=Path, action="append", default=[])
    parser.add_argument("--infer-cvf-negatives", action="store_true")
    args = parser.parse_args()
    if (args.cvf_path or args.infer_cvf_negatives) and args.view != "wl-workup":
        parser.error("CVF preview options require wl-workup.")
    if args.infer_cvf_negatives and not args.cvf_path:
        parser.error("CVF inference requires --cvf-path.")
    output = args.output

    app = QApplication([])
    window = RateManagerWindow()
    _select(window, args.view)
    window.resize(args.width, args.height)
    window.show()
    app.processEvents()
    if args.cvf_path:
        panel = window.wl_workup_panel
        panel.set_paths("CVF", [str(path) for path in args.cvf_path])
        panel.infer_cvf_negatives_check.setChecked(args.infer_cvf_negatives)
        loop = QEventLoop()
        panel.busy_changed.connect(lambda busy: loop.quit() if not busy else None)
        panel._parse()
        if panel.is_busy:
            loop.exec()
        if panel._package is None:
            raise RuntimeError(panel.status.text())
        audit = panel.preview_tables.get("CVF inference")
        if audit is not None:
            panel.preview_tabs.setCurrentWidget(audit)
        app.processEvents()
        print(json.dumps({
            "row_counts": panel._package.row_counts,
            "inferred_rows": audit.model.rowCount() if audit is not None else 0,
            "database_writes": False,
        }))
    output.parent.mkdir(parents=True, exist_ok=True)
    if not window.grab().save(str(output), "PNG"):
        raise RuntimeError(f"Could not save screenshot to {output}")
    print(output)
    window.close()


if __name__ == "__main__":
    main()
