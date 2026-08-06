"""Launch the SuiteView Illustration app against LIVE data (DB2 / UL_Rates).

Unlike ``run_illustration_local.py`` this does NOT set SUITEVIEW_LOCAL_DATA, so
policy lookups and rate queries go to the live production sources. Requires the
work-laptop environment with the DB2 DSNs and UL_Rates connection configured.

Usage:
    venv\\Scripts\\python.exe scripts/run_illustration_live.py [policy_number]

With no argument the window opens empty — type a policy number and click GET.
Passing a policy number pre-loads it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
