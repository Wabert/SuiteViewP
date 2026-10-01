"""Measure RERUN from-issue shadow-account replay against CyberLife.

Usage:
``venv\\Scripts\\python.exe tools\\rerun\\baseline_shadow_from_issue.py
--selection C:\\Users\\ab7y02\\.copilot\\session-state\\299757f2-4658-4ced-b8d8-c4a634e5ee7e\\files\\baseline\\selected_policies.json
--plancodes C:\\Users\\ab7y02\\.copilot\\session-state\\299757f2-4658-4ced-b8d8-c4a634e5ee7e\\files\\baseline_plancodes.tsv
--output-dir C:\\Users\\ab7y02\\.copilot\\session-state\\299757f2-4658-4ced-b8d8-c4a634e5ee7e\\files\\shadow``

The tool is read-only against CyberLife DB2 and UL_Rates.  It builds an
issue-mode RERUN scenario, suppresses modal forecast premiums, replays actual
unreversed FH_FIXED premium/loan/repayment/withdrawal transactions as dated
month-bucketed inputs, optionally reconstructs later base face increases from
current coverage segments, and compares the final RERUN shadow EAV with
CyberLife's current XP shadow-account value.  Outputs:

* ``shadow_from_issue_results.json`` — clear per-policy records.
* ``shadow_from_issue_summary.md`` — per-plancode headline and evidence notes.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rerun.baseline_common import (  # noqa: E402
    REGION,
    SYSTEM_CODE,
    classify_diff,
    json_dump,
    json_load,
    money,
    read_requested_plancodes,
    safe_policy_key,
    traceback_text,
)


ACTIVE_PREMIUM_STATUSES = {"21", "22", "31", "32", "41", "42", "43", "44", "45"}
PREMIUM_CODES = {"PR", "PI", "PA", "PF", "PT", "PB", "PW"}
LOAN_CODES = {"LN", "LG", "LF", "LM", "LA"}
LOAN_REPAYMENT_CODES = {"PL", "PP", "PX", "IP", "IC", "PV"}
WITHDRAWAL_CODES = {"SN", "SG", "SA", "S6", "SW", "SM", "RC", "RD", "SV"}
ALL_REPLAY_CODES = PREMIUM_CODES | LOAN_CODES | LOAN_REPAYMENT_CODES | WITHDRAWAL_CODES
RATE_LOAD_LOCK = Path(r"C:\Users\ab7y02\Dev\Cyberlife_Rates\Rates_Database\results\bulk\LOAD.lock")


def _plancode_table_by_code() -> dict[str, dict[str, Any]]:
    from tools.rerun.baseline_common import plancode_table_rows

    return {
        str(row.get("Plancode", "") or "").strip().upper(): row
        for row in plancode_table_rows()
    }


def _shadow_requested_plancodes(plancode_tsv: Path) -> tuple[set[str], dict[str, str]]:
    table = _plancode_table_by_code()
    shadow_codes: set[str] = set()
    shadow_by_code: dict[str, str] = {}
    for code, _product in read_requested_plancodes(plancode_tsv):
        row = table.get(code)
        shadow = str((row or {}).get("ShadowPlancode", "") or "").strip().upper()
        if not shadow:
            continue
        shadow_codes.add(code)
        shadow_by_code[code] = shadow
        if len(code) == 8:
            shadow_codes.add(code)
    return shadow_codes, shadow_by_code


def _selected_shadow_candidates(
    selection: dict[str, Any],
    shadow_codes: set[str],
    shadow_by_code: dict[str, str],
) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for row in selection.get("selected", []):
        requested = str(row.get("requested_plancode", "") or "").strip().upper()
        plan = str(row.get("plancode", "") or "").strip().upper()
        is_shadow_plan = requested in shadow_codes or plan in shadow_codes
        is_shadow_policy = bool(row.get("shadow_applicable")) or bool(row.get("shadow_requested"))
        if not (is_shadow_plan or is_shadow_policy):
            continue
        key = safe_policy_key(str(row.get("company", "")), str(row.get("policy_number", ""))).upper()
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            **row,
            "source": "selected_policies",
            "shadow_requested": row.get("shadow_requested") or shadow_by_code.get(requested, ""),
        })
    return rows


def _connect():
    from suiteview.core.db2_connection import DB2Connection

    db = DB2Connection(REGION)
    return db, db.connect()


def _schema() -> str:
    from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_SCHEMA_MAP

    return REGION_SCHEMA_MAP.get(REGION, DEFAULT_SCHEMA)


def _candidate_sql(schema: str, limit: int) -> str:
    return f"""
