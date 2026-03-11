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

from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import date, datetime
from decimal import Decimal

# Import from cl_polrec package (single source of truth)
from .cl_polrec.policy_translations import (
    STATUS_CODES, PREMIUM_PAY_STATUS_CODES, SUSPENSE_CODES, PRODUCT_LINE_CODES,
    SEX_CODES, SEX_CODE_DISPLAY, RATE_CLASS_CODES, BILLING_MODE_CODES,
    NON_STANDARD_BILL_MODE_CODES, DEF_OF_LIFE_INS_CODES, DB_OPTION_CODES,
    DIV_OPTION_CODES, NFO_CODES, PERSON_CODES, COMPANY_CODES,
    LOAN_TYPE_CODES,
    translate_state_code, translate_table_rating,
    translate_fund_id, translate_transaction_code, translate_market_org,
    translate_loan_interest_type_code, translate_loan_interest_status_code,
    translate_div_type_code, translate_renewal_rate_type_code,
    translate_elimination_period_code, translate_benefit_period_code,
    translate_substandard_type_code, translate_coverage_target_type,
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
    BasePolicyRecords, LoanRecords, TotalRecords,
)

# Use the shared database connection module instead of a duplicate manager
from suiteview.core.db2_connection import DB2Connection as _DB2Connection

# Data access layer — PolicyData owns DB2 access and table caching
from .policy_data import PolicyData as _PolicyData, _ConnectionManager

# Import Rates class for rate lookups
try:
    from suiteview.core.rates import Rates
