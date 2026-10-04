"""Skipped-coverage reinstatement rules (LH_COV_SKIPPED_PER + FH_FIXED).

CyberLife records a reinstatement after a lapse gap as an LH_COV_SKIPPED_PER row: LAP_DT
starts a period with no coverage and REN_DT ends it. FH_FIXED carries the PB reinstatement
payment and the PU reinstatement value (the restored account value). A continuous
reinstatement (a $0 PB on the date of a reversed lapse) writes no row and changes nothing.

Option C after a skipped-coverage reinstatement returns only the live premiums paid on or
after the latest REN_DT (PB included, PU excluded) less withdrawals since then. Evidence
(RERUN coverage push, 2026-10-04): CyberLife's stored NAR implies exactly that amount on all
6 option C policies with a lapse gap (UIP88048, UE182343, UE160240, UE127229, UE198313,
UE224365), and the latest REN_DT wins on the two reinstated twice (UIP88048, UE182343). All
25 continuous reinstatements and 38 never-reinstated controls keep lifetime premiums less
net withdrawals.

Assumption (untested, none of the 6 has a withdrawal): withdrawals on or after REN_DT are
subtracted net of the plan's per-withdrawal fee, as the lifetime basis is (4986e58/ed6f306).

EPU duration: the EPU schedule month is the calendar coverage month less the monthliversaries
in (LAP_DT, REN_DT] of the MOST RECENT skipped period only; earlier gaps do not extend it.
Evidence: 111 of 111 lapse-gap policies past their EPU period are on/off as predicted, and
all 13 observed EPU end months match (excluding every gap gets 109; UIP53849 ends after
month 135 = 120 + its latest 15-month gap, UIP76119 after 122 = 120 + 2). COI, %-of-AV
charges, the monthly fee and the policy year keep calendar duration.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

from dateutil.relativedelta import relativedelta

from suiteview.illustration.models.policy_data import SkippedCoveragePeriod

# FH_FIXED premium codes in the option C basis (TRANS): regular, PAC/automatic, PDF,
# discounted, fixed AP, 1035, waiver and the PB reinstatement payment. PU (reinstatement
# value) is not a premium.
OPTION_C_PREMIUM_CODES = frozenset({"PA", "PB", "PD", "PE", "PF", "PI", "PR", "PT", "PQ", "PW"})
# FH_FIXED withdrawal codes (TRANS): gross request, maximum and net withdrawals.
WITHDRAWAL_CODES = frozenset({"SG", "SM", "SN"})


def build_skipped_coverage_periods(
    periods: Iterable,
    transactions: Iterable,
    *,
    premiums_to_date: float,
    withdrawals_to_date: float,
    inforce_withdrawal_fees: float,
    withdrawal_fee: float,
) -> list[SkippedCoveragePeriod]:
    """Map closed LH_COV_SKIPPED_PER rows to ``SkippedCoveragePeriod`` (oldest first).

    ``periods`` carry ``lapse_date``/``reinstatement_date`` (PolView ``SkippedPeriodInfo``);
    a row still open (no REN_DT) is not a reinstatement. ``transactions`` are live FH_FIXED
    rows with ``trans_date``, ``trans_code`` and ``gross_amount``. The totals are the
    in-force LH_POL_TOTALS amounts the engine starts from.
    """
    live = [
        (t.trans_date, t.trans_code, float(t.gross_amount))
        for t in transactions
        if t.trans_date is not None and t.gross_amount is not None
    ]
    lifetime_base = premiums_to_date - max(0.0, withdrawals_to_date - inforce_withdrawal_fees)
    result = []
    for period in periods:
        lapse, reinstated = period.lapse_date, period.reinstatement_date
        if lapse is None or reinstated is None:
            continue
        premiums_since = sum(
            amount for day, code, amount in live
            if code in OPTION_C_PREMIUM_CODES and day >= reinstated)
        withdrawals_since = [
            amount for day, code, amount in live if code in WITHDRAWAL_CODES and day >= reinstated]
        net_withdrawals_since = max(
            0.0, sum(withdrawals_since) - len(withdrawals_since) * withdrawal_fee)
        result.append(SkippedCoveragePeriod(
            lapse_date=lapse,
            reinstatement_date=reinstated,
            option_c_excluded_amount=round(
                lifetime_base - (premiums_since - net_withdrawals_since), 2),
        ))
    return sorted(result, key=lambda period: period.reinstatement_date)


def skipped_option_c_note(period: SkippedCoveragePeriod) -> str:
    """Disclosure when an entered premiums/withdrawals total replaces the recorded basis."""
    return (
        "Premiums and withdrawals to date were entered manually, so the option C "
        "(return-of-premium) amount uses the entered totals in full; the premiums before the "
        f"{period.reinstatement_date:%m/%d/%Y} skipped-coverage reinstatement are not excluded.")


def _completed_months(start: date, end: date) -> int:
    """Whole monthliversaries of ``start`` on or before ``end`` (month-end clamped)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end < start + relativedelta(months=months):
        months -= 1
    return max(months, 0)


def skipped_monthliversaries(anchor: date, lapse_date: date, reinstatement_date: date) -> int:
    """Monthliversaries of ``anchor`` in (``lapse_date``, ``reinstatement_date``]."""
    if reinstatement_date <= lapse_date:
        return 0
    return _completed_months(anchor, reinstatement_date) - _completed_months(anchor, lapse_date)


def epu_schedule_year(
    anchor: date | None,
    period: SkippedCoveragePeriod | None,
    projection_date: date | None,
    calendar_year: int,
) -> int:
    """EPU schedule year on ``projection_date`` for coverage issued on ``anchor``.

    ``calendar_year`` (the unshifted coverage year) is returned unless a skipped-coverage
    period applies to coverage already issued when it lapsed; then the schedule month is
    the calendar month less that period's skipped monthliversaries.
    """
    if (period is None or anchor is None or projection_date is None
            or anchor > period.lapse_date):
        return calendar_year
    skipped = skipped_monthliversaries(anchor, period.lapse_date, period.reinstatement_date)
    if skipped <= 0:
        return calendar_year
    return max(1, (_completed_months(anchor, projection_date) - skipped) // 12 + 1)
