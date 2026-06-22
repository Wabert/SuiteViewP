"""Render the NEW File Source editor to a PNG for design review.

Builds a realistic source the way a user would (infer from a first file, then add
a second file of the same type via the intake/validation path), loads it into the
editor, runs a preview, and saves ``widget.grab()`` to a PNG. No DB2 needed.

Usage:
    venv\\Scripts\\python.exe tools/show_new_file_source_editor.py [output_png]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def _build_sample():
    from suiteview.audit.file_source_intake import (
        add_member_file, infer_file_source_from_file)

    base = Path.home() / ".suiteview"
    base.mkdir(parents=True, exist_ok=True)
    claims = base / "CLAIMS.csv"
    claims.write_text(
        "policy,state,claim_amount,status\n"
        "P1001,TX,1500.00,OPEN\nP1002,CA,3200.50,CLOSED\nP1003,NY,875.25,OPEN\n",
        encoding="utf-8")
    rga = base / "RGACLAIMS.csv"
    rga.write_text(
        "policy,state,claim_amount,status\n"
        "R2001,FL,9100.00,OPEN\nR2002,TX,4400.00,OPEN\n",
        encoding="utf-8")

    fds = infer_file_source_from_file(claims, name="Claims")
    fds.description = "Claims extracts (direct + reinsurance), same layout"
    fds.tags = ["claims", "audit"]
    add_member_file(fds, str(rga))
    return fds


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "new_file_source_editor.png")

    app = QApplication(sys.argv)
    from suiteview.audit.tabs.file_source_editor import FileSourceEditor

    editor = FileSourceEditor()
    editor.resize(1180, 760)
    try:
        editor.load_file_source(_build_sample())
    except Exception as exc:
        print(f"(sample load skipped: {exc})")
    editor.show()

    def capture():
        try:
            editor.list_members.setCurrentRow(0)
            editor._preview_selected()
        except Exception as exc:
            print(f"(preview skipped: {exc})")
        ok = editor.grab().save(output, "PNG")
        print(f"{'Saved' if ok else 'FAILED to save'} {output}")
        app.quit()

    QTimer.singleShot(600, capture)
    app.exec()


if __name__ == "__main__":
    main()
