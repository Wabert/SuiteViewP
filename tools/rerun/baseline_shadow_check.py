"""Check RERUN's from-issue shadow-account replay against CyberLife's XP value.

Usage::

    venv\\Scripts\\python.exe tools\\rerun\\baseline_shadow_check.py --policies 01_UE272086,26_UN013474 \\
        --output-dir <folder> [--sensitivity]
    venv\\Scripts\\python.exe tools\\rerun\\baseline_shadow_check.py \\
        --from-results <shadow_from_issue_results.json> --output-dir <folder> --sensitivity

Read-only against CyberLife DB2 (CKPR) and UL_Rates.  Successor to
``baseline_shadow_from_issue.py`` with three corrections found by the shadow
root-cause investigation (9/30/2026):

* **Same quantity, same point.** CyberLife ``LH_COV_TARGET`` ``TAR_TYP_CD='XP'``
  (segment 58 "policy protection account 1") is the shadow value *after* the
  valuation-date premium and monthly deduction and *before* that month's
  interest -- the engine itself seeds its inforce month that way
  (``shadow_calc``: inforce ``shadow_av = XP``).  The comparison is therefore
  ``MonthlyState.shadow_av`` on the valuation date, not ``shadow_eav``
  (which adds one more month of interest).
* **Pre-issue premiums.** Cash paid with the application (FH_FIXED dates
  before the issue date) is applied at issue instead of being dropped.
* **History completeness.** The replayed premium total is reconciled to
  CyberLife premiums-paid-to-date, and value-affecting FH_FIXED codes that the
  replay cannot represent (AV adjustments S7/P7, internal surrender SI,
  reinstatement PB, ...) are listed.  A policy with an incomplete or
  unrepresentable history is reported as such, not as an engine difference.

``--sensitivity`` re-runs the shadow recursion in pure Python over the engine's
own monthly states (checked to reproduce the engine to the cent) with one rule
changed at a time: monthly-effective interest ``(1+i)^(1/12)``, DB discount
equal to the shadow interest rate, interest on premiums from the receipt date,
off-monthliversary premiums credited at the monthliversary on or before receipt,
and no shadow premium load.  Outputs ``shadow_check_results.json`` and
``shadow_check_summary.md`` in ``--output-dir``.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rerun.baseline_common import (  # noqa: E402
    REGION,
    classify_diff,
    json_dump,
    json_load,
    money,
    traceback_text,
)

PREMIUM_CODES = {"PR", "PI", "PA", "PF", "PT", "PB", "PW"}
LOAN_CODES = {"LN", "LG", "LF", "LM", "LA"}
LOAN_REPAYMENT_CODES = {"PL", "PP", "PX", "IP", "IC", "PV"}
WITHDRAWAL_CODES = {"SN", "SG", "SA", "S6", "SW", "SM", "RC", "RD", "SV"}
GROSS_WITHDRAWAL_CODES = {"SG", "S6", "SW", "RC", "RD", "SV"}
# FH_FIXED codes that change policy values but have no RERUN replay input.
UNREPLAYED_VALUE_CODES = {"S7", "P7", "SI", "CC", "LC"}
QUANTITY_DEFINITION = (
    "LH_COV_TARGET.TAR_PRM_AMT where TAR_TYP_CD='XP' (segment 58 'Policy protection account 1'): "
    "shadow value after the valuation-date premium and monthly deduction, before that month's "
    "interest. Compared with RERUN MonthlyState.shadow_av on the valuation date."
)


def _round(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _is_reversed(row: dict[str, Any]) -> bool:
    return (
        str(row.get("FCB0_REV_IND", "") or "").strip() == "1"
        or str(row.get("FCB2_REV_APPL_IND", "") or "").strip() == "1"
        or str(row.get("FBB3_PROCD_IND", "") or "").strip() == "0"
    )


def _transaction_amount(row: dict[str, Any]) -> float:
    for name in ("GROSS_AMT", "TOT_TRS_AMT", "NET_AMT", "ACC_VAL_GRS_AMT"):
        amount = money(row.get(name))
        if amount is not None:
            return abs(amount)
    return 0.0


def _next_monthliversary(issue_date: date, actual_date: date) -> date:
    from dateutil.relativedelta import relativedelta

    if actual_date <= issue_date:
        return issue_date
    months = (actual_date.year - issue_date.year) * 12 + actual_date.month - issue_date.month
    candidate = issue_date + relativedelta(months=months)
    if candidate < actual_date:
        candidate = issue_date + relativedelta(months=months + 1)
    return candidate


def _transaction_kind(code: str, row: dict[str, Any]):
    from suiteview.illustration.models.input_set import TransactionKind

    if code in PREMIUM_CODES:
        return TransactionKind.PREMIUM, ""
    if code in LOAN_CODES:
        return TransactionKind.LOAN, ("variable" if "V" in str(row.get("LN_TYP_CD", "") or "").upper() else "")
    if code in LOAN_REPAYMENT_CODES:
        return TransactionKind.LOAN_REPAYMENT, ""
    if code in WITHDRAWAL_CODES:
        return TransactionKind.WITHDRAWAL, ("gross" if code in GROSS_WITHDRAWAL_CODES else "net")
    return None, ""


def actual_transactions(pi, policy, end_date: date):
    """FH_FIXED cashflows as month-bucketed ``DatedTransaction`` inputs plus an audit trail.

    Pre-issue premiums are applied on the issue date.  Returns
    ``(dated, audit, code_summary)``.
    """
    from suiteview.illustration.models.input_set import DatedTransaction

    dated, audit = [], []
    codes: dict[str, dict[str, Any]] = {}
    for transaction in pi.activity.get_transactions():
        row = transaction.raw_data
        actual = transaction.trans_date
        if actual is None or policy.issue_date is None or actual > end_date:
            continue
        code = (transaction.trans_code or "").strip().upper() or "(blank)"
        amount = _transaction_amount(row)
        reversed_ = _is_reversed(row)
        summary = codes.setdefault(code, {"count": 0, "amount": 0.0, "reversed_or_pending": 0,
                                          "descriptions": set(), "first_entry_date": None})
        summary["count"] += 1
        summary["amount"] += amount
        summary["descriptions"].add(str(transaction.trans_desc or ""))
        summary["reversed_or_pending"] += int(reversed_)
        entry = str(row.get("ENTRY_DT") or "")[:10] or None
        if entry and (summary["first_entry_date"] is None or entry < summary["first_entry_date"]):
            summary["first_entry_date"] = entry
        if reversed_ or amount <= 0.005:
            continue
        kind, subtype = _transaction_kind(code, row)
        if kind is None:
            continue
        if actual < policy.issue_date and code not in PREMIUM_CODES:
            continue
        bucket = _next_monthliversary(policy.issue_date, actual)
        if bucket > end_date:
            continue
        dated.append(DatedTransaction(kind=kind, effective_date=bucket, amount=amount, subtype=subtype,
                                      metadata={"actual_date": str(actual), "code": code}))
        audit.append({
            "actual_date": str(actual), "bucket_date": str(bucket), "code": code, "kind": str(kind.value),
            "subtype": subtype, "amount": amount, "sequence": transaction.sequence_number,
            "entry_date": entry, "days_to_bucket": (bucket - actual).days,
            "pre_issue": actual < policy.issue_date,
        })
    for summary in codes.values():
        summary["amount"] = round(summary["amount"], 2)
        summary["descriptions"] = sorted(summary["descriptions"])
    return dated, audit, codes


def later_face_changes(policy):
    """Base face increases visible as later current coverage segments (as the original tool)."""
    from suiteview.illustration.models.input_set import PolicyChangeEvent, PolicyChangeKind

    if policy.issue_date is None:
        return [], []
    total = sum(
        seg.original_face_amount if seg.original_face_amount > 0 else seg.face_amount
        for seg in policy.segments
        if seg.is_base and not seg.is_cola and seg.issue_date == policy.issue_date
    )
    by_date: dict[date, float] = defaultdict(float)
    for seg in policy.segments:
        if seg.is_base and not seg.is_cola and seg.issue_date and seg.issue_date > policy.issue_date:
            by_date[seg.issue_date] += seg.original_face_amount if seg.original_face_amount > 0 else seg.face_amount
    changes, audit = [], []
    for when in sorted(by_date):
        total += by_date[when]
        changes.append(PolicyChangeEvent(kind=PolicyChangeKind.FACE_AMOUNT, effective_date=when, value=total,
                                         metadata={"source": "current later base coverage segment"}))
        audit.append({"date": str(when), "type": "face_increase", "target_total_face": total})
    return changes, audit


@dataclass
class ShadowCase:
    """Everything needed to replay one policy's shadow account from issue."""

    key: str
    pi: Any
    base: Any
    config: Any
    inputs: Any
    issue_policy: Any
    months: int
    rates: Any
    audit: list
    codes: dict
    changes: list


