from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from math import isfinite
from typing import Any, List, Optional, Tuple

from .policy_data import IllustrationPolicyData


class TransactionKind(str, Enum):
    PREMIUM = "premium"
    LOAN = "loan"
    LOAN_REPAYMENT = "loan_repayment"
    WITHDRAWAL = "withdrawal"


class PolicyChangeKind(str, Enum):
    DB_OPTION = "db_option"
    FACE_AMOUNT = "face_amount"
    RATE_CLASS = "rate_class"
    RIDER_DROP = "rider_drop"
    SUBSTANDARD = "substandard"


@dataclass
class ScheduledTransaction:
    """Recurring transaction defined by policy year rather than an absolute date."""

    kind: TransactionKind
    policy_year: int
    amount: float
    mode: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DatedTransaction:
    """One-time dated transaction such as an unscheduled premium or withdrawal."""

    kind: TransactionKind
    effective_date: date
    amount: float
    subtype: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyChangeEvent:
    """One-time dated policy state change to apply before a projection month runs."""

    kind: PolicyChangeKind
    effective_date: date
    value: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InforceOverrideSet:
    """Optional valuation-date overrides applied once before projection begins."""

    account_value: Optional[float] = None
    face_amount: Optional[float] = None
    db_option: Optional[str] = None
    rate_class: Optional[str] = None
    regular_loan_principal: Optional[float] = None
    regular_loan_accrued: Optional[float] = None
    preferred_loan_principal: Optional[float] = None
    preferred_loan_accrued: Optional[float] = None
    variable_loan_principal: Optional[float] = None
    variable_loan_accrued: Optional[float] = None
    current_interest_rate: Optional[float] = None
    sweep_account_min: Optional[float] = None   # IUL sweep retained minimum
    # IUL crediting inputs from the allocations panel (None on declared-rate
    # plans): the fixed-strategy illustrated rate (WAIR declared rate, RERUN
    # UJ) and the blended asset-charge rate (RERUN SU).
    iul_declared_rate: Optional[float] = None
    iul_asset_charge_rate: Optional[float] = None
    premium_allocations: Optional[dict[str, float]] = None
    index_illustration_rates: Optional[dict[str, float]] = None

    def is_empty(self) -> bool:
        return all(value is None for value in self.__dict__.values())


