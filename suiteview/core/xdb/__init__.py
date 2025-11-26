"""XDB (Cross-Database) Query Engine

This module provides the infrastructure for executing queries across multiple
database types (DB2, SQL Server, Access, CSV, Excel) with intelligent filter
pushdown for efficient data retrieval.
"""

from .sources import (
    DataSource,
    DB2Source,
    SQLServerSource,
    AccessSource,
    CSVSource,
    ExcelSource,
    SavedDBQuerySource,
    create_source,
)
from .executor import XDBQueryExecutor

__all__ = [
    'DataSource',
    'DB2Source',
    'SQLServerSource',
    'AccessSource',
    'CSVSource',
    'ExcelSource',
    'SavedDBQuerySource',
    'XDBQueryExecutor',
    'create_source',
]
