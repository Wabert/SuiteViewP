"""Screenshot the Object Browser's new Data Source *dashboard* canvas.

Seeds a couple of File Sources, opens the unified browser to the Data Sources
tab, selects a File Source node, and captures the source-dashboard detail view
(header badge + health pill + Setup/Tables/Columns/Used-by panels) that replaced
the borrowed QueryObject tabs. No DB2.

Usage:
    venv\\Scripts\\python.exe tools/show_source_dashboard.py [output_png]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def _seed():
    from suiteview.audit import file_source_store
    from suiteview.audit.file_source_intake import add_member_file, infer_file_source_from_file

    base = Path.home() / ".suiteview"
    base.mkdir(parents=True, exist_ok=True)
    claims = base / "CLAIMS.csv"
    claims.write_text("policy,state,claim_amount,status\nP1,TX,100,OPEN\n", encoding="utf-8")
    rga = base / "RGACLAIMS.csv"
    rga.write_text("policy,state,claim_amount,status\nR1,FL,900,OPEN\n", encoding="utf-8")
    c = infer_file_source_from_file(claims, name="Claims Extract")
    add_member_file(c, str(rga))
    file_source_store.save_file_source(c)


def _select_first_file_source(win):
    tree = win.source_tree
    for i in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(i)
        for j in range(group.childCount()):
            child = group.child(j)
            payload = child.data(0, Qt.ItemDataRole.UserRole) or {}
            if payload.get("type") == "file_data_source":
                tree.setCurrentItem(child)
                return True
    return False


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "source_dashboard.png")

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
            win.source_tree.expandAll()
            if not _select_first_file_source(win):
                print("no file_data_source node found")
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
