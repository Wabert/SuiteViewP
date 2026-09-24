"""Render the Query SQL Assist picker in ODBC and Files modes (no database access).

Uses a synthetic File Source and a fake ODBC DSN, clicks the ODBC/Files toggle,
and reports the combo contents per mode as JSON.

Usage:
    venv\\Scripts\\python.exe tools/app/verify_sql_assist_source_toggle.py [--screenshot <dir>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", help="Directory for odbc.png / files.png")
    args = parser.parse_args()

    from suiteview.audit.field_picker_panel import FieldPickerPanel
    from suiteview.audit.file_source import SOURCE_TYPE_EXCEL

    app = QApplication.instance() or QApplication([])
    fds = SimpleNamespace(
        id="demo0001", name="Claims Extract", source_type=SOURCE_TYPE_EXCEL, parse_spec={},
        members=[SimpleNamespace(resolved_table_name=lambda: "claims")],
        columns=[SimpleNamespace(name=n, data_type="VARCHAR") for n in ("CLAIM_ID", "POLICY", "AMOUNT")],
    )
    out_dir = Path(args.screenshot) if args.screenshot else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {}
    with patch("suiteview.audit.file_source_store.list_file_sources", return_value=[fds]), \
            patch("suiteview.audit.file_query_runner.resolve_file_source",
                  side_effect=lambda ref: fds if ref == fds.id else None):
        picker = FieldPickerPanel()
        picker.resize(480, 360)
        picker.set_connection_options([("NEON_DSN (NEON_DSN)", "NEON_DSN")], "NEON_DSN")
        picker.show()
        for mode in ("odbc", "files"):
            if mode == "files":
                picker.btn_source_kind.click()
            app.processEvents()
            report[mode] = {
                "button": picker.btn_source_kind.text(),
                "connection": picker.current_connection(),
                "label": picker.current_connection_label(),
                "tables": [picker.list_tables.item(i).text() for i in range(picker.list_tables.count())],
                "fields": [picker.list_fields.item(i).text() for i in range(picker.list_fields.count())],
            }
            if out_dir:
                picker.grab().save(str(out_dir / f"{mode}.png"))
        picker.close()

    report["all_ok"] = (
        report["odbc"]["button"] == "ODBC"
        and report["odbc"]["connection"] == "NEON_DSN"
        and report["files"]["button"] == "Files"
        and report["files"]["connection"] == "file:demo0001"
        and report["files"]["tables"] == ["claims"]
    )
    print(json.dumps(report, indent=2))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
