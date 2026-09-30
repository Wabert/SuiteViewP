"""The indeterminate premium term illustration report (RERUN's UL page style, landscape).

Built from a finished ``TermResult`` on ``core/ledger_report.py``. The ledger follows
CyberLife's term illustration (TERM - D0194819.pdf): age at the end of the year, year,
the non-guaranteed (current scale) contract premium, and under GUARANTEED VALUES the
guaranteed contract premium, cash value (none: term) and death benefit - with the two
corrections the illustration team asked for (8/27/2026): the guaranteed premium in the
level period is the current premium, and guaranteed renewal premiums are at the
policy's own mode. Riders on the policy add a rider coverage column; the cover lists
the premium structure (level period, annual renewal), substandard extras and any
illustration choices; the notes page explains indeterminate premiums.
"""
from __future__ import annotations

from datetime import date
from typing import List

from suiteview.illustration.core.ledger_report import (
    GROUP_GUARANTEED,
    MODE_LABELS,
    LedgerColumn,
    LedgerReport,
    long_date,
    page_width,
    plain_name,
    short_date,
    two_column_block,
)
from suiteview.illustration.core.report_builder import company_name
from suiteview.illustration.core.term.engine import add_months, completed_months
from suiteview.illustration.models.term import TermResult
from suiteview.polview.models.cl_polrec.policy_translations import rate_class_description

TITLE = "INDETERMINATE PREMIUM TERM LIFE INSURANCE INFORCE ILLUSTRATION"
DISCLAIMER = (
    "THIS IS AN ILLUSTRATION ONLY. AN ILLUSTRATION IS NOT INTENDED TO PREDICT ACTUAL PERFORMANCE. "
    "ACTUAL RESULTS MAY DIFFER FROM THE ILLUSTRATED VALUES SHOWN IN THIS ILLUSTRATION AND MAY BE "
    "MORE OR LESS FAVORABLE. VALUES SET FORTH IN THE ILLUSTRATION ARE NOT GUARANTEED, EXCEPT FOR "
    "THOSE ITEMS CLEARLY LABELED AS GUARANTEED. THE NON-GUARANTEED PREMIUMS ARE THE COMPANY'S CURRENT "
    "PREMIUM RATES, WHICH MAY CHANGE BUT WILL NEVER EXCEED THE GUARANTEED PREMIUMS SHOWN."
)

LEAD_COLUMNS = (
    LedgerColumn("age", ("AGE", "AT", "EOY"), 4, lambda y: y.age, integer=True),
    LedgerColumn("year", ("END", "OF", "YEAR"), 5, lambda y: y.policy_year, integer=True),
    LedgerColumn("current_premium", ("NON-GUAR", "CONTRACT", "PREMIUM"), 14, lambda y: y.current_premium, 2),
)
GUARANTEED_COLUMNS = (
    LedgerColumn("guaranteed_premium", ("", "CONTRACT", "PREMIUM"), 14, lambda y: y.guaranteed_premium, 2,
                 GROUP_GUARANTEED),
    LedgerColumn("cash_value", ("", "CASH", "VALUE"), 10, lambda y: 0.0, group=GROUP_GUARANTEED),
    LedgerColumn("death_benefit", ("", "DEATH", "BENEFIT"), 12, lambda y: y.death_benefit, group=GROUP_GUARANTEED),
)
RIDER_COLUMN = LedgerColumn("rider_death_benefit", ("RIDER", "COVERAGE", "AMOUNT"), 12,
                            lambda y: y.rider_death_benefit, group=GROUP_GUARANTEED)


def _columns(result: TermResult):
    columns = LEAD_COLUMNS + GUARANTEED_COLUMNS
    if any(y.rider_death_benefit > 0 for y in result.years):
        columns += (RIDER_COLUMN,)
    return columns


def _age_at(result: TermResult, when: date) -> int:
    base = result.policy.base
    return base.issue_age + completed_months(base.issue_date, when) // 12


def _premium_class(result: TermResult) -> str:
    base = result.policy.base
    text = (rate_class_description(base.rate_class, base.plancode) or base.rate_class).upper()
    rated = base.table_rating > 0 or bool(base.extras)
    if rated:
        return f"RATED {text}"
    if not any(word in text for word in ("STANDARD", "PREFERRED", "SELECT", "ELITE", "SUPER")):
        return f"STANDARD {text}"     # CyberLife's template: STANDARD NICOTINE USER
    return text


