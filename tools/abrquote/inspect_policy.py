"""Read-only ABR input discovery; emits evidence, never a quote with guessed inputs."""
import argparse
from contextlib import redirect_stdout
from dataclasses import asdict
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.abrquote.automation import (
    QuoteError, _json_value, _assessment_port, QuoteRequest, _validate_assessment,
)
from suiteview.abrquote.core.abr_policy_service import find_policy_companies, build_abr_policy
from suiteview.abrquote.automation_data import (
    open_rate_database, reject_lookup_warnings, capture_lookup_warnings,
)
from suiteview.abrquote.models.abr_database import using_quote_database
from suiteview.core.reinsurance import fetch_reinsurer_list


def inspect(policy_number, region, quote_date, assessment_request):
    from suiteview.abrquote.automation import policy_activity
    _validate_assessment(assessment_request["assessment"])
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise QuoteError("Live discovery must not use local-data mode")
    with capture_lookup_warnings("suiteview.polview.models") as discovery_diagnostics:
        companies = find_policy_companies(policy_number, region)
    if len(companies) != 1:
        raise QuoteError(f"Unique canonical company not resolved: {companies}")
    company = companies[0]
    with capture_lookup_warnings("suiteview.polview.models") as policy_diagnostics:
        policy, pi = build_abr_policy(
            policy_number,
            region,
            company_code=company,
            use_cache=False,
            as_of_date=quote_date,
        )
    if not policy or pi is None:
        raise QuoteError("Canonical policy retrieval failed")
    actual_company = str(pi.data_item("LH_BAS_POL", "CK_CMP_CD") or "").strip()
    if actual_company != company:
        raise QuoteError("Canonical company resolution mismatch")
    policy.company = company
    with reject_lookup_warnings("suiteview.core.reinsurance"):
        policy.reinsurers = fetch_reinsurer_list(policy_number, company, quote_date)
    output = {
        "status": "inputs_retrieved_not_quoted",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "policy_number": policy_number, "company_candidates": companies,
        "company_code": company, "region": region,
        "region_selection": f"Explicit region argument {region}; validated by successful canonical lookup",
        "replay_quote_date": quote_date.isoformat(),
        "quote_date_provenance": "Explicit caller-supplied date; source attribution is in input_provenance",
        "input_provenance": assessment_request,
        "policy": asdict(policy),
        "source_values": {
            "status_code": pi.status.status_code, "status_description": pi.status.status_description,
            "is_active": policy_activity(pi)["verified_active"],
            "activity_resolution": policy_activity(pi),
            "legacy_is_active": pi.status.is_active, "is_joint_insured": pi.coverages.is_joint_insured,
            "total_loan_balance": pi.loans.total_loan_balance,
            "total_loan_principal": pi.loans.total_loan_principal,
            "total_loan_interest": pi.loans.total_loan_interest,
            "cash_surrender_value": policy.surrender_value,
            "monthliversary_account_value": pi.values.mv_av(0),
            "value_source": "LH_POL_MVRY_VAL.CSV_AMT via maintained ABR policy service / mv_av",
            "annual_premium": pi.billing.annual_premium, "modal_premium": pi.billing.modal_premium,
            "monthly_deduction": pi.values.mv_monthly_deduction(),
            "valuation_date": pi.values.valuation_date, "mv_date": pi.values.mv_date(0),
            "current_fund_loan_buckets": {
                loan_type: {
                    amount_type: pi.loan_records.calc_fund_loan_total(loan_type, amount_type)
                    for amount_type in ("principal", "accrued")
                }
                for loan_type in ("regular", "preferred", "variable")
            },
            "loan_bucket_source": "PolicyInformation.loan_records.calc_fund_loan_total; "
                                  "uses 9999 current-record sentinel and interest-status rule",
        },
        "loan_fund_source_rows": pi.fetch_table("LH_FND_VAL_LOAN"),
        "base_policy_status_source_fields": [
            {key: value for key, value in row.items()
             if any(token in key for token in ("STA", "STS", "SUS"))}
            for row in pi.fetch_table("LH_BAS_POL")
        ],
        "abr_benefits": [
            asdict(b) for b in pi.benefits.get_benefits() if str(b.benefit_type_cd).strip() == "#"
        ],
        "source_diagnostics": discovery_diagnostics + policy_diagnostics,
        "source_table_errors": {
            table: error
            for table in ("LH_BAS_POL", "LH_COV_PHA", "LH_SPM_BNF",
                          "LH_FND_VAL_LOAN", "LH_POL_MVRY_VAL")
            if (error := pi.table_error(table))
        },
        "limitations": [
            "Live CyberLife values are current retrieval data, not a historical snapshot.",
            "Email supplies no requested amount; minimum remaining face and full/partial scope are not assumed.",
            "Email supplies no level annual premium to maturity, loan payoff or surrender value instructions.",
            "Physician-supplied critical-illness assessment is attributed input, not an agent medical judgment.",
        ],
        "calculation_blockers": ["Explicit UL level annual premium to maturity is not supplied by the email.",
                                 "Quote options/minimum remaining face require sourced values or explicit approval."],
    }
    if not pi.status.is_active:
        output["calculation_blockers"].append(
            f"Canonical active policy status cannot be verified: {pi.status.status_code!r}")
    if output["source_diagnostics"]:
        output["calculation_blockers"].append("Policy retrieval produced source diagnostics; review completeness.")
    db, queries = open_rate_database(policy.product.product_type)
    try:
        output["canonical_rate_observations"] = {
            "interest": db.get_effective_interest_rate(quote_date.strftime("%Y-%m")),
            "admin_fee": db.get_admin_fee(policy.product.issue_state),
            "per_diem": db.get_per_diem(quote_date.year),
            "minimum_face_rule": db.get_min_face(policy.plan_code),
            "minimum_face_rule_source": "ABROdbcDatabase.get_min_face: canonical hardcoded rule; not a requested amount",
        }
        # Medical-only calculation is independent of the missing financial inputs.
        # No acceleration options are read by _assessment_port or invented here.
        medical_request = QuoteRequest(
            policy_number=policy_number, company_code=company, region=region,
            quote_date=quote_date,
            assessment=assessment_request["assessment"],
            options={},
            input_provenance={"medical": "Physician-supplied probabilities in original email"},
        )
        try:
            with using_quote_database(db):
                medical = _assessment_port(policy, medical_request)
            output["medical_assessment_only"] = asdict(medical)
            if getattr(medical, "automation_warnings", []):
                output["medical_assessment_status"] = "boundary"
                output["medical_boundary"] = medical.automation_warnings[0]
        except QuoteError as exc:
            output["medical_assessment_status"] = "blocked"
            output["calculation_blockers"].append(str(exc))
            if hasattr(exc, "details"):
                output["medical_boundary"] = exc.details
        output["rate_queries"] = queries
    finally:
        db.close()
    output["source_sha256"] = {
        str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
        for path in (
            Path(__file__),
            ROOT / "suiteview" / "abrquote" / "automation.py",
            ROOT / "suiteview" / "abrquote" / "core" / "abr_policy_service.py",
            ROOT / "suiteview" / "abrquote" / "ui" / "assessment_panel.py",
            ROOT / "suiteview" / "abrquote" / "core" / "goal_seek.py",
            ROOT / "suiteview" / "abrquote" / "core" / "mortality_engine.py",
        )
    }
    return _json_value(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--quote-date", required=True, type=date.fromisoformat)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--assessment-request", required=True, type=Path)
    args = parser.parse_args()
    try:
        with redirect_stdout(sys.stderr):
            result = inspect(args.policy, args.region, args.quote_date,
                             json.loads(args.assessment_request.read_text(encoding="utf-8-sig")))
        encoded = json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
        print(json.dumps({"status": result["status"], "path": str(args.output.resolve()),
                          "sha256": sha256(args.output.read_bytes()).hexdigest()}))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
