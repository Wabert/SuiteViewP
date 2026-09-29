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
    '#' premiums repaid loans,
    '+' a new 7-pay test period starts (TAMRA material change).
    (RERUN's '%' post-maturity marker/legend was dropped 2026-07-19: the
    ledger now ends at the maturity-age EOY row, with no post-maturity stub
    row and no contract-specific after-maturity DB wording.)
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
from textwrap import wrap
from typing import Dict, List, Optional

from suiteview.illustration.core.lapse import issue_no_lapse_years
from suiteview.illustration.core.mec import seven_pay_limit_exceeded
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    PolicyChangeKind,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.polview.models.cl_polrec.policy_translations import rate_class_description
from suiteview.illustration.core.report_specs import ReportFacts, ReportSectionSpec, RequestLineSpec
from suiteview.illustration.models.index_strategies import (
    FIXED_FUND_ID,
    MARKET_INDEX_BY_FUND,
    SWEEP_FUND_ID,
    compound_yield,
    historical_credited_rate,
    is_iul_plan,
    load_index_strategies,
    with_current_index_data,
)


# ── Display maps ────────────────────────────────────────────────────────────

_DBO_DESCRIPTIONS = {
    "A": "A - Level Death Benefit",
    "B": "B - Increasing Death Benefit",
    "C": "C - Return of Premium DB",
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
    "#4": "ACCELERATED RIDER TERMINAL ILLNESS",
    "#5": "ACCELERATED RIDER CRITICAL ILLNESS",
    "#6": "ACCELERATED RIDER CHRONIC ILLNESS",
}
_BENEFIT_TYPE_NAMES = {
    "U": "COST OF LIVING ADJUSTMENT BENEFIT",
    "A": "CONTINUOUS COVERAGE RIDER",
    "1": "ACCIDENTAL DEATH BENEFIT",
    "3": "PREMIUM WAIVER",
    "4": "STIPULATED PREMIUM WAIVER",
    "7": "GUARANTEED INCREASE OPTION",
}


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


ISSUE_OUTPUT_LABEL = "NEW BUSINESS - FROM ISSUE"
ROLLBACK_OUTPUT_LABEL = "VALUE ROLLBACK - HISTORICAL INFORCE BASIS"


def rollback_output_basis(policy: IllustrationPolicyData) -> List[str]:
    """Identify recorded starting values separately from forward assumptions."""
    when = getattr(policy, "rollback_date", None)
    manual_lines = [
        line
        for assumption in policy.starting_basis_assumptions
        for line in wrap(assumption, width=108)
    ]
    if when is None:
        if not manual_lines:
            return []
        return [
            "CURRENT INFORCE BASIS - MANUAL STARTING ASSUMPTIONS",
            f"VALUES AS OF: {policy.valuation_date:%m/%d/%Y}",
            "LOADED CURRENT VALUATION WITH EXPLICIT SCENARIO EDITS; SOURCE POLICY IS UNCHANGED.",
            "OTHER BALANCES AND TAX LIMITS RETAIN THE LOADED BASIS.",
            *manual_lines,
        ]
    if policy.rollback_requires_shadow_value:
        raise ValueError("Enter a historical shadow amount before producing rollback projection outputs.")
    source = policy.rollback_source_date
    source_text = source.strftime("%m/%d/%Y") if source else "NOT PROVIDED"
    return [
        ROLLBACK_OUTPUT_LABEL,
        f"VALUES AS OF: {when:%m/%d/%Y} | LOADED VALUATION DATE: {source_text}",
        (
            "MANUAL POST-DEDUCTION AV; FORWARD PROJECTION, NOT A HISTORICAL TRANSACTION REPLAY."
            if policy.starting_account_value_is_manual else
            "RECORDED POST-DEDUCTION AV; FORWARD PROJECTION, NOT A HISTORICAL TRANSACTION REPLAY."
        ),
        "SPECIFIED AMOUNTS AND DEATH-BENEFIT OPTION ARE REVIEWABLE STARTING-BASIS ASSUMPTIONS.",
        "TAX LIMITS USE SELECTED STARTING ASSUMPTIONS; MANUAL EDITS DO NOT RECONSTRUCT HISTORICAL TAX ADJUSTMENTS.",
        *[
            line
            for limitation in policy.rollback_limitations
            for line in wrap(limitation, width=108)
        ],
        *manual_lines,
    ]


def rollback_output_conditions(policy: IllustrationPolicyData) -> List[tuple]:
    historical = policy.rollback_date is not None
    if not historical and not policy.starting_basis_assumptions:
        return []
    return [
        ("Rollback valuation date" if historical else "Current valuation date",
         policy.valuation_date.isoformat()),
        ("Modeled specified amount", policy.face_amount),
        ("Modeled death-benefit option", policy.db_option),
        ("Opening account value", policy.account_value),
        ("Premiums paid through rollback" if historical else "Loaded premiums paid",
         policy.premiums_paid_to_date),
        ("Opening cost basis", policy.cost_basis),
        ("Historical shadow account value" if historical else "Opening shadow account value",
         policy.shadow_account_value),
        ("Rollback accumulated GLP" if historical else "Loaded accumulated GLP", policy.accumulated_glp),
        ("Rollback accumulated MTP" if historical else "Loaded accumulated MTP", policy.accumulated_mtp),
        *[
            (f"Coverage {segment.coverage_phase} specified amount", segment.face_amount)
            for segment in [*policy.segments, *policy.riders]
        ],
        *[
            (
                f"Benefit {benefit.coverage_phase}/{benefit.benefit_type}/"
                f"{benefit.benefit_subtype} amount",
                benefit.benefit_amount,
            )
            for benefit in policy.benefits
        ],
    ]


def issue_output_basis(policy: IllustrationPolicyData) -> List[str]:
    """Output identity for a hypothetical issue run, never historical balances."""
    if not policy.run_from_issue:
        return []
    issue = policy.issue_date.strftime("%m/%d/%Y") if policy.issue_date else "NOT PROVIDED"
    basis = (
        policy.illustration_date.strftime("%m/%d/%Y")
        if policy.illustration_date else "NOT PROVIDED"
    )
    return [
        ISSUE_OUTPUT_LABEL,
        f"ORIGINAL ISSUE DATE: {issue} | RATES BASIS DATE: {basis}",
        "CURRENT ILLUSTRATED INTEREST AND CURRENT SCALE 1; NOT A HISTORICAL RECONSTRUCTION.",
        "GUARANTEED VALUES USE CONTRACTUAL GUARANTEED ASSUMPTIONS.",
        f"NO LAPSE PERIOD: {_issue_lapse_period_text(policy)}; AV LESS LOANS, THEN NORMAL LAPSE RULES.",
        "THE LAPSE OVERRIDE IS A MODELING CONVENIENCE ON BOTH SIDES, NOT A CONTRACTUAL GUARANTEE.",
    ]


