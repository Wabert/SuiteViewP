"""Screenshot the File Source "Add (new)" flow on the Data Sources dashboard.

The File Source editor is no longer a separate window — the Data Sources tab's
dashboard IS the single canonical add/edit/view screen. This opens the unified
browser, triggers "+ Add Data Source → File Source", and captures the blank
editable canvas (Setup name/description, empty Columns, Tables tab with the
Add File(s)… / drop affordance). No DB2.

Usage:
    venv\\Scripts\\python.exe tools/show_audit_file_source.py [output_png]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "audit_file_source.png")

    app = QApplication(sys.argv)
    from suiteview.audit.query_object_viewer_window import QueryObjectViewerWindow

    win = QueryObjectViewerWindow.show_instance(parent=None)
    win.resize(1320, 840)

    def go():
        try:
            for i in range(win.left_tabs.count()):
                if win.left_tabs.tabText(i) == "Data Sources":
                    win.left_tabs.setCurrentIndex(i)
                    break
            win._on_add_file_source()  # opens the dashboard in 'new' mode
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"flow failed: {exc}")
        QTimer.singleShot(400, capture)

    def capture():
        ok = win.grab().save(output, "PNG")
        print(f"{'Saved' if ok else 'FAILED to save'} {output}")
        app.quit()

    QTimer.singleShot(500, go)
    QTimer.singleShot(10000, app.quit)  # hard backstop
    app.exec()


if __name__ == "__main__":
    main()
