"""Build RERUN plancode-table rows for ISWL plans from UL_Rates schema ``rates``.

Usage: venv\\Scripts\\python.exe tools\\rerun\\build_iswl_plancode_rows.py <plancode> [...]
       [--company 01] [--single-premium] [--write]

``load_plancode`` reads an ISWL plan's facts from schema ``rates`` (``plan_facts``):
``PLAN_DEF`` product family, MATURITY_AGE / PREMIUM_CEASE_AGE, plan ``GINT`` (also the
NAR discount rate, DBD) and the loan rates. A row therefore holds only the product
rules. Plans whose premium load rules are not the verified ISWL rule 4
(``400``), whose premiums cease before maturity, or whose GINT or regular loan rates
are missing (or GINT varies by duration) are reported and skipped. ``--single-premium``
accepts any premium load rules: the plan's in-force policies are single premium
(premium pay status 42), which ``load_iswl_rates`` illustrates with no further premium;
a premium-paying policy on such a plan still stops at the premium load rules.
``AgeCalc`` follows ``dbo.CYBERLIFE_PDF`` ``DBSAGCAL-AGE-CALC`` (0 = ANB, 1 = ALB; the
engine does not read it). ``COI_RateBasis`` follows ``DULCVCRU-CALC-RULE`` (0/1 = Annual
rates divided by 12, 2 = Monthly rates as stored). ``--write`` splices
the rows into ``suiteview/illustration/plancodes/plancode_table.json`` as text
(replacing existing rows for the same plancodes, leaving every other row's formatting
as is); without it the rows are only printed. Rows are ``CanIllustrate`` true (only IUL
is blocked); a plan whose schema rates are incomplete stops loudly at rate loading.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from suiteview.core.local_dev import local_data_enabled
from suiteview.core.rates_errors import RatesError
from suiteview.core.rates_schema import RatesSchemaRepository
from suiteview.illustration.models.plan_facts import read_plan_facts
from suiteview.polview.models.schema_rates import resolve_plan

_TABLE = _ROOT / "suiteview" / "illustration" / "plancodes" / "plancode_table.json"
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
         single_premium: bool = False) -> tuple[dict | None, str]:
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
        "LoanType": "Arrears",
        "IntCalcMethod": "Declared",
        "LapseTarget": "SV",
        "AgeCalc": pdf["AgeCalc"],
        "ShadowAvailability": "",
        "TableRatingFactor": 0.25,
        "PremFlatLoad": 0,
        "SA_Basis": "CurrentSA",
        "CanIllustrate": True,
        "PoAV_Table": "0",
        "DynamicBanding": 0,
        "Interest_Method": "ExactDays",
        "Rachet_Banding": False,
        "CompanySub": "ANICO",
        "COI_RateBasis": pdf["COI_RateBasis"],
    }, note


def _row_text(row: dict) -> str:
    """A row as it sits in plancode_table.json: two-space JSON indented four spaces."""
    lines = json.dumps(row, indent=2, ensure_ascii=False).splitlines()
    return "\n".join("    " + line for line in lines)


def _write_rows(rows: list[dict]) -> None:
    """Splice rows into the table as text so every existing row keeps its formatting.

    A plancode already in the table has its exact row block removed first, then the
    new rows are appended before the closing bracket; the result must parse with no
    duplicate plancodes before it is written.
    """
    text = _TABLE.read_text(encoding="utf-8")
    data = json.loads(text)
    existing = {row.get("Plancode") for row in data["Plancodes"]}
    for row in rows:
        if row["Plancode"] in existing:
            text = _remove_row_block(text, row["Plancode"])
    closing = text.rstrip().rfind("]")
    head = text[:closing].rstrip()
    new_text = head + ",\n" + ",\n".join(_row_text(row) for row in rows) + "\n  ]\n}\n"
    parsed = json.loads(new_text)
    codes = [row.get("Plancode") for row in parsed["Plancodes"]]
    if len(codes) != len(set(codes)):
        raise RuntimeError("Splicing produced duplicate plancodes; the table was not written.")
    _TABLE.write_text(new_text, encoding="utf-8")


def _remove_row_block(text: str, plancode: str) -> str:
    marker = f'"Plancode": "{plancode}"'
    at = text.find(marker)
    if at < 0 or text.find(marker, at + 1) >= 0:
        raise RuntimeError(f"Cannot locate a unique row for {plancode} to replace.")
    start = text.rfind("{", 0, at)
    end = text.find("\n    }", at) + len("\n    }")
    before, after = text[:start].rstrip(), text[end:]
    if after.startswith(","):
        after = after[1:]
    elif before.endswith(","):
        before = before[:-1]
    return before + after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plancodes", nargs="+")
    parser.add_argument("--company", default="01")
    parser.add_argument("--single-premium", action="store_true",
                        help="accept any premium load rules (single-premium plans)")
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
                             args.single_premium)
            if row is None:
                skipped[plancode] = note
            else:
                rows.append(row)
    if args.write and rows:
        _write_rows(rows)
    print(json.dumps({"rows": rows, "skipped": skipped, "written": bool(args.write and rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
