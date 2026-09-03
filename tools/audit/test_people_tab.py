"""Verify the Cyberlife query builder's People tab.

The person-name criteria moved off the bottom of Policy (2) onto their own
People tab.  This checks the tab exists in the builder, that the old home no
longer carries the widgets, that the generated SQL picks the filters up from the
new tab, and that the criteria survive a query-object save/load round trip.

Usage:
    venv\\Scripts\\python.exe tools/audit/test_people_tab.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SUITEVIEW_LOCAL_DATA", "1")

from PyQt6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    results = {}
    failures = []

    from suiteview.audit.audit_window import AuditWindow
    from suiteview.audit.tabs.people_tab import PeopleTab
    from suiteview.audit.tabs.policy2_tab import Policy2Tab

    win = AuditWindow()

    # -- 1. The tab is present, right after Policy (2). ------------------
    titles = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    results["tab_titles"] = titles
    if "People" not in titles:
        failures.append("no People tab in the builder")
    elif titles.index("People") != titles.index("Policy (2)") + 1:
        failures.append("People tab is not directly after Policy (2)")
    if not isinstance(win.people_tab, PeopleTab):
        failures.append("win.people_tab is not a PeopleTab")

    # -- 2. Policy (2) no longer owns the person widgets. ----------------
    leftovers = [n for n in ("txt_first_name", "txt_last_name",
                             "cmb_first_name_match", "cmb_last_name_match",
                             "_add_name_row")
                 if hasattr(Policy2Tab, n) or hasattr(win.policy2_tab, n)]
    results["policy2_leftovers"] = leftovers
    if leftovers:
        failures.append(f"Policy (2) still has person widgets: {leftovers}")

    # -- 3. The SQL builder reads the filters from the People tab. -------
    sql_before = win._build_sql()
    results["personinfo_join_before"] = "VH_POL_HAS_LOC_CLT" in sql_before
    if "VH_POL_HAS_LOC_CLT" in sql_before:
        failures.append("person join present with no name criteria entered")

    win.people_tab.txt_last_name.setText("smith")
    win.people_tab.cmb_last_name_match.setCurrentText("Begins with")
    win.people_tab.txt_first_name.setText("jo")
    win.people_tab.cmb_first_name_match.setCurrentText("Contains")
    sql_after = win._build_sql()

    checks = {
        "join": "VH_POL_HAS_LOC_CLT PERSONINFO" in sql_after,
        "last_name_predicate":
            "UPPER(TRIM(PERSONINFO.CK_LST_NM)) LIKE 'SMITH%'" in sql_after,
        "first_name_predicate":
            "UPPER(TRIM(PERSONINFO.CK_FST_NM)) LIKE '%JO%'" in sql_after,
        "result_columns": "PERSONINFO.CK_LST_NM PersonLastName" in sql_after,
    }
    results["sql_checks"] = checks
    for name, passed in checks.items():
        if not passed:
            failures.append(f"SQL missing {name}")

    # -- 4. Criteria round-trip through a saved query object. ------------
    state = win._cyberlife_query_object_state()
    results["people_state"] = state["tabs"].get("people")
    win._on_clear_cyberlife()
    cleared = (win.people_tab.txt_last_name.text(),
               win.people_tab.txt_first_name.text())
    results["after_clear"] = cleared
    if cleared != ("", ""):
        failures.append(f"clear left person criteria behind: {cleared}")

    for key, tab in win._cyberlife_criteria_tabs():
        tab.set_state(state["tabs"].get(key, {}))
    restored = {
        "last": win.people_tab.txt_last_name.text(),
        "last_match": win.people_tab.cmb_last_name_match.currentText(),
        "first": win.people_tab.txt_first_name.text(),
        "first_match": win.people_tab.cmb_first_name_match.currentText(),
    }
    results["after_restore"] = restored
    if restored != {"last": "smith", "last_match": "Begins with",
                    "first": "jo", "first_match": "Contains"}:
        failures.append(f"round-trip lost person criteria: {restored}")

    # -- 5. A query object saved before the People tab existed still loads.
    win._on_clear_cyberlife()
    for key, tab in win._cyberlife_criteria_tabs():
        tab.set_state({})
    results["legacy_load_ok"] = (win.people_tab.txt_first_name.text() == ""
                                 and win.people_tab.cmb_first_name_match
                                 .currentText() == "Exact match")
    if not results["legacy_load_ok"]:
        failures.append("People tab does not default cleanly for legacy objects")

    win.close()
    results["failures"] = failures
    results["all_ok"] = not failures
    print(json.dumps(results, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
