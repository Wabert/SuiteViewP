"""Report what UL_Rates schema ``rates`` lacks for each illustration plancode, and
(``--write``) strip plan facts out of the plancode table.

``load_plancode`` takes every plan fact from schema ``rates`` (``plan_facts``) and
rejects a table row that still carries one (``plancode_config.DATABASE_KEYS``). This tool:

* removes those keys from every row (with ``--write``), keeping a table
  MaturityAge/PremiumCeaseAge that differs from ``PLAN_DEF`` as the explicit illustration
  override ``IllustrationMaturityAgeOverride`` / ``IllustrationPremiumCeaseAgeOverride``;
* reports, per plancode, what the schema lacks:
  ``errors``  - the plan cannot be illustrated (not loaded, no GINT, no regular loan rate,
               no ages, a non-engine product family, an unresolvable CINT key, or a
               shadow-account plan without scale S COI/SHADOW_INT/DB_DISCOUNT);
  ``none``    - read as "none" by product rule (no preferred loan, no safety net, no GPT
               corridor, no MFEE/premium load/EPU cells);
  ``notes``   - table values the database replaces with a different value.

Read-only against UL_Rates. Run it again after rate loads.

Usage::

    venv\\Scripts\\python.exe tools\\rates\\plancode_db_coverage.py --report <out.json> [--write]
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
    DATABASE_KEYS,
    MATURITY_OVERRIDE_KEY,
    PREMIUM_CEASE_OVERRIDE_KEY,
    plancode_table_path,
)

# Former table fields nothing reads.
UNUSED_KEYS = ("MatureEndowValue", "VarLoanAvailable", "SkippedCovRein", "Bonus", "ProductName")
LOAN_KEYS = {
    "LoanChargeRate": "loan_reg_chg",
    "LoanCollateralCreditRate": "loan_reg_crd",
    "PrefLoanChargeRate": "loan_pref_chg",
    "PrefLoanCollateralCreditRate": "loan_pref_crd",
}
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


def _number(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def review_row(row: dict, facts: Optional[PlanFacts], scales: Dict[str, set]) -> dict:
    """The simplified row and the plan's findings."""
    result = {"errors": [], "none": [], "notes": [], "overrides": {}}
    new_row = {k: v for k, v in row.items() if k not in DATABASE_KEYS and k not in UNUSED_KEYS}
    result["row"] = new_row
    if facts is None:
        result["errors"].append("not loaded in schema rates (PLAN_DEF)")
        return result
    errors, none, notes = result["errors"], result["none"], result["notes"]
    try:
        facts.engine_family
    except RatesError as exc:
        errors.append(str(exc))
    try:
        cint = facts.cint_key
    except RatesError as exc:
        errors.append(str(exc))
        cint = ""
    if row.get("CINT_Key") and cint and row["CINT_Key"] != cint:
        notes.append(f"CINT_Key table {row['CINT_Key']} -> {cint}")
    for key, attr, label in (("MaturityAge", "maturity_age", MATURITY_OVERRIDE_KEY),
                             ("PremiumCeaseAge", "premium_cease_age", PREMIUM_CEASE_OVERRIDE_KEY)):
        db_value = getattr(facts, attr)
        if db_value is None:
            errors.append(f"PLAN_DEF has no {key}")
        elif key in row and int(row[key]) != db_value:
            result["overrides"][label] = int(row[key])
    if facts.gint is None:
        errors.append("no PLAN GINT")
    elif _number(row.get("GINT")) not in (None, facts.gint):
        notes.append(f"GINT table {row['GINT']} -> {facts.gint}")
    if _number(row.get("DBD")) not in (None, facts.dbd):
        notes.append(f"DBD table {row['DBD']} -> {facts.dbd}")
    for key, attr in LOAN_KEYS.items():
        value = getattr(facts, attr)
        if value is None:
            (errors if key.startswith("Loan") else none).append(f"no {attr.upper()}")
        elif _number(row.get(key)) not in (None, value):
            notes.append(f"{key} table {row[key]} -> {value}")
    if facts.snet_by_issue_age is None:
        none.append("no SNET_PERIOD (no safety net)")
        if _number(row.get("SafetyNetPeriod")):
            notes.append(f"SafetyNetPeriod table {row['SafetyNetPeriod']} -> none")
    if facts.corridor_by_age is None:
        none.append("no CORR (no GPT corridor)")
    for rate_type, key in (("MFEE", "MFEE"), ("PREMLOAD_PCT", "PremiumLoad"), ("EPU", "EPU_Code")):
        if not scales.get(rate_type, set()) & {"C", "G"}:
            none.append(f"no {rate_type} cells")
            if _number(row.get(key)):
                notes.append(f"{key} table {row[key]} -> none")
    if str(row.get("ShadowAvailability", "") or "").strip():
        for rate_type in ("COI", "SHADOW_INT", "DB_DISCOUNT"):
            if "S" not in scales.get(rate_type, set()):
                errors.append(f"shadow account without scale S {rate_type}")
    for label, value in result["overrides"].items():
        position = list(new_row).index("Plancode") + 1
        items = list(new_row.items())
        items.insert(position, (label, value))
        new_row = dict(items)
    result["row"] = new_row
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", required=True, help="JSON report path")
    parser.add_argument("--write", action="store_true", help="rewrite plancode_table.json")
    args = parser.parse_args()

    path = plancode_table_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    report = {"table": str(path), "rows": len(data["Plancodes"]), "plans": {}}
    new_rows = []
    with RatesSchemaRepository() as repo:
        for row in data["Plancodes"]:
            plancode = str(row.get("Plancode", "")).strip()
            try:
                facts = read_plan_facts(repo, plancode)
            except RatesError as exc:
                facts = None
                report["plans"][plancode] = {"errors": [str(exc)]}
            scales = _cell_scales(repo, facts) if facts is not None else {}
            found = review_row(row, facts, scales)
            new_rows.append(found.pop("row"))
            report["plans"].setdefault(plancode, {}).update(
                {k: v for k, v in found.items() if v or k == "errors"})
            print(f"{plancode}: errors {len(found['errors'])} none {len(found['none'])}", flush=True)
    summary: Dict[str, Dict[str, list]] = {}
    for plancode, found in report["plans"].items():
        for kind in ("errors", "none", "notes"):
            for item in found.get(kind, []):
                summary.setdefault(kind, {}).setdefault(item.split(" table ")[0], []).append(plancode)
    report["summary"] = summary
    Path(args.report).write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    if args.write:
        data["Plancodes"] = new_rows
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({kind: {item: len(plans) for item, plans in items.items()}
                      for kind, items in summary.items()}, indent=1))
    print("written" if args.write else "report only")


if __name__ == "__main__":
    main()
