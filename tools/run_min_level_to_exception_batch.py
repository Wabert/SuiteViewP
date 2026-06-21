r"""Batch "Min Level to Exception" solve over a list of policies in a workbook.

Reads a policy list from a workbook (Company in col A, Policy in col B, header
in row 1), runs the Min Level to Exception solve for each (the lowest modal
level premium that keeps the GPT policy in force to maturity, with GLP
exception premiums allowed), and writes the solved premium plus a snapshot of
the policy back into the same sheet — one row per policy.

Columns are matched to the workbook by HEADER LABEL at runtime (see HEADERS), so
the tool follows whatever order the headers are in and tolerates reordering. A
header that isn't present is simply skipped (and reported). Output fields:
    Plancode, Form, Active Riders and Benefits, Run Status, Absolute Max Prem,
    Min Level Prem, Exception Duration, Current Duration (policy year),
    MD (CyberLife), MD Diff (CyberLife - calc), Loan Amount, Exception Date,
    Face Amount, Issue date, Maturity Date, Issue Age, Attained Age, GSP, GLP,
    AccumLP, PremTD, AccumWD, Note.
(Company / Policy are read from the first two columns as input.)

Absolute Max Prem: a forecast funded to the guideline maximum every month with
GLP exceptions OFF (premium 999,999,999, which the cap clips). "Maturity" if the
policy still reaches its maturity age, otherwise the policy year it lapses. This
runs for every loaded policy, independent of Run Status.

Run Status decides whether the Min Level to Exception solve runs, and its outcome:
    "bypass (<codes>)" - the solve was skipped; the codes name the reason(s):
        A            = active shadow account (benefit type "A")
        LN           = the policy carries a loan
        MD           = MD diff != 0 (our engine doesn't match CyberLife)
        rates missing= an active rider/benefit charge has no loaded rate
        CVAT         = CVAT policy (solve is GPT-only)
        no solution  = no level premium keeps it in force to maturity
      Multiple reasons combine, e.g. "bypass (A, LN)". Solve columns left blank.
    "Error" - the policy could not be loaded or rates/MD could not be evaluated.
    Otherwise the solve ran and the status is:
      "Matured w/o Except Prem" - the level premium endows on its own.
      "Except Prem Required"    - it rides the GLP exception period to maturity.

The solve uses each policy's own billing mode. Every column except the solve
trio (Min Level Prem / Exception Duration / Exception Date) is the policy's
current inforce snapshot and is written regardless of Run Status.

Live data: this reads policy data through PolicyInformation / DB2 like the rest
of the app. It does NOT enable local SQLite fixtures — set SUITEVIEW_LOCAL_DATA=1
in the environment yourself only for deliberate offline testing of the bundled
fixture policies.

Usage (friendly — quoted path + flags, works in PowerShell):
    venv\Scripts\python.exe tools/run_min_level_to_exception_batch.py ^
        "docs\Illustration_UL\Exception prem testing.xlsx"

    # test run — first policy only, do not save:
    venv\Scripts\python.exe tools/run_min_level_to_exception_batch.py ^
        "docs\Illustration_UL\Exception prem testing.xlsx" --limit 1 --dry-run

Flags:
    --region CKPR     DB2 region (default: CKPR)
    --sheet  Sheet1   sheet name (default: first sheet)
    --limit  N        process at most N policy rows from the top
    --rows   2,3,4    explicit 1-based sheet rows to run (overrides --limit)
    --dry-run         compute and print, but do not save the workbook

Also accepts a single JSON blob as the only argument (keys: workbook, sheet,
region, rows, limit, dry_run) for programmatic callers.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from copy import deepcopy
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import openpyxl
except ImportError:
    print(json.dumps({"error": "openpyxl not installed. Run: "
                      "venv\\Scripts\\python.exe -m pip install openpyxl"}))
    sys.exit(1)

# Field key -> exact header text in row 1. Columns are resolved by label at
# runtime (see _resolve_columns) so the tool follows the user's column order
# wherever each header lands. A=Company / B=Policy are read directly, not here.
HEADERS = {
    "plancode": "Plancode",
    "form": "Form",
    "riders": "Active Riders and Benefits",
    "run_status": "Run Status",
    "abs_max": "Absolute Max Prem",
    "min_prem": "Min Level Prem",
    "exc_dur": "Exception Duration",
    "duration": "Current Duration",
    "md": "MD",
    "md_diff": "MD Diff",
    "loan": "Loan Amount",
    "exc_date": "Exception Date",
    "face": "Face Amount",
    "issue_date": "Issue date",
    "maturity_date": "Maturity Date",
    "issue_age": "Issue Age",
    "attained_age": "Attained Age",
    "gsp": "GSP",
    "glp": "GLP",
    "accum_lp": "AccumLP",
    "prem_td": "PremTD",
    "accum_wd": "AccumWD",
    "note": "Note",
}

# Resolved at runtime: field key -> column letter (only headers actually found).
COL: dict = {}

MONEY_FMT = "#,##0.00"
DATE_FMT = "m/d/yyyy"
INT_FMT = "0"

# Premium that always trips the guideline cap, so the policy is funded to its
# absolute maximum each month (exceptions off — see _absolute_max_result).
ABSOLUTE_MAX_PREMIUM = 999_999_999.0

_MODE_LABELS = {"M": "Monthly", "Q": "Quarterly", "S": "Semi-Annual", "A": "Annual"}

# Run Status values. Bypassed rows get a dynamic "bypass (<codes>)" status whose
# codes name the reason(s): A=shadow account, LN=loan, MD=MD diff, rates missing,
# CVAT, no solution.
STATUS_MATURED = "Matured w/o Except Prem"   # solve ran, policy endows on its own
STATUS_EXCEPT = "Except Prem Required"       # solve ran, rides the GLP exception
STATUS_ERROR = "Error"


def _resolve_columns(ws) -> list:
    """Map field keys to column letters from the header row. Returns the list of
    expected headers that were NOT found (so the caller can surface them)."""
    COL.clear()
    label_to_key = {label.strip().lower(): key for key, label in HEADERS.items()}
    for cell in ws[1]:
        key = label_to_key.get(str(cell.value or "").strip().lower())
        if key:
            COL[key] = cell.column_letter
    return [HEADERS[k] for k in HEADERS if k not in COL]


def _put(ws, row: int, key: str, value, fmt: Optional[str] = None) -> None:
    letter = COL.get(key)
    if letter is None:          # header not present in this workbook — skip
        return
    cell = ws[f"{letter}{row}"]
    cell.value = value
    if fmt and value is not None:
        cell.number_format = fmt


def _maturity_date(policy) -> Optional[date]:
    """Base-coverage maturity date, falling back to issue date + term in years."""
    seg = policy.base_segment
    if seg is not None and seg.maturity_date is not None:
        return seg.maturity_date
    if policy.issue_date is not None and policy.maturity_age and policy.issue_age:
        years = int(policy.maturity_age) - int(policy.issue_age)
        try:
            return policy.issue_date.replace(year=policy.issue_date.year + years)
        except ValueError:  # Feb 29 issue
            return policy.issue_date.replace(
                year=policy.issue_date.year + years, day=28)
    return None


def _write_snapshot(ws, row: int, policy) -> None:
    """Write the policy's current inforce snapshot columns (no solve, no MD diff)."""
    _put(ws, row, "plancode", (policy.plancode or "").strip())
    _put(ws, row, "form", (policy.form_number or "").strip())
    _put(ws, row, "loan", round(policy.total_loan_balance, 2), MONEY_FMT)
    _put(ws, row, "face", round(policy.face_amount, 2), MONEY_FMT)
    _put(ws, row, "issue_date", policy.issue_date, DATE_FMT)
    _put(ws, row, "maturity_date", _maturity_date(policy), DATE_FMT)
    _put(ws, row, "issue_age", policy.issue_age, INT_FMT)
    _put(ws, row, "duration", policy.policy_year, INT_FMT)
    _put(ws, row, "attained_age", policy.attained_age, INT_FMT)
    _put(ws, row, "gsp", round(policy.gsp, 2), MONEY_FMT)
    _put(ws, row, "glp", round(policy.glp, 2), MONEY_FMT)
    _put(ws, row, "accum_lp", round(policy.accumulated_glp, 2), MONEY_FMT)
    _put(ws, row, "prem_td", round(policy.premiums_paid_to_date, 2), MONEY_FMT)
    _put(ws, row, "accum_wd", round(policy.withdrawals_to_date, 2), MONEY_FMT)


