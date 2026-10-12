"""The ISWL reduced paid-up illustration report (RERUN's UL page style, landscape).

Built from a finished ``ISWLRPUResult`` on ``core/ledger_report.py`` in the shape of the
par whole life illustration on reduced paid-up (``core/parwl/report.py``): age at the
end of the year, year, then the values on CyberLife's basis (the stored NSPs rolled
forward each anniversary: NSP per $1,000, cash value, the level paid-up death benefit
and any loan) and, beside them, the endowment NSP comparison (NSP per $1,000 and the
cash value it gives). The cover states that no premiums are due; the ledger notes and
the notes page carry the warnings (material divergence, negative roll-forward values
held frozen and unverified, maturity) and list riders and benefits left on the record.
"""
from __future__ import annotations

from datetime import date
from typing import List, Tuple

from suiteview.illustration.core.iswl_rpu.engine import MATERIAL_DIFFERENCE, completed_parts
from suiteview.illustration.core.ledger_report import (
    ILLUSTRATION_DISCLAIMER,
    LedgerColumn,
    LedgerReport,
    long_date,
    page_width,
    plain_name,
    short_date,
    two_column_block,
)
from suiteview.illustration.core.parwl.nsp import mortality_table
from suiteview.illustration.core.report_builder import company_name
from suiteview.illustration.models.iswl_rpu import ISWLRPUResult
from suiteview.polview.models.cl_polrec.policy_translations import rate_class_description

TITLE = "INTEREST SENSITIVE WHOLE LIFE INSURANCE INFORCE ILLUSTRATION"
SUBTITLE = "REDUCED PAID-UP INSURANCE"
GROUP_CYBERLIFE = "CYBERLIFE BASIS"
GROUP_COMPARISON = "ENDOWMENT NSP"

COLUMNS: Tuple[LedgerColumn, ...] = (
    LedgerColumn("age", ("AGE", "AT", "EOY"), 4, lambda y: y.age, integer=True),
    LedgerColumn("year", ("END", "OF", "YEAR"), 5, lambda y: y.policy_year, integer=True),
    LedgerColumn("nsp", ("NSP", "PER", "$1,000"), 10, lambda y: y.nsp, 2, GROUP_CYBERLIFE),
    LedgerColumn("cash_value", ("", "CASH", "VALUE"), 12, lambda y: y.cash_value, 2, GROUP_CYBERLIFE),
    LedgerColumn("death_benefit", ("", "DEATH", "BENEFIT"), 12, lambda y: y.death_benefit, group=GROUP_CYBERLIFE),
    LedgerColumn("loan", ("", "LOAN", "BALANCE"), 10, lambda y: y.loan, 2, GROUP_CYBERLIFE),
    LedgerColumn("comparison_nsp", ("NSP", "PER", "$1,000"), 10, lambda y: y.comparison_nsp or 0.0, 2,
                 GROUP_COMPARISON),
    LedgerColumn("comparison_cash_value", ("", "CASH", "VALUE"), 12, lambda y: y.comparison_cash_value or 0.0, 2,
                 GROUP_COMPARISON),
)


def _age_at(result: ISWLRPUResult, when: date) -> int:
    policy = result.policy
    return policy.issue_age + completed_parts(policy.issue_date, when)[0]


def _rate(rate: float) -> str:
    return f"{rate * 100:.4f}".rstrip("0").rstrip(".") + "%"


def _basis_text(result: ISWLRPUResult) -> str:
    policy = result.policy
    try:
        description = mortality_table(policy.nsp_table).description.upper()
    except ValueError:
        description = policy.nsp_table
    return f"{description} ({policy.nsp_table}), {_rate(policy.nsp_interest)} INTEREST"


def _policy_block(result: ISWLRPUResult) -> List[Tuple[str, str]]:
    policy = result.policy
    plan = f"{plain_name(policy.description)} ({policy.plancode})" if policy.description else policy.plancode
    sex = {"M": "MALE", "F": "FEMALE"}.get(policy.rate_sex.upper(), "UNISEX")
    premium_class = (rate_class_description(policy.rate_class, policy.plancode) or policy.rate_class).upper()
    left = [
        f"POLICY NUMBER:  {policy.policy_number}",
        f"ISSUE DATE:  {long_date(policy.issue_date)}",
        f"ISSUE AGE:  {policy.issue_age}",
        f"PLAN:  {plan}",
        f"FORM:  {policy.form_number}" if policy.form_number else "",
        f"ATTAINED AGE:  {_age_at(result, policy.valuation_date)}",
        f"SEX:  {sex}",
        f"PREMIUM CLASS:  {premium_class}",
    ]
    right = [
        f"PAID-UP FACE AMOUNT:  ${policy.face_amount:,.0f}",
        "PREMIUM:  $0.00",
        "POLICY STATUS:  REDUCED PAID-UP",
        f"VALUES AS OF:  {short_date(policy.valuation_date)}",
        f"MATURITY DATE:  {short_date(policy.maturity_date)} (AGE {policy.maturity_age})",
    ]
    if result.months:
        right.append(f"CASH VALUE:  ${result.months[0].cash_value:,.2f}")
    if policy.loan_balance > 0:
        right.append(f"LOAN BALANCE:  ${policy.loan_balance:,.2f}")
    return two_column_block([line for line in left if line], right)


