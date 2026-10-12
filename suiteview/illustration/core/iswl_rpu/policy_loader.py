"""Build the ISWL reduced paid-up snapshot (``ISWLRPUPolicy``) through PolicyInformation.

Detection: a CyberLife advanced product (``is_advanced_product``) whose base coverage is
interest sensitive whole life (``PRD_LIN_TYP_CD = 'I'``) on premium pay status ``45``
(reduced paid-up; CyberDoc B20 p.62 "the status code of the contract is changed to 45").

Facts come from named PolicyInformation sections: the base coverage and its
``TraditionalCoverageFacts`` (NSP table and interest, the mortality function code
``MTL_FUN_CD`` that decides the claims factor, ``LOW_DUR_PER`` and the three stored
NSPs), and PolView's NSP cash value (``rates.guaranteed_cash_value``: units x the stored
NSPs interpolated to the last processed monthliversary) as the value the illustration
must start from. A function code other than 0, 1 or 2 refuses Run Values (not verified).

**Loans.** B20 p.62: at an RPU conversion an existing loan is paid off unless the
"retain loan" option applies (D202 p.236, 69 segment flag G bit 0), in which case it "is
converted to a traditional format". A traditional loan row (``LH_CSH_VAL_LOAN``, MVRY_DT
12/31/9999) or the latest advanced loan row (``LH_FND_VAL_LOAN``) dated after the last
account value is a current loan (12/31/9999 when present; the earlier ones are anniversary
snapshots - 11051396 keeps its loan there, capitalised at 8% each anniversary). The
interest mechanics of a loan kept on an ISWL RPU are not verified, so such a policy is
shown but Run Values is refused, naming the balance. Advanced loan rows dated on or
before the last account value predate the conversion (B10 p.57: the advanced values "are
for historical purposes only"); they are listed and noted, not illustrated.

**Riders and benefits.** B20 p.62: "after the reduced paid-up conversion, the contract is
processed as if all coverages and benefits are ceased, but the status code ... is not
physically changed". They are shown and not valued; a rider with its own stored cash
values that PolView would add to the cash value refuses the run.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional, Tuple

from suiteview.illustration.core.parwl.nsp import NSPError, claims_factor_for
from suiteview.illustration.core.parwl.policy_loader import benefit_name, plan_name
from suiteview.illustration.models.iswl_rpu import (
    ISWL_PRODUCT_LINE,
    STATUS_RPU,
    ISWLRPUBenefit,
    ISWLRPULoan,
    ISWLRPUPolicy,
)
from suiteview.polview.models.cl_polrec.cyberlife_base import parse_date
from suiteview.polview.models.schema_rates import rates_sex


class ISWLRPUPolicyError(ValueError):
    """The policy cannot be illustrated as ISWL reduced paid-up (explains why)."""


def _float(value, default: float = 0.0) -> float:
    return float(value) if value is not None else default


def is_iswl_rpu(pi) -> bool:
    """An interest sensitive whole life policy (advanced, base product line I) on reduced paid-up."""
    if not pi.product.is_advanced_product:
        return False
    if str(pi.status.premium_pay_status_code or "").strip() != STATUS_RPU:
        return False
    base = pi.coverages.get_base_coverage()
    if base is None:
        return False
    return pi.coverages.traditional_facts(base.cov_pha_nbr).product_line_code == ISWL_PRODUCT_LINE


def _benefits(pi, valuation_date: date) -> Tuple[ISWLRPUBenefit, ...]:
    benefits = []
    for ben in pi.benefits.get_benefits():
        if ben.cease_date is not None and ben.cease_date <= valuation_date:
            continue
        benefits.append(ISWLRPUBenefit(
            phase=ben.cov_pha_nbr,
            code=ben.benefit_code,
            description=benefit_name(ben.benefit_code) or str(ben.benefit_desc or "").strip(),
            form_number=str(ben.form_number or "").strip(),
            units=_float(ben.units),
            value_per_unit=_float(ben.vpu, 1000.0),
            annual_premium_per_unit=_float(ben.coi_rate),
            issue_date=ben.issue_date,
            cease_date=ben.cease_date,
        ))
    return tuple(benefits)


def _loans(pi, last_account_value: Optional[date]) -> Tuple[ISWLRPULoan, ...]:
    loans: List[ISWLRPULoan] = []
    for loan in pi.loans.get_trad_loans():
        if _float(loan.principal) <= 0:
            continue
        loans.append(ISWLRPULoan(
            table="LH_CSH_VAL_LOAN", as_of=loan.mv_date, principal=_float(loan.principal),
            accrued_interest=_float(loan.accrued_interest),
            rate=_float(loan.interest_rate) / 100.0 if loan.interest_rate is not None else None, current=True))
    rows = [(parse_date((loan.raw_data or {}).get("MVRY_DT")), loan) for loan in pi.loans.get_loans()]
    after = [as_of for as_of, _loan in rows
             if as_of is None or last_account_value is None or as_of > last_account_value]
    # After the conversion the advanced loan rows are anniversary snapshots plus the
    # current row (12/31/9999); only the latest of them is the loan carried now.
    latest = max((d for d in after if d is not None), default=None)
    for as_of, loan in rows:
        loans.append(ISWLRPULoan(
            table="LH_FND_VAL_LOAN", as_of=as_of, principal=_float(loan.principal),
            accrued_interest=_float(loan.accrued_interest),
            rate=_float(loan.interest_rate) / 100.0 if loan.interest_rate is not None else None,
            current=bool(after) and (as_of is None or as_of == latest)))
    return tuple(loans)


def _loan_texts(loans: Tuple[ISWLRPULoan, ...], last_account_value: Optional[date]) -> Tuple[str, List[str]]:
    """(run block, notes) for the loans on the record."""
    current = [loan for loan in loans if loan.current]
    notes = []
    block = ""
    if current:
        balance = sum(loan.balance for loan in current)
        principal = sum(loan.principal for loan in current)
        tables = ", ".join(sorted({loan.table for loan in current}))
        block = (f"A policy loan of ${balance:,.2f} (principal ${principal:,.2f} plus interest) is on the record "
                 f"({tables}). Loans kept through an ISWL reduced paid-up conversion are converted to a traditional "
                 "loan (CyberDoc B20 p.62); their interest accrual on RPU is not verified, so this policy is not "
                 "illustrated.")
    history = [loan for loan in loans if not loan.current and loan.as_of is not None
               and last_account_value is not None and loan.as_of <= last_account_value]
    if history and not current:
        latest = max(loan.as_of for loan in history if loan.as_of is not None)
        balance = sum(loan.balance for loan in history if loan.as_of == latest)
        notes.append(
            f"Advanced (UL) loan rows dated on or before the last account value "
            f"{last_account_value:%m/%d/%Y} predate the RPU conversion (balance ${balance:,.2f} at "
            f"{latest:%m/%d/%Y}). No loan row is dated after it, so no current loan is illustrated (CyberDoc B20 "
            "p.62: a loan kept through the conversion is converted and carried on; such loans show as loan rows "
            "dated after the conversion). Confirm against the conversion activity if in doubt.")
    return block, notes


def _other_coverages(pi, base_phase: int, valuation_date: date) -> Tuple[Tuple[str, ...], str]:
    lines, block = [], ""
    for index, cov in enumerate(pi.coverages.get_coverages(), start=1):
        if cov.cov_pha_nbr == base_phase:
            continue
        facts = pi.coverages.traditional_facts(cov.cov_pha_nbr)
        matured = cov.maturity_date is not None and cov.maturity_date <= valuation_date
        state = "matured" if matured else (f"ceased ({facts.cease_reason_code})" if facts.cease_reason_code
                                           else "on the record")
        face = _float(cov.units) * _float(cov.vpu, 1000.0)
        lines.append(f"Phase {cov.cov_pha_nbr} {cov.plancode} {plan_name(cov.plancode)} ${face:,.0f} to "
                     f"{cov.maturity_date:%m/%d/%Y} - {state}" if cov.maturity_date else
                     f"Phase {cov.cov_pha_nbr} {cov.plancode} ${face:,.0f} - {state}")
        stored = pi.rates.cov_cash_value_rates(index)
        if stored.get("basis") and not matured and not facts.cease_reason_code:
            block = (f"Coverage phase {cov.cov_pha_nbr} ({cov.plancode}) carries its own stored "
                     f"{stored['basis']} values; riders with values on an ISWL reduced paid-up are not illustrated.")
    return tuple(lines), block


def build_iswl_rpu_policy(pi, region: str = "CKPR") -> ISWLRPUPolicy:
    """The in-force ISWL reduced paid-up snapshot of a loaded PolicyInformation."""
    if not pi.exists:
        raise ISWLRPUPolicyError(f"Policy {pi.policy_number} was not found.")
    if not is_iswl_rpu(pi):
        raise ISWLRPUPolicyError("The policy is not an interest sensitive whole life policy on reduced paid-up.")
    base = pi.coverages.get_base_coverage()
    facts = pi.coverages.traditional_facts(base.cov_pha_nbr)
    if base.issue_date is None or base.issue_age is None:
        raise ISWLRPUPolicyError("The base coverage has no issue date or issue age.")
    if base.maturity_date is None:
        raise ISWLRPUPolicyError("The base coverage has no maturity date (COV_MT_EXP_DT).")
    stored = tuple(facts.stored_nsp_values)
    if (not facts.nsp_rpu_table or facts.nsp_interest_rate is None or facts.stored_low_duration is None
            or len(stored) != 3 or any(v is None for v in stored)):
        raise ISWLRPUPolicyError(
            "The base coverage has no reduced paid-up NSP basis on the record (NSP_RPU_TBL_CD, NSP_ITS_RT, "
            "LOW_DUR_PER and the three LOW_DUR NSP values are all needed).")
    gcv = pi.rates.guaranteed_cash_value()
    valuation_date = gcv.get("as_of") or pi.activity.last_anniversary
    if valuation_date is None:
        raise ISWLRPUPolicyError("The policy has no monthliversary or anniversary to value from.")
    last_account_value = pi.values.last_account_value_date
    index = pi.coverages.cov_index_for_phase(base.cov_pha_nbr)
    units, vpu = _float(base.units), _float(base.vpu, 1000.0)
    loans = _loans(pi, last_account_value)
    loan_block, notes = _loan_texts(loans, last_account_value)
    others, rider_block = _other_coverages(pi, base.cov_pha_nbr, valuation_date)
    blocks = [loan_block, rider_block]
    function_code = facts.mortality_function_code or None
    try:
        if function_code is not None:
            claims_factor_for(function_code, float(facts.nsp_interest_rate) / 100.0)
    except NSPError as exc:
        blocks.append(str(exc))
    if abs(vpu - 1000.0) > 0.005:
        blocks.append(f"The base coverage's value per unit is {vpu:,.2f}; the stored NSPs are reproduced per $1,000 "
                      "and PolView values them per unit, so a value per unit other than 1,000 is not illustrated.")
    benefits = _benefits(pi, valuation_date)
    if benefits or others:
        notes.append("Riders and benefits are shown, not valued: after the RPU conversion CyberLife processes the "
                     "contract as if all coverages and benefits are ceased (CyberDoc B20 p.62).")
    death_benefit = pi.values.death_benefit
    return ISWLRPUPolicy(
        policy_number=pi.policy_number,
        company_code=pi.company_code,
        region=region,
        insured_name=pi.persons.primary_insured_name,
        issue_state=str(pi.product.issue_state or "").strip().upper(),
        phase=base.cov_pha_nbr,
        plancode=base.plancode,
        form_number=str(base.form_number or "").strip(),
        description=plan_name(base.plancode),
        issue_date=base.issue_date,
        issue_age=int(base.issue_age),
        rate_sex=rates_sex(pi.rates.cov_rate_sex_code(index)),
        sex_description=str(base.sex_desc or "").strip(),
        rate_class=str(base.rate_class or "").strip().upper(),
        premium_status=pi.status.premium_pay_status_code,
        premium_status_description=pi.status.premium_pay_status_description,
        valuation_date=valuation_date,
        last_anniversary=pi.activity.last_anniversary,
        paid_to_date=pi.activity.paid_to_date,
        last_account_value_date=last_account_value,
        units=units,
        value_per_unit=vpu,
        maturity_date=base.maturity_date,
        nsp_table=facts.nsp_rpu_table,
        eti_table=facts.nsp_extended_table,
        nsp_interest=float(facts.nsp_interest_rate) / 100.0,
        rpu_benefit_code=facts.rpu_benefit_code,
        low_duration=int(facts.stored_low_duration),
        stored_nsp=tuple(float(v) for v in stored),
        polview_cash_value=float(gcv["value"]) if gcv.get("value") is not None else None,
        polview_reason=str(gcv.get("reason") or ""),
        mortality_function_code=function_code,
        record_death_benefit=float(death_benefit) if death_benefit is not None else None,
        benefits=benefits,
        loans=loans,
        other_coverages=others,
        run_block=" ".join(b for b in blocks if b),
        notes=tuple(notes),
    )