def _write_solve(ws, row: int, lte) -> None:
    """Write the three solve-derived columns (premium, exception date/duration)."""
    _put(ws, row, "min_prem", lte.premium, MONEY_FMT)
    if lte.enters_exception:
        _put(ws, row, "exc_date", lte.exception_start, DATE_FMT)
        _put(ws, row, "exc_dur", lte.exception_duration, INT_FMT)
    else:
        _put(ws, row, "exc_date", None)
        _put(ws, row, "exc_dur", None)


def _clear_solve(ws, row: int) -> None:
    for key in ("min_prem", "exc_date", "exc_dur"):
        _put(ws, row, key, None)


def _absolute_max_result(engine, policy):
    """Forecast funded to the absolute max (guideline cap), exceptions OFF.

    Pays a premium so large the guideline cap binds every month, so the policy
    is funded to the most the guideline allows — with no GLP-exception rescue.
    Returns "Maturity" if it still reaches the maturity age, otherwise the policy
    year in which it lapses. ``None`` if the projection yields nothing.
    """
    from suiteview.illustration.core.solve_level_to_exception import (
        level_to_exception_options,
    )
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, ScheduledTransaction, TransactionKind,
    )

    options = level_to_exception_options(None, allow_exceptions=False)
    future = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=1,
            amount=ABSOLUTE_MAX_PREMIUM, mode="M")])
    states = engine.project(
        policy, future_inputs=future, options=options, stop_on_lapse=True)
    if not states:
        return None
    if states[-1].attained_age >= policy.maturity_age:
        return "Maturity"
    lapse = next((s for s in states if s.lapsed), states[-1])
    return lapse.policy_year


