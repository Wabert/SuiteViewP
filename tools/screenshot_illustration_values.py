r"""Load a policy in the Illustration window, Run Values, and grab screenshots.

Headless UI verification for the Values tab without driving the desktop: the
window is created for real (local fixture data), a policy is loaded, optional
premium-type selections are applied to the first premium row, Run Values is
invoked, and the requested tab/pages are grabbed to PNG files via QWidget.grab.

    venv\Scripts\python.exe tools/screenshot_illustration_values.py '{"policy":"U0492070"}'
    venv\Scripts\python.exe tools/screenshot_illustration_values.py ^
        '{"policy":"UE050703","premium_type":"Prem to Maturity","group":"Apply Premium"}'

Keys: policy (required), region (CKPR), premium_type (sets the first premium
row's type before the run), group (Values rail page to also capture, e.g.
"Apply Premium"), out_dir (default ~/.suiteview). Writes
<out_dir>/illustration_<policy>_inputs.png / _overview.png / _<group>.png and
prints their paths as JSON.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SUITEVIEW_LOCAL_DATA"] = "1"


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    policy = cmd["policy"]
    region = cmd.get("region", "CKPR")
    premium_type = cmd.get("premium_type")
    group = cmd.get("group")
    out_dir = Path(cmd.get("out_dir") or (Path.home() / ".suiteview"))
    out_dir.mkdir(parents=True, exist_ok=True)

    from PyQt6.QtWidgets import QApplication

    from suiteview.illustration.main import create_illustration_window

    app = QApplication.instance() or QApplication(sys.argv)
    window = create_illustration_window(policy_number=policy, region=region)
    window.resize(1400, 900)
    window.show()
    app.processEvents()

    outputs = {}

    def grab(widget, name: str) -> None:
        path = out_dir / f"illustration_{policy}_{name}.png"
        widget.grab().save(str(path))
        outputs[name] = str(path)

    if premium_type:
        row = window.inputs_tab.dynamic_panel.premium_section.rows()[0]
        row.type_combo.setCurrentText(premium_type)
        app.processEvents()
        window.tabs.setCurrentIndex(1)   # the inputs stack page
        app.processEvents()
        grab(window, "inputs")

    window._on_run_values()
    app.processEvents()

    window.tabs.setCurrentWidget(window.values_tab)
    app.processEvents()
    grab(window, "overview")

    if cmd.get("overview_scroll_right"):
        bar = window.values_tab.overview.ledger.horizontalScrollBar()
        bar.setValue(bar.maximum())
        app.processEvents()
        grab(window, "overview_right")

    if group:
        grid = window.values_tab._tab_grids[group]
        window.values_tab.content_stack.setCurrentWidget(grid)
        app.processEvents()
        column = cmd.get("scroll_to_column")
        if column and grid.model is not None:
            names = list(grid.model.get_display_data().columns)
            if column in names:
                grid.table_view.scrollTo(
                    grid.table_view.model().index(0, names.index(column)),
                    grid.table_view.ScrollHint.PositionAtCenter)
                app.processEvents()
        grab(window, re.sub(r"[^A-Za-z0-9]+", "_", group).lower())

    print(json.dumps({"policy": policy, "premium_type": premium_type,
                      "outputs": outputs}))


if __name__ == "__main__":
    main()
