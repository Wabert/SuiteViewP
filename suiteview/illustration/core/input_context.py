"""Policy-derived context for Illustration input widgets and compilers.

The dynamic input rows need a compact, read-only view of the loaded policy:
forecast year/age, guideline room, plancode rates, tax-test flags and IUL
allocation defaults.  Keeping that derivation in core prevents Run, Compare and
saved-case paths from rebuilding domain assumptions inside widgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta

from suiteview.core.joint_survivor_coi import JointRules
from suiteview.illustration.core.target_premium import floor_monthly_cent
from suiteview.illustration.core.ul_rates import ULRates
from suiteview.illustration.models.index_strategies import is_iul_plan
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.polview.models.policy_sections.lookup import policy_attr

MODE_INTERVALS = {"M": 1, "Q": 3, "S": 6, "A": 12}


def _first_float(source, *names: str) -> float:
    for name in names:
        value = policy_attr(source, name, None)
        if value is not None:
            return float(value or 0.0)
    return 0.0


@dataclass(frozen=True)
class _PolicyTiming:
    issue_date: Optional[date]
    issue_age: int
    valuation_date: Optional[date]
    forecast_date: Optional[date]
    forecast_year: int
    maturity_age: int
    attained_age: int


@dataclass
class PolicyContext:
    """Everything dynamic input rows need to default and bound themselves."""

    issue_date: Optional[date] = None
    issue_age: int = 0
    forecast_year: int = 1
    forecast_age: int = 0
    maturity_age: int = 121
    default_mode: str = "M"
    modal_premium: float = 0.0
    form_number: str = ""
    max_level_premium_room: float = 0.0
    max_level_years: int = 0
    is_cvat: bool = False
    in_exception_period: bool = False
    has_loans: bool = False
    has_shadow: bool = False
    shadow_ceased: bool = False
    rate_class: str = ""
    table_rating: int = 0
    illustrated_rate: float = 0.0
    plancode: str = ""
    is_iul: bool = False
    gint: float = 0.0
    premium_allocations: Optional[dict] = None
    sweep_account_min: float = 0.0
    suspended: bool = False
    valuation_date: Optional[date] = None
    index_illustration_rates: Optional[dict] = None
    index_strategy_parameters: Optional[dict] = None
    forecast_date: Optional[date] = None
    # Joint survivor policies: rate class / table changes name the insured.
    # ((person, "Primary"/"Joint", Insured) ...), the plan's JS_Q rate classes
    # and its JS_TABLE_PCT (code, multiplier) pairs ("0" = standard).
    joint_insureds: tuple = ()
    joint_rate_classes: tuple = ()
    joint_table_codes: tuple = ()

    @property
    def is_joint(self) -> bool:
        return bool(self.joint_insureds)

    @property
    def is_spl87(self) -> bool:
        return self.form_number.strip().upper().startswith("SPL87")

    @property
    def billable_premium(self) -> float:
        return 0.0 if self.is_spl87 else self.modal_premium

    @property
    def maturity_year(self) -> int:
        return max(1, self.maturity_age - self.issue_age)

    def age_for_year(self, year: int) -> int:
        return self.issue_age + year - 1

    def year_for_age(self, age: int) -> int:
        return age - self.issue_age + 1

    def anniversary(self, year: int) -> Optional[date]:
        if self.issue_date is None:
            return None
        return self.issue_date + relativedelta(years=year - 1)

    def effective_date(self, year: int) -> Optional[date]:
        """Return the projected effective date for a policy-year request."""

        when = self.anniversary(year)
        if (
            self.forecast_date is not None
            and when is not None
            and when < self.forecast_date
        ):
            return self.forecast_date
        return when

    def _forecast_months_since_issue(self) -> Optional[int]:
        if self.issue_date is None or self.forecast_date is None:
            return None
        months = (
            (self.forecast_date.year - self.issue_date.year) * 12
            + (self.forecast_date.month - self.issue_date.month)
        )
        if self.forecast_date.day < self.issue_date.day:
            months -= 1
        return months

    def payment_count(self, mode: str) -> int:
        """Modal payments from forecast month to min(maturity, age 100)."""

        interval = MODE_INTERVALS.get(mode, 12)
        freq = 12 // interval
        whole_year_payments = max(0, self.max_level_years) * freq
        n_forecast = self._forecast_months_since_issue()
        if n_forecast is None:
            return whole_year_payments
        forecast_month = n_forecast % 12 + 1
        remaining_this_year = sum(
            1 for month in range(forecast_month, 13) if (month - 1) % interval == 0
        )
        return whole_year_payments + remaining_this_year

    def max_modal_level_premium(self, mode: str) -> float:
        if self.is_cvat or self.max_level_premium_room <= 0.0:
            return 0.0
        count = self.payment_count(mode)
        if count <= 0:
            return 0.0
        return self.max_level_premium_room / count

    @property
    def max_annual_level_premium(self) -> float:
        return self.max_modal_level_premium("A")


def build_policy_context(policy) -> PolicyContext:
    """Build dynamic-input context from a policy or illustration snapshot."""

    timing = _policy_timing(policy)
    mode = _default_mode(policy)
    table_rating = _table_rating(policy)
    plancode, illustrated_rate, gint = _interest_assumptions(policy)
    is_cvat = _is_cvat(policy)
    max_level_years = max(0, min(timing.maturity_age, 100) - timing.attained_age - 1)
    premium_room = _max_level_premium_room(policy, max_level_years)
    return PolicyContext(
        issue_date=timing.issue_date,
        issue_age=timing.issue_age,
        forecast_year=timing.forecast_year,
        forecast_age=timing.issue_age + timing.forecast_year - 1,
        forecast_date=timing.forecast_date,
        maturity_age=timing.maturity_age,
        default_mode=mode,
        modal_premium=float(policy_attr(policy, "modal_premium", 0.0) or 0.0),
        form_number=str(getattr(policy, "form_number", "")
                        or getattr(policy, "base_form_number", "") or ""),
        max_level_premium_room=premium_room,
        max_level_years=max_level_years,
        is_cvat=is_cvat,
        in_exception_period=bool(getattr(policy, "in_exception_period", False)),
        has_loans=bool(policy_attr(policy, "total_loan_balance", 0) or 0),
        rate_class=str(policy_attr(policy, "base_rate_class", "") or getattr(policy, "rate_class", "") or ""),
        table_rating=table_rating,
        illustrated_rate=illustrated_rate,
        plancode=plancode,
        is_iul=is_iul_plan(plancode),
        gint=gint,
        premium_allocations=_premium_allocations_from_policy(policy),
        sweep_account_min=float(getattr(policy, "sweep_account_min", 0.0) or 0.0),
        suspended=is_suspended(policy),
        valuation_date=timing.valuation_date,
        index_illustration_rates=getattr(policy, "index_illustration_rates", None),
        index_strategy_parameters=getattr(policy, "index_strategy_parameters", None),
        **_joint_change_options(policy, plancode),
    )


def _joint_change_options(policy, plancode: str) -> dict:
    """Both insureds and the plan's JS_Q classes / table codes for a joint policy."""
    base = getattr(policy, "base_segment", None)
    lives = getattr(base, "joint_lives", None)
    if lives is None:
        return {}
    rates_db = ULRates(getattr(policy, "company_code", "") or "")
    company = rates_db.joint_survivor_company(plancode)
    if company is None:
        raise ValueError(
            f"Plan {plancode} carries joint lives but is not a joint survivor plan in "
            "UL_Rates rates.PLAN_ATTR (LIVES=3).")
    rules = JointRules.from_plan_attributes(rates_db.get_plan_attributes(company, plancode))
    return {
        "joint_insureds": (("00", "Primary", lives.primary), ("01", "Joint", lives.joint)),
        "joint_rate_classes": tuple(rates_db.joint_survivor_rate_classes(company, plancode)),
        "joint_table_codes": tuple(rules.table_pct.items()),
    }


