"""
SuiteView Python - PolicyInformation Module
============================================
Policy data access module providing:
- DB2 connectivity via ODBC
- Lazy-loaded table caching
- High-level properties with translated values
- Direct DataItem/DataItemArray access for any table.field
- CL_POLREC record class delegates for system-layer access

Structure:
- cl_polrec/policy_translations.py: Code translation tables and functions
- cl_polrec/policy_data_classes.py: Dataclass definitions
- cl_polrec/CL_POLREC_*.py: Record class modules
- policy_information.py: Main PolicyInformation class
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Tuple, TYPE_CHECKING
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from copy import deepcopy

# Import from cl_polrec package (single source of truth)
from .cl_polrec.policy_translations import (
    STATUS_CODES, PREMIUM_PAY_STATUS_CODES, SUSPENSE_CODES, PRODUCT_LINE_CODES,
    SEX_CODES, SEX_CODE_DISPLAY, BILLING_MODE_CODES,
    NON_STANDARD_BILL_MODE_CODES, DEF_OF_LIFE_INS_CODES, DB_OPTION_CODES,
    DIV_OPTION_CODES, NFO_CODES, PERSON_CODES, COMPANY_CODES,
    LOAN_TYPE_CODES,
    translate_state_code, translate_table_rating,
    translate_fund_id, translate_transaction_code, translate_market_org,
    translate_div_type_code, translate_renewal_rate_type_code,
    translate_elimination_period_code, translate_benefit_period_code,
    translate_substandard_type_code, translate_coverage_target_type,
    rate_class_description,
)
from .cl_polrec.policy_data_classes import (
    CoverageInfo, BenefitInfo, AgentInfo, LoanInfo,
    MVValueInfo, ActivityInfo, TransactionInfo,
    AppliedDividendInfo, UnappliedDividendInfo,
    DivOYTInfo, DivPUAInfo, DivDepositInfo,
    FundBucketInfo, LoanRepayInfo,
    RenewalCovRateInfo, RenewalBenRateInfo,
    SubstandardRatingInfo, SkippedPeriodInfo,
    TradLoanInfo, CoverageTargetInfo,
    PolicyNotFoundError,
)

# CL_POLREC record classes — only those still referenced internally
from .cl_polrec import (
    LoanRecords, TotalRecords,
)

# Use the shared database connection module instead of a duplicate manager
from suiteview.core.db2_connection import DB2Connection as _DB2Connection

# Data access layer — PolicyData owns DB2 access and table caching
from .policy_data import PolicyData as _PolicyData, _ConnectionManager

# Import Rates class for rate lookups
try:
    from suiteview.core.rates import Rates, RatesError
except ImportError:
    Rates = None  # type: ignore[assignment,misc]
    RatesError = RuntimeError  # type: ignore[assignment,misc]

# Import DataLookup for official plancode table lookups
try:
    from suiteview.polview.data.lookup import DataLookup as _DataLookup
    _data_lookup = _DataLookup()
except ImportError:
    _data_lookup = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from suiteview.core.rates import Rates  # noqa: F811


# =============================================================================
# POLICY INFORMATION CLASS
# =============================================================================

class PolicyInformation:
    """
    Self-contained policy information module.
    
    Provides:
    - High-level properties with translated values
    - Direct data_item() access for any table.field
    - Lazy-loaded table caching
    - Multi-policy support via index
    
    Example:
        pol = PolicyInformation("1234567", region="CKPR")
        if pol.exists:
            print(f"Status: {pol.status_description}")
            print(f"Plancode: {pol.base_plancode}")
            
            # Direct table access
            sus_cd = pol.data_item("LH_BAS_POL", "SUS_CD")
            plancodes = pol.data_item_array("LH_COV_PHA", "PLN_DES_SER_CD")
    """
    
    def __init__(
        self,
        policy_number: str,
        company_code: str = None,
        system_code: str = "I",
        region: str = "CKPR"
    ):
        """
        Initialize PolicyInformation.
        
        Args:
            policy_number: Policy number to load
            company_code: Optional company code (prompts if multiple found)
            system_code: System code (default "I")
            region: Database region (CKPR, CKMO, CKAS, CKSR, CKCS)
        """
        # Data access layer — owns DB2 connection and table cache
        self._data = _PolicyData(policy_number, company_code, system_code, region)
        
        # Cached business-object collections
        self._coverages: Optional[List[CoverageInfo]] = None
        self._benefits: Optional[List[BenefitInfo]] = None
        self._agents: Optional[List[AgentInfo]] = None
        self._loans: Optional[List[LoanInfo]] = None
        self._mv_values: Optional[List[MVValueInfo]] = None
        self._activities: Optional[List[ActivityInfo]] = None
        
        # Rates lookup (lazy loaded)
        self._rates: Optional[Rates] = None
        self._band_cache: Dict[int, Optional[int]] = {}  # cov_index -> band
        
        # CL_POLREC delegate classes still referenced internally
        # (32 refs to loan_records, 17 refs to total_records)
        self.loan_records = LoanRecords(self)
        self.total_records = TotalRecords(self)

    def cached_reads_only(self):
        """Guard UI rendering against missing/failed prefetches, even if caught."""
        return self._data.cached_reads_only()

    def detached_copy(self) -> "PolicyInformation":
        """Produce independent plain-data state for handoff to another thread."""
        clone = object.__new__(type(self))
        for name, value in self.__dict__.items():
            if name not in ("_data", "_rates", "loan_records", "total_records"):
                setattr(clone, name, deepcopy(value))
        clone._data = self._data.detached_copy()
        clone._rates = None
        clone.loan_records = LoanRecords(clone)
        clone.total_records = TotalRecords(clone)
        return clone

    def merge_prefetched(self, snapshot: "PolicyInformation") -> None:
        """Merge a detached snapshot while preserving the GUI policy identity."""
        identity = lambda policy: (
            policy.policy_number, policy.company_code, policy.system_code,
            policy.region, policy.policy_id,
        )
        if identity(self) != identity(snapshot):
            raise ValueError("Cannot merge a different policy/company/system/region")
        incoming = snapshot.detached_copy()
        self._data._table_cache.update(incoming._data._table_cache)
        for table in incoming._data._table_cache:
            self._data._table_errors.pop(table, None)
        self._data._table_errors.update(incoming._data._table_errors)
        # Any collection built against older rows must be reconstructed.
        for name in ("_coverages", "_benefits", "_agents", "_loans",
                     "_mv_values", "_activities"):
            setattr(self, name, getattr(incoming, name, None))
        self.loan_records.invalidate()
        self.total_records.invalidate()
        self._band_cache.clear()
    
    # =========================================================================
    # CORE API  (delegates to PolicyData)
    # =========================================================================
    
    @property
    def exists(self) -> bool:
        """Whether the policy exists in the database."""
        return self._data.exists
    
    @property
    def cancelled(self) -> bool:
        """Whether loading was cancelled or errored."""
        return self._data.cancelled
    
    @property
    def last_error(self) -> str:
        """Last error message if cancelled."""
        return self._data.last_error
    
    @property
    def available_companies(self) -> List[str]:
        """List of company codes when policy exists in multiple companies."""
        return self._data.available_companies
    
    def data_item(self, table_name: str, field_name: str, index: int = 0) -> Any:
        """Get a value from any table.field."""
        return self._data.data_item(table_name, field_name, index)
    
    def data_item_array(self, table_name: str, field_name: str) -> List[Any]:
        """Get all values for a field as a list."""
        return self._data.data_item_array(table_name, field_name)
    
    def data_item_count(self, table_name: str) -> int:
        """Get row count for a table."""
        return self._data.data_item_count(table_name)
    
    def fetch_table(self, table_name: str) -> List[Dict[str, Any]]:
        """Get entire table as list of dictionaries."""
        return self._data.fetch_table(table_name)

    def cached_table(self, table_name: str) -> Optional[tuple]:
        """Return ``(columns, rows)`` already loaded for a table, never querying DB2."""
        return self._data.cached_table(table_name)

    def table_error(self, table_name: str) -> str:
        """Return the DB2 load error for a table, if one occurred."""
        return self._data.table_error(table_name)
    
    def if_empty(self, value: Any, default: Any = "") -> Any:
        """Return default if value is None or empty string."""
        return self._data.if_empty(value, default)
    
    def find_row_index(self, table_name: str, filter_field: str, filter_value: Any) -> int:
        """Find the first row index where filter_field equals filter_value."""
        return self._data.find_row_index(table_name, filter_field, filter_value)
    
    def data_item_where(self, table_name: str, return_field: str,
                        filter_field: str, filter_value: Any,
                        default: Any = None) -> Any:
        """Get a field value from the first row matching a filter."""
        return self._data.data_item_where(table_name, return_field,
                                          filter_field, filter_value, default)
    
    def data_item_where_multi(self, table_name: str, return_field: str,
                               filters: Dict[str, Any],
                               default: Any = None) -> Any:
        """Get a field value from the first row matching multiple filters."""
        return self._data.data_item_where_multi(table_name, return_field,
                                                 filters, default)
    
    def data_items_where(self, table_name: str, return_field: str,
                         filter_field: str, filter_value: Any) -> List[Any]:
        """Get ALL field values from rows where filter matches."""
        return self._data.data_items_where(table_name, return_field,
                                           filter_field, filter_value)
    
    def get_rows_where(self, table_name: str, filter_field: str,
                       filter_value: Any) -> List[Dict[str, Any]]:
        """Get all row dictionaries where filter matches."""
        return self._data.get_rows_where(table_name, filter_field, filter_value)
    
    # =========================================================================
    # IDENTIFIERS
    # =========================================================================
    
    @property
    def policy_number(self) -> str:
        """Policy number."""
        return self._data.policy_number
    
    @property
    def policy_id(self) -> str:
        """Technical policy ID (TCH_POL_ID)."""
        return self._data.policy_id or ""
    
    @property
    def company_code(self) -> str:
        """Company code."""
        return self._data.company_code or ""
    
    @property
    def company_name(self) -> str:
        """Company name (translated)."""
        return COMPANY_CODES.get(self.company_code, self.company_code)
    
    @property
    def system_code(self) -> str:
        """System code."""
        return self._data.system_code
    
    @property
    def region(self) -> str:
        """Database region."""
        return self._data.region
    
    # =========================================================================
    # STATUS PROPERTIES
    # =========================================================================
    
    @property
    def status_code(self) -> str:
        """Policy status code."""
        return str(self.data_item("LH_BAS_POL", "POL_STS_CD") or "")
    
    @property
    def status_description(self) -> str:
        """Policy status description."""
        return STATUS_CODES.get(self.status_code, f"Unknown ({self.status_code})")
    
    @property
    def suspense_code(self) -> str:
        """Suspense code."""
        return str(self.data_item("LH_BAS_POL", "SUS_CD") or "0")
    
    @property
    def suspense_description(self) -> str:
        """Suspense description."""
        return SUSPENSE_CODES.get(self.suspense_code, f"Unknown ({self.suspense_code})")
    
    @property
    def premium_pay_status_code(self) -> str:
        """Premium paying status code (PRM_PAY_STA_REA_CD)."""
        return str(self.data_item("LH_BAS_POL", "PRM_PAY_STA_REA_CD") or "")
    
    @property
    def premium_pay_status_description(self) -> str:
        """Premium paying status description."""
        return PREMIUM_PAY_STATUS_CODES.get(self.premium_pay_status_code, f"Unknown ({self.premium_pay_status_code})")
    
    @property
    def is_active(self) -> bool:
        """Whether policy is in active status."""
        return self.status_code in ("10", "14", "15")
    
    @property
    def is_suspended(self) -> bool:
        """Whether policy is suspended."""
        return self.status_code == "20"
    
    @property
    def is_terminated(self) -> bool:
        """Whether policy is terminated (any non-active status)."""
        return self.status_code not in ("10", "14", "15", "20")
    
    @property
    def grace_indicator(self) -> bool:
        """Whether policy is in grace period (always False — use in_grace() instead)."""
        return False
    
    # =========================================================================
    # DATE PROPERTIES
    # =========================================================================
    
    @property
    def issue_date(self) -> Optional[date]:
        """Policy issue date (falls back to first coverage issue date)."""
        dt = self._parse_date(self.data_item("LH_COV_PHA", "ISSUE_DT"))
        if dt is None:
            covs = self.get_coverages()
            if covs:
                dt = covs[0].issue_date
        return dt
    
    @property
    def paid_to_date(self) -> Optional[date]:
        """Premium paid-to date."""
        return self._parse_date(self.data_item("LH_BAS_POL", "PRM_PAID_TO_DT"))
    
    @property
    def next_anniversary_date(self) -> Optional[date]:
        """Next policy anniversary date."""
        return self._parse_date(self.data_item("LH_BAS_POL", "NXT_YR_END_PRC_DT"))
    
    @property
    def next_monthliversary_date(self) -> Optional[date]:
        """Next monthliversary date."""
        return self._parse_date(self.data_item("LH_BAS_POL", "NXT_MVRY_PRC_DT"))
    
    @property
    def terminate_date(self) -> Optional[date]:
        """Policy termination date."""
        return self._parse_date(self.data_item("LH_BAS_POL", "PLN_TMN_DT"))
    
    @staticmethod
    def _completed_date_parts_years(date1: date, date2: date) -> int:
        """Python equivalent of VBA CompletedDateParts("YYYY", date1, date2).
        
        Counts the number of full years between date1 and date2.
        If date2 < date1, the dates are swapped (always returns positive).
        """
        if date1 > date2:
            date1, date2 = date2, date1
        # Guard against sentinel dates like 9999-12-31 that would overflow
        if date2.year >= 9999:
            return date2.year - date1.year
        k = 0
        while True:
            try:
                next_date = date1.replace(year=date1.year + k + 1)
            except ValueError:
                # Handles Feb 29 -> non-leap year
                next_date = date(date1.year + k + 1, date1.month, 28)
            if next_date > date2:
                break
            k += 1
        return k
    
    @property
    def policy_year(self) -> int:
        """Current policy year (VBA: CompletedDateParts("YYYY", CovIssueDate(1), ValuationDate) + 1)."""
        covs = self.get_coverages()
        base_issue_date = covs[0].issue_date if covs else None
        val_date = self.valuation_date
        if base_issue_date and val_date:
            years = self._completed_date_parts_years(base_issue_date, val_date)
            return years + 1
        return 0
    
    @property
    def policy_month(self) -> int:
        """Current month within the policy year (1-12).

        Uses coverage 1 issue date (consistent with policy_year).
        Accounts for the day of the month: if today's day is before
        the issue day, the new month hasn't started yet.
        """
        covs = self.get_coverages()
        base_issue_date = covs[0].issue_date if covs else None
        if not base_issue_date:
            return 0
        today = date.today()
        total_months = ((today.year - base_issue_date.year) * 12
                        + (today.month - base_issue_date.month))
        if today.day < base_issue_date.day:
            total_months -= 1
        return (total_months % 12) + 1
    
    # =========================================================================
    # BILLING PROPERTIES
    # =========================================================================
    
    @property
    def billing_frequency(self) -> int:
        """Billing frequency in months."""
        return int(self.data_item("LH_BAS_POL", "PMT_FQY_PER") or 0)
    
    @property
    def billing_mode(self) -> str:
        """Billing mode description."""
        nsd = str(self.data_item("LH_BAS_POL", "NSD_MD_CD") or "")
        if nsd in NON_STANDARD_BILL_MODE_CODES:
            return NON_STANDARD_BILL_MODE_CODES[nsd]
        return BILLING_MODE_CODES.get(self.billing_frequency, f"{self.billing_frequency} months")
    
    @property
    def non_standard_mode_code(self) -> str:
        """Non-standard billing mode code (NSD_MD_CD)."""
        return str(self.data_item("LH_BAS_POL", "NSD_MD_CD") or "")
    
    @property
    def bill_day(self) -> int:
        """Billing day of month."""
        return int(self.data_item("LH_BAS_POL", "BIL_DAY_NBR") or 0)
    
    @property
    def issue_state_code(self) -> str:
        """Issue state code (raw numeric from ISSUE_ST_CD)."""
        return str(self.data_item("LH_BAS_POL", "POL_ISS_ST_CD") or "")
    
    @property
    def issue_state(self) -> str:
        """Issue state abbreviation (e.g., 'AZ', 'NY')."""
        code = self.issue_state_code
        if code and code.isdigit():
            return translate_state_code(int(code))
        return code
    
    @property
    def resident_state_code(self) -> str:
        """Resident/premium-paying state code (raw numeric from PRM_PAY_ST_CD)."""
        return str(self.data_item("LH_BAS_POL", "PRM_PAY_ST_CD") or "")
    
    @property
    def resident_state(self) -> str:
        """Resident/premium-paying state abbreviation (e.g., 'AZ', 'NY')."""
        code = self.resident_state_code
        if code and code.isdigit():
            return translate_state_code(int(code))
        return code
    
    @property
    def state_code(self) -> str:
        """Alias for issue_state_code (deprecated - use issue_state_code instead)."""
        return self.issue_state_code
    
    # =========================================================================
    # PREMIUM PROPERTIES
    # =========================================================================
    
    @property
    def regular_premium(self) -> Optional[Decimal]:
        """Regular premium amount (alias for modal_premium)."""
        return self.modal_premium
    
    @property
    def modal_premium(self) -> Optional[Decimal]:
        """Modal premium (premium per billing period)."""
        val = self.data_item("LH_BAS_POL", "POL_PRM_AMT")
        return Decimal(str(val)) if val is not None else None
    
    @property
    def annual_premium(self) -> Optional[Decimal]:
        """Annualized premium."""
        if self.modal_premium and self.billing_frequency:
            return self.modal_premium * (Decimal(12) / Decimal(self.billing_frequency))
        return self.modal_premium

    @property
    def annual_policy_fee(self) -> Optional[Decimal]:
        """Annual policy fee for traditional products."""
        if self.is_advanced_product:
            return None
        val = self.data_item("LH_FXD_PRM_POL", "POL_FEE_AMT")
        return Decimal(str(val)) if val is not None else None
    
    @property
    def target_premium(self) -> Optional[Decimal]:
        """Target premium (for UL products)."""
        val = self.data_item("LH_POL_TARGET", "TAR_PRM_AMT")
        return Decimal(str(val)) if val is not None else None
    
    @property
    def minimum_premium(self) -> Optional[Decimal]:
        """Minimum premium (for UL products — not stored on LH_BAS_POL)."""
        return None
    
    # =========================================================================
    # OPTIONS
    # =========================================================================
    
    @property
    def div_option_code(self) -> str:
        """Dividend option code."""
        return str(self.data_item("LH_BAS_POL", "PRI_DIV_OPT_CD") or "0")
    
    @property
    def div_option_description(self) -> str:
        """Dividend option description."""
        return DIV_OPTION_CODES.get(self.div_option_code, f"Unknown ({self.div_option_code})")
    
    @property
    def nfo_code(self) -> str:
        """Non-forfeiture option code."""
        return str(self.data_item("LH_BAS_POL", "NFO_OPT_TYP_CD") or "0")
    
    @property
    def nfo_description(self) -> str:
        """Non-forfeiture option description."""
        return NFO_CODES.get(self.nfo_code, f"Unknown ({self.nfo_code})")
    
    @property
    def db_option_code(self) -> str:
        """Death benefit option code."""
        return str(self.data_item("LH_NON_TRD_POL", "DTH_BNF_PLN_OPT_CD") or "")
    
    @property
    def db_option_description(self) -> str:
        """Death benefit option description."""
        return DB_OPTION_CODES.get(self.db_option_code, f"Unknown ({self.db_option_code})")
    
    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    
    @property
    def is_advanced_product(self) -> bool:
        """Whether this is an advanced product (UL/IUL/VUL)."""
        return str(self.data_item("LH_BAS_POL", "NON_TRD_POL_IND")) == "1"
    
    @property
    def product_type(self) -> str:
        """
        Determine product type: WL, TERM, UL, IUL, VUL, ISWL, DI.

        Uses the official plancode table (DataLookup) as the primary source
        of truth.  Falls back to heuristic matching for plancodes not in
        the table.
        """
        plancode = self.base_plancode
        if not plancode:
            return "UNKNOWN"

        if self.is_advanced_product:
            prod_line = self.product_line_code
            if prod_line == "I":
                return "ISWL"
            return "UL"

        if self.product_line_code == "S":
            return "DI"

        if _data_lookup is not None:
            group = _data_lookup.get_plancode_group(plancode)
            if group and group != "Not Found":
                return group

        pln_upper = plancode.upper()
        if any(x in pln_upper for x in ["TRM", "TERM", "TM", "RT", "ART", "YRT"]):
            return "TERM"

        return "WL"
    
    @property
    def product_line_code(self) -> str:
        """Product line type code."""
        return str(self.data_item("LH_COV_PHA", "PRD_LIN_TYP_CD") or "")
    
    @property
    def product_line_description(self) -> str:
        """Product line description."""
        return PRODUCT_LINE_CODES.get(self.product_line_code, f"Unknown ({self.product_line_code})")
    
    @property
    def defra_indicator(self) -> str:
        """DEFRA indicator (not stored on LH_BAS_POL — use tefra_defra_code)."""
        return ""
    
    @property
    def def_of_life_ins_code(self) -> str:
        """Definition of Life Insurance code."""
        return str(self.data_item("LH_NON_TRD_POL", "TFDF_CD") or "")
    
    @property
    def def_of_life_ins_description(self) -> str:
        """Definition of Life Insurance description."""
        return DEF_OF_LIFE_INS_CODES.get(self.def_of_life_ins_code, "")
    
    @property
    def guideline_single_premium(self) -> Optional[Decimal]:
        """Guideline Single Premium (GSP — not stored on LH_BAS_POL)."""
        return None
    
    @property
    def guideline_level_premium(self) -> Optional[Decimal]:
        """Guideline Level Premium (GLP — not stored on LH_BAS_POL)."""
        return None
    
    # =========================================================================
    # BASE COVERAGE PROPERTIES
    # =========================================================================

    @property
    def number_of_lives_code(self) -> str:
        """Base phase 1 FCVLIVES-LIVES: 1 single, 2 first-to-die, 3 second-to-die."""
        value = self.data_item_where(
            "LH_COV_PHA", "NBR_OF_LIVES_CD", "COV_PHA_NBR", 1,
        )
        code = str(value).strip() if value is not None else ""
        if code not in ("1", "2", "3"):
            raise ValueError(
                f"Missing or invalid LH_COV_PHA.NBR_OF_LIVES_CD "
                f"for base coverage phase 1: {value!r}"
            )
        return code

    @property
    def insured_lives_description(self) -> str:
        """Single/joint classification from the base coverage's lives code."""
        return {
            "1": "Single",
            "2": "Joint First to Die",
            "3": "Joint Second to Die",
        }[self.number_of_lives_code]

    @property
    def is_joint_insured(self) -> bool:
        """Whether the base coverage is joint first-to-die or second-to-die."""
        return self.number_of_lives_code in ("2", "3")
    
    @property
    def base_plancode(self) -> str:
        """Base coverage plancode (from first coverage phase)."""
        covs = self.get_coverages()
        return covs[0].plancode if covs else ""
    
    @property
    def base_face_amount(self) -> Optional[Decimal]:
        """Base coverage face amount (units * VPU)."""
        covs = self.get_base_coverages()
        return covs[0].face_amount if covs else None
    
    @property
    def base_units(self) -> Optional[Decimal]:
        """Base coverage raw unit count."""
        covs = self.get_base_coverages()
        return covs[0].units if covs else None
    
    @property
    def base_total_face_amount(self) -> Decimal:
        """Total face amount across all base coverages (for UL increases)."""
        total = Decimal("0")
        for cov in self.get_base_coverages():
            if cov.face_amount:
                total += cov.face_amount
        return total

    def _coverage_is_active(self, cov: CoverageInfo, as_of_date: Optional[date] = None) -> bool:
        """Return whether a coverage is active as of the valuation date."""
        effective_date = as_of_date or self.valuation_date or date.today()
        if cov.terminate_date and cov.terminate_date <= effective_date:
            return False

        status = str(cov.nxt_chg_typ_cd or cov.cov_status or "").strip()
        if status == "0":
            return bool(cov.nxt_chg_dt and cov.nxt_chg_dt > effective_date)
        return True

    @staticmethod
    def _covers_primary_insured(cov: CoverageInfo) -> bool:
        """Return whether a coverage applies only to the primary insured."""
        person_code = str(cov.person_code or "").strip()
        if person_code not in ("", "00"):
            return False
        if cov.prs_seq_nbr not in (0, 1):
            return False
        try:
            return int(str(cov.lives_cov_cd or "1").strip() or "1") <= 1
        except (TypeError, ValueError):
            return False

    @property
    def primary_insured_face_amount(self) -> Decimal:
        """Active face amount covering the primary insured only."""
        total = Decimal("0")
        for cov in self.get_coverages():
            if not self._covers_primary_insured(cov):
                continue
            if not self._coverage_is_active(cov):
                continue
            if cov.face_amount:
                total += cov.face_amount

        if total:
            return total
        return self.base_face_amount or Decimal("0")

    @property
    def primary_insured_db_layers(self) -> List[Tuple[Decimal, Optional[date]]]:
        """Active death-benefit layers covering the primary insured, with expiry.

        Returns a list of ``(face_amount, expiry_date)`` tuples — one per active
        coverage that covers the primary insured (the base coverage plus any
        level-term riders written on the primary insured). ``expiry_date`` is the
        coverage's maturity/expiry date (``COV_MT_EXP_DT``); the base coverage
        expires at policy maturity while a level-term rider expires at the end of
        its level period, at which point its face drops out of the death benefit.

        Mirrors :pyattr:`primary_insured_face_amount` (same coverage selection),
        but preserves per-layer detail so consumers can project a declining death
        benefit. Falls back to the base coverage when no per-insured coverage is
        found.
        """
        layers: List[Tuple[Decimal, Optional[date]]] = []
        for cov in self.get_coverages():
            if not self._covers_primary_insured(cov):
                continue
            if not self._coverage_is_active(cov):
                continue
            if cov.face_amount:
                layers.append((cov.face_amount, cov.maturity_date))

        if layers:
            return layers

        covs = self.get_base_coverages()
        if covs and covs[0].face_amount:
            return [(covs[0].face_amount, covs[0].maturity_date)]
        return []

    @property
    def current_account_value(self) -> Optional[Decimal]:
        """Recorded account value at the most recent monthliversary, if present."""
        return self.mv_av(0)

    @property
    def standard_death_benefit(self) -> Decimal:
        """Death benefit before the 7702 corridor test.

        Face amount covering the primary insured plus the DB-option amount
        (option B adds the account value, option C adds premiums paid).
        """
        total = self.primary_insured_face_amount
        db_option = str(self.db_option_code or "").strip().upper()

        if db_option in ("2", "B"):
            account_value = self.current_account_value
            if account_value:
                total += account_value
        elif db_option in ("3", "C"):
            premiums_paid = self.total_premiums_paid
            if premiums_paid:
                total += premiums_paid

        return total

    @property
    def corridor_death_benefit(self) -> Optional[Decimal]:
        """Corridor (7702 minimum) death benefit — AV × corridor percent.

        Mirrors the CyberLife/VBA audit rule
        ``ROUND(LH_POL_MVRY_VAL.CSV_AMT * LH_NON_TRD_POL.CDR_PCT / 100, 2)``.
        Returns ``None`` when the corridor does not apply (traditional product,
        or no account value / corridor percent on file).
        """
        if not self.is_advanced_product:
            return None

        account_value = self.current_account_value
        if not account_value or account_value <= 0:
            return None

        percent = self.corridor_percent
        if percent is None or percent <= 0:
            return None

        return (Decimal(account_value) * Decimal(percent) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @property
    def corridor_amount(self) -> Decimal:
        """Amount the corridor adds on top of the standard death benefit (0 if none)."""
        corridor_db = self.corridor_death_benefit
        if corridor_db is None:
            return Decimal("0")
        excess = corridor_db - self.standard_death_benefit
        return excess if excess > 0 else Decimal("0")

    @property
    def is_in_corridor(self) -> bool:
        """Whether the corridor death benefit exceeds the standard death benefit."""
        return self.corridor_amount > 0

    @property
    def total_death_benefit(self) -> Decimal:
        """Total death benefit — the greater of the standard and corridor amounts.

        The corridor (IRC 7702 minimum death benefit) applies when the account
        value has grown large enough that ``AV × corridor %`` exceeds the face
        amount plus the DB-option amount.
        """
        standard = self.standard_death_benefit
        corridor_db = self.corridor_death_benefit
        if corridor_db is not None and corridor_db > standard:
            return corridor_db
        return standard
    
    @property
    def base_issue_age(self) -> Optional[int]:
        """Base insured issue age."""
        covs = self.get_base_coverages()
        return covs[0].issue_age if covs else None
    
    @property
    def base_sex_code(self) -> str:
        """Base insured sex code."""
        covs = self.get_base_coverages()
        return covs[0].sex_code if covs else ""
    
    @property
    def base_sex_description(self) -> str:
        """Base insured sex description."""
        covs = self.get_base_coverages()
        return covs[0].sex_desc if covs else ""
    
    @property
    def base_rate_class(self) -> str:
        """Base coverage rate class code."""
        covs = self.get_base_coverages()
        return covs[0].rate_class if covs else ""
    
    @property
    def base_rate_class_description(self) -> str:
        """Base coverage rate class description."""
        covs = self.get_base_coverages()
        return covs[0].rate_class_desc if covs else ""
    
    @property
    def attained_age(self) -> Optional[int]:
        """Current attained age of base insured (VBA: CovIssueAge(1) + PolicyYear - 1)."""
        if self.base_issue_age is not None:
            py = self.policy_year
            if py > 0:
                return self.base_issue_age + py - 1
        return None
    
    @property
    def age_at_maturity(self) -> Optional[int]:
        """Age at maturity of base coverage (VBA: AgeAtMaturity).
        Calculated as issue_age + years from issue to maturity date."""
        covs = self.get_base_coverages()
        if not covs:
            return None
        cov = covs[0]
        issue_date = cov.issue_date
        maturity_date = cov.maturity_date
        issue_age = cov.issue_age
        if issue_date and maturity_date and issue_age is not None:
            years = maturity_date.year - issue_date.year
            if (maturity_date.month, maturity_date.day) < (issue_date.month, issue_date.day):
                years -= 1
            return issue_age + years
        return None
    
    # =========================================================================
    # COVERAGE COLLECTIONS
    # =========================================================================
    
    @property
    def coverage_count(self) -> int:
        """Number of coverage phases."""
        return self.data_item_count("LH_COV_PHA")

    @property
    def has_annuity_rider(self) -> bool:
        """Whether Policy Support's 0699830R annuity-rider tool applies."""
        return any(
            coverage.plancode.strip().upper() == "0699830R"
            for coverage in self.get_coverages()
        )
    
    def get_coverages(self) -> List[CoverageInfo]:
        """Get all coverage phases with complete field mapping.
        
        Coverage classification:
        - is_base=True for all coverages sharing the same plancode as COV_PHA_NBR=1
          (for UL products, coverage increases are added as additional base coverages)
        - is_base=False for riders (different plancode from coverage 1)
        
        Substandard ratings (table_rating, table_cease_date, flat_extra,
        flat_cease_date) and
        TH_COV_PHA fields (cv_amount, nsp_amount) are populated during build.

        """
        if self._coverages is not None:
            return self._coverages
        
        # Don't set self._coverages until we succeed — prevents caching a
        # partial/empty list if an exception occurs mid-build.
        built: List[CoverageInfo] = []
        
        # Fetch TH_COV_PHA for COLA/GIO/CV/NSP
        th_cov_data = {}
        try:
            th_rows = self.fetch_table("TH_COV_PHA")
            for th_row in th_rows:
                pha = int(th_row.get("COV_PHA_NBR", 0))
                th_cov_data[pha] = th_row
        except Exception:
            pass  # Table may not exist for all policies
        
        # Pre-fetch substandard ratings for all coverages
        all_ratings = {}
        try:
            for rating in self.get_substandard_ratings():
                phase = rating.coverage_phase
                if phase not in all_ratings:
                    all_ratings[phase] = []
                all_ratings[phase].append(rating)
        except Exception:
            pass
        
        # Determine base plancode from first coverage row
        lh_rows = self.fetch_table("LH_COV_PHA")
        base_plancode = ""
        if lh_rows:
            base_plancode = str(lh_rows[0].get("PLN_DES_SER_CD", "")).strip()
        
        # Detect advanced product (UL/IUL/VUL) vs Traditional
        is_advanced = self.is_advanced_product
        # Policy-level product line code (for COI rate divisor)
        pol_product_line = self.product_line_code
        
        for i, row in enumerate(lh_rows):
            try:
                cov_pha_nbr = int(row.get("COV_PHA_NBR", 0))
                plancode = str(row.get("PLN_DES_SER_CD", "")).strip()
                
                # Get units and VPU for calculations
                units = self._parse_optional_decimal(row.get("COV_UNT_QTY"))
                orig_units = self._parse_optional_decimal(row.get("OGN_SPC_UNT_QTY"))
                vpu = self._parse_optional_decimal(row.get("COV_VPU_AMT"))
                premium_rate = self._parse_optional_decimal(row.get("ANN_PRM_UNT_AMT"))
                
                # Calculate amounts
                face_amount = (units * vpu) if (units is not None and vpu is not None) else None
                orig_amount = (orig_units * vpu) if (orig_units is not None and vpu is not None) else None
                
                # Get COLA/GIO/CV/NSP from TH_COV_PHA
                th_row = th_cov_data.get(cov_pha_nbr, {})
                cola_indicator = str(th_row.get("COLA_INCR_IND", "")) if th_row else ""
                gio_indicator = ""  # OPT_EXER_IND does not exist on TH_COV_PHA
                cv_amount = None    # CV_AMT does not exist on TH_COV_PHA
                nsp_amount = None   # NSP_AMT does not exist on TH_COV_PHA
                
                cov_ratings = all_ratings.get(cov_pha_nbr, [])
                table_rating = None
                table_rating_code = ""
                table_cease_date = None
                flat_extra = None
                flat_cease_date = None
                for r in cov_ratings:
                    if r.type_code == "T" and r.table_rating_numeric and r.table_rating_numeric > 0:
                        table_rating = r.table_rating_numeric
                        table_rating_code = r.table_rating or ""
                        if r.flat_cease_date:
                            table_cease_date = r.flat_cease_date
                    if r.type_code == "F":
                        if r.flat_amount is not None:
                            flat_extra = r.flat_amount
                        if r.flat_cease_date:
                            flat_cease_date = r.flat_cease_date
                
                # Get status code
                status_code = str(row.get("NXT_CHG_TYP_CD", ""))
                status_date = self._parse_date(row.get("NXT_CHG_DT"))

                # DI fields
                elim_code = str(row.get("AH_ACC_ELM_PER_CD", "") or "")
                bnf_code = str(row.get("AH_ACC_BNF_PER_CD", "") or "")
                
                # is_base: same plancode as first coverage (handles UL increases)
                is_base = (plancode == base_plancode)
                
                cov = CoverageInfo(
                    cov_pha_nbr=cov_pha_nbr,
                    plancode=plancode,
                    form_number=str(row.get("POL_FRM_NBR", "")).strip(),
                    issue_date=self._parse_date(row.get("ISSUE_DT")),
                    maturity_date=self._parse_date(row.get("COV_MT_EXP_DT")),
                    issue_age=self._parse_optional_int(row.get("INS_ISS_AGE")),
                    face_amount=face_amount,
                    orig_amount=orig_amount,
                    units=units,
                    orig_units=orig_units,
                    vpu=vpu,
                    person_code=str(row.get("PRS_CD", "00")),
                    person_desc=PERSON_CODES.get(str(row.get("PRS_CD", "00")), ""),
                    sex_code=SEX_CODE_DISPLAY.get(str(row.get("INS_SEX_CD", "")), str(row.get("INS_SEX_CD", ""))),
                    sex_desc=SEX_CODES.get(str(row.get("INS_SEX_CD", "")), ""),
                    product_line_code=str(row.get("PRD_LIN_TYP_CD", "")),
                    product_line_desc=PRODUCT_LINE_CODES.get(str(row.get("PRD_LIN_TYP_CD", "")), ""),
                    class_code=str(row.get("INS_CLS_CD", "")),
                    rate_class="",   # populated below from LH_COV_INS_RNL_RT
                    rate_class_desc="",
                    table_rating=table_rating,
                    table_rating_code=table_rating_code,
                    table_cease_date=table_cease_date,
                    cola_indicator=cola_indicator,
                    gio_indicator=gio_indicator,
                    flat_extra=flat_extra,
                    flat_cease_date=flat_cease_date,
                    prs_seq_nbr=int(row.get("PRS_SEQ_NBR", 0) or 0),
                    lives_cov_cd=str(row.get("LIVES_COV_CD", "")),
                    cov_status=status_code,
                    cov_status_date=status_date,
                    cov_status_desc="",
                    # Premium rate (Trad) – from LH_COV_PHA.ANN_PRM_UNT_AMT
                    premium_rate=premium_rate,
                    nxt_chg_typ_cd=str(row.get("NXT_CHG_TYP_CD", "")),
                    nxt_chg_dt=self._parse_date(row.get("NXT_CHG_DT")),
                    terminate_date=self._parse_date(row.get("PLN_TMN_DT")),
                    is_base=is_base,
                    # Total annual premium = per-unit rate × units
                    cov_annual_premium=(
                        premium_rate * units
                        if premium_rate is not None and units is not None
                        else premium_rate
                    ),
                    # Raw per-unit rate (ANN_PRM_UNT_AMT)
                    annual_premium_per_unit=premium_rate,
                    cv_amount=cv_amount,
                    nsp_amount=nsp_amount,
                    elimination_period=translate_elimination_period_code(elim_code) if elim_code else "",
                    benefit_period=translate_benefit_period_code(bnf_code) if bnf_code else "",
                    raw_data=row
                )

                # Rate class & sex — from LH_COV_INS_RNL_RT (Record 67)
                # The 67 segment has per-coverage sex (RT_SEX_CD) and rate class
                # (RT_CLS_CD).  LH_COV_PHA.INS_SEX_CD may be the same for all
                # coverages, so the 67 segment is the authoritative source.
                rnl_idx = self.cov_renewal_index(cov_pha_nbr, "C", "0")
                if rnl_idx >= 0:
                    rc = str(self.data_item(
                        "LH_COV_INS_RNL_RT", "RT_CLS_CD", rnl_idx
                    ) or "")
                    cov.rate_class = rc
                    cov.rate_class_desc = rate_class_description(rc, plancode)
                    # Per-coverage sex code from 67 segment
                    rnl_sex = str(self.data_item(
                        "LH_COV_INS_RNL_RT", "RT_SEX_CD", rnl_idx
                    ) or "")
                    if rnl_sex:
                        cov.sex_code = SEX_CODE_DISPLAY.get(rnl_sex, rnl_sex)
                        cov.sex_desc = SEX_CODES.get(rnl_sex, "")

                # COI rate (Advanced) – from LH_COV_INS_RNL_RT.RNL_RT (type "C")
                # Divided by 100 for product line "I", or 100,000 for others.
                if is_advanced and rnl_idx >= 0:
                    raw_rate = self.data_item("LH_COV_INS_RNL_RT", "RNL_RT", rnl_idx)
                    if raw_rate is not None:
                        try:
                            r = Decimal(str(raw_rate))
                            if pol_product_line == "I":
                                cov.coi_rate = r / 100
                            else:
                                cov.coi_rate = r / 100000
                        except Exception:
                            pass

                # Flat extra fallback — LH_SST_XTR_CRG is the only source
                # for flat extra data.  LH_COV_INS_RNL_RT does NOT carry
                # flat extra fields (per COBOL DB2 translation workbook).

                built.append(cov)
            except Exception as _cov_exc:
                import sys as _sys
                print(
                    f"[get_coverages] ERROR building coverage row {i} "
                    f"(COV_PHA_NBR={row.get('COV_PHA_NBR','?')}): {_cov_exc}",
                    file=_sys.stderr,
                )
        
        self._coverages = built
        return self._coverages
    
    def get_base_coverages(self) -> List[CoverageInfo]:
        """Get all base coverages (same plancode as coverage 1).
        
        For UL products, coverage increases are added as additional coverages
        with the same plancode as the original base. All such coverages are
        considered base coverages.
        """
        return [c for c in self.get_coverages() if c.is_base]
    
    def get_base_coverage(self) -> Optional[CoverageInfo]:
        """Get primary base coverage (COV_PHA_NBR = 1).
        
        Deprecated: Use get_base_coverages() for UL products with increases.
        """
        covs = self.get_base_coverages()
        return covs[0] if covs else None
    
    def get_riders(self) -> List[CoverageInfo]:
        """Get rider coverages (different plancode from base)."""
        return [c for c in self.get_coverages() if not c.is_base]
    
    def cov_plancode(self, index: int) -> str:
        """Get plancode for coverage at index (1-based)."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].plancode
        return ""
    
    def cov_face_amount(self, index: int) -> Optional[Decimal]:
        """Get face amount for coverage at index (1-based). Returns units * VPU."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].face_amount
        return None
    
    def cov_issue_age(self, index: int) -> Optional[int]:
        """Get issue age for coverage at index (1-based)."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].issue_age
        return None
    
    # =========================================================================
    # BENEFIT COLLECTIONS
    # =========================================================================
    
    @property
    def benefit_count(self) -> int:
        """Number of benefits."""
        return self.data_item_count("LH_SPM_BNF")
    
    def get_benefits(self, cov_pha_nbr: int = None) -> List[BenefitInfo]:
        """Get benefits with complete VBA-compatible field mapping."""
        if self._benefits is None:
            self._benefits = []
            for row in self.fetch_table("LH_SPM_BNF"):
                # Get type and subtype codes to build benefit code (plancode)
                type_cd = str(row.get("SPM_BNF_TYP_CD", "")).strip()
                subtype_cd = str(row.get("SPM_BNF_SBY_CD", "")).strip()
                benefit_code = type_cd + subtype_cd
                ben_cov_pha_nbr = int(row.get("COV_PHA_NBR", 0) or 0)

                # Get units and VPU for amount calculation
                units = self._parse_optional_decimal(row.get("BNF_UNT_QTY"))
                vpu = self._parse_optional_decimal(row.get("BNF_VPU_AMT"))
                benefit_amount = (units * vpu) if (units is not None and vpu is not None) else None

                # Renewal rate from the 67 segment (LH_BNF_INS_RNL_RT, type "B").
                # The Record-04 BNF_ANN_PPU_AMT above is the issue rate; this is
                # the renewal rate that applies once the benefit renews.
                renewal_rate = self.benefit_renewal_rate(
                    ben_cov_pha_nbr, type_cd, subtype_cd, "B"
                )

                ben = BenefitInfo(
                    cov_pha_nbr=ben_cov_pha_nbr,
                    benefit_code=benefit_code,
                    benefit_type_cd=type_cd,
                    benefit_subtype_cd=subtype_cd,
                    benefit_desc=type_cd,  # Type code is the primary descriptor
                    form_number=str(row.get("BNF_FRM_NBR", "")).strip(),
                    issue_date=self._parse_date(row.get("BNF_ISS_DT")),
                    pay_up_date=self._parse_date(row.get("BNF_PAY_UP_DT")),
                    cease_date=self._parse_date(row.get("BNF_CEA_DT")),
                    orig_cease_date=self._parse_date(row.get("BNF_OGN_CEA_DT")),
                    units=units,
                    vpu=vpu,
                    benefit_amount=benefit_amount,
                    issue_age=self._parse_optional_int(row.get("BNF_ISS_AGE")),
                    rating_factor=self._parse_optional_decimal(row.get("BNF_RT_FCT")),
                    renewal_indicator=str(row.get("RNL_RT_IND", "")).strip(),
                    coi_rate=self._parse_optional_decimal(row.get("BNF_ANN_PPU_AMT")),
                    renewal_rate=renewal_rate,
                    raw_data=row
                )
                self._benefits.append(ben)
        
        if cov_pha_nbr is not None:
            return [b for b in self._benefits if b.cov_pha_nbr == cov_pha_nbr]
        return self._benefits
    
    def ben_value_by_name(self, plancode: str, field_name: str) -> Any:
        """Get raw field value for benefit matching plancode (type+subtype).
        
        For structured access, use get_benefits() which returns BenefitInfo objects.
        This method is for ad-hoc lookups of fields not in BenefitInfo.
        """
        for ben in self.get_benefits():
            if ben.benefit_code == plancode:
                return ben.raw_data.get(field_name.upper())
        return None

    # =========================================================================
    # AGENT COLLECTIONS
    # =========================================================================
    
    @property
    def agent_count(self) -> int:
        """Number of agent records."""
        return self.data_item_count("LH_AGT_COM_AMT")
    
    def get_agents(self) -> List[AgentInfo]:
        """Get all agent records."""
        if self._agents is not None:
            return self._agents
        
        self._agents = []
        for row in self.fetch_table("LH_AGT_COM_AMT"):
            agent = AgentInfo(
                agt_com_pha_nbr=int(row.get("AGT_COM_PHA_NBR", 0)),
                agent_id=str(row.get("AGT_ID", "")),
                commission_pct=Decimal(str(row["COM_PCT"])) if row.get("COM_PCT") else None,
                market_org_cd=str(row.get("MKT_ORG_CD", "")),
                svc_agt_ind=str(row.get("SVC_AGT_IND", "")),
                raw_data=row
            )
            self._agents.append(agent)
        
        return self._agents
    
    @property
    def writing_agent(self) -> str:
        """Primary writing agent ID."""
        agents = self.get_agents()
        for agt in agents:
            if agt.agt_com_pha_nbr == 1:
                return agt.agent_id
        return agents[0].agent_id if agents else ""
    
    # =========================================================================
    # LOAN PROPERTIES
    # =========================================================================
    
    def get_loans(self) -> List[LoanInfo]:
        """Get all active loans."""
        if self._loans is not None:
            return self._loans
        
        self._loans = []
        
        # Traditional loans (LH_CSH_VAL_LOAN)
        for row in self.fetch_table("LH_CSH_VAL_LOAN"):
            principal = Decimal(str(row.get("LN_PRI_AMT", 0) or 0))
            if principal <= 0:
                continue
            
            accrued = Decimal("0")
            if str(row.get("LN_ITS_AMT_TYP_CD")) == "2":
                accrued = Decimal(str(row.get("POL_LN_ITS_AMT", 0) or 0))
            
            loan = LoanInfo(
                loan_type=str(row.get("LN_TYP_CD", "")),
                loan_type_desc=LOAN_TYPE_CODES.get(str(row.get("LN_TYP_CD", "")), ""),
                principal=principal,
                accrued_interest=accrued,
                interest_rate=Decimal(str(row["LN_CRG_ITS_RT"])) if row.get("LN_CRG_ITS_RT") else None,
                preferred_loan=str(row.get("PRF_LN_IND")) == "1",
                raw_data=row
            )
            self._loans.append(loan)
        
        # Advanced product loans (LH_FND_VAL_LOAN)
        for row in self.fetch_table("LH_FND_VAL_LOAN"):
            principal = Decimal(str(row.get("LN_PRI_AMT", 0) or 0))
            if principal <= 0:
                continue
            
            accrued = Decimal(str(row.get("POL_LN_ITS_AMT", 0) or 0))
            
            loan = LoanInfo(
                loan_type=str(row.get("LN_TYP_CD", "")),
                loan_type_desc=LOAN_TYPE_CODES.get(str(row.get("LN_TYP_CD", "")), ""),
                principal=principal,
                accrued_interest=accrued,
                interest_rate=Decimal(str(row["LN_CRG_ITS_RT"])) if row.get("LN_CRG_ITS_RT") else None,
                preferred_loan=str(row.get("PRF_LN_IND")) == "1",
                raw_data=row
            )
            self._loans.append(loan)
        
        return self._loans
    
    @property
    def total_loan_balance(self) -> Decimal:
        """Total loan balance (principal + accrued interest)."""
        total = Decimal("0")
        for loan in self.get_loans():
            total += loan.principal + loan.accrued_interest
        return total
    
    @property
    def total_loan_principal(self) -> Decimal:
        """Total loan principal."""
        return sum((loan.principal for loan in self.get_loans()), Decimal("0"))
    
    @property
    def total_loan_interest(self) -> Decimal:
        """Total accrued loan interest."""
        return sum((loan.accrued_interest for loan in self.get_loans()), Decimal("0"))
    
    # =========================================================================
    # TRADITIONAL LOAN DETAILS (delegated to LoanRecords)
    # =========================================================================
    
    def get_trad_loans(self) -> List[TradLoanInfo]:
        """Get traditional loan detail records."""
        return self.loan_records.get_trad_loans()
    
    @property
    def trad_loan_count(self) -> int:
        """Count of traditional loan records."""
        return self.loan_records.trad_loan_count
    
    def trad_loan_mv_date(self, index: int) -> Optional[date]:
        """Get traditional loan MV date (0-based index)."""
        return self.loan_records.trad_loan_mv_date(index)
    
    def trad_loan_principal(self, index: int) -> Optional[Decimal]:
        """Get traditional loan principal (0-based index)."""
        return self.loan_records.trad_loan_principal(index)
    
    def trad_loan_accrued(self, index: int) -> Optional[Decimal]:
        """Get traditional loan accrued interest (0-based index)."""
        return self.loan_records.trad_loan_accrued(index)
    
    def trad_loan_interest_rate(self, index: int) -> Optional[Decimal]:
        """Get traditional loan interest rate (0-based index)."""
        return self.loan_records.trad_loan_interest_rate(index)
    
    def trad_loan_interest_type(self, index: int) -> str:
        """Get traditional loan interest type code (0-based index)."""
        return self.loan_records.trad_loan_interest_type(index)
    
    def trad_loan_interest_status(self, index: int) -> str:
        """Get traditional loan interest status code (0-based index)."""
        return self.loan_records.trad_loan_interest_status(index)
    
    def trad_loan_preferred(self, index: int) -> str:
        """Get traditional loan preferred indicator (0-based index)."""
        return self.loan_records.trad_loan_preferred(index)
    
    # =========================================================================
    # FUND LOAN DETAILS (delegated to LoanRecords)
    # =========================================================================
    
    @property
    def loan_fund_count(self) -> int:
        """Count of fund loan records."""
        return self.loan_records.loan_fund_count
    
    def loan_fund_id(self, index: int) -> str:
        """Get loan fund ID (0-based index)."""
        return self.loan_records.loan_fund_id(index)
    
    def loan_fund_mv_date(self, index: int) -> Optional[date]:
        """Get loan fund MV date (0-based index)."""
        return self.loan_records.loan_fund_mv_date(index)
    
    def loan_fund_principal(self, index: int) -> Optional[Decimal]:
        """Get loan fund principal (0-based index)."""
        return self.loan_records.loan_fund_principal(index)
    
    def loan_fund_accrued(self, index: int) -> Optional[Decimal]:
        """Get loan fund accrued interest (0-based index)."""
        return self.loan_records.loan_fund_accrued(index)
    
    def loan_fund_interest_rate(self, index: int) -> Optional[Decimal]:
        """Get loan fund interest rate (0-based index)."""
        return self.loan_records.loan_fund_interest_rate(index)
    
    def loan_fund_interest_status(self, index: int) -> str:
        """Get loan fund interest status code (0-based index)."""
        return self.loan_records.loan_fund_interest_status(index)
    
    def loan_fund_preferred(self, index: int) -> str:
        """Get loan fund preferred indicator (0-based index)."""
        return self.loan_records.loan_fund_preferred(index)
    
    # =========================================================================
    # LOAN REPAYMENT SCHEDULE (delegated to LoanRecords)
    # =========================================================================
    
    def get_loan_repayments(self) -> List[LoanRepayInfo]:
        """Get loan repayment schedule records."""
        return self.loan_records.get_loan_repayments()
    
    @property
    def loan_repay_count(self) -> int:
        """Count of loan repayment records."""
        return self.loan_records.loan_repay_count
    
    def loan_repay_number(self, index: int) -> int:
        """Get loan repayment payment number (0-based index)."""
        return self.loan_records.loan_repay_number(index)
    
    def loan_repay_date(self, index: int) -> Optional[date]:
        """Get loan repayment payment date (0-based index)."""
        return self.loan_records.loan_repay_date(index)
    
    def loan_repay_amount(self, index: int) -> Optional[Decimal]:
        """Get loan repayment payment amount (0-based index)."""
        return self.loan_records.loan_repay_amount(index)
    
    def loan_repay_principal(self, index: int) -> Optional[Decimal]:
        """Get loan repayment principal amount (0-based index)."""
        return self.loan_records.loan_repay_principal(index)
    
    def loan_repay_interest(self, index: int) -> Optional[Decimal]:
        """Get loan repayment interest amount (0-based index)."""
        return self.loan_records.loan_repay_interest(index)

    # =========================================================================
    # CASH VALUE PROPERTIES (delegated to TotalRecords)
    # =========================================================================
    
    @property
    def cash_surrender_value(self) -> Optional[Decimal]:
        """Current cash surrender value."""
        return self.total_records.CSH_SUR_VAL_AMT
    
    @property
    def accumulation_value(self) -> Optional[Decimal]:
        """Current accumulation value (for UL products)."""
        return self.total_records.ACC_VAL_AMT
    
    @property
    def death_benefit(self) -> Optional[Decimal]:
        """Current death benefit."""
        total_records_value = self.total_records.DTH_BNF_AMT
        if total_records_value is not None:
            return total_records_value
        return self.total_death_benefit
    
    @property
    def net_amount_at_risk(self) -> Optional[Decimal]:
        """Net amount at risk."""
        return self.total_records.NET_AMT_RSK
    
    # =========================================================================
    # TAMRA/MEC PROPERTIES (delegated to TotalRecords)
    # =========================================================================
    
    @property
    def is_mec(self) -> bool:
        """Whether policy is a Modified Endowment Contract."""
        return self.total_records.is_mec
    
    @property
    def seven_pay_premium(self) -> Optional[Decimal]:
        """7-Pay premium limit."""
        return self.total_records.seven_pay_premium
    
    @property
    def accumulated_glp(self) -> Optional[Decimal]:
        """Accumulated Guideline Level Premium."""
        return self.total_records.accumulated_glp
    
    @property
    def accumulated_mtp(self) -> Optional[Decimal]:
        """Accumulated 7-Pay Premium (MTP)."""
        return self.total_records.accumulated_mtp
    
    # =========================================================================
    # ACCUMULATOR PROPERTIES (delegated to TotalRecords)
    # =========================================================================
    
    @property
    def total_regular_premium(self) -> Decimal:
        """Total regular premiums paid lifetime (VBA: TotalRegularPremium)."""
        return self.total_records.TOT_REG_PRM_AMT
    
    @property
    def total_premiums_paid(self) -> Optional[Decimal]:
        """Total premiums paid lifetime (alias for total_regular_premium for backward compat)."""
        return self.total_regular_premium
    
    @property
    def total_additional_premium(self) -> Decimal:
        """Total additional premiums paid (VBA: TotalAdditionalPremium)."""
        return self.total_records.TOT_ADD_PRM_AMT
    
    @property
    def total_additional_premiums(self) -> Optional[Decimal]:
        """Alias for backward compat."""
        return self.total_additional_premium
    
    @property
    def premium_td(self) -> Decimal:
        """Total premiums to date = regular + additional (VBA: PremiumTD)."""
        return self.total_records.premium_td
    
    @property
    def total_regular_premium_ytd(self) -> Decimal:
        """Total regular premium year-to-date from LH_POL_YR_TOT (VBA: TotalRegularPremiumYTD)."""
        return self.total_records.total_regular_premium_ytd
    
    @property
    def total_additional_premium_ytd(self) -> Decimal:
        """Total additional premium year-to-date from LH_POL_YR_TOT (VBA: TotalAdditionalPremiumYTD)."""
        return self.total_records.total_additional_premium_ytd
    
    @property
    def premium_ytd(self) -> Decimal:
        """Premium year-to-date = regular YTD + additional YTD (VBA: PremiumYTD)."""
        return self.total_records.premium_ytd
    
    @property
    def total_withdrawals(self) -> Decimal:
        """Total withdrawals lifetime (VBA: AccumWithdrawals from TOT_WTD_AMT)."""
        return self.total_records.TOT_WTD_AMT
    
    @property
    def cost_basis(self) -> Decimal:
        """Tax cost basis (VBA: CostBasis from POL_CST_BSS_AMT)."""
        return self.total_records.POL_CST_BSS_AMT
    
    @property
    def policy_totals_count(self) -> int:
        """Count of LH_POL_TOTALS rows (VBA: PolicyTotalsCount)."""
        return self.total_records.policy_totals_count
    
    # =========================================================================
    # ADVANCED DATE PROPERTIES
    # =========================================================================
    
    @property
    def last_anniversary(self) -> Optional[date]:
        """Last policy anniversary date."""
        return self._parse_date(self.data_item("LH_BAS_POL", "LST_ANV_DT"))
    
    @property
    def next_monthliversary(self) -> Optional[date]:
        """Next monthliversary processing date."""
        return self._parse_date(self.data_item("LH_BAS_POL", "NXT_MVRY_PRC_DT"))
    
    @property
    def last_financial_date(self) -> Optional[date]:
        """Last financial processing date."""
        dt = self._parse_date(self.data_item("LH_BAS_POL", "LST_FIN_DT"))
        # Treat sentinel dates (e.g. 9999-12-31) as missing
        if dt and dt.year >= 9999:
            return None
        return dt
    
    @property
    def next_bill_date(self) -> Optional[date]:
        """Next billing date."""
        return self._parse_date(self.data_item("LH_BAS_POL", "NXT_BIL_DT"))
    
    @property
    def premium_paid_to_date(self) -> Optional[date]:
        """Premium paid-to date."""
        return self._parse_date(self.data_item("LH_BAS_POL", "PRM_BILL_TO_DT"))
    
    @property
    def valuation_date(self) -> Optional[date]:
        """
        Get valuation date - MV date for UL, last monthliversary for traditional.
        """
        if self.is_advanced_product:
            mv_dt = self._parse_date(self.data_item("LH_POL_MVRY_VAL", "MVRY_DT"))
            if mv_dt and mv_dt.year < 9999:
                return mv_dt
        
        next_mv = self.next_monthliversary_date
        if next_mv and next_mv.year < 9999:
            # Go back exactly one calendar month (same day)
            if next_mv.month == 1:
                prev_year, prev_month = next_mv.year - 1, 12
            else:
                prev_year, prev_month = next_mv.year, next_mv.month - 1
            # Handle day overflow (e.g. March 31 → Feb 28)
            import calendar
            max_day = calendar.monthrange(prev_year, prev_month)[1]
            prev_day = min(next_mv.day, max_day)
            return date(prev_year, prev_month, prev_day)
        
        return self.last_financial_date
    
    @property
    def grace_period_expiry_date(self) -> Optional[date]:
        """Grace period expiration date."""
        if self.is_advanced_product:
            return self._parse_date(self.data_item("LH_NON_TRD_POL", "GRA_PER_EXP_DT"))
        else:
            return self._parse_date(self.data_item("LH_TRD_POL", "GRA_PER_EXP_DT"))
    
    @property
    def in_grace(self) -> bool:
        """Whether policy is in grace period."""
        if self.is_advanced_product:
            return str(self.data_item("LH_NON_TRD_POL", "IN_GRA_PER_IND")) == "1"
        else:
            return str(self.data_item("LH_TRD_POL", "IN_GRA_PER_IND")) == "1"
    
    # =========================================================================
    # ADDITIONAL POLICY PROPERTIES
    # =========================================================================
    
    @property
    def original_entry_code(self) -> str:
        """Original entry code."""
        return str(self.data_item("LH_BAS_POL", "OGN_ETR_CD") or "")
    
    @property
    def last_entry_code(self) -> str:
        """Last entry code."""
        return str(self.data_item("LH_BAS_POL", "LST_ETR_CD") or "")
    
    @property
    def policy_1035_indicator(self) -> bool:
        """Whether policy involved a 1035 exchange."""
        return str(self.data_item("LH_BAS_POL", "POL_1035_XCG_IND")) == "1"
    
    @property
    def servicing_agent_number(self) -> str:
        """Servicing agent number."""
        return str(self.data_item("LH_BAS_POL", "SVC_AGT_NBR") or "")
    
    @property
    def servicing_branch_code(self) -> str:
        """Servicing branch/agency code."""
        return str(self.data_item("LH_BAS_POL", "SVC_AGC_NBR") or "")
    
    @property
    def servicing_market_org(self) -> str:
        """Determine market organization from company and agent codes."""
        branch = self.servicing_branch_code
        agent_code = branch[0] if branch else ""
        return translate_market_org(self.company_code, agent_code)
    
    @property
    def agency_branch_code(self) -> str:
        """Extract agency branch code from servicing branch code."""
        branch = self.servicing_branch_code
        return branch[1:5] if len(branch) >= 5 else branch
    
    @property
    def is_ffs(self) -> bool:
        """Whether policy is Fee-for-Service (IMG with specific branch)."""
        return self.servicing_market_org == "IMG" and self.agency_branch_code == "0B4Q"
    
    @property
    def policy_loan_charge_rate(self) -> Optional[Decimal]:
        """Policy loan charge interest rate."""
        val = self.data_item("LH_BAS_POL", "LN_PLN_ITS_RT")
        return Decimal(str(val)) if val is not None else None
    
    @property
    def forced_premium_indicator(self) -> bool:
        """Whether policy has forced premium."""
        return str(self.data_item("TH_BAS_POL", "FORCED_PREM_IND")) == "1"
    
    @property
    def mdo_code(self) -> str:
        """MDO (market/distribution) code."""
        return str(self.data_item("LH_BAS_POL", "USR_RES_CD") or "")
    
    @property
    def bill_form_code(self) -> str:
        """Billing form code."""
        return str(self.data_item("LH_BAS_POL", "BIL_FRM_CD") or "")

    @property
    def is_eft(self) -> bool:
        """True if billing uses electronic funds transfer (PAC/EFT).

        CyberLife BIL_FRM_CD values (via VBA TranslateBillFormCode):
            0 = Direct pay notice  (NOT EFT)
            G = PAC                (EFT)
            H = Salary deduction   (EFT)
            I = Bank deduction     (EFT)
            F = Government allotment (EFT)
        Non-direct-bill forms use the EFT modal factor for monthly billing.
        """
        # Anything other than "0" (direct pay notice) is considered EFT
        return self.bill_form_code not in ("0", "")
    
    # =========================================================================
    # DETAILED LOAN PROPERTIES (delegated to LoanRecords)
    # =========================================================================
    
    @property
    def total_regular_loan_principal(self) -> Decimal:
        """Total regular loan principal."""
        return self.loan_records.total_regular_loan_principal
    
    @property
    def total_regular_loan_accrued(self) -> Decimal:
        """Total regular loan accrued interest."""
        return self.loan_records.total_regular_loan_accrued
    
    @property
    def total_preferred_loan_principal(self) -> Decimal:
        """Total preferred loan principal."""
        return self.loan_records.total_preferred_loan_principal
    
    @property
    def total_preferred_loan_accrued(self) -> Decimal:
        """Total preferred loan accrued interest."""
        return self.loan_records.total_preferred_loan_accrued
    
    @property
    def total_variable_loan_principal(self) -> Decimal:
        """Total variable loan principal (UL only, fund LZ)."""
        return self.loan_records.total_variable_loan_principal
    
    @property
    def total_variable_loan_accrued(self) -> Decimal:
        """Total variable loan accrued interest (UL only, fund LZ)."""
        return self.loan_records.total_variable_loan_accrued

    @property
    def variable_loan_charge_rate(self) -> Optional[Decimal]:
        """Most recent variable loan charge rate, or None when not applicable."""
        return self.loan_records.variable_loan_charge_rate
    
    @property
    def policy_debt(self) -> Decimal:
        """Total policy debt (all loans principal + interest)."""
        return self.loan_records.policy_debt
    
    @property
    def preferred_loans_available(self) -> bool:
        """Whether preferred loans are available on this policy."""
        return self.loan_records.preferred_loans_available
    
    # =========================================================================
    # NON-TRAD POLICY PROPERTIES
    # =========================================================================
    
    @property
    def guaranteed_interest_rate(self) -> Optional[Decimal]:
        """Guaranteed interest rate for advanced products."""
        val = self.data_item("LH_NON_TRD_POL", "POL_GUA_ITS_RT")
        return Decimal(str(val)) if val is not None else None

    @property
    def fixed_loan_interest_rate(self) -> Optional[Decimal]:
        """Fixed (regular) loan interest charge rate (LH_BAS_POL.LN_PLN_ITS_RT)."""
        val = self.data_item("LH_BAS_POL", "LN_PLN_ITS_RT")
        return Decimal(str(val)) if val is not None else None

    @property
    def preferred_loan_interest_rate(self) -> Optional[Decimal]:
        """Preferred loan interest charge rate (LH_NON_TRD_POL.PRF_LN_ITS_CRG_RT)."""
        val = self.data_item("LH_NON_TRD_POL", "PRF_LN_ITS_CRG_RT")
        return Decimal(str(val)) if val is not None else None

    @property
    def corridor_percent(self) -> Optional[Decimal]:
        """Corridor percentage for death benefit calculation."""
        val = self.data_item("LH_NON_TRD_POL", "CDR_PCT")
        return Decimal(str(val)) if val is not None else Decimal("100")
    
    @property
    def grace_rule_code(self) -> str:
        """Grace period rule code."""
        return str(self.data_item("LH_NON_TRD_POL", "GRA_THD_RLE_CD") or "")

    @property
    def decrease_charge_rule(self) -> str:
        """Decrease Charge Rule code (TH_NON_TRD_POL.DECR_CHRG_ALLOW, FULDRRUL).

        Live values are ``"1"`` (specified decreases assess a partial surrender
        charge) and ``"0"`` (they do not). Blank/NUL-padded rows are unset and
        return ``""``.
        """
        return str(self.data_item("TH_NON_TRD_POL", "DECR_CHRG_ALLOW") or "").strip(" \x00")

    @property
    def decrease_charge_allowed(self) -> Optional[bool]:
        """Whether a specified-amount decrease assesses a partial surrender charge.

        ``None`` when the Decrease Charge Rule is unset or unrecognized, so
        callers keep their plan-level rule rather than guessing.
        """
        return {"1": True, "0": False}.get(self.decrease_charge_rule)
    
    @property
    def tefra_defra_code(self) -> str:
        """TEFRA/DEFRA indicator code."""
        return str(self.data_item("LH_NON_TRD_POL", "TFDF_CD") or "")
    
    @property
    def tefra_defra(self) -> str:
        """TEFRA or DEFRA description."""
        code = self.tefra_defra_code
        if code in ("1",):
            return "TEFRA"
        elif code in ("2", "3", "5"):
            return "DEFRA"
        return code
    
    @property
    def gpt_cvat(self) -> str:
        """GPT or CVAT test type."""
        code = self.tefra_defra_code
        if code in ("1", "2", "4"):
            return "GPT"
        elif code in ("3", "5"):
            return "CVAT"
        return code
    
    # =========================================================================
    # TARGET PREMIUMS (LH_POL_TARGET)
    # =========================================================================
    # Uses the common pattern: lookup by TAR_TYP_CD to get TAR_PRM_AMT or TAR_DT
    # Target Type Codes:
    #   MT = Minimum Target Premium (MTP)
    #   MA = Accumulated MTP / MAP date
    #   TA = Accumulated GLP Target
    #   LT = Premium Limit Target (PLT)
    #   IX = GAV (Guaranteed Account Value) from Index
    #   DT = Dial-to premium
    #   NS = NSP Base
    #   NT = NSP Other
    
    def _get_target_amount(self, target_type: str) -> Optional[Decimal]:
        """Get target premium amount by type code using data_item_where pattern."""
        val = self.data_item_where("LH_POL_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", target_type)
        return Decimal(str(val)) if val is not None else None
    
    def _get_target_date(self, target_type: str) -> Optional[date]:
        """Get target date by type code using data_item_where pattern."""
        val = self.data_item_where("LH_POL_TARGET", "TAR_DT", "TAR_TYP_CD", target_type)
        return self._parse_date(val)
    
    @property
    def mtp(self) -> Optional[Decimal]:
        """Minimum Target Premium (TAR_TYP_CD = 'MT')."""
        return self._get_target_amount("MT")
    
    @property
    def accumulated_mtp_target(self) -> Optional[Decimal]:
        """Accumulated MTP from targets (TAR_TYP_CD = 'MA')."""
        return self._get_target_amount("MA")
    
    @property
    def map_date(self) -> Optional[date]:
        """MAP (SafetyNet) cease date (TAR_TYP_CD = 'MA')."""
        return self._get_target_date("MA")
    
    @property
    def accumulated_glp_target(self) -> Optional[Decimal]:
        """Accumulated GLP from targets (TAR_TYP_CD = 'TA')."""
        return self._get_target_amount("TA")
    
    @property
    def plt(self) -> Optional[Decimal]:
        """Premium Limit Target (TAR_TYP_CD = 'LT')."""
        return self._get_target_amount("LT")
    
    @property
    def gav(self) -> Optional[Decimal]:
        """GAV (Guaranteed Account Value) from Index target (TAR_TYP_CD = 'IX')."""
        return self._get_target_amount("IX")
    
    @property
    def dial_to_premium(self) -> Optional[Decimal]:
        """Dial-to premium amount (TAR_TYP_CD = 'DT')."""
        return self._get_target_amount("DT")
    
    @property
    def nsp_base(self) -> Optional[Decimal]:
        """NSP Base target (TAR_TYP_CD = 'NS')."""
        return self._get_target_amount("NS")
    
    @property
    def nsp_other(self) -> Optional[Decimal]:
        """NSP Other target (TAR_TYP_CD = 'NT')."""
        return self._get_target_amount("NT")
    
    @property
    def ctp(self) -> Optional[Decimal]:
        """Commission Target Premium - sum of all CT entries."""
        # CTP can have multiple records, so we sum them
        amounts = self.data_items_where("LH_COM_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", "CT")
        if not amounts:
            return None
        total = Decimal("0")
        for val in amounts:
            if val is not None:
                total += Decimal(str(val))
        return total if total > 0 else None
    
    # =========================================================================
    # SHORT PAY / USER GENERIC FIELDS (TH_USER_GENERIC)
    # =========================================================================
    
    @property
    def short_pay_duration(self) -> Optional[int]:
        """Short pay duration in years from TH_USER_GENERIC."""
        val = self.data_item("TH_USER_GENERIC", "INITIAL_PAY_DUR")
        return int(val) if val and int(val) > 0 else None
    
    @property
    def short_pay_mode(self) -> Optional[str]:
        """Short pay mode from TH_USER_GENERIC."""
        return str(self.data_item("TH_USER_GENERIC", "INITIAL_MODE") or "") if self.short_pay_duration else None
    
    @property
    def short_pay_premium(self) -> Optional[Decimal]:
        """Short pay premium amount from LH_POL_TARGET where TAR_TYP_CD = 'VS'."""
        val = self._get_target_amount("VS")
        return val
    
    @property
    def short_pay_date(self) -> Optional[date]:
        """Short pay billing cease date from LH_POL_TARGET where TAR_TYP_CD = 'VS'."""
        val = self._get_target_date("VS")
        return val
    
    @property
    def sp_billing_cease_date(self) -> Optional[date]:
        """Short pay billing cease date (alias for short_pay_date)."""
        return self.short_pay_date
    
    @property
    def sp_prem_cease_age(self) -> Optional[int]:
        """Short pay premium cease age - calculated as duration + issue age of base coverage."""
        if not self.short_pay_duration:
            return None
        # Get issue age of first base coverage (coverage index 1)
        issue_age = self.cov_issue_age(1)
        if issue_age:
            return self.short_pay_duration + issue_age
        return None
    
    @property
    def db_dial_to_age(self) -> Optional[int]:
        """Death benefit dial-to premium age from TH_USER_GENERIC."""
        val = self.data_item("TH_USER_GENERIC", "DIAL_TO_PREM_AGE")
        return int(val) if val and int(val) > 0 else None

    @property
    def reins_partner(self) -> str:
        """Reinsurance partner indicator from TH_USER_GENERIC.FUZGREIN_IND.

        Originally created 11/13/2024 to identify policies in the RGA Orion deal.
        """
        return str(self.data_item("TH_USER_GENERIC", "FUZGREIN_IND") or "").strip()
    
    # =========================================================================
    # GUIDELINE PREMIUMS (LH_COV_INS_GDL_PRM)
    # =========================================================================
    # Uses the common pattern: lookup by PRM_RT_TYP_CD to get GDL_PRM_AMT
    # Premium Rate Type Codes:
    #   A = Annual/Level (GLP - Guideline Level Premium)
    #   S = Single (GSP - Guideline Single Premium)
    
    @property
    def glp(self) -> Optional[Decimal]:
        """Guideline Level Premium (PRM_RT_TYP_CD = 'A')."""
        val = self.data_item_where("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT", "PRM_RT_TYP_CD", "A")
        return Decimal(str(val)) if val is not None else None
    
    @property
    def gsp(self) -> Optional[Decimal]:
        """Guideline Single Premium (PRM_RT_TYP_CD = 'S')."""
        val = self.data_item_where("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT", "PRM_RT_TYP_CD", "S")
        return Decimal(str(val)) if val is not None else None
    
    # =========================================================================
    # MONTHLIVERSARY VALUES (LH_POL_MVRY_VAL)
    # =========================================================================
    
    @property
    def mv_count(self) -> int:
        """Count of monthliversary value records."""
        return self.data_item_count("LH_POL_MVRY_VAL")
    
    def mv_date(self, index: int = 0) -> Optional[date]:
        """Get monthliversary date at index."""
        return self._parse_date(self.data_item("LH_POL_MVRY_VAL", "MVRY_DT", index))
    
    def mv_av(self, index: int = 0) -> Optional[Decimal]:
        """Get MV accumulation value at index."""
        val = self.data_item("LH_POL_MVRY_VAL", "CSV_AMT", index)
        return Decimal(str(val)) if val is not None else None
    
    def mv_coi_charge(self, index: int = 0) -> Decimal:
        """Get MV COI charge at index."""
        val = self.data_item("LH_POL_MVRY_VAL", "CINS_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")
    
    def mv_expense_charge(self, index: int = 0) -> Decimal:
        """Get MV expense charge at index."""
        val = self.data_item("LH_POL_MVRY_VAL", "EXP_CRG_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")
    
    def mv_other_charge(self, index: int = 0) -> Decimal:
        """Get MV other charges at index."""
        val = self.data_item("LH_POL_MVRY_VAL", "OTH_PRM_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")
    
    def mv_monthly_deduction(self, index: int = 0) -> Decimal:
        """Get total MV monthly deduction at index."""
        return self.mv_coi_charge(index) + self.mv_expense_charge(index) + self.mv_other_charge(index)
    
    def mv_nar(self, index: int = 0) -> Decimal:
        """Get MV net amount at risk at index."""
        val = self.data_item("LH_POL_MVRY_VAL", "NAR_AMT", index)
        return Decimal(str(val)) if val else Decimal("0")
    
    @property
    def mv_policy_year(self) -> Optional[int]:
        """Current policy year from MV record."""
        val = self.data_item("LH_POL_MVRY_VAL", "POL_DUR_NBR")
        return int(val) if val else None
    
    # =========================================================================
    # TAMRA / MEC PROPERTIES (from VBA)
    # =========================================================================
    
    @property
    def tamra_7pay_level(self) -> Optional[Decimal]:
        """7-pay level premium."""
        val = self.data_item("LH_TAMRA_7_PY_PER", "SVPY_LVL_PRM_AMT")
        return Decimal(str(val)) if val else None
    
    @property
    def tamra_7pay_start_date(self) -> Optional[date]:
        """7-pay period start date."""
        dt = self._parse_date(self.data_item("LH_TAMRA_7_PY_PER", "SVPY_PER_STR_DT"))
        if dt and dt.year >= 9999:
            return None
        return dt
    
    @property
    def tamra_7pay_av(self) -> Optional[Decimal]:
        """7-pay beginning CSV amount."""
        val = self.data_item("LH_TAMRA_7_PY_PER", "SVPY_BEG_CSV_AMT")
        return Decimal(str(val)) if val else None
    
    @property
    def tamra_7pay_specified_amount(self) -> Optional[Decimal]:
        """7-pay beginning face amount."""
        val = self.data_item("LH_TAMRA_7_PY_PER", "SVPY_BEG_FCE_AMT")
        return Decimal(str(val)) if val else None
    
    @property
    def mec_indicator(self) -> str:
        """MEC status indicator code."""
        return str(self.data_item("LH_TAMRA_7_PY_PER", "MEC_STA_CD") or "")
    
    @property
    def count_1035_payments(self) -> int:
        """Number of 1035 exchange payments."""
        val = self.data_item("LH_TAMRA_7_PY_PER", "XCG_1035_PMT_QTY")
        return int(val) if val else 0
    
    def tamra_7pay_premium_paid(self, year: int) -> Optional[Decimal]:
        """Get 7-pay premium paid for specified year (1-7)."""
        if year < 1 or year > 7:
            return None
        val = self.data_item("LH_TAMRA_7_PY_YR", "SVPY_PRM_PAY_AMT", year - 1)
        return Decimal(str(val)) if val else None
    
    def tamra_7pay_withdrawals(self, year: int) -> Optional[Decimal]:
        """Get 7-pay withdrawals for specified year (1-7)."""
        if year < 1 or year > 7:
            return None
        val = self.data_item("LH_TAMRA_7_PY_YR", "SVPY_WTD_AMT", year - 1)
        return Decimal(str(val)) if val else None
    
    # =========================================================================
    # APPLIED DIVIDENDS (LH_APPLIED_PTP)
    # =========================================================================
    
    def get_applied_dividends(self) -> List[AppliedDividendInfo]:
        """Get applied dividend records."""
        dividends = []
        for row in self.fetch_table("LH_APPLIED_PTP"):
            div_type = str(row.get("PTP_APL_TYP_CD", "") or "")
            div = AppliedDividendInfo(
                dividend_date=self._parse_date(row.get("PTP_APL_DT")),
                dividend_type=div_type,
                dividend_type_desc=translate_div_type_code(div_type),
                gross_amount=Decimal(str(row["PTP_GRS_AMT"])) if row.get("PTP_GRS_AMT") else None,
                net_amount=Decimal(str(row["PTP_NET_AMT"])) if row.get("PTP_NET_AMT") else None,
                year=int(row["POL_DUR_NBR"]) if row.get("POL_DUR_NBR") else None,
                raw_data=row
            )
            dividends.append(div)
        return dividends
    
    @property
    def applied_div_count(self) -> int:
        """Count of applied dividend records."""
        return self.data_item_count("LH_APPLIED_PTP")
    
    def applied_div_date(self, index: int) -> Optional[date]:
        """Get applied dividend date (0-based index)."""
        return self._parse_date(self.data_item("LH_APPLIED_PTP", "PTP_APL_DT", index))
    
    def applied_div_type(self, index: int) -> str:
        """Get applied dividend type code (0-based index)."""
        return str(self.data_item("LH_APPLIED_PTP", "PTP_APL_TYP_CD", index) or "")
    
    def applied_div_gross_amount(self, index: int) -> Optional[Decimal]:
        """Get applied dividend gross amount (0-based index)."""
        val = self.data_item("LH_APPLIED_PTP", "PTP_GRS_AMT", index)
        return Decimal(str(val)) if val else None
    
    def applied_div_net_amount(self, index: int) -> Optional[Decimal]:
        """Get applied dividend net amount (0-based index)."""
        val = self.data_item("LH_APPLIED_PTP", "PTP_NET_AMT", index)
        return Decimal(str(val)) if val else None
    
    def applied_div_year(self, index: int) -> Optional[int]:
        """Get applied dividend policy year (0-based index)."""
        val = self.data_item("LH_APPLIED_PTP", "POL_DUR_NBR", index)
        return int(val) if val else None
    
    # =========================================================================
    # UNAPPLIED DIVIDENDS (LH_UNAPPLIED_PTP)
    # =========================================================================
    
    def get_unapplied_dividends(self) -> List[UnappliedDividendInfo]:
        """Get unapplied dividend records."""
        dividends = []
        for row in self.fetch_table("LH_UNAPPLIED_PTP"):
            div_type = str(row.get("PTP_TYP_CD", "") or "")
            div = UnappliedDividendInfo(
                dividend_date=self._parse_date(row.get("PTP_PRO_DT")),
                dividend_type=div_type,
                dividend_type_desc=translate_div_type_code(div_type),
                gross_amount=Decimal(str(row["PTP_GRS_AMT"])) if row.get("PTP_GRS_AMT") else None,
                net_amount=Decimal(str(row["PTP_NET_AMT"])) if row.get("PTP_NET_AMT") else None,
                year=int(row["POL_DUR_NBR"]) if row.get("POL_DUR_NBR") else None,
                raw_data=row
            )
            dividends.append(div)
        return dividends
    
    @property
    def unapplied_div_count(self) -> int:
        """Count of unapplied dividend records."""
        return self.data_item_count("LH_UNAPPLIED_PTP")
    
    def unapplied_div_date(self, index: int) -> Optional[date]:
        """Get unapplied dividend date (0-based index)."""
        return self._parse_date(self.data_item("LH_UNAPPLIED_PTP", "PTP_PRO_DT", index))
    
    def unapplied_div_type(self, index: int) -> str:
        """Get unapplied dividend type code (0-based index)."""
        return str(self.data_item("LH_UNAPPLIED_PTP", "PTP_TYP_CD", index) or "")
    
    def unapplied_div_gross_amount(self, index: int) -> Optional[Decimal]:
        """Get unapplied dividend gross amount (0-based index)."""
        val = self.data_item("LH_UNAPPLIED_PTP", "PTP_GRS_AMT", index)
        return Decimal(str(val)) if val else None
    
    def unapplied_div_net_amount(self, index: int) -> Optional[Decimal]:
        """Get unapplied dividend net amount (0-based index)."""
        val = self.data_item("LH_UNAPPLIED_PTP", "PTP_NET_AMT", index)
        return Decimal(str(val)) if val else None
    
    def unapplied_div_year(self, index: int) -> Optional[int]:
        """Get unapplied dividend policy year (0-based index)."""
        val = self.data_item("LH_UNAPPLIED_PTP", "POL_DUR_NBR", index)
        return int(val) if val else None
    
    # =========================================================================
    # ONE YEAR TERM ADDITIONS (LH_ONE_YR_TRM_ADD)
    # =========================================================================
    
    def get_div_oyt(self) -> List[DivOYTInfo]:
        """Get one year term dividend addition records."""
        oyts = []
        for row in self.fetch_table("LH_ONE_YR_TRM_ADD"):
            oyt = DivOYTInfo(
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                issue_date=self._parse_date(row.get("OYT_ISS_DT")),
                face_amount=Decimal(str(row["OYT_FCE_AMT"])) if row.get("OYT_FCE_AMT") else None,
                csv_amount=Decimal(str(row["OYT_CSV_AMT"])) if row.get("OYT_CSV_AMT") else None,
                raw_data=row
            )
            oyts.append(oyt)
        return oyts
    
    @property
    def div_oyt_count(self) -> int:
        """Count of OYT records."""
        return self.data_item_count("LH_ONE_YR_TRM_ADD")
    
    def div_oyt_cov_phase(self, index: int) -> int:
        """Get OYT coverage phase (0-based index)."""
        val = self.data_item("LH_ONE_YR_TRM_ADD", "COV_PHA_NBR", index)
        return int(val) if val else 0
    
    def div_oyt_issue_date(self, index: int) -> Optional[date]:
        """Get OYT issue date (0-based index)."""
        return self._parse_date(self.data_item("LH_ONE_YR_TRM_ADD", "OYT_ISS_DT", index))
    
    def div_oyt_face_amount(self, index: int) -> Optional[Decimal]:
        """Get OYT face amount (0-based index)."""
        val = self.data_item("LH_ONE_YR_TRM_ADD", "OYT_FCE_AMT", index)
        return Decimal(str(val)) if val else None
    
    def div_oyt_csv(self, index: int) -> Optional[Decimal]:
        """Get OYT cash surrender value (0-based index)."""
        val = self.data_item("LH_ONE_YR_TRM_ADD", "OYT_CSV_AMT", index)
        return Decimal(str(val)) if val else None
    
    @property
    def total_oyt_face(self) -> Decimal:
        """Total OYT face amount."""
        total = Decimal("0")
        for i in range(self.div_oyt_count):
            val = self.div_oyt_face_amount(i)
            if val:
                total += val
        return total
    
    @property
    def total_oyt_csv(self) -> Decimal:
        """Total OYT cash surrender value."""
        total = Decimal("0")
        for i in range(self.div_oyt_count):
            val = self.div_oyt_csv(i)
            if val:
                total += val
        return total
    
    # =========================================================================
    # PAID UP ADDITIONS (LH_PAID_UP_ADD)
    # =========================================================================
    
    def get_div_pua(self) -> List[DivPUAInfo]:
        """Get paid-up addition records."""
        puas = []
        for row in self.fetch_table("LH_PAID_UP_ADD"):
            pua = DivPUAInfo(
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                issue_date=self._parse_date(row.get("PUA_ISS_DT")),
                face_amount=Decimal(str(row["PUA_FCE_AMT"])) if row.get("PUA_FCE_AMT") else None,
                csv_amount=Decimal(str(row["PUA_CSV_AMT"])) if row.get("PUA_CSV_AMT") else None,
                raw_data=row
            )
            puas.append(pua)
        return puas
    
    @property
    def div_pua_count(self) -> int:
        """Count of PUA records."""
        return self.data_item_count("LH_PAID_UP_ADD")
    
    def div_pua_cov_phase(self, index: int) -> int:
        """Get PUA coverage phase (0-based index)."""
        val = self.data_item("LH_PAID_UP_ADD", "COV_PHA_NBR", index)
        return int(val) if val else 0
    
    def div_pua_issue_date(self, index: int) -> Optional[date]:
        """Get PUA issue date (0-based index)."""
        return self._parse_date(self.data_item("LH_PAID_UP_ADD", "PUA_ISS_DT", index))
    
    def div_pua_face_amount(self, index: int) -> Optional[Decimal]:
        """Get PUA face amount (0-based index)."""
        val = self.data_item("LH_PAID_UP_ADD", "PUA_FCE_AMT", index)
        return Decimal(str(val)) if val else None
    
    def div_pua_csv(self, index: int) -> Optional[Decimal]:
        """Get PUA cash surrender value (0-based index)."""
        val = self.data_item("LH_PAID_UP_ADD", "PUA_CSV_AMT", index)
        return Decimal(str(val)) if val else None
    
    @property
    def total_pua_face(self) -> Decimal:
        """Total PUA face amount."""
        total = Decimal("0")
        for i in range(self.div_pua_count):
            val = self.div_pua_face_amount(i)
            if val:
                total += val
        return total
    
    @property
    def total_pua_csv(self) -> Decimal:
        """Total PUA cash surrender value."""
        total = Decimal("0")
        for i in range(self.div_pua_count):
            val = self.div_pua_csv(i)
            if val:
                total += val
        return total
    
    # =========================================================================
    # DIVIDENDS ON DEPOSIT (LH_PTP_ON_DEP)
    # =========================================================================
    
    def get_div_deposits(self) -> List[DivDepositInfo]:
        """Get dividend on deposit records."""
        deposits = []
        for row in self.fetch_table("LH_PTP_ON_DEP"):
            dep_type = str(row.get("PTP_TYP_CD", "") or "")
            dep = DivDepositInfo(
                deposit_date=self._parse_date(row.get("DEP_DT")),
                deposit_type=dep_type,
                deposit_type_desc=translate_div_type_code(dep_type),
                deposit_amount=Decimal(str(row["CUM_DEP_AMT"])) if row.get("CUM_DEP_AMT") else None,
                interest_amount=Decimal(str(row["ITS_AMT"])) if row.get("ITS_AMT") else None,
                raw_data=row
            )
            deposits.append(dep)
        return deposits
    
    @property
    def div_deposit_count(self) -> int:
        """Count of dividend deposit records."""
        return self.data_item_count("LH_PTP_ON_DEP")
    
    def div_deposit_date(self, index: int) -> Optional[date]:
        """Get dividend deposit date (0-based index)."""
        return self._parse_date(self.data_item("LH_PTP_ON_DEP", "DEP_DT", index))
    
    def div_deposit_type(self, index: int) -> str:
        """Get dividend deposit type code (0-based index)."""
        return str(self.data_item("LH_PTP_ON_DEP", "PTP_TYP_CD", index) or "")
    
    def div_deposit_amount(self, index: int) -> Optional[Decimal]:
        """Get cumulative dividend deposit amount (0-based index)."""
        val = self.data_item("LH_PTP_ON_DEP", "CUM_DEP_AMT", index)
        return Decimal(str(val)) if val else None
    
    def div_deposit_interest(self, index: int) -> Optional[Decimal]:
        """Get dividend deposit interest amount (0-based index)."""
        val = self.data_item("LH_PTP_ON_DEP", "ITS_AMT", index)
        return Decimal(str(val)) if val else None
    
    @property
    def total_div_deposit(self) -> Decimal:
        """Total dividend deposits."""
        total = Decimal("0")
        for i in range(self.div_deposit_count):
            val = self.div_deposit_amount(i)
            if val:
                total += val
        return total
    
    @property
    def total_div_interest(self) -> Decimal:
        """Total dividend deposit interest."""
        total = Decimal("0")
        for i in range(self.div_deposit_count):
            val = self.div_deposit_interest(i)
            if val:
                total += val
        return total

    # =========================================================================
    # PERSON INFORMATION (VH_POL_HAS_LOC_CLT / LH_CTT_CLIENT)
    # =========================================================================
    
    @property
    def person_count(self) -> int:
        """Number of persons on policy."""
        return self.data_item_count("LH_CTT_CLIENT")
    
    def person_index(self, person_code: str = "00", seq_nbr: int = 1) -> Optional[int]:
        """Find index for person by code and sequence."""
        for i in range(self.person_count):
            if (str(self.data_item("LH_CTT_CLIENT", "PRS_CD", i)) == person_code and
                int(self.data_item("LH_CTT_CLIENT", "PRS_SEQ_NBR", i) or 0) == seq_nbr):
                return i
        return None
    
    def person_first_name(self, index: int) -> str:
        """Get person first name at index."""
        return str(self.data_item("VH_POL_HAS_LOC_CLT", "CK_FST_NM", index) or "").strip()
    
    def person_last_name(self, index: int) -> str:
        """Get person last name at index."""
        return str(self.data_item("VH_POL_HAS_LOC_CLT", "CK_LST_NM", index) or "").strip()
    
    def person_full_name(self, index: int) -> str:
        """Get person full name at index."""
        return f"{self.person_first_name(index)} {self.person_last_name(index)}".strip()
    
    def person_birth_date(self, index: int) -> Optional[date]:
        """Get person birth date at index."""
        return self._parse_date(self.data_item("LH_CTT_CLIENT", "BIR_DT", index))
    
    def person_gender(self, index: int) -> str:
        """Get person gender code at index."""
        return str(self.data_item("LH_CTT_CLIENT", "GENDER_CD", index) or "")
    
    def person_code(self, index: int) -> str:
        """Get person code at index."""
        return str(self.data_item("LH_CTT_CLIENT", "PRS_CD", index) or "")
    
    @property
    def primary_insured_name(self) -> str:
        """Primary insured full name."""
        idx = self.person_index("00", 1)
        if idx is not None:
            return self.person_full_name(idx)
        return ""
    
    @property
    def primary_insured_birth_date(self) -> Optional[date]:
        """Primary insured date of birth (LH_CTT_CLIENT.BIR_DT)."""
        idx = self.person_index("00", 1)
        if idx is not None:
            return self.person_birth_date(idx)
        return None
    
    # =========================================================================
    # ADDRESS INFORMATION (LH_LOC_CLT_ADR)
    # =========================================================================

    
    @property
    def address_count(self) -> int:
        """Number of address records."""
        return self.data_item_count("LH_LOC_CLT_ADR")
    
    def address_street1(self, index: int) -> str:
        """Get address line 1 at index."""
        return str(self.data_item("LH_LOC_CLT_ADR", "ADR_LIN_1", index) or "").strip()
    
    def address_street2(self, index: int) -> str:
        """Get address line 2 at index."""
        return str(self.data_item("LH_LOC_CLT_ADR", "ADR_LIN_2", index) or "").strip()
    
    def address_city(self, index: int) -> str:
        """Get city at index."""
        return str(self.data_item("LH_LOC_CLT_ADR", "CIT_TXT", index) or "").strip()
    
    def address_state(self, index: int) -> str:
        """Get state at index."""
        return str(self.data_item("LH_LOC_CLT_ADR", "CK_ST_CD", index) or "").strip()
    
    def address_zip(self, index: int) -> str:
        """Get ZIP code at index."""
        return str(self.data_item("LH_LOC_CLT_ADR", "ZIP_CD", index) or "").strip()
    
    def get_full_address(self, index: int = 0) -> str:
        """Get formatted full address at index."""
        street = f"{self.address_street1(index)} {self.address_street2(index)}".strip()
        city_state_zip = f"{self.address_city(index)}, {self.address_state(index)} {self.address_zip(index)}"
        return f"{street}\n{city_state_zip}".strip()
    
    # =========================================================================
    # AGENT INFORMATION (LH_CTT_COM_PHA_WA)
    # =========================================================================
    
    @property
    def writing_agent_name(self) -> str:
        """Writing agent name."""
        return str(self.data_item("LH_CTT_COM_PHA_WA", "WRT_AGT_NM") or "").strip()
    
    # =========================================================================
    # RENEWAL RATES (LH_COV_INS_RNL_RT / LH_BNF_INS_RNL_RT)
    # =========================================================================
    
    def get_coverage_renewal_rates(self, cov_pha_nbr: int = None) -> List[RenewalCovRateInfo]:
        """Get coverage renewal rate records, optionally filtered by coverage."""
        rates = []
        plancodes_by_phase = {
            int(row.get("COV_PHA_NBR", 0) or 0): str(row.get("PLN_DES_SER_CD", "") or "")
            for row in self.fetch_table("LH_COV_PHA")
        }
        for row in self.fetch_table("LH_COV_INS_RNL_RT"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if cov_pha_nbr is not None and phase != cov_pha_nbr:
                continue
            
            rate_type = str(row.get("PRM_RT_TYP_CD", "") or "")
            rate_class = str(row.get("RT_CLS_CD", "") or "")
            rate = RenewalCovRateInfo(
                coverage_phase=phase,
                rate_type=rate_type,
                rate_type_desc=translate_renewal_rate_type_code(rate_type),
                joint_indicator=str(row.get("JT_INS_IND", "") or ""),
                rate_class=rate_class,
                rate_class_desc=rate_class_description(
                    rate_class, plancodes_by_phase.get(phase, "")
                ),
                issue_age=self._parse_optional_int(row.get("ISS_AGE")),
                raw_data=row
            )
            rates.append(rate)
        return rates
    
    def get_benefit_renewal_rates(self, cov_pha_nbr: int = None) -> List[RenewalBenRateInfo]:
        """Get benefit renewal rate records, optionally filtered by coverage."""
        rates = []
        for row in self.fetch_table("LH_BNF_INS_RNL_RT"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if cov_pha_nbr is not None and phase != cov_pha_nbr:
                continue
            
            rate_type = str(row.get("PRM_RT_TYP_CD", "") or "")
            rate = RenewalBenRateInfo(
                coverage_phase=phase,
                benefit_type=str(row.get("SPM_BNF_TYP_CD", "") or ""),
                benefit_subtype=str(row.get("SPM_BNF_SBY_CD", "") or ""),
                rate_type=rate_type,
                rate_type_desc=translate_renewal_rate_type_code(rate_type),
                joint_indicator=str(row.get("JT_INS_IND", "") or ""),
                rate_class=str(row.get("RT_CLS_CD", "") or ""),
                issue_age=self._parse_optional_int(row.get("ISS_AGE")),
                raw_data=row
            )
            rates.append(rate)
        return rates
    
    @property
    def renewal_cov_count(self) -> int:
        """Count of coverage renewal rate records."""
        return self.data_item_count("LH_COV_INS_RNL_RT")
    
    @property
    def renewal_ben_count(self) -> int:
        """Count of benefit renewal rate records."""
        return self.data_item_count("LH_BNF_INS_RNL_RT")
    
    def cov_renewal_index(self, cov_pha_nbr: int, rate_type: str = "C", joint_ind: str = "0") -> int:
        """Find index of coverage renewal rate record matching criteria (0-based)."""
        for i in range(self.renewal_cov_count):
            if (int(self.data_item("LH_COV_INS_RNL_RT", "COV_PHA_NBR", i) or 0) == cov_pha_nbr and
                str(self.data_item("LH_COV_INS_RNL_RT", "PRM_RT_TYP_CD", i) or "") == rate_type and
                str(self.data_item("LH_COV_INS_RNL_RT", "JT_INS_IND", i) or "") == joint_ind):
                return i
        return -1
    
    def renewal_cov_rateclass(self, index: int) -> str:
        """Get renewal coverage rate class (0-based index)."""
        return str(self.data_item("LH_COV_INS_RNL_RT", "RT_CLS_CD", index) or "")
    
    def renewal_cov_issue_age(self, index: int) -> Optional[int]:
        """Get renewal coverage issue age (0-based index)."""
        val = self.data_item("LH_COV_INS_RNL_RT", "ISS_AGE", index)
        return int(val) if val else None
    
    def ben_renewal_index(self, cov_pha_nbr: int, ben_type: str, ben_subtype: str, 
                          rate_type: str = "C", joint_ind: str = "0") -> int:
        """Find index of benefit renewal rate record matching criteria (0-based)."""
        for i in range(self.renewal_ben_count):
            if (int(self.data_item("LH_BNF_INS_RNL_RT", "COV_PHA_NBR", i) or 0) == cov_pha_nbr and
                str(self.data_item("LH_BNF_INS_RNL_RT", "SPM_BNF_TYP_CD", i) or "") == ben_type and
                str(self.data_item("LH_BNF_INS_RNL_RT", "SPM_BNF_SBY_CD", i) or "") == ben_subtype and
                str(self.data_item("LH_BNF_INS_RNL_RT", "PRM_RT_TYP_CD", i) or "") == rate_type and
                str(self.data_item("LH_BNF_INS_RNL_RT", "JT_INS_IND", i) or "") == joint_ind):
                return i
        return -1
    
    def renewal_ben_rateclass(self, index: int) -> str:
        """Get renewal benefit rate class (0-based index)."""
        return str(self.data_item("LH_BNF_INS_RNL_RT", "RT_CLS_CD", index) or "")
    
    def renewal_ben_issue_age(self, index: int) -> Optional[int]:
        """Get renewal benefit issue age (0-based index)."""
        val = self.data_item("LH_BNF_INS_RNL_RT", "ISS_AGE", index)
        return int(val) if val else None

    def benefit_renewal_rate(self, cov_pha_nbr: int, ben_type: str,
                             ben_subtype: str, rate_type: str = "B") -> Optional[Decimal]:
        """Renewal rate (RNL_RT) for a benefit, from LH_BNF_INS_RNL_RT (Record 67).

        Matches the benefit by coverage phase, type, and subtype, restricted to
        the renewal-premium rate row (PRM_RT_TYP_CD = "B").  The stored RNL_RT is
        scaled, so it is divided by 100,000 to give a per-unit rate.  Returns None
        when no matching row exists for the benefit (rate simply not present).
        """
        for row in self.fetch_table("LH_BNF_INS_RNL_RT"):
            if (int(row.get("COV_PHA_NBR", 0) or 0) == cov_pha_nbr and
                    str(row.get("SPM_BNF_TYP_CD", "") or "").strip() == ben_type and
                    str(row.get("SPM_BNF_SBY_CD", "") or "").strip() == ben_subtype and
                    str(row.get("PRM_RT_TYP_CD", "") or "").strip() == rate_type):
                raw_rate = row.get("RNL_RT")
                if raw_rate is None or str(raw_rate).strip() == "":
                    return None
                try:
                    return Decimal(str(raw_rate)) / 100000
                except Exception:
                    return None
        return None

    # =========================================================================
    # FUND VALUES (LH_POL_FND_VAL_TOT)
    # =========================================================================
    
    def get_fund_values_dict(self) -> Dict[str, Decimal]:
        """
        Get dictionary of current fund values by fund ID.
        Only includes buckets effective on valuation date (MVRY_DT = 12/31/9999).
        """
        fund_values: Dict[str, Decimal] = {}
        
        for row in self.fetch_table("LH_POL_FND_VAL_TOT"):
            mv_date = str(row.get("MVRY_DT", ""))
            # Check if bucket is current (ends on 12/31/9999)
            if "9999" in mv_date:
                fund_id = str(row.get("FND_ID_CD", ""))
                value = Decimal(str(row.get("CSV_AMT", 0) or 0))
                fund_values[fund_id] = fund_values.get(fund_id, Decimal("0")) + value
        
        return fund_values
    
    def get_loan_values_dict(self) -> Dict[str, Decimal]:
        """
        Get dictionary of current loan values by fund ID.
        Only includes buckets effective on valuation date.
        """
        loan_values: Dict[str, Decimal] = {}
        
        for row in self.fetch_table("LH_FND_VAL_LOAN"):
            mv_date = str(row.get("MVRY_DT", ""))
            if "9999" in mv_date:
                fund_id = str(row.get("FND_ID_CD", ""))
                principal = Decimal(str(row.get("LN_PRI_AMT", 0) or 0))
                loan_values[fund_id] = loan_values.get(fund_id, Decimal("0")) + principal
        
        return loan_values
    
    @property
    def total_fund_value(self) -> Decimal:
        """Total of all fund values."""
        return sum(self.get_fund_values_dict().values(), Decimal("0"))
    
    # =========================================================================
    # FUND BUCKETS (LH_POL_FND_VAL_TOT detail)
    # =========================================================================
    
    def get_fund_buckets(self, current_only: bool = True) -> List[FundBucketInfo]:
        """Get fund bucket detail records."""
        buckets = []
        for row in self.fetch_table("LH_POL_FND_VAL_TOT"):
            mv_date_str = str(row.get("MVRY_DT", ""))
            is_current = "9999" in mv_date_str
            
            if current_only and not is_current:
                continue
            
            fund_id = str(row.get("FND_ID_CD", "") or "")
            bucket = FundBucketInfo(
                fund_id=fund_id,
                fund_name=translate_fund_id(fund_id),
                mv_date=self._parse_date(row.get("MVRY_DT")),
                csv_amount=Decimal(str(row["CSV_AMT"])) if row.get("CSV_AMT") else None,
                units=Decimal(str(row["FND_UNT_QTY"])) if row.get("FND_UNT_QTY") else None,
                interest_rate=Decimal(str(row["CRE_ITS_RT"])) if row.get("CRE_ITS_RT") else None,
                start_date=self._parse_date(row.get("BKT_STR_DT")),
                phase=int(row.get("COV_PHA_NBR", 0) or 0),
                is_current=is_current,
                raw_data=row
            )
            buckets.append(bucket)
        return buckets
    
    @property
    def fund_bucket_count(self) -> int:
        """Count of fund bucket records."""
        return self.data_item_count("LH_POL_FND_VAL_TOT")
    
    def fund_bucket_id(self, index: int) -> str:
        """Get fund bucket ID (0-based index)."""
        return str(self.data_item("LH_POL_FND_VAL_TOT", "FND_ID_CD", index) or "")
    
    def fund_bucket_mv_date(self, index: int) -> Optional[date]:
        """Get fund bucket MV date (0-based index)."""
        return self._parse_date(self.data_item("LH_POL_FND_VAL_TOT", "MVRY_DT", index))
    
    def fund_bucket_csv(self, index: int) -> Optional[Decimal]:
        """Get fund bucket CSV amount (0-based index)."""
        val = self.data_item("LH_POL_FND_VAL_TOT", "CSV_AMT", index)
        return Decimal(str(val)) if val else None
    
    def fund_bucket_units(self, index: int) -> Optional[Decimal]:
        """Get fund bucket units (0-based index)."""
        val = self.data_item("LH_POL_FND_VAL_TOT", "FND_UNT_QTY", index)
        return Decimal(str(val)) if val else None
    
    def fund_bucket_interest_rate(self, index: int) -> Optional[Decimal]:
        """Get fund bucket credited interest rate (0-based index)."""
        val = self.data_item("LH_POL_FND_VAL_TOT", "CRE_ITS_RT", index)
        return Decimal(str(val)) if val else None
    
    def fund_bucket_start_date(self, index: int) -> Optional[date]:
        """Get fund bucket start date (0-based index)."""
        return self._parse_date(self.data_item("LH_POL_FND_VAL_TOT", "BKT_STR_DT", index))
    
    def fund_bucket_phase(self, index: int) -> int:
        """Get fund bucket coverage phase (0-based index)."""
        val = self.data_item("LH_POL_FND_VAL_TOT", "COV_PHA_NBR", index)
        return int(val) if val else 0
    
    def fund_bucket_is_current(self, index: int) -> bool:
        """Check if fund bucket is current (MV date contains 9999)."""
        mv_date = str(self.data_item("LH_POL_FND_VAL_TOT", "MVRY_DT", index) or "")
        return "9999" in mv_date

    # =========================================================================
    # PREMIUM ALLOCATION (LH_FND_ALC)
    # =========================================================================
    
    def get_premium_allocation_dict(self) -> Dict[str, Decimal]:
        """
        Get dictionary of current premium allocation percentages by fund ID.
        """
        allocations: Dict[str, Decimal] = {}
        
        # Find the most recent allocation set
        alloc_sets = self.fetch_table("LH_FND_TRS_ALC_SET")
        latest_seq = 0
        
        for row in alloc_sets:
            trs_type = str(row.get("FND_TRS_TYP_CD", ""))
            if trs_type == "P":  # Premium allocation
                seq = int(row.get("FND_ALC_SEQ_NBR", 0) or 0)
                if seq > latest_seq:
                    latest_seq = seq
        
        # Get allocations for that sequence
        for row in self.fetch_table("LH_FND_ALC"):
            alloc_type = str(row.get("FND_ALC_TYP_CD", ""))
            seq_nbr = int(row.get("FND_ALC_SEQ_NBR", 0) or 0)
            
            if alloc_type == "P" and seq_nbr == latest_seq:
                fund_id = str(row.get("FND_ID_CD", ""))
                pct = Decimal(str(row.get("FND_ALC_PCT", 0) or 0))
                allocations[fund_id] = pct
        
        return allocations
    
    # =========================================================================
    # TRANSACTIONS (FH_FIXED)
    # =========================================================================

    PREMIUM_TRANSACTION_CODES = frozenset({"PR", "PI", "PA", "PF", "PT", "PB", "PW"})
    
    def get_transactions(self, limit: int = None) -> List[TransactionInfo]:
        """Get transaction records from FH_FIXED, ordered by date descending."""
        transactions = []
        count = 0
        for row in self.fetch_table("FH_FIXED"):
            if limit and count >= limit:
                break
            
            trans_type = str(row.get("TRN_TYP_CD", "") or "").strip().upper()
            trans_subtype = str(row.get("TRN_SBY_CD", "") or "").strip().upper()
            trans_code = str(row.get("TRANS", "") or "").strip().upper()
            if not trans_code:
                trans_code = trans_type + trans_subtype

            gross_value = row.get("GROSS_AMT")
            if gross_value is None:
                gross_value = row.get("TOT_TRS_AMT")
            net_value = row.get("NET_AMT")
            if net_value is None:
                net_value = row.get("ACC_VAL_GRS_AMT")
            
            trans = TransactionInfo(
                trans_date=self._parse_date(row.get("ASOF_DT")),
                trans_code=trans_code,
                trans_type=trans_type,
                trans_subtype=trans_subtype,
                trans_desc=translate_transaction_code(trans_code),
                gross_amount=Decimal(str(gross_value)) if gross_value is not None else None,
                net_amount=Decimal(str(net_value)) if net_value is not None else None,
                sequence_number=int(row.get("SEQ_NO", 0) or 0),
                fund_id=str(row.get("FND_ID_CD", "") or ""),
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                raw_data=row
            )
            transactions.append(trans)
            count += 1
        return transactions

    def get_premium_transactions(self) -> List[TransactionInfo]:
        """Return unreversed policy premium transactions in issue-date order."""
        transactions = []
        for transaction in self.get_transactions():
            row = transaction.raw_data
            reversed_or_reversal = (
                str(row.get("FCB0_REV_IND", "") or "").strip() == "1"
                or str(row.get("FCB2_REV_APPL_IND", "") or "").strip() == "1"
            )
            if (
                transaction.trans_code in self.PREMIUM_TRANSACTION_CODES
                and not reversed_or_reversal
                and transaction.trans_date is not None
                and transaction.gross_amount is not None
            ):
                transactions.append(transaction)
        return sorted(
            transactions,
            key=lambda transaction: (
                transaction.trans_date,
                transaction.sequence_number,
            ),
        )
    
    @property
    def transaction_count(self) -> int:
        """Count of transaction records."""
        return self.data_item_count("FH_FIXED")
    
    def transaction_date(self, index: int) -> Optional[date]:
        """Get transaction date (0-based index)."""
        return self._parse_date(self.data_item("FH_FIXED", "ASOF_DT", index))
    
    def transaction_code(self, index: int) -> str:
        """Get transaction code (type + subtype) (0-based index)."""
        trans_type = str(self.data_item("FH_FIXED", "TRN_TYP_CD", index) or "")
        trans_subtype = str(self.data_item("FH_FIXED", "TRN_SBY_CD", index) or "")
        return trans_type + trans_subtype
    
    def transaction_type(self, index: int) -> str:
        """Get transaction type code (0-based index)."""
        return str(self.data_item("FH_FIXED", "TRN_TYP_CD", index) or "")
    
    def transaction_subtype(self, index: int) -> str:
        """Get transaction subtype code (0-based index)."""
        return str(self.data_item("FH_FIXED", "TRN_SBY_CD", index) or "")
    
    def transaction_description(self, index: int) -> str:
        """Get transaction description (translated code) (0-based index)."""
        return translate_transaction_code(self.transaction_code(index))
    
    def transaction_gross_amount(self, index: int) -> Optional[Decimal]:
        """Get transaction gross amount (0-based index)."""
        val = self.data_item("FH_FIXED", "TOT_TRS_AMT", index)
        return Decimal(str(val)) if val else None
    
    def transaction_net_amount(self, index: int) -> Optional[Decimal]:
        """Get transaction net amount (0-based index)."""
        val = self.data_item("FH_FIXED", "ACC_VAL_GRS_AMT", index)
        return Decimal(str(val)) if val else None
    
    def transaction_sequence(self, index: int) -> int:
        """Get transaction sequence number (0-based index)."""
        val = self.data_item("FH_FIXED", "SEQ_NO", index)
        return int(val) if val else 0
    
    def transaction_fund_id(self, index: int) -> str:
        """Get transaction fund ID (0-based index)."""
        return str(self.data_item("FH_FIXED", "FND_ID_CD", index) or "")
    
    def transaction_cov_phase(self, index: int) -> int:
        """Get transaction coverage phase (0-based index)."""
        val = self.data_item("FH_FIXED", "COV_PHA_NBR", index)
        return int(val) if val else 0

    # =========================================================================
    # COVERAGE-LEVEL METHODS (from VBA)
    # =========================================================================
    
    def cov_issue_date(self, index: int) -> Optional[date]:
        """Get coverage issue date (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].issue_date
        return None
    
    def cov_maturity_date(self, index: int) -> Optional[date]:
        """Get coverage maturity/expiry date (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].maturity_date
        return None
    
    def cov_amount(self, index: int) -> Optional[Decimal]:
        """Get coverage face amount (units * VPU) (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].face_amount
        return None
    
    def cov_orig_amount(self, index: int) -> Optional[Decimal]:
        """Get coverage original face amount (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].orig_amount
        return None
    
    @property
    def total_specified_amount(self) -> Decimal:
        """Total specified amount across all *active* base coverages.

        Terminated (or otherwise inactive) base coverages no longer contribute
        to the policy's specified amount, so their face is excluded here. This
        matters for band determination: including a terminated base coverage's
        face would over-count the total and can push the policy into a higher
        band than CyberLife (e.g. band 3 vs band 2 across the 250,000 boundary).
        """
        total = Decimal("0")
        for cov in self.get_base_coverages():
            if cov.face_amount and self._coverage_is_active(cov):
                total += cov.face_amount
        return total

    def _base_banding_rider_face(self) -> Decimal:
        """Face of active riders that band as base coverage (see core.band_rules).

        A few riders (e.g. ``1U144A00`` on IUL08 plans) act like a segment of
        base coverage: their face is folded into the base specified amount when
        determining the band. This returns the total such rider face; it is
        added ONLY to the band-determining face, never to the death-benefit
        specified amount.
        """
        from suiteview.core.band_rules import rider_bands_as_base

        total = Decimal("0")
        for cov in self.get_riders():
            if (
                cov.face_amount
                and self._coverage_is_active(cov)
                and rider_bands_as_base(cov.plancode)
            ):
                total += cov.face_amount
        return total

    @property
    def base_band_specified_amount(self) -> Decimal:
        """Specified amount used for BASE band determination.

        Active base coverages plus any rider that bands as base coverage. Kept
        separate from ``total_specified_amount`` (which stays base-only for
        display/export) so the rider quirk only ever moves the band.
        """
        return self.total_specified_amount + self._base_banding_rider_face()
    
    # =========================================================================
    # SUBSTANDARD RATINGS (LH_SST_XTR_CRG and LH_SST_XTR_RNL_RT)
    # =========================================================================
    
    def get_substandard_ratings(self, cov_pha_nbr: int = None) -> List[SubstandardRatingInfo]:
        """Get substandard/flat extra ratings, optionally filtered by coverage."""
        ratings = []
        for row in self.fetch_table("LH_SST_XTR_CRG"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if cov_pha_nbr is not None and phase != cov_pha_nbr:
                continue
            
            type_code = str(row.get("SST_XTR_TYP_CD", "") or "")
            translated_type = translate_substandard_type_code(type_code)
            table_letter = str(row.get("SST_XTR_RT_TBL_CD", "") or "").strip()
            
            rating = SubstandardRatingInfo(
                coverage_phase=phase,
                person_seq=int(row.get("PRS_SEQ_NBR", 0) or 0),
                joint_indicator=str(row.get("JT_INS_IND", "") or ""),
                type_code=translated_type,
                type_desc="Table Rating" if translated_type == "T" else "Flat Extra",
                table_rating=table_letter,
                table_rating_numeric=translate_table_rating(table_letter),
                flat_amount=self._parse_optional_decimal(row.get("XTR_PER_1000_AMT")),
                flat_cease_date=self._parse_date(row.get("SST_XTR_CEA_DT")),
                duration=int(row.get("SST_XTR_CEA_DUR", 0) or 0) or None,
                raw_data=row
            )
            ratings.append(rating)
        return ratings
    
    def cov_table_rating(self, index: int) -> int:
        """Get coverage table rating as number (1-based index). Returns 0 if none."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].table_rating or 0
        return 0
    
    def cov_table_rating_code(self, index: int) -> str:
        """Get coverage table rating letter code (1-based index). Returns '' if none."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].table_rating_code or ""
        return ""

    def cov_table_cease_date(self, index: int) -> Optional[date]:
        """Get coverage table rating cease date (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].table_cease_date
        return None
    
    def cov_flat_extra(self, index: int) -> Optional[Decimal]:
        """Get coverage flat extra amount (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].flat_extra
        return None
    
    def cov_flat_cease_date(self, index: int) -> Optional[date]:
        """Get coverage flat extra cease date (1-based index). Delegates to get_coverages()."""
        covs = self.get_coverages()
        if 0 < index <= len(covs):
            return covs[index - 1].flat_cease_date
        return None
    
    # =========================================================================
    # SKIPPED/REINSTATEMENT PERIODS (LH_COV_SKIPPED_PER)
    # =========================================================================
    
    def get_skipped_periods(self, cov_pha_nbr: int = None) -> List[SkippedPeriodInfo]:
        """Get skipped/reinstatement periods, optionally filtered by coverage."""
        periods = []
        for row in self.fetch_table("LH_COV_SKIPPED_PER"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if cov_pha_nbr is not None and phase != cov_pha_nbr:
                continue
            
            period = SkippedPeriodInfo(
                coverage_phase=phase,
                period_type=str(row.get("SKP_TYP_CD", "") or ""),
                skip_from_date=self._parse_date(row.get("SKP_FRM_DT")),
                skip_to_date=self._parse_date(row.get("SKP_TO_DT")),
                raw_data=row
            )
            periods.append(period)
        return periods
    
    @property
    def skipped_period_count(self) -> int:
        """Count of skipped period records."""
        return self.data_item_count("LH_COV_SKIPPED_PER")
    
    def skipped_from_date(self, index: int) -> Optional[date]:
        """Get skipped period from date (1-based index)."""
        return self._parse_date(self.data_item("LH_COV_SKIPPED_PER", "SKP_FRM_DT", index - 1))
    
    def skipped_to_date(self, index: int) -> Optional[date]:
        """Get skipped period to date (1-based index)."""
        return self._parse_date(self.data_item("LH_COV_SKIPPED_PER", "SKP_TO_DT", index - 1))
    
    def skipped_cov_phase(self, index: int) -> int:
        """Get skipped period coverage phase (1-based index)."""
        val = self.data_item("LH_COV_SKIPPED_PER", "COV_PHA_NBR", index - 1)
        return int(val) if val else 0
    
    # =========================================================================
    # COVERAGE TARGETS (LH_COV_TARGET)
    # =========================================================================
    
    def get_coverage_targets(self, cov_pha_nbr: int = None) -> List[CoverageTargetInfo]:
        """Get coverage-level targets, optionally filtered by coverage."""
        targets = []
        for row in self.fetch_table("LH_COV_TARGET"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if cov_pha_nbr is not None and phase != cov_pha_nbr:
                continue
            
            target_type = str(row.get("TAR_TYP_CD", "") or "")
            target = CoverageTargetInfo(
                coverage_phase=phase,
                target_type=target_type,
                target_type_desc=translate_coverage_target_type(target_type),
                target_amount=Decimal(str(row.get("TAR_PRM_AMT") or row.get("TAR_VAL_AMT") or 0)) or None,
                target_date=self._parse_date(row.get("TAR_DT")),
                raw_data=row
            )
            targets.append(target)
        return targets
    
    @property
    def ccv_target(self) -> Optional[Decimal]:
        """CCV (Coverage Continuation Value) target from LH_COV_TARGET (TAR_TYP_CD = 'CV')."""
        val = self.data_item_where("LH_COV_TARGET", "TAR_VAL_AMT", "TAR_TYP_CD", "CV")
        return Decimal(str(val)) if val else None

    @property
    def shadow_account_value(self) -> Optional[Decimal]:
        """Current shadow account value from segment 58 (premium type XP)."""
        val = self.data_item_where(
            "LH_COV_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", "XP"
        )
        return Decimal(str(val)) if val is not None else None
    
    @property
    def surrender_target(self) -> Optional[Decimal]:
        """Surrender target from LH_COV_TARGET (TAR_TYP_CD = 'SU')."""
        val = self.data_item_where("LH_COV_TARGET", "TAR_VAL_AMT", "TAR_TYP_CD", "SU")
        return Decimal(str(val)) if val else None

    # =========================================================================
    # RATES LOOKUP METHODS (cls_PolicyInformation RATES_xxxx functions)
    # =========================================================================
    
    def _get_rates(self) -> Optional['Rates']:
        """Get or create Rates instance for rate lookups."""
        self._data.reject_uncached_read("Rates lookup during cached rendering")
        if self._rates is None:
            if Rates is not None:
                self._rates = Rates()
        return self._rates
    
    def _translate_sex_for_rates(self, sex_code: str) -> str:
        """Translate sex code for rate lookups (1->M, 2->F)."""
        if sex_code == "1":
            return "M"
        elif sex_code == "2":
            return "F"
        return sex_code
    
    def renewal_cov_sex_code(self, cov_index: int, joint_ind: int = 0) -> str:
        """
        Get sex code for coverage from renewal rates table.
        Uses current rate type "C" by default.
        
        Args:
            cov_index: Coverage index (1-based)
            joint_ind: Joint indicator (0=primary, 1=joint)
            
        Returns:
            Sex code from renewal rates table
        """
        cov_pha_nbr = self._cov_phase_for_index(cov_index)
        if cov_pha_nbr is None:
            return ""
        idx = self.cov_renewal_index(cov_pha_nbr, "C", str(joint_ind))
        if idx >= 0:
            return str(self.data_item("LH_COV_INS_RNL_RT", "RT_SEX_CD", idx) or "")
        return ""
    
    def renewal_cov_rateclass_by_cov(self, cov_index: int, joint_ind: int = 0) -> str:
        """
        Get rate class for coverage from renewal rates table.
        
        Args:
            cov_index: Coverage index (1-based)
            joint_ind: Joint indicator (0=primary, 1=joint)
            
        Returns:
            Rate class code from renewal rates table
        """
        cov_pha_nbr = self._cov_phase_for_index(cov_index)
        if cov_pha_nbr is None:
            return ""
        idx = self.cov_renewal_index(cov_pha_nbr, "C", str(joint_ind))
        if idx >= 0:
            return str(self.data_item("LH_COV_INS_RNL_RT", "RT_CLS_CD", idx) or "")
        return ""
    
    def _cov_phase_for_index(self, cov_index: int) -> Optional[int]:
        """Map a 1-based coverage index to its real COV_PHA_NBR.

        Coverage phases are NOT guaranteed to be 1..N contiguous — terminated
        coverages and interleaved riders leave gaps (e.g. 1, 5, 6, 7, 10, ...).
        The renewal-rate lookup (cov_renewal_index) matches on the real
        COV_PHA_NBR, so callers that pass a 1-based index must be translated
        here first. (Passing the index straight through silently matched the
        wrong renewal row — or none — yielding blank/wrong sex & rate class,
        and in turn empty/wrong COI/EPU/SCR schedules for increase coverages.)
        """
        covs = self.get_coverages()
        if not (0 < cov_index <= len(covs)):
            return None
        return covs[cov_index - 1].cov_pha_nbr
    
    def cov_mtp_band(self, cov_pha_nbr: int) -> int:
        """Stored MTP band by phase, RERUN's BandAtIssue (not current face).

        Segment 02/67 mappings verify BAN_STRUCTURE_CD and RT_BAN_CD.
        ExecuLife structure 6 orders X/Y before A; other structures start at A.
        """
        coverage_rows = [
            row for row in self.fetch_table("LH_COV_PHA")
            if int(row["COV_PHA_NBR"]) == cov_pha_nbr
        ]
        if len(coverage_rows) != 1:
            raise ValueError(f"Coverage {cov_pha_nbr}: missing or ambiguous band structure")
        raw_structure = coverage_rows[0]["BAN_STRUCTURE_CD"]
        if raw_structure is None:
            raise ValueError(f"Coverage {cov_pha_nbr}: NULL band structure")
        structure = str(raw_structure).strip()
        if structure in ("", "00", "0"):
            return 0
        codes = {
            str(row["RT_BAN_CD"] or "").strip()
            for row in self.fetch_table("LH_COV_INS_RNL_RT")
            if int(row["COV_PHA_NBR"]) == cov_pha_nbr
            and str(row["PRM_RT_TYP_CD"]).strip() == "M"
            and str(row["JT_INS_IND"]).strip() == "0"
        }
        alphabet = "XYABCDEFGHIJK" if structure in ("6", "06") else "ABCDEFGHIJK"
        if len(codes) != 1:
            raise ValueError(f"Coverage {cov_pha_nbr}: missing or ambiguous stored MTP band")
        code = codes.pop()
        if len(code) != 1 or code not in alphabet:
            raise ValueError(f"Coverage {cov_pha_nbr}: invalid stored MTP band {code!r}")
        return alphabet.index(code) + 1

    def cov_band(self, cov_index: int) -> Optional[int]:
        """
        Get face amount band for coverage.

        Base coverage bands are based on the total face amount across base
        coverages. Rider coverage bands are based only on that rider's face
        amount.
        
        Args:
            cov_index: Coverage index (1-based)
            
        Returns:
            Band number or None if not determinable
        """
        if cov_index in self._band_cache:
            return self._band_cache[cov_index]
        
        rates = self._get_rates()
        if rates is None:
            self._band_cache[cov_index] = None
            return None

        covs = self.get_coverages()
        if not (0 < cov_index <= len(covs)):
            self._band_cache[cov_index] = None
            return None

        cov = covs[cov_index - 1]
        from suiteview.core.band_rules import rider_bands_as_base

        cov_plancode = self.cov_plancode(cov_index)
        # A base-banding rider (e.g. 1U144A00) acts like a segment of base
        # coverage: it is banded on the BASE plancode's band table using the
        # combined base specified amount — the same band as the policy.
        bands_as_base = cov.is_base or rider_bands_as_base(cov_plancode)
        if bands_as_base:
            band_face = float(self.base_band_specified_amount)
            band_plancode = self.base_plancode if not cov.is_base else cov_plancode
        else:
            band_face = float(cov.face_amount or 0)
            band_plancode = cov_plancode

        # Base coverages (and base-banding riders) pass the policy issue date for
        # the Rates_Control-CZ issue-date band boundary (see Rates.get_band); the
        # rule never applies to ordinary rider band tables, so they stay dateless.
        band = rates.get_band(
            band_plancode, band_face,
            issue_date=self.issue_date if bands_as_base else None,
        )
        self._band_cache[cov_index] = band
        return band
    
    def rates_coi(self, cov_index: int, scale: int = 1) -> Optional[List[float]]:
        """
        Get COI rates for coverage.
        
        Args:
            cov_index: Coverage index (1-based)
            scale: Rate scale (default 1)
            
        Returns:
            List of COI rates by duration (1-indexed) or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(cov_index)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)
        
        return rates.get_coi(
            plancode=self.cov_plancode(cov_index),
            issue_age=self.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            scale=scale,
            band=band
        )
    
    def rates_mtp(self, cov_index: int) -> Optional[float]:
        """
        Get Maximum Target Premium for coverage.
        
        Args:
            cov_index: Coverage index (1-based)
            
        Returns:
            MTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(cov_index)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)
        
        result = rates.get_mtp(
            plancode=self.cov_plancode(cov_index),
            issue_age=self.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            band=band
        )
        return result if result else "NA"
    
    def rates_ctp(self, cov_index: int) -> Optional[float]:
        """
        Get Commission Target Premium for coverage.
        
        Args:
            cov_index: Coverage index (1-based)
            
        Returns:
            CTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(cov_index)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)
        
        result = rates.get_ctp(
            plancode=self.cov_plancode(cov_index),
            issue_age=self.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            band=band
        )
        return result if result else "NA"
    
    def rates_tbl1_mtp(self, cov_index: int) -> Optional[float]:
        """
        Get Table 1 Maximum Target Premium for coverage.
        
        Args:
            cov_index: Coverage index (1-based)
            
        Returns:
            TBL1MTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(cov_index)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)
        
        result = rates.get_tbl1_mtp(
            plancode=self.cov_plancode(cov_index),
            issue_age=self.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            band=band
        )
        return result if result else "NA"
    
    def rates_tbl1_ctp(self, cov_index: int) -> Optional[float]:
        """
        Get Table 1 Commission Target Premium for coverage.
        
        Args:
            cov_index: Coverage index (1-based)
            
        Returns:
            TBL1CTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(cov_index)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)
        
        result = rates.get_tbl1_ctp(
            plancode=self.cov_plancode(cov_index),
            issue_age=self.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            band=band
        )
        return result if result else "NA"
    
    def rates_epu(self, cov_index: int, scale: int = 1) -> Optional[List[float]]:
        """
        Get Extended Paid-Up rates for coverage.
        
        Args:
            cov_index: Coverage index (1-based)
            scale: Rate scale (default 1)
            
        Returns:
            List of EPU rates by duration (1-indexed) or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(cov_index)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)
        
        return rates.get_epu(
            plancode=self.cov_plancode(cov_index),
            issue_age=self.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            scale=scale,
            band=band
        )
    
    def rates_scr(self, cov_index: int, scale: int = 1) -> Optional[List[float]]:
        """
        Get Surrender Charge rates for coverage.
        
        Args:
            cov_index: Coverage index (1-based)
            scale: Rate scale (default 1)
            
        Returns:
            List of SCR rates by duration (1-indexed) or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(cov_index)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(cov_index)
        sex = self._translate_sex_for_rates(sex_code)
        
        return rates.get_scr(
            plancode=self.cov_plancode(cov_index),
            issue_age=self.cov_issue_age(cov_index),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(cov_index),
            band=band,
            state=self.issue_state
        )
    
    def rates_corr(self) -> Optional[List[float]]:
        """
        Get Corridor rates for base coverage.
        
        Returns:
            List of corridor rates by attained age or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        return rates.get_corr(
            plancode=self.cov_plancode(1),
            issue_age=self.cov_issue_age(1)
        )
    
    def rates_gint(self) -> Optional[List[float]]:
        """
        Get Guaranteed Interest rates for base coverage.
        
        Returns:
            List of GINT rates by duration or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        return rates.get_gint(plancode=self.cov_plancode(1))
    
    def rates_epp(self, scale: int) -> Optional[List[float]]:
        """
        Get Expense Per Premium rates for base coverage.
        
        Args:
            scale: Rate scale
            
        Returns:
            List of EPP rates by duration or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(1)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)
        
        return rates.get_epp(
            plancode=self.cov_plancode(1),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            scale=scale,
            band=band
        )
    
    def rates_tpp(self, scale: int) -> Optional[List[float]]:
        """
        Get Target Premium Percent rates for base coverage.
        
        Args:
            scale: Rate scale
            
        Returns:
            List of TPP rates by duration or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(1)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)
        
        return rates.get_tpp(
            plancode=self.cov_plancode(1),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            scale=scale,
            band=band
        )
    
    def rates_mfee(self, scale: int) -> Optional[List[float]]:
        """
        Get Monthly Fee rates for base coverage.
        
        Args:
            scale: Rate scale
            
        Returns:
            List of MFEE rates by duration or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(1)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)
        
        return rates.get_mfee(
            plancode=self.cov_plancode(1),
            issue_age=self.cov_issue_age(1),
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            scale=scale,
            band=band
        )
    
    def rates_ben_coi(self, ben_index: int, scale: int = 1) -> Optional[List[float]]:
        """
        Get Benefit COI rates.
        
        Args:
            ben_index: Benefit index (1-based)
            scale: Rate scale (default 1)
            
        Returns:
            List of BENCOI rates by duration or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(1)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)
        
        benefits = self.get_benefits()
        if ben_index < 1 or ben_index > len(benefits):
            return None
        ben = benefits[ben_index - 1]
        
        return rates.get_ben_coi(
            plancode=self.cov_plancode(1),
            issue_age=ben.issue_age,
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            scale=scale,
            band=band,
            benefit_type=ben.benefit_code
        )
    
    def rates_ben_ctp(self, ben_index: int) -> Optional[float]:
        """
        Get Benefit Commission Target Premium.
        
        Args:
            ben_index: Benefit index (1-based)
            
        Returns:
            BENCTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(1)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)
        
        benefits = self.get_benefits()
        if ben_index < 1 or ben_index > len(benefits):
            return None
        ben = benefits[ben_index - 1]
        
        result = rates.get_ben_ctp(
            plancode=self.cov_plancode(1),
            issue_age=ben.issue_age,
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            band=band,
            benefit_type=ben.benefit_code
        )
        return result if result else None
    
    def rates_ben_mtp(self, ben_index: int) -> Optional[float]:
        """
        Get Benefit Maximum Target Premium.
        
        Args:
            ben_index: Benefit index (1-based)
            
        Returns:
            BENMTP rate or None
        """
        rates = self._get_rates()
        if rates is None:
            return None
        
        band = self.cov_band(1)
        if band is None:
            return None
        
        sex_code = self.renewal_cov_sex_code(1)
        sex = self._translate_sex_for_rates(sex_code)
        
        benefits = self.get_benefits()
        if ben_index < 1 or ben_index > len(benefits):
            return None
        ben = benefits[ben_index - 1]
        
        result = rates.get_ben_mtp(
            plancode=self.cov_plancode(1),
            issue_age=ben.issue_age,
            sex=sex,
            rateclass=self.renewal_cov_rateclass_by_cov(1),
            band=band,
            benefit_type=ben.benefit_code
        )
        return result if result else None

    # =========================================================================
    # RATE MATRIX BUILDERS (for UI display - mirrors VBA LoadUL*RatesToRecordset)
    # =========================================================================

    def cov_cash_value_key(self, cov_index: int) -> str:
        """CVF class/base/sub key from the coverage's valuation codes (1-based)."""
        if not 1 <= cov_index <= self.coverage_count:
            raise ValueError(f"Coverage index {cov_index} is out of range.")
        parts = []
        for column, width in (
            ("INS_CLS_CD", 1), ("PLN_BSE_SRE_CD", 3), ("LIF_PLN_SUB_SRE_CD", 2),
        ):
            value = self.data_item("LH_COV_PHA", column, cov_index - 1)
            if value is None:
                raise ValueError(f"Coverage {cov_index} is missing {column} for its CVF key.")
            text = str(value).strip().upper()
            if len(text) > width or (not text and column != "LIF_PLN_SUB_SRE_CD"):
                raise ValueError(f"Coverage {cov_index} has an invalid {column} for its CVF key.")
            parts.append(text.ljust(width))
        return "".join(parts)

    @property
    def cyberlife_rate_user_code(self) -> str:
        """CyberLife rate-file user for source-keyed WL/ISWL rates (01 -> 00)."""
        from suiteview.core.rates import cyberlife_rate_user
        return cyberlife_rate_user(self.company_code)

    @property
    def has_fixed_premium_rates(self) -> bool:
        """ISWL or traditional WL: IAF premiums, CVF cash values and mode factors apply."""
        product = self.product_type
        return product == "ISWL" or (not self.is_advanced_product and product == "WL")

    def cov_rate_sex_code(self, cov_index: int) -> str:
        """CyberLife sex code (1/2/3) for rate keys: the 67 segment, else LH_COV_PHA."""
        code = self.renewal_cov_sex_code(cov_index)
        if not code:
            code = str(self.data_item("LH_COV_PHA", "INS_SEX_CD", cov_index - 1) or "")
        return code.strip()

    def rates_wl_cv(self, cov_index: int, user_defined: str = "") -> Dict[int, Decimal]:
        """Whole Life cash values by actual source duration, not a one-based array."""
        key = self.cov_cash_value_key(cov_index)
        age = self.cov_issue_age(cov_index)
        if age is None:
            raise ValueError(f"Coverage {cov_index} is missing its cash-value issue age.")
        rates = self._get_rates()
        if rates is None:
            raise RuntimeError("The shared rates service is not available.")
        return rates.get_wl_cash_values(self.cyberlife_rate_user_code, key, age, user_defined)

    def rates_wl_premium(self, plancode: str, issue_age: int, issue_date: Optional[date]) -> Dict[str, Any]:
        """IAF premium cells (WL_RATE_PREM) for a plancode at an issue age."""
        rates = self._get_rates()
        if rates is None:
            raise RuntimeError("The shared rates service is not available.")
        return rates.get_wl_premium_rates(self.cyberlife_rate_user_code, plancode, issue_age, issue_date)

    def rates_modal_factors(self) -> Dict[str, Any]:
        """Base plan mode factors and policy fee (POINT_MODEFACT -> RATE_MODEFACT)."""
        rates = self._get_rates()
        if rates is None:
            raise RuntimeError("The shared rates service is not available.")
        return rates.get_modal_factors(self.cov_plancode(1))

    def build_premium_rate_matrix(self, cov_index: int) -> List[List]:
        """IAF base and benefit premium rates for a fixed-premium coverage."""
        from .fixed_premium_rates import build_premium_rate_matrix
        return build_premium_rate_matrix(self, cov_index)

    def build_modal_premium_matrix(self) -> List[List]:
        """Modal premium from IAF rates and RATE_MODEFACT, beside POL_PRM_AMT."""
        from .fixed_premium_rates import build_modal_premium_matrix
        return build_modal_premium_matrix(self)

    # CyberLife keeps a short per-unit value window on the 02 segment. Each
    # value applies at policy duration LOW_DUR_PER + offset.
    _CV_RATE_COLUMNS = (
        "LOW_DUR_CSV_AMT", "LOW_DUR_1_CSV_AMT", "LOW_DUR_2_CSV_AMT", "LOW_DUR_3_CSV_AMT",
    )
    _NSP_RATE_COLUMNS = ("LOW_DUR_NSP_AMT", "LOW_DUR_1_NSP_AMT", "LOW_DUR_2_NSP_AMT")
    _NONFORFEITURE_STATUS = {"44": "ETI", "45": "RPU"}

    def cov_cash_value_rates(self, cov_index: int) -> Dict[str, Any]:
        """Stored 02-segment cash value rates in play for a coverage (1-based).

        Uses the CV rates when present; otherwise the NSP rates, which CyberLife
        carries for nonforfeiture (ETI/RPU) and paid-up coverages. Rates are per
        coverage unit, keyed by the policy duration where each value applies.
        """
        if not 1 <= cov_index <= self.coverage_count:
            raise ValueError(f"Coverage index {cov_index} is out of range.")
        idx = cov_index - 1

        def values(columns):
            return [self._parse_optional_decimal(self.data_item("LH_COV_PHA", c, idx))
                    for c in columns]

        cv = values(self._CV_RATE_COLUMNS)
        nsp = values(self._NSP_RATE_COLUMNS)
        if any(v for v in cv):
            basis, rates = "CV", cv
        elif any(v for v in nsp):
            basis, rates = "NSP", nsp
        else:
            basis, rates = None, []

        low_duration = self._parse_optional_int(self.data_item("LH_COV_PHA", "LOW_DUR_PER", idx))
        schedule: Dict[int, Decimal] = {}
        if basis and low_duration is not None:
            schedule = {low_duration + k: v for k, v in enumerate(rates) if v is not None}

        return {
            "cov_index": cov_index,
            "cov_pha_nbr": self._parse_optional_int(self.data_item("LH_COV_PHA", "COV_PHA_NBR", idx)),
            "basis": basis,
            "nonforfeiture": self._NONFORFEITURE_STATUS.get(self.premium_pay_status_code, ""),
            "low_duration": low_duration,
            "rates": schedule,
            "units": self._parse_optional_decimal(self.data_item("LH_COV_PHA", "COV_UNT_QTY", idx)),
            "vpu": self._parse_optional_decimal(self.data_item("LH_COV_PHA", "COV_VPU_AMT", idx)),
        }

    def _guaranteed_cash_value_date(self) -> Optional[date]:
        """Last processed monthliversary; the stored monthly value date can be
        stale for advanced policies on nonforfeiture."""
        from dateutil.relativedelta import relativedelta

        candidates = []
        next_mv = self.next_monthliversary_date
        if next_mv and next_mv.year < 9999:
            candidates.append(next_mv - relativedelta(months=1))
        if self.valuation_date:
            candidates.append(self.valuation_date)
        return max(candidates) if candidates else None

    def guaranteed_cash_value(self, as_of: Optional[date] = None) -> Dict[str, Any]:
        """Interpolated guaranteed cash value from the stored 02-segment rates.

        For each active coverage with stored CV (or nonforfeiture NSP) rates:
        units x (BOY rate x months remaining + EOY rate x months elapsed) / 12,
        where BOY/EOY are the rates at the completed policy duration and the next
        one, and months are completed months since the anniversary on or before
        ``as_of`` (default: the last processed monthliversary). Coverages that are
        not active are excluded; if any active coverage with stored rates cannot
        be valued, ``value`` is None with a ``reason`` rather than a partial total.
        """
        from dateutil.relativedelta import relativedelta

        as_of = as_of or self._guaranteed_cash_value_date()
        result: Dict[str, Any] = {"value": None, "as_of": as_of, "details": [], "reason": ""}
        if as_of is None:
            result["reason"] = "No valuation date"
            return result
        coverages = {cov.cov_pha_nbr: cov for cov in self.get_coverages()}
        total = Decimal("0")
        excluded, blockers = [], []
        for cov_index in range(1, self.coverage_count + 1):
            info = self.cov_cash_value_rates(cov_index)
            if not info["basis"]:
                continue
            label = f"Cov {info['cov_pha_nbr'] or cov_index}"
            cov = coverages.get(info["cov_pha_nbr"])
            if cov is None:
                blockers.append(f"{label}: coverage record unavailable")
                continue
            if not self._coverage_is_active(cov, as_of):
                excluded.append(f"{label}: coverage not active")
                continue
            issue = cov.issue_date
            if issue is None or info["units"] is None:
                blockers.append(f"{label}: missing issue date or units")
                continue
            if as_of < issue:
                blockers.append(f"{label}: as-of date precedes issue date")
                continue
            duration = self._completed_date_parts_years(issue, as_of)
            anniversary = issue + relativedelta(years=duration)
            # Monthliversaries clamp to month end (issue on the 31st -> Feb 28).
            months = 0
            while months < 12 and anniversary + relativedelta(months=months + 1) <= as_of:
                months += 1
            boy = info["rates"].get(duration)
            eoy = info["rates"].get(duration + 1)
            if boy is None or eoy is None:
                available = sorted(info["rates"])
                span = f"{available[0]}-{available[-1]}" if available else "none"
                blockers.append(
                    f"{label}: stored {info['basis']} rates cover durations "
                    f"{span}, not {duration}-{duration + 1}"
                )
                continue
            value = (info["units"] * (boy * (12 - months) + eoy * months) / 12).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            total += value
            result["details"].append({
                "cov_index": cov_index, "cov_pha_nbr": info["cov_pha_nbr"],
                "basis": info["basis"], "nonforfeiture": info["nonforfeiture"],
                "duration": duration, "months": months, "boy_rate": boy, "eoy_rate": eoy,
                "units": info["units"], "value": value,
            })
        if result["details"] and not blockers:
            result["value"] = total
        reasons = blockers + excluded
        if not reasons and not result["details"]:
            reasons.append("No stored cash value or NSP rates")
        result["reason"] = "; ".join(reasons)
        return result

    def _stored_cv_check(self, cov_index: int, cash_values: Dict[int, Decimal]) -> str:
        """Compare the 02 segment's stored LOW_DUR CV window with the CVF schedule."""
        stored = self.cov_cash_value_rates(cov_index)
        if stored["basis"] != "CV" or not stored["rates"]:
            return f"Stored rates are {stored['basis']} (not compared)" if stored["basis"] else "None stored"
        durations = sorted(stored["rates"])
        differences = [
            f"dur {d}: {stored['rates'][d]} vs {cash_values.get(d, 'none')}"
            for d in durations if cash_values.get(d) != stored["rates"][d]
        ]
        span = f"Durations {durations[0]}-{durations[-1]}"
        return f"{span} match" if not differences else "Differs: " + "; ".join(differences)

    def build_whole_life_coverage_rate_matrix(self, cov_index: int) -> Optional[List[List]]:
        """Source-keyed WL rates; other WL rate families can add independent schedules."""
        from dateutil.relativedelta import relativedelta

        cash_values = self.rates_wl_cv(cov_index)
        if not cash_values:
            return None
        issue_date = self.cov_issue_date(cov_index)
        issue_age = self.cov_issue_age(cov_index)
        coverage = self.get_coverages()[cov_index - 1]
        metadata = [
            ("Policy", self.policy_number), ("Company", self.company_code),
            ("Rate User", self.cyberlife_rate_user_code),
            ("Cov Index", cov_index), ("Plancode", coverage.plancode),
            ("Rate Key", self.cov_cash_value_key(cov_index)),
            ("User Defined", "(blank)"), ("Issue Age", issue_age),
            ("CV Basis", "Per coverage unit"),
            ("Value per Unit", coverage.vpu if coverage.vpu is not None else "Unknown"),
            ("Source", "WL_RATE_CV"), ("02 Stored CV", self._stored_cv_check(cov_index, cash_values)),
            ("NSP / PUI / Div", "Not yet available"),
        ]
        matrix = [["RateFields", "RateInfo", "Date", "Age", "Duration", "CV"]]
        schedule = sorted(cash_values.items())
        for row in range(max(len(metadata), len(schedule))):
            fields = list(metadata[row]) if row < len(metadata) else ["", ""]
            if row < len(schedule):
                duration, value = schedule[row]
                anniversary = issue_date + relativedelta(years=duration) if issue_date else None
                fields.extend([
                    anniversary.strftime("%m/%d/%Y") if anniversary else "",
                    issue_age + duration, duration, value,
                ])
            else:
                fields.extend(["", "", "", ""])
            matrix.append(fields)
        return matrix

    def build_coverage_rate_matrix(self, cov_index: int, scale: int = 1) -> Optional[List[List]]:
        """
        Build Whole Life cash values or the existing UL coverage-rate matrix.
        
        Returns a 2D list where:
          - Row 0 = column headers (RateFields, RateInfo, Date, Age, Year, COI, EPU, SCR, GuarCOI, GuarEPU)
          - Rows 1..N = data rows by policy year
          - RateFields/RateInfo columns contain metadata in early rows and blanks in data rows
          
        Args:
            cov_index: Coverage index (1-based)
            scale: Rate scale (default 1)
            
        Returns:
            2D list suitable for table display, or None if rates unavailable
        """
        if not self.is_advanced_product and self.product_type == "WL":
            return self.build_whole_life_coverage_rate_matrix(cov_index)

        from dateutil.relativedelta import relativedelta
        
        issue_date = self.cov_issue_date(cov_index)
        maturity_date = self.cov_maturity_date(cov_index)
        issue_age = self.cov_issue_age(cov_index)
        
        if issue_date is None or issue_age is None:
            return None
        
        # Calculate max years from issue to maturity
        if maturity_date and maturity_date > issue_date:
            xmax = (maturity_date.year - issue_date.year)
        else:
            xmax = 100 - issue_age  # fallback
        
        # Get single-value rates
        mtp = self.rates_mtp(cov_index)
        ctp = self.rates_ctp(cov_index)
        tbl1_mtp = self.rates_tbl1_mtp(cov_index)
        tbl1_ctp = self.rates_tbl1_ctp(cov_index)
        
        # Get rate arrays
        coi = self.rates_coi(cov_index, scale)
        epu = self.rates_epu(cov_index, scale)
        scr = self.rates_scr(cov_index, scale)
        guar_coi = self.rates_coi(cov_index, 0)  # Guaranteed (scale=0)
        guar_epu = self.rates_epu(cov_index, 0)  # Guaranteed (scale=0)
        
        # Calculate flat duration
        flat_extra = self.cov_flat_extra(cov_index)
        flat_duration = 0
        if flat_extra and float(flat_extra) > 0:
            flat_cease = self.cov_flat_cease_date(cov_index)
            if flat_cease and issue_date:
                flat_duration = flat_cease.year - issue_date.year
        
        # Get sex code for display (M/F)
        sex_code = self.renewal_cov_sex_code(cov_index)
        sex_display = self._translate_sex_for_rates(sex_code)
        
        # Get band
        band = self.cov_band(cov_index)
        band_display = band if band is not None else "Not Found"
        
        # Build metadata columns
        rate_fields = [
            " ", "Policy", "Cov Index", "Plancode", "IssueDate", "IssueAge",
            "Sex", "Rateclass", "Amount", "OrigAmount", "Band", "Table",
            "Flat", "Flat Duration", " ", "MTP", "CTP", "TBL1MTP", "TBL1CTP",
            " ", "Substandard is not", "included in rates"
        ]
        
        rate_info = [
            " ", self.policy_number, cov_index, self.cov_plancode(cov_index),
            issue_date.strftime("%Y-%m-%d") if issue_date else "",
            issue_age, sex_display,
            self.renewal_cov_rateclass_by_cov(cov_index),
            self._whole_dollars(self.cov_amount(cov_index) or None),
            self._whole_dollars(self.cov_orig_amount(cov_index) or None),
            band_display, self.cov_table_rating(cov_index),
            str(flat_extra or 0), flat_duration,
            " ", mtp, ctp, tbl1_mtp, tbl1_ctp,
            " ", " ", " "
        ]
        
        # Ensure metadata lists are same length
        extra_columns: Dict[str, Optional[list]] = {}
        if self.product_type == "ISWL":
            iswl_meta, extra_columns = self._iswl_coverage_rate_extras(cov_index)
            rate_fields += [name for name, _ in iswl_meta]
            rate_info += [value for _, value in iswl_meta]
        max_meta = max(len(rate_fields), len(rate_info))
        xmax = max(xmax, max_meta)
        
        # Build the matrix
        columns = ["RateFields", "RateInfo", "Date", "Age", "Year", "COI", "EPU", "SCR", "GuarCOI", "GuarEPU"]
        matrix = [columns + list(extra_columns)]  # Row 0 = headers
        
        for row in range(1, xmax + 1):
            row_data = []
            for col_idx, col_name in enumerate(columns):
                if col_name == "RateFields":
                    row_data.append(rate_fields[row] if row < len(rate_fields) else "")
                elif col_name == "RateInfo":
                    row_data.append(rate_info[row] if row < len(rate_info) else "")
                elif col_name == "Date":
                    try:
                        dt = issue_date + relativedelta(years=row - 1)
                        row_data.append(dt.strftime("%m/%d/%Y"))
                    except Exception:
                        row_data.append("")
                elif col_name == "Age":
                    row_data.append(issue_age + row - 1)
                elif col_name == "Year":
                    row_data.append(row)
                elif col_name == "COI":
                    if coi and row < len(coi):
                        row_data.append(coi[row])
                    else:
                        row_data.append("NA" if coi is None else "")
                elif col_name == "EPU":
                    if epu and row < len(epu):
                        row_data.append(epu[row])
                    else:
                        row_data.append("NA" if epu is None else "")
                elif col_name == "SCR":
                    if scr and row < len(scr):
                        row_data.append(scr[row])
                    else:
                        row_data.append("NA" if scr is None else "")
                elif col_name == "GuarCOI":
                    if guar_coi and row < len(guar_coi):
                        row_data.append(guar_coi[row])
                    else:
                        row_data.append("NA" if guar_coi is None else "")
                elif col_name == "GuarEPU":
                    if guar_epu and row < len(guar_epu):
                        row_data.append(guar_epu[row])
                    else:
                        row_data.append("NA" if guar_epu is None else "")
            for values in extra_columns.values():
                if values and row < len(values):
                    row_data.append(values[row])
                else:
                    row_data.append("NA" if values is None else "")
            matrix.append(row_data)
        
        return matrix

    @staticmethod
    def _whole_dollars(amount) -> str:
        """Face amount for the rates grid: commas, no decimals; blank if unknown."""
        if amount is None or amount == "":
            return ""
        return f"{Decimal(str(amount)).quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}"

    def _iswl_coverage_rate_extras(self, cov_index: int) -> Tuple[List[tuple], Dict[str, Optional[list]]]:
        """ISWL plan rates beside the UL view: GINT, CVR, premium, cease ages, loans.

        COI stays the current scale (1) only; older SCALE_COI windows are not shown.
        """
        rates = self._get_rates()
        if rates is None:
            raise RuntimeError("The shared rates service is not available.")
        plancode = self.cov_plancode(cov_index)
        calendar = sorted(
            ((row[0].date() if hasattr(row[0], "date") else row[0], int(row[1]))
             for row in (rates.get_rates("COI_SCALE", plancode) or [])),
            key=lambda entry: entry[0],
        )
        current = next((start for start, scale in calendar if scale == 1), None)
        ages = rates.get_age_limits(plancode)
        meta: List[tuple] = [
            (" ", " "),
            ("COI", f"Scale 1 (current from {current:%Y-%m-%d})" if current else "Scale 1 (current)"),
            ("GuarCOI", "Scale 0"),
            ("Prem Cease Age", ages["premium_cease"] if ages["premium_cease"] is not None else "Not loaded"),
            ("Ben Cease Age", ages["benefit_cease"] if ages["benefit_cease"] is not None else "Not loaded"),
        ]
        extra: Dict[str, Optional[list]] = {}
        extra["GINT"] = rates.get_gint(plancode)
        cvr_meta, extra["CVR"] = self._iswl_cash_value_column(cov_index)
        prem_meta, extra["Prem Rate"] = self._iswl_premium_rate_column(cov_index)
        meta += [(" ", " "), cvr_meta, prem_meta, (" ", " "), ("Loan rates", "RATE_LOAN")]
        for rate_type in ("PLNCRG", "PLNCRD", "RLNCRG", "RLNCRD"):
            values = rates.get_rates(rate_type, plancode)
            rate = values[1] if values and len(values) > 1 else None
            meta.append((f"  {rate_type}", f"{rate:g}%" if rate is not None else "Not loaded"))
        meta += [(" ", " "), ("Rider premiums", "See Fixed Premium")]
        return meta, extra

    def _iswl_cash_value_column(self, cov_index: int) -> Tuple[tuple, Optional[list]]:
        """Per-unit CVF value at each row's Date: Year n is duration n - 1."""
        if self.premium_pay_status_code.strip() in ("44", "45"):
            return ("CVR", "Not available on ETI/RPU"), None
        try:
            values = self.rates_wl_cv(cov_index)
        except (RatesError, ValueError) as exc:
            return ("CVR", f"Error: {exc}"), None
        if not values:
            return ("CVR", f"Not loaded (WL_RATE_CV {self.cov_cash_value_key(cov_index)})"), None
        last = max(values)
        column = [None] + [values.get(year - 1, "") for year in range(1, last + 2)]
        return ("CVR", f"WL_RATE_CV {self.cov_cash_value_key(cov_index)} at Date"), column

    def _iswl_premium_rate_column(self, cov_index: int) -> Tuple[tuple, Optional[list]]:
        """Annual base premium per unit (WL_RATE_PREM type N) through the pay age."""
        from .fixed_premium_rates import _rate, premium_items

        try:
            base = premium_items(self, cov_index)[0]
        except (RatesError, ValueError) as exc:
            return ("Prem Rate", f"Error: {exc}"), None
        row = base.rate_row
        if row is None:
            return ("Prem Rate", base.reason), None
        pay_age, pay_use = row.get("PAY_AGE"), row.get("PAY_AGE_USE")
        issue_age = self.cov_issue_age(cov_index)
        if pay_age is None or pay_use not in (0, 1) or issue_age is None:
            return ("Prem Rate", f"Pay age {pay_age} (use {pay_use}) is not verified"), None
        years = pay_age - issue_age if pay_use == 1 else pay_age
        rate = _rate(row["RATE"])
        column = [None] + [rate] * max(years, 0)
        return ("Prem Rate", f"WL_RATE_PREM ** to {'age' if pay_use == 1 else 'year'} {pay_age}"), column

    def build_benefit_rate_matrix(self, ben_index: int, scale: int = 1) -> Optional[List[List]]:
        """
        Build rate matrix for a benefit, matching VBA LoadULBenefitRatesToRecordset.
        
        Returns a 2D list where:
          - Row 0 = column headers (RateFields, RateInfo, Date, Age, Year, COI)
          - Rows 1..N = data rows by policy year
          
        Args:
            ben_index: Benefit index (1-based)
            scale: Rate scale (default 1)
            
        Returns:
            2D list suitable for table display, or None if rates unavailable
        """
        from dateutil.relativedelta import relativedelta
        
        # Benefits use Cov 1 for many params
        issue_date_cov1 = self.cov_issue_date(1)
        maturity_date_cov1 = self.cov_maturity_date(1)
        
        benefits = self.get_benefits()
        if ben_index < 1 or ben_index > len(benefits):
            return None
        ben = benefits[ben_index - 1]
        ben_iss_age = ben.issue_age
        ben_iss_date = ben.issue_date
        
        if issue_date_cov1 is None or ben_iss_age is None:
            return None
        
        # xmax based on cov 1 dates
        if maturity_date_cov1 and maturity_date_cov1 > issue_date_cov1:
            xmax = (maturity_date_cov1.year - issue_date_cov1.year)
        else:
            xmax = 100 - (self.cov_issue_age(1) or 30)
        
        # Get single-value rates
        mtp = self.rates_ben_mtp(ben_index)
        ctp = self.rates_ben_ctp(ben_index)
        
        # Get rate array
        ben_coi = self.rates_ben_coi(ben_index, scale)
        
        # Get sex/rateclass/band from Cov 1
        sex_code = self.renewal_cov_sex_code(1)
        sex_display = self._translate_sex_for_rates(sex_code)
        band = self.cov_band(1)
        band_display = band if band is not None else "Not Found"
        
        rate_fields = [
            " ", "Policy", "Ben Index", "Benefit Code", "Benefit",
            "IssueAge", "Sex", "Rateclass", "Band", "Scale",
            " ", "MTP", "CTP"
        ]
        
        rate_info = [
            " ", self.policy_number, ben_index,
            ben.benefit_code,
            ben.benefit_type_cd,
            ben_iss_age, sex_display,
            self.renewal_cov_rateclass_by_cov(1),
            band_display, scale,
            " ", mtp if mtp else "", ctp if ctp else ""
        ]
        
        max_meta = max(len(rate_fields), len(rate_info))
        xmax = max(xmax, max_meta)
        
        columns = ["RateFields", "RateInfo", "Date", "Age", "Year", "COI"]
        matrix = [columns]
        
        for row in range(1, xmax + 1):
            row_data = []
            for col_idx, col_name in enumerate(columns):
                if col_name == "RateFields":
                    row_data.append(rate_fields[row] if row < len(rate_fields) else "")
                elif col_name == "RateInfo":
                    row_data.append(rate_info[row] if row < len(rate_info) else "")
                elif col_name == "Date":
                    try:
                        base_date = ben_iss_date or issue_date_cov1
                        dt = base_date + relativedelta(years=row - 1)
                        row_data.append(dt.strftime("%m/%d/%Y"))
                    except Exception:
                        row_data.append("")
                elif col_name == "Age":
                    row_data.append(ben_iss_age + row - 1 if ben_iss_age else "")
                elif col_name == "Year":
                    row_data.append(row)
                elif col_name == "COI":
                    if ben_coi and row < len(ben_coi):
                        row_data.append(ben_coi[row])
                    else:
                        row_data.append("NA" if ben_coi is None else "")
            matrix.append(row_data)
        
        return matrix

    def build_policy_rate_matrix(self, scale: int = 1) -> Optional[List[List]]:
        """
        Build rate matrix for policy-level rates, matching VBA LoadULPolicyRatesToRecordset.
        
        Returns a 2D list where:
          - Row 0 = column headers (RateFields, RateInfo, Date, Year, AttainedAge, TPP, EPP, MFEE, CORR)
          - Rows 1..N = data rows by policy year
          
        Args:
            scale: Rate scale (default 1)
            
        Returns:
            2D list suitable for table display, or None if rates unavailable
        """
        from dateutil.relativedelta import relativedelta
        
        issue_date = self.cov_issue_date(1)
        maturity_date = self.cov_maturity_date(1)
        issue_age = self.cov_issue_age(1)
        
        if issue_date is None or issue_age is None:
            return None
        
        if maturity_date and maturity_date > issue_date:
            xmax = (maturity_date.year - issue_date.year)
        else:
            xmax = 100 - issue_age
        
        # Get rate arrays
        tpp = self.rates_tpp(scale)
        epp = self.rates_epp(scale)
        mfee = self.rates_mfee(scale)
        corr = self.rates_corr()
        
        # Get sex/rateclass/band from Cov 1
        sex_code = self.renewal_cov_sex_code(1)
        sex_display = self._translate_sex_for_rates(sex_code)
        band = self.cov_band(1)
        band_display = band if band is not None else "Not Found"
        
        rate_fields = [
            " ", "Policy", "Product", "Plancode", "IssueDate",
            "IssueAge", "Sex", "Rateclass", "Band", "Scale"
        ]
        
        rate_info = [
            " ", self.policy_number, self.product_type,
            self.cov_plancode(1),
            issue_date.strftime("%Y-%m-%d") if issue_date else "",
            issue_age, sex_display,
            self.renewal_cov_rateclass_by_cov(1),
            band_display, scale
        ]
        
        max_meta = max(len(rate_fields), len(rate_info))
        xmax = max(xmax, max_meta)
        
        columns = ["RateFields", "RateInfo", "Date", "Year", "AttainedAge", "TPP", "EPP", "MFEE", "CORR"]
        matrix = [columns]
        
        for row in range(1, xmax + 1):
            row_data = []
            for col_idx, col_name in enumerate(columns):
                if col_name == "RateFields":
                    row_data.append(rate_fields[row] if row < len(rate_fields) else "")
                elif col_name == "RateInfo":
                    row_data.append(rate_info[row] if row < len(rate_info) else "")
                elif col_name == "Date":
                    try:
                        dt = issue_date + relativedelta(years=row - 1)
                        row_data.append(dt.strftime("%m/%d/%Y"))
                    except Exception:
                        row_data.append("")
                elif col_name == "Year":
                    row_data.append(row)
                elif col_name == "AttainedAge":
                    row_data.append(issue_age + row - 1)
                elif col_name == "TPP":
                    if tpp and row < len(tpp):
                        row_data.append(tpp[row])
                    else:
                        row_data.append("NA" if tpp is None else "")
                elif col_name == "EPP":
                    if epp and row < len(epp):
                        row_data.append(epp[row])
                    else:
                        row_data.append("NA" if epp is None else "")
                elif col_name == "MFEE":
                    if mfee and row < len(mfee):
                        row_data.append(mfee[row])
                    else:
                        row_data.append("NA" if mfee is None else "")
                elif col_name == "CORR":
                    if corr and row < len(corr):
                        row_data.append(corr[row])
                    else:
                        row_data.append("NA" if corr is None else "")
            matrix.append(row_data)
        
        return matrix


    # =========================================================================
    # INFORCE DICTIONARY (VBA-compatible export)
    # =========================================================================
    
    def to_inforce_dict(self) -> Dict[str, Any]:
        """
        Export policy data as an inforce dictionary - similar to VBA InforceDictionary.
        Useful for integration with external systems.
        """
        return {
            "Policy": {
                "Policynumber": self.policy_number,
                "CompanyCode": self.company_code,
                "Company": self.company_name,
                "StatusCode": self.status_code,
                "MarketOrg": self.servicing_market_org,
                "ProductType": self.product_type,
                "IsFFS": self.is_ffs,
                "BillablePremium": float(self.regular_premium or 0),
                "BillingMode": self.billing_mode,
                "GPEDate": str(self.grace_period_expiry_date) if self.grace_period_expiry_date else "",
                "IssueState": self.issue_state,
                "DBOption": self.db_option_code,
                "MTP": float(self.mtp or 0),
                "CTP": float(self.ctp or 0),
                "GLP": float(self.glp or 0),
                "GSP": float(self.gsp or 0),
                "AccumGLP": float(self.accumulated_glp_target or 0),
                "AccumMTP": float(self.accumulated_mtp_target or 0),
                "RegLoanPrincipal": float(self.total_regular_loan_principal),
                "RegLoanAccrued": float(self.total_regular_loan_accrued),
                "PrefLoanPrincipal": float(self.total_preferred_loan_principal),
                "PrefLoanAccrued": float(self.total_preferred_loan_accrued),
                "VarLoanPrincipal": float(self.total_variable_loan_principal),
                "VarLoanAccrued": float(self.total_variable_loan_accrued),
                "CostBasis": float(self.cost_basis or 0),
                "IsMEC": self.is_mec,
                "ValuationDate": str(self.valuation_date) if self.valuation_date else "",
                "MVAV": float(self.mv_av() or 0),
                "TotalAV": float(self.total_fund_value),
                "TotalSpecifiedAmount": float(self.total_specified_amount),
            },
            "Funds": self.get_fund_values_dict(),
            "PremAllocation": self.get_premium_allocation_dict(),
            "BaseCovs": [c.raw_data for c in self.get_coverages() if c.is_base],
            "RiderCovs": [c.raw_data for c in self.get_coverages() if not c.is_base],
            "Benefits": [b.raw_data for b in self.get_benefits()],
        }

    # =========================================================================
    # INTERNAL METHODS  (delegated to PolicyData)
    # =========================================================================

    @staticmethod
    def _parse_date(value) -> Optional[date]:
        """Parse a date value from DB2."""
        return _PolicyData.parse_date(value)

    @staticmethod
    def _parse_optional_decimal(value) -> Optional[Decimal]:
        """Parse an optional DB number without treating zero as missing."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return Decimal(str(value))

    @staticmethod
    def _parse_optional_int(value) -> Optional[int]:
        """Parse an optional DB integer, preserving zero as a valid value."""
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return int(value)

    @staticmethod
    def find_companies(policy_number: str, region: str = "CKPR",
                       system_code: str = "I") -> List[str]:
        """Find all company codes that have this policy number."""
        return _PolicyData.find_companies(policy_number, region, system_code)

    def refresh(self):
        """Clear all caches and reload from database."""
        # Clear business-object caches
        self._coverages = None
        self._benefits = None
        self._agents = None
        self._loans = None
        self._mv_values = None
        self._activities = None
        self._band_cache.clear()
        # Delegate table-cache refresh to PolicyData
        self._data.refresh()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert key policy info to dictionary."""
        return {
            "policy_number": self.policy_number,
            "company_code": self.company_code,
            "company_name": self.company_name,
            "region": self.region,
            "status": f"{self.status_code} - {self.status_description}",
            "suspense": f"{self.suspense_code} - {self.suspense_description}",
            "issue_date": str(self.issue_date) if self.issue_date else "",
            "paid_to_date": str(self.paid_to_date) if self.paid_to_date else "",
            "base_plancode": self.base_plancode,
            "base_face_amount": str(self.base_face_amount) if self.base_face_amount else "",
            "product_type": self.product_type,
            "is_advanced_product": self.is_advanced_product,
            "billing_mode": self.billing_mode,
            "regular_premium": str(self.regular_premium) if self.regular_premium else "",
            "cash_surrender_value": str(self.cash_surrender_value) if self.cash_surrender_value else "",
            "total_loan_balance": str(self.total_loan_balance),
            "is_mec": self.is_mec,
        }
    
    def __repr__(self):
        return f"PolicyInformation('{self.policy_number}', region='{self.region}', company='{self.company_code}')"
    
    def __str__(self):
        if self.exists:
            return f"Policy {self.policy_number} ({self.company_name}) - {self.status_description}"
        return f"Policy {self.policy_number} - NOT FOUND"


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def load_policy(
    policy_number: str,
    region: str = "CKPR",
    company_code: str = None,
    system_code: str = "I"
) -> PolicyInformation:
    """
    Convenience function to load a policy.
    
    Raises:
        PolicyNotFoundError: If policy doesn't exist
    """
    pol = PolicyInformation(policy_number, company_code, system_code, region)
    if not pol.exists:
        raise PolicyNotFoundError(pol.last_error)
    return pol


def close_all_connections():
    """Close all database connections (both PolicyInformation and shared pools)."""
    _ConnectionManager().close_all()
    _DB2Connection.close_all()
