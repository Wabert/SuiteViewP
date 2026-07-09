"""Render the Index Allocations dialog for a given IUL plancode.

Saves ~/.suiteview/mock_allocations_dialog.png for inspection.

Usage:
    venv\\Scripts\\python.exe tools/mock_allocations_dialog.py [plancode]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from suiteview.illustration.models.index_strategies import load_index_strategies
    from suiteview.illustration.ui.allocations_panel import (
        AllocationsDialog,
        AllocationsPanel,
    )

    plancode = sys.argv[1] if len(sys.argv) > 1 else "1U145500"
    plan = load_index_strategies(plancode)
    if plan is None:
        print(f"{plancode} is not an IUL plancode")
        sys.exit(1)

    panel = AllocationsPanel()
    panel.set_plan(plan, gint=0.035, inforce_allocations={"U1": 0.4, "IX": 0.6})
    dialog = AllocationsDialog(panel)
    dialog.show()
    app.processEvents()

    out = Path.home() / ".suiteview" / "mock_allocations_dialog.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    dialog.grab().save(str(out))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
