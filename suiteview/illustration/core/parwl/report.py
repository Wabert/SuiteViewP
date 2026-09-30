"""The par whole life illustration report: structured content and fixed-width pages.

Built from a finished ``ParWLResult`` in the style of RERUN's UL illustration pages
(``ui/report_tab.py``): a header on every page (run date, company, page x of y,
title, prepared-for line), a cover page with the policy block and the assumptions
the illustration makes, annual ledger pages grouped in fives under GUARANTEED /
NON-GUARANTEED banners, and a notes page. The columns follow the par WL in-force
illustrations the illustration team prepares (premium, loan payments, annual
dividend, PUA cash value, guaranteed and non-guaranteed cash value and death
benefit, total loan, dividends on deposit, base and rider paid-up additions, one
year term); columns a policy never uses (no loans, deposits, rider or OYT) are left
out. Pages print landscape; the page is as wide as the ledger (at least 112
characters, like the UL pages).
"""
from __future__ import annotations

from datetime import date
from typing import Callable, List, Optional, Sequence, Tuple

from suiteview.illustration.core.ledger_report import (
    GROUP_GUARANTEED,
    GROUP_NON_GUARANTEED,
    ILLUSTRATION_DISCLAIMER,
    MODE_LABELS,
    LedgerColumn,
    LedgerReport,
    long_date,
    page_width,
    plain_name,
    short_date,
    two_column_block,
)
from suiteview.illustration.core.parwl.engine import completed_months
from suiteview.illustration.core.report_builder import company_name
from suiteview.illustration.models.parwl import (
    DIVIDEND_OPTION_LABELS,
    ROLE_PUA_RIDER,
    ROLE_TERM_RIDER,
    SECONDARY_OPTION_LABELS,
    ParWLMonth,
    ParWLResult,
    ParWLYear,
)
from suiteview.polview.models.cl_polrec.policy_translations import rate_class_description

TITLE = "PARTICIPATING WHOLE LIFE INSURANCE INFORCE ILLUSTRATION"
DISCLAIMER = (
    ILLUSTRATION_DISCLAIMER + " DIVIDENDS ARE NOT GUARANTEED; THEY ARE BASED ON "
    "THE COMPANY'S CURRENT ILLUSTRATED DIVIDEND SCALE, WHICH IS SUBJECT TO CHANGE."
)


def _premium_outlay(year: ParWLYear) -> float:
    return year.premium + year.rider_payments


def _loan_payments(year: ParWLYear) -> float:
    return year.loan_repayments + year.loan_interest_paid


ALL_COLUMNS: Tuple[LedgerColumn, ...] = (
    LedgerColumn("age", ("AGE", "AT", "EOY"), 4, lambda y: y.age, integer=True),
    LedgerColumn("year", ("END", "OF", "YEAR"), 5, lambda y: y.policy_year, integer=True),
    LedgerColumn("premium", ("", "PREMIUM", "OUTLAY"), 12, _premium_outlay, 2),
    LedgerColumn("loan_payments", ("", "LOAN", "PAYMENTS"), 11, _loan_payments, 2),
    LedgerColumn("new_loans", ("", "NEW", "LOANS"), 11, lambda y: y.new_loans, 2),
    LedgerColumn("guaranteed_cash_value", ("", "CASH", "VALUE"), 10, lambda y: y.guaranteed_cash_value,
                 group=GROUP_GUARANTEED),
    LedgerColumn("guaranteed_death_benefit", ("", "DEATH", "BENEFIT"), 11, lambda y: y.guaranteed_death_benefit,
                 group=GROUP_GUARANTEED),
    LedgerColumn("dividend", ("", "ANNUAL", "DIVIDEND"), 10, lambda y: y.dividend, 2, GROUP_NON_GUARANTEED),
    LedgerColumn("additions_cv", ("PUA", "CASH", "VALUE"), 10, lambda y: y.additions_cv, group=GROUP_NON_GUARANTEED),
    LedgerColumn("cash_value", ("", "CASH", "VALUE"), 10, lambda y: y.surrender_value, group=GROUP_NON_GUARANTEED),
    LedgerColumn("death_benefit", ("", "DEATH", "BENEFIT"), 11, lambda y: y.death_benefit,
                 group=GROUP_NON_GUARANTEED),
    LedgerColumn("loan_balance", ("TOTAL", "LOAN", "BALANCE"), 10, lambda y: y.loan_balance,
                 group=GROUP_NON_GUARANTEED),
    LedgerColumn("deposits", ("DIVIDENDS", "ON", "DEPOSIT"), 10, lambda y: y.deposits, group=GROUP_NON_GUARANTEED),
    LedgerColumn("additions_base", ("BASE", "PAID-UP", "ADDITIONS"), 10, lambda y: y.additions_base,
                 group=GROUP_NON_GUARANTEED),
    LedgerColumn("additions_rider", ("RIDER", "PAID-UP", "ADDITIONS"), 10, lambda y: y.additions_rider,
                 group=GROUP_NON_GUARANTEED),
    LedgerColumn("oyt", ("ONE", "YEAR", "TERM"), 10, lambda y: y.oyt_face, group=GROUP_NON_GUARANTEED),
)
# Columns shown only when the illustration uses them (the policy has the feature or a
# ledger year carries a value).
OPTIONAL_COLUMNS = {"loan_payments", "new_loans", "loan_balance", "deposits", "additions_rider", "oyt"}
GROUP_GAP = 2