def _policy_timing(policy) -> _PolicyTiming:
    issue_date = policy_attr(policy, "issue_date", None) or getattr(policy, "base_issue_date", None)
    issue_age = int(policy_attr(policy, "base_issue_age", None)
                    or getattr(policy, "issue_age", 0) or 0)
    valuation = policy_attr(policy, "valuation_date", None) or getattr(
        policy, "last_valuation_date", None)
    forecast = _forecast_date(policy, issue_date, valuation)
    forecast_year = _forecast_year(policy, issue_date, forecast)
    maturity_age = int(getattr(policy, "maturity_age", None)
                       or policy_attr(policy, "age_at_maturity", None) or 121)
    attained_age = int(policy_attr(policy, "attained_age", None)
                       or (issue_age + forecast_year - 1) or 0)
    return _PolicyTiming(
        issue_date=issue_date,
        issue_age=issue_age,
        valuation_date=valuation,
        forecast_date=forecast,
        forecast_year=forecast_year,
        maturity_age=maturity_age,
        attained_age=attained_age,
    )


def _forecast_date(policy, issue_date: Optional[date], valuation: Optional[date]) -> Optional[date]:
    duration = int(getattr(policy, "duration", 0) or 0)
    if getattr(policy, "run_from_issue", False):
        return issue_date
    if issue_date is not None and duration > 0:
        return issue_date + relativedelta(months=duration)
    return valuation + relativedelta(months=1) if valuation else None