def _assumption_lines(result: ISWLRPUResult) -> List[str]:
    policy = result.policy
    lines = [
        "NO FURTHER PREMIUMS ARE DUE (REDUCED PAID-UP)",
        f"THE PAID-UP DEATH BENEFIT OF ${policy.face_amount:,.0f} IS LEVEL TO MATURITY ON "
        f"{short_date(policy.maturity_date)} (AGE {policy.maturity_age})",
        "CYBERLIFE BASIS: CASH VALUES ARE THE NET SINGLE PREMIUMS STORED ON THE POLICY RECORD, EXTENDED ONE YEAR "
        "AT EACH ANNIVERSARY AS CYBERLIFE DOES",
        f"ENDOWMENT NSP COMPARISON: THE NET SINGLE PREMIUM OF THE PAID-UP INSURANCE (ENDOWMENT AT AGE {policy.maturity_age}) AT THE ATTAINED AGE ON THE "
        f"SAME BASIS, {_basis_text(result)}",
    ]
    if result.inputs.end_age is not None:
        lines.append(f"VALUES ARE ILLUSTRATED THROUGH AGE {result.inputs.end_age}")
    return lines


def _ledger_notes(result: ISWLRPUResult) -> List[str]:
    policy = result.policy
    notes = [
        "THE LEDGER VALUES SHOWN FOR AGE, NET SINGLE PREMIUM, CASH VALUE, DEATH BENEFIT AND LOAN ARE END-OF-YEAR "
        "(EOY) VALUES.",
    ]
    if result.divergence_from is not None:
        notes.append(f"FROM YEAR {result.divergence_from} THE CYBERLIFE BASIS DIFFERS FROM THE ENDOWMENT NSP BY "
                     f"MORE THAN {MATERIAL_DIFFERENCE:.0%}.")
    if result.freeze_from is not None and result.negative is not None:
        frozen = [y.policy_year for y in result.years if y.frozen]
        if frozen:
            notes.append(f"YEARS {frozen[0]}-{frozen[-1]}: CYBERLIFE'S NET SINGLE PREMIUM TURNS NEGATIVE AT AGE "
                         f"{result.negative.age} AND IS NO LONGER UPDATED; THESE CYBERLIFE BASIS VALUES ARE HELD AT "
                         f"THE {short_date(result.freeze_from)} VALUE AND ARE NOT VERIFIED.")
    if any(y.end_date == policy.maturity_date for y in result.years):
        notes.append(f"THE LAST YEAR ENDS AT MATURITY ON {short_date(policy.maturity_date)}; THE MATURITY BENEFIT "
                     "IS NOT ILLUSTRATED.")
    return notes


def _note_paragraphs(result: ISWLRPUResult) -> List[str]:
    paragraphs = [
        "THIS POLICY IS ON REDUCED PAID-UP INSURANCE. NO PREMIUMS ARE DUE, THERE IS NO ACCOUNT VALUE AND THE PAID-UP "
        "FACE AMOUNT DOES NOT CHANGE. THE CASH VALUE IS THE NET SINGLE PREMIUM OF THE PAID-UP INSURANCE.",
        "THE CYBERLIFE BASIS REPRODUCES THE VALUES THE ADMINISTRATION SYSTEM STORES AND EXTENDS EACH ANNIVERSARY. "
        "THE ENDOWMENT NSP COMPARISON (THE BASIS CYBERLIFE USES AT CONVERSION) IS SHOWN SO THE TWO CAN BE COMPARED; IT IS NOT THE ADMINISTERED VALUE.",
    ]
    paragraphs += [warning.upper() for warning in result.warnings]
    return paragraphs


def _other_coverage(result: ISWLRPUResult) -> List[str]:
    policy = result.policy
    lines = [f"{plain_name(text)} (NOT VALUED ON REDUCED PAID-UP)" for text in policy.other_coverages]
    for ben in policy.benefits:
        until = f" TO {short_date(ben.cease_date)}" if ben.cease_date else ""
        lines.append(f"{plain_name(ben.description) or ben.code}{until} (NOT VALUED ON REDUCED PAID-UP)")
    return lines or ["NONE"]


def build_iswl_rpu_report(result: ISWLRPUResult, run_date: date) -> LedgerReport:
    """The report content for a finished ISWL reduced paid-up projection."""
    policy = result.policy
    insured = (policy.insured_name or "").strip()
    return LedgerReport(
        run_date=run_date,
        company_name=company_name(policy.company_code),
        title=TITLE,
        subtitle=SUBTITLE,
        prepared_for=f"PREPARED FOR {insured.upper() or f'POLICY {policy.policy_number}'}",
        policy_number=policy.policy_number,
        plancode=policy.plancode,
        insured=insured.upper(),
        policy_block=_policy_block(result),
        assumption_lines=_assumption_lines(result),
        columns=COLUMNS,
        rows=list(result.years),
        ledger_notes=_ledger_notes(result),
        note_paragraphs=_note_paragraphs(result),
        other_coverage=_other_coverage(result),
        disclaimer=ILLUSTRATION_DISCLAIMER,
        width=page_width(COLUMNS),
    )