# -- building ---------------------------------------------------------------------

def _age_at(result: ParWLResult, when: date) -> int:
    base = result.policy.base
    return base.issue_age + completed_months(base.issue_date, when) // 12


def _status_text(result: ParWLResult) -> str:
    policy = result.policy
    if policy.is_rpu:
        return "REDUCED PAID-UP"
    if policy.is_waiver:
        return "PREMIUMS WAIVED"
    if policy.is_paid_up:
        return "PAID-UP"
    return (policy.premium_status_description or "PREMIUM PAYING").upper()


def _secondary_phrase(secondary: str) -> str:
    return {
        "1": "PAID IN CASH", "3": "LEFT ON DEPOSIT AT INTEREST", "4": "APPLIED TO PURCHASE PAID-UP ADDITIONS",
        "8": "APPLIED TO REDUCE THE POLICY LOAN",
    }.get(secondary, "LEFT ON DEPOSIT AT INTEREST")


def _dividend_statement(option: str, secondary: str, deposit_rate: Optional[float]) -> str:
    rest = _secondary_phrase(secondary)
    interest = f" AT {deposit_rate:.2%} INTEREST" if deposit_rate is not None else " AT INTEREST"
    return {
        "1": "DIVIDENDS ARE ASSUMED TO BE PAID IN CASH.",
        "2": f"DIVIDENDS ARE ASSUMED TO REDUCE THE PREMIUMS DUE; ANY EXCESS IS {rest}.",
        "3": f"DIVIDENDS ARE ASSUMED TO BE LEFT ON DEPOSIT{interest}.",
        "4": "DIVIDENDS ARE ASSUMED TO PURCHASE PAID-UP ADDITIONS.",
        "5": "DIVIDENDS ARE ASSUMED TO PURCHASE ONE YEAR TERM INSURANCE.",
        "6": ("DIVIDENDS ARE ASSUMED TO PURCHASE ONE YEAR TERM INSURANCE UP TO THE POLICY'S CASH VALUE; "
              f"THE REMAINDER IS {rest}."),
        "7": ("DIVIDENDS ARE ASSUMED TO PURCHASE ONE YEAR TERM INSURANCE UP TO THE FACE AMOUNT; "
              f"THE REMAINDER IS {rest}."),
        "8": f"DIVIDENDS ARE ASSUMED TO REDUCE THE POLICY LOAN; ONCE THE LOAN IS REPAID THEY ARE {rest}.",
    }.get(option, f"DIVIDENDS ARE APPLIED UNDER OPTION {option}.")


def _step_months(first: date, second: date) -> int:
    return (second.year - first.year) * 12 + second.month - first.month


