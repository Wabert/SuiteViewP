"""UI-independent batch forecast orchestration for the Illustration app.

One place owns the per-policy forecast logic that used to live inside the CLI
batch tools (``tools/run_glp_forecast_batch.py`` and
``tools/run_min_level_to_exception_batch.py``). Both the CLI tools and the
Illustration app's Batch tab call through here:

  * ``FORECAST_TYPES`` — the registry of available batch forecasts. Each entry
    carries its display label, ordered output columns (field key → column
    label), the per-column format class, and the per-policy run function.
  * ``run_batch`` — iterate a policy list through a forecast's per-policy
    function with progress reporting, cooperative cancellation, and per-policy
    error isolation (one bad policy never aborts the batch).
  * ``parse_policy_list`` — tolerant multiline policy-list parsing (whitespace,
    duplicates, optional per-line company code).
  * ``results_dataframe`` — flatten a batch's results into a display-ready
    pandas DataFrame (policies as rows, forecast outputs as columns, plus loud
    Status / Error columns).

Per-policy functions return a ``PolicyResult`` whose ``values`` dict is keyed
by field key; the CLI tools map those keys onto workbook columns, the Batch tab
maps them onto DataFrame columns. Every per-policy function catches its own
failures and reports them as a status + error string.

Live data: policies load through PolicyInformation / DB2 like the rest of the
app. Local SQLite fixtures are opt-in via SUITEVIEW_LOCAL_DATA=1 only.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

# ── Shared constants ────────────────────────────────────────────────────────

# Months-between-payments → modal code for a policy's own billing cadence.
MODE_FROM_FREQ = {1: "M", 3: "Q", 6: "S", 12: "A"}

DB_OPTION_DISPLAY = {"1": "A - Level", "A": "A - Level",
                     "2": "B - Increasing", "B": "B - Increasing",
                     "3": "C - ROP", "C": "C - ROP"}

MATURITY_LABEL = "Maturity"
NO_EXCEPTION_LABEL = "(none)"
NO_SOLUTION_LABEL = "no solution"

STATUS_COMPLETE = "Complete"
STATUS_ERROR = "Error"
STATUS_MATURED = "Matured w/o Except Prem"   # min-level solve: endows on its own
STATUS_EXCEPT = "Except Prem Required"       # min-level solve: rides the GLP exception

# Monthly premium that always trips the guideline acceptance cap, so the policy
# is funded to the absolute maximum the guideline allows (exceptions off).
GLP_ABSOLUTE_MAX_PREMIUM = 9_999_999.0
MINLEVEL_ABSOLUTE_MAX_PREMIUM = 999_999_999.0

# Format classes for output columns (the CLI tools translate these to Excel
# number formats; the Batch tab uses them for display formatting).
FMT_MONEY = "money"
FMT_DATE = "date"
FMT_MIXED_DATE = "mixed_date"   # a real date OR a text label ("Maturity", ...)
FMT_INT = "int"
FMT_TEXT = "text"


# ── Result / registry types ─────────────────────────────────────────────────

@dataclass
class PolicyResult:
    """One policy's outcome in a batch run."""
    policy: str
    company: Optional[str]
    status: str                       # "Complete" / "bypass (...)" / "Error" / solve status
    error: Optional[str] = None       # load/check/solve failure detail, or None
    values: Dict[str, object] = field(default_factory=dict)  # field key -> value


@dataclass(frozen=True)
class ForecastType:
    """A batch forecast the runner knows how to execute per policy."""
    key: str
    label: str
    columns: Tuple[Tuple[str, str], ...]   # ordered (field key, column label)
    formats: Dict[str, str]                # field key -> FMT_* class
    run: Callable[..., PolicyResult]       # run(policy_number, company=, region=, engine=)

    def column_label(self, key: str) -> str:
        for k, label in self.columns:
            if k == key:
                return label
        return key


# ── Policy-list parsing ─────────────────────────────────────────────────────

_COMPANY_CODES = {"01", "04", "06", "08", "26"}


