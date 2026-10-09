"""Build RERUN plancode-table rows for ISWL plans from UL_Rates schema ``rates``.

Usage: venv\\Scripts\\python.exe tools\\rerun\\build_iswl_plancode_rows.py <plancode> [...]
       [--company 01] [--single-premium] [--loan-type Advance|Arrears] [--write]

``load_plancode`` reads an ISWL plan's facts from schema ``rates`` (``plan_facts``):
``PLAN_DEF`` product family, MATURITY_AGE / PREMIUM_CEASE_AGE, plan ``GINT`` (also the
NAR discount rate, DBD) and the loan rates. A row therefore holds only the product
rules. Plans whose premium load rules are not the verified ISWL rule 4
(``400``), whose premiums cease before maturity, or whose GINT or regular loan rates
are missing (or GINT varies by duration) are reported and skipped. ``--single-premium``
accepts any premium load rules: the plan's in-force policies are single premium
(premium pay status 42), which ``load_iswl_rates`` illustrates with no further premium;
a premium-paying policy on such a plan still stops at the premium load rules.
``AgeCalc`` follows ``dbo.CYBERLIFE_PDF`` ``DBSAGCAL-AGE-CALC`` (0 = ANB, 1 = ALB).
``COI_RateBasis`` follows ``DULCVCRU-CALC-RULE`` (0/1 = Annual rates divided by 12,
2 = Monthly rates as stored). ``LoanType`` is ``--loan-type`` (default Advance: every
in-force ISWL plancode is coded LN_TYP_CD 0; check with ``rerun_plancode_tables.py
loan-type-check``). ``--write`` inserts the rows into UL_Rates
``dbo.SV_RERUN_Adv_Plancodes`` (replacing existing rows for the same plancodes); without
it the rows are only printed. Whether a plan may be illustrated is the control table
(``rerun_plancode_tables.py refresh-control``); a plan whose schema rates are incomplete
stops loudly at rate loading.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from suiteview.core.local_dev import local_data_enabled
from suiteview.core.rates_errors import RatesError
from suiteview.core.rates_schema import RatesSchemaRepository
from suiteview.illustration.models.plan_facts import read_plan_facts
from suiteview.polview.models.schema_rates import resolve_plan

_AGE_CALC_FIELD = "DBSAGCAL-AGE-CALC"
_AGE_CALC = {"0": "ANB", "1": "ALB"}
_COI_RULE_FIELD = "DULCVCRU-CALC-RULE"
# CyberDoc D10 DULCVCRU: 0/1 annual rates (ISL convention), 2 monthly rates (UL convention).
_COI_RATE_BASIS = {"0": "Annual", "1": "Annual", "2": "Monthly"}


def _pdf_rules(plancodes: list[str]) -> dict[str, dict[str, str]]:
    """``AgeCalc`` and ``COI_RateBasis`` per plancode from ``dbo.CYBERLIFE_PDF``."""
    from suiteview.core.data_access.connections import ConnectionFactory

    conn = ConnectionFactory().connect_ul_rates(readonly=True)
    try:
        cursor = conn.cursor()
        marks = ", ".join("?" for _ in plancodes)
        cursor.execute(
            "SELECT Plancode, LTRIM(RTRIM(FieldName)), FieldValue FROM dbo.CYBERLIFE_PDF "
            f"WHERE LTRIM(RTRIM(FieldName)) IN (?, ?) AND LTRIM(RTRIM(Plancode)) IN ({marks})",
            (_AGE_CALC_FIELD, _COI_RULE_FIELD, *plancodes))
        rules: dict[str, dict[str, str]] = {}
        for plan, field, value in cursor.fetchall():
            value = str(value or "").strip()
            entry = rules.setdefault(str(plan).strip().upper(), {})
            if field == _AGE_CALC_FIELD:
                entry["AgeCalc"] = _AGE_CALC.get(value, "")
            else:
                entry["COI_RateBasis"] = _COI_RATE_BASIS.get(value, "")
        return rules
    finally:
        conn.close()


def _row(repo, plancode: str, company: str, pdf: dict[str, str],
         single_premium: bool = False, loan_type: str = "Advance") -> tuple[dict | None, str]:
    plan, note = resolve_plan(repo.plan_defs(plancode), company)
    if plan is None:
        return None, f"not loaded in schema rates ({note})"
    try:
        facts = read_plan_facts(repo, plancode)
    except RatesError as exc:
        return None, str(exc)
    if facts.schema_family != "ISWL":
        return None, f"PLAN_DEF family is {facts.schema_family}, not ISWL"
    rules = str(dict(plan.facts).get("PREMLOAD_RULES") or "").strip()
    if rules != "400" and not single_premium:
        return None, f"premium load rules {rules or '(blank)'} are not the verified rule 4 (400)"
    if not pdf.get("AgeCalc"):
        return None, f"CYBERLIFE_PDF {_AGE_CALC_FIELD} is missing or not 0/1"
    if not pdf.get("COI_RateBasis"):
        return None, f"CYBERLIFE_PDF {_COI_RULE_FIELD} is missing or not 0/1/2"
    if facts.maturity_age is None or facts.premium_cease_age != facts.maturity_age:
        return None, (f"premium cease age {facts.premium_cease_age} differs from maturity age "
                      f"{facts.maturity_age}")
    if facts.gint is None:
        return None, "GINT is missing"
    if facts.loan_reg_chg is None or facts.loan_reg_crd is None:
        return None, "regular loan charge/credit rates are missing"
    return {
        "Plancode": plancode,
        "LoanType": loan_type,
        "LapseTarget": "SV",
        "AgeCalc": pdf["AgeCalc"],
        "TableRatingFactor": 0.25,
        "SA_Basis": "CurrentSA",
        "PoAV_Table": "0",
        "DynamicBanding": 0,
        "Interest_Method": "ExactDays",
        "Rachet_Banding": False,
        "CompanySub": "ANICO",
        "COI_RateBasis": pdf["COI_RateBasis"],
    }, note


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plancodes", nargs="+")
    parser.add_argument("--company", default="01")
    parser.add_argument("--single-premium", action="store_true",
                        help="accept any premium load rules (single-premium plans)")
    parser.add_argument("--loan-type", choices=("Advance", "Arrears"), default="Advance",
                        help="LoanType (CyberLife LN_TYP_CD 0 = Advance on every in-force ISWL "
                             "plancode, 10/8/2026)")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if local_data_enabled():
        raise RuntimeError("Schema rates are live UL_Rates only.")
    plancodes = [plancode.strip().upper() for plancode in args.plancodes]
    pdf_rules = _pdf_rules(plancodes)
    rows, skipped = [], {}
    with RatesSchemaRepository() as repo:
        for plancode in plancodes:
            row, note = _row(repo, plancode, args.company, pdf_rules.get(plancode, {}),
                             args.single_premium, args.loan_type)
            if row is None:
                skipped[plancode] = note
            else:
                rows.append(row)
    written = None
    if args.write and rows:
        from rerun_plancode_tables import _write_adv

        written = _write_adv(rows, replace=True, apply=True)
    print(json.dumps({"rows": rows, "skipped": skipped, "written": written}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
