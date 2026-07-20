"""Render the Illustration Control tab so the Run Controls group can be
eyeballed — editable checkboxes packed left, the two always-on locked
controls (Conform to TEFRA/DEFRA, Stop Projection on Lapse) off to the right.

Saves ~/.suiteview/mock_run_controls_group.png.

Usage:
    venv\\Scripts\\python.exe tools/mock_run_controls_group.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SUITEVIEW_LOCAL_DATA"] = "1"


def main() -> None:
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from suiteview.core.policy_service import clear_cache, get_policy_info
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

    clear_cache()
    policy_info = get_policy_info("U0656998", region="CKPR")
    tab = IllustrationInputsTab()
    tab.load_data_from_policy(policy_info)

    # Front the Illustration Control tab (the Run Controls group lives there).
    for index in range(tab.input_tabs.count()):
        if "control" in tab.input_tabs.tabText(index).lower():
            tab.input_tabs.setCurrentIndex(index)
            break

    out_dir = Path.home() / ".suiteview"
    out_dir.mkdir(parents=True, exist_ok=True)
    tab.resize(1240, 780)
    tab.show()
    app.processEvents()
    path = out_dir / "mock_run_controls_group.png"
    tab.grab().save(str(path))
    tab.hide()
    print(str(path))


if __name__ == "__main__":
    main()
