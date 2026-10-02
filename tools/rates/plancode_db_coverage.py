"""Measure how much of the illustration plancode table UL_Rates schema ``rates`` supplies,
and (``--write``) drop the fields the database now covers.

``load_plancode`` reads its rate facts from schema ``rates`` first (``plan_facts`` and the
rate loaders); a plancode-table value is only a fallback for a plan whose database value
is missing. This tool applies that rule to every table row against the live database:

* fields nothing reads (MatureEndowValue, VarLoanAvailable, SkippedCovRein, Bonus,
  ProductName) and the database-only rates EPU_Code and DBD are removed;
* every database-sourced field is removed where the database carries the value and kept
  only where it is still the fallback (``fallbacks`` in the report, by plancode);
* a table MaturityAge/PremiumCeaseAge that differs from ``PLAN_DEF`` is kept as the
  explicit illustration override ``IllustrationMaturityAgeOverride`` /
  ``IllustrationPremiumCeaseAgeOverride``;
* product-rule fields (SA_Basis, LoanType, ...) are untouched.

Read-only against UL_Rates. Run it again after more rates are loaded: rows lose the
fallbacks the database has since filled.

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
    MATURITY_OVERRIDE_KEY,
    PREMIUM_CEASE_OVERRIDE_KEY,
    plancode_table_path,
)

UNUSED_FIELDS = ("MatureEndowValue", "VarLoanAvailable", "SkippedCovRein", "Bonus", "ProductName")
DATABASE_ONLY_FIELDS = ("EPU_Code", "DBD")
LOAN_FIELDS = {
    "LoanChargeRate": "loan_reg_chg",
    "LoanCollateralCreditRate": "loan_reg_crd",
    "PrefLoanChargeRate": "loan_pref_chg",
    "PrefLoanCollateralCreditRate": "loan_pref_crd",
}
# Cell rate types whose presence (any scale listed) replaces a flat table field.
CELL_FIELDS = {"MFEE": ("MFEE", ("C", "G")), "PremiumLoad": ("PREMLOAD_PCT", ("C", "G"))}
# Shadow-account flat codes -> the scale S rate type on the base plancode.
SHADOW_FIELDS = {
    "ShadowPremLoadCode": "PREMLOAD_PCT",
    "ShadowEPUCode": "EPU",
    "ShadowIntRateCode": "SHADOW_INT",
    "ShadowDBDRate": "DB_DISCOUNT",
}
_SCANNED_CELL_TYPES = ("MFEE", "PREMLOAD_PCT", "EPU", "SHADOW_INT", "DB_DISCOUNT", "COI", "MTP", "CTP")


def _cell_scales(repo: RatesSchemaRepository, facts: PlanFacts) -> Dict[str, set]:
    """``{rate type: {scales}}`` loaded on the plan's base (non-benefit) cells."""
    cells = [a for a in repo.cell_assignments(facts.company, facts.plancode)
             if not a.benefit and a.rate_type in _SCANNED_CELL_TYPES]
    by_schedule: Dict[int, set] = {}
    for a in cells:
        by_schedule.setdefault(a.schedule_id, set()).add(a.rate_type)
    scales: Dict[str, set] = {}
    for window in repo.schedule_windows(sorted(by_schedule)):
        for rate_type in by_schedule[window.schedule_id]:
            scales.setdefault(rate_type, set()).add(window.scale)
    plan_rows = repo.plan_assignments(facts.company, facts.plancode)
    for a in plan_rows:
        if a.rate_type == "DB_DISCOUNT":
            scales.setdefault("DB_DISCOUNT", set()).add(a.scale)
    return scales


