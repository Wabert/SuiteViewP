"""Render the File Source browser dialog (Phase 3) to a PNG. No DB2.

Usage:
    venv\\Scripts\\python.exe tools/show_file_source_browser.py [output_png]
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
    c.description = "Direct + reinsurance claims extracts"
    add_member_file(c, str(rga))
    file_source_store.save_file_source(c)
    p = infer_file_source_from_file(pol, name="Policies")
    file_source_store.save_file_source(p)


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "file_source_browser.png")

    app = QApplication(sys.argv)
    _seed()
    from suiteview.audit.dialogs.file_source_browser import FileSourceBrowserDialog

    dlg = FileSourceBrowserDialog()
    dlg.resize(560, 420)
    dlg.show()

    def capture():
        ok = dlg.grab().save(output, "PNG")
        print(f"{'Saved' if ok else 'FAILED to save'} {output}")
        app.quit()

    QTimer.singleShot(400, capture)
    app.exec()


if __name__ == "__main__":
    main()
