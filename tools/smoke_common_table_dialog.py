"""Smoke-check the Common Tables dialog without saving user data."""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from PyQt6.QtWidgets import QApplication

from suiteview.audit.common_table import CommonTable
from suiteview.audit.common_table_dialog import CommonTableDialog


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = CommonTableDialog(parent=None)

    table = CommonTable(
        name="Smoke_Table",
        description="Two-line\ndescription",
        columns=[
            {"name": "policy", "type": "TEXT"},
            {"name": "amount", "type": "DECIMAL"},
        ],
        rows=[["00123", "12.50"]],
    )
    dialog._load_table(table)

    initial_columns = dialog._get_column_defs()
    initial_rows = dialog._get_data_rows()

    pasted = dialog._paste_exported_table([
        ["TEXT", "INTEGER", "DECIMAL"],
        ["policy", "count", "amount"],
        ["00045", "7", "9.25"],
    ])
    pasted_columns = dialog._get_column_defs()
    pasted_rows = dialog._get_data_rows()

    ok = (
        initial_columns == [
            {"name": "policy", "type": "TEXT"},
            {"name": "amount", "type": "DECIMAL"},
        ]
        and initial_rows == [["00123", "12.50"]]
        and pasted
        and pasted_columns == [
            {"name": "policy", "type": "TEXT"},
            {"name": "count", "type": "INTEGER"},
            {"name": "amount", "type": "DECIMAL"},
        ]
        and pasted_rows == [["00045", "7", "9.25"]]
    )

    dialog.close()
    app.processEvents()
    print(json.dumps({"ok": ok, "columns": pasted_columns, "rows": pasted_rows}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())