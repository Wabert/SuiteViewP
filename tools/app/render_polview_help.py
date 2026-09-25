"""Render an empty PolView window and its Shortcuts help to PNGs (no DB2, no policy).

Uses an isolated temporary profile so nothing is written to the real one.

Usage:
    venv\\Scripts\\python.exe tools/app/render_polview_help.py '{"out_dir": "C:/tmp"}'

Writes polview_window.png and polview_help.png to out_dir
(default ~/.suiteview/diagnostics) and prints the help rows as JSON.
"""

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    opts = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    with TemporaryDirectory(prefix="suiteview-polview-help-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        from PyQt6.QtCore import QEventLoop, QTimer
        from PyQt6.QtWidgets import QApplication

        from suiteview.core.profile_paths import diagnostics_dir
        from suiteview.polview.ui.main_window import GetPolicyWindow
        from suiteview.polview.ui.polview_dialogs import SHORTCUTS

        out_dir = Path(opts.get("out_dir") or diagnostics_dir())
        out_dir.mkdir(parents=True, exist_ok=True)
        app = QApplication.instance() or QApplication(sys.argv[:1])

        def pump(ms):
            loop = QEventLoop()
            QTimer.singleShot(ms, loop.quit)
            loop.exec()

        window = GetPolicyWindow(enable_policy_list=False)
        window.resize(1100, 300)
        window.show()
        pump(300)
        window.grab().save(str(out_dir / "polview_window.png"), "PNG")
        window._show_help()
        pump(300)
        window._dialogs[-1].grab().save(str(out_dir / "polview_help.png"), "PNG")
        print(json.dumps({
            "out_dir": str(out_dir),
            "shortcuts": [s.key().toString() for s in window._shortcuts],
            "help_rows": [key for key, _ in SHORTCUTS if key],
        }, indent=2), flush=True)
        window.close()
        window._loader.shutdown()
        pump(100)
    os._exit(0)


if __name__ == "__main__":
    main()
