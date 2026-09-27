"""policy_attr/policy_hasattr read facts from PolicyInformation sections or flat objects."""

from types import SimpleNamespace

import pytest

from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.models.policy_sections.lookup import (
    MEMBER_SECTION,
    policy_attr,
    policy_hasattr,
)


def _policy_information_with_product_type(value: str) -> PolicyInformation:
    pi = object.__new__(PolicyInformation)
    pi._sections = {"product": SimpleNamespace(product_type=value)}
    return pi


def test_member_map_covers_moved_facts():
    assert MEMBER_SECTION["product_type"] == "product"
    assert MEMBER_SECTION["valuation_date"] == "values"
    assert MEMBER_SECTION["get_coverages"] == "coverages"
    assert MEMBER_SECTION["reins_partner"] == "support"
    assert MEMBER_SECTION["build_coverage_rate_matrix"] == "rates"


def test_policy_information_reads_through_its_section():
    pi = _policy_information_with_product_type("UL")
    assert policy_attr(pi, "product_type") == "UL"
    assert policy_attr(pi, "product_type", "") == "UL"
    assert policy_hasattr(pi, "product_type")


def test_flat_snapshot_attribute_wins():
    flat = SimpleNamespace(product_type="WL", product=SimpleNamespace(product_type="UL"))
    assert policy_attr(flat, "product_type") == "WL"


def test_missing_fact_uses_default_or_raises():
    flat = SimpleNamespace()
    assert policy_attr(flat, "product_type", "") == ""
    assert not policy_hasattr(flat, "product_type")
    with pytest.raises(AttributeError):
        policy_attr(flat, "product_type")


def test_non_section_holder_with_a_section_name_is_ignored():
    snapshot = SimpleNamespace(coverages=[1, 2])
    assert policy_attr(snapshot, "base_rate_class", "N") == "N"
