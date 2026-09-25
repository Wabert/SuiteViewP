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
             "226237\t26\tleading zeros lost\n"
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

    from suiteview.audit.dialogs.policy_list_dialog import PolicyListDialog
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

    original_exec = PolicyListDialog.exec

    def exec_and_capture(dialog):
        dialog.resize(760, 480)
        dialog.show()
        app.processEvents()
        report["dialog_summary"] = dialog.lbl_summary.text()
        report["dialog_warnings"] = dialog.lbl_warnings.text()
        if out:
            dialog.grab().save(str(out / "paste_dialog.png"))
        dialog.chk_pad.setChecked(True)  # restore the dropped leading zeros
        report["dialog_summary_padded"] = dialog.lbl_summary.text()
        report["dialog_warnings_padded"] = dialog.lbl_warnings.text()
        QTimer.singleShot(0, dialog.accept)
        return original_exec(dialog)

    with patch.object(PolicyListDialog, "exec", exec_and_capture):
        group.joins_tab.btn_paste_list.click()
    clipboard.setText(previous_clipboard)

    name = "PolicyList"
    group.joins_tab.set_table_columns(POL, POL_COLS)
    report["inline_rows"] = group.inline_tables.get(name, {}).get("rows")
    report["join"] = group.joins_tab.get_join_infos()
    group.refresh_plan_badges()
    app.processEvents()
    report["badges_after_paste"] = group.joins_tab.box_status()
    if out:
        group.grab().save(str(out / "after_paste.png"))

    group.set_pinned_tables([*group.pinned_tables, COV])
    group.joins_tab.set_table_columns(COV, COV_COLS)
    group.joins_tab.ensure_on_canvas(COV)
    app.processEvents()
    report["suggestion_banner"] = group.joins_tab.lbl_suggestion.text()
    report["suggested_keys"] = len(group.joins_tab.scene.suggestion_items)
    if out:
        group.grab().save(str(out / "suggestion.png"))
    group.joins_tab.accept_all_suggestions()

    tab = group._criteria_tabs[0]
    group.select_tab.add_field(f"{name}.PolicyNumber", "PolicyNumber")
    group.select_tab.add_field(f"{name}.Agent note", "Agent note")
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

    by_policy = {r["PolicyNumber"]: r for r in report["result"]}
    report["all_ok"] = bool(
        "leading zeros" in report["dialog_warnings"]
        and report["dialog_warnings_padded"] == ""
        and report["inline_rows"] and [r[0] for r in report["inline_rows"]]
        == ["U0532652", "E0213651", "000226237"]
        and report["join"] and report["join"][0]["join_type"] == "LEFT OUTER JOIN"
        and report["badges_after_paste"].get(name) == ("info", "3 pasted rows")
        and report["badges_after_paste"].get(POL, ("",))[0] == "ok"
        and report["suggested_keys"] == 3
        and "TCH_POL_ID" in report["badges_final"].get(COV, ("", "", ""))[2]
        and "IN ('U0532652', 'E0213651', '000226237')" in report["staging_sql"][0]
        and "IN ('U0532652  QA', '000226237 QB')" in report["staging_sql"][1]
        and by_policy["U0532652"]["PLN_DES_SER_CD"] == "1U143900"
        and by_policy["000226237"]["PLN_DES_SER_CD"] == "NU1F3H00"
        and len(report["result"]) == 2  # COV_PHA_NBR = 1 on the right side filters E0213651
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
