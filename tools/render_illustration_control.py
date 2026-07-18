"""Render the Illustration Control tab to a PNG offscreen.

Lets the Run Controls / IUL Crediting layout (including the AG49 regime panel)
be eyeballed without launching the full app.

Usage:
    venv\\Scripts\\python.exe tools/render_illustration_control.py [out.png] [issue_date] [checked] [iul]

    issue_date  optional YYYY-MM-DD; drives which AG49 regime row auto-selects
    checked     optional 1/0 (default 1) for "Use Policy AG49 Regime"
    iul         optional 1/0 (default 1); 0 greys the IUL Crediting group
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (Path.home() / ".suiteview" / "illustration_control.png")
    issue = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2016, 8, 14)
    checked = (sys.argv[3] != "0") if len(sys.argv) > 3 else True
    iul = (sys.argv[4] != "0") if len(sys.argv) > 4 else True
    out.parent.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    tab = IllustrationInputsTab()
    tab._issue_date = issue
    tab._set_iul_crediting_applicable(iul)
    tab.policy_ag49_check.setChecked(checked)
    tab._update_ag49_regime_panel()
    tab.input_tabs.setCurrentIndex(2)  # Illustration Control
    tab.resize(1180, 900)
    app.processEvents()
    app.processEvents()
    tab.grab().save(str(out))
    print(str(out))


if __name__ == "__main__":
    main()