def build_case(key: str) -> ShadowCase:
    from suiteview.illustration.api import load_policy_data
    from suiteview.illustration.core.rate_loader import load_rates
    from suiteview.illustration.core.scenario_builder import build_illustration_scenario
    from suiteview.illustration.models.input_set import IllustrationInputSet, ScheduledTransaction, TransactionKind
    from suiteview.illustration.models.plancode_config import load_plancode
    from suiteview.polview.services.policy_service import get_policy_info

    company, policy_number = key.split("_", 1)
    pi = get_policy_info(policy_number, REGION, company)
    base = load_policy_data(policy_number, region=REGION, company_code=company)
    config = load_plancode(base.plancode)
    dated, audit, codes = actual_transactions(pi, base, base.valuation_date)
    changes, change_audit = later_face_changes(base)
    inputs = IllustrationInputSet(
        scheduled_transactions=[ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1, amount=0.0,
                                                     mode="M")],
        dated_transactions=dated,
        policy_changes=changes,
    )
    scenario = build_illustration_scenario(copy.deepcopy(base), future_inputs=inputs, run_from_issue=True)
    issue_policy = scenario.projectable_policy
    months = ((base.valuation_date.year - issue_policy.valuation_date.year) * 12
              + base.valuation_date.month - issue_policy.valuation_date.month)
    rates = load_rates(issue_policy, config)
    return ShadowCase(key, pi, base, config, inputs, issue_policy, months, rates, audit, codes, change_audit)


