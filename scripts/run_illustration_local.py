"""Launch the SuiteView Illustration app in LOCAL data mode (offline minipc).

Sets SUITEVIEW_LOCAL_DATA=1 so policy lookups read the bundled SQLite fixtures
(bundled_data/dev/policy_records.sqlite + rates.sqlite) instead of live
DB2/UL_Rates. Local policies: UE000576, U0688012, U0492070, U0656998.

Usage:
    venv\\Scripts\\python.exe scripts/run_illustration_local.py [policy_number]

With no argument the window opens empty — type a policy number and click GET.
Passing a policy number pre-loads it.
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

    from suiteview.illustration.main import create_illustration_window

    app = QApplication.instance() or QApplication(sys.argv)
    policy = sys.argv[1] if len(sys.argv) > 1 else None
    window = create_illustration_window(policy_number=policy)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
