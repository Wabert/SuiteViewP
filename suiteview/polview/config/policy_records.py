"""
Policy Record to DB2 Table mappings.

Thin compatibility layer - delegates to data.lookup which loads from
data/policy_record_db2_tables.json (extracted from the SuiteView workbook).
"""

from typing import Dict, List
from ..data import lookup as _data_lookup

# Backward-compatible aliases - these now load from JSON
POLICY_RECORD_TABLES: Dict[str, List[str]] = _data_lookup.get_all_policy_record_tables()


def get_sorted_policy_records() -> List[str]:
    """Return policy records sorted numerically."""
    return _data_lookup.get_sorted_policy_records()


def get_table_description(table_name: str) -> str:
    """Get human-readable description for a table."""
    return _data_lookup.get_table_description(table_name)