def parse_policy_list(text: str) -> List[Tuple[Optional[str], str]]:
    """Parse a pasted multiline policy list into ``[(company or None, policy)]``.

    One policy per line. Tolerates surrounding whitespace, blank lines, and
    duplicates (first occurrence wins). A line may optionally lead with a
    two-digit company code separated by a comma, tab, or spaces —
    ``01 UL054426`` / ``01,UL054426`` — matching the batch workbooks'
    Company-then-Policy column order.
    """
    entries: List[Tuple[Optional[str], str]] = []
    seen: set = set()
    for raw_line in (text or "").splitlines():
        tokens = [t for t in raw_line.replace(",", " ").replace("\t", " ").split() if t]
        if not tokens:
            continue
        company: Optional[str] = None
        if len(tokens) >= 2 and tokens[0] in _COMPANY_CODES:
            company = tokens[0]
            policy = tokens[1]
        else:
            policy = tokens[0]
        policy = policy.strip().upper()
        if not policy:
            continue
        dedupe_key = (company, policy)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        entries.append((company, policy))
    return entries


# ── Shared per-policy helpers ───────────────────────────────────────────────

def _maturity_date(policy) -> Optional[date]:
    """Base-coverage maturity date, falling back to issue date + term in years."""
    seg = policy.base_segment
    if seg is not None and seg.maturity_date is not None:
        return seg.maturity_date
    if policy.issue_date is not None and policy.maturity_age and policy.issue_age:
        years = int(policy.maturity_age) - int(policy.issue_age)
        try:
            return policy.issue_date.replace(year=policy.issue_date.year + years)
        except ValueError:  # Feb 29 issue
            return policy.issue_date.replace(
                year=policy.issue_date.year + years, day=28)
    return None


def _maturity_duration(policy) -> Optional[int]:
    """Policy-year count to maturity = maturity age − issue age."""
    if policy.maturity_age and policy.issue_age:
        return max(0, int(policy.maturity_age) - int(policy.issue_age))
    return None


def billing_mode_code(policy) -> str:
    return MODE_FROM_FREQ.get(int(policy.billing_frequency or 1), "M")


def _lapse_or_maturity(states, policy):
    """First lapse date in a stop-on-lapse projection, or "Maturity"."""
    if not states:
        return None
    lapse = next((s for s in states if s.lapsed), None)
    if lapse is not None:
        return lapse.date or lapse.policy_year
    if states[-1].attained_age >= policy.maturity_age:
        return MATURITY_LABEL
    return None


def _md_and_rate_check(engine, policy):
    """Rate availability + MD-vs-CyberLife check for a loaded policy.

    Returns ``(md_diff, system_md, missing_rates, check_error)``. On failure the
    first three are best-effort and ``check_error`` explains why.
    """
    from suiteview.illustration.core.rate_loader import load_rates
    from suiteview.illustration.core.rate_validation import (
        missing_required_rate_warnings,
    )
    from suiteview.illustration.models.plancode_config import load_plancode

    system_md = round(float(policy.system_monthly_deduction or 0.0), 2)
    md_diff = None
    missing_rates: List[str] = []
    check_error = None
    try:
        config = load_plancode(policy.plancode)
        rates = load_rates(policy, config)
        missing_rates = missing_required_rate_warnings(policy, rates)
        seed = engine.project(policy, months=0, rates_override=rates)[0]
        system_md = round(float(seed.system_monthly_deduction or 0.0), 2)
        md_diff = round(
            float(seed.system_monthly_deduction or 0.0)
            - float(seed.md_check_calculated_deduction or 0.0), 2)
    except Exception as exc:  # rates DB / plancode / engine failure
        check_error = f"Rate/MD check failed: {exc}"
    return md_diff, system_md, missing_rates, check_error


def _riders_and_policy_info(policy_number: str, region: str, company: Optional[str]):
    """Active premium-paying rider/benefit codes + the PolicyInformation used."""
    from suiteview.core.policy_service import get_policy_info
    from suiteview.illustration.core.illustration_policy_service import (
        active_rider_benefit_codes,
    )
    pi = get_policy_info(policy_number, region, company)
    riders = active_rider_benefit_codes(pi) if pi is not None else ""
    return riders, pi