def run_engine(case: ShadowCase) -> list:
    from suiteview.illustration.api import project_policy
    from suiteview.illustration.models.input_set import IllustrationOptions

    options = IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False,
                                  guideline_forceouts=False, no_lapse=True)
    run = project_policy(case.issue_policy, config=case.config, rates=case.rates, inputs=case.inputs,
                         months=case.months, stop_on_lapse=False, options=options)
    return [s for s in run.states if s.date is not None and s.date >= case.base.issue_date]


def recurse(states: list, valuation_date: date, db_option_b: bool, *, interest: str = "days",
            dbd_from_interest: bool = False, premium_interest: dict | None = None,
            load_scale: float = 1.0, premium_moves: dict | None = None) -> float | None:
    """Pure shadow recursion over engine states (mirrors ``shadow_calc.calculate_shadow``).

    Returns the post-deduction shadow AV on ``valuation_date``.  Inputs that do not
    depend on the shadow balance (premium, load, rates, SA, rider charges, days) are
    read from the engine states; one rule at a time can be changed.  ``premium_moves``
    maps a month date to ``(gross_delta, load_delta)`` to move premium dollars
    between months.
    """
    eav = 0.0
    moves = premium_moves or {}
    for state in states:
        gross_delta, load_delta = moves.get(state.date, (0.0, 0.0))
        gross = state.gross_premium + gross_delta
        load = (state.shadow_prem_load + load_delta) * load_scale
        net = gross - load + (premium_interest or {}).get(state.date, 0.0)
        nar_av = eav + net
        death_benefit = nar_av + state.shadow_sa if db_option_b else state.shadow_sa
        dbd = state.shadow_int_rate if dbd_from_interest else state.shadow_dbd_rate
        nar = death_benefit / (1.0 + dbd) ** (1.0 / 12.0) - nar_av
        coi = _round(nar / 1000.0 * state.shadow_coi_rate)
        av = nar_av - (coi + state.shadow_epu + state.shadow_mfee + state.shadow_rider_charges)
        if state.date == valuation_date:
            return av
        rate = state.shadow_int_rate
        if interest == "monthly":
            effective = (1.0 + rate) ** (1.0 / 12.0) - 1.0
        else:
            effective = (1.0 + rate) ** (state.shadow_days / 365.0) - 1.0
        eav = _round(av + max(0.0, effective * av))
    return None


