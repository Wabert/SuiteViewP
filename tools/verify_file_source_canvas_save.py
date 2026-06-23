"""Headless end-to-end check of the File Source canvas Save round-trip.

The Data Sources dashboard is now the single editable File Source screen, so its
Save must persist edits made in place (description + column name/type). This
seeds a source, selects it in the real window, programmatically edits the
dashboard widgets, fires Save, then reloads from the store and asserts the edits
stuck. No GUI dialogs, no DB2.

Usage:
    venv\\Scripts\\python.exe tools/verify_file_source_canvas_save.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Isolate the file-source store so this never touches real saved sources.
_TMP = tempfile.mkdtemp(prefix="fs_canvas_verify_")
os.environ["SUITEVIEW_FILE_SOURCES_DIR"] = _TMP

from PyQt6.QtCore import Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def _seed():
    from suiteview.audit import file_source_store
    from suiteview.audit.file_source_intake import infer_file_source_from_file

    base = Path(_TMP)
    claims = base / "CLAIMS.csv"
    claims.write_text("policy,state,amount\nP1,TX,100\n", encoding="utf-8")
    fds = infer_file_source_from_file(claims, name="Claims")
    file_source_store.save_file_source(fds)
    return fds.id


def _select(win, fs_id):
    tree = win.source_tree
    win.source_tree.expandAll()

    def walk(item):
        payload = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if payload.get("file_source_id") == fs_id:
            return item
        for i in range(item.childCount()):
            found = walk(item.child(i))
            if found:
                return found
        return None

    for i in range(tree.topLevelItemCount()):
        node = walk(tree.topLevelItem(i))
        if node:
            tree.setCurrentItem(node)
            return True
    return False


def main():
    app = QApplication(sys.argv)
    fs_id = _seed()
    from suiteview.audit import file_source_store
    from suiteview.audit.query_object_viewer_window import QueryObjectViewerWindow

    win = QueryObjectViewerWindow.show_instance(parent=None)
    result = {"ok": False}

    def go():
        try:
            for i in range(win.left_tabs.count()):
                if win.left_tabs.tabText(i) == "Data Sources":
                    win.left_tabs.setCurrentIndex(i)
                    break
            assert _select(win, fs_id), "file source node not found"
            dash = win._source_dashboard

            # Edit in place: description + rename a column + change its type.
            dash.edit_src_desc.setText("edited in canvas")
            name_item = dash.tbl_columns_edit.item(0, 0)
            name_item.setText("policy_no")
            dash.tbl_columns_edit.cellWidget(2, 1).setCurrentText("DECIMAL")
            dash.set_dirty(True)

            win._on_source_save()

            reloaded = file_source_store.load_file_source_by_id(fs_id)
            checks = {
                "description": reloaded.description == "edited in canvas",
                "column_renamed": reloaded.columns[0].name == "policy_no",
                "parse_spec_renamed":
                    reloaded.parse_spec.get("column_names", [None])[0] == "policy_no",
                "type_changed": reloaded.columns[2].data_type == "DECIMAL",
            }
            result["checks"] = checks
            result["ok"] = all(checks.values())
        except Exception as exc:
            import traceback
            traceback.print_exc()
            result["error"] = str(exc)
        finally:
            app.quit()

    QTimer.singleShot(400, go)
    QTimer.singleShot(8000, app.quit)
    app.exec()

    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