def _forecast_options(allow_exceptions: bool = False):
    """Guideline-only basis for the GLP forecasts: TEFRA on, TAMRA OFF."""
    from suiteview.illustration.models.input_set import IllustrationOptions
    return IllustrationOptions(
        conform_to_tefra=True,
        conform_to_tamra=False,
        allow_exception_prems=allow_exceptions,
    )


# ── GLP lapse/exception forecasts (four forecasts per policy) ───────────────

GLP_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("plancode", "Plancode"),
    ("form", "Form"),
    ("issue_date", "Issue Date"),
    ("issue_age", "Issue Age"),
    ("maturity_date", "Maturity Date"),
    ("maturity_age", "Maturity Age"),
    ("face", "Face Amount"),
    ("db_option", "DB Option"),
    ("def_life_ins", "Def Life Ins"),
    ("billing_prem", "Billing Prem"),
    ("billing_mode", "Billing Mode"),
    ("riders", "Active Riders and Benefits"),
    ("md_diff", "MD Diff"),
    ("gsp", "GSP"),
    ("glp", "GLP"),
    ("accum_lp", "AccumLP"),
    ("prem_td", "PremTD"),
    ("accum_wd", "AccumWD"),
    ("valuation_date", "Valuation Date"),
    ("suspense_code", "Suspense Code"),
    ("run_status", "Run Status"),
    ("lapse_no_prem", "Estimated Lapse Date (no more premiums)"),
    ("lapse_cur_prem", "Estimated Lapse Date (current premium)"),
    ("lumpsum", "Lumpsum needed"),
    ("exc_date", "Estimated Exception Prem Date (min level premium)"),
    ("level_prem", "Level Prem to Exception"),
    ("lapse_abs_max", "Estimated Lapse Date Absoluate Max"),
)

GLP_FORMATS: Dict[str, str] = {
    **{k: FMT_MONEY for k in ("face", "billing_prem", "gsp", "glp", "accum_lp",
                              "prem_td", "accum_wd", "md_diff", "lumpsum",
                              "level_prem")},
    **{k: FMT_DATE for k in ("issue_date", "maturity_date", "valuation_date")},
    **{k: FMT_MIXED_DATE for k in ("lapse_no_prem", "lapse_cur_prem",
                                   "exc_date", "lapse_abs_max")},
    **{k: FMT_INT for k in ("issue_age", "maturity_age")},
}

GLP_FORECAST_KEYS = ("lapse_no_prem", "lapse_cur_prem", "lumpsum", "exc_date",
                     "level_prem", "lapse_abs_max")


def _glp_snapshot(policy) -> Dict[str, object]:
    """The policy's current inforce snapshot columns for the GLP forecast set."""
    db_code = str(getattr(policy, "db_option", "") or "").strip().upper()
    return {
        "plancode": (policy.plancode or "").strip(),
        "form": (policy.form_number or "").strip(),
        "issue_date": policy.issue_date,
        "issue_age": policy.issue_age,
        "maturity_date": _maturity_date(policy),
        "maturity_age": int(policy.maturity_age) if policy.maturity_age else None,
        "face": round(policy.face_amount, 2),
        "db_option": DB_OPTION_DISPLAY.get(db_code, db_code or None),
        "def_life_ins": (policy.def_of_life_ins or "").strip() or None,
        "billing_prem": round(float(policy.modal_premium or 0.0), 2),
        "gsp": round(policy.gsp, 2),
        "glp": round(policy.glp, 2),
        "accum_lp": round(policy.accumulated_glp, 2),
        "prem_td": round(policy.premiums_paid_to_date, 2),
        "accum_wd": round(policy.withdrawals_to_date, 2),
        "valuation_date": policy.valuation_date,
    }


