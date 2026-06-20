from __future__ import annotations

from dataclasses import dataclass

from dateutil.relativedelta import relativedelta

from suiteview.illustration.models.input_set import IllustrationInputSet, TransactionKind
from suiteview.illustration.models.policy_data import IllustrationPolicyData


@dataclass
class CompiledMonthInputs:
    """Resolved inputs for a single projection month."""

    scheduled_premium: float | None = None
    unscheduled_premium: float = 0.0
    premium_mode: str = ""
    regular_loan: float = 0.0
    variable_loan: float = 0.0
    loan_repayment: float = 0.0
    withdrawal: float = 0.0

    @property
    def total_premium(self) -> float | None:
        if self.scheduled_premium is None:
            if self.unscheduled_premium == 0.0:
                return None
            return self.unscheduled_premium
        return self.scheduled_premium + self.unscheduled_premium


def compile_month_inputs(
    policy: IllustrationPolicyData,
    input_set: IllustrationInputSet | None,
    months: int,
) -> dict[int, CompiledMonthInputs]:
    """Compile future inputs into month buckets keyed by projected duration."""
    if not input_set or input_set.is_empty() or months <= 0:
        return {}

    compiled = {
        policy.duration + offset: CompiledMonthInputs()
        for offset in range(1, months + 1)
    }

    _compile_scheduled_premiums(policy, input_set, months, compiled)
    _compile_scheduled_loans(policy, input_set, months, compiled)
    _compile_dated_transactions(policy, input_set, months, compiled)
    return compiled


def _compile_scheduled_premiums(
    policy: IllustrationPolicyData,
    input_set: IllustrationInputSet,
    months: int,
    compiled: dict[int, CompiledMonthInputs],
):
    premium_schedules = sorted(
        (entry for entry in input_set.scheduled_transactions if entry.kind == TransactionKind.PREMIUM),
        key=lambda entry: entry.policy_year,
    )
    if not premium_schedules:
        return

    for offset in range(1, months + 1):
        duration = policy.duration + offset
        policy_year = ((duration - 1) // 12) + 1
        policy_month = ((duration - 1) % 12) + 1
        schedule = _active_schedule_for_year(premium_schedules, policy_year)
        if schedule is None:
            continue
        compiled[duration].scheduled_premium = _scheduled_amount_for_month(schedule.amount, schedule.mode, policy_month)
        compiled[duration].premium_mode = schedule.mode or ""


def _compile_scheduled_loans(
    policy: IllustrationPolicyData,
    input_set: IllustrationInputSet,
    months: int,
    compiled: dict[int, CompiledMonthInputs],
):
    loan_schedules = sorted(
        (entry for entry in input_set.scheduled_transactions if entry.kind == TransactionKind.LOAN),
        key=lambda entry: entry.policy_year,
    )
    if not loan_schedules:
        return

    for offset in range(1, months + 1):
        duration = policy.duration + offset
        policy_year = ((duration - 1) // 12) + 1
        policy_month = ((duration - 1) % 12) + 1
        schedule = _active_schedule_for_year(loan_schedules, policy_year)
        if schedule is None:
            continue
        amount = _scheduled_amount_for_month(schedule.amount, schedule.mode, policy_month)
        if amount == 0.0:
            continue
        if (schedule.metadata or {}).get("loan_type") == "variable":
            compiled[duration].variable_loan += amount
        else:
            compiled[duration].regular_loan += amount


def _compile_dated_transactions(
    policy: IllustrationPolicyData,
    input_set: IllustrationInputSet,
    months: int,
    compiled: dict[int, CompiledMonthInputs],
):
    date_to_duration = {}
    for offset in range(1, months + 1):
        duration = policy.duration + offset
        month_date = policy.issue_date + relativedelta(months=duration - 1)
        date_to_duration[month_date] = duration

    for entry in input_set.dated_transactions:
        duration = date_to_duration.get(entry.effective_date)
        if duration is None:
            continue
        month_inputs = compiled[duration]
        if entry.kind == TransactionKind.PREMIUM:
            month_inputs.unscheduled_premium += entry.amount
        elif entry.kind == TransactionKind.LOAN:
            if entry.subtype.lower() == "variable":
                month_inputs.variable_loan += entry.amount
            else:
                month_inputs.regular_loan += entry.amount
        elif entry.kind == TransactionKind.LOAN_REPAYMENT:
            month_inputs.loan_repayment += entry.amount
        elif entry.kind == TransactionKind.WITHDRAWAL:
            month_inputs.withdrawal += entry.amount


def _active_schedule_for_year(schedules, policy_year: int):
    active = None
    for schedule in schedules:
        if schedule.policy_year <= policy_year:
            active = schedule
        else:
            break
    return active


def _scheduled_amount_for_month(amount: float, mode: str, policy_month: int) -> float:
    interval = {
        "M": 1,
        "Q": 3,
        "S": 6,
        "A": 12,
    }.get((mode or "M").strip().upper(), 1)
    return amount if (policy_month - 1) % interval == 0 else 0.0