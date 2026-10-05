"""Debug-view shaping for the development-only IUL segment crediting method.

Three Values-tab views read ``MonthlyState.iul_segment_detail``:

* **IUL Accounts** (one row per month): sweep, fixed, collateral and index
  balances, the sweep minimum, every movement total of the month (maturity
  credit, refill, renewal, deposits, draws by step and by account, sweep out,
  interest) and the account-total-versus-engine-AV check.
* **IUL Segment Grid** (one row per month): each strategy in play gets twelve
  columns, one per policy month a segment matures/renews in (``M01``..``M12``),
  holding that segment's month-end value, plus a strategy total. Renewals stay
  in the same column year after year.
* **IUL Segment Ledger** (one row per account event): the audit trail used to
  compare against CyberLife fund activity.
"""
from __future__ import annotations

from typing import Iterable, List

import pandas as pd

from suiteview.illustration.models.calc_state import MonthlyState

# Accounts columns shown first, in this order; other summary keys follow.
_ACCOUNT_ORDER = (
    "Sweep BOM", "Maturity Interest", "Refill to Sweep", "Renewed", "Sweep In",
    "Draw Sweep", "Swept Out", "Sweep Interest", "Collateral Interest", "Sweep Min",
    "Sweep EOM", "Fixed BOM", "Fixed In", "Draw Fixed", "Fixed Interest", "Fixed EOM",
    "Collateral BOM", "Collateral In", "Collateral Released", "Collateral EOM",
    "Index BOM", "Asset Charges", "Index EOM", "Accounts Total", "Engine AV", "Difference",
)


def has_segment_detail(results: Iterable[MonthlyState]) -> bool:
    return any(state.iul_segment_detail for state in results)


def accounts_columns(results: List[MonthlyState]) -> List[str]:
    keys: dict[str, None] = {}
    for state in results:
        keys.update(dict.fromkeys((state.iul_segment_detail or {}).get("summary", {})))
    ordered = [f"IUL {key}" for key in _ACCOUNT_ORDER if key in keys]
    ordered += [f"IUL {key}" for key in sorted(keys) if key not in _ACCOUNT_ORDER]
    return ordered


def segment_funds(results: List[MonthlyState]) -> List[str]:
    funds: dict[str, None] = {}
    for state in results:
        accounts = (state.iul_segment_detail or {}).get("accounts")
        if accounts is not None:
            funds.update(dict.fromkeys(seg.fund_id for seg in accounts.segments))
    return sorted(funds)


def grid_columns(funds: List[str]) -> List[str]:
    columns: List[str] = []
    for fund in funds:
        columns.extend(f"{fund} M{slot:02d}" for slot in range(1, 13))
        columns.append(f"{fund} Total")
    return columns


def month_values(state: MonthlyState, funds: List[str]) -> dict:
    """Accounts and Segment Grid values for one ledger row."""
    detail = state.iul_segment_detail or {}
    if not detail:
        return {}
    row = {f"IUL {key}": value for key, value in detail.get("summary", {}).items()}
    accounts = detail.get("accounts")
    for fund in funds:
        slots = {slot: 0.0 for slot in range(1, 13)}
        for seg in (accounts.segments if accounts is not None else ()):
            if seg.fund_id == fund:
                slots[seg.slot] = slots.get(seg.slot, 0.0) + seg.value
        for slot, value in slots.items():
            row[f"{fund} M{slot:02d}"] = value
        row[f"{fund} Total"] = sum(slots.values())
    return row


LEDGER_COLUMNS = [
    "Date", "Year", "Month", "Step", "Account", "Event", "Segment", "Segment Start",
    "Amount", "Balance After", "Rate", "Note",
]


def ledger_frame(results: List[MonthlyState]) -> pd.DataFrame:
    rows = []
    for state in results:
        for event in (state.iul_segment_detail or {}).get("events", []):
            rows.append({
                "Date": event.date,
                "Year": state.policy_year,
                "Month": state.policy_month,
                "Step": event.step,
                "Account": event.account,
                "Event": event.event,
                "Segment": event.segment_id,
                "Segment Start": event.segment_start,
                "Amount": event.amount,
                "Balance After": event.balance_after,
                "Rate": event.rate,
                "Note": event.note,
            })
    return pd.DataFrame(rows, columns=LEDGER_COLUMNS)