def _transaction_lines(rows: Sequence[ParWLMonth], amount: Callable[[ParWLMonth], float],
                       singular: str, plural: str) -> List[str]:
    """Describe dated amounts, collapsing equal amounts at a regular interval into one line."""
    items = [(m.when, m.policy_year, round(amount(m), 2)) for m in rows if amount(m) > 0.004]
    runs: List[list] = []   # [first, last, first year, last year, amount, count, step]
    for when, year, value in items:
        if runs:
            run = runs[-1]
            step = _step_months(run[1], when)
            if value == run[4] and step in (1, 3, 6, 12) and (run[5] == 1 or step == run[6]):
                run[1], run[3], run[5], run[6] = when, year, run[5] + 1, step
                continue
        runs.append([when, when, year, year, value, 1, 0])
    lines = []
    frequency = {12: "ANNUAL", 6: "SEMI-ANNUAL", 3: "QUARTERLY", 1: "MONTHLY"}
    for first, last, first_year, last_year, value, count, step in runs:
        if count == 1:
            lines.append(f"{singular} OF ${value:,.2f} ON {short_date(first)} (YEAR {first_year})")
        else:
            years = f"YEAR {first_year}" if first_year == last_year else f"YEARS {first_year}-{last_year}"
            lines.append(f"{frequency[step]} {plural} OF ${value:,.2f} FROM {short_date(first)} "
                         f"THROUGH {short_date(last)} ({years})")
    return lines


def _premium_lines(result: ParWLResult, months: Sequence[ParWLMonth], mode: str) -> List[str]:
    policy = result.policy
    billed = [m for m in months if m.premium_billed > 0]
    if not billed:
        if policy.is_rpu:
            return ["NO FURTHER PREMIUMS ARE DUE (REDUCED PAID-UP)"]
        if policy.is_paid_up:
            return ["NO FURTHER PREMIUMS ARE DUE (PAID-UP)"]
        return ["NO FURTHER PREMIUMS ARE ILLUSTRATED"]
    if all("premium waived" in m.notes for m in billed):
        return ["PREMIUMS ARE WAIVED UNDER THE WAIVER OF PREMIUM BENEFIT"]
    first, last = billed[0], billed[-1]
    text = (f"{mode} PREMIUMS OF ${first.premium_billed:,.2f} FROM {short_date(first.when)} "
            f"(YEAR {first.policy_year}) THROUGH {short_date(last.when)} (YEAR {last.policy_year})")
    if len({m.premium_billed for m in billed}) > 1:
        text += ", CHANGING AS RIDERS AND BENEFITS EXPIRE"
    return [text]


