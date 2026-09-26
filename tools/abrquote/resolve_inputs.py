"""Resolve ABR financial inputs with canonical services, then attempt the dedicated quote.

This subprocess-oriented helper writes immutable request/output/evidence JSON
outside SuiteView. Illustration's ABR solver is used ONLY for funding premium,
never as a substitute for the dedicated ABR payout/clipboard calculation.
"""
def _load_policy_data(*args, **kwargs):
    from suiteview.illustration.api import load_policy_data

    return load_policy_data(*args, **kwargs)
import argparse
from contextlib import redirect_stdout
from dataclasses import asdict
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.abrquote.automation import QuoteError, _json_value, quote_abr
from suiteview.abrquote.models.abr_data import default_minimum_face
from tools.abrquote.inspect_policy import inspect


def resolve_inputs(source):
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise QuoteError("Live resolver cannot use local-data mode")
    allowed = {"policy_number", "quote_date", "survival_5yr", "survival_10yr",
               "rider", "region", "input_provenance"}
    required = allowed - {"region", "input_provenance"}
    if not isinstance(source, dict) or required - source.keys() or source.keys() - allowed:
        raise QuoteError("Resolver requires policy_number, quote_date, survival_5yr, survival_10yr, rider")
    rider = {"CT": "Critical", "Critical": "Critical"}.get(source["rider"])
    if not rider:
        raise QuoteError("This dual-survival resolver requires Critical/CT rider")
    region = source.get("region", "CKPR")
    quote_date = date.fromisoformat(source["quote_date"])
    medical_input = {
        "assessment": {"rider_type": rider, "five_year_survival": source["survival_5yr"],
                       "ten_year_survival": source["survival_10yr"]},
        "input_provenance": source.get("input_provenance", {}),
    }
    evidence = inspect(source["policy_number"], region, quote_date, medical_input)
    policy = evidence["policy"]
    request = {
        "policy_number": source["policy_number"], "company_code": evidence["company_code"],
        "region": region, "quote_date": source["quote_date"],
        "assessment": medical_input["assessment"],
        "options": {},
        "input_provenance": {
            "original_source": source.get("input_provenance", {}),
            "region": "Dedicated ABR application production region" if "region" not in source else "Explicit input",
            "historical_snapshot": False,
        },
    }
    resolved = {}
    blockers = []
    funding = None
    if policy["product_type"] not in {"UL", "IUL", "ISWL"}:
        blockers.append("Resolver supports the UL family only; TERM uses its rate schedule.")
    else:
        minimum = default_minimum_face(policy["product_type"])
        request["options"]["min_face_amount"] = minimum
        request["options"]["surrender_value"] = policy["surrender_value"]
        resolved["min_face_amount"] = {
            "value": minimum,
            "source": "ABR AssessmentPanel.set_policy -> models.abr_data.default_minimum_face",
            "basis": "Unchanged maintained application minimum-remaining-face rule; not a requested acceleration amount.",
        }
        resolved["surrender_value"] = {
            "value": policy["surrender_value"],
            "source": "build_abr_policy -> LH_POL_MVRY_VAL.CSV_AMT (generic accessor only if absent)",
            "basis": "Same loaded surrender value used by dedicated ABR when not overridden.",
        }
        try:
            from suiteview.illustration.core.abr_quote import run_abr_quote
            from suiteview.core.rates import Rates
            illustration_policy = _load_policy_data(
                source["policy_number"], region, evidence["company_code"],
                illustration_date=quote_date,
            )
            interest = evidence["canonical_rate_observations"]["interest"]
            if not interest:
                raise QuoteError("ABR interest rate could not be resolved")
            illustration_policy.current_interest_rate = float(interest[1])
            source_illustration = _json_value(asdict(illustration_policy))
            run = run_abr_quote(illustration_policy, minimum_face_amount=minimum)
            if not run.results:
                raise QuoteError("Canonical funding projection has no inforce net-surrender row")
            inforce = run.results[0]
            request["options"]["surrender_value"] = inforce.surrender_value
            resolved["surrender_value"] = {
                "value": inforce.surrender_value,
                "source": "Illustration ABR funding projection inforce row.surrender_value",
                "gross_loaded_value": policy["surrender_value"],
                "surrender_charge": inforce.surrender_charge,
                "current_loan_retired": run.loan_retired,
                "basis": "Canonical inforce net surrender, after surrender charge and current debt "
                         "retirement, before forecast interest. Not gross CSV_AMT or ending_sv.",
            }
            request["options"]["level_annual_premium"] = run.premium
            request["options"]["loan_payoff"] = run.loan_retired
            if run.max_partial is not None:
                request["options"]["after_partial_deduction"] = run.max_partial.monthly_deduction
            funding = {
                "status": "funding_input_calculated_not_final_abr_quote",
                "premium": run.premium, "regular_premium": run.regular_premium,
                "shadow_premium": run.shadow_premium, "premium_basis": run.premium_basis,
                "first_payment_date": run.first_payment_date,
                "achieved_sv": run.achieved_sv, "achieved_shadow": run.achieved_shadow,
                "illustrated_rate": run.illustrated_rate, "loan_retired": run.loan_retired,
                "db_option_switched": run.db_option_switched,
                "max_partial": asdict(run.max_partial) if run.max_partial else None,
                "source_illustration_policy": source_illustration,
                "projection": [asdict(row) for row in run.results],
                "rate_cache": Rates._cache,
                "basis": "Existing illustration.core.abr_quote.run_abr_quote: annual payments "
                         "from next anniversary, ABR interest, loans retired, Option B to A, "
                         "TEFRA/TAMRA/no-lapse settings and $1000 maturity SV/shadow rule.",
                "historical_snapshot": False,
            }
            resolved["level_annual_premium"] = {
                "value": run.premium,
                "source": "illustration.core.abr_quote.run_abr_quote",
                "basis": funding["basis"],
            }
            resolved["loan_payoff"] = {
                "value": run.loan_retired,
                "source": "IllustrationPolicyData.total_loan_balance, mapped from current LoanRecords buckets",
                "basis": "Current canonical debt retired by ABR funding solve; not a historical-date payoff certificate.",
            }
        except Exception as exc:
            blockers.append(f"Canonical ABR funding-input derivation failed: {type(exc).__name__}: {exc}")
    request["input_provenance"]["resolved_financial_inputs"] = resolved
    request["input_provenance"]["loaded_valuation_date"] = policy["valuation_date"]
    request["input_provenance"]["date_limitation"] = (
        "Quote date is a replay assumption. Policy/loan values are current retrieval values; "
        "no historical snapshot or as-of payoff certification is claimed.")
    if not evidence["source_values"]["is_active"]:
        blockers.append("Canonical PolicyInformation active status could not be verified.")
    if evidence.get("medical_assessment_status") == "blocked":
        medical_blockers = [message for message in evidence["calculation_blockers"]
                           if "goal seek" in message or "did not fit" in message
                           or "Nonnegative mortality boundary" in message]
        blockers.extend(medical_blockers or ["Canonical medical assessment was blocked; see live-input evidence."])
    missing = {"min_face_amount", "surrender_value", "level_annual_premium", "loan_payoff"} - request["options"].keys()
    if missing:
        blockers.append("Unresolved financial fields: " + ", ".join(sorted(missing)))
    if blockers:
        output = {"status": "blocked", "html": None, "results": None,
                  "inputs": request, "blockers": blockers, "quote_issued": False}
    else:
        try:
            output = quote_abr(request)
        except Exception as exc:
            output = {"status": "blocked", "html": None, "results": None,
                      "inputs": request, "blockers": [str(exc)], "quote_issued": False}
    output.setdefault("inputs", request)
    output.setdefault("results", output.get("numbers"))
    if evidence.get("medical_boundary"):
        output["needs_review"] = True
        output["warnings"] = output.get("warnings") or [evidence["medical_boundary"]]
    output["provenance"] = output.get("provenance", {})
    output["provenance"].update(
        benchmark_access=False, historical_snapshot=False,
        resolver_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        funding_source_sha256={
            str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
            for path in (
                ROOT / "suiteview" / "illustration" / "core" / "abr_quote.py",
                ROOT / "suiteview" / "illustration" / "core" / "solve_premium_to_target.py",
                ROOT / "suiteview" / "illustration" / "core" / "calc_engine.py",
                ROOT / "suiteview" / "illustration" / "core" / "illustration_policy_service.py",
                ROOT / "suiteview" / "core" / "rates.py",
            )
        },
        financial_derivations=resolved,
    )
    return _json_value({"request": request, "output": output,
                        "live_inputs": evidence, "funding": funding})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    destination = args.output.resolve()
    evidence_root = (ROOT.parent / "WorkOps_Manager" / "workspace" / "albert").resolve()
    if destination != evidence_root and evidence_root not in destination.parents:
        parser.error("Output must be within WorkOps_Manager\\workspace\\albert")
    names = ("request.json", "output.json", "live-inputs-resolved.json", "funding.json", "manifest.json")
    if any((destination / name).exists() for name in names):
        parser.error("Refusing to overwrite existing independent evidence")
    source = None
    failed = False
    try:
        with redirect_stdout(sys.stderr):
            source = json.loads(args.input.read_text(encoding="utf-8-sig"))
            package = resolve_inputs(source)
    except Exception as exc:
        failed = True
        package = {
            "request": source,
            "output": {
                "status": "error", "html": None, "results": None,
                "inputs": source, "quote_issued": False,
                "error_type": type(exc).__name__, "message": str(exc),
                "blockers": [str(exc)], "needs_review": True,
                "provenance": {"phase": "input_resolution", "benchmark_access": False},
            },
            "live_inputs": None, "funding": None,
        }
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for key, name in zip(("request", "output", "live_inputs", "funding"), names):
        path = destination / name
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(package[key], indent=2, allow_nan=False, ensure_ascii=True) + "\n")
        manifest[name] = sha256(path.read_bytes()).hexdigest()
    with (destination / "manifest.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": package["output"]["status"], "output": str(destination),
                      "manifest": manifest}))
    return 1 if failed else (0 if package["output"]["status"] == "calculated" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
