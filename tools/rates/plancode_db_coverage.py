"""Report what UL_Rates schema ``rates`` lacks for each RERUN advanced plancode.

``load_plancode`` takes every plan fact from schema ``rates`` (``plan_facts``) and the
product rules from ``dbo.SV_RERUN_Adv_Plancodes``. For each table row this reports:

``errors``  - the plan cannot be illustrated (not loaded, no GINT, no regular loan rate,
             no ages, a non-engine product family, an unresolvable CINT key, or a
             shadow-account plan without scale S COI/SHADOW_INT/DB_DISCOUNT);
``none``    - read as "none" by product rule (no preferred loan, no safety net, no GPT
             corridor, no MFEE/premium load/EPU cells).

Read-only against UL_Rates. Run it again after rate loads.

Usage::

    venv\\Scripts\\python.exe tools\\rates\\plancode_db_coverage.py --report <out.json>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from suiteview.core.rates_errors import RatesError  # noqa: E402
from suiteview.core.rates_schema import RatesSchemaRepository  # noqa: E402
from suiteview.illustration.models.plan_facts import PlanFacts, read_plan_facts  # noqa: E402
from suiteview.illustration.models.plancode_config import (  # noqa: E402
    plancode_table_name,
    plancode_table_rows,
)

LOAN_FACTS = ("loan_reg_chg", "loan_reg_crd", "loan_pref_chg", "loan_pref_crd")
_CELL_TYPES = ("MFEE", "PREMLOAD_PCT", "EPU", "COI", "SHADOW_INT", "DB_DISCOUNT")


def _cell_scales(repo: RatesSchemaRepository, facts: PlanFacts) -> Dict[str, set]:
    """``{rate type: {scales}}`` loaded on the plan's base (non-benefit) cells."""
    by_schedule: Dict[int, set] = {}
    for a in repo.cell_assignments(facts.company, facts.plancode):
        if not a.benefit and a.rate_type in _CELL_TYPES:
            by_schedule.setdefault(a.schedule_id, set()).add(a.rate_type)
    scales: Dict[str, set] = {}
    for window in repo.schedule_windows(sorted(by_schedule)):
        for rate_type in by_schedule[window.schedule_id]:
            scales.setdefault(rate_type, set()).add(window.scale)
    # DB_DISCOUNT may be a PLAN rate (ULRates.get_rates("DBD") falls back to it).
    for a in repo.plan_assignments(facts.company, facts.plancode):
        if a.rate_type == "DB_DISCOUNT":
            scales.setdefault("DB_DISCOUNT", set()).add(a.scale)
    return scales


def review_row(row: dict, facts: Optional[PlanFacts], scales: Dict[str, set]) -> dict:
    """The plan's findings."""
    result: dict = {"errors": [], "none": []}
    if facts is None:
        result["errors"].append("not loaded in schema rates (PLAN_DEF)")
        return result
    errors, none = result["errors"], result["none"]
    for check in (lambda: facts.engine_family, lambda: facts.cint_key):
        try:
            check()
        except RatesError as exc:
            errors.append(str(exc))
    for label, value in (("MaturityAge", facts.maturity_age),
                         ("PremiumCeaseAge", facts.premium_cease_age)):
        if value is None:
            errors.append(f"PLAN_DEF has no {label}")
    if facts.gint is None:
        errors.append("no PLAN GINT")
    for attr in LOAN_FACTS:
        if getattr(facts, attr) is None:
            (errors if attr.startswith("loan_reg") else none).append(f"no {attr.upper()}")
    if facts.snet_by_issue_age is None:
        none.append("no SNET_PERIOD (no safety net)")
    if facts.corridor_by_age is None:
        none.append("no CORR (no GPT corridor)")
    for rate_type in ("MFEE", "PREMLOAD_PCT", "EPU"):
        if not scales.get(rate_type, set()) & {"C", "G"}:
            none.append(f"no {rate_type} cells")
    if str(row.get("ShadowAvailability", "") or "").strip():
        for rate_type in ("COI", "SHADOW_INT", "DB_DISCOUNT"):
            if "S" not in scales.get(rate_type, set()):
                errors.append(f"shadow account without scale S {rate_type}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", required=True, help="JSON report path")
    args = parser.parse_args()

    rows = plancode_table_rows()
    report = {"table": plancode_table_name(), "rows": len(rows), "plans": {}}
    with RatesSchemaRepository() as repo:
        for row in rows:
            plancode = str(row.get("Plancode", "")).strip()
            try:
                facts = read_plan_facts(repo, plancode)
            except RatesError as exc:
                report["plans"][plancode] = {"errors": [str(exc)]}
                print(f"{plancode}: errors 1", flush=True)
                continue
            scales = _cell_scales(repo, facts) if facts is not None else {}
            found = review_row(row, facts, scales)
            report["plans"][plancode] = {k: v for k, v in found.items() if v or k == "errors"}
            print(f"{plancode}: errors {len(found['errors'])} none {len(found['none'])}", flush=True)
    summary: Dict[str, Dict[str, list]] = {}
    for plancode, found in report["plans"].items():
        for kind in ("errors", "none"):
            for item in found.get(kind, []):
                summary.setdefault(kind, {}).setdefault(item, []).append(plancode)
    report["summary"] = summary
    Path(args.report).write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({kind: {item: len(plans) for item, plans in items.items()}
                      for kind, items in summary.items()}, indent=1))


if __name__ == "__main__":
    main()
