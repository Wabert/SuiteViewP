"""Select varied live UL/IUL policies for RERUN/CyberLife baseline testing.

Usage:
``venv\\Scripts\\python.exe tools\\rerun\\baseline_select_policies.py
--plancodes <baseline_plancodes.tsv> --output-dir <baseline_folder>
[--per-plancode 6] [--candidate-limit 80] [--pilot]``

The tool performs read-only DB2 candidate sampling, then loads candidate policies
through ``PolicyInformation`` to tag riders, benefits, substandards, DB options,
loans, shadow-account applicability, company, class, sex, and rollback history.
It writes ``selected_policies.json`` (or ``pilot_selected_policies.json``) and a
progress log. No production code or data is modified.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rerun.baseline_common import (  # noqa: E402
    REGION,
    SYSTEM_CODE,
    json_dump,
    parse_date,
    resolve_requested_plancodes,
    safe_policy_key,
    traceback_text,
)


ACTIVE_PREMIUM_STATUSES = {"21", "22", "31", "32", "41", "42", "43", "44", "45"}


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

    schema = _schema()
    cur = conn.cursor()
    try:
        parameters = (SYSTEM_CODE, plancode)
        cur.setinputsizes([(SQL_VARCHAR, len(value), 0) for value in parameters])
        cur.execute(_candidate_sql(schema, limit), parameters)
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
            })
        return rows
    finally:
        cur.close()


def _tag_policy(candidate: dict[str, Any], requested: str, product_name: str, shadow_requested: str) -> dict[str, Any]:
    from suiteview.illustration.api import load_policy_data
    from suiteview.illustration.core.value_rollback import available_rollback_dates
    from suiteview.polview.services.policy_service import get_policy_info

    policy_number = candidate["policy_number"]
    company = candidate["company"]
    pi = get_policy_info(policy_number, REGION, company)
    data = load_policy_data(policy_number, region=REGION, company_code=company)
    rollback_dates = available_rollback_dates(data)
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
    rider_codes = sorted({str(getattr(rider, "plancode", "") or "").strip() for rider in riders if getattr(rider, "plancode", "")})
    benefit_codes = sorted({str(getattr(benefit, "benefit_code", "") or "").strip() for benefit in benefits if getattr(benefit, "benefit_code", "")})
    db_option = str(getattr(data, "db_option", "") or candidate.get("db_option", "")).strip().upper()
    has_shadow = bool(getattr(data, "ccv_active", False) or getattr(data, "shadow_account_value", 0) or getattr(data, "swam", 0) or shadow_requested)
    loan_balance = float(getattr(data, "regular_loan_principal", 0) or 0) + float(getattr(data, "preferred_loan_principal", 0) or 0) + float(getattr(data, "variable_loan_principal", 0) or 0)
    active_status = str(pi.status.premium_pay_status_code or "").strip()
    feature_tags = []
    if rider_codes:
        feature_tags.append("riders")
    if benefit_codes:
        feature_tags.append("benefits")
    if substandard:
        feature_tags.append("substandard")
    if loan_balance > 0.005:
        feature_tags.append("loan")
    if has_shadow:
        feature_tags.append("shadow")
    if len([cov for cov in coverages if getattr(cov, "coverage_type", "") == "base"]) > 1 or len(coverages) > 1:
        feature_tags.append("multi-segment")
    if db_option in {"B", "2"}:
        feature_tags.append("db-option-b")
    elif db_option and db_option not in {"A", "1"}:
        feature_tags.append("db-option-other")
    else:
        feature_tags.append("db-option-a")
    if active_status != "22":
        feature_tags.append("non-premium-paying")
    return {
        **candidate,
        "requested_plancode": requested,
        "product_name": product_name,
        "exists": bool(pi.exists),
        "premium_status": active_status,
        "db_option": db_option,
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
        "rollback_dates": [str(when) for when in rollback_dates],
        "rollback_count": len(rollback_dates),
        "rider_codes": rider_codes,
        "benefit_codes": benefit_codes,
        "substandard_tags": substandard,
        "loan_balance": loan_balance,
        "loan_types": sorted({str(getattr(loan, "loan_type", "") or "").strip() for loan in loans}),
        "shadow_requested": shadow_requested,
        "shadow_applicable": has_shadow,
        "feature_tags": sorted(set(feature_tags)),
        "feature_score": len(set(feature_tags)) + min(len(rider_codes), 3) + min(len(benefit_codes), 3) + min(len(rollback_dates), 2),
    }


def _select_varied(tagged: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    if len(tagged) <= target:
        return tagged
    selected: list[dict[str, Any]] = []
    remaining = sorted(tagged, key=lambda row: (-row.get("feature_score", 0), row["policy_number"]))

    def take(predicate):
        for row in list(remaining):
            if predicate(row):
                selected.append(row)
                remaining.remove(row)
                return

    for predicate in (
        lambda row: row.get("premium_status") == "22",
        lambda row: row.get("premium_status") != "22",
        lambda row: "loan" in row.get("feature_tags", []),
        lambda row: "substandard" in row.get("feature_tags", []),
        lambda row: "riders" in row.get("feature_tags", []),
        lambda row: "benefits" in row.get("feature_tags", []),
        lambda row: "db-option-b" in row.get("feature_tags", []),
        lambda row: "shadow" in row.get("feature_tags", []),
    ):
        if len(selected) < target:
            take(predicate)
    seen = {safe_policy_key(row["company"], row["policy_number"]) for row in selected}
    for row in remaining:
        if len(selected) >= target:
            break
        key = safe_policy_key(row["company"], row["policy_number"])
        if key not in seen:
            selected.append(row)
            seen.add(key)
    return selected[:target]


def run_selection(args) -> dict[str, Any]:
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Baseline selection must read live CyberLife data, not local fixtures.")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "baseline_progress.log"
    suffix = "pilot_" if args.pilot else ""
    resolved = resolve_requested_plancodes(Path(args.plancodes))
    if args.pilot:
        resolved = resolved[: args.pilot_plancodes]
    per_plancode = args.pilot_per_plancode if args.pilot else args.per_plancode
    candidate_limit = args.pilot_candidate_limit if args.pilot else args.candidate_limit
    db, conn = _connect()
    started = time.time()
    selected: list[dict[str, Any]] = []
    not_tested: list[dict[str, Any]] = []
    by_requested = {}
    try:
        for item in resolved:
            print(f"Selecting {item.requested} ({item.product_name})", flush=True)
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"{datetime.now().isoformat()} selecting {item.requested}\n")
            candidates: list[dict[str, Any]] = []
            for cyberlife_code in item.cyberlife_plancodes:
                if not re.fullmatch(r"[A-Z0-9]{1,8}", cyberlife_code):
                    continue
                candidates.extend(_fetch_candidates(conn, cyberlife_code, candidate_limit))
            if not candidates:
                row = {
                    "requested_plancode": item.requested,
                    "product_name": item.product_name,
                    "reason": "No in-force/non-terminated CyberLife policies found for resolved plancode(s).",
                    "resolved_cyberlife_plancodes": list(item.cyberlife_plancodes),
                    "resolution_note": item.resolution_note,
                }
                not_tested.append(row)
                by_requested[item.requested] = {"selected": [], "not_tested": row}
                continue
            tagged = []
            for candidate in candidates:
                try:
                    tagged.append(_tag_policy(candidate, item.requested, item.product_name, item.shadow_plancode))
                except Exception as exc:  # noqa: BLE001
                    not_tested.append({
                        "requested_plancode": item.requested,
                        "plancode": candidate.get("plancode", ""),
                        "company": candidate.get("company", ""),
                        "policy_number": candidate.get("policy_number", ""),
                        "reason": f"Candidate tag load failed: {type(exc).__name__}: {exc}",
                        "traceback": traceback_text(),
                    })
            chosen = _select_varied(tagged, per_plancode)
            selected.extend(chosen)
            by_requested[item.requested] = {
                "selected": chosen,
                "candidate_count": len(candidates),
                "tagged_count": len(tagged),
                "resolved_cyberlife_plancodes": list(item.cyberlife_plancodes),
                "resolution_note": item.resolution_note,
            }
    finally:
        db.close()
    result = {
        "created_at": datetime.now().isoformat(),
        "region": REGION,
        "pilot": bool(args.pilot),
        "per_plancode": per_plancode,
        "candidate_limit": candidate_limit,
        "selected_count": len(selected),
        "selected": selected,
        "by_requested": by_requested,
        "not_tested": not_tested,
        "seconds": round(time.time() - started, 1),
    }
    out_path = output_dir / f"{suffix}selected_policies.json"
    json_dump(out_path, result)
    print(json.dumps({"output": str(out_path), "selected_count": len(selected), "not_tested": len(not_tested)}, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plancodes", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--per-plancode", type=int, default=5)
    parser.add_argument("--candidate-limit", type=int, default=60)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--pilot-plancodes", type=int, default=10)
    parser.add_argument("--pilot-per-plancode", type=int, default=2)
    parser.add_argument("--pilot-candidate-limit", type=int, default=20)
    args = parser.parse_args()
    run_selection(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