def run_glp_forecast_policy(
    policy_number: str,
    *,
    company: Optional[str] = None,
    region: str = "CKPR",
    engine=None,
) -> PolicyResult:
    """Run the four GLP lapse/exception forecasts for one policy.

    All forecasts run on a guideline-only basis (Conform to TEFRA on, Conform
    to TAMRA OFF):

      1. Estimated Lapse Date (no more premiums) — premiums forced to zero,
         GP exceptions off.
      2. Estimated Lapse Date (current premium) — the policy's current billing
         premium/mode with a solved "Lumpsum to Next Premium" bridge layered in.
      3. Estimated Exception Prem Date (min level premium) — the Prem to
         Maturity solve (exceptions allowed) with the same bridge; also yields
         Level Prem to Exception. Loan policies solve with Apply Premium to
         Loan First.
      4. Estimated Lapse Date Absolute Max — an INPUT-premium run at 9,999,999
         monthly, clipped by the guideline acceptance cap (exceptions off).

    Bypass gates (shadow account / MD diff / missing rates / CVAT) skip the
    forecasts but keep the snapshot. Never raises — failures come back as a
    status + error string.
    """
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import (
        build_illustration_data,
    )
    from suiteview.illustration.core.solve_level_to_exception import (
        LevelToExceptionError, solve_level_to_exception,
    )
    from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
        LUMPSUM_SUBTYPE, solve_lumpsum_to_next_premium,
    )
    from suiteview.illustration.models.input_set import (
        DatedTransaction, IllustrationInputSet, ScheduledTransaction,
        TransactionKind,
    )

    engine = engine or IllustrationEngine()
    values: Dict[str, object] = {}

    def result(status: str, error: Optional[str] = None) -> PolicyResult:
        values["run_status"] = status
        return PolicyResult(policy=policy_number, company=company,
                            status=status, error=error, values=values)

    try:
        # ── Load the policy ────────────────────────────────────────────
        try:
            policy = build_illustration_data(
                policy_number, region=region, company_code=company)
        except Exception as exc:  # not found / load failure
            return result("bypass (load error)", str(exc))

        values.update(_glp_snapshot(policy))

        # ── Active premium-paying riders/benefits + billing/suspense ──
        riders, pi = _riders_and_policy_info(policy_number, region, company)
        values["riders"] = riders or None
        if pi is not None:
            values["billing_mode"] = pi.billing_mode
            values["suspense_code"] = f"{pi.suspense_code} - {pi.suspense_description}"

        # ── MD diff + rate availability ────────────────────────────────
        md_diff, _system_md, missing_rates, check_error = _md_and_rate_check(
            engine, policy)
        values["md_diff"] = md_diff
        if check_error is not None:
            return result("bypass (check error)", check_error)

        # ── Bypass gates ───────────────────────────────────────────────
        bypass = []
        if policy.has_shadow_account:
            bypass.append(("A", "active shadow account (benefit type A)"))
        if md_diff is not None and md_diff != 0.0:
            bypass.append(("MD", f"MD diff {md_diff:,.2f}"))
        if missing_rates:
            bypass.append(("rates missing", "missing rider/benefit rates"))
        if policy.is_cvat:
            bypass.append(("CVAT", "CVAT policy — forecasts are GPT-only"))
        if bypass:
            return result(
                f"bypass ({', '.join(code for code, _ in bypass)})",
                "; ".join(detail for _, detail in bypass))

        # ── Run 1: no more premiums ────────────────────────────────────
        no_prem_future = IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.PREMIUM, policy_year=1,
                amount=0.0, mode="A")])
        states = engine.project(
            deepcopy(policy), options=_forecast_options(),
            future_inputs=no_prem_future, stop_on_lapse=True)
        values["lapse_no_prem"] = _lapse_or_maturity(states, policy)

        # ── Run 2: current premium, Lumpsum to Next Premium on ─────────
        mode = billing_mode_code(policy)
        current_future = IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.PREMIUM, policy_year=1,
                amount=float(policy.modal_premium or 0.0), mode=mode)])
        options = _forecast_options()
        lumpsum_amount = None
        lumpsum_date = None
        try:
            lump = solve_lumpsum_to_next_premium(
                deepcopy(policy),
                base_future_inputs=current_future,
                base_options=options,
                engine=engine)
        except Exception:  # bridge solve failed — run without it
            lump = None
        if lump is not None and lump.lumpsum > 0:
            lumpsum_amount = lump.lumpsum
            lumpsum_date = lump.forecast_date
        dated = ([DatedTransaction(
            kind=TransactionKind.PREMIUM, effective_date=lumpsum_date,
            amount=lumpsum_amount, subtype=LUMPSUM_SUBTYPE)]
            if lumpsum_amount else [])
        current_with_lump = IllustrationInputSet(
            scheduled_transactions=list(current_future.scheduled_transactions),
            dated_transactions=list(dated))
        states = engine.project(
            deepcopy(policy), options=options,
            future_inputs=current_with_lump, stop_on_lapse=True)
        values["lapse_cur_prem"] = _lapse_or_maturity(states, policy)
        values["lumpsum"] = lumpsum_amount

        # ── Run 3: Prem to Maturity (min level, exceptions on) ─────────
        # Same lumpsum layered in; the level premium replaces the current
        # premium from year 1. Loan policies repay the loan first.
        lump_only = IllustrationInputSet(dated_transactions=list(dated))
        exc_result = None
        level_prem = None
        try:
            lte = solve_level_to_exception(
                deepcopy(policy),
                mode=None,                # the policy's own billing mode
                start_policy_year=1,
                base_future_inputs=lump_only,
                allow_exceptions=True,
                apply_prem_to_loan=policy.has_loans,
                conform_to_tamra=False,
                engine=engine)
            level_prem = lte.premium
            exc_result = (lte.exception_start if lte.enters_exception
                          else NO_EXCEPTION_LABEL)
        except LevelToExceptionError:
            exc_result = NO_SOLUTION_LABEL
        values["exc_date"] = exc_result
        values["level_prem"] = level_prem

        # ── Run 4: absolute max (guideline-capped INPUT premium) ───────
        abs_max_future = IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.PREMIUM, policy_year=1,
                amount=GLP_ABSOLUTE_MAX_PREMIUM, mode="M")])
        states = engine.project(
            deepcopy(policy), options=_forecast_options(),
            future_inputs=abs_max_future, stop_on_lapse=True)
        values["lapse_abs_max"] = _lapse_or_maturity(states, policy)

        return result(STATUS_COMPLETE)
    except Exception as exc:  # unexpected engine/solve failure — isolate it
        return result(STATUS_ERROR, str(exc))
    finally:
        from suiteview.core.policy_service import clear_cache as _clear
        _clear()