def _forecast_year(policy, issue_date: Optional[date], forecast: Optional[date]) -> int:
    if issue_date is not None and forecast is not None:
        months = (forecast.year - issue_date.year) * 12 + (forecast.month - issue_date.month)
        if forecast.day < issue_date.day:
            months -= 1
        return max(1, months // 12 + 1)
    return int(policy_attr(policy, "policy_year", 1) or 1)


def _default_mode(policy) -> str:
    frequency = policy_attr(policy, "billing_frequency", 1)
    try:
        frequency = int(frequency)
    except (TypeError, ValueError):
        frequency = 1
    return {3: "Q", 6: "S", 12: "A"}.get(frequency, "M")


def is_suspended(policy) -> bool:
    """Suspense code 2 (LH_BAS_POL.SUS_CD, ``SUSPENSE_CODES``): suspended."""
    return str(policy_attr(policy, "suspense_code", "") or "").strip() == "2"


def _table_rating(policy) -> int:
    table_rating = getattr(policy, "base_table_rating", None)
    if table_rating is None:
        getter = policy_attr(policy, "cov_table_rating", None)
        if callable(getter):
            try:
                table_rating = getter(1)
            except Exception:
                table_rating = 0
    try:
        table_rating = int(table_rating or 0)
    except (TypeError, ValueError):
        table_rating = 0
    return table_rating


def _interest_assumptions(policy) -> tuple[str, float, float]:
    plancode = str(policy_attr(policy, "base_plancode", "")
                   or getattr(policy, "plancode", "") or "")
    illustrated_rate = 0.0
    gint = 0.0
    if plancode:
        gint = load_plancode(plancode).gint
        illustrated_rate = gint
    if getattr(policy, "current_interest_rate_source", "") and getattr(policy, "current_interest_rate", None):
        # A declared current rate the policy loader sourced (CIRF) is the default
        # illustrated rate; without one the plan GINT stays the default.
        illustrated_rate = float(policy.current_interest_rate)
    if illustrated_rate == 0.0:
        illustrated_rate = float(
            getattr(policy, "current_interest_rate", None)
            or policy_attr(policy, "guaranteed_interest_rate", 0.0)
            or 0.0
        )
        if illustrated_rate > 1.0:
            illustrated_rate /= 100.0
    if getattr(policy, "run_from_issue", False):
        illustrated_rate = float(policy.current_interest_rate)
    return plancode, illustrated_rate, gint


def _is_cvat(policy) -> bool:
    def_of_life_ins = str(
        getattr(policy, "def_of_life_ins", "")
        or getattr(policy, "def_of_life_insurance", "")
        or getattr(policy, "definition_of_life_insurance", "")
        or "GPT"
    ).upper()
    return def_of_life_ins == "CVAT"


def _max_level_premium_room(policy, max_level_years: int) -> float:
    glp = floor_monthly_cent(_first_float(policy, "glp"))
    accumulated_glp = _first_float(policy, "accumulated_glp", "accumulated_glp_target")
    premiums_paid_to_date = _first_float(
        policy, "premiums_paid_to_date", "premium_td", "total_premiums_paid")
    withdrawals_to_date = _first_float(policy, "withdrawals_to_date", "total_withdrawals")
    total_accumulated_glp_at_limit_age = accumulated_glp + (max_level_years * glp)
    return max(
        0.0,
        total_accumulated_glp_at_limit_age
        - (premiums_paid_to_date - withdrawals_to_date),
    )


def _premium_allocations_from_policy(policy) -> Optional[dict]:
    direct = getattr(policy, "premium_allocations", None)
    if direct:
        return dict(direct)
    getter = policy_attr(policy, "get_premium_allocation_dict", None)
    if callable(getter):
        try:
            allocations = getter()
            return {str(k): float(v) for k, v in allocations.items()} or None
        except Exception:
            return None
    return None
