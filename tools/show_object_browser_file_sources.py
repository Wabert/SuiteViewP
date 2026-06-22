"""Screenshot the Object Browser's Data Sources panel with File Sources listed.

Verifies the Phase 3 unified-browser integration. No DB2.

Usage:
    venv\\Scripts\\python.exe tools/show_object_browser_file_sources.py [output_png]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def _seed():
    from suiteview.audit import file_source_store
    from suiteview.audit.file_source_intake import (
        add_member_file, infer_file_source_from_file)

    base = Path.home() / ".suiteview"
    base.mkdir(parents=True, exist_ok=True)
    claims = base / "CLAIMS.csv"
    claims.write_text("policy,state,claim_amount,status\nP1,TX,100,OPEN\n", encoding="utf-8")
    rga = base / "RGACLAIMS.csv"
    rga.write_text("policy,state,claim_amount,status\nR1,FL,900,OPEN\n", encoding="utf-8")
    pol = base / "POLICIES.csv"
    pol.write_text("policy,issue_date,face\nP1,2020-01-01,50000\n", encoding="utf-8")

    c = infer_file_source_from_file(claims, name="Claims")
    add_member_file(c, str(rga))
    file_source_store.save_file_source(c)
    p = infer_file_source_from_file(pol, name="Policies")
    file_source_store.save_file_source(p)


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "object_browser_file_sources.png")

    app = QApplication(sys.argv)
    _seed()
    from suiteview.audit.query_object_viewer_window import QueryObjectViewerWindow

    win = QueryObjectViewerWindow.show_instance(parent=None)
    win.resize(1180, 760)

    def go():
        try:
            for i in range(win.left_tabs.count()):
                if win.left_tabs.tabText(i) == "Data Sources":
                    win.left_tabs.setCurrentIndex(i)
                    break
            win._refresh_source_tree()
            win.source_tree.expandAll()
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
    QTimer.singleShot(10000, app.quit)
    app.exec()


if __name__ == "__main__":
    main()
