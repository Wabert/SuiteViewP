"""UL Illustration Report assembly — mirrors RERUN's "UL - Illustration Pages".

Builds a structured ``IllustrationReport`` from the projection results; the
Report tab formats it into fixed-width pages. Pure data, no Qt.

Sources in the workbook (decoded 2026-06-10):
  - Cover (sULSubRange1): insured/policy block, AV-basis line, requested
    premium/loan/withdrawal lines (Illustration Values AY5..AY32), forecasted
    policy-change summaries, MEC sentence.
  - Annual ledger (mLedgerKey F..O / mLedgerValuesCurrent AB..AG): EOY Age,
    Year, Premium Outlay, Loan Repays, Exception Prem, MEC, GP Cap, ForceOut,
    Mode, Distribution from Policy; EOY AV / SV / DB / Loan Balance.
  - Row markers (UL pages R17): '*' GP-capped (and no exception prem),
    '@' force-out, '^' exception premiums, '&' forecast year of MEC,
    '#' premiums repaid loans, '%' maturity with SV endowment,
    '+' a new 7-pay test period starts (TAMRA material change).
  - Notes page (BT block): assumptions paragraphs + conditional legends.
  - Riders/regulatory page (CI block): riders list, GSP/GLP/AccumGLP (+7-pay
    within the TAMRA window), per-policy-change estimated limits.

The GUARANTEED value columns come from a second engine run under guaranteed
assumptions with the current side's cash flows locked in (LockValues — see
core/guaranteed_projection.py). When no guaranteed run is supplied the
columns render blank.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    PolicyChangeKind,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData


# ── Display maps ────────────────────────────────────────────────────────────

_DBO_DESCRIPTIONS = {
    "A": "CV INCLUDED IN SPECIFIED AMOUNT",
    "B": "CV ADDED TO SPECIFIED AMOUNT",
    "C": "PREMIUMS ADDED TO SPECIFIED AMOUNT",
}

_MODE_LABELS = {1: "MONTHLY", 3: "QUARTERLY", 6: "SEMI-ANNUAL", 12: "ANNUAL"}
_SCHEDULE_MODE_LABELS = {"M": "MONTHLY", "Q": "QUARTERLY", "S": "SEMI-ANNUAL", "A": "ANNUAL"}

# Premium class wording (Illustration Values C19/C23): nicotine split plus a
# RATED prefix when substandard.
_NICOTINE_CLASSES = {"S", "Q"}

# Benefit type+subtype -> report display names (Illustration Values BA/BB
# rider name table). The '#' subtypes are the ABR accelerated riders.
# TODO: verify the '#4/#5/#6' -> ABR terminal/critical/chronic mapping against
# live data — the engine treats '#' benefits as administrative.
_BENEFIT_NAMES = {
    "39": "PREMIUM WAIVER",
    "3#": "STIPULATED PREMIUM WAIVER",
    "76": "GUARANTEED INCREASE OPTION",
    "#4": "ACCELERATED RIDER TERMINAL ILLNESS",
    "#5": "ACCELERATED RIDER CRITICAL ILLNESS",
    "#6": "ACCELERATED RIDER CHRONIC ILLNESS",
}
_BENEFIT_TYPE_NAMES = {
    "A": "CONTINUOUS COVERAGE RIDER",
    "7": "GUARANTEED INCREASE OPTION",
}


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


# ── Report structure ────────────────────────────────────────────────────────

@dataclass
class LedgerRow:
    """One policy year of the report ledger (RERUN mLedgerKey + Current)."""

    eoy_age: int = 0
    year: int = 0
    premium_outlay: float = 0.0
    markers: str = ""               # '* @ ^ & # % +' combination for the year
    cash_from_policy: float = 0.0   # Distribution from Policy (WDs + force-outs)
    loan_balance: float = 0.0
    # Guaranteed columns; None (blank) when no guaranteed run was supplied.
    guar_accum: Optional[float] = None
    guar_surr: Optional[float] = None
    guar_death: Optional[float] = None
    accum_value: float = 0.0
    surr_value: float = 0.0
    death_benefit: float = 0.0
    lapsed: bool = False


@dataclass
class ChangeSection:
    """Per-policy-change block (cover summary + page-4 estimated limits)."""

    effective_date: Optional[date] = None
    year: int = 0
    summary_lines: List[str] = field(default_factory=list)
    rider_lines: List[str] = field(default_factory=list)
    limit_lines: List[str] = field(default_factory=list)


@dataclass
class IllustrationReport:
    company_name: str = ""
    title: str = "FLEXIBLE PREMIUM UNIVERSAL LIFE INSURANCE HYPOTHETICAL INFORCE ILLUSTRATION"
    prepared_for: str = ""
    run_date: Optional[date] = None

    # Cover blocks
    insured_lines: List[str] = field(default_factory=list)
    agent_lines: List[str] = field(default_factory=list)
    # Two-column policy block: (left text, right text) pairs, pre-formatted.
    # A pair of empty strings renders as a blank separator row.
    policy_block: List[tuple] = field(default_factory=list)
    disclaimer_lines: List[str] = field(default_factory=list)
    av_basis_line: str = ""
    loan_basis_line: str = ""
    request_intro: List[str] = field(default_factory=list)
    request_lines: List[str] = field(default_factory=list)
    change_sections: List[ChangeSection] = field(default_factory=list)
    mec_line: str = ""

    # Ledger
    ledger: List[LedgerRow] = field(default_factory=list)
    # End-of-projection values, set only when the policy reaches maturity
    # (rendered as a VALUES AT MATURITY strip under the ledger).
    maturity_row: Optional[LedgerRow] = None
    footnote_legends: List[str] = field(default_factory=list)
    # (policy year, start date) for each NEW 7-pay test period the projection
    # starts — a TAMRA material change restarts the 7-pay window.
    seven_pay_restarts: List[tuple] = field(default_factory=list)

    # Notes page
    note_paragraphs: List[List[str]] = field(default_factory=list)
    exception_section: List[str] = field(default_factory=list)

    # Riders / regulatory page
    rider_lines: List[str] = field(default_factory=list)
    as_of_date: Optional[date] = None
    regulatory_lines: List[str] = field(default_factory=list)

    # Derived facts (for tests / status)
    termination_year: Optional[int] = None
    guaranteed_termination_year: Optional[int] = None
    year_of_mec: Optional[int] = None
    has_guaranteed_values: bool = False


# ── Annual ledger assembly ──────────────────────────────────────────────────

def _annualize(
    policy: IllustrationPolicyData,
    results: List[MonthlyState],
    options: IllustrationOptions,
) -> tuple[List[LedgerRow], Optional[int], Optional[int]]:
    """Fold projected months into policy-year rows (row 0 inforce excluded).

    Returns (rows, year_of_mec, termination_year).
    """
    projected = results[1:]
    by_year: dict[int, List[MonthlyState]] = {}
    for state in projected:
        by_year.setdefault(state.policy_year, []).append(state)

    maturity_age = 121
    year_of_mec: Optional[int] = None
    termination_year: Optional[int] = None
    rows: List[LedgerRow] = []
    for year in sorted(by_year):
        months = by_year[year]
        eoy = months[-1]
        outlay = sum(m.premium_outlay for m in months)
        forceout = sum(m.guideline_forceout for m in months)
        exception = sum(m.gp_exception_prem for m in months)
        withdrawals = sum(m.applied_net_withdrawal for m in months)
        capped = any(m.premium_capped for m in months)

        # MEC: 7-pay contributions exceed level x year inside the window
        # (only reachable with TAMRA conformance off, or an already-MEC load).
        if year_of_mec is None:
            for m in months:
                if (
                    1 <= m.tamra_year <= 7
                    and m.tamra_7pay_level > 0
                    and m.accumulated_7pay > m.tamra_7pay_level * m.tamra_year + 0.005
                ):
                    year_of_mec = year
                    break

        if termination_year is None and eoy.lapsed:
            termination_year = year

        markers = ""
        if capped and exception <= 0.005:
            markers += "* "
        if forceout > 0.005:
            markers += "@ "
        if exception > 0.005:
            markers += "^ "
        if year_of_mec == year:
            markers += "& "
        # '#' (premiums repaid loans) — loan repayment inputs are not yet
        # surfaced per-month by the engine; wire when they are.
        if eoy.attained_age >= maturity_age:
            markers += "% "

        rows.append(LedgerRow(
            eoy_age=eoy.attained_age,
            year=year,
            premium_outlay=outlay,
            markers=markers.strip(),
            cash_from_policy=withdrawals + forceout,
            loan_balance=eoy.policy_debt,
            accum_value=eoy.av_end_of_month,
            surr_value=eoy.surrender_value,
            death_benefit=eoy.ending_db,
            lapsed=eoy.lapsed,
        ))
    return rows, year_of_mec, termination_year


def _seven_pay_restarts(results: List[MonthlyState]) -> List[tuple]:
    """(policy_year, start_date) for each new 7-pay period the projection starts.

    A TAMRA material change (specified-amount increase, B->A option change)
    restarts the 7-pay test period at the change date; the engine stamps the
    new start date on every subsequent month's state, so a restart shows as
    the state's ``tamra_7pay_start_date`` moving.
    """
    restarts: List[tuple] = []
    previous = results[0].tamra_7pay_start_date if results else None
    for state in results[1:]:
        start = state.tamra_7pay_start_date
        if start is not None and start != previous:
            restarts.append((state.policy_year, start))
        previous = start
    return restarts


def _fill_guaranteed_columns(
    rows: List[LedgerRow],
    guaranteed_results: List[MonthlyState],
) -> Optional[int]:
    """Fill the ledger's guaranteed columns from the guaranteed run.

    Ledger years past the guaranteed run's end (it lapsed earlier) show zero,
    matching RERUN. Returns the guaranteed termination year (None = inforce
    for all years shown).
    """
    by_year: dict[int, MonthlyState] = {}
    termination_year: Optional[int] = None
    for state in guaranteed_results[1:]:
        by_year[state.policy_year] = state
        if termination_year is None and state.lapsed:
            termination_year = state.policy_year
    for row in rows:
        eoy = by_year.get(row.year)
        if eoy is None or eoy.lapsed:
            row.guar_accum = 0.0
            row.guar_surr = 0.0
            row.guar_death = 0.0
        else:
            row.guar_accum = max(eoy.av_end_of_month, 0.0)
            row.guar_surr = max(eoy.surrender_value, 0.0)
            row.guar_death = max(eoy.ending_db, 0.0)
    return termination_year


# ── Requested premium / loan / withdrawal lines ─────────────────────────────

_INTERVAL_MODE_LABELS = {1: "MONTHLY", 3: "QUARTERLY", 6: "SEMI-ANNUAL", 12: "ANNUAL"}


def _request_lines(
    policy: IllustrationPolicyData,
    results: List[MonthlyState],
    future_inputs: Optional[IllustrationInputSet],
) -> List[str]:
    """The cover's requested premium / loan / withdrawal lines (AY5..AY32)."""
    projected = results[1:]
    if not projected:
        return []

    # Premiums: from the projection's REQUESTED per-payment premiums (pre-cap).
    # Consecutive equal payments at a steady month interval compress into one
    # run, so a partial first year (forecast mid-year, paid as dated
    # transactions under a zero-amount silencing schedule) or a truncated
    # final year (lapse/maturity) folds into its neighboring years instead of
    # rendering as a bogus annualized amount. The mode comes from the payment
    # spacing; a single payment falls back to the active nonzero schedule's
    # mode, else the policy's billing mode.
    billed_label = _MODE_LABELS.get(policy.billing_frequency, "MONTHLY")
    schedule_modes: dict[int, str] = {}
    if future_inputs is not None:
        premium_schedules = sorted(
            (t for t in future_inputs.scheduled_transactions
             if t.kind == TransactionKind.PREMIUM and t.amount > 0.005),
            key=lambda t: t.policy_year,
        )
        for state in projected:
            active = None
            for sched in premium_schedules:
                if sched.policy_year <= state.policy_year:
                    active = sched
            if active is not None:
                schedule_modes[state.policy_year] = _SCHEDULE_MODE_LABELS.get(
                    (active.mode or "M").strip().upper(), "MONTHLY")

    runs: List[dict] = []
    for state in projected:
        amount = round(state.requested_premium, 2)
        if amount <= 0.005:
            continue
        run = runs[-1] if runs else None
        gap = state.duration - run["last_duration"] if run else None
        if run and amount == run["amount"] and run["interval"] in (None, gap):
            run["interval"] = gap
            run["end_year"] = state.policy_year
            run["last_duration"] = state.duration
        else:
            runs.append({
                "start_year": state.policy_year, "end_year": state.policy_year,
                "amount": amount, "interval": None, "last_duration": state.duration,
            })

    lines: List[str] = []
    for run in runs:
        label = _INTERVAL_MODE_LABELS.get(run["interval"])
        if label is None:
            label = schedule_modes.get(run["start_year"], billed_label)
        span = (
            f"FOR POLICY YEARS {run['start_year']} THROUGH {run['end_year']}"
            if run["end_year"] != run["start_year"]
            else f"IN POLICY YEAR {run['start_year']}"
        )
        lines.append(f"{label} PREMIUM OF {_money(run['amount'])} {span}")

    if future_inputs is None:
        return lines

    # Loans: annual schedules (vINPUT_Loans) — described from the REQUEST,
    # so a run that ends before the loan years still lists them. A schedule
    # persists until the next entry (or maturity).
    maturity_year = max(1, 121 - policy.issue_age)
    loan_schedules = sorted(
        (t for t in future_inputs.scheduled_transactions if t.kind == TransactionKind.LOAN),
        key=lambda t: t.policy_year,
    )
    for index, sched in enumerate(loan_schedules):
        if sched.amount <= 0:
            continue
        end = (
            loan_schedules[index + 1].policy_year - 1
            if index + 1 < len(loan_schedules)
            else maturity_year
        )
        mode = _SCHEDULE_MODE_LABELS.get((sched.mode or "A").strip().upper(), "ANNUAL")
        span = (
            f"FOR POLICY YEARS {sched.policy_year} THROUGH {end}"
            if end != sched.policy_year
            else f"IN POLICY YEAR {sched.policy_year}"
        )
        lines.append(f"{mode} FIXED LOAN OF {_money(sched.amount)} {span}")

    # Withdrawals: dated, one line per year (AY22..AY27).
    wd_by_year: dict[int, float] = {}
    issue = policy.issue_date
    for tx in future_inputs.dated_transactions:
        if tx.kind != TransactionKind.WITHDRAWAL or issue is None:
            continue
        months = (tx.effective_date.year - issue.year) * 12 + (tx.effective_date.month - issue.month)
        year = months // 12 + 1
        wd_by_year[year] = wd_by_year.get(year, 0.0) + tx.amount
    for year in sorted(wd_by_year):
        lines.append(f"WITHDRAWAL OF {_money(wd_by_year[year])} IN POLICY YEAR {year}")
    return lines


