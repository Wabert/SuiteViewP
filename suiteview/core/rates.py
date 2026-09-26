"""
SuiteView - Insurance Rates Module
====================================
A rate lookup class that provides cached access to insurance rate tables.

Shared infrastructure for PolView, Inforce Illustration, and any other
module that needs insurance rate lookups from the UL_Rates database.

Originally from PolView, promoted to shared core.

Rate Types:
- COI: Cost of Insurance rates (by duration)
- MTP: Maximum Target Premium (single value)
- CTP: Commission Target Premium (single value)
- TBL1MTP: Table 1 Maximum Target Premium
- TBL1CTP: Table 1 Commission Target Premium
- EPU: Extended Paid-Up rates (by duration)
- SCR: Surrender Charge rates (by duration)
- CORR: Corridor rates (by attained age)
- GINT: Guaranteed Interest rates
- EPP: Expense Per Premium (by duration)
- TPP: Target Premium Percent (by duration)
- MFEE: Monthly Fee rates (by duration)
- BENCOI: Benefit COI rates (by duration)
- BENMTP: Benefit Maximum Target Premium
- BENCTP: Benefit Commission Target Premium
- BANDSPECS: Band specifications for face amount banding
- WL cash values: exact CyberLife user/class-base-sub/issue-age schedules by source duration
- WL/ISWL fixed premiums (WL_RATE_PREM) and mode factors (POINT_MODEFACT/RATE_MODEFACT)
- And more...

Usage:
    from suiteview.core.rates import Rates, get_rates_instance

    rates = Rates()
    coi = rates.get_rates("COI", "UL123", 35, "M", "B", scale=1, band=2)
    band = rates.get_band("UL123", 500000)
"""

from __future__ import annotations

import logging
import pyodbc
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Optional, List, Dict, Any, Union, Tuple

from .local_dev import connect_local_rates_database, local_data_enabled

try:
    from .db2_connection import DB2Connection
except ImportError:
    DB2Connection = None

logger = logging.getLogger(__name__)
_owned_rates: ContextVar[list["Rates"] | None] = ContextVar("owned_rates", default=None)


@contextmanager
def owned_rate_connections():
    """Close all helper-created rate connections on their owning worker."""
    instances = []
    token = _owned_rates.set(instances)
    try:
        yield
    finally:
        try:
            for rates in reversed(instances):
                rates.close()
        finally:
            _owned_rates.reset(token)

# The IUL14 Bonus illustration-rate source splits three fund rates onto
# fund-specific rate plancodes while the policy/parameter plancode stays
# 1U145800. Keep that source-system mapping at the query boundary.
_INDEX_ILLUSTRATION_PLAN_ALIASES = {
    "1U145800": {
        "IC": "1U145801",
        "IF": "1U145802",
        "IS": "1U145803",
    },
}


class RatesError(Exception):
    """Exception for rate lookup errors."""
    pass


# Source-keyed CyberLife rate files (CVF prints, IAF premiums, CKUDT323-325
# mode premium tables) are stored under the CyberLife *user* code, not the
# policy company code. Company 01 shares user 00's entries (online-table
# print: "USER 01 SHARES ENTRIES WITH USER 00"); 04/06/08 are their own users,
# as loaded in UL_Rates. Unlisted companies (e.g. 26) have no verified link.
CYBERLIFE_RATE_USER_BY_COMPANY = {"01": "00", "04": "04", "06": "06", "08": "08"}


def cyberlife_rate_user(company_code: str) -> str:
    """CyberLife rate-file user code for a policy company; never guessed."""
    company = str(company_code or "").strip().zfill(2)
    try:
        return CYBERLIFE_RATE_USER_BY_COMPANY[company]
    except KeyError:
        raise RatesError(
            f"Company {company} has no verified CyberLife rate-file user mapping."
        ) from None


# WL_RATE_PREM rate types, as printed on the IAF.
WL_PREMIUM_RATE_TYPES = {
    "N": "Premium",
    "W": "Target premium",
    "C": "Current COI (IAF)",
    "G": "Guaranteed COI (IAF)",
}

_WL_PREMIUM_COLUMNS = (
    "IAF_VERSION", "EFFECTIVE_DATE", "FIRST_AGE", "LAST_AGE", "IAR_USE", "PAY_AGE",
    "PAY_AGE_USE", "ME_AGE", "ME_AGE_USE", "VALUE_PER_UNIT", "RATE_TYPE",
    "SCALE_START", "SCALE_STOP", "PREMIUM_IDENTIFIER", "DURATION_CODE", "SEX",
    "RATECLASS", "BAND", "PLAN_OPTION", "RATE",
)

_MODEFACT_COLUMNS = (
    "Index(MODEFACT)", "PACS", "PACQ", "PACM", "DIRS", "DIRQ", "DIRM",
    "PACS_FEE", "PACQ_FEE", "PACM_FEE", "DIRS_FEE", "DIRQ_FEE", "DIRM_FEE",
    "POLICY_FEE", "POLICY_FEE_ADD", "POLICY_FEE_RULE", "COLLECTION_FEE",
    "COLLECTION_FEE_ADD", "MULTIPLY_ORDER", "RATING_ORDER", "ROUNDING_RULE",
    "USER_CODE", "MODE_PREM_TABLE", "PAC_FACTOR_TABLE", "PAC_FEE_FACTOR_TABLE",
    "DIR_FACTOR_TABLE", "DIR_FEE_FACTOR_TABLE", "RULES_TABLE", "FACTOR_SOURCE",
)


def _is_query_timeout(error: Exception) -> bool:
    """ODBC SQLSTATE HYT00 (query timeout expired)."""
    args = getattr(error, "args", ()) or ()
    return (bool(args) and str(args[0]).upper() == "HYT00") or "HYT00" in str(error)


def _as_date(value) -> Optional[date]:
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


