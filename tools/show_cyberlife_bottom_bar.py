"""Screenshot the Cyberlife bottom bar to verify the compact buttons and the
query-name label.

Captures two states: no saved query (label hidden) and with a saved query
(label shown at bottom-left).

Usage:
    venv\\Scripts\\python.exe tools/show_cyberlife_bottom_bar.py [output_prefix]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "cyberlife_bottom_bar")

    app = QApplication(sys.argv)
    from suiteview.audit.main import create_audit_window

    win = create_audit_window()
    win.resize(1215, 720)
    win.show()

    def capture_empty():
        out = f"{prefix}_empty.png"
        ok = win.cyberlife_bottom_bar.grab().save(out, "PNG")
        print(f"{'Saved' if ok else 'FAILED'} {out}")
        QTimer.singleShot(300, capture_named)

    def capture_named():
        win._cyberlife_saved_object_name = "My Saved Query"
        win.btn_save_cyberlife.setVisible(True)
        win._update_cyberlife_query_name_label()
        out = f"{prefix}_named.png"
        ok = win.cyberlife_bottom_bar.grab().save(out, "PNG")
        print(f"{'Saved' if ok else 'FAILED'} {out}")
        app.quit()

    QTimer.singleShot(600, capture_empty)
    QTimer.singleShot(8000, app.quit)
    app.exec()


if __name__ == "__main__":
    main()