def _assumption_lines(result: ParWLResult, mode: str) -> List[str]:
    policy, inputs, months = result.policy, result.inputs, result.months
    lines = _premium_lines(result, months, mode)
    if inputs.stop_premiums_at is not None:
        lines.append(f"PREMIUMS STOP BEFORE {short_date(inputs.stop_premiums_at)}")
    option = (inputs.dividend_option or policy.dividend_option or "").strip()
    secondary = (inputs.secondary_option or policy.secondary_dividend_option or "").strip()
    deposit_rate = inputs.deposit_rate if inputs.deposit_rate is not None else policy.deposit_rate
    if not inputs.dividends:
        lines.append("NO DIVIDENDS ARE ILLUSTRATED; THE VALUES SHOWN ASSUME NO DIVIDENDS ARE PAID")
    else:
        lines.append(_dividend_statement(option, secondary, deposit_rate).rstrip("."))
        for change in sorted(inputs.option_changes, key=lambda c: c.when):
            lines.append(f"BEGINNING WITH THE {short_date(change.when)} ANNIVERSARY, "
                         + _dividend_statement(change.option, change.secondary or secondary,
                                               deposit_rate).rstrip("."))
        uses_deposits = policy.deposits > 0 or (option in ("2", "5", "6", "7", "8") and secondary == "3") or any(
            c.option == "3" or (c.option in ("2", "5", "6", "7", "8") and (c.secondary or secondary) == "3")
            for c in inputs.option_changes)
        if uses_deposits and option != "3" and deposit_rate is not None:
            lines.append(f"DIVIDENDS ON DEPOSIT EARN {deposit_rate:.2%} INTEREST")
    if policy.loans and months:
        start = months[0]
        loan = policy.loans[0]
        timing = "PAYABLE IN ADVANCE" if loan.in_advance else "IN ARREARS"
        if start.loan_unearned > 0.004:
            lines.append(f"CURRENT LOAN BALANCE OF ${start.loan_principal:,.2f} AT {loan.rate:.2%} INTEREST {timing}; "
                         f"THE PAYOFF IS ${start.loan_payoff:,.2f} AFTER ${start.loan_unearned:,.2f} OF UNEARNED "
                         "INTEREST")
        else:
            lines.append(f"CURRENT LOAN BALANCE OF ${start.loan_payoff:,.2f} AT {loan.rate:.2%} INTEREST {timing}")
    lines += _transaction_lines(months, lambda m: m.new_loan, "NEW LOAN", "NEW LOANS")
    repayments = [m for m in months if m.loan_repayment > 0.004]
    payoffs = {m.when for m in repayments if m.loan_payoff <= 0.004}
    lines += _transaction_lines([m for m in repayments if m.when not in payoffs], lambda m: m.loan_repayment,
                                "LOAN REPAYMENT", "LOAN REPAYMENTS")
    lines += [f"LOAN PAYOFF OF ${m.loan_repayment:,.2f} ON {short_date(m.when)} (YEAR {m.policy_year})"
              for m in repayments if m.when in payoffs]
    if inputs.pay_loan_interest:
        lines.append("LOAN INTEREST IS PAID IN CASH WHEN DUE")
    lines += _transaction_lines(months, lambda m: m.rider_payment, "PAID-UP ADDITIONS RIDER PREMIUM",
                                "PAID-UP ADDITIONS RIDER PREMIUMS")
    for month in months:
        if "Reduced paid-up" in month.notes:
            lines.append(f"THE POLICY IS CONVERTED TO REDUCED PAID-UP INSURANCE ON {short_date(month.when)} "
                         f"(YEAR {month.policy_year}) FOR A PAID-UP FACE AMOUNT OF ${month.face:,.0f}")
    if inputs.end_age is not None:
        lines.append(f"VALUES ARE ILLUSTRATED THROUGH AGE {inputs.end_age}")
    return lines


def _policy_block(result: ParWLResult, mode: str) -> List[Tuple[str, str]]:
    policy = result.policy
    base = policy.base
    start = result.months[0] if result.months else None
    premium = policy.modal_premium if policy.premium_status in ("22", "32") and not policy.is_rpu else 0.0
    plan = f"{plain_name(base.description)} ({base.plancode})" if base.description else base.plancode
    rated = base.table_rating > 0 or bool(base.extra_premiums)
    premium_class = (rate_class_description(base.rate_class, base.plancode) or base.rate_class).upper()
    sex = {"M": "MALE", "F": "FEMALE"}.get(base.rate_sex.upper(), "UNISEX")
    option = (result.inputs.dividend_option or policy.dividend_option or "").strip()
    secondary = (result.inputs.secondary_option or policy.secondary_dividend_option or "").strip()
    left = [
        f"POLICY NUMBER:  {policy.policy_number}",
        f"ISSUE DATE:  {long_date(policy.issue_date)}",
        f"ISSUE AGE:  {base.issue_age}",
        f"PLAN:  {plan}",
        f"ATTAINED AGE:  {_age_at(result, policy.valuation_date)}",
        f"SEX:  {sex}",
        f"PREMIUM CLASS:  {'RATED ' if rated else ''}{premium_class}",
    ]
    right = [
        f"FACE AMOUNT:  ${base.face_amount:,.0f}",
        f"{mode} PREMIUM:  ${premium:,.2f}",
        f"POLICY STATUS:  {_status_text(result)}",
        "DIVIDEND OPTION:  " + (DIVIDEND_OPTION_LABELS.get(option, option).upper() if result.inputs.dividends
                                else "NONE ILLUSTRATED"),
    ]
    if result.inputs.dividends and option in ("2", "5", "6", "7", "8") and secondary:
        right.append(f"SECONDARY OPTION:  {SECONDARY_OPTION_LABELS.get(secondary, secondary).upper()}")
    right.append(f"VALUES AS OF:  {short_date(policy.valuation_date)}")
    if policy.paid_to_date and policy.premium_status in ("22", "32"):
        right.append(f"PREMIUMS PAID TO:  {short_date(policy.paid_to_date)}")
    if start is not None:
        if start.additions > 0:
            right.append(f"PAID-UP ADDITIONS:  ${start.additions:,.0f}")
        if start.deposits > 0:
            right.append(f"DIVIDENDS ON DEPOSIT:  ${start.deposits:,.2f}")
        if start.oyt_face > 0:
            right.append(f"ONE YEAR TERM:  ${start.oyt_face:,.0f}")
        if start.loan_payoff > 0:
            right.append(f"LOAN BALANCE:  ${max(start.loan_principal, start.loan_payoff):,.2f}")
    return two_column_block(left, right)