# ── Min Level to Exception solve ────────────────────────────────────────────

MINLEVEL_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("plancode", "Plancode"),
    ("form", "Form"),
    ("riders", "Active Riders and Benefits"),
    ("run_status", "Run Status"),
    ("abs_max", "Absolute Max Prem"),
    ("abs_max_av", "Absolute Max AV"),
    ("min_prem", "Min Level Prem"),
    ("exc_dur", "Exception Duration"),
    ("duration", "Current Duration"),
    ("md", "MD"),
    ("md_diff", "MD Diff"),
    ("loan", "Loan Amount"),
    ("exc_date", "Exception Date"),
    ("face", "Face Amount"),
    ("issue_date", "Issue date"),
    ("maturity_date", "Maturity Date"),
    ("maturity_duration", "Maturity Duration"),
    ("maturity_age", "Maturity Age"),
    ("issue_age", "Issue Age"),
    ("attained_age", "Attained Age"),
    ("gsp", "GSP"),
    ("glp", "GLP"),
    ("accum_lp", "AccumLP"),
    ("prem_td", "PremTD"),
    ("accum_wd", "AccumWD"),
    ("valuation_date", "Valuation Date"),
    ("suspense_code", "Suspense Code"),
    ("total_prem_paid", "Total Prem Paid"),
    ("lumpsum", "Lumpsum to Next Prem"),
    ("def_life_ins", "Def Life Ins"),
)

MINLEVEL_FORMATS: Dict[str, str] = {
    **{k: FMT_MONEY for k in ("abs_max_av", "min_prem", "md", "md_diff", "loan",
                              "face", "gsp", "glp", "accum_lp", "prem_td",
                              "accum_wd", "total_prem_paid", "lumpsum")},
    **{k: FMT_DATE for k in ("exc_date", "issue_date", "maturity_date",
                             "valuation_date")},
    **{k: FMT_INT for k in ("exc_dur", "duration", "maturity_duration",
                            "maturity_age", "issue_age", "attained_age")},
}

