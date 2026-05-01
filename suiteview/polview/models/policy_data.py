"""
SuiteView Python – PolicyData Module
======================================
Raw DB2 data access with lazy-loaded table caching.

One instance per policy.  All table data is cached on first access.
PolicyInformation delegates all data_item / fetch_table calls here.

Data flow:
    PolicyData(policy_number, region)
      → _load_policy()        validates policy, resolves company
      → _ensure_table_loaded() lazy-fetches via SQL → _table_cache
      → data_item / fetch_table / data_item_count ... public helpers
"""

from __future__ import annotations

import sys
from typing import Optional, List, Dict, Any
from datetime import date, datetime

# Use the shared database connection module
from suiteview.core.db2_connection import DB2Connection as _DB2Connection


# =============================================================================
# CONNECTION MANAGER (delegates to the shared DB2Connection class)
# =============================================================================

class _ConnectionManager:
    """Singleton connection manager – delegates to shared DB2Connection."""

    _instance: Optional[_ConnectionManager] = None
    _db_instances: Dict[str, _DB2Connection] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_connection(self, region: str):
        """Get or create connection for region via shared DB2Connection."""
        region = region.upper()
        if region not in self._db_instances:
            self._db_instances[region] = _DB2Connection(region)
        return self._db_instances[region].connect()

    def close_all(self):
        """Close all cached connections."""
        _DB2Connection.close_all()
        self._db_instances.clear()


# =============================================================================
# POLICY DATA CLASS
# =============================================================================

