"""Verify Phase 2c (Visual builder over a File Source) end-to-end in the app.

Builds + saves a File Source, opens a Visual Query designer targeted at it
(picker populated from the stored schema, no ODBC), runs it through DuckDB, and
screenshots the results. No DB2.

Usage:
    venv\\Scripts\\python.exe tools/show_audit_visual_file_query.py [output_png]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def _build_and_save_source():
    from suiteview.audit import file_source_store
    from suiteview.audit.file_source_intake import (
        add_member_file, infer_file_source_from_file)

    base = Path.home() / ".suiteview"
    base.mkdir(parents=True, exist_ok=True)
    claims = base / "CLAIMS.csv"
    claims.write_text(
        "policy,state,claim_amount,status\n"
        "P1001,TX,1500.00,OPEN\nP1002,CA,3200.50,CLOSED\nP1003,TX,875.25,OPEN\n",
        encoding="utf-8")
    rga = base / "RGACLAIMS.csv"
    rga.write_text(
        "policy,state,claim_amount,status\nR2001,FL,9100.00,OPEN\nR2002,TX,4400.00,OPEN\n",
        encoding="utf-8")
    fds = infer_file_source_from_file(claims, name="Claims")
    add_member_file(fds, str(rga))
    file_source_store.save_file_source(fds)
    return fds


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / ".suiteview" / "audit_visual_file_query.png")

    app = QApplication(sys.argv)
    from suiteview.audit.audit_window import AuditWindow

    win = AuditWindow()
    win.resize(1320, 840)
    win.show()

    def go():
        try:
            fds = _build_and_save_source()
            win._open_visual_query_on_file_source(fds.id)
            name = win._active_unpinned
            dq = win._dynamic_queries[name]
            # Pick the first member as the source table and run SELECT * (DuckDB).
            dq.tables = [fds.table_names[0]]
            dq.joins_tab.update_tables(dq.tables)
            dq.txt_max_count.setText("25")
            dq._run_audit()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"flow failed: {exc}")
        QTimer.singleShot(2500, capture)

    def capture():
        ok = win.grab().save(output, "PNG")
        print(f"{'Saved' if ok else 'FAILED to save'} {output}")
        app.quit()

    QTimer.singleShot(500, go)
    QTimer.singleShot(12000, app.quit)
    app.exec()


if __name__ == "__main__":
    main()
