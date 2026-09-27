"""Historical, post-deduction starting values without changing the live policy.

Sources are the same PolicyInformation tables used by PolView's Monthliversary
Values, Loans and Targets tabs. LH_POL_MVRY_VAL.CSV_AMT is the stored opening AV,
not an amount from which to subtract the monthly deduction a second time.

LH_POL_TOTALS and LH_POL_TARGET are *current* records. In particular TAR_DT is
not a historical-snapshot date (MA uses it for the safety-net cease date).
There is no historical target-change ledger here. For unchanged, single-base
UL/IUL policies, target balances can be derived by reversing the established
RERUN accumulation mechanics. That basis is disclosed, and observed changes
block it; TAR_DT is never treated as an archived balance timestamp.

Copy/mutation rule: `apply_value_rollback` returns a deep-copied policy basis.
The loaded current policy and its captured snapshots are never mutated. Snapshot
source limits are explicit: recorded monthliversary values are post-deduction;
current totals/targets are reversed only for verified ordinary premium activity;
IUL historical fund buckets are not reconstructed from current allocations.
"""
from __future__ import annotations

import calendar
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from suiteview.illustration.models.policy_data import (
    IllustrationPolicyData,
    ValueRollbackSnapshot,
)
from suiteview.illustration.core.target_premium import (
    floor_monthly_cent,
    truncate_monthly_mtp,
)
from suiteview.illustration.models.index_strategies import is_iul_plan

if TYPE_CHECKING:
    from suiteview.polview.models.policy_information import PolicyInformation


_LOAN_FIELDS = tuple(
    f"{kind}_loan_{amount}"
    for kind in ("regular", "preferred", "variable")
    for amount in ("principal", "accrued")
)
_REQUIRED_AMOUNTS = (
    "account_value", "premiums_paid_to_date", "premiums_ytd", "accumulated_mtp",
    "accumulated_glp", "cost_basis", "withdrawals_to_date", *_LOAN_FIELDS,
)
_SYSTEM_AMOUNTS = (
    "system_coi_charge", "system_expense_charge", "system_other_charge",
    "system_monthly_deduction",
)
_IUL_TOTAL_BASIS = (
    "IUL rollback uses the recorded total account value only; individual historical "
    "fund/bucket balances are not reconstructed. Loaded allocations and illustrated "
    "crediting assumptions remain forward-projection assumptions, not historical holdings."
)


def _six_months_before(when: date) -> date:
    year, month = divmod(when.year * 12 + when.month - 1 - 6, 12)
    month += 1
    return date(year, month, min(when.day, calendar.monthrange(year, month)[1]))


def _record_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        result = value.date()
    elif isinstance(value, date):
        result = value
    else:
        result = date.fromisoformat(str(value).strip()[:10])
    return result if result.year not in (1, 9999) else None


def _number(value, label: str) -> Decimal:
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        raise ValueError(f"{label} is missing.")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{label} is not a numeric amount.") from exc
    if not result.is_finite():
        raise ValueError(f"{label} is not finite.")
    return result


def _amount(row: dict, field: str, table: str) -> Decimal:
    return _number(row.get(field), f"{table}.{field}")


def _read_rows(pi: PolicyInformation, table: str) -> list[dict]:
    rows = pi.fetch_table(table)
    error = pi.table_error(table)
    if error:
        raise RuntimeError(f"Cannot load Value Rollback source {table}: {error}")
    return rows


def available_rollback_dates(policy: IllustrationPolicyData) -> list[date]:
    """Actual prior recorded dates, newest first, in six calendar months.

    Incomplete dates remain listed so callers can explain why Update is blocked.
    The window always uses the original loaded valuation, not today's date.
    """
    anchor = policy.rollback_source_date or policy.valuation_date
    if anchor is None:
        return []
    earliest = _six_months_before(anchor)
    return sorted({
        snapshot.valuation_date for snapshot in policy.rollback_snapshots
        if earliest <= snapshot.valuation_date < anchor
        and (policy.issue_date is None or snapshot.valuation_date >= policy.issue_date)
    }, reverse=True)


def _duration(policy: IllustrationPolicyData, when: date) -> tuple[int, int, int, int]:
    if policy.issue_date is None or when < policy.issue_date:
        raise ValueError("Value Rollback requires a valid original issue date.")
    months = (when.year - policy.issue_date.year) * 12 + when.month - policy.issue_date.month
    anniversary_day = min(policy.issue_date.day, calendar.monthrange(when.year, when.month)[1])
    if when.day != anniversary_day:
        raise ValueError("Recorded rollback date is not an issue-day-anchored monthliversary.")
    year, month = divmod(months, 12)
    return year + 1, month + 1, months + 1, policy.issue_age + year


