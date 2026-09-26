"""Agent entry point for the dedicated ABR Quote application's calculation.

No windows, clipboard operations, recipient database, approvals or email sends.
The small in-memory ports below run the *existing* UI orchestration methods;
they deliberately do not reimplement actuarial calculations or HTML formatting.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import math
import os
from pathlib import Path

from .models.abr_data import ABRPolicyData
from .models.abr_database import using_quote_database


class QuoteError(ValueError):
    """A request cannot be quoted without inventing or silently ignoring inputs."""


class BoundaryReviewRequired(QuoteError):
    """A valid nonnegative mortality boundary, rather than an exact target fit."""
    def __init__(self, details):
        self.details = details
        super().__init__(
            f"Nonnegative mortality boundary: requested ten-year survival "
            f"{details['requested_10yr']}, attained {details['attained_10yr']}. "
            "Canonical UI permits continuation; automated boundary acceptance requires review."
        )


def _number(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise QuoteError(f"{name} must be a number")
    if not math.isfinite(value) or value < minimum:
        raise QuoteError(f"{name} must be finite and >= {minimum}")
    return value


def _date(value, name):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError()
        return parsed
    except (ValueError, TypeError):
        raise QuoteError(f"{name} must be YYYY-MM-DD") from None


@dataclass(frozen=True)
class QuoteRequest:
    policy_number: str
    company_code: str
    region: str
    quote_date: date
    assessment: dict
    options: dict
    effective_date: date | None = None
    input_provenance: dict | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "QuoteRequest":
        if not isinstance(data, dict):
            raise QuoteError("Request must be a JSON object")
        required = {"policy_number", "company_code", "region", "quote_date",
                    "assessment", "options"}
        allowed = required | {"effective_date", "input_provenance"}
        if required - data.keys() or data.keys() - allowed:
            raise QuoteError(f"Missing fields: {sorted(required - data.keys())}; "
                             f"unknown fields: {sorted(data.keys() - allowed)}")
        for key in ("policy_number", "company_code", "region"):
            if not isinstance(data[key], str) or not data[key].strip():
                raise QuoteError(f"{key} must be an explicit non-empty string")
            if data[key] != data[key].strip():
                raise QuoteError(f"{key} must not contain surrounding whitespace")
        qd = _date(data["quote_date"], "quote_date")
        ed = (_date(data["effective_date"], "effective_date")
              if data.get("effective_date") is not None else None)
        if ed and ed != qd:
            raise QuoteError("Distinct effective_date and quote_date are unsupported; "
                             "the ABR application has one quote date, not an as-of policy loader")
        assessment = data["assessment"]
        options = data["options"]
        if not isinstance(assessment, dict) or not isinstance(options, dict):
            raise QuoteError("assessment and options must be objects")
        _validate_assessment(assessment)
        allowed_options = {"min_face_amount", "level_annual_premium", "loan_payoff",
                           "surrender_value", "after_partial_deduction", "interest_rate_override"}
        if options.keys() - allowed_options:
            raise QuoteError(f"Unsupported options: {sorted(options.keys() - allowed_options)}")
        if "min_face_amount" not in options:
            raise QuoteError("options.min_face_amount is required; no guessed minimum")
        for key, value in options.items():
            _number(value, f"options.{key}")
        if data.get("input_provenance") is not None and not isinstance(data["input_provenance"], dict):
            raise QuoteError("input_provenance must be an object")
        return cls(data["policy_number"], data["company_code"], data["region"],
                   qd, deepcopy(assessment), deepcopy(options), ed,
                   deepcopy(data.get("input_provenance") or {}))


_SURVIVAL = {"five_year_survival": "five_year", "ten_year_survival": "ten_year",
             "life_expectancy_years": "le"}
_DIRECT = {"table": "table", "flat": "flat", "table_2": "table_2",
           "flat_2": "flat_2", "increased_decrement": "incr_decrement"}


def _validate_assessment(a):
    allowed = {"rider_type", "return_after_5yr", "return_after_10yr"} | _SURVIVAL.keys() | _DIRECT.keys()
    if a.keys() - allowed or a.get("rider_type") not in {"Terminal", "Chronic", "Critical"}:
        raise QuoteError("Invalid/unsupported assessment fields or rider_type")
    if a["rider_type"] == "Terminal":
        _validate_terminal_assessment(a)
        return
    if not (set(a) & (_SURVIVAL.keys() | {"table", "increased_decrement"})):
        raise QuoteError("Non-terminal assessment requires survival, table or increased_decrement")
    if "life_expectancy_years" in a and set(a) & {"five_year_survival", "ten_year_survival"}:
        raise QuoteError("Do not combine life expectancy with survival targets (UI would ignore LE)")
    _validate_survival_inputs(a)
    _validate_return_flags(a)
    _validate_direct_inputs(a)


def _validate_terminal_assessment(a):
    if set(a) != {"rider_type"}:
        raise QuoteError("Terminal uses the application's fixed 50% annual mortality; "
                         "additional medical inputs are unsupported")


def _validate_survival_inputs(a):
    for key in _SURVIVAL:
        if key in a:
            n = _number(a[key], key)
            if key != "life_expectancy_years" and not 0 < n < 1:
                raise QuoteError(f"{key} must be strictly between 0 and 1")
            if key == "life_expectancy_years" and n <= 0:
                raise QuoteError("life_expectancy_years must be positive")
    if a.get("ten_year_survival", 0) > a.get("five_year_survival", 1):
        raise QuoteError("10-year survival cannot exceed 5-year survival")


def _validate_return_flags(a):
    for key in ("return_after_5yr", "return_after_10yr"):
        if key in a and not isinstance(a[key], bool):
            raise QuoteError(f"{key} must be boolean")
        source = "five_year_survival" if key == "return_after_5yr" else "ten_year_survival"
        if a.get(key) and source not in a:
            raise QuoteError(f"{key} requires {source}")
    if a.get("return_after_5yr") and "ten_year_survival" in a:
        raise QuoteError("Dual survival uses return_after_10yr, not return_after_5yr")


def _validate_direct_inputs(a):
    for key in _DIRECT:
        if key not in a:
            continue
        item = a[key]
        if not isinstance(item, dict) or set(item) != {"value", "start_year", "stop_year"}:
            raise QuoteError(f"{key} requires value, start_year and exclusive stop_year")
        _number(item["value"], key)
        for bound in ("start_year", "stop_year"):
            if type(item[bound]) is not int or item[bound] < 1:
                raise QuoteError(f"{key}.{bound} must be a positive integer")
        if item["stop_year"] <= item["start_year"]:
            raise QuoteError(f"{key}.stop_year must exceed start_year")


def policy_activity(pi):
    """Resolve current activity without inventing a missing legacy status code."""
    from suiteview.polview.models.cl_polrec.policy_translations import (
        PREMIUM_PAY_STATUS_CODES, SUSPENSE_CODES,
    )
    if str(pi.status_code).strip():
        return {"verified_active": bool(pi.is_active), "source": "PolicyInformation.status_code",
                "status_code": pi.status_code}
    paying = str(pi.data_item("LH_BAS_POL", "PRM_PAY_STA_REA_CD") or "").strip()
    raw_suspense = pi.data_item("LH_BAS_POL", "SUS_CD")
    suspense = "" if raw_suspense is None else str(raw_suspense).strip()
    return {
        "verified_active": paying in {"21", "22"} and suspense == "0",
        "source": "LH_BAS_POL actual billing/suspense fields; maintained policy_translations",
        "premium_pay_status_code": paying,
        "premium_pay_status_description": PREMIUM_PAY_STATUS_CODES.get(paying),
        "suspense_code": suspense, "suspense_description": SUSPENSE_CODES.get(suspense),
        "limitation": "Conservative fallback supports explicit premium-paying/active only; not historical status.",
    }


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(v) for v in value]
    return value


def _assessment_port(policy, request):
    from .core.assessment_solver import AssessmentInputs, solve_substandard
    from .automation_data import reject_lookup_warnings
    a = request.assessment
    direct_values = {
        key: a.get(key, {}) if key in a else {}
        for key in _DIRECT
    }
    inputs = AssessmentInputs(
        rider_type=a["rider_type"],
        use_five_year="five_year_survival" in a,
        use_ten_year="ten_year_survival" in a,
        use_le="life_expectancy_years" in a,
        use_table="table" in a,
        use_flat="flat" in a,
        use_table_2="table_2" in a,
        use_flat_2="flat_2" in a,
        use_increased_decrement="increased_decrement" in a,
        use_return_5yr=a.get("return_after_5yr", False),
        use_return_10yr=a.get("return_after_10yr", False),
        five_year_survival=a.get("five_year_survival", 0.0),
        ten_year_survival=a.get("ten_year_survival", 0.0),
        life_expectancy_years=a.get("life_expectancy_years", 0.0),
        direct_table_rating=direct_values["table"].get("value", 0.0),
        table_start_year=direct_values["table"].get("start_year", 1),
        table_stop_year=direct_values["table"].get("stop_year", 99),
        direct_flat_extra=direct_values["flat"].get("value", 0.0),
        flat_start_year=direct_values["flat"].get("start_year", 1),
        flat_stop_year=direct_values["flat"].get("stop_year", 99),
        direct_table_rating_2=direct_values["table_2"].get("value", 0.0),
        table_2_start_year=direct_values["table_2"].get("start_year", 1),
        table_2_stop_year=direct_values["table_2"].get("stop_year", 99),
        direct_flat_extra_2=direct_values["flat_2"].get("value", 0.0),
        flat_2_start_year=direct_values["flat_2"].get("start_year", 1),
        flat_2_stop_year=direct_values["flat_2"].get("stop_year", 99),
        direct_increased_decrement=direct_values["increased_decrement"].get("value", 0.0),
        incr_decrement_start_year=direct_values["increased_decrement"].get("start_year", 1),
        incr_decrement_stop_year=direct_values["increased_decrement"].get("stop_year", 99),
    )
    result = None
    try:
        with reject_lookup_warnings("suiteview.abrquote.core.goal_seek"):
            result = solve_substandard(policy, inputs)
    except QuoteError as exc:
        if "Period 2 table rating goal seek failed:" not in str(exc) or result is None:
            raise
        _check_survival_boundary(a, result.assessment)
        raise
    _validate_assessment_result(a, result.assessment)
    return result.assessment


def _check_survival_boundary(inputs, assessment):
    if (assessment is None or inputs.keys() & _DIRECT.keys()
            or not assessment.use_five_year or not assessment.use_ten_year):
        return
    if not {"five_year_survival", "ten_year_survival"} <= inputs.keys():
        return
    if (abs(assessment.computed_survival_5yr - inputs["five_year_survival"]) <= .0001
            and assessment.derived_table_rating_10yr == 0
            and inputs["ten_year_survival"] > assessment.computed_survival_10yr + .0001):
        raise BoundaryReviewRequired({
            "kind": "nonnegative_mortality_boundary",
            "requested_5yr": inputs["five_year_survival"],
            "attained_5yr": assessment.computed_survival_5yr,
            "requested_10yr": inputs["ten_year_survival"],
            "attained_10yr": assessment.computed_survival_10yr,
            "period_2_extra_table": 0,
            "ui_permits_continuation": True,
            "exact_fit": False,
            "required_review": "Confirm company acceptance of the standard-mortality boundary "
                               "for the supplied survival interpretation; do not replace source inputs.",
        })


def _validate_assessment_result(inputs, assessment):
    """Never present a goal-seek fallback as a successful fit to supplied targets."""
    if inputs["rider_type"] == "Terminal" or inputs.keys() & _DIRECT.keys():
        return
    _check_survival_boundary(inputs, assessment)
    for source, computed, tolerance in (
        ("five_year_survival", "computed_survival_5yr", 0.0001),
        ("ten_year_survival", "computed_survival_10yr", 0.0001),
        ("life_expectancy_years", "computed_le", 0.001),
    ):
        if source in inputs:
            value = getattr(assessment, computed)
            if not math.isfinite(value) or abs(value - inputs[source]) > tolerance:
                raise QuoteError(f"Canonical assessment did not fit {source}: "
                                 f"requested {inputs[source]}, calculated {value}; no quote issued")


class _RateTrace:
    """Record every canonical rate lookup; disallow hidden missing-rate results."""
    def __init__(self, source, product_type):
        self.source = source
        self.product_type = product_type
        self.calls = {}

    def __getattr__(self, name):
        if not name.startswith("get_"):
            raise AttributeError(name)
        method = getattr(self.source, name)

        def call(*args, **kwargs):
            if (self.product_type == "TERM"
                    and name in {"get_modal_factor", "get_modal_fee_factor"}
                    and args[1] != 1
                    and hasattr(self.source, "_get_modefact_row")):
                from .models.abr_odbc_database import _MODEFACT_COLUMN_MAP
                columns = _MODEFACT_COLUMN_MAP.get(args[1])
                row = self.source._get_modefact_row(args[0])
                index = 1 if name == "get_modal_fee_factor" else 0
                if not columns or not row or row.get(columns[index]) is None:
                    raise QuoteError("Required modal factor missing; no annual fallback permitted")
            value = method(*args, **kwargs)
            key = json.dumps(_json_value([name, args, kwargs]), sort_keys=True)
            self.calls[key] = _json_value(value)
            # UL orchestration calls the term premium display calculator even
            # though its APV premiums come exclusively from the explicit level input.
            ul_term_display = self.product_type in {"UL", "IUL", "ISWL"} and name == "get_term_rate"
            if value is None and not ul_term_display:
                raise QuoteError(f"Required rate data missing: {name}{args}")
            if name.endswith("_schedule") and not value and self.product_type == "TERM":
                raise QuoteError(f"Required rate schedule missing: {name}{args}")
            return value
        return call


def calculate_quote(request: QuoteRequest | dict, policy: ABRPolicyData, *,
                    database, policy_provenance: dict, eligible_riders: set[str]) -> dict:
    """Offline/injected API. Caller supplies verified policy, rate source and eligibility.

    The supplied policy is copied; the rate source must expose the canonical
    ABR read-only get_* interface. No live access is selected by this function.
    """
    request = _coerce_request(request)
    if not isinstance(policy_provenance, dict):
        raise QuoteError("policy_provenance must be an object identifying the supplied data")
    p = deepcopy(policy)
    _validate_policy_for_quote(request, p, eligible_riders)
    opt = request.options

    from .core.quote_service import ABRQuoteInputs, calculate_abr_quote
    from .core.quote_summary import render_quote_summary
    trace = _RateTrace(database, p.product_type)
    with using_quote_database(trace):
        assessment = _assessment_port(p, request)
    snapshot = calculate_abr_quote(
        ABRQuoteInputs(
            policy=p,
            assessment=assessment,
            quote_date=request.quote_date,
            min_face_amount=opt["min_face_amount"],
            interest_rate_override=opt.get("interest_rate_override"),
            level_annual_premium=opt.get("level_annual_premium"),
            loan_payoff=opt.get("loan_payoff", 0.0),
            surrender_value=opt.get("surrender_value"),
        ),
        trace,
    )
    results = snapshot.result
    _sections, html, text = render_quote_summary(p, results, assessment)
    return _quote_response(
        request,
        p,
        assessment,
        results,
        html,
        text,
        trace,
        policy_provenance,
        eligible_riders,
    )


def _coerce_request(request: QuoteRequest | dict) -> QuoteRequest:
    if isinstance(request, QuoteRequest):
        return QuoteRequest.from_dict(_json_value(asdict(request)))
    return QuoteRequest.from_dict(request)


def _validate_policy_for_quote(request: QuoteRequest, p: ABRPolicyData, eligible_riders: set[str]) -> None:
    _validate_policy_identity(request, p, eligible_riders)
    _validate_policy_basis(request, p)
    _validate_quote_options(request, p)


def _validate_policy_identity(request: QuoteRequest, p: ABRPolicyData, eligible_riders: set[str]) -> None:
    if p.policy_number != request.policy_number or p.region != request.region:
        raise QuoteError("Loaded policy identity does not match request")
    if p.company.split(" ")[0] != request.company_code:
        raise QuoteError("Loaded company does not match request")
    if request.assessment["rider_type"] not in eligible_riders:
        raise QuoteError("Requested ABR rider is not verified active on this policy")


def _validate_policy_basis(request: QuoteRequest, p: ABRPolicyData) -> None:
    if p.product_type not in {"TERM", "UL", "IUL", "ISWL"}:
        raise QuoteError(f"Unsupported ABR product: {p.product_type!r}")
    if not p.issue_date or not p.plan_code or not p.issue_state or not p.rate_class:
        raise QuoteError("Required policy issue date, plan, state or rate class is missing")
    if (p.rate_sex or p.sex) not in {"M", "F"}:
        raise QuoteError("Unsupported or missing mortality rate sex")
    if p.face_amount <= 0 or p.maturity_age <= p.issue_age or p.policy_year < 1 or not 1 <= p.policy_month <= 12:
        raise QuoteError("Invalid policy face, maturity or duration")
    if p.billing_mode not in {1, 2, 3, 4, 5, 6}:
        raise QuoteError("Unsupported billing mode")
    if request.quote_date < p.issue_date or (p.maturity_date and request.quote_date >= p.maturity_date):
        raise QuoteError("Quote date is outside policy coverage")
    if not p.reinsurers:
        raise QuoteError("Reinsurer lookup status is required; do not replace unknown with '(none)'")


def _validate_quote_options(request: QuoteRequest, p: ABRPolicyData) -> None:
    opt = request.options
    if opt["min_face_amount"] > p.face_amount:
        raise QuoteError("Minimum remaining face exceeds policy face")
    is_ul = p.product_type in {"UL", "IUL", "ISWL"}
    ul_fields = {"level_annual_premium", "loan_payoff", "surrender_value"}
    if is_ul and ul_fields - opt.keys():
        raise QuoteError(f"UL requires explicit options: {sorted(ul_fields - opt.keys())}")
    if not is_ul and opt.keys() & (ul_fields | {"after_partial_deduction"}):
        raise QuoteError("UL-specific inputs supplied for a TERM product")


def _quote_response(
    request: QuoteRequest,
    p: ABRPolicyData,
    assessment,
    results,
    html: str,
    text: str,
    trace: _RateTrace,
    policy_provenance: dict,
    eligible_riders: set[str],
) -> dict:
    root = Path(__file__).parent
    opt = request.options
    files = [Path(__file__), root / "automation_data.py", *sorted((root / "core").glob("*.py")),
             root / "models" / "abr_constants.py", root / "models" / "abr_data.py",
             root / "models" / "abr_odbc_database.py", root / "models" / "abr_database.py",
             root / "ui" / "abr_window.py", root / "ui" / "assessment_panel.py",
             root / "ui" / "email_print_dialog.py",
             root.parent / "core" / "policy_service.py",
             root.parent / "core" / "reinsurance.py",
             root.parent / "polview" / "models" / "policy_information.py",
             root.parents[1] / "tools" / "abrquote" / "quote.py"]
    output = _json_value({
        "schema_version": 1, "status": "calculated",
        "html": html, "text": text, "numbers": asdict(results),
        "assessment": asdict(assessment), "policy": asdict(p),
        "warnings": getattr(assessment, "automation_warnings", []),
        "needs_review": bool(getattr(assessment, "automation_warnings", [])),
        "quote_issued": False,
        "provenance": {
            "request": asdict(request), "policy_source": policy_provenance,
            "execution_mode": "strict",
            "historical_equivalence_asserted": False,
            "calculated_at": datetime.now(timezone.utc),
            "engine": "SuiteView dedicated ABR Quote (not IllustrationEngine)",
            "renderer": "EmailPrintDialog._build_clipboard_html",
            "source_sha256": {str(f.relative_to(root.parents[1])): sha256(f.read_bytes()).hexdigest() for f in files},
            "rate_lookups": trace.calls,
            "date_semantics": "Quote date controls interest/per-diem and premium duration. "
                              "Mortality/APV and HTML retain the loaded policy duration, exactly "
                              "as the ABR application does. Live data is not a historical snapshot.",
            "eligible_riders": sorted(eligible_riders),
            "after_partial_deduction": opt.get("after_partial_deduction"),
        },
    })
    json.dumps(output, allow_nan=False)
    return output


def quote_abr(request: QuoteRequest | dict) -> dict:
    """Read-only live adapter. Callers own authorization; this function never prompts."""
    req = _coerce_request(request)
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise QuoteError("Live ABR quoting requires local-data mode to be disabled; "
                         "use calculate_quote for explicit offline fixtures")
    p, pi, activity, benefits, actual_company = _load_live_policy(req)
    eligible = _eligible_live_riders(req, pi.get_coverages(), benefits)
    db, queries = _open_live_rate_database(p.product_type)
    try:
        response = calculate_quote(
            req,
            p,
            database=db,
            eligible_riders=eligible,
            policy_provenance=_live_policy_provenance(
                req,
                p,
                pi,
                activity,
                benefits,
                actual_company,
            ),
        )
        response["provenance"]["rate_queries"] = queries
        return response
    finally:
        db.close()


def _load_live_policy(req: QuoteRequest):
    from .core.abr_policy_service import build_abr_policy
    from .automation_data import reject_lookup_warnings
    from suiteview.core.reinsurance import fetch_reinsurer_list

    with reject_lookup_warnings("suiteview.polview.models"):
        with reject_lookup_warnings("suiteview.abrquote.core.abr_policy_service"):
            p, pi = build_abr_policy(req.policy_number, req.region,
                                     company_code=req.company_code,
                                     use_cache=False,
                                     as_of_date=req.quote_date)
    if pi is None or p is None:
        raise QuoteError("Live policy retrieval failed; manual/default policy is forbidden")
    activity = policy_activity(pi)
    if not activity["verified_active"]:
        raise QuoteError(f"Policy is not active (status {pi.status_code}); "
                         "historical in-force reconstruction is unsupported")
    actual_company = str(pi.data_item("LH_BAS_POL", "CK_CMP_CD") or "").strip()
    if actual_company != req.company_code:
        raise QuoteError("Live company identity mismatch")
    for field in ("base_issue_age", "base_rate_class", "age_at_maturity",
                  "billing_frequency", "policy_month", "policy_year",
                  "primary_insured_face_amount", "issue_date"):
        if getattr(pi, field) in (None, ""):
            raise QuoteError(f"Required CyberLife input missing: {field}")
    for field in ("age_at_maturity", "billing_frequency", "policy_month", "policy_year"):
        if getattr(pi, field) <= 0:
            raise QuoteError(f"Invalid CyberLife input: {field}")
    coverages = pi.get_coverages()
    benefits = pi.get_benefits()
    _validate_live_ul_values(p, pi)
    p.company = actual_company
    with reject_lookup_warnings("suiteview.core.reinsurance"):
        p.reinsurers = fetch_reinsurer_list(req.policy_number, req.company_code, req.quote_date)
    return p, pi, activity, benefits, actual_company


def _validate_live_ul_values(p: ABRPolicyData, pi) -> None:
    if p.product_type not in {"UL", "IUL", "ISWL"}:
        return
    if pi.mv_monthly_deduction() is None:
        raise QuoteError("UL monthly deduction is missing")
    if str(p.db_option).upper() in {"2", "B"} and pi.mv_av(0) is None and pi.accumulation_value is None:
        raise QuoteError("Option B account value is missing")
    if str(p.db_option).upper() in {"3", "C"} and pi.total_premiums_paid is None:
        raise QuoteError("Option C premiums paid is missing")


def _eligible_live_riders(req: QuoteRequest, coverages, benefits) -> set[str]:
    from .ui.assessment_panel import AssessmentPanel

    eligible = set()
    primary_phases = {cov.cov_pha_nbr for cov in coverages if cov.person_code in {"00", ""}}
    for benefit in benefits:
        if str(benefit.benefit_type_cd).strip() != "#":
            continue
        if benefit.cov_pha_nbr not in primary_phases:
            continue
        if benefit.issue_date is None:
            raise QuoteError("ABR rider issue date is missing; eligibility cannot be verified")
        if benefit.issue_date > req.quote_date:
            continue
        if benefit.cease_date and benefit.cease_date < req.quote_date:
            continue
        rider = AssessmentPanel._ABR_SUBTYPE_TO_RIDER.get(str(benefit.benefit_subtype_cd).strip())
        if rider:
            eligible.add(rider)
    return eligible


def _open_live_rate_database(product_type: str):
    from .automation_data import open_rate_database

    return open_rate_database(product_type)


def _live_policy_provenance(req, p, pi, activity, benefits, actual_company) -> dict:
    return {
        "source": "CyberLife DB2 via build_abr_policy/PolicyInformation",
        "company_code": actual_company,
        "region": req.region,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "valuation_date": _json_value(p.valuation_date),
        "policy_status": pi.status_code,
        "activity_resolution": activity,
        "abr_benefits": [
            {"type": b.benefit_type_cd, "subtype": b.benefit_subtype_cd,
             "coverage_phase": b.cov_pha_nbr,
             "issue_date": _json_value(b.issue_date),
             "cease_date": _json_value(b.cease_date)}
            for b in benefits if str(b.benefit_type_cd).strip() == "#"
        ],
        "reinsurance": "TAICession via fetch_reinsurer_list",
        "rates": "UL_Rates ODBC; IssueVersion=1; current scale then guaranteed",
    }
