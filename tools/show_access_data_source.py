"""Screenshot the Object Browser's registered MS Access data source (Phase 4 3b).

Seeds a registered Access data source (pointing at a placeholder .accdb so the
existence check passes), opens the browser to the Data Sources tab, selects the
Access node, and captures its dashboard. The Access ODBC driver is not needed to
render — table listing degrades to empty without it.

Usage:
    venv\\Scripts\\python.exe tools/show_access_data_source.py [output_png]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def _seed():
    from suiteview.audit import data_source_store
    from suiteview.audit.data_source import KIND_ACCESS, RegisteredDataSource

    base = Path.home() / ".suiteview"
    base.mkdir(parents=True, exist_ok=True)
    accdb = base / "ClaimsArchive.accdb"
    if not accdb.exists():
        accdb.write_bytes(b"placeholder")  # existence only; not a real Access DB

    ds = RegisteredDataSource(
        name="Claims Archive", kind=KIND_ACCESS, path=str(accdb), dialect="ACCESS",
        notes="legacy claims back-office database")
    data_source_store.save_data_source(ds)
    return ds.id


def _select_access(win):
    tree = win.source_tree
    for i in range(tree.topLevelItemCount()):
        group = tree.topLevelItem(i)
        for j in range(group.childCount()):
            child = group.child(j)
            payload = child.data(0, Qt.ItemDataRole.UserRole) or {}
            if payload.get("type") == "access_source":
                tree.setCurrentItem(child)
                return True
    return False


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "access_data_source.png")

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
            if not _select_access(win):
                print("access_source node not found")
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
