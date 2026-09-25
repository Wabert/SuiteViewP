"""Render the PolView Tables-panel search (panel + Raw Table matches) to a PNG.

Uses stub cached Policy Record rows so the search box and results grid can be
inspected without a live DB2 connection.

Usage:
    venv\\Scripts\\python.exe tools/app/render_tables_search.py '{"term": "cov", "out": "C:/tmp/search.png"}'

JSON keys (all optional):
    term    search text typed into the Tables search box  (default "cov")
    open    0-based match row to double-click afterwards   (default: none)
    out     output PNG path  (default ~/.suiteview/diagnostics/tables_search.png)
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication, QHBoxLayout, QWidget  # noqa: E402

from suiteview.core.profile_paths import diagnostics_dir  # noqa: E402
from suiteview.polview.services.table_search import search_policy_tables  # noqa: E402
from suiteview.polview.ui.styles import BLUE_BG  # noqa: E402
from suiteview.polview.ui.tabs.raw_table_tab import RawTableTab  # noqa: E402
from suiteview.polview.ui.tree_panel import PolicyRecordTreePanel  # noqa: E402

_POL_ID = "00493109  448D"
_TABLES = {
    "LH_BAS_POL": (
        ["TCH_POL_ID", "CK_CMP_CD", "POL_PRM_AMT", "PRM_PAY_STA_REA_CD"],
        [(_POL_ID, "01", Decimal("1234.56"), "41")],
    ),
    "LH_COV_PHA": (
        ["TCH_POL_ID", "CK_CMP_CD", "COV_PHA_NBR", "PLN_DES_SER_CD", "COV_UNT_QTY"],
        [(_POL_ID, "01", 1, "1U143900  ", Decimal("100.00")),
         (_POL_ID, "01", 2, "1U143900  ", Decimal("25.00"))],
    ),
    "TH_COV_PHA": (
        ["TCH_POL_ID", "COV_PHA_NBR", "INS_CLS_CD"],
        [(_POL_ID, 1, "N"), (_POL_ID, 2, "S")],
    ),
    "LH_SPM_BNF": (
        ["TCH_POL_ID", "COV_PHA_NBR", "SPM_BNF_TYP_CD"],
        [(_POL_ID, 1, "3")],
    ),
}


class _CachedPolicy:
    def cached_table(self, table):
        return _TABLES.get(table)


def main():
    opts = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    term = opts.get("term", "cov")
    out = opts.get("out") or str(diagnostics_dir() / "tables_search.png")
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv[:1])
    host = QWidget()
    host.setStyleSheet(f"background-color: {BLUE_BG};")
    layout = QHBoxLayout(host)
    panel = PolicyRecordTreePanel()
    panel.setFixedWidth(200)
    raw = RawTableTab()
    layout.addWidget(panel)
    layout.addWidget(raw, 1)
    host.resize(980, 420)

    policy = _CachedPolicy()
    opened = {}

    def run_search(text):
        if text:
            raw.show_search_results(search_policy_tables(policy, panel.tables_with_data(), text))

    def open_hit(_record, table, field, row):
        columns, rows = _TABLES[table]
        raw.set_data(columns, rows, table_name=f"Table: {table}", transposed=True)
        raw.focus_field(field, row)
        opened.update(table=table, field=field, row=row)

    panel.search_requested.connect(run_search)
    raw.search_hit_activated.connect(open_hit)
    panel.set_table_presence({table: True for table in _TABLES})
    host.show()
    panel.search_box.setText(term)
    panel.search_box.returnPressed.emit()
    if opts.get("open") is not None:
        raw.activate_search_hit(int(opts["open"]))
    app.processEvents()
    host.grab().save(out, "PNG")

    print(json.dumps({
        "output": out,
        "label": raw.table_label.text(),
        "matches": raw.search_hits_frame().to_dict("records") if raw.showing_search_results else [],
        "opened": opened,
    }, indent=2, default=str))
    host.close()


if __name__ == "__main__":
    main()