def receipt_interest(case: ShadowCase, states: list, monthly: bool) -> dict:
    """Interest a premium would earn from its receipt date to the monthliversary it is bucketed to."""
    rate_by_date = {s.date: s.shadow_int_rate for s in states}
    dates = [s.date for s in states]
    extra: dict = {}
    for row in case.audit:
        if row["kind"] != "premium" or row["days_to_bucket"] <= 0 or row["pre_issue"]:
            continue
        bucket = date.fromisoformat(row["bucket_date"])
        rate = rate_by_date.get(bucket, 0.0)
        if monthly:
            previous = [d for d in dates if d < bucket]
            span = (bucket - previous[-1]).days if previous else 30
            add = row["amount"] * ((1.0 + rate) ** (row["days_to_bucket"] / span / 12.0) - 1.0)
        else:
            add = row["amount"] * ((1.0 + rate) ** (row["days_to_bucket"] / 365.0) - 1.0)
        extra[bucket] = extra.get(bucket, 0.0) + add
    return extra


def previous_monthliversary_moves(case: ShadowCase, states: list) -> dict:
    """Move each off-monthliversary premium from its bucket month back to the month it was paid in."""
    by_date = {s.date: s for s in states}
    dates = [s.date for s in states]
    moves: dict = {}
    for row in case.audit:
        if row["kind"] != "premium" or row["days_to_bucket"] <= 0 or row["pre_issue"]:
            continue
        bucket = date.fromisoformat(row["bucket_date"])
        previous = [d for d in dates if d < bucket]
        state = by_date.get(bucket)
        if not previous or state is None or not state.gross_premium:
            continue
        load = state.shadow_prem_load * row["amount"] / state.gross_premium
        for when, sign in ((bucket, -1.0), (previous[-1], 1.0)):
            gross_delta, load_delta = moves.get(when, (0.0, 0.0))
            moves[when] = (gross_delta + sign * row["amount"], load_delta + sign * load)
    return moves


def sensitivity(case: ShadowCase, states: list, xp: float) -> dict[str, Any]:
    val = case.base.valuation_date
    option_b = str(case.issue_policy.db_option or "").upper() in {"B", "2"}
    receipt_days = receipt_interest(case, states, monthly=False)
    receipt_monthly = receipt_interest(case, states, monthly=True)
    previous_mv = previous_monthliversary_moves(case, states)
    variants = {
        "engine_rules": {},
        "monthly_interest": {"interest": "monthly"},
        "dbd_equals_shadow_int": {"dbd_from_interest": True},
        "receipt_date_premium_interest": {"premium_interest": receipt_days},
        "no_shadow_premium_load": {"load_scale": 0.0},
        "monthly_interest+dbd_equals_shadow_int": {"interest": "monthly", "dbd_from_interest": True},
        "monthly_interest+receipt_interest": {"interest": "monthly", "premium_interest": receipt_monthly},
        "monthly_interest+receipt_interest+dbd_equals_shadow_int": {
            "interest": "monthly", "premium_interest": receipt_monthly, "dbd_from_interest": True},
        "monthly_interest+previous_mv_premiums": {"interest": "monthly", "premium_moves": previous_mv},
        "monthly_interest+previous_mv_premiums+dbd_equals_shadow_int": {
            "interest": "monthly", "premium_moves": previous_mv, "dbd_from_interest": True},
    }
    out = {}
    for name, kwargs in variants.items():
        value = recurse(states, val, option_b, **kwargs)
        out[name] = None if value is None else round(value - xp, 2)
    return out