WITH CAND AS (
  SELECT
    POL.CK_CMP_CD,
    POL.CK_POLICY_NBR,
    POL.TCH_POL_ID,
    POL.PRM_PAY_STA_REA_CD,
    POL.POL_PRM_AMT,
    POL.NXT_MVRY_PRC_DT,
    COV.PLN_DES_SER_CD,
    COV.ISSUE_DT,
    COALESCE(NTP.DTH_BNF_PLN_OPT_CD, '') AS DB_OPT,
    ROW_NUMBER() OVER (
      PARTITION BY COV.PLN_DES_SER_CD
      ORDER BY
        CASE WHEN POL.PRM_PAY_STA_REA_CD = '22' THEN 0 ELSE 1 END,
        COV.ISSUE_DT DESC,
        POL.CK_POLICY_NBR
    ) AS RN
  FROM {schema}.LH_BAS_POL POL
  INNER JOIN {schema}.LH_COV_PHA COV
    ON COV.CK_SYS_CD = POL.CK_SYS_CD
   AND COV.CK_CMP_CD = POL.CK_CMP_CD
   AND COV.TCH_POL_ID = POL.TCH_POL_ID
   AND COV.COV_PHA_NBR = 1
  LEFT JOIN {schema}.LH_NON_TRD_POL NTP
    ON NTP.CK_SYS_CD = POL.CK_SYS_CD
   AND NTP.CK_CMP_CD = POL.CK_CMP_CD
   AND NTP.TCH_POL_ID = POL.TCH_POL_ID
  WHERE POL.CK_SYS_CD = ?
    AND POL.NON_TRD_POL_IND = '1'
    AND POL.PRM_PAY_STA_REA_CD IN ('21','22','31','32','41','42','43','44','45')
    AND COV.PLN_DES_SER_CD = ?
)
SELECT CK_CMP_CD, CK_POLICY_NBR, TCH_POL_ID, PRM_PAY_STA_REA_CD, POL_PRM_AMT,
       NXT_MVRY_PRC_DT, PLN_DES_SER_CD, ISSUE_DT, DB_OPT
