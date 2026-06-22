"""Render the current File Source (CSV/Excel) editor to a PNG for design review.

Standalone, no DB2 needed. Builds the ``CsvExcelObjectEditor`` widget, loads a
small sample file-backed QueryObject so the populated layout is visible, and
saves ``widget.grab()`` to a PNG. ``grab()`` renders the widget offscreen, so
this does not depend on the window being frontmost or on a live desktop session.

Usage:
    venv\\Scripts\\python.exe tools/show_file_source_editor.py [output_png]

Default output: ~/.suiteview/file_source_editor.png
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def _sample_object():
    """Build a file-backed QueryObject from a small sample CSV (best-effort)."""
    try:
        from suiteview.audit.adhoc_source_intake import query_object_from_file

        sample = Path.home() / ".suiteview" / "_sample_claims.csv"
        sample.parent.mkdir(parents=True, exist_ok=True)
        sample.write_text(
            "policy,state,claim_amount,status\n"
            "P1001,TX,1500.00,OPEN\n"
            "P1002,CA,3200.50,CLOSED\n"
            "P1003,NY,875.25,OPEN\n",
            encoding="utf-8",
        )
        return query_object_from_file(sample, name="Claims")
    except Exception as exc:
        print(f"(sample load skipped: {exc})")
        return None


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "file_source_editor.png")

    app = QApplication(sys.argv)
    from suiteview.audit.tabs.csv_excel_object_editor import CsvExcelObjectEditor

    editor = CsvExcelObjectEditor()
    editor.resize(1180, 760)

    obj = _sample_object()
    if obj is not None:
        try:
            editor.load_object(obj)
        except Exception as exc:
            print(f"(load_object skipped: {exc})")

    editor.show()

    def capture():
        ok = editor.grab().save(output, "PNG")
        print(f"{'Saved' if ok else 'FAILED to save'} {output}")
        app.quit()

    QTimer.singleShot(500, capture)
    app.exec()


if __name__ == "__main__":
    main()