def _benefit_rows(pi) -> list[dict[str, Any]]:
    rows = []
    for benefit in pi.benefits.get_benefits():
        rows.append({
            "type": f"{benefit.benefit_type_cd or ''}{getattr(benefit, 'benefit_subtype_cd', '') or ''}",
            "issue_date": str(benefit.issue_date or ""),
            "cease_date": str(benefit.cease_date or ""),
            "units": float(benefit.units) if benefit.units is not None else None,
        })
    return rows


def _xp_rows(pi) -> list[dict[str, Any]]:
    return [
        {k: (str(v) if not isinstance(v, (int, float, str, type(None))) else v) for k, v in row.items()}
        for row in pi.fetch_table("LH_COV_TARGET")
        if str(row.get("TAR_TYP_CD", "") or "").strip() in {"XP", "XQ"}
    ]


def _history(case: ShadowCase) -> dict[str, Any]:
    premiums = [r for r in case.audit if r["kind"] == "premium"]
    replayed = round(sum(r["amount"] for r in premiums), 2)
    paid = float(case.base.premiums_paid_to_date or 0.0)
    first_entry = min((v["first_entry_date"] for v in case.codes.values() if v["first_entry_date"]), default=None)
    unreplayed = {c: {"count": v["count"], "amount": v["amount"], "descriptions": v["descriptions"]}
                  for c, v in case.codes.items() if c in UNREPLAYED_VALUE_CODES}
    return {
        "premiums_replayed": len(premiums),
        "premium_total_replayed": replayed,
        "premiums_paid_to_date": paid,
        "premium_gap": round(replayed - paid, 2),
        "pre_issue_premiums_applied_at_issue": [r for r in premiums if r["pre_issue"]],
        "off_monthliversary_premiums": sum(1 for r in premiums if r["days_to_bucket"] > 0),
        "first_transaction_date": min((r["actual_date"] for r in case.audit), default=None),
        "first_entry_date": first_entry,
        "loans": sum(1 for r in case.audit if r["kind"] == "loan"),
        "loan_repayments": sum(1 for r in case.audit if r["kind"] == "loan_repayment"),
        "withdrawals": sum(1 for r in case.audit if r["kind"] == "withdrawal"),
        "face_changes_reconstructed": case.changes,
        "unreplayed_value_codes": unreplayed,
        "reinstatement": "PB" in case.codes,
    }


def check_policy(key: str, with_sensitivity: bool) -> dict[str, Any]:
    started = time.time()
    record: dict[str, Any] = {"key": key, "status": "started", "quantity_definition": QUANTITY_DEFINITION}
    try:
        case = build_case(key)
        base = case.base
        xp = float(base.shadow_account_value or 0.0)
        record.update({
            "plancode": base.plancode,
            "company": key.split("_", 1)[0],
            "policy_number": key.split("_", 1)[1],
            "issue_date": str(base.issue_date),
            "valuation_date": str(base.valuation_date),
            "db_option": base.db_option,
            "face_amount": base.face_amount,
            "config_shadow_plancode": case.config.shadow_plancode,
            "ccv_active": bool(base.ccv_active),
            "benefits": _benefit_rows(case.pi),
            "xp_rows": _xp_rows(case.pi),
            "cyberlife_xp": xp,
            "history": _history(case),
        })
        ccv = [b for b in record["benefits"] if b["type"].startswith("A")]
        record["shadow_start"] = ccv[0]["issue_date"] if ccv else None
        if not base.has_shadow_account:
            record["status"] = "not-shadow-active"
            return record
        states = run_engine(case)
        final = next((s for s in states if s.date == base.valuation_date), None)
        if final is None:
            record["status"] = "no-valuation-month"
            return record
        record["status"] = "compared"
        record["rerun_shadow_av"] = round(final.shadow_av, 2)
        record["rerun_shadow_eav_reference"] = final.shadow_eav
        record["diff"] = round(final.shadow_av - xp, 2)
        record["class"] = classify_diff(record["diff"])
        record["final_shadow_rates"] = {name: getattr(final, name) for name in (
            "shadow_sa", "shadow_target_prem", "shadow_prem_load", "shadow_coi_rate", "shadow_dbd_rate",
            "shadow_int_rate", "shadow_days", "shadow_epu", "shadow_mfee", "shadow_rider_charges", "shadow_md")}
        if with_sensitivity:
            record["sensitivity_diff_vs_xp"] = sensitivity(case, states, xp)
            check = recurse(states, base.valuation_date, str(case.issue_policy.db_option or "").upper() in {"B", "2"})
            record["recursion_reproduces_engine"] = check is not None and abs(check - final.shadow_av) < 0.005
    except Exception as exc:  # noqa: BLE001
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["traceback"] = traceback_text()
    finally:
        record["seconds"] = round(time.time() - started, 1)
    return record


