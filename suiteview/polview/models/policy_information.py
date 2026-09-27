"""
SuiteView PolicyInformation facade.

PolicyInformation owns identity, cached DB2 PolicyData and section lifecycle.
Policy facts live on cohesive section objects such as ``pi.product`` and
``pi.coverages``; this facade intentionally keeps only cross-section identity,
raw data access and lifecycle helpers.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from suiteview.core.db2_connection import DB2Connection as _DB2Connection
from suiteview.core.data_access.errors import UnknownColumnError

from .cl_polrec import LoanRecords, TotalRecords
from .cl_polrec.policy_data_classes import PolicyNotFoundError
from .cl_polrec.policy_translations import COMPANY_CODES
from .policy_data import PolicyData as _PolicyData, _ConnectionManager
from .policy_fields import FIELD_SPECS_BY_NAME, FieldSpec
from .policy_sections.status import StatusSection
from .policy_sections.product import ProductSection
from .policy_sections.billing import BillingSection
from .policy_sections.coverages import CoveragesSection
from .policy_sections.benefits import BenefitsSection
from .policy_sections.loans import LoansSection
from .policy_sections.values import ValuesSection
from .policy_sections.targets import TargetsSection
from .policy_sections.dividends import DividendsSection
from .policy_sections.persons import PersonsSection
from .policy_sections.agents import AgentsSection
from .policy_sections.activity import ActivitySection
from .policy_sections.rates import RatesSection
from .policy_sections.support import SupportSection


class PolicyInformation:
    """Facade returned by policy service; facts live on section objects."""

    def __init__(
        self,
        policy_number: str,
        company_code: str = None,
        system_code: str = "I",
        region: str = "CKPR",
    ):
        self._data = _PolicyData(policy_number, company_code, system_code, region)
        self._sections: dict[str, object] = {}
        self._rates = None
        self._band_cache: dict[int, Optional[int]] = {}
        self.loan_records = LoanRecords(self)
        self.total_records = TotalRecords(self)

    def _section(self, name: str, factory):
        if not hasattr(self, "_sections"):
            self._sections = {}
        section = self._sections.get(name)
        if section is None:
            section = factory(self)
            self._sections[name] = section
        return section

    @property
    def status(self) -> StatusSection:
        return self._section('status', StatusSection)

    @property
    def product(self) -> ProductSection:
        return self._section('product', ProductSection)

    @property
    def billing(self) -> BillingSection:
        return self._section('billing', BillingSection)

    @property
    def coverages(self) -> CoveragesSection:
        return self._section('coverages', CoveragesSection)

    @property
    def benefits(self) -> BenefitsSection:
        return self._section('benefits', BenefitsSection)

    @property
    def loans(self) -> LoansSection:
        return self._section('loans', LoansSection)

    @property
    def values(self) -> ValuesSection:
        return self._section('values', ValuesSection)

    @property
    def targets(self) -> TargetsSection:
        return self._section('targets', TargetsSection)

    @property
    def dividends(self) -> DividendsSection:
        return self._section('dividends', DividendsSection)

    @property
    def persons(self) -> PersonsSection:
        return self._section('persons', PersonsSection)

    @property
    def agents(self) -> AgentsSection:
        return self._section('agents', AgentsSection)

    @property
    def activity(self) -> ActivitySection:
        return self._section('activity', ActivitySection)

    @property
    def rates(self) -> RatesSection:
        return self._section('rates', RatesSection)

    @property
    def support(self) -> SupportSection:
        return self._section('support', SupportSection)

    def cached_reads_only(self):
        """Guard UI rendering against missing/failed prefetches."""
        return self._data.cached_reads_only()

    def detached_copy(self) -> "PolicyInformation":
        """Produce independent plain-data state for handoff to another thread."""
        clone = object.__new__(type(self))
        clone._data = self._data.detached_copy()
        clone._sections = {}
        clone._rates = None
        clone._band_cache = deepcopy(self._band_cache)
        clone.loan_records = LoanRecords(clone)
        clone.total_records = TotalRecords(clone)
        return clone

    def merge_prefetched(self, snapshot: "PolicyInformation") -> None:
        """Merge a detached snapshot while preserving this GUI policy identity."""
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
        # Every section cache built against older rows must be rebuilt; the
        # sections rebuild lazily from the merged table cache.
        self._sections.clear()
        self.loan_records.invalidate()
        self.total_records.invalidate()
        self._band_cache.clear()

    @property
    def exists(self) -> bool:
        return self._data.exists

    @property
    def cancelled(self) -> bool:
        return self._data.cancelled

    @property
    def last_error(self) -> str:
        return self._data.last_error

    @property
    def available_companies(self) -> List[str]:
        return self._data.available_companies

    def data_item(self, table_name: str, field_name: str, index: int = 0) -> Any:
        return self._data.data_item(table_name, field_name, index)

    def data_item_array(self, table_name: str, field_name: str) -> List[Any]:
        return self._data.data_item_array(table_name, field_name)

    def data_item_count(self, table_name: str) -> int:
        return self._data.data_item_count(table_name)

    def fetch_table(self, table_name: str) -> list:
        return self._data.fetch_table(table_name)

    def cached_table(self, table_name: str):
        return self._data.cached_table(table_name)

    def table_error(self, table_name: str):
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

    def _field(self, name: str, index: int = 0):
        spec: FieldSpec = FIELD_SPECS_BY_NAME[name]
        try:
            return self.data_item(spec.table, spec.column, index)
        except UnknownColumnError:
            if spec.optional:
                return spec.default
            raise

    def field_value(self, name: str, index: int = 0):
        return self._field(name, index)

    @property
    def policy_number(self) -> str:
        return self._data.policy_number

    @property
    def policy_id(self) -> str:
        """Technical policy ID (TCH_POL_ID)."""
        return self._data.policy_id or ""

    @property
    def company_code(self) -> str:
        return self._data.company_code or ""

    @property
    def company_name(self) -> str:
        return COMPANY_CODES.get(self.company_code, self.company_code)

    @property
    def system_code(self) -> str:
        return self._data.system_code

    @property
    def region(self) -> str:
        return self._data.region

    @staticmethod
    def _parse_date(value) -> Optional[date]:
        return _PolicyData.parse_date(value)

    @staticmethod
    def _parse_optional_decimal(value) -> Optional[Decimal]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return Decimal(str(value))

    @staticmethod
    def _parse_optional_int(value) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return int(value)

    @staticmethod
    def find_companies(
        policy_number: str, region: str = "CKPR", system_code: str = "I",
    ) -> List[str]:
        return _PolicyData.find_companies(policy_number, region, system_code)

    def refresh(self):
        self._sections.clear()
        self._band_cache.clear()
        self.loan_records.invalidate()
        self.total_records.invalidate()
        self._data.refresh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_number": self.policy_number,
            "company_code": self.company_code,
            "company_name": self.company_name,
            "region": self.region,
            "status": f"{self.status.status_code} - {self.status.status_description}",
            "suspense": f"{self.status.suspense_code} - {self.status.suspense_description}",
            "issue_date": str(self.activity.issue_date) if self.activity.issue_date else "",
            "paid_to_date": str(self.activity.paid_to_date) if self.activity.paid_to_date else "",
            "base_plancode": self.coverages.base_plancode,
            "base_face_amount": str(self.coverages.base_face_amount) if self.coverages.base_face_amount else "",
            "product_type": self.product.product_type,
            "is_advanced_product": self.product.is_advanced_product,
            "billing_mode": self.billing.billing_mode,
            "regular_premium": str(self.billing.regular_premium) if self.billing.regular_premium else "",
            "cash_surrender_value": str(self.values.cash_surrender_value) if self.values.cash_surrender_value else "",
            "total_loan_balance": str(self.loans.total_loan_balance),
            "is_mec": self.values.is_mec,
        }

    def __repr__(self):
        return (
            f"PolicyInformation('{self.policy_number}', region='{self.region}', "
            f"company='{self.company_code}')"
        )

    def __str__(self):
        if self.exists:
            return (
                f"Policy {self.policy_number} ({self.company_name}) - "
                f"{self.status.status_description}"
            )
        return f"Policy {self.policy_number} - NOT FOUND"


def load_policy(
    policy_number: str,
    region: str = "CKPR",
    company_code: str = None,
    system_code: str = "I",
) -> PolicyInformation:
    """Convenience function to load a policy."""
    pol = PolicyInformation(policy_number, company_code, system_code, region)
    if not pol.exists:
        raise PolicyNotFoundError(pol.last_error)
    return pol


def close_all_connections():
    """Close all database connections (both PolicyInformation and shared pools)."""
    _ConnectionManager().close_all()
    _DB2Connection.close_all()
