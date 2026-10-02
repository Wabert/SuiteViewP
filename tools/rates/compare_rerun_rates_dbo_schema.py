r"""Compare RERUN's schema ``rates`` reader (``ULRates``) with the legacy dbo ``Rates``.

Read-only, live UL_Rates. For each RERUN UL/IUL plancode (``plancode_table.json``;
``PLAN_DEF`` ISWL plans excluded) and a sample of the dbo rate space (sex/class/band
cells at a few issue ages) it compares every rate kind RERUN loads: COI/EPU/MFEE/TPP/EPP
(current and guaranteed), SCR, MTP/CTP/TBL1, GINT, benefit COI/MTP/CTP, bands and the
shadow account (legacy plancode from ``PlancodeConfig.shadow_plancode``). The engine
reads every kind from schema ``rates``, so every kind is compared. Current
CALENDAR rates are read for a coverage issued ``--issue-date`` (so every year falls
in the latest current scale, as dbo scale 1 holds).

Usage:
    venv\Scripts\python.exe tools\rates\compare_rerun_rates_dbo_schema.py [--plancodes A,B] [--ages 35,60]
        [--cells 4] [--json out.json]

Prints one summary line per plancode and a count of mismatch kinds; ``--json`` writes
every difference. Schema ``rates`` is the reference: a difference is a finding about
dbo or a mapping to review, not automatically a schema error.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.rates import Rates  # noqa: E402
from suiteview.illustration.core.ul_rates import SHADOW, ULRates  # noqa: E402
from suiteview.illustration.models.plancode_config import load_plancode  # noqa: E402

TABLE = ROOT / "suiteview" / "illustration" / "plancodes" / "plancode_table.json"
TOL = 1e-7
AMOUNTS = (10_000, 49_999, 50_000, 50_001, 99_999, 100_000, 249_999, 250_000, 250_001,
           499_999, 500_000, 999_999, 1_000_000, 5_000_000)


def _close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= TOL * max(1.0, abs(float(a)))


def _schedule_diff(dbo, schema):
    """None when equal; else a short description. Trailing zero/None tails are ignored."""
    dbo = list(dbo or [])[1:]
    schema = list(schema or [])[1:]
    if not dbo and not schema:
        return None
    if not dbo:
        return "dbo missing"
    if not schema:
        return "schema missing"
    n = min(len(dbo), len(schema))
    for i in range(n):
        if not _close(dbo[i], schema[i]):
            return f"year {i + 1}: dbo {dbo[i]} schema {schema[i]}"
    longer = dbo[n:] or schema[n:]
    last = (dbo if len(dbo) <= len(schema) else schema)[n - 1] if n else None
    # The engine reads past a schedule's end at its last rate, so a tail that
    # repeats the shorter schedule's last rate is the same schedule.
    if any(v is not None and not _close(v, last) for v in longer):
        return f"length dbo {len(dbo)} schema {len(schema)}"
    return None


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:  # noqa: BLE001 - report every lookup failure
        return None, f"{type(exc).__name__}: {exc}"


def _plancodes(selected):
    rows = json.loads(TABLE.read_text(encoding="utf-8"))["Plancodes"]
    result = []
    for row in rows:
        code = row["Plancode"]
        if selected and code not in selected:
            continue
        result.append(row)
    return result


def _cells(dbo: Rates, plancode: str, limit: int):
    space = dbo.get_rates("RATESPACE", plancode) or []
    cells = sorted({(str(s).strip(), str(c).strip(), int(b)) for s, c, b in space})
    if len(cells) <= limit:
        return cells
    step = max(1, len(cells) // limit)
    return cells[::step][:limit]


def _benefit_types(dbo: Rates, plancode: str):
    rows = dbo._fetch_rates(
        "SELECT DISTINCT BenefitType FROM Select_RATE_BENCOI WHERE Plancode = ? AND IssueVersion = 1",
        [plancode]) or []
    return sorted(str(r[0]).strip() for r in rows)


def compare_plancode(dbo: Rates, ul: ULRates, row: dict, ages, cell_limit: int, issue_date: date):
    plancode = row["Plancode"]
    diffs = []

    def note(kind, detail, **key):
        diffs.append({"plancode": plancode, "kind": kind, "detail": detail, **key})

    plan, error = _call(ul.plan, plancode)
    if error:
        note("PLAN", error)
        return diffs
    if plan.product_family == "ISWL":
        return diffs
    gint_d, _ = _call(dbo.get_rates, "GINT", plancode)
    gint_s, error = _call(ul.get_rates, "GINT", plancode)
    diff = error or _schedule_diff(gint_d, gint_s)
    if diff:
        note("GINT", diff)
    for amount in AMOUNTS:
        band_d, _ = _call(dbo.get_band, plancode, amount, issue_date=issue_date)
        band_s, error = _call(ul.get_band, plancode, amount, issue_date=issue_date)
        if error or band_d != band_s:
            note("BAND", error or f"dbo {band_d} schema {band_s}", amount=amount)
    break_d, _ = _call(dbo.get_band_break, plancode, 2, issue_date=issue_date)
    break_s, error = _call(ul.get_band_break, plancode, 2, issue_date=issue_date)
    if error or not _close(break_d, break_s):
        note("BAND_BREAK", error or f"dbo {break_d} schema {break_s}")

    config, error = _call(load_plancode, plancode)
    if error:
        note("CONFIG", error)
    shadow = config.shadow_plancode if config is not None else ""
    benefit_types = _benefit_types(dbo, plancode)
    for sex, rate_class, band in _cells(dbo, plancode, cell_limit):
        for age in ages:
            key = {"cell": f"{sex}/{rate_class}/{band}", "age": age}
            for kind in ("COI", "EPU", "MFEE", "TPP", "EPP"):
                for scale in (1, 0):
                    d, _ = _call(dbo.get_rates, kind, plancode, age, sex, rate_class, scale=scale, band=band)
                    s, error = _call(ul.get_rates, kind, plancode, age, sex, rate_class, scale=scale,
                                     band=band, issue_date=issue_date)
                    diff = error or _schedule_diff(d, s)
                    if diff:
                        note(f"{kind}{scale}", diff, **key)
            d, _ = _call(dbo.get_rates, "SCR", plancode, age, sex, rate_class, band=band, state="AA")
            s, error = _call(ul.get_rates, "SCR", plancode, age, sex, rate_class, band=band,
                             issue_date=issue_date)
            diff = error or _schedule_diff(d, s)
            if diff:
                note("SCR", diff, **key)
            for kind, dbo_fn, ul_fn in (
                ("MTP", dbo.get_mtp, ul.get_mtp), ("CTP", dbo.get_ctp, ul.get_ctp),
                ("TBL1MTP", dbo.get_tbl1_mtp, ul.get_tbl1_mtp), ("TBL1CTP", dbo.get_tbl1_ctp, ul.get_tbl1_ctp),
            ):
                d, _ = _call(dbo_fn, plancode, age, sex, rate_class, band)
                s, error = _call(ul_fn, plancode, age, sex, rate_class, band, issue_date=issue_date)
                if error or not _close(d, s):
                    note(kind, error or f"dbo {d} schema {s}", **key)
            for ben in benefit_types:
                d, _ = _call(dbo.get_rates, "BENCOI", plancode, age, sex, rate_class, scale=1, band=band,
                             benefit_type=ben)
                s, error = _call(ul.get_rates, "BENCOI", plancode, age, sex, rate_class, scale=1, band=band,
                                 benefit_type=ben, issue_date=issue_date)
                diff = error or _schedule_diff(d, s)
                if diff:
                    note(f"BENCOI {ben}", diff, **key)
                for kind, dbo_fn, ul_fn in (("BENMTP", dbo.get_ben_mtp, ul.get_ben_mtp),
                                            ("BENCTP", dbo.get_ben_ctp, ul.get_ben_ctp)):
                    d, _ = _call(dbo_fn, plancode, age, sex, rate_class, band, ben)
                    s, error = _call(ul_fn, plancode, age, sex, rate_class, band, ben, issue_date=issue_date)
                    if error or not _close(d, s):
                        note(f"{kind} {ben}", error or f"dbo {d} schema {s}", **key)
            if shadow:
                for kind in ("COI", "EPU", "TPP", "EPP"):
                    d, _ = _call(dbo.get_rates, kind, shadow, age, sex, rate_class, scale=1, band=band)
                    s, error = _call(ul.get_rates, kind, plancode, age, sex, rate_class, scale=SHADOW,
                                     band=band, issue_date=issue_date)
                    diff = error or _schedule_diff(d, s)
                    if diff:
                        note(f"SHADOW {kind}", diff, **key)
                d, _ = _call(dbo.get_mtp, shadow, age, sex, rate_class, band)
                s, error = _call(ul.get_mtp, plancode, age, sex, rate_class, band, scale=SHADOW)
                if error or not _close(d, s):
                    note("SHADOW MTP", error or f"dbo {d} schema {s}", **key)
                d, _ = _call(dbo.get_tbl1_mtp, shadow, age, sex, rate_class, band)
                s, error = _call(ul.get_tbl1_mtp, plancode, age, sex, rate_class, band, scale=SHADOW)
                if error or not _close(d, s):
                    note("SHADOW TBL1MTP", error or f"dbo {d} schema {s}", **key)
                d, _ = _call(dbo.get_rates, "GINT", shadow)
                s, error = _call(ul.get_rates, "SHADOW_INT", plancode, age, sex, rate_class,
                                 scale=SHADOW, band=band, issue_date=issue_date)
                diff = error or _schedule_diff(d, s)
                if diff:
                    note("SHADOW INT", diff, **key)
    if shadow:
        d, _ = _call(dbo.get_rates, "DBD", shadow)
        s, error = _call(ul.get_rates, "DBD", plancode, scale=SHADOW)
        diff = error or _schedule_diff(d, s)
        if diff:
            note("SHADOW DBD", diff)
    return diffs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plancodes", default="")
    parser.add_argument("--ages", default="35,60")
    parser.add_argument("--cells", type=int, default=4)
    parser.add_argument("--issue-date", default="2026-06-01")
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    selected = {p.strip().upper() for p in args.plancodes.split(",") if p.strip()}
    ages = [int(a) for a in args.ages.split(",") if a.strip()]
    issue_date = date.fromisoformat(args.issue_date)
    dbo, ul = Rates(), ULRates()
    everything = []
    kinds = Counter()
    for row in _plancodes(selected):
        diffs = compare_plancode(dbo, ul, row, ages, args.cells, issue_date)
        everything.extend(diffs)
        by_kind = Counter(d["kind"].split(" ")[0] if d["kind"].startswith("BEN") else d["kind"] for d in diffs)
        kinds.update(by_kind)
        status = "OK" if not diffs else ", ".join(f"{k} {n}" for k, n in sorted(by_kind.items()))
        illustrable = "" if row.get("CanIllustrate", True) else " [CanIllustrate false]"
        print(f"{row['Plancode']}{illustrable}: {status}", flush=True)
    print("TOTAL:", dict(sorted(kinds.items())))
    if args.json:
        Path(args.json).write_text(json.dumps(everything, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
