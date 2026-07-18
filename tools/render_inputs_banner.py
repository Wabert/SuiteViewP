"""Render the Illustration Inputs valuation banner to a PNG, offscreen.

Loads a real policy from the local SQLite data (SUITEVIEW_LOCAL_DATA=1) into
IllustrationInputsTab so the banner strip (Valuation Date ... DB Option) can be
eyeballed without launching the full app.

Usage:
    venv\\Scripts\\python.exe tools/render_inputs_banner.py [policy] [out.png]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["SUITEVIEW_LOCAL_DATA"] = "1"


def main():
    policy_num = sys.argv[1] if len(sys.argv) > 1 else "U0356726"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else (
        Path.home() / ".suiteview" / "inputs_banner.png")

    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])

    from suiteview.core.policy_service import get_policy_info
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

    pi = get_policy_info(policy_num, region="CKPR")
    if pi is None or not pi.exists:
        print(f"policy {policy_num} not found in local data")
        return 1

    tab = IllustrationInputsTab()
    tab.load_data_from_policy(pi)
    tab.resize(1300, 300)
    tab.show()
    app.processEvents()

    out.parent.mkdir(parents=True, exist_ok=True)
    tab.grab().save(str(out))
    print(f"saved {out}  |  DB Option shown: {tab.banner_db_option_label.text()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
