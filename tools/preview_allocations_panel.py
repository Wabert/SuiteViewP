"""Render the IUL AllocationsPanel to a PNG for visual verification.

Shows two states stacked: an IUL14 plan with a split allocation (the live
grid + blended-rate footer) and the greyed Not-Applicable state a declared-
rate UL policy gets.

Usage:
    venv\\Scripts\\python.exe tools/preview_allocations_panel.py
Writes ~/.suiteview/allocations_panel_preview.png and prints the path.
"""
import json
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from suiteview.illustration.models.index_strategies import load_index_strategies  # noqa: E402
from suiteview.illustration.ui.allocations_panel import AllocationsPanel  # noqa: E402
from suiteview.illustration.ui.styles import PURPLE_BG  # noqa: E402

OUT_PATH = Path.home() / ".suiteview" / "allocations_panel_preview.png"


def main():
    app = QApplication(sys.argv)

    host = QWidget()
    host.setStyleSheet(f"background-color: {PURPLE_BG};")
    layout = QVBoxLayout(host)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)

    iul_panel = AllocationsPanel()
    plan = load_index_strategies("1U145500")  # IUL14 — richest strategy set
    iul_panel.set_plan(plan, gint=0.035,
                       inforce_allocations={"U1": 50.0, "IX": 30.0, "IC": 20.0})
    layout.addWidget(iul_panel)

    na_panel = AllocationsPanel()
    na_panel.set_plan(None)
    layout.addWidget(na_panel)

    host.resize(860, 520)
    host.show()
    app.processEvents()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    host.grab().save(str(OUT_PATH))
    print(json.dumps({"screenshot": str(OUT_PATH),
                      "size": [host.width(), host.height()]}))
    app.quit()


if __name__ == "__main__":
    main()
