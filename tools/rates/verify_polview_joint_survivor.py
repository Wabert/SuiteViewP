"""Read-only check of PolView's joint survivor (second-to-die) UL rate view.

Runs in-force company-26 joint survivor phases through the real PolView path
(``policy_service.get_policy_info`` -> ``pi.rates.rates_joint_survivor``)
and compares the calculated current-year joint COI with CyberLife's stored
``LH_COV_INS_RNL_RT`` type C, JT_INS_IND 0 ``RNL_RT``. Nothing is written to
DB2 or UL_Rates.

Usage (venv\\Scripts\\python.exe):
    tools\\rates\\verify_polview_joint_survivor.py '{"all": true, "output": "<report.json>"}'
    tools\\rates\\verify_polview_joint_survivor.py '{"policy": "000313486", "coverage": 1,
        "screenshot": "<png>"}'

Keys: ``all`` (every in-force phase of the 12 plans), ``policy``/``company``/
``region``/``coverage`` (one phase; ``coverage`` is PolView's 1-based index),
``as_of`` (ISO date; default each policy's valuation date), ``output`` (JSON
report with per-phase detail), ``screenshot`` (renders PolView's Rates view).
Stdout carries aggregates only (no policy numbers).
"""

from __future__ import annotations

import collections
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.json_store import write_json  # noqa: E402
from suiteview.core.local_dev import local_data_enabled  # noqa: E402
from suiteview.polview.services.policy_service import get_policy_info  # noqa: E402

PLANS = ("N91EMA00", "N91EMB00", "N91EAA00", "N91EAJ00", "N91EAB00", "N91EAN00",
         "B11EP200", "B11EP400", "N71EMR00", "N71EMJ00", "N71EP100", "N71EP300")


def in_force_phases(region: str) -> list[tuple[str, str, int, str]]:
    """(policy number, company, phase, plancode) for every in-force joint phase."""
    import pyodbc
    from suiteview.core.db2_constants import REGION_DSN_MAP

    # Constant plancodes as literals: DataDirect rejects inferred Unicode binds (HY004).
    plan_list = ",".join(f"'{plan}'" for plan in PLANS)
    con = pyodbc.connect(f"DSN={REGION_DSN_MAP[region]}", readonly=True, autocommit=True, timeout=30)
    try:
        rows = con.cursor().execute(f"""
SELECT POL.CK_POLICY_NBR, COV.CK_CMP_CD, COV.COV_PHA_NBR, COV.PLN_DES_SER_CD
FROM DB2TAB.LH_COV_PHA COV
JOIN DB2TAB.LH_BAS_POL POL ON POL.CK_CMP_CD = COV.CK_CMP_CD AND POL.CK_SYS_CD = COV.CK_SYS_CD
 AND POL.TCH_POL_ID = COV.TCH_POL_ID
WHERE COV.CK_SYS_CD = 'I' AND COV.PLN_DES_SER_CD IN ({plan_list})
  AND POL.PRM_PAY_STA_REA_CD < '97'
ORDER BY COV.PLN_DES_SER_CD, POL.CK_POLICY_NBR, COV.COV_PHA_NBR
WITH UR""").fetchall()
    finally:
        con.close()
    return [(str(r[0]).strip(), str(r[1]).strip(), int(r[2]), str(r[3]).strip()) for r in rows]


def load_policy(number: str, company: str, region: str):
    policy = get_policy_info(number, region=region, company_code=company, use_cache=False)
    if policy is None or not policy.exists:
        raise RuntimeError(f"Policy {number}/{company} was not found or live access failed.")
    return policy


def coverage_index(policy, phase: int) -> int:
    phases = [c.cov_pha_nbr for c in policy.coverages.get_coverages()]
    return phases.index(phase) + 1


def phase_result(policy, index: int, as_of: date | None) -> dict:
    if not policy.rates.cov_is_joint_survivor(index):
        raise RuntimeError("PolView does not treat this coverage as joint survivor.")
    js = policy.rates.rates_joint_survivor(index, as_of)
    return {
        "policy": policy.policy_number, "company": policy.company_code, "coverage": index,
        "phase": policy.coverages.get_coverages()[index - 1].cov_pha_nbr, "plancode": js.plancode,
        "rated": bool(js.ratings), "as_of": js.as_of.isoformat(), "year": js.policy_year,
        "stored": js.stored_rate, "calculated": js.calculated_current,
        "status": js.comparison_status, "check": js.comparison_text,
        "primary": vars(js.primary), "joint": vars(js.joint),
        "ratings": [vars(r) for r in js.ratings],
    }