def apply_value_rollback(
    policy: IllustrationPolicyData, rollback_date: date,
    *, shadow_account_value: float | None = None,
    allow_missing_shadow: bool = False,
) -> IllustrationPolicyData:
    """Copy the loaded current basis, or recover a validated historical basis."""
    if policy.run_from_issue:
        raise ValueError("Value Rollback cannot be combined with New Business - From Issue.")
    anchor = policy.rollback_source_date or policy.valuation_date
    if rollback_date == anchor and policy.rollback_date is None:
        return _current_basis_copy(policy, shadow_account_value)
    snapshot = _snapshot_for_rollback_date(policy, rollback_date)
    historical_shadow = (
        shadow_account_value if shadow_account_value is not None
        else snapshot.shadow_account_value)
    missing_shadow = _missing_shadow_value(policy, historical_shadow)
    contributions = _validate_snapshot_or_raise(
        policy, snapshot, rollback_date, anchor,
        historical_shadow=historical_shadow,
        missing_shadow=missing_shadow,
        allow_missing_shadow=allow_missing_shadow,
    )
    result, unavailable_charge_details = _copy_historical_basis(
        policy, snapshot, rollback_date, anchor, contributions)
    _apply_historical_shadow(
        result, historical_shadow, shadow_account_value, missing_shadow)
    _append_charge_limitations(result, unavailable_charge_details)
    _set_rollback_duration(result, policy, rollback_date)
    return result


def _current_basis_copy(
    policy: IllustrationPolicyData,
    shadow_account_value: float | None,
) -> IllustrationPolicyData:
    result = deepcopy(policy)
    if shadow_account_value is not None:
        result.shadow_account_value = float(
            _number(shadow_account_value, "Starting shadow account value"))
    return result


def _snapshot_for_rollback_date(policy: IllustrationPolicyData, rollback_date: date):
    if rollback_date not in available_rollback_dates(policy):
        raise ValueError("No recorded rollback snapshot within six months for the selected date.")
    matches = [s for s in policy.rollback_snapshots if s.valuation_date == rollback_date]
    if len(matches) != 1:
        raise ValueError("Multiple historical snapshots exist for the selected date.")
    return matches[0]


def _missing_shadow_value(policy: IllustrationPolicyData, historical_shadow) -> bool:
    return bool(
        (policy.ccv_active or policy.shadow_account_value or policy.swam)
        and historical_shadow is None)


def _validate_snapshot_or_raise(
    policy: IllustrationPolicyData,
    snapshot,
    rollback_date: date,
    anchor: date,
    *,
    historical_shadow,
    missing_shadow: bool,
    allow_missing_shadow: bool,
):
    errors = list(snapshot.blocking_errors)
    if snapshot.source_valuation_date not in (None, anchor):
        errors.append("Snapshot belongs to a different loaded valuation date.")
    errors.extend(_required_amount_errors(snapshot))
    contributions = _validated_tamra_contributions(snapshot, errors)
    errors.extend(_shadow_amount_errors(historical_shadow, missing_shadow, allow_missing_shadow))
    errors.extend(_supplemental_snapshot_errors(policy, snapshot))
    if errors:
        raise ValueError(
            f"Value Rollback to {rollback_date:%Y-%m-%d} is unsafe:\n"
            + "\n".join(f"- {error}" for error in dict.fromkeys(errors))
        )
    return contributions


def _required_amount_errors(snapshot) -> list[str]:
    errors: list[str] = []
    for name in (*_REQUIRED_AMOUNTS, "system_monthly_deduction"):
        if getattr(snapshot, name) is None and snapshot.blocking_errors:
            continue
        try:
            amount = _number(getattr(snapshot, name), f"Historical {name} for the selected rollback date")
            if name in _LOAN_FIELDS and amount < 0:
                errors.append(f"{name} cannot be negative.")
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def _validated_tamra_contributions(snapshot, errors: list[str]):
    contributions = snapshot.tamra_7year_contributions
    if contributions is None:
        if not snapshot.blocking_errors:
            errors.append("Historical TAMRA year contributions are incomplete (seven years required).")
        return contributions
    if len(contributions) != 7:
        errors.append("Historical TAMRA year contributions are incomplete (seven years required).")
        return contributions
    for year, amount in enumerate(contributions, 1):
        try:
            _number(amount, f"TAMRA year {year}")
        except ValueError as exc:
            errors.append(str(exc))
    return contributions


def _shadow_amount_errors(
    historical_shadow,
    missing_shadow: bool,
    allow_missing_shadow: bool,
) -> list[str]:
    errors: list[str] = []
    if missing_shadow and not allow_missing_shadow:
        errors.append("Historical shadow-account values are unavailable. Enter a verified historical shadow amount.")
    if historical_shadow is not None:
        try:
            _number(historical_shadow, "Historical shadow account value")
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def _supplemental_snapshot_errors(policy: IllustrationPolicyData, snapshot) -> list[str]:
    errors: list[str] = []
    if policy.deemed_cash_value and snapshot.deemed_cash_value is None:
        errors.append("Historical deemed cash value is unavailable.")
    if snapshot.variable_loan_principal or snapshot.variable_loan_accrued:
        try:
            rate = _number(snapshot.variable_loan_charge_rate, "Historical variable-loan charge rate")
            if rate < 0:
                errors.append("Historical variable-loan charge rate cannot be negative.")
        except ValueError as exc:
            errors.append(str(exc))
    if policy.swam:
        errors.append("Historical SWAM state has not been recovered.")
    if snapshot.fund_values is not None:
        for fund, amount in snapshot.fund_values.items():
            try:
                _number(amount, f"Historical fund {fund}")
            except ValueError as exc:
                errors.append(str(exc))
    return errors