def _structure_lines(result: TermResult) -> List[str]:
    base = result.policy.base
    lines = []
    if base.initial_renewal_period:
        level_end = add_months(base.issue_date, base.initial_renewal_period * 12)
        if base.renewal_period == 1:
            lines.append(f"PREMIUMS ARE LEVEL FOR THE FIRST {base.initial_renewal_period} YEARS (TO "
                         f"{short_date(level_end)}), THEN RENEW ANNUALLY BY ATTAINED AGE")
        elif base.renewal_period:
            lines.append(f"PREMIUMS ARE LEVEL FOR THE FIRST {base.initial_renewal_period} YEARS (TO "
                         f"{short_date(level_end)}), THEN RENEW EVERY {base.renewal_period} YEARS")
        else:
            lines.append(f"PREMIUMS ARE LEVEL FOR {base.initial_renewal_period} YEARS")
    if base.maturity_date is not None:
        lines.append(f"COVERAGE CONTINUES TO {short_date(base.maturity_date)} (AGE {_age_at(result, base.maturity_date)})")
    return lines


def _policy_block(result: TermResult, mode: str):
    policy = result.policy
    base = policy.base
    plan = f"{plain_name(base.description)} ({base.plancode})" if base.description else base.plancode
    sex = {"M": "MALE", "F": "FEMALE"}.get(base.rate_sex.upper(), "UNISEX")
    left = [
        f"POLICY NUMBER:  {policy.policy_number}",
        f"ISSUE DATE:  {long_date(policy.issue_date)}",
        f"ISSUE AGE:  {base.issue_age}",
        f"PLAN:  {plan}",
        f"FORM:  {base.form_number}" if base.form_number else "",
        f"ATTAINED AGE:  {_age_at(result, policy.valuation_date)}",
        f"SEX:  {sex}",
        f"PREMIUM CLASS:  {_premium_class(result)}",
    ]
    left = [line for line in left if line]
    status = "PREMIUMS WAIVED" if policy.is_waiver else (policy.premium_status_description or "").upper()
    right = [
        f"FACE AMOUNT:  ${base.face_amount:,.0f}",
        f"{MODE_LABELS.get(policy.billing_frequency, 'MODAL')} PREMIUM:  ${policy.modal_premium:,.2f}",
        f"POLICY STATUS:  {status}",
        f"VALUES AS OF:  {short_date(policy.valuation_date)}",
    ]
    if policy.paid_to_date:
        right.append(f"PREMIUMS PAID TO:  {short_date(policy.paid_to_date)}")
    if base.next_change_date:
        right.append(f"NEXT PREMIUM CHANGE:  {short_date(base.next_change_date)}")
    return two_column_block(left, right)


def _assumption_lines(result: TermResult, mode: str) -> List[str]:
    policy, inputs = result.policy, result.inputs
    due = [m for m in result.months if m.premium_due]
    lines: List[str] = []
    if due:
        first, last = due[0], due[-1]
        lines.append(f"{mode} PREMIUMS FROM {short_date(first.when)} (YEAR {first.policy_year}) THROUGH "
                     f"{short_date(last.when)} (YEAR {last.policy_year}), THE NON-GUARANTEED PREMIUMS ON THE "
                     "COMPANY'S CURRENT PREMIUM RATES")
    else:
        lines.append("NO FURTHER PREMIUMS ARE DUE")
    if inputs.billing_frequency and inputs.billing_frequency != policy.billing_frequency:
        lines.append(f"PREMIUMS ARE ILLUSTRATED {mode} (THE POLICY IS BILLED "
                     f"{MODE_LABELS.get(policy.billing_frequency, 'MODAL')})")
    if policy.is_waiver:
        lines.append("PREMIUMS ARE CURRENTLY WAIVED; THE PREMIUMS SHOWN ARE THE CONTRACT PREMIUMS")
    lines += _structure_lines(result)
    for cov in policy.coverages:
        for extra in cov.extras:
            until = f" TO {short_date(extra.cease_date)}" if extra.cease_date else ""
            if extra.percent is not None and extra.percent > 1.0:
                lines.append(f"{cov.plancode} TABLE {extra.table_code} RATING: AN EXTRA PREMIUM OF "
                             f"{(extra.percent - 1.0):.0%} OF THE STANDARD PREMIUM{until}")
            elif extra.per_unit:
                lines.append(f"{cov.plancode} FLAT EXTRA PREMIUM OF ${extra.per_unit:,.2f} PER $1,000{until}")
    for phase in inputs.drop_riders:
        cov = next((c for c in policy.coverages if c.phase == phase), None)
        if cov is not None:
            lines.append(f"RIDER {cov.plancode} ({plain_name(cov.description) or cov.form_number}) IS REMOVED")
    for code in inputs.drop_benefits:
        ben = next((b for b in policy.benefits if b.code == code), None)
        if ben is not None:
            lines.append(f"BENEFIT {plain_name(ben.description) or code} IS REMOVED")
    if inputs.end_age is not None:
        lines.append(f"VALUES ARE ILLUSTRATED THROUGH AGE {inputs.end_age}")
    return lines