def _columns(result: ParWLResult) -> Tuple[LedgerColumn, ...]:
    policy, years = result.policy, result.years
    used = {
        "loan_payments": any(_loan_payments(y) > 0.004 for y in years),
        "new_loans": any(y.new_loans > 0.004 for y in years),
        "loan_balance": bool(policy.loans) or any(y.loan_balance > 0.004 for y in years),
        "deposits": policy.deposits > 0 or any(y.deposits > 0.004 for y in years),
        "additions_rider": policy.pua_rider is not None or any(y.additions_rider > 0.004 for y in years),
        "oyt": policy.oyt_amount > 0 or any(y.oyt_face > 0.004 for y in years),
    }
    return tuple(c for c in ALL_COLUMNS if c.key not in OPTIONAL_COLUMNS or used[c.key])


def _lapse_line(months: Sequence[ParWLMonth], basis: str, end_age: int, matures: bool) -> str:
    last = months[-1] if months else None
    if last is not None and "lapses" in last.notes:
        return (f"UNDER {basis} ASSUMPTIONS THE POLICY LAPSES IN YEAR {last.policy_year} "
                f"(AGE {last.attained_age}) WHEN THE LOAN EXCEEDS THE CASH VALUE.")
    if matures:
        return f"UNDER {basis} ASSUMPTIONS YOUR POLICY WILL REMAIN IN FORCE UNTIL MATURITY (AGE {end_age})."
    return f"UNDER {basis} ASSUMPTIONS YOUR POLICY WILL REMAIN IN FORCE THROUGH AGE {end_age}, THE LAST AGE SHOWN."


def _note_paragraphs(result: ParWLResult) -> List[str]:
    policy = result.policy
    base = policy.base
    maturity_age = _age_at(result, base.maturity_date) if base.maturity_date else None
    end_age = result.years[-1].age if result.years else _age_at(result, policy.valuation_date)
    matures = maturity_age is not None and (result.inputs.end_age is None or result.inputs.end_age >= maturity_age)
    shown_age = maturity_age if matures else end_age
    paragraphs = [
        "IMPORTANT: " + _lapse_line(result.guaranteed_months, "GUARANTEED", shown_age, matures),
        _lapse_line(result.months, "NON-GUARANTEED", shown_age, matures),
        "DIVIDENDS ARE BASED ON THE COMPANY'S ILLUSTRATED SCALE AND ARE NOT GUARANTEED.",
        "PREMIUM PAYMENTS ARE ASSUMED TO BE PAID AT THE BEGINNING OF EACH MODAL PERIOD. CASH VALUE AND DEATH "
        "BENEFIT ARE END OF THE YEAR VALUES.",
        "THE NON-GUARANTEED VALUES AND BENEFITS ARE BASED ON ASSUMPTIONS WHICH ARE SUBJECT TO CHANGE BY THE "
        "INSURER. ACTUAL RESULTS MAY BE MORE OR LESS FAVORABLE.",
        "THE GUARANTEED VALUES ASSUME NO DIVIDENDS ARE PAID, WITH THE SAME PREMIUMS, LOANS AND LOAN PAYMENTS. "
        "CASH VALUES AND DEATH BENEFITS ARE REDUCED BY ANY POLICY LOAN AND LOAN INTEREST. THE PUA CASH VALUE IS "
        "THE CASH VALUE OF THE PAID-UP ADDITIONS AND IS INCLUDED IN THE NON-GUARANTEED CASH VALUE.",
    ]
    if policy.loans or any(y.new_loans > 0 for y in result.years):
        rate = policy.loans[0].rate if policy.loans else (policy.loan_rate or 0.0)
        timing = "IN ADVANCE" if (policy.loans[0].in_advance if policy.loans else True) else "IN ARREARS"
        paragraphs.append(f"POLICY LOAN INTEREST IS CHARGED AT {rate:.2%} {timing} AND, UNLESS PAID, IS ADDED "
                          "TO THE LOAN. A LOAN REDUCES THE CASH VALUE AND DEATH BENEFIT.")
    return paragraphs


