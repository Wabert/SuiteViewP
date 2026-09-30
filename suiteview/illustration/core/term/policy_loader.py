"""Build the indeterminate premium term snapshot (``TermPolicy``) through PolicyInformation.

Every fact comes from a named PolicyInformation section. CyberLife keeps the premium
rate for the current renewal period on the coverage (``ANN_PRM_UNT_AMT``) and the rate
for the next period on the renewal rates segment (67, ``LH_COV_INS_RNL_RT`` type C,
CyberDoc D20 "the renewal rates carried in this segment apply to the next renewal
period"). ``RNL_RT`` is stored in cents per unit: D0194819's 13063 is B15TG100's
schema ``PREM`` scale C 130.63 at duration 11.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from suiteview.illustration.core.parwl.policy_loader import benefit_name, plan_name
from suiteview.illustration.models.term import (
    ROLE_BASE,
    ROLE_RIDER,
    TermBenefit,
    TermCoverage,
    TermExtra,
    TermPolicy,
)
from suiteview.polview.models.schema_rates import rates_sex

TERM_PRODUCT_LINE = "N"


class TermPolicyError(ValueError):
    """The policy cannot be illustrated as indeterminate premium term (explains why)."""


def _float(value, default: float = 0.0) -> float:
    return float(value) if value is not None else default


def _optional(value) -> Optional[float]:
    return float(value) if value is not None else None


def is_indeterminate_term(pi) -> bool:
    """A traditional term policy with indeterminate premiums (``IDT_PRM_IND = 1``)."""
    if pi.product.is_advanced_product:
        return False
    if str(pi.field_value("identified_premium_indicator") or "").strip() != "1":
        return False
    base = pi.coverages.get_base_coverage()
    if base is None:
        return False
    return pi.coverages.traditional_facts(base.cov_pha_nbr).product_line_code == TERM_PRODUCT_LINE


def _renewal_rate(pi, phase: int) -> Optional[float]:
    for row in pi.rates.get_coverage_renewal_rates(phase):
        if row.rate_type == "C" and str(row.joint_indicator or "0").strip() in ("", "0"):
            value = row.raw_data.get("RNL_RT")
            return round(float(value) / 100.0, 2) if value is not None else None
    return None


def _extras(pi, phase: int, valuation_date: date) -> tuple:
    extras = []
    for rating in pi.coverages.get_substandard_ratings(phase):
        raw = rating.raw_data or {}
        cease = rating.flat_cease_date
        if cease is not None and cease <= valuation_date:
            continue
        extras.append(TermExtra(
            type_code=str(raw.get("SST_XTR_TYP_CD", "") or "").strip(),
            per_unit=_optional(rating.extra_premium_per_unit),
            percent=_optional(rating.extra_percent),
            table_code=str(raw.get("SST_XTR_RT_TBL_CD", "") or "").strip(),
            cease_date=cease,
        ))
    return tuple(extras)


def _coverages(pi, valuation_date: date) -> List[TermCoverage]:
    coverages: List[TermCoverage] = []
    base_phase = pi.coverages.get_base_coverage().cov_pha_nbr
    for index, cov in enumerate(pi.coverages.get_coverages(), start=1):
        if cov.maturity_date is not None and cov.maturity_date <= valuation_date and cov.cov_pha_nbr != base_phase:
            continue
        facts = pi.coverages.traditional_facts(cov.cov_pha_nbr)
        if facts.cease_reason_code and cov.cov_pha_nbr != base_phase:
            continue
        if cov.issue_date is None or cov.issue_age is None:
            raise TermPolicyError(f"Coverage {cov.cov_pha_nbr} has no issue date or issue age.")
        coverages.append(TermCoverage(
            phase=cov.cov_pha_nbr,
            plancode=cov.plancode,
            role=ROLE_BASE if cov.cov_pha_nbr == base_phase else ROLE_RIDER,
            form_number=str(cov.form_number or "").strip(),
            description=plan_name(cov.plancode),
            product_line=facts.product_line_code,
            issue_date=cov.issue_date,
            issue_age=int(cov.issue_age),
            rate_sex=rates_sex(pi.rates.cov_rate_sex_code(index)),
            sex_description=str(cov.sex_desc or "").strip(),
            rate_class=str(cov.rate_class or "").strip().upper(),
            band_code=facts.rate_band_code,
            units=_float(cov.units),
            value_per_unit=_float(cov.vpu, 1000.0),
            annual_premium_per_unit=_float(cov.annual_premium_per_unit),
            pay_up_date=facts.pay_up_date,
            maturity_date=cov.maturity_date,
            renewable_code=facts.renewable_premium_code,
            initial_renewal_period=int(facts.initial_renewal_period or 0),
            renewal_start_duration=int(facts.renewal_start_duration or 0),
            renewal_period=int(facts.renewal_period or 0),
            guaranteed_period_months=int(facts.indeterminate_guaranteed_months or 0),
            table_rating=int(cov.table_rating or 0),
            extras=_extras(pi, cov.cov_pha_nbr, valuation_date),
            next_renewal_rate=_renewal_rate(pi, cov.cov_pha_nbr),
            next_change_date=cov.nxt_chg_dt,
        ))
    return coverages


def _benefits(pi, valuation_date: date) -> List[TermBenefit]:
    benefits = []
    for ben in pi.benefits.get_benefits():
        if ben.cease_date is not None and ben.cease_date <= valuation_date:
            continue
        benefits.append(TermBenefit(
            phase=ben.cov_pha_nbr,
            code=ben.benefit_code,
            type_code=str(ben.benefit_type_cd or "").strip(),
            description=benefit_name(ben.benefit_code) or ben.benefit_desc,
            form_number=str(ben.form_number or "").strip(),
            units=_float(ben.units),
            value_per_unit=_float(ben.vpu, 1000.0),
            annual_premium_per_unit=_float(ben.coi_rate),
            rate_factor=_float(ben.rating_factor, 1.0) or 1.0,
            issue_date=ben.issue_date,
            issue_age=ben.issue_age,
            cease_date=ben.cease_date,
            pay_up_date=ben.pay_up_date,
            renews=str(ben.renewal_indicator or "").strip() == "1",
            renewal_rate=_optional(ben.renewal_rate),
        ))
    return benefits


def build_term_policy(pi, region: str = "CKPR") -> TermPolicy:
    """The in-force indeterminate premium term snapshot of a loaded PolicyInformation."""
    if not pi.exists:
        raise TermPolicyError(f"Policy {pi.policy_number} was not found.")
    if not is_indeterminate_term(pi):
        raise TermPolicyError("The policy is not an indeterminate premium term policy.")
    base_info = pi.coverages.get_base_coverage()
    last_anniversary = pi.activity.last_anniversary
    valuation_date = pi.values.valuation_date or last_anniversary
    if last_anniversary is None or valuation_date is None:
        raise TermPolicyError("The policy has no last anniversary (LST_ANV_DT) to value from.")
    valuation_date = max(valuation_date, last_anniversary)
    forced_code = str(pi.field_value("forced_premium_indicator") or "").strip()
    notes = []
    if forced_code not in ("", "0"):
        notes.append(f"Forced premium indicator {forced_code}: the billed premium is kept as billed.")
    return TermPolicy(
        policy_number=pi.policy_number,
        company_code=pi.company_code,
        region=region,
        insured_name=pi.persons.primary_insured_name,
        issue_state=str(pi.product.issue_state or "").strip().upper(),
        issue_date=base_info.issue_date,
        valuation_date=valuation_date,
        last_anniversary=last_anniversary,
        paid_to_date=pi.activity.paid_to_date,
        billing_frequency=int(pi.billing.billing_frequency or 12),
        bill_form=pi.billing.bill_form_code,
        modal_premium=_float(pi.billing.modal_premium),
        forced_premium=forced_code not in ("", "0"),
        premium_status=pi.status.premium_pay_status_code,
        premium_status_description=pi.status.premium_pay_status_description,
        indeterminate=True,
        coverages=tuple(_coverages(pi, valuation_date)),
        benefits=tuple(_benefits(pi, valuation_date)),
        notes=tuple(notes),
    )
