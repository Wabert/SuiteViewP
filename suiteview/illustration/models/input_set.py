from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional

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

    def is_empty(self) -> bool:
        return all(value is None for value in self.__dict__.values())


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


@dataclass
class IllustrationOptions:
    """Per-run illustration toggles (mirror the RERUN sINPUT_* booleans).

    These are set once before a forecast runs and control the 7702 guideline
    machinery. Defaults match a normal "as-is" inforce illustration: guideline
    and TAMRA limits enforced, exception premium off.
    """

    # sINPUT_TEFRA_Force — enforce the 7702 guideline premium limit. Drives both
    # guideline force-out and premium capping at acceptance.
    conform_to_tefra: bool = True

    # sINPUT_TAMRA_Force — enforce the 7-pay (TAMRA/MEC) premium limit.
    conform_to_tamra: bool = True

    # sINPUT_AllowExceptionPrems — allow GP exception premium past the safety-net
    # period to keep the policy alive once it is sitting at the guideline limit.
    allow_exception_prems: bool = False

    # sINPUT_LevelizingPremium — when a premium cap binds, spread the allowed
    # premium evenly across the year's modal payments instead of billing each
    # payment in full until the annual room runs out mid-year. Off by default
    # (matches the RERUN workbook default); ignored on a policy that carries a
    # loan. See ``core/premium_allowance.py`` (CalcEngine NV..NZ).
    levelizing_premium: bool = False

    # None keeps the plancode interest method. True/False force exact-days or
    # monthly compounding for what-if illustration runs.
    exact_days_interest: Optional[bool] = None

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

    # sInput_ApplyPremToLoan — apply the requested premium to repay the policy
    # loan FIRST, only loading what remains onto the account value. The lumpsum
    # (unscheduled) deposit repays first, then the scheduled modal premium, each
    # capped at the loan payoff; the rest becomes premium. Off by default — a
    # normal illustration loads premium straight to the account value. See
    # ``core/loan_handler.repay_loan`` (CalcEngine MH/MI) and
    # ``core/premium_allowance.py`` (NL/NY).
    apply_prem_to_loan: bool = False

    # Internal escape hatch: a consumer can keep force-out on while still letting
    # injected premiums intentionally exceed the guideline (no acceptance cap).
    # None -> derive from conform_to_tefra. Used by the PolView GLP solver, which
    # solves a premium that is allowed to breach the guideline.
    cap_premiums_at_acceptance: Optional[bool] = None

    @property
    def force_out_enabled(self) -> bool:
        return self.conform_to_tefra

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