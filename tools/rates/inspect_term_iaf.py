r"""Report the Term rate space inside an IAF file.

Diagnostic companion to the Term Rate Workup: parses one IAF and prints the
facts the workup derives from it — plan header maturity fields, the base
(Sex, Rateclass, Band) combo space, benefit plan_options, and the select /
ultimate age-duration extents that determine how far compiled rates run.

Usage:
    venv\Scripts\python.exe tools\rates\inspect_term_iaf.py "<IAF file>"
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from suiteview.ratemanager.parser import IAFParser


def _clean_option(opt: str) -> str:
    return (opt or "").replace("*", "").strip()


def _map_sex(code: str) -> str:
    return {"1": "M", "2": "F"}.get(code, code)


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: inspect_term_iaf.py <IAF file>"}))
        sys.exit(1)
    path = sys.argv[1]

    result = IAFParser().parse(path)
    if result.error:
        print(json.dumps({"error": result.error}))
        sys.exit(1)

    prod = result.products[0] if result.products else None
    by_option: dict = {}
    for rate in result.rates:
        if rate.rate == 0:
            continue
        opt = _clean_option(rate.plan_option)
        bucket = by_option.setdefault(opt, {
            "combos": set(),
            "rate_types": set(),
            "scale_starts": set(),
            "select_durations": set(),
            "select_issue_ages": set(),
            "ultimate_attained_ages": set(),
            "count": 0,
        })
        bucket["count"] += 1
        bucket["combos"].add((_map_sex(rate.gender), rate.rate_class, rate.band))
        bucket["rate_types"].add(rate.rate_type)
        bucket["scale_starts"].add(rate.scale_start)
        if rate.duration != 99:
            bucket["select_durations"].add(rate.duration + 1)
            bucket["select_issue_ages"].add(rate.issue_age)
        else:
            bucket["ultimate_attained_ages"].add(rate.attained_age)

    def _extent(values):
        return [min(values), max(values)] if values else None

    options = {}
    for opt, bucket in sorted(by_option.items()):
        options[opt or "(base)"] = {
            "rate_count": bucket["count"],
            "combo_count": len(bucket["combos"]),
            "combos_sample": sorted(bucket["combos"])[:6],
            "sexes": sorted({c[0] for c in bucket["combos"]}),
            "rate_classes": sorted({c[1] for c in bucket["combos"]}),
            "bands": sorted({c[2] for c in bucket["combos"]}),
            "rate_types": sorted(bucket["rate_types"]),
            "scale_starts": sorted(bucket["scale_starts"]),
            "select_duration_extent": _extent(bucket["select_durations"]),
            "select_issue_age_extent": _extent(bucket["select_issue_ages"]),
            "ultimate_attained_age_extent": _extent(
                bucket["ultimate_attained_ages"]),
        }

    print(json.dumps({
        "file": os.path.basename(path),
        "plancode": prod.plancode.strip() if prod else "",
        "version": prod.version.strip() if prod else "",
        "eff_date": prod.eff_date if prod else "",
        "pay_age": prod.pay_age if prod else None,
        "pay_age_use": prod.pay_age_use if prod else None,
        "me_age": prod.me_age if prod else None,
        "me_age_use": prod.me_age_use if prod else None,
        "issue_age_low": prod.first if prod else None,
        "issue_age_high": max((p.first for p in result.products), default=0),
        "line_count": result.line_count,
        "rate_count": len(result.rates),
        "options": options,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
