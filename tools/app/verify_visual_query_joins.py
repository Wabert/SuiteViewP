"""Render the Visual Query Joins canvas with a database table + a file dataset (no DB).

Builds SQL Assist (multi-source) beside a Visual Query, using a synthetic CSV File
Source written to a temp folder and fake ODBC metadata. Drops both tables on the
Joins canvas, draws a join line, sets it to a Left join, then runs the federated
query end-to-end: the real file reader + DuckDB, with an in-memory stand-in for
the DB2 fetch that records the pushed-down SQL.

Usage:
    venv\\Scripts\\python.exe tools/app/verify_visual_query_joins.py [--screenshot <dir>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QMimeData, QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QWidget  # noqa: E402

POL = "DB2TAB.LH_BAS_POL"
CSV_TABLE = "UL_SLR_202606"


class _FakeSession:
    def __init__(self, frame, key):
        self.frame, self.key, self.sql = frame, key, []

    def column_types(self, dsn, table):
        return {"CK_POLICY_NBR": "CHAR", "TCH_POL_ID": "CHAR", "POL_PRM_AMT": "DECIMAL"}

    def fetch(self, dsn, sql):
        self.sql.append(sql)
        match = re.search(rf'"{self.key}" IN \((.*?)\)', sql, re.S)
        df = self.frame
        if match:
            wanted = {v.strip().strip("'") for v in match.group(1).split(",")}
            df = df[df[self.key].str.strip().isin(wanted)]
        return df.reset_index(drop=True)

    def close(self):
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", help="Directory for joins.png / sql_assist.png")
    args = parser.parse_args()

    import pandas as pd

    from suiteview.audit.dataforge.join_canvas_view import JoinLineItem
    from suiteview.audit.dynamic_group import DynamicQuery
    from suiteview.audit.federated_query import execute_federated_plan
    from suiteview.audit.field_picker_panel import FieldPickerPanel
    from suiteview.audit.file_source import FileColumn, FileDataSource, FileMember
    from suiteview.audit.query_sources import TABLE_DRAG_MIME, file_token

    app = QApplication.instance() or QApplication([])
    out_dir = Path(args.screenshot) if args.screenshot else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    tmp = tempfile.TemporaryDirectory()
    csv_path = Path(tmp.name) / f"{CSV_TABLE}.csv"
    csv_path.write_text("PolicyId,Stat Res - Gross Basic Reserve\n000123,1500.25\n000456,99.10\n"
                        "000777,12.00\n", encoding="utf-8")
    fds = FileDataSource(
        name="UL_SLR", source_type="csv",
        parse_spec={"delimiter": ",", "has_header": True, "encoding": "utf-8"},
        columns=[FileColumn("PolicyId", "TEXT"),
                 FileColumn("Stat Res - Gross Basic Reserve", "DOUBLE")],
        members=[FileMember(path=str(csv_path), table_name=CSV_TABLE)],
        id="verifyjoins",
    )
    token = file_token(fds)
    report: dict = {}

    with patch("suiteview.audit.file_source_store.list_file_sources", return_value=[fds]), \
            patch("suiteview.audit.file_query_runner.resolve_file_source",
                  side_effect=lambda ref: fds if ref == fds.id else None):
        host = QWidget()
        host.resize(1280, 640)
        lay = QHBoxLayout(host)
        picker = FieldPickerPanel(multi_source=True)
        picker._load_fields = lambda table: picker._populate_fields(
            table, picker._field_cache.get(table) or [
                ("CK_POLICY_NBR", "CHAR", 20, "No", True),
                ("TCH_POL_ID", "CHAR", 14, "No", True),
                ("POL_PRM_AMT", "DECIMAL", 11, "Yes", False)])
        group = DynamicQuery("\u25b8 Visual Query", "NEON_DSN", [POL])
        lay.addWidget(picker, 0)
        lay.addWidget(group, 1)

        picker.table_sources_changed.connect(group.set_table_sources)
        picker.tables_changed.connect(group.set_tables)
        picker.pinned_tables_changed.connect(group.set_pinned_tables)
        picker.set_connection_options([("NEON_DSN (NEON_DSN)", "NEON_DSN")], "NEON_DSN")
        picker.set_group("NEON_DSN", [POL], {}, pinned_tables=[POL])
        group.set_pinned_tables([POL])
        group.joins_tab.set_table_columns(POL, ["CK_POLICY_NBR", "TCH_POL_ID", "POL_PRM_AMT"])

        with patch("suiteview.audit.dialogs.add_file_tables_dialog.AddFileTablesDialog.exec",
                   return_value=1), \
                patch("suiteview.audit.dialogs.add_file_tables_dialog.AddFileTablesDialog.get_selected",
                      return_value=[(token, CSV_TABLE)]):
            picker.btn_source_kind.click()  # Files: +Table browses file datasets
            report["add_table_enabled_in_files_mode"] = picker.btn_add_table.isEnabled()
            picker.btn_add_table.click()
        report["sql_assist_tables"] = [
            picker.list_tables.item(i).data(0x0100) for i in range(picker.list_tables.count())
            if picker.list_tables.item(i).data(0x0100) != "__separator__"]

        group.tab_widget.setCurrentWidget(group.joins_tab)
        host.show()
        app.processEvents()
        report["empty_canvas_hint"] = bool(group.joins_tab.view.empty_text)
        if out_dir:
            group.grab().save(str(out_dir / "joins_empty.png"))
        mime = QMimeData()
        mime.setData(TABLE_DRAG_MIME, CSV_TABLE.encode())
        group.joins_tab._handle_external_drop(mime, QPointF(30, 30))
        mime = QMimeData()
        mime.setData(TABLE_DRAG_MIME, POL.encode())
        group.joins_tab._handle_external_drop(mime, QPointF(340, 60))
        linked = group.joins_tab.scene.add_link(CSV_TABLE, "PolicyId", POL, "CK_POLICY_NBR")
        line = next(i for i in group.joins_tab.scene.items() if isinstance(i, JoinLineItem))
        menu = group.joins_tab._build_join_menu(line)
        next(a for a in menu.actions() if a.text().startswith("Left join")).trigger()
        app.processEvents()
        report["canvas_tables"] = group.joins_tab.canvas_tables()
        report["linked"] = linked
        report["join_infos"] = group.joins_tab.get_join_infos()
        report["file_badge"] = group.joins_tab.scene.box_items[CSV_TABLE].tag
        if out_dir:
            group.grab().save(str(out_dir / "joins.png"))
            picker.grab().save(str(out_dir / "sql_assist.png"))

        tab = group._criteria_tabs[0]
        tab.add_field_auto(CSV_TABLE, "PolicyId", "TEXT", "PolicyId")
        tab.add_field_auto(POL, "TCH_POL_ID", "CHAR", "TCH_POL_ID")
        tab.grid.field(f"{CSV_TABLE}.PolicyId").txt.setText("000")
        prepared = group._prepare_query()
        report["federated"] = prepared is not None and prepared.plan is not None
        db2 = pd.DataFrame({
            "CK_POLICY_NBR": ["000123   ", "000456   ", "000999   "],
            "TCH_POL_ID": ["000123  QA", "000456  QB", "000999  QC"],
        })
        session = _FakeSession(db2, "CK_POLICY_NBR")
        df = execute_federated_plan(prepared.plan, session=session)
        report["pushdown_sql"] = session.sql
        report["result"] = df.astype(object).where(df.notnull(), None).to_dict(orient="records")
        if out_dir:
            (out_dir / "sql.txt").write_text(prepared.sql, encoding="utf-8")
        host.close()
    tmp.cleanup()

    rows = {r["PolicyId"]: r["TCH_POL_ID"] for r in report["result"]}
    report["all_ok"] = bool(
        report["add_table_enabled_in_files_mode"]
        and report["sql_assist_tables"] == [POL, CSV_TABLE]
        and report["canvas_tables"] == [CSV_TABLE, POL]
        and report["linked"]
        and report["join_infos"][0]["join_type"] == "LEFT OUTER JOIN"
        and report["file_badge"] == "CSV"
        and report["federated"]
        and "IN ('000123', '000456', '000777')" in report["pushdown_sql"][0]
        and rows == {"000123": "000123  QA", "000456": "000456  QB", "000777": None}
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
