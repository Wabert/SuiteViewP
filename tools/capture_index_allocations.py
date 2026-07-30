r"""Render the Index Strategy Allocations panel with live UL_Rates data.

Usage:
    venv\Scripts\python.exe tools\capture_index_allocations.py ^
      "{\"company\":\"01\",\"plancode\":\"1U147500\",\"illustration_date\":\"2026-08-15\",\"output\":\"C:\\temp\\index_allocations.png\"}"
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from suiteview.core.rates import Rates  # noqa: E402
from suiteview.illustration.models.index_strategies import (  # noqa: E402
    load_index_strategies,
    with_current_index_data,
)
from suiteview.illustration.ui.allocations_panel import AllocationsPanel  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Pass a JSON config argument.")
    config = json.loads(sys.argv[1])
    company = config["company"]
    plancode = config["plancode"]
    illustration_date = date.fromisoformat(config["illustration_date"])
    rga_indicator = str(config.get("rga_indicator", ""))
    output = Path(config["output"]).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    rates = Rates()
    try:
        plan = load_index_strategies(plancode)
        if plan is None:
            raise ValueError(f"{plancode} does not have an index strategy catalog row.")
        plan = with_current_index_data(
            plan,
            rates.get_index_illustration_rates(
                company, plancode, illustration_date, rga_indicator),
            rates.get_index_strategy_parameters(
                plancode, illustration_date, rga_indicator),
        )
    finally:
        rates.close()

    app = QApplication.instance() or QApplication(sys.argv)
    panel = AllocationsPanel()
    panel.set_plan(
        plan,
        gint=0.03,
        inforce_allocations={"U1": 50.0, "IP": 25.0, "IR": 25.0},
    )
    panel.adjustSize()
    panel.resize(1050, panel.sizeHint().height())
    panel.show()
    app.processEvents()
    if not panel.grab().save(str(output)):
        raise RuntimeError(f"Could not save screenshot to {output}")
    panel.close()

    print(json.dumps({
        "output": str(output),
        "plancode": plancode,
        "problems": panel.problems(),
    }, indent=2))


if __name__ == "__main__":
    main()
