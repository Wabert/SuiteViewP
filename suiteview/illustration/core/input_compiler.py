from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from dateutil.relativedelta import relativedelta

from suiteview.illustration.models.input_set import IllustrationInputSet, TransactionKind
from suiteview.illustration.models.policy_data import IllustrationPolicyData


@dataclass
class DatedCashFlow:
    """Dated input retained for historical receipt-date interest."""

    kind: TransactionKind
    effective_date: date
    bucket_date: date
    amount: float
    subtype: str = ""


@dataclass
class CompiledMonthInputs:
    """Resolved inputs for a single projection month."""

    scheduled_premium: float | None = None
    unscheduled_premium: float = 0.0
    # Portion of unscheduled_premium that belongs to a tagged one-time
    # Billable-to-MD deposit. Current-year modal payments compile as scheduled.
    billable_to_md_premium: float = 0.0
    premium_mode: str = ""
    regular_loan: float = 0.0
    variable_loan: float = 0.0
    loan_repayment: float = 0.0
    withdrawal: float = 0.0          # net-basis request (RERUN AX — cash to client)
    withdrawal_gross: float = 0.0    # gross-basis request (amount leaving the AV)
    shadow_prior_period_premium: float = 0.0
    shadow_bucketed_prior_period_premium: float = 0.0
    # Bucketed to a policy anniversary but received in the previous policy year
    # (history replays): the shadow loads it against that year's premiums.
    shadow_prior_year_premium: float = 0.0
    # Received after the opening monthliversary of a history replay (late-payment
    # forgiveness plans): brought forward into this month's shadow BAV.
    shadow_opening_late_premium: float = 0.0
    shadow_premium_days_to_bucket: float = 0.0
    shadow_withdrawal_days_to_bucket: float = 0.0
    dated_cash_flows: list[DatedCashFlow] = field(default_factory=list)

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

    historical_receipt_timing = _historical_receipt_timing(policy)
    for entry in input_set.dated_transactions:
        bucket_date = (
            _next_monthliversary_on_or_after(policy, entry.effective_date)
            if historical_receipt_timing else entry.effective_date
        )
        duration = date_to_duration.get(bucket_date)
        if duration is None:
            continue
        month_inputs = compiled[duration]
        if historical_receipt_timing:
            actual_date = _actual_cash_flow_date(entry)
            month_inputs.dated_cash_flows.append(DatedCashFlow(
                kind=entry.kind,
                effective_date=actual_date,
                bucket_date=bucket_date,
                amount=entry.amount,
                subtype=entry.subtype,
            ))
        if entry.kind == TransactionKind.PREMIUM:
            metadata = entry.metadata or {}
            if metadata.get("scheduled_current_year"):
                month_inputs.scheduled_premium = (
                    float(month_inputs.scheduled_premium or 0.0) + entry.amount
                )
                month_inputs.premium_mode = str(metadata.get("mode") or "")
            else:
                month_inputs.unscheduled_premium += entry.amount
            if metadata.get("billable_to_md") and not metadata.get("scheduled_current_year"):
                month_inputs.billable_to_md_premium += entry.amount
            _compile_shadow_premium_timing(policy, entry, duration, compiled)
            _compile_shadow_premium_interest_timing(entry, month_inputs)
            if historical_receipt_timing:
                _compile_shadow_prior_year_premium(policy, entry, duration, month_inputs)
        elif entry.kind == TransactionKind.LOAN:
            if entry.subtype.lower() == "variable":
                month_inputs.variable_loan += entry.amount
            else:
                month_inputs.regular_loan += entry.amount
        elif entry.kind == TransactionKind.LOAN_REPAYMENT:
            month_inputs.loan_repayment += entry.amount
        elif entry.kind == TransactionKind.WITHDRAWAL:
            # entry.subtype carries the requested basis from the inputs UI —
            # "net" (default, also "") means the client receives the amount
            # and the engine charges the WD fee / partial SC on top (RERUN's
            # input column AX is a net request); "gross" means the entered
            # amount is what leaves the account value (RERUN BN) and the
            # withdrawal handler inverts it back to a net request.
            if (entry.subtype or "").strip().lower() == "gross":
                month_inputs.withdrawal_gross += entry.amount
            else:
                month_inputs.withdrawal += entry.amount
            _compile_shadow_withdrawal_timing(entry, month_inputs)