def _other_coverage(result: TermResult) -> List[str]:
    policy, inputs = result.policy, result.inputs
    lines = []
    for cov in policy.riders:
        if cov.phase in inputs.drop_riders:
            continue
        until = f" TO {short_date(cov.maturity_date)}" if cov.maturity_date else ""
        lines.append(f"{plain_name(cov.description) or 'TERM RIDER'} ({cov.plancode}) - ${cov.face_amount:,.0f}{until}")
    for ben in policy.benefits:
        if ben.code in inputs.drop_benefits:
            continue
        until = f" TO {short_date(ben.cease_date)}" if ben.cease_date else ""
        lines.append(f"{plain_name(ben.description) or ben.code}{until}")
    return lines or ["NONE"]


def build_term_report(result: TermResult, run_date: date) -> LedgerReport:
    """The report content for a finished indeterminate premium term projection."""
    policy = result.policy
    frequency = result.inputs.billing_frequency or policy.billing_frequency
    mode = MODE_LABELS.get(int(frequency), "MODAL")
    columns = _columns(result)
    insured = (policy.insured_name or "").strip()
    first_year = result.years[0].policy_year if result.years else None
    ledger_notes = [
        "PREMIUM PAYMENTS ARE ASSUMED TO BE PAID AT THE BEGINNING OF EACH MODAL PERIOD. CASH VALUE AND DEATH "
        "BENEFIT ARE END OF THE YEAR VALUES.",
    ]
    if first_year is not None:
        ledger_notes.append(
            f"YEAR {first_year} SHOWS ONLY THE PREMIUMS DUE AFTER {short_date(policy.valuation_date)}, THE DATE "
            "OF THE VALUES THIS ILLUSTRATION STARTS FROM.")
    base = policy.base
    maturity_age = _age_at(result, base.maturity_date) if base.maturity_date else None
    notes = [
        "THE NON-GUARANTEED VALUES AND BENEFITS ARE BASED ON ASSUMPTIONS WHICH ARE SUBJECT TO CHANGE BY THE "
        "INSURER. ACTUAL RESULTS MAY BE MORE OR LESS FAVORABLE.",
        "THIS POLICY HAS INDETERMINATE PREMIUMS: THE NON-GUARANTEED CONTRACT PREMIUMS ARE THE COMPANY'S CURRENT "
        "PREMIUM RATES, WHICH THE COMPANY MAY CHANGE. THE GUARANTEED CONTRACT PREMIUMS ARE THE MOST THE COMPANY "
        "MAY CHARGE. A PREMIUM ALREADY SET FOR THE CURRENT PREMIUM PERIOD DOES NOT CHANGE UNTIL THAT PERIOD ENDS.",
        "THIS IS TERM INSURANCE: IT HAS NO CASH VALUE, AND THE DEATH BENEFIT IS PAYABLE ONLY WHILE PREMIUMS ARE PAID.",
    ]
    if maturity_age is not None:
        notes.append(f"COVERAGE ENDS AT AGE {maturity_age} ON {short_date(base.maturity_date)}.")
    return LedgerReport(
        run_date=run_date,
        company_name=company_name(policy.company_code),
        title=TITLE,
        subtitle="",
        prepared_for=f"PREPARED FOR {insured.upper() or f'POLICY {policy.policy_number}'}",
        policy_number=policy.policy_number,
        plancode=base.plancode,
        insured=insured.upper(),
        policy_block=_policy_block(result, mode),
        assumption_lines=_assumption_lines(result, mode),
        columns=columns,
        rows=list(result.years),
        ledger_notes=ledger_notes,
        note_paragraphs=notes,
        other_coverage=_other_coverage(result),
        disclaimer=DISCLAIMER,
        width=page_width(columns),
    )
