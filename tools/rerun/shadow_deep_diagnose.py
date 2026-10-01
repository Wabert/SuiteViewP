"""Deepen shadow from-issue baseline diagnostics and update artifacts.

Usage:
``venv\\Scripts\\python.exe tools\\rerun\\shadow_deep_diagnose.py
--input <shadow_from_issue_results.json> --output-dir <shadow folder>``

Read-only against CyberLife DB2 and UL_Rates.  Adds definition/source evidence,
CCV start-date evidence, root-cause categories, and sensitivity results for the
cleanest compared policy per plancode.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import shutil
import sys
import time
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rerun.baseline_common import classify_diff, json_dump, json_load, safe_policy_key, traceback_text  # noqa: E402
from tools.rerun.baseline_shadow_from_issue import (  # noqa: E402
    RATE_LOAD_LOCK,
    _actual_transactions,
    _later_face_changes,
    _measure,
    _months_between,
    _premium_reconciliation,
    _state_shadow_detail,
)


QUANTITY_DEFINITION = {
    "suiteview_source": "suiteview.polview.models.policy_sections.targets.TargetsSection.shadow_account_value",
    "db2_source": "LH_COV_TARGET.TAR_PRM_AMT where TAR_TYP_CD = 'XP' (record/segment 58 TP coverage target)",
    "suiteview_policy_data_field": "IllustrationPolicyData.shadow_account_value",
    "polview_label_evidence": "Coverage target type CV is labelled CCV; XP is read explicitly as the current shadow account value.",
    "cyberdoc_evidence": (
        "CyberDoc B10 Products, Policy Protection: universal life supports policy protection values, "
        "also called alternative cash values or shadow accounts, used for grace-period processing; "
        "the benefit can be added only as of the issue date of base coverage; the value is used "
        "only for grace-period processing and only needs to be calculated on a monthly policy day."
    ),
    "comparison_field": "RERUN MonthlyState.shadow_eav (Debug File CCV Value = vShadowEAV)",
    "debt_treatment": "Raw XP target is not adjusted by SuiteView; RERUN also records shadow_eav before debt and shadow_eav_less_debt separately.",
    "timing_uncertainty": (
        "CyberLife stores the current monthly policy-day target, not a separate detailed shadow "
        "BAV/AV/EAV ledger row exposed through PolicyInformation. Month-0 RERUN can compute a "
        "shadow deduction from the XP seed, but no CyberLife field was found for that deduction."
    ),
}


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return str(value)


def _target_rows(pi) -> list[dict[str, Any]]:
    rows = []
    for row in pi.fetch_table("LH_COV_TARGET"):
        code = str(row.get("TAR_TYP_CD", "") or "").strip()
        if code in {"XP", "CV", "SU", "ST", "NS", "NT"}:
            rows.append(_jsonable(row))
    return rows


def _benefit_rows(pi) -> list[dict[str, Any]]:
    out = []
    for ben in pi.benefits.get_benefits():
        out.append({
            "coverage_phase": ben.cov_pha_nbr,
            "benefit_code": ben.benefit_code,
            "benefit_type": ben.benefit_type_cd,
            "benefit_subtype": ben.benefit_subtype_cd,
            "benefit_desc": ben.benefit_desc,
            "issue_date": _jsonable(ben.issue_date),
            "cease_date": _jsonable(ben.cease_date),
            "pay_up_date": _jsonable(ben.pay_up_date),
            "units": _jsonable(ben.units),
            "benefit_amount": _jsonable(ben.benefit_amount),
            "raw": _jsonable(ben.raw_data),
        })
    return out


def _coverage_rows(policy) -> list[dict[str, Any]]:
    rows = []
    for seg in getattr(policy, "segments", []) or []:
        rows.append({
            "coverage_phase": seg.coverage_phase,
            "is_base": seg.is_base,
            "is_cola": seg.is_cola,
            "plancode": getattr(seg, "plancode", ""),
            "issue_date": _jsonable(seg.issue_date),
            "issue_age": seg.issue_age,
            "face_amount": seg.face_amount,
            "original_face_amount": seg.original_face_amount,
            "status": seg.status,
        })
    return rows


def _shadow_start(policy, benefit_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]]) -> dict[str, Any]:
    ccv = [row for row in benefit_rows if str(row.get("benefit_type", "")).strip() == "A"]
    ccv_dates = sorted({row.get("issue_date") for row in ccv if row.get("issue_date")})
    target_dates = sorted({
        row.get("TAR_DT") for row in target_rows
        if str(row.get("TAR_TYP_CD", "")).strip() in {"XP", "CV"} and row.get("TAR_DT")
    })
    chosen = (ccv_dates[0] if ccv_dates else (_jsonable(policy.issue_date) if policy.ccv_active else None))
    if chosen is None and target_dates:
        chosen = target_dates[0]
    reason = (
        "Active CCV benefit type A issue date."
        if ccv_dates else
        "No active benefit type A row found; using policy issue date when ccv_active is true, else XP/CV target date."
    )
    return {
        "shadow_start_date": chosen,
        "ccv_benefit_issue_dates": ccv_dates,
        "xp_cv_target_dates": target_dates,
        "base_issue_date": _jsonable(policy.issue_date),
        "reason": reason,
        "cyberdoc_scope": "CyberDoc B10 says policy protection benefit can be added only as of the issue date of base coverage.",
    }


def _zero_like(series, months: int) -> list:
    length = max(len(series), months + 3, 3)
    return [None] + [0.0] * (length - 1)


def _constant_like(series, value: float, months: int) -> list:
    length = max(len(series), months + 3, 3)
    return [None] + [float(value)] * (length - 1)


def _run_replay(policy_number: str, company: str, variant: str = "baseline") -> dict[str, Any]:
    from suiteview.illustration.api import load_policy_data, project_policy
    from suiteview.illustration.core.rate_loader import load_rates
    from suiteview.illustration.core.scenario_builder import build_illustration_scenario
    from suiteview.illustration.models.input_set import IllustrationInputSet, IllustrationOptions, ScheduledTransaction, TransactionKind
    from suiteview.illustration.models.plancode_config import load_plancode
    from suiteview.polview.services.policy_service import get_policy_info

    pi = get_policy_info(policy_number, "CKPR", company)
    base_policy = load_policy_data(policy_number, region="CKPR", company_code=company)
    config = load_plancode(base_policy.plancode)
    dated, transaction_audit, _code_summary = _actual_transactions(pi, base_policy, base_policy.valuation_date)
    face_changes, _change_audit = _later_face_changes(base_policy)
    inputs = IllustrationInputSet(
        scheduled_transactions=[ScheduledTransaction(kind=TransactionKind.PREMIUM, policy_year=1, amount=0.0, mode="M")],
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
    run_config = config
    options = IllustrationOptions(
        conform_to_tefra=False,
        conform_to_tamra=False,
        guideline_forceouts=False,
        no_lapse=True,
    )
    if variant == "exact_days":
        options.exact_days_interest = True
    elif variant == "monthly_days":
        options.exact_days_interest = False
    elif variant == "no_shadow_load":
        rates = copy.deepcopy(rates)
        rates.shadow_tpp = _zero_like(rates.shadow_tpp, months)
        rates.shadow_epp = _zero_like(rates.shadow_epp, months)
    elif variant == "no_shadow_coi":
        rates = copy.deepcopy(rates)
        rates.shadow_coi = _zero_like(rates.shadow_coi, months)
    elif variant == "zero_shadow_interest":
        rates = copy.deepcopy(rates)
        rates.shadow_int = _zero_like(rates.shadow_int, months)
        try:
            run_config = replace(config, shadow_int_rate_code=0.0)
        except TypeError:
            pass
    elif variant == "zero_db_discount":
        rates = copy.deepcopy(rates)
        rates.shadow_dbd = _zero_like(rates.shadow_dbd, months)
        try:
            run_config = replace(config, shadow_dbd_rate=0.0)
        except TypeError:
            pass
    elif variant == "no_shadow_epu_mfee":
        rates = copy.deepcopy(rates)
        rates.shadow_epu = _zero_like(rates.shadow_epu, months)
        try:
            run_config = replace(config, shadow_mfee=0.0, shadow_epu_code=0.0)
        except TypeError:
            pass
    elif variant == "half_shadow_coi":
        rates = copy.deepcopy(rates)
        rates.shadow_coi = [None] + [
            (float(value) * 0.5 if value is not None else 0.0)
            for value in (rates.shadow_coi[1:] if rates.shadow_coi else [0.0] * (months + 2))
        ]
    run = project_policy(
        issue_policy,
        config=run_config,
        rates=rates,
        inputs=inputs,
        months=months,
        stop_on_lapse=False,
        options=options,
    )
    states_by_date = {state.date: state for state in run.states if state.date is not None}
    final_state = states_by_date.get(base_policy.valuation_date) or run.states[-1]
    return {
        "variant": variant,
        "state_date": _jsonable(final_state.date),
        "shadow_eav": getattr(final_state, "shadow_eav", None),
        "shadow_av": getattr(final_state, "shadow_av", None),
        "shadow_md": getattr(final_state, "shadow_md", None),
        "shadow_coi": getattr(final_state, "shadow_coi", None),
        "shadow_prem_load": getattr(final_state, "shadow_prem_load", None),
        "shadow_interest": getattr(final_state, "shadow_interest", None),
        "shadow_int_rate": getattr(final_state, "shadow_int_rate", None),
        "av_after_deduction": getattr(final_state, "av_after_deduction", None),
        "cyberlife_shadow": base_policy.shadow_account_value,
        "diff": (
            None if base_policy.shadow_account_value is None
            else getattr(final_state, "shadow_eav", 0.0) - float(base_policy.shadow_account_value or 0.0)
        ),
        "class": classify_diff(
            getattr(final_state, "shadow_eav", 0.0) - float(base_policy.shadow_account_value or 0.0)
        ),
        "transaction_count": len(transaction_audit),
    }


def _receipt_timing_estimate(record: dict[str, Any]) -> dict[str, Any]:
    transactions = record.get("transactions_replayed", [])
    final_rate = float(record.get("final_shadow_detail", {}).get("shadow_int_rate") or 0.0)
    final_date = record.get("final_state_date") or record.get("valuation_date")
    from datetime import date

    try:
        val_date = date.fromisoformat(str(final_date)[:10])
    except Exception:
        val_date = None
    immediate = 0.0
    compounded = 0.0
    for row in transactions:
        if row.get("kind") != "premium":
            continue
        amount = float(row.get("amount") or 0.0)
        days = max(int(row.get("days_to_bucket") or 0), 0)
        extra = amount * ((1.0 + final_rate) ** (days / 365.0) - 1.0)
        immediate += extra
        if val_date is not None:
            try:
                bucket = date.fromisoformat(str(row.get("bucket_date"))[:10])
                remaining = max((val_date - bucket).days, 0)
                extra *= (1.0 + final_rate) ** (remaining / 365.0)
            except Exception:
                pass
        compounded += extra
    return {
        "method": "Approximate gross-premium interest from receipt date to bucket, accumulated to valuation at final shadow_int_rate.",
        "shadow_int_rate_used": final_rate,
        "immediate_receipt_to_bucket_interest": round(immediate, 2),
        "accumulated_to_valuation": round(compounded, 2),
    }


def _choose_clean_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_plan: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("status") == "compared":
            by_plan[record.get("plancode", "")].append(record)
    chosen = []
    for _plan, items in by_plan.items():
        def key(row):
            features = row.get("features", {})
            complex_count = (
                int(features.get("loan_transactions", 0))
                + int(features.get("loan_repayment_transactions", 0))
                + int(features.get("withdrawal_transactions", 0))
                + int(features.get("policy_change_events", 0))
                + int(bool(row.get("premium_reconciliation", {}).get("replay_vs_cyberlife_paid")))
            )
            diff = abs(row.get("shadow_comparison", {}).get("diff") or 0.0)
            return (complex_count, diff)
        chosen.append(sorted(items, key=key)[0])
    return chosen


def _sensitivity_for_record(record: dict[str, Any]) -> dict[str, Any]:
    variants = [
        "baseline", "monthly_days", "exact_days", "no_shadow_load",
        "no_shadow_coi", "half_shadow_coi", "zero_shadow_interest",
        "zero_db_discount", "no_shadow_epu_mfee",
    ]
    out = {
        "policy": record["key"],
        "plancode": record.get("plancode"),
        "baseline_diff": record.get("shadow_comparison", {}).get("diff"),
        "receipt_timing_estimate": _receipt_timing_estimate(record),
        "variants": [],
    }
    try:
        company, policy = record["key"].split("_", 1)
        for variant in variants:
            out["variants"].append(_run_replay(policy, company, variant))
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["traceback"] = traceback_text()
    return out


def _best_sensitivity_category(record: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    baseline_diff = abs(record.get("shadow_comparison", {}).get("diff") or 0.0)
    evidence = {}
    sens = record.get("sensitivity") or {}
    variants = sens.get("variants") or []
    if not variants or baseline_diff <= 1.0:
        return "engine rule", record.get("root_cause", ""), evidence
    best = min(
        (row for row in variants if row.get("diff") is not None),
        key=lambda row: abs(row["diff"]),
        default=None,
    )
    if best is not None:
        evidence["best_sensitivity"] = best
        improvement = baseline_diff - abs(best["diff"])
        evidence["best_sensitivity_improvement"] = improvement
        if improvement > max(1.0, baseline_diff * 0.5):
            variant = best["variant"]
            if variant in {"no_shadow_load"}:
                return "rate", "Shadow premium-load treatment/rate is the largest closing sensitivity.", evidence
            if variant in {"no_shadow_coi", "half_shadow_coi", "zero_db_discount"}:
                return "engine rule", "Shadow COI/NAR/DB-discount treatment is the largest closing sensitivity.", evidence
            if variant in {"zero_shadow_interest", "exact_days", "monthly_days"}:
                return "input-timing", "Shadow interest/day-count treatment is the largest closing sensitivity.", evidence
            if variant == "no_shadow_epu_mfee":
                return "rate", "Shadow EPU/MFEE treatment is the largest closing sensitivity.", evidence
    timing = sens.get("receipt_timing_estimate", {}).get("accumulated_to_valuation")
    if timing is not None and baseline_diff and abs(abs(timing) - baseline_diff) <= max(5.0, baseline_diff * 0.25):
        evidence["receipt_timing_estimate"] = sens.get("receipt_timing_estimate")
        return "input-timing", "Receipt-date premium crediting estimate is the same order as the mismatch.", evidence
    features = record.get("features", {})
    if features.get("loan_transactions") or features.get("loan_repayment_transactions") or features.get("withdrawal_transactions"):
        return "input-timing", record.get("root_cause", ""), evidence
    if features.get("policy_change_events"):
        return "start-date", record.get("root_cause", ""), evidence
    if record.get("premium_reconciliation", {}).get("replay_vs_cyberlife_paid") not in (None, 0, 0.0):
        return "data", record.get("root_cause", ""), evidence
    return "engine rule", record.get("root_cause", ""), evidence


def _augment_record(record: dict[str, Any]) -> dict[str, Any]:
    from suiteview.illustration.api import load_policy_data
    from suiteview.polview.services.policy_service import get_policy_info

    record["quantity_definition"] = QUANTITY_DEFINITION
    if record.get("status") == "rates-not-loaded":
        record["root_cause_category"] = "data"
        record["root_cause"] = record.get("blocker", "Required shadow rates not loaded.")
        record["evidence"] = {"rate_load_lock_present": RATE_LOAD_LOCK.exists(), "blocker": record.get("blocker")}
        return record
    if record.get("status") == "not-shadow-active":
        record["root_cause_category"] = "definition"
        record["root_cause"] = "No active policy-level CCV/shadow account value exists to compare on this policy."
        record["evidence"] = {"blocker": record.get("blocker")}
    try:
        company = record.get("company") or record.get("key", "_").split("_", 1)[0]
        policy_number = record.get("policy_number") or record.get("key", "_").split("_", 1)[1]
        pi = get_policy_info(policy_number, "CKPR", company)
        policy = load_policy_data(policy_number, region="CKPR", company_code=company)
        targets = _target_rows(pi)
        benefits = _benefit_rows(pi)
        record["target_rows_evidence"] = targets
        record["ccv_benefit_rows"] = [row for row in benefits if str(row.get("benefit_type", "")).strip() == "A"]
        record["all_benefit_rows_summary"] = [
            {k: row.get(k) for k in ("coverage_phase", "benefit_code", "benefit_desc", "issue_date", "cease_date", "units", "benefit_amount")}
            for row in benefits
        ]
        record["coverage_rows_summary"] = _coverage_rows(policy)
        start = _shadow_start(policy, benefits, targets)
        record["shadow_start_date"] = start["shadow_start_date"]
        record["shadow_start_evidence"] = start
        if record.get("status") == "compared":
            category, cause, extra_evidence = _best_sensitivity_category(record)
            record["root_cause_category"] = category
            record["root_cause"] = cause or record.get("root_cause", "")
            record["evidence"] = {
                "target_rows": targets,
                "shadow_start": start,
                "premium_reconciliation": record.get("premium_reconciliation"),
                "first_divergence": record.get("first_divergence_evidence"),
                **extra_evidence,
            }
    except Exception as exc:  # noqa: BLE001
        record.setdefault("evidence", {})["augmentation_error"] = f"{type(exc).__name__}: {exc}"
        record.setdefault("evidence", {})["augmentation_traceback"] = traceback_text()
    return record


def _summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_plan: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_plan[str(record.get("plancode") or record.get("selected_plancode") or "").strip()].append(record)
    rows = []
    for plan, items in sorted(by_plan.items()):
        compared = [row for row in items if row.get("status") == "compared"]
        classes = Counter(row.get("shadow_comparison", {}).get("class", row.get("status")) for row in compared)
        categories = Counter(row.get("root_cause_category", "") for row in items)
        causes = Counter(row.get("root_cause", "") for row in compared)
        max_diff = None
        for row in compared:
            diff = row.get("shadow_comparison", {}).get("diff")
            if diff is not None:
                max_diff = max(max_diff or 0.0, abs(diff))
        rows.append({
            "plancode": plan,
            "policies": len(items),
            "compared": len(compared),
            "exact": classes.get("Exact", 0),
            "within_1": classes.get("Rounding", 0),
            "material": classes.get("Material", 0),
            "max_abs_diff": max_diff,
            "status_counts": dict(Counter(row.get("status", "") for row in items)),
            "root_cause_categories": dict(categories),
            "top_root_causes": causes.most_common(3),
            "sample_evidence": [
                {
                    "policy": row.get("key"),
                    "diff": row.get("shadow_comparison", {}).get("diff"),
                    "category": row.get("root_cause_category"),
                    "root_cause": row.get("root_cause"),
                    "shadow_start_date": row.get("shadow_start_date"),
                    "target_rows": row.get("target_rows_evidence", [])[:2],
                    "best_sensitivity": row.get("evidence", {}).get("best_sensitivity"),
                    "receipt_timing_estimate": row.get("sensitivity", {}).get("receipt_timing_estimate"),
                }
                for row in compared[:3]
            ],
        })
    return rows


def _write_summary(output_dir: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Shadow account from-issue deep diagnosis",
        "",
        f"Updated: {payload['updated_at']}",
        "",
        "## Definition check",
        "",
        f"- Source read by SuiteView: `{QUANTITY_DEFINITION['suiteview_source']}`.",
        f"- DB2 source: `{QUANTITY_DEFINITION['db2_source']}`.",
        f"- CyberDoc: {QUANTITY_DEFINITION['cyberdoc_evidence']}",
        f"- Comparison field: {QUANTITY_DEFINITION['comparison_field']}.",
        f"- Timing caveat: {QUANTITY_DEFINITION['timing_uncertainty']}",
        "",
        "## Per-plancode root cause table",
        "",
        "| Plancode | Compared | Exact | <=$1 | Material | Max abs diff | Categories | Root-cause evidence |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in payload["by_plancode_deep"]:
        max_diff = "" if row["max_abs_diff"] is None else f"{row['max_abs_diff']:.2f}"
        causes = "; ".join(f"{count}x {cause}" for cause, count in row["top_root_causes"]) or str(row["status_counts"])
        lines.append(
            f"| {row['plancode']} | {row['compared']} | {row['exact']} | {row['within_1']} | "
            f"{row['material']} | {max_diff} | {row['root_cause_categories']} | {causes} |"
        )
    lines.extend(["", "## Sensitivity samples", ""])
    for sens in payload.get("sensitivities", []):
        lines.append(f"### {sens.get('plancode')} / {sens.get('policy')}")
        if sens.get("error"):
            lines.append(f"- Sensitivity blocked: {sens['error']}")
            continue
        receipt = sens.get("receipt_timing_estimate", {})
        lines.append(f"- Receipt-date timing estimate accumulated to valuation: {receipt.get('accumulated_to_valuation')}")
        baseline = next((row for row in sens.get("variants", []) if row.get("variant") == "baseline"), None)
        if baseline:
            lines.append(f"- Baseline shadow diff: {baseline.get('diff')}")
        for variant in sens.get("variants", []):
            if variant.get("variant") == "baseline":
                continue
            lines.append(
                f"- {variant.get('variant')}: shadow={variant.get('shadow_eav')} diff={variant.get('diff')} "
                f"load={variant.get('shadow_prem_load')} coi={variant.get('shadow_coi')} interest={variant.get('shadow_interest')}"
            )
        lines.append("")
    lines.extend([
        "## Legacy RERUN workbook reference",
        "",
        payload.get("legacy_reference", "Not attempted."),
        "",
        "## Files",
        "",
        f"- Updated JSON: `{output_dir / 'shadow_from_issue_results.json'}`",
        f"- Deep summary: `{output_dir / 'shadow_from_issue_deep_summary.md'}`",
        f"- CyberDoc search evidence: `{output_dir / 'cyberdoc_policy_protection_search.json'}`",
    ])
    (output_dir / "shadow_from_issue_deep_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _legacy_reference(output_dir: Path) -> str:
    workbook = Path(r"C:\Users\ab7y02\Dev\SuiteViewP_archived_docs\docs\Illustration_UL\RERUN (v20.0).xlsm")
    if not workbook.exists():
        return f"Legacy workbook not found at `{workbook}`."
    return (
        "Legacy Excel reference was not run against live shadow policies. The available tools are read-only for "
        "existing Saved Cases, but building a new case (`rerun_build_case_inputs.py`) forces `SUITEVIEW_LOCAL_DATA=1` "
        "and writes a Saved Cases column, so it cannot faithfully load the live CKPR policy basis used here. "
        f"Workbook availability verified at `{workbook}`; `rerun_debug_map.py` maps Debug File column Y `CCV Value` "
        "to SuiteView `shadow_eav`."
    )


def run(args) -> dict[str, Any]:
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Deep shadow diagnosis must read live CyberLife data, not local fixtures.")
    output_dir = Path(args.output_dir)
    payload = json_load(Path(args.input))
    records = payload.get("records", [])
    sensitivities = payload.get("sensitivities") or []
    sensitivity_by_key = {row.get("policy"): row for row in sensitivities}
    chosen = _choose_clean_records(records)
    for record in chosen:
        if record.get("key") in sensitivity_by_key:
            record["sensitivity"] = sensitivity_by_key[record["key"]]
            continue
        if args.sensitivity_limit and len(sensitivities) >= args.sensitivity_limit:
            break
        sens = _sensitivity_for_record(record)
        sensitivities.append(sens)
        record["sensitivity"] = sens
        print(f"sensitivity {record.get('key')} {record.get('plancode')}", flush=True)
    augmented = []
    for index, record in enumerate(records, 1):
        augmented.append(_augment_record(record))
        print(f"augment {index}/{len(records)} {record.get('key')} {record.get('status')}", flush=True)
    payload["records"] = augmented
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload["quantity_definition"] = QUANTITY_DEFINITION
    payload["sensitivities"] = sensitivities
    payload["by_plancode_deep"] = _summarize(augmented)
    payload["legacy_reference"] = _legacy_reference(output_dir)
    json_dump(output_dir / "shadow_from_issue_results.json", payload)
    _write_summary(output_dir, payload)
    print(json.dumps({
        "json": str(output_dir / "shadow_from_issue_results.json"),
        "summary": str(output_dir / "shadow_from_issue_deep_summary.md"),
        "records": len(augmented),
        "sensitivities": len(sensitivities),
    }, indent=2))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sensitivity-limit", type=int, default=0)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
