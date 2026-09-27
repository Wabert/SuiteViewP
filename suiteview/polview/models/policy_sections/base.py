"""Shared helpers for PolicyInformation section objects."""

from __future__ import annotations

from decimal import Decimal

from ..policy_data import PolicyData as _PolicyData


class PolicySection:
    """Base object for one cohesive PolicyInformation section."""

    CACHE_ATTRS: tuple[str, ...] = ()

    def __init__(self, policy):
        self._policy = policy
        for name in self.CACHE_ATTRS:
            setattr(self, name, None)

    @property
    def policy(self):
        return self._policy

    @property
    def status(self):
        return self.policy.status

    @property
    def product(self):
        return self.policy.product

    @property
    def billing(self):
        return self.policy.billing

    @property
    def coverages(self):
        return self.policy.coverages

    @property
    def benefits(self):
        return self.policy.benefits

    @property
    def loans(self):
        return self.policy.loans

    @property
    def values(self):
        return self.policy.values

    @property
    def targets(self):
        return self.policy.targets

    @property
    def dividends(self):
        return self.policy.dividends

    @property
    def persons(self):
        return self.policy.persons

    @property
    def agents(self):
        return self.policy.agents

    @property
    def activity(self):
        return self.policy.activity

    @property
    def rates(self):
        return self.policy.rates

    @property
    def support(self):
        return self.policy.support

    def data_item(self, *args, **kwargs):
        return self.policy.data_item(*args, **kwargs)

    def data_item_array(self, *args, **kwargs):
        return self.policy.data_item_array(*args, **kwargs)

    def data_item_count(self, *args, **kwargs):
        return self.policy.data_item_count(*args, **kwargs)

    def fetch_table(self, *args, **kwargs):
        return self.policy.fetch_table(*args, **kwargs)

    def cached_table(self, *args, **kwargs):
        return self.policy.cached_table(*args, **kwargs)

    def table_error(self, *args, **kwargs):
        return self.policy.table_error(*args, **kwargs)

    def if_empty(self, *args, **kwargs):
        return self.policy.if_empty(*args, **kwargs)

    def find_row_index(self, *args, **kwargs):
        return self.policy.find_row_index(*args, **kwargs)

    def data_item_where(self, *args, **kwargs):
        return self.policy.data_item_where(*args, **kwargs)

    def data_item_where_multi(self, *args, **kwargs):
        return self.policy.data_item_where_multi(*args, **kwargs)

    def data_items_where(self, *args, **kwargs):
        return self.policy.data_items_where(*args, **kwargs)

    def get_rows_where(self, *args, **kwargs):
        return self.policy.get_rows_where(*args, **kwargs)

    def field_value(self, *args, **kwargs):
        return self.policy.field_value(*args, **kwargs)

    def _field(self, *args, **kwargs):
        return self.policy._field(*args, **kwargs)

    @staticmethod
    def _parse_date(value):
        """Parse a date value from DB2."""
        return _PolicyData.parse_date(value)

    @staticmethod
    def _parse_optional_decimal(value) -> Decimal | None:
        """Parse an optional DB number without treating zero as missing."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return Decimal(str(value))

    @staticmethod
    def _parse_optional_int(value) -> int | None:
        """Parse an optional DB integer, preserving zero as a valid value."""
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return int(value)