@dataclass
class IssueOverrideSet:
    """New-business conditions; never applied to the inforce policy basis."""

    face_amount: float | None = None
    db_option: str | None = None
    no_lapse_years: float | None = None
    excluded_rider_phases: list[int] = field(default_factory=list)
    excluded_benefit_keys: list[tuple[int, str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class RecordFieldSpec:
    label: str
    kind: str = "amount"
    nullable: bool = False


RECORD_FIELD_SPECS = {
    "premium_pay_status_code": RecordFieldSpec("Premium-paying status", "status"),
    "premiums_ytd": RecordFieldSpec("Premiums YTD"),
    "premiums_paid_to_date": RecordFieldSpec("Premiums paid to date"),
    "withdrawals_to_date": RecordFieldSpec("Withdrawals to date"),
    "accumulated_mtp": RecordFieldSpec("Accumulated MTP"),
    "map_cease_date": RecordFieldSpec("MAP cease date", "date", nullable=True),
    "mtp": RecordFieldSpec("Monthly MTP"),
    "ctp": RecordFieldSpec("Commission target premium"),
    "cost_basis": RecordFieldSpec("Cost basis"),
    "is_mec": RecordFieldSpec("MEC", "bool"),
    "tamra_7pay_start_date": RecordFieldSpec("7-pay start date", "date", nullable=True),
    "tamra_7pay_cash_value": RecordFieldSpec("7-pay cash value"),
    "tamra_7pay_level": RecordFieldSpec("7-pay level premium"),
    "tamra_7year_lowest_db": RecordFieldSpec("7-pay lowest death benefit"),
    "glp": RecordFieldSpec("GLP"),
    "gsp": RecordFieldSpec("GSP"),
    "accumulated_glp": RecordFieldSpec("Accumulated GLP"),
    "regular_loan_principal": RecordFieldSpec("Regular loan principal"),
    "regular_loan_accrued": RecordFieldSpec("Regular loan accrued interest"),
    "preferred_loan_principal": RecordFieldSpec("Preferred loan principal"),
    "preferred_loan_accrued": RecordFieldSpec("Preferred loan accrued interest"),
    "variable_loan_principal": RecordFieldSpec("Variable loan principal"),
    "variable_loan_accrued": RecordFieldSpec("Variable loan accrued interest"),
    "regular_loan_charge_rate": RecordFieldSpec("Regular loan charge rate", "rate"),
    "preferred_loan_charge_rate": RecordFieldSpec("Preferred loan charge rate", "rate"),
    "variable_loan_charge_rate": RecordFieldSpec("Variable loan charge rate", "rate"),
}


def record_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite numeric value.")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be a finite numeric value.") from exc
    if not isfinite(number):
        raise ValueError(f"{label} must be a finite numeric value.")
    return number


def validate_tamra_contributions(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 7:
        raise ValueError("7-pay contributions must contain exactly seven numeric amounts.")
    return [record_number(amount, f"7-pay contribution year {index + 1}")
            for index, amount in enumerate(value)]


def validate_record_values(values: dict[str, Any], *, from_json: bool = False) -> dict[str, Any]:
    """Validate the closed editing surface; absent and explicitly cleared differ."""
    from suiteview.polview.models.cl_polrec.policy_translations import PREMIUM_PAY_STATUS_CODES

    if not isinstance(values, dict) or set(values) - RECORD_FIELD_SPECS.keys():
        raise ValueError("Edit Record contains unknown fields or malformed record values.")
    result = {}
    for name, value in values.items():
        spec = RECORD_FIELD_SPECS[name]
        if value is None and spec.nullable:
            result[name] = None
            continue
        if spec.kind == "date":
            if from_json and isinstance(value, str):
                try:
                    value = date.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError(f"{spec.label} must be an ISO date or null.") from exc
            if type(value) is not date:
                raise ValueError(f"{spec.label} must be a date or null.")
        elif spec.kind == "bool":
            if type(value) is not bool:
                raise ValueError(f"{spec.label} must be true or false.")
        elif spec.kind == "status":
            if not isinstance(value, str) or value not in PREMIUM_PAY_STATUS_CODES:
                raise ValueError("Premium-paying status must be a recognized two-digit status code.")
        else:
            value = record_number(value, spec.label)
            if spec.kind == "rate" and not 0 <= value <= 1:
                raise ValueError(f"{spec.label} must be a fraction between 0 and 1.")
        result[name] = value
    return result


@dataclass
class RollbackOverrideSet:
    """Applied current or historical valuation and manual starting-basis edits."""

    valuation_date: date
    coverage_amounts: dict[int, float] = field(default_factory=dict)
    benefit_amounts: dict[tuple[int, str, str], float] = field(default_factory=dict)
    db_option: str | None = None
    shadow_account_value: float | None = None
    account_value: float | None = None
    record_values: dict[str, Any] = field(default_factory=dict)
    tamra_7year_contributions: list[float] | None = None
    fund_values: dict[str, float] | None = None
    impaired_fund_values: dict[str, float] | None = None
    premium_allocations: dict[str, float] | None = None


@dataclass
class IllustrationInputSet:
    """Future-dated projection inputs normalized from the UI."""

    scheduled_transactions: list[ScheduledTransaction] = field(default_factory=list)
    dated_transactions: list[DatedTransaction] = field(default_factory=list)
    policy_changes: list[PolicyChangeEvent] = field(default_factory=list)

    def is_empty(self) -> bool:
        return (
            not self.scheduled_transactions
            and not self.dated_transactions
            and not self.policy_changes
        )


@dataclass(frozen=True)
class InterimOpening:
    """An opening account value rolled forward past the valuation monthliversary.

    ``as_of`` is the interim date the policy's account value is stated at;
    ``valuation_account_value`` is the monthliversary AV it was rolled from.
    """

    as_of: date
    valuation_account_value: float


@dataclass
class IllustrationOptions:
    """Per-run illustration toggles (mirror the RERUN sINPUT_* booleans).

    These are set once before a forecast runs and control the 7702 guideline
    machinery. Defaults match a normal "as-is" inforce illustration: guideline
    and TAMRA limits enforced, entry into a future exception period off.
    """

    # GLP-adjustment what-ifs set GLP to zero to solve funding, not to assert an
    # existing exception period. Ordinary inforce illustrations recognize it.
    recognize_inforce_exception_period: bool = True

    # sINPUT_TEFRA_Force — enforce the 7702 guideline premium limit. Drives both
    # guideline force-out and premium capping at acceptance.
    conform_to_tefra: bool = True

    # sINPUT_TAMRA_Force — enforce the 7-pay (TAMRA/MEC) premium limit.
    conform_to_tamra: bool = True

    # sINPUT_AllowExceptionPrems — allow GP exception premium past the safety-net
    # period to keep the policy alive once it is sitting at the guideline limit.
    allow_exception_prems: bool = False

    # Switch to Option A in the exception period — when an Option B policy enters
    # the GP exception period, re-run its monthly deduction + exception premium
    # under Option A (level death benefit) assumptions. This changes the COI
    # saving that discounts the exception premium (Option A gives the full COI
    # saving; Option B nearly washes it out). Off by default — the policy keeps
    # its own death-benefit option through the exception period unless opted in.
    switch_to_option_a_in_exception: bool = False

    # sINPUT_LevelizingPremium — when a premium cap binds, spread the allowed
    # premium evenly across the year's modal payments instead of billing each
    # payment in full until the annual room runs out mid-year. Off by default
    # (matches the RERUN workbook default); ignored on a policy that carries a
    # loan. See ``core/premium_allowance.py`` (CalcEngine NV..NZ).
    levelizing_premium: bool = False

    # Accept the scheduled premium dollar-for-dollar in the TRANSITION year — the
    # first policy year the GP guideline binds the level premium and the policy
    # tips into GP exception mode. That year's premium can never be level anyway
    # (it ends on exception premiums), so levelizing the freshly-opened annual
    # room across the modal payments only makes the billable premium oscillate
    # against the room for the rest of the year. When this is on, that one year
    # bills the scheduled premium in full (up to the annual guideline room) and
    # lets the MD / GP exception premium take over once the room is exhausted.
    # Off by default (normal runs keep RERUN levelizing); the Prem-to-Maturity
    # solve and its displayed run turn it on only when levelizing is off.
    # See ``core/premium_allowance.py``.
    dollar_for_dollar_in_transition_year: bool = False

    # None keeps the plancode interest method. True/False force exact-days or
    # monthly compounding for what-if illustration runs.
    exact_days_interest: Optional[bool] = None

    # Interim opening value: the policy's account value has been rolled forward
    # from the valuation monthliversary to ``interim_opening.as_of`` (strictly
    # before the next monthliversary), so the inforce month credits interest
    # only from then to the next monthliversary; the valuation month's deduction
    # is still calculated on the monthliversary account value. None credits the
    # whole valuation month.
    interim_opening: Optional[InterimOpening] = None

    # Find GP/TAMRA by Search Routine — solve GLP/GSP/7-pay by premium search
    # on the calc engine (guaranteed COIs, statutory interest floors, current
    # expenses) instead of the monthly commutation formula. Default off; the
    # two methods should agree closely except in edge cases such as multiple
    # base coverage segments.
    guideline_by_search: bool = False

    # sInput_RestrictLoansToSV — cap a new fixed loan at the lapse surrender
    # value (AV − surrender charge − existing debt, less the MD holdback).
    # The workbook default is ON: you cannot borrow past the surrender value.
    restrict_loans_to_sv: bool = True

    # Disable the lapse test entirely — the policy is never lapsed for failing
    # the safety-net (minimum premium), surrender-value, or AV-less-loans
    # tests, so the account value and surrender value may run negative and the
    # projection always reaches maturity. Set by the ABR Quote run, whose
    # theoretical premium solve must let the policy coast (negative) to its
    # first annual premium.
    no_lapse: bool = False

    # sInput_ApplyPremToLoan — apply the requested premium to repay the policy
    # loan FIRST, only loading what remains onto the account value. The lumpsum
    # (unscheduled) deposit repays first, then the scheduled modal premium, each
    # capped at the loan payoff; the rest becomes premium. Off by default — a
    # normal illustration loads premium straight to the account value. See
    # ``core/loan_handler.repay_loan`` (CalcEngine MH/MI) and
    # ``core/premium_allowance.py`` (NL/NY).
    apply_prem_to_loan: bool = False

    # Apply excess loan repayment as premium — when a loan repayment exceeds the
    # loan payoff, the excess (vLNRepayLeftOver / RERUN MY) is applied as premium
    # through the acceptance chain, picking up the premium load. Off by default:
    # repayments stop once the loan is repaid and the excess is discarded. (RERUN
    # always returns the leftover to the premium pool; this option gates it.)
    apply_excess_repayment_as_premium: bool = False

    # Pay Monthly Deduction premium — a per-month premium computed in-engine
    # right after the monthly deduction (it reuses the GP exception premium
    # machinery, just retargeted) that grosses the after-charge account value
    # back up to where it stood just before the deduction. Mutually exclusive
    # with allow_exception_prems (enforced in the inputs UI). See
    # ``_compute_exception_premium`` in ``core/calc_engine.py``.
    pay_monthly_deduction: bool = False

    # The policy-year windows the Monthly Deduction premium is paid over, each
    # ``(start_year, end_year)`` inclusive; ``end_year`` None runs that window to
    # maturity. ``None`` (with ``pay_monthly_deduction`` True) means the whole
    # projection from the forecast date — the plain "pay the deduction" case with
    # no bounding row. A Monthly Deduction premium row on the Input tab supplies a
    # bounded window (its start year through For Years / To Age); once the window
    # ends, later premium rows apply normally and the premium stops.
    monthly_deduction_windows: Optional[List[Tuple[int, Optional[int]]]] = None

    # "Billable to MD" premium windows, same shape as monthly_deduction_windows.
    # Within a window the row's scheduled billable premium pays normally until
    # the FIRST month the policy would otherwise fail its lapse test; from that
    # month on the billable premium stops (latched on MonthlyState.
    # billable_md_switched) and the Monthly Deduction premium takes over —
    # capped at the guideline room, with the GP exception premium as the
    # backstop once the room runs out. Models the owner who pays the bill until
    # the policy runs out of value, then pays whatever keeps it alive.
    billable_to_md_windows: Optional[List[Tuple[int, Optional[int]]]] = None

    # Earliest month the Billable-to-MD hand-off may latch. Set when a
    # "Lumpsum to Next Premium" bridge is layered in: the lumpsum only funds the
    # policy to its next modal premium, so the point of the run is to pay enough
    # to reach the regularly billable premium and then measure how long THAT
    # sustains the policy. Latching before the next premium is paid (while the
    # bridged AV sits near breakeven) would defeat that — so the switch probe is
    # suppressed for every month strictly before this date. None means no such
    # floor (the switch may latch from the first forecast month).
    billable_to_md_no_latch_before: Optional[date] = None

    # Internal escape hatch — NOT exposed in the UI (capping premiums at the
    # guideline room is part of Conform to TEFRA/DEFRA, which the Illustration
    # Control tab locks on). A programmatic consumer can keep force-out on while
    # still letting injected premiums intentionally exceed the guideline (no
    # acceptance cap). None -> derive from conform_to_tefra. Sole consumer:
    # PolView's GLP-exception solver (``polview/services/glp_exception.py``),
    # which solves a premium that is allowed to breach the guideline.
    cap_premiums_at_acceptance: Optional[bool] = None

    # IUL crediting method — False credits the single blended rate (RERUN INPUT
    # B52/E52, mirrored into current_interest_rate); True credits the Weighted
    # Average Interest Rate (RERUN CalcEngine TAV/WAIR block, columns US..VL),
    # implemented in ``core/iul_crediting.py`` and wired through
    # ``calc_engine.process_month`` (illustration timing).
    iul_wair_crediting: bool = False

    # Use the AG49 regime in effect at policy issue (RERUN Rates_Control CP79 =
    # MAX(2, issue-date tier)) instead of the current regime. Gates IP/IR
    # multiplier crediting and the asset charge (index ≤ 2) and selects the
    # variable-loan credit spread. The UI re-bases the allocation blend on the
    # resolved index; the engine resolves the same index for the asset charge
    # (SS..SX) and the variable-loan accrual spread (VV) — see
    # ``core/iul_crediting.build_iul_context``.
    use_policy_ag49_regime: bool = False

    # sAssumptionCode = 3 — this run is the guaranteed-basis projection. Set by
    # ``guaranteed_projection.guaranteed_options``; the only engine consumer is
    # the WAIR cap (RERUN VK caps vWAIR at the declared rate + bonus).
    guaranteed_assumption: bool = False

    # Internal comparison basis: suppress distributions without relaxing premium
    # acceptance caps, TEFRA/TAMRA or the GP exception machinery.
    guideline_forceouts: bool = True

    @property
    def force_out_enabled(self) -> bool:
        return self.conform_to_tefra and self.guideline_forceouts

    @property
    def guideline_cap_enabled(self) -> bool:
        if self.cap_premiums_at_acceptance is None:
            return self.conform_to_tefra
        return self.conform_to_tefra and self.cap_premiums_at_acceptance

    @property
    def tamra_cap_enabled(self) -> bool:
        return self.conform_to_tamra


@dataclass
class IllustrationScenario:
    """Projection scenario = baseline policy + optional overrides + future inputs."""

    base_policy: IllustrationPolicyData
    projectable_policy: IllustrationPolicyData
    inforce_overrides: InforceOverrideSet = field(default_factory=InforceOverrideSet)
    future_inputs: IllustrationInputSet = field(default_factory=IllustrationInputSet)
    run_from_issue: bool = False
    issue_overrides: IssueOverrideSet = field(default_factory=IssueOverrideSet)
    rollback_overrides: RollbackOverrideSet | None = None