MINLEVEL_SOLVE_KEYS = ("min_prem", "total_prem_paid", "lumpsum", "exc_date",
                       "exc_dur")


def _minlevel_snapshot(policy) -> Dict[str, object]:
    """The policy's current inforce snapshot columns for the min-level solve."""
    return {
        "plancode": (policy.plancode or "").strip(),
        "form": (policy.form_number or "").strip(),
        "loan": round(policy.total_loan_balance, 2),
        "face": round(policy.face_amount, 2),
        "issue_date": policy.issue_date,
        "maturity_date": _maturity_date(policy),
        "maturity_duration": _maturity_duration(policy),
        "maturity_age": int(policy.maturity_age) if policy.maturity_age else None,
        "valuation_date": policy.valuation_date,
        "issue_age": policy.issue_age,
        "duration": policy.policy_year,
        "attained_age": policy.attained_age,
        "gsp": round(policy.gsp, 2),
        "glp": round(policy.glp, 2),
        "accum_lp": round(policy.accumulated_glp, 2),
        "prem_td": round(policy.premiums_paid_to_date, 2),
        "accum_wd": round(policy.withdrawals_to_date, 2),
        "def_life_ins": (policy.def_of_life_ins or "").strip() or None,
    }


def _absolute_max_result(engine, policy):
    """Forecast funded to the absolute max (guideline cap), exceptions OFF.

    Returns ``(label, maturity_av)``: label is "Maturity" if the policy still
    reaches its maturity age (and ``maturity_av`` is the account value then),
    otherwise the policy year in which it lapses (``maturity_av`` is ``None``).
    ``(None, None)`` if the projection yields nothing.
    """
    from suiteview.illustration.core.solve_level_to_exception import (
        level_to_exception_options,
    )
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet, ScheduledTransaction, TransactionKind,
    )

    options = level_to_exception_options(None, allow_exceptions=False)
    future = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=1,
            amount=MINLEVEL_ABSOLUTE_MAX_PREMIUM, mode="M")])
    states = engine.project(
        policy, future_inputs=future, options=options, stop_on_lapse=True)
    if not states:
        return None, None
    if states[-1].attained_age >= policy.maturity_age:
        return MATURITY_LABEL, round(float(states[-1].av_end_of_month or 0.0), 2)
    lapse = next((s for s in states if s.lapsed), states[-1])
    return lapse.policy_year, None


