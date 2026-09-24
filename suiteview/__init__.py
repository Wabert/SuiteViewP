"""SuiteView application package."""

import pyodbc

# Set before the first ODBC environment/connection is created. A closed DV
# connection must not be recycled across workers or returned to its own retry.
# Explicit application-owned connection caches remain in use.
pyodbc.pooling = False

# Single source of truth for the application version.
# Update this value whenever you cut a new distribution (see docs/DEV_GUIDE.md).
__version__ = "4.1"
