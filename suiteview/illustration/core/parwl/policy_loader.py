"""Build the par WL in-force snapshot (``ParWLPolicy``) through PolicyInformation.

Every fact comes from a named PolicyInformation section; the snapshot is plain frozen
data so an illustration can be rerun, saved or tested without DB2.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from suiteview.illustration.models.parwl import (
    ROLE_BASE,
    ROLE_PUA_RIDER,
    ROLE_TERM_RIDER,
    ParWLAdditions,
    ParWLBenefit,
    ParWLCoverage,
    ParWLDividendValue,
    ParWLLoan,
    ParWLPolicy,
)
from suiteview.polview.data import lookup as reference_lookup
from suiteview.polview.models.policy_sections.dividends import DividendsSection
from suiteview.polview.models.schema_rates import rates_sex

PUA_RIDER_PRODUCT_LINE = "C"
BLENDED_RIDER_PRODUCT_LINE = "B"


class ParWLPolicyError(ValueError):
    """The policy cannot be illustrated as par whole life (explains why)."""


def _float(value, default: float = 0.0) -> float:
    return float(value) if value is not None else default


def _rate(value) -> Optional[float]:
    return float(value) / 100.0 if value is not None else None


def plan_name(plancode: str) -> str:
    """The plancode's common name from the official plancode table ("" when not listed)."""
    entry = reference_lookup.get_plancode_entry(plancode)
    return str(entry.get("common_name") or "").strip() if entry else ""


def benefit_name(code: str) -> str:
    """The supplemental benefit's description by type + subtype ("" when not listed)."""
    entry = reference_lookup.get_benefit_by_code(code)
    return str(entry.get("description") or "").strip() if entry else ""


def is_par_whole_life(pi) -> bool:
    """A traditional (fixed-value) policy whose base coverage participates in dividends."""
    if pi.product.is_advanced_product:
        return False
    base = pi.coverages.get_base_coverage()
    if base is None:
        return False
    facts = pi.coverages.traditional_facts(base.cov_pha_nbr)
    return facts.dividend_participation_code not in ("", "0") and facts.product_line_code in ("0", "")


def _anniversary_date(day: int, year: Optional[int], month: Optional[int]) -> Optional[date]:
    return DividendsSection.month_year_date(year, month, day)


def _coverages(pi, valuation_date: date) -> List[ParWLCoverage]:
    coverages: List[ParWLCoverage] = []
    for index, cov in enumerate(pi.coverages.get_coverages(), start=1):
        facts = pi.coverages.traditional_facts(cov.cov_pha_nbr)
        if cov.maturity_date is not None and cov.maturity_date <= valuation_date and not cov.is_base:
            continue
        ceased = bool(facts.cease_reason_code) and (cov.nxt_chg_dt is None or cov.nxt_chg_dt <= valuation_date)
        if ceased and not cov.is_base and facts.product_line_code != PUA_RIDER_PRODUCT_LINE:
            continue
        if facts.product_line_code == BLENDED_RIDER_PRODUCT_LINE:
            raise ParWLPolicyError(
                f"Coverage {cov.cov_pha_nbr} ({cov.plancode}) is a blended insurance rider; "
                "blended insurance riders are not illustrated yet.")
        if cov.is_base and cov.cov_pha_nbr == pi.coverages.get_base_coverage().cov_pha_nbr:
            role = ROLE_BASE
        elif facts.product_line_code == PUA_RIDER_PRODUCT_LINE:
            role = ROLE_PUA_RIDER
        elif cov.is_base:
            raise ParWLPolicyError(
                f"Coverage {cov.cov_pha_nbr} repeats the base plancode {cov.plancode}; "
                "par WL policies with more than one base phase are not illustrated.")
        else:
            role = ROLE_TERM_RIDER
        if cov.issue_date is None or cov.issue_age is None:
            raise ParWLPolicyError(f"Coverage {cov.cov_pha_nbr} has no issue date or issue age.")
        coverages.append(ParWLCoverage(
            phase=cov.cov_pha_nbr,
            plancode=cov.plancode,
            role=role,
            product_line=facts.product_line_code,
            issue_date=cov.issue_date,
            issue_age=int(cov.issue_age),
            rate_sex=rates_sex(pi.rates.cov_rate_sex_code(index)),
            rate_class=str(cov.rate_class or "").strip().upper(),
            band_code=facts.rate_band_code,
            subseries=facts.subseries_code,
            units=_float(cov.units),
            value_per_unit=_float(cov.vpu, 1000.0),
            annual_premium_per_unit=_float(cov.annual_premium_per_unit),
            pay_up_date=facts.pay_up_date,
            maturity_date=cov.maturity_date,
            table_rating=int(cov.table_rating or 0),
            extra_premiums=tuple(
                (float(r.extra_premium_per_unit), r.flat_cease_date)
                for r in pi.coverages.get_substandard_ratings(cov.cov_pha_nbr)
                if r.extra_premium_per_unit and (r.flat_cease_date is None or r.flat_cease_date > valuation_date)
            ),
            nsp_table=facts.nsp_rpu_table,
            nsp_interest=_rate(facts.nsp_interest_rate),
            stored_low_duration=facts.stored_low_duration,
            stored_cash_values=tuple(_float(v) if v is not None else None for v in facts.stored_cash_values),
            stored_nsp_values=tuple(_float(v) if v is not None else None for v in facts.stored_nsp_values),
            dividend_key=f"{facts.class_code}{facts.base_series_code}{facts.subseries_code}",
            payments_ceased=ceased and role == ROLE_PUA_RIDER,
            description=plan_name(cov.plancode),
            form_number=str(getattr(cov, "form_number", "") or "").strip(),
            sex_description=str(getattr(cov, "sex_desc", "") or "").strip(),
        ))
    if not any(c.role == ROLE_BASE for c in coverages):
        raise ParWLPolicyError("The policy has no base coverage.")
    return coverages