def _issue_lapse_period_text(policy: IllustrationPolicyData) -> str:
    years = policy.issue_no_lapse_years
    if years is None:
        try:
            years = issue_no_lapse_years(policy, load_plancode(policy.plancode))
        except Exception:
            years = None
    return f"{years:g} YEARS" if years is not None else "PLAN SAFETY-NET PERIOD (DEFAULT)"


def issue_output_conditions(policy: IllustrationPolicyData) -> List[tuple]:
    """Edited issue conditions carried by the modeled policy, not the live record."""
    if not policy.run_from_issue:
        return []
    rows = [
        ("Modeled specified amount", policy.face_amount),
        ("Modeled DB option", _DBO_DESCRIPTIONS.get(policy.db_option, policy.db_option)),
        ("No Lapse Period", _issue_lapse_period_text(policy)),
        ("Lapse basis", "AV less loans during period; normal rules afterward. Modeling convenience on both sides."),
    ]
    for rider in policy.riders:
        if rider.is_active:
            rows.append((
                "Included rider",
                f"Phase {rider.coverage_phase}: {rider.description or 'TERM RIDER'} "
                f"({rider.plancode}); face {_money(rider.face_amount)}",
            ))
    for benefit in policy.benefits:
        if benefit.is_active:
            code = (benefit.benefit_type or "") + (benefit.benefit_subtype or "")
            name = _BENEFIT_NAMES.get(code) or _BENEFIT_TYPE_NAMES.get(
                benefit.benefit_type or "", "BENEFIT")
            rows.append((
                "Included benefit",
                f"Phase {benefit.coverage_phase}: {name} ({code})",
            ))
    if not any(r.is_active for r in policy.riders) and not any(b.is_active for b in policy.benefits):
        rows.append(("Included riders / benefits", "NONE"))
    return rows


# ── Report structure ────────────────────────────────────────────────────────

@dataclass
class LedgerRow:
    """One policy year of the report ledger (RERUN mLedgerKey + Current)."""

    eoy_age: int = 0                # age at END of policy year (issue_age + year)
    year: int = 0
    premium_outlay: float = 0.0
    markers: str = ""               # '* @ ^ & # +' combination for the year
    cash_from_policy: float = 0.0   # Gross withdrawals + new loans + force-outs
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
class ExpenseRow:
    """One policy year of the supplemental Expense Report (RERUN "Expense
    Report" sheet, columns J:Y). Charges/credits are annual sums of the
    month's values; policy values are end-of-year. Years at or past the
    current-basis termination year render as zeros (the sheet's inforce
    flag ``I = year < sTerminationYear``).

    The rendered page keeps Premium Charge (N) as its own column and
    collapses the remaining expense components (P, Q, R, S) plus any partial
    surrender charges assessed on withdrawals into one combined
    EXPENSES/FEES column (``expenses``). It also adds a POLICY DEBT column
    (not on the RERUN sheet; same EOY loan balance the annual ledger shows).
    The components stay granular here for tests and future use."""

    year: int = 0                       # J — End of Year (policy year)
    eoy_age: int = 0                    # K — age at END of policy year (issue_age + year)
    premium_outlay: float = 0.0         # L — Σ vPremiumOutlay
    distributions: float = 0.0          # M — Σ gross withdrawals + force-outs
    premium_charge: float = 0.0         # N — Σ vTotalPremLoad
    coi_charge: float = 0.0             # O — Σ vTotalCOICharge − Σ vRiderBenefitCharge (base COI)
    per_unit_charge: float = 0.0        # P — Σ vTotalEPU (per-1000 monthly charge)
    monthly_fee: float = 0.0            # Q — Σ vMFee
    asset_charge: float = 0.0           # R — Σ vAssetCharge (IUL segment asset charge)
    av_charge: float = 0.0              # S — Σ vAVCharge (% of accumulation value)
    rider_charges: float = 0.0          # T — Σ vRiderBenefitCharge (benefit + rider charges)
    interest_credited: float = 0.0      # U — Σ vTotalInterest
    accum_value: float = 0.0            # V — EOY vIllustrationAV
    surrender_charges: float = 0.0      # W — EOY vFullSC
    net_surrender_value: float = 0.0    # X — EOY vIllustrationSV
    net_death_benefit: float = 0.0      # Y — EOY vIllustrationDB
    # Not on the RERUN sheet: EOY policy debt (principal + accrued), the same
    # value the annual ledger's LOAN BALANCE column shows (MonthlyState.policy_debt).
    policy_debt: float = 0.0
    @property
    def expenses(self) -> float:
        """Combined EXPENSES/FEES page column: per-1000 charge + monthly fee +
        segment asset charge + AV charge (sheet cols P+Q+R+S)."""
        return (self.per_unit_charge + self.monthly_fee + self.asset_charge
                + self.av_charge)


@dataclass
class ChangeSection:
    """Per-policy-change block (cover summary + page-4 estimated limits)."""

    effective_date: Optional[date] = None
    year: int = 0
    summary_lines: List[str] = field(default_factory=list)
    rider_lines: List[str] = field(default_factory=list)
    limit_lines: List[str] = field(default_factory=list)


@dataclass
class IULFundValueRow:
    fund_id: str = ""
    label: str = ""
    value: float = 0.0


@dataclass
class IULAllocationRow:
    fund_id: str = ""
    label: str = ""
    allocation: float = 0.0


@dataclass
class IULStrategyRateRow:
    fund_id: str = ""
    label: str = ""
    illustrated_rate: Optional[float] = None
    market_index: str = ""
    parameters: Dict[str, float] = field(default_factory=dict)


@dataclass
class IULHistoricalRow:
    date_eoy: Optional[date] = None
    market_returns: Dict[str, float] = field(default_factory=dict)
    credited_rates: Dict[str, float] = field(default_factory=dict)


@dataclass
class IULCompoundYieldRow:
    years: int = 0
    market_returns: Dict[str, float] = field(default_factory=dict)
    credited_rates: Dict[str, float] = field(default_factory=dict)


