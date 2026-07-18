"""Dump the engine's per-month ratchet-COI internals for one projected case.

Runs the SuiteView illustration engine (local SQLite, SUITEVIEW_LOCAL_DATA=1)
with optional premium/face-change inputs and writes one CSV row per month with
the ratchet-banding COI detail (band NARs/rates per coverage, per-coverage COI
charges) so it can be aligned against a RERUN CalcEngine dump (cols PP-QX).

Usage (single JSON arg):
    venv\\Scripts\\python.exe tools/dump_ratchet_projection.py '<json>'

    {"policy":"UL062614","region":"CKPR","months":360,
     "premiums":[{"year":1,"amount":27.67,"mode":"M"}],
     "changes":[{"kind":"face_amount","date":"2027-07-10","value":73000}],
     "tamra":true,"tefra":false,"exact_days":true,
     "out_csv":"<path>"}
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
for _p in (str(ROOT), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

COV_KEYS = ("cov1", "cov2", "cov3", "corr")


def main() -> None:
    cmd = json.loads(sys.argv[1])
    out_csv = cmd.pop("out_csv", None)

    import os

    os.environ["SUITEVIEW_LOCAL_DATA"] = "1"
    import datetime

    from suiteview.core.policy_service import clear_cache
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, IllustrationOptions,
        PolicyChangeEvent, PolicyChangeKind, ScheduledTransaction, TransactionKind,
    )

    opt_kwargs = {}
    for key, opt in (("tefra", "conform_to_tefra"), ("tamra", "conform_to_tamra"),
                     ("exception", "allow_exception_prems"), ("exact_days", "exact_days_interest")):
        if key in cmd:
            opt_kwargs[opt] = bool(cmd[key])
    options = IllustrationOptions(**opt_kwargs)

    evs = [
        PolicyChangeEvent(
            kind=(PolicyChangeKind.FACE_AMOUNT if ch["kind"] == "face_amount"
                  else PolicyChangeKind.DB_OPTION),
            effective_date=datetime.date.fromisoformat(ch["date"]),
            value=(float(ch["value"]) if ch["kind"] == "face_amount" else ch["value"]),
            metadata=ch.get("metadata") or {})
        for ch in cmd.get("changes") or []
    ]
    scheds = [
        ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=int(p["year"]),
            amount=float(p["amount"]), mode=p.get("mode", "A"))
        for p in cmd.get("premiums") or []
    ]
    future = IllustrationInputSet(scheduled_transactions=scheds, policy_changes=evs) \
        if (evs or scheds) else None

    clear_cache()
    policy_data = build_illustration_data(
        cmd["policy"], region=cmd.get("region", "CKPR"),
        company_code=cmd.get("company"))
    states = IllustrationEngine().project(
        policy_data, months=int(cmd.get("months", 360)),
        options=options, future_inputs=future)

    fields = ["row", "duration", "date", "policy_year", "attained_age",
              "face_amount", "av_end_of_month",
              "ratchet_active", "band_break",
              "coi_rate", "coi_charge", "coi_charge_corr", "nar", "nar_corr"]
    for k in COV_KEYS:
        fields += [f"nar_{k}", f"b1nar_{k}", f"b2nar_{k}",
                   f"b1rate_{k}", f"b2rate_{k}", f"charge_{k}"]

    rows = []
    for i, st in enumerate(states):
        rec = {
            "row": i,
            "duration": getattr(st, "duration", None),
            "date": getattr(st, "date", None),
            "policy_year": getattr(st, "policy_year", None),
            "attained_age": getattr(st, "attained_age", None),
            "face_amount": getattr(st, "face_amount", None),
            "av_end_of_month": getattr(st, "av_end_of_month", None),
            "ratchet_active": getattr(st, "ratchet_active", None),
            "band_break": getattr(st, "band_break", None),
            "coi_rate": getattr(st, "coi_rate", None),
            "coi_charge": getattr(st, "coi_charge", None),
            "coi_charge_corr": getattr(st, "coi_charge_corr", None),
            "nar": getattr(st, "nar", None),
            "nar_corr": getattr(st, "nar_corr", None),
        }
        nar_by = getattr(st, "nar_by_coverage", {}) or {}
        b1n = getattr(st, "coi_band1_nar_by_coverage", {}) or {}
        b2n = getattr(st, "coi_band2_nar_by_coverage", {}) or {}
        b1r = getattr(st, "coi_band1_rates_by_coverage", {}) or {}
        b2r = getattr(st, "coi_band2_rates_by_coverage", {}) or {}
        chg = getattr(st, "coi_charges_by_coverage", {}) or {}
        for k in COV_KEYS:
            rec[f"nar_{k}"] = nar_by.get(k)
            rec[f"b1nar_{k}"] = b1n.get(k)
            rec[f"b2nar_{k}"] = b2n.get(k)
            rec[f"b1rate_{k}"] = b1r.get(k)
            rec[f"b2rate_{k}"] = b2r.get(k)
            rec[f"charge_{k}"] = chg.get(k)
        rows.append(rec)

    summary = {
        "policy": cmd["policy"],
        "plancode": policy_data.plancode,
        "issue_date": str(policy_data.issue_date),
        "valuation_date": str(policy_data.valuation_date),
        "segments": [
            {"phase": s.coverage_phase, "issue_date": str(s.issue_date),
             "issue_age": s.issue_age, "face": s.face_amount, "band": s.band,
             "rate_class": s.rate_class, "sex": s.rate_sex}
            for s in policy_data.segments
        ],
        "months": len(states),
        "out_csv": out_csv,
    }

    if out_csv:
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(fields)
            for rec in rows:
                w.writerow([rec[f] for f in fields])
    else:
        summary["preview"] = rows[:6]
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