def _benefits(pi, valuation_date: date) -> List[ParWLBenefit]:
    benefits = []
    for ben in pi.benefits.get_benefits():
        if ben.cease_date is not None and ben.cease_date <= valuation_date:
            continue
        benefits.append(ParWLBenefit(
            phase=ben.cov_pha_nbr,
            code=ben.benefit_code,
            description=benefit_name(ben.benefit_code) or ben.benefit_desc,
            units=_float(ben.units),
            value_per_unit=_float(ben.vpu, 1000.0),
            annual_premium_per_unit=_float(ben.coi_rate),
            rate_factor=_float(ben.rating_factor, 1.0) or 1.0,
            issue_date=ben.issue_date,
            issue_age=ben.issue_age,
            cease_date=ben.cease_date,
            form_number=str(ben.form_number or "").strip(),
            pay_up_date=ben.pay_up_date,
        ))
    return benefits


def _additions(rows, anniversary_day: int) -> List[ParWLAdditions]:
    return [ParWLAdditions(
        phase=row.coverage_phase,
        source=row.purchase_source,
        amount=_float(row.amount),
        mortality_table=row.mortality_table,
        interest=_rate(row.interest_rate) or 0.0,
        maturity_date=_anniversary_date(anniversary_day, row.maturity_year, row.maturity_month),
        nfo_code=row.nfo_code,
    ) for row in rows]


def _rows_at_last_anniversary(pua_rows, last_anniversary: date) -> list:
    """Additions going into the last anniversary: the snapshot taken before its processing,
    or (premium-bought rider additions, which the dividend does not change) the snapshot
    CyberLife keeps at that anniversary."""
    at = [r for r in pua_rows if r.mv_date == last_anniversary]
    before = {(r.coverage_phase, r.purchase_source): r for r in at if r.before_anniversary}
    for row in at:
        before.setdefault((row.coverage_phase, row.purchase_source), row)
    return list(before.values())