except ImportError:
    Rates = None  # type: ignore[assignment,misc]

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
        # (59 refs to base_records, 32 refs to loan_records, 17 refs to total_records)
        self.base_records = BasePolicyRecords(self)
        self.loan_records = LoanRecords(self)
        self.total_records = TotalRecords(self)
    
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
    # STATUS PROPERTIES (delegated to BasePolicyRecords)
    # =========================================================================
    
    @property
    def status_code(self) -> str:
        """Policy status code."""
        return self.base_records.STS_CD
    
    @property
    def status_description(self) -> str:
        """Policy status description."""
        return self.base_records.status_description
    
    @property
    def suspense_code(self) -> str:
        """Suspense code."""
        return self.base_records.SUS_CD
    
    @property
    def suspense_description(self) -> str:
        """Suspense description."""
        return self.base_records.suspense_description
    
    @property
    def premium_pay_status_code(self) -> str:
        """Premium paying status code (PRM_PAY_STA_REA_CD)."""
        return self.base_records.PRM_PAY_STA_REA_CD
    
    @property
    def premium_pay_status_description(self) -> str:
        """Premium paying status description."""
        return self.base_records.premium_pay_status_description
    
    @property
    def is_active(self) -> bool:
        """Whether policy is in active status."""
        return self.base_records.is_active
    
    @property
    def is_suspended(self) -> bool:
        """Whether policy is suspended."""
        return self.base_records.is_suspended
    
    @property
    def is_terminated(self) -> bool:
        """Whether policy is terminated (any non-active status)."""
        return self.base_records.is_terminated
    
    @property
    def grace_indicator(self) -> bool:
        """Whether policy is in grace period."""
        return self.base_records.GRC_IND
    
    # =========================================================================
    # DATE PROPERTIES (delegated to BasePolicyRecords)
    # =========================================================================
    
    @property
    def issue_date(self) -> Optional[date]:
        """Policy issue date (falls back to first coverage issue date)."""
        dt = self.base_records.ISSUE_DT
        if dt is None:
            covs = self.get_coverages()
            if covs:
                dt = covs[0].issue_date
        return dt
    
    @property
    def paid_to_date(self) -> Optional[date]:
        """Premium paid-to date."""
        return self.base_records.PAID_TO_DT
    
    @property
    def next_anniversary_date(self) -> Optional[date]:
        """Next policy anniversary date."""
        return self.base_records.NXT_ANV_DT
    
    @property
    def next_monthliversary_date(self) -> Optional[date]:
        """Next monthliversary date."""
        return self.base_records.NXT_MVRY_DT
    
    
    @property
    def terminate_date(self) -> Optional[date]:
        """Policy termination date."""
        return self.base_records.TMN_DT
    
    @staticmethod
    def _completed_date_parts_years(date1: date, date2: date) -> int:
        """Python equivalent of VBA CompletedDateParts("YYYY", date1, date2).
        
        Counts the number of full years between date1 and date2.
        If date2 < date1, the dates are swapped (always returns positive).
        """
        if date1 > date2:
            date1, date2 = date2, date1
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
    # BILLING PROPERTIES (delegated to BasePolicyRecords)
    # =========================================================================
    
    @property
    def billing_frequency(self) -> int:
        """Billing frequency in months."""
        return self.base_records.PMT_FQY_PER
    
    @property
    def billing_mode(self) -> str:
        """Billing mode description."""
        return self.base_records.billing_mode_desc
    
    @property
    def non_standard_mode_code(self) -> str:
        """Non-standard billing mode code (NSD_MD_CD).

        When this field is non-empty, the payment mode is forced to 01 (monthly)
        and the actual billing cadence is indicated by this code:
            1 = Weekly, 2 = Bi-Weekly, 4 = 13thly (every 4 weeks),
            9 = 9thly, A = 10thly, S = Semi-Monthly.
        For bi-weekly and other non-standard modes, the premium in CyberLife
        is still a monthly premium (premiums are deposited into a PDF and
        swept monthly to pay the policy premium).
        """
        return str(self.data_item("LH_BAS_POL", "NSD_MD_CD") or "")
    
    @property
    def bill_day(self) -> int:
        """Billing day of month."""
        return self.base_records.BL_DAY_NBR
    
    @property
    def issue_state_code(self) -> str:
        """Issue state code (raw numeric from ISSUE_ST_CD)."""
        return self.base_records.ISSUE_ST_CD
    
    @property
    def issue_state(self) -> str:
        """Issue state abbreviation (e.g., 'AZ', 'NY')."""
        return self.base_records.issue_state
    
    @property
    def resident_state_code(self) -> str:
        """Resident/premium-paying state code (raw numeric from PRM_PAY_ST_CD)."""
        return self.base_records.PRM_PAY_ST_CD
    
    @property
    def resident_state(self) -> str:
        """Resident/premium-paying state abbreviation (e.g., 'AZ', 'NY')."""
        return self.base_records.resident_state
    
    @property
    def state_code(self) -> str:
        """Alias for issue_state_code (deprecated - use issue_state_code instead)."""
        return self.issue_state_code
    
    # =========================================================================
    # PREMIUM PROPERTIES (delegated to BasePolicyRecords)
    # =========================================================================
    
    @property
    def regular_premium(self) -> Optional[Decimal]:
        """Regular premium amount."""
        return self.base_records.REG_PRM_AMT
    
    @property
    def modal_premium(self) -> Optional[Decimal]:
        """Modal premium (premium per billing period)."""
        return self.base_records.POL_PRM_AMT
    
    @property
    def annual_premium(self) -> Optional[Decimal]:
        """Annualized premium."""
        return self.base_records.annual_premium
    
    @property
    def target_premium(self) -> Optional[Decimal]:
        """Target premium (for UL products)."""
        return self.base_records.TAR_PRM_AMT
    
    @property
    def minimum_premium(self) -> Optional[Decimal]:
        """Minimum premium (for UL products)."""
        return self.base_records.MIN_PRM_AMT
    
    # =========================================================================
    # OPTIONS (delegated to BasePolicyRecords)
    # =========================================================================
    
    @property
    def div_option_code(self) -> str:
        """Dividend option code."""
        return self.base_records.PR_DIV_OPT_CD
    
    @property
    def div_option_description(self) -> str:
        """Dividend option description."""
        return self.base_records.div_option_description
    
    @property
    def nfo_code(self) -> str:
        """Non-forfeiture option code."""
        return self.base_records.NFO_CD
    
    @property
    def nfo_description(self) -> str:
        """Non-forfeiture option description."""
        return self.base_records.nfo_description
    
    @property
    def db_option_code(self) -> str:
        """Death benefit option code."""
        return self.base_records.DTH_BNF_PLN_OPT_CD
    
    @property
    def db_option_description(self) -> str:
        """Death benefit option description."""
        return self.base_records.db_option_description
    
    # =========================================================================
    # CLASSIFICATION (delegated to BasePolicyRecords)
    # =========================================================================
    
    @property
    def is_advanced_product(self) -> bool:
        """Whether this is an advanced product (UL/IUL/VUL)."""
        return self.base_records.NON_TRD_POL_IND
    
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

        # Advanced products — determined by system indicators, not plancode
        # Note: VUL_IND and IUL_IND do not exist on TH_BAS_POL.
        # Product line code is used as the differentiator.
        if self.is_advanced_product:
            prod_line = self.product_line_code
            if prod_line == "I":
                return "ISWL"
            return "UL"

        # DI — determined by product line code
        if self.product_line_code == "S":
            return "DI"

        # ── Official plancode table lookup (primary) ────────────────────
        if _data_lookup is not None:
            group = _data_lookup.get_plancode_group(plancode)
            if group and group != "Not Found":
                return group  # "WL", "TERM", "Trad Rider", etc.

        # ── Fallback: heuristic pattern matching ────────────────────────
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
        """DEFRA indicator."""
        return self.base_records.DEFRA_IND
    
    @property
    def def_of_life_ins_code(self) -> str:
        """Definition of Life Insurance code."""
        return self.base_records.TFDF_CD
    
    @property
    def def_of_life_ins_description(self) -> str:
        """Definition of Life Insurance description."""
        return self.base_records.def_of_life_ins_description
    
    @property
    def guideline_single_premium(self) -> Optional[Decimal]:
        """Guideline Single Premium (GSP)."""
        return self.base_records.GSP_AMT
    
    @property
    def guideline_level_premium(self) -> Optional[Decimal]:
        """Guideline Level Premium (GLP)."""
        return self.base_records.GLP_AMT
    
    # =========================================================================
    # BASE COVERAGE PROPERTIES
    # =========================================================================
    
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
    
    def get_coverages(self) -> List[CoverageInfo]:
        """Get all coverage phases with complete field mapping.
        
        Coverage classification:
        - is_base=True for all coverages sharing the same plancode as COV_PHA_NBR=1
          (for UL products, coverage increases are added as additional base coverages)
        - is_base=False for riders (different plancode from coverage 1)
        
        Substandard ratings (table_rating, flat_extra, flat_cease_date) and
        TH_COV_PHA fields (cv_amount, nsp_amount) are populated during build.

        NOTE: A parallel implementation exists in CL_POLREC_02_03_09_67 mixin
        (uses self._policy accessor pattern).  Any fix applied here MUST also
        be applied there to keep both in sync.
        """
        if self._coverages is not None:
            return self._coverages
        
        self._coverages = []
        
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
            cov_pha_nbr = int(row.get("COV_PHA_NBR", 0))
            plancode = str(row.get("PLN_DES_SER_CD", "")).strip()
            
            # Get units and VPU for calculations
            units = Decimal(str(row["COV_UNT_QTY"])) if row.get("COV_UNT_QTY") else None
            orig_units = Decimal(str(row["OGN_SPC_UNT_QTY"])) if row.get("OGN_SPC_UNT_QTY") else None
            vpu = Decimal(str(row.get("COV_VPU_AMT") or 0))
            if vpu == 0:
                vpu = None
            
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
            flat_extra = None
            flat_cease_date = None
            for r in cov_ratings:
                if r.type_code == "T" and r.table_rating_numeric and r.table_rating_numeric > 0:
                    table_rating = r.table_rating_numeric
                    table_rating_code = r.table_rating or ""
                if r.type_code == "F":
                    if r.flat_amount:
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
                issue_age=int(row.get("INS_ISS_AGE") or 0) or None,
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
                premium_rate=Decimal(str(row["ANN_PRM_UNT_AMT"])) if row.get("ANN_PRM_UNT_AMT") else None,
                nxt_chg_typ_cd=str(row.get("NXT_CHG_TYP_CD", "")),
                nxt_chg_dt=self._parse_date(row.get("NXT_CHG_DT")),
                terminate_date=self._parse_date(row.get("PLN_TMN_DT")),
                is_base=is_base,
                # Total annual premium = per-unit rate × units
                cov_annual_premium=(
                    Decimal(str(row["ANN_PRM_UNT_AMT"])) * units
                    if row.get("ANN_PRM_UNT_AMT") and units is not None
                    else (Decimal(str(row["ANN_PRM_UNT_AMT"])) if row.get("ANN_PRM_UNT_AMT") else None)
                ),
                # Raw per-unit rate (ANN_PRM_UNT_AMT)
                annual_premium_per_unit=Decimal(str(row["ANN_PRM_UNT_AMT"])) if row.get("ANN_PRM_UNT_AMT") else None,
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
                cov.rate_class_desc = RATE_CLASS_CODES.get(rc, "")
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

            self._coverages.append(cov)
        
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
                
                # Get units and VPU for amount calculation
                units = Decimal(str(row["BNF_UNT_QTY"])) if row.get("BNF_UNT_QTY") else None
                vpu = Decimal(str(row["BNF_VPU_AMT"])) if row.get("BNF_VPU_AMT") else None
                benefit_amount = (units * vpu) if (units is not None and vpu is not None) else None
                
                ben = BenefitInfo(
                    cov_pha_nbr=int(row.get("COV_PHA_NBR", 0)),
                    benefit_code=benefit_code,
                    benefit_type_cd=type_cd,
                    benefit_subtype_cd=subtype_cd,
                    benefit_desc=type_cd,  # Type code is the primary descriptor
                    form_number=str(row.get("BNF_FRM_NBR", "")).strip(),
                    issue_date=self._parse_date(row.get("BNF_ISS_DT")),
                    cease_date=self._parse_date(row.get("BNF_CEA_DT")),
                    orig_cease_date=self._parse_date(row.get("BNF_OGN_CEA_DT")),
                    units=units,
                    vpu=vpu,
                    benefit_amount=benefit_amount,
                    issue_age=int(row["BNF_ISS_AGE"]) if row.get("BNF_ISS_AGE") else None,
                    rating_factor=Decimal(str(row["BNF_RT_FCT"])) if row.get("BNF_RT_FCT") else None,
                    renewal_indicator=str(row.get("RNL_RT_IND", "")).strip(),
                    coi_rate=Decimal(str(row["BNF_ANN_PPU_AMT"])) if row.get("BNF_ANN_PPU_AMT") else None,
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
        return self.total_records.DTH_BNF_AMT
    
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
    # ADVANCED DATE PROPERTIES (delegated to BasePolicyRecords)
    # =========================================================================
    
    @property
    def last_anniversary(self) -> Optional[date]:
        """Last policy anniversary date."""
        return self.base_records.LST_ANV_DT
    
    @property
    def next_monthliversary(self) -> Optional[date]:
        """Next monthliversary processing date."""
        return self.base_records.NXT_MVRY_PRC_DT
    
    @property
    def last_financial_date(self) -> Optional[date]:
        """Last financial processing date."""
        return self.base_records.LST_FIN_DT
    
    @property
    def next_bill_date(self) -> Optional[date]:
        """Next billing date."""
        return self.base_records.NXT_BIL_DT
    
    @property
    def premium_paid_to_date(self) -> Optional[date]:
        """Premium paid-to date."""
        return self.base_records.PRM_BILL_TO_DT
    
    @property
    def valuation_date(self) -> Optional[date]:
        """
        Get valuation date - MV date for UL, NextMonthliversary-1 for traditional.
        """
        if self.is_advanced_product:
            mv_dt = self._parse_date(self.data_item("LH_POL_MVRY_VAL", "MVRY_DT"))
            if mv_dt:
                return mv_dt
        
        next_mv = self.next_monthliversary
        if next_mv:
            from datetime import timedelta
            return next_mv - timedelta(days=30)  # Approximate previous month
        
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
    # ADDITIONAL POLICY PROPERTIES (delegated to BasePolicyRecords)
    # =========================================================================
    
    @property
    def original_entry_code(self) -> str:
        """Original entry code."""
        return self.base_records.OGN_ETR_CD
    
    @property
    def last_entry_code(self) -> str:
        """Last entry code."""
        return self.base_records.LST_ETR_CD
    
    @property
    def policy_1035_indicator(self) -> bool:
        """Whether policy involved a 1035 exchange."""
        return self.base_records.POL_1035_XCG_IND
    
    @property
    def servicing_agent_number(self) -> str:
        """Servicing agent number."""
        return self.base_records.SVC_AGT_NBR
    
    @property
    def servicing_branch_code(self) -> str:
        """Servicing branch/agency code."""
        return self.base_records.SVC_AGC_NBR
    
    @property
    def servicing_market_org(self) -> str:
        """Determine market organization from company and agent codes."""
        return self.base_records.servicing_market_org
    
    @property
    def agency_branch_code(self) -> str:
        """Extract agency branch code from servicing branch code."""
        return self.base_records.agency_branch_code
    
    @property
    def is_ffs(self) -> bool:
        """Whether policy is Fee-for-Service (IMG with specific branch)."""
        return self.servicing_market_org == "IMG" and self.agency_branch_code == "0B4Q"
    
    @property
    def policy_loan_charge_rate(self) -> Optional[Decimal]:
        """Policy loan charge interest rate."""
        return self.base_records.LN_PLN_ITS_RT
    
    @property
    def forced_premium_indicator(self) -> bool:
        """Whether policy has forced premium."""
        return self.base_records.FORCED_PREM_IND
    
    @property
    def mdo_code(self) -> str:
        """MDO (market/distribution) code."""
        return self.base_records.USR_RES_CD
    
    @property
    def bill_form_code(self) -> str:
        """Billing form code."""
        return self.base_records.BIL_FRM_CD

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
    def policy_debt(self) -> Decimal:
        """Total policy debt (all loans principal + interest)."""
        return self.loan_records.policy_debt
    
    @property
    def preferred_loans_available(self) -> bool:
        """Whether preferred loans are available on this policy."""
        return self.loan_records.preferred_loans_available
    
    # =========================================================================
    # NON-TRAD POLICY PROPERTIES (delegated to BasePolicyRecords)
    # =========================================================================
    
    @property
    def guaranteed_interest_rate(self) -> Optional[Decimal]:
        """Guaranteed interest rate for advanced products."""
        return self.base_records.POL_GUA_ITS_RT
    
    @property
    def corridor_percent(self) -> Optional[Decimal]:
        """Corridor percentage for death benefit calculation."""
        return self.base_records.CDR_PCT
    
    @property
    def grace_rule_code(self) -> str:
        """Grace period rule code."""
        return self.base_records.GRA_THD_RLE_CD
    
    @property
    def tefra_defra_code(self) -> str:
        """TEFRA/DEFRA indicator code."""
        return self.base_records.NON_TRD_TFDF_CD
    
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
        return self._parse_date(self.data_item("LH_TAMRA_7_PY_PER", "SVPY_PER_STR_DT"))
    
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
    def is_joint_insured(self) -> bool:
        """Whether policy has a joint insured (person code 01)."""
        for i in range(self.person_count):
            if self.person_code(i) == "01":
                return True
        return False
    
    @property
    def primary_insured_name(self) -> str:
        """Primary insured full name."""
        idx = self.person_index("00", 1)
        if idx is not None:
            return self.person_full_name(idx)
        return ""
    
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
        for row in self.fetch_table("LH_COV_INS_RNL_RT"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if cov_pha_nbr is not None and phase != cov_pha_nbr:
                continue
            
            rate_type = str(row.get("PRM_RT_TYP_CD", "") or "")
            rate = RenewalCovRateInfo(
                coverage_phase=phase,
                rate_type=rate_type,
                rate_type_desc=translate_renewal_rate_type_code(rate_type),
                joint_indicator=str(row.get("JT_INS_IND", "") or ""),
                rate_class=str(row.get("RT_CLS_CD", "") or ""),
                rate_class_desc=RATE_CLASS_CODES.get(str(row.get("RT_CLS_CD", "") or ""), ""),
                issue_age=int(row["ISS_AGE"]) if row.get("ISS_AGE") else None,  # TODO: verify column name
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
                issue_age=int(row["ISS_AGE"]) if row.get("ISS_AGE") else None,
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
    
    def get_transactions(self, limit: int = None) -> List[TransactionInfo]:
        """Get transaction records from FH_FIXED, ordered by date descending."""
        transactions = []
        count = 0
        for row in self.fetch_table("FH_FIXED"):
            if limit and count >= limit:
                break
            
            trans_type = str(row.get("TRN_TYP_CD", "") or "")
            trans_subtype = str(row.get("TRN_SBY_CD", "") or "")
            trans_code = trans_type + trans_subtype
            
            trans = TransactionInfo(
                trans_date=self._parse_date(row.get("ASOF_DT")),
                trans_code=trans_code,
                trans_type=trans_type,
                trans_subtype=trans_subtype,
                trans_desc=translate_transaction_code(trans_code),
                gross_amount=Decimal(str(row["TOT_TRS_AMT"])) if row.get("TOT_TRS_AMT") else None,
                net_amount=Decimal(str(row["ACC_VAL_GRS_AMT"])) if row.get("ACC_VAL_GRS_AMT") else None,
                sequence_number=int(row.get("SEQ_NO", 0) or 0),
                fund_id=str(row.get("FND_ID_CD", "") or ""),
                coverage_phase=int(row.get("COV_PHA_NBR", 0) or 0),
                raw_data=row
            )
            transactions.append(trans)
            count += 1
        return transactions
    
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
        """Total specified amount across all base coverages."""
        total = Decimal("0")
        for cov in self.get_base_coverages():
            if cov.face_amount:
                total += cov.face_amount
        return total
    
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
                flat_amount=Decimal(str(row["XTR_PER_1000_AMT"])) if row.get("XTR_PER_1000_AMT") else None,
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
    def surrender_target(self) -> Optional[Decimal]:
        """Surrender target from LH_COV_TARGET (TAR_TYP_CD = 'SU')."""
        val = self.data_item_where("LH_COV_TARGET", "TAR_VAL_AMT", "TAR_TYP_CD", "SU")
        return Decimal(str(val)) if val else None

    # =========================================================================
    # RATES LOOKUP METHODS (cls_PolicyInformation RATES_xxxx functions)
    # =========================================================================
    
    def _get_rates(self) -> Optional['Rates']:
        """Get or create Rates instance for rate lookups."""
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
        idx = self.cov_renewal_index(cov_index, "C", str(joint_ind))
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
        idx = self.cov_renewal_index(cov_index, "C", str(joint_ind))
        if idx >= 0:
            return str(self.data_item("LH_COV_INS_RNL_RT", "RT_CLS_CD", idx) or "")
        return ""
    
    def cov_band(self, cov_index: int) -> Optional[int]:
        """
        Get face amount band for coverage.
        
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
        
        plancode = self.cov_plancode(cov_index)
        total_face = float(self.total_specified_amount or 0)
        
        band = rates.get_band(plancode, total_face)
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
            band=band
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

    def build_coverage_rate_matrix(self, cov_index: int, scale: int = 1) -> Optional[List[List]]:
        """
        Build rate matrix for a coverage, matching VBA LoadULCoverageRatesToRecordset.
        
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
        from datetime import date as date_type
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
            str(self.cov_amount(cov_index) or ""),
            str(self.cov_orig_amount(cov_index) or ""),
            band_display, self.cov_table_rating(cov_index),
            str(flat_extra or 0), flat_duration,
            " ", mtp, ctp, tbl1_mtp, tbl1_ctp,
            " ", " ", " "
        ]
        
        # Ensure metadata lists are same length
        max_meta = max(len(rate_fields), len(rate_info))
        xmax = max(xmax, max_meta)
        
        # Build the matrix
        columns = ["RateFields", "RateInfo", "Date", "Age", "Year", "COI", "EPU", "SCR", "GuarCOI", "GuarEPU"]
        matrix = [columns]  # Row 0 = headers
        
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
            matrix.append(row_data)
        
        return matrix

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
        from datetime import date as date_type
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
        from datetime import date as date_type
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