@dataclass
class IllustrationReport:
    company_name: str = ""
    title: str = "FLEXIBLE PREMIUM UNIVERSAL LIFE INSURANCE HYPOTHETICAL INFORCE ILLUSTRATION"
    subtitle: str = ""
    prepared_for: str = ""
    run_date: Optional[date] = None
    run_from_issue: bool = False
    basis_lines: List[str] = field(default_factory=list)

    # Identity used for default output filenames (policy number - plancode).
    policy_number: str = ""
    plancode: str = ""

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
    loan_repayments_illustrated: bool = False
    # Supplemental Expense Report rows (RERUN "Expense Report" J:Y) — always
    # built; the Report tab appends the page only when the user opts in.
    expense_rows: List[ExpenseRow] = field(default_factory=list)
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

    # IUL-only report sections.
    is_iul: bool = False
    iul_fund_values: List[IULFundValueRow] = field(default_factory=list)
    iul_allocations: List[IULAllocationRow] = field(default_factory=list)
    iul_strategy_rates: List[IULStrategyRateRow] = field(default_factory=list)
    iul_fixed_rate: Optional[float] = None
    iul_benchmark_minimum: Optional[float] = None
    iul_benchmark_maximum: Optional[float] = None
    iul_historical_rows: List[IULHistoricalRow] = field(default_factory=list)
    iul_compound_yields: List[IULCompoundYieldRow] = field(default_factory=list)


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

    maturity_age = int(policy.maturity_age or 121)
    year_of_mec: Optional[int] = next(
        (state.mec_year for state in projected if state.mec_year > 0), None)
    termination_year: Optional[int] = None
    rows: List[LedgerRow] = []
    for year in sorted(by_year):
        months = by_year[year]
        # A policy year that BEGINS at/after the maturity age is the engine's
        # post-maturity stub (the anniversary month that endows the policy).
        # The printed ledger ends at the year whose EOY age is the maturity
        # age; the stub is dropped entirely — nothing extra renders at maturity.
        if months[0].attained_age >= maturity_age:
            continue
        eoy = months[-1]
        outlay = sum(
            m.premium_outlay + m.applied_loan_repayment
            for m in months
        )
        forceout = sum(m.guideline_forceout for m in months)
        exception = sum(m.gp_exception_prem for m in months)
        withdrawals = sum(m.gross_withdrawal for m in months)
        loans = sum(m.applied_new_loan for m in months)
        guideline_capped = any(m.premium_capped_by_guideline for m in months)
        tamra_capped = any(m.premium_capped_by_tamra for m in months)

        # MEC: 7-pay contributions exceed level x year inside the window
        # (only reachable with TAMRA conformance off, or an already-MEC load).
        if year_of_mec is None:
            for m in months:
                if seven_pay_limit_exceeded(m):
                    year_of_mec = year
                    break

        lapsed = any(month.lapsed for month in months)
        if termination_year is None and lapsed:
            termination_year = year

        markers = ""
        if guideline_capped and exception <= 0.005:
            markers += "* "
        if tamra_capped and exception <= 0.005:
            markers += "# "
        if forceout > 0.005:
            markers += "@ "
        if exception > 0.005:
            markers += "^ "
        if year_of_mec == year:
            markers += "& "
        rows.append(LedgerRow(
            # EOY age: the age the insured reaches at the END of the policy year
            # (issue_age + year). The engine's attained_age holds the age at the
            # anniversary that BEGAN the year (issue_age + year - 1).
            eoy_age=eoy.attained_age + 1,
            year=year,
            premium_outlay=outlay,
            markers=markers.strip(),
            cash_from_policy=withdrawals + loans + forceout,
            loan_balance=eoy.policy_debt,
            accum_value=eoy.av_end_of_month,
            surr_value=eoy.ending_sv,
            death_benefit=0.0 if lapsed else eoy.ending_db,
            lapsed=lapsed,
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
        if state.is_mec:
            previous = state.tamra_7pay_start_date
            continue
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
    lapsed_years: set[int] = set()
    termination_year: Optional[int] = None
    for state in guaranteed_results[1:]:
        by_year[state.policy_year] = state
        if state.lapsed:
            lapsed_years.add(state.policy_year)
        if termination_year is None and state.lapsed:
            termination_year = state.policy_year
    for row in rows:
        eoy = by_year.get(row.year)
        if eoy is None or row.year in lapsed_years:
            row.guar_accum = 0.0
            row.guar_surr = 0.0
            row.guar_death = 0.0
        else:
            row.guar_accum = max(eoy.av_end_of_month, 0.0)
            row.guar_surr = max(eoy.ending_sv, 0.0)
            row.guar_death = max(eoy.ending_db, 0.0)
    return termination_year


# ── Expense Report rows (RERUN "Expense Report" sheet, columns J:Y) ─────────

def _expense_rows(
    results: List[MonthlyState],
    termination_year: Optional[int],
    maturity_age: int,
) -> List[ExpenseRow]:
    """Fold the projection into the Expense Report's per-year J:Y columns.

    Mirrors the sheet exactly: charge/credit columns are SUMs of the year's
    monthly values, policy-value columns are the end-of-year snapshot, and a
    year at or past the termination year renders all-zero (the sheet's
    ``I = year < sTerminationYear`` inforce flag zeroes the whole row). The
    engine's post-maturity stub year is skipped, matching the annual ledger.
    """
    projected = results[1:]
    by_year: dict[int, List[MonthlyState]] = {}
    for state in projected:
        by_year.setdefault(state.policy_year, []).append(state)

    rows: List[ExpenseRow] = []
    for year in sorted(by_year):
        months = by_year[year]
        if months[0].attained_age >= maturity_age:
            continue
        eoy = months[-1]
        # eoy_age is the END-of-year age (issue_age + year); attained_age holds
        # the beginning-of-year age (issue_age + year - 1).
        row = ExpenseRow(year=year, eoy_age=eoy.attained_age + 1)
        if termination_year is None or year < termination_year:
            row.premium_outlay = sum(m.premium_outlay for m in months)
            row.distributions = sum(
                m.gross_withdrawal + m.guideline_forceout
                for m in months)
            row.premium_charge = sum(m.total_premium_load for m in months)
            row.coi_charge = sum(m.total_coi_charge for m in months)
            row.per_unit_charge = sum(m.epu_charge for m in months)
            row.monthly_fee = sum(m.mfee_charge for m in months)
            row.asset_charge = sum(m.asset_charge for m in months)
            row.av_charge = sum(m.av_charge for m in months)
            row.rider_charges = sum(m.benefit_charges + m.rider_charges for m in months)
            row.interest_credited = sum(m.interest_credited for m in months)
            row.accum_value = max(eoy.av_end_of_month, 0.0)
            row.surrender_charges = eoy.surrender_charge
            row.net_surrender_value = max(eoy.ending_sv, 0.0)
            row.net_death_benefit = max(eoy.ending_db, 0.0)
            row.policy_debt = eoy.policy_debt
        rows.append(row)
    return rows


# ── Requested premium / loan / withdrawal lines ─────────────────────────────

_INTERVAL_MODE_LABELS = {1: "MONTHLY", 3: "QUARTERLY", 6: "SEMI-ANNUAL", 12: "ANNUAL"}


def _request_lines_from_specs(
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

    # Monthly Deduction premium years: the premium is solved in-engine each
    # month (grossed-up monthly deduction, varying monthly), so the cover
    # describes it without a dollar amount. ``md_premium_mode`` is the engine's
    # per-month marker for that premium type — never inferred from amounts.
    # Consecutive years compress into one range per run.
    md_runs: List[List[int]] = []
    for state in projected:
        if not state.md_premium_mode:
            continue
        if md_runs and state.policy_year <= md_runs[-1][1] + 1:
            md_runs[-1][1] = max(md_runs[-1][1], state.policy_year)
        else:
            md_runs.append([state.policy_year, state.policy_year])

    premium_entries: List[tuple[int, str]] = []
    for run in runs:
        label = _INTERVAL_MODE_LABELS.get(run["interval"])
        if label is None:
            label = schedule_modes.get(run["start_year"], billed_label)
        span = (
            f"FOR POLICY YEARS {run['start_year']} THROUGH {run['end_year']}"
            if run["end_year"] != run["start_year"]
            else f"IN POLICY YEAR {run['start_year']}"
        )
        premium_entries.append(
            (run["start_year"], f"{label} PREMIUM OF {_money(run['amount'])} {span}"))
    for start_year, end_year in md_runs:
        span = (
            f"FOR POLICY YEARS {start_year} THROUGH {end_year}"
            if end_year != start_year
            else f"IN POLICY YEAR {start_year}"
        )
        premium_entries.append(
            (start_year, f"PREMIUMS TO COVER MONTHLY DEDUCTIONS {span}"))
    if not premium_entries:
        first_year = projected[0].policy_year
        last_year = projected[-1].policy_year
        span = (
            f"FOR POLICY YEARS {first_year} THROUGH {last_year}"
            if last_year != first_year
            else f"IN POLICY YEAR {first_year}"
        )
        premium_entries.append(
            (first_year, f"{billed_label} PREMIUM OF {_money(0.0)} {span}"))
    premium_entries.sort(key=lambda entry: entry[0])
    lines: List[str] = [text for _year, text in premium_entries]

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
    loan_runs: List[dict] = []
    for index, sched in enumerate(loan_schedules):
        if sched.amount <= 0:
            continue
        end = (
            loan_schedules[index + 1].policy_year - 1
            if index + 1 < len(loan_schedules)
            else maturity_year
        )
        mode = _SCHEDULE_MODE_LABELS.get((sched.mode or "A").strip().upper(), "ANNUAL")
        loan_runs.append({
            "start_year": sched.policy_year,
            "end_year": end,
            "amount": round(sched.amount, 2),
            "mode": mode,
            "loan_type": str(sched.metadata.get("loan_type", "fixed")).upper(),
        })

    issue = policy.issue_date
    dated_loan_runs: dict[tuple[str, str, float], List[int]] = {}
    forecast_loans: List[DatedTransaction] = []
    for tx in future_inputs.dated_transactions:
        if tx.kind != TransactionKind.LOAN or tx.amount <= 0 or issue is None:
            continue
        if tx.metadata.get("forecast_date_transaction"):
            forecast_loans.append(tx)
            continue
        months = (tx.effective_date.year - issue.year) * 12 + (
            tx.effective_date.month - issue.month)
        year = months // 12 + 1
        mode = _SCHEDULE_MODE_LABELS.get(
            str(tx.metadata.get("mode", "A")).strip().upper(), "ANNUAL")
        loan_type = str(tx.metadata.get("loan_type", "fixed")).upper()
        key = (mode, loan_type, round(tx.amount, 2))
        dated_loan_runs.setdefault(key, []).append(year)

    for (mode, loan_type, amount), years in dated_loan_runs.items():
        start_year = min(years)
        end_year = max(years)
        matching = next(
            (
                run for run in loan_runs
                if run["mode"] == mode
                and run["loan_type"] == loan_type
                and run["amount"] == amount
                and end_year + 1 >= run["start_year"]
            ),
            None,
        )
        if matching is not None:
            matching["start_year"] = min(matching["start_year"], start_year)
            matching["end_year"] = max(matching["end_year"], end_year)
        else:
            loan_runs.append({
                "start_year": start_year,
                "end_year": end_year,
                "amount": amount,
                "mode": mode,
                "loan_type": loan_type,
            })

    for run in sorted(loan_runs, key=lambda item: item["start_year"]):
        span = (
            f"FOR POLICY YEARS {run['start_year']} THROUGH {run['end_year']}"
            if run["end_year"] != run["start_year"]
            else f"IN POLICY YEAR {run['start_year']}"
        )
        lines.append(
            f"{run['mode']} {run['loan_type']} LOAN OF "
            f"{_money(run['amount'])} {span}")
    for tx in sorted(forecast_loans, key=lambda item: item.effective_date):
        loan_type = str(tx.metadata.get("loan_type", "fixed")).upper()
        lines.append(
            f"ONE-TIME {loan_type} LOAN OF {_money(tx.amount)} "
            f"ON {tx.effective_date.strftime('%m/%d/%Y')}")

    # Loan repayments are exported as dated modal transactions. Group equal
    # per-payment amounts across consecutive policy years into one assumption.
    repayment_years: dict[tuple[str, float], set[int]] = {}
    for tx in future_inputs.dated_transactions:
        if tx.kind != TransactionKind.LOAN_REPAYMENT or tx.amount <= 0 or issue is None:
            continue
        months = (tx.effective_date.year - issue.year) * 12 + (
            tx.effective_date.month - issue.month)
        year = months // 12 + 1
        mode = _SCHEDULE_MODE_LABELS.get(
            str(tx.metadata.get("mode", "A")).strip().upper(), "ANNUAL")
        repayment_years.setdefault((mode, round(tx.amount, 2)), set()).add(year)

    for (mode, amount), years in sorted(
        repayment_years.items(), key=lambda item: min(item[1])
    ):
        ordered_years = sorted(years)
        start_year = end_year = ordered_years[0]
        runs: List[tuple[int, int]] = []
        for year in ordered_years[1:]:
            if year == end_year + 1:
                end_year = year
            else:
                runs.append((start_year, end_year))
                start_year = end_year = year
        runs.append((start_year, end_year))
        for start_year, end_year in runs:
            span = (
                f"FOR POLICY YEARS {start_year} THROUGH {end_year}"
                if end_year != start_year
                else f"IN POLICY YEAR {start_year}"
            )
            lines.append(
                f"{mode} LOAN REPAYMENT OF {_money(amount)} {span}")

    # Withdrawals: dated, one line per year (AY22..AY27).
    wd_by_year: dict[tuple[int, str], float] = {}
    forecast_withdrawals: List[DatedTransaction] = []
    for tx in future_inputs.dated_transactions:
        if tx.kind != TransactionKind.WITHDRAWAL or issue is None:
            continue
        if tx.metadata.get("forecast_date_transaction"):
            forecast_withdrawals.append(tx)
            continue
        months = (tx.effective_date.year - issue.year) * 12 + (tx.effective_date.month - issue.month)
        year = months // 12 + 1
        mode = _SCHEDULE_MODE_LABELS.get(
            str(tx.metadata.get("mode", "A")).strip().upper(), "ANNUAL")
        key = (year, mode)
        wd_by_year[key] = wd_by_year.get(key, 0.0) + tx.amount
    for year, mode in sorted(wd_by_year):
        lines.append(
            f"{mode} WITHDRAWAL OF {_money(wd_by_year[(year, mode)])} "
            f"IN POLICY YEAR {year}")
    for tx in sorted(forecast_withdrawals, key=lambda item: item.effective_date):
        basis = "GROSS" if tx.subtype == "gross" else "NET"
        lines.append(
            f"ONE-TIME {basis} WITHDRAWAL OF {_money(tx.amount)} "
            f"ON {tx.effective_date.strftime('%m/%d/%Y')}")
    return lines


def _request_lines(
    policy: IllustrationPolicyData,
    results: List[MonthlyState],
    future_inputs: Optional[IllustrationInputSet],
) -> List[str]:
    """Interpret request-line specs without changing report text."""

    spec = RequestLineSpec(
        collect=lambda p, r, f: _request_lines_from_specs(p, r, f),
        group="requested_activity",
    )
    return spec.render(policy, results, future_inputs)


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
    # Changes that land on the same effective date share a single section so the
    # cover page and regulatory page each show one block per date.
    by_date: dict = {}
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
        section = by_date.get(change.effective_date)
        if section is None:
            section = ChangeSection(effective_date=change.effective_date, year=eff.policy_year)
            by_date[change.effective_date] = section
            sections.append(section)
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
        # GLP/GSP/7-pay at the change month). All changes on a given date share
        # the same as-of state, so the limits are computed once per date.
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
                if not eff.is_mec and new_start is not None and new_start != prior_start:
                    section.limit_lines.append(
                        f"NEW 7-PAY PERIOD STARTS = {new_start.strftime('%m/%d/%Y')}")
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
        if not rider.is_active:
            continue
        name = rider.description or "TERM RIDER"
        if name not in names:
            names.append(name)
    return names or ["NONE"]


# ── IUL-only report data ─────────────────────────────────────────────────────

_IUL_FUND_ORDER = ("IX", "IF", "IS", "IC", "IP", "IR", "NX", "M1")
_IUL_REPORT_LABELS = {
    "SW": "SWEEP ACCOUNT",
    "U1": "FIXED ACCOUNT",
    "IX": "S&P 500 INDEX ONE YEAR POINT TO POINT WITH A CAP AND 0% FLOOR",
    "IF": "S&P 500 INDEX ONE YEAR POINT TO POINT UNCAPPED WITH INTEREST SPREAD",
    "IS": "S&P 500 INDEX ONE YEAR POINT TO POINT WITH A SPECIFIED RATE",
    "IC": "S&P 500 INDEX ONE YEAR POINT TO POINT WITH A CAP AND 1.5% FLOOR",
    "IP": "S&P 500 INDEX STRATEGY WITH LOW MULTIPLIER",
    "IR": "S&P 500 INDEX STRATEGY WITH HIGH MULTIPLIER",
    "NX": "NASDAQ-100 INDEX ONE YEAR POINT TO POINT WITH A CAP",
    "M1": "S&P MARC 5 INDEX ONE YEAR POINT TO POINT WITH PARTICIPATION",
}


def _normalized_report_allocations(raw: Dict[str, float]) -> Dict[str, float]:
    allocations = {
        str(fund_id).strip().upper(): float(value or 0.0)
        for fund_id, value in (raw or {}).items()
    }
    if sum(allocations.values()) > 1.5:
        allocations = {
            fund_id: value / 100.0 for fund_id, value in allocations.items()
        }
    return allocations


def _build_iul_sections_from_specs(
    report: IllustrationReport,
    policy: IllustrationPolicyData,
) -> None:
    catalog = load_index_strategies(policy.plancode)
    if catalog is None:
        return
    plan = with_current_index_data(
        catalog,
        policy.index_illustration_rates,
        policy.index_strategy_parameters,
    )
    offered = {
        strategy.fund_id: strategy
        for strategy in plan.strategies
        if strategy.is_offered
    }
    ordered_funds = [
        fund_id
        for fund_id in (FIXED_FUND_ID, *_IUL_FUND_ORDER)
        if fund_id in offered
    ]

    report.is_iul = True
    report.subtitle = "WITH INDEXED INTEREST CREDITING OPTION"

    fund_values = {
        str(fund_id).strip().upper(): float(value or 0.0)
        for fund_id, value in (policy.fund_values or {}).items()
    }
    value_order = [SWEEP_FUND_ID, *ordered_funds]
    value_order.extend(
        fund_id
        for fund_id, value in fund_values.items()
        if fund_id not in value_order and abs(value) > 0.005
    )
    value_funds = [
        fund_id
        for fund_id in value_order
        if abs(fund_values.get(fund_id, 0.0)) > 0.005
    ]
    report.iul_fund_values = [
        IULFundValueRow(
            fund_id=fund_id,
            label=_IUL_REPORT_LABELS.get(fund_id, f"FUND {fund_id}"),
            value=fund_values.get(fund_id, 0.0),
        )
        for fund_id in value_funds
    ]

    allocations = _normalized_report_allocations(policy.premium_allocations)
    report.iul_allocations = [
        IULAllocationRow(
            fund_id=fund_id,
            label=_IUL_REPORT_LABELS.get(fund_id, offered[fund_id].label.upper()),
            allocation=allocations.get(fund_id, 0.0),
        )
        for fund_id in ordered_funds
    ]

    parameters = policy.index_strategy_parameters or {}
    report.iul_strategy_rates = [
        IULStrategyRateRow(
            fund_id=fund_id,
            label=_IUL_REPORT_LABELS.get(fund_id, offered[fund_id].label.upper()),
            illustrated_rate=offered[fund_id].max_rate,
            market_index=MARKET_INDEX_BY_FUND[fund_id],
            parameters=dict(parameters.get(fund_id, {})),
        )
        for fund_id in _IUL_FUND_ORDER
        if fund_id in offered
    ]
    fixed_strategy = offered.get(FIXED_FUND_ID)
    report.iul_fixed_rate = (
        policy.iul_declared_rate
        if policy.iul_declared_rate is not None
        else fixed_strategy.max_rate if fixed_strategy is not None else None
    ) if allocations.get(FIXED_FUND_ID, 0.0) > 0.00005 else None
    report.iul_benchmark_minimum = policy.index_benchmark_minimum
    report.iul_benchmark_maximum = policy.index_benchmark_maximum

    if not report.iul_strategy_rates:
        return

    raw_market_returns = policy.index_market_returns
    if raw_market_returns is None:
        return
    if not raw_market_returns or not parameters:
        raise ValueError(
            "IUL historical lookback data is missing market returns or strategy parameters."
        )

    required_markets = list(dict.fromkeys(
        row.market_index for row in report.iul_strategy_rates
    ))
    market_values: Dict[str, Dict[date, float]] = {}
    last_full_year = (
        (policy.illustration_date or date.today()).year - 1
    )
    for market_index in required_markets:
        entries = raw_market_returns.get(market_index)
        if not entries:
            raise ValueError(
                f"IUL historical lookback has no returns for {market_index}."
            )
        values: Dict[date, float] = {}
        for entry in entries:
            raw_date = entry["date"]
            date_eoy = (
                raw_date
                if isinstance(raw_date, date)
                else date.fromisoformat(str(raw_date)[:10])
            )
            if date_eoy.year <= last_full_year:
                values[date_eoy] = float(entry["return"])
        market_values[market_index] = values

    selected_dates = [
        date(year, 12, 31)
        for year in range(last_full_year - 19, last_full_year + 1)
    ]
    if any(
        not set(selected_dates).issubset(values)
        for values in market_values.values()
    ):
        raise ValueError(
            "IUL historical lookback requires 20 complete calendar years "
            "for every relevant market index."
        )

    for strategy in report.iul_strategy_rates:
        if strategy.fund_id not in parameters:
            raise ValueError(
                f"IUL historical lookback has no parameters for fund {strategy.fund_id}."
            )

    for date_eoy in selected_dates:
        row = IULHistoricalRow(
            date_eoy=date_eoy,
            market_returns={
                market_index: market_values[market_index][date_eoy]
                for market_index in required_markets
            },
        )
        row.credited_rates = {
            strategy.fund_id: historical_credited_rate(
                strategy.fund_id,
                row.market_returns[strategy.market_index],
                parameters[strategy.fund_id],
            )
            for strategy in report.iul_strategy_rates
        }
        report.iul_historical_rows.append(row)

    for years in (5, 10, 15, 20):
        period = report.iul_historical_rows[-years:]
        report.iul_compound_yields.append(IULCompoundYieldRow(
            years=years,
            market_returns={
                market_index: compound_yield([
                    row.market_returns[market_index] for row in period
                ])
                for market_index in required_markets
            },
            credited_rates={
                strategy.fund_id: compound_yield([
                    row.credited_rates[strategy.fund_id] for row in period
                ])
                for strategy in report.iul_strategy_rates
            },
        ))


def _build_iul_sections(
    report: IllustrationReport,
    policy: IllustrationPolicyData,
) -> None:
    """Interpret the IUL section spec."""
    ReportSectionSpec(
        name="iul_sections",
        collect=_build_iul_sections_from_specs,
    ).render(report, policy)



# ── Main entry ──────────────────────────────────────────────────────────────

def _build_ul_report_from_facts(
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
    report = IllustrationReport(
        run_date=run_date,
        run_from_issue=policy.run_from_issue,
        basis_lines=issue_output_basis(policy) + rollback_output_basis(policy),
    )
    if policy.run_from_issue:
        report.title = "FLEXIBLE PREMIUM UNIVERSAL LIFE INSURANCE HYPOTHETICAL ILLUSTRATION"
    inforce = results[0] if results else MonthlyState()
    projected = results[1:]

    report.company_name = (
        "AMERICAN NATIONAL LIFE INSURANCE COMPANY OF NEW YORK"
        if (policy.company_code or "").strip() == "26"
        else "AMERICAN NATIONAL INSURANCE COMPANY"
    )
    prepared_name = (policy.insured_name or "").strip() or f"POLICY {policy.policy_number}"
    report.prepared_for = f"PREPARED FOR {prepared_name}"
    report.policy_number = (policy.policy_number or "").strip()
    report.plancode = (getattr(policy, "plancode", "") or "").strip()
    report.is_iul = is_iul_plan(report.plancode)

    # ── Ledger + derived facts ──
    report.ledger, report.year_of_mec, report.termination_year = _annualize(
        policy, results, options)
    report.loan_repayments_illustrated = any(
        state.applied_loan_repayment > 0.005 for state in projected
    )
    if future_inputs is not None:
        report.loan_repayments_illustrated = (
            report.loan_repayments_illustrated
            or any(
                tx.kind == TransactionKind.LOAN_REPAYMENT and tx.amount > 0.005
                for tx in future_inputs.dated_transactions
            )
            or any(
                tx.kind == TransactionKind.LOAN_REPAYMENT and tx.amount > 0.005
                for tx in future_inputs.scheduled_transactions
            )
        )
    report.expense_rows = _expense_rows(
        results, report.termination_year, int(policy.maturity_age or 121))
    report.seven_pay_restarts = _seven_pay_restarts(results)
    for restart_year, _start in report.seven_pay_restarts:
        for row in report.ledger:
            if row.year == restart_year and "+" not in row.markers:
                row.markers = f"{row.markers} +".strip()
    if guaranteed_results:
        report.has_guaranteed_values = True
        report.guaranteed_termination_year = _fill_guaranteed_columns(
            report.ledger, guaranteed_results)

    # Nothing extra happens at maturity: the ledger simply ends at the
    # maturity-age EOY row. (No VALUES AT MATURITY strip — removed 2026-07-19.)

    # ── Cover ──
    valuation = (
        policy.issue_date if policy.run_from_issue
        else policy.valuation_date or policy.issue_date
    )
    report.as_of_date = valuation
    report.disclaimer_lines = [
        "THIS IS AN ILLUSTRATION ONLY. AN ILLUSTRATION IS NOT INTENDED TO PREDICT ACTUAL PERFORMANCE.",
        "ACTUAL RESULTS MAY DIFFER FROM THE ILLUSTRATED VALUES SHOWN IN THIS ILLUSTRATION AND MAY BE",
        "MORE OR LESS FAVORABLE. VALUES SET FORTH IN THE ILLUSTRATION ARE NOT GUARANTEED, EXCEPT FOR",
        "THOSE ITEMS CLEARLY LABELED AS GUARANTEED.",
    ]
    if report.is_iul:
        report.disclaimer_lines.extend([
            "INDEXED INTEREST RATES AND VALUES ARE NOT GUARANTEED. THE POLICY IS NOT A STOCK "
            "MARKET INVESTMENT AND DOES NOT DIRECTLY PARTICIPATE IN ANY STOCK OR INDEX.",
        ])
    report.insured_lines = [line for line in [policy.insured_name] if line]
    joint = policy.base_segment.joint_lives if policy.base_segment else None

    def premium_class(rate_class: str, is_rated: bool) -> str:
        code = (rate_class or "").upper()
        desc = rate_class_description(code, policy.plancode).upper()
        if not desc:
            desc = "NICOTINE USER" if code in _NICOTINE_CLASSES else "NON-NICOTINE USER"
        return f"{'RATED ' if is_rated else ''}{desc}"

    def sex_text(code: str) -> str:
        return {"M": "MALE", "F": "FEMALE"}.get((code or "").upper(), "UNISEX")

    def joint_rated(person: str) -> bool:
        return any(r.person == person and r.type_code in ("0", "1", "3") for r in joint.ratings)

    primary_rated = (
        joint_rated("00") if joint is not None
        else bool(policy.base_segment and policy.base_segment.table_rating > 0))
    class_text = premium_class(policy.rate_class, primary_rated)
    sex = sex_text(policy.rate_sex)
    if report.is_iul:
        product_line = "INDEXED UNIVERSAL LIFE"
    elif joint is not None:
        product_line = "JOINT SURVIVOR FLEXIBLE PREMIUM UNIVERSAL LIFE"
    else:
        product_line = "FLEXIBLE PREMIUM UNIVERSAL LIFE"
    mode_label = _MODE_LABELS.get(policy.billing_frequency, "MONTHLY")
    issue_date_long = (
        f"{policy.issue_date:%B} {policy.issue_date.day}, {policy.issue_date.year}"
        if policy.issue_date else ""
    )
    as_of_short = valuation.strftime("%m/%d/%Y") if valuation else ""
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
        (product_line,
         f"{'ACTUAL PREMIUMS PAID:':<27}{_money(policy.premiums_paid_to_date)}"),
        (f"FORM {(policy.form_number or '').upper()}",
         f"{'':<27}(AS OF {as_of_short})" if as_of_short else ""),
        ("", ""),
        (f"ATTAINED AGE: {policy.attained_age}", ""),
        (f"SEX: {sex}", ""),
        (f"{'PREMIUM CLASS:':<17}{class_text}", ""),
    ]
    if joint is not None:
        joint_age = joint.joint.issue_age + policy.attained_age - joint.primary.issue_age
        report.policy_block += [
            ("", ""),
            (f"JOINT INSURED ATTAINED AGE: {joint_age}", ""),
            (f"SEX: {sex_text(joint.joint.sex)}", ""),
            (f"{'PREMIUM CLASS:':<17}"
             f"{premium_class(joint.joint.rate_class, joint_rated('01'))}", ""),
        ]
    if policy.run_from_issue:
        replacements = {
            "CURRENT SPECIFIED AMOUNT:": "MODELED SPECIFIED AMOUNT:",
            "CURRENT PLAN OPTION:": "MODELED PLAN OPTION:",
            "CURRENT BILLING MODE:": "MODELED PREMIUM MODE:",
            "CURRENT BILLABLE PREMIUM:": "MODELED PREMIUM:",
            "ACTUAL PREMIUMS PAID:": "OPENING PREMIUMS PAID:",
        }
        report.policy_block = [
            (left, next(
                (f"{new:<27}{right[27:]}" for old, new in replacements.items()
                 if right.startswith(old)), right,
            ))
            for left, right in report.policy_block
        ]
        report.av_basis_line = (
            f"MODELED ISSUE OPENING ACCUMULATION VALUE: {_money(policy.account_value)} "
            f"BEFORE ISSUE-DATE ACTIVITY ({as_of_short}). "
            "THE TECHNICAL PRE-ISSUE ROW IS NOT AN INFORCE OR HISTORICAL BALANCE."
        )
    elif valuation and report.is_iul:
        report.av_basis_line = (
            f"THE ACCUMULATION VALUE OF {_money(policy.account_value)} CONSISTS OF "
            "THE FOLLOWING ACCOUNTS:"
        )
    elif valuation:
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
        report.loan_basis_line = (
            f"MODELED OPENING LOAN BALANCE: {inforce_debt:,.2f}"
            if policy.run_from_issue
            else f"WITH A LOAN BALANCE OF {inforce_debt:,.2f}"
        )

    guideline_restricted = any("*" in r.markers for r in report.ledger)
    tamra_restricted = any("#" in r.markers for r in report.ledger)
    intro = "THE FOLLOWING ACTIVITY WAS REQUESTED IN PREPARING THIS ILLUSTRATION."
    if guideline_restricted and tamra_restricted:
        intro += (
            " HOWEVER, PREMIUMS MAY BE RESTRICTED BY GUIDELINE OR 7-PAY PREMIUM LIMITS.")
    elif guideline_restricted:
        intro += " HOWEVER, PREMIUMS MAY BE RESTRICTED BY GUIDELINE PREMIUM LIMITS."
    elif tamra_restricted:
        intro += " HOWEVER, PREMIUMS MAY BE RESTRICTED BY 7-PAY PREMIUM LIMITS."
    report.request_intro = [intro]
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
    if "#" in markers:
        legends.append(
            "# PREMIUMS IN THIS YEAR WERE RESTRICTED BY THE 7-PAY PREMIUM LIMIT TO "
            "PREVENT THE POLICY FROM BECOMING A MEC")
    if "@" in markers:
        legends.append(
            "@ PREMIUMS WERE FORCED OUT OF THE POLICY TO MAINTAIN LIFE INSURANCE PREMIUM "
            "LIMITS. ANY POLICY DEBT WILL BE REDUCED BEFORE ACCOUNT VALUE")
    if "^" in markers:
        legends.append(
            "^ THESE PREMIUMS INCLUDE GUIDELINE EXCEPTION PREMIUMS. SEE GUIDELINE EXCEPTION "
            "PREMIUM SECTION FOR MORE DETAILS")
    if "&" in markers:
        legends.append("& THE POLICY IS ILLUSTRATED TO BECOME A MEC IN THIS YEAR")
    for _year, start in report.seven_pay_restarts:
        legends.append(
            f"+ A NEW 7-PAY PREMIUM TEST PERIOD STARTS ON {start.strftime('%m/%d/%Y')} "
            "DUE TO A MATERIAL POLICY CHANGE")
    report.footnote_legends = legends

    # ── Notes page ──
    guaranteed_rate = policy.guaranteed_interest_rate or 0.0
    illustrated_rate = projected[0].annual_interest_rate if projected else 0.0
    bonus_months = [s for s in projected if s.bonus_interest_rate > 0]
    # The bonus is stated inline in the non-guaranteed assumptions sentence
    # (no separate footnote): "... PLUS A BONUS OF X% WHICH IS ADDED TO THE
    # ILLUSTRATED RATE STARTING IN POLICY YEAR N".
    bonus_clause = ""
    if bonus_months:
        bonus_clause = (
            f" PLUS A BONUS OF {bonus_months[0].bonus_interest_rate * 100:.3f}% "
            f"WHICH IS ADDED TO THE ILLUSTRATED RATE STARTING IN POLICY YEAR "
            f"{bonus_months[0].policy_year}")
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
        ["PREMIUM OUTLAY, PROCEEDS AND LOAN BALANCE VALUES ARE DETERMINED BY "
         "VALUES USING NON-GUARANTEED ASSUMPTIONS"],
        ["GUARANTEED ASSUMPTIONS",
         "",
         f"FOR GUARANTEED PROJECTED VALUES, THE ILLUSTRATION ASSUMES A GUARANTEED INTEREST "
         f"RATE OF {_pct(guaranteed_rate)},",
         "GUARANTEED COST OF INSURANCE CHARGES, AND GUARANTEED MONTHLY EXPENSES.",
         guaranteed_termination],
        ["NON-GUARANTEED ASSUMPTIONS",
         "",
         "NON-GUARANTEED VALUES AND BENEFITS ARE BASED ON ASSUMPTIONS WHICH ARE SUBJECT TO "
         "CHANGE BY THE INSURER.",
         "ACTUAL RESULTS MAY BE MORE OR LESS FAVORABLE.",
         f"FOR NON-GUARANTEED PROJECTED VALUES, THE ILLUSTRATION ASSUMES AN ILLUSTRATED "
         f"INTEREST RATE OF {_pct(illustrated_rate)}{bonus_clause},",
         "NON-GUARANTEED COST OF INSURANCE CHARGES, AND NON-GUARANTEED MONTHLY EXPENSES.",
         "",
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
        ["CHARGES CONTINUE TO BE PAID USING NON-GUARANTEED VALUES IF PREMIUM PAYMENTS ARE "
         "OF LESSER",
         "AMOUNTS OR SHORTER DURATION THAN THE PREMIUM NEEDED TO GUARANTEE BENEFITS UNDER "
         "THE POLICY.",
         "DEPENDING ON ACTUAL RESULTS, THE PREMIUM PAYER MAY NEED TO CONTINUE OR RESUME "
         "PREMIUM OUTLAY."],
        ["NON-GUARANTEED ELEMENTS CAN BE USED TO BUILD GREATER SURRENDER VALUES AND BENEFITS",
         "OR THEY CAN BE USED TO REDUCE PREMIUM OUTLAY OR SHORTEN THE PREMIUM PAYING PERIOD."],
    ]

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
        seven_pay_level = inforce.tamra_7pay_level or policy.tamra_7pay_level
        if 1 <= inforce.tamra_year <= 7 and seven_pay_level > 0:
            report.regulatory_lines.append(
                f"7-PAY PREMIUM = {_money(seven_pay_level)}")
            if policy.tamra_7pay_start_date:
                report.regulatory_lines.append(
                    f"7-PAY START DATE = {policy.tamra_7pay_start_date.strftime('%m/%d/%Y')}")
    else:
        seven_pay_level = inforce.tamra_7pay_level or policy.tamra_7pay_level
    if policy.is_cvat and 1 <= inforce.tamra_year <= 7 and seven_pay_level > 0:
        # CVAT policies have no GLP/GSP guideline limits, but a 7-pay premium
        # still applies while the policy is inside its 7-pay period.
        report.regulatory_lines = [
            f"7-PAY PREMIUM = {_money(seven_pay_level)}",
        ]
        if policy.tamra_7pay_start_date:
            report.regulatory_lines.append(
                f"7-PAY START DATE = {policy.tamra_7pay_start_date.strftime('%m/%d/%Y')}")
    if report.is_iul:
        _build_iul_sections(report, policy)
    return report


def build_ul_report(
    policy: IllustrationPolicyData,
    results: List[MonthlyState],
    options: Optional[IllustrationOptions] = None,
    future_inputs: Optional[IllustrationInputSet] = None,
    run_date: Optional[date] = None,
    guaranteed_results: Optional[List[MonthlyState]] = None,
) -> IllustrationReport:
    """Interpret ``ReportFacts`` into the byte-identical UL report."""
    return ReportFacts(
        policy=policy,
        results=results,
        options=options,
        future_inputs=future_inputs,
        run_date=run_date,
        guaranteed_results=guaranteed_results,
    ).interpret(_build_ul_report_from_facts)