# ── Policy change sections ──────────────────────────────────────────────────

def _change_sections(
    policy: IllustrationPolicyData,
    results: List[MonthlyState],
    future_inputs: Optional[IllustrationInputSet],
    rider_lines: List[str],
    options: IllustrationOptions,
) -> List[ChangeSection]:
    if future_inputs is None or not future_inputs.policy_changes:
        return []
    projected = results[1:]
    sections: List[ChangeSection] = []
    seen: set = set()
    for change in sorted(future_inputs.policy_changes, key=lambda c: c.effective_date):
        # The same change entered through both input styles shows once.
        signature = (change.kind, change.effective_date, str(change.value))
        if signature in seen:
            continue
        seen.add(signature)
        at_or_after = [s for s in projected if s.date and s.date >= change.effective_date]
        if not at_or_after:
            continue
        eff = at_or_after[0]
        section = ChangeSection(effective_date=change.effective_date, year=eff.policy_year)
        if change.kind == PolicyChangeKind.FACE_AMOUNT:
            section.summary_lines.append(
                f"SPECIFIED AMOUNT CHANGE TO {_money(float(change.value))}")
        elif change.kind == PolicyChangeKind.DB_OPTION:
            new = str(change.value or "").upper()
            section.summary_lines.append(
                f"DEATH BENEFIT OPTION CHANGE TO OPTION {new} "
                f"({_DBO_DESCRIPTIONS.get(new, '')})")
        # Rider drops are not modeled — the rider set carries through.
        section.rider_lines = list(rider_lines)

        # Estimated regulatory limits as of the change (the engine recalcs
        # GLP/GSP/7-pay at the change month).
        eoy_states = [s for s in at_or_after if s.policy_year == eff.policy_year]
        eoy = eoy_states[-1] if eoy_states else eff
        if options.conform_to_tefra or True:  # limits are informational either way
            section.limit_lines = [
                f"GUIDELINE SINGLE = {_money(eff.gsp)}",
                f"LEVEL PREMIUM = {_money(eff.glp)}",
                f"LEVEL ACCUMULATION = {_money(eoy.accumulated_glp)}",
            ]
            if 1 <= eff.tamra_year <= 7 and eff.tamra_7pay_level > 0:
                section.limit_lines.append(f"7-PAY PREMIUM = {_money(eff.tamra_7pay_level)}")
                # A material change restarts the 7-pay test period — the state
                # before the change still carries the old window's start date.
                before = [s for s in projected if s.date and s.date < change.effective_date]
                prior_start = (before[-1] if before else results[0]).tamra_7pay_start_date
                new_start = eff.tamra_7pay_start_date
                if new_start is not None and new_start != prior_start:
                    section.limit_lines.append(
                        f"NEW 7-PAY PERIOD STARTS = {new_start.strftime('%m-%d-%Y')}")
        sections.append(section)
    return sections