def run_min_level_policy(
    policy_number: str,
    *,
    company: Optional[str] = None,
    region: str = "CKPR",
    engine=None,
) -> PolicyResult:
    """Run the Min Level to Exception solve (plus the Absolute Max forecast)
    for one policy.

    Solves the lowest modal level premium (the policy's own billing mode) that
    keeps the GPT policy in force to maturity with GLP exception premiums
    allowed. Loan policies solve with Apply Premium to Loan First. Lumpsum to
    Next Prem is always layered on top of the solved premium. The Absolute Max
    forecast runs for every loaded policy regardless of the bypass gates.

    Never raises — failures come back as a status + error string.
    """
    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import (
        build_illustration_data,
    )
    from suiteview.illustration.core.solve_level_to_exception import (
        LevelToExceptionError, _build_result, level_to_exception_options,
        solve_level_to_exception,
    )
    from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
        LUMPSUM_SUBTYPE, solve_lumpsum_to_next_premium,
    )
    from suiteview.illustration.models.input_set import (
        DatedTransaction, IllustrationInputSet, ScheduledTransaction,
        TransactionKind,
    )

    engine = engine or IllustrationEngine()
    values: Dict[str, object] = {}

    def result(status: str, error: Optional[str] = None) -> PolicyResult:
        values["run_status"] = status
        return PolicyResult(policy=policy_number, company=company,
                            status=status, error=error, values=values)

    try:
        # ── Load the policy ────────────────────────────────────────────
        try:
            policy = build_illustration_data(
                policy_number, region=region, company_code=company)
        except Exception as exc:  # not found / load failure
            return result(STATUS_ERROR, str(exc))

        values.update(_minlevel_snapshot(policy))

        # ── Absolute Max Prem forecast (runs for every loaded policy) ──
        try:
            abs_max, abs_max_av = _absolute_max_result(engine, deepcopy(policy))
        except Exception:
            abs_max, abs_max_av = None, None
        values["abs_max"] = abs_max
        values["abs_max_av"] = abs_max_av

        # ── Active premium-paying riders/benefits + suspense code ──────
        riders, pi = _riders_and_policy_info(policy_number, region, company)
        values["riders"] = riders or None
        if pi is not None:
            values["suspense_code"] = f"{pi.suspense_code} - {pi.suspense_description}"

        # ── MD + MD diff + rate availability ───────────────────────────
        md_diff, system_md, missing_rates, check_error = _md_and_rate_check(
            engine, policy)
        values["md"] = system_md
        values["md_diff"] = md_diff
        if check_error is not None:
            return result(STATUS_ERROR, check_error)

        # ── Bypass gates ───────────────────────────────────────────────
        # A policy loan is NOT a bypass — it is solved with Apply Premium to
        # Loan First (the level premium repays the loan before funding the AV).
        bypass = []
        if policy.has_shadow_account:
            bypass.append(("A", "active shadow account (benefit type A)"))
        if md_diff is not None and md_diff != 0.0:
            bypass.append(("MD", f"MD diff {md_diff:,.2f}"))
        if missing_rates:
            bypass.append(("rates missing", "missing rider/benefit rates"))
        if bypass:
            return result(
                f"bypass ({', '.join(code for code, _ in bypass)})",
                "; ".join(detail for _, detail in bypass))

        # ── Solve (Min Level to Exception) ─────────────────────────────
        try:
            lte = solve_level_to_exception(
                deepcopy(policy),
                mode=None,                # the policy's own billing mode
                start_policy_year=1,
                allow_exceptions=True,
                apply_prem_to_loan=policy.has_loans,
            )
        except LevelToExceptionError as exc:
            code = "CVAT" if policy.is_cvat else "no solution"
            return result(f"bypass ({code})", str(exc))

        # ── Lumpsum to Next Prem (always on) ───────────────────────────
        # Layer a bridging lumpsum on top of the solved level premium so a thin
        # policy survives from the forecast date to its first modal premium.
        lumpsum_amount = None
        level_options = level_to_exception_options(
            None, allow_exceptions=True, apply_prem_to_loan=policy.has_loans)
        level_future = IllustrationInputSet(scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.PREMIUM, policy_year=1,
                amount=lte.premium, mode=lte.mode)])
        try:
            lump = solve_lumpsum_to_next_premium(
                deepcopy(policy),
                base_future_inputs=level_future,
                base_options=level_options,
                engine=engine,
            )
        except Exception:  # bridge solve failed — report the level solve alone
            lump = None
        if lump is not None and lump.lumpsum > 0:
            lumpsum_amount = lump.lumpsum
            final_future = IllustrationInputSet(
                scheduled_transactions=list(level_future.scheduled_transactions),
                dated_transactions=[DatedTransaction(
                    kind=TransactionKind.PREMIUM,
                    effective_date=lump.forecast_date,
                    amount=lump.lumpsum,
                    subtype=LUMPSUM_SUBTYPE)])
            final_states = engine.project(
                deepcopy(policy), options=level_options,
                future_inputs=final_future)
            # Keep the solved level premium; refresh exception/total-paid from
            # the run that includes the bridge.
            lte = _build_result(lte.premium, lte.mode, final_states, lte.iterations)

        values["min_prem"] = lte.premium
        values["total_prem_paid"] = round(lte.total_premium_paid, 2)
        values["lumpsum"] = round(lumpsum_amount, 2) if lumpsum_amount else None
        values["exc_date"] = lte.exception_start if lte.enters_exception else None
        values["exc_dur"] = lte.exception_duration if lte.enters_exception else None
        values["_mode"] = lte.mode
        values["_iterations"] = lte.iterations
        values["_enters_exception"] = lte.enters_exception

        return result(STATUS_EXCEPT if lte.enters_exception else STATUS_MATURED)
    except Exception as exc:  # unexpected engine/solve failure — isolate it
        return result(STATUS_ERROR, str(exc))
    finally:
        from suiteview.core.policy_service import clear_cache as _clear
        _clear()


