r"""Render the Illustration Batch tab to a PNG for visual verification.

Offscreen (no display needed): constructs IllustrationBatchTab, populates it
with a couple of fake results (one Complete, one bypass), and saves a widget
grab. Takes one JSON argument: {"out": "path/to/png"}.

    venv\Scripts\python.exe tools/screenshot_illustration_batch.py "{\"out\": \"...\"}"
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    out = Path(cmd.get("out") or (Path.home() / ".suiteview" / "batch_tab.png"))
    out.parent.mkdir(parents=True, exist_ok=True)

    from PyQt6.QtWidgets import QApplication

    from suiteview.illustration.core.batch_runner import PolicyResult
    from suiteview.illustration.ui.batch_tab import IllustrationBatchTab

    app = QApplication.instance() or QApplication([])
    tab = IllustrationBatchTab()
    tab.resize(1180, 720)
    tab.policy_edit.setPlainText("01 UL054426\nS0503261\nZZ999999")
    tab.populate_results([
        PolicyResult(policy="UL054426", company="01", status="Complete",
                     values={"run_status": "Complete", "plancode": "1U130N2X",
                             "form": "FPL83", "issue_date": date(1984, 12, 7),
                             "face": 50000.0, "level_prem": 99.12,
                             "exc_date": "(none)", "lapse_no_prem": date(2040, 12, 7),
                             "lapse_cur_prem": date(2048, 11, 7),
                             "lapse_abs_max": "Maturity"}),
        PolicyResult(policy="ZZ999999", company=None, status="bypass (load error)",
                     error="Policy ZZ999999 not found in region CKPR",
                     values={"run_status": "bypass (load error)"}),
    ])
    tab.show()
    app.processEvents()
    tab.grab().save(str(out))
    print(json.dumps({"out": str(out)}))
    app.quit()


if __name__ == "__main__":
    main()