def _keys(args) -> list[str]:
    keys = [k.strip() for k in (args.policies or "").split(",") if k.strip()]
    if args.from_results:
        data = json_load(Path(args.from_results))
        keys += [r["key"] for r in data.get("records", []) if r.get("status") in {"compared", "rates-not-loaded"}
                 or r.get("cyberlife_shadow")]
    seen, out = set(), []
    for key in keys:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _write_summary(output_dir: Path, records: list[dict[str, Any]]) -> None:
    by_plan: dict[str, list] = defaultdict(list)
    for record in records:
        by_plan[record.get("plancode", "?")].append(record)
    lines = ["# Shadow account check (shadow_av at valuation vs CyberLife XP)", "",
             f"Created: {datetime.now().isoformat(timespec='seconds')}", "",
             "| Plancode | Policies | Compared | Within $1 | Max abs diff | Premium-gap policies | Unreplayed-code policies |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for plan, rows in sorted(by_plan.items()):
        compared = [r for r in rows if r["status"] == "compared"]
        within = sum(1 for r in compared if abs(r["diff"]) <= 1.0)
        max_diff = max((abs(r["diff"]) for r in compared), default=None)
        gaps = sum(1 for r in rows if abs((r.get("history") or {}).get("premium_gap") or 0) > 0.01)
        unrep = sum(1 for r in rows if (r.get("history") or {}).get("unreplayed_value_codes"))
        lines.append(f"| {plan} | {len(rows)} | {len(compared)} | {within} | "
                     f"{'' if max_diff is None else f'{max_diff:,.2f}'} | {gaps} | {unrep} |")
    lines += ["", "## Policies", "",
              "| Policy | Plancode | XP | RERUN shadow_av | Diff | Premium gap | Sensitivity (diff vs XP) |",
              "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for record in sorted(records, key=lambda r: (r.get("plancode", ""), r["key"])):
        if record["status"] != "compared":
            lines.append(f"| {record['key']} | {record.get('plancode', '')} | {record.get('cyberlife_xp', '')} | "
                         f"{record['status']} | | | {record.get('error', '')[:80]} |")
            continue
        sens = record.get("sensitivity_diff_vs_xp") or {}
        sens_text = "; ".join(f"{k}={v}" for k, v in sens.items() if k != "engine_rules")
        lines.append(f"| {record['key']} | {record['plancode']} | {record['cyberlife_xp']:,.2f} | "
                     f"{record['rerun_shadow_av']:,.2f} | {record['diff']:,.2f} | "
                     f"{record['history']['premium_gap']:,.2f} | {sens_text} |")
    (output_dir / "shadow_check_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--policies", default="", help="Comma-separated <company>_<policy> keys.")
    parser.add_argument("--from-results", default="", help="A shadow_from_issue_results.json to take keys from.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sensitivity", action="store_true")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("The shadow check must read live CyberLife data, not local fixtures.")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    keys = _keys(args)
    for index, key in enumerate(keys, 1):
        record = check_policy(key, args.sensitivity)
        records.append(record)
        json_dump(output_dir / "policy_checks" / f"{key}.json", record)
        print(f"{index}/{len(keys)} {key} {record.get('plancode', '')} {record['status']} "
              f"diff={record.get('diff')} {json.dumps(record.get('sensitivity_diff_vs_xp') or {})}", flush=True)
    json_dump(output_dir / "shadow_check_results.json", {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "quantity_definition": QUANTITY_DEFINITION,
        "status_counts": dict(Counter(r["status"] for r in records)),
        "records": records,
    })
    _write_summary(output_dir, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