def _metadata_actual_date(entry) -> date | None:
    actual = (entry.metadata or {}).get("actual_date")
    if not actual:
        return None
    return date.fromisoformat(str(actual)[:10])


def _compile_shadow_premium_timing(
    policy: IllustrationPolicyData,
    entry,
    duration: int,
    compiled: dict[int, CompiledMonthInputs],
) -> None:
    actual = _metadata_actual_date(entry)
    if actual is None or actual >= entry.effective_date or actual <= policy.issue_date:
        return
    prior = compiled.get(duration - 1)
    if prior is None:
        if duration - 1 == policy.duration and _historical_receipt_timing(policy):
            # Received after the opening (inforce / seed) monthliversary, whose row is not
            # recalculated: the shadow brings it forward net of load with that month's
            # interest instead (six-month replay UNE05228 -30.28 vs seriatim XP).
            compiled[duration].shadow_opening_late_premium += entry.amount
            compiled[duration].shadow_bucketed_prior_period_premium += entry.amount
        return
    prior.shadow_prior_period_premium += entry.amount
    compiled[duration].shadow_bucketed_prior_period_premium += entry.amount


def _compile_shadow_prior_year_premium(
    policy: IllustrationPolicyData,
    entry,
    duration: int,
    month_inputs: CompiledMonthInputs,
) -> None:
    """A premium received before the anniversary it is bucketed to belongs to the prior year.

    CyberLife counts shadow premiums by the policy year of receipt: U0609851 (LTGUL,
    pays ~3 weeks before each monthliversary) has no load on 9/2026 because year 18's
    receipts are below target, although the 4/28 receipt bucketed to the 5/23
    anniversary would push the bucketed year-18 total above it.
    """
    actual = _metadata_actual_date(entry)
    if actual is None or actual >= entry.effective_date or actual <= policy.issue_date:
        return
    if duration <= 1 or (duration - 1) % 12 != 0:
        return
    month_inputs.shadow_prior_year_premium += entry.amount


def _compile_shadow_premium_interest_timing(entry, month_inputs: CompiledMonthInputs) -> None:
    actual = _metadata_actual_date(entry)
    if actual is None or actual >= entry.effective_date:
        return
    total_amount = month_inputs.unscheduled_premium + float(month_inputs.scheduled_premium or 0.0)
    if total_amount <= 0.0:
        return
    previous_amount = max(total_amount - entry.amount, 0.0)
    month_inputs.shadow_premium_days_to_bucket = (
        (month_inputs.shadow_premium_days_to_bucket * previous_amount
         + (entry.effective_date - actual).days * entry.amount)
        / total_amount
    )


def _compile_shadow_withdrawal_timing(entry, month_inputs: CompiledMonthInputs) -> None:
    actual = _metadata_actual_date(entry)
    if actual is None or actual >= entry.effective_date:
        return
    existing_amount = month_inputs.withdrawal + month_inputs.withdrawal_gross
    total_amount = existing_amount if existing_amount > 0.0 else entry.amount
    previous_days = month_inputs.shadow_withdrawal_days_to_bucket
    new_days = (entry.effective_date - actual).days
    month_inputs.shadow_withdrawal_days_to_bucket = (
        (previous_days * max(total_amount - entry.amount, 0.0) + new_days * entry.amount)
        / total_amount
    )


def _historical_receipt_timing(policy: IllustrationPolicyData) -> bool:
    """Receipt-date interest applies only to rollback and from-issue replays."""
    return bool(policy.run_from_issue or policy.rollback_date is not None)


def _actual_cash_flow_date(entry) -> date:
    return _metadata_actual_date(entry) or entry.effective_date


def _next_monthliversary_on_or_after(
    policy: IllustrationPolicyData, effective_date: date,
) -> date:
    issue = policy.issue_date
    if issue is None:
        return effective_date
    months = (
        (effective_date.year - issue.year) * 12
        + effective_date.month - issue.month
    )
    candidate = issue + relativedelta(months=months)
    if candidate < effective_date:
        candidate = issue + relativedelta(months=months + 1)
    return candidate


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