# ── Riders / benefits ───────────────────────────────────────────────────────

def _rider_lines(policy: IllustrationPolicyData) -> List[str]:
    names: List[str] = []
    for ben in policy.benefits:
        key = (ben.benefit_type or "") + (ben.benefit_subtype or "")
        name = _BENEFIT_NAMES.get(key) or _BENEFIT_TYPE_NAMES.get(ben.benefit_type or "")
        if name and name not in names:
            names.append(name)
    for rider in policy.riders:
        if rider.is_active and "TERM RIDER" not in names:
            names.append("TERM RIDER")
    return names or ["NONE"]


# ── Main entry ──────────────────────────────────────────────────────────────

def build_ul_report(
    policy: IllustrationPolicyData,
    results: List[MonthlyState],
    options: Optional[IllustrationOptions] = None,
    future_inputs: Optional[IllustrationInputSet] = None,
    run_date: Optional[date] = None,
    guaranteed_results: Optional[List[MonthlyState]] = None,
) -> IllustrationReport:
    """Assemble the UL illustration report from a finished projection.

    ``guaranteed_results`` is the guaranteed-assumption run built from the
    current run's locked cash flows (core/guaranteed_projection.py); when
    omitted the guaranteed ledger columns render blank.
    """
    if options is None:
        options = IllustrationOptions()
    report = IllustrationReport(run_date=run_date)
    inforce = results[0] if results else MonthlyState()
    projected = results[1:]

    report.company_name = (
        "AMERICAN NATIONAL LIFE INSURANCE COMPANY OF NEW YORK"
        if (policy.company_code or "").strip() == "26"
        else "AMERICAN NATIONAL INSURANCE COMPANY"
    )
    prepared_name = (policy.insured_name or "").strip() or f"POLICY {policy.policy_number}"
    report.prepared_for = f"PREPARED FOR {prepared_name}"

    # ── Ledger + derived facts ──
    report.ledger, report.year_of_mec, report.termination_year = _annualize(
        policy, results, options)
    report.seven_pay_restarts = _seven_pay_restarts(results)
    for restart_year, _start in report.seven_pay_restarts:
        for row in report.ledger:
            if row.year == restart_year and "+" not in row.markers:
                row.markers = f"{row.markers} +".strip()
    if guaranteed_results:
        report.has_guaranteed_values = True
        report.guaranteed_termination_year = _fill_guaranteed_columns(
            report.ledger, guaranteed_results)

    # ── Values at maturity (only when the projection endows) ──
    last = projected[-1] if projected else None
    if last is not None and not last.lapsed and last.attained_age >= policy.maturity_age:
        maturity = LedgerRow(
            eoy_age=last.attained_age,
            year=last.policy_year,
            loan_balance=last.policy_debt,
            accum_value=last.av_end_of_month,
            surr_value=last.surrender_value,
            death_benefit=last.ending_db,
        )
        if guaranteed_results:
            guar_last = guaranteed_results[-1] if len(guaranteed_results) > 1 else None
            if (guar_last is None or guar_last.lapsed
                    or guar_last.attained_age < policy.maturity_age):
                maturity.guar_accum = maturity.guar_surr = maturity.guar_death = 0.0
            else:
                maturity.guar_accum = max(guar_last.av_end_of_month, 0.0)
                maturity.guar_surr = max(guar_last.surrender_value, 0.0)
                maturity.guar_death = max(guar_last.ending_db, 0.0)
        report.maturity_row = maturity

    # ── Cover ──
    valuation = policy.valuation_date or policy.issue_date
    report.as_of_date = valuation
    report.disclaimer_lines = [
        "THIS IS AN ILLUSTRATION ONLY. AN ILLUSTRATION IS NOT INTENDED TO PREDICT ACTUAL PERFORMANCE.",
        "ACTUAL RESULTS MAY DIFFER FROM THE ILLUSTRATED VALUES SHOWN IN THIS ILLUSTRATION AND MAY BE",
        "MORE OR LESS FAVORABLE. VALUES SET FORTH IN THE ILLUSTRATION ARE NOT GUARANTEED, EXCEPT FOR",
        "THOSE ITEMS CLEARLY LABELED AS GUARANTEED.",
    ]
    report.insured_lines = [line for line in [policy.insured_name] if line]
    rated = "RATED " if (policy.base_segment and policy.base_segment.table_rating > 0) else ""
    nicotine = (
        "NICOTINE USER"
        if (policy.rate_class or "").upper() in _NICOTINE_CLASSES
        else "NON-NICOTINE USER"
    )
    sex = {"M": "MALE", "F": "FEMALE"}.get((policy.rate_sex or "").upper(), "UNISEX")
    mode_label = _MODE_LABELS.get(policy.billing_frequency, "MONTHLY")
    issue_date_long = (
        f"{policy.issue_date:%B} {policy.issue_date.day}, {policy.issue_date.year}"
        if policy.issue_date else ""
    )
    as_of_short = valuation.strftime("%m-%d-%Y") if valuation else ""
    # Two-column cover block (RERUN page 1): identity on the left, the
    # CURRENT policy elements on the right. ("", "") rows are separators.
    report.policy_block = [
        (f"{'POLICY NUMBER:':<17}{policy.policy_number}",
         f"{'CURRENT SPECIFIED AMOUNT:':<27}${policy.face_amount:,.0f}"),
        ("",
         f"{'CURRENT PLAN OPTION:':<27}"
         f"{_DBO_DESCRIPTIONS.get((policy.db_option or 'A').upper(), '')}"),
        ("", ""),
        (f"{'ISSUE DATE:':<17}{issue_date_long}",
         f"{'CURRENT BILLING MODE:':<27}{mode_label}"),
        (f"{'ISSUE AGE:':<17}{policy.issue_age}",
         f"{'CURRENT BILLABLE PREMIUM:':<27}{_money(policy.modal_premium)}"),
        ("FLEXIBLE PREMIUM UNIVERSAL LIFE",
         f"{'ACTUAL PREMIUMS PAID:':<27}{_money(policy.premiums_paid_to_date)}"),
        (f"FORM {(policy.form_number or '').upper()}",
         f"{'':<27}(AS OF {as_of_short})" if as_of_short else ""),
        ("", ""),
        (f"ATTAINED AGE: {policy.attained_age}", ""),
        (f"SEX: {sex}", ""),
        (f"{'PREMIUM CLASS:':<17}{rated}{nicotine}", ""),
    ]
    if valuation:
        report.av_basis_line = (
            f"THIS ILLUSTRATION IS BASED ON AN ACCUMULATION VALUE OF "
            f"{_money(policy.account_value)} AS OF {valuation.strftime('%m/%d/%Y')}"
        )
    inforce_debt = (
        policy.regular_loan_principal + policy.regular_loan_accrued
        + policy.preferred_loan_principal + policy.preferred_loan_accrued
        + policy.variable_loan_principal + policy.variable_loan_accrued
    )
    if inforce_debt > 0.005:
        report.loan_basis_line = f"WITH A LOAN BALANCE OF {inforce_debt:,.2f}"

    has_loans = future_inputs is not None and any(
        t.kind == TransactionKind.LOAN and t.amount > 0
        for t in future_inputs.scheduled_transactions
    )
    has_wds = future_inputs is not None and any(
        t.kind == TransactionKind.WITHDRAWAL for t in future_inputs.dated_transactions
    )
    intro = "THE FOLLOWING PREMIUMS "
    if has_loans:
        intro += "AND LOANS "
    if has_wds:
        intro += "AND WITHDRAWALS "
    intro += "WERE REQUESTED IN PREPARING THIS ILLUSTRATION."
    report.request_intro = [intro]
    prem_restricted = any(r.markers and "*" in r.markers for r in report.ledger)
    if prem_restricted:
        report.request_intro.append(
            "HOWEVER IN THIS ILLUSTRATION PREMIUMS HAVE BEEN RESTRICTED BY THE GUIDELINE "
            "PREMIUM LIMIT. THIS IS INDICATED IN THE LEDGER WHERE APPLICABLE.")
    report.request_lines = _request_lines(policy, results, future_inputs)

    report.rider_lines = _rider_lines(policy)
    report.change_sections = _change_sections(
        policy, results, future_inputs, report.rider_lines, options)
    if report.year_of_mec is not None:
        report.mec_line = (
            f"THIS ILLUSTRATION SHOWS THE POLICY WILL BECOME A MEC IN YEAR {report.year_of_mec}"
        )

    # ── Footnote legends (only the triggered ones) ──
    legends: List[str] = []
    markers = "".join(r.markers for r in report.ledger)
    if "*" in markers:
        legends.append(
            "* PREMIUMS IN THIS YEAR WERE RESTRICTED BY THE GUIDELINE PREMIUM LIMIT TO "
            "MAINTAIN DEFINITION OF LIFE INSURANCE")
    if "@" in markers:
        legends.append(
            "@ PREMIUMS WERE FORCED OUT OF THE POLICY TO MAINTAIN LIFE INSURANCE PREMIUM "
            "LIMITS. ANY POLICY DEBT WILL BE REDUCED BEFORE ACCOUNT VALUE")
    if "^" in markers:
        legends.append(
            "^ THESE PREMIUMS INCLUDE GUIDELINE EXCEPTION PREMIUMS. SEE GUIDELINE EXCEPTION "
            "PREMIUM SECTION FOR MORE DETAILS")
    if "&" in markers:
        legends.append("& THE POLICY IS FORECASTED TO BECOME A MEC DURING THIS YEAR")
    if "%" in markers:
        legends.append(
            "% ACCORDING TO THE CONTRACT, THE DEATH BENEFIT AFTER MATURITY IS EQUAL TO THE "
            "SURRENDER VALUE")
    for _year, start in report.seven_pay_restarts:
        legends.append(
            f"+ A NEW 7-PAY PREMIUM TEST PERIOD STARTS ON {start.strftime('%m-%d-%Y')} "
            "DUE TO A MATERIAL POLICY CHANGE")
    report.footnote_legends = legends

    # ── Notes page ──
    guaranteed_rate = policy.guaranteed_interest_rate or 0.0
    illustrated_rate = projected[0].annual_interest_rate if projected else 0.0
    bonus_months = [s for s in projected if s.bonus_interest_rate > 0]
    termination = (
        f"TERMINATE IN POLICY YEAR {report.termination_year}"
        if report.termination_year is not None
        else "REMAIN INFORCE FOR ALL YEARS SHOWN"
    )
    if report.has_guaranteed_values:
        guaranteed_termination = (
            f"UNDER GUARANTEED ACCUMULATION VALUE, YOUR POLICY WILL TERMINATE IN "
            f"POLICY YEAR {report.guaranteed_termination_year}."
            if report.guaranteed_termination_year is not None
            else "UNDER GUARANTEED ACCUMULATION VALUE, YOUR POLICY WILL REMAIN "
                 "INFORCE FOR ALL YEARS SHOWN."
        )
    else:
        guaranteed_termination = "GUARANTEED VALUES ARE NOT PROJECTED IN THIS ILLUSTRATION."
    report.note_paragraphs = [
        ["NON-GUARANTEED VALUES AND BENEFITS ARE BASED ON ASSUMPTIONS WHICH ARE SUBJECT TO "
         "CHANGE BY THE INSURER.",
         "ACTUAL RESULTS MAY BE MORE OR LESS FAVORABLE."],
        ["GUARANTEED ASSUMPTIONS",
         "",
         f"FOR GUARANTEED PROJECTED VALUES, THE ILLUSTRATION ASSUMES A GUARANTEED INTEREST "
         f"RATE OF {_pct(guaranteed_rate)},",
         "GUARANTEED COST OF INSURANCE CHARGES, AND GUARANTEED MONTHLY EXPENSES.",
         guaranteed_termination],
        ["NON-GUARANTEED ASSUMPTIONS",
         "",
         f"FOR NON-GUARANTEED PROJECTED VALUES, THE ILLUSTRATION ASSUMES AN ILLUSTRATED "
         f"INTEREST RATE OF {_pct(illustrated_rate)}"
         + (" PLUS A BONUS*" if bonus_months else ""),
         "NON-GUARANTEED COST OF INSURANCE CHARGES, AND NON-GUARANTEED MONTHLY EXPENSES.",
         f"UNDER NON-GUARANTEED ACCUMULATION VALUE, YOUR POLICY WILL {termination}. THIS "
         "ILLUSTRATION ASSUMES",
         "THAT THE CURRENTLY ILLUSTRATED NON-GUARANTEED ELEMENTS USED WILL NOT CHANGE FOR "
         "ALL YEARS SHOWN. THIS IS NOT",
         "LIKELY TO OCCUR, AND ACTUAL RESULTS WILL BE MORE OR LESS FAVORABLE THAN SHOWN. IF "
         "THE ACTUAL POLICY VALUES",
         "DEVELOPED OVER TIME ARE LESS THAN THOSE ILLUSTRATED IN THE NON-GUARANTEED SECTION, "
         "YOU MAY BE REQUIRED TO PAY",
         "ADDITIONAL PREMIUMS TO KEEP THE COVERAGE INFORCE TO THE ILLUSTRATED DATE, OR THE "
         "ACCUMULATION VALUE IN THE",
         "POLICY MAY BE LESS THAN ILLUSTRATED."],
        ["CASH FROM POLICY AND LOAN BALANCE VALUES ARE DETERMINED BY VALUES USING "
         "NON-GUARANTEED ASSUMPTIONS"],
        ["CHARGES CONTINUE TO BE PAID USING NON-GUARANTEED VALUES IF PREMIUM PAYMENTS ARE "
         "OF LESSER",
         "AMOUNTS OR SHORTER DURATION THAN THE PREMIUM NEEDED TO GUARANTEE BENEFITS UNDER "
         "THE POLICY.",
         "DEPENDING ON ACTUAL RESULTS, THE PREMIUM PAYER MAY NEED TO CONTINUE OR RESUME "
         "PREMIUM OUTLAY."],
        ["NON-GUARANTEED ELEMENTS CAN BE USED TO BUILD GREATER SURRENDER VALUES AND BENEFITS",
         "OR THEY CAN BE USED TO REDUCE PREMIUM OUTLAY OR SHORTEN THE PREMIUM PAYING PERIOD."],
    ]
    if bonus_months:
        first_bonus_year = bonus_months[0].policy_year
        report.note_paragraphs.append([
            f"*CURRENTLY THIS PLAN HAS A BONUS OF {bonus_months[0].bonus_interest_rate * 100:.3f}% "
            f"WHICH IS ADDED TO THE ILLUSTRATED RATE STARTING IN POLICY YEAR {first_bonus_year}"])

    if any(s.gp_exception_prem > 0 for s in projected):
        report.exception_section = [
            "GUIDELINE EXCEPTION PREMIUM",
            "",
            "IRC SECTION 7702(F)(6) STATES THAT IF THE MAXIMUM PREMIUM LIMITATION (DEFINED IN "
            "7702) HAS BEEN EXCEEDED AND YOUR",
            "POLICY HAS NO CASH VALUE THEN ADDITIONAL PREMIUMS ARE ALLOWED TO KEEP THE POLICY "
            "INFORCE. HOWEVER, UNDER",
            "THIS SECTION THE POLICY WILL NEVER BE ALLOWED TO BUILD ACCOUNT VALUE IN THE "
            "FUTURE AND YOU WILL ONLY BE ALLOWED",
            "TO PAY JUST ENOUGH TO COVER MONTHLY DEDUCTIONS. THESE PREMIUMS ARE KNOWN AS "
            "GUIDELINE EXCEPTION PREMIUMS.",
        ]

    # ── Regulatory limits (as of the valuation date) ──
    if policy.is_gpt:
        report.regulatory_lines = [
            f"GUIDELINE SINGLE = {_money(inforce.gsp)}",
            f"LEVEL PREMIUM = {_money(inforce.glp)}",
            f"LEVEL ACCUMULATION = {_money(inforce.accumulated_glp)}",
        ]
        if 1 <= inforce.tamra_year <= 7 and policy.tamra_7pay_level > 0:
            report.regulatory_lines.append(
                f"7-PAY PREMIUM = {_money(policy.tamra_7pay_level)}")
            if policy.tamra_7pay_start_date:
                report.regulatory_lines.append(
                    f"7-PAY START DATE = {policy.tamra_7pay_start_date.strftime('%m-%d-%Y')}")
    return report
