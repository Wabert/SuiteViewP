"""
ABR Quote — Core service to build ABRPolicyData from CyberLife DB2 records.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

from ...core.policy_service import get_policy_info
from ..models.abr_constants import NON_STANDARD_MODE_MAP
from ..models.abr_data import ABRPolicyData, DBLayer, PremiumResult, RiderInfo

logger = logging.getLogger(__name__)

_FREQ_TO_MODE = {12: 1, 6: 2, 3: 3, 1: 4}


class ABRPolicyLookupError(RuntimeError):
    """Raised when live ABR policy data cannot be read safely."""


@dataclass(frozen=True)
class PremiumScheduleResult:
    """Premium schedule inputs used by ABR APV and premium displays."""

    start_year: int
    effective_policy_month: int
    payments_per_year: int
    remaining_payments: int
    modal_factor: float
    modal_fee_factor: float
    premium_result: PremiumResult
    premium_schedule: List[float] = field(default_factory=list)
    base_annual_schedule: List[float] = field(default_factory=list)
    annual_schedule: List[float] = field(default_factory=list)
    current_modal_premium: float = 0.0
    current_year_premium: float = 0.0


@dataclass(frozen=True)
class PolicyIdentity:
    """Policy identity/duration from PolicyInformation and DB2 policy/coverage rows."""

    policy_number: str
    region: str
    insured_name: str
    issue_age: int
    attained_age: int
    sex: str
    rate_sex: str
    rate_class: str
    face_amount: float
    db_option: str
    issue_date: date | None
    maturity_age: int
    maturity_date: date | None
    issue_state: str
    plan_code: str
    product_type: str
    base_plancode: str
    billing_mode: int
    policy_month: int
    policy_year: int
    paid_to_date: date | None
    modal_premium: float
    annual_premium: float


@dataclass(frozen=True)
class PolicySubstandard:
    """Base-coverage substandard ratings from PolicyInformation substandard rows."""

    table_rating: int = 0
    table_rating_2: int = 0
    flat_extra: float = 0.0
    flat_to_age: int = 0
    flat_cease_date: date | None = None


@dataclass(frozen=True)
class RidersAndLayers:
    """Riders/benefits from coverages/benefits plus primary-insured DB layers."""

    riders: List[RiderInfo]
    rider_annual_premium: float
    db_layers: List[DBLayer]
    issue_date: date | None


@dataclass(frozen=True)
class PolicyValues:
    """UL/IUL/ISWL value basis from monthliversary and policy total fields."""

    account_value: float
    surrender_value: float
    premiums_paid_to_date: float
    valuation_date: date | None
    monthly_deduction: float


def _months_since_issue(issue_date: Optional[date], target: Optional[date]) -> Optional[int]:
    """Whole policy months from issue to ``target`` (absolute policy month scale)."""
    if not issue_date or not target:
        return None
    months = (target.year - issue_date.year) * 12 + (target.month - issue_date.month)
    if target.day < issue_date.day:
        months -= 1
    return months


def find_policy_companies(policy_num: str, region: str = "CKPR") -> List[str]:
    """Return CyberLife company codes holding this policy via PolicyInformation."""
    pi = get_policy_info(
        policy_num,
        company_code=None,
        region=region,
        include_unresolved=True,
    )
    if pi is None:
        return []
    if pi.exists:
        co = str(pi.data_item("LH_BAS_POL", "CK_CMP_CD") or "").strip()
        return [co] if co else []
    if pi.available_companies:
        return pi.available_companies
    return []


def _read_surrender_value(pi):
    # CKPR UL monthliversary rows are in LH_POL_MVRY_VAL. The generic
    # cash_surrender_value accessor first probes an undefined TH table.
    value = pi.data_item("LH_POL_MVRY_VAL", "CSV_AMT")
    return value if value is not None else pi.cash_surrender_value


def _billing_mode(pi) -> int:
    nsd_code = pi.non_standard_mode_code
    if nsd_code and nsd_code in NON_STANDARD_MODE_MAP:
        return NON_STANDARD_MODE_MAP[nsd_code]
    freq = pi.billing_frequency or 12
    billing_mode = _FREQ_TO_MODE.get(freq, 1)
    if freq == 1 and pi.is_eft:
        billing_mode = 5
    return billing_mode


def _sex_from_code(raw_sex: str) -> str:
    return {"1": "M", "2": "F", "3": "U"}.get(raw_sex, raw_sex)


def _rate_sex(pi, fallback: str) -> str:
    raw_rate_sex = pi.renewal_cov_sex_code(1)
    return {"1": "M", "2": "F"}.get(raw_rate_sex, raw_rate_sex) or fallback


def _base_maturity_date(policy_num: str, pi) -> date | None:
    try:
        base_covs = pi.get_base_coverages()
    except (AttributeError, LookupError, RuntimeError, ValueError) as exc:
        raise ABRPolicyLookupError(
            f"Base coverage lookup failed for {policy_num}"
        ) from exc
    return base_covs[0].maturity_date if base_covs else None


def _base_plancode_from_data_item(pi) -> str:
    return str(pi.data_item("LH_COV_PHA", "PLN_BSE_SRE_CD") or "").strip()


def extract_policy_identity(policy_num: str, region: str, pi) -> PolicyIdentity:
    """Extract identity/duration fields from PolicyInformation.

    Sources: LH_BAS_POL for billing/status/date/state fields, base LH_COV_PHA
    for demographics/plan/face, LH_COV_INS_RNL_RT for rate sex, and the
    canonical PolicyInformation properties that wrap those DB2 rows.
    """
    sex = _sex_from_code(pi.base_sex_code or "")
    return PolicyIdentity(
        policy_number=policy_num,
        region=region,
        insured_name=pi.primary_insured_name or "",
        issue_age=int(pi.base_issue_age or 0),
        attained_age=int(pi.attained_age or 0),
        sex=sex,
        rate_sex=_rate_sex(pi, sex),
        rate_class=pi.base_rate_class or "N",
        face_amount=float(pi.primary_insured_face_amount or 0),
        db_option=pi.db_option_code or "",
        issue_date=pi.issue_date,
        maturity_age=pi.age_at_maturity or 95,
        maturity_date=_base_maturity_date(policy_num, pi),
        issue_state=pi.issue_state or pi.issue_state_code or "",
        plan_code=pi.base_plancode or "",
        product_type=pi.product_type or "",
        base_plancode=_base_plancode_from_data_item(pi),
        billing_mode=_billing_mode(pi),
        policy_month=pi.policy_month or 1,
        policy_year=pi.policy_year or 1,
        paid_to_date=pi.paid_to_date,
        modal_premium=float(pi.modal_premium or 0),
        annual_premium=float(pi.annual_premium or 0),
    )


def extract_policy_substandard(policy_num: str, pi) -> PolicySubstandard:
    """Extract base-coverage ratings from PolicyInformation substandard rows.

    Source: LH_SST_XTR_CRG through ``get_substandard_ratings(1)``.
    """
    try:
        ratings = pi.get_substandard_ratings(1)
    except (AttributeError, LookupError, RuntimeError, ValueError) as exc:
        raise ABRPolicyLookupError(
            f"Substandard rating lookup failed for {policy_num}"
        ) from exc
    table_numeric = 0
    table_numeric_2 = 0
    flat_extra = 0.0
    flat_to_age = 0
    flat_cease_date = None
    for rating in ratings:
        if rating.type_code == "T":
            value = rating.table_rating_numeric or 0
            if not table_numeric:
                table_numeric = value
            elif not table_numeric_2:
                table_numeric_2 = value
        if rating.type_code == "F":
            flat_extra = float(rating.flat_amount or 0)
            flat_cease_date = rating.flat_cease_date
            if flat_cease_date and pi.issue_date and pi.base_issue_age is not None:
                flat_to_age = pi.base_issue_age + (
                    flat_cease_date.year - pi.issue_date.year
                )
    return PolicySubstandard(
        table_rating=table_numeric,
        table_rating_2=table_numeric_2,
        flat_extra=flat_extra,
        flat_to_age=flat_to_age,
        flat_cease_date=flat_cease_date,
    )


def _make_benefit_rider(cov, ben, cov_sex_mapped: str, cov_rc_str: str) -> RiderInfo:
    pc = (cov.plancode or "").upper()
    cov_face = float(cov.face_amount or 0)
    cov_issue_age = int(cov.issue_age or 0)
    ben_type = (ben.benefit_type_cd or "").strip()
    ben_sub = (ben.benefit_subtype_cd or "").strip()
    ben_face = float(ben.benefit_amount or 0) or cov_face
    fallback = 0.0
    if ben.coi_rate is not None and ben.units:
        fallback = float(ben.coi_rate) * float(ben.units)
    return RiderInfo(
        plancode=pc,
        face_amount=ben_face,
        issue_age=int(ben.issue_age or cov_issue_age or 0),
        sex=cov_sex_mapped,
        rate_class=cov_rc_str,
        table_rating=int(cov.table_rating or 0),
        rider_type="BENEFIT",
        fallback_premium=fallback,
        benefit_type=ben_type,
        benefit_subtype=ben_sub,
        benefit_units=float(ben.units or 0),
        benefit_vpu=float(ben.vpu or 0),
        benefit_rating_factor=float(ben.rating_factor) if ben.rating_factor else 0.0,
        cease_date=ben.cease_date,
    )


def _coverage_rider(cov, sex: str, base_rate_class: str) -> tuple[RiderInfo | None, float]:
    if cov.is_base:
        return None, 0.0
    cov_rc = (cov.rate_class or "0").strip()
    cov_sex = {"1": "M", "2": "F"}.get(cov.sex_code, cov.sex_code or sex)
    if cov_rc == "0":
        cov_rc = base_rate_class or "N"
    annual = cov.cov_annual_premium
    if annual is None and cov.premium_rate and cov.units:
        annual = cov.premium_rate * cov.units
    fallback = float(annual) if annual else 0.0
    rider = RiderInfo(
        plancode=(cov.plancode or "").upper(),
        face_amount=float(cov.face_amount or 0),
        issue_age=int(cov.issue_age or 0),
        sex=cov_sex,
        rate_class=cov_rc,
        table_rating=int(cov.table_rating or 0),
        rider_type="CTR" if cov.person_code == "50" else "COVERAGE",
        fallback_premium=fallback,
    )
    return rider, fallback


def extract_riders_and_layers(
    policy_num: str,
    pi,
    identity: PolicyIdentity,
    as_of_date: date,
) -> RidersAndLayers:
    """Extract premium riders, benefits and primary-insured death-benefit layers.

    Sources: PolicyInformation ``get_coverages()``, ``get_benefits()`` and
    ``primary_insured_db_layers`` (LH_COV_PHA/LH_SPM_BNF-derived records).
    Benefit cease-date filtering is evaluated at the boundary-supplied
    ``as_of_date`` so tests and quote retrieval are clock-independent.
    """
    try:
        coverages = pi.get_coverages()
        all_benefits = pi.get_benefits()
    except (AttributeError, LookupError, RuntimeError, ValueError) as exc:
        raise ABRPolicyLookupError(
            f"Coverage/benefit lookup failed for {policy_num}"
        ) from exc
    issue_date = identity.issue_date or (coverages[0].issue_date if coverages else None)
    riders: List[RiderInfo] = []
    rider_annual = 0.0
    for cov in coverages:
        rider, annual = _coverage_rider(cov, identity.sex, identity.rate_class)
        if rider:
            riders.append(rider)
            rider_annual += annual
        cov_sex = {"1": "M", "2": "F"}.get(cov.sex_code, cov.sex_code or identity.sex)
        cov_rc = (cov.rate_class or "0").strip()
        if cov_rc == "0" and cov.is_base:
            cov_rc = identity.rate_class
        for benefit in (b for b in all_benefits if b.cov_pha_nbr == cov.cov_pha_nbr):
            if benefit.cease_date and benefit.cease_date < as_of_date:
                continue
            if (benefit.benefit_type_cd or "").strip() == "#":
                continue
            riders.append(_make_benefit_rider(cov, benefit, cov_sex, cov_rc))
    db_layers: List[DBLayer] = []
    try:
        layer_rows = pi.primary_insured_db_layers
    except (AttributeError, LookupError, RuntimeError, ValueError) as exc:
        raise ABRPolicyLookupError(
            f"Death-benefit layer lookup failed for {policy_num}"
        ) from exc
    for face, expiry in layer_rows:
        db_layers.append(
            DBLayer(
                face_amount=float(face or 0),
                expiry_month=_months_since_issue(issue_date, expiry),
            )
        )
    return RidersAndLayers(riders, rider_annual, db_layers, issue_date)


def extract_policy_values(policy_num: str, pi) -> PolicyValues:
    """Extract value basis fields from PolicyInformation.

    Sources: LH_POL_MVRY_VAL for account/surrender values and valuation date,
    LH_POL_TOTALS-derived premium totals, and the monthliversary deduction row.
    """
    try:
        mv_account_value = pi.mv_av(0)
    except (AttributeError, LookupError, RuntimeError, ValueError) as exc:
        raise ABRPolicyLookupError(
            f"Account value lookup failed for {policy_num}"
        ) from exc
    account_value = (
        float(mv_account_value)
        if mv_account_value is not None
        else float(pi.accumulation_value or 0)
    )
    try:
        surrender_value = float(_read_surrender_value(pi) or 0)
    except (AttributeError, LookupError, RuntimeError, ValueError) as exc:
        raise ABRPolicyLookupError(
            f"Surrender value lookup failed for {policy_num}"
        ) from exc
    try:
        mv_date = pi.mv_date(0)
    except (AttributeError, LookupError, RuntimeError, ValueError) as exc:
        raise ABRPolicyLookupError(
            f"Valuation date lookup failed for {policy_num}"
        ) from exc
    valuation_date = mv_date if mv_date and mv_date.year < 9999 else pi.valuation_date
    return PolicyValues(
        account_value=account_value,
        surrender_value=surrender_value,
        premiums_paid_to_date=float(pi.total_premiums_paid or 0),
        valuation_date=valuation_date,
        monthly_deduction=float(pi.mv_monthly_deduction() or 0),
    )


def _duration_at_quote(policy: ABRPolicyData, quote_date: date) -> tuple[int, int]:
    if policy.issue_date:
        anniv_month = policy.issue_date.month
        anniv_day = policy.issue_date.day
        years_since_issue = quote_date.year - policy.issue_date.year
        if (quote_date.month, quote_date.day) < (anniv_month, anniv_day):
            years_since_issue -= 1
        start_year = max(years_since_issue + 1, 1)
        anniv_year = policy.issue_date.year + years_since_issue
        months_elapsed = (
            (quote_date.year - anniv_year) * 12
            + quote_date.month - anniv_month
        )
        if quote_date.day < anniv_day:
            months_elapsed -= 1
        effective_policy_month = max(months_elapsed + 1, 1)
    else:
        effective_policy_month = policy.policy_month
        start_year = max(policy.policy_year, 1)
    return start_year, effective_policy_month


def premium_schedule_for_quote(
    policy: ABRPolicyData,
    quote_date: date,
    level_annual_premium: float | None = None,
    *,
    use_arithmetic_modal_rounding: bool = False,
) -> PremiumScheduleResult:
    """Build the APV premium schedule for a quote date."""
    from .premium_calc import PremiumCalculator, arithmetic_round
    from ..models.abr_database import get_abr_database

    db = get_abr_database()
    calc = PremiumCalculator(policy)
    start_year, effective_policy_month = _duration_at_quote(policy, quote_date)
    prem_result = calc.compute(policy_year=start_year)
    is_ul = policy.product_type in ("UL", "IUL", "ISWL")
    if is_ul:
        max_duration = (
            policy.maturity_age - policy.issue_age
            if policy.maturity_age and policy.issue_age else 0
        )
        premium_schedule = [0.0] * max(max_duration, 0)
        for year_index in range(start_year - 1, len(premium_schedule)):
            premium_schedule[year_index] = float(level_annual_premium or 0.0)
        if start_year - 1 < len(premium_schedule):
            premium_schedule[start_year - 1] = 0.0
        annual_schedule: List[float] = []
        base_annual_schedule: List[float] = []
    else:
        base_annual_schedule = calc.get_base_annual_premium_schedule()
        annual_schedule = calc.get_annual_premium_schedule()
        premium_schedule = list(base_annual_schedule)
    payments_per_year = {1: 1, 2: 2, 3: 4, 4: 12, 5: 12}.get(
        policy.billing_mode, 12
    )
    months_per_payment = 12 // payments_per_year
    modal_factor = db.get_modal_factor(policy.plan_code, policy.billing_mode)
    modal_fee_factor = db.get_modal_fee_factor(policy.plan_code, policy.billing_mode)
    payments_made = (effective_policy_month - 1) // months_per_payment + 1
    remaining_payments = max(payments_per_year - payments_made, 0)
    year_index = start_year - 1
    current_year_premium = (
        premium_schedule[year_index] if year_index < len(premium_schedule) else 0.0
    )
    if not is_ul and year_index < len(premium_schedule) and remaining_payments < payments_per_year:
        modal_amount = premium_schedule[year_index] * modal_factor
        modal_total = (
            arithmetic_round(modal_amount, 2)
            if use_arithmetic_modal_rounding
            else round(modal_amount, 2)
        )
        premium_schedule[year_index] = modal_total * remaining_payments
    return PremiumScheduleResult(
        start_year=start_year,
        effective_policy_month=effective_policy_month,
        payments_per_year=payments_per_year,
        remaining_payments=remaining_payments,
        modal_factor=modal_factor,
        modal_fee_factor=modal_fee_factor,
        premium_result=prem_result,
        premium_schedule=premium_schedule,
        base_annual_schedule=base_annual_schedule,
        annual_schedule=annual_schedule,
        current_modal_premium=prem_result.modal_premium,
        current_year_premium=current_year_premium,
    )


def build_abr_policy(
    policy_num: str,
    region: str,
    company_code: Optional[str] = None,
    *,
    use_cache: bool = True,
    as_of_date: date,
) -> Tuple[Optional[ABRPolicyData], Optional[object]]:
    """Fetch CyberLife policy data and assemble an ABRPolicyData object."""
    pi = get_policy_info(
        policy_num,
        region=region,
        company_code=company_code,
        use_cache=use_cache,
    )
    if pi is None:
        raise ABRPolicyLookupError(f"Policy {policy_num} not found in {region}")
    identity = extract_policy_identity(policy_num, region, pi)
    substandard = extract_policy_substandard(policy_num, pi)
    riders = extract_riders_and_layers(policy_num, pi, identity, as_of_date)
    values = extract_policy_values(policy_num, pi)
    policy = ABRPolicyData(
        policy_number=identity.policy_number,
        region=identity.region,
        insured_name=identity.insured_name,
        issue_age=identity.issue_age,
        attained_age=identity.attained_age,
        sex=identity.sex,
        rate_sex=identity.rate_sex,
        rate_class=identity.rate_class,
        face_amount=identity.face_amount,
        db_option=identity.db_option,
        account_value=values.account_value,
        surrender_value=values.surrender_value,
        premiums_paid_to_date=values.premiums_paid_to_date,
        valuation_date=values.valuation_date,
        issue_date=riders.issue_date,
        maturity_age=identity.maturity_age,
        maturity_date=identity.maturity_date,
        issue_state=identity.issue_state,
        plan_code=identity.plan_code,
        product_type=identity.product_type,
        base_plancode=identity.base_plancode,
        billing_mode=identity.billing_mode,
        policy_month=identity.policy_month,
        policy_year=identity.policy_year,
        table_rating=substandard.table_rating,
        table_rating_2=substandard.table_rating_2,
        flat_extra=substandard.flat_extra,
        flat_to_age=substandard.flat_to_age,
        flat_cease_date=substandard.flat_cease_date,
        paid_to_date=identity.paid_to_date,
        modal_premium=identity.modal_premium,
        annual_premium=identity.annual_premium,
        rider_annual_premium=riders.rider_annual_premium,
        riders=riders.riders,
        db_layers=riders.db_layers,
        monthly_deduction=values.monthly_deduction,
    )
    return policy, pi