def _copy_historical_basis(
    policy: IllustrationPolicyData,
    snapshot,
    rollback_date: date,
    anchor: date,
    contributions,
) -> tuple[IllustrationPolicyData, list[str]]:
    result = deepcopy(policy)
    for name in (*_REQUIRED_AMOUNTS, "system_monthly_deduction"):
        setattr(result, name, float(getattr(snapshot, name)))
    unavailable_charge_details = _apply_system_charges(result, snapshot)
    result.tamra_7year_contributions = list(contributions)
    _copy_optional_snapshot_values(result, snapshot)
    result.variable_loan_charge_rate = snapshot.variable_loan_charge_rate
    result.fund_values = deepcopy(snapshot.fund_values) if snapshot.fund_values is not None else {}
    result.impaired_fund_values = {}
    result.rollback_date = rollback_date
    result.rollback_source_date = anchor
    result.rollback_limitations = list(snapshot.limitations)
    if _is_iul(policy):
        result.fund_values = {}
        if _IUL_TOTAL_BASIS not in result.rollback_limitations:
            result.rollback_limitations.append(_IUL_TOTAL_BASIS)
    return result, unavailable_charge_details


def _apply_system_charges(result: IllustrationPolicyData, snapshot) -> list[str]:
    unavailable_charge_details = []
    for name in _SYSTEM_AMOUNTS[:3]:
        amount = getattr(snapshot, name)
        if amount is None:
            result.__setattr__(name, 0.0)
            unavailable_charge_details.append(name)
        else:
            setattr(result, name, float(_number(amount, name)))
    return unavailable_charge_details


def _copy_optional_snapshot_values(result: IllustrationPolicyData, snapshot) -> None:
    for name in ("shadow_account_value", "deemed_cash_value"):
        value = getattr(snapshot, name)
        if value is not None:
            setattr(result, name, float(_number(value, name)))


def _apply_historical_shadow(
    result: IllustrationPolicyData,
    historical_shadow,
    manual_shadow,
    missing_shadow: bool,
) -> None:
    result.rollback_requires_shadow_value = missing_shadow
    if historical_shadow is not None:
        result.shadow_account_value = float(historical_shadow)
    if manual_shadow is not None:
        result.rollback_limitations.append(
            "Historical shadow account value was entered manually, not recovered from CyberLife.")
    elif missing_shadow:
        result.rollback_limitations.append(
            "Historical shadow account value is unavailable. Projection is blocked until "
            "a historical amount is explicitly entered; the loaded shadow balance is not rolled back.")


def _append_charge_limitations(result: IllustrationPolicyData, unavailable_charge_details: list[str]) -> None:
    if not unavailable_charge_details:
        return
    result.rollback_limitations.append(
        "Historical charge breakdown unavailable: "
        + ", ".join(unavailable_charge_details)
        + ". Opening comparison shows diagnostic zero placeholders for these "
        "components, not recovered amounts; the total deduction is sourced."
    )


def _set_rollback_duration(
    result: IllustrationPolicyData,
    policy: IllustrationPolicyData,
    rollback_date: date,
) -> None:
    year, month, duration, attained_age = _duration(policy, rollback_date)
    result.valuation_date = rollback_date
    result.policy_year = year
    result.policy_month = month
    result.duration = duration
    result.attained_age = attained_age
def _transactions(rows: list[dict]) -> list[tuple[date, str, dict]]:
    result = []
    for row in rows:
        when = _record_date(row.get("ASOF_DT"))
        if when is None:
            raise ValueError("Financial history contains a missing effective date.")
        code = str(row.get("TRANS") or "").strip().upper()
        if not code:
            code = (
                str(row.get("TRN_TYP_CD") or "").strip()
                + str(row.get("TRN_SBY_CD") or "").strip()
            ).upper()
        if not code:
            raise ValueError("Financial history contains a missing transaction code.")
        result.append((when, code, row))
    return result