class PolicyData:
    """Raw DB2 data access with lazy-loaded table caching.

    One instance per policy.  Every table is fetched once on first access
    and cached for the lifetime of the instance.

    Example::

        data = PolicyData("16335939", region="CKPR")
        if data.exists:
            status = data.data_item("LH_BAS_POL", "STS_CD")
            plancodes = data.data_item_array("LH_COV_PHA", "PLN_DES_SER_CD")
    """

    def __init__(
        self,
        policy_number: str,
        company_code: str = None,
        system_code: str = "I",
        region: str = "CKPR",
    ):
        self._policy_number = policy_number.strip()
        self._company_code = company_code
        self._system_code = system_code
        self._region = region.upper()

        # State
        self._policy_id: Optional[str] = None
        self._exists: bool = False
        self._cancelled: bool = False
        self._last_error: str = ""
        self._available_companies: List[str] = []

        # Table cache:  {table_name: {"columns": [...], "rows": [...]}}
        self._table_cache: Dict[str, Dict] = {}

        # Connection
        self._conn_mgr = _ConnectionManager()

        # Load policy header (validates existence, resolves company)
        self._load_policy()

    # =========================================================================
    # PUBLIC STATE PROPERTIES
    # =========================================================================

    @property
    def exists(self) -> bool:
        """Whether the policy exists in the database."""
        return self._exists

    @property
    def cancelled(self) -> bool:
        """Whether loading was cancelled or errored."""
        return self._cancelled

    @property
    def last_error(self) -> str:
        """Last error message if cancelled."""
        return self._last_error

    @property
    def policy_number(self) -> str:
        return self._policy_number

    @property
    def company_code(self) -> Optional[str]:
        return self._company_code

    @property
    def system_code(self) -> str:
        return self._system_code

    @property
    def region(self) -> str:
        return self._region

    @property
    def policy_id(self) -> Optional[str]:
        return self._policy_id

    @property
    def available_companies(self) -> List[str]:
        """Company codes when policy exists in multiple companies.

        Non-empty only when company_code was not specified at init and
        multiple companies were found.  The UI should present these
        to the user for selection.
        """
        return self._available_companies

    # =========================================================================
    # CORE DATA ACCESS
    # =========================================================================

    def data_item(
        self,
        table_name: str,
        field_name: str,
        index: int = 0,
    ) -> Any:
        """Get a value from any table.field.

        Args:
            table_name: DB2 table name (e.g., ``"LH_BAS_POL"``)
            field_name: Column name
            index: Row index for multi-row tables (0-based)

        Returns:
            Field value or ``None`` if not found
        """
        self._ensure_table_loaded(table_name)

        table_data = self._table_cache.get(table_name)
        if not table_data or not table_data.get("rows"):
            return None

        rows = table_data["rows"]
        columns = table_data["columns"]

        if index >= len(rows):
            return None

        try:
            col_idx = columns.index(field_name.upper())
            return rows[index][col_idx]
        except (ValueError, IndexError):
            return None

    def data_item_array(self, table_name: str, field_name: str) -> List[Any]:
        """Get all values for a field as a list."""
        self._ensure_table_loaded(table_name)

        table_data = self._table_cache.get(table_name)
        if not table_data or not table_data.get("rows"):
            return []

        rows = table_data["rows"]
        columns = table_data["columns"]

        try:
            col_idx = columns.index(field_name.upper())
            return [row[col_idx] for row in rows]
        except ValueError:
            return []

    def data_item_count(self, table_name: str) -> int:
        """Get row count for a table."""
        self._ensure_table_loaded(table_name)

        table_data = self._table_cache.get(table_name)
        if not table_data:
            return 0

        return len(table_data.get("rows", []))

    def fetch_table(self, table_name: str) -> List[Dict[str, Any]]:
        """Get entire table as list of dictionaries."""
        self._ensure_table_loaded(table_name)

        table_data = self._table_cache.get(table_name)
        if not table_data or not table_data.get("rows"):
            return []

        columns = table_data["columns"]
        return [dict(zip(columns, row)) for row in table_data["rows"]]

    def if_empty(self, value: Any, default: Any = "") -> Any:
        """Return *default* if *value* is ``None`` or empty string."""
        if value is None or value == "":
            return default
        return value

    # =========================================================================
    # FILTERED DATA ACCESS  (common VBA pattern for lookup tables)
    # =========================================================================

    def find_row_index(
        self,
        table_name: str,
        filter_field: str,
        filter_value: Any,
    ) -> int:
        """Find the first row index where *filter_field* equals *filter_value*.

        Returns:
            Row index (0-based) or ``-1`` if not found
        """
        count = self.data_item_count(table_name)
        for i in range(count):
            if str(self.data_item(table_name, filter_field, i)) == str(filter_value):
                return i
        return -1

    def data_item_where(
        self,
        table_name: str,
        return_field: str,
        filter_field: str,
        filter_value: Any,
        default: Any = None,
    ) -> Any:
        """Get a field value from the first row matching a filter."""
        idx = self.find_row_index(table_name, filter_field, filter_value)
        if idx >= 0:
            return self.data_item(table_name, return_field, idx)
        return default

    def data_item_where_multi(
        self,
        table_name: str,
        return_field: str,
        filters: Dict[str, Any],
        default: Any = None,
    ) -> Any:
        """Get a field value from the first row matching *all* filters."""
        count = self.data_item_count(table_name)
        for i in range(count):
            match = True
            for field, value in filters.items():
                if str(self.data_item(table_name, field, i)) != str(value):
                    match = False
                    break
            if match:
                return self.data_item(table_name, return_field, i)
        return default

    def data_items_where(
        self,
        table_name: str,
        return_field: str,
        filter_field: str,
        filter_value: Any,
    ) -> List[Any]:
        """Get ALL values for *return_field* from rows matching a filter."""
        results = []
        count = self.data_item_count(table_name)
        for i in range(count):
            if str(self.data_item(table_name, filter_field, i)) == str(filter_value):
                results.append(self.data_item(table_name, return_field, i))
        return results

    def get_rows_where(
        self,
        table_name: str,
        filter_field: str,
        filter_value: Any,
    ) -> List[Dict[str, Any]]:
        """Get all row dictionaries where *filter_field* equals *filter_value*."""
        self._ensure_table_loaded(table_name)

        table_data = self._table_cache.get(table_name)
        if not table_data or not table_data.get("rows"):
            return []

        columns = table_data["columns"]
        results = []

        try:
            filter_idx = columns.index(filter_field.upper())
            for row in table_data["rows"]:
                if str(row[filter_idx]) == str(filter_value):
                    results.append(dict(zip(columns, row)))
        except ValueError:
            pass

        return results

    # =========================================================================
    # DATE PARSING
    # =========================================================================

    @staticmethod
    def parse_date(value) -> Optional[date]:
        """Parse a date value from DB2.

        Handles ``datetime.date``, ``datetime.datetime``, ISO strings,
        and CyberLife CYMD format (e.g., ``1240115`` → ``2024-01-15``).
        """
        if value is None:
            return None

        if isinstance(value, date):
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

        # CYMD format (e.g., 1240115 → 2024-01-15)
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

    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================

    def refresh(self):
        """Clear table cache and reload policy header from database."""
        self._table_cache.clear()
        self._load_policy()

    def invalidate_table(self, table_name: str):
        """Remove a single table from cache so it is re-fetched next access."""
        self._table_cache.pop(table_name, None)

    # =========================================================================
    # STATIC HELPERS
    # =========================================================================

    @staticmethod
    def find_companies(
        policy_number: str,
        region: str = "CKPR",
        system_code: str = "I",
    ) -> List[str]:
        """Find all company codes that have this policy number.

        Returns a sorted list of distinct ``CK_CMP_CD`` values.
        Used by the UI to detect multi-company policies before loading.
        """
        from suiteview.core.db2_connection import sql_for_region

        conn_mgr = _ConnectionManager()
        try:
            conn = conn_mgr.get_connection(region.upper())
            sql = sql_for_region(
                "WITH DUMBY AS (SELECT 1 FROM SYSIBM.SYSDUMMY1) "
                "SELECT DISTINCT CK_CMP_CD FROM DB2TAB.LH_BAS_POL "
                f"WHERE CK_SYS_CD = '{system_code}' "
                f"AND CK_POLICY_NBR = '{policy_number.strip()}' "
                "ORDER BY CK_CMP_CD",
                region,
            )
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            cursor.close()
            return [str(r[0]).strip() for r in rows]
        except Exception:
            return []

    # =========================================================================
    # INTERNAL — LOADING & CACHING
    # =========================================================================

    def _load_policy(self):
        """Load and validate policy from database."""
        try:
            conn = self._conn_mgr.get_connection(self._region)

            # Build WHERE clause
            where_parts = [
                f"CK_SYS_CD = '{self._system_code}'",
                f"CK_POLICY_NBR = '{self._policy_number}'",
            ]
            if self._company_code:
                where_parts.append(f"CK_CMP_CD = '{self._company_code}'")

            sql = self._add_with_clause(f"""
                SELECT CK_CMP_CD, CK_POLICY_NBR, CK_SYS_CD, TCH_POL_ID
                FROM DB2TAB.LH_BAS_POL
                WHERE {' AND '.join(where_parts)}
            """)

            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                self._exists = False
                self._cancelled = True
                self._last_error = f"Policy {self._policy_number} not found"
                return

            # Handle multiple companies
            if len(rows) > 1 and not self._company_code:
                self._available_companies = sorted(
                    set(str(r[0]).strip() for r in rows)
                )
                self._exists = False
                self._cancelled = False
                self._last_error = ""
                return

            row = rows[0]
            self._company_code = str(row[0]).strip()
            self._policy_id = str(row[3]).strip()
            self._exists = True

        except Exception as e:
            self._exists = False
            self._cancelled = True
            # Walk the exception chain to find the real driver message
            from suiteview.core.db2_connection import _extract_odbc_message
            self._last_error = _extract_odbc_message(e)
            print(
                f"[PolicyData] ERROR loading policy {self._policy_number} "
                f"(region={self._region}): {self._last_error}",
                file=sys.stderr,
            )

    # Tables that should be ordered by COV_PHA_NBR (matches VBA LoadDB2Table)
    _COV_PHA_ORDERED_TABLES = {
        "LH_COV_PHA", "LH_NEW_BUS_COV_PHA", "TH_COV_PHA",
        "LH_SPM_BNF", "TH_SPM_BNF", "LH_SST_XTR_CRG", "TH_SST_XTR_CRG",
        "LH_COV_INS_RNL_RT", "LH_BNF_INS_RNL_RT", "LH_SST_XTR_RNL_RT",
        "LH_COV_TARGET", "LH_COV_SKIPPED_PER",
    }

    # Custom ORDER BY clauses matching VBA aryOrderClause in cls_PolicyData
    _TABLE_ORDER_CLAUSES: dict[str, str] = {
        "LH_COM_TARGET":        "AGT_COM_PHA_NBR",
        "LH_CTT_COM_PHA_WA":    "AGT_ITS_EFF_DT DESC",
        "LH_FND_VAL_LOAN":      "MVRY_DT DESC, FND_VAL_PHA_NBR DESC",
        "LH_CSH_VAL_LOAN":      "MVRY_DT DESC",
        "LH_POL_FND_VAL_TOT":   "MVRY_DT DESC, FND_ID_CD DESC, FND_VAL_PHA_NBR DESC",
        "LH_POL_MVRY_VAL":      "MVRY_DT DESC",
        "LH_UNAPPLIED_PTP":     "ERN_DT_MO_YR_NBR DESC",
        "LH_APPLIED_PTP":       "ERN_DT_MO_YR_NBR DESC",
        "LH_PAID_UP_ADD":       "MVRY_DT DESC",
        "LH_ONE_YR_TRM_ADD":    "MVRY_DT DESC",
        "LH_PTP_ON_DEP":        "MVRY_DT DESC",
        "TH_COV_INS_RNL_RT":    "COV_PHA_NBR, PRS_CD, PRS_SEQ_NBR, SEG_IDX_NBR",
        "LH_BNF_INS_GDL_PRM":   "COV_PHA_NBR, PRS_CD, PRS_SEQ_NBR, SEG_IDX_NBR",
    }

    def _ensure_table_loaded(self, table_name: str):
        """Ensure a table is loaded into cache."""
        if table_name in self._table_cache:
            return

        if not self._exists:
            return

        try:
            conn = self._conn_mgr.get_connection(self._region)

            # Build WHERE clause based on table requirements
            # FH_FIXED table does NOT use CK_SYS_CD
            if table_name == "FH_FIXED":
                where_clause = (
                    f"TCH_POL_ID = '{self._policy_id}' "
                    f"AND CK_CMP_CD = '{self._company_code}'"
                )
                order_clause = " ORDER BY ASOF_DT DESC, SEQ_NO DESC"
            else:
                where_clause = (
                    f"CK_SYS_CD = '{self._system_code}' "
                    f"AND TCH_POL_ID = '{self._policy_id}' "
                    f"AND CK_CMP_CD = '{self._company_code}'"
                )
                if table_name in self._COV_PHA_ORDERED_TABLES:
                    order_clause = " ORDER BY COV_PHA_NBR"
                elif table_name in self._TABLE_ORDER_CLAUSES:
                    order_clause = f" ORDER BY {self._TABLE_ORDER_CLAUSES[table_name]}"
                else:
                    order_clause = ""

            sql = self._add_with_clause(
                f"SELECT * FROM DB2TAB.{table_name} WHERE {where_clause}{order_clause}"
            )

            cursor = conn.cursor()
            cursor.execute(sql)

            columns = [desc[0].upper() for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            cursor.close()

            self._table_cache[table_name] = {
                "columns": columns,
                "rows": rows,
            }

        except Exception as exc:
            print(
                f"[PolicyData] FAILED to load table {table_name} for policy "
                f"{self._policy_number} (region={self._region}, "
                f"company={self._company_code}, sys={self._system_code}, "
                f"pol_id={self._policy_id}): {exc}",
                file=sys.stderr,
            )
            # Cache empty result so we don't retry on every access
            self._table_cache[table_name] = {"columns": [], "rows": []}

    def _add_with_clause(self, sql: str) -> str:
        """Add WITH clause for Office 365 compatibility and apply
        region-specific schema replacement (DB2TAB → CKSR/UNIT/CYBERTEK).
        """
        from suiteview.core.db2_constants import REGION_SCHEMA_MAP, DEFAULT_SCHEMA
        import re as _re

        schema = REGION_SCHEMA_MAP.get(self._region, DEFAULT_SCHEMA)
        if schema != DEFAULT_SCHEMA:
            sql = _re.sub(r"(?i)DB2TAB\.", f"{schema}.", sql)

        if sql.strip().upper().startswith("WITH"):
            return sql
        return f"WITH DUMBY AS (SELECT 1 FROM SYSIBM.SYSDUMMY1) {sql}"

    # =========================================================================
    # REPRESENTATION
    # =========================================================================

    def __repr__(self):
        return (
            f"PolicyData('{self._policy_number}', "
            f"region='{self._region}', "
            f"company='{self._company_code}')"
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def close_all_connections():
    """Close all database connections."""
    _ConnectionManager().close_all()
    _DB2Connection.close_all()