def _dividend_values(rows, applied: bool, anniversary_day: int) -> List[ParWLDividendValue]:
    values = []
    for row in rows:
        earn = _anniversary_date(anniversary_day, row.earn_year, row.earn_month)
        if earn is None:
            continue
        values.append(ParWLDividendValue(
            phase=row.coverage_phase,
            earn_date=earn,
            source=row.source,
            applied=applied,
            option=getattr(row, "applied_option", ""),
            cash_per_unit=_float(row.cash_per_unit),
            pua_per_unit=_float(row.pua_per_unit),
            oyt_per_unit=_float(row.oyt_per_unit),
            units=_float(row.units),
            rpu_values=bool(getattr(row, "rpu_values", False)),
            deposit_rate=_rate(getattr(row, "deposit_interest_rate", None)),
            direct_recognition=bool(getattr(row, "direct_recognition", False)),
            gross_interest_rate=_rate(getattr(row, "gross_interest_rate", None)),
        ))
    return values


def build_parwl_policy(pi, region: str = "CKPR") -> ParWLPolicy:
    """The in-force par WL snapshot of a loaded PolicyInformation."""
    if not pi.exists:
        raise ParWLPolicyError(f"Policy {pi.policy_number} was not found.")
    if pi.product.is_advanced_product:
        raise ParWLPolicyError("The policy is an advanced (account value) product, not par whole life.")
    base_info = pi.coverages.get_base_coverage()
    if base_info is None or base_info.issue_date is None:
        raise ParWLPolicyError("The policy has no base coverage issue date.")
    last_anniversary = pi.activity.last_anniversary
    valuation_date = pi.values.valuation_date or last_anniversary
    if last_anniversary is None or valuation_date is None:
        raise ParWLPolicyError("The policy has no last anniversary (LST_ANV_DT) to value from.")
    if valuation_date < last_anniversary:
        valuation_date = last_anniversary
    day = base_info.issue_date.day
    dividends = pi.dividends
    pua_rows = dividends.get_div_pua()
    oyts = dividends.current_oyts()
    deposits = dividends.current_deposits()
    unapplied = dividends.get_unapplied_dividends()
    deposit_rate = next((_rate(d.interest_rate) for d in deposits if d.interest_rate is not None), None)
    if deposit_rate is None:
        deposit_rate = next((_rate(u.deposit_interest_rate) for u in unapplied
                             if u.deposit_interest_rate is not None), None)
    oyt_expiry = None
    if oyts:
        first = oyts[0]
        oyt_expiry = _anniversary_date(day, first.expiry_year, first.expiry_month)
    loans = tuple(ParWLLoan(
        principal=_float(loan.principal),
        interest_amount=_float(loan.accrued_interest),
        rate=_rate(loan.interest_rate) or 0.0,
        in_advance=loan.interest_in_advance,
        capitalized=str(loan.interest_type).strip() == "1",
        interest_paid_to=loan.interest_paid_to_date,
        preferred=str(loan.preferred_indicator).strip() == "1",
        last_activity=loan.last_activity_date,
    ) for loan in pi.loans.get_trad_loans() if _float(loan.principal) > 0)
    forced_code = str(pi.field_value("forced_premium_indicator") or "").strip()
    notes = []
    if forced_code not in ("", "0"):
        notes.append(f"Forced premium indicator {forced_code}: the billed premium is kept as billed.")
    return ParWLPolicy(
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
        dividend_option=dividends.div_option_code,
        secondary_dividend_option=dividends.secondary_div_option_code,
        nfo_option=dividends.nfo_code,
        loan_type_code=pi.loans.loan_type_code,
        loan_rate=_rate(pi.loans.fixed_loan_interest_rate),
        reinsurance_key="RGA" if pi.support.reins_partner == "R" else "",
        coverages=tuple(_coverages(pi, valuation_date)),
        benefits=tuple(_benefits(pi, valuation_date)),
        additions=tuple(_additions([r for r in pua_rows if r.is_current], day)),
        additions_before_anniversary=tuple(_additions(_rows_at_last_anniversary(pua_rows, last_anniversary), day)),
        oyt_amount=sum(_float(o.amount) for o in oyts),
        oyt_expiry=oyt_expiry,
        deposits=round(sum(_float(d.deposit_amount) for d in deposits), 2),
        deposit_rate=deposit_rate,
        loans=loans,
        applied_dividends=tuple(_dividend_values(dividends.get_applied_dividends(), True, day)),
        unapplied_dividends=tuple(_dividend_values(unapplied, False, day)),
        notes=tuple(notes),
    )
