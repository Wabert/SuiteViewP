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
    Absolute Max AV, Min Level Prem, Total Prem Paid, Exception Duration,
    Current Duration (policy year), MD (CyberLife), MD Diff (CyberLife - calc),
    Loan Amount, Exception Date, Face Amount, Issue date, Maturity Date,
    Maturity Duration (years), Maturity Age, Issue Age, Attained Age, GSP, GLP,
    AccumLP, PremTD, AccumWD, Valuation Date, Suspense Code, Def Life Ins.
(Company / Policy are read from the first two columns as input.)

Absolute Max Prem: a forecast funded to the guideline maximum every month with
GLP exceptions OFF (premium 999,999,999, which the cap clips). "Maturity" if the
policy still reaches its maturity age, otherwise the policy year it lapses. This
runs for every loaded policy, independent of Run Status. Absolute Max AV is the
account value at maturity in that scenario (blank when it lapses before maturity).

Total Prem Paid: lifetime premiums to maturity in the Min Level to Exception solve
scenario — the cumulative applied premium plus GP exception premiums plus loan
repayments. Blank when the solve doesn't run (bypassed / error).

Run Status decides whether the Min Level to Exception solve runs, and its outcome:
    "bypass (<codes>)" - the solve was skipped; the codes name the reason(s):
        A            = active shadow account (benefit type "A")
        MD           = MD diff != 0 (our engine doesn't match CyberLife)
        rates missing= an active rider/benefit charge has no loaded rate
        CVAT         = CVAT policy (solve is GPT-only)
        no solution  = no level premium keeps it in force to maturity
      Multiple reasons combine, e.g. "bypass (A, MD)". Solve columns left blank.
      A policy loan is NOT a bypass: it is solved with Apply Premium to Loan First
      (the level premium repays the loan before funding the account value).
    "Error" - the policy could not be loaded or rates/MD could not be evaluated.
    Otherwise the solve ran and the status is:
      "Matured w/o Except Prem" - the level premium endows on its own.
      "Except Prem Required"    - it rides the GLP exception period to maturity.

The solve uses each policy's own billing mode. Every column except the solve
set (Min Level Prem / Total Prem Paid / Exception Duration / Exception Date) is
the policy's current inforce snapshot and is written regardless of Run Status.

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
    --start-policy P  start at the first row whose policy in col B matches P
    --start-row N     start at 1-based sheet row N
    --rows   2,3,4    explicit 1-based sheet rows to run (overrides --limit)
    --dry-run         compute and print, but do not save the workbook
    --summarize-only  read matching rows and print saved Run Status counts
    --sidecar PATH    write per-row JSONL results here (default: next to workbook)
    --replay-sidecar PATH
                      write a prior sidecar JSONL back into the workbook

Also accepts a single JSON blob as the only argument (keys: workbook, sheet,
region, rows, start_policy, start_row, limit, dry_run, summarize_only, sidecar,
replay_sidecar) for programmatic callers.
"""
from __future__ import annotations

import json
import os
import re
import sys
from copy import deepcopy
from datetime import date, datetime
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
# wherever each header lands. Missing output columns are appended automatically.
# A=Company / B=Policy are read directly, not here.
HEADERS = {
    "plancode": "Plancode",
    "form": "Form",
    "riders": "Active Riders and Benefits",
    "run_status": "Run Status",
    "abs_max": "Absolute Max Prem",
    "abs_max_av": "Absolute Max AV",
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
    "maturity_duration": "Maturity Duration",
    "maturity_age": "Maturity Age",
    "issue_age": "Issue Age",
    "attained_age": "Attained Age",
    "gsp": "GSP",
    "glp": "GLP",
    "accum_lp": "AccumLP",
    "prem_td": "PremTD",
    "accum_wd": "AccumWD",
    "valuation_date": "Valuation Date",
    "suspense_code": "Suspense Code",
    "total_prem_paid": "Total Prem Paid",
    "def_life_ins": "Def Life Ins",
}

# Resolved at runtime: field key -> column letter (only headers actually found).
COL: dict = {}

MONEY_FMT = "#,##0.00"
DATE_FMT = "m/d/yyyy"
INT_FMT = "0"

MONEY_KEYS = {
    "abs_max_av",
    "min_prem",
    "md",
    "md_diff",
    "loan",
    "face",
    "gsp",
    "glp",
    "accum_lp",
    "prem_td",
    "accum_wd",
    "total_prem_paid",
}
DATE_KEYS = {"exc_date", "issue_date", "maturity_date", "valuation_date"}
INT_KEYS = {
    "exc_dur",
    "duration",
    "maturity_duration",
    "maturity_age",
    "issue_age",
    "attained_age",
}

# Premium that always trips the guideline cap, so the policy is funded to its
# absolute maximum each month (exceptions off — see _absolute_max_result).
ABSOLUTE_MAX_PREMIUM = 999_999_999.0

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


def _ensure_output_columns(ws) -> None:
    """Append every known output header missing from row 1."""
    _resolve_columns(ws)
    next_col = ws.max_column + 1
    for key, label in HEADERS.items():
        if key in COL:
            continue
        cell = ws.cell(row=1, column=next_col)
        cell.value = label
        COL[key] = cell.column_letter
        next_col += 1


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _row_record(ws, row: int, *, workbook: str, region: str, extras: Optional[dict] = None) -> dict:
    record = {
        "workbook": workbook,
        "sheet": ws.title,
        "row": row,
        "region": region,
        "company": _json_value(ws[f"A{row}"].value),
        "policy": _json_value(ws[f"B{row}"].value),
        "columns": {},
    }
    for key, label in HEADERS.items():
        letter = COL.get(key)
        record["columns"][label] = _json_value(ws[f"{letter}{row}"].value) if letter else None
    if extras:
        record.update(extras)
    return record


def _default_sidecar_path(workbook_path: str, sheet: str, start_policy: str, start_row: Optional[int], limit) -> Path:
    workbook = Path(workbook_path)
    suffix_parts = [sheet]
    if start_policy:
        suffix_parts.append(start_policy)
    elif start_row:
        suffix_parts.append(f"row{start_row}")
    if limit:
        suffix_parts.append(f"limit{limit}")
    suffix_parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))
    suffix = ".".join(re.sub(r"[^A-Za-z0-9_.-]+", "_", str(part)) for part in suffix_parts)
    return workbook.with_name(f"{workbook.stem}.{suffix}.results.jsonl")


def _write_sidecar(handle, record: dict) -> None:
    if handle is None:
        return
    handle.write(json.dumps(record, default=str) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def _replay_value(key: str, value):
    if value in (None, ""):
        return None
    if key in DATE_KEYS and isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return value
    return value


def _replay_format(key: str) -> Optional[str]:
    if key in MONEY_KEYS:
        return MONEY_FMT
    if key in DATE_KEYS:
        return DATE_FMT
    if key in INT_KEYS:
        return INT_FMT
    return None


def _replay_sidecar(ws, sidecar_path: Path) -> dict:
    _ensure_output_columns(ws)
    label_to_key = {label: key for key, label in HEADERS.items()}
    counts = {}
    rows = []
    with sidecar_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            row = int(record["row"])
            columns = record.get("columns") or {}
            for label, value in columns.items():
                key = label_to_key.get(label)
                if key is None:
                    continue
                _put(ws, row, key, _replay_value(key, value), _replay_format(key))
            status = str(columns.get(HEADERS["run_status"]) or "").strip() or "(blank)"
            counts[status] = counts.get(status, 0) + 1
            rows.append(row)
    return {
        "sidecar": str(sidecar_path),
        "processed": len(rows),
        "start_row": min(rows) if rows else None,
        "end_row": max(rows) if rows else None,
        "status_counts": counts,
    }


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


def _maturity_duration(policy) -> Optional[int]:
    """Policy-year count to maturity (the term in years) = maturity age − issue age.

    Parallels the "Current Duration" column (which is the policy year); this is the
    policy year the contract runs to, matching ``PolicyContext.maturity_year``.
    """
    if policy.maturity_age and policy.issue_age:
        return max(0, int(policy.maturity_age) - int(policy.issue_age))
    return None


def _write_snapshot(ws, row: int, policy) -> None:
    """Write the policy's current inforce snapshot columns (no solve, no MD diff)."""
    _put(ws, row, "plancode", (policy.plancode or "").strip())
    _put(ws, row, "form", (policy.form_number or "").strip())
    _put(ws, row, "loan", round(policy.total_loan_balance, 2), MONEY_FMT)
    _put(ws, row, "face", round(policy.face_amount, 2), MONEY_FMT)
    _put(ws, row, "issue_date", policy.issue_date, DATE_FMT)
    _put(ws, row, "maturity_date", _maturity_date(policy), DATE_FMT)
    _put(ws, row, "maturity_duration", _maturity_duration(policy), INT_FMT)
    _put(ws, row, "maturity_age", int(policy.maturity_age) if policy.maturity_age else None, INT_FMT)
    _put(ws, row, "valuation_date", policy.valuation_date, DATE_FMT)
    _put(ws, row, "issue_age", policy.issue_age, INT_FMT)
    _put(ws, row, "duration", policy.policy_year, INT_FMT)
    _put(ws, row, "attained_age", policy.attained_age, INT_FMT)
    _put(ws, row, "gsp", round(policy.gsp, 2), MONEY_FMT)
    _put(ws, row, "glp", round(policy.glp, 2), MONEY_FMT)
    _put(ws, row, "accum_lp", round(policy.accumulated_glp, 2), MONEY_FMT)
    _put(ws, row, "prem_td", round(policy.premiums_paid_to_date, 2), MONEY_FMT)
    _put(ws, row, "accum_wd", round(policy.withdrawals_to_date, 2), MONEY_FMT)
    _put(ws, row, "def_life_ins", (policy.def_of_life_ins or "").strip() or None)


def _write_solve(ws, row: int, lte) -> None:
    """Write the solve-derived columns (premium, exception date/duration, total paid)."""
    _put(ws, row, "min_prem", lte.premium, MONEY_FMT)
    _put(ws, row, "total_prem_paid", round(lte.total_premium_paid, 2), MONEY_FMT)
    if lte.enters_exception:
        _put(ws, row, "exc_date", lte.exception_start, DATE_FMT)
        _put(ws, row, "exc_dur", lte.exception_duration, INT_FMT)
    else:
        _put(ws, row, "exc_date", None)
        _put(ws, row, "exc_dur", None)


def _clear_solve(ws, row: int) -> None:
    for key in ("min_prem", "total_prem_paid", "exc_date", "exc_dur"):
        _put(ws, row, key, None)


def _absolute_max_result(engine, policy):
    """Forecast funded to the absolute max (guideline cap), exceptions OFF.

    Pays a premium so large the guideline cap binds every month, so the policy
    is funded to the most the guideline allows — with no GLP-exception rescue.
    Returns ``(label, maturity_av)``: label is "Maturity" if it still reaches the
    maturity age (and ``maturity_av`` is the account value then), otherwise the
    policy year in which it lapses (and ``maturity_av`` is ``None`` — there is no
    maturity). ``(None, None)`` if the projection yields nothing.
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
        return None, None
    if states[-1].attained_age >= policy.maturity_age:
        return "Maturity", round(float(states[-1].av_end_of_month or 0.0), 2)
    lapse = next((s for s in states if s.lapsed), states[-1])
    return lapse.policy_year, None


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
        if flag == "--summarize-only":
            cmd["summarize_only"] = True
            i += 1
            continue
        value = argv[i + 1] if i + 1 < len(argv) else None
        if flag == "--region":
            cmd["region"] = value
        elif flag == "--sheet":
            cmd["sheet"] = value
        elif flag == "--limit":
            cmd["limit"] = int(value)
        elif flag == "--start-policy":
            cmd["start_policy"] = value
        elif flag == "--start-row":
            cmd["start_row"] = int(value)
        elif flag == "--rows":
            cmd["rows"] = [int(r) for r in str(value).replace(",", " ").split()]
        elif flag == "--sidecar":
            cmd["sidecar"] = value
        elif flag == "--replay-sidecar":
            cmd["replay_sidecar"] = value
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
    start_policy = str(cmd.get("start_policy") or "").strip().upper()
    start_row = cmd.get("start_row")
    limit = cmd.get("limit")
    dry_run = bool(cmd.get("dry_run", False))
    summarize_only = bool(cmd.get("summarize_only", False))
    sidecar_arg = cmd.get("sidecar")
    replay_sidecar = cmd.get("replay_sidecar")

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

    if replay_sidecar:
        replay_result = _replay_sidecar(ws, Path(replay_sidecar))
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
                    **replay_result,
                }, indent=2))
                sys.exit(1)
        print(json.dumps({
            "workbook": workbook_path,
            "sheet": ws.title,
            "saved": saved,
            "dry_run": dry_run,
            **replay_result,
        }, indent=2))
        return

    if summarize_only:
        _resolve_columns(ws)
    else:
        _ensure_output_columns(ws)

    # Collect candidate data rows (policy number present in col B, below header).
    data_rows = [
        r for r in range(2, ws.max_row + 1)
        if str(ws[f"B{r}"].value or "").strip()
    ]
    if explicit_rows:
        wanted = {int(r) for r in explicit_rows}
        data_rows = [r for r in data_rows if r in wanted]
    else:
        if start_policy:
            matches = [
                r for r in data_rows
                if str(ws[f"B{r}"].value or "").strip().upper() == start_policy
            ]
            if not matches:
                print(json.dumps({
                    "error": f"start policy not found: {start_policy}",
                    "workbook": workbook_path,
                    "sheet": ws.title,
                }, indent=2))
                sys.exit(1)
            start_row = matches[0]
        if start_row:
            data_rows = [r for r in data_rows if r >= int(start_row)]
        if limit:
            data_rows = data_rows[: int(limit)]

    if summarize_only:
        status_col = COL.get("run_status")
        if status_col is None:
            print(json.dumps({"error": "Run Status header not found"}, indent=2))
            sys.exit(1)
        counts = {}
        for row in data_rows:
            status = str(ws[f"{status_col}{row}"].value or "").strip()
            status = status or "(blank)"
            counts[status] = counts.get(status, 0) + 1
        print(json.dumps({
            "workbook": workbook_path,
            "sheet": ws.title,
            "start_row": data_rows[0] if data_rows else None,
            "end_row": data_rows[-1] if data_rows else None,
            "processed": len(data_rows),
            "status_counts": counts,
        }, indent=2))
        return

    sidecar_path = None
    sidecar_handle = None
    if not dry_run or sidecar_arg:
        sidecar_path = Path(sidecar_arg) if sidecar_arg else _default_sidecar_path(
            workbook_path, ws.title, start_policy, start_row, limit)
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_handle = sidecar_path.open("w", encoding="utf-8")
        print(f"Writing per-row sidecar JSONL: {sidecar_path}")

    def persist_row(row: int, extras: Optional[dict] = None) -> None:
        _write_sidecar(
            sidecar_handle,
            _row_record(ws, row, workbook=workbook_path, region=region, extras=extras),
        )

    engine = IllustrationEngine()
    results = []
    try:
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
                record.update({"status": STATUS_ERROR, "error": str(exc)})
                results.append(record)
                persist_row(row, {"error": str(exc)})
                print(f"row {row:>4}  {policy_number:<12}  ERROR (load): {exc}")
                clear_cache()
                continue

            _write_snapshot(ws, row, policy)

            # ── Absolute Max Prem forecast (runs for every loaded policy) ──
            # Funds to the guideline cap every month (exceptions off); reports whether
            # it reaches maturity and, if so, the account value there.
            try:
                abs_max, abs_max_av = _absolute_max_result(engine, deepcopy(policy))
            except Exception as exc:
                abs_max, abs_max_av = None, None
                print(f"row {row:>4}  {policy_number:<12}  abs-max forecast failed: {exc}")
            _put(ws, row, "abs_max", abs_max)
            _put(ws, row, "abs_max_av", abs_max_av, MONEY_FMT)
            record["abs_max"] = abs_max
            record["abs_max_av"] = abs_max_av

            # ── Active premium-paying riders/benefits + suspense code ──
            pi = get_policy_info(policy_number, region, company)
            riders = active_rider_benefit_codes(pi) if pi is not None else ""
            _put(ws, row, "riders", riders or None)
            if pi is not None:
                _put(ws, row, "suspense_code",
                     f"{pi.suspense_code} - {pi.suspense_description}")

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
                record.update({"status": STATUS_ERROR, "error": check_error,
                               "riders": riders})
                results.append(record)
                persist_row(row, {"error": check_error})
                print(f"row {row:>4}  {policy_number:<12}  ERROR: {check_error}")
                clear_cache()
                continue

            # Each entry: (parenthetical reason code, human-readable detail). A policy
            # loan is no longer a bypass — it is solved with "Apply Premium to Loan
            # First" (the level premium repays the loan before funding the AV).
            bypass = []
            if policy.has_shadow_account:
                bypass.append(("A", "active shadow account (benefit type A)"))
            if md_diff is not None and md_diff != 0.0:
                bypass.append(("MD", f"MD diff {md_diff:,.2f}"))
            if missing_rates:
                bypass.append(("rates missing", "missing rider/benefit rates"))

            if bypass:
                status = f"bypass ({', '.join(code for code, _ in bypass)})"
                reasons = "; ".join(detail for _, detail in bypass)
                _clear_solve(ws, row)
                _put(ws, row, "run_status", status)
                record.update({"status": status, "reasons": reasons,
                               "riders": riders, "md_diff": md_diff})
                results.append(record)
                persist_row(row, {"reasons": reasons})
                print(f"row {row:>4}  {policy_number:<12}  {status}: {reasons}"
                      f"  [abs-max: {abs_max}]")
                clear_cache()
                continue

            # ── Solve (Min Level to Exception) ─────────────────────────
            # Loan policies are solved with Apply Premium to Loan First: the level
            # premium repays the loan before funding the account value.
            try:
                lte = solve_level_to_exception(
                    deepcopy(policy),
                    mode=None,                # each policy's own billing mode
                    start_policy_year=1,
                    allow_exceptions=True,
                    apply_prem_to_loan=policy.has_loans,
                )
            except LevelToExceptionError as exc:
                # Passed the business gates but the solve genuinely can't run —
                # bypass with a reason code (CVAT, else no level premium survives).
                code = "CVAT" if policy.is_cvat else "no solution"
                status = f"bypass ({code})"
                _clear_solve(ws, row)
                _put(ws, row, "run_status", status)
                record.update({"status": status, "error": str(exc),
                               "riders": riders, "md_diff": md_diff})
                results.append(record)
                persist_row(row, {"error": str(exc)})
                print(f"row {row:>4}  {policy_number:<12}  {status}: {exc}")
                clear_cache()
                continue

            _write_solve(ws, row, lte)
            status = STATUS_EXCEPT if lte.enters_exception else STATUS_MATURED
            _put(ws, row, "run_status", status)

            record.update({
                "status": status,
                "plancode": policy.plancode,
                "form": policy.form_number,
                "riders": riders,
                "md_diff": md_diff,
                "mode": lte.mode,
                "min_level_prem": lte.premium,
                "total_premium_paid": lte.total_premium_paid,
                "enters_exception": lte.enters_exception,
                "exception_date": str(lte.exception_start) if lte.exception_start else None,
                "exception_duration": lte.exception_duration,
                "iterations": lte.iterations,
            })
            results.append(record)
            persist_row(row, {
                "mode": lte.mode,
                "enters_exception": lte.enters_exception,
                "iterations": lte.iterations,
            })
            exc_txt = (f"exc {lte.exception_start} (yr {lte.exception_duration})"
                       if lte.enters_exception else "endows")
            print(f"row {row:>4}  {policy_number:<12}  {lte.mode} "
                  f"min level {lte.premium:>12,.2f}  {exc_txt}  "
                  f"total paid {lte.total_premium_paid:>12,.2f}  [abs-max: {abs_max}]")
            clear_cache()
    finally:
        if sidecar_handle is not None:
            sidecar_handle.close()

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
                "sidecar": str(sidecar_path) if sidecar_path else None,
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
        "sidecar": str(sidecar_path) if sidecar_path else None,
        "results": results,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