def _parse_args(argv: list) -> dict:
    """Two call styles: a single JSON blob, or a workbook path + --flags.

    PowerShell mangles embedded JSON quotes, so the friendly style is:
        run_..._batch.py "path\\to\\workbook.xlsx" [--region CKPR] [--sheet S]
                         [--limit N] [--rows 2,3,4] [--dry-run]
    """
    if not argv:
        return {}
    if argv[0].lstrip().startswith("{"):
        return json.loads(argv[0])

    cmd = {"workbook": argv[0]}
    i = 1
    while i < len(argv):
        flag = argv[i]
        if flag == "--dry-run":
            cmd["dry_run"] = True
            i += 1
            continue
        value = argv[i + 1] if i + 1 < len(argv) else None
        if flag == "--region":
            cmd["region"] = value
        elif flag == "--sheet":
            cmd["sheet"] = value
        elif flag == "--limit":
            cmd["limit"] = int(value)
        elif flag == "--rows":
            cmd["rows"] = [int(r) for r in str(value).replace(",", " ").split()]
        else:
            print(json.dumps({"error": f"unknown flag: {flag}"}))
            sys.exit(1)
        i += 2
    return cmd


def main() -> None:
    cmd = _parse_args(sys.argv[1:])
    workbook_path = cmd.get("workbook")
    if not workbook_path:
        print(json.dumps({"error": "missing required arg: workbook path"}))
        sys.exit(1)

    region = cmd.get("region", "CKPR")
    explicit_rows = cmd.get("rows")
    limit = cmd.get("limit")
    dry_run = bool(cmd.get("dry_run", False))

    from suiteview.core.policy_service import clear_cache, get_policy_info
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import (
        active_rider_benefit_codes, build_illustration_data,
    )
    from suiteview.illustration.core.rate_loader import load_rates
    from suiteview.illustration.core.rate_validation import (
        missing_required_rate_warnings,
    )
    from suiteview.illustration.core.solve_level_to_exception import (
        LevelToExceptionError, solve_level_to_exception,
    )
    from suiteview.illustration.models.plancode_config import load_plancode

    wb = openpyxl.load_workbook(workbook_path)
    ws = wb[cmd["sheet"]] if cmd.get("sheet") else wb[wb.sheetnames[0]]

    missing_headers = _resolve_columns(ws)
    if missing_headers:
        print(f"NOTE: header(s) not found (those columns are skipped): "
              f"{', '.join(missing_headers)}")

    # Collect candidate data rows (policy number present in col B, below header).
    data_rows = [
        r for r in range(2, ws.max_row + 1)
        if str(ws[f"B{r}"].value or "").strip()
    ]
    if explicit_rows:
        wanted = {int(r) for r in explicit_rows}
        data_rows = [r for r in data_rows if r in wanted]
    elif limit:
        data_rows = data_rows[: int(limit)]

    engine = IllustrationEngine()
    results = []
    for row in data_rows:
        company = str(ws[f"A{row}"].value or "").strip() or None
        policy_number = str(ws[f"B{row}"].value or "").strip()
        record = {"row": row, "policy": policy_number}

        # ── Load the policy ────────────────────────────────────────
        try:
            policy = build_illustration_data(
                policy_number, region=region, company_code=company)
        except Exception as exc:  # not found / load failure
            _clear_solve(ws, row)
            _put(ws, row, "run_status", STATUS_ERROR)
            _put(ws, row, "note", f"Load failed: {exc}")
            record.update({"status": STATUS_ERROR, "error": str(exc)})
            results.append(record)
            print(f"row {row:>4}  {policy_number:<12}  ERROR (load): {exc}")
            clear_cache()
            continue

        _write_snapshot(ws, row, policy)

        # ── Absolute Max Prem forecast (runs for every loaded policy) ──
        try:
            abs_max = _absolute_max_result(engine, deepcopy(policy))
        except Exception as exc:
            abs_max = None
            print(f"row {row:>4}  {policy_number:<12}  abs-max forecast failed: {exc}")
        _put(ws, row, "abs_max", abs_max)
        record["abs_max"] = abs_max

        # ── Active premium-paying riders/benefits ──────────────────
        pi = get_policy_info(policy_number, region, company)
        riders = active_rider_benefit_codes(pi) if pi is not None else ""
        _put(ws, row, "riders", riders or None)

        # ── MD + MD diff + rate availability ───────────────────────
        # Engine seed row gives our calculated MD vs CyberLife's; rate validation
        # flags any active rider/benefit charge we lack a rate for.
        system_md = round(float(policy.system_monthly_deduction or 0.0), 2)
        md_diff = None
        missing_rates: list[str] = []
        check_error = None
        try:
            config = load_plancode(policy.plancode)
            rates = load_rates(policy, config)
            missing_rates = missing_required_rate_warnings(policy, rates)
            seed = engine.project(policy, months=0, rates_override=rates)[0]
            system_md = round(float(seed.system_monthly_deduction or 0.0), 2)
            md_diff = round(
                float(seed.system_monthly_deduction or 0.0)
                - float(seed.md_check_calculated_deduction or 0.0), 2)
        except Exception as exc:  # rates DB / plancode / engine failure
            check_error = f"Rate/MD check failed: {exc}"

        _put(ws, row, "md", system_md, MONEY_FMT)
        _put(ws, row, "md_diff", md_diff, MONEY_FMT)

        # ── Decide Run Status ──────────────────────────────────────
        if check_error is not None:
            _clear_solve(ws, row)
            _put(ws, row, "run_status", STATUS_ERROR)
            _put(ws, row, "note", check_error)
            record.update({"status": STATUS_ERROR, "error": check_error,
                           "riders": riders})
            results.append(record)
            print(f"row {row:>4}  {policy_number:<12}  ERROR: {check_error}")
            clear_cache()
            continue

        # Each entry: (parenthetical reason code, human-readable detail).
        bypass = []
        if policy.has_shadow_account:
            bypass.append(("A", "active shadow account (benefit type A)"))
        if policy.has_loans:
            bypass.append(("LN", f"has loan {policy.total_loan_balance:,.2f}"))
        if md_diff is not None and md_diff != 0.0:
            bypass.append(("MD", f"MD diff {md_diff:,.2f}"))
        if missing_rates:
            bypass.append(("rates missing", "missing rider/benefit rates"))

        if bypass:
            status = f"bypass ({', '.join(code for code, _ in bypass)})"
            note = "; ".join(detail for _, detail in bypass)
            _clear_solve(ws, row)
            _put(ws, row, "run_status", status)
            _put(ws, row, "note", note)
            record.update({"status": status, "reasons": note,
                           "riders": riders, "md_diff": md_diff})
            results.append(record)
            print(f"row {row:>4}  {policy_number:<12}  {status}: {note}"
                  f"  [abs-max: {abs_max}]")
            clear_cache()
            continue

        # ── Solve (Min Level to Exception) ─────────────────────────
        try:
            lte = solve_level_to_exception(
                deepcopy(policy),
                mode=None,                # each policy's own billing mode
                start_policy_year=1,
                allow_exceptions=True,
            )
        except LevelToExceptionError as exc:
            # Passed the business gates but the solve genuinely can't run —
            # bypass with a reason code (CVAT, else no level premium survives).
            code = "CVAT" if policy.is_cvat else "no solution"
            status = f"bypass ({code})"
            _clear_solve(ws, row)
            _put(ws, row, "run_status", status)
            _put(ws, row, "note", str(exc))
            record.update({"status": status, "error": str(exc),
                           "riders": riders, "md_diff": md_diff})
            results.append(record)
            print(f"row {row:>4}  {policy_number:<12}  {status}: {exc}")
            clear_cache()
            continue

        _write_solve(ws, row, lte)
        mode_label = _MODE_LABELS.get(lte.mode, lte.mode)
        status = STATUS_EXCEPT if lte.enters_exception else STATUS_MATURED
        _put(ws, row, "run_status", status)
        _put(ws, row, "note", mode_label)

        record.update({
            "status": status,
            "plancode": policy.plancode,
            "form": policy.form_number,
            "riders": riders,
            "md_diff": md_diff,
            "mode": lte.mode,
            "min_level_prem": lte.premium,
            "enters_exception": lte.enters_exception,
            "exception_date": str(lte.exception_start) if lte.exception_start else None,
            "exception_duration": lte.exception_duration,
            "iterations": lte.iterations,
        })
        results.append(record)
        exc_txt = (f"exc {lte.exception_start} (yr {lte.exception_duration})"
                   if lte.enters_exception else "endows")
        print(f"row {row:>4}  {policy_number:<12}  {lte.mode} "
              f"min level {lte.premium:>12,.2f}  {exc_txt}  [abs-max: {abs_max}]")
        clear_cache()

    saved = False
    if not dry_run:
        try:
            wb.save(workbook_path)
            saved = True
        except PermissionError:
            print(json.dumps({
                "error": "Could not save — the workbook is open in Excel. "
                         "Close it and re-run.",
                "workbook": workbook_path,
                "processed": len(results),
            }, indent=2))
            sys.exit(1)

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print(json.dumps({
        "workbook": workbook_path,
        "sheet": ws.title,
        "processed": len(results),
        "status_counts": counts,
        "saved": saved,
        "dry_run": dry_run,
        "results": results,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