def _other_coverage(result: ParWLResult) -> List[str]:
    policy = result.policy
    lines = []
    for cov in policy.coverages:
        if cov.role == ROLE_TERM_RIDER:
            until = f" TO {short_date(cov.maturity_date)}" if cov.maturity_date else ""
            lines.append(f"{plain_name(cov.description) or 'TERM RIDER'} ({cov.plancode}) - "
                         f"${cov.face_amount:,.0f}{until}")
        elif cov.role == ROLE_PUA_RIDER:
            ceased = " - PREMIUM PAYMENTS HAVE CEASED" if cov.payments_ceased else ""
            lines.append(f"PAID-UP ADDITIONS RIDER ({cov.plancode}){ceased}")
    for ben in policy.benefits:
        until = f" TO {short_date(ben.cease_date)}" if ben.cease_date else ""
        lines.append(f"{plain_name(ben.description) or ben.code}{until}")
    return lines or ["NONE"]


def build_parwl_report(result: ParWLResult, run_date: date) -> LedgerReport:
    """The report content for a finished par WL projection."""
    policy = result.policy
    mode = MODE_LABELS.get(int(policy.billing_frequency), "MODAL")
    columns = _columns(result)
    insured = (policy.insured_name or "").strip()
    first_year = result.years[0].policy_year if result.years else None
    ledger_notes = [
        "PREMIUMS, LOANS AND LOAN PAYMENTS ARE ASSUMED TO OCCUR AT THE BEGINNING OF THE APPLICABLE PERIOD. "
        "THE LEDGER VALUES SHOWN FOR AGE, CASH VALUE, DEATH BENEFIT, LOAN BALANCE, DEPOSITS AND ADDITIONS ARE "
        "END-OF-YEAR (EOY) VALUES.",
    ]
    if first_year is not None:
        ledger_notes.append(
            f"YEAR {first_year} SHOWS ONLY THE PREMIUMS AND TRANSACTIONS AFTER {short_date(policy.valuation_date)}, "
            "THE DATE OF THE VALUES THIS ILLUSTRATION STARTS FROM.")
    if any(c.key == "loan_balance" for c in columns):
        ledger_notes.append(
            "THE TOTAL LOAN BALANCE IS THE AMOUNT NEEDED TO REPAY THE LOAN AT THE END OF THE YEAR; INTEREST "
            "CHARGED IN ADVANCE FOR THE FOLLOWING YEAR IS NOT INCLUDED.")
    return LedgerReport(
        run_date=run_date,
        company_name=company_name(policy.company_code),
        title=TITLE,
        subtitle="" if result.inputs.dividends else "GUARANTEED VALUES ONLY - NO DIVIDENDS ILLUSTRATED",
        prepared_for=f"PREPARED FOR {insured.upper() or f'POLICY {policy.policy_number}'}",
        policy_number=policy.policy_number,
        plancode=policy.base.plancode,
        insured=insured.upper(),
        policy_block=_policy_block(result, mode),
        assumption_lines=_assumption_lines(result, mode),
        columns=columns,
        rows=list(result.years),
        ledger_notes=ledger_notes,
        note_paragraphs=_note_paragraphs(result),
        other_coverage=_other_coverage(result),
        disclaimer=DISCLAIMER,
        width=page_width(columns),
    )
