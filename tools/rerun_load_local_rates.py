"""Load UL rates from the local rates.sqlite into RERUN's Rates_Control blocks.

This is the offline replacement for RERUN's ``mdl_GetRates.MainGetRates`` VBA,
which queries the UL_Rates SQL Server and pastes result blocks into the
``Span_*`` named ranges on Rates_Control. Here the same nine block queries are
replicated against ``bundled_data/dev/rates.sqlite`` (SQLite dialect; the
merged server views Select_RATE_TRGPREM / Select_RATE_PREMLOAD are synthesized
by joining the split MTP/TBL1MTP/CTP/TBL1CTP and TPP/EPP tables) and written
via Excel COM into a *copy* of the workbook, producing a prepared
"local rates" RERUN that recalculates for the requested plancodes with no
database connection.

Select_RATE_SHDINT (shadow interest) is not in the local export; the
Span_ShadowINT block is left untouched with a warning when a shadow plancode
needs it.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/rerun_load_local_rates.py '<json>'

    {"plancodes": ["1U135100"],          # base plancode(s); riders auto-typed
     "state": "TX",                       # optional; default: workbook's sQueryWithStateCode
     "workbook": "docs/Illustration_UL/RERUN (v20.0).xlsm",   # default shown
     "out": "docs/Illustration_UL/RERUN (v20.0) local.xlsm",  # default shown
     "dry_run": false}                    # true = print block row counts, no COM

Plancode expansion mirrors AddBaseRateTypes / AddTermRiderRateTypes /
AddAPBRiderRateTypes: base plancodes pull Targets/CCOI/GCOI/SCR plus the
config-gated PremLoad/MFEE/SNET/EPU; a configured ShadowPlancode adds its
CCOI (+gated Targets/PremLoad/EPU/ShadowInt); rider plancodes (typed via
rider_table.json CovType) add Targets/CCOI/GCOI (APB also EPU).
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rerun_com import _open_excel, XL_CALC_MANUAL  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RATES_DB = ROOT / "bundled_data" / "dev" / "rates.sqlite"
PLANCODE_TABLE = ROOT / "suiteview" / "illustration" / "plancodes" / "plancode_table.json"
RIDER_TABLE = ROOT / "suiteview" / "illustration" / "plancodes" / "rider_table.json"

DEFAULT_WORKBOOK = ROOT / "docs" / "Illustration_UL" / "RERUN (v20.0).xlsm"
DEFAULT_OUT = ROOT / "docs" / "Illustration_UL" / "RERUN (v20.0) local.xlsm"

XL_UP = -4162
XL_XLSM = 52  # xlOpenXMLWorkbookMacroEnabled

# SQLite expression for SQL Server's RIGHT(CONCAT('000', x), 3)
_A3 = "printf('%03d', {})"
_PC = "REPLACE({}.Plancode, ' ', '')"


def _key(*parts: str) -> str:
    return " || ".join(parts)


def _in_clause(plancodes: list[str]) -> tuple[str, list[str]]:
    return "(" + ",".join("?" * len(plancodes)) + ")", list(plancodes)


def _dur_pivot(n: int) -> str:
    return ", ".join(
        f"MAX(CASE WHEN Duration = {d} THEN Rate END) AS Dur{d}" for d in range(1, n + 1)
    )


# ── The nine block queries (VBA CreateServerSQLString, SQLite dialect) ──────

def q_targets(conn, plancodes):
    """Span_Targets — synthesized Select_RATE_TRGPREM (MTP/TBL1MTP/CTP/TBL1CTP)."""
    ph, params = _in_clause(plancodes)
    keys = """
        SELECT Plancode, Sex, Rateclass, Band, IssueAge FROM Select_RATE_MTP
            WHERE Plancode IN {ph} AND IssueVersion = 1
        UNION
        SELECT Plancode, Sex, Rateclass, Band, IssueAge FROM Select_RATE_CTP
            WHERE Plancode IN {ph} AND IssueVersion = 1
        UNION
        SELECT Plancode, Sex, Rateclass, Band, IssueAge FROM Select_RATE_TBL1MTP
            WHERE Plancode IN {ph} AND IssueVersion = 1
        UNION
        SELECT Plancode, Sex, Rateclass, Band, IssueAge FROM Select_RATE_TBL1CTP
            WHERE Plancode IN {ph} AND IssueVersion = 1
    """.format(ph=ph)
    key_expr = _key(_PC.format("k"), "k.Sex", "k.Rateclass",
                    "printf('%d', k.Band)", _A3.format("k.IssueAge"))
    sql = f"""
        SELECT {_PC.format('k')}, k.Sex, k.Rateclass, k.Band, k.IssueAge,
               {key_expr} AS RateKey,
               m.Rate, t1m.Rate, c.Rate, t1c.Rate
        FROM ({keys}) k
        LEFT JOIN Select_RATE_MTP m ON m.Plancode = k.Plancode AND m.IssueVersion = 1
             AND m.Sex = k.Sex AND m.Rateclass = k.Rateclass AND m.Band = k.Band
             AND m.IssueAge = k.IssueAge
        LEFT JOIN Select_RATE_TBL1MTP t1m ON t1m.Plancode = k.Plancode AND t1m.IssueVersion = 1
             AND t1m.Sex = k.Sex AND t1m.Rateclass = k.Rateclass AND t1m.Band = k.Band
             AND t1m.IssueAge = k.IssueAge
        LEFT JOIN Select_RATE_CTP c ON c.Plancode = k.Plancode AND c.IssueVersion = 1
             AND c.Sex = k.Sex AND c.Rateclass = k.Rateclass AND c.Band = k.Band
             AND c.IssueAge = k.IssueAge
        LEFT JOIN Select_RATE_TBL1CTP t1c ON t1c.Plancode = k.Plancode AND t1c.IssueVersion = 1
             AND t1c.Sex = k.Sex AND t1c.Rateclass = k.Rateclass AND t1c.Band = k.Band
             AND t1c.IssueAge = k.IssueAge
        ORDER BY RateKey
    """
    return conn.execute(sql, params * 4).fetchall()


def q_premload(conn, plancodes):
    """Span_PremiumLoad — synthesized Select_RATE_PREMLOAD (TPP/EPP)."""
    ph, params = _in_clause(plancodes)
    keys = """
        SELECT Plancode, Scale, Band, Duration FROM Select_RATE_TPP
            WHERE Plancode IN {ph} AND IssueVersion = 1 AND Scale IN (0, 1) AND Duration <= 11
        UNION
        SELECT Plancode, Scale, Band, Duration FROM Select_RATE_EPP
            WHERE Plancode IN {ph} AND IssueVersion = 1 AND Scale IN (0, 1) AND Duration <= 11
    """.format(ph=ph)
    key_expr = _key(_PC.format("k"), "printf('%d', k.Scale)",
                    "printf('%d', k.Band)", _A3.format("k.Duration"))
    sql = f"""
        SELECT {_PC.format('k')}, k.Scale, k.Band, k.Duration,
               {key_expr} AS RateKey,
               MAX(t.Rate), MAX(e.Rate)
        FROM ({keys}) k
        LEFT JOIN Select_RATE_TPP t ON t.Plancode = k.Plancode AND t.IssueVersion = 1
             AND t.Scale = k.Scale AND t.Band = k.Band AND t.Duration = k.Duration
        LEFT JOIN Select_RATE_EPP e ON e.Plancode = k.Plancode AND e.IssueVersion = 1
             AND e.Scale = k.Scale AND e.Band = k.Band AND e.Duration = k.Duration
        GROUP BY k.Plancode, k.Scale, k.Band, k.Duration
        ORDER BY RateKey
    """
    return conn.execute(sql, params * 2).fetchall()


def q_select_ccoi(conn, plancodes):
    """Span_Select_CCOI — current COI pivoted to Dur1..121 (Scale = 1)."""
    ph, params = _in_clause(plancodes)
    key_expr = _key("REPLACE(Plancode, ' ', '')", "Sex", "Rateclass",
                    "printf('%d', Band)", _A3.format("IssueAge"))
    sql = f"""
        SELECT REPLACE(Plancode, ' ', ''), Sex, Rateclass, Band, IssueAge,
               {key_expr} AS RateKey, {_dur_pivot(121)}
        FROM Select_RATE_COI
        WHERE Plancode IN {ph} AND IssueVersion = 1 AND Scale = 1
        GROUP BY Plancode, Sex, Rateclass, Band, IssueAge
        ORDER BY RateKey
    """
    return conn.execute(sql, params).fetchall()


def q_ultimate_gcoi(conn, plancodes):
    """Span_Ultimate_GCOI — guaranteed COI by attained age (Scale = 0)."""
    ph, params = _in_clause(plancodes)
    key_expr = _key("REPLACE(Plancode, ' ', '')", "Sex", "Rateclass",
                    _A3.format("IssueAge + Duration - 1"))
    sql = f"""
        SELECT REPLACE(Plancode, ' ', ''), Sex, Rateclass,
               IssueAge + Duration - 1 AS AttainedAge,
               {key_expr} AS RateKey, MAX(Rate)
        FROM Select_RATE_COI
        WHERE Plancode IN {ph} AND IssueVersion = 1 AND Scale = 0 AND Duration > 0
        GROUP BY Plancode, Sex, Rateclass, IssueAge + Duration - 1
        ORDER BY RateKey
    """
    return conn.execute(sql, params).fetchall()


def q_scr(conn, plancodes, state):
    """Span_SCR — surrender charge rates pivoted to Dur1..20 for one state.

    Plancodes with no rows for the requested state fall back to state "AA"
    (the all-states code — most plancodes only carry AA rows).
    """
    def _run(pcs, st):
        ph, params = _in_clause(pcs)
        key_expr = _key("REPLACE(Plancode, ' ', '')", "Sex", "Rateclass", _A3.format("IssueAge"))
        sql = f"""
            SELECT REPLACE(Plancode, ' ', ''), Sex, Rateclass, IssueAge,
                   {key_expr} AS RateKey, {_dur_pivot(20)}
            FROM Select_RATE_SCR
            WHERE Plancode IN {ph} AND IssueVersion = 1 AND State = ?
            GROUP BY Plancode, Sex, Rateclass, State, IssueAge
            ORDER BY RateKey
        """
        return conn.execute(sql, params + [st]).fetchall()

    rows = _run(plancodes, state)
    if state != "AA":
        missing = [pc for pc in plancodes if pc not in {str(r[0]) for r in rows}]
        if missing:
            rows = sorted(rows + _run(missing, "AA"), key=lambda r: str(r[4]))
    return rows


def q_epu(conn, plancodes):
    """Span_EPU — expense per unit pivoted to Dur1..21 (Scale 0 and 1)."""
    ph, params = _in_clause(plancodes)
    key_expr = _key("REPLACE(Plancode, ' ', '')", "printf('%d', Scale)", "Sex", "Rateclass",
                    "printf('%d', Band)", _A3.format("IssueAge"))
    sql = f"""
        SELECT REPLACE(Plancode, ' ', ''), Scale, Sex, Rateclass, Band, IssueAge,
               {key_expr} AS RateKey, {_dur_pivot(21)}
        FROM Select_RATE_EPU
        WHERE Plancode IN {ph} AND IssueVersion = 1 AND Scale IN (0, 1)
        GROUP BY Plancode, Scale, Sex, Rateclass, Band, IssueAge
        ORDER BY RateKey
    """
    return conn.execute(sql, params).fetchall()


def q_mfee(conn, plancodes):
    """Span_MFEE — monthly fee rows (Scale 0/1, Duration <= 11)."""
    ph, params = _in_clause(plancodes)
    key_expr = _key("REPLACE(Plancode, ' ', '')", "printf('%d', Scale)", "printf('%d', Band)",
                    _A3.format("IssueAge"), _A3.format("Duration"))
    sql = f"""
        SELECT REPLACE(Plancode, ' ', ''), Scale, Band, IssueAge, Duration,
               {key_expr} AS RateKey, Rate
        FROM Select_RATE_MFEE
        WHERE Plancode IN {ph} AND IssueVersion = 1 AND Scale IN (0, 1) AND Duration <= 11
        GROUP BY Plancode, Scale, Band, IssueAge, Duration, Rate
        ORDER BY RateKey
    """
    return conn.execute(sql, params).fetchall()


def q_snet(conn, plancodes):
    """Span_SNET — safety-net period by issue age (no IssueVersion filter, as in VBA)."""
    ph, params = _in_clause(plancodes)
    key_expr = _key("REPLACE(Plancode, ' ', '')", _A3.format("IssueAge"))
    sql = f"""
        SELECT REPLACE(Plancode, ' ', ''), IssueAge, {key_expr} AS RateKey, Rate
        FROM Select_RATE_SNETPERIOD
        WHERE Plancode IN {ph}
        GROUP BY Plancode, IssueAge, Rate
        ORDER BY RateKey
    """
    return conn.execute(sql, params).fetchall()


# ── Plancode expansion (VBA AddBaseRateTypes / rider variants) ──────────────

def _load_json(path: Path, list_key: str) -> dict[str, dict]:
    with open(path, "r") as fh:
        data = json.load(fh)
    return {str(rec.get("Plancode", "")).strip(): rec for rec in data[list_key]}


def _is_table(value) -> bool:
    return str(value).strip().upper() == "TABLE"


def expand_plancodes(base_plancodes: list[str]) -> tuple[dict[str, set], list[str]]:
    """Return ({family: plancode_set}, warnings) mirroring MainGetRates."""
    plan_cfg = _load_json(PLANCODE_TABLE, "Plancodes")
    rider_cfg = _load_json(RIDER_TABLE, "Riders")

    fams: dict[str, set] = {k: set() for k in (
        "targets", "premload", "ccoi", "gcoi", "scr", "epu", "mfee", "snet", "shadowint")}
    warnings: list[str] = []

    for pc in (str(p).strip() for p in base_plancodes):
        if not pc:
            continue
        rider = rider_cfg.get(pc)
        if rider is not None:
            cov = str(rider.get("CovType", "")).strip().upper()
            fams["targets"].add(pc)
            fams["ccoi"].add(pc)
            fams["gcoi"].add(pc)
            if cov == "APB":
                fams["epu"].add(pc)
            continue

        cfg = plan_cfg.get(pc)
        fams["targets"].add(pc)
        fams["ccoi"].add(pc)
        fams["gcoi"].add(pc)
        fams["scr"].add(pc)
        if cfg is None:
            # Unknown plancode: query every optional family rather than drop rates.
            warnings.append(f"{pc}: not in plancode_table.json; querying all rate families")
            for fam in ("premload", "mfee", "snet", "epu"):
                fams[fam].add(pc)
            continue

        if _is_table(cfg.get("PremiumLoad")):
            fams["premload"].add(pc)
        if _is_table(cfg.get("MFEE")):
            fams["mfee"].add(pc)
        if _is_table(cfg.get("SafetyNetPeriod")):
            fams["snet"].add(pc)
        if _is_table(cfg.get("EPU_Code")):
            fams["epu"].add(pc)

        shadow = str(cfg.get("ShadowPlancode", "") or "").strip()
        if shadow and shadow not in ("NA", "0"):
            fams["ccoi"].add(shadow)
            if _is_table(cfg.get("ShadowTarget")):
                fams["targets"].add(shadow)
            if _is_table(cfg.get("ShadowPremLoadCode")):
                fams["premload"].add(shadow)
            if _is_table(cfg.get("ShadowEPUCode")):
                fams["epu"].add(shadow)
            if _is_table(cfg.get("ShadowIntRateCode")):
                fams["shadowint"].add(shadow)

    return fams, warnings


# ── Block assembly ──────────────────────────────────────────────────────────

BLOCK_WIDTHS = {
    "Span_Targets": 10,
    "Span_PremiumLoad": 7,
    "Span_Select_CCOI": 127,
    "Span_Ultimate_GCOI": 6,
    "Span_SCR": 25,
    "Span_EPU": 28,
    "Span_MFEE": 7,
    "Span_SNET": 4,
}


def build_blocks(fams: dict[str, set], state: str) -> tuple[dict[str, list], list[str]]:
    conn = sqlite3.connect(f"file:{RATES_DB.as_posix()}?mode=ro", uri=True)
    warnings: list[str] = []
    try:
        blocks: dict[str, list] = {}
        spec = [
            ("Span_Targets", "targets", lambda p: q_targets(conn, p)),
            ("Span_PremiumLoad", "premload", lambda p: q_premload(conn, p)),
            ("Span_Select_CCOI", "ccoi", lambda p: q_select_ccoi(conn, p)),
            ("Span_Ultimate_GCOI", "gcoi", lambda p: q_ultimate_gcoi(conn, p)),
            ("Span_SCR", "scr", lambda p: q_scr(conn, p, state)),
            ("Span_EPU", "epu", lambda p: q_epu(conn, p)),
            ("Span_MFEE", "mfee", lambda p: q_mfee(conn, p)),
            ("Span_SNET", "snet", lambda p: q_snet(conn, p)),
        ]
        for span, fam, fn in spec:
            plancodes = sorted(fams[fam])
            if not plancodes:
                continue
            rows = [list(r) for r in fn(plancodes)]
            blocks[span] = rows
            found = {str(r[0]) for r in rows}
            for pc in plancodes:
                if pc not in found:
                    warnings.append(f"{span}: no local rows for plancode {pc}")
        if fams["shadowint"]:
            warnings.append(
                "Span_ShadowINT: Select_RATE_SHDINT not in local rates.sqlite; block left "
                f"untouched for {sorted(fams['shadowint'])} (laptop export needed)")
        return blocks, warnings
    finally:
        conn.close()


# ── COM write ───────────────────────────────────────────────────────────────

def _span_range(xl, wb, name: str):
    """Resolve a Span_* name to its anchor Range (handles INDIRECT-defined names)."""
    try:
        return wb.Names(name).RefersToRange
    except Exception:
        return xl.Evaluate(name)


def write_blocks(workbook: Path, out: Path, blocks: dict[str, list],
                 plancodes_present: list[str]) -> dict:
    if workbook.resolve() != out.resolve():
        shutil.copyfile(workbook, out)
    xl = _open_excel()
    report = {}
    try:
        wb = xl.Workbooks.Open(str(out), UpdateLinks=0, ReadOnly=False)
        xl.Calculation = XL_CALC_MANUAL

        for span, rows in blocks.items():
            anchor = _span_range(xl, wb, span)
            ws = anchor.Worksheet
            r0 = int(anchor.Row)
            c0 = int(anchor.Column)
            width = BLOCK_WIDTHS[span]

            # Clear the existing block (anchor row down to last used row in col c0).
            last = int(ws.Cells(ws.Rows.Count, c0).End(XL_UP).Row)
            clear_rows = max(last, r0) - r0 + 1
            ws.Range(ws.Cells(r0, c0), ws.Cells(r0 + clear_rows - 1, c0 + width - 1)).ClearContents

            if rows:
                data = tuple(tuple(cell for cell in row) for row in rows)
                ws.Range(ws.Cells(r0, c0), ws.Cells(r0 + len(rows) - 1, c0 + width - 1)).Value = data
            report[span] = len(rows)

        # Mirror VBA: record which plancodes this rate set covers.
        try:
            pres = wb.Names("vPlancodesPresent").RefersToRange
            pres.ClearContents
            for i, pc in enumerate(plancodes_present[: int(pres.Rows.Count)], start=1):
                pres.Cells(i, 1).Value = pc
        except Exception as exc:
            report["vPlancodesPresent_error"] = str(exc)

        xl.CalculateFull()
        wb.SaveAs(str(out), FileFormat=XL_XLSM)
        wb.Close(SaveChanges=False)
    finally:
        xl.Quit()
    return report


def _read_default_state(workbook: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    try:
        dn = wb.defined_names["sQueryWithStateCode"]
        for sheet, coord in dn.destinations:
            return str(wb[sheet][coord].value or "").strip()
    finally:
        wb.close()
    return ""


def main():
    cmd = json.loads(sys.argv[1])
    workbook = Path(cmd.get("workbook") or DEFAULT_WORKBOOK).resolve()
    out = Path(cmd.get("out") or DEFAULT_OUT).resolve()
    base_plancodes = cmd["plancodes"]

    if not workbook.exists():
        print(json.dumps({"ok": False, "error": f"workbook not found: {workbook}"}))
        sys.exit(1)
    if not RATES_DB.exists():
        print(json.dumps({"ok": False, "error": f"rates db not found: {RATES_DB}"}))
        sys.exit(1)

    state = str(cmd.get("state") or _read_default_state(workbook)).strip()

    fams, warnings = expand_plancodes(base_plancodes)
    blocks, w2 = build_blocks(fams, state)
    warnings.extend(w2)

    result = {
        "ok": True,
        "workbook": str(workbook),
        "state": state,
        "families": {k: sorted(v) for k, v in fams.items() if v},
        "block_rows": {k: len(v) for k, v in blocks.items()},
        "warnings": warnings,
    }

    if cmd.get("dry_run"):
        result["dry_run"] = True
        print(json.dumps(result, indent=2))
        return

    result["out"] = str(out)
    result["written"] = write_blocks(workbook, out, blocks, sorted(fams["targets"]))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