def _processed_history(history, tables):
    """Exclude pending premiums only after reconciliation to current paid totals.

    Live UE000576 demonstrates FH_FIXED can contain the next unapplied PR:
    FBB3_PROCD_IND=0, while LH_POL_TOTALS equals only the processed premiums.
    Ignoring the flag would subtract a receipt never included in the anchor.
    A retained/purged history that cannot prove this relationship is blocked.
    """
    from suiteview.polview.models.policy_sections.activity import ActivitySection

    premium_codes = ActivitySection.PREMIUM_TRANSACTION_CODES
    pending = [
        item for item in history
        if item[1] in premium_codes and str(item[2].get("FBB3_PROCD_IND", "")).strip() == "0"
        and all(str(item[2].get(flag, "")).strip() == "0"
                for flag in ("FCB0_REV_IND", "FCB2_REV_APPL_IND"))
    ]
    if not pending:
        return history, False
    totals = tables["LH_POL_TOTALS"]
    if len(totals) != 1:
        raise ValueError("Pending premiums cannot be reconciled to a unique current total.")
    current_paid = (
        _amount(totals[0], "TOT_REG_PRM_AMT", "LH_POL_TOTALS")
        + _amount(totals[0], "TOT_ADD_PRM_AMT", "LH_POL_TOTALS")
    )
    processed = Decimal(0)
    for _, code, row in history:
        if code not in premium_codes or str(row.get("FBB3_PROCD_IND", "")).strip() != "1":
            continue
        if any(str(row.get(flag, "")).strip() != "0"
               for flag in ("FCB0_REV_IND", "FCB2_REV_APPL_IND")):
            continue
        field = "GROSS_AMT" if "GROSS_AMT" in row else "TOT_TRS_AMT"
        processed += _amount(row, field, "FH_FIXED")
    if processed != current_paid:
        raise ValueError(
            "Pending premiums cannot be safely excluded: processed financial history "
            "does not reconcile to current premiums paid."
        )
    pending_rows = {id(row) for _, _, row in pending}
    return [item for item in history if id(item[2]) not in pending_rows], True


def _same_day_cd_boundary(history: list[tuple[date, str, dict]], when: date) -> Decimal | None:
    boundary_rows = [
        row for day, code, row in history
        if day == when and code == "CD"
        and str(row.get("FCB0_REV_IND", "")).strip() == "0"
        and str(row.get("FCB2_REV_APPL_IND", "")).strip() == "0"
    ]
    return (
        _amount(boundary_rows[0], "SEQ_NO", "FH_FIXED")
        if len(boundary_rows) == 1 else None
    )


def _history_reversal_flags(row: dict) -> list[str]:
    flags = [str(row.get(key, "")).strip() for key in ("FCB0_REV_IND", "FCB2_REV_APPL_IND")]
    if any(flag not in {"0", "1"} for flag in flags):
        raise ValueError("Financial history reversal flags are missing or invalid.")
    return flags


def _later_history_candidate(day: date, code: str, row: dict, when: date) -> bool:
    entry = _record_date(row.get("ENTRY_DT"))
    if entry is None:
        raise ValueError("Financial history entry dates are required to check backdated activity.")
    if day < when:
        if entry > when and code != "CD":
            raise ValueError("Backdated financial activity can invalidate the stored historical basis.")
        return False
    flags = _history_reversal_flags(row)
    if "1" in flags:
        raise ValueError("Reversed financial activity requires verified historical accumulator effects.")
    if any(
        str(row.get(key, "0")).strip() == "1"
        for key in ("FCB3_ACT_CORR_IND", "FEB1_UNDO_REDO_IND")
    ):
        raise ValueError("Corrected financial activity requires verified historical accumulator effects.")
    if code == "CD":
        return False
    if code != "PR":
        raise ValueError(f"Historical accumulator effects are unverified for transaction {code}.")
    if str(row.get("FEB3_1035_EXCH_IND", "0")).strip() != "0":
        raise ValueError("1035-exchange premiums require the historical transferred cost basis.")
    return True


def _later_premium_amount(row: dict) -> Decimal:
    amount_field = "GROSS_AMT" if "GROSS_AMT" in row else "TOT_TRS_AMT"
    amount = _amount(row, amount_field, "FH_FIXED")
    if amount < 0:
        raise ValueError("Negative premiums require verified correction handling.")
    return amount


def _same_day_premium_is_after_boundary(
    row: dict,
    boundary: Decimal | None,
) -> bool:
    if boundary is None:
        raise ValueError("Same-day premium/deduction ordering is unavailable.")
    return _amount(row, "SEQ_NO", "FH_FIXED") >= boundary


def _later_premiums(
    history: list[tuple[date, str, dict]], when: date,
) -> list[tuple[date, Decimal]]:
    """Ordinary premium-only reversals; reject ambiguous boundary/corrections.

    FH_FIXED's CD sequence marks the recorded deduction on a date shared with
    premiums. Entries before it are already in that day's post-deduction basis.
    Gross PR increases paid premiums and cost basis (the engine's apply_premium
    convention). Exchanges, withdrawals, corrections and other transaction
    families need their own verified accumulator effects; they are not guessed.
    """
    boundary = _same_day_cd_boundary(history, when)
    result = []
    for day, code, row in history:
        if not _later_history_candidate(day, code, row, when):
            continue
        amount = _later_premium_amount(row)
        if day == when and not _same_day_premium_is_after_boundary(row, boundary):
            continue
        result.append((day, amount))
    return result


