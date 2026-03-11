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

import pyodbc
from typing import Optional, List, Dict, Any, Union

try:
    from .db2_connection import DB2Connection
except ImportError:
    DB2Connection = None


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
        self._connection: Optional[pyodbc.Connection] = None
    
    def _get_connection(self) -> pyodbc.Connection:
        """Get or create database connection."""
        if self._connection is not None:
            try:
                # Test if connection is alive
                self._connection.execute("SELECT 1")
                return self._connection
            except Exception:
                self._connection = None
        
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
        benefit_type: str = None
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
            key_parts.extend([issue_age, sex, rateclass, band])
        elif rate_type in ("BENMTP", "BENCTP"):
            key_parts.extend([issue_age, band, benefit_type])
        elif rate_type in ("BENCOI",):
            key_parts.extend([issue_age, band, benefit_type, scale])
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
        benefit_type: str = None
    ) -> str:
        """
        Create SQL query for rate lookup.
        
        Mirrors VBA CreateServerSQLString function.
        """
        rate_type = rate_type.upper()
        
        sql_map = {
            "EPP": f"SELECT Rate FROM Select_RATE_EPP WHERE Plancode='{plancode}' AND IssueVersion=1 AND Sex='{sex}' AND Rateclass='{rateclass}' AND Scale={scale} AND [Band]={band}",
            "TPP": f"SELECT Rate FROM Select_RATE_TPP WHERE Plancode='{plancode}' AND IssueVersion=1 AND Sex='{sex}' AND Rateclass='{rateclass}' AND Scale={scale} AND [Band]={band}",
            "FLATP": f"SELECT Rate FROM Select_RATE_FLATPREM WHERE Plancode='{plancode}' AND IssueVersion=1 AND Sex='{sex}' AND Rateclass='{rateclass}' AND Scale={scale} AND [Band]={band}",
            "MFEE": f"SELECT Rate FROM Select_RATE_MFEE WHERE Plancode='{plancode}' AND IssueVersion=1 AND IssueAge={issue_age} AND Sex='{sex}' AND Rateclass='{rateclass}' AND Scale={scale} AND [Band]={band}",
            "DBD": f"SELECT Rate FROM Select_RATE_DBD WHERE Plancode='{plancode}' AND IssueVersion=1",
            "GINT": f"SELECT Rate FROM Select_RATE_GINT WHERE Plancode='{plancode}' AND IssueVersion=1",
            "CORR": f"SELECT Rate FROM Select_RATE_CORR WHERE Plancode='{plancode}' AND IssueVersion=1 AND AttainedAge>={issue_age}",
            "BONUSAV": f"SELECT Rate FROM Select_RATE_BONUSAV WHERE Plancode='{plancode}' AND IssueVersion=1 AND Scale={scale}",
            "BONUSDUR": f"SELECT Rate FROM Select_RATE_BONUSDUR WHERE Plancode='{plancode}' AND IssueVersion=1 AND Scale={scale}",
            "MTP": f"SELECT Rate FROM Select_RATE_MTP WHERE Plancode='{plancode}' AND IssueVersion=1 AND IssueAge={issue_age} AND Sex='{sex}' AND Rateclass='{rateclass}' AND [Band]={band}",
            "CTP": f"SELECT Rate FROM Select_RATE_CTP WHERE Plancode='{plancode}' AND IssueVersion=1 AND IssueAge={issue_age} AND Sex='{sex}' AND Rateclass='{rateclass}' AND [Band]={band}",
            "TBL1CTP": f"SELECT Rate FROM Select_RATE_TBL1CTP WHERE Plancode='{plancode}' AND IssueVersion=1 AND IssueAge={issue_age} AND Sex='{sex}' AND Rateclass='{rateclass}' AND [Band]={band}",
            "TBL1MTP": f"SELECT Rate FROM Select_RATE_TBL1MTP WHERE Plancode='{plancode}' AND IssueVersion=1 AND IssueAge={issue_age} AND Sex='{sex}' AND Rateclass='{rateclass}' AND [Band]={band}",
            "EPU": f"SELECT Rate FROM Select_RATE_EPU WHERE Plancode='{plancode}' AND IssueVersion=1 AND IssueAge={issue_age} AND Sex='{sex}' AND Rateclass='{rateclass}' AND Scale={scale} AND [Band]={band}",
            "COI": f"SELECT Rate FROM Select_RATE_COI WHERE Plancode='{plancode}' AND IssueVersion=1 AND IssueAge={issue_age} AND Sex='{sex}' AND Rateclass='{rateclass}' AND Scale={scale} AND [Band]={band}",
            "SCR": f"SELECT Rate FROM Select_RATE_SCR WHERE Plancode='{plancode}' AND IssueVersion=1 AND IssueAge={issue_age} AND Sex='{sex}' AND Rateclass='{rateclass}' AND [Band]={band}",
            "BENMTP": f"SELECT Rate FROM Select_RATE_BENMTP WHERE Plancode='{plancode}' AND BenefitType='{benefit_type}' AND IssueVersion=1 AND IssueAge={issue_age} AND Sex='{sex}' AND Rateclass='{rateclass}' AND [Band]={band}",
            "BENCTP": f"SELECT Rate FROM Select_RATE_BENCTP WHERE Plancode='{plancode}' AND BenefitType='{benefit_type}' AND IssueVersion=1 AND IssueAge={issue_age} AND Sex='{sex}' AND Rateclass='{rateclass}' AND [Band]={band}",
            "BENCOI": f"SELECT Rate FROM Select_RATE_BENCOI WHERE Plancode='{plancode}' AND BenefitType='{benefit_type}' AND IssueVersion=1 AND IssueAge={issue_age} AND Sex='{sex}' AND Rateclass='{rateclass}' AND [Band]={band} AND Scale={scale}",
            "BANDSPECS": f"SELECT SpecifiedAmount, [Band] FROM Select_RATE_BANDSPECS WHERE Plancode='{plancode}' AND IssueVersion=1",
            "PLNCRD": f"SELECT Rate FROM Select_RATE_PLNCRD WHERE Plancode='{plancode}' AND IssueVersion=1",
            "PLNCRG": f"SELECT Rate FROM Select_RATE_PLNCRG WHERE Plancode='{plancode}' AND IssueVersion=1",
            "RLNCRD": f"SELECT Rate FROM Select_RATE_RLNCRD WHERE Plancode='{plancode}' AND IssueVersion=1",
            "RLNCRG": f"SELECT Rate FROM Select_RATE_RLNCRG WHERE Plancode='{plancode}' AND IssueVersion=1",
            "SNETPERIOD": f"SELECT Rate FROM Select_RATE_SNETPERIOD WHERE Plancode='{plancode}' AND IssueVersion=1 AND IssueAge={issue_age}",
            "RATESPACE": f"SELECT POINT_PVSRB.[Sex], POINT_PVSRB.[Rateclass], POINT_PVSRB.[Band] FROM POINT_PVSRB WHERE [Plancode]='{plancode}' AND [IssueVersion]=1",
            "COI_SCALE": f"SELECT Date, Scale FROM Select_SCALE_COI WHERE Plancode='{plancode}' AND IssueVersion=1",
        }
        
        return sql_map.get(rate_type, "")
    
    def _fetch_rates(self, sql: str) -> Optional[List]:
        """Execute SQL and return results."""
        if not sql:
            return None
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            cursor.close()
            
            if not rows:
                return None
            
            return rows
        except Exception:
            return None
    
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
        benefit_type: str = ""
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
        
        # Generate cache key
        rate_key = self._get_rate_key(
            rate_type, plancode, issue_age, sex, rateclass, band, scale, benefit_type
        )
        
        # Check cache
        if rate_key in self._cache:
            return self._cache[rate_key]
        
        # Fetch from database
        sql = self._create_sql(
            rate_type, plancode, issue_age, sex, rateclass, scale, band, benefit_type
        )
        
        rows = self._fetch_rates(sql)
        
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
        duration: int = None
    ) -> Optional[Union[List[float], float]]:
        """Get Surrender Charge rates."""
        rates = self.get_rates("SCR", plancode, issue_age, sex, rateclass, band=band)
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
