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
from typing import Optional, List, Dict, Any, Union, Tuple

from .local_dev import connect_local_rates_database, local_data_enabled

try:
    from .db2_connection import DB2Connection
except ImportError:
    DB2Connection = None

logger = logging.getLogger(__name__)


class RatesError(Exception):
    """Exception for rate lookup errors."""
    pass


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
    
    def __init__(self, connection_string: str = None):
        """
        Initialize Rates class.
        
        Args:
            connection_string: Optional ODBC connection string for UL_Rates database.
                             If not provided, uses DSN=UL_Rates.
        """
        self._connection_string = connection_string
        self._connection: Optional[Any] = None
    
    def _get_connection(self) -> pyodbc.Connection:
        """Get or create database connection."""
        if self._connection is not None:
            try:
                # Test if connection is alive
                self._connection.execute("SELECT 1")
                return self._connection
            except Exception:
                self._connection = None

        if local_data_enabled():
            try:
                self._connection = connect_local_rates_database()
            except Exception as e:
                raise RatesError(f"Could not connect to local SuiteView rates database: {e}") from e
            return self._connection
        
        # Create new connection
        if self._connection_string:
            self._connection = pyodbc.connect(self._connection_string)
        else:
            # Use local ODBC DSN
            try:
                self._connection = pyodbc.connect(f"DSN={self.DEFAULT_DSN}", autocommit=True)
            except Exception as e:
                raise RatesError(f"Could not connect to UL_Rates database via DSN '{self.DEFAULT_DSN}': {e}")
        
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
            "BANDSPECS": ("SELECT SpecifiedAmount, [Band] FROM Select_RATE_BANDSPECS WHERE Plancode=? AND IssueVersion=1", [plancode]),
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
            raise RatesError(f"Rate lookup failed: {e}") from e

        if not rows:
            return None

        return rows

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
            or None if not found
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
        
        # Process results based on rate type
        if rate_type_upper == "BANDSPECS":
            # Returns 2D array of [SpecifiedAmount, Band]
            result = [[row[0], row[1]] for row in rows]
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
    
    def get_band(self, plancode: str, specified_amount: float) -> Optional[int]:
        """
        Get band number for specified amount.
        
        Args:
            plancode: Product plan code
            specified_amount: Face amount to band
            
        Returns:
            Band number or None if not found
        """
        band_specs = self.get_rates("BANDSPECS", plancode)
        
        if not band_specs:
            return None
        
        # band_specs is [[amount1, band1], [amount2, band2], ...]
        # Find the highest band where specified_amount >= threshold
        band_count = len(band_specs)
        while band_count > 0:
            if specified_amount >= band_specs[band_count - 1][0]:
                return int(band_specs[band_count - 1][1])
            band_count -= 1

        return int(band_specs[0][1]) if band_specs else None

    def get_band_break(self, plancode: str, band: int = 2) -> Optional[float]:
        """Get the face-amount threshold at which ``band`` begins.

        Used by ratchet banding: net amount at risk up to this break is charged
        at band 1's COI rate, and the excess at band 2's rate (RERUN CalcEngine
        ``QG = Band 2 Amount``). Returns the ``SpecifiedAmount`` from BANDSPECS for
        the requested band (e.g. 50000 for the 2-band plancode 1U130N2X), or
        ``None`` if the plancode has no such band.
        """
        band_specs = self.get_rates("BANDSPECS", plancode)
        if not band_specs:
            return None
        # band_specs is [[amount1, band1], [amount2, band2], ...]
        for amount, spec_band in band_specs:
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
                pass
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
    if _rates_instance is None:
        _rates_instance = Rates(connection_string)
    return _rates_instance
