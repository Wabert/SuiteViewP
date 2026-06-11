"""Render the Illustration Policy tab from a real local policy.

Saves ~/.suiteview/mock_illustration_policy_tab.png for inspection.

Usage:
    venv\\Scripts\\python.exe tools/mock_illustration_policy_tab.py
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
    from suiteview.illustration.ui.policy_tab import IllustrationPolicyTab

    clear_cache()
    policy = get_policy_info("U0688012", region="CKPR")
    tab = IllustrationPolicyTab()
    tab.load_data_from_policy(policy, {"PolicyNumber": "U0688012", "Region": "CKPR"})
    tab.resize(1180, 760)
    tab.show()
    app.processEvents()

    out = Path.home() / ".suiteview" / "mock_illustration_policy_tab.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    tab.grab().save(str(out))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