def _completed_months(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + end.month - start.month
    return months - (end.day < min(start.day, calendar.monthrange(end.year, end.month)[1]))


def _is_iul(policy: IllustrationPolicyData) -> bool:
    return policy.product_type.upper() == "IUL" or is_iul_plan(policy.plancode)


def _recover_totals(policy, snapshot, tables, history):
    later = _later_premiums(history, snapshot.valuation_date)
    totals = tables["LH_POL_TOTALS"]
    if len(totals) != 1:
        raise ValueError("A unique current policy-total record is required to reverse premiums.")
    row = totals[0]
    premium_delta = sum((amount for _, amount in later), Decimal(0))
    snapshot.premiums_paid_to_date = float(
        _amount(row, "TOT_REG_PRM_AMT", "LH_POL_TOTALS")
        + _amount(row, "TOT_ADD_PRM_AMT", "LH_POL_TOTALS") - premium_delta
    )
    snapshot.cost_basis = float(_amount(row, "POL_CST_BSS_AMT", "LH_POL_TOTALS") - premium_delta)
    snapshot.withdrawals_to_date = float(_amount(row, "TOT_WTD_AMT", "LH_POL_TOTALS"))
    if snapshot.premiums_paid_to_date < 0 or snapshot.cost_basis < 0:
        raise ValueError("Reversed premiums exceed the current accumulator; history does not reconcile.")
    policy_year = _duration(policy, snapshot.valuation_date)[0]
    year_rows = [
        row for row in tables["LH_POL_YR_TOT"]
        if _amount(row, "POL_YR_DUR", "LH_POL_YR_TOT") == policy_year
    ]
    if len(year_rows) != 1:
        raise ValueError("The selected policy year's premium-total record is unavailable or ambiguous.")
    year_delta = sum(
        (amount for day, amount in later
         if _completed_months(policy.issue_date, day) // 12 + 1 == policy_year), Decimal(0)
    )
    snapshot.premiums_ytd = float(
        _amount(year_rows[0], "YTD_TOT_PMT_AMT", "LH_POL_YR_TOT")
        + _amount(year_rows[0], "YTD_ADD_PRM_AMT", "LH_POL_YR_TOT") - year_delta
    )
    if snapshot.premiums_ytd < 0:
        raise ValueError("Reversed year-to-date premiums do not reconcile.")
    snapshot.limitations.append(
        "Premiums/cost basis reverse only ordinary unreversed PR transactions, including "
        "activity after the loaded valuation. Same-day premiums use the recorded CD sequence."
    )
    return later


def _recover_tamra(snapshot, tables, later, policy):
    periods = tables["LH_TAMRA_7_PY_PER"]
    if (
        not periods and not tables["LH_TAMRA_7_PY_YR"]
        and policy.tamra_7pay_start_date is None
        and policy.tamra_7pay_level == 0 and not policy.is_mec
    ):
        # VBA NoTAMRAValues distinguishes an absent subsystem from a missing
        # amount inside an existing period/year. The latter remains an error.
        snapshot.tamra_7year_contributions = [0.0] * 7
        snapshot.limitations.append(
            "CyberLife has no TAMRA period or year records (NoTAMRAValues); "
            "there are no existing seven-pay contributions to roll back."
        )
        return
    if len(periods) != 1:
        raise ValueError("A unique historical TAMRA period is unavailable.")
    start = _record_date(periods[0].get("SVPY_PER_STR_DT"))
    if start is None or start > snapshot.valuation_date:
        raise ValueError("Selected date predates the retained TAMRA period; prior contributions are unavailable.")
    by_year = {}
    for row in tables["LH_TAMRA_7_PY_YR"]:
        year = _amount(row, "SVPY_YR_SEQ_NBR", "LH_TAMRA_7_PY_YR")
        if year != int(year) or not 1 <= year <= 7 or int(year) in by_year:
            raise ValueError("Historical TAMRA year keys are invalid or ambiguous.")
        by_year[int(year)] = (
            _amount(row, "SVPY_PRM_PAY_AMT", "LH_TAMRA_7_PY_YR")
            - _amount(row, "SVPY_WTD_AMT", "LH_TAMRA_7_PY_YR")
        )
    if set(by_year) != set(range(1, 8)):
        raise ValueError("TAMRA contribution rows are incomplete; missing years are not zero.")
    for day, amount in later:
        year = _completed_months(start, day) // 12 + 1
        if 1 <= year <= 7:
            by_year[year] -= amount
    snapshot.tamra_7year_contributions = [float(by_year[year]) for year in range(1, 8)]


def _ensure_single_base_target_basis(policy) -> None:
    if len(policy.segments) != 1:
        raise ValueError(
            "Historical target reconstruction currently requires a single-base "
            "UL/IUL policy with an unchanged coverage basis."
        )


def _check_coverage_target_basis(coverages, when: date, anchor: date) -> None:
    if not coverages:
        raise ValueError("Coverage history is unavailable to check the target basis.")
    for coverage in coverages:
        for field in ("issue_date", "cov_status_date", "terminate_date", "maturity_date"):
            changed = getattr(coverage, field, None)
            if changed is not None and when < changed <= anchor:
                raise ValueError(
                    "A recorded coverage change crosses the rollback interval; "
                    "historical targets are unavailable.")
        original = getattr(coverage, "orig_amount", None)
        current = getattr(coverage, "face_amount", None)
        if original is not None and current is not None and original != current:
            raise ValueError(
                "Coverage face differs from its original amount without a dated target-change "
                "history; unchanged-target reconstruction is unsafe."
            )


def _check_rider_benefit_target_basis(policy, when: date, anchor: date) -> None:
    for item in [*policy.riders, *policy.benefits]:
        for field in ("issue_date", "maturity_date", "cease_date", "pay_up_date"):
            changed = getattr(item, field, None)
            if changed is not None and when < changed <= anchor:
                raise ValueError(
                    "A rider/benefit boundary crosses the rollback interval; "
                    "historical targets are unavailable.")


def _target_amount(tables, code: str, when: date, anchor: date) -> Decimal:
    matches = [
        row for row in tables["LH_POL_TARGET"]
        if str(row.get("TAR_TYP_CD", "")).strip() == code
    ]
    if len(matches) != 1:
        raise ValueError(f"A unique current {code} target amount is required.")
    if code in {"MT", "TA"}:
        target_date = _record_date(matches[0].get("TAR_DT"))
        if target_date is not None and when < target_date <= anchor:
            raise ValueError(
                f"The {code} target date crosses the rollback interval; "
                "prior target basis is unavailable.")
    return _amount(matches[0], "TAR_PRM_AMT", "LH_POL_TARGET")


def _guideline_level_premium(tables) -> Decimal:
    glp_rows = [
        row for row in tables["LH_COV_INS_GDL_PRM"]
        if str(row.get("PRM_RT_TYP_CD", "")).strip() == "A"
    ]
    if len(glp_rows) != 1:
        raise ValueError("A unique current guideline level premium is required.")
    return _amount(glp_rows[0], "GDL_PRM_AMT", "LH_COV_INS_GDL_PRM")


def _target_month_window(policy, when: date, anchor: date) -> tuple[int, int]:
    return (
        _completed_months(policy.issue_date, when),
        _completed_months(policy.issue_date, anchor),
    )


def _anniversary_count_before_age_100(policy, first_month: int, last_month: int) -> int:
    return sum(
        month % 12 == 0 and policy.issue_age + month // 12 < 100
        for month in range(first_month + 1, last_month + 1)
    )


def _recover_targets(snapshot, tables, policy, history, coverages):
    """Reverse canonical engine target accrual on an explicitly unchanged basis."""
    when = snapshot.valuation_date
    anchor = snapshot.source_valuation_date
    _later_premiums(history, when)
    _ensure_single_base_target_basis(policy)
    _check_coverage_target_basis(coverages, when, anchor)
    _check_rider_benefit_target_basis(policy, when, anchor)
    if any(day > anchor and code == "CD" for day, code, _ in history):
        raise ValueError("A later recorded deduction makes the loaded target-accumulation date ambiguous.")

    monthly_mtp = _target_amount(tables, "MT", when, anchor)
    accumulated_mtp = _target_amount(tables, "MA", when, anchor)
    if policy.is_cvat:
        accumulated_glp = glp = Decimal(0)
        snapshot.limitations.append(
            "CVAT has no guideline-premium test; AccumGLP is zero (not applicable).")
    else:
        accumulated_glp = _target_amount(tables, "TA", when, anchor)
        glp = _guideline_level_premium(tables)
    first_month, last_month = _target_month_window(policy, when, anchor)
    # calc_engine steps 8/10: MTP is already MONTHLY; GLP is added only at
    # anniversaries before attained age 100, not one twelfth every month.
    monthly_mtp = Decimal(str(truncate_monthly_mtp(float(monthly_mtp))))
    mtp_delta = monthly_mtp * (last_month - first_month)
    anniversaries = _anniversary_count_before_age_100(policy, first_month, last_month)
    glp_delta = Decimal(str(floor_monthly_cent(float(glp)))) * anniversaries
    if accumulated_mtp < mtp_delta:
        raise ValueError("Current AccumMTP does not reconcile with unchanged-target reverse accrual.")
    snapshot.accumulated_mtp = float(accumulated_mtp - mtp_delta)
    snapshot.accumulated_glp = float(accumulated_glp - glp_delta)
    snapshot.limitations.append(
        "AccumMTP/AccumGLP are derived, not archived: reverse RERUN monthly MTP "
        "and anniversary-only GLP (no growth at age 100), assuming the loaded target "
        "rates and coverage basis were unchanged. Recorded changes are screened; "
        "unrecorded/nonfinancial target overrides cannot be recovered. Review this basis."
    )


def _recover_deduction(snapshot, history):
    if snapshot.system_monthly_deduction is not None:
        return
    rows = [
        row for day, code, row in history
        if day == snapshot.valuation_date and code == "CD"
        and str(row.get("FCB0_REV_IND", "")).strip() == "0"
        and str(row.get("FCB2_REV_APPL_IND", "")).strip() == "0"
    ]
    if len(rows) != 1:
        return
    amount_field = "GROSS_AMT" if "GROSS_AMT" in rows[0] else "TOT_TRS_AMT"
    snapshot.system_monthly_deduction = float(_amount(rows[0], amount_field, "FH_FIXED"))
    snapshot.limitations.append(
        "The recorded same-day CD charge deduction supplies the total monthly "
        "deduction; unavailable U1MV component breakdowns remain unrecovered."
    )


def _dated_loan_rows(loan_rows, valuation_date: date) -> list[dict]:
    return [
        row for row in loan_rows
        if _record_date(row.get("MVRY_DT")) == valuation_date
    ]


def _recover_absent_loans(snapshot, loan_rows, policy, history) -> None:
    # An empty successfully read table plus unchanged zero current loans is
    # evidence of no loan buckets, not a missing amount in a retained row.
    if not history:
        raise ValueError("Financial history is required to establish that no historical loans existed.")
    _later_premiums(history, snapshot.valuation_date)
    if loan_rows or any(getattr(policy, name) != 0 for name in _LOAN_FIELDS):
        raise ValueError("Exact-date loan values are unavailable; current/sentinel loans cannot be reused.")
    for name in _LOAN_FIELDS:
        setattr(snapshot, name, 0.0)


def _loan_bucket_identity(row: dict) -> tuple[str, Decimal, str, str]:
    fund = str(row.get("FND_ID_CD") or "").strip()
    preferred = str(row.get("PRF_LN_IND", "")).strip()
    status = str(row.get("LN_ITS_AMT_TYP_CD", "")).strip()
    phase = _amount(row, "FND_VAL_PHA_NBR", "LH_FND_VAL_LOAN")
    if not fund or preferred not in {"0", "1"} or status not in {"0", "1", "2"}:
        raise ValueError("Historical loan bucket classification/interest status is unavailable.")
    return fund, phase, preferred, status


def _loan_kind(fund: str, preferred: str) -> str:
    if fund == "LZ":
        return "variable"
    return "preferred" if preferred == "1" else "regular"


def _accumulate_loan_row(
    row: dict,
    amounts: dict,
    rates: set,
    seen: set,
) -> None:
    fund, phase, preferred, status = _loan_bucket_identity(row)
    key = (fund, phase, preferred, status)
    if key in seen:
        raise ValueError("Duplicate historical loan buckets are ambiguous.")
    seen.add(key)
    kind = _loan_kind(fund, preferred)
    amounts[f"{kind}_loan_principal"] += _amount(row, "LN_PRI_AMT", "LH_FND_VAL_LOAN")
    if status != "1":
        amounts[f"{kind}_loan_accrued"] += _amount(row, "POL_LN_ITS_AMT", "LH_FND_VAL_LOAN")
    if kind == "variable":
        rate = _amount(row, "LN_CRG_ITS_RT", "LH_FND_VAL_LOAN")
        rates.add(rate / 100 if rate > 1 else rate)


def _apply_recovered_loans(snapshot, amounts: dict, rates: set) -> None:
    if len(rates) > 1:
        raise ValueError("Historical variable-loan buckets have conflicting rates.")
    if rates:
        snapshot.variable_loan_charge_rate = float(rates.pop())
    for name, amount in amounts.items():
        setattr(snapshot, name, float(amount))


def _recover_loans(snapshot, loan_rows, policy, history):
    dated = _dated_loan_rows(loan_rows, snapshot.valuation_date)
    if not dated:
        _recover_absent_loans(snapshot, loan_rows, policy, history)
        return
    amounts = dict.fromkeys(_LOAN_FIELDS, Decimal(0))
    rates = set()
    seen = set()
    for row in dated:
        _accumulate_loan_row(row, amounts, rates, seen)
    _apply_recovered_loans(snapshot, amounts, rates)


def _rollback_monthliversary_rows(pi: PolicyInformation, anchor: date) -> dict[date, list[dict]]:
    rows = _read_rows(pi, "LH_POL_MVRY_VAL")
    dated = {}
    earliest = _six_months_before(anchor)
    for row in rows:
        when = _record_date(row.get("MVRY_DT"))
        if when is not None and earliest <= when < anchor:
            dated.setdefault(when, []).append(row)
    return dated


def _rollback_source_tables(pi: PolicyInformation) -> dict[str, list[dict]]:
    return {
        name: _read_rows(pi, name) for name in (
            "LH_POL_TOTALS", "LH_POL_YR_TOT", "LH_POL_TARGET",
            "LH_COV_INS_GDL_PRM",
            "LH_TAMRA_7_PY_PER", "LH_TAMRA_7_PY_YR", "LH_FND_VAL_LOAN", "FH_FIXED",
        )
    }


def _rollback_history_context(tables) -> tuple[list | None, str | None, bool]:
    history = None
    history_error = None
    excluded_pending = False
    try:
        history = _transactions(tables["FH_FIXED"])
        if not history:
            raise ValueError("Financial history is unavailable; accumulator reversal cannot be verified.")
        history, excluded_pending = _processed_history(history, tables)
    except ValueError as exc:
        history_error = str(exc)
    return history, history_error, excluded_pending


def _new_rollback_snapshot(
    when: date,
    anchor: date,
    excluded_pending: bool,
) -> ValueRollbackSnapshot:
    snapshot = ValueRollbackSnapshot(valuation_date=when, source_valuation_date=anchor)
    snapshot.limitations.extend([
        "Account value is the recorded post-deduction U1MV value; do not deduct charges again.",
        "Specified amounts, DB option, underwriting, target rates and billing are current "
        "assumptions, not recovered historical coverage conditions.",
    ])
    if excluded_pending:
        snapshot.limitations.append(
            "Pending premiums (FBB3_PROCD_IND=0) were excluded only after "
            "processed premium history reconciled exactly to current premiums paid."
        )
    return snapshot


def _apply_monthliversary_amounts(
    snapshot: ValueRollbackSnapshot,
    policy: IllustrationPolicyData,
    row: dict,
) -> None:
    try:
        snapshot.account_value = float(_amount(row, "CSV_AMT", "LH_POL_MVRY_VAL"))
        expected_year = _duration(policy, snapshot.valuation_date)[0]
        if _amount(row, "POL_DUR_NBR", "LH_POL_MVRY_VAL") != expected_year:
            raise ValueError("U1MV policy year disagrees with the original issue date.")
    except ValueError as exc:
        snapshot.blocking_errors.append(str(exc))
    for name, column in (
        ("system_coi_charge", "CINS_AMT"),
        ("system_expense_charge", "EXP_CRG_AMT"),
        ("system_other_charge", "OTH_PRM_AMT"),
    ):
        try:
            setattr(snapshot, name, float(_amount(row, column, "LH_POL_MVRY_VAL")))
        except ValueError as exc:
            snapshot.limitations.append(str(exc))
    if all(getattr(snapshot, name) is not None for name in _SYSTEM_AMOUNTS[:3]):
        snapshot.system_monthly_deduction = sum(
            getattr(snapshot, name) for name in _SYSTEM_AMOUNTS[:3])


def _recover_snapshot_accumulators(
    snapshot: ValueRollbackSnapshot,
    policy: IllustrationPolicyData,
    tables,
    history,
    history_error: str | None,
    coverages,
) -> None:
    if history_error:
        snapshot.blocking_errors.append(history_error)
        return
    try:
        later = _recover_totals(policy, snapshot, tables, history)
        _recover_tamra(snapshot, tables, later, policy)
    except ValueError as exc:
        snapshot.blocking_errors.append(str(exc))
    try:
        _recover_targets(snapshot, tables, policy, history, coverages)
    except ValueError as exc:
        snapshot.blocking_errors.append(str(exc))
    try:
        _recover_deduction(snapshot, history)
    except ValueError as exc:
        snapshot.blocking_errors.append(str(exc))


def _recover_snapshot_loans(snapshot, tables, policy, history) -> None:
    try:
        _recover_loans(snapshot, tables["LH_FND_VAL_LOAN"], policy, history or [])
    except ValueError as exc:
        snapshot.blocking_errors.append(str(exc))


def _append_snapshot_policy_limitations(
    snapshot: ValueRollbackSnapshot,
    policy: IllustrationPolicyData,
) -> None:
    snapshot.limitations.append(
        "Historical individual fund balances are unavailable; the recorded total "
        "account value is not assigned to current fund IDs.")
    if policy.ccv_active or policy.shadow_account_value or policy.swam:
        snapshot.limitations.append(
            "The coverage-target XP record is current, not historical. A historical "
            "shadow amount must be entered before projection.")
    if policy.is_cvat:
        snapshot.deemed_cash_value = snapshot.account_value
        snapshot.limitations.append(
            "CVAT deemed-value display follows the Policy tab's account-value convention; "
            "historical NSP and tax-test calculations are not reconstructed.")
    if _is_iul(policy):
        snapshot.limitations.append(_IUL_TOTAL_BASIS)


def build_value_rollback_snapshots(
    pi: PolicyInformation, policy: IllustrationPolicyData,
) -> list[ValueRollbackSnapshot]:
    """Capture recoverable values eagerly through the canonical policy layer.

    Database errors propagate. Missing/ambiguous historical amounts instead
    belong to the snapshot's explicit blockers so the loaded baseline survives.
    """
    anchor = policy.valuation_date
    if anchor is None:
        return []
    dated = _rollback_monthliversary_rows(pi, anchor)
    if not dated:
        return []
    tables = _rollback_source_tables(pi)
    coverages = pi.coverages.get_coverages()
    history, history_error, excluded_pending = _rollback_history_context(tables)
    snapshots = []
    for when, matching in sorted(dated.items(), reverse=True):
        snapshot = _new_rollback_snapshot(when, anchor, excluded_pending)
        if len(matching) != 1:
            snapshot.blocking_errors.append("Multiple U1MV records exist for this date.")
        _apply_monthliversary_amounts(snapshot, policy, matching[0])
        _recover_snapshot_accumulators(
            snapshot, policy, tables, history, history_error, coverages)
        _recover_snapshot_loans(snapshot, tables, policy, history)
        _append_snapshot_policy_limitations(snapshot, policy)
        snapshots.append(snapshot)
    return snapshots