class Rates:
    """
    Rate lookup class with caching.
    
    Provides access to insurance rate tables from the UL_Rates database.
    Rates are cached to avoid repeated database queries.
    
    Example:
        rates = Rates()
        
        # Get COI rates (returns list by duration)
        coi_rates = rates.get_rates("COI", "UL123", 35, "M", "B", scale=1, band=2)
        
        # Get MTP (returns single value)
        mtp = rates.get_mtp("UL123", 35, "M", "B", 2)
        
        # Get band for face amount
        band = rates.get_band("UL123", 500000)
    """
    
    # Class-level rate cache
    _cache: Dict[str, Any] = {}

    # Plancodes whose surrender charges actually vary by state (i.e. have any
    # non-"AA" State row in Select_RATE_SCR). This set is small (~10) and is
    # loaded once per process; every other plancode uses the "AA" default in a
    # single query. None = not yet loaded.
    _scr_state_plancodes: Optional[set] = None
    
    # Default SQL Server connection settings for UL_Rates database
    DEFAULT_DSN = "UL_Rates"
    QUERY_TIMEOUT = 15          # seconds, interactive (GUI-thread) lookups
    WORKER_QUERY_TIMEOUT = 30   # seconds, background worker lookups
    
    def __init__(self, connection_string: str = None):
        """
        Initialize Rates class.
        
        Args:
            connection_string: Optional ODBC connection string for UL_Rates database.
                             If not provided, uses DSN=UL_Rates.
        """
        self._connection_string = connection_string
        self._connection: Optional[Any] = None
        owned = _owned_rates.get()
        if owned is not None:
            owned.append(self)
    
    def _get_connection(self) -> pyodbc.Connection:
        """Get or create database connection."""
        if self._connection is not None:
            try:
                # Test if connection is alive
                self._connection.execute("SELECT 1")
                return self._connection
            except Exception:
                self.close()

        if local_data_enabled():
            try:
                self._connection = connect_local_rates_database()
            except Exception as e:
                raise RatesError(f"Could not connect to local SuiteView rates database: {e}") from e
            return self._connection
        
        # Create new connection
        options = {"timeout": 15}
        if self._connection_string:
            self._connection = pyodbc.connect(self._connection_string, **options)
        else:
            # Use local ODBC DSN
            try:
                self._connection = pyodbc.connect(
                    f"DSN={self.DEFAULT_DSN}", autocommit=True, **options,
                )
            except Exception as e:
                raise RatesError(f"Could not connect to UL_Rates database via DSN '{self.DEFAULT_DSN}': {e}")
        
        # A read blocked by another session's rate-load transaction must fail
        # loudly instead of hanging the caller (PolView reads on the GUI thread).
        self._connection.timeout = (
            self.WORKER_QUERY_TIMEOUT if _owned_rates.get() is not None else self.QUERY_TIMEOUT
        )
        return self._connection
    
    def _get_rate_key(
        self,
        rate_type: str,
        plancode: str,
        issue_age: int = None,
        sex: str = None,
        rateclass: str = None,
        band: int = None,
        scale: int = None,
        benefit_type: str = None,
        state: str = None
    ) -> str:
        """
        Generate unique cache key for rate lookup.
        
        Mirrors VBA GetRateKey function.
        """
        plancode = (plancode or "").strip()
        
        # Normalize rateclass
        if rateclass == "0":
            rateclass = "N"
        
        key_parts = [rate_type, plancode]
        
        rate_type = rate_type.upper()
        
        if rate_type in ("EPP", "TPP", "FLATP"):
            key_parts.extend([sex, rateclass, band, scale])
        elif rate_type in ("DBD", "GINT"):
            pass  # Just rate_type and plancode
        elif rate_type in ("CORR",):
            key_parts.append(issue_age)
        elif rate_type in ("BONUSAV", "BONUSDUR"):
            key_parts.append(scale)
        elif rate_type in ("MTP", "CTP", "TBL1CTP", "TBL1MTP"):
            key_parts.extend([issue_age, sex, rateclass, band])
        elif rate_type in ("MFEE",):
            key_parts.extend([issue_age, sex, rateclass, band, scale])
        elif rate_type in ("EPU", "COI"):
            key_parts.extend([issue_age, sex, rateclass, band, scale])
        elif rate_type in ("SCR",):
            key_parts.extend([issue_age, sex, rateclass, band, state])
        elif rate_type in ("BENMTP", "BENCTP"):
            key_parts.extend([issue_age, sex, rateclass, band, benefit_type])
        elif rate_type in ("BENCOI",):
            key_parts.extend([issue_age, sex, rateclass, band, benefit_type, scale])
        elif rate_type in ("BANDSPECS", "PLNCRD", "PLNCRG", "RLNCRD", "RLNCRG"):
            pass  # Just rate_type and plancode
        elif rate_type in ("SNETPERIOD",):
            key_parts.append(issue_age)
        elif rate_type in ("RATESPACE", "COI_SCALE"):
            pass  # Just rate_type and plancode
        
        return "_".join(str(p) for p in key_parts if p is not None)
    
    def _create_sql(
        self,
        rate_type: str,
        plancode: str,
        issue_age: int = None,
        sex: str = None,
        rateclass: str = None,
        scale: int = None,
        band: int = None,
        benefit_type: str = None,
        state: str = None
    ) -> Tuple[str, list]:
        """
        Create a parameterized SQL query for rate lookup.

        Returns a ``(sql, params)`` tuple where ``sql`` uses ``?`` placeholders
        and ``params`` is the ordered list of bound values. Values are bound as
        parameters (never string-interpolated) to avoid SQL injection and to
        tolerate values containing quotes.

        Mirrors VBA CreateServerSQLString function.
        """
        rate_type = rate_type.upper()

        # Each entry: (sql_with_placeholders, [ordered params])
        sql_map = {
            "EPP": ("SELECT Rate FROM Select_RATE_EPP WHERE Plancode=? AND IssueVersion=1 AND Sex=? AND Rateclass=? AND Scale=? AND [Band]=?", [plancode, sex, rateclass, scale, band]),
            "TPP": ("SELECT Rate FROM Select_RATE_TPP WHERE Plancode=? AND IssueVersion=1 AND Sex=? AND Rateclass=? AND Scale=? AND [Band]=?", [plancode, sex, rateclass, scale, band]),
            "FLATP": ("SELECT Rate FROM Select_RATE_FLATPREM WHERE Plancode=? AND IssueVersion=1 AND Sex=? AND Rateclass=? AND Scale=? AND [Band]=?", [plancode, sex, rateclass, scale, band]),
            "MFEE": ("SELECT Rate FROM Select_RATE_MFEE WHERE Plancode=? AND IssueVersion=1 AND IssueAge=? AND Sex=? AND Rateclass=? AND Scale=? AND [Band]=?", [plancode, issue_age, sex, rateclass, scale, band]),
            "DBD": ("SELECT Rate FROM Select_RATE_DBD WHERE Plancode=? AND IssueVersion=1", [plancode]),
            "GINT": ("SELECT Rate FROM Select_RATE_GINT WHERE Plancode=? AND IssueVersion=1", [plancode]),
            "CORR": ("SELECT Rate FROM Select_RATE_CORR WHERE Plancode=? AND IssueVersion=1 AND AttainedAge>=?", [plancode, issue_age]),
            "BONUSAV": ("SELECT Rate FROM Select_RATE_BONUSAV WHERE Plancode=? AND IssueVersion=1 AND Scale=?", [plancode, scale]),
            "BONUSDUR": ("SELECT Rate FROM Select_RATE_BONUSDUR WHERE Plancode=? AND IssueVersion=1 AND Scale=?", [plancode, scale]),
            "MTP": ("SELECT Rate FROM Select_RATE_MTP WHERE Plancode=? AND IssueVersion=1 AND IssueAge=? AND Sex=? AND Rateclass=? AND [Band]=?", [plancode, issue_age, sex, rateclass, band]),
            "CTP": ("SELECT Rate FROM Select_RATE_CTP WHERE Plancode=? AND IssueVersion=1 AND IssueAge=? AND Sex=? AND Rateclass=? AND [Band]=?", [plancode, issue_age, sex, rateclass, band]),
            "TBL1CTP": ("SELECT Rate FROM Select_RATE_TBL1CTP WHERE Plancode=? AND IssueVersion=1 AND IssueAge=? AND Sex=? AND Rateclass=? AND [Band]=?", [plancode, issue_age, sex, rateclass, band]),
            "TBL1MTP": ("SELECT Rate FROM Select_RATE_TBL1MTP WHERE Plancode=? AND IssueVersion=1 AND IssueAge=? AND Sex=? AND Rateclass=? AND [Band]=?", [plancode, issue_age, sex, rateclass, band]),
            "EPU": ("SELECT Rate FROM Select_RATE_EPU WHERE Plancode=? AND IssueVersion=1 AND IssueAge=? AND Sex=? AND Rateclass=? AND Scale=? AND [Band]=?", [plancode, issue_age, sex, rateclass, scale, band]),
            "COI": ("SELECT Rate FROM Select_RATE_COI WHERE Plancode=? AND IssueVersion=1 AND IssueAge=? AND Sex=? AND Rateclass=? AND Scale=? AND [Band]=?", [plancode, issue_age, sex, rateclass, scale, band]),
            "SCR": (
                "SELECT Rate FROM Select_RATE_SCR WHERE Plancode=? AND IssueVersion=1 AND IssueAge=? AND Sex=? AND Rateclass=? AND [Band]=?"
                + (" AND [State]=?" if state else ""),
                [plancode, issue_age, sex, rateclass, band] + ([state] if state else []),
            ),
            "BENMTP": ("SELECT Rate FROM Select_RATE_BENMTP WHERE Plancode=? AND BenefitType=? AND IssueVersion=1 AND IssueAge=? AND Sex=? AND Rateclass=? AND [Band]=?", [plancode, benefit_type, issue_age, sex, rateclass, band]),
            "BENCTP": ("SELECT Rate FROM Select_RATE_BENCTP WHERE Plancode=? AND BenefitType=? AND IssueVersion=1 AND IssueAge=? AND Sex=? AND Rateclass=? AND [Band]=?", [plancode, benefit_type, issue_age, sex, rateclass, band]),
            "BENCOI": ("SELECT Rate FROM Select_RATE_BENCOI WHERE Plancode=? AND BenefitType=? AND IssueVersion=1 AND IssueAge=? AND Sex=? AND Rateclass=? AND [Band]=? AND Scale=?", [plancode, benefit_type, issue_age, sex, rateclass, band, scale]),
            "BANDSPECS": ("SELECT SpecifiedAmount, [Band], [Issue_Date] FROM Select_RATE_BANDSPECS WHERE Plancode=? AND IssueVersion=1", [plancode]),
            "PLNCRD": ("SELECT Rate FROM Select_RATE_PLNCRD WHERE Plancode=? AND IssueVersion=1", [plancode]),
            "PLNCRG": ("SELECT Rate FROM Select_RATE_PLNCRG WHERE Plancode=? AND IssueVersion=1", [plancode]),
            "RLNCRD": ("SELECT Rate FROM Select_RATE_RLNCRD WHERE Plancode=? AND IssueVersion=1", [plancode]),
            "RLNCRG": ("SELECT Rate FROM Select_RATE_RLNCRG WHERE Plancode=? AND IssueVersion=1", [plancode]),
            "SNETPERIOD": ("SELECT Rate FROM Select_RATE_SNETPERIOD WHERE Plancode=? AND IssueVersion=1 AND IssueAge=?", [plancode, issue_age]),
            "RATESPACE": ("SELECT POINT_PVSRB.[Sex], POINT_PVSRB.[Rateclass], POINT_PVSRB.[Band] FROM POINT_PVSRB WHERE [Plancode]=? AND [IssueVersion]=1", [plancode]),
            "COI_SCALE": ("SELECT Date, Scale FROM Select_SCALE_COI WHERE Plancode=? AND IssueVersion=1", [plancode]),
        }

        return sql_map.get(rate_type, ("", []))

    def _fetch_rates(self, sql: str, params: list = None) -> Optional[List]:
        """Execute the parameterized rate query and return result rows.

        Returns ``None`` when the query legitimately matches no rows. Raises
        ``RatesError`` on an actual database failure — a DB error must NOT be
        silently turned into ``None``, because callers treat ``None`` as
        "no rate" and would otherwise compute silently-wrong (zeroed) values.
        """
        if not sql:
            return None

        from .sql_permissions import guard_query_sql

        guard_query_sql(sql)
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params or [])
                rows = cursor.fetchall()
            finally:
                cursor.close()
        except Exception as e:
            logger.error("Rate query failed: %s | SQL: %s | params: %r", e, sql, params)
            if _is_query_timeout(e):
                raise RatesError(
                    "UL_Rates did not answer within the query timeout. The rate tables are "
                    "probably locked by a rate load in progress; try again when it finishes."
                ) from e
            raise RatesError(f"Rate lookup failed: {e}") from e

        if not rows:
            return None

        return rows

    def get_wl_cash_values(
        self, user_code: str, rate_key: str, issue_age: int, user_defined: str = "",
    ) -> Dict[int, Decimal]:
        """Return an exact CVF schedule, retaining duration zero and decimal rates.

        ``user_code`` is the CyberLife rate-file user (see
        ``cyberlife_rate_user``), not the policy company. Blank user-defined
        selects only the blank key, never another variant or user. No match
        returns an empty schedule; database failures propagate.
        """
        company = user_code.strip().upper()
        # Base/subseries are fixed-width source keys; retain their spaces.
        rate_key = rate_key.upper()
        user_defined = user_defined.strip().upper()
        if not re.fullmatch(r"[0-9]{2}", company):
            raise RatesError("Whole Life cash values require a two-digit CyberLife user code.")
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9 ]{5}", rate_key):
            raise RatesError("Whole Life cash values require a six-character class/base/sub key.")
        if isinstance(issue_age, bool) or not isinstance(issue_age, int) or not 0 <= issue_age <= 999:
            raise RatesError("Whole Life cash values require an issue age from 0 to 999.")
        if len(user_defined) > 8:
            raise RatesError("CVF user-defined keys cannot exceed eight characters.")

        rows = self._fetch_rates(
            "SELECT [DURATION], [RATE], [FIRST_DURATION], [LAST_DURATION] "
            "FROM [WL_RATE_CV] WHERE [USER_CODE] = ? AND [RATE_KEY] = ? "
            "AND [ISSUE_AGE] = ? AND [USER_DEFINED] = ? ORDER BY [DURATION]",
            [company, rate_key, issue_age, user_defined],
        )
        if not rows:
            return {}
        first, last = rows[0][2], rows[0][3]
        values = {}
        for duration, rate, row_first, row_last in rows:
            if (row_first, row_last) != (first, last) or duration in values:
                raise RatesError("Inconsistent or duplicate Whole Life cash-value durations.")
            if rate is None:
                raise RatesError("Missing Whole Life cash-value rate.")
            value = Decimal(str(rate))
            if not value.is_finite() or value < 0:
                raise RatesError("Invalid stored cash value; reload the CVF with zero flooring.")
            values[duration] = value
        if first > last or set(values) != set(range(first, last + 1)):
            raise RatesError("Incomplete Whole Life cash-value schedule.")
        return values

    def get_wl_premium_rates(
        self, user_code: str, plancode: str, issue_age: int, issue_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """IAF fixed-premium cells (``WL_RATE_PREM``) for one plan and issue age.

        Returns ``{"rows": [...], "iaf_version", "effective_date", "versions"}``.
        Every rate type is returned (N premium, W target, C/G COI as printed);
        callers choose sex/rateclass/option. When several IAF versions exist,
        the latest effective on or before ``issue_date`` is used; without an
        issue date that choice fails rather than mixing versions. No rows for
        the plan/user/age returns an empty ``rows`` list.
        """
        user_code = str(user_code or "").strip()
        plancode = str(plancode or "").strip().upper()
        if not re.fullmatch(r"[0-9]{2}", user_code):
            raise RatesError("Fixed premiums require a two-digit CyberLife user code.")
        if not plancode:
            raise RatesError("Fixed premiums require a plancode.")
        if isinstance(issue_age, bool) or not isinstance(issue_age, int) or issue_age < 0:
            raise RatesError("Fixed premiums require a nonnegative integer issue age.")
        rows = self._fetch_rates(
            "SELECT " + ", ".join(f"[{c}]" for c in _WL_PREMIUM_COLUMNS) + ", "
            "[SOURCE_PLANCODE], [SOURCE_IAF_VERSION], [SOURCE_EFFECTIVE_DATE] "
            "FROM [WL_RATE_PREM] WHERE [USER_CODE] = ? AND [PLANCODE] = ? "
            "AND [FIRST_AGE] <= ? AND [LAST_AGE] >= ? "
            "ORDER BY [EFFECTIVE_DATE], [RATE_TYPE], [PLAN_OPTION], [SCALE_START], [PREMIUM_IDENTIFIER]",
            [user_code, plancode, issue_age, issue_age],
        ) or []
        records = []
        for raw in rows:
            record = dict(zip(_WL_PREMIUM_COLUMNS + (
                "SOURCE_PLANCODE", "SOURCE_IAF_VERSION", "SOURCE_EFFECTIVE_DATE"), raw))
            for key in ("EFFECTIVE_DATE", "SCALE_START", "SCALE_STOP", "SOURCE_EFFECTIVE_DATE"):
                record[key] = _as_date(record[key])
            for key in ("RATE", "VALUE_PER_UNIT"):
                if record[key] is not None:
                    record[key] = Decimal(str(record[key]))
            for key in ("IAF_VERSION", "RATE_TYPE", "PREMIUM_IDENTIFIER", "DURATION_CODE",
                        "SEX", "RATECLASS", "BAND", "PLAN_OPTION", "SOURCE_PLANCODE",
                        "SOURCE_IAF_VERSION"):
                record[key] = str(record[key] or "").strip()
            if record["RATE"] is None:
                raise RatesError(f"WL_RATE_PREM {plancode} has a NULL rate.")
            if record["IAR_USE"] not in (0, None):
                raise RatesError(
                    f"WL_RATE_PREM {plancode} issue-age-range use {record['IAR_USE']} is not verified."
                )
            records.append(record)
        versions = sorted({(r["EFFECTIVE_DATE"], r["IAF_VERSION"]) for r in records},
                          key=lambda v: (v[0] or date.min, v[1]))
        result = {"rows": [], "iaf_version": None, "effective_date": None, "versions": versions}
        if not versions:
            return result
        eligible = [v for v in versions if issue_date is None or v[0] is None or v[0] <= issue_date]
        if len(versions) > 1 and issue_date is None:
            raise RatesError(f"WL_RATE_PREM {plancode} has several IAF versions; an issue date is required.")
        if not eligible:
            return result
        chosen = eligible[-1]
        if len([v for v in eligible if v[0] == chosen[0]]) > 1:
            raise RatesError(f"WL_RATE_PREM {plancode} has several IAF versions effective {chosen[0]}.")
        selected = [r for r in records if (r["EFFECTIVE_DATE"], r["IAF_VERSION"]) == chosen]
        if len({(r["SOURCE_PLANCODE"], r["SOURCE_IAF_VERSION"], r["SOURCE_EFFECTIVE_DATE"])
                for r in selected}) > 1:
            raise RatesError(f"WL_RATE_PREM {plancode} mixes several source IAF prints.")
        result.update(rows=selected, effective_date=chosen[0], iaf_version=chosen[1])
        return result

    def get_modal_factors(self, plancode: str) -> Dict[str, Any]:
        """Plan mode-premium factors via ``POINT_MODEFACT`` → ``RATE_MODEFACT``.

        Returns ``{"index": None, "factors": None}`` without a pointer and
        ``{"index": idx, "factors": None}`` for a pointer whose table is not
        loaded, so callers can say which source is missing.
        """
        plancode = str(plancode or "").strip().upper()
        pointer = self._fetch_rates(
            "SELECT [Index(MODEFACT)] FROM [POINT_MODEFACT] WHERE [Plancode] = ? AND [IssueVersion] = 1",
            [plancode],
        )
        if not pointer:
            return {"index": None, "factors": None}
        if len(pointer) > 1:
            raise RatesError(f"POINT_MODEFACT has several rows for plancode {plancode}.")
        index = str(pointer[0][0] or "").strip()
        if not index:
            raise RatesError(f"POINT_MODEFACT has a blank index for plancode {plancode}.")
        rows = self._fetch_rates(
            "SELECT " + ", ".join(f"[{c}]" for c in _MODEFACT_COLUMNS)
            + " FROM [RATE_MODEFACT] WHERE [Index(MODEFACT)] = ?",
            [index],
        )
        if not rows:
            return {"index": index, "factors": None}
        if len(rows) > 1:
            raise RatesError(f"RATE_MODEFACT has several rows for {index}.")
        factors = dict(zip(_MODEFACT_COLUMNS, rows[0]))
        for key in _MODEFACT_COLUMNS[1:13] + ("POLICY_FEE", "COLLECTION_FEE"):
            if factors[key] is None:
                raise RatesError(f"RATE_MODEFACT {index} has a NULL {key}.")
            factors[key] = Decimal(str(factors[key]))
        for key in ("POLICY_FEE_ADD", "POLICY_FEE_RULE", "COLLECTION_FEE_ADD",
                    "MULTIPLY_ORDER", "RATING_ORDER", "ROUNDING_RULE", "USER_CODE", "FACTOR_SOURCE"):
            factors[key] = str(factors[key] or "").strip()
        return {"index": index, "factors": factors}

    def get_age_limits(self, plancode: str) -> Dict[str, Optional[int]]:
        """Premium and benefit cease ages from ``POINT_PV.Index(AGE)`` (None if absent)."""
        plancode = str(plancode or "").strip().upper()
        result = {}
        for key, view in (("premium_cease", "Select_RATE_PREMIUMCEASE"),
                          ("benefit_cease", "Select_RATE_BENEFITCEASEAGE")):
            rows = self._fetch_rates(
                f"SELECT [Rate] FROM [{view}] WHERE [Plancode] = ? AND [IssueVersion] = 1", [plancode],
            )
            if rows and len(rows) > 1:
                raise RatesError(f"{view} has several rows for plancode {plancode}.")
            result[key] = int(rows[0][0]) if rows and rows[0][0] is not None else None
        return result

    def get_index_illustration_rates(
        self,
        company: str,
        plancode: str,
        illustration_date: date,
        rga_indicator: str = "",
    ) -> Dict[str, Optional[float]]:
        """Current IUL illustration rate by fund as of ``illustration_date``.

        The most recent effective row on or before the illustration date is used
        for each fund. ``Rate_RGA`` is selected only when the policy's
        reinsurance-partner indicator is ``R``; all other policies use
        ``Rate_ANICO``. A present SQL NULL remains ``None`` so callers can
        surface missing rates instead of silently substituting another value.
        """
        company = (company or "").strip()
        plancode = (plancode or "").strip().upper()
        if not company or not plancode or illustration_date is None:
            return {}
        company = company.zfill(2)

        aliases = _INDEX_ILLUSTRATION_PLAN_ALIASES.get(plancode, {})
        lookup_plancodes = sorted({plancode, *aliases.values()})
        placeholders = ", ".join("?" for _ in lookup_plancodes)
        sql = (
            "SELECT r.[Plancode], r.[FundID], r.[Rate_ANICO], r.[Rate_RGA] "
            "FROM [SV_INDEX_ILL_RATES] r "
            "WHERE r.[Company] = ? "
            f"AND r.[Plancode] IN ({placeholders}) "
            "AND r.[EffDate] = ("
            "SELECT MAX(r2.[EffDate]) FROM [SV_INDEX_ILL_RATES] r2 "
            "WHERE r2.[Company] = r.[Company] "
            "AND r2.[Plancode] = r.[Plancode] "
            "AND r2.[FundID] = r.[FundID] "
            "AND r2.[EffDate] <= ?)"
        )
        rows = self._fetch_rates(
            sql, [company, *lookup_plancodes, illustration_date.isoformat()]
        ) or []
        use_rga = (rga_indicator or "").strip().upper() == "R"
        rates: Dict[str, Optional[float]] = {}
        for row in rows:
            row_plancode = str(row[0] or "").strip().upper()
            fund_id = str(row[1] or "").strip().upper()
            expected_plancode = aliases.get(fund_id, plancode)
            if row_plancode != expected_plancode:
                continue
            value = row[3] if use_rga else row[2]
            rates[fund_id] = None if value is None else float(value)
        return rates

    def get_index_strategy_parameters(
        self,
        plancode: str,
        illustration_date: date,
        rga_indicator: str = "",
    ) -> Dict[str, Dict[str, float]]:
        """Effective IUL strategy parameters by fund as of the illustration date."""
        plancode = (plancode or "").strip().upper()
        rga_indicator = (
            "R" if (rga_indicator or "").strip().upper() == "R" else ""
        )
        if not plancode or illustration_date is None:
            return {}

        sql = (
            "SELECT p.[Fund_ID], p.[FLOOR], p.[CAP], p.[PARTICIPATION], "
            "p.[INT_RATE_SPREAD], p.[SPECIFIED_RATE], p.[MULTIPLIER], "
            "p.[ASSET_FEE] "
            "FROM [SV_INDEX_PARAMS] p "
            "WHERE p.[Plancode] = ? AND p.[RGA_Ind] = ? "
            "AND p.[DATE] = ("
            "SELECT MAX(p2.[DATE]) FROM [SV_INDEX_PARAMS] p2 "
            "WHERE p2.[Plancode] = p.[Plancode] "
            "AND p2.[RGA_Ind] = p.[RGA_Ind] "
            "AND p2.[Fund_ID] = p.[Fund_ID] "
            "AND p2.[DATE] <= ?)"
        )
        rows = self._fetch_rates(
            sql, [plancode, rga_indicator, illustration_date.isoformat()]
        ) or []
        columns = (
            "floor",
            "cap",
            "participation",
            "int_rate_spread",
            "specified_rate",
            "multiplier",
            "asset_fee",
        )
        return {
            str(row[0] or "").strip().upper(): {
                column: float(value)
                for column, value in zip(columns, row[1:])
            }
            for row in rows
        }

    def get_index_benchmark_minmax(
        self,
        plancode: str,
        illustration_date: date,
        rga_indicator: str = "",
        fund_id: str = "IX",
    ) -> Optional[Dict[str, float]]:
        """Current benchmark geometric-average minimum and maximum."""
        plancode = (plancode or "").strip().upper()
        fund_id = (fund_id or "").strip().upper()
        rga_indicator = (
            "R" if (rga_indicator or "").strip().upper() == "R" else ""
        )
        if not plancode or not fund_id or illustration_date is None:
            return None

        sql = (
            "SELECT b.[MIN_GEOMETRIC_AVG], b.[MAX_GEOMETRIC_AVG] "
            "FROM [SV_INDEX_BENCHMARK_MINMAX] b "
            "WHERE b.[PLAN_ID] = ? AND b.[REIN_BLOCK_IND] = ? "
            "AND b.[FUND_ID] = ? AND b.[EFFECTIVE_DATE] = ("
            "SELECT MAX(b2.[EFFECTIVE_DATE]) FROM [SV_INDEX_BENCHMARK_MINMAX] b2 "
            "WHERE b2.[PLAN_ID] = b.[PLAN_ID] "
            "AND b2.[REIN_BLOCK_IND] = b.[REIN_BLOCK_IND] "
            "AND b2.[FUND_ID] = b.[FUND_ID] "
            "AND b2.[EFFECTIVE_DATE] <= ?)"
        )
        rows = self._fetch_rates(
            sql,
            [plancode, rga_indicator, fund_id, illustration_date.isoformat()],
        )
        if not rows:
            return None
        return {
            "minimum": float(rows[0][0]),
            "maximum": float(rows[0][1]),
        }

    def get_index_market_returns(self) -> Dict[str, List[Dict[str, Any]]]:
        """Year-end returns used by the IUL historical lookback report."""
        rows = self._fetch_rates(
            "SELECT [DateEOY], [MarketIndex], [OneYrReturn] "
            "FROM [SV_INDEX_MARKET_RETURNS] "
            "ORDER BY [DateEOY], [MarketIndex]",
            [],
        ) or []
        returns: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            market_index = str(row[1] or "").strip().upper()
            date_eoy = date.fromisoformat(str(row[0])[:10])
            returns.setdefault(market_index, []).append({
                "date": date_eoy,
                "return": float(row[2]),
            })
        return returns

    def _scr_plancode_varies(self, plancode: str) -> bool:
        """True if this plancode has any state-specific (non-"AA") surrender
        charge schedule.

        The set of such plancodes is small (~10) and is loaded once per process,
        so the common case (plancodes that only have an "AA" schedule) never
        pays for a wasted state-specific query.
        """
        if Rates._scr_state_plancodes is None:
            self._load_scr_state_plancodes()
        return (plancode or "").strip().upper() in Rates._scr_state_plancodes

    def _load_scr_state_plancodes(self) -> None:
        """Populate the cached set of plancodes that have non-"AA" SCR schedules.

        A failure here must not break rate lookups: on error the set is left
        empty, so every plancode falls back to the "AA" default schedule.
        """
        plancodes: set = set()
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT DISTINCT Plancode FROM Select_RATE_SCR WHERE [State] <> 'AA'"
                )
                plancodes = {
                    str(row[0]).strip().upper()
                    for row in cursor.fetchall() if row[0] is not None
                }
            finally:
                cursor.close()
        except Exception as e:
            logger.warning("Could not load state-varying SCR plancodes: %s", e)
        Rates._scr_state_plancodes = plancodes
    
    def get_rates(
        self,
        rate_type: str,
        plancode: str,
        issue_age: int = None,
        sex: str = None,
        rateclass: str = None,
        scale: int = 1,
        band: int = None,
        specified_amount: float = 0,
        benefit_type: str = "",
        state: str = None
    ) -> Optional[Union[List[float], List[List]]]:
        """
        Get rates from cache or database.
        
        Args:
            rate_type: Type of rate (COI, MTP, CTP, etc.)
            plancode: Product plan code
            issue_age: Issue age (optional for some rate types)
            sex: Sex code (M/F)
            rateclass: Rate class code
            scale: Rate scale (default 1)
            band: Face amount band
            specified_amount: Specified amount (for band lookup)
            benefit_type: Benefit type code (for benefit rates)
            state: Issue state (2-letter) for state-varying SCR rates; falls
                back to the "AA" default schedule when the plancode has no
                schedule for that state. Ignored for non-SCR rate types.

        Returns:
            List of rates (1-indexed by duration for most types)
            or None if not found. All-NULL TBL1MTP/TBL1CTP rows also mean
            unavailable, not a zero rate; callers must check applicability.
        """
        # Normalize inputs
        plancode = (plancode or "").strip()
        if issue_age is not None:
            issue_age = int(issue_age)
        if band is not None:
            band = int(band)
        if rateclass == "0":
            rateclass = "N"

        # Surrender-charge rates vary by state for only a handful of plancodes
        # (a few states such as DE, NY, NJ, MD differ); every other plancode
        # and state uses the "AA" default schedule. Only those few plancodes pay
        # for a state-specific lookup — all others go straight to "AA" in a single
        # query. The local-dev Select_RATE_SCR has no State column, so state is
        # never applied there.
        scr_state = None
        if rate_type.upper() == "SCR" and not local_data_enabled():
            requested_state = (state or "AA").strip().upper() or "AA"
            if requested_state != "AA" and self._scr_plancode_varies(plancode):
                scr_state = requested_state
            else:
                scr_state = "AA"

        # Generate cache key
        rate_key = self._get_rate_key(
            rate_type, plancode, issue_age, sex, rateclass, band, scale, benefit_type, scr_state
        )
        
        # Check cache
        if rate_key in self._cache:
            return self._cache[rate_key]
        
        # Fetch from database
        sql, params = self._create_sql(
            rate_type, plancode, issue_age, sex, rateclass, scale, band, benefit_type, scr_state
        )

        rows = self._fetch_rates(sql, params)

        # State fallback: a policy whose state has no plancode-specific
        # surrender-charge schedule uses the "AA" default schedule.
        if rows is None and scr_state is not None and scr_state != "AA":
            sql, params = self._create_sql(
                rate_type, plancode, issue_age, sex, rateclass, scale, band, benefit_type, "AA"
            )
            rows = self._fetch_rates(sql, params)

        if rows is None:
            self._cache[rate_key] = None
            return None
        
        rate_type_upper = rate_type.upper()

        if rate_type_upper in {"TBL1MTP", "TBL1CTP"} and any(
            row[0] is None for row in rows
        ):
            if not all(row[0] is None for row in rows):
                raise RatesError(
                    f"Inconsistent NULL and numeric {rate_type_upper} rates for "
                    f"plancode {plancode}, issue age {issue_age}, sex {sex}, "
                    f"rate class {rateclass}, band {band}."
                )
            self._cache[rate_key] = None
            return None
        
        # Process results based on rate type
        if rate_type_upper == "BANDSPECS":
            # Returns 2D array of [SpecifiedAmount, Band, Issue_Date]. Issue_Date
            # is the effective-from date of that band set (sentinel 1900-01-01 =
            # "from the beginning"); get_band() selects the set effective for the
            # POLICY issue date. Tolerate a 2-column row (a mirror without the
            # Issue_Date column) by defaulting Issue_Date to None.
            result = [
                [row[0], row[1], (row[2] if len(row) > 2 else None)]
                for row in rows
            ]
            self._cache[rate_key] = result
        elif rate_type_upper == "COI_SCALE":
            # Returns raw rows
            result = rows
            self._cache[rate_key] = result
        elif rate_type_upper == "RATESPACE":
            # Returns 2D array
            result = [[row[0], row[1], row[2]] for row in rows]
            self._cache[rate_key] = result
        else:
            # Most rate types return 1D array indexed by duration
            # Convert to 1-indexed list (index 0 is empty, duration 1 = index 1)
            result = [None] + [float(row[0]) for row in rows]
            self._cache[rate_key] = result
        
        return self._cache[rate_key]
    
    def get_band(
        self,
        plancode: str,
        specified_amount: float,
        issue_date=None,
    ) -> Optional[int]:
        """
        Get band number for specified amount, effective for the POLICY issue date.

        Thresholds are INCLUSIVE — the band is the highest BANDSPECS row whose
        SpecifiedAmount is <= face. This matches RERUN's band lookup
        (CalcEngine ``vCurrentBand = VLOOKUP(face, mBandTable<code>, 2)``, an
        approximate-match VLOOKUP).

        ISSUE-DATE-DEPENDENT BANDING (single source of truth = the data):
        ``RATE_BANDSPECS.Issue_Date`` lets a plancode's band breakpoints vary by
        issue date. Each distinct ``Issue_Date`` is one complete band set that is
        effective from that date forward (sentinel ``1900-01-01`` = "from the
        beginning"). When a plancode has more than one effective-dated set, the
        set whose ``Issue_Date`` is the latest on/before the **policy** issue date
        is used — exactly mirroring ``TERM_RATE_BANDSPECS`` on the ABR side.

        You MUST pass the POLICY issue date here, never the coverage issue date:
        a policy's band structure is fixed by when the *policy* was issued, and
        all base coverages share it. (Riders are banded on their own face amount
        but still under the base plancode's dateless call — the CZ rule below and
        the effective-dating apply to base plancodes only.)

        LEGACY CZ FALLBACK (transitional): before a CZ plancode's effective-dated
        rows are curated in ``RATE_BANDSPECS`` it still has a single (1900-01-01)
        set holding the mBandTable2 thresholds (band 3 @ 250,000). For those
        plancodes RERUN's Rates_Control!CZ rule shifts the band-3 start to 250,001
        for policies issued before the cutoff (Rates_Control!CZ9 = 2018-10-01).
        That $1 shift is applied here ONLY while the plancode still has fewer than
        two effective-dated sets; once the effective-dated rows exist in the data,
        the data drives banding and this fallback is skipped (no double-adjust).

        Args:
            plancode: Product plan code
            specified_amount: Face amount to band
            issue_date: POLICY issue date (RERUN sINPUT_Issue_Date), a
                datetime.date/datetime. Pass it whenever known. When omitted,
                the earliest (1900-01-01) band set is used and the legacy CZ
                shift is not applied.

        Returns:
            Band number or None if not found
        """
        band_specs = self.get_rates("BANDSPECS", plancode)
        if not band_specs:
            return None

        rows = self._effective_band_rows(plancode, band_specs, issue_date)
        if not rows:
            return None

        # rows is [[amount1, band1], [amount2, band2], ...] sorted by amount asc.
        # Find the highest band where specified_amount >= threshold.
        band_count = len(rows)
        while band_count > 0:
            if specified_amount >= rows[band_count - 1][0]:
                return int(rows[band_count - 1][1])
            band_count -= 1

        return int(rows[0][1]) if rows else None

    @staticmethod
    def _coerce_date(value):
        """Normalize a date/datetime/'YYYY-MM-DD' string to a ``date`` (or None)."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    def _effective_band_rows(self, plancode, band_specs, issue_date):
        """Resolve the ``[amount, band]`` rows effective for ``issue_date``.

        ``band_specs`` rows are ``[SpecifiedAmount, Band, Issue_Date]`` (a legacy
        2-element row without Issue_Date is tolerated). When two or more distinct
        Issue_Dates are present the set is picked by policy-issue-date effectivity
        (latest Issue_Date on/before the policy issue date). Otherwise the legacy
        Rates_Control-CZ $1 band-3 shift is applied as a transitional fallback.
        Returns rows sorted by SpecifiedAmount ascending.
        """
        parsed = []
        for row in band_specs:
            amount = row[0]
            band = int(row[1])
            eff = self._coerce_date(row[2]) if len(row) > 2 else None
            parsed.append((amount, band, eff))

        distinct_dates = sorted({eff for _, _, eff in parsed if eff is not None})

        if len(distinct_dates) >= 2:
            # Data-driven effective dating (single source of truth).
            ref = self._coerce_date(issue_date) or date(1900, 1, 1)
            effective = distinct_dates[0]
            for eff in distinct_dates:
                if eff <= ref:
                    effective = eff
            rows = [[amount, band] for amount, band, eff in parsed if eff == effective]
        else:
            # Legacy transitional path: a single (or no) effective-dated set.
            rows = [[amount, band] for amount, band, _ in parsed]
            if issue_date is not None:
                cutoff = self._band_table2_cutoff(plancode)
                if cutoff is not None:
                    ref = self._coerce_date(issue_date)
                    if ref is not None and ref < cutoff:
                        # Pre-cutoff issues band with RERUN mBandTable1: the
                        # band-3 threshold is one dollar higher (250,001 vs the
                        # 250,000 stored in BANDSPECS); all other rows identical.
                        rows = [
                            [amount + 1 if band == 3 else amount, band]
                            for amount, band in rows
                        ]

        rows.sort(key=lambda r: r[0])
        return rows

    @staticmethod
    def _band_table2_cutoff(plancode: str):
        """Cutoff date for the Rates_Control-CZ band rule, or None.

        Reads ``BandTable2IssueDate`` from the illustration plancode table
        (the single source of truth for the CZ plancode list — see
        tools/rates/merge_band_table2_date.py). Plancodes without a row in that
        table (e.g. Traditional products) have no issue-date banding rule.
        """
        try:
            from suiteview.core.plancode_rules import band_table2_issue_date

            return band_table2_issue_date(plancode)
        except (ValueError, FileNotFoundError):
            return None

    def get_band_break(
        self, plancode: str, band: int = 2, issue_date=None
    ) -> Optional[float]:
        """Get the face-amount threshold at which ``band`` begins.

        Used by ratchet banding: net amount at risk up to this break is charged
        at band 1's COI rate, and the excess at band 2's rate (RERUN CalcEngine
        ``QG = Band 2 Amount``). Returns the ``SpecifiedAmount`` from BANDSPECS for
        the requested band (e.g. 50000 for the 2-band plancode 1U130N2X), or
        ``None`` if the plancode has no such band.

        ``issue_date`` is the POLICY issue date; it selects the effective-dated
        band set the same way ``get_band`` does.
        """
        band_specs = self.get_rates("BANDSPECS", plancode)
        if not band_specs:
            return None
        rows = self._effective_band_rows(plancode, band_specs, issue_date)
        for amount, spec_band in rows:
            if int(spec_band) == int(band):
                return float(amount)
        return None

    # =========================================================================
    # CONVENIENCE METHODS FOR SPECIFIC RATE TYPES
    # =========================================================================
    
    def get_mtp(
        self,
        plancode: str,
        issue_age: int,
        sex: str,
        rateclass: str,
        band: int
    ) -> Optional[float]:
        """Get Maximum Target Premium."""
        rates = self.get_rates("MTP", plancode, issue_age, sex, rateclass, band=band)
        return rates[1] if rates and len(rates) > 1 else None
    
    def get_ctp(
        self,
        plancode: str,
        issue_age: int,
        sex: str,
        rateclass: str,
        band: int
    ) -> Optional[float]:
        """Get Commission Target Premium."""
        rates = self.get_rates("CTP", plancode, issue_age, sex, rateclass, band=band)
        return rates[1] if rates and len(rates) > 1 else None
    
    def get_tbl1_mtp(
        self,
        plancode: str,
        issue_age: int,
        sex: str,
        rateclass: str,
        band: int
    ) -> Optional[float]:
        """Get Table 1 Maximum Target Premium."""
        rates = self.get_rates("TBL1MTP", plancode, issue_age, sex, rateclass, band=band)
        return rates[1] if rates and len(rates) > 1 else None
    
    def get_tbl1_ctp(
        self,
        plancode: str,
        issue_age: int,
        sex: str,
        rateclass: str,
        band: int
    ) -> Optional[float]:
        """Get Table 1 Commission Target Premium."""
        rates = self.get_rates("TBL1CTP", plancode, issue_age, sex, rateclass, band=band)
        return rates[1] if rates and len(rates) > 1 else None
    
    def get_coi(
        self,
        plancode: str,
        issue_age: int,
        sex: str,
        rateclass: str,
        scale: int,
        band: int,
        duration: int = None
    ) -> Optional[Union[List[float], float]]:
        """
        Get Cost of Insurance rates.
        
        Args:
            duration: If provided, returns rate for specific duration.
                     Otherwise returns full rate array.
        """
        rates = self.get_rates("COI", plancode, issue_age, sex, rateclass, scale, band)
        if rates is None:
            return None
        if duration is not None:
            return rates[duration] if duration < len(rates) else None
        return rates
    
    def get_epu(
        self,
        plancode: str,
        issue_age: int,
        sex: str,
        rateclass: str,
        scale: int,
        band: int,
        duration: int = None
    ) -> Optional[Union[List[float], float]]:
        """Get Extended Paid-Up rates."""
        rates = self.get_rates("EPU", plancode, issue_age, sex, rateclass, scale, band)
        if rates is None:
            return None
        if duration is not None:
            return rates[duration] if duration < len(rates) else None
        return rates
    
    def get_scr(
        self,
        plancode: str,
        issue_age: int,
        sex: str,
        rateclass: str,
        band: int,
        duration: int = None,
        state: str = None
    ) -> Optional[Union[List[float], float]]:
        """Get Surrender Charge rates.

        ``state`` is the policy's 2-letter issue state; the lookup uses the
        state-specific schedule when the plancode has one and otherwise falls
        back to the "AA" default.
        """
        rates = self.get_rates("SCR", plancode, issue_age, sex, rateclass, band=band, state=state)
        if rates is None:
            return None
        if duration is not None:
            return rates[duration] if duration < len(rates) else None
        return rates
    
    def get_corr(
        self,
        plancode: str,
        issue_age: int,
        attained_age: int = None
    ) -> Optional[Union[List[float], float]]:
        """Get Corridor rates."""
        rates = self.get_rates("CORR", plancode, issue_age)
        if rates is None:
            return None
        if attained_age is not None:
            # Corridor rates are indexed by attained age relative to issue age
            idx = attained_age - issue_age + 1
            return rates[idx] if idx < len(rates) else None
        return rates
    
    def get_gint(self, plancode: str, duration: int = None) -> Optional[Union[List[float], float]]:
        """Get Guaranteed Interest rates."""
        rates = self.get_rates("GINT", plancode)
        if rates is None:
            return None
        if duration is not None:
            return rates[duration] if duration < len(rates) else None
        return rates
    
    def get_epp(
        self,
        plancode: str,
        sex: str,
        rateclass: str,
        scale: int,
        band: int,
        duration: int = None
    ) -> Optional[Union[List[float], float]]:
        """Get Expense Per Premium rates."""
        rates = self.get_rates("EPP", plancode, sex=sex, rateclass=rateclass, scale=scale, band=band)
        if rates is None:
            return None
        if duration is not None:
            return rates[duration] if duration < len(rates) else None
        return rates
    
    def get_tpp(
        self,
        plancode: str,
        sex: str,
        rateclass: str,
        scale: int,
        band: int,
        duration: int = None
    ) -> Optional[Union[List[float], float]]:
        """Get Target Premium Percent rates."""
        rates = self.get_rates("TPP", plancode, sex=sex, rateclass=rateclass, scale=scale, band=band)
        if rates is None:
            return None
        if duration is not None:
            return rates[duration] if duration < len(rates) else None
        return rates
    
    def get_mfee(
        self,
        plancode: str,
        issue_age: int,
        sex: str,
        rateclass: str,
        scale: int,
        band: int,
        duration: int = None
    ) -> Optional[Union[List[float], float]]:
        """Get Monthly Fee rates."""
        rates = self.get_rates("MFEE", plancode, issue_age, sex, rateclass, scale, band)
        if rates is None:
            return None
        if duration is not None:
            return rates[duration] if duration < len(rates) else None
        return rates
    
    def get_ben_coi(
        self,
        plancode: str,
        issue_age: int,
        sex: str,
        rateclass: str,
        scale: int,
        band: int,
        benefit_type: str,
        duration: int = None
    ) -> Optional[Union[List[float], float]]:
        """Get Benefit COI rates."""
        rates = self.get_rates("BENCOI", plancode, issue_age, sex, rateclass, scale, band, benefit_type=benefit_type)
        if rates is None:
            return None
        if duration is not None:
            return rates[duration] if duration < len(rates) else None
        return rates
    
    def get_ben_mtp(
        self,
        plancode: str,
        issue_age: int,
        sex: str,
        rateclass: str,
        band: int,
        benefit_type: str
    ) -> Optional[float]:
        """Get Benefit Maximum Target Premium."""
        rates = self.get_rates("BENMTP", plancode, issue_age, sex, rateclass, band=band, benefit_type=benefit_type)
        return rates[1] if rates and len(rates) > 1 else None
    
    def get_ben_ctp(
        self,
        plancode: str,
        issue_age: int,
        sex: str,
        rateclass: str,
        band: int,
        benefit_type: str
    ) -> Optional[float]:
        """Get Benefit Commission Target Premium."""
        rates = self.get_rates("BENCTP", plancode, issue_age, sex, rateclass, band=band, benefit_type=benefit_type)
        return rates[1] if rates and len(rates) > 1 else None
    
    def clear_cache(self):
        """Clear the rate cache."""
        self._cache.clear()
    
    def close(self):
        """Close database connection."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                logger.exception("Could not close rates connection")
            self._connection = None


# Module-level singleton for convenience
_rates_instance: Optional[Rates] = None


def get_rates_instance(connection_string: str = None) -> Rates:
    """
    Get or create singleton Rates instance.
    
    Args:
        connection_string: Optional connection string (only used on first call)
        
    Returns:
        Rates instance
    """
    global _rates_instance
    owned = _owned_rates.get()
    if owned is not None:
        for instance in owned:
            if instance._connection_string == connection_string:
                return instance
        return Rates(connection_string)
    if _rates_instance is None:
        _rates_instance = Rates(connection_string)
    return _rates_instance
