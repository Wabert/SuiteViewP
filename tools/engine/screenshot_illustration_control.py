r"""Grab a screenshot of the Illustration Control sub-tab for UI verification.

Creates the Illustration window against local fixture data, selects the
"Illustration Control" sub-tab, and saves a PNG of the inputs area via
QWidget.grab (no live desktop needed).

    venv\Scripts\python.exe tools/engine/screenshot_illustration_control.py '{"policy":"UX012760"}'

Keys: policy (required), region (CKPR), out_dir (default ~/.suiteview/diagnostics).
Prints the output path as JSON.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.profile_paths import diagnostics_dir

os.environ["SUITEVIEW_LOCAL_DATA"] = "1"


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    policy = cmd["policy"]
    region = cmd.get("region", "CKPR")
    out_dir = Path(cmd.get("out_dir") or (diagnostics_dir()))
    out_dir.mkdir(parents=True, exist_ok=True)

    from PyQt6.QtWidgets import QApplication

    from suiteview.illustration.main import create_illustration_window

    app = QApplication.instance() or QApplication(sys.argv)
    window = create_illustration_window(policy_number=policy, region=region)
    window.resize(1400, 900)
    window.show()
    app.processEvents()

    inputs_tab = window.inputs_tab
    control_index = None
    for i in range(inputs_tab.input_tabs.count()):
        if inputs_tab.input_tabs.tabText(i) == "Illustration Control":
            control_index = i
            break
    if control_index is not None:
        inputs_tab.input_tabs.setCurrentIndex(control_index)
    window.tabs.setCurrentWidget(inputs_tab)
    app.processEvents()

    path = out_dir / f"illustration_{policy}_control.png"
    inputs_tab.input_tabs.currentWidget().grab().save(str(path))

    print(json.dumps({"policy": policy, "output": str(path)}))


if __name__ == "__main__":
    main()