def capture(policy, index: int, output: str) -> dict:
    from PyQt6.QtWidgets import QApplication
    from suiteview.polview.ui.main_window import GetPolicyWindow, joint_survivor_columns

    app = QApplication.instance() or QApplication([])
    window = GetPolicyWindow(enable_policy_list=False)
    try:
        window._policy = policy
        window.lookup_bar.set_policy_display(policy.company_code, policy.policy_number, policy.region)
        window.records_tree.enable_rates_tab(policy)
        window.records_tree.show_rates_tab()
        window._toggle_tree_panel()
        window.resize(1500, 900)
        window.move(60, 40)
        window.show()
        tree = window.records_tree._tree
        parent = tree.topLevelItem(0)
        parent.setExpanded(True)
        item = parent.child(index - 1)
        tree.setCurrentItem(item)
        tree._on_item_clicked(item, 0)
        raw = window.raw_table_tab
        if joint_survivor_columns(raw._current_cols) is None:
            raise RuntimeError(f"Rates view did not show the joint matrix: {raw.table_label.text()}")
        highlighted = raw._normal_grid.model._highlighted_cells
        app.processEvents()
        window.repaint()
        app.processEvents()
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(target), "PNG"):
            raise RuntimeError(f"Could not save screenshot: {target}")
        return {"title": raw.table_label.text(), "columns": raw._current_cols,
                "highlighted_rows": sorted({row for row, _ in highlighted}),
                "status": window.statusBar().currentMessage() if hasattr(window, "statusBar") else ""}
    finally:
        window.close()
        app.processEvents()


def main() -> None:
    arg = sys.argv[1]
    config = json.loads(Path(arg[1:]).read_text(encoding="utf-8")) if arg.startswith("@") else json.loads(arg)
    if local_data_enabled():
        raise RuntimeError("This verification requires live data, not SUITEVIEW_LOCAL_DATA.")
    region = config.get("region", "CKPR")
    as_of = date.fromisoformat(config["as_of"]) if config.get("as_of") else None
    report: dict = {"region": region, "as_of_override": config.get("as_of")}

    if config.get("all"):
        phases = in_force_phases(region)
        grouped = collections.defaultdict(list)
        for number, company, phase, _ in phases:
            grouped[(number, company)].append(phase)
        details, stats, by_plan = [], collections.Counter(), collections.defaultdict(collections.Counter)
        for (number, company), policy_phases in grouped.items():
            policy = load_policy(number, company, region)
            for phase in policy_phases:
                try:
                    result = phase_result(policy, coverage_index(policy, phase), as_of)
                except Exception as exc:  # reported, never hidden
                    result = {"policy": number, "company": company, "phase": phase,
                              "plancode": "", "rated": False, "status": "error", "check": str(exc)}
                details.append(result)
                stats[("rated" if result["rated"] else "std", result["status"])] += 1
                by_plan[result.get("plancode") or "?"][result["status"]] += 1
        summary = {
            "phases": len(details),
            "by_status": {f"{k[0]}/{k[1]}": v for k, v in sorted(stats.items())},
            "by_plan": {plan: dict(counts) for plan, counts in sorted(by_plan.items())},
            "not_matching": [
                {k: d.get(k) for k in ("plancode", "rated", "year", "stored", "calculated", "check")}
                for d in details if d["status"] not in ("match", "prior_year")
            ],
        }
        report.update(summary, details=details)
        print(json.dumps(summary, indent=2, default=str))
    else:
        policy = load_policy(config["policy"], config.get("company", "26"), region)
        index = int(config.get("coverage", 1))
        report["result"] = phase_result(policy, index, as_of)
        print(json.dumps({k: report["result"][k] for k in
                          ("plancode", "rated", "year", "stored", "calculated", "status", "check")},
                         indent=2, default=str))
        if config.get("screenshot"):
            report["screenshot"] = capture(policy, index, config["screenshot"])
            print(json.dumps(report["screenshot"], indent=2, default=str))

    if config.get("output"):
        write_json(config["output"], report)


if __name__ == "__main__":
    main()
