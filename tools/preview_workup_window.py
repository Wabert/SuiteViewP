"""Open the Rate Manager window (workup main view) for visual verification.

Usage:
    venv\\Scripts\\python.exe tools/preview_workup_window.py [iaf_path]
        [--topmost] [--auto-analyze] [--converters]

Optionally pre-fills the IAF path (and the other sample files if they exist)
so the Analyze flow can be exercised by hand. Close the window to exit.
"""

import os
import sys

sys.path.insert(0, ".")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from suiteview.ratemanager.ratemanager_window import RateManagerWindow  # noqa: E402

SAMPLES = {
    "iaf": r"docs\RateManager\IAF\1U1F4M00.ISSUEAGE.PRINT.CKAS 02252022.txt",
    "mpf": r"docs\RateManager\MPF\MPF CKAS 2019-04-04.txt",
    "scr": r"docs\RateManager\CKULTB04\CKULTBF4 07-07-2026.txt",
    "epu": r"docs\RateManager\CKULTB01\CKULTB01 (EPU).COMPANY 00.CKPR.TXT",
}


def main():
    app = QApplication(sys.argv)
    win = RateManagerWindow()
    panel = win.workup_panel

    if "--topmost" in sys.argv:
        from PyQt6.QtCore import Qt
        win.setWindowFlags(
            win.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    if "--converters" in sys.argv:
        win._toggle_view()

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    iaf = args[0] if args else SAMPLES["iaf"]
    if os.path.isfile(iaf):
        panel.iaf_edit.setText(os.path.abspath(iaf))
        panel.output_edit.setText(os.path.dirname(os.path.abspath(iaf)))
    for key, edit in (("mpf", panel.mpf_edit), ("scr", panel.scr_edit),
                      ("epu", panel.epu_edit)):
        if os.path.isfile(SAMPLES[key]):
            edit.setText(os.path.abspath(SAMPLES[key]))

    win.show()

    if "--state-dialog" in sys.argv:
        from PyQt6.QtCore import QTimer
        from suiteview.ratemanager.workup.workup_window import _StateMapDialog
        QTimer.singleShot(600, lambda: _StateMapDialog.get_mapping(
            panel, ["01", "07", "19", "29", "31", "42", "99"]))

    if "--auto-analyze" in sys.argv:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, panel._on_analyze)

        def _poll_done():
            if panel.btn_build.isEnabled():
                print("ANALYZE_DONE", flush=True)
            else:
                QTimer.singleShot(2000, _poll_done)
        QTimer.singleShot(2000, _poll_done)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