def _number(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class RowPlan:
    """The decisions for one table row: removals, kept fallbacks, overrides, notes."""

    def __init__(self, row: dict):
        self.row = row
        self.plancode = str(row.get("Plancode", "")).strip()
        self.remove: list[str] = []
        self.fallbacks: Dict[str, object] = {}
        self.overrides: Dict[str, object] = {}
        self.notes: list[str] = []

    def drop(self, key: str) -> None:
        if key in self.row:
            self.remove.append(key)

    def keep_fallback(self, key: str, why: str) -> None:
        if key in self.row:
            self.fallbacks[key] = self.row[key]
            self.notes.append(f"{key}={self.row[key]!r} kept: {why}")

    def flat_or_drop(self, key: str, why: str) -> None:
        """Keep a nonzero flat fallback; a zero, blank or "Table" value implies nothing."""
        value = self.row.get(key)
        if key not in self.row:
            return
        number = _number(value)
        if number:
            self.keep_fallback(key, why)
        else:
            self.drop(key)
            if str(value).strip().upper() == "TABLE":
                self.notes.append(f"{key}='Table' but the database has no rate ({why}): charge is 0")


def plan_row(row: dict, facts: Optional[PlanFacts], cell_scales: Dict[str, set]) -> RowPlan:
    plan = RowPlan(row)
    for key in UNUSED_FIELDS + DATABASE_ONLY_FIELDS:
        plan.drop(key)
    if facts is None:
        plan.notes.append("not loaded in schema rates: every rate field stays as the fallback")
        for key, value in row.items():
            if key not in _DATABASE_FIELDS or key in DATABASE_ONLY_FIELDS:
                continue
            if str(value).strip().upper() == "TABLE":
                plan.drop(key)
            else:
                plan.fallbacks[key] = value
        if "DBD" in row and "GINT" in row and abs(float(row["DBD"]) - float(row["GINT"])) > 1e-9:
            plan.notes.append(f"DBD {row['DBD']} differs from the GINT fallback {row['GINT']}")
        return plan
    _plan_family(plan, facts)
    _plan_ages(plan, facts)
    _plan_scalars(plan, facts)
    _plan_cells(plan, cell_scales)
    _plan_shadow(plan, facts, cell_scales)
    return plan


_DATABASE_FIELDS = (
    "ProductFamily", "MaturityAge", "PremiumCeaseAge", "CINT_Key", "GINT", "DBD", "EPU_Code",
    *LOAN_FIELDS, "SafetyNetPeriod", "CorridorCode", *CELL_FIELDS, "ShadowPlancode",
    "ShadowTarget", *SHADOW_FIELDS,
)


def _plan_family(plan: RowPlan, facts: PlanFacts) -> None:
    table = str(plan.row.get("ProductFamily", "UL")).strip().upper() or "UL"
    try:
        family = facts.engine_family
    except RatesError as exc:
        plan.notes.append(str(exc))
        plan.keep_fallback("ProductFamily", "PLAN_DEF family is not an engine family")
        return
    if family != table:
        plan.notes.append(f"ProductFamily table {table} -> database {family} ({facts.schema_family})")
    plan.drop("ProductFamily")


def _plan_ages(plan: RowPlan, facts: PlanFacts) -> None:
    for key, override, db_value in (
        ("MaturityAge", MATURITY_OVERRIDE_KEY, facts.maturity_age),
        ("PremiumCeaseAge", PREMIUM_CEASE_OVERRIDE_KEY, facts.premium_cease_age),
    ):
        if key not in plan.row:
            continue
        if db_value is None:
            plan.keep_fallback(key, "PLAN_DEF has no value")
            continue
        plan.drop(key)
        table = int(plan.row[key])
        if table != db_value:
            plan.overrides[override] = table
            plan.notes.append(f"{key} table {table} vs PLAN_DEF {db_value}: kept as {override}")


def _plan_scalars(plan: RowPlan, facts: PlanFacts) -> None:
    row = plan.row
    try:
        db_cint = facts.cint_key
    except RatesError as exc:
        plan.notes.append(str(exc))
        db_cint = ""
    table_cint = str(row.get("CINT_Key", "") or "").strip()
    if db_cint:
        if table_cint and table_cint != db_cint:
            plan.notes.append(f"CINT_Key table {table_cint} -> database {db_cint}")
        plan.drop("CINT_Key")
    elif table_cint:
        plan.keep_fallback("CINT_Key", "no CIRF_KEY in PLAN_DEF")
    else:
        plan.drop("CINT_Key")

    if facts.gint is not None:
        if "GINT" in row and abs(float(row["GINT"]) - facts.gint) > 1e-9:
            plan.notes.append(f"GINT table {row['GINT']} -> database {facts.gint}")
        plan.drop("GINT")
    else:
        plan.keep_fallback("GINT", "no PLAN GINT")
    if "DBD" in row and facts.dbd is not None and abs(float(row["DBD"]) - facts.dbd) > 1e-9:
        plan.notes.append(f"DBD table {row['DBD']} -> database {facts.dbd} "
                          f"({'DB_DISCOUNT' if facts.db_discount is not None else 'GINT'})")
    if "DBD" in row and facts.dbd is None:
        plan.notes.append("DBD: neither DB_DISCOUNT nor GINT loaded; DBD = the GINT fallback")

    for key, attr in LOAN_FIELDS.items():
        db_value = getattr(facts, attr)
        if db_value is not None:
            if key in row and abs(float(row[key]) - db_value) > 1e-9:
                plan.notes.append(f"{key} table {row[key]} -> database {db_value}")
            plan.drop(key)
        else:
            plan.flat_or_drop(key, f"no {attr.upper()}")

    if facts.snet_by_issue_age is not None:
        table = row.get("SafetyNetPeriod")
        ages = sorted(set(facts.snet_by_issue_age.values()))
        if table is not None and (len(ages) != 1 or _number(table) != ages[0]):
            plan.notes.append(f"SafetyNetPeriod table {table!r} -> database by issue age {ages}")
        plan.drop("SafetyNetPeriod")
    else:
        plan.flat_or_drop("SafetyNetPeriod", "no SNET_PERIOD")

    if facts.corridor_by_age is not None:
        plan.drop("CorridorCode")
    else:
        plan.keep_fallback("CorridorCode", "no PLAN CORR (tRates_CORR.json fallback)")


def _plan_cells(plan: RowPlan, cell_scales: Dict[str, set]) -> None:
    for key, (rate_type, scales) in CELL_FIELDS.items():
        if cell_scales.get(rate_type, set()) & set(scales):
            plan.drop(key)
        else:
            plan.flat_or_drop(key, f"no {rate_type} cells")


def _plan_shadow(plan: RowPlan, facts: PlanFacts, cell_scales: Dict[str, set]) -> None:
    row = plan.row
    has_s = {t for t, scales in cell_scales.items() if "S" in scales}
    shadow_offered = bool(str(row.get("ShadowAvailability", "") or "").strip())
    table_shadow = str(row.get("ShadowPlancode", "") or "").strip()
    if facts.shadow_legacy_plancode or "COI" in has_s or not table_shadow:
        if table_shadow and facts.shadow_legacy_plancode and table_shadow != facts.shadow_legacy_plancode:
            plan.notes.append(f"ShadowPlancode table {table_shadow} -> database "
                              f"{facts.shadow_legacy_plancode}")
        plan.drop("ShadowPlancode")
    else:
        plan.keep_fallback("ShadowPlancode", "no SHADOW_LEGACY_PLANCODE and no scale S COI")
    basis = str(row.get("ShadowTargetRateBasis", "MTP") or "MTP").strip().upper()
    fields = dict(SHADOW_FIELDS, ShadowTarget=basis)
    for key, rate_type in fields.items():
        if key not in row:
            continue
        value = str(row[key]).strip()
        if rate_type in has_s:
            if shadow_offered and value.upper() != "TABLE":
                plan.notes.append(f"{key} table {value!r} -> database scale S {rate_type}")
            plan.drop(key)
        elif not shadow_offered:
            plan.drop(key)
        elif value.upper() == "TABLE":
            plan.drop(key)
            plan.notes.append(f"{key}='Table' but no scale S {rate_type}: shadow account cannot load")
        else:
            plan.keep_fallback(key, f"no scale S {rate_type}")


def apply(row: dict, plan: RowPlan) -> dict:
    """The simplified row: removals applied, overrides inserted after Plancode's peers."""
    result = {}
    for key, value in row.items():
        if key in plan.remove:
            if key == "MaturityAge" and MATURITY_OVERRIDE_KEY in plan.overrides:
                result[MATURITY_OVERRIDE_KEY] = plan.overrides[MATURITY_OVERRIDE_KEY]
            if key == "PremiumCeaseAge" and PREMIUM_CEASE_OVERRIDE_KEY in plan.overrides:
                result[PREMIUM_CEASE_OVERRIDE_KEY] = plan.overrides[PREMIUM_CEASE_OVERRIDE_KEY]
            continue
        result[key] = value
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", required=True, help="JSON report path")
    parser.add_argument("--write", action="store_true", help="rewrite plancode_table.json")
    args = parser.parse_args()

    path = plancode_table_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["Plancodes"]
    report = {"table": str(path), "rows": len(rows), "plans": {}, "fallbacks": {}, "overrides": {}}
    new_rows = []
    with RatesSchemaRepository() as repo:
        for row in rows:
            plancode = str(row.get("Plancode", "")).strip()
            facts = read_plan_facts(repo, plancode)
            scales = _cell_scales(repo, facts) if facts is not None else {}
            plan = plan_row(row, facts, scales)
            new_rows.append(apply(row, plan))
            report["plans"][plancode] = {
                "loaded": facts is not None,
                "family": facts.schema_family if facts else None,
                "removed": plan.remove,
                "fallbacks": plan.fallbacks,
                "overrides": plan.overrides,
                "notes": plan.notes,
            }
            for key, value in plan.fallbacks.items():
                report["fallbacks"].setdefault(key, {})[plancode] = value
            for key, value in plan.overrides.items():
                report["overrides"].setdefault(key, {})[plancode] = value
            print(f"{plancode}: -{len(plan.remove)} keep {sorted(plan.fallbacks)} "
                  f"{sorted(plan.overrides)}", flush=True)
    report["fallback_counts"] = {k: len(v) for k, v in report["fallbacks"].items()}
    Path(args.report).write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    if args.write:
        data["Plancodes"] = new_rows
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"fallback_counts": report["fallback_counts"],
                      "overrides": {k: len(v) for k, v in report["overrides"].items()},
                      "written": args.write}, indent=1))


if __name__ == "__main__":
    main()
