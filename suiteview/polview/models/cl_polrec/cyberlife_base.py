"""
Cyberlife Base — Protocol and utilities for all record modules.

PolicyDataAccessor defines the contract that each CL_POLREC_*
module requires from the host (PolicyInformation).  Any object satisfying
this protocol can be injected, making record classes testable in isolation.

ALL_CAPS convention:
- Protocol method parameter names use ALL_CAPS for DB2 identifiers
  (TABLE_NAME, FIELD_NAME, FILTER_FIELD, RETURN_FIELD)
- This mirrors the Cyberlife mainframe naming convention
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Protocol — what each record class needs from the host
# ---------------------------------------------------------------------------

@runtime_checkable
class PolicyDataAccessor(Protocol):
    """Contract for raw DB2 data access.

    PolicyInformation already satisfies this protocol.
    """

    def data_item(
        self, TABLE_NAME: str, FIELD_NAME: str, index: int = 0
    ) -> Any:
        """Get a single field value by TABLE_NAME, FIELD_NAME, row index."""
        ...

    def data_item_array(
        self, TABLE_NAME: str, FIELD_NAME: str
    ) -> List[Any]:
        """Get all values for a field across every row."""
        ...

    def data_item_count(self, TABLE_NAME: str) -> int:
        """Get the row count for a table."""
        ...

    def fetch_table(
        self, TABLE_NAME: str
    ) -> List[Dict[str, Any]]:
        """Get entire table as list of row dictionaries."""
        ...

    def find_row_index(
        self, TABLE_NAME: str, FILTER_FIELD: str, filter_value: Any
    ) -> int:
        """Find first matching row index (-1 if not found)."""
        ...

    def data_item_where(
        self,
        TABLE_NAME: str,
        RETURN_FIELD: str,
        FILTER_FIELD: str,
        filter_value: Any,
        default: Any = None,
    ) -> Any:
        """Get a field value from first row matching a filter."""
        ...

    def data_item_where_multi(
        self,
        TABLE_NAME: str,
        RETURN_FIELD: str,
        filters: Dict[str, Any],
        default: Any = None,
    ) -> Any:
        """Get a field value from first row matching multiple filters."""
        ...

    def data_items_where(
        self,
        TABLE_NAME: str,
        RETURN_FIELD: str,
        FILTER_FIELD: str,
        filter_value: Any,
    ) -> List[Any]:
        """Get ALL matching field values for a filter."""
        ...

    def get_rows_where(
        self,
        TABLE_NAME: str,
        FILTER_FIELD: str,
        filter_value: Any,
    ) -> List[Dict[str, Any]]:
        """Get all row dicts matching a filter."""
        ...


# ---------------------------------------------------------------------------
# Shared utility — date parsing
# ---------------------------------------------------------------------------

def parse_date(value: Any) -> Optional[date]:
    """Parse a date value from DB2.

    Handles:
    - None / empty / "0" / "0001-..." → None
    - Python date / datetime pass-through
    - ISO format ("2024-01-15")
    - Cyberlife CYMD format ("1240115" → 2024-01-15)
    """
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()

    str_val = str(value).strip()
    if not str_val or str_val == "0" or str_val.startswith("0001"):
        return None

    # ISO format
    try:
        return datetime.strptime(str_val[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        pass

    # CYMD format (e.g. 1240115 → 2024-01-15)
    try:
        if len(str_val) == 7 and str_val.isdigit():
            century = 19 if str_val[0] == "0" else 20
            year = century * 100 + int(str_val[1:3])
            month = int(str_val[3:5])
            day = int(str_val[5:7])
            return date(year, month, day)
    except (ValueError, TypeError):
        pass

    return None
