"""Launch the real Audit window, open the File Source editor in-app, screenshot it.

Verifies the Phase 2 wiring (New Query → File Source → new editor) renders inside
the actual AuditWindow chrome. No DB2 connection is made (only DSN strings are
read). A hard timer quits the app even if something stalls.

Usage:
    venv\\Scripts\\python.exe tools/show_audit_file_source.py [output_png]
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
        "policy,state,claim_amount,status\nR2001,FL,9100.00,OPEN\nR2002,TX,4400.00,OPEN\n",
        encoding="utf-8")
    fds = infer_file_source_from_file(claims, name="Claims")
    fds.description = "Claims extracts (direct + reinsurance), same layout"
    fds.tags = ["claims", "audit"]
    add_member_file(fds, str(rga))
    return fds


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "audit_file_source.png")

    app = QApplication(sys.argv)
    from suiteview.audit.audit_window import AuditWindow

    win = AuditWindow()
    win.resize(1320, 840)
    win.show()

    def go():
        try:
            win.open_file_source(_build_sample())
        except Exception as exc:
            print(f"open_file_source failed: {exc}")
            try:
                win.new_file_source()
            except Exception as exc2:
                print(f"new_file_source failed: {exc2}")
        QTimer.singleShot(500, capture)

    def capture():
        ok = win.grab().save(output, "PNG")
        print(f"{'Saved' if ok else 'FAILED to save'} {output}")
        app.quit()

    QTimer.singleShot(500, go)
    QTimer.singleShot(8000, app.quit)  # hard backstop
    app.exec()


if __name__ == "__main__":
    main()
