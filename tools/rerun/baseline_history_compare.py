"""Replay CyberLife monthliversary history through the RERUN UL/IUL engine.

Usage:
``venv\\Scripts\\python.exe tools\\rerun\\baseline_history_compare.py
--selection <selected_policies.json> --output-dir <baseline_folder>
[--workers 5] [--limit N] [--force]``

Each policy writes one JSON file under ``policy_results`` so interrupted runs are
resumable. The script uses live CyberLife data and the UL_Rates ``rates`` schema
read-only. It does not modify production code or data.

Comparison rules (harness only; the engine is not changed):

* The rollback seed row is the starting point (CyberLife's own recorded values),
  so every measure on it is classed ``Seed`` and excluded from match counts.
* AV is ``LH_POL_MVRY_VAL.CSV_AMT`` (post-deduction) vs ``av_after_deduction``.
* Charges: COI (``CINS_AMT``), expense (``EXP_CRG_AMT``), other (``OTH_PRM_AMT``),
  total charges (``CINS+OTH`` vs COI+benefit+rider+asset; CyberLife books the
  table/flat COI load in OTH) and MD. When CyberLife records MD = 0 while its
  components are populated, MD is compared with the component sum (flagged).
* Interest credited: ``TOT_CRE_ITS_AMT`` (closes CyberLife's own roll-forward)
  vs the engine's ``interest_credited`` for the same monthliversary span.
* Loans: CyberLife principal + accrued at the monthliversary vs the engine's
  regular/preferred/variable principal + accrued on the same date plus any loan
  advanced that month (the engine's buckets are beginning-of-month; not
  ``policy_debt``, which already includes the accrual to the next monthliversary).
* Withdrawals: CyberLife writes one SN/SM/... row per values phase; the rows of
  one event (date, code) are grouped. The lead row's ``NET_AMT`` is the net
  request (its ``CHARGE_AMT`` is the fee); without one the summed ``GROSS_AMT``
  is replayed as a gross request.
* PW waiver credits are not premiums (no load, outside premium accumulators); the
  UL engine has no waiver-credit mode, so they are excluded and the policy is
  flagged ``waiver_credit_in_window``.
* CVAT deemed cash value (93 segment) is not in DB2 or the history: a selection
  row may carry ``deemed_cash_value`` (as of the rollback start date); without it
  the engine uses DCV = 0 (Robert, 2026-10-06) and the result records
  ``deemed_cash_value_defaulted`` so an NPT-limited month can be read with that in mind.

Per policy the run also writes decomposition inputs under ``<output>/decomp``
(``cyber/<key>.json`` and ``engine/<key>.json``) in the format used by
``baseline_av_decompose.py fit``, so the AV/interest decomposition needs no second
engine replay or DB2 fetch.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rerun.baseline_common import (  # noqa: E402
    REGION,
    classify_diff,
    code_fingerprint,
    json_dump,
    json_load,
    money,
    parse_date,
    rate_state_note,
    safe_policy_key,
    traceback_text,
)


PREMIUM_CODES = {"PR", "PI", "PA", "PF", "PT", "PB"}
WAIVER_CREDIT_CODES = {"PW"}
LOAN_CODES = {"LN", "LG", "LF", "LM", "LA"}
LOAN_REPAYMENT_CODES = {"PL", "PP", "PX", "IP", "IC", "PV"}
WITHDRAWAL_CODES = {"SN", "SG", "SA", "S6", "SW", "SM", "RC", "RD", "SV"}
GROSS_WITHDRAWAL_CODES = {"SG", "S6", "SW", "RC", "RD", "SV"}
ALL_REPLAY_CODES = PREMIUM_CODES | LOAN_CODES | LOAN_REPAYMENT_CODES | WITHDRAWAL_CODES
DECOMP_CASH_FLOW_CODES = ALL_REPLAY_CODES | WAIVER_CREDIT_CODES


def _next_projected_month(policy, actual_date):
    from dateutil.relativedelta import relativedelta

    if policy.issue_date is None or actual_date is None:
        return None
    if actual_date <= policy.valuation_date:
        return policy.valuation_date
    months = (actual_date.year - policy.issue_date.year) * 12 + actual_date.month - policy.issue_date.month
    candidate = policy.issue_date + relativedelta(months=months)
    if candidate < actual_date:
        candidate = policy.issue_date + relativedelta(months=months + 1)
    return candidate


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


def _actual_transactions(pi, policy, start_date, end_date):
    """Return (dated transactions, audit rows, code summary) for the replay window.

    Cash flows dated in ``(start_date, end_date]`` are bucketed to the next
    projected monthliversary. Withdrawal rows of one event are grouped (see the
    module docstring) and PW waiver credits are excluded but audited.
    """
    from suiteview.illustration.models.input_set import DatedTransaction, TransactionKind

    events: list[dict[str, Any]] = []
    withdrawal_events: dict[tuple[str, str], dict[str, Any]] = {}
    all_codes: dict[str, dict[str, Any]] = {}
    for transaction in pi.activity.get_transactions():
        row = transaction.raw_data
        actual_date = transaction.trans_date
        if actual_date is None or actual_date <= start_date or actual_date > end_date:
            continue
        code = (transaction.trans_code or "").strip().upper()
        amount = _transaction_amount(row)
        code_row = all_codes.setdefault(code or "(blank)", {
            "count": 0,
            "amount": 0.0,
            "reversed_or_pending": 0,
            "descriptions": set(),
            "examples": [],
        })
        code_row["count"] += 1
        code_row["amount"] += amount
        code_row["descriptions"].add(str(transaction.trans_desc or ""))
        if _is_reversed(row):
            code_row["reversed_or_pending"] += 1
        if len(code_row["examples"]) < 5:
            code_row["examples"].append({
                "date": str(actual_date),
                "sequence": transaction.sequence_number,
                "amount": amount,
            })
        if _is_reversed(row):
            continue
        if code in WITHDRAWAL_CODES:
            event = withdrawal_events.setdefault((str(actual_date), code), {
                "actual_date": actual_date,
                "code": code,
                "gross": 0.0,
                "lead_net": 0.0,
                "charge": 0.0,
                "pieces": 0,
                "sequences": [],
            })
            event["gross"] += abs(money(row.get("GROSS_AMT")) or 0.0)
            event["lead_net"] = max(event["lead_net"], abs(money(row.get("NET_AMT")) or 0.0))
            event["charge"] += abs(money(row.get("CHARGE_AMT")) or 0.0)
            event["pieces"] += 1
            event["sequences"].append(transaction.sequence_number)
            continue
        if amount <= 0.005:
            continue
        if code in WAIVER_CREDIT_CODES:
            events.append({"kind": "waiver_credit_excluded", "actual_date": actual_date, "code": code,
                           "amount": amount, "subtype": "", "sequence": transaction.sequence_number})
            continue
        kind = None
        subtype = ""
        if code in PREMIUM_CODES:
            kind = TransactionKind.PREMIUM
        elif code in LOAN_CODES:
            kind = TransactionKind.LOAN
            if "V" in str(row.get("LN_TYP_CD", "") or "").upper():
                subtype = "variable"
        elif code in LOAN_REPAYMENT_CODES:
            kind = TransactionKind.LOAN_REPAYMENT
        if kind is None:
            continue
        events.append({"kind": kind, "actual_date": actual_date, "code": code, "amount": amount,
                       "subtype": subtype, "sequence": transaction.sequence_number})
    for event in withdrawal_events.values():
        if event["lead_net"] > 0.005 and event["code"] not in GROSS_WITHDRAWAL_CODES:
            amount, subtype, basis = event["lead_net"], "net", "lead-row NET_AMT (fee = CHARGE_AMT)"
        else:
            amount, subtype, basis = event["gross"], "gross", "sum of per-values-phase GROSS_AMT"
        if amount <= 0.005:
            continue
        events.append({
            "kind": TransactionKind.WITHDRAWAL, "actual_date": event["actual_date"], "code": event["code"],
            "amount": round(amount, 2), "subtype": subtype, "sequence": min(event["sequences"]),
            "withdrawal_event": {
                "pieces": event["pieces"], "gross_sum": round(event["gross"], 2),
                "lead_net": round(event["lead_net"], 2), "charge": round(event["charge"], 2), "basis": basis,
            },
        })
    dated = []
    audit = []
    for event in sorted(events, key=lambda item: (item["actual_date"], str(item["sequence"]))):
        kind = event["kind"]
        actual_date = event["actual_date"]
        bucket_date = _next_projected_month(policy, actual_date)
        if bucket_date is None or bucket_date <= start_date or bucket_date > end_date:
            continue
        days_to_bucket = (bucket_date - actual_date).days
        if kind != "waiver_credit_excluded":
            dated.append(DatedTransaction(
                kind=kind,
                effective_date=bucket_date,
                amount=event["amount"],
                subtype=event["subtype"],
                metadata={"actual_date": str(actual_date), "code": event["code"], "sequence": event["sequence"]},
            ))
        audit.append({
            "actual_date": str(actual_date),
            "bucket_date": str(bucket_date),
            "code": event["code"],
            "kind": kind if isinstance(kind, str) else str(kind.value),
            "subtype": event["subtype"],
            "amount": event["amount"],
            "sequence": event["sequence"],
            "days_to_bucket": days_to_bucket,
            "estimated_interest_to_bucket": 0.0,
            "estimated_net_premium": None,
            "net_ratio_source": "",
            **({"withdrawal_event": event["withdrawal_event"]} if "withdrawal_event" in event else {}),
        })
    compact_codes = {}
    for code, row in all_codes.items():
        compact_codes[code] = {
            **row,
            "amount": round(row["amount"], 2),
            "descriptions": sorted(row["descriptions"]),
        }
    return dated, audit, compact_codes


def _history_rows(policy):
    rows = []
    for snapshot in policy.rollback_snapshots:
        rows.append({
            "date": snapshot.valuation_date,
            "av": snapshot.account_value,
            "coi": snapshot.system_coi_charge,
            "expense": snapshot.system_expense_charge,
            "other": snapshot.system_other_charge,
            "md": snapshot.system_monthly_deduction,
            "shadow": snapshot.shadow_account_value,
            "premiums_paid_to_date": snapshot.premiums_paid_to_date,
            "premiums_ytd": snapshot.premiums_ytd,
            "regular_loan": (snapshot.regular_loan_principal or 0) + (snapshot.regular_loan_accrued or 0),
            "preferred_loan": (snapshot.preferred_loan_principal or 0) + (snapshot.preferred_loan_accrued or 0),
            "variable_loan": (snapshot.variable_loan_principal or 0) + (snapshot.variable_loan_accrued or 0),
            "limitations": list(snapshot.limitations),
            "blocking_errors": list(snapshot.blocking_errors),
        })
    rows.append({
        "date": policy.valuation_date,
        "av": policy.account_value,
        "coi": policy.system_coi_charge,
        "expense": policy.system_expense_charge,
        "other": policy.system_other_charge,
        "md": policy.system_monthly_deduction,
        "shadow": policy.shadow_account_value,
        "premiums_paid_to_date": policy.premiums_paid_to_date,
        "premiums_ytd": policy.premiums_ytd,
        "regular_loan": (policy.regular_loan_principal or 0) + (policy.regular_loan_accrued or 0),
        "preferred_loan": (policy.preferred_loan_principal or 0) + (policy.preferred_loan_accrued or 0),
        "variable_loan": (policy.variable_loan_principal or 0) + (policy.variable_loan_accrued or 0),
        "limitations": [],
        "blocking_errors": [],
    })
    return {row["date"]: row for row in rows if row["date"] is not None}


def _mvry_by_date(mvry_rows) -> dict[Any, dict[str, Any]]:
    """Index raw ``LH_POL_MVRY_VAL`` rows by monthliversary date."""
    indexed = {}
    for row in mvry_rows or []:
        when = parse_date(row.get("MVRY_DT"))
        if when is not None:
            indexed[when] = row
    return indexed


def _add_recorded_interest(cyber_by_date, mvry_by_date) -> None:
    """Attach CyberLife credited interest / NAR from ``LH_POL_MVRY_VAL`` to history rows.

    A null ``OTH_PRM_AMT`` (or ``EXP_CRG_AMT``) on a row whose ``CINS_AMT`` is recorded
    is read as 0.00: CyberLife's own roll-forward ``CSV(prev) + TOT_CRE_ITS_AMT + net
    premiums - (CINS+EXP+OTH) - withdrawals = CSV(cur)`` closes on that reading in every
    replayed month. Such rows are flagged ``components_null_as_zero``.
    """
    for when, row in cyber_by_date.items():
        raw = mvry_by_date.get(when) or {}
        row["interest"] = money(raw.get("TOT_CRE_ITS_AMT"))
        row["guaranteed_interest"] = money(raw.get("GUA_RT_ERN_ITS_AMT"))
        row["nar"] = money(raw.get("NAR_AMT"))
        row["death_benefit"] = money(raw.get("DEATH_BEN_AMT"))
        row["components_null_as_zero"] = []
        if raw and money(raw.get("CINS_AMT")) is not None:
            for name, column in (("coi", "CINS_AMT"), ("expense", "EXP_CRG_AMT"), ("other", "OTH_PRM_AMT")):
                if row.get(name) is None:
                    value = money(raw.get(column))
                    if value is None:
                        value = 0.0
                        row["components_null_as_zero"].append(column)
                    row[name] = value
            if row.get("md") is None:
                row["md"] = float(row["coi"]) + float(row["expense"]) + float(row["other"])
                row["md_from_components"] = True


def _snapshot_for_date(policy, when):
    matches = [snapshot for snapshot in policy.rollback_snapshots if snapshot.valuation_date == when]
    return matches[0] if len(matches) == 1 else None


def _baseline_basis_from_snapshot(policy, when):
    from suiteview.illustration.core.value_rollback import _duration

    snapshot = _snapshot_for_date(policy, when)
    if snapshot is None:
        raise ValueError(f"No unique rollback snapshot exists for {when}.")
    result = copy.deepcopy(policy)
    year, month, duration, age = _duration(policy, when)
    result.rollback_date = when
    result.rollback_source_date = policy.valuation_date
    result.valuation_date = when
    result.policy_year = year
    result.policy_month = month
    result.duration = duration
    result.attained_age = age
    result.account_value = float(snapshot.account_value or 0.0)
    result.system_coi_charge = float(snapshot.system_coi_charge or 0.0)
    result.system_expense_charge = float(snapshot.system_expense_charge or 0.0)
    result.system_other_charge = float(snapshot.system_other_charge or 0.0)
    result.system_monthly_deduction = float(snapshot.system_monthly_deduction or 0.0)
    for name in (
        "regular_loan_principal", "regular_loan_accrued",
        "preferred_loan_principal", "preferred_loan_accrued",
        "variable_loan_principal", "variable_loan_accrued",
    ):
        value = getattr(snapshot, name, None)
        if value is not None:
            setattr(result, name, float(value))
    result.rollback_limitations = [
        *getattr(snapshot, "limitations", []),
        "BASELINE HARNESS BASIS: apply_value_rollback safety gates were bypassed for AV/charge baselining. "
        "The starting basis uses the recorded LH_POL_MVRY_VAL row for AV/system charges and dated loan rows where available, "
        "but keeps current target/accumulator fields. Target-dependent effects are data limitations, not engine findings.",
    ]
    result.starting_basis_assumptions.append("Baseline harness basis: current targets/accumulators retained.")
    return result


def _months_between(start, end) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _measure(cyber, rerun):
    if cyber is None or rerun is None:
        return {"cyberlife": cyber, "rerun": rerun, "diff": None, "class": "Not comparable"}
    diff = float(rerun) - float(cyber)
    return {"cyberlife": float(cyber), "rerun": float(rerun), "diff": diff, "class": classify_diff(diff)}


def _state_values(state) -> dict[str, float]:
    def num(name: str) -> float:
        return float(getattr(state, name, 0.0) or 0.0)

    expense = num("epu_charge") + num("mfee_charge") + num("av_charge")
    other = num("benefit_charges") + num("rider_charges") + num("asset_charge")
    after_deduction = getattr(state, "av_after_deduction", None)
    return {
        "av": float(after_deduction if after_deduction is not None else num("av_end_of_month")),
        "av_end_of_month": num("av_end_of_month"),
        "av_after_deduction": num("av_after_deduction"),
        "coi": num("total_coi_charge"),
        "expense": expense,
        "other": other,
        "total_charges": num("total_coi_charge") + num("benefit_charges") + num("rider_charges") + num("asset_charge"),
        "md": num("total_deduction"),
        "interest": num("interest_credited"),
        "loan": (
            num("rg_loan_princ") + num("rg_loan_accrued")
            + num("pf_loan_princ") + num("pf_loan_accrued")
            + num("vbl_loan_princ") + num("vbl_loan_accrued")
            + num("applied_regular_loan") + num("applied_preferred_loan") + num("applied_variable_loan")
        ),
        "policy_debt": num("policy_debt"),
        "nar": num("total_nar") or num("nar"),
        "shadow": num("shadow_eav"),
    }


def _component_sum(cyber: dict[str, Any]) -> float | None:
    values = [cyber.get("coi"), cyber.get("expense"), cyber.get("other")]
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _charge_sum(cyber: dict[str, Any]) -> float | None:
    values = [cyber.get("coi"), cyber.get("other")]
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _charge_measure(cyber, rerun, *, seed_row: bool) -> dict[str, Any]:
    measured = _measure(cyber, rerun)
    if seed_row:
        measured["class"] = "Seed"
    return measured


def _exclude_shadow_for_history_replay(policy):
    """Let AV/charge replay run when historical shadow is unavailable.

    CYBERLIFE_MONTHLIVERSARY timing does not calculate shadow protection. The
    engine nevertheless blocks a rollback basis that lacks historical shadow AV
    before it reaches that timing branch. For this measurement harness only, we
    clear the blocker and mark shadow as not comparable; all non-shadow AV,
    charge and loan fields still use the selected rollback basis.
    """
    if not getattr(policy, "rollback_requires_shadow_value", False):
        return False
    policy.rollback_requires_shadow_value = False
    policy.rollback_limitations.append(
        "BASELINE HARNESS: historical shadow account value was unavailable, so "
        "shadow protection is excluded from the six-month AV/charge replay. "
        "Shadow values are not compared here; see Shadow From Issue evidence."
    )
    policy.starting_basis_assumptions.append(
        "Baseline harness excluded shadow from six-month replay."
    )
    return True


def _enrich_premium_timing(transaction_audit, states_by_date, policy) -> None:
    rate = float(getattr(policy, "current_interest_rate", 0.0) or 0.0)
    for tx in transaction_audit:
        if tx.get("kind") != "premium":
            continue
        try:
            bucket = parse_date(tx.get("bucket_date"))
        except (TypeError, ValueError):
            bucket = None
        state = states_by_date.get(bucket)
        ratio = 1.0
        if state is not None and float(getattr(state, "gross_premium", 0.0) or 0.0) > 0.005:
            ratio = max(0.0, float(getattr(state, "net_premium", 0.0) or 0.0) / float(getattr(state, "gross_premium", 0.0) or 0.0))
            tx["net_ratio_source"] = f"state.net_premium/state.gross_premium on {bucket}"
        else:
            tx["net_ratio_source"] = "gross premium fallback; state premium unavailable"
        net = float(tx.get("amount") or 0.0) * ratio
        tx["estimated_net_premium"] = net
        tx["estimated_interest_to_bucket"] = net * rate * max(int(tx.get("days_to_bucket") or 0), 0) / 365.0


def _premium_timing_analysis(monthly, transaction_audit) -> dict[str, Any]:
    by_date: dict[str, float] = defaultdict(float)
    for tx in transaction_audit:
        if tx.get("kind") == "premium":
            by_date[str(tx.get("bucket_date"))] += float(tx.get("estimated_interest_to_bucket") or 0.0)
    cumulative = 0.0
    rows = []
    max_abs_unexplained = 0.0
    for row in monthly:
        cumulative += by_date.get(row.get("date"), 0.0)
        diff = ((row.get("av") or {}).get("diff"))
        unexplained = None
        if diff is not None:
            unexplained = float(diff) + cumulative
            max_abs_unexplained = max(max_abs_unexplained, abs(unexplained))
        row["premium_timing"] = {
            "expected_cumulative_interest_missing_from_bucketed_replay": cumulative,
            "av_diff_plus_expected_interest": unexplained,
            "basis": "sum(net premium * current credited rate * days from actual receipt to bucket / 365)",
        }
        rows.append(row["premium_timing"])
    total_expected = sum(float(tx.get("estimated_interest_to_bucket") or 0.0) for tx in transaction_audit if tx.get("kind") == "premium")
    tolerance = max(2.0, abs(total_expected) * 0.25)
    return {
        "premium_transactions": sum(1 for tx in transaction_audit if tx.get("kind") == "premium"),
        "expected_interest_total": total_expected,
        "max_abs_unexplained_after_timing": max_abs_unexplained,
        "tolerance": tolerance,
        "timing_explained": bool(total_expected) and max_abs_unexplained <= tolerance,
        "method": "Compare AV residual after adding expected missed receipt-to-bucket interest; tolerance=max($2,25% of expected timing interest).",
    }


def _loan_timing_analysis(monthly, transaction_audit, policy) -> dict[str, Any]:
    max_loan_diff = 0.0
    for row in monthly:
        diff = ((row.get("loan") or {}).get("diff"))
        if diff is not None:
            max_loan_diff = max(max_loan_diff, abs(float(diff)))
    loan_tx = [tx for tx in transaction_audit if tx.get("kind") in {"loan", "loan_repayment"}]
    loan_balance = (
        float(getattr(policy, "regular_loan_principal", 0.0) or 0.0)
        + float(getattr(policy, "regular_loan_accrued", 0.0) or 0.0)
        + float(getattr(policy, "preferred_loan_principal", 0.0) or 0.0)
        + float(getattr(policy, "preferred_loan_accrued", 0.0) or 0.0)
        + float(getattr(policy, "variable_loan_principal", 0.0) or 0.0)
        + float(getattr(policy, "variable_loan_accrued", 0.0) or 0.0)
    )
    if max_loan_diff <= 1.0:
        classification = "reconciled"
    elif loan_tx:
        classification = "loan transaction timing/cashflow"
    elif loan_balance:
        classification = "loan accrual/capitalization timing"
    else:
        classification = "no recorded loan basis; investigate"
    return {
        "max_abs_loan_diff": max_loan_diff,
        "loan_transaction_count": len(loan_tx),
        "current_loan_balance": loan_balance,
        "classification": classification,
        "note": "Harness buckets dated loan/repayment cash flows to monthliversary dates; engine loan buckets are beginning-of-month before end-of-month accrual.",
    }


def _coi_diagnostic(state, cyber_coi, policy) -> dict[str, Any]:
    nar_total = float(getattr(state, "total_nar", 0.0) or getattr(state, "nar", 0.0) or 0.0)
    diag = {
        "cyberlife_coi": cyber_coi,
        "rerun_coi": float(getattr(state, "total_coi_charge", 0.0) or 0.0),
        "total_nar": nar_total,
        "implied_aggregate_rate_per_1000": None,
        "rerun_aggregate_rate_per_1000": None,
        "nar_by_coverage": getattr(state, "nar_by_coverage", {}),
        "rerun_rates_by_coverage": getattr(state, "coi_rates_by_coverage", {}),
        "rerun_charges_by_coverage": getattr(state, "coi_charges_by_coverage", {}),
        "ratchet_active": getattr(state, "ratchet_active", False),
        "band_break": getattr(state, "band_break", 0.0),
        "coverage_basis": [],
    }
    if cyber_coi is not None and nar_total:
        diag["implied_aggregate_rate_per_1000"] = float(cyber_coi) / nar_total * 1000.0
    if nar_total:
        diag["rerun_aggregate_rate_per_1000"] = diag["rerun_coi"] / nar_total * 1000.0
    for segment in getattr(policy, "segments", []) or []:
        diag["coverage_basis"].append({
            "phase": getattr(segment, "coverage_phase", None),
            "plancode": getattr(segment, "plancode", ""),
            "issue_age": getattr(segment, "issue_age", None),
            "rate_sex": getattr(segment, "rate_sex", ""),
            "rate_class": getattr(segment, "rate_class", ""),
            "band": getattr(segment, "band", None),
            "table_rating": getattr(segment, "table_rating", None),
            "flat_extra": getattr(segment, "flat_extra", None),
            "face_amount": getattr(segment, "face_amount", None),
        })
    return diag


def _premium_reconciliation(policy, cyber_by_date, start_date, end_date, transaction_audit, code_summary):
    start = cyber_by_date.get(start_date, {})
    replayed = sum(row["amount"] for row in transaction_audit if row["kind"] == "premium")
    premium_code_amount = sum(
        row.get("amount", 0.0)
        for code, row in code_summary.items()
        if code in PREMIUM_CODES
    )
    start_paid = start.get("premiums_paid_to_date")
    current_paid = getattr(policy, "premiums_paid_to_date", None)
    delta = None
    if start_paid is not None and current_paid is not None:
        delta = float(current_paid) - float(start_paid)
    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "start_premiums_paid_to_date": start_paid,
        "current_premiums_paid_to_date": current_paid,
        "cyberlife_paid_delta": delta,
        "replayed_premium_total": replayed,
        "premium_code_total_in_window": premium_code_amount,
        "replay_vs_paid_delta": None if delta is None else replayed - delta,
        "code_summary": code_summary,
    }


def _write_decomposition_inputs(output_dir: str, key: str, pi, policy, historical, config, run, start_date) -> None:
    """Write ``baseline_av_decompose.py fit`` inputs from data already loaded for this replay.

    ``cyber/<key>.json`` holds the raw ``LH_POL_MVRY_VAL`` / ``LH_FND_VAL_LOAN`` rows and the
    FH_FIXED cash-flow rows after the rollback date; ``engine/<key>.json`` holds compact
    monthly engine states. Both match the formats written by the decompose tool's own
    ``fetch`` and ``engine`` commands.
    """
    from tools.rerun.baseline_av_decompose import ENGINE_FIELDS, _scalar

    decomp = Path(output_dir) / "decomp"
    transactions = []
    for txn in pi.activity.get_transactions():
        code = (txn.trans_code or "").strip().upper()
        if txn.trans_date is None or txn.trans_date <= start_date or code not in DECOMP_CASH_FLOW_CODES:
            continue
        transactions.append({"date": str(txn.trans_date), "code": code, "seq": txn.sequence_number,
                             "raw": {k: _scalar(v) for k, v in txn.raw_data.items()}})
    json_dump(decomp / "cyber" / f"{key}.json", {
        "key": key,
        "LH_POL_MVRY_VAL": [{k: _scalar(v) for k, v in row.items()} for row in pi.fetch_table("LH_POL_MVRY_VAL")],
        "LH_FND_VAL_LOAN": [{k: _scalar(v) for k, v in row.items()} for row in pi.fetch_table("LH_FND_VAL_LOAN")],
        "transactions": transactions,
    })
    states = []
    for state in run.states:
        row = {name: _scalar(getattr(state, name, None)) for name in ENGINE_FIELDS}
        detail = getattr(state, "premium_allowance_detail", None) or {}
        row["allowance"] = {k: detail.get(k) for k in ("GP_Allowance0", "NPT Allowance0", "TAMRA_Allowance0", "Annual Cap2")}
        states.append(row)
    json_dump(decomp / "engine" / f"{key}.json", {
        "key": key,
        "policy": {
            "is_cvat": bool(getattr(historical, "is_cvat", False)), "is_gpt": bool(getattr(historical, "is_gpt", False)),
            "is_mec": bool(getattr(historical, "is_mec", False)), "db_option": getattr(historical, "db_option", None),
            "total_face": getattr(historical, "total_face", None),
            "current_interest_rate": getattr(historical, "current_interest_rate", None),
            "current_interest_rate_source": getattr(historical, "current_interest_rate_source", ""),
        },
        "config": {
            "interest_method": config.interest_method, "cint_key": config.cint_key, "gint": config.gint,
            "reg_credit": config.loan_charge_rate_curr or config.loan_charge_rate_guar or historical.guaranteed_interest_rate,
            "pref_credit": config.pref_loan_charge_rate_curr or config.pref_loan_charge_rate_guar or historical.guaranteed_interest_rate,
            "withdrawal_fee": config.withdrawal_fee, "min_face_after_wd": config.min_face_after_wd,
            "loan_charge_rate": getattr(config, "loan_charge_rate", None),
        },
        "states": states,
    })


def _policy_features(policy, config) -> dict[str, Any]:
    """Facts about the replayed policy used for feature coverage and root-cause tests."""
    segments = []
    for seg in getattr(policy, "segments", []) or []:
        segments.append({
            "phase": getattr(seg, "coverage_phase", None),
            "plancode": getattr(seg, "plancode", ""),
            "issue_date": str(getattr(seg, "issue_date", "") or ""),
            "face": getattr(seg, "face_amount", None),
            "table_rating": getattr(seg, "table_rating", 0) or 0,
            "flat_extra": getattr(seg, "flat_extra", 0.0) or 0.0,
            "rate_class": getattr(seg, "rate_class", ""),
        })
    benefits = [
        {"type": f"{getattr(b, 'benefit_type', '') or ''}{getattr(b, 'benefit_subtype', '') or ''}",
         "issue_date": str(getattr(b, "issue_date", "") or ""), "cease_date": str(getattr(b, "cease_date", "") or "")}
        for b in getattr(policy, "benefits", []) or []
    ]
    riders = [
        {"plancode": getattr(r, "plancode", ""), "issue_date": str(getattr(r, "issue_date", "") or ""),
         "table_rating": getattr(r, "table_rating", 0) or 0, "flat_extra": getattr(r, "flat_extra", 0.0) or 0.0}
        for r in getattr(policy, "riders", []) or []
    ]
    return {
        "db_option": str(getattr(policy, "db_option", "") or ""),
        "is_cvat": bool(getattr(policy, "is_cvat", False)),
        "segments": segments,
        "benefits": benefits,
        "riders": riders,
        "ccv_active": bool(getattr(policy, "ccv_active", False)),
        "interest_method": getattr(config, "interest_method", ""),
        "loan_charge_rate": getattr(config, "loan_charge_rate_curr", None) or getattr(config, "loan_charge_rate_guar", None),
        "min_face_after_wd": getattr(config, "min_face_after_wd", None),
        "withdrawal_fee": getattr(config, "withdrawal_fee", None),
    }


def _selection_dcv(selection_row: dict[str, Any]) -> float | None:
    """The 93-segment deemed cash value a selection row supplies, if any."""
    value = selection_row.get("deemed_cash_value")
    if value is None or value == "":
        return None
    return float(value)


def compare_policy(selection_row: dict[str, Any], output_dir: str, force: bool = False) -> dict[str, Any]:
    from suiteview.illustration.api import project_policy
    from suiteview.illustration.core.calc_engine import ProjectionTiming
    from suiteview.illustration.core.deemed_cash_value import dcv_defaulted
    from suiteview.illustration.core.value_rollback import apply_value_rollback, available_rollback_dates
    from suiteview.illustration.models.input_set import IllustrationInputSet, IllustrationOptions
    from suiteview.polview.services.policy_service import get_policy_info

    policy_number = selection_row["policy_number"]
    company = selection_row["company"]
    key = safe_policy_key(company, policy_number)
    result_path = Path(output_dir) / "policy_results" / f"{key}.json"
    if result_path.exists() and not force:
        return json_load(result_path)
    started = time.time()
    result: dict[str, Any] = {
        "key": key,
        "company": company,
        "policy_number": policy_number,
        "requested_plancode": selection_row.get("requested_plancode", ""),
        "plancode": selection_row.get("plancode", ""),
        "product_name": selection_row.get("product_name", ""),
        "feature_tags": selection_row.get("feature_tags", []),
        "status": "started",
    }
    try:
        from suiteview.illustration.api import load_policy_data
        from suiteview.illustration.core.rate_loader import load_rates
        from suiteview.illustration.models.input_set import ScheduledTransaction, TransactionKind
        from suiteview.illustration.models.plancode_config import load_plancode

        pi = get_policy_info(policy_number, REGION, company)
        policy = load_policy_data(policy_number, region=REGION, company_code=company)
        result.update({
            "plancode": policy.plancode,
            "product_type": policy.product_type,
            "valuation_date": str(policy.valuation_date or ""),
            "shadow_applicable": bool(policy.ccv_active or policy.shadow_account_value or policy.swam or selection_row.get("shadow_requested")),
            "cyberlife_current_shadow": getattr(policy, "shadow_account_value", None),
        })
        result["month0"] = {
            "system_md": getattr(policy, "system_monthly_deduction", None),
            "system_coi": getattr(policy, "system_coi_charge", None),
            "system_expense": getattr(policy, "system_expense_charge", None),
            "system_other": getattr(policy, "system_other_charge", None),
            "calculated_md": None,
            "variance": None,
            "note": "System values loaded; calculated values require successful rate load/projection.",
        }
        config = load_plancode(policy.plancode)
        rates = load_rates(policy, config)
        run0 = project_policy(policy, config=config, rates=rates, months=0, stop_on_lapse=False)
        s0 = run0.states[0]
        result["month0"] = {
            "system_md": getattr(s0, "system_monthly_deduction", None),
            "calculated_md": getattr(s0, "md_check_calculated_deduction", None),
            "variance": getattr(s0, "md_check_deduction_variance", None),
            "system_coi": getattr(s0, "system_coi_charge", None),
            "system_expense": getattr(s0, "system_expense_charge", None),
            "system_other": getattr(s0, "system_other_charge", None),
            "calculated_coi": getattr(s0, "total_coi_charge", None),
            "calculated_expense": getattr(s0, "epu_charge", 0.0) + getattr(s0, "mfee_charge", 0.0),
            "calculated_other": getattr(s0, "benefit_charges", 0.0) + getattr(s0, "rider_charges", 0.0),
            "shadow_rerun": getattr(s0, "shadow_eav", None),
            "shadow_diff": (
                getattr(s0, "shadow_eav", 0.0) - getattr(policy, "shadow_account_value", 0.0)
                if result.get("shadow_applicable") else None
            ),
        }
        dates = sorted(available_rollback_dates(policy))
        result["available_rollback_dates"] = [str(when) for when in dates]
        if not dates or policy.valuation_date is None:
            result["status"] = "month0-only"
            result["blocker"] = "No available rollback dates within the six-month recorded window."
            json_dump(result_path, result)
            return result
        end_date = policy.valuation_date
        historical = None
        start_date = None
        rollback_attempts = []
        for candidate_date in dates:
            try:
                historical = apply_value_rollback(policy, candidate_date, allow_missing_shadow=True)
                start_date = candidate_date
                rollback_attempts.append({"date": str(candidate_date), "status": "apply_value_rollback"})
                break
            except Exception as exc:  # noqa: BLE001
                rollback_attempts.append({"date": str(candidate_date), "status": "blocked", "reason": f"{type(exc).__name__}: {exc}"})
        basis_kind = "canonical rollback"
        if historical is None:
            start_date = dates[0]
            try:
                historical = _baseline_basis_from_snapshot(policy, start_date)
                basis_kind = "harness basis: current targets"
                rollback_attempts.append({"date": str(start_date), "status": basis_kind})
            except Exception as exc:  # noqa: BLE001
                result["status"] = "month0-only"
                result["blocker"] = f"Rollback/fallback blocked: {type(exc).__name__}: {exc}"
                result["rollback_attempts"] = rollback_attempts
                result["traceback"] = traceback_text()
                json_dump(result_path, result)
                return result
        result["rollback_date"] = str(start_date)
        result["rollback_basis"] = basis_kind
        result["rollback_attempts"] = rollback_attempts
        result["shadow_replay_excluded"] = _exclude_shadow_for_history_replay(historical)
        result["iul_av_limitations"] = (
            "IUL six-month AV replay uses recorded total account value; historical bucket/segment balances and index segment crediting history are not reconstructed."
            if str(getattr(historical, "product_type", "")).upper() == "IUL" or getattr(historical, "index_strategy_parameters", None)
            else ""
        )
        dated, transaction_audit, code_summary = _actual_transactions(pi, historical, start_date, end_date)
        zero_schedule = ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1, amount=0.0, mode="M")
        inputs = IllustrationInputSet(scheduled_transactions=[zero_schedule], dated_transactions=dated)
        months = _months_between(start_date, end_date)
        # CVAT deemed cash value: not in DB2/history, so the harness has no source
        # of its own. A selection row may supply one (the 93-segment DCV as of
        # the rollback start date); otherwise the engine uses DCV = 0 and the
        # result records ``deemed_cash_value_defaulted``.
        historical.deemed_cash_value = _selection_dcv(selection_row)
        result["deemed_cash_value"] = historical.deemed_cash_value
        run = project_policy(
            historical,
            config=config,
            rates=rates,
            inputs=inputs,
            # CyberLife applies a loan repayment to principal first (fix E03).
            options=IllustrationOptions(loan_repay_principal_first=True),
            months=months,
            stop_on_lapse=False,
            timing=ProjectionTiming.CYBERLIFE_MONTHLIVERSARY,
        )
        result["deemed_cash_value_defaulted"] = dcv_defaulted(run.states)
        cyber_by_date = _history_rows(policy)
        _add_recorded_interest(cyber_by_date, _mvry_by_date(pi.fetch_table("LH_POL_MVRY_VAL")))
        states_by_date = {state.date: state for state in run.states if state.date is not None}
        _enrich_premium_timing(transaction_audit, states_by_date, historical)
        result["premium_reconciliation"] = _premium_reconciliation(
            policy, cyber_by_date, start_date, end_date, transaction_audit, code_summary
        )
        result["features"] = _policy_features(historical, config)
        result["future_segments"] = [
            seg for seg in result["features"]["segments"]
            if seg["issue_date"] and parse_date(seg["issue_date"]) and parse_date(seg["issue_date"]) > start_date
        ]
        result["waiver_credit_in_window"] = [tx for tx in transaction_audit if tx.get("kind") == "waiver_credit_excluded"]
        result["withdrawal_events"] = [tx for tx in transaction_audit if tx.get("kind") == "withdrawal"]
        _write_decomposition_inputs(output_dir, key, pi, policy, historical, config, run, start_date)
        monthly = []
        coi_details = []
        for when in sorted(cyber_by_date):
            if when < start_date or when > end_date:
                continue
            cyber = cyber_by_date[when]
            state = states_by_date.get(when)
            if state is None:
                monthly.append({"date": str(when), "status": "No RERUN state for date"})
                continue
            values = _state_values(state)
            seed_row = when == start_date
            cyber_md = cyber.get("md")
            md_component_sum = _component_sum(cyber)
            md_component_sum_substituted = False
            if cyber_md is not None and abs(float(cyber_md)) <= 0.005 and md_component_sum not in (None, 0.0):
                cyber_md = md_component_sum
                md_component_sum_substituted = True
            row = {
                "date": str(when),
                "seed_row": seed_row,
                "duration": getattr(state, "duration", None),
                "policy_year": getattr(state, "policy_year", None),
                "policy_month": getattr(state, "policy_month", None),
                "av": _charge_measure(cyber.get("av"), values["av"], seed_row=seed_row),
                "av_alignment": {
                    "cyberlife_csv_amt_semantics": "LH_POL_MVRY_VAL.CSV_AMT is post-deduction monthliversary AV.",
                    "compared_state_field": "av_after_deduction",
                    "rerun_av_after_deduction": values["av_after_deduction"],
                    "rerun_av_end_of_month": values["av_end_of_month"],
                },
                "coi": _charge_measure(cyber.get("coi"), values["coi"], seed_row=seed_row),
                "expense": _charge_measure(cyber.get("expense"), values["expense"], seed_row=seed_row),
                "other": _charge_measure(cyber.get("other"), values["other"], seed_row=seed_row),
                "total_charges": _charge_measure(_charge_sum(cyber), values["total_charges"], seed_row=seed_row),
                "md": _charge_measure(cyber_md, values["md"], seed_row=seed_row),
                "md_component_sum_substituted": md_component_sum_substituted,
                "cyberlife_md_recorded": cyber.get("md"),
                "cyberlife_md_from_components": bool(cyber.get("md_from_components")),
                "cyberlife_components_null_as_zero": cyber.get("components_null_as_zero", []),
                "loan": _charge_measure(
                    (cyber.get("regular_loan") or 0) + (cyber.get("preferred_loan") or 0) + (cyber.get("variable_loan") or 0),
                    values["loan"],
                    seed_row=seed_row,
                ),
                "rerun_policy_debt": values["policy_debt"],
                "interest": _charge_measure(cyber.get("interest"), values["interest"], seed_row=seed_row),
                "nar": {"cyberlife": cyber.get("nar"), "rerun": values["nar"]},
                "shadow": {
                    "cyberlife": cyber.get("shadow"),
                    "rerun": values["shadow"],
                    "diff": None,
                    "class": "Not compared - see Shadow From Issue",
                },
                "rollback_limitations": cyber.get("limitations", []),
                "rollback_blocking_errors": cyber.get("blocking_errors", []),
            }
            monthly.append(row)
            if (
                row["coi"].get("diff") is not None
                and abs(row["coi"]["diff"]) > 1.0
                and row["coi"].get("class") == "Material"
            ):
                coi_diag = _coi_diagnostic(state, cyber.get("coi"), historical)
                coi_diag.update({"date": str(when), "coi_diff": row["coi"]["diff"]})
                coi_details.append(coi_diag)
        max_diffs = {}
        classifications = defaultdict(int)
        for row in monthly:
            for measure in ("av", "coi", "expense", "other", "total_charges", "md", "loan", "interest"):
                item = row.get(measure) or {}
                cls = item.get("class", "Not comparable")
                classifications[f"{measure}:{cls}"] += 1
                diff = item.get("diff")
                if diff is not None and cls in {"Exact", "Rounding", "Material"}:
                    max_diffs[measure] = max(abs(diff), max_diffs.get(measure, 0.0))
        result.update({
            "status": "compared",
            "months_compared": len(monthly),
            "transactions_replayed": transaction_audit,
            "all_transaction_codes_in_window": code_summary,
            "monthly": monthly,
            "coi_details": coi_details,
            "premium_timing_analysis": _premium_timing_analysis(monthly, transaction_audit),
            "loan_timing_analysis": _loan_timing_analysis(monthly, transaction_audit, historical),
            "max_abs_diff": max_diffs,
            "classifications": dict(classifications),
            "rollback_limitations": sorted({msg for row in monthly for msg in row.get("rollback_limitations", [])}),
        })
    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback_text()
    result["seconds"] = round(time.time() - started, 1)
    json_dump(result_path, result)
    return result


def run_compare(args) -> dict[str, Any]:
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Baseline comparison must read live CyberLife data, not local fixtures.")
    selection = json_load(Path(args.selection))
    selected = selection["selected"]
    if args.policy_keys:
        wanted = {key.strip().upper() for key in args.policy_keys.split(",") if key.strip()}
        selected = [
            row for row in selected
            if safe_policy_key(row.get("company", ""), row.get("policy_number", "")).upper() in wanted
            or str(row.get("policy_number", "")).strip().upper() in wanted
        ]
    if args.limit:
        selected = selected[: args.limit]
    output_dir = Path(args.output_dir)
    (output_dir / "policy_results").mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "baseline_progress.log"
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"{datetime.now().isoformat()} comparing {len(selected)} policies workers={args.workers}\n")
    started = time.time()
    run_record: dict[str, Any] = {
        "started_at": datetime.now().isoformat(),
        "policy_count": len(selected),
        "force": bool(args.force),
        "policy_keys": args.policy_keys,
        "code_state_start": code_fingerprint(),
        "rate_state_start": rate_state_note(),
    }
    results = []
    if args.workers <= 1:
        for row in selected:
            results.append(compare_policy(row, str(output_dir), args.force))
            print(f"{results[-1]['key']} {results[-1].get('status')}", flush=True)
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(compare_policy, row, str(output_dir), args.force): row
                for row in selected
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)
                print(f"{result['key']} {result.get('status')}", flush=True)
    summary = {
        "created_at": datetime.now().isoformat(),
        "selection": str(Path(args.selection)),
        "policy_count": len(results),
        "status_counts": dict(defaultdict(int, ((status, sum(1 for row in results if row.get("status") == status)) for status in {row.get("status") for row in results}))),
        "seconds": round(time.time() - started, 1),
        "results": results,
    }
    out = output_dir / ("pilot_comparison_summary.json" if "pilot" in Path(args.selection).name else "comparison_summary.json")
    json_dump(out, summary)
    run_record.update({
        "finished_at": datetime.now().isoformat(),
        "seconds": summary["seconds"],
        "status_counts": summary["status_counts"],
        "code_state_end": code_fingerprint(),
        "rate_state_end": rate_state_note(),
    })
    if args.pdf_coding:
        from tools.rerun.baseline_av_decompose import fetch_pdf_coding

        plancodes = sorted({str(row.get("plancode") or "").strip().upper() for row in results} - {""})
        json_dump(output_dir / "decomp" / "pdf_interest_coding.json", fetch_pdf_coding(plancodes))
        run_record["pdf_coding"] = "dbo.CYBERLIFE_PDF interest coding (plan metadata, not rates) for the decomposition"
    manifest_path = output_dir / "run_manifest.json"
    manifest = json_load(manifest_path) if manifest_path.exists() else {"runs": []}
    manifest["runs"].append(run_record)
    json_dump(manifest_path, manifest)
    print(json.dumps({"output": str(out), "policy_count": len(results), "seconds": summary["seconds"]}, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--policy-keys", default="", help="Comma-separated company_policy keys or policy numbers to run.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--pdf-coding",
        action="store_true",
        help="Also write decomp/pdf_interest_coding.json (dbo.CYBERLIFE_PDF plan metadata, not rates) "
             "for baseline_av_decompose.py fit.",
    )
    args = parser.parse_args()
    run_compare(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
