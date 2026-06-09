"""Align and diff a RERUN CalcEngine dump against a SuiteView engine dump.

Inputs are CSVs from tools/rerun_com.py (run mode) and tools/run_engine_case.py.
Alignment is by DATE: the engine's inforce snapshot (row 0 = valuation date) is
matched to RERUN's valuation-date row, then both walk forward.

Columns are GROUPED and ORDERED to mirror RERUN (see tools/calc_compare_map.py),
with a detail-level selector and expand/collapse by group.

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/compare_case.py '<json>'

    {"engine_csv":"...","rerun_csv":"...","months":13,
     "detail":"full",            # summary | standard | full
     "groups":["Shadow"],        # optional: only these groups
     "collapse":false,           # true = group-level deltas only
     "include_anchor":false,     # row 0 deltas are reported separately by default
     "rows":[1,6]}               # optional: per-row field values for drill-down
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calc_compare_map import groups_for_level, KIND_TOL  # noqa: E402


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _date10(v):
    return (v or "").strip()[:10]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _engine_val(erow, ef):
    if isinstance(ef, (list, tuple)):
        total = 0.0
        for f in ef:
            n = _num(erow.get(f))
            if n is None:
                return None
            total += n
        return total
    return _num(erow.get(ef))


def main():
    cmd = json.loads(sys.argv[1])
    months = int(cmd.get("months", 13))
    detail = cmd.get("detail", "full")
    group_filter = set(cmd.get("groups") or [])
    collapse = bool(cmd.get("collapse", False))
    include_anchor = bool(cmd.get("include_anchor", False))
    row_window = cmd.get("rows")  # [start, end] inclusive engine-row indices

    engine = _read_csv(cmd["engine_csv"])
    rerun = _read_csv(cmd["rerun_csv"])
    rerun_by_date = {_date10(r.get("C")): r for r in rerun}
    engine_by_row = {int(r["row"]): r for r in engine}

    anchor_date = _date10(cmd.get("anchor") or engine_by_row[0]["date"])
    anchor_rerun = rerun_by_date.get(anchor_date)

    groups = [g for g in groups_for_level(detail)
              if not group_filter or g["name"] in group_filter]

    # Walk aligned rows; accumulate per-field deltas (projected rows and anchor row 0).
    field_stats = {}   # (group, label) -> {max_abs, max_row, rerun_col, kind, anchor_delta}
    drill = []         # optional per-row field values

    for i in range(months + 1):
        erow = engine_by_row.get(i)
        if erow is None:
            break
        edate = _date10(erow["date"])
        rrow = rerun_by_date.get(edate)
        if rrow is None:
            continue
        want_drill = row_window and row_window[0] <= i <= row_window[1]
        drill_rec = {"row": i, "date": edate, "fields": {}} if want_drill else None

        for g in groups:
            for label, ef, rc, kind in g["fields"]:
                key = (g["name"], label)
                st = field_stats.setdefault(key, {
                    "group": g["name"], "label": label, "rerun_col": rc, "kind": kind,
                    "max_abs": 0.0, "max_row": None, "anchor_delta": None,
                })
                if kind in ("date",):
                    if want_drill:
                        drill_rec["fields"][label] = {"rerun": _date10(rrow.get(rc)), "engine": edate}
                    continue
                en = _engine_val(erow, ef)
                rn = _num(rrow.get(rc))
                delta = (en - rn) if (en is not None and rn is not None) else None
                if want_drill:
                    drill_rec["fields"][label] = {"rerun": rn, "engine": en, "delta": delta}
                if delta is None:
                    continue
                if i == 0:
                    st["anchor_delta"] = delta
                    if not include_anchor:
                        continue
                if abs(delta) > st["max_abs"]:
                    st["max_abs"] = abs(delta)
                    st["max_row"] = i
        if want_drill:
            drill.append(drill_rec)

    # Build grouped output.
    out_groups = []
    flagged = []
    for g in groups:
        gfields = []
        gmax = 0.0
        gflagged = []
        for label, ef, rc, kind in g["fields"]:
            if kind == "date":
                continue
            st = field_stats[(g["name"], label)]
            tol = KIND_TOL.get(kind, 0.01)
            ok = st["max_abs"] <= tol
            gmax = max(gmax, st["max_abs"])
            rec = {
                "label": label, "rerun_col": rc, "kind": kind,
                "max_abs_delta": round(st["max_abs"], 7), "max_row": st["max_row"],
                "tol": tol, "ok": ok,
                "anchor_delta": (None if st["anchor_delta"] is None
                                 else round(st["anchor_delta"], 7)),
            }
            if not ok:
                gflagged.append(label)
                flagged.append(f"{g['name']}.{label}")
            if not collapse:
                gfields.append(rec)
        og = {"name": g["name"], "group_max_abs_delta": round(gmax, 7),
              "ok": not gflagged, "flagged": gflagged}
        if not collapse:
            og["fields"] = gfields
        out_groups.append(og)

    out = {
        "anchor_date": anchor_date,
        "anchor_found_in_rerun": anchor_rerun is not None,
        "anchor_rerun_month": anchor_rerun.get("month") if anchor_rerun else None,
        "anchor_valuation_flag": anchor_rerun.get("K") if anchor_rerun else None,
        "detail": detail, "months": months, "include_anchor_in_deltas": include_anchor,
        "groups": out_groups,
        "flagged_fields": flagged,
        "all_ok": not flagged,
    }
    if drill:
        out["drill"] = drill
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