FROM CAND
WHERE RN <= {int(limit)}
ORDER BY RN
"""


def _fetch_candidates(conn, plancode: str, limit: int) -> list[dict[str, Any]]:
    from pyodbc import SQL_VARCHAR

    cur = conn.cursor()
    try:
        parameters = (SYSTEM_CODE, plancode)
        cur.setinputsizes([(SQL_VARCHAR, len(value), 0) for value in parameters])
        cur.execute(_candidate_sql(_schema(), limit), parameters)
        rows = []
        for row in cur.fetchall():
            rows.append({
                "company": str(row[0]).strip(),
                "policy_number": str(row[1]).strip(),
                "tch_pol_id": str(row[2]).strip(),
                "premium_status": str(row[3]).strip(),
                "modal_premium": float(row[4] or 0),
                "next_monthliversary": str(row[5])[:10] if row[5] else "",
                "plancode": str(row[6]).strip(),
                "issue_date": str(row[7])[:10] if row[7] else "",
                "db_option": str(row[8]).strip(),
                "requested_plancode": str(row[6]).strip(),
                "source": "live_fill",
            })
        return rows
    finally:
        cur.close()


def _tag_candidate(candidate: dict[str, Any], shadow_by_code: dict[str, str]) -> dict[str, Any] | None:
    from suiteview.illustration.api import load_policy_data
    from suiteview.polview.services.policy_service import get_policy_info

    company = candidate["company"]
    policy_number = candidate["policy_number"]
    pi = get_policy_info(policy_number, REGION, company)
    if not pi.exists:
        return None
    data = load_policy_data(policy_number, region=REGION, company_code=company)
    if str(pi.status.premium_pay_status_code or "").strip() not in ACTIVE_PREMIUM_STATUSES:
        return None
    coverages = pi.coverages.get_coverages()
    riders = pi.coverages.get_riders()
    benefits = pi.benefits.get_benefits()
    loans = pi.loans.get_loans()
    substandard = []
    for cov in coverages:
        if getattr(cov, "table_rating", None):
            substandard.append(f"cov{cov.cov_pha_nbr}:table{cov.table_rating_code or cov.table_rating}")
        if getattr(cov, "flat_extra", None):
            substandard.append(f"cov{cov.cov_pha_nbr}:flat")
    loan_balance = sum(float(getattr(data, name, 0.0) or 0.0) for name in (
        "regular_loan_principal", "regular_loan_accrued",
        "preferred_loan_principal", "preferred_loan_accrued",
        "variable_loan_principal", "variable_loan_accrued",
    ))
    plan = str(data.plancode or candidate.get("plancode", "")).strip().upper()
    later_segments = [
        seg for seg in data.segments
        if seg.is_base and not seg.is_cola and data.issue_date and seg.issue_date
        and seg.issue_date > data.issue_date
    ]
    feature_tags = []
    if riders:
        feature_tags.append("riders")
    if benefits:
        feature_tags.append("benefits")
    if substandard:
        feature_tags.append("substandard")
    if loan_balance > 0.005:
        feature_tags.append("loan")
    if later_segments:
        feature_tags.append("face-change")
    if str(data.db_option or "").upper() in {"B", "2"}:
        feature_tags.append("db-option-b")
    else:
        feature_tags.append("db-option-a")
    if data.ccv_active or data.shadow_account_value or data.swam:
        feature_tags.append("shadow")
    return {
        **candidate,
        "plancode": plan,
        "requested_plancode": candidate.get("requested_plancode") or plan,
        "shadow_requested": candidate.get("shadow_requested") or shadow_by_code.get(plan, ""),
        "exists": True,
        "premium_status": str(pi.status.premium_pay_status_code or "").strip(),
        "db_option": str(data.db_option or candidate.get("db_option", "")).strip().upper(),
        "product_type": data.product_type,
        "issue_state": data.issue_state,
        "issue_age": data.issue_age,
        "attained_age": data.attained_age,
        "rate_sex": data.rate_sex,
        "rate_class": data.rate_class,
        "face_amount": data.face_amount,
        "account_value": data.account_value,
        "modal_premium": data.modal_premium,
        "valuation_date": str(data.valuation_date or ""),
        "rider_codes": sorted({str(getattr(r, "plancode", "") or "").strip() for r in riders if getattr(r, "plancode", "")}),
        "benefit_codes": sorted({str(getattr(b, "benefit_code", "") or "").strip() for b in benefits if getattr(b, "benefit_code", "")}),
        "substandard_tags": substandard,
        "loan_balance": loan_balance,
        "loan_types": sorted({str(getattr(loan, "loan_type", "") or "").strip() for loan in loans}),
        "shadow_applicable": bool(data.ccv_active or data.shadow_account_value or data.swam),
        "feature_tags": sorted(set(feature_tags)),
        "feature_score": len(set(feature_tags)),
    }


def _clean_sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    tags = set(row.get("feature_tags") or [])
    complex_count = sum(1 for tag in ("loan", "face-change", "substandard", "riders", "benefits") if tag in tags)
    return (complex_count, -int(row.get("shadow_applicable", False)), row.get("policy_number", ""))


def _fill_to_per_plancode(
    selected: list[dict[str, Any]],
    shadow_codes: set[str],
    shadow_by_code: dict[str, str],
    per_plancode: int,
    candidate_limit: int,
) -> list[dict[str, Any]]:
    by_plan: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen = {
        safe_policy_key(str(row.get("company", "")), str(row.get("policy_number", ""))).upper()
        for row in selected
    }
    for row in selected:
        by_plan[str(row.get("plancode", "") or row.get("requested_plancode", "")).strip().upper()].append(row)
    deficits = [
        plan for plan in sorted(shadow_codes)
        if sum(1 for row in by_plan.get(plan, []) if row.get("shadow_applicable")) < per_plancode
        and len(plan) == 8
    ]
    if not deficits:
        return selected
    db, conn = _connect()
    try:
        for plan in deficits:
            needed = per_plancode - sum(
                1 for row in by_plan.get(plan, []) if row.get("shadow_applicable")
            )
            candidates = _fetch_candidates(conn, plan, candidate_limit)
            tagged = []
            for candidate in candidates:
                key = safe_policy_key(candidate["company"], candidate["policy_number"]).upper()
                if key in seen:
                    continue
                try:
                    row = _tag_candidate(candidate, shadow_by_code)
                except Exception:
                    continue
                if row is not None:
                    tagged.append(row)
            for row in sorted(tagged, key=_clean_sort_key)[:needed]:
                selected.append(row)
                by_plan[plan].append(row)
                seen.add(safe_policy_key(row["company"], row["policy_number"]).upper())
    finally:
        db.close()
    return selected


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


def _next_projected_month(issue_date: date | None, actual_date: date | None) -> date | None:
    from dateutil.relativedelta import relativedelta

    if issue_date is None or actual_date is None:
        return None
    months = (actual_date.year - issue_date.year) * 12 + actual_date.month - issue_date.month
    candidate = issue_date + relativedelta(months=months)
    if candidate < actual_date:
        candidate = issue_date + relativedelta(months=months + 1)
    return candidate


def _actual_transactions(pi, policy, end_date: date):
    from suiteview.illustration.models.input_set import DatedTransaction, TransactionKind

    dated = []
    audit = []
    all_codes: dict[str, dict[str, Any]] = {}
    for transaction in pi.activity.get_transactions():
        row = transaction.raw_data
        actual_date = transaction.trans_date
        if actual_date is None or policy.issue_date is None:
            continue
        if actual_date < policy.issue_date or actual_date > end_date:
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
        if _is_reversed(row) or amount <= 0.005:
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
        elif code in WITHDRAWAL_CODES:
            kind = TransactionKind.WITHDRAWAL
            subtype = "gross" if code in {"SG", "S6", "SW", "RC", "RD", "SV"} else "net"
        if kind is None:
            continue
        bucket_date = _next_projected_month(policy.issue_date, actual_date)
        if bucket_date is None or bucket_date > end_date:
            continue
        dated.append(DatedTransaction(
            kind=kind,
            effective_date=bucket_date,
            amount=amount,
            subtype=subtype,
            metadata={"actual_date": str(actual_date), "code": code, "sequence": transaction.sequence_number},
        ))
        audit.append({
            "actual_date": str(actual_date),
            "bucket_date": str(bucket_date),
            "code": code,
            "kind": str(kind.value),
            "subtype": subtype,
            "amount": amount,
            "sequence": transaction.sequence_number,
            "days_to_bucket": (bucket_date - actual_date).days,
        })
    compact_codes = {}
    for code, row in all_codes.items():
        compact_codes[code] = {
            **row,
            "amount": round(row["amount"], 2),
            "descriptions": sorted(row["descriptions"]),
        }
    return dated, audit, compact_codes


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _measure(cyber, rerun):
    if cyber is None or rerun is None:
        return {"cyberlife": cyber, "rerun": rerun, "diff": None, "class": "Not comparable"}
    diff = float(rerun) - float(cyber)
    return {"cyberlife": float(cyber), "rerun": float(rerun), "diff": diff, "class": classify_diff(diff)}


def _later_face_changes(policy) -> tuple[list[Any], list[dict[str, Any]]]:
    from suiteview.illustration.models.input_set import PolicyChangeEvent, PolicyChangeKind

    if policy.issue_date is None:
        return [], []
    issue_segments = [
        seg for seg in policy.segments
        if seg.is_base and not seg.is_cola and seg.issue_date == policy.issue_date
    ]
    current_total = sum(
        seg.original_face_amount if seg.original_face_amount > 0 else seg.face_amount
        for seg in issue_segments
    )
    by_date: dict[date, float] = defaultdict(float)
    for seg in policy.segments:
        if not (seg.is_base and not seg.is_cola and seg.issue_date and seg.issue_date > policy.issue_date):
            continue
        by_date[seg.issue_date] += seg.original_face_amount if seg.original_face_amount > 0 else seg.face_amount
    changes = []
    audit = []
    for when in sorted(by_date):
        current_total += by_date[when]
        changes.append(PolicyChangeEvent(
            kind=PolicyChangeKind.FACE_AMOUNT,
            effective_date=when,
            value=current_total,
            metadata={"source": "current later base coverage segment"},
        ))
        audit.append({"date": str(when), "type": "face_increase", "target_total_face": current_total})
    return changes, audit


def _premium_reconciliation(policy, transaction_audit) -> dict[str, Any]:
    replayed = sum(row["amount"] for row in transaction_audit if row["kind"] == "premium")
    return {
        "cyberlife_premiums_paid_to_date": getattr(policy, "premiums_paid_to_date", None),
        "replayed_premium_total": round(replayed, 2),
        "replay_vs_cyberlife_paid": (
            None if getattr(policy, "premiums_paid_to_date", None) is None
            else round(replayed - float(policy.premiums_paid_to_date or 0.0), 2)
        ),
        "note": (
            "RERUN dated inputs are month-bucketed to the next policy monthliversary; "
            "actual FH_FIXED dates remain in transaction metadata."
        ),
    }


def _features(policy, transaction_audit, code_summary, change_audit) -> dict[str, Any]:
    premium_count = sum(1 for row in transaction_audit if row["kind"] == "premium")
    loan_count = sum(1 for row in transaction_audit if row["kind"] == "loan")
    repayment_count = sum(1 for row in transaction_audit if row["kind"] == "loan_repayment")
    withdrawal_count = sum(1 for row in transaction_audit if row["kind"] == "withdrawal")
    return {
        "premium_transactions": premium_count,
        "loan_transactions": loan_count,
        "loan_repayment_transactions": repayment_count,
        "withdrawal_transactions": withdrawal_count,
        "policy_change_events": len(change_audit),
        "has_riders": bool(getattr(policy, "riders", None)),
        "has_benefits": bool(getattr(policy, "benefits", None)),
        "has_substandard": any(
            float(getattr(seg, "table_rating", 0) or 0) > 0 or float(getattr(seg, "flat_extra", 0) or 0) > 0
            for seg in getattr(policy, "segments", []) or []
        ),
        "current_loan_balance": float(getattr(policy, "total_loan_balance", 0.0) or 0.0),
        "all_transaction_codes": code_summary,
    }


def _first_divergence_evidence(transaction_audit, change_audit) -> dict[str, Any]:
    material_events = [
        *[
            {"date": row["actual_date"], "bucket_date": row["bucket_date"], "kind": row["kind"], "code": row["code"], "amount": row["amount"]}
            for row in transaction_audit
            if row["kind"] != "premium"
        ],
        *change_audit,
    ]
    material_events.sort(key=lambda row: str(row.get("bucket_date") or row.get("date") or ""))
    if material_events:
        return {
            "first_possible_divergence": material_events[0],
            "reason": "First non-premium cashflow or reconstructed policy change in the replay.",
        }
    first_premium = min(transaction_audit, key=lambda row: row["bucket_date"], default=None)
    return {
        "first_possible_divergence": (
            None if first_premium is None else {
                "date": first_premium["actual_date"],
                "bucket_date": first_premium["bucket_date"],
                "kind": first_premium["kind"],
                "code": first_premium["code"],
                "amount": first_premium["amount"],
            }
        ),
        "reason": (
            "No historical CyberLife shadow path exists; for premium-only histories the first "
            "possible measured difference is premium timing/rate/rule treatment from issue."
        ),
    }


def _state_shadow_detail(state) -> dict[str, Any]:
    names = (
        "shadow_bav", "shadow_sa", "shadow_target_prem",
        "shadow_prem_under_target", "shadow_prem_over_target",
        "shadow_target_load", "shadow_excess_load", "shadow_prem_load",
        "shadow_net_prem", "shadow_nar_av", "shadow_db",
        "shadow_coi_rate", "shadow_coi", "shadow_dbd_rate",
        "shadow_nar", "shadow_epu_rate", "shadow_epu",
        "shadow_mfee", "shadow_rider_charges", "shadow_md",
        "shadow_av", "shadow_days", "shadow_int_rate",
        "shadow_eff_rate", "shadow_interest", "shadow_eav",
        "shadow_eav_less_debt",
    )
    return {name: getattr(state, name, None) for name in names}


def _root_cause(record: dict[str, Any]) -> str:
    if record["status"] != "compared":
        return record.get("blocker") or record.get("error") or record["status"]
    diff = record.get("shadow_comparison", {}).get("diff")
    if diff is None:
        return "CyberLife shadow value unavailable."
    if abs(diff) <= 1.0:
        return "Reconciles to the current CyberLife XP shadow value within $1."
    features = record.get("features", {})
    if features.get("loan_transactions") or features.get("loan_repayment_transactions") or features.get("withdrawal_transactions"):
        return (
            "Material mismatch on a policy with loan/withdrawal activity; RERUN can replay "
            "cashflows only in monthliversary buckets, so transaction-day timing and loan bucket "
            "history are input limitations before an engine-rate conclusion."
        )
    if features.get("policy_change_events"):
        return (
            "Material mismatch on a reconstructed face-change history; only current coverage "
            "segments identify increases, while DB-option/decrease details are not archived in "
            "the RERUN input surface."
        )
    if record.get("premium_reconciliation", {}).get("replay_vs_cyberlife_paid") not in (None, 0, 0.0):
        return (
            "Material mismatch with premium-total reconciliation variance; FH_FIXED replayed "
            "premium total does not equal CyberLife premium-to-date."
        )
    return (
        "Material mismatch on a clean premium-only history; evidence points to a shadow rate/rule "
        "or premium timing difference rather than loans, withdrawals, or reconstructed face changes."
    )


def compare_policy(selection_row: dict[str, Any], output_dir: Path, force: bool = False) -> dict[str, Any]:
    from suiteview.illustration.api import load_policy_data, project_policy
    from suiteview.illustration.core.rate_loader import RateLookupError, load_rates
    from suiteview.illustration.core.scenario_builder import build_illustration_scenario
    from suiteview.illustration.models.input_set import IllustrationInputSet, IllustrationOptions, ScheduledTransaction, TransactionKind
    from suiteview.illustration.models.plancode_config import load_plancode
    from suiteview.polview.services.policy_service import get_policy_info

    company = str(selection_row.get("company", "")).strip()
    policy_number = str(selection_row.get("policy_number", "")).strip()
    key = safe_policy_key(company, policy_number)
    result_path = output_dir / "policy_results" / f"{key}.json"
    if result_path.exists() and not force:
        return json_load(result_path)
    started = time.time()
    record: dict[str, Any] = {
        "key": key,
        "company": company,
        "policy_number": policy_number,
        "selection_source": selection_row.get("source", ""),
        "requested_plancode": selection_row.get("requested_plancode", ""),
        "selected_plancode": selection_row.get("plancode", ""),
        "status": "started",
    }
    try:
        pi = get_policy_info(policy_number, REGION, company)
        base_policy = load_policy_data(policy_number, region=REGION, company_code=company)
        config = load_plancode(base_policy.plancode)
        record.update({
            "plancode": base_policy.plancode,
            "product_type": base_policy.product_type,
            "issue_date": str(base_policy.issue_date or ""),
            "valuation_date": str(base_policy.valuation_date or ""),
            "issue_age": base_policy.issue_age,
            "attained_age": base_policy.attained_age,
            "rate_sex": base_policy.rate_sex,
            "rate_class": base_policy.rate_class,
            "db_option_current": base_policy.db_option,
            "face_amount_current": base_policy.face_amount,
            "shadow_plancode": getattr(config, "shadow_plancode", ""),
            "has_shadow_account": bool(base_policy.has_shadow_account),
            "ccv_active": bool(base_policy.ccv_active),
            "ccv_ceased": bool(base_policy.ccv_ceased),
            "cyberlife_shadow": float(base_policy.shadow_account_value or 0.0),
            "cyberlife_av": float(base_policy.account_value or 0.0),
        })
        if not (base_policy.has_shadow_account and getattr(config, "shadow_plancode", "")):
            record["status"] = "not-shadow-active"
            record["blocker"] = (
                "Plancode selection is shadow-capable, but this policy does not have an "
                "active CCV/shadow account in the loaded policy basis."
            )
            json_dump(result_path, record)
            return record
        if base_policy.issue_date is None or base_policy.valuation_date is None:
            record["status"] = "not-comparable"
            record["blocker"] = "Missing issue date or valuation date."
            json_dump(result_path, record)
            return record
        run0 = project_policy(base_policy, config=config, rates=load_rates(base_policy, config), months=0, stop_on_lapse=False)
        state0 = run0.states[0]
        record["month0_current_shadow_deduction"] = {
            "rerun": _state_shadow_detail(state0),
            "cyberlife_record": "No separate CyberLife current-month shadow deduction record was identified; LH_COV_TARGET XP stores current shadow value only.",
        }
        dated, transaction_audit, code_summary = _actual_transactions(pi, base_policy, base_policy.valuation_date)
        face_changes, change_audit = _later_face_changes(base_policy)
        zero_schedule = ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1, amount=0.0, mode="M")
        inputs = IllustrationInputSet(
            scheduled_transactions=[zero_schedule],
            dated_transactions=dated,
            policy_changes=face_changes,
        )
        scenario = build_illustration_scenario(
            copy.deepcopy(base_policy),
            future_inputs=inputs,
            run_from_issue=True,
        )
        issue_policy = scenario.projectable_policy
        months = _months_between(issue_policy.valuation_date, base_policy.valuation_date)
        rates = load_rates(issue_policy, config)
        options = IllustrationOptions(
            conform_to_tefra=False,
            conform_to_tamra=False,
            guideline_forceouts=False,
            no_lapse=True,
        )
        run = project_policy(
            issue_policy,
            config=config,
            rates=rates,
            inputs=inputs,
            months=months,
            stop_on_lapse=False,
            options=options,
        )
        states_by_date = {state.date: state for state in run.states if state.date is not None}
        final_state = states_by_date.get(base_policy.valuation_date) or run.states[-1]
        record.update({
            "status": "compared",
            "months_projected": months,
            "final_state_date": str(final_state.date),
            "transactions_replayed_count": len(transaction_audit),
            "transactions_replayed": transaction_audit,
            "policy_changes_reconstructed": change_audit,
            "features": _features(base_policy, transaction_audit, code_summary, change_audit),
            "premium_reconciliation": _premium_reconciliation(base_policy, transaction_audit),
            "shadow_comparison": _measure(base_policy.shadow_account_value, getattr(final_state, "shadow_eav", None)),
            "av_comparison": _measure(base_policy.account_value, getattr(final_state, "av_after_deduction", None)),
            "av_alignment": {
                "cyberlife": "Current LH_POL_MVRY_VAL CSV/account value is a post-deduction monthliversary value.",
                "rerun_field": "av_after_deduction",
                "rerun_av_end_of_month": getattr(final_state, "av_end_of_month", None),
                "note": "From-issue AV uses current illustrated interest assumptions, not historical declared rates.",
            },
            "final_shadow_detail": _state_shadow_detail(final_state),
            "first_divergence_evidence": _first_divergence_evidence(transaction_audit, change_audit),
            "input_limitations": [
                "DatedTransaction inputs bucket historical transactions to policy monthliversaries; exact transaction-day shadow crediting is not represented.",
                "From-issue mode defaults issue DB option from the current policy because original DB-option history is not reconstructed.",
                "Only later base face increases visible as current coverage segments are reconstructed; historical decreases and some option changes require explicit archived events not presently loaded.",
                "Regular AV replay uses current illustrated interest assumptions from issue, so AV mismatches are expected and are not shadow-rate proof by themselves.",
            ],
        })
        record["root_cause"] = _root_cause(record)
    except RateLookupError as exc:
        record["status"] = "rates-not-loaded"
        record["blocker"] = f"RateLookupError: {exc}"
        record["rate_load_lock_present"] = RATE_LOAD_LOCK.exists()
        record["traceback"] = traceback_text()
    except Exception as exc:  # noqa: BLE001
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["traceback"] = traceback_text()
    record["seconds"] = round(time.time() - started, 1)
    json_dump(result_path, record)
    return record


def _summarize_by_plan(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_plan: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_plan[str(record.get("plancode") or record.get("selected_plancode") or "").strip()].append(record)
    rows = []
    for plan, items in sorted(by_plan.items()):
        comparable = [row for row in items if row.get("status") == "compared"]
        classes = Counter(row.get("shadow_comparison", {}).get("class", row.get("status")) for row in comparable)
        max_diff = None
        material_examples = []
        root_cause_counts = Counter()
        month0_shadow_md = []
        for row in comparable:
            diff = row.get("shadow_comparison", {}).get("diff")
            if row.get("root_cause"):
                root_cause_counts[row["root_cause"]] += 1
            month0_md = (
                row.get("month0_current_shadow_deduction", {})
                .get("rerun", {})
                .get("shadow_md")
            )
            if month0_md is not None:
                month0_shadow_md.append(float(month0_md))
            if diff is not None:
                max_diff = max(abs(diff), max_diff or 0.0)
                if abs(diff) > 1.0 and len(material_examples) < 3:
                    material_examples.append({
                        "policy": row["key"],
                        "diff": diff,
                        "root_cause": row.get("root_cause", ""),
                    })
        rows.append({
            "plancode": plan,
            "policies": len(items),
            "compared": len(comparable),
            "exact": classes.get("Exact", 0),
            "within_1": classes.get("Rounding", 0),
            "material": classes.get("Material", 0),
            "max_abs_diff": max_diff,
            "status_counts": dict(Counter(row.get("status", "") for row in items)),
            "root_cause_counts": dict(root_cause_counts),
            "month0_shadow_md_range": (
                None if not month0_shadow_md
                else {"min": min(month0_shadow_md), "max": max(month0_shadow_md)}
            ),
            "material_examples": material_examples,
        })
    return rows


def _write_markdown(output_dir: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Shadow account from-issue baseline",
        "",
        f"Created: {summary['created_at']}",
        f"Policies: {summary['policy_count']} ({summary['status_counts']})",
        "",
        "## Headline by shadow plancode",
        "",
        "| Plancode | Policies | Compared | Exact | Within $1 | Material | Max abs diff | Statuses |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in summary["by_plancode"]:
        max_diff = "" if row["max_abs_diff"] is None else f"{row['max_abs_diff']:.2f}"
        lines.append(
            f"| {row['plancode']} | {row['policies']} | {row['compared']} | "
            f"{row['exact']} | {row['within_1']} | {row['material']} | {max_diff} | "
            f"{row['status_counts']} |"
        )
    lines.extend([
        "",
        "## Root causes and evidence",
        "",
    ])
    for row in summary["by_plancode"]:
        lines.append(f"### {row['plancode']}")
        if row.get("month0_shadow_md_range") is not None:
            rng = row["month0_shadow_md_range"]
            lines.append(
                f"- Month-0 RERUN shadow MD range: {rng['min']:.2f} to {rng['max']:.2f}; "
                "CyberLife record found for comparison: none (only current XP shadow value)."
            )
        if row.get("root_cause_counts"):
            lines.append("- Root-cause counts:")
            for cause, count in row["root_cause_counts"].items():
                lines.append(f"  - {count}: {cause}")
        if not row["material_examples"]:
            lines.append("- No material compared shadow mismatch, or no comparable policies.")
        for example in row["material_examples"]:
            lines.append(
                f"- {example['policy']}: diff {example['diff']:.2f}. {example['root_cause']}"
            )
        lines.append("")
    lines.extend([
        "## Limitations",
        "",
        "- CyberLife exposes current XP shadow value only; no historical month-by-month shadow ledger was found.",
        "- RERUN from-issue inputs accept month-bucketed dated transactions, not exact transaction-day history.",
        "- Original DB-option history and historical face decreases are not fully archived in the current input basis.",
        "- AV comparisons are diagnostic only because declared/current interest history is not replayed.",
        "",
        "## Files",
        "",
        f"- JSON: `{output_dir / 'shadow_from_issue_results.json'}`",
        f"- Per-policy JSON: `{output_dir / 'policy_results'}`",
    ])
    (output_dir / "shadow_from_issue_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args) -> dict[str, Any]:
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Shadow from-issue baseline must read live CyberLife data, not local fixtures.")
    output_dir = Path(args.output_dir)
    (output_dir / "policy_results").mkdir(parents=True, exist_ok=True)
    selection = json_load(Path(args.selection))
    shadow_codes, shadow_by_code = _shadow_requested_plancodes(Path(args.plancodes))
    selected = _selected_shadow_candidates(selection, shadow_codes, shadow_by_code)
    selected = _fill_to_per_plancode(
        selected,
        shadow_codes,
        shadow_by_code,
        args.per_plancode,
        args.candidate_limit,
    )
    if args.limit:
        selected = selected[: args.limit]
    if args.policy_keys:
        wanted = {key.strip().upper() for key in args.policy_keys.split(",") if key.strip()}
        selected = [
            row for row in selected
            if safe_policy_key(row.get("company", ""), row.get("policy_number", "")).upper() in wanted
            or str(row.get("policy_number", "")).strip().upper() in wanted
        ]
    started = time.time()
    records = []
    for index, row in enumerate(selected, 1):
        result = compare_policy(row, output_dir, args.force)
        records.append(result)
        print(f"{index}/{len(selected)} {result['key']} {result.get('status')}", flush=True)
    if args.rerun_rate_errors and any(row.get("status") == "rates-not-loaded" for row in records):
        if RATE_LOAD_LOCK.exists() and args.rate_lock_wait_seconds > 0:
            deadline = time.time() + args.rate_lock_wait_seconds
            while RATE_LOAD_LOCK.exists() and time.time() < deadline:
                time.sleep(15)
        if not RATE_LOAD_LOCK.exists():
            rerun_records = []
            rate_error_keys = {row["key"] for row in records if row.get("status") == "rates-not-loaded"}
            for row in selected:
                if safe_policy_key(row.get("company", ""), row.get("policy_number", "")) in rate_error_keys:
                    rerun_records.append(compare_policy(row, output_dir, True))
            by_key = {row["key"]: row for row in records}
            by_key.update({row["key"]: row for row in rerun_records})
            records = list(by_key.values())
    for record in records:
        if record.get("status") == "compared" and not record.get("root_cause"):
            record["root_cause"] = _root_cause(record)
    summary = {
        "created_at": datetime.now().isoformat(),
        "selection": str(Path(args.selection)),
        "plancodes": str(Path(args.plancodes)),
        "shadow_requested_plancodes": sorted(shadow_codes),
        "policy_count": len(records),
        "status_counts": dict(Counter(row.get("status", "") for row in records)),
        "by_plancode": _summarize_by_plan(records),
        "rate_load_lock_present": RATE_LOAD_LOCK.exists(),
        "seconds": round(time.time() - started, 1),
        "records": records,
    }
    json_dump(output_dir / "shadow_from_issue_results.json", summary)
    _write_markdown(output_dir, summary)
    print(json.dumps({
        "output": str(output_dir / "shadow_from_issue_results.json"),
        "summary": str(output_dir / "shadow_from_issue_summary.md"),
        "policy_count": len(records),
        "status_counts": summary["status_counts"],
        "seconds": summary["seconds"],
    }, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--plancodes", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--per-plancode", type=int, default=5)
    parser.add_argument("--candidate-limit", type=int, default=25)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--policy-keys", default="", help="Comma-separated company_policy keys or policy numbers to run.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rerun-rate-errors", action="store_true")
    parser.add_argument("--rate-lock-wait-seconds", type=int, default=0)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
