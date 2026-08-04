r"""Batch the "Batch2" premium-solve columns of GLP Limit Calc v2.

Reads a policy list from a workbook sheet (Company in col A, Policy in col B,
headers in row 1) and, for each policy, writes an inforce snapshot plus four
premium accumulations measuring the total premium that would be paid from the
VALUATION DATE to the MATURITY DATE (no premium is paid ON the maturity date).

Columns written (matched by header LABEL at runtime, so column order is free):

  Run Date                          today's date (when the policy was run)
  Valuation Date                    most recent monthiversary (policy.valuation_date)
  AV                                account value on the valuation date
  Loans                             total policy debt on the valuation date
  Face Amount                       base face + riders on the primary insured
  DB Option                         A - Level / B - Increasing / C - ROP
  Billing Prem                      current billable modal premium
  Billing Mode                      current billing mode (human readable)
  Active Riders and Benefits        plancodes/codes of active riders + benefits
  MD Diff                           CyberLife MD − our calculated MD (valuation date)
  Accum(CPM)                        modes-to-maturity × current modal premium
  Level Premium to Maturity (LPM)   level premium (current mode) that endows with
                                    ~$1,000 at maturity, NO guideline restrictions
  Accum Prem (LPM)                  total future premium from the LPM solve
  Level Prem to Exception (LPExc)   min level premium to maturity WITH guideline
                                    exceptions/force-outs on (Prem to Maturity)
  Accum Level to Exception          total future premium from the LPExc solve
  Accum Level to MD                 total future premium from the "Billable to MD"
                                    solve (guideline exceptions on)

Every solve/accumulation reflects only premium paid on/after the valuation date.
The four accumulations sum each month's actual premium outlay (applied premium +
Monthly-Deduction premium + GP exception premium + loan repayment) over the
projection to maturity, so they honor the engine's own billing schedule and the
"no premium on the maturity date" boundary.

Lumpsum to Next Premium (``--lumpsum-to-next``): when set, a bridging lumpsum is
solved and layered on the forecast date of the two guideline-exception solves so
a thin policy survives from the valuation date to its next scheduled premium (the
same bridge the shipped Min-Level / Billable-to-MD batch runs use). It lifts the
"Accum Level to Exception" and "Accum Level to MD" totals by the bridge premium;
the level-premium value itself (LPExc) is unchanged. Accum(CPM) (pure modes ×
modal) and the NO-RESTRICTIONS LPM solve are left bridge-free by definition.

Live data: policies load through PolicyInformation / DB2 like the rest of the
app. Local SQLite fixtures are opt-in via SUITEVIEW_LOCAL_DATA=1 only.

Usage (PowerShell):
    venv\Scripts\python.exe tools/run_glp_limit_batch2.py ^
        "path\to\GLP Limit Calc v2.xlsx" --sheet Batch2 --limit 5

Flags:
    --sheet  NAME     sheet name (default: first sheet)
    --region CKPR     DB2 region (default: CKPR)
    --limit  N        process at most N policy rows from the top
    --start-row N     start at 1-based sheet row N
    --rows   2,3,4    explicit 1-based sheet rows to run (overrides --limit)
    --lumpsum-to-next solve a Lumpsum to Next Premium bridge and layer it into
                      the "Accum Level to Exception" and "Accum Level to MD"
                      accumulations
    --dry-run         compute and print, but do not save the workbook
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import openpyxl
except ImportError:
    print(json.dumps({"error": "openpyxl not installed. Run: "
                      "venv\\Scripts\\python.exe -m pip install openpyxl"}))
    sys.exit(1)

MONEY_FMT = "#,##0.00"
DATE_FMT = "m/d/yyyy"

# field key -> exact header text in row 1. Company (A) / Policy (B) are read
# directly. Only these output columns are written; everything else is left as-is.
HEADERS: Dict[str, str] = {
    "run_date": "Run Date",
    "valuation_date": "Valuation Date",
    "av": "AV",
    "loans": "Loans",
    "face": "Face Amount",
    "db_option": "DB Option",
    "billing_prem": "Billing Prem",
    "billing_mode": "Billing Mode",
    "riders": "Active Riders and Benefits",
    "md_diff": "MD Diff",
    "accum_cpm": "Accum(CPM)",
    "lpm": "Level Premium to Maturity (LPM)",
    "accum_lpm": "Accum Prem (LPM)",
    "lpexc": "Level Prem to Exception (LPExc)",
    "accum_lpexc": "Accum Level to Exception",
    "accum_lpmd": "Accum Level to MD",
}

MONEY_KEYS = {"av", "loans", "face", "billing_prem", "md_diff", "accum_cpm",
              "lpm", "accum_lpm", "lpexc", "accum_lpexc", "accum_lpmd"}
DATE_KEYS = {"run_date", "valuation_date"}

# field key -> column letter, resolved from the header row at runtime.
COL: Dict[str, str] = {}


def _resolve_columns(ws) -> List[str]:
    COL.clear()
    label_to_key = {label.strip().lower(): key for key, label in HEADERS.items()}
    for cell in ws[1]:
        key = label_to_key.get(str(cell.value or "").strip().lower())
        if key:
            COL[key] = cell.column_letter
    return [HEADERS[k] for k in HEADERS if k not in COL]


def _put(ws, row: int, key: str, value) -> None:
    letter = COL.get(key)
    if letter is None or value is None:
        return
    cell = ws[f"{letter}{row}"]
    cell.value = value
    if key in MONEY_KEYS:
        cell.number_format = MONEY_FMT
    elif key in DATE_KEYS:
        cell.number_format = DATE_FMT


# ── Per-policy compute ──────────────────────────────────────────────────────

def _future_premium(states) -> float:
    """Total premium paid over a projection: each month's actual outlay
    (applied premium + MD premium + GP exception premium) plus loan repayment.
    Projections start at the valuation date, so this is future premium only."""
    total = 0.0
    for s in states:
        total += float(s.premium_outlay) + float(getattr(s, "applied_loan_repayment", 0.0) or 0.0)
    return round(total, 2)


def compute_policy(policy_number: str, company: Optional[str], region: str,
                   engine, lumpsum_to_next: bool = False) -> Dict[str, object]:
    """Compute the Batch2 snapshot + solve columns for one policy.

    Returns a dict keyed by field key. Raises on load failure; individual solve
    failures are caught and recorded under ``_errors`` with the column left blank.

    When ``lumpsum_to_next`` is set, a Lumpsum to Next Premium bridge is solved
    and layered into the two guideline-exception accumulations (Accum Level to
    Exception, Accum Level to MD) so a thin policy survives from the valuation
    date to its next scheduled premium.
    """
    from dataclasses import replace

    from suiteview.core.policy_service import get_policy_info
    from suiteview.illustration.core.batch_runner import (
        DB_OPTION_DISPLAY, _billable_to_md_run, _md_and_rate_check,
        billing_mode_code,
    )
    from suiteview.illustration.core.calc_engine import _primary_insured_rider_face
    from suiteview.illustration.core.illustration_policy_service import (
        active_rider_benefit_codes, build_illustration_data,
    )
    from suiteview.illustration.core.solve_level_to_exception import (
        level_to_exception_options, solve_level_to_exception,
    )
    from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
        LUMPSUM_SUBTYPE, solve_lumpsum_to_next_premium,
    )
    from suiteview.illustration.core.solve_premium_to_target import (
        solve_premium_to_target,
    )
    from suiteview.illustration.models.input_set import (
        DatedTransaction, IllustrationInputSet, IllustrationOptions,
        ScheduledTransaction, TransactionKind,
    )

    values: Dict[str, object] = {}
    errors: List[str] = []

    policy = build_illustration_data(policy_number, region=region,
                                     company_code=company)
    pi = get_policy_info(policy_number, region, company)

    def _bridge(base_future: IllustrationInputSet,
                base_options: IllustrationOptions):
        """Solve the Lumpsum to Next Premium bridge for ``base_future`` /
        ``base_options``. Returns ``(dated_transactions, next_premium_date)`` —
        an empty list and ``None`` when no bridge is needed or the solve fails."""
        if not lumpsum_to_next:
            return [], None
        try:
            lump = solve_lumpsum_to_next_premium(
                deepcopy(policy), base_future_inputs=base_future,
                base_options=base_options, engine=engine)
        except Exception:  # bridge solve failed — accumulate without it
            return [], None
        if lump is not None and lump.lumpsum > 0:
            return ([DatedTransaction(
                kind=TransactionKind.PREMIUM, effective_date=lump.forecast_date,
                amount=lump.lumpsum, subtype=LUMPSUM_SUBTYPE)],
                lump.next_premium_date)
        return [], None

    # ── Snapshot ───────────────────────────────────────────────────────
    values["run_date"] = date.today()
    values["valuation_date"] = policy.valuation_date
    values["av"] = round(float(policy.account_value or 0.0), 2)
    values["loans"] = round(float(policy.total_loan_balance or 0.0), 2)
    face = float(policy.face_amount or 0.0) + _primary_insured_rider_face(
        policy, policy.valuation_date)
    values["face"] = round(face, 2)
    db = str(getattr(policy, "db_option", "") or "").strip().upper()
    values["db_option"] = DB_OPTION_DISPLAY.get(db, db or None)
    values["billing_prem"] = round(float(policy.modal_premium or 0.0), 2)
    values["billing_mode"] = pi.billing_mode if pi is not None else None
    values["riders"] = (active_rider_benefit_codes(pi) or None) if pi is not None else None

    md_diff, _system_md, _missing, check_error = _md_and_rate_check(engine, policy)
    values["md_diff"] = md_diff
    if check_error is not None:
        errors.append(check_error)

    modal = float(policy.modal_premium or 0.0)
    mode = billing_mode_code(policy)
    maturity_age = int(policy.maturity_age or 121)
    no_restrict = IllustrationOptions(
        conform_to_tefra=False, conform_to_tamra=False,
        allow_exception_prems=False)
    # Apply Premium to Loan First — on for every premium solve (per request).
    # Harmless on a loan-free policy (no premium is diverted with no loan
    # balance), and _future_premium still counts the full outlay, so a loan
    # repayment is included without double-counting the premium that funded it.
    no_restrict_loan = IllustrationOptions(
        conform_to_tefra=False, conform_to_tamra=False,
        allow_exception_prems=False, apply_prem_to_loan=True)

    def _level_future(premium: float, m: str) -> IllustrationInputSet:
        return IllustrationInputSet(scheduled_transactions=[ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=1, amount=premium, mode=m)])

    # ── Accum(CPM): modes-to-maturity × current modal premium ──────────
    # No guideline restrictions and no stop-on-lapse so every remaining modal
    # payment is counted; the sum equals modes × modal premium.
    try:
        states = engine.project(
            deepcopy(policy), options=no_restrict,
            future_inputs=_level_future(modal, mode), stop_on_lapse=False)
        values["accum_cpm"] = _future_premium(states)
    except Exception as exc:
        errors.append(f"Accum(CPM): {exc}")

    # ── LPM: level premium that endows with ~$1,000 at maturity, no rules ─
    try:
        lpm_res = solve_premium_to_target(
            deepcopy(policy), target="av", amount=1000.0, at_age=maturity_age,
            mode=mode, start_policy_year=1, base_options=no_restrict_loan,
            engine=engine)
        values["lpm"] = round(lpm_res.premium, 2)
        level_future = _level_future(lpm_res.premium, mode)
        dated, _next_due = _bridge(level_future, no_restrict_loan)
        future = IllustrationInputSet(
            scheduled_transactions=list(level_future.scheduled_transactions),
            dated_transactions=dated)
        states = engine.project(
            deepcopy(policy), options=no_restrict_loan,
            future_inputs=future, stop_on_lapse=False)
        values["accum_lpm"] = _future_premium(states)
    except Exception as exc:
        errors.append(f"LPM: {exc}")

    # ── LPExc: min level to maturity WITH guideline exceptions on ──────
    try:
        lte = solve_level_to_exception(
            deepcopy(policy), mode=None, start_policy_year=1,
            allow_exceptions=True, apply_prem_to_loan=True,
            conform_to_tamra=False, engine=engine)
        values["lpexc"] = round(lte.premium, 2)
        opts = level_to_exception_options(
            None, allow_exceptions=True,
            apply_prem_to_loan=True, conform_to_tamra=False)
        level_future = _level_future(lte.premium, lte.mode)
        dated, _next_due = _bridge(level_future, opts)
        future = IllustrationInputSet(
            scheduled_transactions=list(level_future.scheduled_transactions),
            dated_transactions=dated)
        states = engine.project(deepcopy(policy), options=opts,
                                future_inputs=future)
        values["accum_lpexc"] = _future_premium(states)
    except Exception as exc:
        errors.append(f"LPExc: {exc}")

    # ── Accum Level to MD: "Billable to MD" solve, exceptions on ───────
    try:
        future, options = _billable_to_md_run(policy)
        options = replace(options, apply_prem_to_loan=True)
        dated, next_due = _bridge(future, options)
        if dated:
            future = IllustrationInputSet(
                scheduled_transactions=list(future.scheduled_transactions),
                dated_transactions=list(future.dated_transactions) + dated,
                policy_changes=list(future.policy_changes))
            options = replace(options,
                              billable_to_md_no_latch_before=next_due)
        states = engine.project(
            deepcopy(policy), options=options, future_inputs=future,
            stop_on_lapse=True)
        values["accum_lpmd"] = _future_premium(states)
    except Exception as exc:
        errors.append(f"Accum Level to MD: {exc}")

    if errors:
        values["_errors"] = "; ".join(errors)
    return values


# ── Workbook orchestration ──────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("workbook")
    parser.add_argument("--sheet", default=None)
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start-row", type=int, default=None)
    parser.add_argument("--rows", default=None, help="explicit 1-based rows, comma-separated")
    parser.add_argument("--lumpsum-to-next", action="store_true",
                        help="layer a Lumpsum to Next Premium bridge into the "
                             "guideline-exception accumulations")
    parser.add_argument("--end-row", type=int, default=None,
                        help="last 1-based row to process (inclusive)")
    parser.add_argument("--save-every", type=int, default=25,
                        help="save the workbook every N processed rows so a "
                             "long run survives a crash (0 disables)")
    parser.add_argument("--skip-done", action="store_true",
                        help="skip rows that already have a Run Date, so an "
                             "interrupted run can be resumed")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.calc_engine import IllustrationEngine

    wb = openpyxl.load_workbook(args.workbook)
    ws = wb[args.sheet] if args.sheet else wb[wb.sheetnames[0]]

    missing = _resolve_columns(ws)
    if missing:
        print(json.dumps({"error": "missing output headers", "missing": missing,
                          "sheet": ws.title}, indent=2))
        sys.exit(1)

    data_rows = [r for r in range(2, ws.max_row + 1)
                 if str(ws[f"B{r}"].value or "").strip()]
    if args.rows:
        wanted = {int(x) for x in args.rows.split(",") if x.strip()}
        data_rows = [r for r in data_rows if r in wanted]
    else:
        if args.start_row:
            data_rows = [r for r in data_rows if r >= args.start_row]
        if args.end_row:
            data_rows = [r for r in data_rows if r <= args.end_row]
        if args.limit:
            data_rows = data_rows[: args.limit]

    run_col = COL.get("run_date")
    if args.skip_done and run_col:
        data_rows = [r for r in data_rows
                     if not str(ws[f"{run_col}{r}"].value or "").strip()]

    def _save() -> bool:
        try:
            wb.save(args.workbook)
            return True
        except PermissionError:
            print(json.dumps({"warning": "Could not save — workbook open in "
                              "Excel. Will retry at the next checkpoint; "
                              "keep it closed to persist progress."}))
            sys.stdout.flush()
            return False

    engine = IllustrationEngine()
    summary = []
    saved = False
    since_save = 0
    for row in data_rows:
        company = str(ws[f"A{row}"].value or "").strip() or None
        policy_number = str(ws[f"B{row}"].value or "").strip()
        rec: Dict[str, object] = {"row": row, "company": company,
                                  "policy": policy_number}
        try:
            values = compute_policy(policy_number, company, args.region, engine,
                                    lumpsum_to_next=args.lumpsum_to_next)
            for key in HEADERS:
                _put(ws, row, key, values.get(key))
            rec["status"] = "error(s)" if values.get("_errors") else "ok"
            rec["values"] = {
                HEADERS[k]: (v.isoformat() if isinstance(v, date) else v)
                for k, v in values.items() if not k.startswith("_")
            }
            if values.get("_errors"):
                rec["errors"] = values["_errors"]
        except Exception as exc:
            rec["status"] = "load error"
            rec["errors"] = str(exc)
        finally:
            clear_cache()
        summary.append(rec)
        print(json.dumps(rec, default=str))
        sys.stdout.flush()

        since_save += 1
        if (not args.dry_run and args.save_every
                and since_save >= args.save_every):
            if _save():
                saved = True
                since_save = 0

    if not args.dry_run and data_rows and since_save:
        if _save():
            saved = True

    print(json.dumps({"workbook": args.workbook, "sheet": ws.title,
                      "processed": len(data_rows), "saved": saved,
                      "lumpsum_to_next": args.lumpsum_to_next,
                      "dry_run": args.dry_run}, default=str, indent=2))


if __name__ == "__main__":
    main()