# ── Registry ────────────────────────────────────────────────────────────────

FORECAST_TYPES: Dict[str, ForecastType] = {
    "glp_forecasts": ForecastType(
        key="glp_forecasts",
        label="GLP Lapse/Exception Forecasts",
        columns=GLP_COLUMNS,
        formats=GLP_FORMATS,
        run=run_glp_forecast_policy,
    ),
    "min_level_to_exception": ForecastType(
        key="min_level_to_exception",
        label="Min Level to Exception",
        columns=MINLEVEL_COLUMNS,
        formats=MINLEVEL_FORMATS,
        run=run_min_level_policy,
    ),
}


# ── Batch orchestration ─────────────────────────────────────────────────────

def run_batch(
    entries: Sequence[Union[str, Tuple[Optional[str], str]]],
    forecast: Union[str, ForecastType],
    *,
    region: str = "CKPR",
    default_company: Optional[str] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    engine=None,
) -> List[PolicyResult]:
    """Run ``forecast`` for every policy in ``entries``.

    Args:
        entries: policy numbers, or ``(company, policy)`` tuples (a ``None``
            company falls back to ``default_company``).
        forecast: a ``FORECAST_TYPES`` key or a ``ForecastType`` instance.
        progress: called as ``progress(index, total, policy_number)`` with a
            1-based index just before each policy runs.
        should_cancel: polled before each policy; returning True stops the
            batch after the in-flight policy (results so far are returned).

    One policy's failure never aborts the batch: the per-policy functions
    report their own errors, and any exception that still escapes is captured
    as an Error-status ``PolicyResult`` for that policy alone.
    """
    if isinstance(forecast, str):
        forecast = FORECAST_TYPES[forecast]

    normalized: List[Tuple[Optional[str], str]] = []
    for entry in entries:
        if isinstance(entry, str):
            normalized.append((None, entry.strip()))
        else:
            company, policy = entry
            normalized.append((company, str(policy).strip()))
    normalized = [(c, p) for c, p in normalized if p]

    if engine is None:
        from suiteview.illustration.core.calc_engine import IllustrationEngine
        engine = IllustrationEngine()

    results: List[PolicyResult] = []
    total = len(normalized)
    for index, (company, policy_number) in enumerate(normalized, start=1):
        if should_cancel is not None and should_cancel():
            break
        if progress is not None:
            progress(index, total, policy_number)
        company = company or default_company
        try:
            result = forecast.run(
                policy_number, company=company, region=region, engine=engine)
        except Exception as exc:  # a per-policy function should never raise, but
            result = PolicyResult(   # one bad policy must not abort the batch
                policy=policy_number, company=company,
                status=STATUS_ERROR, error=str(exc))
        results.append(result)
    return results


# ── DataFrame flattening (Batch tab grid / Excel export) ────────────────────

def _display_value(value, fmt: Optional[str]):
    """Format one result value for the grid: dates as m/d/yyyy, money 2dp."""
    if value is None:
        return ""
    if isinstance(value, date):
        return f"{value.month}/{value.day}/{value.year}"
    if fmt == FMT_MONEY and isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return value


def results_dataframe(results: Sequence[PolicyResult], forecast: Union[str, ForecastType]):
    """Flatten batch results into a display-ready pandas DataFrame.

    Policies as rows; columns are Policy / Company / Status / Error followed by
    the forecast's output columns (skipping the duplicate Run Status column —
    Status already carries it). Errors are loud: the Error column holds the
    full per-policy failure text.
    """
    import pandas as pd

    if isinstance(forecast, str):
        forecast = FORECAST_TYPES[forecast]

    rows = []
    for result in results:
        row = {
            "Policy": result.policy,
            "Company": result.company or "",
            "Status": result.status,
            "Error": result.error or "",
        }
        for key, label in forecast.columns:
            if key == "run_status":
                continue        # Status column already carries it
            row[label] = _display_value(
                result.values.get(key), forecast.formats.get(key))
        rows.append(row)

    columns = ["Policy", "Company", "Status", "Error"] + [
        label for key, label in forecast.columns if key != "run_status"]
    return pd.DataFrame(rows, columns=columns)
