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
class IllustrationScenario:
    """Projection scenario = baseline policy + optional overrides + future inputs."""

    base_policy: IllustrationPolicyData
    projectable_policy: IllustrationPolicyData
    inforce_overrides: InforceOverrideSet = field(default_factory=InforceOverrideSet)
    future_inputs: IllustrationInputSet = field(default_factory=IllustrationInputSet)