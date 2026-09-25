"""Native check of Paste Policy List, join suggestions and canvas plan badges (no DB).

Puts Excel-style rows on the real clipboard, opens the Paste Policy List dialog
from the Visual Query's Joins tab, accepts it, then adds LH_COV_PHA so a join is
suggested, accepts the suggestion and runs the federated query with an in-memory
stand-in for DB2 (the real pasted-list loader and DuckDB are used).

Usage:
    venv\\Scripts\\python.exe tools/app/verify_policy_list_paste.py [--screenshot <dir>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

POL = "DB2TAB.LH_BAS_POL"
COV = "DB2TAB.LH_COV_PHA"
POL_COLS = ["CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID", "CK_POLICY_NBR", "POL_PRM_AMT"]
COV_COLS = ["CK_SYS_CD", "CK_CMP_CD", "TCH_POL_ID", "COV_PHA_NBR", "PLN_DES_SER_CD"]
CLIPBOARD = ("Policy\tCo\tAgent note\n"
             "U0532652\t1\tcall back\n"
             "E0213651\t1\t\n"
             "000226237\t26\t\n"
             "U0532652\t01\tduplicate\n")


class _FakeDb2:
    """Serves LH_BAS_POL / LH_COV_PHA from memory, honouring IN (...) pushdown."""

    def __init__(self, frames):
        self.frames, self.sql = frames, []

    def column_types(self, dsn, table):
        return {c: "CHAR" for c in self.frames[table].columns}

    def fetch(self, dsn, sql):
        self.sql.append(sql)
        table = POL if "LH_BAS_POL" in sql else COV
        df = self.frames[table]
        match = re.search(r'"(\w+)" IN \((.*?)\)', sql, re.S)
        if match:
            wanted = {v.strip().strip("'") for v in match.group(2).split(",")}
            df = df[df[match.group(1)].str.strip().isin(wanted)]
        for col, op, value in re.findall(r'"(\w+)" (>=|<=) \'([^\']*)\'', sql):
            df = df[df[col] >= value] if op == ">=" else df[df[col] <= value]
        return df.reset_index(drop=True)

    def close(self):
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", help="Directory for the PNG captures")
    args = parser.parse_args()

    import traceback

    # PyQt6 aborts the process on an exception inside a slot; print it instead.
    sys.excepthook = lambda *exc: traceback.print_exception(*exc)

    import pandas as pd

    from suiteview.audit.dialogs import tables_dialog
    from suiteview.audit.dialogs.pasted_list_dialog import PastedListDialog
    from suiteview.audit.dynamic_group import DynamicQuery
    from suiteview.audit.federated_query import execute_federated_plan

    app = QApplication.instance() or QApplication([])
    out = Path(args.screenshot) if args.screenshot else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    report: dict = {}

    clipboard = QApplication.clipboard()
    previous_clipboard = clipboard.text()
    clipboard.setText(CLIPBOARD)

    group = DynamicQuery("\u25b8 Visual Query", "NEON_DSN", [])
    group.resize(1100, 640)
    group.tab_widget.setCurrentWidget(group.joins_tab)
    group.show()
    app.processEvents()

    original_exec = PastedListDialog.exec

    def exec_and_capture(dialog):
        dialog.resize(640, 420)
        dialog.show()
        app.processEvents()
        report["dialog_columns"] = dialog.column_names()
        report["dialog_count"] = dialog.lbl_count.text()
        if out:
            dialog.grab().save(str(out / "paste_dialog.png"))
        dialog.rename_column(2, "Note")
        report["dialog_columns_renamed"] = dialog.column_names()
        QTimer.singleShot(0, dialog.accept)
        return original_exec(dialog)

    with patch.object(PastedListDialog, "exec", exec_and_capture):
        group.joins_tab.btn_paste_list.click()
    clipboard.setText(previous_clipboard)

    name = "PastedList"
    report["inline"] = group.inline_tables.get(name)
    report["joins_after_paste"] = group.joins_tab.get_join_infos()

    view = group.open_table_view(name)
    app.processEvents()
    report["table_view_rows"] = len(view.table.df)
    report["table_view_limit"] = view.row_limit()
    if out:
        view.grab().save(str(out / "table_view.png"))
    view.close()

    for table, cols in ((POL, POL_COLS), (COV, COV_COLS)):
        group.set_pinned_tables([*group.pinned_tables, table])
        group.joins_tab.set_table_columns(table, cols)
        group.joins_tab.ensure_on_canvas(table)
        app.processEvents()
        report.setdefault("suggested", []).append(group.joins_tab.lbl_suggestion.text())
        group.joins_tab.accept_all_suggestions()
        if table == POL:
            # Every pasted row stays in the result, found or not.
            join = group.joins_tab.model.find_join(name, POL)
            group.joins_tab.model.set_how(
                name, POL, "left" if join is not None and join.left_source == name else "right")
            group.joins_tab.scene.rebuild()
    report["join"] = group.joins_tab.get_join_infos()
    if out:
        group.grab().save(str(out / "after_joins.png"))

    tab = group._criteria_tabs[0]
    group.select_tab.add_field(f"{name}.PolicyNumber", "PolicyNumber")
    group.select_tab.add_field(f"{name}.Note", "Note")
    group.select_tab.add_field(f"{POL}.TCH_POL_ID", "TCH_POL_ID")
    group.select_tab.add_field(f"{COV}.PLN_DES_SER_CD", "PLN_DES_SER_CD")
    tab.add_field_auto(COV, "COV_PHA_NBR", "SMALLINT", "COV_PHA_NBR")
    row = tab.grid.field(f"{COV}.COV_PHA_NBR")
    row.txt.setText("1")
    row.txt_hi.setText("1")
    group.refresh_plan_badges()
    app.processEvents()
    report["badges_final"] = group.joins_tab.box_status()
    if out:
        group.tab_widget.setCurrentWidget(group.joins_tab)
        app.processEvents()
        group.grab().save(str(out / "final_canvas.png"))

    prepared = group._prepare_query()
    db2 = _FakeDb2({
        POL: pd.DataFrame({"CK_SYS_CD": ["I", "I"], "CK_CMP_CD": ["01", "26"],
                           "TCH_POL_ID": ["U0532652  QA", "000226237 QB"],
                           "CK_POLICY_NBR": ["U0532652", "000226237"],
                           "POL_PRM_AMT": ["10.00", "20.00"]}),
        COV: pd.DataFrame({"CK_SYS_CD": ["I", "I", "I"], "CK_CMP_CD": ["01", "01", "26"],
                           "TCH_POL_ID": ["U0532652  QA", "U0532652  QA", "000226237 QB"],
                           "COV_PHA_NBR": ["1", "2", "1"],
                           "PLN_DES_SER_CD": ["1U143900", "1U535A00", "NU1F3H00"]}),
    })
    df = execute_federated_plan(prepared.plan, session=db2)
    report["staging_sql"] = db2.sql
    report["result"] = df.astype(object).where(df.notnull(), None).to_dict(orient="records")
    if out:
        (out / "sql.txt").write_text(prepared.sql, encoding="utf-8")
    group.close()

    by_policy = {}
    for r in report["result"]:
        by_policy.setdefault(r["PolicyNumber"], r)
    pol_join = next((j for j in report["join"]
                     if {j["left_table"], j["right_table"]} == {name, POL}), {})
    report["all_ok"] = bool(
        report["dialog_columns"] == ["PolicyNumber", "CompanyCode", "Agent note"]
        and report["dialog_columns_renamed"] == ["PolicyNumber", "CompanyCode", "Note"]
        and report["dialog_count"] == "4 rows"
        and report["inline"]["columns"] == ["PolicyNumber", "CompanyCode", "Note"]
        and [r[:2] for r in report["inline"]["rows"]] == [
            ["U0532652", "01"], ["E0213651", "01"], ["000226237", "26"], ["U0532652", "01"]]
        and report["joins_after_paste"] == []
        and report["table_view_rows"] == 4 and report["table_view_limit"] == 1000
        and sorted(tuple(sorted(pair)) for pair in pol_join.get("on_pairs", [])) == [
            ("CK_CMP_CD", "CompanyCode"), ("CK_POLICY_NBR", "PolicyNumber")]
        and (pol_join.get("join_type") == "LEFT OUTER JOIN") == (pol_join.get("left_table") == name)
        and "TCH_POL_ID" in report["badges_final"].get(COV, ("", "", ""))[2]
        and len(report["staging_sql"]) == 2
        and len(report["result"]) == 3  # COV_PHA_NBR = 1 drops E0213651 (no coverage)
        and by_policy["U0532652"]["PLN_DES_SER_CD"] == "1U143900"
        and by_policy["000226237"]["PLN_DES_SER_CD"] == "NU1F3H00"
        and not tables_dialog._OPEN_TABLE_VIEWS
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())